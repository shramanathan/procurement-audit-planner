"""Resolve threshold tiers, the quote threshold and the publication threshold
from outputs/rules.json -> outputs/analytics-full/thresholds.json.

No amount is typed here: every figure comes from rules.json.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FULL, RULES, read_json, stop, write_json  # noqa: E402

TIER_TYPES = {"threshold_procedure", "approval"}
QUOTE_CLAUSES = {"App B row B1", "App B row B2"}
SKIP_REASON = "parameter {} is null in rules.json; value must come from the Procurement intranet page"


def resolve(bound, params):
    """-> (amount or None, parameter name or None). bound is a dict or None."""
    if bound is None:
        return None, None
    if bound.get("amount") is not None:
        return bound["amount"], None
    p = bound.get("parameter")
    if p is None:
        return None, None
    if p not in params:
        stop(f"rules.json bound refers to unknown parameter {p}")
    return params[p].get("value"), p


def clause_threshold(rules, params, rtype, label):
    picks = [r for r in rules if r.get("type") == rtype and r.get("clause") in QUOTE_CLAUSES]
    if not picks:
        return {"status": "unresolved", "reason": f"no {rtype} rule on {sorted(QUOTE_CLAUSES)}",
                "rule_ids": []}
    vals, unresolved = set(), []
    for r in picks:
        amt, p = resolve(r.get("threshold_low"), params)
        if amt is None:
            unresolved.append({"rule_id": r["rule_id"], "parameter": p,
                               "reason": SKIP_REASON.format(p) if p else "no threshold_low"})
        else:
            vals.add(amt)
    if len(vals) > 1:
        stop(f"{label}: rules {[r['rule_id'] for r in picks]} disagree on threshold_low: {sorted(vals)}")
    if not vals:
        return {"status": "unresolved", "rule_ids": [r["rule_id"] for r in picks],
                "reason": "; ".join(u["reason"] for u in unresolved)}
    return {"status": "resolved", "amount": vals.pop(),
            "as_printed": sorted({r["threshold_low"].get("as_printed", "") for r in picks}),
            "rule_ids": [r["rule_id"] for r in picks], "clauses": sorted(QUOTE_CLAUSES),
            "unresolved_rules": unresolved}


def main():
    if not RULES.exists():
        stop(f"{RULES} missing; run /extract-rules")
    rj = read_json(RULES)
    rules, params = rj.get("rules"), rj.get("parameters", {})
    if not isinstance(rules, list) or not rules:
        stop("rules.json has no rules array")

    tiers, skipped = {}, []
    for r in rules:
        if r.get("type") not in TIER_TYPES:
            continue
        b = r.get("threshold_low")
        if b is None:
            continue
        amt, p = resolve(b, params)
        if amt is None:
            skipped.append({"rule_id": r["rule_id"], "parameter": p, "reason": SKIP_REASON.format(p)})
            continue
        t = tiers.setdefault(amt, {"amount": amt, "as_printed": [], "rule_ids": []})
        if b.get("as_printed") and b["as_printed"] not in t["as_printed"]:
            t["as_printed"].append(b["as_printed"])
        t["rule_ids"].append(r["rule_id"])
    tier_list = [tiers[k] for k in sorted(tiers)]

    quote = clause_threshold(rules, params, "threshold_procedure", "quote_threshold")
    publication = clause_threshold(rules, params, "advertising", "publication_threshold")

    vat_notes = [n["note"] for n in rj.get("notes", [])
                 if "6.15" in n.get("clauses", []) and "VAT" in n.get("note", "")]
    caveats = [
        "Thresholds in rules.json are stated for total contract value. A single payment, or a "
        "supplier's spend in the window (or its annualised estimate), is not a contract value: "
        "results are risk indicators to investigate, not findings.",
        "Spend data is net of VAT. rules.json records that VAT treatment differs between clause "
        "6.15 and Appendix B: " + (" ".join(vat_notes) if vat_notes else "(note not found)"),
    ]
    out = {"source": "outputs/rules.json", "tiers": tier_list, "skipped_tiers": skipped,
           "quote_threshold": quote, "publication_threshold": publication, "caveats": caveats}
    write_json(FULL / "thresholds.json", out)

    print(f"resolved tiers ({len(tier_list)}):")
    for t in tier_list:
        print(f"  {t['amount']}  rules {','.join(t['rule_ids'])}")
    print(f"skipped tiers ({len(skipped)}): " +
          ", ".join(f"{s['rule_id']}<-{s['parameter']}" for s in skipped))
    for name, v in (("quote_threshold", quote), ("publication_threshold", publication)):
        print(f"{name}: {v.get('amount', 'UNRESOLVED')} ({v['status']}; rules {','.join(v['rule_ids'])})")


if __name__ == "__main__":
    main()
