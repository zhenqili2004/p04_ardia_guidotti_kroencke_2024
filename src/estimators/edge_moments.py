"""
EDGE's moment conditions: the one place in this repository where they are
computed.

`edge()` (in edge.py) is a thin wrapper around `edge_moments()`, and the
extension's diagnostics (src/extension/) read the per-bar moment series from
here, so EDGE is computed in exactly one place (no duplicated arithmetic).

What it returns
---------------
EDGE (Ardia, Guidotti & Kroencke 2024, eqs. 19-25) averages two moment
conditions, each the mean of two "discrete generalized estimators" (DGEs,
the paper's Table 1):

    x1_t = (OHL_t  + CHL_t ) / 2
    x2_t = (OHLC_t + CHLO_t) / 2

Under the paper's Assumptions 1-3 (fundamental returns serially
uncorrelated and uncorrelated with bid-ask bounces; bounces serially
uncorrelated with mean zero), each of x1, x2 and the four DGEs has
expectation S^2 = (S_o^2 + S_c^2) / 2, the mean squared effective spread of
the open and close trades (eqs. 19-20). The coefficients pi_o = -8 / po and
pi_c = -8 / pc account for discretely observed prices: they correct for the
open (previous close) trade being itself the high or low trade of its bar
(Appendix A.2). Returns are de-meaned with the indicator tau_t (eqs. 7, 9),
which is 0 when h_t = l_t = c_{t-1}: bar t had no trade, or every trade was
at the previous close. EDGE weights the two means to minimise variance:

    w1 = Var[x2] / (Var[x1] + Var[x2]),   w2 = 1 - w1
    S_hat^2 = w1 * mean(x1) + w2 * mean(x2)

The arithmetic is the upstream `bidask` code moved here unchanged (same
operations in the same order), so `edge()` stays bit-identical to `bidask`.
"""

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np

# See edge.py for why `_Vec` is Any rather than a precise union.
_Vec = Any


@dataclass(frozen=True)
class EdgeMoments:
    """
    EDGE's per-bar moment conditions and the quantities built from them.

    Every array has one entry per input bar. Entry t uses bars t-1 and t, so
    entry 0 is always NaN; entries are also NaN where an input is missing.
    When EDGE is undefined (fewer than 3 bars, fewer than 2 bars with
    tau_t = 1, or `po` or `pc` equal to zero), every array is all-NaN and
    `s2`, `w1`, `w2` are NaN.

    Attributes
    ----------
    x1, x2 : np.ndarray
        The two moment conditions, x1 = (OHL + CHL) / 2 and
        x2 = (OHLC + CHLO) / 2, in squared log-spread units.
    ohl, chl, ohlc, chlo : np.ndarray
        The four DGE building blocks (paper's Table 1); each estimates S^2.
    po, pc, pt : float
        Probabilities estimated from the data:
        po = P[o_t != h_t, tau_t = 1] + P[o_t != l_t, tau_t = 1],
        pc = P[c_{t-1} != h_{t-1}, tau_t = 1] + P[c_{t-1} != l_{t-1}, tau_t = 1],
        pt = P[tau_t = 1]. The DGEs are scaled by pi_o = -8 / po and
        pi_c = -8 / pc (paper's Table 1).
    w1, w2 : float
        EDGE's weights on mean(x1) and mean(x2); w1 + w2 = 1.
    s2 : float
        Signed squared spread, w1 * mean(x1) + w2 * mean(x2). `edge()` returns
        sqrt(|s2|), with the sign of s2 when `sign=True`.
    """

    x1: np.ndarray
    x2: np.ndarray
    ohl: np.ndarray
    chl: np.ndarray
    ohlc: np.ndarray
    chlo: np.ndarray
    po: float
    pc: float
    pt: float
    w1: float
    w2: float
    s2: float


def _undefined_moments(
    nobs: int, po: float = np.nan, pc: float = np.nan, pt: float = np.nan
) -> EdgeMoments:
    """Return the all-NaN result used when EDGE is undefined."""
    nan = np.full(nobs, np.nan)
    return EdgeMoments(
        x1=nan,
        x2=nan.copy(),
        ohl=nan.copy(),
        chl=nan.copy(),
        ohlc=nan.copy(),
        chlo=nan.copy(),
        po=float(po),
        pc=float(pc),
        pt=float(pt),
        w1=np.nan,
        w2=np.nan,
        s2=np.nan,
    )


def _align(values: np.ndarray) -> np.ndarray:
    """Prepend NaN so that entry t of a moment series lines up with bar t."""
    return np.concatenate([[np.nan], values])


def edge_moments(open: _Vec, high: _Vec, low: _Vec, close: _Vec) -> EdgeMoments:
    """
    Compute EDGE's moment conditions from open, high, low and close prices.

    Parameters
    ----------
    open, high, low, close : array-like
        Prices sorted in ascending order of the timestamp, all the same
        length. Missing values (NaN) are allowed.

    Returns
    -------
    EdgeMoments
        Per-bar moment series aligned with the input, plus EDGE's weights
        and signed squared spread. See `EdgeMoments` for the fields.

    Raises
    ------
    ValueError
        If the four inputs do not have the same length.

    Examples
    --------
    Four bars whose log prices (in percent) are chosen so that the moments
    can be worked out by hand (src/tests/test_edge_moments.py does it step
    by step). Every open and close lies strictly inside its bar's range, so
    po = pc = 2 and pt = 1.

    >>> import numpy as np
    >>> logp = np.array([[0, 4, -2, 2], [3, 5, -1, 1], [0, 3, -3, -1], [-2, 2, -4, 1]])
    >>> o, h, l, c = np.exp(logp.T / 100)
    >>> m = edge_moments(o, h, l, c)
    >>> [round(float(v), 4) for v in m.x1[1:] * 1e4]  # x1 in percent^2
    [3.3333, -1.3333, 4.6667]
    >>> [round(float(v), 4) for v in m.x2[1:] * 1e4]
    [-0.6667, -1.3333, 0.6667]
    >>> round(m.w1, 6) == round(7 / 74, 6)
    True
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

    # undefined if there are less than 3 observations
    if nobs < 3:
        return _undefined_moments(nobs)

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
    tau = np.where(
        np.isnan(h) | np.isnan(l) | np.isnan(c1), np.nan, (h != l) | (l != c1)
    )
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

        # undefined if there are less than two periods with tau=1
        # or po or pc is zero
        if np.nansum(tau) < 2 or po == 0 or pc == 0:
            return _undefined_moments(nobs, po=po, pc=pc, pt=pt)

        # compute de-meaned log-returns
        d1 = r1 - np.nanmean(r1) / pt * tau
        d3 = r3 - np.nanmean(r3) / pt * tau
        d5 = r5 - np.nanmean(r5) / pt * tau

        # half of each DGE; x1 and x2 are sums of two halves, computed with
        # the same operations in the same order as upstream bidask
        half_ohl = -4.0 / po * d1 * r2
        half_chl = -4.0 / pc * d3 * r4
        half_ohlc = -4.0 / po * d1 * r5
        half_chlo = -4.0 / pc * d5 * r4

        # compute input vectors
        x1 = half_ohl + half_chl
        x2 = half_ohlc + half_chlo

        # compute expectations
        e1 = np.nanmean(x1)
        e2 = np.nanmean(x2)

        # compute variances
        v1 = np.nanmean(x1**2) - e1**2
        v2 = np.nanmean(x2**2) - e2**2

    # compute square spread by using a (equally) weighted
    # average if the total variance is (not) positive
    vt = v1 + v2
    if vt > 0:
        s2 = (v2 * e1 + v1 * e2) / vt
        w1, w2 = v2 / vt, v1 / vt
    else:
        s2 = (e1 + e2) / 2.0
        w1, w2 = 0.5, 0.5

    return EdgeMoments(
        x1=_align(x1),
        x2=_align(x2),
        ohl=_align(2.0 * half_ohl),
        chl=_align(2.0 * half_chl),
        ohlc=_align(2.0 * half_ohlc),
        chlo=_align(2.0 * half_chlo),
        po=float(po),
        pc=float(pc),
        pt=float(pt),
        w1=float(w1),
        w2=float(w2),
        s2=float(s2),
    )
