"""
Monte Carlo experiments for Task A2.

For each cell in an observation-probability grid, run `n_trials` independent
simulations of a length-`n_periods` OHLC series with a known true spread,
compute all four estimators (EDGE / Roll / Corwin-Schultz / Abdi-Ranaldo) on
each trial, and summarise with:

  - a tidy CSV of per-cell bias / RMSE / sample size
  - a two-panel PDF (bias and RMSE vs probability, log x-axis)
  - a boxplot PDF (estimate distribution at a single low-probability cell
    — the regime where EDGE is designed to dominate)
  - a LaTeX summary table at representative probabilities

Run `python src/simulations/monte_carlo.py` for a CI-friendly scale
(~1 minute); add `--full` for a slow, higher-resolution run (~10+ minutes).
"""

# Shim so direct-script invocation (`python src/simulations/monte_carlo.py`)
# finds sibling top-level modules (estimators, settings, simulations.*).
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from estimators import abdi_ranaldo, corwin_schultz, edge, roll
from settings import config
from simulations.simulator import simulate_ohlc

ESTIMATORS = {
    "EDGE": lambda df: edge(df.Open, df.High, df.Low, df.Close),
    "Roll": lambda df: roll(df.Open, df.High, df.Low, df.Close),
    "CS": lambda df: corwin_schultz(df.Open, df.High, df.Low, df.Close),
    "AR": lambda df: abdi_ranaldo(df.Open, df.High, df.Low, df.Close),
}


def run_cell(n_trials: int, sim_kwargs: dict, rng: np.random.Generator) -> dict:
    """Run n_trials independent sims at one parameter cell. Returns {name: array}."""
    out = {name: np.full(n_trials, np.nan) for name in ESTIMATORS}
    for i in range(n_trials):
        df = simulate_ohlc(rng=rng, **sim_kwargs)
        for name, fn in ESTIMATORS.items():
            out[name][i] = fn(df)
    return out


def bias_rmse(estimates: np.ndarray, true_value: float) -> tuple:
    arr = np.asarray(estimates, dtype=float)
    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return (np.nan, np.nan, 0, np.nan)
    bias = float(valid.mean() - true_value)
    rmse = float(np.sqrt(np.mean((valid - true_value) ** 2)))
    return (bias, rmse, int(valid.size), float(valid.mean()))


def sweep_probability(
    prob_grid: list,
    n_trials: int,
    true_spread: float,
    n_periods: int,
    trades: int,
    volatility: float,
    seed: int = 2024,
) -> tuple:
    """Run MC across the prob grid. Returns (tidy summary DataFrame, {prob: cell})."""
    rng = np.random.default_rng(seed)
    rows = []
    all_cells = {}
    for prob in prob_grid:
        sim_kwargs = dict(
            n=n_periods, trades=trades, prob=prob,
            spread=true_spread, volatility=volatility,
        )
        cell = run_cell(n_trials, sim_kwargs, rng)
        all_cells[prob] = cell
        for name, ests in cell.items():
            b, r, nv, mn = bias_rmse(ests, true_spread)
            rows.append(dict(
                prob=prob, estimator=name,
                bias=b, rmse=r, mean=mn, n_valid=nv,
            ))
    return pd.DataFrame(rows), all_cells


def make_bias_rmse_figure(df: pd.DataFrame, true_spread: float, output_path: Path):
    fig, (ax_bias, ax_rmse) = plt.subplots(1, 2, figsize=(10, 4), sharex=True)
    for name in ESTIMATORS:
        sub = df[df.estimator == name].sort_values("prob")
        ax_bias.plot(sub.prob, sub.bias * 1e4, marker="o", label=name)
        ax_rmse.plot(sub.prob, sub.rmse * 1e4, marker="o", label=name)
    for ax in (ax_bias, ax_rmse):
        ax.set_xscale("log")
        ax.set_xlabel("Observation probability")
        ax.grid(alpha=0.3)
    ax_bias.axhline(0, color="k", lw=0.5)
    ax_bias.set_ylabel("Bias (bps)")
    ax_bias.set_title("Estimator bias")
    ax_bias.legend()
    ax_rmse.set_ylabel("RMSE (bps)")
    ax_rmse.set_title("Estimator RMSE")
    fig.suptitle(
        f"MC bias / RMSE vs observation probability "
        f"(true spread = {true_spread*1e4:.0f} bps)"
    )
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def make_distribution_figure(
    cell: dict, true_spread: float, prob: float, output_path: Path
):
    fig, ax = plt.subplots(figsize=(6, 4))
    data = [cell[name] * 1e4 for name in ESTIMATORS]
    ax.boxplot(data, showfliers=False)
    ax.set_xticklabels(list(ESTIMATORS.keys()))
    ax.axhline(
        true_spread * 1e4, color="red", linestyle="--",
        label=f"True = {true_spread*1e4:.0f} bps",
    )
    ax.set_ylabel("Spread estimate (bps)")
    ax.set_title(f"Distribution of estimates at prob = {prob}")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def make_summary_table(
    df: pd.DataFrame, true_spread: float, output_path: Path, highlight_probs: list
):
    sub = df[df.prob.isin(highlight_probs)].copy()
    sub["Bias (bps)"] = sub.bias * 1e4
    sub["RMSE (bps)"] = sub.rmse * 1e4
    table = sub.pivot_table(
        index="estimator", columns="prob", values=["Bias (bps)", "RMSE (bps)"]
    )
    # Reformat the inner prob column labels: 0.01 / 0.10 / 1.00 instead of 0.010000.
    table.columns = pd.MultiIndex.from_tuples(
        [(metric, f"{p:.2f}") for metric, p in table.columns]
    )
    table.index.name = "Estimator"
    tex = table.to_latex(
        float_format="%.1f",
        caption=(
            f"Monte Carlo bias and RMSE (basis points) by estimator and "
            f"observation probability. True spread is "
            f"{true_spread*1e4:.0f} bps."
        ),
        label="tab:mc_bias_rmse",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tex)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full", action="store_true",
        help="Full-scale run (1000 trials x 1000 periods x 390 ticks).",
    )
    args = parser.parse_args()

    if args.full:
        n_trials, n_periods, trades = 1000, 1000, 390
    else:
        n_trials, n_periods, trades = 200, 250, 100

    true_spread = 0.01
    volatility = 0.03
    prob_grid = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 1.0]
    highlight_probs = [0.01, 0.10, 1.0]
    dist_prob = 0.05  # the paper's main-finding regime

    output_dir = Path(str(config("OUTPUT_DIR"))) / "simulations"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Running MC: {n_trials} trials x {len(prob_grid)} cells "
        f"x ({n_periods} periods x {trades} ticks per trial)"
    )
    results_df, all_cells = sweep_probability(
        prob_grid, n_trials, true_spread, n_periods, trades, volatility
    )

    results_df.to_csv(output_dir / "mc_bias_rmse.csv", index=False)
    make_bias_rmse_figure(results_df, true_spread, output_dir / "mc_bias_rmse.pdf")
    make_distribution_figure(
        all_cells[dist_prob], true_spread, dist_prob,
        output_dir / "mc_distribution.pdf",
    )
    make_summary_table(
        results_df, true_spread, output_dir / "mc_summary_table.tex", highlight_probs
    )
    print(f"Done. Outputs in {output_dir}")


if __name__ == "__main__":
    main()
