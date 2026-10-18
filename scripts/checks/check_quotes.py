#!/usr/bin/env python3
"""Quote check: rule quotes are verbatim and the register quotes the rules correctly.

1. Runs the extract-rules verifier on rules.json against the Contract
   Procedure Rules PDF (every verbatim_quote is on its stated page, and the
   rest of its checks). Any ERROR fails this check; WARN lines are noted.
2. Checks every rule excerpt in risk-register.md against rules.json:
   - each evidence line "rule: CPR-xx (cl. X)" names a rule that exists, with
     the clause rules.json gives it;
   - each inline [CPR-xx] or [rule:CPR-xx] names a rule that exists;
   - each quoted passage (15+ characters, in straight or curly quotes) in a
     paragraph that cites a rule appears, ignoring whitespace, in the
     verbatim_quote of a rule that paragraph cites.

Usage: check_quotes.py [--out-dir outputs] [--rules …] [--pdf …]
Exit 1 if the check fails.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ROOT, Result, add_path_args, load_json, paths, read_text  # noqa: E402

VERIFIER = ROOT / ".claude/skills/extract-rules/verify_quotes.py"
EVIDENCE_RE = re.compile(r"^\s*-\s*rule:\s*(CPR-\d+)\s*\(cl\.\s*(.+?)\)\s*$")
INLINE_RE = re.compile(r"\[(?:rule:)?(CPR-\d+)\]")
QUOTED_RE = re.compile(r"[\"“]([^\"“”]{15,})[\"”]")


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def run(p: dict) -> Result:
    res = Result("quotes", what="quotes and rule references")

    # 1. the extract-rules verifier
    if not VERIFIER.is_file():
        res.fail(f"{VERIFIER}: verifier missing")
    elif not p["pdf"].is_file():
        res.fail(f"{p['pdf']}: PDF missing")
    else:
        proc = subprocess.run([sys.executable, str(VERIFIER), str(p["rules"]), str(p["pdf"])],
                              capture_output=True, text=True)
        out = (proc.stdout + proc.stderr).splitlines()
        errors = [l.strip() for l in out if l.strip().startswith("ERROR")]
        warns = [l.strip() for l in out if l.strip().startswith("WARN")]
        if proc.returncode != 0:
            for e in errors or [f"verifier exited {proc.returncode}: " + " / ".join(out[-3:])]:
                res.fail(f"verifier: {e}")
        if warns:
            res.notes.append(f"verifier: {len(warns)} warning(s) for a human look")

    rules = load_json(p["rules"], res)
    if rules is None:
        return res
    by_id = {r["rule_id"]: r for r in rules.get("rules", [])}
    res.checked = len(by_id)
    res.notes.append(f"verifier checked {len(by_id)} rule quotes")

    # 2. the register's rule excerpts
    reg = read_text(p["risk-register.md"], res)
    if reg is None:
        return res
    n_refs = n_quotes = 0
    paras, cur, start = [], [], 1
    for n, line in enumerate(reg.splitlines(), 1):
        if line.strip():
            if not cur:
                start = n
            cur.append(line)
        elif cur:
            paras.append((start, "\n".join(cur)))
            cur = []
    if cur:
        paras.append((start, "\n".join(cur)))
    for lineno, para in paras:
        cited = set(INLINE_RE.findall(para))
        for i, line in enumerate(para.splitlines()):
            m = EVIDENCE_RE.match(line)
            if m:
                n_refs += 1
                rid, clause = m.group(1), m.group(2).strip()
                cited.add(rid)
                if rid not in by_id:
                    res.fail(f"risk-register.md:{lineno + i}: {rid} is not in rules.json")
                elif by_id[rid]["clause"] != clause:
                    res.fail(f"risk-register.md:{lineno + i}: {rid} shown as cl. {clause}; "
                             f"rules.json has {by_id[rid]['clause']}")
            for rid in INLINE_RE.findall(line):
                n_refs += 1
                if rid not in by_id:
                    res.fail(f"risk-register.md:{lineno + i}: [{rid}] is not in rules.json")
        if cited:
            for q in QUOTED_RE.findall(para):
                n_quotes += 1
                frags = [norm(f) for f in re.split(r"\[\.\.\.\]|…", q) if norm(f)]
                sources = [norm(by_id[r]["verbatim_quote"]) for r in cited if r in by_id]
                if not all(any(f in s for s in sources) for f in frags):
                    res.fail(f"risk-register.md:{lineno}: quoted text \"{q[:60]}…\" is not in the "
                             f"verbatim_quote of {', '.join(sorted(cited))}")
    res.checked += n_refs + n_quotes
    res.notes.append(f"register: {n_refs} rule reference(s), {n_quotes} quoted excerpt(s)")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_path_args(ap)
    res = run(paths(ap.parse_args()))
    for f in res.failures:
        print(f"FAIL {f}")
    for n in res.notes:
        print(f"note {n}")
    print(f"quotes: {res.status} ({res.checked} {res.what} checked, {len(res.failures)} failure(s))")
    return 1 if res.failures else 0


if __name__ == "__main__":
    sys.exit(main())
