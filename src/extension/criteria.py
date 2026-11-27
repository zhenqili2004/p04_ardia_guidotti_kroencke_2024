"""
Pre-registered success criteria for the EDGE assumption-violation extension.

This file holds data only: constants and dictionaries, with no imports from
the pipeline. Tests and the verdict task read it; nothing here computes. It
can be read on its own and diffed against the agreed plan.

Source
------
- Extension pitch v2, section 5 "How will we know it worked?", sent to the
  instructor in November 2026 and approved by email (see the README's
  Extension section, which is what the extension is graded against).
- Thresholds that the pitch states numerically are copied here unchanged.
  The pitch does not give a number for "the derived biases hold in
  simulation"; `PREDICTION_MAX_REL_ERROR_S2` below fixes that number here,
  before any formal run.

Integrity note
--------------
These thresholds were written after a prototype exploration (whose numbers
we have seen) and before the formal runs, which use new code and new seeds.
They must not be loosened after the formal results are seen. A criterion
that is not met is reported as a result, not hidden or re-tuned.

Committed 2026-11-26.
"""

# ---------------------------------------------------------------------------
# 1. Our EDGE implementation against the `bidask` package (the oracle).
# ---------------------------------------------------------------------------
# Absolute difference in the spread estimate (0.01 = 1%).
EDGE_VS_BIDASK_ABS_TOL = 1e-10

# ---------------------------------------------------------------------------
# 2. No violations (rho = alpha = 0): the simulator reproduces Table 2.
# ---------------------------------------------------------------------------
# Owned by the replication task (Task A2). The extension cites that result
# and does not re-implement it, so no threshold is duplicated here.

# ---------------------------------------------------------------------------
# 3. Derived biases hold in simulation.
# ---------------------------------------------------------------------------
# Each prediction is checked on the S^2 scale: the mean over trials of
# EDGE's signed squared spread (w1 * mean(x1) + w2 * mean(x2)) against the
# mean over trials of the predicted value. Relative error is
# |mean(S_hat^2) / mean(predicted S^2) - 1|.
#
# The predictions are large-sample approximations for bars with many trades,
# so they are checked only in cells that meet `PREDICTION_CHECK_REGION`.
PREDICTION_MAX_REL_ERROR_S2 = 0.10

PREDICTION_CHECK_REGION = {
    # Expected trades per bar = time slots per bar x trading probability.
    "min_trades_per_bar": 20,
    "min_n_bars": 2000,
}

# `priority` follows the instructor's email: 1 = core, 2 = if time permits.
# `formula` is documentation; the experiment code implements it.
# `rho_b` is the realised boundary sign correlation (see `RHO_HAT_TRUTH`);
# `w2` is EDGE's weight on x2 in the same trial.
#
# S is the spread every continuous trade pays (the simulator's `spread`).
# EDGE targets (S_o^2 + S_c^2) / 2, the mean squared effective spread of the
# open and close trades (the paper's Eqs. 19-20). The two coincide unless an
# auction or a tick grid makes the open and close trades pay a different
# spread; the open-auction prediction S^2 / 2 is exactly that target with
# S_o = 0.
PREDICTIONS = {
    "order_splitting": {
        "priority": 1,
        "formula": "E[S_hat^2] = (1 - w2 * rho_b) * S^2",
        "applies_when": "any rho, alpha = 0, no auctions, no tick",
    },
    "price_impact": {
        "priority": 2,
        "formula": "E[S_hat^2] = (1 - alpha) * S^2",
        "applies_when": "alpha != 0, rho = 0, no auctions, no tick",
    },
    "open_auction": {
        "priority": 2,
        "formula": "E[S_hat^2] = S^2 / 2  (S_hat = S / sqrt(2))",
        "applies_when": "auction_open = True, auction_close = False, "
        "rho = 0, alpha = 0, no tick",
    },
}

# ---------------------------------------------------------------------------
# 4. rho_hat in the applicable region.
# ---------------------------------------------------------------------------
# A cell is in the applicable region only if every condition holds.
APPLICABLE_REGION = {
    "min_trades_per_bar": 20,  # expected trades per bar (trades x prob)
    "min_n_bars": 2000,
    "min_spread_to_volatility": 0.67,  # spread / per-bar volatility
    "auction_open": False,
    "auction_close": False,
    "tick": None,
    "alpha": 0.0,
}

# The value rho_hat is scored against in each trial. rho_hat estimates
# rho_b, the sign correlation of the two adjacent trades at a bar boundary
# (the previous close and the next open). rho_b equals the simulator's rho
# when sign persistence passes from trade to trade; when it decays with time
# and some minutes have no trade, rho_b is about rho ** Delta (Delta = time
# between the two trades). Scoring against the realised rho_b of the same
# path is right under either model.
RHO_HAT_TRUTH = "rho_b_realized"

# |median over trials of (rho_hat - truth)| must not exceed this.
RHO_HAT_MAX_ABS_MEDIAN_BIAS = 0.05

# Share of trials whose interval covers the truth must fall in this range
# (inclusive). The interval is rho_hat +/- z * SE at `RHO_HAT_CI_LEVEL`.
RHO_HAT_CI_LEVEL = 0.95
RHO_HAT_COVERAGE_RANGE = (0.90, 0.98)

# ---------------------------------------------------------------------------
# 5. Failure regions.
# ---------------------------------------------------------------------------
# Reported as results, with no pass/fail threshold. Priority as above.
FAILURE_REGIONS = {
    "thin_trading": 1,
    "auctions": 2,
    "tick_grid": 2,
    "splitting_and_impact": 2,
}
