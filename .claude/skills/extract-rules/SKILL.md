---
name: extract-rules
description: Turn the council's Contract Procedure Rules (data/contract-rules.pdf) into outputs/rules.json, one entry per testable rule with clause, page, thresholds, required action, approver, evidence source and a verbatim quote, plus named parameters, excluded clauses and drafting notes. Use when the user runs /extract-rules or asks to (re)extract the procurement rules.
---

# extract-rules

Read `data/contract-rules.pdf` and write `outputs/rules.json`. Every later step
(spend tests, risk ratings, audit program, QA) takes its criteria from this
file, so it must be exact, complete and checkable against the PDF.

You are reading and classifying text. You are not computing anything and you
are not supplying knowledge the PDF does not contain.

## Hard rules

1. **Quote, don't paraphrase.** `verbatim_quote` is copied character for
   character from the PDF text. Fix nothing: not typos, grammar, odd
   numbering or broken sentences. Those go in `notes`.
2. **Never fill in a value the PDF only names.** "the Threshold", "the
   relevant Threshold" and "Procurement Legislation thresholds" are not printed
   in this PDF; they are on the council intranet. They become entries in
   `parameters` with `"value": null`. Never write the current UK procurement
   thresholds from memory, even if you know them.
3. **Every clause is accounted for.** Each numbered clause and each appendix
   row ends up in `rules` (testable) or `excluded` (with a one-line reason).
   Nothing is silently skipped.
4. **Missing or unreadable PDF → stop and report.** If `pdfinfo` fails, the
   page count differs from what the text extraction shows, or the text is
   empty or garbled (a scanned PDF), stop. Don't guess.
5. **Done means the verifier passes.** Finish only when
   `verify_quotes.py` exits 0. Fix a failing quote by re-copying it from the
   PDF text, never by loosening the wording.

## Steps

### 1. Extract the text

```bash
pdfinfo data/contract-rules.pdf            # note "Pages:"
W=$(mktemp -d)
pdftotext -layout data/contract-rules.pdf "$W/layout.txt"
pdftotext        data/contract-rules.pdf "$W/plain.txt"
```

Pages are separated by form-feed characters (`\f`). The page number used
everywhere in rules.json is the **physical PDF page, starting at 1**. In this
document it matches the number printed in the footer.

- Read the **layout** text in full to understand structure: clause numbering,
  and appendix tables with their columns side by side.
- Copy quotes from the **plain** text. It keeps each table cell's text
  together, whereas layout text interleaves columns line by line. Get a single
  page with `pdftotext -f N -l N data/contract-rules.pdf -`.
- Ignore the footer line on every page (`$3inav0bz.docx  N`).

### 2. Build the clause inventory

List every numbered clause (`4.3`, `7.4.2`, `10.7.9.1`, ...) and every appendix
row before classifying anything. What to expect in this document:

- **Body, pages 1–10:** sections 1–11. Clause numbers sit at the left margin
  or are indented; sub-items such as `4.1.3.1` often start at column 0 in
  layout text.
- **Numbering quirks**, recorded as found, not "corrected":
  - `5.2` and `5.2.1` read like items of the 5.1 Transparency Code list.
  - `6.23` is a heading ("Evaluations of Quotes and Tenders") numbered as a
    clause.
  - `1.6.1` and `1.6.2` follow an unnumbered bullet list.
- **Appendix A, page 11:** delegated authority to award, as four value bands.
  The rows are unlabelled; call them `App A row 1` … `App A row 4`, top to
  bottom.
- **Appendix B, pages 12–13:** financial thresholds and mandatory processes,
  rows `A`, `B1`, `B2`, `C`, `D`. Columns: value band (exclusive of VAT) ·
  award procedure · advertising. Its footnotes (`*`, `**`, `***`, `****`) are
  on page 13.
- **Appendix C, pages 14–15:** exclusions from competition, rows `A`–`F`.
  Columns: circumstance · written record and approval. A closing sentence
  follows on page 15.

Clause IDs in rules.json:

| Source | `clause` value |
| --- | --- |
| Numbered clause | `"7.4.2"` (as printed) |
| Appendix A band | `"App A row 1"` … `"App A row 4"` |
| Appendix B/C row | `"App B row B1"`, `"App C row D"` |
| Appendix footnote | `"App B note ***"` |
| Appendix intro or closing text | `"App B intro"`, `"App C closing"` |

An entry for a parent clause covers its sub-clauses, and the reverse also
holds. Use that to keep `excluded` short, for example one entry for `6.1`
covering 6.1.1–6.1.6. A section number on its own (`"6"`) is never a valid
clause.

### 3. Decide what is testable

A clause is **testable** if an auditor could check a transaction, contract or
record against it. That means it sets at least one of:
- a **value threshold** that triggers a process (quotes, tender, advert, key
  decision, sealing, bond), or
- a **required action** that leaves evidence (a report, approval, notice,
  record, written contract), or
- a named **approver** or decision-maker.

Advisory clauses ("should", "should consider") are still testable when the
action leaves evidence. Set `obligation` to the modal verb as printed.

**Excluded**, each with a one-line reason: legal background (1.1–1.3),
definitions that set no requirement, statements of purpose (section 2), lists
of things that are not obligations, duplicates of another clause (give its
number in the reason), headings, and clauses too vague to test. The reason
says *why*, for example `"definition only; no action, threshold or approver"`
or `"duplicates 7.1"`.

One clause can yield several rules; one rule per distinct test. A table row
with a value band plus a procedure plus an advertising requirement is usually
two rules: one for the award procedure, one for advertising.

### 4. Record thresholds as printed

Each of `threshold_low` and `threshold_high` is either `null` (no bound on
that side) or an object:

```json
{"amount": 25000, "inclusive": true, "as_printed": "£25,000 or more"}
{"parameter": "THRESHOLD_GOODS_SERVICES", "inclusive": false, "as_printed": "less than the Threshold"}
```

- `amount` is a GBP integer: £2.5million → 2500000. If the PDF prints pence,
  for example "more than £24,999.99", keep the exact decimal (24999.99) and
  don't round. `amount` and `parameter` are mutually exclusive.
- `inclusive` follows the wording:

  | Bound | Wording | `inclusive` |
  | --- | --- | --- |
  | Lower | "or more", "at least" | `true` |
  | Lower | "above", "over", "more than", "exceeds", "in excess of" | `false` |
  | Upper | "up to" | `true` |
  | Upper | "less than", "below" | `false` |

- `as_printed` is the exact phrase from the PDF, and it must also appear
  inside `verbatim_quote`.
- If the PDF leaves the band edge unclear, don't decide it. Record the wording
  and add a `notes` entry.

### 5. Declare parameters

Every threshold the PDF names but does not print goes in `parameters`, with
`value: null`, the clause and page where it is defined or referred to, a
description, and a verbatim quote. In this document 1.4 and the Appendix B
`***` footnote say there are **three** thresholds:
- works and concession contracts,
- goods and services,
- light touch contracts.

Declare each one separately; don't merge them into one "Threshold". Where a
clause says only "the Threshold" or "the relevant Threshold" without saying
which, refer to the parameter that matches the rule's `scope`. If the scope
is `all`, add a note that the threshold depends on contract type, and use
`THRESHOLD_RELEVANT` (declared with `value: null`). Parameters are filled in
later from the intranet by a human, not by this skill.

### 6. Write notes: contradictions and drafting gaps

Go through the document deliberately, looking for each of these:
- **Band edges.** Does every value fall in exactly one band? Check each
  appendix table, then compare it with the body clauses on the same subject:
  7.4 against Appendix A, 4.3 against Appendix A, and 7.2 against Appendix B
  row A. A value that sits *exactly* on a boundary such as £500,000, the
  Threshold or £1,000 may fall in no band, or in two.
- **Value basis.** VAT included or excluded; total or annual value. Compare
  6.15 with Appendix B's "exclusive of VAT" and the Appendix C closing
  sentence.
- **Approvers.** Clauses that give the same power to different people, for
  example who may grant waivers in 7.2.2 compared with 7.3.
- **Placeholders and broken text.** `Part []`, `Parts [] (Call-In)`,
  sentences that don't parse, footnote markers that are defined but never
  used or used but never defined.
- **Duplicates and numbering faults.**

Each note gives its `kind` (`contradiction` | `gap` | `drafting` |
`ambiguity`), the clauses and pages involved, and one or two sentences of
plain description. Notes describe the document. They are not findings about
the council's conduct.

### 7. Write the file and verify it

Write `outputs/rules.json`, then run:

```bash
.venv/bin/python .claude/skills/extract-rules/verify_quotes.py \
  outputs/rules.json data/contract-rules.pdf
```

Fix every `ERROR` and re-run until the verifier exits 0. Review each
`WARN`: fix it, or leave it and mention it in your report.

## Output schema: `outputs/rules.json`

```json
{
  "source": {"file": "data/contract-rules.pdf", "page_count": 15},
  "parameters": {
    "THRESHOLD_GOODS_SERVICES": {
      "value": null,
      "defined_in": "1.4",
      "page": 1,
      "description": "Procurement Legislation threshold for goods and services; published on the Procurement intranet page, not in this PDF",
      "verbatim_quote": "exact text from the PDF"
    }
  },
  "rules": [
    {
      "rule_id": "CPR-01",
      "clause": "App B row B1",
      "page": 12,
      "type": "threshold_procedure",
      "scope": ["goods_services"],
      "obligation": "must",
      "condition": "goods/services contract, total value £25,000 up to (not including) the goods & services Threshold, excl. VAT",
      "threshold_low": {"amount": 25000, "inclusive": true, "as_printed": "£25,000 or more"},
      "threshold_high": {"parameter": "THRESHOLD_GOODS_SERVICES", "inclusive": false, "as_printed": "less than the Threshold"},
      "required_action": "send invitations to quote via the Procurement Portal to at least three appropriate sources, incl. one SME/VCSE and one local supplier where appropriate",
      "approver": null,
      "evidence_source": "Procurement Portal RFQ record showing the invitees",
      "verbatim_quote": "£25,000 or more and less than the Threshold [...] Invitations to quote must be sent via the Procurement Portal to at least three appropriate sources"
    }
  ],
  "excluded": [
    {"clause": "1.1", "page": 1, "reason": "statutory background quoting s.135 LGA 1972; no requirement"}
  ],
  "notes": [
    {"kind": "contradiction", "clauses": ["6.15", "App B intro"], "pages": [4, 12], "note": "6.15 says Total Contract Value includes VAT; Appendix B bands are stated exclusive of VAT."}
  ]
}
```

Field rules:

| Field | Rule |
| --- | --- |
| `rule_id` | `CPR-01`, `CPR-02`, … sequential in array order, with no gaps or repeats. Order by document position. |
| `clause`, `page` | Where the quote is. `page` is an integer, or `[n, n+1]` only when the quote crosses a page break. |
| `type` | One of `threshold_procedure`, `advertising`, `approval`, `anti-avoidance`, `exception_waiver`, `valuation`, `documentation`, `contract_terms`, `security`, `sealing`, `governance`. The no-splitting rule (6.16) is `anti-avoidance`; there must be at least one. |
| `scope` | Non-empty list from `all`, `goods_services`, `works`, `concessions`, `light_touch`. |
| `obligation` | `must` \| `shall` \| `should` \| `may` \| `none`, as printed. |
| `condition` | Plain-English trigger for the rule. |
| `required_action` | What must be done. |
| `approver` | Role(s) as printed, e.g. `"S.151 Officer"`, or `null` if none named. |
| `evidence_source` | The record or system an auditor would inspect to test the rule. |
| `verbatim_quote` | Exact PDF text. To join separate cells of one table row, separate fragments with ` [...] ` in reading order. Each fragment must be at least 15 characters. |
| `excluded[].reason` | One line, no line breaks, at most 200 characters. |

## Report back

In a few lines:
- the number of rules, by type
- the number of excluded clauses
- the parameters declared, all null and awaiting values from the intranet
- the notes, each in one line
- any warnings the verifier left

Remind the user that the parameter values must come from the council's
Procurement intranet page before the spend tests can use them.
