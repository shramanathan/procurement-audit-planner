#!/usr/bin/env python3
"""Verify outputs/history.json against the committee papers in data/committee/.

Usage:
    verify_history.py [HISTORY_JSON] [COMMITTEE_DIR]
    (defaults: outputs/history.json data/committee)

Checks:
  - structure: top-level keys, required fields, enums, sequential ids
  - sources: every committee PDF listed, page count and sha256 match
  - quotes: every object with a "quote" names a listed source and a pdf_page,
    and the quote is on that page (plain or -layout text)
  - records, never scores: no likelihood/impact/score keys outside scoring_method
  - every empty section and every not_found method is explained in gaps
  - every discrepancy quotes at least two locations

Exits 1 on any ERROR. WARN lines need a human look.
Needs poppler's pdftotext and pdfinfo.
"""
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

TOP_KEYS = ["generated_at", "sources", "audit_opinions", "agreed_actions",
            "risk_themes", "scoring_method", "strategic_risk_register",
            "discrepancies", "gaps"]
LISTS = {"audit_opinions": "AO", "agreed_actions": "AA",
         "risk_themes": "RT", "discrepancies": "DS"}
OPINION_KEYS = ["id", "source", "pdf_page", "period", "section", "directorate",
                "service", "audit_title", "opinion", "implementation_progress",
                "keyword_hits", "rebuilt_from_layout", "quote"]
OPINION_SECTIONS = {"completed_audit", "follow_up", "advisory"}
ACTION_KEYS = ["id", "source", "pdf_page", "theme", "due_date", "status", "quote"]
THEME_KEYS = ["id", "source", "pdf_page", "theme", "kind", "keyword_hits", "quote"]
THEME_KINDS = {"risk_source_category", "context_risk", "register_reference"}
SCORING_PARTS = ["evaluation_levels", "impact_scale", "likelihood_scale",
                 "matrix", "rag_bands", "register_criteria", "appetite"]
SCORE_WORDS = {"likelihood", "impact", "score", "risk_score", "rating",
               "priority", "severity"}
MIN_FRAGMENT, MIN_QUOTE, SEP = 8, 15, "[...]"


class Report:
    def __init__(self):
        self.errors, self.warns = [], []

    def error(self, where, msg):
        self.errors.append(f"ERROR [{where}] {msg}")

    def warn(self, where, msg):
        self.warns.append(f"WARN  [{where}] {msg}")


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except FileNotFoundError:
        sys.exit(f"STOP: {cmd[0]} not found. Install poppler (brew install poppler).")
    except subprocess.CalledProcessError as e:
        sys.exit(f"STOP: {' '.join(cmd)} failed: {e.stderr.strip()}")


def normalise(text):
    """Same quotes/dashes, no bullets, single spaces. Wording and case untouched."""
    text = unicodedata.normalize("NFKC", text)
    for chars, repl in (("‘’‚‛′", "'"), ("“”„″", '"'), ("–—‐‑‒−", "-")):
        for c in chars:
            text = text.replace(c, repl)
    text = "".join(c for c in text
                   if unicodedata.category(c) != "Co" and c not in "•▪●◦")
    return re.sub(r"\s+", " ", text).strip()


class Pdf:
    def __init__(self, path):
        self.path = path
        out = run(["pdfinfo", str(path)])
        m = re.search(r"^Pages:\s+(\d+)", out, re.M)
        if not m:
            sys.exit(f"STOP: pdfinfo gave no page count for {path}")
        self.pages = int(m.group(1))
        self.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self._cache = {}

    def text(self, page, layout):
        key = (page, layout)
        if key not in self._cache:
            cmd = ["pdftotext", "-f", str(page), "-l", str(page)]
            if layout:
                cmd.append("-layout")
            self._cache[key] = normalise(run(cmd + [str(self.path), "-"]))
        return self._cache[key]


def find_in_order(fragments, text):
    pos = 0
    for frag in fragments:
        i = text.find(frag, pos)
        if i < 0:
            return frag
        pos = i + len(frag)
    return None


def check_quote(obj, pdfs, rep, where):
    src, page, quote = obj.get("source"), obj.get("pdf_page"), obj.get("quote")
    if src not in pdfs:
        rep.error(where, f"source {src!r} is not in sources[]")
        return
    pdf = pdfs[src]
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= pdf.pages:
        rep.error(where, f"pdf_page {page!r} is not a page of {src} (1-{pdf.pages})")
        return
    if not isinstance(quote, str) or len(normalise(quote.replace(SEP, " "))) < MIN_QUOTE:
        rep.error(where, f"quote missing or shorter than {MIN_QUOTE} characters")
        return
    fragments = [normalise(f) for f in quote.split(SEP)]
    short = [f for f in fragments if len(f) < MIN_FRAGMENT]
    if short:
        rep.error(where, f"quote fragment shorter than {MIN_FRAGMENT} characters: {short[0]!r}")
        return
    missing = None
    for layout in (False, True):
        missing = find_in_order(fragments, pdf.text(page, layout))
        if missing is None:
            return
    others = [p for p in range(1, pdf.pages + 1) if p != page
              and (missing in pdf.text(p, False) or missing in pdf.text(p, True))]
    hint = f"; it is on page {others[0]}" if others else "; not found anywhere in this PDF"
    rep.error(where, f"quote not found on {Path(src).name} p{page}: {missing[:70]!r}{hint}")


def walk(node, path=""):
    """Yield (path, dict) for every dict in the tree."""
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")


def label(path, obj):
    return obj.get("id") or path


def verify(data, committee_dir, rep):
    if not isinstance(data, dict):
        rep.error("file", "top level must be an object")
        return
    for k in TOP_KEYS:
        if k not in data:
            rep.error("file", f"missing top-level key {k!r}")
    for k in set(data) - set(TOP_KEYS):
        rep.error("file", f"unknown top-level key {k!r}")

    # sources
    pdfs = {}
    for i, s in enumerate(data.get("sources") or []):
        where = f"sources[{i}]"
        f = s.get("file") if isinstance(s, dict) else None
        if not isinstance(f, str) or not Path(f).is_file():
            rep.error(where, f"file {f!r} not found")
            continue
        pdf = Pdf(Path(f))
        pdfs[f] = pdf
        if s.get("pages") != pdf.pages:
            rep.error(where, f"pages is {s.get('pages')!r}; PDF has {pdf.pages}")
        if s.get("sha256") != pdf.sha256:
            rep.error(where, "sha256 does not match the file")
    listed = {Path(f).name for f in pdfs}
    for p in sorted(Path(committee_dir).glob("*.pdf")):
        if p.name not in listed:
            rep.error("sources", f"{p.name} is in {committee_dir} but not in sources[]")

    # every quoted object, anywhere
    n_quotes = 0
    for path, obj in walk({k: v for k, v in data.items() if k != "sources"}):
        if "quote" in obj:
            n_quotes += 1
            check_quote(obj, pdfs, rep, label(path, obj))

    # list sections: ids and fields
    for key, prefix in LISTS.items():
        items = data.get(key)
        if not isinstance(items, list):
            rep.error(key, "must be a list")
            continue
        for i, it in enumerate(items, start=1):
            want = f"{prefix}-{i:02d}"
            if not isinstance(it, dict) or it.get("id") != want:
                rep.error(f"{key}[{i - 1}]", f"id should be {want} (sequential, no gaps)")

    for it in data.get("audit_opinions") or []:
        w = it.get("id", "audit_opinion")
        for k in OPINION_KEYS:
            if k not in it:
                rep.error(w, f"missing key {k!r}")
        if it.get("section") not in OPINION_SECTIONS:
            rep.error(w, f"section {it.get('section')!r} not in {sorted(OPINION_SECTIONS)}")
        if it.get("section") != "follow_up" and it.get("implementation_progress") is not None:
            rep.error(w, "implementation_progress is only for follow_up rows")
        if not isinstance(it.get("keyword_hits"), list):
            rep.error(w, "keyword_hits must be a list")
    for it in data.get("agreed_actions") or []:
        for k in ACTION_KEYS:
            if k not in it:
                rep.error(it.get("id", "agreed_action"), f"missing key {k!r}")
    for it in data.get("risk_themes") or []:
        w = it.get("id", "risk_theme")
        for k in THEME_KEYS:
            if k not in it:
                rep.error(w, f"missing key {k!r}")
        if it.get("kind") not in THEME_KINDS:
            rep.error(w, f"kind {it.get('kind')!r} not in {sorted(THEME_KINDS)}")
    for it in data.get("discrepancies") or []:
        w = it.get("id", "discrepancy")
        locs = it.get("locations")
        if not isinstance(it.get("description"), str) or not it["description"].strip():
            rep.error(w, "description is missing")
        if not isinstance(locs, list) or len(locs) < 2:
            rep.error(w, "needs at least two quoted locations")
        elif not all(isinstance(l, dict) and "quote" in l for l in locs):
            rep.error(w, "every location needs source, pdf_page and quote")

    # records, never scores
    for key in ("audit_opinions", "agreed_actions", "risk_themes"):
        for path, obj in walk(data.get(key), key):
            bad = SCORE_WORDS & {k.lower() for k in obj}
            if bad:
                rep.error(label(path, obj), f"scoring field(s) {sorted(bad)} not allowed: the agent records, never scores")

    # gaps
    gaps = data.get("gaps")
    if not isinstance(gaps, list):
        rep.error("gaps", "must be a list")
        gaps = []
    gap_fields = set()
    for i, g in enumerate(gaps):
        w = f"gaps[{i}]"
        if not isinstance(g, dict):
            rep.error(w, "must be an object")
            continue
        gap_fields.add(g.get("field"))
        for k in ("field", "item", "reason"):
            if not isinstance(g.get(k), str) or not g[k].strip():
                rep.error(w, f"{k} is missing")
        searched = g.get("searched")
        if not isinstance(searched, list) or not searched:
            rep.error(w, "searched must list the files that were checked")
        elif not all(s in pdfs for s in searched):
            rep.error(w, "searched names a file that is not in sources[]")
    for key in ("audit_opinions", "agreed_actions", "risk_themes"):
        if data.get(key) == [] and key not in gap_fields:
            rep.error(key, f"is empty but no gap with field {key!r} explains why")

    # scoring method
    sm = data.get("scoring_method")
    if not isinstance(sm, dict) or sm.get("status") not in ("found", "not_found"):
        rep.error("scoring_method", "must be an object with status 'found' or 'not_found'")
    elif sm["status"] == "not_found":
        if "scoring_method" not in gap_fields:
            rep.error("scoring_method", "not_found but no gap with field 'scoring_method'")
    else:
        for part in SCORING_PARTS:
            if part not in sm:
                rep.error("scoring_method", f"missing {part!r} (use [] plus a gap if absent)")
            elif sm[part] in ([], {}) and f"scoring_method.{part}" not in gap_fields:
                rep.error("scoring_method", f"{part} is empty but no gap 'scoring_method.{part}'")
        for part in ("impact_scale", "likelihood_scale"):
            scale = sm.get(part) or []
            scores = sorted(x.get("score") for x in scale if isinstance(x, dict) and isinstance(x.get("score"), int))
            if scale and scores != list(range(1, len(scale) + 1)):
                rep.error(f"scoring_method.{part}", f"scores {scores} are not 1..{len(scale)} without gaps or repeats")
        for row in sm.get("matrix") or []:
            for cell in row.get("cells", []) if isinstance(row, dict) else []:
                imp, lik, sc = row.get("impact"), cell.get("likelihood"), cell.get("score")
                if all(isinstance(v, int) for v in (imp, lik, sc)) and imp * lik != sc:
                    rep.warn("scoring_method.matrix", f"printed score {sc} at impact {imp} x likelihood {lik}: check the transcription (record it as printed if the PDF says so)")

    # strategic risk register
    srr = data.get("strategic_risk_register")
    if not isinstance(srr, dict) or not srr.get("status") or not srr.get("note"):
        rep.error("strategic_risk_register", "needs status and note (its absence must be recorded)")

    return n_quotes


def main(argv):
    hist = Path(argv[1] if len(argv) > 1 else "outputs/history.json")
    committee = Path(argv[2] if len(argv) > 2 else "data/committee")
    if not hist.is_file():
        sys.exit(f"STOP: {hist} not found.")
    if not committee.is_dir():
        sys.exit(f"STOP: {committee} not found.")
    try:
        data = json.loads(hist.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"STOP: {hist} is not valid JSON: {e}")
    rep = Report()
    n = verify(data, committee, rep) or 0
    for line in rep.errors + rep.warns:
        print(line)
    print(f"\n{len(rep.errors)} error(s), {len(rep.warns)} warning(s); {n} quote(s) checked.")
    print("PASS" if not rep.errors else "FAIL")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
