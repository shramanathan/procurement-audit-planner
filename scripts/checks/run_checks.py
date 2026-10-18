#!/usr/bin/env python3
"""Run every QA check on the audit planning pack and print one table and a verdict.

Checks: quotes, numbers, trace, challenges (both from check_trace.py) and
samples. Every failure is listed in full under the table. The verdict is
ALL CHECKS PASS only when every check passes.

--pack-only leaves out the challenges check, for runs while the challenger
is still working; the output says so, and its verdict covers the pack only.
The final run for review.md must be without it.

Usage: run_checks.py [--pack-only] [--out-dir outputs] [path options as in each check]
Exit 0 if every check run passed, 1 otherwise.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_numbers  # noqa: E402
import check_quotes  # noqa: E402
import check_samples  # noqa: E402
import check_trace  # noqa: E402
from _common import Result, add_path_args, paths  # noqa: E402


def safe(name: str, fn, p) -> list[Result]:
    """A check that crashes is a failed check, never a skipped one."""
    try:
        out = fn(p)
        return out if isinstance(out, list) else [out]
    except Exception as e:  # noqa: BLE001
        r = Result(name)
        r.fail(f"check crashed: {type(e).__name__}: {e}")
        return [r]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_path_args(ap)
    ap.add_argument("--pack-only", action="store_true", help="leave out the challenges check")
    args = ap.parse_args()
    p = paths(args)

    results = []
    results += safe("quotes", check_quotes.run, p)
    results += safe("numbers", check_numbers.run, p)
    trace = safe("trace", check_trace.run, p)
    results += [r for r in trace if not (args.pack_only and r.check == "challenges")]
    results += safe("samples", check_samples.run, p)

    print(f"QA checks on {p['out']}/ · run {dt.datetime.now().isoformat(timespec='seconds')}"
          + (" · pack only (challenges not checked)" if args.pack_only else ""))
    print()
    print("| Check | Result | Checked | Failures |")
    print("|---|---|---|---|")
    for r in results:
        print(f"| {r.check} | {r.status} | {r.checked} {r.what} | {len(r.failures)} |")
    for r in results:
        if r.failures or r.notes:
            print(f"\n{r.check}:")
        for f in r.failures:
            print(f"  FAIL {f}")
        for n in r.notes:
            print(f"  note {n}")
    failed = [r.check for r in results if r.failures]
    print()
    if failed:
        print(f"VERDICT: FAIL ({len(failed)} of {len(results)} checks failed: {', '.join(failed)})")
    elif args.pack_only:
        print(f"VERDICT: PACK CHECKS PASS ({len(results)} of {len(results)}; challenges not checked)")
    else:
        print(f"VERDICT: ALL CHECKS PASS ({len(results)} of {len(results)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
