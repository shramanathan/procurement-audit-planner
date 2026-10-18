# How-to: metric citations vs placeholders

- Filtered paths such as `[metric:$.tests.split_purchases.counts.per_tier[?tier==25000].groups]`
  resolve in citations as well as in placeholders and `impact.basis` (a builder regex bug that cut
  them at the first `]` was fixed on 2026-10-17).
- Don't put a tier-specific £ placeholder next to an all-tier by_tag citation: the two
  figures differ, which misleads. Cite the rule instead, or describe the cited metric as
  the all-tier total.
- Typed-figure check: any 2+ digit number or £digit outside a placeholder or citation
  warns (years too). IDs like CPR-61/AO-16 are safe because of the hyphen.
