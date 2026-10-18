"""Clean the spend workbooks and (if present) parse contracts.csv.

Outputs (outputs/analytics-full/):
  spend_clean.csv          kept rows plus credit rows (is_credit = true)
  exclusions.csv           every excluded row with its first reason
  cross_file_duplicates.csv rows identical on supplier/amount/timestamp across files
  contract_suppliers.csv   one row per (notice, supplier), council notices only
  cleaning_summary.json    counts and GBP only
Prints a short summary. Stops on malformed input.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import (CONTRACT_DATE_FORMAT, CONTRACTS, EXPECTED_COLS, FULL,  # noqa: E402
                    HEADER_SCAN_ROWS, SHEET, SPEND_DIR, SPEND_TEXT_DATE_FORMAT,
                    money, normalise_supplier, rel, sha256, stop, write_json)

# ---------------------------------------------------------------- rules (spec)
RE_REDACTED = re.compile(r"withheld|personal data|not disclosed")
RE_PENSION = re.compile(r"LGPS|\bAVC\b|Pension|Court Order|Deferred Debt|Children in Care: Savings",
                        re.IGNORECASE)
PUBLIC_BODY_NARRATIVES = {
    "Payments to Other Local Authorities (excl Joint Arrangements)",
    "Payments to NHS (excl Joint Arrangement)",
    "Joint Arrangements (with Other Local Authorities or NHS)",
}
RE_PUBLIC_KEY = re.compile(r"\bCOUNCIL\b|\bBOROUGH OF\b|\bNHS\b|\bPOLICE\b|FIRE AND RESCUE|"
                           r"\bDEPARTMENT FOR\b|SECRETARY OF STATE|\bHMRC\b|HM REVENUE|"
                           r"INTEGRATED CARE BOARD")
RE_GRANT = re.compile(r"\bGrants?\b", re.IGNORECASE)
RE_CARE_SERVICE = re.compile(r"Social Care|Education|SEND")
CARE_NARRATIVES = {"Private Contractors", "Allowances for provision care",
                   "Adult Placement Allowances", "Direct Payment", "Payments to Carers",
                   "Other agencies", "Voluntary Associations"}
COUNCIL_BUYERS = {"West Berkshire Council", "West Berkshire"}
SUPPLIER_COL = "Supplier [Name|Address|Ref type|Ref Number|Is SME|Is VCSE]"


def is_blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and v.strip() == "") \
        or (v is pd.NaT)


def text(v) -> str:
    return "" if is_blank(v) else str(v).strip()


def find_header(raw: pd.DataFrame, fname: str) -> int:
    for i in range(min(HEADER_SCAN_ROWS, len(raw))):
        cells = {text(v) for v in raw.iloc[i].tolist() if not is_blank(v)}
        if set(EXPECTED_COLS) <= cells:
            return i
    found = sorted({text(v) for i in range(min(HEADER_SCAN_ROWS, len(raw)))
                    for v in raw.iloc[i].tolist() if not is_blank(v)})[:30]
    stop(f"{fname}: no header row with all of {EXPECTED_COLS} in the first "
         f"{HEADER_SCAN_ROWS} rows; non-blank values found include {found}")


def read_workbook(path):
    fname = path.name
    xl = pd.ExcelFile(path, engine="openpyxl")
    if SHEET not in xl.sheet_names:
        stop(f"{fname}: sheet '{SHEET}' missing (sheets: {xl.sheet_names})")
    raw = pd.read_excel(xl, sheet_name=SHEET, header=None, dtype=object)
    hidx = find_header(raw, fname)
    header_excel_row = hidx + 1
    # guard the pandas-index -> Excel-row mapping with a direct openpyxl read
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET]
    xl_header = [text(c) for c in next(ws.iter_rows(min_row=header_excel_row,
                                                    max_row=header_excel_row, values_only=True))]
    wb.close()
    if not set(EXPECTED_COLS) <= set(xl_header):
        stop(f"{fname}: header located at pandas row {hidx} but Excel row {header_excel_row} "
             f"does not hold the expected columns; row mapping is unreliable")
    names = [text(v) for v in raw.iloc[hidx].tolist()]
    missing = [c for c in EXPECTED_COLS if c not in names]
    if missing:
        stop(f"{fname}: columns missing {missing}; found {names}")
    dupes = [c for c in EXPECTED_COLS if names.count(c) > 1]
    if dupes:
        stop(f"{fname}: expected columns appear more than once: {dupes}")
    cols = {c: names.index(c) for c in EXPECTED_COLS}
    body = raw.iloc[hidx + 1:, [cols[c] for c in EXPECTED_COLS]].copy()
    body.columns = EXPECTED_COLS
    body["data_index"] = range(len(body))
    body["excel_row"] = header_excel_row + 1 + body["data_index"]
    body["file"] = fname
    body["row_id"] = fname + "|" + SHEET + "|" + body["excel_row"].astype(str)
    return body, header_excel_row


def period_of(fname: str) -> str:
    m = re.search(r"(\d{4})_P(\d{2})", fname)
    return f"{m.group(1)}-P{m.group(2)}" if m else fname.rsplit(".", 1)[0]


def parse_spend_date(v):
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return pd.Timestamp(v)
    if isinstance(v, str):
        try:
            return pd.Timestamp(dt.datetime.strptime(v.strip(), SPEND_TEXT_DATE_FORMAT))
        except ValueError:
            return None
    return None


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and not math.isnan(v)


def main():
    files = sorted(SPEND_DIR.glob("*.xlsx"))
    files = [f for f in files if not f.name.startswith("~$")]
    if not files:
        stop(f"no spend workbooks in {rel(SPEND_DIR)}")

    frames, file_meta = [], []
    for f in files:
        body, hrow = read_workbook(f)
        file_meta.append({"file": f.name, "sha256": sha256(f), "header_excel_row": hrow,
                          "period": period_of(f.name), "rows_raw": int(len(body))})
        frames.append(body)
    # same six columns asserted per workbook above, before combining
    for fr, m in zip(frames, file_meta):
        assert list(fr.columns[:6]) == EXPECTED_COLS, m["file"]
    df = pd.concat(frames, ignore_index=True)

    blank_mask = df[EXPECTED_COLS].apply(lambda r: all(is_blank(v) for v in r), axis=1)
    blank_rows = int(blank_mask.sum())
    df = df[~blank_mask].copy()
    for m in file_meta:
        m["rows"] = int((df["file"] == m["file"]).sum())

    # ---- dates
    ts = df["Date"].map(parse_spend_date)
    bad = ts.isna()
    if bad.any():
        stop(f"{int(bad.sum())} spend dates failed to parse (format {SPEND_TEXT_DATE_FORMAT}); "
             f"examples: {df.loc[bad, 'row_id'].head(5).tolist()}")
    df["timestamp"] = ts.map(lambda t: t.isoformat())
    df["pay_date"] = ts.map(lambda t: t.date().isoformat())

    # ---- amounts
    badamt = ~df["Net amount"].map(is_number)
    if badamt.any():
        stop(f"{int(badamt.sum())} non-numeric Net amount values; examples: "
             f"{df.loc[badamt, 'row_id'].head(5).tolist()}")
    df["amount"] = df["Net amount"].astype(float)

    # ---- supplier
    blank_sup = df["Supplier name"].map(is_blank)
    if blank_sup.any():
        stop(f"{int(blank_sup.sum())} rows have a blank Supplier name; examples: "
             f"{df.loc[blank_sup, 'row_id'].head(5).tolist()}")
    df["supplier_raw"] = df["Supplier name"].map(text)
    df["supplier_key"] = df["supplier_raw"].map(normalise_supplier)
    df["service"] = df["Service"].map(text)
    df["category"] = df["Expenditure category"].map(text)
    df["narrative"] = df["Narrative"].map(text)
    df["period"] = df["file"].map(period_of)
    df["is_credit"] = df["amount"] < 0

    # ---- exclusions (first reason wins)
    sup_l = df["supplier_raw"].str.lower()
    is_grant = df["narrative"].str.contains(RE_GRANT)
    r1 = (sup_l == "redacted") | sup_l.str.contains(RE_REDACTED)
    r2 = df["narrative"].str.contains(RE_PENSION)
    r3 = (df["narrative"].isin(PUBLIC_BODY_NARRATIVES) | df["supplier_key"].str.contains(RE_PUBLIC_KEY)) & ~is_grant
    r4 = df["is_credit"]
    reason = pd.Series("", index=df.index)
    for name, mask in [("redacted_supplier", r1), ("pension_statutory", r2),
                       ("public_body", r3), ("credit", r4)]:
        reason = reason.mask((reason == "") & mask, name)
    df["reason"] = reason

    # ---- tags (first that applies), computed for every row
    tag = pd.Series("general_procurement", index=df.index)
    tag = tag.mask(df["category"] == "Premises", "premises")
    tag = tag.mask(df["narrative"] == "Agency & Temporary Staff", "agency_staff")
    tag = tag.mask(df["service"].str.contains(RE_CARE_SERVICE) & df["narrative"].isin(CARE_NARRATIVES),
                   "care_education_placement")
    tag = tag.mask(is_grant, "grant")
    df["tag"] = tag

    FULL.mkdir(parents=True, exist_ok=True)
    excl = df[df["reason"] != ""]
    excl_out = excl.rename(columns={"supplier_raw": "supplier"})[
        ["row_id", "reason", "supplier", "service", "category", "narrative", "amount", "pay_date"]]
    excl_out.to_csv(FULL / "exclusions.csv", index=False)

    clean = df[df["reason"].isin(["", "credit"])]
    clean[["row_id", "file", "period", "service", "category", "narrative", "supplier_raw",
           "supplier_key", "pay_date", "timestamp", "amount", "is_credit", "tag"]].to_csv(
        FULL / "spend_clean.csv", index=False)
    kept = df[df["reason"] == ""]

    # ---- cross-file duplicates (logged, not dropped)
    g = df.groupby(["supplier_raw", "amount", "timestamp"])["file"].transform("nunique")
    xdup = df[g > 1].sort_values(["supplier_raw", "timestamp"])
    xdup[["row_id", "file", "supplier_raw", "amount", "timestamp", "reason"]].to_csv(
        FULL / "cross_file_duplicates.csv", index=False)

    window_start = min(df["pay_date"])
    window_end = max(df["pay_date"])
    n_periods = len(files)

    pub = excl[excl["reason"] == "public_body"].groupby("supplier_raw")["amount"].agg(["size", "sum"])
    summary = {
        "spend_files": [{k: m[k] for k in ("file", "sha256", "header_excel_row", "rows", "period")}
                        for m in file_meta],
        "blank_rows_dropped": blank_rows,
        "window": {"start": window_start, "end": window_end,
                   "periods": [m["period"] for m in file_meta],
                   "annualisation_factor": 12 / n_periods, "label": "annualised estimate"},
        "rows_read": int(len(df)),
        "excluded": {r: {"rows": int((excl["reason"] == r).sum()),
                         "gbp": money(excl.loc[excl["reason"] == r, "amount"].sum())}
                     for r in ["redacted_supplier", "pension_statutory", "public_body", "credit"]},
        "public_body_names": {k: {"rows": int(v["size"]), "gbp": money(v["sum"])}
                              for k, v in pub.sort_values("sum", ascending=False).iterrows()},
        "rows_kept": int(len(kept)),
        "gbp_kept": money(kept["amount"].sum()),
        "tags": {t: {"rows": int((kept["tag"] == t).sum()),
                     "gbp": money(kept.loc[kept["tag"] == t, "amount"].sum())}
                 for t in ["grant", "care_education_placement", "agency_staff", "premises",
                           "general_procurement"]},
        "cross_file_duplicates": {"rows": int(len(xdup)),
                                  "groups": int(xdup.groupby(["supplier_raw", "amount", "timestamp"]).ngroups),
                                  "file": rel(FULL / "cross_file_duplicates.csv")},
        "files": {"spend_clean": rel(FULL / "spend_clean.csv"),
                  "exclusions": rel(FULL / "exclusions.csv")},
    }

    # ---- contracts (optional)
    contracts = {"present": CONTRACTS.exists()}
    if CONTRACTS.exists():
        contracts.update(parse_contracts(window_start, window_end))
    summary["contracts"] = contracts
    write_json(FULL / "cleaning_summary.json", summary)

    # ---- short printed summary
    print(f"workbooks: {len(files)}  (header Excel rows: "
          f"{', '.join(str(m['header_excel_row']) for m in file_meta)})")
    print(f"rows read: {summary['rows_read']}  blank rows dropped: {blank_rows}")
    print(f"window: {window_start} .. {window_end}  factor: {12 / n_periods}")
    for r, v in summary["excluded"].items():
        print(f"  excluded {r}: {v['rows']} rows, GBP {v['gbp']:,.2f}")
    print(f"kept: {summary['rows_kept']} rows, GBP {summary['gbp_kept']:,.2f}")
    for t, v in summary["tags"].items():
        print(f"  tag {t}: {v['rows']} rows, GBP {v['gbp']:,.2f}")
    print(f"public-body distinct names: {len(summary['public_body_names'])}")
    print(f"cross-file duplicate rows: {summary['cross_file_duplicates']['rows']}")
    if contracts["present"]:
        print(f"contracts: raw {contracts['rows_raw']}, council {contracts['rows_council']}, "
              f"supplier rows {contracts['supplier_rows']}, live notices {contracts['live_in_window']}")
        print(f"  dropped by org: {sum(contracts['dropped_by_org'].values())} rows "
              f"across {len(contracts['dropped_by_org'])} names")
        for w in contracts["warnings"]:
            print(f"  WARNING: {w}")
    else:
        print("contracts: not present")


def parse_contract_date(v, notice, col, allow_blank=False):
    s = text(v)
    if s == "":
        if allow_blank:
            return None
        stop(f"contracts.csv notice {notice}: blank {col}")
    try:
        return dt.datetime.strptime(s, CONTRACT_DATE_FORMAT).date()
    except ValueError:
        stop(f"contracts.csv notice {notice}: unparseable {col} '{s}' (expected {CONTRACT_DATE_FORMAT})")


def parse_contracts(window_start: str, window_end: str) -> dict:
    raw = pd.read_csv(CONTRACTS, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    need = ["Notice Identifier", "Organisation Name", "Title", "Published Date", "Awarded Value",
            SUPPLIER_COL, "Contract start date", "Contract end date"]
    miss = [c for c in need if c not in raw.columns]
    if miss:
        stop(f"contracts.csv missing columns {miss}")
    org = raw["Organisation Name"].str.strip()
    keep = org.isin(COUNCIL_BUYERS)
    dropped = Counter(org[~keep])
    council = raw[keep]
    ws = dt.date.fromisoformat(window_start)
    we = dt.date.fromisoformat(window_end)

    rows, live_notices, pub_years = [], set(), Counter()
    for _, r in council.iterrows():
        nid = text(r["Notice Identifier"])
        start = parse_contract_date(r["Contract start date"], nid, "Contract start date")
        end = parse_contract_date(r["Contract end date"], nid, "Contract end date", allow_blank=True)
        parse_contract_date(r["Awarded Date"], nid, "Awarded Date", allow_blank=True) \
            if "Awarded Date" in r else None
        try:
            value = float(text(r["Awarded Value"]).replace(",", "") or "nan")
        except ValueError:
            stop(f"contracts.csv notice {nid}: non-numeric Awarded Value '{r['Awarded Value']}'")
        if math.isnan(value):
            stop(f"contracts.csv notice {nid}: blank Awarded Value")
        try:
            pub_years[dt.datetime.fromisoformat(text(r["Published Date"])).year] += 1
        except ValueError:
            stop(f"contracts.csv notice {nid}: unparseable Published Date")
        live = start <= we and (end is None or end >= ws)
        if live:
            live_notices.add(nid)
        s = text(r[SUPPLIER_COL])
        if not (s.startswith("[") and s.endswith("]")):
            stop(f"contracts.csv notice {nid}: supplier field is not bracketed")
        blocks = s[1:-1].split("][")
        for b in blocks:
            fields = b.split("|")
            if len(fields) != 6:
                stop(f"contracts.csv notice {nid}: supplier block has {len(fields)} fields, expected 6")
        for b in blocks:
            fields = b.split("|")
            name = fields[0].strip()
            rows.append({"notice_id": nid, "title": text(r["Title"]), "supplier_name": name,
                         "supplier_key": normalise_supplier(name),
                         "ch_number": fields[3].strip() if fields[2].strip() == "COMPANIES_HOUSE" else "",
                         "n_suppliers": len(blocks), "start": start.isoformat(),
                         "end": end.isoformat() if end else "", "awarded_value": value, "live": live})
    cs = pd.DataFrame(rows)
    cs.to_csv(FULL / "contract_suppliers.csv", index=False)

    warnings = []
    if len(raw) >= 1000:
        warnings.append(f"raw export has {len(raw)} rows (>= 1,000 download cap): it may be truncated")
    if pub_years:
        lo, hi = min(pub_years), max(pub_years)
        thin = [y for y in range(lo + 1, hi) if pub_years.get(y, 0) < 5]
        if thin:
            warnings.append(f"full publication years with fewer than 5 kept notices: {thin}; "
                            "the export may be incomplete")
    return {"file": rel(CONTRACTS), "sha256": sha256(CONTRACTS), "rows_raw": int(len(raw)),
            "rows_council": int(len(council)),
            "dropped_by_org": dict(sorted(dropped.items(), key=lambda kv: -kv[1])),
            "supplier_rows": int(len(cs)), "live_in_window": len(live_notices),
            "notices_by_publication_year": {str(k): v for k, v in sorted(pub_years.items())},
            "warnings": warnings, "file_out": rel(FULL / "contract_suppliers.csv")}


if __name__ == "__main__":
    main()
