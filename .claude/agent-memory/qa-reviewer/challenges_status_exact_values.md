---
name: challenges-status-exact-values
description: challenges check fails any status that isn't exactly resolved / declined / for the auditor, even annotated variants
metadata:
  type: feedback
---

The challenges check fails with `FAIL #N: status '<text>' is not one of resolved, declined, for the auditor` when a status cell has extra wording, such as "resolved (decided by the auditor)". The summary line can still say "0 for the auditor · 0 open".

**Why:** it compares status values exactly, and `--pack-only` runs never test challenges.md, so this shows up only on the final run.

**How to apply:** report it as printed to `challenger` (step 2 format) and to the lead in QA DONE ... BLOCKED (challenges). Never treat it as cosmetic.
