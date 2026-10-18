---
name: risk-assessment
description: The method for rating procurement risks for West Berkshire Council. Merge outputs/rules.json, outputs/analytics.json and outputs/history.json into judgments in outputs/risk-ratings.json, then run build_register.py to resolve citations, fill figures, compute scores and bands with the council's own matrix, and render outputs/risk-register.md and the auditor's decision template outputs/auditor-comments.md. Also covers revising the register after the auditor's decisions. Loaded by the risk-assessor.
---

# risk-assessment

You **judge**; `build_register.py` **computes and checks**. You write
`outputs/risk-ratings.json`. The builder turns it into
`outputs/risk-register.md` and `outputs/auditor-comments.md`. You never type a
figure, a score product, a band or a colour: the builder fills those in.

```bash
.venv/bin/python .claude/skills/risk-assessment/build_register.py
```

The builder exits 1 and writes nothing if anything is structurally wrong.
A risk it can't evidence is **dropped** and listed under "Excluded"; that is
not an error, but read why and fix it if you can.

## Inputs (read-only)

| File | What you take from it | How you cite it |
| --- | --- | --- |
| `outputs/rules.json` | testable rules | `[rule:CPR-15]` |
| `outputs/analytics.json` | risk indicators computed by the spend-analyst | `[metric:$.tests.split_purchases.counts.per_tier[?tier==25000].groups]` |
| `outputs/history.json` | audit opinions (AO-), risk themes (RT-), discrepancies (DS-), the council's scoring method | `[history:AO-16]` |

Inspect analytics.json by key, never by dumping: e.g.
`python -c "import json;a=json.load(open('outputs/analytics.json'));print(a['tests']['duplicates']['by_tag'])"`.
Useful paths:
- `$.tests.<test>.status`, `.counts.flagged`, `.gbp_total`
- `$.tests.<test>.by_tag.<tag>.count` and `.gbp`
- `$.tests.threshold_clustering.counts.per_tier[?tier==25000].band_count`,
  `.comparison_count` and `.band_to_comparison_ratio`
- `$.tests.split_purchases.counts.per_tier[?tier==25000].by_tag.general_procurement.count`
- `$.tests.spend_vs_award.counts.eligible`
- `$.tests.high_value_suppliers.counts.by_notice_status.none`
- `$.cleaning.excluded.redacted_supplier.rows`
- `$.window.annualisation_factor`

Tags are `grant`, `care_education_placement`, `agency_staff`, `premises` and
`general_procurement`.

## Writing rules

1. **Citations.** Every likelihood and impact justification cites at least
   one source that resolves: `[rule:ID]`, `[metric:$.path]` or
   `[history:ID]`. **No resolvable citation means the risk is excluded.** A
   metric path must resolve to a single value, not a list or object, in a
   test whose status is `ran`.
2. **Figures are placeholders.** Write `{{$.tests.duplicates.counts.flagged}}`,
   never "689". Write `£{{$.tests.spend_vs_award.gbp_total}}`; the builder
   formats the number and you supply the £. Parameters are placeholders too:
   `{{$.tests.split_purchases.parameters.window_days}}` days. The builder
   warns on any figure typed in prose; aim for zero warnings. Small words
   like "one" or "two" are fine.
3. **Indicator language.** Write "payments just below the £{{…}} tier
   indicate possible avoidance of the quote requirement: to investigate".
   Never "split to evade", "fraud", "non-compliant" or "breach". Never name a
   supplier or an individual.
4. **One risk = one theme** that an auditor could scope as a test area, such
   as threshold avoidance, competition and notices, contract variation and
   extension, duplicate payment, contract register completeness, or care
   placement commissioning. Number risks R-01, R-02, … in the order you
   write them.

## Likelihood rubric (base score)

Choose the **highest row whose conditions are all met**, and write its id in
`likelihood.rubric_row`. Two runs on the same evidence must land on the same
row, so decide on these facts only:
- **"Relevant tag"** means the tags the risk is about (`scope_tags`).
  Care-placement flags don't count for a risk scoped to general procurement,
  and the reverse also holds.
- **"Item-level flags"** means ≥1 flagged item in a relevant tag in
  `threshold_clustering` (with band_count > comparison_count),
  `split_purchases`, `duplicates`, `expired_notice_spend` or
  `spend_vs_award`.
- **"Population-level only"** means the only data is `high_value_suppliers`
  or `off_contract`, which are coverage indicators with known matching
  limits.
- **"Adverse history on the theme"** means an AO- item whose opinion is
  Limited Assurance or Weak, or whose implementation progress is
  Unsatisfactory, in an area that matches the risk's theme. Say in the
  justification why it matches.

| Row | Council label | Conditions |
| --- | --- | --- |
| L1 | Rare | The relevant test(s) ran and flagged nothing in the relevant tags, **and** there is no adverse history on the theme. |
| L2 | Unlikely | Population-level only; **or** item-level flags where the comparison shows no excess (clustering ratio ≤ 1); **or** flags only in tags outside the scope. **And** no adverse history on the theme. |
| L3 | Likely | Item-level flags in a relevant tag; **or** population-level data plus adverse history on the theme. |
| L4 | Almost Certain | Item-level flags in a relevant tag from **two independent tests** on the same theme; **or** item-level flags plus adverse history on the theme. |
| L5 | Certain | Item-level flags in a relevant tag **and** an adverse opinion on this exact area in the **latest** period recorded in history.json. |

Record the history ids you used to reach the row in
`likelihood.base_history`.

**Repeat-finding uplift (+1, capped at 5).** Apply it when the theme was
already the subject of an adverse audit finding, *in addition to* what the
row already counts. Set `likelihood.uplift: 1`, list the AO- ids in
`likelihood.uplift_history` (these must not also be in `base_history`), and
say explicitly in the justification: "Likelihood raised by one point for the
repeat finding in [history:AO-xx]." The builder **rejects the uplift**
unless at least one cited AO- item has an adverse opinion or Unsatisfactory
progress. Reasonable or Substantial Assurance never supports an uplift.

## Impact

Use the council's Table 1 criteria (`history.json` → `scoring_method.impact_scale`):
- **`financial`** (the default whenever a £ figure fits): set `impact.basis`
  to an analytics path giving the £ value exposed, for example the £ of
  flagged items in the relevant tag. The builder computes the band from the
  council's £ figures. Leave `impact.score` null, or the builder replaces it
  and warns. This is value exposed to the risk, not proven loss; say so.
- **`compliance`, `reputation`, `personal`, `assets`**: only when no £ figure
  fits. Give `impact.score` yourself and quote the matching Table 1 wording in
  the justification, e.g. "Reasonable possibility of successful legal
  challenge" = 3.

## Conflicts in the council's method

`history.json` records discrepancies in the scoring method. The builder uses
one value and marks the other, and states both in the register header:
- **Corporate Risk Register escalation:** Table 4 (Extreme 15–25) is used.
  Figure 4's "Score 9 or above" is shown in a separate "CRR alt." column and
  marked ⚠ where only it would escalate.
- **Band names:** both the matrix label and the RAG band are shown; the RAG
  band sets escalation and response.
- **Impact:** the Table 1 scores are used (so Medium = 3, not the "Medium (2)"
  in 4.3). Financial bands use the £ figures, not the overlapping
  percentages.

Never resolve a conflict yourself, and never quietly pick the friendlier
reading.

If `history.json` reports **no usable method** (`scoring_method.status` is
`not_found`), the builder falls back to 1–5 Very low…Very high and states
that in the header. You then give impact scores yourself for every criterion.

## `outputs/risk-ratings.json`

```json
{
  "generated_at": "ISO timestamp",
  "revision": null,
  "risks": [
    {
      "risk_id": "R-01",
      "title": "Payments just below the quote tier",
      "status": "proposed",
      "scope_tags": ["general_procurement"],
      "description": "Text with {{$.path}} placeholders and [rule:…]/[metric:…]/[history:…] tags.",
      "likelihood": {
        "base": 3,
        "rubric_row": "L3",
        "base_history": [],
        "uplift": 0,
        "uplift_history": [],
        "justification": "Why this row, with citations."
      },
      "impact": {
        "criterion": "financial",
        "basis": "$.tests.split_purchases.counts.per_tier[?tier==25000].by_tag.general_procurement.gbp",
        "score": null,
        "justification": "Why this criterion, with citations."
      },
      "evidence": ["[rule:CPR-61]", "[metric:$.tests.split_purchases.counts.per_tier[?tier==25000].groups]"],
      "proposed_focus": "What the audit would test, and which flagged lists in outputs/analytics-full/ to sample from."
    }
  ]
}
```

- `status` is `proposed`, or `rejected` after the auditor rejects the risk.
- `likelihood.base` must equal the number in `rubric_row`, except when an
  auditor Amend sets a different likelihood (see below).
- `scope_tags` must be a subset of the five tags above.

## The auditor gate and revisions

The first build is **revision 0** (`"revision": null`). The builder writes
`outputs/auditor-comments.md`, with one row per rated risk and blank
**Decision** and **Comment** cells. The auditor writes `Approve`, `Reject` or
`Amend` and a comment, and replaces the sign-off line under `## Auditor
notes` with `Reviewer: NAME. Date: YYYY-MM-DD.` A revision **fails without
that line**; the register's header and decisions section are dated from it.
Never write or edit the sign-off line yourself. Decisions already in the
file are kept whenever the builder rewrites it; rows for risks no longer
rated move to a "kept, not applied" table. Everything under `## Auditor
notes` is preserved verbatim.

Once there are decisions, the builder refuses to build without a revision
block. To revise:
1. Read `outputs/auditor-comments.md`.
2. Apply **every** Amend and Reject and **nothing else**:
   - **Reject:** set `status: "rejected"`. The risk stays in the file; the
     register moves it to "Excluded by the auditor" with the comment as the
     reason.
   - **Amend:** change only what the comment asks for.
   - **Amend that sets a score:** the auditor's score wins. For likelihood,
     set `likelihood.base` to the auditor's value and **leave `rubric_row`
     at the row the evidence supports**; the register shows both, flagged
     ⚑. For impact, set `impact.score`; on a financial risk the builder
     keeps it and shows the band the £ figures give. The change entry's
     `field` is `likelihood.base` or `impact.score`. The justification
     still needs a resolvable citation.
   - **Approve:** leave the risk untouched.
   - **A new risk** the auditor asked for in a comment (on any row): add it
     with `field: "risk"` in its change entry and `requested_by` set to the
     row where they asked. Its id is the next number after the highest id
     ever used; ids of dropped or removed risks are never reused.
   - **A risk the builder dropped** (never rated, so never shown to the
     auditor) may be removed without a request. Rated risks are never
     deleted.
   - Decisions applied in an earlier revision stay in the file and count as
     applied; don't re-apply them, and don't undo an auditor-set score.
3. Add the block below:

```json
"revision": {
  "number": 1,
  "summary": "One sentence.",
  "changes": [
    {"risk_id": "R-02", "field": "likelihood.base", "requested_by": "R-02",
     "reason": "Auditor: the 2025/26 Accounts Payable audit already covered duplicates; rate L2."}
  ]
}
```

The builder compares the ratings with the previous build, which it keeps in
`outputs/risk-register-state.json` together with a log of every decision
applied. It **fails** if:
- the sign-off line (reviewer and date) is missing;
- an Amend or Reject has no change entry, in this or an earlier revision;
- a rejected risk isn't `rejected`;
- a risk changed (rating, scope, wording or justification) without a change
  entry backed by an Amend or Reject on that row;
- a change entry describes a change that didn't happen;
- a rated risk was deleted, or a new risk's id is out of sequence or reused.

It writes a "Revision N: what changed" header dated from the sign-off, marks
each changed risk **⚑ auditor override** with the auditor's comment, moves a
rejected risk to "Excluded by the auditor", and ends with the decisions
table: every decision, its comment, and how it was applied.

## Report back

In a few lines:
- the number of risks rated and dropped, with each dropped risk's reason;
- each risk's id, title, score and RAG band, copied from the builder's
  output or register, never computed;
- the method conflicts stated in the header;
- any builder warnings left, and why;
- the next step: the auditor completes `outputs/auditor-comments.md`.
