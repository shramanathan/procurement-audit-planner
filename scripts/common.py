"""Shared helpers for the spend-analyst pipeline.

Paths, the supplier-name normaliser, money rounding, JSON writing and a
stop() helper for malformed input. Outputs describe risk indicators to
investigate, never findings of wrongdoing.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SPEND_DIR = DATA / "spend"
CONTRACTS = DATA / "contracts.csv"
RULES_PDF = DATA / "contract-rules.pdf"
OUT = ROOT / "outputs"
RULES = OUT / "rules.json"
FULL = OUT / "analytics-full"
ANALYTICS = OUT / "analytics.json"
VERIFIER = ROOT / ".claude" / "skills" / "extract-rules" / "verify_quotes.py"

SHEET = "Data to publish"
EXPECTED_COLS = ["Service", "Expenditure category", "Narrative", "Date",
                 "Net amount", "Supplier name"]
HEADER_SCAN_ROWS = 20
SPEND_TEXT_DATE_FORMAT = "%m/%d/%y"      # month first; never auto-detect
CONTRACT_DATE_FORMAT = "%d/%m/%Y"        # day first; never auto-detect

LANGUAGE = "Risk indicators to investigate, not findings of wrongdoing."
ANNUAL_LABEL = "annualised estimate"

_SUFFIXES = ("LTD", "LIMITED", "PLC", "LLP")


def normalise_supplier(name) -> str:
    """Uppercase; non-alphanumerics -> space; collapse; drop trailing suffixes."""
    if name is None or (isinstance(name, float) and math.isnan(name)):
        return ""
    s = str(name).upper()
    s = re.sub(r"[^A-Z0-9]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    parts = s.split(" ") if s else []
    while parts and parts[-1] in _SUFFIXES:
        parts.pop()
    return " ".join(parts)


def money(x) -> float:
    return float(round(float(x) + 0.0, 2))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _default(o):
    try:
        import numpy as np  # noqa
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
    except ImportError:
        pass
    if isinstance(o, (_dt.date, _dt.datetime)):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o.relative_to(ROOT)) if o.is_absolute() else str(o)
    raise TypeError(f"not JSON serialisable: {type(o)}")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=_default)
        f.write("\n")


def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rel(path: Path) -> str:
    return str(Path(path).resolve().relative_to(ROOT))


def stop(msg: str, code: int = 2) -> None:
    print(f"STOP: {msg}", file=sys.stderr)
    sys.exit(code)
