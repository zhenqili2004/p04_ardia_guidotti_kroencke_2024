"""
Tests for `estimators.edge_moments`, the one place EDGE's moment conditions
are computed.

`edge()` is now a thin wrapper around `edge_moments()`, so comparing the two
would be circular. These tests check the moments against things that were
not computed by them:

1. The `bidask` package (oracle): the signed root of `s2` matches
   `bidask.edge(sign=True)` within 1e-10, including on missing data and on
   inputs where EDGE is undefined. Every intermediate quantity (pt, po, pc,
   the means and variances of x1 and x2, s2) matches the values the author
   publishes for the two reference files.
2. A four-bar example worked out by hand with exact fractions, which pins
   down x1, x2, all four DGE building blocks, and the weights.
3. The decomposition S_hat^2 = w1 * mean(x1) + w2 * mean(x2) that the
   extension's diagnostics rely on.
4. The shape contract: one entry per input bar, NaN where undefined.
"""

import doctest
import importlib
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from estimators import edge_moments
from simulations.simulator import simulate_ohlc

FIXTURES = Path(__file__).parent.parent / "estimators" / "_fixtures"
df = pd.read_csv(FIXTURES / "ohlc.csv")
df_miss = pd.read_csv(FIXTURES / "ohlc-miss.csv")

bidask_pkg = pytest.importorskip(
    "bidask",
    reason="bidask package not installed; skipping oracle differential test",
)


def _signed_root(s2: float) -> float:
    return float(np.sign(s2) * np.sqrt(np.abs(s2)))


# ===========================================================================
# 1. Oracle: bidask
# ===========================================================================

ORACLE_CASES = {
    "fixture": df,
    "fixture_missing_values": df_miss,
    "fixture_first_10_negative_estimate": df.iloc[:10],
    "simulated_thin_trading": simulate_ohlc(
        n=500, trades=50, prob=0.1, rng=np.random.default_rng(11)
    ),
    # Same flat input as test_edge(): h = l = previous close, so tau = 0 and
    # EDGE is undefined.
    "undefined_flat_prices": pd.DataFrame(
        {
            "Open": [18.21, 17.61, 17.61],
            "High": [18.21, 17.61, 17.61],
            "Low": [17.61, 17.61, 17.61],
            "Close": [17.61, 17.61, 17.61],
        }
    ),
    "undefined_two_bars": df.iloc[:2],
}


@pytest.mark.parametrize("case", ORACLE_CASES)
def test_signed_root_of_s2_matches_bidask(case):
    """sign(s2) * sqrt(|s2|) equals bidask.edge(sign=True), NaN where it is NaN."""
    data = ORACLE_CASES[case]
    ours = _signed_root(edge_moments(data.Open, data.High, data.Low, data.Close).s2)
    theirs = bidask_pkg.edge(data.Open, data.High, data.Low, data.Close, sign=True)
    if np.isnan(theirs):
        assert np.isnan(ours), f"{case}: bidask is NaN but ours is {ours}"
    else:
        # Same tolerance as the existing edge() vs bidask oracle tests.
        assert ours == pytest.approx(theirs, abs=1e-10), case


# --- 1b. The author's published intermediate values ------------------------
# bidask's pseudocode/README.md (https://github.com/eguidotti/bidask) lists
# every intermediate quantity of the estimator on the two reference files
# in _fixtures/, "to check and debug the intermediate steps". Matching them
# checks each step of edge_moments(), not only the final estimate.
AUTHOR_INTERMEDIATES = {
    "fixture": {
        "pt": 0.9820982098209821,
        "po": 1.227922792279228,
        "pc": 1.2052205220522052,
        "e1": 0.00010702425689560482,
        "e2": 0.000101595812797079,
        "v1": 2.074215642985551e-06,
        "v2": 1.3461279919743572e-06,
        "s2": 0.00010373225911177194,
    },
    "fixture_missing_values": {
        "pt": 0.9822078447230085,
        "po": 1.2272254421162134,
        "pc": 1.205827632480371,
        "e1": 0.00010337780767834583,
        "e2": 0.00010219271972776808,
        "v1": 2.0045420261850617e-06,
        "v2": 1.373839551967266e-06,
        "s2": 0.00010267464299824543,
    },
}


@pytest.mark.parametrize("case", AUTHOR_INTERMEDIATES)
def test_intermediates_match_author_published_values(case):
    data = ORACLE_CASES[case]
    m = edge_moments(data.Open, data.High, data.Low, data.Close)
    e1, e2 = np.nanmean(m.x1), np.nanmean(m.x2)
    got = {
        "pt": m.pt,
        "po": m.po,
        "pc": m.pc,
        "e1": e1,
        "e2": e2,
        "v1": np.nanmean(m.x1**2) - e1**2,
        "v2": np.nanmean(m.x2**2) - e2**2,
        "s2": m.s2,
    }
    expected = AUTHOR_INTERMEDIATES[case]
    for name, value in expected.items():
        # The author prints 16 significant digits; 1e-10 relative leaves room
        # for summation order and still catches any real difference.
        assert got[name] == pytest.approx(value, rel=1e-10), f"{case}: {name}"
    # The weights follow from the variances (paper's Eq. 25).
    v1, v2 = expected["v1"], expected["v2"]
    assert m.w2 == pytest.approx(v1 / (v1 + v2), rel=1e-10), f"{case}: w2"


# ===========================================================================
# 2. A four-bar example worked out by hand
# ===========================================================================
# Log prices in percent (o, h, l, c). Every open and close lies strictly
# inside its bar's range and h != l in every bar, so tau = 1, po = pc = 2 and
# pt = 1, and -4/po = -4/pc = -2.
#
#   bar  o   h   l   c   eta=(h+l)/2
#    0   0   4  -2   2   1
#    1   3   5  -1   1   2
#    2   0   3  -3  -1   0
#    3  -2   2  -4   1  -1
#
# For t = 1, 2, 3:
#   r1 = eta_t - o_t          = (-1,  0,  1)   mean  0
#   r2 = o_t - eta_{t-1}      = ( 2, -2, -2)
#   r3 = eta_t - c_{t-1}      = ( 0, -1,  0)   mean -1/3
#   r4 = c_{t-1} - eta_{t-1}  = ( 1, -1, -1)
#   r5 = o_t - c_{t-1}        = ( 1, -1, -1)   mean -1/3
# De-meaned (d = r - mean(r)):
#   d1 = (-1, 0, 1),  d3 = (1/3, -2/3, 1/3),  d5 = (4/3, -2/3, -2/3)
# DGEs (each = 2 x its half-term; -8/po = -4):
#   OHL  = -4 d1 r2 = (8, 0, 8)
#   CHL  = -4 d3 r4 = (-4/3, -8/3, 4/3)
#   OHLC = -4 d1 r5 = (4, 0, 4)
#   CHLO = -4 d5 r4 = (-16/3, -8/3, -8/3)
#   x1 = (OHL + CHL) / 2  = (10/3, -4/3, 14/3)    mean 20/9
#   x2 = (OHLC + CHLO) / 2 = (-2/3, -4/3, 2/3)    mean -4/9
# Variances (population): v1 = 536/81, v2 = 56/81, so
#   w1 = v2 / (v1 + v2) = 7/74,  s2 = w1 * 20/9 + (67/74) * (-4/9) = -64/333.

HAND_LOG_PRICES = np.array(
    [[0, 4, -2, 2], [3, 5, -1, 1], [0, 3, -3, -1], [-2, 2, -4, 1]], dtype=float
)
F = Fraction
HAND_EXPECTED = {  # in percent^2, entry 0 is NaN
    "x1": [F(10, 3), F(-4, 3), F(14, 3)],
    "x2": [F(-2, 3), F(-4, 3), F(2, 3)],
    "ohl": [F(8), F(0), F(8)],
    "chl": [F(-4, 3), F(-8, 3), F(4, 3)],
    "ohlc": [F(4), F(0), F(4)],
    "chlo": [F(-16, 3), F(-8, 3), F(-8, 3)],
}


@pytest.fixture
def hand_moments():
    o, h, l, c = np.exp(HAND_LOG_PRICES.T / 100)
    return edge_moments(o, h, l, c)


@pytest.mark.parametrize("field", HAND_EXPECTED)
def test_hand_example_moment_series(hand_moments, field):
    got = getattr(hand_moments, field)
    assert np.isnan(got[0]), "entry 0 has no previous bar and must be NaN"
    expected = np.array([float(v) for v in HAND_EXPECTED[field]]) * 1e-4
    np.testing.assert_allclose(got[1:], expected, rtol=1e-9, atol=1e-15, err_msg=field)


def test_hand_example_scalars(hand_moments):
    assert hand_moments.po == pytest.approx(2.0)
    assert hand_moments.pc == pytest.approx(2.0)
    assert hand_moments.pt == pytest.approx(1.0)
    assert hand_moments.w1 == pytest.approx(7 / 74, rel=1e-9)
    assert hand_moments.w2 == pytest.approx(67 / 74, rel=1e-9)
    assert hand_moments.s2 == pytest.approx(-64 / 333 * 1e-4, rel=1e-9)


def test_docstring_example_runs():
    """The worked example in edge_moments' docstring must stay true."""
    # `estimators.edge_moments` the attribute is the re-exported function, so
    # fetch the module itself by name.
    module = importlib.import_module("estimators.edge_moments")
    result = doctest.testmod(module)
    assert result.attempted > 0
    assert result.failed == 0


# ===========================================================================
# 3. Decomposition used by the diagnostics
# ===========================================================================


@pytest.mark.parametrize("case", ["fixture", "fixture_missing_values"])
def test_s2_is_weighted_mean_of_moments(case):
    data = ORACLE_CASES[case]
    m = edge_moments(data.Open, data.High, data.Low, data.Close)
    assert m.w1 + m.w2 == pytest.approx(1.0, abs=1e-12)
    assert 0.0 <= m.w1 <= 1.0
    recombined = m.w1 * np.nanmean(m.x1) + m.w2 * np.nanmean(m.x2)
    assert recombined == pytest.approx(m.s2, rel=1e-12)


# ===========================================================================
# 4. Shape contract
# ===========================================================================


@pytest.mark.parametrize("case", ["fixture_missing_values", "undefined_flat_prices"])
def test_series_are_aligned_with_input_bars(case):
    data = ORACLE_CASES[case]
    m = edge_moments(data.Open, data.High, data.Low, data.Close)
    for field in HAND_EXPECTED:
        series = getattr(m, field)
        assert series.shape == (len(data),), field
        assert np.isnan(series[0]), field
    if np.isnan(m.s2):
        assert np.isnan(m.x1).all() and np.isnan(m.w1) and np.isnan(m.w2)


def test_length_mismatch_raises():
    with pytest.raises(ValueError, match="same length"):
        edge_moments([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], [1.0, 2.0], [1.0, 2.0, 3.0])
