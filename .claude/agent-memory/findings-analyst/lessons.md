# findings-analyst: how-to lessons (no evidence)

- Dump every page once to scratchpad in both modes (`pdftotext -f N -l N [-layout]`); work from the files.
- The verifier normalises whitespace (incl. newlines), dashes and quotes, and drops bullets. So a whole
  layout-text table row, joined across lines, is usually one quotable string; wrapped cell
  continuations that fall on the next line can be appended directly if nothing intervenes.
- Plain text emits tables column by column. That works for `[...]` fragment quotes across columns
  of one row (e.g. impact Table 1), as long as the fragments are in reading order and each is >= 8 chars.
- Short wrapped words ("given") can't be a fragment on their own (min 8 chars). Quote the joined line instead.
- Plain text sometimes drops dashes that layout shows (e.g. range cells "0.01% -"). Check both modes.
- Plain text drops the hyphen in some table labels ("Medium High"); layout keeps "Medium -".
- Risk strategy: printed page number == physical PDF page (cover pages are numbered too).
- Matrix trap: in layout mode the band labels sit on the line above each impact row and the scores on the line below.
- Building JSON from a Python script in scratchpad (with mechanical keyword_hits/ids/sha256) passed the verifier first time.
