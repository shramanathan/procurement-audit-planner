"""Runs the full Skills + Agents pipeline for the web app, one run at a time.

Each run gets its own folder (a copy of the project: CLAUDE.md, .claude/,
data/, scripts/checks/) and goes through the stages in CLAUDE.md:

  rules     main session runs the extract-rules skill
  evidence  spend-analyst and findings-analyst, in parallel
  register  risk-assessor builds the register
  decisions HUMAN: the auditor fills the decision form; the risk-assessor
            applies it as a revision; repeats until build_pack.py --gate opens
  team      planner, challenger and qa-reviewer; this module is the lead and
            relays their messages word for word (headless Claude Code can't
            keep background teammates alive, so each agent runs in its own
            resumable session)
  signoff   HUMAN: the auditor signs review.md

Every Claude Code call is `claude -p` with a dollar cap; the run stops when
its budget (RUN_BUDGET_USD) is spent.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = Path(os.environ.get("RUNS_DIR", ROOT / "runs"))
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")
MODEL = os.environ.get("CLAUDE_MODEL", "").strip()
BUDGET = float(os.environ.get("RUN_BUDGET_USD", "40"))
CALL_TIMEOUT = int(os.environ.get("CALL_TIMEOUT_S", "3600"))
MAX_TEAM_TURNS = 30
MAX_REVISIONS = 6
TEAM = ["planner", "challenger", "qa-reviewer"]

STAGES = [
    ("rules", "Extract the rules (extract-rules skill)"),
    ("evidence", "Analyse spend and audit history (spend-analyst, findings-analyst)"),
    ("register", "Rate the risks (risk-assessor)"),
    ("decisions", "Auditor decisions (you), applied as revisions"),
    ("team", "Agent team builds and checks the pack"),
    ("signoff", "Auditor sign-off (you)"),
]
ACTIVE = {"running"}

UNATTENDED = (
    "This is an unattended run started from the web app. No human is available until the auditor "
    "steps (the decision form and the sign-off form). Don't ask questions: where CLAUDE.md says to "
    "ask, use the documented default and say so in your report. Missing or malformed input still "
    "means stop and report."
)
TEAM_NOTE = (
    "Team messaging in this web run: the lead is a script that relays messages word for word. "
    "SendMessage is not available, so don't call it. Write each message you would send as its own "
    "block in your reply, starting on a new line with `TO <recipient>:` (recipient is planner, "
    "challenger, qa-reviewer or main) followed by the message. Several blocks per reply are fine. "
    "When you're waiting for a teammate, end your reply; the lead resumes you with their messages, "
    "each starting `From <name>:`."
)

_lock = threading.Lock()      # guards the single active run
_active: str | None = None
_state_locks: dict[str, threading.Lock] = {}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def redact(s: str) -> str:
    for k in ("ANTHROPIC_API_KEY", "ACCESS_CODES"):
        v = os.environ.get(k, "")
        for part in [v] + v.split(","):
            part = part.strip()
            if len(part) >= 6:
                s = s.replace(part, "[redacted]")
    return s


class BudgetSpent(Exception):
    pass


class StageFailed(Exception):
    pass


# ------------------------------------------------------------------ runs on disk

class Run:
    def __init__(self, run_id: str):
        self.id = run_id
        self.dir = RUNS / run_id
        self.out = self.dir / "outputs"
        self._lock = _state_locks.setdefault(run_id, threading.Lock())

    @property
    def state_path(self) -> Path:
        return self.dir / "run.json"

    @property
    def log_path(self) -> Path:
        return self.dir / "run.log"

    def state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {}

    def update(self, **kw) -> dict:
        with self._lock:
            s = self.state()
            s.update(kw)
            s["updated"] = now()
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(s, indent=1))
            tmp.replace(self.state_path)
            return s

    def add_cost(self, label: str, cost: float, secs: float, ok: bool) -> None:
        with self._lock:
            s = self.state()
            s["cost_usd"] = round(s.get("cost_usd", 0) + (cost or 0), 4)
            s.setdefault("calls", []).append({"label": label, "cost_usd": round(cost or 0, 4),
                                              "seconds": round(secs), "ok": ok, "at": now()})
            self.state_path.write_text(json.dumps(s, indent=1))

    def log(self, line: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(redact(f"{dt.datetime.now(dt.timezone.utc).strftime('%H:%M:%S')}  {line}") + "\n")

    def tail(self, n: int = 200) -> list[str]:
        if not self.log_path.is_file():
            return []
        return self.log_path.read_text(encoding="utf-8").splitlines()[-n:]


def list_runs() -> list[dict]:
    if not RUNS.is_dir():
        return []
    out = []
    for d in RUNS.iterdir():
        s = Run(d.name).state()
        if s:
            out.append(s)
    return sorted(out, key=lambda s: s.get("created", ""), reverse=True)


def get(run_id: str) -> Run | None:
    if not re.fullmatch(r"[0-9a-f]{8}", run_id or ""):
        return None
    r = Run(run_id)
    return r if r.state_path.is_file() else None


def active_run() -> str | None:
    return _active


def recover() -> None:
    """After a restart, a run that was mid-stage can't continue on its own."""
    for s in list_runs():
        if s.get("status") in ACTIVE:
            Run(s["id"]).update(status="interrupted",
                                message="The server restarted during this stage. Resume to run it again.")


def create(started_by: str) -> Run:
    run_id = uuid.uuid4().hex[:8]
    r = Run(run_id)
    r.dir.mkdir(parents=True)
    for name in ("CLAUDE.md", "requirements.txt"):
        shutil.copy2(ROOT / name, r.dir / name)
    shutil.copytree(ROOT / ".claude", r.dir / ".claude",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    shutil.copytree(ROOT / "data", r.dir / "data", ignore=shutil.ignore_patterns(".DS_Store"))
    shutil.copytree(ROOT / "scripts" / "checks", r.dir / "scripts" / "checks",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    copy_tools(r)
    (r.dir / "outputs").mkdir()
    (r.dir / ".venv" / "bin").mkdir(parents=True)        # agent files call .venv/bin/python
    os.symlink(sys.executable, r.dir / ".venv" / "bin" / "python")
    r.update(id=run_id, created=now(), started_by=started_by, status="running", stage="rules",
             message="Starting.", cost_usd=0, calls=[], revisions=0, budget_usd=BUDGET)
    r.log(f"run {run_id} created")
    return r


# ------------------------------------------------------------------ claude calls

def _summ(block: dict) -> str:
    name = block.get("name", "")
    inp = block.get("input") or {}
    if name == "Bash":
        return f"Bash: {str(inp.get('command', ''))[:140]}"
    if name in ("Read", "Write", "Edit"):
        return f"{name}: {inp.get('file_path', '')}"
    if name == "Skill":
        return f"Skill: {inp.get('skill', '')}"
    if name in ("Agent", "Task"):
        return f"Agent: {inp.get('subagent_type', '')} ({inp.get('description', '')})"
    return name


def claude(run: Run, label: str, prompt: str, agent: str | None = None,
           session: str | None = None, resume: bool = False) -> str:
    spent = run.state().get("cost_usd", 0)
    remaining = BUDGET - spent
    if remaining < 0.5:
        raise BudgetSpent(f"run budget of ${BUDGET:.2f} is spent")
    cmd = [CLAUDE, "-p", "--output-format", "stream-json", "--verbose",
           "--dangerously-skip-permissions", "--max-budget-usd", f"{remaining:.2f}"]
    if MODEL:
        cmd += ["--model", MODEL]
    if agent:
        cmd += ["--agent", agent]
    if session:
        cmd += ["--resume", session] if resume else ["--session-id", session]
    cmd.append(prompt)
    run.log(f"[{label}] start{' (resume)' if resume else ''}")
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=run.dir, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    timer = threading.Timer(CALL_TIMEOUT, proc.kill)
    timer.start()
    result_text, cost, ok = "", 0.0, False
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                run.log(f"[{label}] {line[:300]}")
                continue
            sub = " ↳" if ev.get("parent_tool_use_id") else ""
            if ev.get("type") == "assistant":
                for b in ev.get("message", {}).get("content", []):
                    if b.get("type") == "text" and b.get("text", "").strip():
                        run.log(f"[{label}]{sub} {b['text'].strip()[:400]}")
                    elif b.get("type") == "tool_use":
                        run.log(f"[{label}]{sub} → {_summ(b)}")
            elif ev.get("type") == "result":
                result_text = ev.get("result") or ""
                cost = float(ev.get("total_cost_usd") or 0)
                ok = ev.get("subtype") == "success" and not ev.get("is_error")
                if not ok:
                    run.log(f"[{label}] ended: {ev.get('subtype')} {str(ev.get('result') or '')[:300]}")
        proc.wait()
    finally:
        timer.cancel()
    secs = time.time() - t0
    run.add_cost(label, cost, secs, ok)
    run.log(f"[{label}] done in {secs/60:.1f} min, ${cost:.2f}")
    if not ok:
        if run.state().get("cost_usd", 0) >= BUDGET - 0.5:
            raise BudgetSpent(f"run budget of ${BUDGET:.2f} is spent")
        raise StageFailed(f"{label} did not finish (exit {proc.returncode})")
    return result_text


def require(run: Run, *names: str) -> None:
    missing = [n for n in names if not (run.out / n).is_file()]
    if missing:
        raise StageFailed("missing after this stage: " + ", ".join(f"outputs/{m}" for m in missing))


def gate(run: Run) -> tuple[bool, str]:
    p = subprocess.run([sys.executable, ".claude/skills/audit-program/build_pack.py", "--gate"],
                       cwd=run.dir, capture_output=True, text=True, timeout=120)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


# ------------------------------------------------------------------ stages

def stage_rules(run: Run) -> None:
    claude(run, "extract-rules", f"{UNATTENDED}\n\nRun the extract-rules skill (Skill tool) to turn "
           "data/contract-rules.pdf into outputs/rules.json, and finish only when the skill's "
           "verify_quotes.py exits 0. Then report as the skill says.")
    require(run, "rules.json")


def stage_evidence(run: Run) -> None:
    errors: list[str] = []

    def one(agent: str, task: str) -> None:
        try:
            claude(run, agent, f"{UNATTENDED}\n\n{task}", agent=agent)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{agent}: {e}")

    t1 = threading.Thread(target=one, args=("spend-analyst", "Do your full task as your agent file and "
                          "CLAUDE.md describe: clean the spend workbooks, parse contracts.csv, run every "
                          "test, write outputs/analytics.json, outputs/analytics-full/ and the self-check, "
                          "and report."))
    t2 = threading.Thread(target=one, args=("findings-analyst", "Do your full task as your agent file and "
                          "CLAUDE.md describe: read the committee papers and write outputs/history.json, "
                          "with the council's scoring method, and report."))
    t1.start(); t2.start(); t1.join(); t2.join()
    if errors:
        raise StageFailed("; ".join(errors))
    require(run, "analytics.json", "history.json")


def stage_register(run: Run) -> None:
    claude(run, "risk-assessor", f"{UNATTENDED}\n\nBuild the risk register (first build): follow your "
           "agent file and the risk-assessment skill, write outputs/risk-ratings.json and run "
           "build_register.py until PASS with 0 warnings. Report as your file says.", agent="risk-assessor")
    require(run, "risk-register.md", "auditor-comments.md")


def stage_revision(run: Run, reviewer: str, date: str) -> None:
    claude(run, "risk-assessor (revision)", f"{UNATTENDED}\n\nRevision run. The auditor ({reviewer}, "
           f"sign-off dated {date}) has filled outputs/auditor-comments.md through the web form. Apply "
           "the decisions and mark the register as the next revision, following the skill's \"auditor "
           "gate and revisions\" section and your agent file. Run build_register.py until PASS with 0 "
           "warnings and report.", agent="risk-assessor")


def parse_to_blocks(text: str) -> list[tuple[str, str]]:
    out, cur_to, buf = [], None, []
    for line in (text or "").splitlines():
        m = re.match(r"^\s*\**TO\s+(planner|challenger|qa-reviewer|main)\s*\**\s*:\s*(.*)$", line, re.I)
        if m:
            if cur_to:
                out.append((cur_to, "\n".join(buf).strip()))
            cur_to, buf = m.group(1).lower(), [m.group(2)]
        elif cur_to:
            buf.append(line)
    if cur_to:
        out.append((cur_to, "\n".join(buf).strip()))
    return [(t, m) for t, m in out if m]


def stage_team(run: Run) -> None:
    ok, gate_out = gate(run)
    if not ok:
        raise StageFailed("the gate is closed: " + gate_out.splitlines()[-1])
    gate_line = gate_out.splitlines()[-1]
    sessions = {a: str(uuid.uuid4()) for a in TEAM}
    started = set()
    inbox: dict[str, list[str]] = {a: [] for a in TEAM}
    common = f"{UNATTENDED}\n\n{TEAM_NOTE}\n\nThe lead checked the gate: \"{gate_line}\""
    inbox["planner"].append(f"{common}\n\nYou are the planner. Teammates: challenger, qa-reviewer; the lead "
                            "is main. Follow your agent file. Start at once; send PACK READY vN to both "
                            "teammates, and PLANNER DONE vN to qa-reviewer and main.")
    inbox["challenger"].append(f"{common}\n\nYou are the challenger. Teammates: planner, qa-reviewer; the "
                               "lead is main. Follow your agent file. Prepare now (step 1) and reply with a "
                               "one-line status and no TO blocks; send nothing until PACK READY v1 arrives. "
                               "Send CHALLENGER DONE to planner, qa-reviewer and main.")
    inbox["qa-reviewer"].append(f"{common}\n\nYou are the qa-reviewer. Teammates: planner, challenger; the "
                                "lead is main. Follow your agent file. Get ready and reply with a one-line "
                                "status and no TO blocks; run nothing until PACK READY v1 arrives. Send "
                                "QA DONE vN to main.")
    done: dict[str, str] = {}
    nudged = False
    order = list(TEAM)
    for turn in range(MAX_TEAM_TURNS):
        pending = [a for a in order if inbox[a]]
        if not pending:
            if {"planner", "challenger", "qa-reviewer"} <= set(done):
                break
            if nudged:
                raise StageFailed("the team stopped with no messages pending and not all agents done")
            nudged = True
            for a in TEAM:
                if a not in done:
                    inbox[a].append("From main: no messages are pending for anyone. If you have finished, "
                                    "send your DONE line; if you are waiting on a teammate, send them what "
                                    "they need.")
            continue
        a = pending[0]
        order.remove(a)
        order.append(a)                                   # round robin
        msg = "\n\n".join(inbox[a])
        inbox[a] = []
        text = claude(run, a, msg, agent=a, session=sessions[a], resume=a in started)
        started.add(a)
        blocks = parse_to_blocks(text)
        if blocks:
            nudged = False
        for to, body in blocks:
            run.log(f"[{a} → {to}] {body[:300]}")
            first = body.splitlines()[0]
            if re.search(r"\bPLANNER DONE\b", first) and a == "planner":
                done["planner"] = first
            if re.search(r"\bCHALLENGER DONE\b", first) and a == "challenger":
                done["challenger"] = first
            if re.search(r"\bQA DONE\b", first) and a == "qa-reviewer":
                done["qa-reviewer"] = first
            if to != "main":
                inbox[to].append(f"From {a}: {body}")
        run.update(message=f"Team turn {turn + 1}: {a}. Done so far: {', '.join(done) or 'none'}.",
                   team_done=done)
        if {"planner", "challenger", "qa-reviewer"} <= set(done) and not any(inbox.values()):
            break
    else:
        raise StageFailed(f"the team did not finish within {MAX_TEAM_TURNS} turns")


def review_verdict(run: Run) -> str:
    p = run.out / "review.md"
    if not p.is_file():
        return ""
    m = re.search(r"^## Verdict: (.+)$", p.read_text(encoding="utf-8"), re.M)
    return m.group(1).strip() if m else ""


# ------------------------------------------------------------------ orchestration

class Pause(Exception):
    """A human step is next: the status has been set; end the thread quietly."""


def _go(run: Run, steps) -> None:
    global _active
    try:
        for name, fn in steps:
            run.update(status="running", stage=name, message=dict(STAGES).get(name, name) + "...")
            fn()
    except Pause:
        pass
    except BudgetSpent as e:
        run.log(f"STOPPED: {e}")
        run.update(status="failed", message=f"Stopped: {e}.")
    except Exception as e:  # noqa: BLE001
        run.log(f"FAILED: {e}")
        run.update(status="failed", message=f"Failed in stage '{run.state().get('stage')}': {e}")
    finally:
        with _lock:
            _active = None


def _start(run: Run, steps) -> bool:
    global _active
    with _lock:
        if _active:
            return False
        _active = run.id
    run.update(status="running", stage=steps[0][0], message=dict(STAGES).get(steps[0][0], "") + "...")
    threading.Thread(target=_go, args=(run, steps), daemon=True).start()
    return True


def _to_gate(run: Run):
    def step():
        run.update(status="awaiting_decisions", stage="decisions",
                   message="The register is ready. Decide every risk below.")
        raise Pause()
    return step


def _revise(run: Run, reviewer: str, date: str):
    def step():
        n = run.state().get("revisions", 0)
        if n >= MAX_REVISIONS:
            raise StageFailed(f"more than {MAX_REVISIONS} revisions")
        stage_revision(run, reviewer, date)
        run.update(revisions=n + 1)
        ok, out = gate(run)
        last = out.splitlines()[-1] if out else ""
        run.log(f"[gate] {last}")
        if not ok:
            run.update(status="awaiting_decisions", stage="decisions",
                       message=f"The gate is still closed: {last} Complete the decisions below.")
            raise Pause()
    return step


def _to_signoff(run: Run):
    def step():
        v = review_verdict(run)
        if v.startswith("READY"):
            run.update(status="awaiting_signoff", stage="signoff",
                       message="The pack is ready for sign-off. Review it, then sign below.")
        else:
            run.update(status="blocked", stage="team",
                       message=f"QA verdict: {v or 'none'}. The pack goes back to the team: rerun the team stage.")
        raise Pause()
    return step


def start_new(started_by: str) -> Run | None:
    with _lock:
        if _active:
            return None
    run = create(started_by)
    steps = [("rules", lambda: stage_rules(run)), ("evidence", lambda: stage_evidence(run)),
             ("register", lambda: stage_register(run)), ("decisions", _to_gate(run))]
    if not _start(run, steps):
        run.update(status="failed", message="Another run started at the same moment.")
        return None
    return run


def submit_decisions(run: Run, reviewer: str, date: str) -> bool:
    steps = [("decisions", _revise(run, reviewer, date)), ("team", lambda: stage_team(run)),
             ("signoff", _to_signoff(run))]
    return _start(run, steps)


def copy_tools(r: Run) -> None:
    """Provided verifiers the agents run (not written by them), e.g. findings-analyst's."""
    for name in ("verify_history.py",):
        if not (r.dir / "scripts" / name).exists():
            (r.dir / "scripts").mkdir(exist_ok=True)
            shutil.copy2(ROOT / "scripts" / name, r.dir / "scripts" / name)


def resume(run: Run) -> bool:
    """Rerun the stage a run stopped in (after a failure, a restart or a BLOCKED verdict)."""
    copy_tools(run)
    stage = run.state().get("stage")
    first = {"rules": lambda: stage_rules(run), "evidence": lambda: stage_evidence(run),
             "register": lambda: stage_register(run)}
    if stage in first:
        names = list(first)
        steps = [(n, first[n]) for n in names[names.index(stage):]] + [("decisions", _to_gate(run))]
    elif stage == "team":
        steps = [("team", lambda: stage_team(run)), ("signoff", _to_signoff(run))]
    elif stage == "decisions":
        run.update(status="awaiting_decisions", message="Complete the decisions below.")
        return True
    else:
        return False
    return _start(run, steps)


# ------------------------------------------------------------------ human forms

def comment_rows(run: Run) -> list[dict]:
    p = run.out / "auditor-comments.md"
    if not p.is_file():
        return []
    rows = []
    body = p.read_text(encoding="utf-8").split("## Auditor notes")[0]
    for line in body.splitlines():
        if re.match(r"^\|\s*R-\d+", line):
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) >= 6:
                rows.append({"risk": c[0], "title": c[1], "score": c[2], "band": c[3],
                             "decision": c[4], "comment": " | ".join(c[5:]).strip()})
    return rows


def write_decisions(run: Run, decisions: dict[str, tuple[str, str]], reviewer: str, date: str) -> None:
    p = run.out / "auditor-comments.md"
    lines = p.read_text(encoding="utf-8").splitlines()
    out, in_notes, signed = [], False, False
    for line in lines:
        if line.strip().startswith("## Auditor notes"):
            in_notes = True
        m = re.match(r"^\|\s*(R-\d+)\s*\|", line)
        if m and not in_notes and m.group(1) in decisions:
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            dec, com = decisions[m.group(1)]
            line = "| " + " | ".join(c[:4] + [dec, com.replace("|", "/").replace("\n", " ")]) + " |"
        if in_notes and re.match(r"^\s*Reviewer:", line):
            line = f"Reviewer: {reviewer}. Date: {date}."
            signed = True
        out.append(line)
    if not signed:
        if not in_notes:
            out += ["", "## Auditor notes", ""]
        out += ["", f"Reviewer: {reviewer}. Date: {date}."]
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def write_signoff(run: Run, reviewer: str, date: str, decision: str, comments: str) -> bool:
    p = run.out / "review.md"
    text = p.read_text(encoding="utf-8")
    i = text.find("## Auditor sign-off")
    if i < 0:
        return False
    block = (f"## Auditor sign-off\n\n"
             f"- [x] I have read planning-memo.md, risk-control-matrix.md, audit-program.md and challenges.md.\n"
             f"- [x] I have decided each challenge marked *for the auditor*.\n"
             f"- [x] I accept the samples in outputs/samples/ as the basis for fieldwork.\n\n"
             f"Decision: {decision}\nReviewer: {reviewer}. Date: {date}.\n"
             f"Comments: {comments.replace(chr(10), ' ').strip()} (Recorded through the web app.)\n")
    p.write_text(text[:i] + block, encoding="utf-8")
    return True
