"""Validate all saved monthly outputs; optionally run live pinned-R oracle checks.

No WRDS connection and no changes to the source or estimated panels.
"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pandas as pd

from estimate_crsp_monthly import METHODS, VARIANTS
from pull_crsp_daily import write_json
from settings import config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r-reference", action="store_true")
    args = parser.parse_args()
    root = Path(config("DATA_DIR")) / "crsp_daily"
    out = Path(config("OUTPUT_DIR")) / "crsp_monthly"
    out.mkdir(parents=True, exist_ok=True)
    if not (root / "monthly/complete.json").exists():
        raise RuntimeError("Monthly outputs incomplete")
    failures = []
    months = set()
    count = 0
    samples = []
    expected = []
    zero_factor = []
    coverage = pd.read_parquet(root / "clean/stock_month_coverage.parquet")
    for file in sorted((root / "monthly").glob("estimates_*.parquet")):
        year = int(file.stem[-4:])
        d = pd.read_parquet(file)

        def require(condition, label):
            if not condition:
                failures.append(f"{year}: {label}")

        require(not d.duplicated(["permno", "month"]).any(), "unique monthly keys")
        universe = coverage.loc[
            (coverage.n_sample > 0) & coverage.month.dt.year.eq(year),
            ["permno", "month"],
        ]
        require(
            pd.MultiIndex.from_frame(d[["permno", "month"]])
            .sort_values()
            .equals(pd.MultiIndex.from_frame(universe).sort_values()),
            "complete eligible universe",
        )
        require(d.month.dt.year.eq(year).all(), "annual partition bounds")
        count += len(d)
        months.update(d.month)
        for prefix in VARIANTS:
            common = np.ones(len(d), bool)
            for method in METHODS:
                estimate = d[prefix + method].to_numpy()
                finite = np.isfinite(estimate)
                common &= finite
                require(not np.isinf(estimate).any(), "no infinite " + prefix + method)
                require((estimate[finite] >= 0).all(), "nonnegative " + prefix + method)
                require(
                    np.array_equal(
                        finite, d[prefix + method + "_status"].eq("ok").to_numpy()
                    ),
                    "reason/availability " + prefix + method,
                )
                signed = d[
                    prefix + ("cs_signed" if method == "cs" else method + "_s2")
                ].to_numpy()
                reconstructed = (
                    np.maximum(signed, 0)
                    if method == "cs"
                    else np.sqrt(np.maximum(signed, 0))
                )
                require(
                    np.allclose(
                        estimate, reconstructed, rtol=0, atol=0, equal_nan=True
                    ),
                    "final transformation " + prefix + method,
                )
            require(
                np.array_equal(common, d[prefix + "common_sample"].to_numpy()),
                "common sample " + prefix,
            )
            require(
                np.allclose(
                    d[prefix + "edge_abs"],
                    np.sqrt(abs(d[prefix + "edge_s2"])),
                    rtol=0,
                    atol=0,
                    equal_nan=True,
                ),
                "EDGE modulus " + prefix,
            )
        require(
            d.loc[d.n_invalid_factors.gt(0), METHODS].isna().all().all(),
            "invalid factors stay unavailable",
        )
        if args.r_reference:
            chosen = d.loc[d.common_sample].sample(
                n=min(8, int(d.common_sample.sum())), random_state=32800 + year
            )
            clean = pd.read_parquet(
                root / "clean" / f"daily_{year}.parquet",
                columns=[
                    "permno",
                    "month",
                    "date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "price_factor",
                ],
            )
            for row in chosen.itertuples():
                key = f"{row.permno}_{row.month:%Y%m}"
                g = clean.loc[
                    clean.permno.eq(row.permno) & clean.month.eq(row.month)
                ].sort_values("date")
                prices = g[["open", "high", "low", "close"]].div(g.price_factor, axis=0)
                samples.append(prices.assign(case=key, position=np.arange(len(g))))
                expected.append(
                    dict(
                        case=key,
                        edge_signed=row.edge_signed,
                        roll_signed=np.sign(row.roll_s2) * np.sqrt(abs(row.roll_s2)),
                        ar_signed=np.sign(row.ar_s2) * np.sqrt(abs(row.ar_s2)),
                        cs_signed=row.cs_signed,
                    )
                )
            zero_factor.append(clean.loc[clean.price_factor.eq(0), ["permno", "date"]])
    require(len(months) == 344, "344 core months")
    result = dict(
        rows=count,
        months=len(months),
        failures=failures,
        r_reference_run=False,
        source="local saved CRSP monthly partitions",
        taq_validated=False,
    )
    if args.r_reference:
        rscript = shutil.which("Rscript")
        if not rscript:
            raise RuntimeError(
                "Rscript is required for --r-reference; offline fixtures remain available"
            )
        pd.concat(samples, ignore_index=True).to_csv(
            out / "r_reference_inputs.csv", index=False, float_format="%.17g"
        )
        generator = (
            Path(__file__).parent / "tests/reference_bidask/generate_monthly_fixture.R"
        )
        subprocess.run(
            [
                rscript,
                str(generator),
                str(out / "r_reference_inputs.csv"),
                str(out / "r_reference_outputs.csv"),
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        reference = (
            pd.read_csv(out / "r_reference_outputs.csv").set_index("case").sort_index()
        )
        actual = pd.DataFrame(expected).set_index("case").sort_index()
        errors = {}
        for col in actual:
            a, b = actual[col].to_numpy(), reference[col].to_numpy()
            errors[col] = float(np.nanmax(abs(a - b)))
            if not np.allclose(a, b, rtol=1e-10, atol=1e-12, equal_nan=True):
                failures.append("R oracle " + col)
        result.update(
            r_reference_run=True,
            r_reference_months=len(actual),
            r_reference_max_absolute_errors=errors,
            r_reference_tolerance=dict(atol=1e-12, rtol=1e-10),
        )
        z = pd.concat(zero_factor, ignore_index=True)
        z.groupby("permno").agg(
            rows=("date", "size"), first=("date", "min"), last=("date", "max")
        ).to_csv(out / "zero_factor_securities.csv")
    result["monthly_provenance"] = json.loads(
        (root / "monthly/complete.json").read_text()
    )["fingerprint"]
    write_json(
        out / ("r_validation.json" if args.r_reference else "validation.json"), result
    )
    if failures:
        raise RuntimeError("; ".join(failures))
    print(
        f"Validated {count:,} stock-months across {len(months)} months; all checks passed."
    )
    if args.r_reference:
        print(
            "Pinned author R checks:",
            result["r_reference_months"],
            "stock-months;",
            errors,
        )


if __name__ == "__main__":
    main()
