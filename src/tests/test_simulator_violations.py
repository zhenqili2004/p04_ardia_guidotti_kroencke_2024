"""
Tests for the extension's simulator, `simulations.violations`, and for the
bar-building helper `extract_ohlc` it shares with `simulate_ohlc`.

1. Nesting: with every switch off, simulate_ohlc_violations returns exactly
   (byte for byte) what simulate_ohlc returns for the same seed, so the
   replication's Monte Carlo is a special case of the extension's. With
   every slot trading (prob = 1), the two sign-persistence models coincide.
2. extract_ohlc (vectorized) picks the same prices as the per-bar loop it
   replaced, including bars without trades and signed prices.
3. Each switch does what it says: OHLC invariants hold; signs have the
   requested autocorrelation under each persistence model; only trades move
   the price; auction prints carry no bounce; tick prices sit on the grid;
   bad parameters fail loudly.
4. Ground truth matches formulas derived by hand:
   - with prob = p < 1, the time between consecutive trades is geometric,
     and the gaps that straddle a bar boundary are length-biased:
     E[gap] = (2 - p) / p, and under "time" persistence
     E[rho ** gap] = p^2 rho / (1 - rho (1 - p))^2; under "trade"
     persistence the boundary correlation stays rho;
   - EDGE's target (S_o^2 + S_c^2) / 2 is the spread of the open and close
     trades, so an opening auction halves it on the squared scale;
   - with MRR-type "surprise" impact the realized spread is
     S * (1 - alpha * (1 - rho^2)), while the effective spread stays S.
   Tolerances are at least 5 standard deviations of the seed-to-seed spread
   measured while writing the tests (noted at each test).
"""

import numpy as np
import pytest

from simulations import simulate_ohlc, simulate_ohlc_violations
from simulations.simulator import extract_ohlc
from simulations.violations import _impact_log, _markov_signs, _slot_signs

OHLC = ["Open", "High", "Low", "Close"]


# ===========================================================================
# 1. Nesting
# ===========================================================================


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n": 200, "trades": 30},
        {"n": 200, "trades": 30, "prob": 0.05},  # many bars without trades
        {"n": 200, "trades": 30, "prob": 0.3, "overnight": 0.02, "drift": 0.001},
    ],
    ids=["dense", "thin", "overnight_drift"],
)
def test_switches_off_reproduce_simulate_ohlc(kwargs):
    expected = simulate_ohlc(rng=np.random.default_rng(7), **kwargs).to_numpy()
    got = simulate_ohlc_violations(rng=np.random.default_rng(7), **kwargs).to_numpy()
    assert got.tobytes() == expected.tobytes()


def test_persistence_models_coincide_when_every_slot_trades():
    kw = {"n": 200, "trades": 30, "rho": 0.5, "alpha": 0.4}
    by_time = simulate_ohlc_violations(rng=np.random.default_rng(8), **kw)
    by_trade = simulate_ohlc_violations(
        persistence="trade", rng=np.random.default_rng(8), **kw
    )
    assert by_trade.to_numpy().tobytes() == by_time.to_numpy().tobytes()


# ===========================================================================
# 2. extract_ohlc vs the per-bar loop it replaced
# ===========================================================================


def _extract_ohlc_loop(p, keep, n, trades):
    """The per-bar loop that simulate_ohlc used before extract_ohlc existed."""
    p_mat, keep_mat = p.reshape(n, trades), keep.reshape(n, trades)
    ohlc = np.empty((n, 4))
    prev_close = p[0]
    for i in range(n):
        if keep_mat[i].any():
            obs = p_mat[i, keep_mat[i]]
            ohlc[i] = [
                obs[0],
                obs[np.argmax(np.abs(obs))],
                obs[np.argmin(np.abs(obs))],
                obs[-1],
            ]
            prev_close = obs[-1]
        else:
            ohlc[i] = prev_close
    return ohlc


@pytest.mark.parametrize("prob", [1.0, 0.2, 0.02])
def test_extract_ohlc_matches_per_bar_loop(prob):
    rng = np.random.default_rng(3)
    n, trades = 300, 12
    # Signed prices (as with simulate_ohlc(sign=True)) with repeated values,
    # so High/Low ties and |price| ordering are both exercised.
    p = rng.choice([-1.0, 1.0], n * trades) * rng.integers(90, 110, n * trades)
    keep = rng.random(n * trades) < prob
    keep[:trades] = False  # first bar has no trade: falls back to p[0]
    np.testing.assert_array_equal(
        extract_ohlc(p, keep, n, trades), _extract_ohlc_loop(p, keep, n, trades)
    )


# ===========================================================================
# 3. Each switch does what it says
# ===========================================================================

VIOLATIONS = {
    "order_splitting": {"rho": 0.6},
    "splitting_trade_to_trade": {"rho": 0.6, "persistence": "trade"},
    "price_impact": {"alpha": 0.5},
    "impact_on_sign": {"rho": 0.5, "alpha": 0.5, "impact": "sign"},
    "open_auction": {"auction_open": True},
    "both_auctions": {"auction_open": True, "auction_close": True},
    "tick_grid": {"tick": 0.005},
    "everything": {"rho": 0.5, "alpha": 0.3, "auction_open": True, "tick": 0.005},
}


@pytest.mark.parametrize("case", VIOLATIONS)
def test_ohlc_invariants_hold_under_each_violation(case):
    bars = simulate_ohlc_violations(
        n=300, trades=40, prob=0.5, rng=np.random.default_rng(1), **VIOLATIONS[case]
    )
    assert list(bars.columns) == OHLC and bars.shape == (300, 4)
    assert (bars.High >= bars[["Open", "Close"]].max(axis=1)).all()
    assert (bars.Low <= bars[["Open", "Close"]].min(axis=1)).all()
    assert (bars.to_numpy() > 0).all()


def test_same_seed_same_output_with_violations():
    kw = {"n": 200, "trades": 30, **VIOLATIONS["everything"]}
    a = simulate_ohlc_violations(rng=np.random.default_rng(9), **kw)
    b = simulate_ohlc_violations(rng=np.random.default_rng(9), **kw)
    assert a.equals(b)


@pytest.mark.parametrize("rho", [0.5, -0.3])
def test_markov_signs_have_requested_autocorrelation(rho):
    # 200,000 signs: the lag-1 sample autocorrelation has SD about
    # sqrt((1 - rho^2) / m) < 0.003, so +/- 0.02 is over 6 SD.
    signs = _markov_signs(200_000, rho, np.random.default_rng(1))
    assert set(np.unique(signs)) == {-1, 1}
    assert np.corrcoef(signs[1:], signs[:-1])[0, 1] == pytest.approx(rho, abs=0.02)
    assert abs(signs.mean()) < 0.02  # buys and sells equally likely


@pytest.mark.parametrize("persistence", ["trade", "time"])
def test_sign_autocorrelation_between_consecutive_trades(persistence):
    # One slot in five trades (p = 0.2), rho = 0.5. Under "trade" persistence
    # consecutive trades keep correlation rho. Under "time" persistence the
    # slots between two trades are geometric, so the correlation is
    # E[rho ** G] = p rho / (1 - (1 - p) rho) = 1/6. About 40,000 trades:
    # SD of the sample autocorrelation < 0.005; tolerance 0.03.
    p, rho = 0.2, 0.5
    chain = _markov_signs(200_000, rho, np.random.default_rng(1))
    trade_idx = np.flatnonzero(np.random.default_rng(2).random(200_000) < p)
    signs = _slot_signs(chain, trade_idx, persistence)[trade_idx]
    expected = rho if persistence == "trade" else p * rho / (1 - (1 - p) * rho)
    assert np.corrcoef(signs[1:], signs[:-1])[0, 1] == pytest.approx(expected, abs=0.03)


@pytest.mark.parametrize(
    "persistence, expected",
    [
        # u = (1, 1 - 0.5**3, -1 - 0.5**1) = (1, 0.875, -1.5)
        ("time", [0, 0, 1, 1, 1, 1.875, 0.375, 0.375]),
        # u = (1, 1 - 0.5, -1 - 0.5) = (1, 0.5, -1.5)
        ("trade", [0, 0, 1, 1, 1, 1.5, 0, 0]),
    ],
)
def test_only_trades_move_the_price(persistence, expected):
    # Eight slots; trades at slots 1, 4, 5 with signs +1, +1, -1; rho = 0.5,
    # alpha = 1 and spread = 2 so each unit of surprise moves log M by 1.
    # A trade moves the price from the next slot on; empty slots add nothing.
    # The surprise subtracts E[D | previous trade]: rho ** (slots apart) under
    # "time", rho under "trade".
    sign = np.array([1, 1, 1, 1, 1, -1, 1, 1])
    impact = _impact_log(
        sign,
        np.array([1, 4, 5]),
        rho=0.5,
        alpha=1.0,
        spread=2.0,
        impact="surprise",
        persistence=persistence,
    )
    np.testing.assert_allclose(impact, expected, atol=1e-12)


@pytest.mark.parametrize(
    "auction_open, auction_close", [(True, False), (False, True), (True, True)]
)
def test_auction_prints_have_no_bounce(auction_open, auction_close):
    # With zero volatility and no impact the efficient price stays at 1, so
    # continuous trades print at 1 +/- spread/2 and auction prints at 1.
    bars = simulate_ohlc_violations(
        n=50,
        trades=20,
        spread=0.02,
        volatility=0.0,
        auction_open=auction_open,
        auction_close=auction_close,
        rng=np.random.default_rng(4),
    )
    no_bounce, with_bounce = {1.0}, {0.99, 1.01}
    opens, closes = set(bars.Open.round(12)), set(bars.Close.round(12))
    assert opens == (no_bounce if auction_open else with_bounce)
    assert closes == (no_bounce if auction_close else with_bounce)


@pytest.mark.parametrize(
    "spread, tick, auction_open",
    [(0.0, 0.01, False), (0.02, 0.005, False), (0.02, 0.005, True)],
    ids=["pure_grid", "spread_on_grid", "auction_on_grid"],
)
def test_tick_grid_prices_lie_on_the_grid(spread, tick, auction_open):
    bars = simulate_ohlc_violations(
        n=200,
        trades=30,
        spread=spread,
        volatility=0.01,
        tick=tick,
        auction_open=auction_open,
        rng=np.random.default_rng(5),
    )
    units = bars.to_numpy() / tick
    np.testing.assert_allclose(units, np.round(units), atol=1e-9)


@pytest.mark.parametrize(
    "bad",
    [
        {"rho": 1.5},
        {"persistence": "bogus"},
        {"alpha": -0.1},
        {"impact": "bogus"},
        {"tick": 0.0},
    ],
    ids=["rho", "persistence", "alpha", "impact", "tick"],
)
def test_invalid_parameters_raise(bad):
    with pytest.raises(ValueError):
        simulate_ohlc_violations(n=10, trades=5, rng=np.random.default_rng(0), **bad)


# ===========================================================================
# 4. Ground truth against hand-derived formulas
# ===========================================================================


def test_truth_without_violations():
    _, truth = simulate_ohlc_violations(
        n=500, trades=30, spread=0.01, return_truth=True, rng=np.random.default_rng(0)
    )
    assert truth["effective_spread"] == pytest.approx(0.01, rel=1e-9)
    assert truth["effective_spread_open_close"] == pytest.approx(0.01, rel=1e-9)
    assert truth["realized_spread"] == pytest.approx(0.01, rel=1e-9)
    assert truth["quoted_spread"] == 0.01
    assert truth["boundary_gap_mean"] == 1.0  # every slot trades
    assert truth["trades_per_bar"] == 30.0


@pytest.mark.parametrize(
    "auction_close, open_close_factor",
    [(False, 1 / np.sqrt(2)), (True, 0.0)],
    ids=["open_auction", "both_auctions"],
)
def test_open_close_spread_under_auctions(auction_close, open_close_factor):
    # 20 trades per bar. The auction print(s) pay no spread and every other
    # trade pays S, so EDGE's target sqrt((S_o^2 + S_c^2) / 2) is S / sqrt(2)
    # (open auction) or 0 (both), while the all-trade RMS is
    # S * sqrt(19/20) or S * sqrt(18/20).
    spread = 0.01
    _, truth = simulate_ohlc_violations(
        n=200,
        trades=20,
        spread=spread,
        auction_open=True,
        auction_close=auction_close,
        return_truth=True,
        rng=np.random.default_rng(0),
    )
    paying = 18 if auction_close else 19
    assert truth["effective_spread"] == pytest.approx(
        spread * np.sqrt(paying / 20), rel=1e-9
    )
    assert truth["effective_spread_open_close"] == pytest.approx(
        spread * open_close_factor, abs=1e-12
    )


def test_boundary_correlation_when_every_slot_trades():
    # The boundary trades are one slot apart, so rho_b = rho. 4,000 pairs:
    # SD of the realised mean is about sqrt(0.75 / 4000) = 0.014; +/- 0.07
    # is 5 SD.
    _, truth = simulate_ohlc_violations(
        n=4000, trades=20, rho=0.5, return_truth=True, rng=np.random.default_rng(2)
    )
    assert truth["rho_b_expected"] == pytest.approx(0.5)
    assert truth["rho_b_realized"] == pytest.approx(0.5, abs=0.07)


@pytest.mark.parametrize("persistence", ["time", "trade"])
def test_boundary_correlation_with_minutes_without_trades(persistence):
    # One slot in five trades (p = 0.2). The two boundary trades are still
    # adjacent trades, but the slots between them are length-biased:
    #   E[gap] = (2 - p) / p = 9 slots, under either persistence.
    # Their sign correlation is rho = 0.5 under "trade" persistence, and
    #   E[rho ** gap] = p^2 rho / (1 - rho (1 - p))^2 = 0.0556 under "time".
    # 15,000 bars. SD of the gap mean: sqrt(2 (1 - p) / p^2 / n) = 0.05; of
    # rho_b_realized: sqrt((1 - rho_b^2) / n) = 0.008 (time) / 0.007
    # (trade); measured over 40 other seeds: 0.048, 0.009 / 0.006, and
    # 0.0008 for rho_b_expected (time). Tolerances 0.5, 0.05 / 0.09 and 0.01
    # are at least 5.6 SD.
    p, rho = 0.2, 0.5
    _, truth = simulate_ohlc_violations(
        n=15000,
        trades=50,
        prob=p,
        rho=rho,
        persistence=persistence,
        return_truth=True,
        rng=np.random.default_rng(3),
    )
    assert truth["boundary_gap_mean"] == pytest.approx((2 - p) / p, abs=0.5)
    if persistence == "trade":
        assert truth["rho_b_expected"] == pytest.approx(rho)
        assert truth["rho_b_realized"] == pytest.approx(rho, abs=0.09)
    else:
        expected = p**2 * rho / (1 - rho * (1 - p)) ** 2
        assert truth["rho_b_expected"] == pytest.approx(expected, abs=0.01)
        assert truth["rho_b_realized"] == pytest.approx(expected, abs=0.05)


@pytest.mark.parametrize(
    "rho, alpha, prob, persistence",
    [(0.0, 0.5, 1.0, "time"), (0.5, 0.5, 1.0, "time"), (0.5, 0.5, 0.3, "trade")],
)
def test_realized_spread_under_surprise_impact(rho, alpha, prob, persistence):
    # Trade k at P = M_k (1 + D_k S/2) moves the price by alpha (S/2) u_k with
    # u_k = D_k - rho D_prev (consecutive trades have correlation rho in all
    # three cases). E[D_k u_k] = 1 - rho^2 and E[D_k u_j] = 0 for later
    # trades j, so E[realized] = S (1 - alpha (1 - rho^2)) at any horizon;
    # the effective spread is S exactly. 25,000 bars; measured SD of
    # realized / S over 40 other seeds: 0.0028, 0.0033 and 0.0029, so the
    # tolerance 0.025 is at least 7 SD.
    spread = 0.01
    _, truth = simulate_ohlc_violations(
        n=25000,
        trades=10,
        prob=prob,
        spread=spread,
        rho=rho,
        persistence=persistence,
        alpha=alpha,
        return_truth=True,
        rng=np.random.default_rng(6),
    )
    assert truth["effective_spread"] == pytest.approx(spread, rel=1e-9)
    factor = 1 - alpha * (1 - rho**2)
    assert truth["realized_spread"] / spread == pytest.approx(factor, abs=0.025)
