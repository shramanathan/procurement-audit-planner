# QA review: audit planning pack

Pack v5 · register revision 6 · final check run 2026-10-18T14:33:44 · qa-reviewer

## Verdict: READY FOR SIGN-OFF

All five checks passed on the final run.

## Final check results (as printed)

```
QA checks on outputs/ · run 2026-10-18T14:33:44

| Check | Result | Checked | Failures |
|---|---|---|---|
| quotes | PASS | 144 quotes and rule references | 0 |
| numbers | PASS | 87 figures | 0 |
| trace | PASS | 97 rules and risks | 0 |
| challenges | PASS | 8 challenges | 0 |
| samples | PASS | 3955 transactions | 0 |

quotes:
  note verifier: 1 warning(s) for a human look
  note verifier checked 78 rule quotes
  note register: 66 rule reference(s), 0 quoted excerpt(s)

numbers:
  note source values: analytics.json 637, pack-figures.json 140, rules.json 283, samples/*.csv 3955

trace:
  note rules: 18 cited by rated risks, 39 by controls/tests, 39 not tested
  note risks: 9 in scope, 1 rejected, 10 High or Extreme

samples:
  note 3955 sampled transaction(s) in 14 file(s); 0 row ID(s) quoted in audit-program.md; 2726 workbook row(s) read

VERDICT: ALL CHECKS PASS (5 of 5)
```

Exit code: 0.

## Check history

| Version | Run | Verdict line |
| --- | --- | --- |
| v1 | 2026-10-18T14:15:06 (--pack-only) | VERDICT: PACK CHECKS PASS (4 of 4; challenges not checked) |
| v2 | 2026-10-18T14:17:39 (--pack-only) | VERDICT: PACK CHECKS PASS (4 of 4; challenges not checked) |
| v2 | 2026-10-18T14:18:18 (final; superseded by v3) | VERDICT: ALL CHECKS PASS (5 of 5) |
| v3 | 2026-10-18T14:24:06 (--pack-only) | VERDICT: PACK CHECKS PASS (4 of 4; challenges not checked) |
| v3 | 2026-10-18T14:24:32 (final; superseded by register revision 6) | VERDICT: ALL CHECKS PASS (5 of 5) |
| v4 | 2026-10-18T14:31:27 (--pack-only) | VERDICT: PACK CHECKS PASS (4 of 4; challenges not checked) |
| v5 | 2026-10-18T14:32:20 (--pack-only) | VERDICT: PACK CHECKS PASS (4 of 4; challenges not checked) |
| v5 | 2026-10-18T14:32:57 (final; BLOCKED) | VERDICT: FAIL (1 of 5 checks failed: challenges) |
| v5 | 2026-10-18T14:33:44 (final, re-run on the lead's instruction after the challenger corrected #6's status cell; pack unchanged) | VERDICT: ALL CHECKS PASS (5 of 5) |

The BLOCKED run printed: `FAIL #6: status 'resolved (decided by the auditor)' is not one of resolved, declined, for the auditor`.

## Points for the auditor

- **Challenges marked *for the auditor*:** none. `outputs/challenges.md` reads: "7 resolved · 1 declined · 0 for the auditor · 0 open." Its "For the auditor" section also says: "The auditor may wish to note #7 (declined): T-15 draws by repeat_value rather than by amount, and the planner gave the reason in footnote ²."
- **Verifier warning:** the check output prints only `note verifier: 1 warning(s) for a human look`. The lead looked up the warning text: "WARN [App A] rows are unlabelled in the PDF; confirm by eye that every band is covered".
- **Concern about a check:** `run_checks.py` and `check_quotes.py` print only the count of verifier warnings, not the warning text. That is why the text above came from the lead and not from the check output. This is a concern about the output only; the quotes result stands as printed (PASS).

## Auditor sign-off

- [x] I have read planning-memo.md, risk-control-matrix.md, audit-program.md and challenges.md.
- [x] I have decided each challenge marked *for the auditor*.
- [x] I accept the samples in outputs/samples/ as the basis for fieldwork.

Decision: Signed off
Reviewer: Shivathmika Ramanathan. Date: 2026-10-18.
Comments: Signed off on pack v5 (register revision 6). Challenge #6 was decided by bringing care-placement duplicate payments into scope as R-10. Recorded by Claude at the reviewer's instruction.
