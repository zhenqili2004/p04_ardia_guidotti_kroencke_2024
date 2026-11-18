"""
Corwin & Schultz (2012) high-low bid-ask spread estimator.

Reference
---------
Corwin, S.A., Schultz, P. (2012). "A Simple Way to Estimate Bid-Ask Spreads
from Daily High and Low Prices." *Journal of Finance*, 67(2), 719-760.
https://doi.org/10.1111/j.1540-6261.2012.01729.x

Reviewed as a benchmark in:
    Ardia, D., Guidotti, E., Kroencke, T.A. (2024). *JFE*, 161, 103916.
    https://doi.org/10.1016/j.jfineco.2024.103916

Formula
-------
For each two-day window (day t, day t+1), define:

    β_t = [ln(H_t   / L_t  )]² + [ln(H_{t+1} / L_{t+1})]²
    γ_t = [ln( max(H_t, H_{t+1}) / min(L_t, L_{t+1}) )]²

    α_t = ( sqrt(2 β_t) - sqrt(β_t) ) / (3 - 2√2) - sqrt( γ_t / (3 - 2√2) )

    S_t = 2 (e^{α_t} - 1) / (1 + e^{α_t})      ≈ 2 α_t      for small α_t

Following CS (2012, Section 2 and footnote 10), negative two-day spread
estimates are commonly set to zero before averaging. The sample spread is
the mean of S_t over all valid two-day windows.

The output is a proportional spread (0.01 = 1%).

Overnight-return adjustment (CS Section 4) is not applied by default — set
`overnight_adjust=True` to shift H_{t+1} and L_{t+1} by the overnight return
inferred from close_t vs. {low_{t+1}, high_{t+1}}.

This implementation keeps a uniform signature `(open, high, low, close)` so
it is drop-in interchangeable with `edge()` for Monte Carlo comparisons.
Only `high` and `low` (plus `close` if `overnight_adjust=True`) are used.
"""

import numpy as np

_K = 3.0 - 2.0 * np.sqrt(2.0)  # = 3 - 2√2


def corwin_schultz(
    open: np.array,
    high: np.array,
    low: np.array,
    close: np.array,
    overnight_adjust: bool = False,
    clip_negative: bool = True,
) -> float:
    """
    Corwin-Schultz (2012) effective bid-ask spread estimator from high-low.

    Parameters
    ----------
    open : array-like
        Unused; present for signature compatibility.
    high, low : array-like
        High and low prices in ascending timestamp order. Length >= 2.
    close : array-like
        Close prices; only used when `overnight_adjust=True`.
    overnight_adjust : bool, default False
        If True, apply the CS (2012, Section 4) overnight-gap correction:
        when close_t < low_{t+1}, subtract (low_{t+1} - close_t) from both
        high_{t+1} and low_{t+1}; when close_t > high_{t+1}, add
        (close_t - high_{t+1}) to both high_{t+1} and low_{t+1}.
    clip_negative : bool, default True
        If True, two-day spread estimates with α < 0 are set to 0 before
        averaging (CS 2012 footnote 10). If False, negative values are kept.

    Returns
    -------
    float
        Proportional spread estimate (0.01 = 1%). NaN if fewer than 2
        observations or if no valid two-day windows remain.
    """
    nobs = len(high)
    if len(low) != nobs or len(close) != nobs:
        raise ValueError("high, low, close must have the same length")
    if nobs < 2:
        return np.nan

    h = np.asarray(high, dtype=float).copy()
    l = np.asarray(low, dtype=float).copy()
    c = np.asarray(close, dtype=float)

    if overnight_adjust:
        # Shift h[t+1] and l[t+1] by the overnight return inferred from c[t].
        gap_up = c[:-1] > h[1:]                    # close above next day's high
        gap_dn = c[:-1] < l[1:]                    # close below next day's low
        shift_up = np.where(gap_up, c[:-1] - h[1:], 0.0)    # positive shift
        shift_dn = np.where(gap_dn, c[:-1] - l[1:], 0.0)    # negative shift
        h[1:] = h[1:] + shift_up + shift_dn
        l[1:] = l[1:] + shift_up + shift_dn

    h_t, h_tp1 = h[:-1], h[1:]
    l_t, l_tp1 = l[:-1], l[1:]

    # β_t: sum of two one-day squared log-ranges
    with np.errstate(invalid="ignore", divide="ignore"):
        beta = np.log(h_t / l_t) ** 2 + np.log(h_tp1 / l_tp1) ** 2
        # γ_t: squared log-range over the two-day window
        h2 = np.maximum(h_t, h_tp1)
        l2 = np.minimum(l_t, l_tp1)
        gamma = np.log(h2 / l2) ** 2

        alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / _K - np.sqrt(gamma / _K)
        # Two-day spread estimate (CS eq. 14)
        s_t = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))

    if clip_negative:
        s_t = np.where(s_t < 0, 0.0, s_t)

    valid = np.isfinite(s_t)
    if not valid.any():
        return np.nan
    return float(np.mean(s_t[valid]))
