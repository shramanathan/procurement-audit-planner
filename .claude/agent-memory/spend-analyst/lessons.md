# spend-analyst: how-to lessons (no evidence here)

- pandas `read_excel(header=None)` keeps leading blank rows, so pandas index i = Excel row i+1.
  clean.py still re-reads the header row with openpyxl to guard that mapping; keep the guard.
- Spend dates load as real datetimes with milliseconds; openpyxl and pandas give identical
  values, so self_check can compare full ISO timestamps, not just dates.
- contracts.csv: `Published Date` is ISO with a UTC offset (use `datetime.fromisoformat`);
  the contract date columns are D/M/Y. Read with `keep_default_na=False` so blank end dates
  stay "" rather than NaN.
- rules.json bounds are dicts (`amount` or `parameter` + `as_printed` + `inclusive`), and
  `threshold_low` is often null (no bound at all) — that is not a skipped tier; only a
  parameter whose `value` is null is.
- The 10.1 written-evidence rule is found by type == documentation, clause == "10.1".
  App C row D / row E rules have type exception_waiver; look them up by clause.
- Name-candidate search over all unmatched spend keys x notice keys with difflib runs in a
  few seconds at this scale; no prefilter needed.
- Group-level full lists (split, duplicates) carry `amounts` and `pay_dates` columns joined
  with ';' so self_check can compare per-row source values against the full list.
