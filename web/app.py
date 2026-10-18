"""Web app for the procurement audit planner.

- The reference run (outputs/ in the repo, signed off) as browsable pages,
  with live QA that reruns the gate and the checks.
- New runs: anyone with an access code can start the full Skills + Agents
  pipeline (web/runner.py), make the auditor decisions and sign off.
"""
from __future__ import annotations

import csv
import datetime as dt
import hmac
import html
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import markdown
from flask import Flask, abort, redirect, request, send_file, url_for

import runner

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "outputs"
PY = sys.executable

DOCS = {  # slug -> (file name in outputs/, title, blurb)
    "review": ("review.md", "QA review and sign-off", "Verdict, final check results and the auditor's sign-off."),
    "planning-memo": ("planning-memo.md", "Planning memo", "Objective, scope, approach, samples and limitations."),
    "risk-control-matrix": ("risk-control-matrix.md", "Risk and control matrix", "Risk → expected control → rules → tests."),
    "audit-program": ("audit-program.md", "Audit program", "Each test's objective, steps, sample and the PBC list."),
    "challenges": ("challenges.md", "Challenges", "The challenger's points, the planner's responses and their status."),
    "risk-register": ("risk-register.md", "Risk register", "Rated risks with evidence, method and the auditor's decisions."),
    "auditor-comments": ("auditor-comments.md", "Auditor decisions", "Approve / Reject / Amend for every risk."),
}
SAMPLE_RE = re.compile(r"^T-\d{2,}\.csv$")
NOTICE = ("Risk indicators to investigate, not findings of wrongdoing. A supplier in a flagged list or a "
          "sample has not been found to have done anything wrong.")
STATUS_LABEL = {"running": "Running", "awaiting_decisions": "Waiting for auditor decisions",
                "awaiting_signoff": "Waiting for sign-off", "done": "Signed off", "failed": "Stopped",
                "blocked": "Blocked by QA", "interrupted": "Interrupted"}

app = Flask(__name__)
_qa_lock = threading.Lock()
_qa_last: dict | None = None
runner.recover()

CSS = """
:root{--bg:#fbfaf7;--fg:#1f2328;--muted:#5f6670;--line:#dcd9d2;--card:#fff;--accent:#1d5c8c;--ok:#1d7a46;--bad:#b42318;--warn:#9a6700;--code:#f2f0eb}
@media (prefers-color-scheme:dark){:root{--bg:#15171a;--fg:#e6e6e3;--muted:#9aa1a9;--line:#30343a;--card:#1c1f23;--accent:#7fb3df;--ok:#5cc28b;--bad:#f0837a;--warn:#d9b45a;--code:#22262b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
header{border-bottom:1px solid var(--line);background:var(--card)}
.wrap{max-width:1100px;margin:0 auto;padding:0 16px}
header .wrap{display:flex;gap:18px;align-items:center;flex-wrap:wrap;padding-top:12px;padding-bottom:12px}
header a.brand{font-weight:650;color:var(--fg);text-decoration:none}
nav a{color:var(--muted);text-decoration:none;margin-right:14px;font-size:15px}nav a:hover{color:var(--accent)}
.notice{background:var(--code);border-left:3px solid var(--accent);padding:10px 14px;margin:18px 0;font-size:14px;color:var(--muted)}
main{padding-bottom:48px}a{color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px;margin:18px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px}
a.card{text-decoration:none;color:inherit}.card h3{margin:0 0 4px;font-size:16px}.card p{margin:0;color:var(--muted);font-size:14px}
.stats{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;min-width:140px}
.stat b{display:block;font-size:22px}.stat span{color:var(--muted);font-size:13px}
.pass{color:var(--ok);font-weight:650}.fail{color:var(--bad);font-weight:650}.wait{color:var(--warn);font-weight:650}
.doc{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 24px 24px;overflow-x:auto}
table{border-collapse:collapse;margin:12px 0;font-size:14px;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top}th{background:var(--code)}
pre{background:var(--code);padding:12px;border-radius:6px;overflow-x:auto;font-size:13px;white-space:pre-wrap;word-break:break-word}code{background:var(--code);padding:1px 4px;border-radius:4px;font-size:.92em}pre code{padding:0;background:none}
button{background:var(--accent);color:#fff;border:0;border-radius:6px;padding:9px 16px;font-size:15px;cursor:pointer}
input,select,textarea{font:inherit;padding:7px 9px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);max-width:100%}
textarea{width:100%;min-height:54px}label{display:block;font-size:14px;color:var(--muted);margin:10px 0 4px}
.form{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin:18px 0}
ol.stages{padding-left:20px}ol.stages li{margin:4px 0}.err{color:var(--bad)}
"""


def page(title: str, body: str, refresh: int | None = None) -> str:
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    links = "".join(f'<a href="{url_for("doc", slug=s)}">{DOCS[s][1]}</a>'
                    for s in ("planning-memo", "risk-register", "audit-program", "review"))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">{meta}
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} · Procurement Audit Planner</title>
<style>{CSS}</style></head><body><header><div class="wrap"><a class="brand" href="{url_for('index')}">Procurement Audit Planner</a>
<nav>{links}<a href="{url_for('samples')}">Samples</a><a href="{url_for('qa')}">Live QA</a><a href="{url_for('runs')}"><b>New runs</b></a></nav></div></header>
<main class="wrap"><div class="notice">{NOTICE}</div>{body}</main></body></html>"""


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def md_file(path: Path) -> str:
    return markdown.markdown(runner.redact(path.read_text(encoding="utf-8")),
                             extensions=["tables", "fenced_code", "sane_lists"])


def load(out: Path, name: str):
    try:
        return json.loads((out / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def code_ok(code: str) -> bool:
    codes = [c.strip() for c in os.environ.get("ACCESS_CODES", "").split(",") if c.strip()]
    ok = any(hmac.compare_digest(code.strip().encode(), c.encode()) for c in codes) if code else False
    if not ok:
        time.sleep(1)                                    # slow down guessing
    return ok


def runs_enabled() -> tuple[bool, str]:
    if not os.environ.get("ACCESS_CODES", "").strip():
        return False, "New runs are switched off: no access codes are configured on the server."
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return False, "New runs are switched off: no Anthropic API key is configured on the server."
    return True, ""


# ------------------------------------------------------------------ reference run

def summary(out: Path) -> dict:
    s = {}
    review = (out / "review.md").read_text(encoding="utf-8") if (out / "review.md").is_file() else ""
    m = re.search(r"^## Verdict: (.+)$", review, re.M)
    s["verdict"] = m.group(1).strip() if m else "not reviewed"
    m = re.search(r"^Pack (v\d+) · register revision (\d+)", review, re.M)
    s["pack"], s["revision"] = (m.group(1), m.group(2)) if m else ("?", "?")
    m = re.search(r"^Decision: (.+)$", review, re.M)
    s["signoff"] = m.group(1).strip() if m and "delete one" not in m.group(1) else "awaiting sign-off"
    risks = (load(out, "audit-plan.json") or {}).get("risks", [])
    s["risks"] = len(risks)
    s["controls"] = sum(len(r.get("controls", [])) for r in risks)
    s["tests"] = sum(len(r.get("tests", [])) for r in risks)
    figs = load(out, "pack-figures.json") or {}
    s["transactions"] = sum(f["value"] for f in figs.get("computed", []) if f.get("figure", "").endswith(".transactions"))
    s["rules"] = len((load(out, "rules.json") or {}).get("rules", []))
    return s


def doc_cards(out: Path, link) -> str:
    cards = "".join(f'<a class="card" href="{link(k)}"><h3>{t}</h3><p>{b}</p></a>'
                    for k, (f, t, b) in DOCS.items() if (out / f).is_file())
    return cards


@app.get("/")
def index():
    s = summary(REF)
    cls = "pass" if s["verdict"].startswith("READY") else "fail"
    stats = "".join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for k, v in [
        ("testable rules", s["rules"]), ("risks in scope", s["risks"]), ("expected controls", s["controls"]),
        ("tests", s["tests"]), ("sampled payments", f'{s["transactions"]:,}')])
    body = f"""<h1>Audit planning pack: West Berkshire Council procurement</h1>
<p>Built by Claude Code skills and agents from the council's public data; every figure computed by Python and
checked by automated QA. This is the <b>reference run</b>: pack <b>{s['pack']}</b> from risk register revision
<b>{s['revision']}</b>. <a href="{url_for('runs')}">Start a new run</a> with an access code.</p>
<p>QA verdict: <span class="{cls}">{esc(s['verdict'])}</span> · Auditor: <b>{esc(s['signoff'])}</b>
· <a href="{url_for('qa')}">rerun the checks</a></p>
<div class="stats">{stats}</div><h2>Documents</h2><div class="grid">{doc_cards(REF, lambda k: url_for('doc', slug=k))}
<a class="card" href="{url_for('samples')}"><h3>Samples</h3><p>The payments each test pulls, drawn
deterministically from the flagged lists.</p></a>
<a class="card" href="{url_for('readme')}"><h3>About this project</h3><p>Skills, agents and how they work
together.</p></a></div>"""
    return page("Overview", body)


@app.get("/doc/<slug>")
def doc(slug: str):
    if slug not in DOCS or not (REF / DOCS[slug][0]).is_file():
        abort(404)
    return page(DOCS[slug][1], f'<div class="doc">{md_file(REF / DOCS[slug][0])}</div>')


@app.get("/about")
def readme():
    return page("About", f'<div class="doc">{md_file(ROOT / "README.md")}</div>')


def samples_table(out: Path, link) -> str:
    figs = {f["figure"]: f["value"] for f in (load(out, "pack-figures.json") or {}).get("computed", [])}
    rows = []
    for f in sorted((out / "samples").glob("T-*.csv")):
        t = f.stem
        with f.open(newline="", encoding="utf-8") as fh:
            n = sum(1 for _ in csv.reader(fh)) - 1
        gbp = figs.get(f"{t}.sample_gbp")
        rows.append(f'<tr><td>{t}</td><td>{figs.get(f"{t}.drawn", "")} of {figs.get(f"{t}.population", "")}</td>'
                    f'<td>{n:,}</td><td>{"£{:,.2f}".format(gbp) if gbp is not None else ""}</td>'
                    f'<td><a href="{link(f.name)}">{f.name}</a></td></tr>')
    if not rows:
        return "<p>No samples yet.</p>"
    return ("<table><tr><th>Test</th><th>Units drawn</th><th>Payments</th><th>Value</th><th>Download</th></tr>"
            + "".join(rows) + "</table>")


@app.get("/samples")
def samples():
    body = ("<h1>Samples</h1><p>One file per test. Each row is a payment, checked against the cleaned spend data "
            "and its row in the council's published workbook.</p>"
            + samples_table(REF, lambda n: url_for("sample_file", name=n)))
    return page("Samples", body)


@app.get("/samples/<name>")
def sample_file(name: str):
    if not SAMPLE_RE.match(name) or not (REF / "samples" / name).is_file():
        abort(404)
    return send_file(REF / "samples" / name, mimetype="text/csv", as_attachment=True, download_name=name)


def run_cmd(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 1, "timed out after 120 seconds"


@app.get("/qa")
def qa():
    last = _qa_last
    if last:
        res = f"<p>Last run: {last['at']} UTC.</p>" + "".join(
            f'<h2>{esc(name)} <span class="{"pass" if code == 0 else "fail"}">{"PASS" if code == 0 else "FAIL"}</span></h2>'
            f'<pre>{esc(out)}</pre>' for name, code, out in last["runs"])
    else:
        res = "<p>No run on this server yet.</p>"
    body = f"""<h1>Live QA (reference run)</h1><p>Reruns, on this server, the auditor-gate check
(<code>build_pack.py --gate</code>) and every QA check (<code>scripts/checks/run_checks.py</code>): quotes against
the rules PDF, figures against their sources, rule → risk → control → test traceability, closed challenges, and
every sampled payment against the council's workbooks. Neither writes any file.</p>
<form method="post" action="{url_for('qa_run')}"><button type="submit">Run the checks</button></form>{res}"""
    return page("Live QA", body)


@app.post("/qa/run")
def qa_run():
    global _qa_last
    if not _qa_lock.acquire(blocking=False):
        return redirect(url_for("qa"))
    try:
        runs_ = [("Auditor gate",) + run_cmd([PY, ".claude/skills/audit-program/build_pack.py", "--gate"], ROOT),
                 ("QA checks",) + run_cmd([PY, "scripts/checks/run_checks.py"], ROOT)]
        _qa_last = {"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "runs": runs_}
    finally:
        _qa_lock.release()
    return redirect(url_for("qa"))


# ------------------------------------------------------------------ new runs

def status_html(s: dict) -> str:
    st = s.get("status", "")
    cls = {"done": "pass", "awaiting_signoff": "wait", "awaiting_decisions": "wait", "running": "wait"}.get(st, "fail")
    return f'<span class="{cls}">{esc(STATUS_LABEL.get(st, st))}</span>'


@app.get("/runs")
def runs():
    enabled, why = runs_enabled()
    active = runner.active_run()
    err = request.args.get("err", "")
    rows = "".join(
        f'<tr><td><a href="{url_for("run_page", run_id=s["id"])}">{s["id"]}</a></td><td>{esc(s.get("created"))}</td>'
        f'<td>{esc(s.get("started_by"))}</td><td>{status_html(s)}</td><td>{esc(s.get("stage"))}</td>'
        f'<td>${s.get("cost_usd", 0):.2f}</td></tr>' for s in runner.list_runs())
    table = ("<table><tr><th>Run</th><th>Started</th><th>By</th><th>Status</th><th>Stage</th><th>Cost</th></tr>"
             + rows + "</table>") if rows else "<p>No runs yet.</p>"
    if not enabled:
        form = f'<p class="err">{esc(why)}</p>'
    elif active:
        form = (f'<p>Run <a href="{url_for("run_page", run_id=active)}">{active}</a> is in progress. One run works '
                "at a time; start another when it reaches a human step or finishes.</p>")
    else:
        form = f"""<form class="form" method="post" action="{url_for('run_new')}">
<p>Starts the full pipeline on the bundled council data: rules extraction, spend and history analysis, risk
rating. You then decide each risk here, the agent team builds and checks the pack, and you sign off. A run
takes roughly an hour of agent work and is capped at ${runner.BUDGET:.0f} of API usage.</p>
<label for="name">Your name (shown on the run and recorded as the auditor)</label><input id="name" name="name" required maxlength="80">
<label for="code">Access code</label><input id="code" name="code" type="password" required maxlength="200">
<p><button type="submit">Start a new run</button></p>{f'<p class="err">{esc(err)}</p>' if err else ''}</form>"""
    stages = "".join(f"<li>{esc(t)}</li>" for _, t in runner.STAGES)
    body = f"""<h1>New runs</h1><p>Each run repeats the whole Skills + Agents pipeline from the council's public
files, with you as the auditor at both human gates.</p><ol class="stages">{stages}</ol>{form}<h2>Runs</h2>{table}"""
    return page("New runs", body)


@app.post("/runs/new")
def run_new():
    enabled, why = runs_enabled()
    if not enabled:
        return redirect(url_for("runs", err=why))
    name = request.form.get("name", "").strip()[:80]
    if not name or not code_ok(request.form.get("code", "")):
        return redirect(url_for("runs", err="Wrong access code, or no name given."))
    r = runner.start_new(name)
    if not r:
        return redirect(url_for("runs", err="Another run is in progress."))
    return redirect(url_for("run_page", run_id=r.id))


def run_or_404(run_id: str) -> runner.Run:
    r = runner.get(run_id)
    if not r:
        abort(404)
    return r


def decisions_form(r: runner.Run, s: dict, err: str) -> str:
    rows = runner.comment_rows(r)
    if not rows:
        return '<p class="err">The decision template is missing.</p>'
    opts = ["", "Approve", "Reject", "Amend"]
    trs = ""
    for row in rows:
        sel = "".join(f'<option{" selected" if o.lower() == row["decision"].lower() else ""}>{o}</option>' for o in opts)
        trs += (f'<tr><td><b>{esc(row["risk"])}</b></td><td>{esc(row["title"])}</td><td>{esc(row["score"])}<br>'
                f'{esc(row["band"])}</td><td><select name="dec_{esc(row["risk"])}">{sel}</select></td>'
                f'<td><textarea name="com_{esc(row["risk"])}" maxlength="1000">{esc(row["comment"])}</textarea></td></tr>')
    return f"""<form class="form" method="post" action="{url_for('run_decide', run_id=r.id)}">
<h2>Auditor decisions</h2><p>Read the <a href="{url_for('run_doc', run_id=r.id, slug='risk-register')}">risk
register</a>, then decide every risk. Reject and Amend need a comment saying what to change; a comment can also
request a new risk. The risk-assessor applies your decisions as a revision; when every risk is decided the agent
team starts.</p>
<table><tr><th>Risk</th><th>Title</th><th>Score</th><th>Decision</th><th>Comment</th></tr>{trs}</table>
<label for="rv">Reviewer name</label><input id="rv" name="reviewer" required maxlength="80" value="{esc(s.get('started_by'))}">
<label for="code">Access code</label><input id="code" name="code" type="password" required>
<p><button type="submit">Submit decisions</button></p>{f'<p class="err">{esc(err)}</p>' if err else ''}</form>"""


def signoff_form(r: runner.Run, s: dict, err: str) -> str:
    return f"""<form class="form" method="post" action="{url_for('run_signoff', run_id=r.id)}">
<h2>Auditor sign-off</h2><p>QA verdict: <span class="pass">{esc(runner.review_verdict(r))}</span>. Read the
<a href="{url_for('run_doc', run_id=r.id, slug='review')}">QA review</a>, the
<a href="{url_for('run_doc', run_id=r.id, slug='challenges')}">challenges</a> and the pack, then sign.</p>
<label><input type="checkbox" required> I have read planning-memo.md, risk-control-matrix.md, audit-program.md and challenges.md.</label>
<label><input type="checkbox" required> I have decided each challenge marked <i>for the auditor</i>.</label>
<label><input type="checkbox" required> I accept the samples as the basis for fieldwork.</label>
<label for="dec">Decision</label><select id="dec" name="decision"><option>Signed off</option><option>Returned to the team</option></select>
<label for="rv">Reviewer name</label><input id="rv" name="reviewer" required maxlength="80" value="{esc(s.get('started_by'))}">
<label for="cm">Comments</label><textarea id="cm" name="comments" maxlength="1000"></textarea>
<label for="code">Access code</label><input id="code" name="code" type="password" required>
<p><button type="submit">Record sign-off</button></p>{f'<p class="err">{esc(err)}</p>' if err else ''}</form>"""


def resume_form(r: runner.Run, err: str, label: str) -> str:
    return f"""<form class="form" method="post" action="{url_for('run_resume', run_id=r.id)}">
<label for="code">Access code</label><input id="code" name="code" type="password" required>
<p><button type="submit">{esc(label)}</button></p>{f'<p class="err">{esc(err)}</p>' if err else ''}</form>"""


@app.get("/runs/<run_id>")
def run_page(run_id: str):
    r = run_or_404(run_id)
    s = r.state()
    st = s.get("status")
    err = request.args.get("err", "")
    order = [k for k, _ in runner.STAGES]
    cur = order.index(s.get("stage")) if s.get("stage") in order else 0
    stages = ""
    for i, (k, t) in enumerate(runner.STAGES):
        mark = "✓" if i < cur or st == "done" else ("●" if i == cur else "○")
        stages += f"<li>{mark} {esc(t)}</li>"
    action = ""
    if st == "awaiting_decisions":
        action = decisions_form(r, s, err)
    elif st == "awaiting_signoff":
        action = signoff_form(r, s, err)
    elif st in ("failed", "interrupted"):
        action = resume_form(r, err, f"Resume from stage '{s.get('stage')}'")
    elif st == "blocked":
        action = resume_form(r, err, "Rerun the team stage")
    docs = doc_cards(r.out, lambda k: url_for("run_doc", run_id=r.id, slug=k))
    smp = samples_table(r.out, lambda n: url_for("run_sample", run_id=r.id, name=n)) if (r.out / "samples").is_dir() else ""
    log = "\n".join(r.tail(150))
    calls = "".join(f'<tr><td>{esc(c["label"])}</td><td>{c["seconds"] // 60} min</td><td>${c["cost_usd"]:.2f}</td>'
                    f'<td>{"ok" if c["ok"] else "failed"}</td></tr>' for c in s.get("calls", []))
    body = f"""<h1>Run {r.id}</h1><p>Started {esc(s.get('created'))} by {esc(s.get('started_by'))} ·
Status: {status_html(s)} · Cost so far: <b>${s.get('cost_usd', 0):.2f}</b> of ${s.get('budget_usd', runner.BUDGET):.0f}</p>
<p>{esc(s.get('message'))}</p><ol class="stages" style="list-style:none;padding-left:0">{stages}</ol>{action}
{f'<h2>Documents</h2><div class="grid">{docs}</div>' if docs else ''}{f'<h2>Samples</h2>{smp}' if smp else ''}
<h2>Agent activity</h2><pre>{esc(log) or 'Nothing yet.'}</pre>
{f'<h2>Claude Code calls</h2><table><tr><th>Call</th><th>Time</th><th>Cost</th><th>Result</th></tr>{calls}</table>' if calls else ''}"""
    return page(f"Run {r.id}", body, refresh=10 if st == "running" else None)


@app.get("/runs/<run_id>/doc/<slug>")
def run_doc(run_id: str, slug: str):
    r = run_or_404(run_id)
    if slug not in DOCS or not (r.out / DOCS[slug][0]).is_file():
        abort(404)
    back = f'<p><a href="{url_for("run_page", run_id=r.id)}">← Run {r.id}</a></p>'
    return page(f"{DOCS[slug][1]} · run {r.id}", back + f'<div class="doc">{md_file(r.out / DOCS[slug][0])}</div>')


@app.get("/runs/<run_id>/samples/<name>")
def run_sample(run_id: str, name: str):
    r = run_or_404(run_id)
    if not SAMPLE_RE.match(name) or not (r.out / "samples" / name).is_file():
        abort(404)
    return send_file(r.out / "samples" / name, mimetype="text/csv", as_attachment=True, download_name=name)


def today() -> str:
    return dt.date.today().isoformat()


@app.post("/runs/<run_id>/decide")
def run_decide(run_id: str):
    r = run_or_404(run_id)
    if r.state().get("status") != "awaiting_decisions":
        return redirect(url_for("run_page", run_id=r.id))
    if not code_ok(request.form.get("code", "")):
        return redirect(url_for("run_page", run_id=r.id, err="Wrong access code."))
    reviewer = request.form.get("reviewer", "").strip()[:80]
    decisions, missing = {}, []
    for row in runner.comment_rows(r):
        rid = row["risk"]
        dec = request.form.get(f"dec_{rid}", "").strip()
        com = request.form.get(f"com_{rid}", "").strip()[:1000]
        if dec not in ("Approve", "Reject", "Amend"):
            missing.append(rid)
        elif dec in ("Reject", "Amend") and not com:
            missing.append(f"{rid} (needs a comment)")
        decisions[rid] = (dec, com)
    if missing or not reviewer:
        return redirect(url_for("run_page", run_id=r.id,
                                err="Decide every risk: " + ", ".join(missing) if missing else "Give a reviewer name."))
    runner.write_decisions(r, decisions, reviewer, today())
    r.log(f"[auditor] decisions submitted by {reviewer}")
    if not runner.submit_decisions(r, reviewer, today()):
        return redirect(url_for("run_page", run_id=r.id, err="Another run is in progress; submit again when it pauses."))
    return redirect(url_for("run_page", run_id=r.id))


@app.post("/runs/<run_id>/signoff")
def run_signoff(run_id: str):
    r = run_or_404(run_id)
    if r.state().get("status") != "awaiting_signoff":
        return redirect(url_for("run_page", run_id=r.id))
    if not code_ok(request.form.get("code", "")):
        return redirect(url_for("run_page", run_id=r.id, err="Wrong access code."))
    reviewer = request.form.get("reviewer", "").strip()[:80]
    decision = request.form.get("decision", "")
    if decision not in ("Signed off", "Returned to the team") or not reviewer:
        return redirect(url_for("run_page", run_id=r.id, err="Choose a decision and give a reviewer name."))
    runner.write_signoff(r, reviewer, today(), decision, request.form.get("comments", "")[:1000])
    r.log(f"[auditor] {decision} by {reviewer}")
    if decision == "Signed off":
        r.update(status="done", stage="signoff", message=f"Signed off by {reviewer} on {today()}.")
    else:
        r.update(status="blocked", stage="team", message=f"Returned to the team by {reviewer}. Rerun the team stage.")
    return redirect(url_for("run_page", run_id=r.id))


@app.post("/runs/<run_id>/resume")
def run_resume(run_id: str):
    r = run_or_404(run_id)
    if r.state().get("status") not in ("failed", "interrupted", "blocked"):
        return redirect(url_for("run_page", run_id=r.id))
    if not code_ok(request.form.get("code", "")):
        return redirect(url_for("run_page", run_id=r.id, err="Wrong access code."))
    if not runner.resume(r):
        return redirect(url_for("run_page", run_id=r.id, err="Another run is in progress."))
    return redirect(url_for("run_page", run_id=r.id))


@app.get("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False)
