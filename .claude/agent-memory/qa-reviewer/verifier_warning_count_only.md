---
name: verifier-warning-count-only
description: run_checks.py / check_quotes.py print only "verifier: N warning(s) for a human look", never the warning text
metadata:
  type: feedback
---

The quotes check prints only a count of extract-rules verifier warnings (`note verifier: N warning(s) for a human look`). Neither run_checks.py nor check_quotes.py run alone prints the warning text.

**Why:** review.md must pass verifier warnings to the auditor as printed, but the text isn't in the output.

**How to apply:** copy the count line as printed. Under "Points for the auditor", add a concern that the warning text isn't shown and the auditor needs to see it. Never invent the text, and never change the result.
