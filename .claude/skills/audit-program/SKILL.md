---
name: audit-program
description: The method for turning the auditor-approved risk register into the audit planning pack for West Berkshire Council procurement. Write expected controls, test steps, sample recipes and PBC items to outputs/audit-plan.json, then run build_pack.py to check the auditor gate, resolve citations, draw samples from outputs/analytics-full/ deterministically, verify every sampled transaction, and render planning-memo.md, risk-control-matrix.md, audit-program.md, outputs/samples/ and pack-figures.json. Loaded by the planner.
---

# audit-program

You **judge**; `build_pack.py` **computes and checks**. You write
`outputs/audit-plan.json`. The builder turns it into the pack. You never
type a figure, choose sample rows, or write the documents by hand.

```bash
.venv/bin/python .claude/skills/audit-program/build_pack.py --gate   # gate only, writes nothing
.venv/bin/python .claude/skills/audit-program/build_pack.py          # gate + full build
```

Exit 1 means nothing was written. Fix the cause in `audit-plan.json`.
Never edit the inputs or this skill.

## The gate (checked first, every time)

The pack covers only risks the auditor has decided. The gate fails, and so
does the build, if:
- a register risk has no row in `outputs/auditor-comments.md`, or its
  Decision is blank, or the file has a row for a risk not in the register;
- the register is not a revision, or `risk-ratings.json` changed after the
  register was built;
- a decision in `auditor-comments.md` differs from the one the register was
  built with, meaning someone changed it after the last revision;
- the sign-off line (`Reviewer: NAME. Date: YYYY-MM-DD.`) is missing.

**Approved scope** is every risk decided Approve or Amend. A Reject is out
of scope and must not appear in the plan. Scores and bands come from the
register's summary table; never re-score.

If the gate is closed, stop and report. The auditor and the risk-assessor
fix it, not you.

## Inputs (read-only)

| File | Use |
| --- | --- |
| `outputs/risk-register.md`, `outputs/risk-ratings.json` | the approved risks, their evidence and proposed focus |
| `outputs/rules.json` | controls and tests cite rules: `[rule:CPR-37]` |
| `outputs/analytics.json` | metrics: `[metric:$.tests.duplicates.by_tag.general_procurement.count]`, figures: `{{$.path}}` |
| `outputs/analytics-full/*.csv` | sample sources. Inspect with `head -3` and aggregates only; never print them |

## Writing rules

1. **Every expected control cites ≥1 rule** (`[rule:ID]`) that it rests on.
2. **Every test cites ≥1 rule or metric** in its objective or steps, and
   tests ≥1 control of the same risk. **Every control has ≥1 test.**
3. **Every citation and placeholder must resolve**: an unresolved one is
   an error, not a warning.
4. **Figures are `{{$.path}}` placeholders** into `analytics.json`, never
   typed. The builder warns on typed figures; aim for zero warnings.
   Sample counts and £ totals are computed by the builder and appear in
   the documents on their own; don't write them.
5. **Indicator language.** "Indicator to investigate", "may indicate",
   "establish whether". Words like fraud, breach, non-compliant,
   wrongdoing, evade or deliberate fail the build.
6. **No supplier names** in any text you write. Multi-word names match in
   any case; one-word names match when written as a proper noun. Suppliers
   appear only in `outputs/samples/*.csv`, which the auditor needs.
7. **Rule coverage.** Every rule in `rules.json` must be cited by an
   approved risk, a control or a test, or be listed in `not_tested` with a
   one-line reason, e.g. "Sealing of contracts: not linked to an approved
   risk" or "Tender records fall outside the spend window". Don't cite a
   rule just to tick it off; a citation must be the basis of the control
   or test.

## Samples

Each test names a **recipe**; the builder draws it.

```json
"sample": {
  "source": "duplicates.csv",
  "filter": [{"col": "tag", "op": "==", "value": "general_procurement"}],
  "sort":   [{"col": "repeat_value", "desc": true}],
  "method": "top"
}
```

- **source**: a CSV in `outputs/analytics-full/` with `row_id` or
  `row_ids`:

  | File | Unit | Useful columns |
  | --- | --- | --- |
  | `threshold_clustering.csv` | payment (`row_id`) | tier, amount, tag, service |
  | `split_purchases.csv` | flagged group (`group_id`) | tier, n, total, tag |
  | `duplicates.csv` | flagged group (`group_id`) | amount, n, total, repeat_value, tag |
  | `expired_notice_spend.csv` | supplier | total, annualised_estimate, main_tag, latest_end |
  | `spend_vs_award.csv`, `spend_vs_award_population.csv` | supplier | ratio, flag, awarded_value, main_tag |
  | `off_contract.csv`, `high_value_suppliers.csv` | supplier | total, annualised_estimate, main_tag, notice_status / indicator |
  | `spend_clean.csv` | payment | amount, tag, service, category |

  Don't use `exclusions.csv`: those rows were removed from the population.
- **filter**: a list of `{col, op, value}`, all of which must hold. Ops are
  `== != in not_in > >= < <= contains`.
- **sort**: a list of `{col, desc}`. Ties are broken by the unit id, so the
  order is always the same.
- **method**:
  - `top`: the first N after sorting. Use it for risk-led samples.
  - `systematic`: every k-th after sorting. Use it to spread a sample
    across a range.
  - `seeded_random`: a random draw seeded from the test id.

  All three give the same rows every run.
- **Size is set by the risk's score**, not by you:

  | Score | Units per test |
  | --- | --- |
  | 15–25 | 25 |
  | 8–12 | 15 |
  | 4–6 | 10 |
  | 1–3 | 5 |

  The builder takes everything when the population is smaller. A unit
  (group or supplier) brings all its transactions, so filter supplier-level
  sources with care: one large supplier can mean many payments.
- The builder expands each unit to its transactions, checks every one exists
  in `spend_clean.csv` with the same amount, and writes
  `outputs/samples/<test_id>.csv`. A missing or mismatched transaction is an
  error.
- **No sample** (e.g. a walkthrough of a control) needs `"sample": null`
  and a `no_sample_reason`.

## `outputs/audit-plan.json`

```json
{
  "generated_at": "ISO timestamp",
  "memo": {
    "objective": "…", "scope_note": "…", "approach": "…", "limitations": "…"
  },
  "risks": [
    {
      "risk_id": "R-03",
      "controls": [
        {"control_id": "C-01", "description": "Each payment is supported by written evidence of the purchase… [rule:CPR-37]"}
      ],
      "tests": [
        {
          "test_id": "T-01",
          "control_ids": ["C-01"],
          "objective": "Establish whether … [metric:$.tests.duplicates.by_tag.general_procurement.count]",
          "steps": ["For each sampled group, obtain … [rule:CPR-37]", "…"],
          "sample": { "source": "duplicates.csv", "filter": [], "sort": [], "method": "top" },
          "pbc": [{"item": "Purchase order and supplier invoice for each sampled payment", "held_by": "Accounts Payable"}]
        }
      ]
    }
  ],
  "not_tested": [{"rule_id": "CPR-36", "reason": "…"}]
}
```

- Ids run C-01, C-02, … and T-01, T-02, … across the whole plan. Sample
  files are named after the test id.
- `pbc`: what the auditee must provide for this test, and who holds it
  (a role, never a person). The builder merges identical items into one
  numbered PBC list at the end of `audit-program.md`.
- The memo's four parts are short prose with placeholders; the builder adds
  the scope table, the sample table, rule coverage and the out-of-scope
  list.
- Use each risk's `proposed_focus` in the register as the starting point
  for its tests.

## What the builder writes

- **`planning-memo.md`**: objective, scope (approved risks with score and
  band; rejected risks with the auditor's reason), approach and sample
  table, rule coverage, limitations.
- **`risk-control-matrix.md`**: risk → control → rules → tests, then the
  rules not tested, with reasons.
- **`audit-program.md`**: per risk and test: objective, steps, sample recipe
  and result, PBC references; it ends with the PBC list.
- **`outputs/samples/T-*.csv`**: one row per sampled transaction.
- **`pack-figures.json`**: every figure the builder computed (population,
  population £, size rule, units drawn, transactions, sample £ per test;
  counts), copied from the register (L, I, score, band) or filled from
  `analytics.json` (each placeholder, with where it was used). This is for
  the QA number check.

## Report back

In a few lines, copying figures from the builder output or the documents:
- the gate result and the builder result line;
- risks in scope, controls, tests, sample files and transactions;
- the rules not tested and why, in one line;
- any warnings left, and why;
- `PACK READY v<N>` when it passes (the team protocol in CLAUDE.md).
