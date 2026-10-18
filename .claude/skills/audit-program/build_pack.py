#!/usr/bin/env python3
"""Build the audit planning pack from the planner's judgments in outputs/audit-plan.json.

Usage:
    build_pack.py --gate     check the auditor gate only; writes nothing
    build_pack.py            gate + full build

The planner judges; this script computes and checks:
  - gate: every register risk has an auditor decision, the register is a revision
    built from the current risk-ratings.json, and the decisions have not changed
    since that build. Approved scope = Approve or Amend; Reject is out of scope.
  - every approved risk has a plan entry, and nothing else does
  - every control cites a rule; every test cites a rule or a metric; every
    control has at least one test; every citation and {{$.path}} resolves
  - every rule in rules.json is cited by an in-scope risk, a control or a test,
    or listed in not_tested with a reason
  - samples are drawn deterministically from outputs/analytics-full/, sized by
    the risk's score; every sampled transaction must exist in spend_clean.csv
    (with the same amount) and is written to outputs/samples/<test_id>.csv
  - renders planning-memo.md, risk-control-matrix.md and audit-program.md
    (ending with the PBC list), and pack-figures.json listing every figure
    this script computed, copied or filled in

Exit 1 on any ERROR; nothing is written in that case.
"""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("build_register", HERE.parent / "risk-assessment" / "build_register.py")
br = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(br)          # shared citation / placeholder / comment parsing

# Sample size per test, by the risk's score (council matrix, 1-25). First row whose minimum is met.
SAMPLE_SIZE_BY_SCORE = [(15, 25), (8, 15), (4, 10), (1, 5)]
METHODS = {"top", "systematic", "seeded_random"}
OPS = {"==", "!=", "in", "not_in", ">", ">=", "<", "<=", "contains"}
ACCUSATORY = ["fraud", "fraudulent", "breach", "breached", "non-compliant", "noncompliant", "non-compliance",
              "wrongdoing", "evade", "evaded", "evasion", "deliberate", "deliberately", "corrupt", "corruption",
              "theft", "illegal", "misconduct", "abuse", "guilty"]
# A file with a row_id column has one payment per row, so its unit is the payment,
# even if it also names the supplier. Group and supplier files carry row_ids instead.
UNIT_COLS = ["row_id", "group_id", "supplier_key"]
UNIT_LABEL = {"group_id": "flagged groups", "supplier_key": "suppliers", "row_id": "payments"}
TEST_ID_RE = re.compile(r"T-\d{2,}")


class Report:
    def __init__(self):
        self.errors, self.warns = [], []
        self.gate_closed = False

    def error(self, where, msg):
        self.errors.append(f"ERROR [{where}] {msg}")

    def warn(self, where, msg):
        self.warns.append(f"WARN  [{where}] {msg}")


def load_json(path, rep, where):
    p = Path(path)
    if not p.is_file():
        rep.error(where, f"{p} not found")
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        rep.error(where, f"{p} is not valid JSON: {e}")
        return None


def now():
    return dt.datetime.now().replace(microsecond=0).isoformat()


def sample_size(score):
    for lo, n in SAMPLE_SIZE_BY_SCORE:
        if score >= lo:
            return n
    return SAMPLE_SIZE_BY_SCORE[-1][1]


# ---------------------------------------------------------------- register tables

def md_rows(text, start_heading, first_col_re=r"R-\d+"):
    """Rows of the first table after a heading, as lists of cells."""
    i = text.find(start_heading)
    if i < 0:
        return []
    rows = []
    for line in text[i:].splitlines()[1:]:
        if line.startswith("## "):
            break
        m = re.match(rf"^\|\s*({first_col_re})\b", line)
        if m:
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


# ---------------------------------------------------------------- gate

def gate(args, rep):
    """Return the approved scope, or None if the gate is closed."""
    ratings = load_json(args.ratings, rep, "ratings")
    state = load_json(args.state, rep, "register state")
    if not Path(args.comments).is_file():
        rep.error("gate", f"{args.comments} not found: the auditor has not been given the decision template")
    if not Path(args.register).is_file():
        rep.error("gate", f"{args.register} not found: build the risk register first")
    if rep.errors:
        return None
    register = Path(args.register).read_text(encoding="utf-8")
    decisions, _notes = br.parse_comments(args.comments)
    signoff = br.parse_signoff(args.comments)

    rev = (ratings.get("revision") or {}).get("number") if isinstance(ratings.get("revision"), dict) else None
    if not rev:
        rep.error("gate", "the register is not yet a revision: the auditor's decisions have not been applied "
                          "(run the risk-assessor after the auditor completes auditor-comments.md)")
    elif state.get("revision") != rev:
        rep.error("gate", f"risk-ratings.json is revision {rev} but the register was last built as revision "
                          f"{state.get('revision')}: rebuild the register")
    if state.get("inputs", {}).get("ratings", {}).get("sha256") != br.sha256(args.ratings):
        rep.error("gate", "risk-ratings.json has changed since the register was built: rebuild the register")
    if not signoff["reviewer"] or not signoff["date"]:
        rep.error("gate", "auditor-comments.md has no sign-off line (Reviewer: NAME. Date: YYYY-MM-DD.)")

    risks = {r["risk_id"]: r for r in ratings.get("risks", [])}
    dropped = set(state.get("dropped", []))
    rated = [rid for rid in risks if rid not in dropped]
    for rid in rated:
        if rid not in decisions:
            rep.error(rid, "register risk has no row in auditor-comments.md")
        elif not decisions[rid]["decision"]:
            rep.error(rid, "undecided: the auditor has not recorded Approve, Reject or Amend")
        elif decisions[rid]["decision"].lower() not in br.DECISIONS:
            rep.error(rid, f"decision {decisions[rid]['decision']!r} is not Approve, Reject or Amend")
    for rid in decisions:
        if rid not in risks:
            rep.error(rid, "auditor-comments.md has a row for a risk that is not in the register")
    # decisions must be the ones the register was last built with
    built = {row[0]: row[1] for row in md_rows(register, "## Auditor decisions")}
    for rid in rated:
        now_dec = (decisions.get(rid) or {}).get("decision", "")
        was = built.get(rid, "")
        was = "" if was == "_pending_" else was
        if rid in decisions and now_dec and now_dec != was:
            rep.error(rid, f"decision is {now_dec!r} in auditor-comments.md but {was or 'pending'!r} in the register: "
                           "decisions changed after the last build; rerun the risk-assessor")
    for rid in rated:
        dec = (decisions.get(rid) or {}).get("decision", "").lower()
        st = risks[rid].get("status", "proposed")
        if dec == "reject" and st != "rejected":
            rep.error(rid, "rejected by the auditor but not marked rejected in risk-ratings.json")
        if dec in ("approve", "amend") and st == "rejected":
            rep.error(rid, f"marked rejected in risk-ratings.json but the auditor's decision is {dec}")
    if rep.errors:
        rep.gate_closed = True
        return None

    summary = {row[0].split()[0]: row for row in md_rows(register, "## Summary")}
    in_scope, out_scope = [], []
    for rid in rated:
        dec = decisions[rid]["decision"].lower()
        if dec == "reject":
            out_scope.append({"risk_id": rid, "title": risks[rid].get("title"), "reason": decisions[rid]["comment"]})
            continue
        row = summary.get(rid)
        if not row:
            rep.error(rid, "approved risk is missing from the register's summary table")
            continue
        in_scope.append({"risk_id": rid, "title": risks[rid].get("title"), "decision": decisions[rid]["decision"],
                         "L": int(row[2]), "I": int(row[3]), "score": int(row[4]), "band": row[6],
                         "risk": risks[rid]})
    if rep.errors:
        return None
    return {"rev": rev, "signoff": signoff, "in_scope": in_scope, "out_scope": out_scope,
            "ratings": ratings, "decisions": decisions}


# ---------------------------------------------------------------- text checks

class TextChecker:
    def __init__(self, src, analytics, supplier_keys, rep):
        self.src, self.analytics, self.rep = src, analytics, rep
        self.keys = [k for k in supplier_keys if len(k.split()) >= 2]       # matched in any case
        self.one_word = {k for k in supplier_keys if len(k.split()) == 1}    # matched only as a proper noun
        self.filled = []          # (path, value, where)

    def render(self, text, where):
        """Fill placeholders, resolve citations, and check language. Returns (rendered, cites)."""
        text = text or ""
        problems, seen = [], []
        out = br.render_text(text, self.src, problems, seen)
        for m in br.PLACE_RE.finditer(text):
            ok, val = br.resolve_path(self.analytics, m.group(1))
            if ok and not isinstance(val, (dict, list)):
                self.filled.append({"path": m.group(1).strip(), "value": val, "where": where})
        for p in sorted(set(problems)):
            self.rep.error(where, p)
        for kind, ref, ok, label in seen:
            if not ok:
                self.rep.error(where, f"unresolved citation [{kind}:{ref}]: {label}")
        figs = br.typed_figures(text)
        if figs:
            self.rep.warn(where, f"figure(s) typed in prose {figs[:3]}; use {{{{$.path}}}} placeholders")
        low = " " + re.sub(r"[^a-z\-]+", " ", text.lower()) + " "
        bad = [w for w in ACCUSATORY if f" {w} " in low]
        if bad:
            self.rep.error(where, f"accusatory wording {bad}: use indicator language "
                                  "('indicator to investigate', 'may indicate')")
        norm = " " + br_norm(text) + " "
        hits = [k for k in self.keys if f" {k} " in norm]
        plain = br.PLACE_RE.sub(" ", br.CITE_RE.sub(" ", text))
        for sent in re.split(r"(?<=[.!?:;])\s+|\n+", plain):
            toks = re.findall(r"[A-Za-z0-9]+", sent)
            hits += [t for t in toks[1:] if any(ch.isupper() for ch in t) and t.upper() in self.one_word]
        if hits:
            self.rep.error(where, f"names a supplier ({len(hits)} match(es)); suppliers appear only in the sample files")
        return out, seen


def br_norm(s):
    s = re.sub(r"[^A-Za-z0-9]+", " ", str(s).upper())
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"(\s(LTD|LIMITED|PLC|LLP))+$", "", s)


# ---------------------------------------------------------------- samples

def apply_filter(df, flt, where, rep):
    mask = pd.Series(True, index=df.index)
    for i, f in enumerate(flt or []):
        col, op, val = f.get("col"), f.get("op"), f.get("value")
        if col not in df.columns:
            rep.error(where, f"filter[{i}] column {col!r} not in {list(df.columns)}")
            continue
        if op not in OPS:
            rep.error(where, f"filter[{i}] op {op!r} not in {sorted(OPS)}")
            continue
        s = df[col]
        if op in (">", ">=", "<", "<="):
            num = pd.to_numeric(s, errors="coerce")
            v = float(val)
            mask &= {">": num > v, ">=": num >= v, "<": num < v, "<=": num <= v}[op].fillna(False)
        elif op in ("in", "not_in"):
            vals = {str(x) for x in (val if isinstance(val, list) else [val])}
            hit = s.astype(str).isin(vals)
            mask &= hit if op == "in" else ~hit
        elif op == "contains":
            mask &= s.astype(str).str.contains(str(val), case=False, regex=False)
        else:
            num = pd.to_numeric(s, errors="coerce")
            if isinstance(val, (int, float)) and not isinstance(val, bool) and num.notna().all():
                hit = num == float(val)
            else:
                hit = s.astype(str) == str(val)
            mask &= hit if op == "==" else ~hit
    return df[mask]


def draw(df, sample, size, test_id, unit_col, where, rep):
    sort = sample.get("sort") or []
    by, asc = [], []
    for i, s in enumerate(sort):
        if s.get("col") not in df.columns:
            rep.error(where, f"sort[{i}] column {s.get('col')!r} not in the source file")
            return df.iloc[0:0]
        by.append(s["col"])
        asc.append(not s.get("desc", False))
    work = df.copy()
    keys = []
    for c in by:
        num = pd.to_numeric(work[c], errors="coerce")
        k = f"__k{len(keys)}"
        work[k] = num if num.notna().all() else work[c].astype(str)
        keys.append(k)
    work = work.sort_values(keys + [unit_col], ascending=asc + [True], kind="mergesort")
    n = min(size, len(work))
    method = sample.get("method", "top")
    if method == "top":
        idx = list(range(n))
    elif method == "systematic":
        step = len(work) / n if n else 1
        idx = sorted({int(i * step) for i in range(n)})
    else:
        seed = int(hashlib.sha256(f"{test_id}|{sample.get('source')}".encode()).hexdigest()[:16], 16)
        idx = sorted(random.Random(seed).sample(range(len(work)), n))
    return work.iloc[idx].drop(columns=keys)


def expand(drawn, unit_col):
    """One row per transaction: (unit_id, row_id, expected_amount or None)."""
    out = []
    for _, r in drawn.iterrows():
        unit = r[unit_col]
        if "row_ids" in drawn.columns:
            ids = [x for x in str(r["row_ids"]).split(";") if x]
            amts = str(r["amounts"]).split(";") if "amounts" in drawn.columns else []
            amts = [float(a) for a in amts] if len(amts) == len(ids) else [None] * len(ids)
            out += [(unit, i, a) for i, a in zip(ids, amts)]
        else:
            amt = float(r["amount"]) if "amount" in drawn.columns else None
            out.append((unit, r["row_id"], amt))
    return out


# ---------------------------------------------------------------- build

def build(args, rep):
    scope = gate(args, rep)
    if scope is None:
        return None
    if args.gate:
        return scope
    rules = load_json(args.rules, rep, "rules")
    analytics = load_json(args.analytics, rep, "analytics")
    history = load_json(args.history, rep, "history")
    plan = load_json(args.plan, rep, "plan")
    full = Path(args.full_dir)
    spend_path = full / "spend_clean.csv"
    if not spend_path.is_file():
        rep.error("samples", f"{spend_path} not found")
    if rep.errors:
        return None
    spend = pd.read_csv(spend_path, dtype=str).set_index("row_id")
    spend_amount = pd.to_numeric(spend["amount"], errors="coerce")
    supplier_keys = sorted({str(k) for k in spend["supplier_key"].dropna().unique() if str(k).strip()})
    src = br.Sources(rules, analytics, history)
    tc = TextChecker(src, analytics, supplier_keys, rep)

    in_scope = {s["risk_id"]: s for s in scope["in_scope"]}
    out_ids = {s["risk_id"] for s in scope["out_scope"]}
    plan_risks = plan.get("risks") or []
    plan_ids = [p.get("risk_id") for p in plan_risks]
    for rid in in_scope:
        if rid not in plan_ids:
            rep.error(rid, "approved risk is missing from audit-plan.json: every approved risk needs controls and tests")
    for rid in plan_ids:
        if rid in out_ids:
            rep.error(rid, "audit-plan.json covers a risk the auditor rejected; it is out of scope")
        elif rid not in in_scope:
            rep.error(rid, "audit-plan.json covers a risk that is not in the approved register")
    if len(set(plan_ids)) != len(plan_ids):
        rep.error("plan", "a risk appears more than once in audit-plan.json")

    memo_r = {}
    for k in ("objective", "scope_note", "approach", "limitations"):
        if not (plan.get("memo") or {}).get(k):
            rep.error("memo", f"memo.{k} is missing")
        memo_r[k], _ = tc.render((plan.get("memo") or {}).get(k, ""), f"memo.{k}")

    cited_rules = set()
    for s in in_scope.values():
        for kind, ref in br.CITE_RE.findall(json.dumps(s["risk"], ensure_ascii=False)):
            if kind == "rule":
                cited_rules.add(ref.strip())

    control_ids, test_ids, built = [], [], []
    figures = []
    pbc, pbc_index = [], {}
    samples_out = {}
    for p in plan_risks:
        rid = p.get("risk_id")
        if rid not in in_scope:
            continue
        sc = in_scope[rid]
        entry = {"risk_id": rid, "scope": sc, "controls": [], "tests": []}
        ctrl_here = set()
        for c in p.get("controls") or []:
            cid = c.get("control_id")
            where = f"{rid}/{cid}"
            if not re.fullmatch(r"C-\d{2,}", str(cid)):
                rep.error(where, "control_id must be C-01, C-02, ...")
            if cid in control_ids:
                rep.error(where, "duplicate control_id")
            control_ids.append(cid)
            ctrl_here.add(cid)
            text, cites = tc.render(c.get("description", ""), where)
            rule_cites = [ref for kind, ref, ok, _ in cites if ok and kind == "rule"]
            if not rule_cites:
                rep.error(where, "control cites no rule: every expected control must cite at least one [rule:ID]")
            cited_rules.update(rule_cites)
            entry["controls"].append({"id": cid, "text": text, "rules": rule_cites})
        if not entry["controls"]:
            rep.error(rid, "no expected controls")
        tested = set()
        for t in p.get("tests") or []:
            tid = t.get("test_id")
            where = f"{rid}/{tid}"
            if not TEST_ID_RE.fullmatch(str(tid)):
                rep.error(where, "test_id must be T-01, T-02, ...")
            if tid in test_ids:
                rep.error(where, "duplicate test_id")
            test_ids.append(tid)
            for cid in t.get("control_ids") or []:
                if cid not in ctrl_here:
                    rep.error(where, f"tests control {cid!r}, which is not a control of {rid}")
                tested.add(cid)
            if not t.get("control_ids"):
                rep.error(where, "control_ids is empty: every test tests at least one control")
            obj, cites = tc.render(t.get("objective", ""), f"{where}.objective")
            steps = []
            for i, s in enumerate(t.get("steps") or []):
                st, c2 = tc.render(s, f"{where}.steps[{i}]")
                steps.append(st)
                cites = cites + c2
            if not steps:
                rep.error(where, "no test steps")
            good = [(k, ref) for k, ref, ok, _ in cites if ok and k in ("rule", "metric")]
            if not good:
                rep.error(where, "test cites no rule or metric: each test needs at least one [rule:ID] or [metric:$.path]")
            cited_rules.update(ref for k, ref in good if k == "rule")
            # PBC
            items = []
            for j, it in enumerate(t.get("pbc") or []):
                item, held = (it.get("item") or "").strip(), (it.get("held_by") or "").strip()
                if not item or not held:
                    rep.error(where, f"pbc[{j}] needs 'item' and 'held_by'")
                    continue
                tc.render(item, f"{where}.pbc[{j}]")
                key = (item.lower(), held.lower())
                if key not in pbc_index:
                    pbc_index[key] = f"P-{len(pbc) + 1:02d}"
                    pbc.append({"id": pbc_index[key], "item": item, "held_by": held, "tests": []})
                pid = pbc_index[key]
                next(x for x in pbc if x["id"] == pid)["tests"].append(tid)
                items.append(pid)
            if not items:
                rep.error(where, "no PBC items: list what the auditee must provide for this test")
            # sample
            smp = t.get("sample")
            sinfo = None
            if smp is None:
                if not t.get("no_sample_reason"):
                    rep.error(where, "sample is null: give no_sample_reason (e.g. a walkthrough of the control)")
                sinfo = {"none": t.get("no_sample_reason")}
            else:
                sinfo = draw_sample(smp, tid, sc, full, spend, spend_amount, where, rep, figures)
                if sinfo and "rows" in sinfo:
                    samples_out[tid] = sinfo.pop("rows")
            entry["tests"].append({"id": tid, "controls": t.get("control_ids") or [], "objective": obj,
                                   "steps": steps, "pbc": items, "sample": sinfo,
                                   "cites": sorted({f"{k}:{r}" for k, r in good})})
        for cid in ctrl_here - tested:
            rep.error(f"{rid}/{cid}", "control has no test")
        built.append(entry)

    # rule coverage
    all_rules = [r["rule_id"] for r in (rules or {}).get("rules", [])]
    nt = {}
    for i, x in enumerate(plan.get("not_tested") or []):
        rid_, why = x.get("rule_id"), (x.get("reason") or "").strip()
        if rid_ not in all_rules:
            rep.error(f"not_tested[{i}]", f"{rid_!r} is not a rule in rules.json")
        elif not why:
            rep.error(f"not_tested[{i}]", f"{rid_} needs a reason")
        else:
            nt[rid_] = why
            tc.render(why, f"not_tested.{rid_}")
    for r in all_rules:
        if r not in cited_rules and r not in nt:
            rep.error(r, "rule is not cited by an approved risk, a control or a test, and not listed in not_tested with a reason")
        if r in cited_rules and r in nt:
            rep.warn(r, "rule is both cited and listed in not_tested; remove it from not_tested")

    if rep.errors:
        return None
    # ---- write
    out = Path(args.out_dir)
    sdir = out / "samples"
    sdir.mkdir(parents=True, exist_ok=True)
    for old in sdir.glob("T-*.csv"):
        if old.stem not in samples_out:
            old.unlink()
    for tid, rows in samples_out.items():
        rows.to_csv(sdir / f"{tid}.csv", index=False)
    inputs = {k: {"file": str(p), "sha256": br.sha256(p)} for k, p in (
        ("plan", args.plan), ("ratings", args.ratings), ("comments", args.comments), ("rules", args.rules),
        ("analytics", args.analytics), ("history", args.history), ("spend_clean", spend_path))}
    ctx = {"scope": scope, "built": built, "memo": memo_r, "pbc": pbc, "nt": nt, "cited": cited_rules,
           "all_rules": all_rules, "inputs": inputs, "args": args}
    (out / "planning-memo.md").write_text(render_memo(ctx), encoding="utf-8")
    (out / "risk-control-matrix.md").write_text(render_rcm(ctx), encoding="utf-8")
    (out / "audit-program.md").write_text(render_program(ctx), encoding="utf-8")
    figures += [{"figure": "scope.risks_in_scope", "value": len(built), "how": "count of Approve/Amend decisions"},
                {"figure": "scope.risks_rejected", "value": len(scope["out_scope"]), "how": "count of Reject decisions"},
                {"figure": "pack.controls", "value": len(control_ids), "how": "count"},
                {"figure": "pack.tests", "value": len(test_ids), "how": "count"},
                {"figure": "pack.pbc_items", "value": len(pbc), "how": "count of distinct PBC items"},
                {"figure": "rules.total", "value": len(all_rules), "how": "count in rules.json"},
                {"figure": "rules.cited", "value": len(set(all_rules) & cited_rules), "how": "rules cited by an in-scope risk, control or test"},
                {"figure": "rules.not_tested", "value": len(nt), "how": "rules listed in not_tested"}]
    copied = [{"figure": f"{s['risk_id']}.{k}", "value": s[k], "from": "risk-register.md summary table"}
              for s in scope["in_scope"] for k in ("L", "I", "score", "band")]
    (out / "pack-figures.json").write_text(json.dumps(
        {"generated_at": now(), "inputs": inputs, "sample_size_by_score": SAMPLE_SIZE_BY_SCORE,
         "computed": figures, "copied_from_register": copied, "filled_from_analytics": tc.filled},
        indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return {"in_scope": len(built), "tests": len(test_ids), "samples": len(samples_out),
            "transactions": sum(len(v) for v in samples_out.values())}


def draw_sample(smp, tid, sc, full, spend, spend_amount, where, rep, figures):
    name = smp.get("source")
    path = full / str(name)
    if not name or "/" in str(name) or path.suffix != ".csv" or not path.is_file():
        rep.error(where, f"sample.source {name!r} is not a CSV file in {full}")
        return None
    df = pd.read_csv(path, dtype=str)
    if "row_id" not in df.columns and "row_ids" not in df.columns:
        rep.error(where, f"{name} has no row_id/row_ids column, so its rows cannot be traced to transactions")
        return None
    unit_col = next((c for c in UNIT_COLS if c in df.columns), None)
    method = smp.get("method", "top")
    if method not in METHODS:
        rep.error(where, f"sample.method {method!r} not in {sorted(METHODS)}")
        return None
    pop = apply_filter(df, smp.get("filter"), where, rep)
    if rep.errors:
        return None
    if pop.empty:
        rep.error(where, f"the filter leaves no rows in {name}; change the filter or give a no_sample_reason")
        return None
    size = sample_size(sc["score"])
    drawn = draw(pop, smp, size, tid, unit_col, where, rep)
    tx = expand(drawn, unit_col)
    missing, mismatch, rows = [], [], []
    for unit, rid_, amt in tx:
        if rid_ not in spend.index:
            missing.append(rid_)
            continue
        s = spend.loc[rid_]
        a = float(spend_amount.loc[rid_])
        if amt is not None and abs(a - amt) > 0.005:
            mismatch.append(rid_)
        rows.append({"test_id": tid, "sample_unit": unit, "row_id": rid_, "pay_date": s["pay_date"],
                     "supplier": s["supplier_raw"], "service": s["service"], "category": s["category"],
                     "narrative": s["narrative"], "amount": a, "tag": s["tag"], "period": s["period"]})
    if missing:
        rep.error(where, f"{len(missing)} sampled transaction(s) not found in spend_clean.csv, e.g. {missing[0]}")
    if mismatch:
        rep.error(where, f"{len(mismatch)} sampled transaction(s) have a different amount in spend_clean.csv, e.g. {mismatch[0]}")
    if missing or mismatch:
        return None
    gbp_col = "total" if "total" in pop.columns else ("amount" if "amount" in pop.columns else None)
    pop_gbp = float(pd.to_numeric(pop[gbp_col], errors="coerce").sum()) if gbp_col else None
    smp_gbp = round(sum(r["amount"] for r in rows), 2)
    info = {"source": name, "filter": smp.get("filter") or [], "sort": smp.get("sort") or [], "method": method,
            "unit": unit_col, "population": len(pop), "population_gbp": round(pop_gbp, 2) if pop_gbp is not None else None,
            "size_rule": size, "drawn": len(drawn), "transactions": len(rows), "sample_gbp": smp_gbp,
            "file": f"samples/{tid}.csv", "rows": pd.DataFrame(rows)}
    for k, how in (("population", f"rows of {name} after the filter"),
                   ("population_gbp", f"sum of '{gbp_col}' over the filtered rows"),
                   ("size_rule", f"sample size for score {sc['score']} from the size table"),
                   ("drawn", f"units drawn ({method}); fewer than the size rule only when the population is smaller"),
                   ("transactions", "spend_clean.csv rows behind the drawn units"),
                   ("sample_gbp", "sum of spend_clean.csv amounts of those rows")):
        figures.append({"figure": f"{tid}.{k}", "value": info[k], "how": how})
    return info


# ---------------------------------------------------------------- rendering

def money(v):
    return "-" if v is None else f"£{v:,.2f}"


def header(ctx, title):
    sc = ctx["scope"]
    so = sc["signoff"]
    return [f"# {title}: procurement audit, West Berkshire Council\n",
            f"**Built from risk register revision {sc['rev']}** · auditor decisions by {so['reviewer']}, dated "
            f"{so['date']} · built {now()} by `.claude/skills/audit-program/build_pack.py`\n",
            "> Risk indicators to investigate, not findings of wrongdoing. Figures are filled from "
            "`outputs/analytics.json` or computed by the builder (see `outputs/pack-figures.json`).\n"]


def sample_line(s):
    if s is None:
        return "-"
    if "none" in s:
        return f"No sample: {s['none']}"
    unit = UNIT_LABEL.get(s["unit"], s["unit"])
    return (f"{s['drawn']} of {s['population']} {unit} ({s['transactions']} transactions, "
            f"{money(s['sample_gbp'])}) → `outputs/{s['file']}`")


def render_memo(ctx):
    sc, m = ctx["scope"], ctx["memo"]
    L = header(ctx, "Planning memo")
    L += ["## Objective\n", m["objective"], "\n## Scope\n", m["scope_note"], "",
          "Risks in scope (approved at the auditor gate):\n",
          "| Risk | Title | L x I = Score | RAG band | Decision | Controls | Tests |", "|---|---|---|---|---|---|---|"]
    for b in ctx["built"]:
        s = b["scope"]
        L.append(f"| {s['risk_id']} | {br.cell(s['title'])} | {s['L']} x {s['I']} = {s['score']} | {s['band']} | "
                 f"{s['decision']} | {len(b['controls'])} | {len(b['tests'])} |")
    if sc["out_scope"]:
        L.append("\nOut of scope (rejected by the auditor):\n")
        for o in sc["out_scope"]:
            L.append(f"- {o['risk_id']} {o['title']}: \"{o['reason']}\"")
    L += ["\n## Approach\n", m["approach"], "",
          "Samples are drawn by `build_pack.py` from the flagged lists in `outputs/analytics-full/`, sized by the "
          "risk's score (" + "; ".join(f"score {lo}+ → {n}" for lo, n in SAMPLE_SIZE_BY_SCORE) +
          " units per test), and every sampled transaction is checked against `spend_clean.csv`.\n",
          "| Test | Risk | Sample |", "|---|---|---|"]
    for b in ctx["built"]:
        for t in b["tests"]:
            L.append(f"| {t['id']} | {b['risk_id']} | {sample_line(t['sample'])} |")
    n_rules = len(ctx["all_rules"])
    L += [f"\nRule coverage: {len(set(ctx['all_rules']) & ctx['cited'])} of {n_rules} rules in `outputs/rules.json` "
          f"are cited by an approved risk, a control or a test; {len(ctx['nt'])} are listed as not tested, with "
          "reasons, in `risk-control-matrix.md`.\n",
          "## Limitations\n", m["limitations"], ""]
    return "\n".join(L) + "\n"


def render_rcm(ctx):
    L = header(ctx, "Risk and control matrix")
    L += ["| Risk | Score | Expected control | Rules | Tested by |", "|---|---|---|---|---|"]
    for b in ctx["built"]:
        s = b["scope"]
        for c in b["controls"]:
            tests = [t["id"] for t in b["tests"] if c["id"] in t["controls"]]
            L.append(f"| {s['risk_id']} {br.cell(s['title'])} | {s['score']} ({s['band']}) | {c['id']}: "
                     f"{br.cell(c['text'])} | {', '.join(c['rules'])} | {', '.join(tests)} |")
    L += ["\n## Rules not tested in this audit\n",
          "Every other rule in `outputs/rules.json` is cited above or by an approved risk.\n",
          "| Rule | Clause | Reason |", "|---|---|---|"]
    clauses = {r: c for r, c in ((x["rule_id"], x["clause"]) for x in json.load(open(ctx["args"].rules))["rules"])}
    for r in sorted(ctx["nt"]):
        L.append(f"| {r} | {clauses.get(r, '')} | {br.cell(ctx['nt'][r])} |")
    return "\n".join(L) + "\n"


def render_program(ctx):
    L = header(ctx, "Audit program")
    for b in ctx["built"]:
        s = b["scope"]
        L.append(f"\n## {s['risk_id']}. {s['title']} (score {s['score']}, {s['band']})\n")
        for t in b["tests"]:
            L.append(f"### {t['id']} · tests {', '.join(t['controls'])}\n")
            L.append(f"**Objective.** {t['objective']}\n")
            L.append("**Steps.**")
            for i, st in enumerate(t["steps"], 1):
                L.append(f"{i}. {st}")
            smp = t["sample"]
            L.append("\n**Sample.** " + sample_line(smp))
            if smp and "none" not in smp:
                f = "; ".join(f"{x['col']} {x['op']} {x['value']}" for x in smp["filter"]) or "none"
                o = ", ".join(f"{x['col']} {'desc' if x.get('desc') else 'asc'}" for x in smp["sort"]) or "unit id"
                L.append(f"Recipe: `{smp['source']}`, filter: {f}; sort: {o}; method: {smp['method']}; "
                         f"population {smp['population']} ({money(smp['population_gbp'])}); size rule {smp['size_rule']}.")
            L.append(f"\n**PBC.** {', '.join(t['pbc'])}\n")
    L += ["\n## PBC list (prepared by client)\n", "| PBC | Item | Held by | For tests |", "|---|---|---|---|"]
    for p in ctx["pbc"]:
        L.append(f"| {p['id']} | {br.cell(p['item'])} | {br.cell(p['held_by'])} | {', '.join(sorted(set(p['tests'])))} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gate", action="store_true", help="run only the auditor-gate check; write nothing")
    ap.add_argument("--plan", default="outputs/audit-plan.json")
    ap.add_argument("--ratings", default="outputs/risk-ratings.json")
    ap.add_argument("--comments", default="outputs/auditor-comments.md")
    ap.add_argument("--register", default="outputs/risk-register.md")
    ap.add_argument("--state", default="outputs/risk-register-state.json")
    ap.add_argument("--rules", default="outputs/rules.json")
    ap.add_argument("--analytics", default="outputs/analytics.json")
    ap.add_argument("--history", default="outputs/history.json")
    ap.add_argument("--full-dir", default="outputs/analytics-full")
    ap.add_argument("--out-dir", default="outputs")
    args = ap.parse_args()
    rep = Report()
    res = build(args, rep)
    for line in rep.errors + rep.warns:
        print(line)
    if rep.errors:
        what = "GATE CLOSED" if rep.gate_closed else "FAIL"
        print(f"\n{len(rep.errors)} error(s), {len(rep.warns)} warning(s). {what}: nothing written.")
        return 1
    if args.gate:
        print(f"\nGATE OPEN: register revision {res['rev']}, decisions by {res['signoff']['reviewer']} dated "
              f"{res['signoff']['date']}; {len(res['in_scope'])} risk(s) in scope "
              f"({', '.join(s['risk_id'] for s in res['in_scope'])}), {len(res['out_scope'])} rejected.")
        return 0
    print(f"\n{res['in_scope']} risk(s) in scope, {res['tests']} test(s), {res['samples']} sample file(s), "
          f"{res['transactions']} sampled transaction(s); {len(rep.warns)} warning(s). PASS: wrote planning-memo.md, "
          "risk-control-matrix.md, audit-program.md, samples/ and pack-figures.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
