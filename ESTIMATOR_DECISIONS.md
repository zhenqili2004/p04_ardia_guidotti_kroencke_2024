# Estimator functions: issues and current choices

This note explains which formula functions Part B uses, why it does not call
every original Part A function unchanged, and what still needs review.
For the data panel and cleaning rules, see [CRSP_DATA.md](CRSP_DATA.md).
For validation commands and reference provenance, see
[CRSP_MONTHLY.md](CRSP_MONTHLY.md).

**Current position:** the four core monthly estimators are implemented in
Python and have passed the recorded checks. Their arithmetic agrees with the
pinned authors' R functions on tested inputs. Original Part A functions and
simulations remain unchanged; some of their defaults differ from the paper's
conventions and our monthly implementation. Exact empirical replication is
not yet established.

## 1. Which implementation should teammates use?

| Purpose | Implementation | Current role |
|---|---|---|
| Build the empirical monthly panel | `src/estimate_crsp_monthly.py` using `src/estimators/monthly_batch.py` | Part B production path |
| Original scalar functions and simulations | `src/estimators/edge.py`, `roll.py`, `corwin_schultz.py`, `abdi_ranaldo.py`; `src/simulations/monte_carlo.py` | Preserved Part A code; review the differences below before reusing defaults |
| Check calculations against authors | Pinned R files in `src/tests/reference_bidask/` | Test reference only; not used for production estimates |

The batch interface is `estimate_batch(prices, current, boundary=False,
adjacent=None)`. Prices have shape `(groups, observations, 4)` in **O,H,L,C**
order, sorted by date within each group. `current` marks the target month's
rows; optional preceding rows supply context only. The function returns arrays
of estimates, signed intermediates, usable-term counts, status codes and a
four-estimator common-sample flag.

Use the monthly pipeline to prepare these inputs rather than passing an
unfiltered CRSP array directly. All spread outputs are proportions:
`0.01 = 1% = 100 bp`. Squared-spread fields have proportion-squared units.

## 2. Confirmed differences and our decisions

### EDGE: absolute value versus final zero truncation

The original local `edge(..., sign=False)` returns `sqrt(abs(s2))`. The signed
option returns `sign(s2) * sqrt(abs(s2))`. Thus, the default turns a negative
squared-spread estimate into a positive spread. That is different from the
paper's final zero-truncation convention (§2.2).

Part B retains all three representations:

| Field | Definition | Use |
|---|---|---|
| `edge_s2` | Signed squared estimate | Preserve the estimated moment |
| `edge_signed` | `sign(s2) * sqrt(abs(s2))` | Reference validation before clipping |
| `edge` | `sqrt(max(s2, 0))` | Baseline, following the paper |
| `edge_abs` | `sqrt(abs(s2))` | Agreed sensitivity comparison |

Missing moments remain missing in every conversion. For example, if
`s2 = -0.0001`, the baseline is zero, the signed root is -1%, and the modulus
estimate is +1%. The sign option alone does not select the paper's final rule.

**Decision:** use final zero truncation for the replication baseline and retain
modulus estimates for comparison. Do not decide between them by which aggregate
mean looks closer to the paper. On the baseline four-method common sample,
modulus changes 25.88% of EDGE estimates and raises the mean by 33.66 bp; this
is convention sensitivity, not evidence of better accuracy.

### Roll: defined negative squared estimates versus missing estimates

The local scalar `roll.py` returns `NaN` when the estimated return covariance is
nonnegative. In contrast, Part B distinguishes a **defined** nonpositive
squared-spread estimate from an **undefined** covariance:

- Compute `s2 = -4 * sample_covariance(adjacent log returns)`.
- If covariance is finite, return `sqrt(max(s2, 0))`.
- If there are too few usable pairs or covariance is undefined, retain `NaN`.

This distinction affects both zero frequency and sample coverage. Dropping
defined negative estimates would change the sample and omit observations that
the paper's convention retains as zeros.

**Decision:** use pairwise-complete return pairs and sample covariance
(`ddof=1`), consistent with the pinned R function on the tested inputs. At least
two return pairs are needed: four prices for a within-month calculation. The
original scalar guard says three prices, but three produce only one pair and
an undefined sample covariance. The paper's statement of at least three daily
observations does not settle the covariance/window detail; this remains a
paper-alignment question, not grounds for inserting a zero or changing `ddof`.

### Corwin–Schultz: clipping order and overnight correction

There are two separate differences in the original scalar function:

1. Its defaults are `overnight_adjust=False` and `clip_negative=True`. It clips
   each two-day spread before averaging, whereas the selected paper convention
   averages signed contributions and truncates the final estimate.
2. Setting `overnight_adjust=True` shifts **price levels**, then computes beta
   and gamma from the modified arrays. The pinned author CS function shifts
   **log prices** for the two-day range and keeps original one-day ranges in
   beta. These operations are not equivalent. Changing the two flags alone
   does not reproduce that author implementation.

**Decision:** Part B implements the author-style correction directly. With
lowercase letters denoting log prices:

```text
gap_t = max(0, c_(t-1) - h_t) + min(0, c_(t-1) - l_t)
beta_t = (h_t - l_t)^2 + (h_(t-1) - l_(t-1))^2
gamma_t = [max(h_t + gap_t, h_(t-1)) - min(l_t + gap_t, l_(t-1))]^2
```

Apply the CS alpha formula, convert each contribution using
`2*tanh(alpha/2)` (algebraically equivalent to the exponential expression),
average signed spreads, and finally take `max(monthly_mean, 0)`.
`cs_signed` is the average spread before truncation, **not** a squared spread.
The authors' daily-clipped `CS2` is a different variant and is not substituted
for CS. We have not added CS2 as another production sensitivity.

### Abdi–Ranaldo: no identified arithmetic mismatch on tested inputs

The scalar and batch implementations average signed squared contributions and
then apply the zero-truncated square root. Both use HLC; neither requires O.
Part B retains `ar_s2` so the final transformation can be checked.

**Decision:** retain that calculation and verify batch/scalar agreement.
There is a documentation inconsistency in the original scalar module: its
displayed formula uses `4/T` with `T-1` terms, while the executable function
uses four times the mean of valid terms. The current batch follows the
executable mean and pinned reference, not that displayed denominator. This
documentation issue has not been edited in Part A.

## 3. Input and window choices that also change estimates

Correct formula arithmetic does not establish that the paper supplied the
same observations. The following are approved project choices; the original
empirical scripts have not been inspected.

| Issue | Current baseline | Alternative / limitation |
|---|---|---|
| Corporate actions | Divide all OHLC by positive CFACPR | `raw_` variant uses unadjusted prices; paper's exact adjustment procedure unverified |
| Invalid factors | Any unusable factor among retained current-month HLC rows makes all adjusted methods unavailable for that month | Raw estimates remain when computable; no factor replacement or partial adjusted month |
| Month boundaries | Every moment input lies within the calendar month | `boundary_` permits up to two preceding-calendar-month context rows; only moments ending in the current month count |
| Missing sessions | Form lags over consecutive retained daily rows | `gap_` suppresses moments crossing missing sessions; calendar is the union of raw CRSP dates |
| Missing opens | Keep HLC rows and use EDGE's componentwise missing-data behavior | Do not fill O or require every day to have O; insufficient information can still make EDGE missing |
| Observation count | No arbitrary 20-day or other monthly screen | Each method must have enough usable terms for its formula |
| Common sample | Save every eligible month and separate availability by method; `common_sample` requires all four finite | Paper's matched sample also depends on TAQ and additional estimators |

For the gap variant, Roll requires both adjacent-return links to be consecutive;
other lagged moments require their one link. Pool surviving moments rather than
averaging separate segment estimates. Boundary estimates also reject unusable
factors in supplied context rows. Neither sensitivity changes the baseline.

These choices matter: prior-month lags change 76.12% of comparable EDGE
estimates (median absolute difference 4.01 bp); excluding moments across missing
sessions changes 14.23%. Neither result identifies the paper's convention.
There is no additional blanket overnight-return subtraction applied to all
methods; CS has its specific correction described above.

## 4. What remains unresolved in Part A

| Issue | Evidence in the repository | Consequence / next review |
|---|---|---|
| Independent EDGE implementation | `edge.py` describes its numeric logic as identical to upstream; the batch follows that algebra | Numerical agreement is not evidence of an independent derivation from the paper. Verify the course deliverable separately. |
| Simulation defaults differ from Part B | `monte_carlo.py` calls scalar EDGE, Roll and CS with default arguments | EDGE uses modulus; Roll drops nonnegative covariance; CS lacks overnight correction and clips daily. Review and align definitions before claiming paper simulation replication. |
| Simulation missingness affects metrics | `bias_rmse()` removes `NaN` estimates separately by method and reports `n_valid` | Roll's defined negative cases are excluded under current defaults. Review availability and metric samples, especially as trading frequency declines. |
| Additional component estimators | Current empirical pipeline produces EDGE, AR, CS and Roll only | Full corresponding paper tables/columns also require CHL, OHL, CHLO and OHLC; four core methods do not reproduce every column. |
| Original package tests | `test_estimators.py` uses module-level `pytest.importorskip("bidask", ...)`; Python `bidask` was absent in the environment used | A skipped module is not a passed comparison; it can skip other tests in that module too. |
| Original competitor snapshot tests | Expected values are local snapshots, explicitly not published reference numbers | They check stability, not alignment with the authors' formulas. Part B adds a separate author-R reference check. |

These findings do not imply that all Part A work is wrong. They identify what
must be reconciled before its outputs and the Part B panel can be described as
using the same estimator definitions. No scalar functions, simulation settings
or original tests were changed during the Part B work.

## 5. What is verified, and what is not?

**Already verified in the recorded run:** 24 focused tests passed; full-panel
invariants passed for 1,711,915 eligible stock-months; 232 sampled baseline
stock-months matched the pinned author R functions in signed outputs with
maximum absolute differences below 1.24e-15. Signed comparison prevents final
clipping from hiding disagreements behind matching zeros. Synthetic tests
cover missing inputs, degeneracy, split scaling, boundaries and gaps.

**Limits:** the real-data R check covers sampled baseline months, not every
stock-month or an author implementation of our alternative window definitions.
The reference is a pinned package version, not a verified copy of the exact
publication workflow. Agreement does not establish identical CRSP vintage,
daily filtering, TAQ matching, size groups or benchmark accuracy. The saved
panel has not yet been validated against TAQ effective spreads.

**Next review priorities:** reconcile Part A's transformation/CS/Roll choices
and independent-derivation requirement; rerun affected simulations if definitions
change; add component estimators only if required by the chosen replication
targets; and keep empirical preprocessing assumptions explicit until stronger
evidence becomes available. Do not change assumptions merely to match Table 3
aggregate statistics. Part C remains separately planned.

This note records the current implementation; writing it did not rerun tests
or simulations, change estimator code, or download data.
