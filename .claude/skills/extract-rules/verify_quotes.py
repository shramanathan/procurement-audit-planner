#!/usr/bin/env python3
"""Verify outputs/rules.json against the Contract Procedure Rules PDF.

Usage:
    verify_quotes.py [RULES_JSON] [PDF]
    (defaults: outputs/rules.json data/contract-rules.pdf)

Checks:
  - schema: required keys, types, enums, threshold objects
  - rule IDs: CPR-01, CPR-02, ... sequential with no gaps
  - parameters: all declared, all null, every reference declared
  - thresholds: amount matches the printed £ figure, inclusive flag matches
    the wording, as_printed appears in the quote
  - quotes: every verbatim_quote (rules and parameters) is on its stated page
  - coverage: every numbered clause and appendix B/C row in the PDF is in
    rules or excluded; nothing listed that isn't in the PDF

Exits 1 if there is any ERROR, otherwise 0. WARN lines need a human look.
Needs poppler's pdftotext and pdfinfo.
"""
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

RULE_TYPES = {
    "threshold_procedure", "advertising", "approval", "anti-avoidance",
    "exception_waiver", "valuation", "documentation", "contract_terms",
    "security", "sealing", "governance",
}
SCOPES = {"all", "goods_services", "works", "concessions", "light_touch"}
OBLIGATIONS = {"must", "shall", "should", "may", "none"}
NOTE_KINDS = {"contradiction", "gap", "drafting", "ambiguity"}
RULE_KEYS = [
    "rule_id", "clause", "page", "type", "scope", "obligation", "condition",
    "threshold_low", "threshold_high", "required_action", "approver",
    "evidence_source", "verbatim_quote",
]
PARAM_KEYS = ["value", "defined_in", "page", "description", "verbatim_quote"]
TOP_KEYS = ["source", "parameters", "rules", "excluded", "notes"]
MIN_FRAGMENT = 15
FRAGMENT_SEP = "[...]"

CLAUSE_RE = re.compile(r"^\d+(\.\d+)+$")
APPENDIX_RE = re.compile(r"^App ([ABC]) (row [A-Z0-9]+|note \S+|intro|closing)$")
PARAM_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Wording that fixes the inclusive flag of a bound.
LOW_INCLUSIVE = re.compile(r"\bor more\b|\bat least\b", re.I)
LOW_EXCLUSIVE = re.compile(r"\babove\b|\bover\b|\bmore than\b|\bexceed|\bin excess of\b|\bgreater than\b", re.I)
HIGH_INCLUSIVE = re.compile(r"\bup to\b|\bor less\b|\bnot exceeding\b", re.I)
HIGH_EXCLUSIVE = re.compile(r"\bless than\b|\bbelow\b|\bunder\b", re.I)
MONEY_RE = re.compile(r"£\s?(\d[\d,]*(?:\.\d+)?)\s*(million|m\b)?", re.I)

FOOTER_RE = re.compile(r"^\s*\$\S+\.docx\s+\d+\s*$")


class Report:
    def __init__(self):
        self.errors, self.warns = [], []

    def error(self, where, msg):
        self.errors.append(f"ERROR [{where}] {msg}")

    def warn(self, where, msg):
        self.warns.append(f"WARN  [{where}] {msg}")


# ---------- PDF text ----------

def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except FileNotFoundError:
        sys.exit(f"STOP: {cmd[0]} not found. Install poppler (brew install poppler).")
    except subprocess.CalledProcessError as e:
        sys.exit(f"STOP: {' '.join(cmd)} failed: {e.stderr.strip()}")


def page_count(pdf):
    m = re.search(r"^Pages:\s+(\d+)", run(["pdfinfo", str(pdf)]), re.M)
    if not m:
        sys.exit("STOP: pdfinfo did not report a page count.")
    return int(m.group(1))


def normalise(text):
    """Make PDF text and quotes comparable: same quotes/dashes, no bullets,
    no footers, single spaces. Case and wording are left alone."""
    text = unicodedata.normalize("NFKC", text)
    lines = [ln for ln in text.splitlines() if not FOOTER_RE.match(ln)]
    text = "\n".join(lines)
    for chars, repl in (("‘’‚‛′", "'"), ("“”„″", '"'), ("–—‐‑‒−", "-")):
        for c in chars:
            text = text.replace(c, repl)
    text = "".join(
        c for c in text
        if unicodedata.category(c) != "Co" and c not in "•▪●◦"
    )
    return re.sub(r"\s+", " ", text).strip()


class Pdf:
    def __init__(self, path):
        self.path = path
        self.pages = page_count(path)
        self._cache = {}

    def raw(self, page, layout):
        key = (page, layout)
        if key not in self._cache:
            cmd = ["pdftotext", "-f", str(page), "-l", str(page)]
            if layout:
                cmd.append("-layout")
            self._cache[key] = run(cmd + [str(self.path), "-"])
        return self._cache[key]

    def text(self, pages, layout):
        return normalise(" \n".join(self.raw(p, layout) for p in pages))


# ---------- helpers ----------

def page_list(page, pdf, rep, where):
    """Return the list of pages a `page` field refers to, or None if invalid."""
    if isinstance(page, bool):
        page = None
    if isinstance(page, int):
        pages = [page]
    elif (isinstance(page, list) and len(page) == 2
          and all(isinstance(p, int) and not isinstance(p, bool) for p in page)
          and page[1] == page[0] + 1):
        pages = page
    else:
        rep.error(where, f"page must be an integer or [n, n+1]; got {page!r}")
        return None
    if not all(1 <= p <= pdf.pages for p in pages):
        rep.error(where, f"page {page} is outside the PDF (1-{pdf.pages})")
        return None
    return pages


def find_fragments(fragments, text):
    pos = 0
    for frag in fragments:
        i = text.find(frag, pos)
        if i < 0:
            return frag
        pos = i + len(frag)
    return None


def check_quote(quote, page, pdf, rep, where):
    if not isinstance(quote, str) or not quote.strip():
        rep.error(where, "verbatim_quote is missing or empty")
        return
    pages = page_list(page, pdf, rep, where)
    if pages is None:
        return
    fragments = [normalise(f) for f in quote.split(FRAGMENT_SEP)]
    short = [f for f in fragments if len(f) < MIN_FRAGMENT]
    if short:
        rep.error(where, f"quote fragment too short to verify (<{MIN_FRAGMENT} chars): {short[0]!r}")
        return
    missing = None
    for layout in (False, True):
        missing = find_fragments(fragments, pdf.text(pages, layout))
        if missing is None:
            return
    # Not on the stated page: say where it is, if anywhere.
    elsewhere = [p for p in range(1, pdf.pages + 1)
                 if p not in pages and missing in pdf.text([p], False)]
    hint = f"; it is on page {elsewhere[0]}" if elsewhere else "; not found anywhere in the PDF"
    rep.error(where, f"quote not found on page {page}: {missing[:80]!r}{hint}")


def parse_money(as_printed):
    found = MONEY_RE.findall(as_printed)
    if len(found) != 1:
        return None, len(found)
    digits, million = found[0]
    value = float(digits.replace(",", ""))
    if million:
        value *= 1_000_000
    return value, 1


def check_bound(name, bound, rule, params, rep, where):
    if bound is None:
        return None
    if not isinstance(bound, dict):
        rep.error(where, f"{name} must be null or an object")
        return None
    as_printed = bound.get("as_printed")
    if not isinstance(as_printed, str) or not as_printed.strip():
        rep.error(where, f"{name}.as_printed is missing")
        return None
    if not isinstance(bound.get("inclusive"), bool):
        rep.error(where, f"{name}.inclusive must be true or false")
    has_amount, has_param = "amount" in bound, "parameter" in bound
    if has_amount == has_param:
        rep.error(where, f"{name} needs exactly one of 'amount' or 'parameter'")
        return None
    extra = set(bound) - {"amount", "parameter", "inclusive", "as_printed"}
    if extra:
        rep.error(where, f"{name} has unknown keys {sorted(extra)}")

    printed_value, n_money = parse_money(as_printed)
    amount = None
    if has_amount:
        amount = bound["amount"]
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            rep.error(where, f"{name}.amount must be a number")
            return None
        if n_money != 1:
            rep.error(where, f"{name}.as_printed {as_printed!r} must contain exactly one £ figure to back 'amount'")
        else:
            has_pence = re.search(r"£\s?[\d,]+\.\d", as_printed) is not None
            if isinstance(amount, float) and not has_pence:
                rep.error(where, f"{name}.amount must be a GBP integer (PDF prints no pence)")
            if abs(amount - printed_value) > 1e-9:
                rep.error(where, f"{name}.amount {amount} does not match printed {as_printed!r} ({printed_value:g})")
    else:
        pname = bound["parameter"]
        if pname not in params:
            rep.error(where, f"{name}.parameter {pname!r} is not declared in parameters")
        if n_money:
            rep.error(where, f"{name} uses a parameter but as_printed shows a £ figure: {as_printed!r}")

    # inclusive flag against the wording
    inc = bound.get("inclusive")
    if name == "threshold_low":
        want = True if LOW_INCLUSIVE.search(as_printed) else False if LOW_EXCLUSIVE.search(as_printed) else None
    else:
        want = True if HIGH_INCLUSIVE.search(as_printed) else False if HIGH_EXCLUSIVE.search(as_printed) else None
    if want is None:
        rep.warn(where, f"{name}: can't tell inclusive/exclusive from {as_printed!r}; check by hand")
    elif isinstance(inc, bool) and inc != want:
        rep.error(where, f"{name}.inclusive is {inc} but {as_printed!r} means {want}")

    quote = rule.get("verbatim_quote")
    if isinstance(quote, str) and normalise(as_printed) not in normalise(quote.replace(FRAGMENT_SEP, " ")):
        rep.error(where, f"{name}.as_printed {as_printed!r} does not appear in verbatim_quote")
    return amount


def nonempty_str(value):
    return isinstance(value, str) and value.strip() != ""


# ---------- clause inventory from the PDF ----------

def pdf_inventory(pdf):
    """Numbered clauses (body) and lettered rows (appendices B and C)."""
    clauses, rows = {}, {}
    appendix = None
    clause_line = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,3})\s+\S")
    row_line = re.compile(r"^\s{0,6}([A-F][12]?)(?:\s{2,}|\s*$)")
    for p in range(1, pdf.pages + 1):
        for line in pdf.raw(p, layout=True).splitlines():
            head = re.match(r"^\s*Contract Rules - Appendix ([A-Z])\b", line)
            if head:
                appendix = head.group(1)
                continue
            if appendix is None:
                m = clause_line.match(line)
                if m:
                    clauses.setdefault(m.group(1), p)
            elif appendix in "BC":
                m = row_line.match(line)
                if m:
                    rows.setdefault((appendix, m.group(1)), p)
    return clauses, rows


def covered(clause, listed):
    """A clause is covered by itself, an ancestor or a descendant."""
    return any(c == clause or clause.startswith(c + ".") or c.startswith(clause + ".")
               for c in listed)


# ---------- main checks ----------

def verify(data, pdf, rep):
    if not isinstance(data, dict):
        rep.error("file", "top level must be an object with source, parameters, rules, excluded, notes")
        return
    for k in TOP_KEYS:
        if k not in data:
            rep.error("file", f"missing top-level key {k!r}")
    for k in set(data) - set(TOP_KEYS):
        rep.error("file", f"unknown top-level key {k!r}")

    src = data.get("source") or {}
    if src.get("page_count") != pdf.pages:
        rep.error("source", f"page_count is {src.get('page_count')!r}; PDF has {pdf.pages}")

    # parameters
    params = data.get("parameters")
    if not isinstance(params, dict):
        rep.error("parameters", "must be an object keyed by parameter name")
        params = {}
    for name, p in params.items():
        where = f"param {name}"
        if not PARAM_NAME_RE.match(name):
            rep.error(where, "name must be UPPER_SNAKE_CASE")
        if not isinstance(p, dict):
            rep.error(where, "must be an object")
            continue
        for k in PARAM_KEYS:
            if k not in p:
                rep.error(where, f"missing key {k!r}")
        if p.get("value", None) is not None:
            rep.error(where, f"value must be null (the PDF does not print it); got {p['value']!r}")
        check_quote(p.get("verbatim_quote"), p.get("page"), pdf, rep, where)

    # rules
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        rep.error("rules", "must be a non-empty list")
        rules = []
    used_params, rule_clauses = set(), set()
    width = max(2, len(str(len(rules))))
    for i, r in enumerate(rules, start=1):
        rid = r.get("rule_id") if isinstance(r, dict) else None
        where = rid or f"rules[{i - 1}]"
        if not isinstance(r, dict):
            rep.error(where, "must be an object")
            continue
        expected = f"CPR-{i:0{width}d}"
        if rid != expected:
            rep.error(where, f"rule_id should be {expected} (sequential, no gaps)")
        for k in RULE_KEYS:
            if k not in r:
                rep.error(where, f"missing key {k!r}")
        for k in set(r) - set(RULE_KEYS):
            rep.warn(where, f"unexpected key {k!r}")

        clause = r.get("clause")
        if not isinstance(clause, str) or not (CLAUSE_RE.match(clause) or APPENDIX_RE.match(clause)):
            rep.error(where, f"clause {clause!r} is not a valid clause id")
        else:
            rule_clauses.add(clause)
        if r.get("type") not in RULE_TYPES:
            rep.error(where, f"type {r.get('type')!r} not in {sorted(RULE_TYPES)}")
        scope = r.get("scope")
        if not isinstance(scope, list) or not scope or not set(scope) <= SCOPES:
            rep.error(where, f"scope must be a non-empty list from {sorted(SCOPES)}")
        if r.get("obligation") not in OBLIGATIONS:
            rep.error(where, f"obligation {r.get('obligation')!r} not in {sorted(OBLIGATIONS)}")
        for k in ("condition", "required_action", "evidence_source"):
            if k in r and not nonempty_str(r[k]):
                rep.error(where, f"{k} must be a non-empty string")
        if "approver" in r and r["approver"] is not None and not nonempty_str(r["approver"]):
            rep.error(where, "approver must be a non-empty string or null")

        low = check_bound("threshold_low", r.get("threshold_low"), r, params, rep, where)
        high = check_bound("threshold_high", r.get("threshold_high"), r, params, rep, where)
        if low is not None and high is not None and low >= high:
            rep.error(where, f"threshold_low {low} is not below threshold_high {high}")
        for b in (r.get("threshold_low"), r.get("threshold_high")):
            if isinstance(b, dict) and "parameter" in b:
                used_params.add(b["parameter"])

        check_quote(r.get("verbatim_quote"), r.get("page"), pdf, rep, where)

    if not any(isinstance(r, dict) and r.get("type") == "anti-avoidance" for r in rules):
        rep.error("rules", "no rule has type 'anti-avoidance' (the no-splitting rule)")
    for name in sorted(set(params) - used_params):
        rep.warn(f"param {name}", "declared but no rule refers to it")

    # excluded
    excluded = data.get("excluded")
    if not isinstance(excluded, list):
        rep.error("excluded", "must be a list")
        excluded = []
    excl_clauses = set()
    for i, e in enumerate(excluded):
        where = f"excluded[{i}]"
        if not isinstance(e, dict):
            rep.error(where, "must be an object")
            continue
        clause = e.get("clause")
        where = f"excluded {clause}"
        if not isinstance(clause, str) or not (CLAUSE_RE.match(clause) or APPENDIX_RE.match(clause)):
            rep.error(where, f"clause {clause!r} is not a valid clause id (a bare section number is not allowed)")
        else:
            excl_clauses.add(clause)
        reason = e.get("reason")
        if not nonempty_str(reason):
            rep.error(where, "reason is missing")
        elif "\n" in reason or len(reason) > 200:
            rep.error(where, "reason must be one line of at most 200 characters")
        page_list(e.get("page"), pdf, rep, where)
    for c in sorted(rule_clauses & excl_clauses):
        rep.error(f"clause {c}", "is in both rules and excluded")

    # notes
    notes = data.get("notes")
    if not isinstance(notes, list):
        rep.error("notes", "must be a list")
        notes = []
    for i, n in enumerate(notes):
        where = f"notes[{i}]"
        if not isinstance(n, dict):
            rep.error(where, "must be an object")
            continue
        if n.get("kind") not in NOTE_KINDS:
            rep.error(where, f"kind {n.get('kind')!r} not in {sorted(NOTE_KINDS)}")
        if not isinstance(n.get("clauses"), list) or not n["clauses"]:
            rep.error(where, "clauses must be a non-empty list")
        if not nonempty_str(n.get("note")):
            rep.error(where, "note text is missing")
        pages = n.get("pages", [])
        if not isinstance(pages, list) or not all(isinstance(p, int) and 1 <= p <= pdf.pages for p in pages):
            rep.error(where, "pages must be a list of PDF page numbers")

    # coverage against the PDF
    pdf_clauses, pdf_rows = pdf_inventory(pdf)
    listed = rule_clauses | excl_clauses
    listed_numeric = {c for c in listed if CLAUSE_RE.match(c)}
    for c, p in sorted(pdf_clauses.items(), key=lambda kv: [int(x) for x in kv[0].split(".")]):
        if not covered(c, listed_numeric):
            rep.error(f"clause {c}", f"(page {p}) is in neither rules nor excluded")
    for c in sorted(listed_numeric):
        if not covered(c, set(pdf_clauses)):
            rep.error(f"clause {c}", "is listed but does not exist in the PDF")
    listed_rows = set()
    for c in listed:
        m = APPENDIX_RE.match(c)
        if m and m.group(2).startswith("row "):
            listed_rows.add((m.group(1), m.group(2)[4:]))
    for (app, row), p in sorted(pdf_rows.items()):
        if (app, row) not in listed_rows:
            rep.error(f"App {app} row {row}", f"(page {p}) is in neither rules nor excluded")
    for app, row in sorted(listed_rows):
        if app in "BC" and (app, row) not in pdf_rows:
            rep.error(f"App {app} row {row}", "is listed but does not exist in the PDF")
    if not any(c.startswith("App A ") for c in listed):
        rep.error("App A", "no entry for Appendix A (delegated authority bands)")
    else:
        rep.warn("App A", "rows are unlabelled in the PDF; confirm by eye that every band is covered")


def main(argv):
    rules_path = Path(argv[1] if len(argv) > 1 else "outputs/rules.json")
    pdf_path = Path(argv[2] if len(argv) > 2 else "data/contract-rules.pdf")
    for p in (rules_path, pdf_path):
        if not p.is_file():
            sys.exit(f"STOP: {p} not found.")
    try:
        data = json.loads(rules_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"STOP: {rules_path} is not valid JSON: {e}")

    rep = Report()
    verify(data, Pdf(pdf_path), rep)
    for line in rep.errors + rep.warns:
        print(line)
    n_rules = len(data.get("rules", [])) if isinstance(data, dict) else 0
    print(f"\n{len(rep.errors)} error(s), {len(rep.warns)} warning(s); {n_rules} rule(s) checked.")
    print("PASS" if not rep.errors else "FAIL")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
