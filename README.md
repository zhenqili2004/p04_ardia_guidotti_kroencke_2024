p04_ardia_guidotti_kroencke_2024
================================

> **Reference implementation (oracle for our tests):** https://github.com/eguidotti/bidask

## About this project

Replication of **Ardia, Guidotti, Kroencke (2024, JFE): *Efficient Estimation of
Bid-Ask Spreads from Open, High, Low, and Close Prices***. UChicago FinM Data
Pipeline final project.

See [`PROJECT_SPEC.md`](PROJECT_SPEC.md) for the full course rubric and
cookiecutter/ChartBook requirements.

## Paper and course brief

You can measure the effective spread directly if you have the trades and quotes.
Most of the time you do not — you have daily open, high, low, and close, and
that is all. The estimators that recover spreads from those four numbers (Roll,
Corwin–Schultz, Abdi–Ranaldo) are biased downward when trading is infrequent,
which is exactly the case where you most want them. This paper derives
estimators that account for discretely observed prices and combines them
optimally "to minimize estimation variance," producing the **EDGE** estimator
now shipping in the [`bidask`](https://github.com/eguidotti/bidask) package.

What makes this a good course project is the validation structure. The
estimator has a published reference implementation, and the quantity it
estimates has an observable ground truth in TAQ. You are not comparing your
output to a printed table — you are comparing it to the thing itself.

### Tasks

1. **Build the price and benchmark panel.** CRSP daily open/high/low/close for
   the sample, plus TAQ effective spreads for the same stock-months as ground
   truth, with a summary table and a coverage figure (this is the data-cleaning
   deliverable).
2. **Replicate the Monte Carlo.** Bias and RMSE of EDGE against Roll,
   Corwin–Schultz, and Abdi–Ranaldo as trading frequency falls.
3. **Replicate the empirical comparison.** Each estimator's correlation with
   TAQ effective spreads, by size decile and through time.
4. **Implement the estimator from the paper's equations**, then test your
   implementation against the `bidask` package output — the package is the
   oracle, your code is what is being tested.
5. **Extension: EDGE when its assumptions fail.** Stress-test EDGE and its
   competitors in simulation under autocorrelated trade signs, informed trading,
   auctions and a tick grid, and estimate order-flow autocorrelation from OHLC
   prices alone. See [Extension](#extension) below.

### Data sources

- **CRSP daily stock file** (WRDS) — daily OHLC inputs for EDGE
- **Daily TAQ** (WRDS) — trades + NBBO quotes for the ground-truth effective
  spread
- **Extension** — simulated prices only; no external data
- **Reference implementation**: https://github.com/eguidotti/bidask

### Notes

- *Do not call the package and stop.* The deliverable is your own
  implementation plus the test suite that proves it matches.

### Citation

> Ardia, David, Emanuele Guidotti, and Tim A. Kroencke. "Efficient estimation
> of bid–ask spreads from open, high, low, and close prices." *Journal of
> Financial Economics* 161 (2024): 103916.
> https://doi.org/10.1016/j.jfineco.2024.103916
> (working paper: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3892335)

## Extension

*Agreed with Prof. Bejarano by email on 2026-11-20.*

**Question.** EDGE is derived, and evaluated in the paper's Monte Carlo, only under the paper's
Assumptions 1-3 (a random-walk fundamental price, and bid-ask bounces that are serially uncorrelated,
mean zero, and uncorrelated with fundamental returns). We ask how EDGE behaves when those
assumptions fail, and we show that EDGE's two moment conditions identify order-flow (trade-sign)
autocorrelation from OHLC prices alone. Earlier work on autocorrelated order flow
(Choi, Salandro & Shastri, 1988) needs trade-level data to estimate it.

**Who would use it.**
- Researchers who use EDGE as a trading-cost or liquidity proxy without TAQ. They learn when order
  splitting biases EDGE, and can switch to the rho-robust spread estimate or flag those observations.
- Microstructure researchers who study order-flow persistence where only bars exist (historical
  intraday bars, markets without signed trades). They get an estimate of order-flow autocorrelation,
  with a standard error, without trade-level data. The estimator targets intraday bars during
  continuous trading, not U.S. daily bars, which open and close with auctions.

**Priority 1 (the core deliverable, per instructor guidance)**
1. A simulator that extends the paper's Monte Carlo with autocorrelated trade signs (order splitting, `rho`,
   with persistence passed from trade to trade or decaying with time) and variable trading frequency. The main
   results vary the number of trades per bar; thinning by minutes without trades is reported separately.
2. Bias, RMSE and fraction of non-positive estimates of EDGE, its four DGE building blocks, AR, CS and Roll
   as `rho` and trading frequency vary. Estimates follow the paper's conventions: CS includes the overnight
   adjustment, and a negative squared-spread estimate is reset to zero only at the final estimate (Eq. 26),
   not window by window, as in its simulations (Table 2, which reports means and standard deviations). The
   fraction of non-positive estimates, which the paper reports for its empirical estimates (Table 3), is
   counted before that reset.
3. An OHLC-only estimator of order-flow autocorrelation, `rho_hat = 1 - mean(x2) / mean(x1)`, where x1 and x2 are
   EDGE's two moment conditions, with a delta-method Newey-West standard error, and a rho-robust spread
   estimate `sqrt(mean(x1))`. Exposed as tested, documented functions:
   `edge_moments`, `rho_hat`, `spread_x1`, `edge_diagnostics`.
4. A reliability map showing where EDGE and `rho_hat` can be trusted: trades per bar, sample size,
   and spread relative to volatility.

**Priority 2 (secondary; delivered if time permits, per instructor guidance)**
5. The same stress test, and the matching parts of the reliability map, under opening/closing auctions,
   a tick grid, and permanent price impact (informed trading), including order splitting and price impact
   together.

**How we will know it worked** (thresholds committed in `src/extension/criteria.py` before the final runs)
- Our EDGE matches the `bidask` package to 1e-10.
- With no violations, the simulator reproduces the paper's Table 2 (shared with the replication task).
- Order splitting: EDGE's bias matches the derived E[S_hat^2] = (1 - w2 * rho_b) * S^2, where w2 is EDGE's
  weight on x2 and rho_b is the sign correlation of the two adjacent trades at a bar boundary (the previous
  close and the next open): rho_b = rho when sign persistence passes from trade to trade, and it is smaller
  when persistence decays with time and those two trades are far apart.
- In the applicable region (>= 20 trades per bar, >= 2,000 bars, spread/volatility >= 0.67, no auctions,
  no ticks, no price impact): |median bias of rho_hat| <= 0.05, and 95% interval coverage between 90% and 98%.
- Priority 2 predictions: (1 - alpha) * S^2 under price impact; S / sqrt(2) when the open is an auction.
- Spread estimates are compared with two truths: the effective spread of all trades, and that of the open
  and close trades, (S_o^2 + S_c^2) / 2, which is what EDGE targets.
- Failure regions (thin trading, auctions, ticks, rho and impact together) are reported as results.

*Note on tolerances.* We explored a prototype before writing these thresholds. They were fixed after that
exploration and before the final runs, which use new code and new seeds.

**Stretch (not committed)**
- Analytical results for order splitting and price impact together (MRR-type model).
- A finite-trades correction for `rho_hat`.

**How to run.** (to be filled in when the pipeline tasks land)

**Outputs.** (to be filled in when the pipeline tasks land)

---

## Quick Start

The quickest way to run code in this repo is to use the following steps.

You must have TexLive (or another LaTeX distribution) installed on your computer and available in your path.
You can do this by downloading and installing it from here ([windows](https://tug.org/texlive/windows.html#install)
and [mac](https://tug.org/mactex/mactex-download.html) installers).


First, you must have the `conda` package manager installed (e.g., via Anaconda). However, I recommend using `mamba`, via [miniforge](https://github.com/conda-forge/miniforge) as it is faster and more lightweight than `conda`.

Create and activate the conda environment:
```bash
conda env create -f environment.yml
conda activate p04_ardia_guidotti_kroencke_2024
```

Finally, run the project tasks:
```bash
doit
```
And that's it!


### Other commands

#### Unit Tests and Doc Tests

You can run the unit test, including doctests, with the following command:
```
pytest --doctest-modules
```

You can build the documentation with:
```
rm ./src/.pytest_cache/README.md
jupyter-book build -W ./
```
Use `del` instead of rm on Windows


#### Setting Environment Variables

You can [export your environment variables](https://stackoverflow.com/questions/43267413/how-to-set-environment-variables-from-env-file)
from your `.env` files like so, if you wish. This can be done easily in a Linux or Mac terminal with the following command:
```bash
set -a  # automatically export all variables
source .env
set +a
```
On Windows (PowerShell):
```powershell
Get-Content .env | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
```

### Formatting

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting Python code.

```bash
# Auto-fix linting issues (e.g., unused imports, undefined names)
ruff check . --fix

# Format code (consistent style, spacing, line length)
ruff format .

# Sort imports, then fix linting issues, then format
ruff format . && ruff check --select I --fix . && ruff check --fix .
```

- `ruff check --fix` applies safe auto-fixes for linting violations
- `ruff format` formats code similar to Black
- `--select I` targets only import sorting rules (isort-compatible)

### General Directory Structure

 - The `_data` folder holds raw / cached data pulled by the pipeline (CRSP,
   TAQ). It is gitignored — everything in it can be recreated by
   re-running `doit pull`.

 - The `_output` folder holds generated artifacts (tables, figures, rendered
   notebooks, the ChartBook site). Also recreatable from code; gitignored.

 - The `doit` Python module is the task runner (`make`-like). Run `doit` from
   the project root to rebuild anything out of date; see `dodo.py` for the
   task graph.

 - The `.env` file is a per-collaborator container for secrets (WRDS
   credentials) and machine-specific paths. It is gitignored;
   see `.env.example` for the required variables.

### Data and Output Storage

`_data` and `_output` paths default to inside the repo but can be overridden
via `.env`:

    DATA_DIR=/absolute/path/to/cache
    OUTPUT_DIR=/absolute/path/to/outputs

`settings.py` is the single source of truth for these paths and for analysis
constants like `START_DATE` / `END_DATE` / `TAQ_START_DATE`. Dates are *not*
read from `.env` — two collaborators building the same commit must get the
same bytes.

Of course, the _data directory and _output directory can be kept elsewhere on the
machine. To make this easy, I always include the ability to customize these
locations by defining the path to these directories in environment variables,
which I intend to be defined in the `.env` file, though they can also simply be
defined on the command line or elsewhere. The `settings.py` is responsible for
loading these environment variables and doing some preprocessing on them.
The `settings.py` file is the entry point for all other scripts to these
definitions. That is, all code that references these variables and others are
loaded by importing `config`.

### Naming Conventions

 - **`pull_` vs `load_`**: Files or functions that pull data from an external
 data source are prepended with "pull_", as in "pull_fred.py". Functions that
 load data that has been cached in the "_data" folder are prepended with "load_".
 For example, inside of the `pull_CRSP_Compustat.py` file there is both a
 `pull_compustat` function and a `load_compustat` function. The first pulls from
 the web, whereas the other loads cached data from the "_data" directory.


### Dependencies and Virtual Environments

#### Working with `conda` environments

This project uses conda for environment management. The dependencies are stored in `environment.yml`.

To create/update the environment:
```bash
conda env create -f environment.yml
# or to update an existing environment:
conda env update -f environment.yml
```

To activate the environment:
```bash
conda activate p04_ardia_guidotti_kroencke_2024
```

To export the current environment:
```bash
conda env export > environment.yml
```

**Tip:** Consider using `mamba` instead of `conda` for faster package resolution. Install via [miniforge](https://github.com/conda-forge/miniforge).
