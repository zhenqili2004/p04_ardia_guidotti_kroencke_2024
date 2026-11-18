"""
OHLC price-path simulator with embedded bid-ask spread.

Numeric model matches the R version. The two implementations will not produce
bit-identical output for a given seed because R and NumPy use different RNG
algorithms (R: Mersenne-Twister with its own seeding; NumPy: PCG64 via
`default_rng`). The statistical properties are the same.

Model
-----
For each of `n` periods, simulate `trades` tick-level transactions. For each
tick t:

    r_t  ~ N(drift/trades, (volatility/sqrt(trades))^2)       # efficient-price log return
    z_t  ~ (spread/2) * {-1, +1}   with P=0.5                 # bid/ask side indicator
    P_t  =  exp(cumsum(r)_t) * (1 + z_t)                      # observed trade price

An overnight log-return N(0, overnight) is added at the first tick of each
period (positions 1, trades+1, 2*trades+1, ...).

Each tick is "observed" independently with probability `prob`; unobserved
ticks are dropped. The period's OHLC is then:

    Open   = first observed trade price in the period
    Close  = last  observed trade price
    High   = trade with the largest |price|
    Low    = trade with the smallest |price|

If a period has zero observed ticks, all four OHLC values inherit the previous
period's Close (constant-row flat day).

Setting `sign=True` returns signed prices (positive for ask/buy, negative for
bid/sell) so the sampling side of each extremum can be recovered downstream.
"""

from typing import Optional

import numpy as np
import pandas as pd


def simulate_ohlc(
    n: int = 10000,
    trades: int = 390,
    prob: float = 1.0,
    spread: float = 0.01,
    volatility: float = 0.03,
    overnight: float = 0.0,
    drift: float = 0.0,
    sign: bool = False,
    rng: Optional[np.random.Generator] = None,
) -> pd.DataFrame:
    """
    Simulate `n` periods of Open-High-Low-Close prices with embedded bid-ask spread.

    Parameters
    ----------
    n : int, default 10000
        Number of periods (e.g. trading days) to simulate.
    trades : int, default 390
        Number of candidate trades per period (390 = one per minute of a NYSE
        regular trading session).
    prob : float, default 1.0
        Probability that each candidate trade is observed. Lower values model
        thinly traded assets.
    spread : float, default 0.01
        True effective bid-ask spread (0.01 = 1%).
    volatility : float, default 0.03
        Open-to-close log-return volatility per period.
    overnight : float, default 0.0
        Close-to-open log-return volatility between periods.
    drift : float, default 0.0
        Expected log return per period.
    sign : bool, default False
        If True, Open/High/Low/Close are signed (positive for ask, negative
        for bid) and High/Low are chosen by absolute value.
    rng : np.random.Generator, optional
        NumPy random generator. If None, `np.random.default_rng()` is used.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns ['Open', 'High', 'Low', 'Close'] and `n` rows.
    """
    if rng is None:
        rng = np.random.default_rng()

    m = n * trades

    # Per-tick log returns of the efficient price.
    r = rng.normal(loc=drift / trades, scale=volatility / np.sqrt(trades), size=m)

    # Overnight jumps at the first tick of each period.
    if overnight > 0:
        period_starts = np.arange(n) * trades
        r[period_starts] += rng.normal(loc=0.0, scale=overnight, size=n)

    # Bid/ask bounce: z ∈ {-spread/2, +spread/2} with equal probability.
    z = spread * (rng.integers(0, 2, size=m) - 0.5)

    # Observed trade prices.
    p = np.exp(np.cumsum(r)) * (1.0 + z)
    if sign:
        p = p * np.sign(z)

    # Observation mask.
    keep = rng.random(m) < prob

    # Reshape to (n, trades) and extract OHLC per row, falling back to the
    # previous Close when a row has no observed tick.
    p_mat = p.reshape(n, trades)
    keep_mat = keep.reshape(n, trades)

    ohlc = np.empty((n, 4), dtype=float)
    prev_close = p[0]  # seed for the first period if it happens to be empty

    for i in range(n):
        row_mask = keep_mat[i]
        if row_mask.any():
            obs = p_mat[i, row_mask]
            uobs = np.abs(obs)
            ohlc[i, 0] = obs[0]  # Open
            ohlc[i, 1] = obs[np.argmax(uobs)]  # High (by |price|)
            ohlc[i, 2] = obs[np.argmin(uobs)]  # Low  (by |price|)
            ohlc[i, 3] = obs[-1]  # Close
            prev_close = obs[-1]
        else:
            ohlc[i, :] = prev_close  # flat day

    return pd.DataFrame(ohlc, columns=["Open", "High", "Low", "Close"])
