"""
Roll (1984) effective bid-ask spread estimator.

Reference
---------
Roll, R. (1984). "A Simple Implicit Measure of the Effective Bid-Ask Spread
in an Efficient Market." *Journal of Finance*, 39(4), 1127-1139.
https://doi.org/10.1111/j.1540-6261.1984.tb03897.x

Reviewed as a benchmark in:
    Ardia, D., Guidotti, E., Kroencke, T.A. (2024). *JFE*, 161, 103916.
    https://doi.org/10.1016/j.jfineco.2024.103916

Formula
-------
Let c_t = log(close_t) and Δc_t = c_t - c_{t-1}. Under Roll's microstructure
model with zero-mean efficient-price innovations, the serial covariance of
consecutive log price changes identifies the effective spread S:

    Cov(Δc_t, Δc_{t-1}) = -S² / 4

Hence the sample estimator:

    S_Roll = 2 * sqrt(-Cov(Δc_t, Δc_{t-1}))    if Cov < 0
           = NaN                                 otherwise

The output is a proportional spread (0.01 = 1%).

This implementation keeps a uniform signature `(open, high, low, close)` so
it is drop-in interchangeable with `edge()` for Monte Carlo comparisons;
only `close` is used.
"""

import numpy as np
from numpy.typing import ArrayLike


def roll(open: ArrayLike, high: ArrayLike, low: ArrayLike, close: ArrayLike) -> float:
    """
    Roll (1984) effective bid-ask spread estimator from close prices.

    Parameters
    ----------
    open, high, low : array-like
        Unused; present for signature compatibility with the other OHLC
        estimators in this package.
    close : array-like
        Close prices in ascending timestamp order. Must have length >= 3.

    Returns
    -------
    float
        Proportional spread estimate (0.01 = 1%). NaN if sample serial
        covariance of log-returns is non-negative (Roll's estimator is
        undefined in that case) or if fewer than 3 observations.
    """
    # open, high, low accepted for signature compatibility with edge() /
    # corwin_schultz() / abdi_ranaldo(); Roll (1984) uses only close.
    del open, high, low

    close_arr = np.asarray(close, dtype=float)
    nobs = close_arr.shape[0]
    if nobs < 3:
        return np.nan

    c = np.log(close_arr)
    dc = np.diff(c)                      # log returns, length nobs-1
    # Sample autocovariance at lag 1 (ddof=1 to match the usual unbiased
    # estimator; ddof choice only affects small samples).
    cov = np.cov(dc[1:], dc[:-1], ddof=1)[0, 1]
    if not np.isfinite(cov) or cov >= 0:
        return np.nan
    return float(2.0 * np.sqrt(-cov))
