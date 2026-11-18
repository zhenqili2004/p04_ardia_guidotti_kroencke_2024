"""
EDGE: Efficient Discrete Generalized Estimator of bid-ask spreads.

Ported from the reference implementation:
    https://github.com/eguidotti/bidask (MIT License)
    file:  python/bidask/edge.py
    upstream commit: 1caba55d63eb (2025-10-13)

Numeric logic is bit-identical to upstream; only the input parameter type
annotations were corrected from `np.array` (which is a function, not a type,
and triggers Pyright errors) to `numpy.typing.ArrayLike`.

Accompanying paper:
    Ardia, D., Guidotti, E., Kroencke, T.A. (2024).
    Efficient Estimation of Bid-Ask Spreads from Open, High, Low, and Close
    Prices. Journal of Financial Economics, 161, 103916.
    https://doi.org/10.1016/j.jfineco.2024.103916
"""

import warnings

import numpy as np
from numpy.typing import ArrayLike


def edge(
    open: ArrayLike,
    high: ArrayLike,
    low: ArrayLike,
    close: ArrayLike,
    sign: bool = False,
) -> float:
    """
    Efficient Estimation of Bid-Ask Spreads from Open, High, Low, and Close Prices

    Implements the efficient estimator of bid-ask spreads from open, high, low,
    and close prices described in Ardia, Guidotti, & Kroencke (JFE, 2024):
    https://doi.org/10.1016/j.jfineco.2024.103916

    Parameters
    ----------
    - `open`: array-like
        Vector of open prices sorted in ascending order of the timestamp.
    - `high`: array-like
        Vector of high prices sorted in ascending order of the timestamp.
    - `low`: array-like
        Vector of low prices sorted in ascending order of the timestamp.
    - `close`: array-like
        Vector of close prices sorted in ascending order of the timestamp.
    - `sign`:
        Whether to return signed estimates.

    Returns
    -------
    float
        The spread estimate. A value of 0.01 corresponds to a spread of 1%.
    """
    # compute log-prices (cast to ndarray so .shape[0] / nanmean work)
    o = np.log(np.asarray(open))
    h = np.log(np.asarray(high))
    l = np.log(np.asarray(low))
    c = np.log(np.asarray(close))

    # check that the open, high, low, and close prices have the same length
    nobs = o.shape[0]
    if h.shape[0] != nobs or l.shape[0] != nobs or c.shape[0] != nobs:
        raise ValueError("Open, high, low, and close prices must have the same length")

    # return missing if there are less than 3 observations
    if nobs < 3:
        return np.nan

    m = (h + l) / 2.0

    # shift log-prices by one period
    h1, l1, c1, m1 = h[:-1], l[:-1], c[:-1], m[:-1]
    o, h, l, c, m = o[1:], h[1:], l[1:], c[1:], m[1:]

    # compute log-returns
    r1 = m - o
    r2 = o - m1
    r3 = m - c1
    r4 = c1 - m1
    r5 = o - c1

    # compute indicator variables
    tau = np.where(np.isnan(h) | np.isnan(l) | np.isnan(c1), np.nan, (h != l) | (l != c1))
    po1 = tau * np.where(np.isnan(o) | np.isnan(h), np.nan, o != h)
    po2 = tau * np.where(np.isnan(o) | np.isnan(l), np.nan, o != l)
    pc1 = tau * np.where(np.isnan(c1) | np.isnan(h1), np.nan, c1 != h1)
    pc2 = tau * np.where(np.isnan(c1) | np.isnan(l1), np.nan, c1 != l1)

    # ignore warnings raised by nanmean for all-NaN slices
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)

        # compute probabilities
        pt = np.nanmean(tau)
        po = np.nanmean(po1) + np.nanmean(po2)
        pc = np.nanmean(pc1) + np.nanmean(pc2)

        # return missing if there are less than two periods with tau=1
        # or po or pc is zero
        if np.nansum(tau) < 2 or po == 0 or pc == 0:
            return np.nan

        # compute de-meaned log-returns
        d1 = r1 - np.nanmean(r1) / pt * tau
        d3 = r3 - np.nanmean(r3) / pt * tau
        d5 = r5 - np.nanmean(r5) / pt * tau

        # compute input vectors
        x1 = -4.0 / po * d1 * r2 + -4.0 / pc * d3 * r4
        x2 = -4.0 / po * d1 * r5 + -4.0 / pc * d5 * r4

        # compute expectations
        e1 = np.nanmean(x1)
        e2 = np.nanmean(x2)

        # compute variances
        v1 = np.nanmean(x1**2) - e1**2
        v2 = np.nanmean(x2**2) - e2**2

    # compute square spread by using a (equally) weighted
    # average if the total variance is (not) positive
    vt = v1 + v2
    s2 = (v2 * e1 + v1 * e2) / vt if vt > 0 else (e1 + e2) / 2.0

    # compute signed root
    s = np.sqrt(np.abs(s2))
    if sign:
        s *= np.sign(s2)

    # return the spread
    return float(s)
