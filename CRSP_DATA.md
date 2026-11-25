# Part B: CRSP panel guide

This is the main guide to the daily inputs and monthly spread panel. Production
code is **Python**. The authors' R functions are used only for validation.
Extraction, cleaning, estimation and coverage reporting have completed locally.
**This is a CRSP-only panel, not yet the paper's CRSP–TAQ matched sample.**

## 1. Start here

- Main analysis files: `DATA_DIR/crsp_daily/monthly/estimates_YYYY.parquet`.
- One row per **PERMNO/calendar month-end**, May 1993–December 2021.
- All **1,711,915 sample-eligible stock-months** are retained, including failures.
- Baseline estimates: `edge`, `ar`, `cs`, `roll`; use `common_sample` for the
  **1,688,307 months** with all four available. Zero is a valid estimate;
  missing is an estimation failure. Do not replace missing values with zero.
- Spreads are **proportions**: `0.01 = 1% = 100 bp`. Multiply by 100 for percent
  or 10,000 for basis points. Market capitalization is in **USD**.
- Daily matching inputs: `clean/daily_YYYY.parquet` and
  `clean/identifier_history.parquet`. Monthly tickers do not describe every day.
- Size inputs are supplied, but paper size deciles/quintiles are **not assigned**.

Paths below use the configured `DATA_DIR` (default `_data`) and `OUTPUT_DIR`
(default `_output`). Dates are fixed in `src/settings.py`; local paths and WRDS
credentials are configured separately.

## 2. Sources, dates and security identifiers

| Decision | Implemented rule | Basis |
|---|---|---|
| Empirical window | May 1, 1993–December 31, 2021; 344 months | Paper §4.1 |
| Lag buffer | Extract April 1993 too; exclude it from all reported coverage and monthly output | Project choice for boundary sensitivity |
| Actual source | WRDS `crsp.dsf` and `crsp.dsenames` | Verified access and completed extraction |
| Source selection | Prefer a complete legacy schema; fall back to complete CIZ; never mix source families within a cache | Project choice; CIZ has not been verified live |
| Universe | Historical share codes 10/11 and exchange codes 1/2/3 (NYSE, AMEX, NASDAQ) | Paper §4.1 |
| Security key | PERMNO; preserve PERMCO but do not aggregate securities by company | Project panel definition |
| History join | Match PERMNO/date within inclusive `namedt`–`nameendt`; no expired identifier carry-forward | Date-valid history |
| History checks | Stop on duplicate daily keys, missing keys, overlapping or reversed history intervals; no silent deduplication | Project integrity checks |
| History dates | Clip join intervals to extraction bounds; retain original source dates as strings | Date-sentinel handling |
| Identifier availability | Preserve historical CUSIP/ticker; missing identifiers are diagnosed, not an additional price filter | Retain inputs for later matching |

The broad daily universe is extracted before applying sample filters locally.
No current-ticker selection or survival-to-2021 condition is imposed.

Legacy field mapping:

| CRSP fields | Saved fields / use |
|---|---|
| `openprc`, `askhi`, `bidlo`, `prc` | `open_raw`, `high_raw`, `low_raw`, `close_raw` |
| `prc` | Also `price_raw`, separately used for size |
| `cfacpr`, `cfacshr` | `price_factor`, `share_factor`; source factors retained unchanged |
| `shrout`, `vol` | `shares_thousands`, `volume` |
| `ncusip`, `ticker`, `shrcd`, `exchcd` | Historical `cusip`, `ticker`, `share_code`, `exchange_code` |

The unused CIZ adapter maps common shares to NS/EQTY/COM, U.S. incorporated,
issuer ACOR/CORP, and eligible exchanges to N/A/Q with RW/A conditions, following
WRDS's legacy-code mapping. It uses transaction `dlyclose`; a BA quote flag is
not accepted as a transaction close. CIZ source cap and flags are retained for
reconciliation if that source is used. See `src/crsp_schema.py` for all aliases.

## 3. Daily cleaning decisions

Apply historical classification, common-share and exchange filters, then:

| Condition | Treatment | Basis |
|---|---|---|
| Negative OHLC price | Set estimator-facing field to missing; never take its absolute value | Paper's quote-price convention |
| Zero or nonfinite OHLC price | Set to missing | Project safeguard for log prices |
| Missing H, L or C | Exclude the daily row from cleaned prices | Paper §4.1 |
| L > H, C outside [L,H], or observed O outside [L,H] | Exclude the daily row | Paper §4.1 |
| Missing O but valid HLC | Retain row, flag missing O; no filling | Preserve HLC information and estimator-specific availability |
| Small number of days | Retain; no arbitrary minimum of 20 or other monthly count cutoff | Paper gives no such screen; estimator computability governs |
| Zero volume | Retain if prices pass; no added positive-volume screen | No corresponding paper screen established |
| Missing CUSIP/ticker or size | Diagnose; do not drop otherwise valid prices | Project choice |

`clean/daily_YYYY.parquet` contains **unadjusted** eligible transaction prices
(`open`, `high`, `low`, `close`), raw fields, factors, historical metadata and
flags. `valid_hlc` identifies retained rows; `valid_ohlc` additionally requires
an open. `in_core` separates April's buffer from the reporting window.
No price filling, dividend reinvestment, winsorization or return-index conversion
is applied. Adjustment happens only in monthly estimation.

Each raw security-day has an audit record. Exclusion flags may overlap;
sequential filter counts assign losses to the first failing stage. Day-count
columns in `stock_month_coverage.parquet` include `n_raw`, `n_sample`, `n_hlc`
and `n_ohlc`. Its universe includes excluded securities; the estimation output
keeps only months with `n_sample > 0`. The coverage file's identifier, quote and
factor diagnostics summarize raw rows, whereas monthly `n_invalid_factors`
counts unusable factors among retained HLC rows.

## 4. Monthly estimation decisions

The baseline and alternatives below are fixed project choices. **Corporate-action,
month-boundary and gap treatment have not been confirmed against the paper's
empirical scripts.** They are documented assumptions, not claims of exact replication.

| Column prefix | Prices | Month boundaries | Missing trading sessions |
|---|---|---|---|
| None (baseline) | Each OHLC field / positive `CFACPR` | All moment inputs within month | Consecutive retained rows; gaps compressed |
| `raw_` | Cleaned unadjusted prices | Within month | Same as baseline |
| `boundary_` | Same as baseline | Up to two retained observations from preceding calendar month supply lags only; moment belongs to ending day's month | Consecutive retained rows |
| `gap_` | Same as baseline | Within month | Suppress moments crossing missing sessions |

Boundary lags never come from an older calendar month and never contribute
extra prior-month moments. The gap calendar is the union of raw CRSP dates;
weekends/holidays are not gaps. One-lag moments require consecutive sessions;
Roll's two-lag moments require both links. Pool surviving moments rather than
averaging estimates from separate uninterrupted segments.

**Unusable factors:** if any retained current-month HLC row has a missing,
nonfinite or nonpositive factor, all adjusted estimates for that month are
missing with status `invalid_price_factor`. Boundary estimates also reject
unusable factors in their supplied context. Do not replace a factor with one,
reconstruct it, or estimate a partial adjusted month. Raw estimates remain
available when otherwise computable. Zero-factor causes remain unverified.

**Estimator conventions:**

- **EDGE:** use Part A's algebra and componentwise missing-data behavior.
  Save signed squared estimate `edge_s2`, signed root `edge_signed`, baseline
  `edge = sqrt(max(edge_s2, 0))`, and sensitivity `edge_abs = sqrt(abs(edge_s2))`.
  Preserve missing inputs/results; missing opens are not filled.
- **Roll:** sample covariance of adjacent log returns (`ddof=1`); at least two
  complete return pairs, hence at least four within-month prices. Negative
  final squared estimates become zero; undefined covariances remain missing.
  This follows the pinned author R function; the paper's three-observation
  statement does not resolve this finite-sample/window detail.
- **Abdi–Ranaldo:** average signed squared contributions, then take the final
  zero-truncated square root. It does not require opens.
- **Corwin–Schultz:** author-style overnight adjustment in log prices; preserve
  original one-day ranges in beta; average signed two-day spreads and truncate
  the final average at zero. Use `2*tanh(alpha/2)` for the spread transformation.
  This is CS, not the CS2 variant that clips each daily contribution. No opens required.

Final zero truncation follows the paper (§2.2). Negative intermediates are saved,
not discarded. Squared fields have **proportion-squared** units; `cs_signed`
is a spread, not a squared spread. Estimated spreads are not capped or winsorized.

Each method has a `*_status` and `*_negative` flag. Status is `ok` or one of
`no_clean_rows`, `invalid_price_factor`, `insufficient_pairs`,
`insufficient_informative_periods`, `missing_open`, `degenerate_prices`,
`nonfinite_moments`. Negative flags alone do not imply computability: check status.
Each variant's `common_sample` requires all four finite estimates. Sensitivity
reports use the intersection of both variants' four-method common samples;
EDGE modulus versus zero uses the baseline common sample. Differences are
alternative minus baseline in bp; the fixed change threshold is 1e-8 in
proportions (0.0001 bp). These comparisons measure convention sensitivity, not accuracy.

## 5. Size and metadata

- `market_cap = abs(price_raw) × shares_thousands × 1,000`, in USD. The absolute
  value is allowed **only for size**, never to turn quote prices into OHLC trades.
  `shares` is the resulting number of shares; `cap_price_is_quote` records quote use.
- `monthly_size.parquet` uses the last observed **sample-eligible** date in each
  month, independently of price-cleaning eligibility. `cap_date` records that date.
  Missing cap on that date stays missing; no substitution of an earlier valid cap.
- Size is left-joined to estimates; missing size does not remove spread estimates.
  `size_available` means finite, positive capitalization.
- Monthly `permco`, `cusip`, `ticker`, `price_raw` and `shares` come from the size
  snapshot. `n_cusips`/`n_tickers` count distinct identifiers in retained daily rows;
  `exchange_code` is their last exchange. Use daily history for date-specific matching.
- `last_observed_size.parquet` saves each security's final size observation within
  our bounded panel. The paper uses last-listing-date size (§4.4–4.5); equivalence
  is unresolved. No monthly rebalanced deciles, post-2021 data or size groups
  have been introduced.

## 6. Files teammates should use

Under `DATA_DIR/crsp_daily/`:

| File | Contents / key |
|---|---|
| `raw/daily_YYYY.parquet`, `raw/identifier_history.parquet` | Original extraction and dated history |
| `raw/schema_inventory.json`, `raw/manifest.json` | Validated schema; source fields, queries, dates, retrieval timestamps and row counts |
| `clean/daily_YYYY.parquet` | Clean transaction inputs and metadata; `(permno, date)` |
| `clean/audit_YYYY.parquet` | Disposition flags for every raw row |
| `clean/identifier_history.parquet` | Validated inclusive identifier intervals |
| `clean/stock_month_coverage.parquet` | Counts before/after filters; `(permno, month)` |
| `clean/monthly_size.parquet`, `clean/last_observed_size.parquet` | Size snapshots described above |
| `monthly/estimates_YYYY.parquet` | All eligible months, baseline/alternative estimates, statuses, intermediates, counts, size and metadata; `(permno, month)` |
| `clean/complete.json`, `monthly/manifest.json`, `monthly/complete.json` | Completion and cache provenance |

Monthly diagnostics also include first/last retained dates, prior-row counts,
within-month gap counts, missing-session counts, boundary gaps and usable
estimator-term counts. `month` is a calendar month-end date even on weekends;
`date` and `cap_date` are actual observation dates.

Under `OUTPUT_DIR/`:

| Directory / files | Purpose |
|---|---|
| `crsp_daily/filter_counts.csv`, `monthly_coverage.csv`, `coverage.pdf`, `coverage_caption.txt` | Sequential daily filtering and CRSP input coverage |
| `crsp_monthly/estimator_coverage.csv`, `failure_reasons.csv` | Method availability, zeros, negative intermediates and failures |
| `crsp_monthly/monthly_coverage.csv`, `estimator_coverage.pdf`, `caption.txt` | Four-estimator coverage through time |
| `crsp_monthly/sensitivity_comparison.csv`, `summary.json` | Convention comparisons and run totals |
| `crsp_monthly/validation.json`, optional `r_validation.json` | Full-panel invariants and sampled R comparison |

`crsp_daily/data_review.json` records the earlier local audit; the ordinary
coverage task does not regenerate it. The optional R check also writes
`r_reference_inputs.csv`, `r_reference_outputs.csv` and `zero_factor_securities.csv`.
All figures here are CRSP-only; none measures CRSP–TAQ matched coverage.

## 7. Completed run and limits

Recorded run: November 24, 2026; 29 annual partitions and all 344 core months.

| Measure | Count |
|---|---:|
| Raw daily rows, including April buffer | 54,800,456 |
| Raw daily rows in core window | 54,648,582 |
| Core rows after common-share / exchange filters | 36,454,060 / 35,714,486 |
| Core rows with transaction HLC / after range checks | 33,948,044 / 33,947,957 |
| Core rows with complete OHLC | 33,900,832 |
| Securities with retained core HLC rows | 16,657 |
| Eligible months / months with at least one HLC day | 1,711,915 / 1,710,485 |
| Months with at least one OHLC day | 1,708,668 |
| Four-method common months: baseline / raw | 1,688,307 / 1,689,311 |
| Four-method common months: boundary / gap | 1,693,080 / 1,657,059 |
| Adjusted baseline months rejected for factors | 1,010 |
| Eligible months with within-month retained-row gaps | 310,326 |
| Monthly size missing / quote-based | 530 / 77,927 |

There are 20,560 retained zero-factor daily rows across 11 securities, six
retained zero-volume rows, and one missing final bounded-panel cap. The 9,401
eligible months with fewer than three OHLC days and 437,667 with fewer than
20 remain in the output universe. At-least-one-day coverage is not estimator coverage.

Completed checks found no duplicate daily/monthly keys, no overlapping/reversed
history intervals, valid retained price ranges, and reconciled filter counts.
The 75,194 historical intervals were validated; retained core rows had no missing
CUSIP/ticker. Full monthly invariants passed. **24 focused tests passed**; a
232-stock-month author-R comparison had maximum absolute signed-spread errors
below 1.24e-15. See [CRSP_MONTHLY.md](CRSP_MONTHLY.md) for validation details.
These checks do not establish TAQ identifier matches or independent vendor agreement.

Paper Table 3 has **1,637,621 matched stock-months** and additional component
estimators; our four-method CRSP common sample is different. TAQ matching,
benchmark accuracy, exact size groups, original empirical window/adjustment
conventions and data-vintage equivalence remain unverified. Whether the authors
filter daily CRSP inputs through TAQ before estimation is also unresolved.
Do not tune our filters to match aggregate table values. The extension and
Part C are outside this implementation; Part A simulations were not rerun.

## 8. Reproduce locally and share through Git

**Git receives code, tests, configuration templates and documentation. Downloaded
CRSP data, cleaned panels, monthly estimates, generated reports and credentials
stay local.** `/_data/*`, `/_output/*` and `.env*` are ignored (the example config
is allowed); no data/output files are currently tracked. Do not force-add them.
If paths are overridden to another directory inside the repo, add that directory
to ignore rules before staging. Git ignore rules do not protect arbitrary paths.

From the repo root, use an environment with `environment.yml` dependencies.
The completed run used the existing `finm` environment; the separately named
project environment has not been tested. Configure your own `WRDS_USERNAME`
and matching `~/.pgpass` entry; neither file belongs in Git. The extractor can
also obtain a username from a matching passfile entry if configuration omits it.

```bash
# Access/schema check only; writes inventory, does not pull the price panel.
python src/pull_crsp_daily.py --check

# Extract, clean, and report daily input coverage.
python -m doit crsp_coverage

# Estimate, validate, and report monthly spreads; reuses up-to-date inputs.
python -m doit crsp_monthly_report
```

The old `pull:crsp_stock` task is separate monthly-data code, not this OHLC pipeline.
All production stages are Python; R is optional for reference validation.
Extraction uses a read-only WRDS session, streaming chunks, annual partitions
and atomic completion. Matching cached partitions are reused after interruption.
Estimation uses saved local prices; it does not query WRDS when inputs are current.
A new teammate without the cache needs WRDS access for the initial pull.

Keep the original raw cache and its manifest. A fresh download can reflect vendor
revisions, so the same code/date window does **not** guarantee identical bytes.
For deliberate refreshes or source changes use a fresh `DATA_DIR`. Resume checks
validate cached row counts; monthly provenance hashes code/metadata and checks
input sizes/mtimes, not every data file's contents. Restricted-session DNS failure
is not evidence of bad credentials; capture the exact error before changing setup.

## Sources

- Local working paper `../ssrn-3892335.pdf`: §2.2 (final truncation), §4.1
  (sample/cleaning, PDF pp. 23–24), §4.4–4.5 (size groups), Table 3 (matched sample).
- [Authors' package](https://github.com/eguidotti/bidask): estimator reference,
  not confirmation of the paper's full empirical preprocessing.
- [Replication archive](https://doi.org/10.7910/DVN/G8DPBM): identified but its
  empirical scripts have not been inspected; implementation assumptions remain explicit.
- [WRDS CIZ-to-SIZ mapping](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/crsp-ciztosiz-macro/)
  and [CRSP cross-reference guide](https://www.crsp.org/wp-content/uploads/guides/CRSP_Cross_Reference_Guide_1.0_to_2.0.pdf).
- Homework references: `../hw1-Weijie-Shen/src/pull_CRSP_stock.py` (dated history)
  and `shared_portfolio_sorts.py` in the same directory (CIZ classification).
  Homework blanket absolute prices, portfolio lags and company aggregation are
  not adopted as spread-cleaning rules.
