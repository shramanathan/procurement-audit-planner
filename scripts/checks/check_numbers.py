#!/usr/bin/env python3
"""Number check: every figure in the pack documents comes from a source file.

A figure is any number in planning-memo.md, risk-control-matrix.md or
audit-program.md that has a £ sign or three or more digits. Each must equal
a value in analytics.json, pack-figures.json, rules.json or a cell of
outputs/samples/*.csv. A figure printed with d decimals matches a source
value that rounds to it at d decimals; a whole number must match exactly.
A percentage may also match its fraction (12% ↔ 0.12).

Skipped, because they are labels, not figures: row IDs (file|sheet|row),
rule/risk/control/test/PBC and history IDs (CPR-04, R-01, T-02, AO-15…),
dates and timestamps, spend periods (2026-P02), years, clause and page
references (cl. 6.16, App B row B1, p. 12, the Clause column of a table),
JSON paths and file names, and hex hashes.

Usage: check_numbers.py [--out-dir outputs] [--analytics …] [--rules …]
Exit 1 if the check fails.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import Result, add_path_args, load_json, paths, read_text  # noqa: E402

DOCS = ["planning-memo.md", "risk-control-matrix.md", "audit-program.md"]
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
SKIP = [
    r"\S+\.xlsx\|[^|\n]+?\|\d+",                              # row IDs
    r"`[^`]*(?:\$\.|/|\.(?:csv|json|md|py|xlsx|pdf)\b)[^`]*`",  # code spans holding a path or file name
    r"\$\.[^\s\]]*",                                          # JSON paths outside code spans
    r"[\w./-]+\.(?:csv|json|md|py|xlsx|pdf)\b",               # file names
    r"\b[A-Z]{1,4}-\d+\b",                                    # CPR-04, R-01, C-02, T-03, P-01, AO-15, DS-02
    r"\b\d{4}-\d{2}-\d{2}(?:[T ][\d:.]+)?",                   # ISO dates, timestamps
    r"\b\d{4}-P\d{2}\b",                                      # spend periods
    rf"\b\d{{1,2}}(?:st|nd|rd|th)? (?:{MONTHS}) \d{{4}}\b",   # 17 October 2026
    rf"\b(?:{MONTHS}) \d{{4}}\b",                             # October 2026
    r"\b(?:cl\.|clauses?|para(?:graph)?s?\.?|sections?)\s*\d+(?:\.\d+)*(?:\s*(?:,|and|to|-|–)\s*\d+(?:\.\d+)*)*",
    r"\bApp(?:endix)? [ABC](?: (?:row|note) \S+)?",
    r"\b(?:p|pp|page|pages|pdf_page)\.?\s*\d+(?:\s*[-–]\s*\d+)?",
    r"\b[0-9a-f]{12,}\b",                                     # hashes
    r"(?<![£\d.,])\b(?:19|20)\d{2}\b(?![\d,.%])",             # years
    r"\bv\d+\b",                                              # pack versions
]
SKIP_RE = re.compile("|".join(f"(?:{s})" for s in SKIP))
NUM_RE = re.compile(r"(£\s?)?(-?\d[\d,]*(?:\.\d+)?)(%)?")


def numeric_leaves(obj, out: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, str):
        s = obj.strip().replace(",", "").lstrip("£")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
            out.append(float(s))
    elif isinstance(obj, dict):
        for v in obj.values():
            numeric_leaves(v, out)
    elif isinstance(obj, list):
        for v in obj:
            numeric_leaves(v, out)


class Sources:
    def __init__(self, values: list[float]):
        self.exact = {v for v in values if v == int(v)}
        self.rounded = {d: {round(v, d) for v in values} for d in range(1, 5)}

    def has(self, x: float, decimals: int) -> bool:
        if decimals == 0:
            return x in self.exact
        return round(x, decimals) in self.rounded.get(decimals, set())


def blank_clause_columns(line: str, header: list[str] | None) -> str:
    """Blank table cells under a 'Clause' or 'Page' header."""
    if not header or not line.strip().startswith("|"):
        return line
    cells = line.strip().strip("|").split("|")
    keep = [("" if i < len(header) and header[i].strip().lower() in ("clause", "clauses", "page") else c)
            for i, c in enumerate(cells)]
    return "|" + "|".join(keep) + "|"


def run(p: dict) -> Result:
    res = Result("numbers", what="figures")
    values: list[float] = []
    counts = {}
    for key in ("analytics", "pack-figures.json", "rules"):
        data = load_json(p[key], res)
        before = len(values)
        if data is not None:
            numeric_leaves(data, values)
        counts[p[key].name] = len(values) - before
    n_csv = 0
    if p["samples"].is_dir():
        for f in sorted(p["samples"].glob("*.csv")):
            with f.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    before = len(values)
                    numeric_leaves(list(row.values()), values)
                    n_csv += len(values) - before
    else:
        res.fail(f"{p['samples']}: missing")
    counts["samples/*.csv"] = n_csv
    src = Sources(values)
    res.notes.append("source values: " + ", ".join(f"{k} {v}" for k, v in counts.items()))

    for doc in DOCS:
        text = read_text(p[doc], res)
        if text is None:
            continue
        header = None
        for n, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if s.startswith("|"):
                cells = [c.strip() for c in s.strip("|").split("|")]
                if header is None:
                    header = cells
                    continue
                if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                    continue
            else:
                header = None
            clean = SKIP_RE.sub(" ", blank_clause_columns(line, header))
            for m in NUM_RE.finditer(clean):
                pound, raw, pct = m.group(1), m.group(2), m.group(3)
                digits = sum(ch.isdigit() for ch in raw)
                if not pound and digits < 3:
                    continue
                res.checked += 1
                x = float(raw.replace(",", ""))
                dec = len(raw.split(".")[1]) if "." in raw else 0
                ok = src.has(x, dec) or src.has(abs(x), dec)
                if not ok and pct:
                    ok = src.has(round(x / 100, dec + 2), dec + 2)
                if not ok:
                    shown = (pound or "") + raw + (pct or "")
                    res.fail(f"{doc}:{n}: {shown.strip()} is not a value in analytics.json, "
                             f"pack-figures.json, rules.json or samples/*.csv")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_path_args(ap)
    res = run(paths(ap.parse_args()))
    for f in res.failures:
        print(f"FAIL {f}")
    for n in res.notes:
        print(f"note {n}")
    print(f"numbers: {res.status} ({res.checked} {res.what} checked, {len(res.failures)} failure(s))")
    return 1 if res.failures else 0


if __name__ == "__main__":
    sys.exit(main())
