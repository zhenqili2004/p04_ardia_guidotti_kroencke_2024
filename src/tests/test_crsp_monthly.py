import numpy as np
import pandas as pd

from estimate_crsp_monthly import pack_months, estimate_packed, complete_universe


def daily():
    dates = pd.to_datetime(
        [
            "1993-04-29",
            "1993-04-30",
            "1993-05-03",
            "1993-05-04",
            "1993-05-06",
            "1993-05-07",
        ]
    )
    c = np.array([100, 101, 99, 102, 100, 103.0])
    return pd.DataFrame(
        dict(
            permno=10001,
            date=dates,
            month=dates.to_period("M").to_timestamp("M"),
            open=c - 0.5,
            high=c + 1,
            low=c - 1,
            close=c,
            price_factor=1.0,
            exchange_code=1,
            cusip="00123456",
            ticker="TEST",
        )
    )


def test_pack_context_and_missing_session_not_weekends():
    d = daily()
    cal = pd.bdate_range("1993-04-29", "1993-05-07")
    summary, p, f, current, adjacent = pack_months(d, calendar=cal)
    assert len(summary) == 1 and summary.n_hlc.item() == 4
    assert summary.n_prior_rows.item() == 2
    assert summary.n_within_month_gaps.item() == 1
    assert summary.missing_sessions_between_rows.item() == 1
    assert summary.boundary_gap_sessions.item() == 0  # weekend does not count
    assert current.tolist() == [[False, False, True, True, True, True]]
    assert adjacent.tolist() == [[False, True, True, True, False, True]]
    np.testing.assert_array_equal(p[0, :, 3], d.close)


def test_adjusted_split_invariance_raw_sensitivity_and_zero_factor():
    d = daily()
    original = estimate_packed(pack_months(d))
    split = d.copy()
    split.loc[:3, ["open", "high", "low", "close"]] *= 2
    split.loc[:3, "price_factor"] = 2
    adjusted = estimate_packed(pack_months(split))
    for m in ["edge", "ar", "cs", "roll"]:
        np.testing.assert_allclose(adjusted[m], original[m], equal_nan=True, atol=1e-12)
    assert not np.isclose(adjusted.raw_roll.item(), original.raw_roll.item())
    split.loc[3, "price_factor"] = 0
    invalid = estimate_packed(pack_months(split))
    assert invalid.edge.isna().all() and invalid.roll.isna().all()
    assert invalid.edge_status.item() == "invalid_price_factor"
    assert invalid.raw_edge.notna().all()


def test_invalid_context_affects_only_boundary_specification():
    d = daily()
    d.loc[0, "price_factor"] = 0
    r = estimate_packed(pack_months(d))
    assert r.edge.notna().all()
    assert r.boundary_edge.isna().all()
    assert r.boundary_edge_status.item() == "invalid_price_factor"


def test_do_not_use_older_months_as_context():
    d = daily()
    d.loc[:1, "date"] = pd.to_datetime(["1993-03-30", "1993-03-31"])
    d["month"] = d.date.dt.to_period("M").dt.to_timestamp("M")
    summary, *_ = pack_months(d)
    assert summary.n_prior_rows.item() == 0


def test_year_boundary_prior_and_no_clean_rows():
    d = daily()
    result = estimate_packed(pack_months(d.iloc[2:], prior=d.iloc[:2]))
    full = estimate_packed(pack_months(d))
    np.testing.assert_allclose(result.boundary_edge, full.boundary_edge)
    month = pd.Timestamp("1993-05-31")
    coverage = pd.DataFrame(
        dict(
            permno=[10001, 10002],
            month=month,
            n_sample=[4, 10],
            n_hlc=[4, 0],
            n_ohlc=[4, 0],
        )
    )
    size = pd.DataFrame(
        dict(permno=[10001, 10002], month=month, market_cap=[np.nan, 1000.0])
    )
    panel = complete_universe(result, coverage, size)
    assert len(panel) == 2
    assert panel.loc[1, "edge_status"] == "no_clean_rows"
    assert np.isnan(panel.loc[1, "edge"])
    assert not panel.loc[0, "size_available"]  # missing size does not delete spread
    assert np.isfinite(panel.loc[0, "edge"])
