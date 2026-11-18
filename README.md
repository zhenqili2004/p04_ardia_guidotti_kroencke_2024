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
5. **Extend to futures.** Apply the estimators to E-mini and Treasury futures
   from Databento, where the true spread is observable from the top of book at
   essentially no data cost.

### Data sources

- **CRSP daily stock file** (WRDS) — daily OHLC inputs for EDGE
- **Daily TAQ** (WRDS) — trades + NBBO quotes for the ground-truth effective
  spread
- **Databento GLBX (mbp-1)** — for the futures extension
- **Reference implementation**: https://github.com/eguidotti/bidask

### Notes

- *Do not call the package and stop.* The deliverable is your own
  implementation plus the test suite that proves it matches.
- The futures extension is the most interesting part and is not in the paper.
  Futures give you a clean, cheap ground truth in an asset class where the
  daily-data estimators are used constantly and validated rarely.

### Citation

> Ardia, David, Emanuele Guidotti, and Tim A. Kroencke. "Efficient estimation
> of bid–ask spreads from open, high, low, and close prices." *Journal of
> Financial Economics* 161 (2024): 103916.
> https://doi.org/10.1016/j.jfineco.2024.103916
> (working paper: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3892335)

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
   TAQ, Databento). It is gitignored — everything in it can be recreated by
   re-running `doit pull`.

 - The `_output` folder holds generated artifacts (tables, figures, rendered
   notebooks, the ChartBook site). Also recreatable from code; gitignored.

 - The `doit` Python module is the task runner (`make`-like). Run `doit` from
   the project root to rebuild anything out of date; see `dodo.py` for the
   task graph.

 - The `.env` file is a per-collaborator container for secrets (WRDS /
   Databento credentials) and machine-specific paths. It is gitignored;
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
