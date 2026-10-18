"""Self-check: re-derive the first top-20 item of every test that ran and
flagged something, from the SOURCE workbooks (openpyxl) and contracts.csv
(csv module), independently of clean.py.

Writes outputs/analytics-full/self_check.json, updates analytics.json ->
self_check, exits 1 on any mismatch.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SPEND_DIR = ROOT / "data" / "spend"
CONTRACTS = ROOT / "data" / "contracts.csv"
FULL = ROOT / "outputs" / "analytics-full"
ANALYTICS = ROOT / "outputs" / "analytics.json"
SHEET = "Data to publish"
COLS = ["Service", "Expenditure category", "Narrative", "Date", "Net amount", "Supplier name"]
BUYERS = {"West Berkshire Council", "West Berkshire"}
SUPPLIER_COL = "Supplier [Name|Address|Ref type|Ref Number|Is SME|Is VCSE]"
TOL = 0.01


# independent re-implementation of the supplier normaliser (not imported)
def key_of(name) -> str:
    s = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]", " ", str(name or "").upper())).strip()
    toks = s.split() if s else []
    while toks and toks[-1] in ("LTD", "LIMITED", "PLC", "LLP"):
        toks = toks[:-1]
    return " ".join(toks)


def load_source():
    """-> {row_id: (supplier, datetime, amount)}, n_files, window (start, end)."""
    rows, files = {}, sorted(p for p in SPEND_DIR.glob("*.xlsx") if not p.name.startswith("~$"))
    for f in files:
        wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        ws = wb[SHEET]
        hdr_row, idx = None, None
        for n, vals in enumerate(ws.iter_rows(values_only=True), start=1):
            if hdr_row is None:
                names = [str(v).strip() if v is not None else "" for v in vals]
                if set(COLS) <= set(names):
                    hdr_row, idx = n, {c: names.index(c) for c in COLS}
                elif n >= 20:
                    raise SystemExit(f"self_check: no header in {f.name}")
                continue
            sup, d, amt = vals[idx["Supplier name"]], vals[idx["Date"]], vals[idx["Net amount"]]
            if all(vals[idx[c]] in (None, "") for c in COLS):
                continue
            if isinstance(d, str):
                d = dt.datetime.strptime(d.strip(), "%m/%d/%y")
            rows[f"{f.name}|{SHEET}|{n}"] = (str(sup).strip(), d, float(amt))
        wb.close()
    dates = [v[1].date() for v in rows.values()]
    return rows, len(files), (min(dates), max(dates))


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_notices(window):
    """Re-parse contracts.csv with the csv module -> list of dicts (council only)."""
    ws, we = window
    out = []
    with open(CONTRACTS, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["Organisation Name"].strip() not in BUYERS:
                continue
            start = dt.datetime.strptime(r["Contract start date"].strip(), "%d/%m/%Y").date()
            e = r["Contract end date"].strip()
            end = dt.datetime.strptime(e, "%d/%m/%Y").date() if e else None
            live = start <= we and (end is None or end >= ws)
            blocks = r[SUPPLIER_COL].strip()[1:-1].split("][")
            for b in blocks:
                out.append({"notice_id": r["Notice Identifier"].strip(), "key": key_of(b.split("|")[0].strip()),
                            "start": start, "end": end, "live": live, "n_suppliers": len(blocks),
                            "value": float(r["Awarded Value"].replace(",", "") or 0)})
    return out


class Check:
    def __init__(self, test):
        self.test, self.items, self.ok = test, [], True

    def eq(self, what, expected, got, ok=None):
        ok = (expected == got) if ok is None else ok
        self.items.append({"check": what, "expected": expected, "source": got, "pass": bool(ok)})
        self.ok &= bool(ok)

    def result(self, item_ref):
        return {"status": "PASS" if self.ok else "FAIL", "item": item_ref, "checks": self.items}


def check_rows(c, row_ids, src, expect):
    """expect: {row_id: (supplier, pay_date iso, amount, timestamp or None)} from full lists."""
    for rid in row_ids:
        if rid not in src:
            c.eq(f"{rid} exists in source", True, False)
            continue
        s_sup, s_dt, s_amt = src[rid]
        e_sup, e_date, e_amt, e_ts = expect[rid]
        c.eq(f"{rid} supplier", e_sup, s_sup)
        c.eq(f"{rid} date", e_date, s_dt.date().isoformat())
        if e_ts:
            c.eq(f"{rid} timestamp", e_ts, s_dt.isoformat())
        c.eq(f"{rid} amount", round(e_amt, 2), round(s_amt, 2), abs(e_amt - s_amt) < 0.005)


def main():
    a = json.load(open(ANALYTICS, encoding="utf-8"))
    tests = a["tests"]
    src, n_files, window = load_source()
    factor = 12 / n_files
    clean = {r["row_id"]: r for r in load_csv(FULL / "spend_clean.csv")}
    excluded = {r["row_id"] for r in load_csv(FULL / "exclusions.csv")}
    notices = load_notices(window) if CONTRACTS.exists() else []
    per_test, all_ok = {}, True

    def clean_expect(rids):
        return {r: (clean[r]["supplier_raw"], clean[r]["pay_date"], float(clean[r]["amount"]),
                    clean[r]["timestamp"]) if r in clean else ("<missing>", "", float("nan"), None)
                for r in rids}

    def group_expect(row):
        rids, amts, dates = row["row_ids"].split(";"), row["amounts"].split(";"), row["pay_dates"].split(";")
        return rids, {r: (clean.get(r, {}).get("supplier_raw", "<missing>"), d, float(x), None)
                      for r, x, d in zip(rids, amts, dates)}

    def supplier_check(c, name, item):
        full = {r["supplier_key"]: r for r in load_csv(ROOT / tests[name]["full_list"])}
        row = full[item["supplier_key"]]
        rids = row["row_ids"].split(";")
        check_rows(c, rids, src, clean_expect(rids))
        same_key = {rid for rid, v in src.items() if key_of(v[0]) == item["supplier_key"]}
        c.eq("listed rows all carry this normalised supplier", True, set(rids) <= same_key)
        others = same_key - set(rids)
        c.eq("every other same-supplier source row is in exclusions.csv", sorted(others - excluded) == [], True,
             not (others - excluded))
        s = sum(src[r][2] for r in rids if r in src)
        rep = float(row["annualised_estimate"])
        c.eq("annualised estimate = source sum x factor", rep, round(s * factor, 2), abs(s * factor - rep) <= TOL)
        return row

    for name, t in tests.items():
        if t.get("status") != "ran" or not t.get("top20"):
            per_test[name] = {"status": "NOT APPLICABLE",
                              "reason": t.get("reason", "no flagged items")}
            continue
        item = t["top20"][0]
        c = Check(name)
        if name == "threshold_clustering":
            check_rows(c, [item["row_id"]], src, clean_expect([item["row_id"]]))
            amt, T = src[item["row_id"]][2], float(item["tier"])
            c.eq("0.9*T <= amount < T", True, 0.9 * T <= amt < T)
            ref = item["row_id"]
        elif name in ("split_purchases", "duplicates"):
            full = {r["group_id"]: r for r in load_csv(ROOT / t["full_list"])}
            row = full[item["group_id"]]
            rids, exp = group_expect(row)
            check_rows(c, rids, src, exp)
            vals = [src[r] for r in rids]
            amts = [v[2] for v in vals]
            days = [v[1].date() for v in vals]
            c.eq("same normalised supplier", [item["supplier_key"]], sorted({key_of(v[0]) for v in vals}))
            c.eq(">= 2 payments", True, len(vals) >= 2)
            if name == "split_purchases":
                T = float(row["tier"])
                c.eq("each payment < T", True, all(x < T for x in amts))
                c.eq("sum >= T", True, sum(amts) >= T)
                c.eq("sum equals reported total", float(row["total"]), round(sum(amts), 2),
                     abs(sum(amts) - float(row["total"])) <= TOL)
                c.eq("date span <= 30 days", True, (max(days) - min(days)).days <= 30)
            else:
                c.eq("same amount to the penny", 1, len({round(x * 100) for x in amts}))
                ds = sorted(days)
                c.eq("consecutive gaps <= 7 days", True, all((b - a_).days <= 7 for a_, b in zip(ds, ds[1:])))
            ref = item["group_id"]
        else:
            row = supplier_check(c, name, item)
            mine = [n for n in notices if n["key"] == item["supplier_key"]]
            if name == "off_contract":
                c.eq("no live council notice with same key", 0, sum(n["live"] for n in mine))
                c.eq("annualised > publication threshold", True,
                     float(row["annualised_estimate"]) > float(t["parameters"]["publication_threshold"]))
            elif name == "expired_notice_spend":
                c.eq("has matched notices", True, len(mine) > 0)
                c.eq("all matched notices end before window start", True,
                     all(n["end"] is not None and n["end"] < window[0] for n in mine))
            elif name == "spend_vs_award":
                live = {n["notice_id"]: n for n in mine if n["live"]}
                c.eq("exactly one live notice", 1, len(live))
                n = next(iter(live.values()))
                c.eq("notice id", row["notice_id"], n["notice_id"])
                c.eq("single supplier, value > 0", True, n["n_suppliers"] == 1 and n["value"] > 0)
                years = (n["end"] - n["start"]).days / 365.25
                annual = n["value"] / years
                s = sum(src[r][2] for r in row["row_ids"].split(";"))
                ratio = s * factor / annual
                c.eq("annual award recomputes", float(row["annual_award"]), round(annual, 2),
                     abs(annual - float(row["annual_award"])) <= TOL)
                c.eq("ratio recomputes (4 dp)", float(row["ratio"]), round(ratio, 4),
                     abs(ratio - float(row["ratio"])) <= 0.00005 + 1e-12)
                c.eq("ratio >= 1.25", True, ratio >= 1.25)
            elif name == "high_value_suppliers":
                c.eq("annualised > quote threshold", True,
                     float(row["annualised_estimate"]) > float(t["parameters"]["quote_threshold"]))
                if notices:
                    exp = ("exact_live" if any(n["live"] for n in mine) else
                           "exact_expired_only" if mine else row["notice_status"])
                    if row["notice_status"] in ("candidate_only", "none"):
                        c.eq("no exact notice match", 0, len(mine))
                    else:
                        c.eq("notice_status", row["notice_status"], exp)
            ref = item["supplier_key"]
        per_test[name] = c.result(ref)
        all_ok &= c.ok

    status = "PASS" if all_ok else "FAIL"
    out = {"status": status, "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
           "method": "first top-20 item per test re-derived from source workbooks (openpyxl) and "
                     "contracts.csv (csv module) with an independent normaliser",
           "factor": factor, "window": [window[0].isoformat(), window[1].isoformat()],
           "per_test": per_test}
    with open(FULL / "self_check.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    a["self_check"] = {"status": status, "file": "outputs/analytics-full/self_check.json",
                       "per_test": {k: v["status"] for k, v in per_test.items()}}
    with open(ANALYTICS, "w", encoding="utf-8") as f:
        json.dump(a, f, indent=2, ensure_ascii=False)
        f.write("\n")
    for k, v in per_test.items():
        n_fail = sum(not x["pass"] for x in v.get("checks", []))
        print(f"{k}: {v['status']}" + (f" ({len(v['checks'])} checks, {n_fail} failed)" if "checks" in v else ""))
        for x in v.get("checks", []):
            if not x["pass"]:
                print(f"   FAIL {x['check']}")
    print(f"self-check: {status}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
