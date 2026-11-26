"""
Simulation subpackage for Task A2.

Contains:
  - `simulator.simulate_ohlc`: OHLC price-path generator with embedded
    bid-ask spread (ported from the R reference implementation).
  - `monte_carlo`: experiment driver that sweeps the observation
    probability grid, runs each estimator on independent simulated
    series, and writes bias / RMSE figures and tables to `_output/`.
  - `violations.simulate_ohlc_violations`: the extension's simulator, which
    adds switches that break the paper's assumptions (autocorrelated trade
    signs, price impact, auctions, a tick grid). With every switch off it
    returns exactly what `simulate_ohlc` returns.
"""

from .simulator import simulate_ohlc
from .violations import simulate_ohlc_violations

__all__ = ["simulate_ohlc", "simulate_ohlc_violations"]
