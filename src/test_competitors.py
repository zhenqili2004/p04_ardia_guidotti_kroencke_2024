"""
Tests for the competitor bid-ask spread estimators in `src/estimators/`:
Roll (1984), Corwin-Schultz (2012), and Abdi-Ranaldo (2017).

Test structure:

- Snapshot tests on the bidask reference fixture (`ohlc.csv`) lock in the
  numeric output of each estimator. These values were captured once from the
  committed implementation and fix the tolerance *before* any Monte Carlo
  comparison exercise — regressions will fail loudly.

- Shape / argument validation: wrong lengths raise ValueError; too-few
  observations return NaN.

- Flat-price corner case: when high == low == close every day there is no
  microstructure signal; each estimator must produce either 0 (after
  non-negativity clipping) or NaN rather than silently returning garbage.

Property-based tests against Monte Carlo generated spreads live in the
simulation module (Task A2) and are not duplicated here.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from estimators import abdi_ranaldo, corwin_schultz, roll

FIXTURES = Path(__file__).parent / "estimators" / "_fixtures"
df = pd.read_csv(FIXTURES / "ohlc.csv")


# ---------------------------------------------------------------------------
# Snapshot tests on the reference OHLC fixture.
# These values were produced by the initial commit of each estimator; they
# are not published reference numbers. Their purpose is regression detection.
# Tolerance is 1e-12 (bit-exact up to float jitter), fixed before use.
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Argument / shape validation.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fn", [roll, corwin_schultz, abdi_ranaldo], ids=["roll", "cs", "ar"]
)
def test_too_few_observations_returns_nan(fn):
    assert np.isnan(fn([1.0], [1.0], [1.0], [1.0]))


@pytest.mark.parametrize("fn", [corwin_schultz, abdi_ranaldo], ids=["cs", "ar"])
def test_length_mismatch_raises(fn):
    with pytest.raises(ValueError):
        fn(open=[1, 2, 3], high=[1, 2, 3], low=[1, 2], close=[1, 2, 3])


# ---------------------------------------------------------------------------
# Flat-price corner case.
# When high == low == close every day, there is no high-low range and no
# serial-covariance signal. Each estimator should return either 0
# (after non-negativity clipping) or NaN.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fn", [roll, corwin_schultz, abdi_ranaldo], ids=["roll", "cs", "ar"]
)
def test_flat_prices(fn):
    n = 50
    o = h = l = c = np.full(n, 100.0)
    result = fn(o, h, l, c)
    assert np.isnan(result) or result == pytest.approx(0.0, abs=1e-12)
