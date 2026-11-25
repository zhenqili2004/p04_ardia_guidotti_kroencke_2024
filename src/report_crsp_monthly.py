"""Estimator availability and matched-sample sensitivity, without a TAQ benchmark."""

from pathlib import Path
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from estimate_crsp_monthly import METHODS, VARIANTS
from pull_crsp_daily import write_json
from settings import config

CHANGE_THRESHOLD = 1e-8  # proportion = 0.0001 basis points; fixed before full run


def main():
    root = Path(config("DATA_DIR")) / "crsp_daily/monthly"
    if not (root / "complete.json").exists():
        raise RuntimeError("Monthly estimation is incomplete")
    out = Path(config("OUTPUT_DIR")) / "crsp_monthly"
    out.mkdir(parents=True, exist_ok=True)
    counts = []
    monthly = []
    reasons = []
    differences = {}
    totals = dict(
        months=0,
        baseline_common=0,
        raw_common=0,
        boundary_common=0,
        gap_common=0,
        invalid_factor_months=0,
        no_clean_months=0,
        months_with_gaps=0,
        missing_size_months=0,
    )
    for path in sorted(root.glob("estimates_*.parquet")):
        d = pd.read_parquet(path)
        totals["months"] += len(d)
        totals["baseline_common"] += int(d.common_sample.sum())
        totals["raw_common"] += int(d.raw_common_sample.sum())
        totals["boundary_common"] += int(d.boundary_common_sample.sum())
        totals["gap_common"] += int(d.gap_common_sample.sum())
        totals["invalid_factor_months"] += int(
            d.edge_status.eq("invalid_price_factor").sum()
        )
        totals["no_clean_months"] += int(d.n_hlc.eq(0).sum())
        totals["months_with_gaps"] += int(d.n_within_month_gaps.gt(0).sum())
        totals["missing_size_months"] += int((~d.size_available).sum())
        for prefix in VARIANTS:
            label = prefix.rstrip("_") or "adjusted_within"
            part = (
                d.groupby("month")[prefix + "common_sample"]
                .agg(["size", "sum"])
                .reset_index()
            )
            part.columns = ["month", "eligible", "common"]
            part["variant"] = label
            monthly.append(part)
            for method in METHODS:
                x = d[prefix + method]
                finite = np.isfinite(x)
                counts.append(
                    dict(
                        variant=label,
                        method=method,
                        eligible=len(d),
                        available=int(finite.sum()),
                        zero=int(x.eq(0).sum()),
                        negative_intermediate=int(
                            d[prefix + method + "_negative"].sum()
                        ),
                    )
                )
                reason = d[prefix + method + "_status"].value_counts()
                reasons.extend(
                    dict(variant=label, method=method, reason=str(k), count=int(v))
                    for k, v in reason.items()
                )
        for variant in ["raw", "boundary", "gap"]:
            # Same stock-months AND common availability of all four methods.
            mask = d.common_sample & d[variant + "_common_sample"]
            for method in METHODS:
                differences.setdefault((variant, method), []).append(
                    (
                        d.loc[mask, variant + "_" + method] - d.loc[mask, method]
                    ).to_numpy()
                )
        mask = d.common_sample
        differences.setdefault(("edge_abs", "edge"), []).append(
            (d.loc[mask, "edge_abs"] - d.loc[mask, "edge"]).to_numpy()
        )
    counts = pd.DataFrame(counts).groupby(["variant", "method"], as_index=False).sum()
    counts["available_fraction"] = counts.available / counts.eligible
    counts["zero_fraction_of_available"] = counts.zero / counts.available
    counts.to_csv(out / "estimator_coverage.csv", index=False)
    pd.DataFrame(reasons).groupby(["variant", "method", "reason"], as_index=False)[
        "count"
    ].sum().to_csv(out / "failure_reasons.csv", index=False)
    monthly = pd.concat(monthly, ignore_index=True)
    monthly.to_csv(out / "monthly_coverage.csv", index=False)
    comparison = []
    for (variant, method), arrays in differences.items():
        delta = np.concatenate(arrays)
        comparison.append(
            dict(
                comparison=variant,
                method=method,
                paired_months=len(delta),
                mean_difference_bps=float(np.mean(delta) * 10000)
                if len(delta)
                else None,
                median_absolute_difference_bps=float(np.median(abs(delta)) * 10000)
                if len(delta)
                else None,
                p95_absolute_difference_bps=float(np.quantile(abs(delta), 0.95) * 10000)
                if len(delta)
                else None,
                max_absolute_difference_bps=float(np.max(abs(delta)) * 10000)
                if len(delta)
                else None,
                fraction_changed=float(np.mean(abs(delta) > CHANGE_THRESHOLD))
                if len(delta)
                else None,
            )
        )
    pd.DataFrame(comparison).to_csv(out / "sensitivity_comparison.csv", index=False)
    fig, ax = plt.subplots(figsize=(10, 4))
    for label, g in monthly.groupby("variant"):
        ax.plot(g.month, g.common / g.eligible, label=label)
    ax.set(
        xlabel="Month",
        ylabel="Fraction with all four estimators",
        ylim=(0, 1.02),
        title="CRSP monthly estimator availability",
    )
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out / "estimator_coverage.pdf")
    plt.close(fig)
    totals["change_threshold_proportion"] = CHANGE_THRESHOLD
    totals["paper_empirical_scripts_verified"] = False
    totals["taq_comparison_performed"] = False
    write_json(out / "summary.json", totals)
    (out / "caption.txt").write_text(
        f"The adjusted within-month specification produces all four estimators for "
        f"{totals['baseline_common']:,} of {totals['months']:,} eligible CRSP stock-months. "
        f"{totals['invalid_factor_months']:,} months have unusable adjustment factors. "
        "Sensitivity comparisons use identical stock-month intersections with all four methods available. "
        "These are CRSP-only availability and convention comparisons, not accuracy comparisons against TAQ.\n"
    )
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
