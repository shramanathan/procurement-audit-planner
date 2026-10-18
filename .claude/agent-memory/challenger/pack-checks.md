---
name: pack-checks
description: How-to lessons for challenging the audit planning pack: where to look, which filters to check, and challenge forms the planner acts on quickly
metadata:
  type: feedback
---

Checks that found real weak spots, and challenge forms that landed in one rebuild:

- Check every `not_tested` reason that says "checked under the general controls" against the controls that actually exist. Each risk's tests may lack that step. **Why:** a reason can point to a control that exists only under another risk. **How to apply:** grep the controls for the cited rules, per risk.
- Check split_purchases.csv recipes for a tier filter. A tag-only filter pulls £1,000-tier groups into a test whose objective is about approval tiers. Compare per_tier[...].by_tag counts with the test's drawn count in pack-figures.json `computed`.
- Check whether any test sources threshold_clustering.csv. Its by_tag counts are not broken down per tier; only `counts.per_tier[?tier==X]` carries the band ratio.
- `analytics.json $.thresholds.skipped_tiers` lists the rules whose Relevant Threshold is null. A "threshold null" reason in not_tested is weak when the auditor can get the value as a PBC item.
- In pack-figures.json `computed`, `T-xx.transactions` shows when a few units bring huge transaction counts. That flags test steps that don't say what is inspected per unit.
- Planner-ready form: name the test id and step, give the exact filter JSON or step text, and give one ask. The planner accepted all of these in one round.
- When a builder-side label or unit looks wrong (e.g. sample units mislabelled), report it to the lead rather than challenging the planner; the planner cannot change build_pack.py.
- A design-only walkthrough test ("is designed to catch") leaves the control's operation untested. Ask for the control to be added to the related sample test's control_ids, with a step that uses the walkthrough's exception report. The planner accepted this in one rebuild.
- Before challenging a sort on duplicates.csv, check the field definitions in analytics.json caveats. repeat_value excludes the first payment. A sort challenge built only on reasoning about a column, which the planner can rebut with an aggregate on the CSV, will be declined. Bring an aggregate-backed figure or skip it.
- The QA challenges check accepts only `resolved`, `declined` or `for the auditor` in the Status cell, written exactly. Put qualifiers such as "decided by the auditor" in the response cell or a footnote, never in Status.
