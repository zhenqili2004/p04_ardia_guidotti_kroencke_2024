"""CRSP input coverage plot/table, distinct from a CRSP–TAQ match figure."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from settings import config


def main():
    clean = Path(config("DATA_DIR")) / "crsp_daily" / "clean"
    if not (clean / "complete.json").exists():
        raise RuntimeError("Cleaning has not completed.")
    out = Path(config("OUTPUT_DIR")) / "crsp_daily"
    coverage = pd.read_parquet(clean / "stock_month_coverage.parquet")
    for name, field in [("sample", "n_sample"), ("hlc", "n_hlc"), ("ohlc", "n_ohlc")]:
        coverage[name] = coverage[field].gt(0)
    monthly = coverage.groupby("month")[["sample", "hlc", "ohlc"]].sum()
    monthly.columns = ["sample_stocks", "hlc_stocks", "ohlc_stocks"]
    monthly["ohlc_fraction"] = monthly.ohlc_stocks / monthly.sample_stocks.replace(
        0, float("nan")
    )
    monthly.to_csv(out / "monthly_coverage.csv")
    fig, ax = plt.subplots(figsize=(10, 4))
    for col, label in [
        ("sample_stocks", "Eligible common stocks"),
        ("hlc_stocks", "At least one valid HLC day"),
        ("ohlc_stocks", "At least one valid OHLC day"),
    ]:
        ax.plot(monthly.index, monthly[col], label=label)
    ax.set(
        ylabel="Number of securities",
        xlabel="Month",
        title="CRSP input coverage, May 1993–December 2021",
    )
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out / "coverage.pdf")
    plt.close(fig)
    denominator = int(coverage["sample"].sum())
    numerator = int(coverage["ohlc"].sum())
    fraction = numerator / denominator if denominator else float("nan")
    (out / "coverage_caption.txt").write_text(
        f"{numerator:,} of {denominator:,} eligible CRSP stock-months ({fraction:.2%}) "
        "have at least one valid OHLC day. This measures input availability only; "
        "it does not establish estimator computability, common-estimator coverage, "
        "or TAQ matching. The HLC/OHLC difference isolates missing-open coverage.\n"
    )


if __name__ == "__main__":
    main()
