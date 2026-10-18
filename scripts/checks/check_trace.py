#!/usr/bin/env python3
"""Traceability check: rule → risk → control → test is complete, and challenges are closed.

Reports two results:

trace
  - every rule in rules.json is cited ([rule:ID]) by a rated risk in
    risk-ratings.json, a control or a test in audit-plan.json, or is listed
    in not_tested with a reason; not_tested names only real rules;
  - every in-scope risk (Approve or Amend in auditor-comments.md) is in
    audit-plan.json, has at least one control, every control has a test,
    and the risk appears in risk-control-matrix.md and audit-program.md;
  - no rejected risk is in the plan or the program;
  - every High or Extreme risk (the council's matrix label in history.json,
    looked up from L and I in risk-register.md) is in scope, or is rejected
    with a reason in auditor-comments.md and listed out of scope, with that
    reason, in planning-memo.md.

challenges
  - outputs/challenges.md exists, every challenge row cites evidence (a
    [rule:], [metric:] or [history:] tag, a register entry, or a pack file),
    every [rule:ID] it cites exists, and no row is open (allowed statuses:
    resolved, declined, for the auditor).

Usage: check_trace.py [--out-dir outputs] [--rules …] [--history …]
Exit 1 if either result fails.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (Result, add_path_args, comment_decisions, load_json, paths,  # noqa: E402
                     read_text, table_rows)

RULE_TAG = re.compile(r"\[rule:(CPR-\d+)\]")
EVIDENCE = re.compile(r"\[(?:rule|metric|history):[^\]]+\]|\bregister\s+R-\d+|"
                      r"\b(?:planning-memo|risk-control-matrix|audit-program)\.md\b|"
                      r"\b(?:pack-figures|audit-plan|analytics|history|rules)\.json\b")
STATUSES = {"resolved", "declined", "for the auditor"}
HIGH_LABELS = {"high", "extreme"}


def cites(obj) -> set[str]:
    return set(RULE_TAG.findall(json.dumps(obj, ensure_ascii=False)))


def matrix_label(history: dict, L: int, I: int) -> str | None:
    for row in history.get("scoring_method", {}).get("matrix", []):
        if row.get("impact") == I:
            for c in row.get("cells", []):
                if c.get("likelihood") == L:
                    return c.get("band")
    return None


def run_trace(p: dict) -> Result:
    res = Result("trace", what="rules and risks")
    rules = load_json(p["rules"], res)
    ratings = load_json(p["risk-ratings.json"], res)
    plan = load_json(p["audit-plan.json"], res)
    history = load_json(p["history"], res)
    comments = read_text(p["auditor-comments.md"], res)
    register = read_text(p["risk-register.md"], res)
    memo = read_text(p["planning-memo.md"], res)
    rcm = read_text(p["risk-control-matrix.md"], res)
    program = read_text(p["audit-program.md"], res)
    if None in (rules, ratings, plan, history, comments, register):
        return res
    rule_ids = [r["rule_id"] for r in rules.get("rules", [])]
    plan_risks = {r.get("risk_id"): r for r in plan.get("risks", [])}

    # 1. rule coverage
    by_risk = cites(ratings.get("risks", []))
    by_plan = set()
    for r in plan.get("risks", []):
        by_plan |= cites(r.get("controls", [])) | cites(r.get("tests", []))
    not_tested = {}
    for n in plan.get("not_tested", []):
        rid, why = n.get("rule_id"), (n.get("reason") or "").strip()
        if rid not in rule_ids:
            res.fail(f"not_tested lists {rid}, which is not in rules.json")
        elif not why:
            res.fail(f"{rid}: listed as not tested with no reason")
        else:
            not_tested[rid] = why
    for rid in rule_ids:
        if rid not in by_risk | by_plan | set(not_tested):
            res.fail(f"{rid}: not cited by a rated risk, a control or a test, and not listed as not tested")
    for rid in sorted(set(not_tested) & by_plan):
        res.notes.append(f"{rid} is listed as not tested but is cited by a control or test")
    res.checked += len(rule_ids)
    res.notes.append(f"rules: {len(by_risk & set(rule_ids))} cited by rated risks, "
                     f"{len(by_plan & set(rule_ids))} by controls/tests, {len(not_tested)} not tested")

    # 2. in-scope risks
    decisions = comment_decisions(comments)
    in_scope = [r for r, d in decisions.items() if d["decision"] in ("approve", "amend")]
    rejected = [r for r, d in decisions.items() if d["decision"] == "reject"]
    undecided = [r for r, d in decisions.items() if d["decision"] not in ("approve", "amend", "reject")]
    for r in undecided:
        res.fail(f"{r}: no valid decision in auditor-comments.md ('{decisions[r]['decision']}')")
    rcm_risks = {cells[0].split()[0] for _, cells in table_rows(rcm or "", r"R-\d+\b.*")}
    prog_risks = set(re.findall(r"^## (R-\d+)\.", program or "", re.M))
    for rid in in_scope:
        res.checked += 1
        r = plan_risks.get(rid)
        if r is None:
            res.fail(f"{rid}: in scope but not in audit-plan.json")
            continue
        controls = [c.get("control_id") for c in r.get("controls", [])]
        tested = {c for t in r.get("tests", []) for c in t.get("control_ids", [])}
        if not controls:
            res.fail(f"{rid}: in scope but has no expected control")
        for c in controls:
            if c not in tested:
                res.fail(f"{rid}/{c}: control has no test")
        if rcm is not None and rid not in rcm_risks:
            res.fail(f"{rid}: in scope but not in risk-control-matrix.md")
        if program is not None and rid not in prog_risks:
            res.fail(f"{rid}: in scope but not in audit-program.md")
    for rid in rejected:
        if rid in plan_risks:
            res.fail(f"{rid}: rejected by the auditor but in audit-plan.json")
        if rid in prog_risks:
            res.fail(f"{rid}: rejected by the auditor but in audit-program.md")

    # 3. High and Extreme risks: in scope, or excluded with a recorded reason
    scored = {}
    for header, cells in table_rows(register, r"R-\d+"):
        h = [x.lower() for x in header]
        if "l" in h and "i" in h:
            scored[cells[0]] = (int(cells[h.index("l")]), int(cells[h.index("i")]))
    for m in re.finditer(r"^- (R-\d+) .*?\(was (\d) x (\d) = \d+\)", register, re.M):
        scored[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    for rid in sorted(decisions):
        if rid not in scored:
            res.fail(f"{rid}: decided in auditor-comments.md but no likelihood and impact found in risk-register.md")
    n_high = 0
    for rid, (L, I) in sorted(scored.items()):
        label = matrix_label(history, L, I)
        if label is None:
            res.fail(f"{rid}: no matrix label in history.json for L{L} x I{I}")
            continue
        if label.lower() not in HIGH_LABELS:
            continue
        n_high += 1
        if rid in in_scope:
            continue
        reason = decisions.get(rid, {}).get("comment", "").strip()
        if rid not in rejected:
            res.fail(f"{rid}: {label} risk ({L} x {I}) is neither in scope nor rejected")
        elif not reason:
            res.fail(f"{rid}: {label} risk rejected with no reason in auditor-comments.md")
        elif memo is not None and not re.search(rf"^- {re.escape(rid)}\b.*\S", memo.split("## Approach")[0], re.M):
            res.fail(f"{rid}: {label} risk rejected but not listed out of scope in planning-memo.md")
    res.checked += len(scored)
    res.notes.append(f"risks: {len(in_scope)} in scope, {len(rejected)} rejected, {n_high} High or Extreme")
    return res


def run_challenges(p: dict) -> Result:
    res = Result("challenges", what="challenges")
    text = read_text(p["challenges.md"], res)
    rules = load_json(p["rules"], Result("rules"))
    rule_ids = {r["rule_id"] for r in (rules or {}).get("rules", [])}
    if text is None:
        return res
    rows = table_rows(text, r"\d+")
    if not rows:
        res.notes.append("challenges.md has no challenge rows")
    for header, cells in rows:
        res.checked += 1
        h = [x.lower() for x in header]
        n = cells[0]
        si = next((i for i, x in enumerate(h) if x == "status"), None)
        resp = next((i for i, x in enumerate(h) if "response" in x), None)
        ev_cells = [c for i, c in enumerate(cells) if i not in (si, resp)]
        ev_text = " ".join(ev_cells)
        if not EVIDENCE.search(ev_text):
            res.fail(f"#{n}: cites no evidence")
        for rid in RULE_TAG.findall(ev_text):
            if rule_ids and rid not in rule_ids:
                res.fail(f"#{n}: cites {rid}, which is not in rules.json")
        status = cells[si].strip().lower() if si is not None and si < len(cells) else ""
        if status == "open":
            res.fail(f"#{n}: still open")
        elif status not in STATUSES:
            res.fail(f"#{n}: status '{status}' is not one of resolved, declined, for the auditor")
    return res


def run(p: dict) -> list[Result]:
    return [run_trace(p), run_challenges(p)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_path_args(ap)
    results = run(paths(ap.parse_args()))
    for res in results:
        for f in res.failures:
            print(f"FAIL [{res.check}] {f}")
        for n in res.notes:
            print(f"note [{res.check}] {n}")
        print(f"{res.check}: {res.status} ({res.checked} {res.what} checked, {len(res.failures)} failure(s))")
    return 1 if any(r.failures for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
