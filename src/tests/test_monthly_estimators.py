"""Monthly numeric contracts; no dependency on installed Python bidask."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from estimators.edge import edge
from estimators.abdi_ranaldo import abdi_ranaldo
from estimators.monthly_batch import estimate_batch

REF = Path(__file__).parent / "reference_bidask"


def test_pinned_author_r_oracles():
    inputs = pd.read_csv(REF / "monthly_inputs.csv")
    expected = pd.read_csv(REF / "monthly_expected.csv").set_index("case")
    for name, d in inputs.groupby("case"):
        prices = d.sort_values("position")[["open", "high", "low", "close"]].to_numpy()[
            None
        ]
        result = estimate_batch(prices, np.ones(prices.shape[:2], bool))
        actual = [
            result["edge_signed"][0],
            np.sign(result["roll_s2"][0]) * np.sqrt(abs(result["roll_s2"][0])),
            np.sign(result["ar_s2"][0]) * np.sqrt(abs(result["ar_s2"][0])),
            result["cs_signed"][0],
        ]
        oracle = expected.loc[name].to_numpy(float)
        # The positive-covariance fixture has analytically zero EDGE: identical
        # intraday log offsets. sqrt is ill-conditioned at zero; inspect its
        # underlying squared moment instead of weakening all root tolerances.
        if name == "positive_roll_covariance":
            assert abs(result["edge_s2"][0]) < 1e-17
            assert abs(oracle[0] * abs(oracle[0])) < 1e-17
            actual, oracle = actual[1:], oracle[1:]
        np.testing.assert_allclose(
            actual, oracle, atol=1e-12, rtol=1e-10, equal_nan=True, err_msg=name
        )


def test_batch_matches_part_a_scalar_on_random_and_missing_open():
    rng = np.random.default_rng(32800)
    prices = np.exp(rng.normal(3, 0.05, (200, 23, 4)))
    prices[:, :, 1] = prices.max(axis=2)
    prices[:, :, 2] = prices.min(axis=2)
    prices[::3, ::5, 0] = np.nan
    current = np.ones(prices.shape[:2], bool)
    result = estimate_batch(prices, current)
    for j, p in enumerate(prices):
        assert result["edge_signed"][j] == pytest.approx(
            edge(*p.T, sign=True), rel=1e-10, abs=1e-12
        )
        assert result["ar"][j] == pytest.approx(
            abdi_ranaldo(*p.T), rel=1e-10, abs=1e-12
        )


def test_boundary_uses_only_current_month_moments():
    rng = np.random.default_rng(21)
    p = np.exp(rng.normal(0, 0.02, (1, 9, 4)))
    p[:, :, 1] = p.max(axis=2)
    p[:, :, 2] = p.min(axis=2)
    current = np.ones((1, 9), bool)
    current[:, :2] = False
    result = estimate_batch(p, current, boundary=True)
    # EDGE/AR/CS need one preceding row; Roll needs two, but no older moment.
    for method in ["edge", "ar", "cs", "roll"]:
        offset = 0 if method == "roll" else 1
        expected = estimate_batch(p[:, offset:], np.ones((1, 9 - offset), bool))[
            method
        ][0]
        assert result[method][0] == pytest.approx(expected, abs=1e-12, rel=1e-10)
    baseline = estimate_batch(p, current)
    independent = estimate_batch(p[:, 2:], np.ones((1, 7), bool))
    for m in ["edge", "ar", "cs", "roll"]:
        np.testing.assert_allclose(
            baseline[m], independent[m], equal_nan=True, atol=1e-12
        )


def test_roll_defined_negative_is_zero_but_short_sample_stays_missing():
    c = np.exp(np.array([0.0, 0.01, 0.03, 0.06, 0.10]))
    p = np.stack([c, c * 1.01, c * 0.99, c], axis=1)[None]
    r = estimate_batch(p, np.ones((1, 5), bool))
    assert r["roll_s2"][0] < 0 and r["roll"][0] == 0
    assert r["roll_status"][0] == "ok"
    short = estimate_batch(p[:, :3], np.ones((1, 3), bool))
    assert np.isnan(short["roll"][0])
    assert short["roll_status"][0] == "insufficient_pairs"


def test_negative_edge_conversions_and_missing_are_distinct():
    p = pd.read_csv(Path(__file__).parents[1] / "estimators/_fixtures/ohlc.csv").iloc[
        :10
    ]
    prices = p[["Open", "High", "Low", "Close"]].to_numpy()[None]
    r = estimate_batch(prices, np.ones((1, 10), bool))
    assert r["edge_s2"][0] < 0 and r["edge"][0] == 0 and r["edge_abs"][0] > 0
    prices[:, :, 0] = np.nan
    r = estimate_batch(prices, np.ones((1, 10), bool))
    assert np.isnan(r["edge"][0]) and np.isnan(r["edge_abs"][0])
    assert r["edge_status"][0] == "missing_open"


def test_constant_price_scaling_invariance_and_padding():
    p = pd.read_csv(REF / "monthly_inputs.csv").query("`case` == 'ordinary'")
    p = p[["open", "high", "low", "close"]].to_numpy()[None]
    q = np.pad(p, ((0, 0), (2, 4), (0, 0)), constant_values=np.nan)
    mask = np.isfinite(q[:, :, 3])
    a = estimate_batch(p, np.ones(p.shape[:2], bool))
    b = estimate_batch(q * 7, mask)
    for m in ["edge", "ar", "cs", "roll"]:
        np.testing.assert_allclose(a[m], b[m], atol=1e-12, rtol=1e-10, equal_nan=True)


def test_gap_mask_excludes_pairs_and_both_affected_roll_triples():
    p = np.array(
        [
            [10, 11, 9, 10.5],
            [10, 11, 9, 9.5],
            [12, 13, 11, 12.5],
            [12, 13, 11, 11.5],
            [10, 11, 9, 10.5],
        ],
        dtype=float,
    )[None]
    current = np.ones((1, 5), bool)
    adjacent = np.array([[False, True, False, True, True]])
    r = estimate_batch(p, current, adjacent=adjacent)
    assert r["ar_pairs"][0] == 3 and r["cs_pairs"][0] == 3
    assert r["roll_pairs"][0] == 1 and np.isnan(r["roll"][0])
    h, lo, c = np.log(p[0, :, 1]), np.log(p[0, :, 2]), np.log(p[0, :, 3])
    m = (h + lo) / 2
    terms = 4 * (c[:-1] - m[:-1]) * (c[:-1] - m[1:])
    assert r["ar_s2"][0] == pytest.approx(terms[[0, 2, 3]].mean(), abs=1e-12)
    a = estimate_batch(p, current)
    b = estimate_batch(p, current, adjacent=np.ones((1, 5), bool))
    for method in ["edge", "ar", "cs", "roll"]:
        np.testing.assert_allclose(a[method], b[method], atol=0, rtol=0, equal_nan=True)
