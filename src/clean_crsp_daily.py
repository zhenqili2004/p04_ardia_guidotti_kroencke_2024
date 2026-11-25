"""CRSP price eligibility, historical identifiers, size inputs and audit counts.

No spread estimation, forward filling, corporate-action adjustment, winsorization,
or minimum-observation threshold is applied here. Retain April 1993 as a buffer.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from settings import CRSP_CORE_END, CRSP_CORE_START, CRSP_EXTRACT_START, config


def validate_history(history):
    """Reject ambiguous inclusive intervals, including exact duplicates."""
    h = history.sort_values(["permno", "valid_from", "valid_to"]).copy()
    if h[["permno", "valid_from", "valid_to"]].isna().any().any():
        raise ValueError("Identifier history has missing keys or interval dates.")
    if (h.valid_from > h.valid_to).any():
        raise ValueError("Identifier history contains reversed intervals.")
    previous_end = h.groupby("permno").valid_to.transform(lambda s: s.cummax().shift())
    if (h.valid_from <= previous_end).any():
        raise ValueError(
            "Overlapping identifier intervals; resolve at source, do not deduplicate."
        )
    return h


def attach_history(daily, history):
    """Attach at most one historical record per PERMNO/date, inclusive ends."""
    if daily[["permno", "date"]].isna().any().any():
        raise ValueError("Daily data has missing PERMNO/date keys.")
    if daily.duplicated(["permno", "date"]).any():
        raise ValueError(
            "Duplicate PERMNO/date observations; do not silently deduplicate."
        )
    h = validate_history(history)
    d = daily.copy()
    d["permno"] = d.permno.astype("int64")
    h["permno"] = h.permno.astype("int64")
    out = pd.merge_asof(
        d.sort_values("date"),
        h.sort_values("valid_from"),
        left_on="date",
        right_on="valid_from",
        by="permno",
        direction="backward",
        allow_exact_matches=True,
    )
    out["history_matched"] = out.valid_to.notna() & out.date.le(out.valid_to)
    # Prevent expired identifiers/classifications from leaking through asof.
    for col in h.columns.difference(["permno"]):
        out.loc[~out.history_matched, col] = (
            pd.NaT if pd.api.types.is_datetime64_any_dtype(out[col]) else pd.NA
        )
    return out.sort_values(["permno", "date"]).reset_index(drop=True)


def annotate(daily, history, kind):
    if kind not in {"legacy", "ciz"}:
        raise ValueError("Unknown CRSP source kind")
    d = attach_history(daily, history)
    d["month"] = d.date.dt.to_period("M").dt.to_timestamp("M")
    d["in_core"] = d.date.between(CRSP_CORE_START, CRSP_CORE_END)
    if kind == "legacy":
        d["common_stock"] = d.share_code.isin([10, 11])
        d["eligible_exchange"] = d.exchange_code.isin([1, 2, 3])
        d["quote_close"] = d.price_raw.lt(0)
        d["cap_price_is_quote"] = d.price_raw.lt(0)
    else:
        d["common_stock"] = (
            d.share_type.eq("NS")
            & d.security_type.eq("EQTY")
            & d.security_subtype.eq("COM")
            & d.us_incorporated.eq("Y")
            & d.issuer_type.isin(["ACOR", "CORP"])
        )
        d["eligible_exchange"] = (
            d.exchange.isin(["N", "A", "Q"])
            & d.condition.eq("RW")
            & d.trading_status.eq("A")
        )
        d["quote_close"] = d.price_flag.eq("BA").fillna(False)
        d["cap_price_is_quote"] = d.price_flag.eq("BA").fillna(False)
    for col in ["common_stock", "eligible_exchange"]:
        d[col] = d[col].fillna(False).astype(bool)
    for field in ("open", "high", "low", "close"):
        raw = d[f"{field}_raw"]
        d[f"{field}_nonpositive"] = raw.le(0).fillna(False)
        d[field] = raw.where(np.isfinite(raw) & raw.gt(0))
    # CIZ dlyprc is unsigned; BA is explicitly not a transaction close.
    d.loc[d.quote_close, "close"] = np.nan
    d["missing_hlc"] = d[["high", "low", "close"]].isna().any(axis=1)
    d["missing_open"] = d.open.isna()
    d["reversed_range"] = d.low.gt(d.high)
    d["close_outside"] = d.close.lt(d.low) | d.close.gt(d.high)
    d["open_outside"] = d.open.notna() & (d.open.lt(d.low) | d.open.gt(d.high))
    d["sample_eligible"] = d.history_matched & d.common_stock & d.eligible_exchange
    d["valid_hlc"] = (
        d.sample_eligible
        & ~d.missing_hlc
        & ~d.reversed_range
        & ~d.close_outside
        & ~d.open_outside
    )
    d["valid_ohlc"] = d.valid_hlc & ~d.missing_open
    for col in ("cusip", "ticker"):
        d[col] = d[col].astype("string").str.strip().replace("", pd.NA)
    d["missing_identifier"] = d[["cusip", "ticker"]].isna().any(axis=1)
    # Cap is a distinct size input: abs(price) is allowed HERE, never in OHLC.
    d["shares"] = d.shares_thousands * 1000.0
    d["market_cap"] = (d.price_raw.abs() * d.shares).where(
        np.isfinite(d.price_raw)
        & d.price_raw.ne(0)
        & np.isfinite(d.shares)
        & d.shares.gt(0)
    )
    if kind == "ciz":
        d["source_market_cap"] = d.cap_thousands_raw * 1000.0
        d["cap_difference"] = d.market_cap - d.source_market_cap
    d["invalid_price_factor"] = ~np.isfinite(d.price_factor) | d.price_factor.le(0)
    return d


FILTERS = [
    ("raw", None),
    ("historical_classification", "history_matched"),
    ("common_stock", "common_stock"),
    ("exchange", "eligible_exchange"),
    ("transaction_hlc", "missing_hlc"),
    ("ordered_range", "reversed_range"),
    ("close_in_range", "close_outside"),
    ("open_in_range_if_present", "open_outside"),
    ("complete_ohlc", "missing_open"),
]


def diagnostics(d):
    """Daily counts and stock-month counts; no estimator eligibility asserted."""
    d = d.loc[d.in_core].copy()
    stages = []
    keep = pd.Series(True, index=d.index)
    for stage, col in FILTERS:
        if col:
            condition = d[col]
            keep &= (
                ~condition
                if col
                in {
                    "missing_hlc",
                    "reversed_range",
                    "close_outside",
                    "open_outside",
                    "missing_open",
                }
                else condition
            )
        selected = d.loc[keep]
        counts = selected.groupby("month").agg(
            rows=("permno", "size"), securities=("permno", "nunique")
        )
        counts = (
            counts.reindex(sorted(d.month.unique()), fill_value=0)
            .rename_axis("month")
            .reset_index()
        )
        counts["stage"] = stage
        stages.append(counts)
    # Includes unsuccessful stock-months so lost coverage is measurable.
    coverage = d.groupby(["permno", "month"], as_index=False).agg(
        n_raw=("date", "size"),
        n_sample=("sample_eligible", "sum"),
        n_hlc=("valid_hlc", "sum"),
        n_ohlc=("valid_ohlc", "sum"),
        n_missing_identifier=("missing_identifier", "sum"),
        n_quote_close=("quote_close", "sum"),
        n_invalid_price_factor=("invalid_price_factor", "sum"),
        n_price_factors=("price_factor", "nunique"),
    )
    return pd.concat(stages, ignore_index=True), coverage


def size_snapshots(d):
    """Last observed eligible date in each month; retain missing cap at that date.

    Does not backfill cap or form deciles. Does not aggregate PERMNOs by PERMCO.
    """
    columns = [
        "permno",
        "permco",
        "month",
        "date",
        "market_cap",
        "price_raw",
        "shares",
        "cap_price_is_quote",
        "cusip",
        "ticker",
    ]
    columns += [
        c
        for c in ["price_flag", "cap_flag", "source_market_cap", "cap_difference"]
        if c in d
    ]
    return (
        d.loc[d.in_core & d.sample_eligible]
        .sort_values(["permno", "date"])
        .groupby(["permno", "month"], sort=False)
        .tail(1)[columns]
        .rename(columns={"date": "cap_date"})
        .reset_index(drop=True)
    )


def save_parquet(frame, path):
    tmp = path.with_suffix(".parquet.tmp")
    frame.to_parquet(tmp, index=False, compression="zstd")
    tmp.replace(path)


def main():
    root = Path(config("DATA_DIR")) / "crsp_daily"
    raw, clean = root / "raw", root / "clean"
    out = Path(config("OUTPUT_DIR")) / "crsp_daily"
    manifest = json.loads((raw / "manifest.json").read_text())
    kind = manifest["spec"]["source"]["kind"]
    expected = [
        f"daily_{y}.parquet"
        for y in range(CRSP_EXTRACT_START.year, CRSP_CORE_END.year + 1)
    ]
    for name in ["identifier_history.parquet", *expected]:
        if name not in manifest["files"] or not (raw / name).exists():
            raise RuntimeError(f"Incomplete raw extraction: {name}")
    clean.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    (clean / "complete.json").unlink(missing_ok=True)
    history = pd.read_parquet(raw / "identifier_history.parquet")
    validate_history(history)
    save_parquet(history, clean / "identifier_history.parquet")
    stages, coverages, caps = [], [], []
    for name in expected:
        d = annotate(pd.read_parquet(raw / name), history, kind)
        if not d.date.between(CRSP_EXTRACT_START, CRSP_CORE_END).all():
            raise ValueError(
                "Raw partition includes dates outside the extraction window."
            )
        if not d.date.dt.year.eq(int(name[6:10])).all():
            raise ValueError("Daily observations are in the wrong annual partition.")
        save_parquet(d.loc[d.valid_hlc], clean / name)
        # Flags plus keys preserve the disposition of every input observation.
        audit = ["permno", "date", "month"] + list(
            d.select_dtypes(include="bool").columns
        )
        save_parquet(d[audit], clean / name.replace("daily_", "audit_"))
        stage, coverage = diagnostics(d)
        stages.append(stage)
        coverages.append(coverage)
        caps.append(size_snapshots(d))
        print(
            f"Cleaned {name}: {int(d.valid_hlc.sum()):,} HLC-eligible rows", flush=True
        )
    pd.concat(stages, ignore_index=True).to_csv(out / "filter_counts.csv", index=False)
    save_parquet(
        pd.concat(coverages, ignore_index=True), clean / "stock_month_coverage.parquet"
    )
    cap = pd.concat(caps, ignore_index=True).sort_values(["permno", "cap_date"])
    save_parquet(cap, clean / "monthly_size.parquet")
    save_parquet(
        cap.groupby("permno", sort=False).tail(1), clean / "last_observed_size.parquet"
    )
    from pull_crsp_daily import write_json

    write_json(
        clean / "complete.json",
        dict(
            raw_fingerprint=manifest["fingerprint"],
            kind=kind,
            note="CRSP-only input panel; no estimator or TAQ common-sample filter.",
        ),
    )


if __name__ == "__main__":
    main()
