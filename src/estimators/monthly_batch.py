"""Batched monthly estimators with explicit moment ownership and final clipping.

Prices have shape (groups, observations, OHLC). `current` marks observations
belonging to the target month; earlier observations supply lags only. Baseline
requires all observations in each moment to belong to the month. `boundary`
assigns each moment to its final observation's month, permitting prior lags.

EDGE uses the equations in the local Part A scalar edge function; differential
tests enforce agreement. Competitors follow the pinned author R reference,
with final zero truncation as in paper §2.2, rather than package abs defaults.
No positive estimate is imputed for undefined moments. Units are proportions.
"""

import warnings

import numpy as np


def lag(x, periods=1):
    result = np.full_like(x, np.nan)
    result[:, periods:] = x[:, :-periods]
    return result


def mean(x):
    return np.nanmean(x, axis=1)


def signed_root(x):
    return np.sign(x) * np.sqrt(np.abs(x))


def estimate_batch(prices, current, boundary=False, adjacent=None):
    """Return arrays of estimates, signed intermediates and reason codes.

    Missing HLC is allowed for padding/context; production current HLC rows
    have already passed cleaning. Missing opens remain in their original rows.
    Roll uses sample covariance (ddof=1), hence at least two lagged-return pairs.
    CS averages signed two-day spreads before final clipping, never CS2.
    """
    prices = np.asarray(prices, dtype=float)
    current = np.asarray(current, dtype=bool)
    if prices.ndim != 3 or prices.shape[-1] != 4 or prices.shape[:2] != current.shape:
        raise ValueError(
            "Expected prices (groups, observations, 4) and matching current mask"
        )
    if np.any(np.isfinite(prices) & (prices <= 0)) or np.isinf(prices).any():
        raise ValueError("Prices must be positive or missing")
    if adjacent is not None and np.shape(adjacent) != current.shape:
        raise ValueError("adjacent must match the current mask")
    with (
        warnings.catch_warnings(),
        np.errstate(divide="ignore", invalid="ignore", over="ignore"),
    ):
        warnings.simplefilter("ignore", RuntimeWarning)
        o, h, l, c = np.moveaxis(np.log(prices), -1, 0)  # noqa: E741 - paper notation
        m = (h + l) / 2
        h1, l1, c1, m1, c2 = lag(h), lag(l), lag(c), lag(m), lag(c, 2)
        pair = current.copy()
        triple = current.copy()
        if not boundary:
            pair &= np.nan_to_num(lag(current.astype(float)), nan=0).astype(bool)
            triple = pair & np.nan_to_num(lag(current.astype(float), 2), nan=0).astype(
                bool
            )
        if adjacent is not None:
            adjacent = np.asarray(adjacent, dtype=bool)
            pair &= adjacent
            triple &= adjacent & np.nan_to_num(
                lag(adjacent.astype(float)), nan=0
            ).astype(bool)

        # Part A EDGE algebra, reduced independently for each stock-month.
        r1, r2, r3, r4, r5 = [
            np.where(pair, x, np.nan) for x in (m - o, o - m1, m - c1, c1 - m1, o - c1)
        ]
        tau = np.where(
            pair & np.isfinite(h) & np.isfinite(l) & np.isfinite(c1),
            (h != l) | (l != c1),
            np.nan,
        )
        po1 = tau * np.where(np.isnan(o) | np.isnan(h), np.nan, o != h)
        po2 = tau * np.where(np.isnan(o) | np.isnan(l), np.nan, o != l)
        pc1 = tau * np.where(np.isnan(c1) | np.isnan(h1), np.nan, c1 != h1)
        pc2 = tau * np.where(np.isnan(c1) | np.isnan(l1), np.nan, c1 != l1)
        pt, po, pc = mean(tau), mean(po1) + mean(po2), mean(pc1) + mean(pc2)
        nt = np.nansum(tau, axis=1)
        d1 = r1 - (mean(r1) / pt)[:, None] * tau
        d3 = r3 - (mean(r3) / pt)[:, None] * tau
        d5 = r5 - (mean(r5) / pt)[:, None] * tau
        x1 = (-4 / po)[:, None] * d1 * r2 + (-4 / pc)[:, None] * d3 * r4
        x2 = (-4 / po)[:, None] * d1 * r5 + (-4 / pc)[:, None] * d5 * r4
        e1, e2 = mean(x1), mean(x2)
        v1, v2 = mean(x1 * x1) - e1 * e1, mean(x2 * x2) - e2 * e2
        vt = v1 + v2
        edge_s2 = np.where(vt > 0, (v2 * e1 + v1 * e2) / vt, (e1 + e2) / 2)
        edge_s2[(nt < 2) | (po == 0) | (pc == 0)] = np.nan

        ar_terms = np.where(pair, 4 * (c1 - m1) * (c1 - m), np.nan)
        ar_s2 = mean(ar_terms)

        # Covariance: pairwise complete adjacent returns, no zero imputation.
        rnew, rold = c - c1, c1 - c2
        roll_valid = triple & np.isfinite(rnew) & np.isfinite(rold)
        rn, ro = np.where(roll_valid, rnew, np.nan), np.where(roll_valid, rold, np.nan)
        nroll = roll_valid.sum(axis=1)
        # Center before multiplying for numerical stability.
        covariance = np.nansum(
            (rn - mean(rn)[:, None]) * (ro - mean(ro)[:, None]), axis=1
        ) / (nroll - 1)
        roll_s2 = -4 * covariance
        roll_s2[nroll < 2] = np.nan

        # CS overnight correction in LOG prices, without modifying beta ranges.
        gap = np.maximum(0, c1 - h) + np.minimum(0, c1 - l)
        beta = (h - l) ** 2 + (h1 - l1) ** 2
        gamma = (np.maximum(h + gap, h1) - np.minimum(l + gap, l1)) ** 2
        k = 3 - 2 * np.sqrt(2)
        alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
        cs_terms = np.where(pair, 2 * np.tanh(alpha / 2), np.nan)
        cs_signed = mean(cs_terms)

    result = dict(
        edge_s2=edge_s2,
        edge_signed=signed_root(edge_s2),
        edge_abs=np.sqrt(np.abs(edge_s2)),
        ar_s2=ar_s2,
        roll_s2=roll_s2,
        cs_signed=cs_signed,
        edge_informative_periods=nt.astype(int),
        roll_pairs=nroll,
        ar_pairs=np.isfinite(ar_terms).sum(axis=1),
        cs_pairs=np.isfinite(cs_terms).sum(axis=1),
    )
    for name, value in [
        ("edge", edge_s2),
        ("ar", ar_s2),
        ("roll", roll_s2),
        ("cs", cs_signed),
    ]:
        finite = np.isfinite(value)
        estimate = (
            np.maximum(value, 0) if name == "cs" else np.sqrt(np.maximum(value, 0))
        )
        result[name] = np.where(finite, estimate, np.nan)
        result[name + "_negative"] = finite & (value < 0)
        status = np.where(finite, "ok", "nonfinite_moments").astype(object)
        if name == "edge":
            status[~finite & (nt < 2)] = "insufficient_informative_periods"
            status[~finite & ((po == 0) | (pc == 0))] = "degenerate_prices"
            no_open = ~np.any(current & np.isfinite(o), axis=1)
            status[~finite & no_open] = "missing_open"
        else:
            count = result[name + "_pairs"]
            status[~finite & (count < (2 if name == "roll" else 1))] = (
                "insufficient_pairs"
            )
        result[name + "_status"] = status
    result["common_sample"] = np.logical_and.reduce(
        [np.isfinite(result[m]) for m in ["edge", "ar", "cs", "roll"]]
    )
    return result
