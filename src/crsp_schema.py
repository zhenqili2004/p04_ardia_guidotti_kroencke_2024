"""Explicit CRSP adapters. Live column/privilege validation precedes extraction.

CIZ classification mapping follows WRDS ciztosiz.sas (January 2026).
Aliases below do not imply that CIZ and legacy vintages are numerically equal.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    kind: str
    schema: str
    daily_table: str
    history_table: str
    daily: dict
    history: dict

    @property
    def daily_path(self):
        return f"{self.schema}.{self.daily_table}"

    @property
    def history_path(self):
        return f"{self.schema}.{self.history_table}"


LEGACY_DAILY = dict(
    permno="permno",
    permco="permco",
    date="date",
    open_raw="openprc",
    high_raw="askhi",
    low_raw="bidlo",
    close_raw="prc",
    price_raw="prc",
    volume="vol",
    shares_thousands="shrout",
    price_factor="cfacpr",
    share_factor="cfacshr",
)
LEGACY_HISTORY = dict(
    permno="permno",
    valid_from="namedt",
    valid_to="nameendt",
    cusip="ncusip",
    ticker="ticker",
    share_code="shrcd",
    exchange_code="exchcd",
)
CIZ_DAILY = dict(
    permno="permno",
    permco="permco",
    date="dlycaldt",
    open_raw="dlyopen",
    high_raw="dlyhigh",
    low_raw="dlylow",
    close_raw="dlyclose",
    price_raw="dlyprc",
    price_flag="dlyprcflg",
    volume="dlyvol",
    shares_thousands="shrout",
    price_factor="dlycumfacpr",
    share_factor="dlycumfacshr",
    cap_thousands_raw="dlycap",
    cap_flag="dlycapflg",
)
CIZ_HISTORY = dict(
    permno="permno",
    valid_from="secinfostartdt",
    valid_to="secinfoenddt",
    cusip="cusip",
    ticker="ticker",
    share_type="sharetype",
    security_type="securitytype",
    security_subtype="securitysubtype",
    us_incorporated="usincflg",
    issuer_type="issuertype",
    exchange="primaryexch",
    condition="conditionaltype",
    trading_status="tradingstatusflg",
)


def candidates(mode="auto"):
    """Prefer legacy for the historical replication; never mix vintages."""
    if mode not in {"auto", "legacy", "ciz"}:
        raise ValueError("source must be auto, legacy, or ciz")
    result = []
    if mode in {"auto", "legacy"}:
        for schema in ("crsp", "crspm", "crsp_a_stock"):
            for history in ("dsenames", "stocknames"):
                result.append(
                    Source(
                        "legacy", schema, "dsf", history, LEGACY_DAILY, LEGACY_HISTORY
                    )
                )
    if mode in {"auto", "ciz"}:
        for schema in ("crsp", "crspm", "crsp_a_stock"):
            result.append(
                Source(
                    "ciz",
                    schema,
                    "dsf_v2",
                    "stksecurityinfohist",
                    CIZ_DAILY,
                    CIZ_HISTORY,
                )
            )
    return result


def choose_source(columns, mode="auto"):
    """columns maps (schema, table) to the accessible column-name set."""
    for source in candidates(mode):
        daily = columns.get((source.schema, source.daily_table), set())
        history = columns.get((source.schema, source.history_table), set())
        if (
            set(source.daily.values()) <= daily
            and set(source.history.values()) <= history
        ):
            return source
    raise RuntimeError(
        "No complete supported CRSP daily/history schema found. "
        "Inspect the saved column inventory; do not guess field names."
    )
