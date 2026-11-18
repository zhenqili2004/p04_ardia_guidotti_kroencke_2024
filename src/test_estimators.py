"""
Tests for the EDGE family of bid-ask spread estimators in `src/estimators/`.

Structure:

- `test_edge`, `test_edge_rolling`, `test_edge_expanding`:
  Ported verbatim from the upstream bidask test suite
  (https://github.com/eguidotti/bidask, python/tests/test_edge.py,
  upstream commit 1caba55d63eb, 2025-10-13). Adapted to read the two
  reference OHLC CSVs from `estimators/_fixtures/` instead of fetching
  them over the network, so CI is self-contained.

- `test_edge_matches_bidask_package`:
  Oracle differential test. Our implementation (src/estimators) must match
  the installed `bidask` package bit-for-bit on the reference fixture. This
  is the "package is the oracle, your code is what is being tested" check
  called out in PROJECT_SPEC.md §2 Rubric and is the test that WILL fail
  once we re-derive the estimators from the paper's equations instead of
  porting the reference code verbatim — at which point the tolerance below
  becomes load-bearing.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from estimators import edge, edge_expanding, edge_rolling

FIXTURES = Path(__file__).parent / "estimators" / "_fixtures"
df = pd.read_csv(FIXTURES / "ohlc.csv")
df_miss = pd.read_csv(FIXTURES / "ohlc-miss.csv")


def test_edge():
    """
    Compares the `edge` function to the known test case.
    """
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
    """
    Compares the rolling vectorized implementation to the original function.

    Parameters
    ----------
    - `window` : int
        The rolling window size.
    - `step`: int
        Evaluate the window at every step result.
    - `sign`: bool
        Whether to use signed estimates.
    """
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
    """
    Compares the expanding vectorized implementation to the original function.

    Parameters
    ----------
    - `min_periods` : int
        Minimum number of observations in window required to have a value;
        otherwise, result is np.nan.
    - `sign`: bool
        Whether to use signed estimates.
    """
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


# ---------------------------------------------------------------------------
# Oracle differential test: our estimators vs. installed `bidask` package.
# ---------------------------------------------------------------------------
# While our code is a verbatim port of the upstream reference, this test is
# tautologically green. It exists so that when we later re-derive the
# estimator from Ardia, Guidotti, & Kroencke's equations, this test becomes
# the load-bearing comparison against the oracle. The tolerance (1e-10) is
# fixed here, before we see our independent implementation's results.
# ---------------------------------------------------------------------------

bidask_pkg = pytest.importorskip(
    "bidask",
    reason="bidask package not installed; skipping oracle differential test",
)


def test_edge_matches_bidask_package():
    """Our edge() must match the installed bidask.edge() on the reference fixture."""
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
