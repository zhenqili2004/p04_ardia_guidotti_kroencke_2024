"""
Simulation subpackage for Task A2.

Contains:
  - `simulator.simulate_ohlc`: OHLC price-path generator with embedded
    bid-ask spread (ported from the R reference implementation).
  - `monte_carlo`: experiment driver that sweeps the observation
    probability grid, runs each estimator on independent simulated
    series, and writes bias / RMSE figures and tables to `_output/`.
"""

from .simulator import simulate_ohlc

__all__ = ["simulate_ohlc"]
