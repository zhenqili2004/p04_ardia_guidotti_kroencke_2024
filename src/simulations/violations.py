"""
OHLC simulator that breaks the paper's assumptions one switch at a time.

`simulate_ohlc_violations` extends `simulations.simulator.simulate_ohlc`
(the paper's Monte Carlo model, Section 4.1) with switches for the ways
real order flow departs from Assumptions 1-3 of Ardia, Guidotti & Kroencke
(2024):

- `rho`, `persistence`: autocorrelated trade signs (order splitting), which
  makes bid-ask bounces correlated (violates Assumption 3);
- `alpha`, `impact`: permanent price impact (informed trading), which
  correlates fundamental returns with bounces (violates Assumption 2);
- `auction_open`, `auction_close`: opening / closing auction prints;
- `tick`: a price grid;
- trading frequency, through the existing `trades` and `prob`.

With every switch off it returns exactly what `simulate_ohlc` returns for
the same generator state (same draws, same order), so it nests the
replication's Monte Carlo. Bars are built by the same `extract_ohlc`.

Time slots and trades
---------------------
Each bar has `trades` time slots (390 = one per minute), and each slot has
a trade with probability `prob`. `prob < 1` therefore means minutes without
trading, as in the paper ("prices are observed with a given probability";
its Fig. 2 plots the average number of trades per day). By construction the
previous bar's close and the next bar's open are adjacent trades: no trade
happens between them, though several empty minutes may.

Model (in time order across all bars)
-------------------------------------
    D          trade sign, +1 buy / -1 sell, from a Markov chain that keeps
               the previous sign with probability (1 + rho) / 2. With
               rho = 0, independent fair signs. Where the chain runs is set
               by `persistence`:
                 "time"  (default) the chain runs over every time slot, so
                         persistence also decays through minutes without a
                         trade: two adjacent trades Delta slots apart have
                         sign correlation rho ** Delta;
                 "trade" the chain runs over trades only, so adjacent trades
                         have correlation rho however far apart they are
                         (the trade-to-trade definition of Choi, Salandro &
                         Shastri 1988).
               With prob = 1 the two are identical.
    log M      efficient log price at each slot: cumsum of
               N(drift/trades, (volatility/sqrt(trades))^2) returns, plus
               overnight jumps, plus alpha * (spread/2) * u_j for every
               earlier trade j (permanent impact; a trade moves the price
               from the next slot on). Slots without a trade have no impact.
    u_j        "surprise" (default): D_j - E[D_j | previous trade], the
               unexpected part of order flow as in Madhavan, Richardson &
               Roomans (1997); E[D_j | previous trade] = rho * D_prev under
               "trade" persistence and rho ** Delta * D_prev under "time".
               "sign": u_j = D_j. With rho > 0, "sign" makes prices drift
               predictably after each run of buys, which itself violates
               Assumption 1; it is offered only as a comparison.
    P          trade price: M * (1 + D * spread/2). With a tick grid, buys
               pay ceil(M (1 + spread/2) / tick) * tick and sells receive
               floor(M (1 - spread/2) / tick) * tick, so the quoted spread
               is at least one tick. (spread = 0 gives the pure grid:
               bid = floor(M/tick) * tick, ask = bid + tick.) `tick` is in
               units of the initial price, which is 1.
    auctions   the first (last) trade of each bar prints at the efficient
               price itself, with no bounce (rounded to the grid if there
               is one). Signs and impact are unchanged.

Two ways to thin trading
------------------------
They test different things, so results should report them separately:

- fewer `trades` per bar with `prob = 1`: only the number of trades per bar
  changes. With few trades per bar under order splitting, the high and low
  trades sit close to the boundary trades and share their sign persistence,
  so E[x1] ~ S^2 no longer holds. The paper's pi coefficients do not correct
  this; they correct only the case where the open (close) trade is itself
  the high or low (Appendix A.2).
- `prob < 1`: also spaces trades apart in time, so under `persistence="time"`
  the boundary correlation rho_b falls as well.

Ground truth (`return_truth=True`)
----------------------------------
Measured on the simulated path, not plugged in from formulas:

    rho_b_realized     mean of D_open,t * D_close,t-1 over bars t that have
                       a trade, where D_close,t-1 is the last trade before
                       bar t (the two adjacent trades at the boundary). This
                       is what rho_hat estimates under either persistence.
    rho_b_expected     its expected value given which slots traded: rho
                       under "trade" persistence, mean of rho ** Delta under
                       "time".
    boundary_gap_mean  mean number of time slots Delta between those two
                       trades (1 when every slot trades).
    effective_spread   root mean square over all trades of
                       2 * D * (P - M) / M, the paper's Eq. (1) (equal to
                       `spread` with no tick and no auction).
    effective_spread_open_close
                       sqrt((S_o^2 + S_c^2) / 2), where S_o^2 (S_c^2) is the
                       mean squared effective spread of the bars' open
                       (close) trades. This is what EDGE targets (Eqs. 19-20).
                       It equals `effective_spread` when every trade pays the
                       same spread; with an opening auction S_o = 0, so it is
                       effective_spread / sqrt(2).
    realized_spread    mean over trades of
                       2 * D * ((P - M) / M - (I_{k+h} - I_k)),
                       where I is the cumulative impact in log price and the
                       horizon h is `trades` time slots (one bar). Only the
                       trade-driven part of the future price move is used:
                       the exogenous returns are independent of D and would
                       add noise but no bias. Trades without a full horizon
                       left are dropped. Equals effective_spread when
                       alpha = 0.
    quoted_spread      mean over trades of (ask - bid) / M; equal to `spread`
                       without a tick grid.
    trades_per_bar     mean number of trades per bar (trades x prob in
                       expectation).
"""

from typing import Literal

import numpy as np
import pandas as pd

from .simulator import extract_ohlc


def _markov_signs(m: int, rho: float, rng: np.random.Generator) -> np.ndarray:
    """
    Draw m trade signs (+1/-1) with lag-1 autocorrelation rho.

    The first sign is a fair coin; each later sign repeats the previous one
    with probability (1 + rho) / 2. Vectorized with the parity of the
    cumulative number of flips.
    """
    first = 1 if rng.integers(0, 2) == 1 else -1
    flips = rng.random(m) >= (1.0 + rho) / 2.0
    flips[0] = False
    return np.where(np.cumsum(flips) % 2 == 0, first, -first)


def _slot_signs(
    chain: np.ndarray, trade_idx: np.ndarray, persistence: str
) -> np.ndarray:
    """
    Assign the Markov chain to time slots.

    "time": slot k gets chain[k], so persistence decays through empty slots.
    "trade": the j-th trade gets chain[j], so adjacent trades are one chain
    step apart; slots without a trade get +1 (they never trade, so it is
    never used).
    """
    if persistence == "time":
        return chain
    sign = np.ones(chain.size, dtype=chain.dtype)
    sign[trade_idx] = chain[: trade_idx.size]
    return sign


def _impact_log(
    sign: np.ndarray,
    trade_idx: np.ndarray,
    *,
    rho: float,
    alpha: float,
    spread: float,
    impact: str,
    persistence: str,
) -> np.ndarray:
    """
    Cumulative permanent impact in log price at each slot.

    Only trades move the price: trade j adds alpha * (spread/2) * u_j from
    the next slot on. Entry k is the impact of all trades before slot k.
    """
    m = sign.size
    impact_log = np.zeros(m)
    if alpha == 0 or trade_idx.size == 0:
        return impact_log
    d = sign[trade_idx].astype(float)
    u = d.copy()
    if impact == "surprise" and rho != 0:
        # E[D_j | previous trade]: one chain step ("trade") or Delta steps.
        lag = np.diff(trade_idx) if persistence == "time" else 1
        u[1:] -= float(rho) ** lag * d[:-1]
    steps = np.zeros(m)
    steps[trade_idx] = alpha * (spread / 2.0) * u
    impact_log[1:] = np.cumsum(steps)[:-1]
    return impact_log


def _first_last_trades(keep: np.ndarray, n: int, trades: int):
    """Flat indices of each bar's first and last trade, and which bars trade."""
    keep_mat = keep.reshape(n, trades)
    has_trade = keep_mat.any(axis=1)
    offsets = np.arange(n) * trades
    first = offsets + np.argmax(keep_mat, axis=1)
    last = offsets + trades - 1 - np.argmax(keep_mat[:, ::-1], axis=1)
    return first, last, has_trade


def _ground_truth(
    *,
    sign: np.ndarray,
    price: np.ndarray,
    efficient: np.ndarray,
    impact_log: np.ndarray,
    bid: np.ndarray | None,
    ask: np.ndarray | None,
    keep: np.ndarray,
    n: int,
    trades: int,
    rho: float,
    persistence: str,
    spread: float,
) -> dict:
    """Measure the quantities documented in the module docstring on one path."""
    traded = np.flatnonzero(keep)
    first, last, has_trade = _first_last_trades(keep, n, trades)
    opens, closes = first[has_trade], last[has_trade]

    # Boundary pairs: first trade of bar t and the last trade before it
    # (skipping bars without trades, as the OHLC rows do).
    pos = np.searchsorted(traded, opens)  # position of each open among trades
    has_prev = pos > 0
    open_idx = opens[has_prev]
    prev_idx = traded[pos[has_prev] - 1]
    gap = open_idx - prev_idx
    if open_idx.size:
        rho_b_realized = float(np.mean(sign[open_idx] * sign[prev_idx]))
        lag = gap if persistence == "time" else np.ones_like(gap)
        rho_b_expected = float(np.mean(float(rho) ** lag))
        boundary_gap_mean = float(np.mean(gap))
    else:
        rho_b_realized = rho_b_expected = boundary_gap_mean = np.nan

    # Per-trade effective spread, the paper's Eq. (1).
    es = np.full(price.size, np.nan)
    es[traded] = 2.0 * sign[traded] * (price[traded] - efficient[traded])
    es[traded] /= efficient[traded]
    if traded.size:
        effective_spread = float(np.sqrt(np.mean(es[traded] ** 2)))
        s2_open, s2_close = np.mean(es[opens] ** 2), np.mean(es[closes] ** 2)
        effective_spread_open_close = float(np.sqrt((s2_open + s2_close) / 2.0))
    else:
        effective_spread = effective_spread_open_close = np.nan

    k = traded[traded + trades < price.size]
    if k.size:
        future_impact = impact_log[k + trades] - impact_log[k]
        rel_dev = (price[k] - efficient[k]) / efficient[k]
        realized_spread = float(np.mean(2.0 * sign[k] * (rel_dev - future_impact)))
    else:
        realized_spread = np.nan

    if bid is None or ask is None:
        quoted_spread = float(spread)
    elif traded.size:
        quoted = (ask[traded] - bid[traded]) / efficient[traded]
        quoted_spread = float(np.mean(quoted))
    else:
        quoted_spread = np.nan

    return {
        "rho_b_realized": rho_b_realized,
        "rho_b_expected": rho_b_expected,
        "boundary_gap_mean": boundary_gap_mean,
        "effective_spread": effective_spread,
        "effective_spread_open_close": effective_spread_open_close,
        "realized_spread": realized_spread,
        "quoted_spread": quoted_spread,
        "trades_per_bar": float(traded.size / n),
    }


def simulate_ohlc_violations(
    n: int = 10000,
    trades: int = 390,
    prob: float = 1.0,
    spread: float = 0.01,
    volatility: float = 0.03,
    overnight: float = 0.0,
    drift: float = 0.0,
    rho: float = 0.0,
    persistence: Literal["time", "trade"] = "time",
    alpha: float = 0.0,
    impact: Literal["surprise", "sign"] = "surprise",
    auction_open: bool = False,
    auction_close: bool = False,
    tick: float | None = None,
    return_truth: bool = False,
    rng: np.random.Generator | None = None,
) -> pd.DataFrame | tuple[pd.DataFrame, dict]:
    """
    Simulate OHLC bars with switches that violate EDGE's assumptions.

    See the module docstring for the model and the ground-truth definitions.

    Parameters
    ----------
    n, spread, volatility, overnight, drift
        As in `simulations.simulator.simulate_ohlc`.
    trades : int, default 390
        Time slots per bar (390 = one per minute of a NYSE session).
    prob : float, default 1.0
        Probability that a time slot has a trade. With prob = 1 every bar
        has `trades` trades.
    rho : float, default 0.0
        Lag-1 autocorrelation of trade signs, in [-1, 1]. 0 gives
        independent signs.
    persistence : {"time", "trade"}, default "time"
        Whether sign persistence decays per time slot ("time") or passes
        from trade to trade ("trade"). Identical when prob = 1.
    alpha : float, default 0.0
        Permanent price impact, as a fraction of the half-spread per unit
        of `impact` (0 = no information in trades). Must be >= 0.
    impact : {"surprise", "sign"}, default "surprise"
        What moves the price: the unexpected part of the sign (default) or
        the sign itself (comparison only; see the module docstring).
    auction_open, auction_close : bool, default False
        Whether each bar's first / last trade is an auction print at the
        efficient price.
    tick : float or None, default None
        Price grid in units of the initial price (1). None means no grid.
    return_truth : bool, default False
        If True, also return the ground-truth dictionary.
    rng : np.random.Generator, optional
        NumPy random generator. If None, `np.random.default_rng()` is used.

    Returns
    -------
    pd.DataFrame or (pd.DataFrame, dict)
        Columns ['Open', 'High', 'Low', 'Close'] with `n` rows; plus the
        ground truth if `return_truth` is True.

    Raises
    ------
    ValueError
        On parameters outside their ranges, or if a tick grid pushes a bid
        to zero or below (the tick is too coarse for the simulated path).
    """
    if not -1.0 <= rho <= 1.0:
        raise ValueError(f"rho must be in [-1, 1], got {rho}")
    if persistence not in ("time", "trade"):
        raise ValueError(f"persistence must be 'time' or 'trade', got {persistence!r}")
    if alpha < 0:
        raise ValueError(f"alpha must be >= 0, got {alpha}")
    if impact not in ("surprise", "sign"):
        raise ValueError(f"impact must be 'surprise' or 'sign', got {impact!r}")
    if tick is not None and tick <= 0:
        raise ValueError(f"tick must be positive or None, got {tick}")
    if rng is None:
        rng = np.random.default_rng()

    m = n * trades

    # Random draws, in simulate_ohlc's order: returns, overnight jumps,
    # signs, then which slots trade.
    r = rng.normal(loc=drift / trades, scale=volatility / np.sqrt(trades), size=m)
    if overnight > 0:
        period_starts = np.arange(n) * trades
        r[period_starts] += rng.normal(loc=0.0, scale=overnight, size=n)
    if rho == 0:
        # Independent signs: the same draw as simulate_ohlc, so the bounce
        # is bit-identical to it (persistence is irrelevant).
        side = rng.integers(0, 2, size=m)  # 1 = buy, 0 = sell
        chain = None
    else:
        chain = _markov_signs(m, rho, rng)
    keep = rng.random(m) < prob
    trade_idx = np.flatnonzero(keep)

    if chain is None:
        sign = 2 * side - 1
    else:
        sign = _slot_signs(chain, trade_idx, persistence)
        side = (sign + 1) // 2
    z = spread * (side - 0.5)  # +/- spread/2

    # Efficient log price, with permanent impact from earlier trades.
    log_m = np.cumsum(r)
    impact_log = _impact_log(
        sign,
        trade_idx,
        rho=rho,
        alpha=alpha,
        spread=spread,
        impact=impact,
        persistence=persistence,
    )
    if alpha > 0:
        log_m = log_m + impact_log
    efficient = np.exp(log_m)

    # Trade prices.
    if tick is None:
        p = efficient * (1.0 + z)
        bid = ask = None
    else:
        bid = np.floor(efficient * (1.0 - spread / 2.0) / tick) * tick
        ask = np.ceil(efficient * (1.0 + spread / 2.0) / tick) * tick
        if (bid <= 0).any():
            raise ValueError(
                f"tick={tick} is too coarse for this price path: some bids "
                "round to zero. Use a smaller tick, lower volatility or fewer bars."
            )
        p = np.where(side == 1, ask, bid)

    # Auction prints replace the bounce at the open / close of each bar.
    if auction_open or auction_close:
        auction_price = efficient if tick is None else np.round(efficient / tick) * tick
        first, last, has_trade = _first_last_trades(keep, n, trades)
        p = p.copy()
        if auction_open:
            p[first[has_trade]] = auction_price[first[has_trade]]
        if auction_close:
            p[last[has_trade]] = auction_price[last[has_trade]]

    ohlc = pd.DataFrame(
        extract_ohlc(p, keep, n, trades), columns=["Open", "High", "Low", "Close"]
    )
    if not return_truth:
        return ohlc
    truth = _ground_truth(
        sign=sign,
        price=p,
        efficient=efficient,
        impact_log=impact_log,
        bid=bid,
        ask=ask,
        keep=keep,
        n=n,
        trades=trades,
        rho=rho,
        persistence=persistence,
        spread=spread,
    )
    return ohlc, truth
