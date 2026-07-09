"""Canonical data schemas and time helpers shared by every source.

The whole point of the package: no matter which venue the bytes came from,
callers get back the *same* shape. Bar sources emit a UTC-indexed OHLCV frame;
funding sources emit a UTC-indexed funding frame. All the per-venue mess
(column order, tz quirks, string vs ms timestamps) is beaten into this shape
here, in one place.
"""
from __future__ import annotations

import pandas as pd

OHLCV = ["open", "high", "low", "close", "volume"]


# --------------------------------------------------------------------------- #
# time helpers
# --------------------------------------------------------------------------- #
def to_utc_ts(x) -> pd.Timestamp | None:
    """Coerce anything date-ish to a tz-aware UTC Timestamp (or None)."""
    if x is None:
        return None
    ts = pd.Timestamp(x)
    return ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")


def resolve_window(start=None, end=None, years=None,
                   default_years: float = 5.0) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Turn (start|end|years) into a concrete [start, end] UTC window.

    Precedence: an explicit ``start`` wins over ``years``. ``end`` defaults to now.
    """
    e = to_utc_ts(end) or pd.Timestamp.now(tz="UTC")
    if start is not None:
        s = to_utc_ts(start)
    else:
        yrs = default_years if years is None else years
        s = e - pd.Timedelta(days=float(yrs) * 365.25)
    # floor to whole seconds: exchange APIs take second/ms precision, and sub-
    # second values trigger "discarding nonzero nanoseconds" warnings downstream
    return s.floor("s"), e.floor("s")


# --------------------------------------------------------------------------- #
# bar normalization
# --------------------------------------------------------------------------- #
def empty_bars() -> pd.DataFrame:
    idx = pd.DatetimeIndex([], name="timestamp", tz="UTC")
    return pd.DataFrame(columns=OHLCV, index=idx)


def normalize_bars(df: pd.DataFrame | None) -> pd.DataFrame:
    """Return a clean OHLCV frame: UTC DatetimeIndex named 'timestamp',
    lowercase float columns, deduped + sorted. Accepts a timestamp in the
    index or in a 'timestamp'/'time'/'date'/'datetime' column."""
    if df is None or len(df) == 0:
        return empty_bars()

    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    if not isinstance(df.index, pd.DatetimeIndex):
        for c in ("timestamp", "time", "date", "datetime"):
            if c in df.columns:
                df = df.set_index(c)
                break

    # utc=True localizes naive->UTC and converts aware->UTC in one shot
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "timestamp"

    keep = [c for c in OHLCV if c in df.columns]
    extra = [c for c in ("adj_close",) if c in df.columns]
    for c in keep + extra:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[keep + extra]

    df = df[~df.index.duplicated(keep="first")].sort_index()
    price_cols = [c for c in ("open", "high", "low", "close") if c in df.columns]
    if price_cols:
        df = df.dropna(subset=price_cols)
    return df


# --------------------------------------------------------------------------- #
# funding normalization
# --------------------------------------------------------------------------- #
def empty_funding() -> pd.DataFrame:
    idx = pd.DatetimeIndex([], name="time", tz="UTC")
    return pd.DataFrame(columns=["funding_rate", "mark_price"], index=idx)


def normalize_funding(df: pd.DataFrame | None) -> pd.DataFrame:
    """UTC 'time'-indexed frame with 'funding_rate' and 'mark_price' columns."""
    if df is None or len(df) == 0:
        return empty_funding()
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if not isinstance(df.index, pd.DatetimeIndex):
        for c in ("time", "timestamp", "date"):
            if c in df.columns:
                df = df.set_index(c)
                break
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "time"
    if "funding_rate" not in df.columns:
        raise ValueError("funding frame missing 'funding_rate'")
    df["funding_rate"] = pd.to_numeric(df["funding_rate"], errors="coerce")
    if "mark_price" not in df.columns:
        df["mark_price"] = float("nan")
    df["mark_price"] = pd.to_numeric(df["mark_price"], errors="coerce")
    df = df[["funding_rate", "mark_price"]]
    return df[~df.index.duplicated(keep="first")].sort_index().dropna(subset=["funding_rate"])


def annualized_funding_pct(df: pd.DataFrame) -> float:
    """Annualized mean funding (%), inferred from the data's own cadence.

    Venues settle on different schedules (Bybit/OKX every 8h, Hyperliquid every
    1h). Rather than hardcode a multiplier, derive periods-per-year from the
    median spacing between timestamps, so the number is right regardless of source.
    """
    if df is None or len(df) < 2 or "funding_rate" not in df.columns:
        return float("nan")
    period_s = df.index.to_series().diff().dropna().dt.total_seconds().median()
    if not period_s or period_s <= 0:
        return float("nan")
    periods_per_year = 365.25 * 24 * 3600 / period_s
    return float(df["funding_rate"].mean() * periods_per_year * 100)
