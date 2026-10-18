---
name: builder-lessons
description: build_pack.py quirks: typed-figure check, unit labels for threshold_clustering, accusatory word list, care-placement sample volume
metadata:
  type: feedback
---

- Typed-figure warnings fire on any number with 2 or more digits, any £-digit and any percentage. Write tiers as `£{{$.thresholds.tiers[i].amount}}` and day windows as `{{$.tests.split_purchases.parameters.window_days}}` / `{{$.tests.duplicates.parameters.days}}`. Rule IDs like CPR-37 are safe.
- The accusatory-word list includes "wrongdoing", even when it is negated ("not findings of wrongdoing"). Use "risk indicators to investigate" instead.
- Unit column priority is now row_id > group_id > supplier_key (builder fixed 2026-10-18; earlier, threshold_clustering samples were mislabelled "suppliers"). If a unit label looks wrong, report it to the lead; never work around it.
- `{{$.matching.method}}` already reads "exact normalised name only", so don't repeat that phrase around it.
- Supplier-level and care-placement sources bring a lot of transactions (one provider can bring hundreds). For a second test on an overlapping population, use `systematic` to spread it across the value range.
- Sample filters compare a column with a constant only, never two columns. duplicates.csv has first_date/last_date but no same-day flag, so "weight to same-day groups" can't be a filter. Sort by repeat_value (it tends to favour them anyway) and say so in limitations.
- spend_vs_award.csv `flag` is the string "True"; filter it with `"value": "True"`.

**Why:** these cost a rebuild or a challenge round.
**How to apply:** check them before the first build.
