---
name: revisions-howto
description: How to add auditor-requested new risks in a revision without disturbing existing risks byte-for-byte, and what the builder shows for them
metadata:
  type: feedback
---

- To keep earlier risks byte-identical, back up risk-ratings.json to the scratchpad, append the new
  risks with a script (json.dump indent=2, ensure_ascii=False, plus a trailing newline), then `diff`
  against the backup: the only hunks should be the header/revision block and one pure insertion after
  the last old risk.
- A new risk's change entry uses `field: "risk"`, with `requested_by` set to the row whose **Comment**
  asked for it. A blank Decision cell is fine; the builder only needs a comment on that row.
- A comment like "auditor expects likelihood N" on a new-risk request is not an Amend: rate by the
  rubric and record any difference in the change reason.
- The builder marks new risks "⚑ auditor override" and shows "R-0x ()" when the requesting row has no
  decision. That is how the builder displays them, not a problem in the ratings; mention it in the report.
- Rubric "two independent tests on the same theme" (L4): count two tests only when both detect the same
  pattern (e.g. expired notice and spend over award both mean spend beyond contract cover). Duplicates
  and grouped payments detect different patterns, so they stay L3. Threshold-clustering by_tag figures
  are not broken down by tier, so a band excess can't be shown per tag.
- A breakdown the caller mentions (e.g. same-day vs week-apart duplicate groups) may have no metric in
  analytics.json (duplicates `by_tag` holds only count/gbp). Check it with a pandas aggregate on the
  analytics-full CSV so the wording is true, but describe it in words in the risk and say no metric exists.
- An Approve-only revision (no Amend/Reject/new risk) builds with `"changes": []`. Edit only the revision block
  (and generated_at) with an exact Edit, then diff against a scratchpad backup to confirm the risks are untouched.

Related: [[citation-paths]]
