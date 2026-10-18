# Procurement risk register: West Berkshire Council

**Revision 6** · auditor decisions by Shivathmika Ramanathan, dated 2026-10-18 · built 2026-10-18T14:29:57 by `.claude/skills/risk-assessment/build_register.py`

> Risk indicators to investigate, not findings of wrongdoing. Every figure below is filled from `outputs/analytics.json`; every rating cites a rule, a metric or a history item.

## Method

- Scale: the council's own 5x5 method from the Risk Management Strategy 2024-2027 (recorded in `outputs/history.json` → `scoring_method`). Score = likelihood x impact.
- Likelihood: 1 Rare, 2 Unlikely, 3 Likely, 4 Almost Certain, 5 Certain. Impact: 1 Negligible, 2 Minor, 3 Medium, 4 Major, 5 Critical.
- RAG bands (as printed): Extreme (Red) 15 -25; Medium - High (Amber) 8-12; Moderate 4-6; Low (Green) Up to 3.
- Likelihood base comes from the rubric in the risk-assessment skill; a repeat finding on the same theme adds one point (cap 5) only when it cites an adverse audit opinion.

### Conflicts in the scoring method and how this register handles them

- Financial impact is banded on the £ figures in Table 1 (lower bound of each band; a value exactly on a shared boundary goes to the higher band). The percentage bands are not used: the annual WBC budget is not in the papers [history:DS-02].
- CONFLICT: Corporate Risk Register escalation is Table 4 (Extreme 15-25) in one place and Figure 4 (score 9 or above) in another [history:DS-03]. This register USES Table 4 (Extreme 15-25), the table that also sets the response; the column 'CRR alt.' MARKS risks that would be escalated under Figure 4 (score 9 or above).
- Matrix label (Figure 1) and RAG band (Table 4) are both shown; their names differ for the same scores [history:DS-04]. The RAG band sets escalation and response.
- Impact scores are taken from Table 1 (Medium = 3); the 'Medium (2)' in paragraph 4.3 is not used [history:DS-01].

Other discrepancies recorded on the scoring pages; they do not change how scores, bands or escalation are computed here:

- [DS-05] The evaluation levels are named 'Gross level', 'Actual level' and 'Expected level' in 4.1, but 'Gross risk rating', 'Current risk rating' and 'Expected Net risk rating' in Appendix 2 (Table 4's score column is headed 'Current Score').
- [DS-06] The reputation appetite is stated as 'Open' in 5.10, but the same paragraph's wording 'little chance of significant repercussions' matches the Cautious cell of Table 3; the paragraph also refers to 'an open reputational risk'.
- [DS-07] The risk appetite definition is sourced to 'Risk Appetite Guidance v.2., August2021' in 5.2 (and 5.9) but to 'Risk Appetite Guidance note V1.0, October 2020' in Appendix 2.
- [DS-09] Figure 4 names the body that monitors the Corporate Risk Register six-monthly as the 'Governance and Ethics Committee', while the strategy elsewhere (and the committee papers themselves) name the 'Governance Committee'.

### Inputs

- rules: `outputs/rules.json` sha256 `4b0ec07b1837e59b…`
- analytics: `outputs/analytics.json` sha256 `39ab904e1ea5ad9d…`
- history: `outputs/history.json` sha256 `3d094a00ac8670de…`
- ratings: `outputs/risk-ratings.json` sha256 `612a413d56c5c7a1…`

## Revision 6: what changed

Responds to the auditor decisions in `outputs/auditor-comments.md` by Shivathmika Ramanathan, dated 2026-10-18. Records the auditor's Approve on R-10 with no comment; no risk changes, R-01 to R-08 and R-10 stay approved and unchanged and R-09 stays rejected.

| Risk | Field | Requested by | Auditor comment | Change |
|---|---|---|---|---|

## Summary

| ID | Risk | L | I | Score | Matrix label | RAG band | CRR (used) | CRR alt. (marked) |
|---|---|---|---|---|---|---|---|---|
| R-01 | Payments grouped just under the quote tiers (general procurement) | 3 | 5 | 15 | Extreme | Extreme | yes | yes |
| R-02 | Grouped payments passing the Key Decision and Executive approval tiers | 3 | 5 | 15 | Extreme | Extreme | yes | yes |
| R-03 | Possible duplicate payments (general procurement) | 3 | 4 | 12 | High | Medium - High | no | ⚠ yes |
| R-04 | Spend after notice expiry or above the awarded value | 4 | 4 | 16 | Extreme | Extreme | yes | yes |
| R-05 | High-value suppliers with no published contract notice | 2 | 5 | 10 | High | Medium - High | no | ⚠ yes |
| R-06 | Care and education placement commissioning route | 3 | 5 | 15 | Extreme | Extreme | yes | yes |
| R-07 | Agency staff spend passing approval tiers | 3 | 4 | 12 | High | Medium - High | no | ⚠ yes |
| R-08 | Contracts above the Key Decision tier reaching award without the required approval or procedure (general procurement) | 3 | 5 | 15 | Extreme | Extreme | yes | yes |
| R-10 | Possible duplicate payments in care and education placements | 3 | 5 | 15 | Extreme | Extreme | yes | yes |

*CRR (used)*: Table 4 (Extreme 15-25). *CRR alt.*: Figure 4 (score 9 or above); ⚠ marks a risk that only the alternative would escalate.

## R-01. Payments grouped just under the quote tiers (general procurement)

**Risk.** Repeated payments to the same supplier within 30 days, each below a tier but together passing it, indicate possible division of a requirement that would avoid the quotation route: to investigate. At the £25,000 tier (three quotes via the Portal and a CDP notice, [CPR-61], [CPR-62]) there are 59 general-procurement groups worth £3,256,736.03; at the £1,000 tier (one quote, [CPR-60]) there are 85 groups worth £187,888.13. The Rules prohibit splitting to avoid them ([CPR-15], [CPR-16]). Single payments are not contract values, so these are indicators only.

**Likelihood: 3 (Likely)**, rubric row L3 (base 3). Row L3: item-level flags in the relevant tag, with 151 general-procurement split groups [metric: `$.tests.split_purchases.by_tag.general_procurement.count`] against the anti-splitting rule [CPR-15]. Not L4: threshold clustering is not counted as a second test, because at the £25,000 tier the band holds fewer payments than the comparison band (ratio 0.87), and at the £1,000 tier the excess (ratio 1.19) is not broken down by tag. No adverse audit history on this theme: [AO-01] Contract Letting was Reasonable Assurance, so no uplift.

**Impact: 5 (Critical)**, criterion: financial. Financial: the value exposed is the general-procurement spend in groups passing the quote tier, £3,256,736.03, which falls under [CPR-61]. This is value exposed to the risk, not proven loss.
*Financial band computed from `$.tests.split_purchases.counts.per_tier[?tier==25000].by_tag.general_procurement.gbp` = £3,256,736.03 (value exposed, not proven loss).*

**Score 15**: matrix label Extreme, RAG band Extreme (Red). Escalation: Add to Corporate Risk Register and mitigation action.. Response: Allocate to Executive Director to oversee and Service Director implement agreed actions.

**Evidence.**
- rule: CPR-61 (cl. App B row B1)
- rule: CPR-62 (cl. App B row B1)
- rule: CPR-60 (cl. App B row A)
- rule: CPR-15 (cl. 6.16)
- rule: CPR-16 (cl. 6.17)
- metric: $.tests.split_purchases.by_tag.general_procurement.count = 151
- history: AO-01: Contract Letting, Reasonable Assurance (End of March 2025)
- metric: $.tests.split_purchases.by_tag.general_procurement.gbp = 18,668,982.97

**Proposed focus.** Recommend sampling general-procurement groups at the quote tier from outputs/analytics-full/split_purchases.csv (tag general_procurement). For each group, would test whether the payments are one requirement, whether quotations were sought as the tier requires, and whether advice on aggregation was sought.

## R-02. Grouped payments passing the Key Decision and Executive approval tiers

**Risk.** Payments to one supplier within 30 days, each below an approval tier but together passing it, indicate that a requirement may not have gone through the approval route its total value needs: to investigate. At the £500,000 tier (Key Decision, [CPR-04], [CPR-58]) there are 4 general-procurement groups worth £6,046,162.94. At the £2,500,000 tier (Executive approval, [CPR-59]) there are 3 groups worth £9,178,195.87. These may be staged payments under a properly approved contract.

**Likelihood: 3 (Likely)**, rubric row L3 (base 3). Row L3: item-level split-purchase flags in the relevant tag [metric: `$.tests.split_purchases.by_tag.general_procurement.count`] at the approval tiers of [CPR-58] and [CPR-59]. Not L4: threshold clustering found no payments in the band below either approval tier, so there is only one item-level test. No adverse audit history on approvals: [AO-01] Contract Letting was Reasonable Assurance.

**Impact: 5 (Critical)**, criterion: financial. Financial: the value exposed is the general-procurement spend in groups passing the Executive approval tier of [CPR-59], £9,178,195.87. This is value exposed to the risk, not proven loss.
*Financial band computed from `$.tests.split_purchases.counts.per_tier[?tier==2500000].by_tag.general_procurement.gbp` = £9,178,195.87 (value exposed, not proven loss).*

**Score 15**: matrix label Extreme, RAG band Extreme (Red). Escalation: Add to Corporate Risk Register and mitigation action.. Response: Allocate to Executive Director to oversee and Service Director implement agreed actions.

**Evidence.**
- rule: CPR-04 (cl. 4.3)
- rule: CPR-58 (cl. App A row 3)
- rule: CPR-59 (cl. App A row 4)
- metric: $.tests.split_purchases.by_tag.general_procurement.count = 151
- history: AO-01: Contract Letting, Reasonable Assurance (End of March 2025)
- rule: CPR-15 (cl. 6.16)

**Proposed focus.** Would test every general-procurement group at the two approval tiers in outputs/analytics-full/split_purchases.csv. For each, recommend obtaining the contract and checking that the Key Decision or Executive approval covers the total value paid.

## R-03. Possible duplicate payments (general procurement)

**Risk.** Payments of the same amount to the same supplier within 7 days indicate possible duplicate payment: to investigate. There are 50 general-procurement groups worth £634,682.11, counting every payment in each group. Each purchase should be backed by written evidence [CPR-37]. Care placements dominate this test overall (604 groups) because fixed fees recur, and they are left out of this risk.

**Likelihood: 3 (Likely)**, rubric row L3 (base 3). Row L3: item-level duplicate flags in the relevant tag [metric: `$.tests.duplicates.by_tag.general_procurement.count`], tested against [CPR-37]. No second independent test covers duplicate payment. No adverse history: [AO-15] Accounts Payable was Reasonable Assurance, so no uplift.

**Impact: 4 (Major)**, criterion: financial. Financial: the value exposed is the general-procurement payments in duplicate groups, £634,682.11 [metric: `$.tests.duplicates.by_tag.general_procurement.gbp`]. This includes the first payment of each group, so it overstates any amount paid twice. It is value exposed, not proven loss.
*Financial band computed from `$.tests.duplicates.by_tag.general_procurement.gbp` = £634,682.11 (value exposed, not proven loss).*

**Score 12**: matrix label High, RAG band Medium - High (Amber). Escalation: Seek assurance that identified controls are effective. Response: Allocate to Service Director to put in place Controls Assurance.

**Evidence.**
- rule: CPR-37 (cl. 10.1)
- metric: $.tests.duplicates.by_tag.general_procurement.count = 50
- history: AO-15: Accounts Payable, Reasonable Assurance (End of December 2025)
- metric: $.tests.duplicates.by_tag.general_procurement.gbp = 634,682.11

**Proposed focus.** Recommend sampling general-procurement groups from outputs/analytics-full/duplicates.csv and matching each payment to a separate invoice and purchase order. Would also test the duplicate-payment checks in Accounts Payable.

## R-04. Spend after notice expiry or above the awarded value

**Risk.** Two contract-variation and extension indicators to investigate. First, 7 suppliers were paid £183,352.36 in the window although every matching published notice had ended before it began; an extension needs approval [CPR-74]. Second, 7 of 17 eligible suppliers have annualised spend at or above 1.25 times the yearly awarded value (£633,768.19 spent in the window); a variation needs prior approval ([CPR-75], [CPR-76]). A newer contract, an approved extension or an award stated as an estimate may explain either.

**Likelihood: 4 (Almost Certain)**, rubric row L4 (base 4). Row L4: item-level flags in relevant tags from two independent tests on the same theme. Expired-notice spend flags 5 general-procurement suppliers [metric: `$.tests.expired_notice_spend.by_tag.general_procurement.count`] against [CPR-74]. Spend-versus-award flags 6 [metric: `$.tests.spend_vs_award.by_tag.general_procurement.count`] against [CPR-75]. The tests are independent: one needs every matched notice to have expired, the other needs a live notice. Not L5: there is no adverse audit opinion on contract management, and [AO-01] Contract Letting was Reasonable Assurance.

**Impact: 4 (Major)**, criterion: financial. Financial: the value exposed is the window spend with suppliers whose spend exceeds the awarded rate, £633,768.19 [metric: `$.tests.spend_vs_award.gbp_total`], under [CPR-76]. This is value exposed, not proven loss.
*Financial band computed from `$.tests.spend_vs_award.gbp_total` = £633,768.19 (value exposed, not proven loss).*

**Score 16**: matrix label Extreme, RAG band Extreme (Red). Escalation: Add to Corporate Risk Register and mitigation action.. Response: Allocate to Executive Director to oversee and Service Director implement agreed actions.

**Evidence.**
- rule: CPR-74 (cl. App C row D)
- rule: CPR-75 (cl. App C row E)
- rule: CPR-76 (cl. App C row E)
- metric: $.tests.expired_notice_spend.by_tag.general_procurement.count = 5
- metric: $.tests.spend_vs_award.by_tag.general_procurement.count = 6
- history: AO-01: Contract Letting, Reasonable Assurance (End of March 2025)
- metric: $.tests.spend_vs_award.gbp_total = 633,768.19
- metric: $.tests.expired_notice_spend.counts.flagged = 7
- metric: $.tests.spend_vs_award.counts.flagged = 7

**Proposed focus.** Would test every supplier in outputs/analytics-full/expired_notice_spend.csv and outputs/analytics-full/spend_vs_award.csv. For each, recommend requesting the current contract, any extension or variation approval, and the contract value, and checking them against the approval route in Appendix C.

## R-05. High-value suppliers with no published contract notice

**Risk.** 178 general-procurement suppliers have an annualised estimate above the £25,000 publication threshold but no exact name match to a live notice in the Contracts Finder export (£24,310,816.42 spent in the window). Contracts above this value need a CDP notice [CPR-62] and should be on the contract register ([CPR-08], [CPR-40]). This is a coverage indicator to investigate, not evidence that no contract exists: matching is by exact name only, and frameworks, older contracts and name variants are missed. Results must never be used to question suppliers below the threshold.

**Likelihood: 2 (Unlikely)**, rubric row L2 (base 2). Row L2: population-level data only, from the off-contract coverage test [metric: `$.tests.off_contract.by_tag.general_procurement.count`] and high-value suppliers with no notice [metric: `$.tests.high_value_suppliers.counts.by_notice_status.none`], measured against [CPR-62]. No adverse history on the theme: [AO-01] Contract Letting was Reasonable Assurance, so L3 does not apply.

**Impact: 5 (Critical)**, criterion: financial. Financial: the value exposed is general-procurement window spend with suppliers above the threshold and no matched notice, £24,310,816.42 [metric: `$.tests.off_contract.by_tag.general_procurement.gbp`], under [CPR-62]. This is value exposed, not proven loss, and it is inflated by name-matching limits.
*Financial band computed from `$.tests.off_contract.by_tag.general_procurement.gbp` = £24,310,816.42 (value exposed, not proven loss).*

**Score 10**: matrix label High, RAG band Medium - High (Amber). Escalation: Seek assurance that identified controls are effective. Response: Allocate to Service Director to put in place Controls Assurance.

**Evidence.**
- rule: CPR-62 (cl. App B row B1)
- rule: CPR-08 (cl. 5.2.1)
- rule: CPR-40 (cl. 10.4)
- metric: $.tests.off_contract.by_tag.general_procurement.count = 178
- metric: $.tests.high_value_suppliers.counts.by_notice_status.none = 617
- history: AO-01: Contract Letting, Reasonable Assurance (End of March 2025)
- metric: $.tests.off_contract.by_tag.general_procurement.gbp = 24,310,816.42
- metric: $.tests.off_contract.counts.flagged_with_candidates = 19

**Proposed focus.** Recommend first resolving name candidates in outputs/analytics-full/name_candidates.csv, then sampling the highest-value general-procurement suppliers in outputs/analytics-full/off_contract.csv. For each, would request the contract or framework call-off and check that it appears on the Council Contract Register.

## R-06. Care and education placement commissioning route

**Risk.** Recurring care and education placement payments to the same provider pass the £25,000 quote tier in 221 groups worth £19,641,184.52, and 311 placement providers above the publication threshold have no matched notice. Placements recur by nature and many are made under the Provider Selection Regime or as individual placements [CPR-72], so these indicate a need to confirm the commissioning route, not avoidance. For individual placements the reasons for choosing the provider must be on the case notes [CPR-77].

**Likelihood: 3 (Likely)**, rubric row L3 (base 3). Row L3: item-level split-purchase flags in the relevant tag [metric: `$.tests.split_purchases.by_tag.care_education_placement.count`], measured against [CPR-77]. The off-contract figure is population-level, so it is not a second item-level test. No adverse history on the theme: [AO-18] Purchase of Residential and Nursing Care Provision was Reasonable Assurance. [AO-16] Personal Budgets (Direct Payments) was Limited Assurance, but it covers payments made to families to arrange their own support, not council-commissioned placements, so it is not counted.

**Impact: 5 (Critical)**, criterion: financial. Financial: the value exposed is placement spend in groups passing the quote tier, £19,641,184.52, under [CPR-72]. This is value exposed, not proven loss; most of it is likely to be ordinary recurring fees.
*Financial band computed from `$.tests.split_purchases.counts.per_tier[?tier==25000].by_tag.care_education_placement.gbp` = £19,641,184.52 (value exposed, not proven loss).*

**Score 15**: matrix label Extreme, RAG band Extreme (Red). Escalation: Add to Corporate Risk Register and mitigation action.. Response: Allocate to Executive Director to oversee and Service Director implement agreed actions.

**Evidence.**
- rule: CPR-72 (cl. App C row B)
- rule: CPR-77 (cl. App C row F)
- metric: $.tests.split_purchases.by_tag.care_education_placement.count = 367
- history: AO-18: Purchase of Residential and Nursing Care Provision, Reasonable Assurance (End of December 2025)
- history: AO-16: Personal Budgets (Direct Payments), Limited Assurance (End of December 2025)
- metric: $.tests.off_contract.by_tag.care_education_placement.count = 311

**Proposed focus.** Recommend sampling the highest-value placement providers in outputs/analytics-full/split_purchases.csv and outputs/analytics-full/off_contract.csv (tag care_education_placement). For each, would test that the commissioning route is recorded (framework, PSR decision or individual placement) and that the provider-choice reasons are on the case notes.

## R-07. Agency staff spend passing approval tiers

**Risk.** Agency staff payments to one supplier within 30 days pass a tier in 4 groups worth £1,079,106.78, including the £500,000 Key Decision tier [CPR-58]. The main agency supplier above the publication threshold has no matched notice (1 supplier, £1,275,552.15 in the window). These indicate a need to confirm that agency spend runs through an approved contract or framework [CPR-73]: to investigate.

**Likelihood: 3 (Likely)**, rubric row L3 (base 3). Row L3: item-level split-purchase flags in the relevant tag [metric: `$.tests.split_purchases.by_tag.agency_staff.count`] at the approval tiers of [CPR-58]. The off-contract figure is population-level, so it is not a second item-level test. No audit opinion in history.json covers agency staffing [AO-14], since Recruitment (Talent Attraction) and Retention is a different area, so there is no adverse history and no uplift.

**Impact: 4 (Major)**, criterion: financial. Financial: the value exposed is agency spend in flagged groups, £1,079,106.78 [metric: `$.tests.split_purchases.by_tag.agency_staff.gbp`], under [CPR-58]. This is value exposed, not proven loss.
*Financial band computed from `$.tests.split_purchases.by_tag.agency_staff.gbp` = £1,079,106.78 (value exposed, not proven loss).*

**Score 12**: matrix label High, RAG band Medium - High (Amber). Escalation: Seek assurance that identified controls are effective. Response: Allocate to Service Director to put in place Controls Assurance.

**Evidence.**
- rule: CPR-58 (cl. App A row 3)
- rule: CPR-73 (cl. App C row C)
- metric: $.tests.split_purchases.by_tag.agency_staff.count = 4
- history: AO-14: Recruitment (Talent Attraction) and Retention, Reasonable Assurance (End of December 2025)
- metric: $.tests.split_purchases.by_tag.agency_staff.gbp = 1,079,106.78
- metric: $.tests.off_contract.by_tag.agency_staff.count = 1

**Proposed focus.** Would test the agency-staff groups in outputs/analytics-full/split_purchases.csv and the agency supplier in outputs/analytics-full/off_contract.csv. Recommend requesting the framework call-off or contract and the approval covering the total value.

## R-08. Contracts above the Key Decision tier reaching award without the required approval or procedure (general procurement)

**Risk.** Contracts with a total value above £500,000 must be treated as a Key Decision ([CPR-04], [CPR-58]), and works contracts above that value need a full competitive tender ([CPR-65]). Payments to one supplier within 30 days, each below £500,000 but together passing it, indicate that a requirement may have reached award without that approval or procedure: to investigate. There are 4 general-procurement groups worth £6,046,162.94 at this tier [metric: `$.tests.split_purchases.counts.per_tier[?tier==500000].by_tag.general_procurement.count`]. Overlap with R-02: this evidence is a subset of R-02's, which covers the same tier together with the Executive approval tier; this risk isolates the Key Decision tier at the auditor's request. The groups may be staged payments under a properly approved contract, and a single payment is not a contract value.

**Likelihood: 3 (Likely)**, rubric row L3 (base 3). Row L3: item-level split-purchase flags in the relevant tag at this tier, 4 general-procurement groups [metric: `$.tests.split_purchases.counts.per_tier[?tier==500000].by_tag.general_procurement.count`], measured against [CPR-58]. Not L4: threshold clustering found 0 payments in the band below this tier [metric: `$.tests.threshold_clustering.counts.per_tier[?tier==500000].band_count`] and 0 in the comparison band [metric: `$.tests.threshold_clustering.counts.per_tier[?tier==500000].comparison_count`], so there is no second item-level test. No adverse audit history on awards or approvals: [AO-01] Contract Letting was Reasonable Assurance, so no uplift.

**Impact: 5 (Critical)**, criterion: financial. Financial: the value exposed is the general-procurement spend in groups passing the Key Decision tier of [CPR-04], £6,046,162.94 [metric: `$.tests.split_purchases.counts.per_tier[?tier==500000].by_tag.general_procurement.gbp`]. This is value exposed to the risk, not proven loss, and it is also counted in R-02's evidence.
*Financial band computed from `$.tests.split_purchases.counts.per_tier[?tier==500000].by_tag.general_procurement.gbp` = £6,046,162.94 (value exposed, not proven loss).*

**Score 15**: matrix label Extreme, RAG band Extreme (Red). Escalation: Add to Corporate Risk Register and mitigation action.. Response: Allocate to Executive Director to oversee and Service Director implement agreed actions.

**Evidence.**
- rule: CPR-04 (cl. 4.3)
- rule: CPR-58 (cl. App A row 3)
- rule: CPR-65 (cl. App B row C)
- metric: $.tests.split_purchases.counts.per_tier[?tier==500000].by_tag.general_procurement.count = 4
- metric: $.tests.threshold_clustering.counts.per_tier[?tier==500000].band_count = 0
- metric: $.tests.threshold_clustering.counts.per_tier[?tier==500000].comparison_count = 0
- history: AO-01: Contract Letting, Reasonable Assurance (End of March 2025)
- metric: $.tests.split_purchases.counts.per_tier[?tier==500000].by_tag.general_procurement.gbp = 6,046,162.94
- rule: CPR-15 (cl. 6.16)
- metric: $.tests.split_purchases.counts.per_tier[?tier==500000].groups = 12

**Proposed focus.** Would test every general-procurement group at the Key Decision tier in outputs/analytics-full/split_purchases.csv (tag general_procurement, tier of the Key Decision). For each, recommend obtaining the contract and checking for a Key Decision record covering the total value, and for works, evidence of the full competitive tender. Sample alongside R-02 so the same groups are not tested twice.

## R-10. Possible duplicate payments in care and education placements

**Risk.** Payments of the same amount to the same placement provider within 7 days indicate possible duplicate payment: to investigate. There are 604 care and education placement groups worth £7,813,842.33, counting every payment in each group. Each purchase should be backed by written evidence [CPR-37]. In most of these groups the first and last payment fall on the same day rather than a week apart, so recurring weekly fees do not by themselves explain them; analytics.json has no metric for this split, so it is described here without a figure. Several placements with the same provider at the same rate would also produce this pattern legitimately.

**Likelihood: 3 (Likely)**, rubric row L3 (base 3). Row L3: item-level duplicate flags in the relevant tag [metric: `$.tests.duplicates.by_tag.care_education_placement.count`], tested against [CPR-37]. No second independent test detects duplicate payment, so L4 is not met. No adverse history on the theme: [AO-15] Accounts Payable was Reasonable Assurance. [AO-16] Personal Budgets (Direct Payments) was Limited Assurance, but it covers payments made to families to arrange their own support, not duplicate payment to placement providers, so it is not counted and no uplift applies.

**Impact: 5 (Critical)**, criterion: financial. Financial: the value exposed is the care and education placement payments in duplicate groups, £7,813,842.33 [metric: `$.tests.duplicates.by_tag.care_education_placement.gbp`]. This includes the first payment of each group, so it overstates any amount paid twice, and much of it is likely to be separate placements at the same rate. It is value exposed, not proven loss.
*Financial band computed from `$.tests.duplicates.by_tag.care_education_placement.gbp` = £7,813,842.33 (value exposed, not proven loss).*

**Score 15**: matrix label Extreme, RAG band Extreme (Red). Escalation: Add to Corporate Risk Register and mitigation action.. Response: Allocate to Executive Director to oversee and Service Director implement agreed actions.

**Evidence.**
- rule: CPR-37 (cl. 10.1)
- metric: $.tests.duplicates.by_tag.care_education_placement.count = 604
- history: AO-15: Accounts Payable, Reasonable Assurance (End of December 2025)
- history: AO-16: Personal Budgets (Direct Payments), Limited Assurance (End of December 2025)
- metric: $.tests.duplicates.by_tag.care_education_placement.gbp = 7,813,842.33

**Proposed focus.** Recommend sampling care_education_placement groups from outputs/analytics-full/duplicates.csv, giving weight to same-day groups. For each payment in a sampled group, would test whether it relates to a different placement (client or placement reference, invoice number and period), and would test the Accounts Payable duplicate checks for placement invoices. The commissioning route is covered by R-06 and is not retested here.

## Excluded by the auditor (rejected)

Rated, then rejected at the auditor gate. Not in scope for the audit program.

- R-09 Possible duplicate and grouped grant payments (was 3 x 3 = 9). Auditor's reason: "Grants will be covered by a separate review."

## Auditor decisions

Record a decision for every risk in `outputs/auditor-comments.md` (Approve, Reject or Amend, with a comment for Reject/Amend). The risk-assessor then writes a revision; this builder refuses a revision that leaves a decision unapplied or changes anything the auditor did not ask for.

Decisions by Shivathmika Ramanathan, dated 2026-10-18.

| Risk | Decision | Comment | How applied |
|---|---|---|---|
| R-01 | Approve |  | Approved: kept unchanged (checked against the previous revision) |
| R-02 | Approve | New risk requested: contracts above £500,000 reaching award without the required approval or procedure (general procurement, £500,000 tier). Auditor expects likelihood 3: awards above £500,000 are rare but carry the highest stakes. Decision on R-02 itself still to come. | Approved: kept unchanged (checked against the previous revision); new risk R-08 added at this row's request |
| R-03 | Approve | New risk requested: grant payments, duplicate and grouped payments (grant tag). Decision on R-03 itself still to come. | Approved: kept unchanged (checked against the previous revision); new risk R-09 added at this row's request |
| R-04 | Approve |  | Approved: kept unchanged (checked against the previous revision) |
| R-05 | Approve |  | Approved: kept unchanged (checked against the previous revision) |
| R-06 | Approve | New risk requested (challenge #6): possible duplicate payments in care and education placements (care_education_placement tag in the duplicates test). Most flagged groups were paid on the same day rather than a week apart, so recurring weekly fees do not explain them. Rate it on its own evidence; the test should establish whether each payment relates to a different placement. R-06 itself stays approved and unchanged. | Approved: kept unchanged (checked against the previous revision); new risk R-10 added at this row's request |
| R-07 | Approve |  | Approved: kept unchanged (checked against the previous revision) |
| R-08 | Approve |  | Approved: kept unchanged (checked against the previous revision) |
| R-09 | Reject | Grants will be covered by a separate review. | Rejected in revision 4: moved to Excluded by the auditor, with the reason |
| R-10 | Approve |  | Approved: kept unchanged (checked against the previous revision) |

10 of 10 risks decided; 0 pending.
