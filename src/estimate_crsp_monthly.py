"""Monthly CRSP spreads: adjusted baseline, raw and boundary sensitivities.

Baseline: calendar-month-only moments, OHLC / positive CFACPR, final clipping.
Raw comparison changes adjustment only. Boundary comparison changes lag
ownership only; previous-month observations supply lags, never extra moments.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from clean_crsp_daily import save_parquet
from estimators.monthly_batch import estimate_batch
from pull_crsp_daily import write_json
from settings import CRSP_CORE_END, CRSP_CORE_START, config

METHODS = ["edge", "ar", "cs", "roll"]
VARIANTS = ["", "raw_", "boundary_", "gap_"]
VERSION = 2
COLS = [
    "permno",
    "date",
    "month",
    "open",
    "high",
    "low",
    "close",
    "price_factor",
    "exchange_code",
    "cusip",
    "ticker",
]


def pack_months(daily, prior=None, calendar=None):
    """Pack month rows plus up to two preceding-month rows, without filling gaps.

    prior contains only the preceding year's final two eligible rows per stock.
    Historical identifier changes within a month are counted, not overwritten.
    """
    data = daily[COLS].copy()
    data["output"] = data.date.between(CRSP_CORE_START, CRSP_CORE_END)
    if prior is not None and len(prior):
        p = prior[COLS].copy()
        p["output"] = False
        data = pd.concat([p, data], ignore_index=True)
    data = data.sort_values(["permno", "date"]).reset_index(drop=True)
    if data.duplicated(["permno", "date"]).any():
        raise ValueError("Duplicate daily keys at estimation input")
    # Keep the preceding two observations, not arbitrary extra prior-month days.
    target = data.loc[data.output].copy()
    if target.empty:
        return None
    groups = target.groupby(["permno", "month"], sort=True)
    summary = groups.agg(
        n_hlc=("date", "size"),
        n_ohlc=("open", "count"),
        first_date=("date", "min"),
        last_date=("date", "max"),
        n_cusips=("cusip", "nunique"),
        n_tickers=("ticker", "nunique"),
        exchange_code=("exchange_code", "last"),
    ).reset_index()
    group_id = groups.ngroup().to_numpy()
    positions = groups.cumcount().to_numpy() + 2
    n, width = len(summary), int(summary.n_hlc.max()) + 2
    prices = np.full((n, width, 4), np.nan)
    factors = np.full((n, width), np.nan)
    current = np.zeros((n, width), bool)
    dates = np.full((n, width), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
    prices[group_id, positions] = target[["open", "high", "low", "close"]].to_numpy(
        float
    )
    factors[group_id, positions] = target.price_factor.to_numpy(float)
    dates[group_id, positions] = target.date.to_numpy()
    current[group_id, positions] = True
    first = target.index[positions == 2].to_numpy()
    months = summary.month.dt.to_period("M")
    for offset, slot in [(1, 1), (2, 0)]:
        idx = first - offset
        safe = np.maximum(idx, 0)
        previous = data.iloc[safe]
        ok = (idx >= 0) & (previous.permno.to_numpy() == summary.permno.to_numpy())
        ok &= (
            previous.month.dt.to_period("M").reset_index(drop=True) == (months - 1)
        ).to_numpy()
        prices[ok, slot] = previous.loc[ok, ["open", "high", "low", "close"]].to_numpy(
            float
        )
        factors[ok, slot] = previous.loc[ok, "price_factor"].to_numpy(float)
        dates[ok, slot] = previous.loc[ok, "date"].to_numpy()
    summary["n_prior_rows"] = np.isfinite(prices[:, :2, 3]).sum(axis=1)
    bad = (~np.isfinite(factors)) | (factors <= 0)
    summary["n_invalid_factors"] = (bad & current).sum(axis=1)
    summary["boundary_invalid_factor"] = (
        bad & (current | np.isfinite(prices[:, :, 3]))
    ).any(axis=1)
    adjacent = np.ones(current.shape, dtype=bool)
    if calendar is not None:
        cal = np.asarray(calendar, dtype="datetime64[ns]")
        cal.sort()
        loc = np.searchsorted(cal, dates)
        valid_dates = ~np.isnat(dates)
        pair = (
            current[:, 1:] & current[:, :-1] & valid_dates[:, 1:] & valid_dates[:, :-1]
        )
        gap = loc[:, 1:] - loc[:, :-1] - 1
        adjacent[:, 0] = False
        adjacent[:, 1:] = valid_dates[:, 1:] & valid_dates[:, :-1] & (gap == 0)
        summary["n_within_month_gaps"] = (pair & (gap > 0)).sum(axis=1)
        summary["missing_sessions_between_rows"] = np.where(
            pair, np.maximum(gap, 0), 0
        ).sum(axis=1)
        summary["boundary_gap_sessions"] = np.where(
            valid_dates[:, 1] & valid_dates[:, 2],
            np.maximum(loc[:, 2] - loc[:, 1] - 1, 0),
            0,
        )
    return summary, prices, factors, current, adjacent


def estimate_packed(packed, batch_size=4096):
    """Bound intermediate memory and preserve every failure reason."""
    summary, prices, factors, current, adjacent = packed
    output = summary.copy()
    for prefix in VARIANTS:
        pieces = []
        for start in range(0, len(summary), batch_size):
            end = min(start + batch_size, len(summary))
            p = prices[start:end].copy()
            mask = current[start:end]
            invalid = np.zeros(end - start, bool)
            if prefix != "raw_":
                f = factors[start:end]
                invalid = (
                    summary.boundary_invalid_factor.iloc[start:end].to_numpy()
                    if prefix == "boundary_"
                    else summary.n_invalid_factors.iloc[start:end].gt(0).to_numpy()
                )
                # Missing/zero factors do not turn into 1 or partial-month estimates.
                usable = np.isfinite(f) & (f > 0)
                p = np.divide(
                    p,
                    f[:, :, None],
                    out=np.full_like(p, np.nan),
                    where=usable[:, :, None],
                )
                p[invalid] = np.nan
            result = estimate_batch(
                p,
                mask,
                boundary=prefix == "boundary_",
                adjacent=adjacent[start:end] if prefix == "gap_" else None,
            )
            for method in METHODS:
                result[method + "_status"][invalid] = "invalid_price_factor"
            pieces.append(pd.DataFrame(result))
        values = pd.concat(pieces, ignore_index=True).add_prefix(prefix)
        output = pd.concat([output, values], axis=1)
    return output


def complete_universe(estimates, coverage, size):
    """Keep sample-eligible months without usable rows; never replace NaN by zero."""
    universe = coverage.loc[coverage.n_sample > 0].copy()
    # Counts in the canonical coverage file are independently retained.
    result = universe.merge(
        estimates.drop(columns=["n_hlc", "n_ohlc"]),
        on=["permno", "month"],
        how="left",
        validate="one_to_one",
    )
    for prefix in VARIANTS:
        for method in METHODS:
            status = prefix + method + "_status"
            result[status] = result[status].fillna("no_clean_rows").astype("category")
            result[prefix + method + "_negative"] = (
                result[prefix + method + "_negative"]
                .astype("boolean")
                .fillna(False)
                .astype(bool)
            )
        result[prefix + "common_sample"] = (
            result[prefix + "common_sample"]
            .astype("boolean")
            .fillna(False)
            .astype(bool)
        )
    result = result.merge(
        size, on=["permno", "month"], how="left", validate="one_to_one"
    )
    result["size_available"] = np.isfinite(result.market_cap) & result.market_cap.gt(0)
    if result.duplicated(["permno", "month"]).any():
        raise ValueError("Duplicate monthly keys")
    return result


def fingerprint(root):
    """Include file content checksums for code and raw extraction provenance."""
    inputs = [
        Path(__file__),
        Path(__file__).parent / "estimators/monthly_batch.py",
        Path(__file__).parent / "settings.py",
        root / "clean/complete.json",
        root / "raw/manifest.json",
    ]
    h = hashlib.sha256()
    for p in inputs:
        h.update(p.read_bytes())
    # Invalidate resumable partitions when any local input is replaced, even
    # when the extraction-level completion marker has identical contents.
    for folder in ["clean", "raw"]:
        for p in sorted((root / folder).glob("*.parquet")):
            stat = p.stat()
            h.update(f"{folder}/{p.name}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return h.hexdigest()


def main():
    root = Path(config("DATA_DIR")) / "crsp_daily"
    clean = root / "clean"
    if not (clean / "complete.json").exists():
        raise RuntimeError("Complete CRSP cleaning before monthly estimation")
    output = root / "monthly"
    output.mkdir(parents=True, exist_ok=True)
    (output / "complete.json").unlink(missing_ok=True)
    tag = fingerprint(root)
    manifest_path = output / "manifest.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest = (
        old
        if old.get("fingerprint") == tag
        else dict(version=VERSION, fingerprint=tag, files={})
    )
    coverage = pd.read_parquet(clean / "stock_month_coverage.parquet")
    size = pd.read_parquet(clean / "monthly_size.parquet")
    prior = None
    previous_calendar = np.array([], dtype="datetime64[ns]")
    for year in range(CRSP_CORE_START.year, CRSP_CORE_END.year + 1):
        d = pd.read_parquet(clean / f"daily_{year}.parquet", columns=COLS)
        calendar = pd.read_parquet(
            root / "raw" / f"daily_{year}.parquet", columns=["date"]
        ).date.unique()
        calendar = np.unique(np.concatenate([previous_calendar, calendar]))
        filename = f"estimates_{year}.parquet"
        if filename not in manifest["files"] or not (output / filename).exists():
            packed = pack_months(d, prior, calendar)
            result = estimate_packed(packed)
            yearmask = coverage.month.dt.year.eq(year)
            result = complete_universe(
                result, coverage.loc[yearmask], size.loc[size.month.dt.year.eq(year)]
            )
            save_parquet(result, output / filename)
            manifest["files"][filename] = dict(
                rows=len(result), common_sample=int(result.common_sample.sum())
            )
            write_json(manifest_path, manifest)
            print(
                f"{year}: {len(result):,} months; {int(result.common_sample.sum()):,} baseline common-sample months",
                flush=True,
            )
        else:
            print(f"{year}: reused completed monthly partition", flush=True)
        combined = pd.concat([prior, d], ignore_index=True) if prior is not None else d
        prior = (
            combined.sort_values(["permno", "date"])
            .groupby("permno", sort=False)
            .tail(2)[COLS]
        )
        previous_calendar = calendar[-25:]
    write_json(
        output / "complete.json",
        dict(
            fingerprint=tag,
            files=manifest["files"],
            baseline="OHLC / positive CFACPR, within calendar month, final zero truncation",
            units="proportion; 0.01=1%",
            paper_empirical_scripts_verified=False,
            size_groups_assigned=False,
        ),
    )


if __name__ == "__main__":
    main()
