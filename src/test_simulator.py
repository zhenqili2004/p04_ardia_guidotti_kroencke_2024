"""
Tests for the OHLC simulator in `src/simulator.py`.

- Shape and invariants: output has the requested dimensions, each row's
  High is the largest of its OHLC entries and Low the smallest.
- Seed reproducibility: identical seeds produce identical output.
- Empty-period fallback: with prob=0 every period inherits the previous
  period's close, so every row is flat (Open==High==Low==Close) and the
  entire table is a single repeated price.
- Statistical sanity: on a modest number of trials the EDGE estimator
  applied to the simulated OHLC recovers the true spread within a few
  basis points. This is a bridge between the simulator and the estimator
  package — a cheap end-to-end "the pieces plug together" check.
"""

import numpy as np
import pytest

from estimators import edge
from simulator import simulate_ohlc


def test_shape_and_columns():
    df = simulate_ohlc(n=100, trades=20, rng=np.random.default_rng(0))
    assert df.shape == (100, 4)
    assert list(df.columns) == ["Open", "High", "Low", "Close"]


def test_ohlc_invariants():
    df = simulate_ohlc(n=500, trades=50, spread=0.01, rng=np.random.default_rng(1))
    row_max = df[["Open", "High", "Low", "Close"]].max(axis=1)
    row_min = df[["Open", "High", "Low", "Close"]].min(axis=1)
    assert (df.High >= row_max - 1e-12).all()
    assert (df.Low <= row_min + 1e-12).all()
    assert (df.High >= df.Low).all()


def test_seed_reproducibility():
    a = simulate_ohlc(n=100, trades=20, rng=np.random.default_rng(42))
    b = simulate_ohlc(n=100, trades=20, rng=np.random.default_rng(42))
    np.testing.assert_array_equal(a.values, b.values)


def test_prob_zero_gives_flat_output():
    # No tick is ever observed, so every period falls back to prev_close.
    # prev_close is seeded with p[0] (the first simulated tick), so the whole
    # table is one repeated value.
    df = simulate_ohlc(n=50, trades=10, prob=0.0, rng=np.random.default_rng(7))
    first = df.iloc[0, 0]
    assert np.allclose(df.values, first)


@pytest.mark.parametrize("true_spread", [0.005, 0.01, 0.02])
def test_edge_recovers_true_spread(true_spread):
    # Single long simulation; EDGE should land within a few bps of the truth
    # at prob=1 and 390 ticks/period (same regime as the author's reference
    # fixture, which produces 0.01018 on a true spread of 0.01).
    df = simulate_ohlc(
        n=5000,
        trades=390,
        prob=1.0,
        spread=true_spread,
        volatility=0.03,
        rng=np.random.default_rng(2024),
    )
    est = edge(df.Open, df.High, df.Low, df.Close)
    assert abs(est - true_spread) < 0.001, f"EDGE={est:.4f} vs true={true_spread}"
