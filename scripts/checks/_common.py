"""Shared helpers for the QA checks in scripts/checks/.

The checks are written independently of the builders (build_register.py,
build_pack.py): they parse the outputs themselves, so a builder bug is not
repeated in the check that is meant to catch it.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Result:
    check: str                       # e.g. "numbers"
    checked: int = 0                 # how many items were checked
    what: str = "items"              # what the items are
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "FAIL" if self.failures else "PASS"

    def fail(self, msg: str) -> None:
        self.failures.append(msg)


def add_path_args(ap: argparse.ArgumentParser) -> None:
    """Every check takes the same paths, so run_checks can pass one namespace to all."""
    ap.add_argument("--out-dir", default="outputs", help="folder holding the pack (default outputs)")
    ap.add_argument("--rules", help="rules.json (default <out-dir>/rules.json)")
    ap.add_argument("--analytics", help="analytics.json (default <out-dir>/analytics.json)")
    ap.add_argument("--history", help="history.json (default <out-dir>/history.json)")
    ap.add_argument("--full-dir", help="analytics-full folder (default <out-dir>/analytics-full)")
    ap.add_argument("--pdf", default="data/contract-rules.pdf")
    ap.add_argument("--spend-dir", default="data/spend", help="the council's monthly workbooks (read only)")


def paths(args) -> dict[str, Path]:
    out = Path(args.out_dir)
    p = {
        "out": out,
        "rules": Path(args.rules) if args.rules else out / "rules.json",
        "analytics": Path(args.analytics) if args.analytics else out / "analytics.json",
        "history": Path(args.history) if args.history else out / "history.json",
        "full": Path(args.full_dir) if args.full_dir else out / "analytics-full",
        "pdf": Path(args.pdf),
        "spend_dir": Path(args.spend_dir),
    }
    for name in ("risk-register.md", "auditor-comments.md", "risk-ratings.json", "audit-plan.json",
                 "planning-memo.md", "risk-control-matrix.md", "audit-program.md", "pack-figures.json",
                 "challenges.md"):
        p[name] = out / name
    p["samples"] = out / "samples"
    p["spend_clean"] = p["full"] / "spend_clean.csv"
    return p


def load_json(path: Path, res: Result):
    """Load a JSON file, or record a failure and return None."""
    if not path.is_file():
        res.fail(f"{path}: missing")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        res.fail(f"{path}: not valid JSON ({e})")
        return None


def read_text(path: Path, res: Result) -> str | None:
    if not path.is_file():
        res.fail(f"{path}: missing")
        return None
    return path.read_text(encoding="utf-8")


def table_rows(text: str, first_col: str) -> list[tuple[list[str], list[str]]]:
    """Markdown table rows whose first cell matches first_col, each with its table's header cells."""
    out, header = [], None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if re.fullmatch(first_col, cells[0]):
            out.append((header, cells))
    return out


def comment_decisions(text: str) -> dict[str, dict]:
    """Decisions from auditor-comments.md: {risk_id: {decision, comment}}.

    Reads the decision table above '## Auditor notes'; the Decision column is
    found by its header, not by position.
    """
    body = text.split("## Auditor notes")[0]
    out = {}
    for header, cells in table_rows(body, r"R-\d+"):
        h = [x.lower() for x in header]
        di = h.index("decision") if "decision" in h else 4
        ci = h.index("comment") if "comment" in h else di + 1
        out[cells[0]] = {"decision": cells[di].strip().lower() if di < len(cells) else "",
                         "comment": " | ".join(cells[ci:]).strip() if ci < len(cells) else ""}
    return out
