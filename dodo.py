"""Run or update the project. This file uses the `doit` Python package. It works
like a Makefile, but is Python-based.
"""

import sys
from pathlib import Path

sys.path.insert(1, "./src/")

from settings import config  # noqa: E402

DOIT_CONFIG = {"backend": "sqlite3", "dep_file": "./.doit-db.sqlite"}

BASE_DIR = config("BASE_DIR")
DATA_DIR = config("DATA_DIR")
MANUAL_DATA_DIR = config("MANUAL_DATA_DIR")
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
        "doc": "Pull CRSP daily stock data from WRDS",
        "actions": [
            "python ./src/settings.py",
            "python ./src/pull_CRSP_stock.py",
        ],
        "targets": [DATA_DIR / "CRSP_monthly_stock.parquet"],
        "file_dep": ["./src/settings.py", "./src/pull_CRSP_stock.py"],
        "clean": [],
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
    src_py_files = list(Path("./src").glob("*.py"))
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
