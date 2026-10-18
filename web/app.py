"""Web viewer for the procurement audit planning pack, with live QA.

Read-only: it renders the documents in outputs/, serves the sample CSVs, and
can rerun the auditor-gate check and the QA checks (neither writes files).
Nothing here runs an agent or rebuilds the pack.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import subprocess
import sys
import threading
from pathlib import Path

import markdown
from flask import Flask, abort, redirect, send_file, url_for

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
PY = sys.executable

DOCS = {  # slug -> (file, title, blurb)
    "review": (OUT / "review.md", "QA review and sign-off", "Verdict, final check results and the auditor's sign-off."),
    "planning-memo": (OUT / "planning-memo.md", "Planning memo", "Objective, scope, approach, samples and limitations."),
    "risk-control-matrix": (OUT / "risk-control-matrix.md", "Risk and control matrix", "Risk → expected control → rules → tests."),
    "audit-program": (OUT / "audit-program.md", "Audit program", "Each test's objective, steps, sample and the PBC list."),
    "challenges": (OUT / "challenges.md", "Challenges", "The challenger's points, the planner's responses and their status."),
    "risk-register": (OUT / "risk-register.md", "Risk register", "Rated risks with evidence, method and the auditor's decisions."),
    "auditor-comments": (OUT / "auditor-comments.md", "Auditor decisions", "Approve / Reject / Amend for every risk."),
    "readme": (ROOT / "README.md", "About this project", "Skills, agents and how they work together."),
}
SAMPLE_RE = re.compile(r"^T-\d{2,}\.csv$")
NOTICE = ("Risk indicators to investigate, not findings of wrongdoing. A supplier in a flagged list or a "
          "sample has not been found to have done anything wrong.")

app = Flask(__name__)
_qa_lock = threading.Lock()
_qa_last: dict | None = None

CSS = """
:root{--bg:#fbfaf7;--fg:#1f2328;--muted:#5f6670;--line:#dcd9d2;--card:#fff;--accent:#1d5c8c;--ok:#1d7a46;--bad:#b42318;--code:#f2f0eb}
@media (prefers-color-scheme:dark){:root{--bg:#15171a;--fg:#e6e6e3;--muted:#9aa1a9;--line:#30343a;--card:#1c1f23;--accent:#7fb3df;--ok:#5cc28b;--bad:#f0837a;--code:#22262b}}
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
.card h3{margin:0 0 4px;font-size:16px}.card p{margin:0;color:var(--muted);font-size:14px}
.stats{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;min-width:140px}
.stat b{display:block;font-size:22px}.stat span{color:var(--muted);font-size:13px}
.pass{color:var(--ok);font-weight:650}.fail{color:var(--bad);font-weight:650}
.doc{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 24px 24px;overflow-x:auto}
table{border-collapse:collapse;margin:12px 0;font-size:14px;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top}th{background:var(--code)}
pre{background:var(--code);padding:12px;border-radius:6px;overflow-x:auto;font-size:13px}code{background:var(--code);padding:1px 4px;border-radius:4px;font-size:.92em}pre code{padding:0;background:none}
button{background:var(--accent);color:#fff;border:0;border-radius:6px;padding:9px 16px;font-size:15px;cursor:pointer}
"""


def page(title: str, body: str) -> str:
    links = "".join(f'<a href="{url_for("doc", slug=s)}">{t}</a>' for s, (_, t, _) in DOCS.items()
                    if s in ("planning-memo", "risk-register", "audit-program", "challenges", "review"))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} · Procurement Audit Planner</title>
<style>{CSS}</style></head><body><header><div class="wrap"><a class="brand" href="{url_for('index')}">Procurement Audit Planner</a>
<nav>{links}<a href="{url_for('samples')}">Samples</a><a href="{url_for('qa')}">Live QA</a></nav></div></header>
<main class="wrap"><div class="notice">{NOTICE}</div>{body}</main></body></html>"""


def md(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])


def load(name: str):
    try:
        return json.loads((OUT / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def summary() -> dict:
    s = {}
    review = (OUT / "review.md").read_text(encoding="utf-8") if (OUT / "review.md").is_file() else ""
    m = re.search(r"^## Verdict: (.+)$", review, re.M)
    s["verdict"] = m.group(1).strip() if m else "not reviewed"
    m = re.search(r"^Pack (v\d+) · register revision (\d+)", review, re.M)
    s["pack"], s["revision"] = (m.group(1), m.group(2)) if m else ("?", "?")
    m = re.search(r"^Decision: (.+)$", review, re.M)
    s["signoff"] = m.group(1).strip() if m and "delete one" not in m.group(1) else "awaiting sign-off"
    plan = load("audit-plan.json") or {}
    risks = plan.get("risks", [])
    s["risks"] = len(risks)
    s["controls"] = sum(len(r.get("controls", [])) for r in risks)
    s["tests"] = sum(len(r.get("tests", [])) for r in risks)
    figs = load("pack-figures.json") or {}
    s["transactions"] = sum(f["value"] for f in figs.get("computed", []) if f.get("figure", "").endswith(".transactions"))
    rules = load("rules.json") or {}
    s["rules"] = len(rules.get("rules", []))
    return s


@app.get("/")
def index():
    s = summary()
    cls = "pass" if s["verdict"].startswith("READY") else "fail"
    stats = "".join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for k, v in [
        ("testable rules", s["rules"]), ("risks in scope", s["risks"]), ("expected controls", s["controls"]),
        ("tests", s["tests"]), ("sampled payments", f'{s["transactions"]:,}')])
    cards = "".join(f'<a class="card" href="{url_for("doc", slug=k)}" style="text-decoration:none;color:inherit">'
                    f'<h3>{t}</h3><p>{b}</p></a>' for k, (_, t, b) in DOCS.items())
    body = f"""<h1>Audit planning pack: West Berkshire Council procurement</h1>
<p>Built by Claude Code skills and agents from the council's public data; every figure computed by Python and
checked by automated QA. Pack <b>{s['pack']}</b> from risk register revision <b>{s['revision']}</b>.</p>
<p>QA verdict: <span class="{cls}">{html.escape(s['verdict'])}</span> · Auditor: <b>{html.escape(s['signoff'])}</b>
· <a href="{url_for('qa')}">rerun the checks</a></p>
<div class="stats">{stats}</div><h2>Documents</h2><div class="grid">{cards}
<a class="card" href="{url_for('samples')}" style="text-decoration:none;color:inherit"><h3>Samples</h3>
<p>The payments each test pulls, drawn deterministically from the flagged lists.</p></a></div>"""
    return page("Overview", body)


@app.get("/doc/<slug>")
def doc(slug: str):
    if slug not in DOCS:
        abort(404)
    path, title, _ = DOCS[slug]
    if not path.is_file():
        abort(404)
    return page(title, f'<div class="doc">{md(path)}</div>')


@app.get("/samples")
def samples():
    figs = {f["figure"]: f["value"] for f in (load("pack-figures.json") or {}).get("computed", [])}
    rows = []
    for f in sorted((OUT / "samples").glob("T-*.csv")):
        t = f.stem
        with f.open(newline="", encoding="utf-8") as fh:
            n = sum(1 for _ in csv.reader(fh)) - 1
        gbp = figs.get(f"{t}.sample_gbp")
        rows.append(f'<tr><td>{t}</td><td>{figs.get(f"{t}.drawn", "")} of {figs.get(f"{t}.population", "")}</td>'
                    f'<td>{n:,}</td><td>{"£{:,.2f}".format(gbp) if gbp is not None else ""}</td>'
                    f'<td><a href="{url_for("sample_file", name=f.name)}">{f.name}</a></td></tr>')
    body = ("<h1>Samples</h1><p>One file per test. Each row is a payment, checked against the cleaned spend data "
            "and its row in the council's published workbook.</p><table><tr><th>Test</th><th>Units drawn</th>"
            "<th>Payments</th><th>Value</th><th>Download</th></tr>" + "".join(rows) + "</table>")
    return page("Samples", body)


@app.get("/samples/<name>")
def sample_file(name: str):
    if not SAMPLE_RE.match(name) or not (OUT / "samples" / name).is_file():
        abort(404)
    return send_file(OUT / "samples" / name, mimetype="text/csv", as_attachment=True, download_name=name)


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 1, "timed out after 120 seconds"


@app.get("/qa")
def qa():
    last = _qa_last
    if last:
        res = "".join(f'<h2>{html.escape(name)} <span class="{"pass" if code == 0 else "fail"}">'
                      f'{"PASS" if code == 0 else "FAIL"}</span></h2><pre>{html.escape(out)}</pre>'
                      for name, code, out in last["runs"])
        res = f"<p>Last run: {last['at']} UTC.</p>" + res
    else:
        res = "<p>No run on this server yet.</p>"
    body = f"""<h1>Live QA</h1><p>Reruns, on this server, the auditor-gate check
(<code>build_pack.py --gate</code>) and every QA check (<code>scripts/checks/run_checks.py</code>):
quotes against the rules PDF, figures against their sources, rule → risk → control → test traceability, closed
challenges, and every sampled payment against the council's workbooks. Neither writes any file.</p>
<form method="post" action="{url_for('qa_run')}"><button type="submit">Run the checks</button></form>{res}"""
    return page("Live QA", body)


@app.post("/qa/run")
def qa_run():
    global _qa_last
    if not _qa_lock.acquire(blocking=False):
        return redirect(url_for("qa"))  # a run is already in progress
    try:
        runs = []
        code, out = run([PY, ".claude/skills/audit-program/build_pack.py", "--gate"])
        runs.append(("Auditor gate", code, out))
        code, out = run([PY, "scripts/checks/run_checks.py"])
        runs.append(("QA checks", code, out))
        _qa_last = {"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "runs": runs}
    finally:
        _qa_lock.release()
    return redirect(url_for("qa"))


@app.get("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False)
