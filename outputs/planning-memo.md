# Planning memo: procurement audit, West Berkshire Council

**Built from risk register revision 6** · auditor decisions by Shivathmika Ramanathan, dated 2026-10-18 · built 2026-10-18T14:32:07 by `.claude/skills/audit-program/build_pack.py`

> Risk indicators to investigate, not findings of wrongdoing. Figures are filled from `outputs/analytics.json` or computed by the builder (see `outputs/pack-figures.json`).

## Objective

To establish whether the controls in the Contract Procedure Rules over quotation and tender routes, approval of total contract value, contract extensions and variations, contract publication, the commissioning of placements and agency staff, and the evidence behind each payment operate as intended, by testing transactions that the full-population analytics flagged as risk indicators to investigate. The results are risk indicators to investigate; they make no finding about the council, any service or any supplier.

## Scope

The pack covers every risk the auditor approved in risk register revision 6 and nothing else. Spend population: 8,526 payments in the window 2026-05-01 to 2026-07-31 after cleaning. Grant payments are out of scope at the auditor's direction and will be covered by a separate review. Groups at the Key Decision tier are tested once, under R-08; R-02 tests the groups at the Executive approval tier, so the same groups are not tested twice. R-10 tests whether same-amount placement payments relate to different placements; the placement commissioning route is tested under R-06 and is not retested under R-10.

Risks in scope (approved at the auditor gate):

| Risk | Title | L x I = Score | RAG band | Decision | Controls | Tests |
|---|---|---|---|---|---|---|
| R-01 | Payments grouped just under the quote tiers (general procurement) | 3 x 5 = 15 | Extreme | Approve | 4 | 3 |
| R-02 | Grouped payments passing the Key Decision and Executive approval tiers | 3 x 5 = 15 | Extreme | Approve | 2 | 1 |
| R-03 | Possible duplicate payments (general procurement) | 3 x 4 = 12 | Medium - High | Approve | 2 | 2 |
| R-04 | Spend after notice expiry or above the awarded value | 4 x 4 = 16 | Extreme | Approve | 2 | 2 |
| R-05 | High-value suppliers with no published contract notice | 2 x 5 = 10 | Medium - High | Approve | 4 | 1 |
| R-06 | Care and education placement commissioning route | 3 x 5 = 15 | Extreme | Approve | 2 | 2 |
| R-07 | Agency staff spend passing approval tiers | 3 x 4 = 12 | Medium - High | Approve | 2 | 2 |
| R-08 | Contracts above the Key Decision tier reaching award without the required approval or procedure (general procurement) | 3 x 5 = 15 | Extreme | Approve | 2 | 1 |
| R-10 | Possible duplicate payments in care and education placements | 3 x 5 = 15 | Extreme | Approve | 2 | 2 |

Out of scope (rejected by the auditor):

- R-09 Possible duplicate and grouped grant payments: "Grants will be covered by a separate review."

## Approach

Risk-led samples are drawn by the builder from the flagged lists in outputs/analytics-full/, sized by each risk's score from the register. Each sampled group or supplier brings all its payments, and every sampled payment is checked against the cleaned spend data. For each sample the auditor obtains the contract, quotations or tender record, approval and register evidence named in the PBC list and establishes whether the expected control operated. Where a control is a process rather than a transaction, the test is a walkthrough with no sample.

Samples are drawn by `build_pack.py` from the flagged lists in `outputs/analytics-full/`, sized by the risk's score (score 15+ → 25; score 8+ → 15; score 4+ → 10; score 1+ → 5 units per test), and every sampled transaction is checked against `spend_clean.csv`.

| Test | Risk | Sample |
|---|---|---|
| T-01 | R-01 | 25 of 59 flagged groups (379 transactions, £2,149,065.56) → `outputs/samples/T-01.csv` |
| T-02 | R-01 | 25 of 85 flagged groups (85 transactions, £57,705.75) → `outputs/samples/T-02.csv` |
| T-14 | R-01 | 25 of 46 payments (25 transactions, £23,893.11) → `outputs/samples/T-14.csv` |
| T-03 | R-02 | 3 of 3 flagged groups (103 transactions, £9,178,195.87) → `outputs/samples/T-03.csv` |
| T-04 | R-03 | 15 of 50 flagged groups (35 transactions, £542,579.56) → `outputs/samples/T-04.csv` |
| T-05 | R-03 | No sample: Walkthrough of the Accounts Payable duplicate-payment check; transaction testing is in T-04. |
| T-06 | R-04 | 7 of 7 suppliers (53 transactions, £183,352.36) → `outputs/samples/T-06.csv` |
| T-07 | R-04 | 7 of 7 suppliers (30 transactions, £633,768.19) → `outputs/samples/T-07.csv` |
| T-08 | R-05 | 15 of 178 suppliers (400 transactions, £20,250,106.60) → `outputs/samples/T-08.csv` |
| T-09 | R-06 | 25 of 221 flagged groups (1608 transactions, £8,460,420.00) → `outputs/samples/T-09.csv` |
| T-10 | R-06 | 25 of 311 suppliers (842 transactions, £3,819,151.40) → `outputs/samples/T-10.csv` |
| T-11 | R-07 | 2 of 2 flagged groups (12 transactions, £1,076,284.47) → `outputs/samples/T-11.csv` |
| T-12 | R-07 | 1 of 1 suppliers (14 transactions, £1,275,552.15) → `outputs/samples/T-12.csv` |
| T-13 | R-08 | 4 of 4 flagged groups (128 transactions, £6,046,162.94) → `outputs/samples/T-13.csv` |
| T-15 | R-10 | 25 of 604 flagged groups (241 transactions, £2,878,999.67) → `outputs/samples/T-15.csv` |
| T-16 | R-10 | No sample: Walkthrough of the placement-invoice duplicate check; transaction testing is in T-15. |

Rule coverage: 39 of 78 rules in `outputs/rules.json` are cited by an approved risk, a control or a test; 39 are listed as not tested, with reasons, in `risk-control-matrix.md`.

## Limitations

Thresholds in the Rules apply to total contract value; single payments, groups within 30 days and annualised estimates (factor 4.00) are proxies, so a flag may be explained by staged payments under an approved contract. Contract matching method: exact normalised name only; name candidates are not counted as matches, and frameworks, older contracts and name variants are missed. Contracts Finder holds only notices above the publication threshold, so results must never be used to question smaller suppliers. Payments with a redacted supplier were removed from the population (2,015 rows) and cannot be sampled. The Relevant Threshold under the Procurement Legislation is not set in rules.json, so no sample is drawn at it; T-13 asks Procurement and Commissioning for the value in force. The duplicates list has no field marking groups paid on a single day, so the R-10 sample is drawn by the value that may have been paid more than once, not filtered to same-day groups; the payment dates of every sampled payment are in its sample file. Placement providers with several placements at the same rate will produce legitimate groups.

