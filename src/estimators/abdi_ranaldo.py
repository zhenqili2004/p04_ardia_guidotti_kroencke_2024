"""
Abdi & Ranaldo (2017) close-high-low bid-ask spread estimator.

Reference
---------
Abdi, F., Ranaldo, A. (2017). "A Simple Estimation of Bid-Ask Spreads from
Daily Close, High, and Low Prices." *Review of Financial Studies*,
30(12), 4437-4480.
https://doi.org/10.1093/rfs/hhx084

Reviewed as a benchmark in:
    Ardia, D., Guidotti, E., Kroencke, T.A. (2024). *JFE*, 161, 103916.
    https://doi.org/10.1016/j.jfineco.2024.103916

Formula
-------
Let c_t = log(close_t) and η_t = (log H_t + log L_t) / 2 be the log mid-point
of the daily high-low range. Under the Abdi-Ranaldo microstructure model,

    S² = E[ 4 ( c_t - η_t ) ( c_t - η_{t+1} ) ]

Hence the sample estimator:

    S_AR = sqrt( max{ 0,  (4/T) Σ_{t=1}^{T-1} (c_t - η_t)(c_t - η_{t+1}) } )

The max{0, ·} guards against negative sample estimates arising from
microstructure noise or small samples, following standard practice.

The output is a proportional spread (0.01 = 1%).

This implementation keeps a uniform signature `(open, high, low, close)` so
it is drop-in interchangeable with `edge()` for Monte Carlo comparisons;
`open` is unused.
"""

import numpy as np
from numpy.typing import ArrayLike


def abdi_ranaldo(
    open: ArrayLike, high: ArrayLike, low: ArrayLike, close: ArrayLike
) -> float:
    """
    Abdi-Ranaldo (2017) effective bid-ask spread estimator from CHL prices.

    Parameters
    ----------
    open : array-like
        Unused; present for signature compatibility.
    high, low, close : array-like
        High, low, close prices in ascending timestamp order. Length >= 2.

    Returns
    -------
    float
        Proportional spread estimate (0.01 = 1%). Returns 0 if the sample
        inner product is non-positive (clipped). NaN if fewer than 2
        observations.
    """
    # open accepted for signature compatibility with edge() / roll() /
    # corwin_schultz(); Abdi-Ranaldo (2017) uses only high, low, close.
    del open

    close_arr = np.asarray(close, dtype=float)
    high_arr = np.asarray(high, dtype=float)
    low_arr = np.asarray(low, dtype=float)
    nobs = close_arr.shape[0]
    if high_arr.shape[0] != nobs or low_arr.shape[0] != nobs:
        raise ValueError("high, low, close must have the same length")
    if nobs < 2:
        return np.nan

    c = np.log(close_arr)
    h = np.log(high_arr)
    l = np.log(low_arr)
    eta = 0.5 * (h + l)

    # (c_t - η_t) * (c_t - η_{t+1}), t = 0, ..., T-2
    with np.errstate(invalid="ignore"):
        inner = (c[:-1] - eta[:-1]) * (c[:-1] - eta[1:])

    valid = np.isfinite(inner)
    if valid.sum() < 1:
        return np.nan
    s2 = 4.0 * float(np.mean(inner[valid]))
    return float(np.sqrt(max(0.0, s2)))
