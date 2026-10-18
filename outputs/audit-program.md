# Audit program: procurement audit, West Berkshire Council

**Built from risk register revision 6** · auditor decisions by Shivathmika Ramanathan, dated 2026-10-18 · built 2026-10-18T14:32:07 by `.claude/skills/audit-program/build_pack.py`

> Risk indicators to investigate, not findings of wrongdoing. Figures are filled from `outputs/analytics.json` or computed by the builder (see `outputs/pack-figures.json`).


## R-01. Payments grouped just under the quote tiers (general procurement) (score 15, Extreme)

### T-01 · tests C-01, C-02, C-04

**Objective.** Establish whether general-procurement payment groups whose combined value passes the quote tier of £25,000 may indicate one requirement that should have followed the quotation route [metric: `$.tests.split_purchases.counts.per_tier[?tier==25000].by_tag.general_procurement.count`].

**Steps.**
1. For each sampled group, obtain the purchase orders and invoices and establish whether the payments relate to one requirement or to separate requirements [CPR-15].
2. Where the payments relate to one requirement, establish whether its total value was estimated over the full duration [CPR-14] and whether quotes were invited via the Procurement Portal from at least three appropriate sources [CPR-61].
3. Check whether a contract notice was published on the CDP for the requirement [CPR-62].
4. Where the quotation route was not followed, obtain any waiver and check that it was approved in advance and documented [CPR-25] [CPR-29].
5. Establish whether advice on aggregation was sought for repeat or similar purchases [CPR-16].

**Sample.** 25 of 59 flagged groups (379 transactions, £2,149,065.56) → `outputs/samples/T-01.csv`
Recipe: `split_purchases.csv`, filter: tag == general_procurement; tier == 25000; sort: total desc; method: top; population 59 (£3,256,736.03); size rule 25.

**PBC.** P-01, P-02, P-03, P-04, P-05

### T-02 · tests C-02, C-03

**Objective.** Establish whether general-procurement payment groups whose combined value passes the lowest tier of £1,000 were supported by a quote and documented [metric: `$.tests.split_purchases.counts.per_tier[?tier==1000].by_tag.general_procurement.count`].

**Steps.**
1. For each sampled group, obtain the purchase orders and invoices and establish whether the payments relate to one requirement [CPR-15].
2. Where they do, check that at least one quote was obtained from an appropriate source [CPR-60] and that the procedure followed is documented [CPR-35].

**Sample.** 25 of 85 flagged groups (85 transactions, £57,705.75) → `outputs/samples/T-02.csv`
Recipe: `split_purchases.csv`, filter: tag == general_procurement; tier == 1000; sort: total desc; method: systematic; population 85 (£187,888.13); size rule 25.

**PBC.** P-01, P-06

### T-14 · tests C-02, C-03

**Objective.** Establish whether general-procurement single payments just below the lowest tier of £1,000 may indicate part of a larger requirement that needed a quote, given the excess of payments in the band below that tier over the comparison band above it (ratio 1.19) [metric: `$.tests.threshold_clustering.counts.per_tier[?tier==1000].band_to_comparison_ratio`] [metric: `$.tests.threshold_clustering.by_tag.general_procurement.count`].

**Steps.**
1. For each sampled payment, obtain the purchase order and invoice and establish whether it is part of a larger requirement with the same supplier [CPR-15] [CPR-14].
2. Where it is, check that at least one quote was obtained for the requirement [CPR-60] and that the procedure followed is documented [CPR-35].

**Sample.** 25 of 46 payments (25 transactions, £23,893.11) → `outputs/samples/T-14.csv`
Recipe: `threshold_clustering.csv`, filter: tag == general_procurement; tier == 1000; sort: amount desc; method: systematic; population 46 (£43,871.17); size rule 25.

**PBC.** P-01, P-06


## R-02. Grouped payments passing the Key Decision and Executive approval tiers (score 15, Extreme)

### T-03 · tests C-05, C-06

**Objective.** Establish whether general-procurement payment groups whose combined value passes the Executive approval tier of £2,500,000 are covered by an Executive approval for the total value paid [metric: `$.tests.split_purchases.counts.per_tier[?tier==2500000].by_tag.general_procurement.count`]. Groups at the Key Decision tier are tested under T-13.

**Steps.**
1. For each sampled group, obtain the contract under which the payments were made and its total contract value.
2. Obtain the Executive decision approving the award and check that it covers the total value paid [CPR-59].
3. Check that the Key Decision record and written report exist where the total value is above the Key Decision tier [CPR-04] [CPR-58].
4. Where the award was made under delegated authority, check that approval was obtained under Appendix A before award [CPR-05] [CPR-02].
5. Where the payments are staged payments under one approved contract, record this as the explanation of the indicator.

**Sample.** 3 of 3 flagged groups (103 transactions, £9,178,195.87) → `outputs/samples/T-03.csv`
Recipe: `split_purchases.csv`, filter: tag == general_procurement; tier == 2500000; sort: total desc; method: top; population 3 (£9,178,195.87); size rule 25.

**PBC.** P-01, P-07, P-08


## R-03. Possible duplicate payments (general procurement) (score 12, Medium - High)

### T-04 · tests C-07

**Objective.** Establish whether general-procurement payments of the same amount to the same supplier within 7 days each relate to a separate invoice and purchase [metric: `$.tests.duplicates.by_tag.general_procurement.count`].

**Steps.**
1. For each sampled group, obtain the invoice and purchase order behind every payment [CPR-37].
2. Establish whether each payment relates to a separate invoice for a separate supply, or whether one invoice may have been paid more than once.
3. Where a payment may have been made twice, establish whether it was identified and recovered.

**Sample.** 15 of 50 flagged groups (35 transactions, £542,579.56) → `outputs/samples/T-04.csv`
Recipe: `duplicates.csv`, filter: tag == general_procurement; sort: repeat_value desc; method: top; population 50 (£634,682.11); size rule 15.

**PBC.** P-01, P-09

### T-05 · tests C-08

**Objective.** Establish whether Accounts Payable's duplicate-payment check is designed to catch payments of the same amount to the same supplier within a short period [metric: `$.tests.duplicates.counts.flagged`] [CPR-37].

**Steps.**
1. Walk through the duplicate-invoice check in the payment system with Accounts Payable and record how it identifies matching supplier, amount and invoice reference.
2. Obtain the exception report produced by the check for the window and establish how flagged items are cleared.

**Sample.** No sample: Walkthrough of the Accounts Payable duplicate-payment check; transaction testing is in T-04.

**PBC.** P-10


## R-04. Spend after notice expiry or above the awarded value (score 16, Extreme)

### T-06 · tests C-09

**Objective.** Establish whether suppliers paid in the window, whose every matched published notice had ended before it began, are covered by an approved extension or a newer contract [metric: `$.tests.expired_notice_spend.counts.flagged`].

**Steps.**
1. For each sampled supplier, obtain the current contract and its end date.
2. Where the contract was extended, obtain the extension approval and check it was given before the previous end date [CPR-74].
3. Check that the contract register shows the current contract and end date [CPR-08].

**Sample.** 7 of 7 suppliers (53 transactions, £183,352.36) → `outputs/samples/T-06.csv`
Recipe: `expired_notice_spend.csv`, filter: none; sort: total desc; method: top; population 7 (£183,352.36); size rule 25.

**PBC.** P-11, P-12

### T-07 · tests C-10

**Objective.** Establish whether suppliers whose annualised spend is at or above 1.25 times the yearly awarded value are covered by an approved variation [metric: `$.tests.spend_vs_award.counts.flagged`].

**Steps.**
1. For each sampled supplier, obtain the contract, its awarded value and whether that value was an estimate or a maximum [CPR-14].
2. Obtain any variation of scope and check that it had prior written approval, or board approval where the contract value is above the Threshold [CPR-75] [CPR-76].
3. Where no variation exists, establish whether spend above the awarded value may indicate a requirement that needed a new procurement.

**Sample.** 7 of 7 suppliers (30 transactions, £633,768.19) → `outputs/samples/T-07.csv`
Recipe: `spend_vs_award.csv`, filter: flag == True; sort: ratio desc; method: top; population 7 (£633,768.19); size rule 25.

**PBC.** P-07, P-13


## R-05. High-value suppliers with no published contract notice (score 10, Medium - High)

### T-08 · tests C-11, C-12, C-13, C-20

**Objective.** Establish whether the highest-value general-procurement suppliers above the publication threshold with no matched notice are covered by a contract or framework call-off recorded on the Council Contract Register [metric: `$.tests.off_contract.by_tag.general_procurement.count`]. This is a coverage indicator, not evidence that no contract exists.

**Steps.**
1. Before testing, resolve the name candidates in outputs/analytics-full/name_candidates.csv for the sampled suppliers [metric: `$.tests.off_contract.counts.flagged_with_candidates`].
2. For each sampled supplier, obtain the contract or framework call-off under which the payments were made.
3. Check that the contract appears on the Council Contract Register [CPR-40] [CPR-08].
4. Where the total contract value is at or above the publication threshold, check for a CDP contract notice [CPR-62] [CPR-11].
5. Where a framework was used, obtain the advice confirming entitlement and coverage [CPR-32].
6. Where no contract or call-off exists, obtain any waiver or exception and check that it was approved at its value band [CPR-26] [CPR-27].

**Sample.** 15 of 178 suppliers (400 transactions, £20,250,106.60) → `outputs/samples/T-08.csv`
Recipe: `off_contract.csv`, filter: main_tag == general_procurement; sort: total desc; method: top; population 178 (£24,310,816.42); size rule 15.

**PBC.** P-14, P-12, P-03, P-15, P-04


## R-06. Care and education placement commissioning route (score 15, Extreme)

### T-09 · tests C-14, C-15

**Objective.** Establish whether recurring placement payments whose combined value passes the quote tier are made under a recorded commissioning route [metric: `$.tests.split_purchases.counts.per_tier[?tier==25000].by_tag.care_education_placement.count`]. Recurring fees are expected for placements; the test confirms the route, not avoidance.

**Steps.**
1. For each sampled group, establish the commissioning route: Provider Selection Regime, framework or individual placement [CPR-72].
2. Where the Provider Selection Regime applies, obtain the record of key decisions [CPR-72].
3. Where it is an individual placement, inspect the case notes for the placement behind the largest payment in each sampled group, and check that the reasons for the choice of provider are recorded [CPR-77].
4. Where an Appendix C exemption is relied on for a contract above the Threshold, obtain the board approval [CPR-78].

**Sample.** 25 of 221 flagged groups (1608 transactions, £8,460,420.00) → `outputs/samples/T-09.csv`
Recipe: `split_purchases.csv`, filter: tag == care_education_placement; tier == 25000; sort: total desc; method: top; population 221 (£19,641,184.52); size rule 25.

**PBC.** P-16, P-17, P-18

### T-10 · tests C-14

**Objective.** Establish whether placement providers above the publication threshold with no matched notice are covered by a recorded commissioning route, spread across the value range [metric: `$.tests.off_contract.by_tag.care_education_placement.count`] [CPR-72].

**Steps.**
1. For each sampled provider, establish the commissioning route and obtain the PSR decision record, framework call-off or placement agreement [CPR-72].
2. Where a framework was used, obtain the advice confirming entitlement and coverage [CPR-32].

**Sample.** 25 of 311 suppliers (842 transactions, £3,819,151.40) → `outputs/samples/T-10.csv`
Recipe: `off_contract.csv`, filter: main_tag == care_education_placement; sort: total desc; method: systematic; population 311 (£30,418,099.02); size rule 25.

**PBC.** P-16, P-15


## R-07. Agency staff spend passing approval tiers (score 12, Medium - High)

### T-11 · tests C-16, C-17

**Objective.** Establish whether agency staff payment groups that pass an approval tier are covered by a contract or framework and an approval for the total value [metric: `$.tests.split_purchases.by_tag.agency_staff.count`].

**Steps.**
1. For each sampled group, obtain the framework call-off or contract under which the agency staff were engaged and the prior written approval for any award without further competition [CPR-73].
2. Obtain the approval of the total value and check it was given at the Appendix A tier reached [CPR-57] [CPR-58].

**Sample.** 2 of 2 flagged groups (12 transactions, £1,076,284.47) → `outputs/samples/T-11.csv`
Recipe: `split_purchases.csv`, filter: tag == agency_staff; tier == 500000; sort: total desc; method: top; population 2 (£1,076,284.47); size rule 15.

**PBC.** P-14, P-19, P-08

### T-12 · tests C-16

**Objective.** Establish whether the agency staff supplier above the publication threshold with no matched notice is engaged through an approved contract or framework [metric: `$.tests.off_contract.by_tag.agency_staff.count`] [CPR-73].

**Steps.**
1. Obtain the framework call-off or contract and the advice confirming entitlement to use the framework [CPR-32].
2. Check that the arrangement covers the services paid for in the window and that the prior written approval exists [CPR-73].

**Sample.** 1 of 1 suppliers (14 transactions, £1,275,552.15) → `outputs/samples/T-12.csv`
Recipe: `off_contract.csv`, filter: main_tag == agency_staff; sort: total desc; method: top; population 1 (£1,275,552.15); size rule 15.

**PBC.** P-14, P-15


## R-08. Contracts above the Key Decision tier reaching award without the required approval or procedure (general procurement) (score 15, Extreme)

### T-13 · tests C-18, C-19

**Objective.** Establish whether general-procurement payment groups whose combined value passes the Key Decision tier of £500,000 rest on a Key Decision and, for works, a full competitive tender [metric: `$.tests.split_purchases.counts.per_tier[?tier==500000].by_tag.general_procurement.count`].

**Steps.**
1. For each sampled group, obtain the contract under which the payments were made and its total contract value.
2. Obtain the Key Decision record and the written report approved by the relevant board [CPR-04] [CPR-58].
3. For works, concession or light touch contracts, obtain the tender record showing that at least five written tenders were sought via the Procurement Portal and that the opportunity was advertised with information on the CDP [CPR-65] [CPR-67].
4. Obtain the Relevant Threshold in force from Procurement and Commissioning; for goods or services contracts above it, obtain the tender record showing the Procurement Legislation procedure followed [CPR-69].
5. Obtain the written procurement report recording the key decisions [CPR-33].
6. Where an exception was relied on, obtain the recommendation to the Executive and its approval [CPR-28].
7. Where the payments are staged payments under one approved contract, record this as the explanation of the indicator.

**Sample.** 4 of 4 flagged groups (128 transactions, £6,046,162.94) → `outputs/samples/T-13.csv`
Recipe: `split_purchases.csv`, filter: tag == general_procurement; tier == 500000; sort: total desc; method: top; population 4 (£6,046,162.94); size rule 25.

**PBC.** P-01, P-07, P-08, P-20, P-21


## R-10. Possible duplicate payments in care and education placements (score 15, Extreme)

### T-15 · tests C-21, C-22

**Objective.** Establish whether care and education placement payments of the same amount to the same provider within 7 days each relate to a different placement or period [metric: `$.tests.duplicates.by_tag.care_education_placement.count`].

**Steps.**
1. For each sampled group, obtain the invoice behind every payment and the placement record it relates to [CPR-37].
2. For each payment, record the client or placement reference, the invoice number and the period covered, and establish whether each payment relates to a different placement or period.
3. Give particular attention to groups whose payments were all made on the same day, using the payment dates in the sample file.
4. Where a payment may have been made twice, establish whether it was identified and recovered.
5. For each payment that may have been made twice, establish whether the pre-payment duplicate check flagged it, using the exception report obtained in T-16, and how it was cleared [CPR-37].

**Sample.** 25 of 604 flagged groups (241 transactions, £2,878,999.67) → `outputs/samples/T-15.csv`
Recipe: `duplicates.csv`, filter: tag == care_education_placement; sort: repeat_value desc; method: top; population 604 (£7,813,842.33); size rule 25.

**PBC.** P-22, P-23, P-09

### T-16 · tests C-22

**Objective.** Establish whether the duplicate check applied to placement invoices is designed to catch payments of the same amount to the same provider for the same placement and period [metric: `$.tests.duplicates.by_tag.care_education_placement.gbp`] [CPR-37].

**Steps.**
1. Walk through how placement invoices are matched to the placement record and checked for duplicates before payment, with Accounts Payable and the placement teams, and record which fields the check compares.
2. Establish whether the check differs from the general duplicate-invoice check walked through in T-05, and obtain its exception report for the window and how flagged items are cleared.

**Sample.** No sample: Walkthrough of the placement-invoice duplicate check; transaction testing is in T-15.

**PBC.** P-24


## PBC list (prepared by client)

| PBC | Item | Held by | For tests |
|---|---|---|---|
| P-01 | Purchase orders and supplier invoices for each sampled payment | Accounts Payable | T-01, T-02, T-03, T-04, T-13, T-14 |
| P-02 | Quotation or tender record on the Procurement Portal for the requirement, or confirmation that none exists | Procurement and Commissioning | T-01 |
| P-03 | CDP contract notice for the requirement, or confirmation that none was published | Procurement and Commissioning | T-01, T-08 |
| P-04 | Any waiver or exception report covering the requirement, with its approval | Procurement and Commissioning | T-01, T-08 |
| P-05 | Record of advice sought on aggregation of repeat or similar purchases | Procurement and Commissioning | T-01 |
| P-06 | Quote obtained and procurement record for the requirement | Budget-holding service | T-02, T-14 |
| P-07 | Signed contract and its total contract value for each sampled supplier | Legal Services | T-03, T-07, T-13 |
| P-08 | Executive or Key Decision record and the written report approving the award | Democratic Services | T-03, T-11, T-13 |
| P-09 | Record of any duplicate payment identified and its recovery | Accounts Payable | T-04, T-15 |
| P-10 | Description of the duplicate-invoice check and its exception reports for the period | Accounts Payable | T-05 |
| P-11 | Current contract, any extension approval and the contract end date for each sampled supplier | Procurement and Commissioning | T-06 |
| P-12 | Council Contract Register entry for each sampled supplier | Procurement and Commissioning | T-06, T-08 |
| P-13 | Variation approvals and any variation report to the relevant board | Procurement and Commissioning | T-07 |
| P-14 | Contract or framework call-off for each sampled supplier | Procurement and Commissioning | T-08, T-11, T-12 |
| P-15 | Advice confirming entitlement to use the framework or Purchasing Scheme | Procurement and Commissioning | T-08, T-10, T-12 |
| P-16 | Commissioning route record for each sampled placement provider (PSR decision record, framework call-off or placement agreement) | Commissioning (Adult and Children's Social Care, Education) | T-09, T-10 |
| P-17 | Case-note extract recording the reasons for the choice of provider, for individual placements | Social care and SEN case teams | T-09 |
| P-18 | Board approval of any Appendix C exemption applied | Procurement and Commissioning | T-09 |
| P-19 | Prior written approval for an award under a Purchasing Scheme without further competition | Legal Services | T-11 |
| P-20 | Tender record on the Procurement Portal and the written procurement report | Procurement and Commissioning | T-13 |
| P-21 | Relevant Threshold values in force during the period | Procurement and Commissioning | T-13 |
| P-22 | Supplier invoices for each sampled placement payment, showing the client or placement reference and period covered | Accounts Payable | T-15 |
| P-23 | Placement records (placement reference, start date and agreed rate) for each sampled placement payment | Children's and Adult Social Care placement teams | T-15 |
| P-24 | Description of the placement-invoice duplicate check and its exception reports for the period | Accounts Payable | T-16 |
