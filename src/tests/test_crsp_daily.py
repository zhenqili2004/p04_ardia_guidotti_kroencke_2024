"""Synthetic data-contract tests; these do not establish WRDS access or replication."""

import json

import numpy as np
import pandas as pd
import pytest

from clean_crsp_daily import (
    annotate,
    attach_history,
    diagnostics,
    size_snapshots,
    validate_history,
)
from crsp_schema import candidates, choose_source
from pull_crsp_daily import extract


def history():
    return pd.DataFrame(
        dict(
            permno=[10001, 10001],
            valid_from=pd.to_datetime(["1993-04-01", "1993-05-05"]),
            valid_to=pd.to_datetime(["1993-05-04", "1993-05-31"]),
            cusip=["00123456", "00987654"],
            ticker=["OLD", "NEW"],
            share_code=[10, 11],
            exchange_code=[1, 3],
        )
    )


def daily():
    dates = pd.to_datetime(
        [
            "1993-04-30",
            "1993-05-03",
            "1993-05-04",
            "1993-05-05",
            "1993-05-06",
            "1993-05-07",
            "1993-06-01",
        ]
    )
    return pd.DataFrame(
        dict(
            permno=10001,
            permco=10000,
            date=dates,
            open_raw=[10.0, 10.0, np.nan, 10.0, 10.0, 10.0, 10.0],
            high_raw=11.0,
            low_raw=9.0,
            close_raw=[10.0, -10.0, 10.0, 12.0, 10.0, 10.0, 10.0],
            price_raw=[10.0, -10.0, 10.0, 12.0, 10.0, np.nan, 10.0],
            volume=100.0,
            shares_thousands=2000.0,
            price_factor=[2.0, 2.0, 2.0, 2.0, 1.0, 1.0, 1.0],
            share_factor=1.0,
        )
    )


def test_interval_boundaries_history_changes_and_expiry():
    d = attach_history(daily(), history()).set_index("date")
    assert d.loc["1993-05-04", "ticker"] == "OLD"
    assert d.loc["1993-05-05", "ticker"] == "NEW"
    assert pd.isna(d.loc["1993-06-01", "ticker"])
    assert not d.loc["1993-06-01", "history_matched"]
    assert len(d) == len(daily())


def test_overlapping_intervals_and_duplicate_daily_keys_fail():
    h = history()
    h.loc[1, "valid_from"] = pd.Timestamp("1993-05-04")
    with pytest.raises(ValueError, match="Overlapping"):
        validate_history(h)
    with pytest.raises(ValueError, match="Duplicate"):
        attach_history(pd.concat([daily(), daily().iloc[:1]]), history())


def test_paper_price_filters_buffer_and_separate_cap():
    d = annotate(daily(), history(), "legacy").set_index("date")
    assert not d.loc["1993-04-30", "in_core"]
    assert pd.isna(d.loc["1993-05-03", "close"])
    assert d.loc["1993-05-03", "close_raw"] == -10
    assert d.loc["1993-05-03", "market_cap"] == 20_000_000
    assert not d.loc["1993-05-03", "valid_hlc"]
    assert d.loc["1993-05-04", "valid_hlc"]
    assert not d.loc["1993-05-04", "valid_ohlc"]
    assert not d.loc["1993-05-05", "valid_hlc"]
    assert d.loc["1993-05-06", "close"] == 10  # no factor adjustment yet
    assert d.loc["1993-05-06", "price_factor"] == 1
    assert not d.loc["1993-06-01", "sample_eligible"]


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("high_raw", 8.0, "reversed_range"),
        ("open_raw", 12.0, "open_outside"),
        ("low_raw", 0.0, "missing_hlc"),
        ("close_raw", np.inf, "missing_hlc"),
    ],
)
def test_additional_invalid_prices(field, value, reason):
    data = daily().iloc[[4]].copy()
    data[field] = value
    d = annotate(data, history(), "legacy")
    assert d[reason].item()
    assert not d.valid_hlc.item()


def test_ciz_unsigned_quote_prices_and_common_stock_mapping():
    data = daily().iloc[[1, 4]].copy()
    data["price_raw"] = 10.0
    data["close_raw"] = 10.0
    data["price_flag"] = ["BA", "TR"]
    data["cap_thousands_raw"] = 20_000.0
    data["cap_flag"] = "A"
    h = history().drop(columns=["share_code", "exchange_code"])
    for col, value in dict(
        share_type="NS",
        security_type="EQTY",
        security_subtype="COM",
        us_incorporated="Y",
        issuer_type="CORP",
        exchange="N",
        condition="RW",
        trading_status="A",
    ).items():
        h[col] = value
    d = annotate(data, h, "ciz")
    assert list(d.valid_ohlc) == [False, True]
    assert list(d.cap_difference) == [0.0, 0.0]
    h["us_incorporated"] = "N"
    assert not annotate(data, h, "ciz").sample_eligible.any()
    h["us_incorporated"] = "Y"
    h["trading_status"] = "H"
    assert not annotate(data, h, "ciz").sample_eligible.any()


def test_counts_no_minimum_days_and_no_cap_backfill():
    d = annotate(daily(), history(), "legacy")
    stages, coverage = diagnostics(d)
    may = coverage.loc[coverage.month.eq(pd.Timestamp("1993-05-31"))].iloc[0]
    assert (may.n_raw, may.n_sample, may.n_hlc, may.n_ohlc) == (5, 5, 3, 2)
    counts = stages.loc[stages.month.eq(pd.Timestamp("1993-05-31"))]
    assert counts.rows.is_monotonic_decreasing
    assert counts.iloc[-1].rows == 2
    cap = size_snapshots(d)
    assert cap.cap_date.item() == pd.Timestamp("1993-05-07")
    assert pd.isna(cap.market_cap.item())  # do not silently use May 6


def test_schema_preference_and_missing_required_columns():
    legacy, ciz = candidates("legacy")[0], candidates("ciz")[0]
    columns = {}
    for source in (legacy, ciz):
        columns[source.schema, source.daily_table] = set(source.daily.values())
        columns[source.schema, source.history_table] = set(source.history.values())
    assert choose_source(columns).kind == "legacy"
    assert choose_source(columns, "ciz").kind == "ciz"
    columns[legacy.schema, legacy.daily_table].remove("openprc")
    assert choose_source(columns).kind == "ciz"
    columns[ciz.schema, ciz.daily_table].remove("dlyprcflg")
    with pytest.raises(RuntimeError, match="No complete"):
        choose_source(columns)


def test_streaming_extraction_stable_null_columns_and_atomic_failure(tmp_path):
    from types import SimpleNamespace

    class Cursor:
        description = [
            SimpleNamespace(name=n) for n in ["permno", "date", "open_raw", "ticker"]
        ]

        def __init__(self, chunks):
            self.chunks = iter(chunks)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, *args):
            pass

        def fetchmany(self, size):
            chunk = next(self.chunks)
            if isinstance(chunk, Exception):
                raise chunk
            return chunk

    class Connection:
        def __init__(self, chunks):
            self.chunks = chunks

        def cursor(self, name):
            return Cursor(self.chunks)

    path = tmp_path / "test.parquet"
    first = [(1, pd.Timestamp("2000-01-01"), None, None)]
    second = [(2, pd.Timestamp("2000-01-02"), 10.0, "XYZ")]
    assert extract(Connection([first, second, []]), "", {}, path) == 2
    assert pd.read_parquet(path).ticker.iloc[1] == "XYZ"
    original = path.read_bytes()
    with pytest.raises(RuntimeError, match="interrupted"):
        extract(Connection([first, RuntimeError("interrupted")]), "", {}, path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_clean_and_report_with_synthetic_raw_files(tmp_path, monkeypatch):
    import clean_crsp_daily as cleaner
    import report_crsp_coverage as reporter

    data_dir, output_dir = tmp_path / "data", tmp_path / "output"

    def config(key):
        return data_dir if key == "DATA_DIR" else output_dir

    monkeypatch.setattr(cleaner, "config", config)
    monkeypatch.setattr(reporter, "config", config)
    monkeypatch.setattr(cleaner, "CRSP_CORE_END", pd.Timestamp("1993-12-31"))
    raw = data_dir / "crsp_daily" / "raw"
    raw.mkdir(parents=True)
    daily().to_parquet(raw / "daily_1993.parquet", index=False)
    history().to_parquet(raw / "identifier_history.parquet", index=False)
    manifest = dict(
        spec=dict(source=dict(kind="legacy")),
        fingerprint="synthetic-test",
        files={"daily_1993.parquet": {}, "identifier_history.parquet": {}},
    )
    (raw / "manifest.json").write_text(json.dumps(manifest))
    cleaner.main()
    reporter.main()
    clean = data_dir / "crsp_daily" / "clean"
    result = pd.read_parquet(clean / "daily_1993.parquet")
    assert len(result) == 4  # April buffer plus three valid HLC days in May
    assert len(pd.read_parquet(clean / "audit_1993.parquet")) == 7
    assert (output_dir / "crsp_daily" / "coverage.pdf").exists()
    assert (clean / "complete.json").exists()
