"""Run or update the project. This file uses the `doit` Python package. It works
like a Makefile, but is Python-based.
"""

import sys
from pathlib import Path

sys.path.insert(1, "./src/")

from settings import CRSP_CORE_END, CRSP_EXTRACT_START, config  # noqa: E402

DOIT_CONFIG = {"backend": "sqlite3", "dep_file": "./.doit-db.sqlite"}

DATA_DIR = config("DATA_DIR")
OUTPUT_DIR = config("OUTPUT_DIR")
OS_TYPE = config("OS_TYPE")


##################################
## PyDoit tasks
##################################


def task_config():
    """Create empty directories for data and output if they don't exist."""
    return {
        "actions": ["python ./src/settings.py"],
        "targets": [DATA_DIR, OUTPUT_DIR],
        "file_dep": ["./src/settings.py"],
        "clean": [],
    }


def task_pull():
    """Pull data from external sources."""
    yield {
        "name": "crsp_stock",
        "doc": "Pull legacy project monthly CRSP stock inputs from WRDS",
        "actions": [
            "python ./src/settings.py",
            "python ./src/pull_CRSP_stock.py",
        ],
        "targets": [DATA_DIR / "CRSP_monthly_stock.parquet"],
        "file_dep": ["./src/settings.py", "./src/pull_CRSP_stock.py"],
        "clean": [],
    }
    raw = DATA_DIR / "crsp_daily" / "raw"
    yield {
        "name": "crsp_daily",
        "doc": "Extract Part B daily OHLC and historical identifiers from WRDS",
        "actions": [[sys.executable, "src/pull_crsp_daily.py"]],
        "targets": [
            raw / "manifest.json",
            raw / "schema_inventory.json",
            raw / "identifier_history.parquet",
        ]
        + [
            raw / f"daily_{y}.parquet"
            for y in range(CRSP_EXTRACT_START.year, CRSP_CORE_END.year + 1)
        ],
        "file_dep": ["src/pull_crsp_daily.py", "src/crsp_schema.py", "src/settings.py"],
        "clean": [],
    }


def task_clean_crsp_daily():
    """Clean Part B CRSP inputs and preserve an observation-level audit."""
    root = DATA_DIR / "crsp_daily"
    years = range(CRSP_EXTRACT_START.year, CRSP_CORE_END.year + 1)
    raw_files = [
        root / "raw" / "manifest.json",
        root / "raw" / "identifier_history.parquet",
    ]
    raw_files += [root / "raw" / f"daily_{y}.parquet" for y in years]
    targets = [
        root / "clean" / name
        for name in [
            "complete.json",
            "identifier_history.parquet",
            "stock_month_coverage.parquet",
            "monthly_size.parquet",
            "last_observed_size.parquet",
        ]
    ]
    targets += [
        root / "clean" / f"{prefix}_{y}.parquet"
        for y in years
        for prefix in ["daily", "audit"]
    ]
    return {
        "actions": [[sys.executable, "src/clean_crsp_daily.py"]],
        "task_dep": ["pull:crsp_daily"],
        "file_dep": raw_files
        + ["src/clean_crsp_daily.py", "src/settings.py", "src/pull_crsp_daily.py"],
        "targets": targets + [OUTPUT_DIR / "crsp_daily" / "filter_counts.csv"],
        "clean": [],
    }


def task_crsp_coverage():
    """Produce the CRSP-only input-coverage table and figure."""
    return {
        "actions": [[sys.executable, "src/report_crsp_coverage.py"]],
        "task_dep": ["clean_crsp_daily"],
        "file_dep": [
            "src/report_crsp_coverage.py",
            "src/settings.py",
            DATA_DIR / "crsp_daily" / "clean" / "complete.json",
            DATA_DIR / "crsp_daily" / "clean" / "stock_month_coverage.parquet",
        ],
        "targets": [
            OUTPUT_DIR / "crsp_daily" / name
            for name in ["monthly_coverage.csv", "coverage.pdf", "coverage_caption.txt"]
        ],
        "clean": True,
    }


def task_crsp_monthly():
    """Estimate CRSP stock-month spreads and convention sensitivities."""
    root = DATA_DIR / "crsp_daily"
    years = range(CRSP_EXTRACT_START.year, CRSP_CORE_END.year + 1)
    return {
        "actions": [[sys.executable, "src/estimate_crsp_monthly.py"]],
        "task_dep": ["clean_crsp_daily"],
        "file_dep": [
            "src/estimate_crsp_monthly.py",
            "src/estimators/monthly_batch.py",
            "src/settings.py",
            "src/clean_crsp_daily.py",
            "src/pull_crsp_daily.py",
            root / "clean/complete.json",
            root / "clean/stock_month_coverage.parquet",
            root / "clean/monthly_size.parquet",
            root / "raw/manifest.json",
        ]
        + [
            root / folder / f"daily_{year}.parquet"
            for folder in ["clean", "raw"]
            for year in years
        ],
        "targets": [root / "monthly/complete.json", root / "monthly/manifest.json"]
        + [root / "monthly" / f"estimates_{year}.parquet" for year in years],
        "clean": [],
        "verbosity": 2,
    }


def task_crsp_monthly_report():
    """Report monthly estimator availability and matched sensitivity comparisons."""
    root = DATA_DIR / "crsp_daily/monthly"
    return {
        "actions": [[sys.executable, "src/report_crsp_monthly.py"]],
        "task_dep": ["validate_crsp_monthly"],
        "file_dep": [
            "src/report_crsp_monthly.py",
            "src/estimate_crsp_monthly.py",
            "src/settings.py",
            "src/pull_crsp_daily.py",
            root / "complete.json",
        ]
        + [
            root / f"estimates_{year}.parquet"
            for year in range(CRSP_EXTRACT_START.year, CRSP_CORE_END.year + 1)
        ],
        "targets": [
            OUTPUT_DIR / "crsp_monthly" / name
            for name in [
                "summary.json",
                "estimator_coverage.csv",
                "failure_reasons.csv",
                "monthly_coverage.csv",
                "sensitivity_comparison.csv",
                "estimator_coverage.pdf",
                "caption.txt",
            ]
        ],
        "clean": True,
        "verbosity": 2,
    }


def task_validate_crsp_monthly():
    """Check saved monthly estimates and common-sample flags before reporting."""
    root = DATA_DIR / "crsp_daily/monthly"
    return {
        "actions": [[sys.executable, "src/validate_crsp_monthly.py"]],
        "task_dep": ["crsp_monthly"],
        "file_dep": [
            "src/validate_crsp_monthly.py",
            "src/estimate_crsp_monthly.py",
            "src/settings.py",
            "src/pull_crsp_daily.py",
            root / "complete.json",
            DATA_DIR / "crsp_daily/clean/stock_month_coverage.parquet",
        ]
        + [
            root / f"estimates_{y}.parquet"
            for y in range(CRSP_EXTRACT_START.year, CRSP_CORE_END.year + 1)
        ],
        "targets": [OUTPUT_DIR / "crsp_monthly/validation.json"],
        "clean": True,
        "verbosity": 2,
    }


def task_monte_carlo():
    """Run Task A2 Monte Carlo and write figures / tables to _output/."""
    return {
        "actions": ["python ./src/simulations/monte_carlo.py"],
        "targets": [
            OUTPUT_DIR / "simulations" / "mc_bias_rmse.csv",
            OUTPUT_DIR / "simulations" / "mc_bias_rmse.pdf",
            OUTPUT_DIR / "simulations" / "mc_distribution.pdf",
            OUTPUT_DIR / "simulations" / "mc_summary_table.tex",
        ],
        "file_dep": [
            "./src/simulations/__init__.py",
            "./src/simulations/monte_carlo.py",
            "./src/simulations/simulator.py",
            "./src/settings.py",
            "./src/estimators/__init__.py",
            "./src/estimators/edge.py",
            "./src/estimators/roll.py",
            "./src/estimators/corwin_schultz.py",
            "./src/estimators/abdi_ranaldo.py",
        ],
        "clean": True,
        "verbosity": 2,
    }


def task_build_chartbook_site():
    """Build the ChartBook site (published to GitHub Pages)."""
    return {
        "actions": ["chartbook docs build -f"],
        "targets": ["./docs/index.html"],
        "file_dep": [
            "./README.md",
            "./chartbook.toml",
        ],
        "clean": True,
    }


def task_run_pytest():
    """Run pytest and save a JUnit XML report to OUTPUT_DIR."""
    src_py_files = list(Path("./src").rglob("*.py"))
    test_output = OUTPUT_DIR / "pytest_results.xml"

    def run_pytest():
        import subprocess

        result = subprocess.run(["pytest", f"--junitxml={test_output}"])
        if result.returncode != 0:
            Path(test_output).unlink(missing_ok=True)
            raise RuntimeError(f"pytest failed with exit code {result.returncode}")

    return {
        "actions": [run_pytest],
        "targets": [test_output],
        "file_dep": src_py_files,
        "clean": True,
        "verbosity": 2,
    }
