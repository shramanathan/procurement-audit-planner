#!/usr/bin/env python3
"""Build outputs/risk-register.md and outputs/auditor-comments.md from the
risk-assessor's judgments in outputs/risk-ratings.json.

Usage:
    build_register.py [--ratings F] [--rules F] [--analytics F] [--history F] [--out-dir D]

The agent judges; this script computes and checks:
  - resolves every [rule:ID], [metric:$.path] and [history:ID] citation
  - fills every {{$.path}} placeholder from analytics.json
  - computes final likelihood (base + repeat uplift), score, matrix label,
    RAG band and Corporate Risk Register escalation from the council's
    method in history.json (or a stated fallback)
  - computes financial impact from the council's £ bands when the impact
    criterion is "financial"
  - drops any risk whose likelihood or impact justification has no
    resolvable citation, or whose placeholders don't resolve
  - checks that a repeat-finding uplift cites an adverse audit opinion
  - warns when a figure is typed in prose instead of a placeholder
  - writes auditor-comments.md, keeping decisions already entered
  - on a revision, checks every auditor decision was applied and nothing
    else changed, and marks auditor overrides

State between runs: <out-dir>/risk-register-state.json.
Exit 1 on any ERROR (nothing is written in that case).
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- constants

ADVERSE_OPINIONS = {"limited assurance", "weak", "no assurance", "minimal assurance"}
ADVERSE_PROGRESS = {"unsatisfactory"}
DECISIONS = {"approve", "reject", "amend"}
IMPACT_CRITERIA = {"financial", "personal", "assets", "reputation", "compliance"}
SCOPE_TAGS = {"grant", "care_education_placement", "agency_staff", "premises", "general_procurement"}
FALLBACK_LABELS = {1: "Very low", 2: "Low", 3: "Medium", 4: "High", 5: "Very high"}
ITEM_LEVEL_TESTS = {"threshold_clustering", "split_purchases", "duplicates",
                    "expired_notice_spend", "spend_vs_award"}
MATERIAL_FIELDS = ["title", "status", "scope_tags", "likelihood.base_history", "likelihood.rubric_row", "likelihood.base", "likelihood.uplift",
                   "likelihood.uplift_history", "impact.criterion", "impact.score",
                   "impact.basis", "proposed_focus"]

CITE_RE = re.compile(r"\[(rule|metric|history):((?:[^\[\]]|\[[^\[\]]*\])+)\]")  # allows one level of [..] inside, e.g. [?tier==25000]
PLACE_RE = re.compile(r"\{\{\s*(\$[^}]*)\}\}")
TYPED_FIGURE_RE = re.compile(
    r"£\s?\d|(?<![\w.\-])\d+(?:\.\d+)?\s?%|(?<![A-Za-z\-\d.])\d{2,}(?:,\d{3})*(?:\.\d+)?(?![\d])")


class Report:
    def __init__(self):
        self.errors, self.warns, self.notes = [], [], []

    def error(self, where, msg):
        self.errors.append(f"ERROR [{where}] {msg}")

    def warn(self, where, msg):
        self.warns.append(f"WARN  [{where}] {msg}")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path, rep, required=True):
    p = Path(path)
    if not p.is_file():
        if required:
            sys.exit(f"STOP: {p} not found.")
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"STOP: {p} is not valid JSON: {e}")


# ---------------------------------------------------------------- JSON paths

SEG_RE = re.compile(r"""
    \.(?P<key>[A-Za-z_][\w\-]*)              # .key
  | \[(?P<idx>\d+)\]                         # [0]
  | \[\s*'(?P<qkey>[^']+)'\s*\]              # ['key with spaces']
  | \[\?\s*(?P<fkey>[\w\-]+)\s*==\s*(?P<fval>'[^']*'|-?\d+(?:\.\d+)?)\s*\]   # [?k==v]
""", re.X)


def resolve_path(doc, path):
    """Resolve a small JSONPath subset. Returns (ok, value_or_reason)."""
    path = path.strip()
    if not path.startswith("$"):
        return False, "path must start with $"
    pos, node = 1, doc
    while pos < len(path):
        m = SEG_RE.match(path, pos)
        if not m:
            return False, f"cannot parse path at {path[pos:]!r}"
        pos = m.end()
        if m.group("key") or m.group("qkey"):
            k = m.group("key") or m.group("qkey")
            if not isinstance(node, dict) or k not in node:
                return False, f"no key {k!r}"
            node = node[k]
        elif m.group("idx") is not None:
            i = int(m.group("idx"))
            if not isinstance(node, list) or i >= len(node):
                return False, f"no index [{i}]"
            node = node[i]
        else:
            fk, fv = m.group("fkey"), m.group("fval")
            want = fv[1:-1] if fv.startswith("'") else (float(fv) if "." in fv else int(fv))
            if not isinstance(node, list):
                return False, f"filter [?{fk}==...] needs a list"
            hits = [x for x in node if isinstance(x, dict) and x.get(fk) == want]
            if len(hits) != 1:
                return False, f"filter [?{fk}=={fv}] matched {len(hits)} items (need exactly 1)"
            node = hits[0]
    return True, node


def fmt_value(v):
    if isinstance(v, bool) or v is None:
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.0f}" if v.is_integer() and abs(v) >= 1000 else f"{v:,.2f}"
    return str(v)


# ---------------------------------------------------------------- method

def parse_money_k(text):
    """'£175k -500k' -> [175000, 500000]. Only figures after the first £."""
    if "£" not in text:
        return []
    out = []
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([kKmM])", text[text.index("£"):]):
        out.append(float(num) * (1_000 if unit.lower() == "k" else 1_000_000))
    return out


class Method:
    """The council's scoring method from history.json, or the CLAUDE.md fallback."""

    def __init__(self, history, rep):
        sm = (history or {}).get("scoring_method") or {}
        self.found = sm.get("status") == "found" and sm.get("matrix") and sm.get("rag_bands")
        self.notes, self.choices = [], []
        self.l_labels, self.i_labels, self.matrix, self.bands = {}, {}, {}, []
        self.fin_bands, self.crr_primary, self.crr_alt = [], None, None
        self.method_ds = []
        self._history = history or {}
        if not self.found:
            self.l_labels = self.i_labels = dict(FALLBACK_LABELS)
            self.notes.append("FALLBACK: history.json reports no usable council scoring method, so the "
                              "1-5 Very low...Very high scale is used for likelihood and impact (CLAUDE.md). "
                              "No matrix label, RAG band or register escalation is available.")
            return
        src = Path(sm.get("source", "risk-management-strategy-2024-27.pdf")).name if isinstance(sm.get("source"), str) else "Risk Management Strategy"
        self.l_labels = {x["score"]: x["label"] for x in sm["likelihood_scale"]}
        self.i_labels = {x["score"]: x["label"] for x in sm["impact_scale"]}
        for row in sm["matrix"]:
            for c in row["cells"]:
                self.matrix[(row["impact"], c["likelihood"])] = (c.get("score"), c.get("band"))
        for b in sm["rag_bands"]:
            rng = str(b.get("score_range", ""))
            m = re.search(r"(\d+)\s*-\s*(\d+)", rng) or None
            if m:
                lo, hi = int(m.group(1)), int(m.group(2))
            else:
                m = re.search(r"up to\s*(\d+)", rng, re.I)
                if not m:
                    rep.error("method", f"cannot parse RAG score range {rng!r}")
                    continue
                lo, hi = 0, int(m.group(1))
            self.bands.append({"level": b["level"], "colour": b.get("colour"), "lo": lo, "hi": hi, "printed": rng,
                               "escalation": b.get("escalation") or "", "response": b.get("response") or ""})
        # financial £ bands from Table 1 (percentages are not used)
        for x in sorted(sm["impact_scale"], key=lambda x: x["score"]):
            vals = parse_money_k((x.get("criteria") or {}).get("financial", ""))
            self.fin_bands.append((x["score"], vals))
        lows = {}
        for score, vals in self.fin_bands:
            if score == 1:
                lows[score] = 0.0
            elif vals:
                lows[score] = vals[0]
        if len(lows) == len(self.fin_bands) == 5:
            self.fin_lows = lows
            self.choices.append("Financial impact is banded on the £ figures in Table 1 (lower bound of each band; "
                                "a value exactly on a shared boundary goes to the higher band). The percentage "
                                "bands are not used: the annual WBC budget is not in the papers"
                                + self._ds_ref(["overlap"]) + ".")
        else:
            self.fin_lows = None
            rep.warn("method", "could not parse all five £ bands from Table 1; financial impact must be scored by the agent")
        # Corporate Risk Register escalation: primary from the RAG table, alternative from other statements
        for b in self.bands:
            if "corporate risk register" in b["escalation"].lower():
                self.crr_primary = (b["lo"], f"Table 4 ({b['level']} {b['lo']}-{b['hi']})")
        for rc in sm.get("register_criteria") or []:
            crit = " ".join(rc.get("criteria") or []) if isinstance(rc.get("criteria"), list) else str(rc.get("criteria"))
            m = re.search(r"Score\s+(\d+)\s+or above", crit, re.I)
            if m and "corporate" in str(rc.get("register", "")).lower():
                self.crr_alt = (int(m.group(1)), f"{rc.get('from', 'register criteria')} (score {m.group(1)} or above)")
        if self.crr_primary and self.crr_alt and self.crr_primary[0] != self.crr_alt[0]:
            self.choices.append(
                f"CONFLICT: Corporate Risk Register escalation is {self.crr_primary[1]} in one place and "
                f"{self.crr_alt[1]} in another" + self._ds_ref(["Corporate Risk Register", "Score"]) +
                f". This register USES {self.crr_primary[1]}, the table that also sets the response; "
                f"the column 'CRR alt.' MARKS risks that would be escalated under {self.crr_alt[1]}.")
        self.choices.append("Matrix label (Figure 1) and RAG band (Table 4) are both shown; their names differ "
                            "for the same scores" + self._ds_ref(["Medium - High"]) +
                            ". The RAG band sets escalation and response.")
        if "no matching" not in self._ds_ref(["Medium (2)"]):
            self.choices.append("Impact scores are taken from Table 1 (Medium = " +
                                str({v: k for k, v in self.i_labels.items()}.get("Medium", "?")) +
                                "); the 'Medium (2)' in paragraph 4.3 is not used" + self._ds_ref(["Medium (2)"]) + ".")
        # every discrepancy located in the scoring pages of the strategy
        for d in history.get("discrepancies", []):
            for loc in d.get("locations", []):
                try:
                    pg = int(loc.get("pdf_page"))
                except (TypeError, ValueError):
                    continue
                if "risk-management-strategy" in str(loc.get("source")) and 13 <= pg <= 21:
                    self.method_ds.append(d)
                    break
        self.source = src

    def _ds_ref(self, words):
        """Cite the recorded discrepancies whose description contains all the words."""
        ids = [d["id"] for d in self._history.get("discrepancies", [])
               if all(w.lower() in d.get("description", "").lower() for w in words)]
        return f" [history:{', '.join(ids)}]" if ids else " (no matching discrepancy recorded)"

    def band_for(self, score):
        hits = [b for b in self.bands if b["lo"] <= score <= b["hi"]]
        return hits[0] if len(hits) == 1 else None

    def financial_score(self, value):
        if not self.fin_lows:
            return None
        return max(s for s, lo in self.fin_lows.items() if value >= lo)


# ---------------------------------------------------------------- citations

class Sources:
    def __init__(self, rules, analytics, history):
        self.rules = {r["rule_id"]: r for r in (rules or {}).get("rules", [])}
        self.analytics = analytics
        self.history = {}
        for k in ("audit_opinions", "agreed_actions", "risk_themes", "discrepancies"):
            for it in (history or {}).get(k, []):
                self.history[it["id"]] = it

    def resolve(self, kind, ref):
        ref = ref.strip()
        if kind == "rule":
            r = self.rules.get(ref)
            return (True, f"{ref} (cl. {r['clause']})") if r else (False, f"no rule {ref} in rules.json")
        if kind == "history":
            h = self.history.get(ref)
            if not h:
                return False, f"no history item {ref}"
            if ref.startswith("AO-"):
                return True, f"{ref}: {h.get('audit_title')}, {h.get('opinion') or 'no opinion'} ({h.get('period')})"
            if ref.startswith("RT-"):
                return True, f"{ref}: {h.get('theme')}"
            return True, ref
        ok, val = resolve_path(self.analytics, ref)
        if not ok:
            return False, f"metric {ref}: {val}"
        if isinstance(val, (dict, list)):
            return False, f"metric {ref} is a {type(val).__name__}, not a value"
        m = re.match(r"\$\.tests\.(\w+)", ref)
        if m and not re.search(r"\.(status|reason)$", ref):
            st = self.analytics.get("tests", {}).get(m.group(1), {}).get("status")
            if st != "ran":
                return False, f"metric {ref}: test {m.group(1)} status is {st!r}"
        return True, f"{ref} = {fmt_value(val)}"


def text_fields(risk):
    out = [("description", risk.get("description", "")),
           ("likelihood.justification", (risk.get("likelihood") or {}).get("justification", "")),
           ("impact.justification", (risk.get("impact") or {}).get("justification", "")),
           ("proposed_focus", risk.get("proposed_focus", ""))]
    for i, e in enumerate(risk.get("evidence") or []):
        out.append((f"evidence[{i}]", e))
    return out


def render_text(text, src, problems, cites_seen):
    def place(m):
        ok, val = resolve_path(src.analytics, m.group(1))
        if not ok or isinstance(val, (dict, list)):
            problems.append(f"placeholder {{{{{m.group(1)}}}}} does not resolve to a value")
            return "⚠UNRESOLVED"
        return fmt_value(val)

    def cite(m):
        ok, label = src.resolve(m.group(1), m.group(2))
        cites_seen.append((m.group(1), m.group(2).strip(), ok, label))
        if m.group(1) == "metric":
            return f"[metric: `{m.group(2).strip()}`]" if ok else f"[⚠ unresolved metric `{m.group(2).strip()}`]"
        return f"[{m.group(2).strip()}]" if ok else f"[⚠ unresolved {m.group(1)}:{m.group(2).strip()}]"

    return CITE_RE.sub(cite, PLACE_RE.sub(place, text or ""))


def typed_figures(text):
    """Figures written into prose rather than filled from a placeholder."""
    stripped = PLACE_RE.sub(" ", CITE_RE.sub(" ", text or ""))
    return [m.group(0) for m in TYPED_FIGURE_RE.finditer(stripped)]


def get_field(risk, dotted):
    node = risk
    for part in dotted.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node


# ---------------------------------------------------------------- auditor comments

def parse_comments(path):
    """Return ({risk_id: {decision, comment}}, notes_block)."""
    p = Path(path)
    if not p.is_file():
        return {}, ""
    decisions, notes, in_notes = {}, [], False
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("## Auditor notes"):
            in_notes = True
            continue
        if in_notes:
            notes.append(line)
            continue
        if re.match(r"^\|\s*R-\d+", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 6:
                decisions[cells[0]] = {"decision": cells[4], "comment": " | ".join(cells[5:]).strip()}
    return decisions, "\n".join(notes).strip("\n")


def parse_signoff(path):
    """Reviewer and date from a line like 'Reviewer: NAME. Date: YYYY-MM-DD.' anywhere in the file.
    Returns {'reviewer': str|None, 'date': str|None}."""
    out = {"reviewer": None, "date": None}
    p = Path(path)
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        m = re.search(r"Reviewer:\s*(.*?)\s*(?:\.\s*)?(?:Date:|$)", line)
        if m and out["reviewer"] is None:
            name = m.group(1).strip().rstrip(".").strip()
            if name and not name.startswith("(") and not re.fullmatch(r"[_\-\s.]*|<[^>]*>|NAME", name):
                out["reviewer"] = name
        d = re.search(r"Date:\s*(\d{4}-\d{2}-\d{2})", line)
        if d and out["date"] is None:
            try:
                dt.date.fromisoformat(d.group(1))
                out["date"] = d.group(1)
            except ValueError:
                pass
    return out


def cell(s):
    return str(s).replace("|", "/").replace("\n", " ").strip()


# ---------------------------------------------------------------- build

def build(args):
    rep = Report()
    out = Path(args.out_dir)
    ratings = load_json(args.ratings, rep)
    rules = load_json(args.rules, rep)
    analytics = load_json(args.analytics, rep)
    history = load_json(args.history, rep)
    state_path = out / "risk-register-state.json"
    comments_path = out / "auditor-comments.md"
    state = load_json(state_path, rep, required=False)

    src = Sources(rules, analytics, history)
    method = Method(history, rep)

    # ---- structure of risk-ratings.json
    risks = ratings.get("risks")
    if not isinstance(risks, list) or not risks:
        rep.error("ratings", "risks must be a non-empty list")
        risks = []
    ids = [r.get("risk_id") for r in risks]
    if state is None or ratings.get("revision") is None:
        for i, rid in enumerate(ids, start=1):
            if rid != f"R-{i:02d}" and not (state and rid in {r["risk_id"] for r in state["current"]["risks"]}):
                rep.error(f"risks[{i - 1}]", f"risk_id {rid!r}: new risks are numbered R-01, R-02, ... in order")
    else:
        # in a revision, new risks continue after the highest id ever used (dropped ids are not reused)
        if ratings["revision"].get("number") == state.get("revision") and state.get("base"):
            current = {r["risk_id"] for r in state["base"]["risks"]}      # re-render: compare with what it revised
        else:
            current = {r["risk_id"] for r in state["current"]["risks"]}
        used = (current | {r["risk_id"] for r in state["current"]["risks"]}
                | {r["risk_id"] for r in (state.get("base") or {}).get("risks", [])}
                | set(state.get("dropped", [])) | {e.get("risk_id") for e in state.get("log", [])})
        used_before = {k for k in used if k not in {r["risk_id"] for r in state["current"]["risks"]}} - current
        nxt = max([int(k[2:]) for k in used if re.fullmatch(r"R-\d+", str(k))
                   and k not in set(ids) - current] or [0]) + 1
        for i, rid in enumerate(ids):
            if rid in current:
                continue
            if rid in used_before:
                rep.error(f"risks[{i}]", f"risk_id {rid!r} was used before (dropped or removed); ids are never reused")
            elif rid != f"R-{nxt:02d}":
                rep.error(f"risks[{i}]", f"risk_id {rid!r}: the next new risk must be R-{nxt:02d}")
            nxt += 1
    if len(set(ids)) != len(ids):
        rep.error("ratings", "duplicate risk_id")

    decisions, notes_block = parse_comments(comments_path)
    signoff = parse_signoff(comments_path)
    for rid, d in decisions.items():
        if d["decision"] and d["decision"].lower() not in DECISIONS:
            rep.error(f"auditor-comments {rid}", f"decision {d['decision']!r} must be Approve, Reject, Amend or blank")

    # ---- revision checks
    revision = ratings.get("revision")
    prev_rev = state["revision"] if state else None
    any_decision = any(d["decision"] for d in decisions.values())
    base = None
    if revision is None:
        if any_decision:
            rep.error("revision", "auditor-comments.md holds decisions; write a 'revision' block in risk-ratings.json "
                                  "that applies them (see SKILL.md)")
        rev_no = 0
    else:
        rev_no = revision.get("number")
        if not isinstance(rev_no, int) or rev_no < 1:
            rep.error("revision", "revision.number must be an integer >= 1")
        elif state is None:
            rep.error("revision", "no earlier build state found; a revision needs the draft it revises")
        elif rev_no == prev_rev + 1:
            base = state["current"]
        elif rev_no == prev_rev and state.get("base"):
            base = state["base"]          # re-render of the same revision
        else:
            rep.error("revision", f"revision.number {rev_no} does not follow the last build ({prev_rev})")
        if not signoff["reviewer"] or not signoff["date"]:
            rep.error("auditor-comments", "a revision needs the auditor's sign-off line in auditor-comments.md: "
                                          "'Reviewer: NAME. Date: YYYY-MM-DD.' (found reviewer="
                                          f"{signoff['reviewer']!r}, date={signoff['date']!r})")
    # log of decisions applied in earlier revisions (kept in the state file)
    prior_log = [e for e in (state or {}).get("log", []) if isinstance(rev_no, int) and e.get("revision", 0) < rev_no]
    overrides, this_log = {}, []
    if base is not None:
        this_log = check_revision(base, ratings, revision, decisions, rep, overrides, rev_no, prior_log,
                                  set((state or {}).get("dropped", [])))
    cur = {r.get("risk_id"): r for r in risks}
    authorised = {}
    for e in prior_log + this_log:
        if e.get("auditor_set") and get_field(cur.get(e["risk_id"], {}), e["field"]) == e.get("value"):
            authorised.setdefault(e["risk_id"], set()).add(e["field"])

    # ---- per-risk evaluation
    built, dropped = [], []
    for r in risks:
        rid = r.get("risk_id", "?")
        reasons, problems, rendered = [], [], {}
        lk, im = r.get("likelihood") or {}, r.get("impact") or {}
        # likelihood
        lbase = lk.get("base")
        if not isinstance(lbase, int) or not 1 <= lbase <= 5:
            rep.error(rid, "likelihood.base must be an integer 1-5")
            continue
        auth = authorised.get(rid, set())
        row = lk.get("rubric_row")
        if not (isinstance(row, str) and re.fullmatch(r"L[1-5]", row)):
            rep.error(rid, f"likelihood.rubric_row {row!r} must be L1-L5")
            continue
        auditor_l_note = None
        if row != f"L{lbase}":
            if "likelihood.base" in auth:
                auditor_l_note = (f"Auditor-set likelihood {lbase}; the rubric row the evidence supports is {row} "
                                  f"(base {row[1]}).")
            else:
                rep.error(rid, f"likelihood.rubric_row {row!r} must be 'L{lbase}' (the rubric row that gives the base); "
                               "a different base needs an auditor Amend that sets it")
        uplift = lk.get("uplift", 0)
        if uplift not in (0, 1):
            rep.error(rid, "likelihood.uplift must be 0 or 1")
            continue
        double = set(lk.get("base_history") or []) & set(lk.get("uplift_history") or [])
        if double:
            rep.error(rid, f"{sorted(double)} used for both the rubric row and the uplift; count a finding once")
        tags = r.get("scope_tags")
        if not isinstance(tags, list) or not tags or not set(tags) <= SCOPE_TAGS:
            rep.error(rid, f"scope_tags must be a non-empty list from {sorted(SCOPE_TAGS)}")
        if r.get("status", "proposed") not in ("proposed", "rejected"):
            rep.error(rid, "status must be 'proposed' or 'rejected'")
        uplift_note = None
        if uplift == 1:
            hist_ids = lk.get("uplift_history") or []
            adverse = []
            for hid in hist_ids:
                h = src.history.get(hid)
                if h and hid.startswith("AO-") and (
                        str(h.get("opinion") or "").lower() in ADVERSE_OPINIONS
                        or str(h.get("implementation_progress") or "").lower() in ADVERSE_PROGRESS):
                    adverse.append(hid)
            if not adverse:
                uplift = 0
                uplift_note = (f"Repeat-finding uplift REJECTED: {hist_ids or 'no history cited'} "
                               f"contains no audit opinion that is adverse ({', '.join(sorted(ADVERSE_OPINIONS))}) "
                               f"or has 'Unsatisfactory' implementation progress.")
                rep.warn(rid, uplift_note)
            else:
                uplift_note = f"+1 repeat-finding uplift: adverse opinion in {', '.join(adverse)}."
        lfinal = min(5, lbase + uplift)
        # impact
        crit = im.get("criterion")
        if crit not in IMPACT_CRITERIA:
            rep.error(rid, f"impact.criterion {crit!r} not in {sorted(IMPACT_CRITERIA)}")
            continue
        iscore, impact_note = im.get("score"), None
        if crit == "financial" and method.found and method.fin_lows:
            basis = im.get("basis")
            ok, val = resolve_path(analytics, basis or "")
            if not basis or not ok or not isinstance(val, (int, float)) or isinstance(val, bool):
                reasons.append(f"financial impact basis {basis!r} does not resolve to a number")
            else:
                computed = method.financial_score(float(val))
                impact_note = f"Financial band computed from `{basis}` = £{fmt_value(val)} (value exposed, not proven loss)."
                if iscore is not None and iscore != computed and "impact.score" in auth:
                    impact_note += f" Auditor-set impact {iscore}; the council's £ bands give {computed}."
                else:
                    if iscore is not None and iscore != computed:
                        rep.warn(rid, f"impact.score {iscore} replaced by {computed}, computed from basis {basis} = {fmt_value(val)}")
                    iscore = computed
        if not isinstance(iscore, int) or not 1 <= iscore <= 5:
            rep.error(rid, "impact.score must be an integer 1-5 (or a resolvable financial basis)")
            continue
        # citations and placeholders
        cites = {}
        for name, text in text_fields(r):
            seen = []
            rendered[name] = render_text(text, src, problems, seen)
            cites[name] = seen
            figs = typed_figures(text)
            if figs:
                rep.warn(rid, f"{name}: figure(s) typed in prose {figs[:3]}; use {{{{$.path}}}} placeholders")
        for name in ("likelihood.justification", "impact.justification"):
            if not any(ok for _, _, ok, _ in cites[name]):
                reasons.append(f"{name} has no resolvable citation")
        for name, seen in cites.items():
            for kind, ref, ok, label in seen:
                if not ok:
                    rep.warn(rid, f"{name}: unresolved citation [{kind}:{ref}]: {label}")
        if problems:
            reasons.extend(sorted(set(problems)))
        # rubric cap: L4+ needs an item-level test metric
        metric_tests = set()
        for kind, ref, ok, _label in cites["likelihood.justification"]:
            m = re.match(r"\$\.tests\.(\w+)", ref)
            if ok and kind == "metric" and m:
                metric_tests.add(m.group(1))
        if int(row[1]) >= 4 and not (metric_tests & ITEM_LEVEL_TESTS):
            rep.warn(rid, "rubric: L4/L5 needs a cited metric from an item-level test "
                          f"({', '.join(sorted(ITEM_LEVEL_TESTS))}) in the likelihood justification")
        if reasons:
            dropped.append({"risk_id": rid, "title": r.get("title"), "reasons": reasons})
            continue
        score = lfinal * iscore
        mlabel, band = None, None
        if method.found:
            printed = method.matrix.get((iscore, lfinal))
            if printed:
                if printed[0] is not None and printed[0] != score:
                    rep.warn(rid, f"matrix prints {printed[0]} at impact {iscore} x likelihood {lfinal}; computed {score} is used")
                mlabel = printed[1]
            band = method.band_for(score)
            if band is None:
                rep.warn(rid, f"score {score} falls in no RAG band")
        crr = (method.crr_primary and score >= method.crr_primary[0])
        crr_alt = (method.crr_alt and score >= method.crr_alt[0])
        built.append({"risk": r, "rid": rid, "lbase": lbase, "uplift": uplift, "lfinal": lfinal,
                      "uplift_note": uplift_note, "auditor_l_note": auditor_l_note,
                      "iscore": iscore, "impact_note": impact_note,
                      "score": score, "mlabel": mlabel, "band": band, "crr": bool(crr), "crr_alt": bool(crr_alt),
                      "rendered": rendered, "cites": cites, "override": overrides.get(rid)})

    for d in dropped:
        rep.warn(d["risk_id"], "DROPPED: " + "; ".join(d["reasons"]))
    if rep.errors:
        return rep, None

    # ---- write outputs
    inputs = {k: {"file": str(p), "sha256": sha256(p)} for k, p in
              (("rules", args.rules), ("analytics", args.analytics), ("history", args.history), ("ratings", args.ratings))}
    log = prior_log + this_log
    register = render_register(ratings, built, dropped, method, history, inputs, rev_no, revision, decisions,
                               overrides, rep, signoff, log)
    out.mkdir(parents=True, exist_ok=True)
    (out / "risk-register.md").write_text(register, encoding="utf-8")
    (out / "auditor-comments.md").write_text(render_comments(built, decisions, notes_block, rev_no), encoding="utf-8")
    new_state = {"revision": rev_no, "built_at": now(), "inputs": inputs,
                 "base": base if base is not None else (state.get("base") if state and rev_no == prev_rev else None),
                 "current": copy.deepcopy(ratings), "signoff": signoff, "log": log,
                 "dropped": sorted(set((state or {}).get("dropped", [])) | {d["risk_id"] for d in dropped})}
    state_path.write_text(json.dumps(new_state, indent=1, ensure_ascii=False), encoding="utf-8")
    return rep, {"built": len(built), "dropped": len(dropped), "revision": rev_no}


def check_revision(base, ratings, revision, decisions, rep, overrides, rev_no, prior_log, prev_dropped=()):
    """Every Amend/Reject applied (now or in an earlier revision); nothing changed that wasn't asked for.
    Returns this revision's log entries."""
    old = {r["risk_id"]: r for r in base.get("risks", [])}
    new = {r["risk_id"]: r for r in ratings.get("risks", [])}
    changes = revision.get("changes") or []
    for i, c in enumerate(changes):
        for k in ("risk_id", "field", "requested_by"):
            if not c.get(k):
                rep.error(f"revision.changes[{i}]", f"missing {k!r}")
    # what actually changed
    diffs = {}
    for rid in set(old) | set(new):
        if rid not in new:
            diffs[rid] = ["removed"]
        elif rid not in old:
            diffs[rid] = ["added"]
        else:
            fs = [f for f in MATERIAL_FIELDS if get_field(old[rid], f) != get_field(new[rid], f)]
            for f in ("likelihood.justification", "impact.justification", "description"):
                if get_field(old[rid], f) != get_field(new[rid], f):
                    fs.append(f)
            if fs:
                diffs[rid] = fs
    declared = {}
    for c in changes:
        declared.setdefault(c.get("risk_id"), []).append(c)

    def request(rid_req):
        d = decisions.get(rid_req, {})
        return d.get("decision", "").lower(), d.get("comment", "")

    # 1. every change was asked for, and declared
    for rid, fs in diffs.items():
        if fs == ["removed"] and rid in prev_dropped:
            continue                      # never rated, never shown to the auditor
        if fs == ["removed"]:
            old_dec = request(rid)[0]
            what = "an approved risk" if old_dec == "approve" else "a risk"
            rep.error(rid, f"{what} was removed from risk-ratings.json; risks are never deleted "
                           "(a rejected risk stays, with status 'rejected')")
            continue
        decl = declared.get(rid)
        if not decl:
            rep.error(rid, f"changed ({', '.join(fs)}) but no revision.changes entry declares it: "
                           "the auditor did not ask for this change")
            continue
        for c in decl:
            dec, com = request(c.get("requested_by"))
            asked = dec in ("amend", "reject") or (fs == ["added"] and com)
            if not asked:
                rep.error(rid, f"change to {c.get('field')} cites {c.get('requested_by')!r}, but that row has no "
                               "Amend/Reject decision (or, for a new risk, no comment) in auditor-comments.md")
    # 2. every Amend/Reject decision was applied, in this revision or an earlier one
    for rid, d in decisions.items():
        dec, com = request(rid)
        if dec not in ("amend", "reject"):
            continue
        applied = [c for c in changes if c.get("requested_by") == rid]
        before = [e for e in prior_log if e.get("requested_by") == rid
                  and e.get("decision") == dec and e.get("comment") == com]
        if not applied and not before:
            rep.error(rid, f"auditor decision '{d['decision']}' is not applied: no revision.changes entry has requested_by {rid}")
            continue
        if dec == "reject" and (new.get(rid) or {}).get("status") != "rejected":
            rep.error(rid, "auditor rejected this risk but its status is not 'rejected'")
        if applied and dec == "amend" and rid not in diffs and not any(c.get("risk_id") != rid for c in applied):
            rep.error(rid, "auditor asked for an amendment but nothing in the risk changed")
    # 3. declared changes that did not happen
    for c in changes:
        rid = c.get("risk_id")
        if rid not in diffs:
            rep.error(rid or "?", f"revision.changes declares a change to {c.get('field')} but the risk is unchanged")
    # overrides
    for rid in diffs:
        if rid in new and rid in declared:
            o, n = old.get(rid, {}), new[rid]
            parts = []
            for f, lab in (("likelihood.base", "likelihood base"), ("likelihood.uplift", "uplift"),
                           ("impact.score", "impact"), ("status", "status")):
                if get_field(o, f) != get_field(n, f):
                    parts.append(f"{lab} {get_field(o, f)} → {get_field(n, f)}")
            if diffs[rid] == ["added"]:
                parts = ["new risk added at the auditor's request"]
            reqs = sorted({c.get("requested_by") for c in declared[rid]})
            overrides[rid] = {"parts": parts or ["wording/scope"],
                              "comment": "; ".join(decisions.get(q, {}).get("comment", "") for q in reqs).strip("; "),
                              "requested_by": reqs, "reasons": [c.get("reason", "") for c in declared[rid]],
                              "added": diffs[rid] == ["added"]}
    # log entries for this revision
    log = []
    for c in changes:
        rid, field = c.get("risk_id"), c.get("field")
        dec, com = request(c.get("requested_by"))
        is_new = diffs.get(rid) == ["added"]
        log.append({"revision": rev_no, "risk_id": rid, "field": field, "requested_by": c.get("requested_by"),
                    "decision": dec, "comment": com, "reason": c.get("reason", ""),
                    "value": get_field(new.get(rid, {}), field) if field else None,
                    "auditor_set": field in ("likelihood.base", "impact.score")
                                   and (dec == "amend" or (is_new and bool(com)))})
    return log


def now():
    return dt.datetime.now().replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- rendering

def render_register(ratings, built, dropped, method, history, inputs, rev_no, revision, decisions, overrides, rep,
                    signoff, log):
    L = []
    active = [b for b in built if b["risk"].get("status", "proposed") != "rejected"]
    rejected = [b for b in built if b["risk"].get("status") == "rejected"]
    L.append("# Procurement risk register: West Berkshire Council\n")
    who = (f" · auditor decisions by {signoff['reviewer']}, dated {signoff['date']}"
           if rev_no and signoff.get("reviewer") and signoff.get("date") else "")
    L.append(f"**{'Revision ' + str(rev_no) if rev_no else 'Draft (revision 0)'}**{who} · built {now()} by "
             "`.claude/skills/risk-assessment/build_register.py`\n")
    L.append("> Risk indicators to investigate, not findings of wrongdoing. Every figure below is filled from "
             "`outputs/analytics.json`; every rating cites a rule, a metric or a history item.\n")
    L.append("## Method\n")
    if method.found:
        L.append(f"- Scale: the council's own 5x5 method from the Risk Management Strategy 2024-2027 "
                 f"(recorded in `outputs/history.json` → `scoring_method`). Score = likelihood x impact.")
        L.append("- Likelihood: " + ", ".join(f"{k} {v}" for k, v in sorted(method.l_labels.items())) +
                 ". Impact: " + ", ".join(f"{k} {v}" for k, v in sorted(method.i_labels.items())) + ".")
        L.append("- RAG bands (as printed): " + "; ".join(f"{b['level']}{' (' + b['colour'] + ')' if b['colour'] else ''} "
                                                        f"{b['printed']}" for b in method.bands) + ".")
    for n in method.notes:
        L.append(f"- **{n}**")
    L.append("- Likelihood base comes from the rubric in the risk-assessment skill; a repeat finding on the same "
             "theme adds one point (cap 5) only when it cites an adverse audit opinion.")
    if method.choices or method.method_ds:
        L.append("\n### Conflicts in the scoring method and how this register handles them\n")
        for c in method.choices:
            L.append(f"- {c}")
        handled = set(re.findall(r"DS-\d+", " ".join(method.choices)))
        rest = [d for d in method.method_ds if d["id"] not in handled]
        if rest:
            L.append("\nOther discrepancies recorded on the scoring pages; they do not change how scores, bands "
                     "or escalation are computed here:\n")
            for d in rest:
                L.append(f"- [{d['id']}] {d['description']}")
    L.append("\n### Inputs\n")
    for k, v in inputs.items():
        L.append(f"- {k}: `{v['file']}` sha256 `{v['sha256'][:16]}…`")
    if revision:
        L.append(f"\n## Revision {rev_no}: what changed\n")
        L.append(f"Responds to the auditor decisions in `outputs/auditor-comments.md` by {signoff.get('reviewer')}, "
                 f"dated {signoff.get('date')}. {cellsafe(revision.get('summary', ''))}\n")
        L.append("| Risk | Field | Requested by | Auditor comment | Change |")
        L.append("|---|---|---|---|---|")
        for c in revision.get("changes", []):
            com = decisions.get(c.get("requested_by"), {}).get("comment", "")
            how = decisions.get(c.get('requested_by'), {}).get('decision') or 'comment'
            L.append(f"| {c.get('risk_id')} | {c.get('field')} | {c.get('requested_by')} "
                     f"({how}) | {cell(com)} | {cell(c.get('reason', ''))} |")
        ovr = sorted(k for k, o in overrides.items() if not o.get("added"))
        new = sorted(k for k, o in overrides.items() if o.get("added"))
        if ovr:
            L.append("\nAuditor overrides (marked ⚑ below): " + ", ".join(ovr) + ".")
        if new:
            L.append("\nNew risks added at the auditor's request (marked ＋ below): " + ", ".join(new) + ".")
    L.append("\n## Summary\n")
    alt = method.crr_alt[1] if method.crr_alt else None
    hdr = "| ID | Risk | L | I | Score | Matrix label | RAG band | CRR (used) |" + (" CRR alt. (marked) |" if alt else "")
    L.append(hdr)
    L.append("|" + "---|" * (hdr.count("|") - 1))
    def mark(b):
        o = b["override"]
        return "" if not o else (" ＋" if o.get("added") else " ⚑")

    for b in active:
        flag = mark(b)
        row = (f"| {b['rid']}{flag} | {cell(b['risk'].get('title'))} | {b['lfinal']} | {b['iscore']} | {b['score']} | "
               f"{b['mlabel'] or '-'} | {(b['band'] or {}).get('level', '-')} | {'yes' if b['crr'] else 'no'} |")
        if alt:
            row += f" {'⚠ yes' if b['crr_alt'] and not b['crr'] else ('yes' if b['crr_alt'] else 'no')} |"
        L.append(row)
    if alt:
        L.append(f"\n*CRR (used)*: {method.crr_primary[1]}. *CRR alt.*: {alt}; ⚠ marks a risk that only the "
                 "alternative would escalate.")
    for b in active:
        r = b["risk"]
        L.append(f"\n## {b['rid']}. {r.get('title')}{mark(b)}\n")
        if b["override"]:
            o = b["override"]
            if o.get("added"):
                L.append(f"> ＋ **Added at the auditor's request** (comment on {', '.join(o['requested_by'])}): "
                         f"\"{o['comment']}\" Rated by the rubric; awaiting the auditor's decision.\n")
            else:
                L.append(f"> ⚑ **Auditor override** ({', '.join(o['requested_by'])}): {', '.join(o['parts'])}. "
                         f"Auditor comment: \"{o['comment']}\"\n")
        L.append(f"**Risk.** {b['rendered']['description']}\n")
        ll = method.l_labels.get(b['lfinal'], '')
        L.append(f"**Likelihood: {b['lfinal']} ({ll})**, rubric row {r['likelihood']['rubric_row']} "
                 f"(base {b['lbase']}){' + 1 uplift' if b['uplift'] else ''}. {b['rendered']['likelihood.justification']}")
        if b["uplift_note"]:
            L.append(f"*{b['uplift_note']}*")
        if b["auditor_l_note"]:
            L.append(f"*⚑ {b['auditor_l_note']}*")
        il = method.i_labels.get(b['iscore'], '')
        L.append(f"\n**Impact: {b['iscore']} ({il})**, criterion: {r['impact']['criterion']}. "
                 f"{b['rendered']['impact.justification']}")
        if b["impact_note"]:
            L.append(f"*{b['impact_note']}*")
        band = b["band"] or {}
        L.append(f"\n**Score {b['score']}**: matrix label {b['mlabel'] or '-'}, RAG band {band.get('level', '-')}"
                 f"{' (' + band['colour'] + ')' if band.get('colour') else ''}. "
                 f"Escalation: {band.get('escalation') or '-'}. Response: {band.get('response') or '-'}")
        L.append("\n**Evidence.**")
        seen = set()
        for name, cs in b["cites"].items():
            for kind, ref, ok, label in cs:
                if (kind, ref) not in seen and ok:
                    seen.add((kind, ref))
                    L.append(f"- {kind}: {label}")
        for i, raw in enumerate(r.get("evidence") or []):
            if CITE_RE.sub("", raw).strip():
                L.append(f"- {b['rendered'][f'evidence[{i}]']}")
        L.append(f"\n**Proposed focus.** {b['rendered']['proposed_focus']}")
    if rejected:
        L.append("\n## Excluded by the auditor (rejected)\n")
        L.append("Rated, then rejected at the auditor gate. Not in scope for the audit program.\n")
        for b in rejected:
            com = decisions.get(b["rid"], {}).get("comment") or (b["override"] or {}).get("comment", "")
            L.append(f"- {b['rid']} {b['risk'].get('title')} (was {b['lfinal']} x {b['iscore']} = {b['score']}). "
                     f"Auditor's reason: \"{com}\"")
    if dropped:
        L.append("\n## Excluded: no resolvable citation\n")
        L.append("These risks were proposed but cannot be evidenced from the sources, so they are not rated.\n")
        for d in dropped:
            L.append(f"- {d['risk_id']} {d['title']}: {'; '.join(d['reasons'])}")
    if rep.warns:
        L.append("\n## Build notes\n")
        for w in rep.warns:
            L.append(f"- {w}")
    L.append("\n## Auditor decisions\n")
    L.append("Record a decision for every risk in `outputs/auditor-comments.md` (Approve, Reject or Amend, with "
             "a comment for Reject/Amend). The risk-assessor then writes a revision; this builder refuses a "
             "revision that leaves a decision unapplied or changes anything the auditor did not ask for.\n")
    if signoff.get("reviewer") or signoff.get("date"):
        L.append(f"Decisions by {signoff.get('reviewer') or '(reviewer not given)'}, dated "
                 f"{signoff.get('date') or '(date not given)'}.\n")
    L.append("| Risk | Decision | Comment | How applied |")
    L.append("|---|---|---|---|")
    for b in built:
        d = decisions.get(b["rid"], {})
        L.append(f"| {b['rid']} | {cell(d.get('decision', '')) or '_pending_'} | {cell(d.get('comment', ''))} | "
                 f"{how_applied(b['rid'], d, log, built, rev_no)} |")
    n_dec = sum(1 for b in built if decisions.get(b["rid"], {}).get("decision"))
    L.append(f"\n{n_dec} of {len(built)} risks decided; {len(built) - n_dec} pending.")
    return "\n".join(L) + "\n"


def how_applied(rid, d, log, built, rev_no):
    """One line saying what the builder verified for this decision row."""
    dec, com = (d.get("decision") or "").lower(), d.get("comment") or ""
    mine = [e for e in log if e["requested_by"] == rid and e["decision"] == dec and e["comment"] == com]
    revs = sorted({e["revision"] for e in mine})
    rtxt = ", ".join(str(r) for r in revs)
    added = sorted({e["risk_id"] for e in log if e["requested_by"] == rid and e["risk_id"] != rid})
    extra = f"; new risk {', '.join(added)} added at this row's request" if added else ""
    if dec == "approve":
        return ("Approved: kept unchanged (checked against the previous revision)" if rev_no
                else "Approved: kept unchanged") + extra
    if dec == "reject":
        return f"Rejected in revision {rtxt}: moved to Excluded by the auditor, with the reason" + extra
    if dec == "amend":
        fields = sorted({e["field"] for e in mine if e["risk_id"] == rid})
        aset = any(e.get("auditor_set") and e["risk_id"] == rid for e in mine)
        return (f"Amended in revision {rtxt}: {', '.join(fields) or 'see revision table'}; ⚑ auditor override"
                + ("; score set by the auditor" if aset else "") + extra)
    return "_pending_" + extra


def cellsafe(s):
    return str(s or "").replace("\n", " ")


def render_comments(built, decisions, notes_block, rev_no):
    L = [f"# Auditor decisions: risk register {'revision ' + str(rev_no) if rev_no else 'draft (revision 0)'}\n",
         "Fill in **Decision** (Approve, Reject or Amend) and **Comment** for every risk. Reject and Amend need "
         "a comment saying what to change. Only edit the Decision and Comment cells; the builder keeps what you "
         "write here when it rewrites this file. Before a revision, replace the sign-off line under Auditor notes "
         "with your name and the date (`Reviewer: NAME. Date: YYYY-MM-DD.`).\n",
         "| Risk | Title | L x I = Score | RAG band | Decision | Comment |",
         "|---|---|---|---|---|---|"]
    for b in built:
        d = decisions.get(b["rid"], {})
        L.append(f"| {b['rid']} | {cell(b['risk'].get('title'))} | {b['lfinal']} x {b['iscore']} = {b['score']} | "
                 f"{(b['band'] or {}).get('level', '-')} | {cell(d.get('decision', ''))} | {cell(d.get('comment', ''))} |")
    orphan = {k: v for k, v in decisions.items() if k not in {b['rid'] for b in built} and (v['decision'] or v['comment'])}
    if orphan:
        L.append("\n### Decisions for risks no longer rated (kept, not applied)\n")
        L.append("| Risk | Title | L x I = Score | RAG band | Decision | Comment |")
        L.append("|---|---|---|---|---|---|")
        for k, v in sorted(orphan.items()):
            L.append(f"| {k} | (not in register) | - | - | {cell(v['decision'])} | {cell(v['comment'])} |")
    L.append("\n## Auditor notes\n")
    L.append(notes_block if notes_block else "Reviewer: NAME. Date: YYYY-MM-DD.")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ratings", default="outputs/risk-ratings.json")
    ap.add_argument("--rules", default="outputs/rules.json")
    ap.add_argument("--analytics", default="outputs/analytics.json")
    ap.add_argument("--history", default="outputs/history.json")
    ap.add_argument("--out-dir", default="outputs")
    args = ap.parse_args()
    rep, summary = build(args)
    for line in rep.errors + rep.warns:
        print(line)
    if rep.errors:
        print(f"\n{len(rep.errors)} error(s), {len(rep.warns)} warning(s). FAIL: nothing written.")
        return 1
    print(f"\n{summary['built']} risk(s) rated, {summary['dropped']} dropped, revision {summary['revision']}; "
          f"{len(rep.warns)} warning(s). PASS: wrote risk-register.md and auditor-comments.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
