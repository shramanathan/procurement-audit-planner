"""Run the risk-indicator tests -> outputs/analytics.json and
outputs/analytics-full/<test>.csv.

Every result is a risk indicator to investigate, not a finding.
Thresholds come only from analytics-full/thresholds.json (built from rules.json).
"""
from __future__ import annotations

import datetime as dt
import difflib
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (ANALYTICS, ANNUAL_LABEL, FULL, LANGUAGE, RULES, RULES_PDF,  # noqa: E402
                    VERIFIER, money, read_json, rel, sha256, stop, write_json)

ROOT = Path(__file__).resolve().parent.parent
TAGS = ["grant", "care_education_placement", "agency_staff", "premises", "general_procurement"]
CLUSTER_LOW, CLUSTER_HIGH = 0.9, 1.1          # band factors set by the spec
SPLIT_DAYS, DUP_DAYS = 30, 7
AWARD_RATIO_FLAG = 1.25
RE_TRADING = re.compile(r"\bT A\b|\bT AS\b|\bTRADING AS\b")
CANDIDATE_MIN_LEN, CANDIDATE_RATIO = 6, 0.85

CAVEAT_ANNUAL = (f"'{ANNUAL_LABEL}' = window total x 12 / number of monthly workbooks; spend can be "
                 "seasonal or one-off, so this is an estimate only.")


# ------------------------------------------------------------------ helpers
def by_tag(df: pd.DataFrame, amount_col: str, tag_col: str = "tag") -> dict:
    out = {}
    for t in TAGS:
        sub = df[df[tag_col] == t]
        if len(sub):
            out[t] = {"count": int(len(sub)), "gbp": money(sub[amount_col].sum())}
    return out


def records(df: pd.DataFrame, n=20):
    recs = df.head(n).to_dict(orient="records")
    for r in recs:
        for k, v in list(r.items()):
            if isinstance(v, float):
                r[k] = money(v) if k not in ("ratio", "score", "contract_years", "band_to_comparison_ratio") \
                    else round(v, 4)
    return recs


def skipped(reason, rule_ids=None):
    return {"status": "skipped", "reason": reason, "rule_ids": rule_ids or []}


def majority_tag(amounts: pd.Series, tags: pd.Series) -> str:
    s = amounts.groupby(tags.values).sum()
    return str(s.sort_values(ascending=False, kind="stable").index[0])


# ------------------------------------------------------------------ main
def main():
    # rules.json must still verify
    res = subprocess.run([sys.executable, str(VERIFIER), str(RULES), str(RULES_PDF)],
                         capture_output=True, text=True, cwd=ROOT)
    if res.returncode != 0:
        stop("rules.json fails verify_quotes.py; /extract-rules must be re-run")
    verify_line = [l for l in res.stdout.splitlines() if "error(s)" in l]

    cs_sum = read_json(FULL / "cleaning_summary.json")
    th = read_json(FULL / "thresholds.json")
    rj = read_json(RULES)
    rules = rj["rules"]

    clean = pd.read_csv(FULL / "spend_clean.csv", dtype={"row_id": str, "supplier_key": str},
                        keep_default_na=False)
    clean["amount"] = clean["amount"].astype(float)
    clean["is_credit"] = clean["is_credit"].astype(str).str.lower() == "true"
    pay = clean[~clean["is_credit"]].copy()
    pay["pay_date_d"] = pd.to_datetime(pay["pay_date"], format="%Y-%m-%d")
    factor = float(cs_sum["window"]["annualisation_factor"])
    window_start = dt.date.fromisoformat(cs_sum["window"]["start"])

    contracts_present = cs_sum["contracts"]["present"]
    notices = None
    if contracts_present:
        notices = pd.read_csv(FULL / "contract_suppliers.csv", dtype=str, keep_default_na=False)
        notices["live"] = notices["live"].str.lower() == "true"
        notices["awarded_value"] = notices["awarded_value"].astype(float)
        notices["n_suppliers"] = notices["n_suppliers"].astype(int)

    anti = [r["rule_id"] for r in rules if r.get("type") == "anti-avoidance"]
    tiers = th["tiers"]
    vat_caveats = th["caveats"]
    tests = {}

    # supplier aggregates (used by supplier-level tests)
    sup = supplier_table(pay, factor)

    # matching (section 4)
    match = None
    if contracts_present:
        match = build_matching(sup, notices)

    # 1. threshold_clustering
    if tiers:
        tests["threshold_clustering"] = threshold_clustering(pay, tiers, anti, vat_caveats)
    else:
        tests["threshold_clustering"] = skipped("no resolved threshold tier in rules.json")

    # 2. split_purchases
    if tiers:
        tests["split_purchases"] = split_purchases(pay, tiers, anti, vat_caveats)
    else:
        tests["split_purchases"] = skipped("no resolved threshold tier in rules.json")

    # 3. off_contract
    pubt = th["publication_threshold"]
    if not contracts_present:
        tests["off_contract"] = skipped("data/contracts.csv not present", pubt.get("rule_ids"))
    elif pubt["status"] != "resolved":
        tests["off_contract"] = skipped(f"publication_threshold unresolved: {pubt.get('reason')}",
                                        pubt.get("rule_ids"))
    else:
        tests["off_contract"] = off_contract(sup, match, pubt, factor, vat_caveats)

    # 4. duplicates
    doc_ids = [r["rule_id"] for r in rules if r.get("type") == "documentation"
               and r.get("clause") == "10.1" and "written" in r.get("required_action", "").lower()
               and "evidence" in r.get("required_action", "").lower()]
    tests["duplicates"] = duplicates(pay, doc_ids)

    # 5/6 notice tests
    rid_d = [r["rule_id"] for r in rules if r.get("clause") == "App C row D"]
    rid_e = [r["rule_id"] for r in rules if r.get("clause") == "App C row E"]
    if contracts_present:
        tests["expired_notice_spend"] = expired_notice_spend(sup, match, notices, window_start, rid_d)
        tests["spend_vs_award"] = spend_vs_award(sup, match, notices, factor, rid_e, vat_caveats)
    else:
        tests["expired_notice_spend"] = skipped("data/contracts.csv not present", rid_d)
        tests["spend_vs_award"] = skipped("data/contracts.csv not present", rid_e)

    # 7. high_value_suppliers
    qt = th["quote_threshold"]
    if qt["status"] != "resolved":
        tests["high_value_suppliers"] = skipped(f"quote_threshold unresolved: {qt.get('reason')}",
                                                qt.get("rule_ids"))
    else:
        tests["high_value_suppliers"] = high_value(sup, match, qt, vat_caveats)

    c = cs_sum["contracts"]
    analytics = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "language": LANGUAGE,
        "inputs": {
            "rules": {"file": rel(RULES), "sha256": sha256(RULES),
                      "verify_quotes": "PASS", "verify_summary": verify_line[-1] if verify_line else ""},
            "spend_files": [{k: f[k] for k in ("file", "sha256", "header_excel_row", "rows")}
                            for f in cs_sum["spend_files"]],
            "contracts": ({"present": True, "sha256": c["sha256"], "rows_raw": c["rows_raw"],
                           "rows_council": c["rows_council"], "dropped_by_org": c["dropped_by_org"],
                           "live_in_window": c["live_in_window"], "warnings": c["warnings"]}
                          if c["present"] else {"present": False}),
        },
        "window": cs_sum["window"],
        "cleaning": {k: cs_sum[k] for k in ("rows_read", "excluded", "public_body_names", "rows_kept",
                                            "gbp_kept", "tags")}
        | {"cross_file_duplicates": cs_sum["cross_file_duplicates"]["rows"]},
        "thresholds": {k: th[k] for k in ("tiers", "skipped_tiers", "quote_threshold",
                                          "publication_threshold", "caveats")},
        "matching": {"method": "exact normalised name only",
                     "companies_house": "not possible: spend has no company numbers",
                     "candidates_file": rel(FULL / "name_candidates.csv") if contracts_present else None,
                     "candidate_pairs": match["n_candidate_pairs"] if match else None,
                     "spend_keys_with_candidates": match["n_keys_with_candidates"] if match else None,
                     "note": "A candidate is never counted as a match; the auditor confirms candidates."},
        "tests": tests,
        "self_check": {"status": "not run"},
    }
    write_json(ANALYTICS, analytics)

    print(f"window {cs_sum['window']['start']}..{cs_sum['window']['end']}  factor {factor}")
    for name, t in tests.items():
        if t["status"] == "skipped":
            print(f"{name}: skipped ({t['reason'][:70]})")
        else:
            print(f"{name}: {t['counts'].get('flagged')} flagged, GBP {t['gbp_total']:,.2f}")
    if match:
        print(f"name candidates: {match['n_candidate_pairs']} pairs for "
              f"{match['n_keys_with_candidates']} spend keys (not counted as matches)")


# ------------------------------------------------------------------ supplier table
def supplier_table(pay: pd.DataFrame, factor: float) -> pd.DataFrame:
    rows = []
    for key, g in pay.groupby("supplier_key", sort=False):
        tag_mix = g.groupby("tag")["amount"].sum().sort_values(ascending=False, kind="stable")
        raw_mode = g["supplier_raw"].value_counts()
        total = g["amount"].sum()
        rows.append({"supplier_key": key,
                     "supplier_name": raw_mode.index[0],
                     "n_payments": int(len(g)),
                     "total": money(total),
                     "annualised_estimate": money(total * factor),
                     "main_tag": tag_mix.index[0],
                     "tag_mix": "; ".join(f"{t}={money(v)}" for t, v in tag_mix.items()),
                     "services": "; ".join(sorted(g["service"].unique())),
                     "row_ids": ";".join(g.sort_values(["pay_date", "timestamp"])["row_id"])})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ matching
def build_matching(sup: pd.DataFrame, notices: pd.DataFrame) -> dict:
    by_key = defaultdict(list)
    for r in notices.itertuples():
        by_key[r.supplier_key].append(r)
    notice_keys = sorted(by_key)
    exact = {k: by_key[k] for k in sup["supplier_key"] if k in by_key}

    def sides(k):
        return [s.strip() for s in RE_TRADING.split(k) if s.strip()]

    cand_rows = []
    for k in sup["supplier_key"]:
        if k in exact:
            continue
        ksides = sides(k)
        for nk in notice_keys:
            method = None
            nsides = sides(nk)
            score = difflib.SequenceMatcher(None, k, nk).ratio()
            if (len(ksides) > 1 and nk in ksides) or (len(nsides) > 1 and k in nsides) or \
                    (len(ksides) > 1 and len(nsides) > 1 and set(ksides) & set(nsides)):
                method = "trading_name"
            elif len(k) >= CANDIDATE_MIN_LEN and len(nk) >= CANDIDATE_MIN_LEN and (k in nk or nk in k):
                method = "contains"
            elif score >= CANDIDATE_RATIO:
                method = "similarity"
            if method:
                for nid in sorted({r.notice_id for r in by_key[nk]}):
                    cand_rows.append({"spend_key": k, "notice_key": nk, "notice_id": nid,
                                      "method": method, "score": round(score, 4)})
    cand = pd.DataFrame(cand_rows, columns=["spend_key", "notice_key", "notice_id", "method", "score"])
    cand.to_csv(FULL / "name_candidates.csv", index=False)
    n_cand = cand.groupby("spend_key")["notice_id"].nunique().to_dict() if len(cand) else {}
    return {"exact": exact, "candidates": n_cand, "n_candidate_pairs": int(len(cand)),
            "n_keys_with_candidates": int(len(n_cand))}


def notice_status(key, match) -> str:
    if match is None:
        return "not checked"
    if key in match["exact"]:
        return "exact_live" if any(r.live for r in match["exact"][key]) else "exact_expired_only"
    return "candidate_only" if match["candidates"].get(key, 0) > 0 else "none"


# ------------------------------------------------------------------ tests
def threshold_clustering(pay, tiers, anti, vat_caveats):
    parts, per_tier, rule_ids = [], [], []
    for t in tiers:
        T = float(t["amount"])
        band = pay[(pay["amount"] >= CLUSTER_LOW * T) & (pay["amount"] < T)].copy()
        comp = pay[(pay["amount"] >= T) & (pay["amount"] < CLUSTER_HIGH * T)]
        band["tier"] = t["amount"]
        parts.append(band)
        per_tier.append({"tier": t["amount"], "rule_ids": t["rule_ids"],
                         "band": [money(CLUSTER_LOW * T), t["amount"]],
                         "band_count": int(len(band)), "band_gbp": money(band["amount"].sum()),
                         "comparison_band": [t["amount"], money(CLUSTER_HIGH * T)],
                         "comparison_count": int(len(comp)), "comparison_gbp": money(comp["amount"].sum()),
                         "band_to_comparison_ratio": (round(len(band) / len(comp), 4) if len(comp) else None)})
        rule_ids += t["rule_ids"]
    flagged = pd.concat(parts, ignore_index=True)
    flagged = flagged.sort_values("amount", ascending=False, kind="stable")
    cols = ["tier", "row_id", "supplier_raw", "supplier_key", "pay_date", "timestamp", "amount",
            "service", "narrative", "tag"]
    path = FULL / "threshold_clustering.csv"
    flagged[cols].to_csv(path, index=False)
    uniq = flagged.drop_duplicates("row_id")
    return {"status": "ran", "rule_ids": sorted(set(rule_ids + anti)),
            "parameters": {"band": f"[{CLUSTER_LOW} x T, T)", "comparison": f"[T, {CLUSTER_HIGH} x T)",
                           "tiers": [t["amount"] for t in tiers], "unit": "single payment"},
            "counts": {"flagged": int(len(uniq)), "per_tier": per_tier},
            "gbp_total": money(uniq["amount"].sum()),
            "by_tag": by_tag(uniq, "amount"),
            "top20": records(flagged[cols]),
            "full_list": rel(path),
            "caveats": ["Payments just below a threshold: an indicator to investigate. Many "
                        "legitimate payments fall in any band; compare with the adjacent band."]
            + vat_caveats}


def split_purchases(pay, tiers, anti, vat_caveats):
    groups, per_tier, rule_ids = [], [], []
    gid = 0
    for t in tiers:
        T = float(t["amount"])
        rule_ids += t["rule_ids"]
        under = pay[pay["amount"] < T].sort_values(["supplier_key", "pay_date_d", "timestamp", "row_id"])
        n_before = len(groups)
        for key, g in under.groupby("supplier_key", sort=False):
            if len(g) < 2:
                continue
            dates = g["pay_date_d"].tolist()
            amts = g["amount"].tolist()
            i = 0
            while i < len(g):
                j = i
                while j + 1 < len(g) and (dates[j + 1] - dates[i]).days <= SPLIT_DAYS:
                    j += 1
                total = sum(amts[i:j + 1])
                if j > i and total >= T:
                    sl = g.iloc[i:j + 1]
                    gid += 1
                    groups.append({"group_id": f"S{gid:05d}", "tier": t["amount"], "supplier_key": key,
                                   "supplier_name": sl["supplier_raw"].value_counts().index[0],
                                   "first_date": sl["pay_date"].iloc[0], "last_date": sl["pay_date"].iloc[-1],
                                   "n": int(len(sl)), "total": money(total),
                                   "tag": majority_tag(sl["amount"], sl["tag"]),
                                   "row_ids": ";".join(sl["row_id"]),
                                   "amounts": ";".join(f"{a:.2f}" for a in sl["amount"]),
                                   "pay_dates": ";".join(sl["pay_date"])})
                    i = j + 1
                else:
                    i += 1
        tg = pd.DataFrame(groups[n_before:])
        per_tier.append({"tier": t["amount"], "rule_ids": t["rule_ids"], "groups": int(len(tg)),
                         "gbp": money(tg["total"].sum()) if len(tg) else 0.0,
                         "by_tag": by_tag(tg, "total") if len(tg) else {}})
    gdf = pd.DataFrame(groups)
    path = FULL / "split_purchases.csv"
    if len(gdf):
        gdf = gdf.sort_values("total", ascending=False, kind="stable")
    gdf.to_csv(path, index=False)
    rows_in = sorted({r for ids in gdf.get("row_ids", []) for r in ids.split(";")})
    gbp_rows = money(pay[pay["row_id"].isin(rows_in)]["amount"].sum())
    return {"status": "ran", "rule_ids": sorted(set(rule_ids + anti)),
            "parameters": {"window_days": SPLIT_DAYS, "rule": "same supplier_key, >=2 payments each < T, "
                           "pay_date span <= window_days, sum >= T; greedy scan",
                           "tiers": [t["amount"] for t in tiers]},
            "counts": {"flagged": int(len(gdf)), "distinct_payments": len(rows_in), "per_tier": per_tier},
            "gbp_total": gbp_rows,
            "gbp_total_basis": "distinct payments in any group (a payment can sit in groups for several tiers)",
            "by_tag": by_tag(gdf, "total") if len(gdf) else {},
            "top20": records(gdf.drop(columns=["amounts", "pay_dates"])) if len(gdf) else [],
            "full_list": rel(path),
            "caveats": ["Repeated payments that together pass a threshold: an indicator to investigate, "
                        "not evidence that a requirement was divided. Care placements and other recurring "
                        "services recur by nature; see by_tag.",
                        "Groups for the lowest tier are numerous by construction."] + vat_caveats}


def off_contract(sup, match, pubt, factor, vat_caveats):
    T = float(pubt["amount"])
    pop = sup[sup["annualised_estimate"] > T].copy()
    live_exact = {k for k, rs in match["exact"].items() if any(r.live for r in rs)}
    fl = pop[~pop["supplier_key"].isin(live_exact)].copy()
    fl["exact_expired_only"] = fl["supplier_key"].isin(match["exact"].keys())
    fl["candidates"] = fl["supplier_key"].map(lambda k: int(match["candidates"].get(k, 0)))
    fl["indicator"] = "no published notice found"
    fl = fl.sort_values("total", ascending=False, kind="stable")
    cols = ["supplier_key", "supplier_name", "n_payments", "total", "annualised_estimate",
            "exact_expired_only", "candidates", "main_tag", "tag_mix", "services", "indicator", "row_ids"]
    path = FULL / "off_contract.csv"
    fl[cols].to_csv(path, index=False)
    return {"status": "ran", "rule_ids": pubt["rule_ids"],
            "parameters": {"publication_threshold": pubt["amount"], "basis": ANNUAL_LABEL,
                           "annualisation_factor": factor, "match": "exact normalised name, live notice"},
            "counts": {"flagged": int(len(fl)), "population_above_threshold": int(len(pop)),
                       "flagged_with_candidates": int((fl["candidates"] > 0).sum()),
                       "flagged_exact_expired_only": int(fl["exact_expired_only"].sum())},
            "gbp_total": money(fl["total"].sum()),
            "gbp_total_basis": "spend in window (not annualised)",
            "by_tag": by_tag(fl, "total", "main_tag"),
            "top20": records(fl[cols[:-1]]),
            "full_list": rel(path),
            "caveats": [
                "No published notice found: an indicator to investigate, not evidence that no contract exists.",
                "Contracts Finder only publishes contracts above about GBP 25k, so smaller suppliers "
                "legitimately never appear in it. This test covers only suppliers whose annualised "
                "estimate exceeds the publication threshold; its results must never be used to question "
                "smaller suppliers.",
                "Pre-2021 contracts, frameworks, care placements and other routes can legitimately have "
                "no notice in this export.",
                "Matching is exact on normalised name only; near-miss names are listed as candidates "
                "(column 'candidates') for the auditor to confirm and are not counted as matches.",
                CAVEAT_ANNUAL] + vat_caveats}


def duplicates(pay, doc_ids):
    pay = pay.copy()
    pay["pence"] = (pay["amount"] * 100).round().astype("int64")
    groups, gid = [], 0
    for (key, pence), g in pay.groupby(["supplier_key", "pence"], sort=False):
        if len(g) < 2:
            continue
        g = g.sort_values(["pay_date_d", "timestamp", "row_id"])
        dates = g["pay_date_d"].tolist()
        start = 0
        for i in range(1, len(g) + 1):
            if i == len(g) or (dates[i] - dates[i - 1]).days > DUP_DAYS:
                if i - start >= 2:
                    sl = g.iloc[start:i]
                    gid += 1
                    groups.append({"group_id": f"D{gid:05d}", "supplier_key": key,
                                   "supplier_name": sl["supplier_raw"].value_counts().index[0],
                                   "amount": money(sl["amount"].iloc[0]), "n": int(len(sl)),
                                   "total": money(sl["amount"].sum()),
                                   "repeat_value": money(sl["amount"].sum() - sl["amount"].iloc[0]),
                                   "first_date": sl["pay_date"].iloc[0], "last_date": sl["pay_date"].iloc[-1],
                                   "tag": majority_tag(sl["amount"], sl["tag"]),
                                   "row_ids": ";".join(sl["row_id"]),
                                   "amounts": ";".join(f"{a:.2f}" for a in sl["amount"]),
                                   "pay_dates": ";".join(sl["pay_date"])})
                start = i
    gdf = pd.DataFrame(groups)
    path = FULL / "duplicates.csv"
    if len(gdf):
        gdf = gdf.sort_values("total", ascending=False, kind="stable")
    gdf.to_csv(path, index=False)
    return {"status": "ran", "rule_ids": doc_ids,
            "parameters": {"rule": "same supplier_key, same amount to the penny, consecutive pay_dates "
                           f"<= {DUP_DAYS} days apart (pairs joined into groups)", "days": DUP_DAYS},
            "counts": {"flagged": int(len(gdf)), "payments": int(gdf["n"].sum()) if len(gdf) else 0},
            "gbp_total": money(gdf["total"].sum()) if len(gdf) else 0.0,
            "gbp_repeat_value": money(gdf["repeat_value"].sum()) if len(gdf) else 0.0,
            "by_tag": by_tag(gdf, "total") if len(gdf) else {},
            "top20": records(gdf.drop(columns=["amounts", "pay_dates"])) if len(gdf) else [],
            "full_list": rel(path),
            "caveats": ["Possible duplicate payments: an indicator to investigate. Recurring fixed-fee "
                        "services (care packages, rents, instalments) legitimately repeat the same amount.",
                        "gbp_total counts every payment in a group; gbp_repeat_value excludes the first."]}


def expired_notice_spend(sup, match, notices, window_start, rule_ids):
    rows = []
    for r in sup.itertuples():
        ns = match["exact"].get(r.supplier_key)
        if not ns:
            continue
        ends = {(n.notice_id, n.end) for n in ns}
        if all(e != "" and dt.date.fromisoformat(e) < window_start for _, e in ends):
            rows.append({"supplier_key": r.supplier_key, "supplier_name": r.supplier_name,
                         "n_payments": r.n_payments, "total": r.total,
                         "annualised_estimate": r.annualised_estimate, "main_tag": r.main_tag,
                         "notice_ids": ";".join(n for n, _ in sorted(ends)),
                         "notice_end_dates": ";".join(e for _, e in sorted(ends)),
                         "latest_end": max(e for _, e in ends), "row_ids": r.row_ids})
    df = pd.DataFrame(rows, columns=["supplier_key", "supplier_name", "n_payments", "total",
                                     "annualised_estimate", "main_tag", "notice_ids", "notice_end_dates",
                                     "latest_end", "row_ids"])
    df = df.sort_values("total", ascending=False, kind="stable")
    path = FULL / "expired_notice_spend.csv"
    df.to_csv(path, index=False)
    return {"status": "ran", "rule_ids": rule_ids,
            "parameters": {"window_start": window_start.isoformat(),
                           "rule": "every exact-matched council notice ended before the window start"},
            "counts": {"flagged": int(len(df)), "suppliers_with_exact_match": len(match["exact"])},
            "gbp_total": money(df["total"].sum()), "gbp_total_basis": "spend in window",
            "by_tag": by_tag(df, "total", "main_tag"),
            "top20": records(df.drop(columns=["row_ids"])),
            "full_list": rel(path),
            "caveats": ["Spend after the published end date: an indicator to investigate (Appendix C row D: "
                        "extensions need approval). A newer contract or an approved extension may exist "
                        "without a published notice.",
                        "Matching is exact on normalised name only."]}


def spend_vs_award(sup, match, notices, factor, rule_ids, vat_caveats):
    rows, skipped_years, eligible = [], 0, 0
    for r in sup.itertuples():
        ns = match["exact"].get(r.supplier_key)
        if not ns:
            continue
        live = {n.notice_id: n for n in ns if n.live}
        if len(live) != 1:
            continue
        n = next(iter(live.values()))
        if n.n_suppliers != 1 or not n.awarded_value > 0:
            continue
        if n.end == "":
            skipped_years += 1
            continue
        days = (dt.date.fromisoformat(n.end) - dt.date.fromisoformat(n.start)).days
        if days <= 0:
            skipped_years += 1
            continue
        eligible += 1
        years = days / 365.25
        annual_award = n.awarded_value / years
        ratio = r.annualised_estimate / annual_award
        rows.append({"supplier_key": r.supplier_key, "supplier_name": r.supplier_name,
                     "notice_id": n.notice_id, "title": n.title, "start": n.start, "end": n.end,
                     "awarded_value": money(n.awarded_value), "contract_years": round(years, 4),
                     "annual_award": money(annual_award), "total": r.total,
                     "annualised_estimate": r.annualised_estimate, "ratio": round(ratio, 4),
                     "flag": ratio >= AWARD_RATIO_FLAG, "main_tag": r.main_tag, "row_ids": r.row_ids})
    df = pd.DataFrame(rows, columns=["supplier_key", "supplier_name", "notice_id", "title", "start", "end",
                                     "awarded_value", "contract_years", "annual_award", "total",
                                     "annualised_estimate", "ratio", "flag", "main_tag", "row_ids"])
    fl = df[df["flag"]].sort_values("total", ascending=False, kind="stable")
    path = FULL / "spend_vs_award.csv"
    fl.to_csv(path, index=False)
    df.to_csv(FULL / "spend_vs_award_population.csv", index=False)
    return {"status": "ran", "rule_ids": rule_ids,
            "parameters": {"flag_ratio": AWARD_RATIO_FLAG, "annualisation_factor": factor,
                           "rule": "exactly one live exact-matched notice, n_suppliers == 1, "
                           "Awarded Value > 0; ratio = annualised estimate / (value / contract years)"},
            "counts": {"flagged": int(len(fl)), "eligible": eligible,
                       "skipped_no_or_bad_contract_years": skipped_years},
            "gbp_total": money(fl["total"].sum()), "gbp_total_basis": "spend in window",
            "by_tag": by_tag(fl, "total", "main_tag"),
            "top20": records(fl.drop(columns=["row_ids"])),
            "full_list": rel(path),
            "caveats": ["Spend above the awarded value: an indicator to investigate (Appendix C row E: "
                        "variations need approval).",
                        "Award values may be estimates or maxima, and may include VAT; spend is net.",
                        CAVEAT_ANNUAL] + vat_caveats}


def high_value(sup, match, qt, vat_caveats):
    T = float(qt["amount"])
    hv = sup[sup["annualised_estimate"] > T].copy()
    hv["notice_status"] = hv["supplier_key"].map(lambda k: notice_status(k, match))
    hv = hv.sort_values("total", ascending=False, kind="stable")
    cols = ["supplier_key", "supplier_name", "n_payments", "total", "annualised_estimate", "main_tag",
            "tag_mix", "services", "notice_status", "row_ids"]
    path = FULL / "high_value_suppliers.csv"
    hv[cols].to_csv(path, index=False)
    status_counts = hv["notice_status"].value_counts().to_dict()
    return {"status": "ran", "rule_ids": qt["rule_ids"],
            "parameters": {"quote_threshold": qt["amount"], "basis": ANNUAL_LABEL},
            "counts": {"flagged": int(len(hv)), "by_notice_status": {k: int(v) for k, v in status_counts.items()}},
            "gbp_total": money(hv["total"].sum()), "gbp_total_basis": "spend in window",
            "by_tag": by_tag(hv, "total", "main_tag"),
            "top20": records(hv[cols[:-1]]),
            "full_list": rel(path),
            "caveats": ["Population to request contract evidence for, not a list of concerns.",
                        CAVEAT_ANNUAL] + vat_caveats}


if __name__ == "__main__":
    main()
