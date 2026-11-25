# Part B: monthly implementation and validation

For the **panel definition, every data decision, column meanings, outputs and
reproduction commands**, read [CRSP_DATA.md](CRSP_DATA.md). That is the main
teammate guide. This appendix records implementation and test details.

For confirmed differences in the original formula functions and the choices
used in Part B, see [ESTIMATOR_DECISIONS.md](ESTIMATOR_DECISIONS.md).

## Python production code and Part A integration

| File | Responsibility |
|---|---|
| `src/pull_crsp_daily.py`, `src/crsp_schema.py` | Schema checks, extraction and source mapping |
| `src/clean_crsp_daily.py` | Historical join, cleaning, audits and size snapshots |
| `src/estimate_crsp_monthly.py` | Pack stock-months, build four variants and retain the full eligible universe |
| `src/estimators/monthly_batch.py` | Batched EDGE, AR, CS and Roll calculations |
| `src/validate_crsp_monthly.py` | Full-panel invariants and optional author-R comparison |
| `src/report_crsp_coverage.py`, `src/report_crsp_monthly.py` | Coverage and sensitivity reports |
| `dodo.py` | Dependencies and reproducible task entry points |

Batched calculations avoid millions of scalar Python calls. EDGE uses the local
Part A algebra and is tested against its scalar implementation; AR is also
checked against the local scalar function. Original Part A functions and
simulation code were preserved. Their Roll and CS defaults differ from the
empirical conventions documented in CRSP_DATA.md; this work does not validate
or correct their simulation results. Independent derivation and full Part A
replication remain separate deliverables.

## Reference provenance and checks

Unmodified author R functions and MIT license are stored in
`src/tests/reference_bidask/`, pinned to commit
[`1caba55d63ebab6c855536be51c43bdfc48d2dec`](https://github.com/eguidotti/bidask/tree/1caba55d63ebab6c855536be51c43bdfc48d2dec/r/R).
`PROVENANCE.md` and `generate_monthly_fixture.R` document the synthetic fixtures.
R is a test oracle, not a production dependency.

The completed checks comprise:

- **24 focused tests:** 12 daily-data tests, seven estimator tests and five
  monthly-pipeline tests. Cases cover history, invalid prices, missing opens,
  signed conversions, local scalar agreement, split invariance, boundary
  ownership, gaps, invalid factors, unavailable months and missing size.
- **Full saved monthly panel:** keys, universe, nonnegative final estimates,
  exact signed-to-final transformations, status/availability agreement,
  common-sample flags and invalid-factor handling. All 1,711,915 rows passed.
- **Real-data R comparison:** eight baseline-computable months per year,
  fixed-seed sample of 232. Signed outputs are compared before zero clipping.
  Maximum absolute differences: EDGE 4.44e-16, Roll 3.75e-16, AR 1.24e-15,
  CS 2.50e-16. This checks arithmetic on identical inputs, not the original
  paper's preprocessing, sample or benchmark accuracy.

Signed-root tolerances are `atol=1e-12, rtol=1e-10`. One analytically zero
synthetic EDGE case is ill-conditioned under square-root conversion; its
underlying squared moment is checked against zero at 1e-17 instead. These
choices were fixed during synthetic testing before the empirical comparison.
Offline tests use saved synthetic reference values and require neither R nor
Python `bidask`. Python `bidask` was absent from the `finm` environment; existing
Part A package tests were not counted as passed.

```bash
# Offline focused tests; no WRDS access or price-panel download.
python -m pytest src/tests/test_crsp_daily.py src/tests/test_monthly_estimators.py src/tests/test_crsp_monthly.py -q

# Full-panel checks plus live author-R comparison on saved local inputs.
# This optional command requires Rscript and data.table.
python src/validate_crsp_monthly.py --r-reference
```

Normal full-panel validation is already a dependency of
`python -m doit crsp_monthly_report`. R comparison results are stored separately
in `r_validation.json` with the monthly provenance fingerprint.

## Observed convention sensitivity

These comparisons use the common-sample intersections specified in CRSP_DATA.md.
They are differences between conventions, not errors relative to TAQ.

| EDGE alternative versus baseline | Observed difference |
|---|---|
| Raw prices | 0.55% of paired months change above threshold; mean increase 0.55 bp |
| Prior-month lags | 76.12% change; median absolute difference 4.01 bp |
| Exclude moments across missing sessions | 14.23% change; 95th percentile absolute difference 48.46 bp |
| Modulus instead of final zero truncation | 25.88% change; mean increase 33.66 bp |

Tail differences remain uncapped in `sensitivity_comparison.csv`. A local Apple
split check (PERMNO 14593, August 28–31, 2020) confirmed dividing by CFACPR gave
about $124.81 before and $129.04 after the factor changed from four to one.
This checks adjustment direction for that case; it is not external validation
or an explanation of the 11 securities with zero factors.
