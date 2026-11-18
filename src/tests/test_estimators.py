"""
Tests for all bid-ask spread estimators in `src/estimators/`:
EDGE (and its rolling / expanding variants), Roll (1984),
Corwin-Schultz (2012), Abdi-Ranaldo (2017).

The file is organised in three sections:

1. EDGE reference tests
   Ported from the upstream bidask test suite
   (https://github.com/eguidotti/bidask, python/tests/test_edge.py,
   upstream commit 1caba55d63eb, 2025-10-13). Adapted to read the two
   reference OHLC CSVs from `estimators/_fixtures/` instead of fetching
   them over the network, so CI is self-contained.

2. EDGE oracle differential tests
   Our implementation (src/estimators) must match the installed `bidask`
   package bit-for-bit on the reference fixture. Currently tautological
   (we ported verbatim) but becomes the load-bearing comparison once we
   re-derive EDGE from Ardia-Guidotti-Kroencke (2024) equations as
   PROJECT_SPEC.md §2 requires.

3. Competitor estimator tests
   Roll / CS / AR have no bidask-package oracle (the package ships only
   EDGE), so we validate with:
     - snapshot tests on the reference fixture (regression protection,
       tolerance fixed at 1e-12 before any Monte Carlo was run)
     - NaN-on-too-few-observations contract
     - ValueError on length-mismatched inputs
     - flat-price degenerate case (result must be 0 or NaN, not garbage)
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from estimators import (
    abdi_ranaldo,
    corwin_schultz,
    edge,
    edge_expanding,
    edge_rolling,
    roll,
)

FIXTURES = Path(__file__).parent.parent / "estimators" / "_fixtures"
df = pd.read_csv(FIXTURES / "ohlc.csv")
df_miss = pd.read_csv(FIXTURES / "ohlc-miss.csv")


# ===========================================================================
# 1. EDGE reference tests (ported from upstream bidask test suite)
# ===========================================================================


def test_edge():
    """Compares the `edge` function to the known test case."""
    estimate = edge(df.Open, df.High, df.Low, df.Close)
    assert estimate == pytest.approx(0.0101849034905478)

    estimate = edge(df.Open[0:10], df.High[0:10], df.Low[0:10], df.Close[0:10], True)
    assert estimate == pytest.approx(-0.016889917516422)

    estimate = edge(df_miss.Open, df_miss.High, df_miss.Low, df_miss.Close)
    assert estimate == pytest.approx(0.01013284969780197)

    assert np.isnan(
        edge(
            [18.21, 17.61, 17.61],
            [18.21, 17.61, 17.61],
            [17.61, 17.61, 17.61],
            [17.61, 17.61, 17.61],
        )
    )


@pytest.mark.parametrize("window", [1, 2, 3, 4, 42, 1000])
@pytest.mark.parametrize("sign", [True, False])
@pytest.mark.parametrize("step", [1, 2, 5, 10])
def test_edge_rolling(window: int, step: int, sign: bool):
    """Rolling vectorized implementation must match the per-window loop."""
    rolling_estimates = edge_rolling(df=df, window=window, step=step, sign=sign)
    assert isinstance(rolling_estimates, pd.Series)

    expected_estimates = []
    for t in range(0, len(df), step):
        t1 = t + 1
        t0 = t1 - window
        expected_estimates.append(
            edge(
                df.Open.values[t0:t1],
                df.High.values[t0:t1],
                df.Low.values[t0:t1],
                df.Close.values[t0:t1],
                sign=sign,
            )
            if t0 >= 0
            else np.nan
        )

    np.testing.assert_allclose(
        actual=rolling_estimates,
        desired=expected_estimates,
        rtol=1e-8,
        atol=1e-8,
        err_msg="Rolling estimates do not match expected estimates",
    )


@pytest.mark.parametrize("min_periods", [0, 1, 2, 3, 42, 1000])
@pytest.mark.parametrize("sign", [True, False])
def test_edge_expanding(min_periods: int, sign: bool):
    """Expanding vectorized implementation must match the per-window loop."""
    expanding_estimates = edge_expanding(df=df, min_periods=min_periods, sign=sign)
    assert isinstance(expanding_estimates, pd.Series)

    expected_estimates = []
    for t in range(0, len(df)):
        t1 = t + 1
        expected_estimates.append(
            edge(
                df.Open.values[0:t1],
                df.High.values[0:t1],
                df.Low.values[0:t1],
                df.Close.values[0:t1],
                sign=sign,
            )
            if t1 >= min_periods
            else np.nan
        )

    np.testing.assert_allclose(
        actual=expanding_estimates,
        desired=expected_estimates,
        rtol=1e-8,
        atol=1e-8,
        err_msg="Expanding estimates do not match expected estimates",
    )


# ===========================================================================
# 2. EDGE oracle differential tests (vs. installed `bidask` package)
# ===========================================================================
# Tautologically green while our code remains a verbatim port; becomes
# load-bearing once we re-derive the estimator from the paper equations.
# Tolerance (1e-10) is fixed here before any independent implementation.

bidask_pkg = pytest.importorskip(
    "bidask",
    reason="bidask package not installed; skipping oracle differential test",
)


def test_edge_matches_bidask_package():
    """Our edge() must match bidask.edge() on the reference fixture."""
    ours = edge(df.Open, df.High, df.Low, df.Close)
    theirs = bidask_pkg.edge(df.Open, df.High, df.Low, df.Close)
    assert ours == pytest.approx(theirs, abs=1e-10)


@pytest.mark.parametrize("window", [2, 21, 252])
def test_edge_rolling_matches_bidask_package(window: int):
    """Our edge_rolling() must match bidask.edge_rolling() on the reference fixture."""
    ours = edge_rolling(df=df, window=window)
    theirs = bidask_pkg.edge_rolling(df=df, window=window)
    np.testing.assert_allclose(ours, theirs, rtol=1e-10, atol=1e-10)


def test_edge_expanding_matches_bidask_package():
    """Our edge_expanding() must match bidask.edge_expanding() on the reference fixture."""
    ours = edge_expanding(df=df, min_periods=21)
    theirs = bidask_pkg.edge_expanding(df=df, min_periods=21)
    np.testing.assert_allclose(ours, theirs, rtol=1e-10, atol=1e-10)


# ===========================================================================
# 3. Competitor estimators: Roll (1984), Corwin-Schultz (2012), Abdi-Ranaldo (2017)
# ===========================================================================

# --- 3a. Snapshot regression tests ------------------------------------------
# Numeric outputs captured once from the committed implementations on the
# reference OHLC fixture. They are not published reference numbers; their
# purpose is regression detection. Tolerance 1e-12 was fixed before use.


def test_roll_snapshot():
    assert roll(df.Open, df.High, df.Low, df.Close) == pytest.approx(
        0.0091074938583031, abs=1e-12
    )


def test_corwin_schultz_snapshot():
    assert corwin_schultz(df.Open, df.High, df.Low, df.Close) == pytest.approx(
        0.0024996788218458, abs=1e-12
    )


def test_corwin_schultz_overnight_snapshot():
    assert corwin_schultz(
        df.Open, df.High, df.Low, df.Close, overnight_adjust=True
    ) == pytest.approx(0.0028568009185977, abs=1e-12)


def test_abdi_ranaldo_snapshot():
    assert abdi_ranaldo(df.Open, df.High, df.Low, df.Close) == pytest.approx(
        0.0072133349635286, abs=1e-12
    )


# --- 3b. Argument / shape validation ----------------------------------------


@pytest.mark.parametrize(
    "fn", [roll, corwin_schultz, abdi_ranaldo], ids=["roll", "cs", "ar"]
)
def test_too_few_observations_returns_nan(fn):
    assert np.isnan(fn([1.0], [1.0], [1.0], [1.0]))


@pytest.mark.parametrize("fn", [corwin_schultz, abdi_ranaldo], ids=["cs", "ar"])
def test_length_mismatch_raises(fn):
    with pytest.raises(ValueError):
        fn(open=[1, 2, 3], high=[1, 2, 3], low=[1, 2], close=[1, 2, 3])


# --- 3c. Flat-price degenerate case -----------------------------------------
# When high == low == close every day there is no high-low range and no
# serial-covariance signal. Each estimator should return either 0 (after
# non-negativity clipping) or NaN rather than silently returning garbage.


@pytest.mark.parametrize(
    "fn", [roll, corwin_schultz, abdi_ranaldo], ids=["roll", "cs", "ar"]
)
def test_flat_prices(fn):
    n = 50
    o = h = l = c = np.full(n, 100.0)
    result = fn(o, h, l, c)
    assert np.isnan(result) or result == pytest.approx(0.0, abs=1e-12)
