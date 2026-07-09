"""Canonical timeframes + resampling. One vocabulary of timeframe strings for
the whole package; each source maps these onto whatever its API calls them.

'Native vs resample' knowledge (e.g. Coinbase has no 4h candle, so build it
from 1h) lives *inside* each source, because it differs per venue. What lives
here is the shared vocabulary and the pandas resample rules.
"""
from __future__ import annotations

import pandas as pd

# canonical timeframe strings, ascending
CANON = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo", "1y"]

SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
    "1w": 604800, "1mo": 2_592_000, "1y": 31_536_000,
}

# pandas offset alias used when resampling *up* to this timeframe.
# 1MS/1YS = calendar-month/year start, matching the original download scripts.
PANDAS_RULE = {
    "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
    "1h": "1h", "4h": "4h", "1d": "1D",
    "1w": "1W", "1mo": "1MS", "1y": "1YS",
}

_AGG = {"open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum"}


def validate(tf: str) -> str:
    if tf not in CANON:
        raise ValueError(f"unknown timeframe {tf!r}; valid: {CANON}")
    return tf


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Aggregate finer bars up to `rule`. Extra columns (e.g. adj_close) are
    carried with a last-value rule so they survive."""
    if df is None or len(df) == 0:
        return df
    agg = {c: _AGG[c] for c in _AGG if c in df.columns}
    for c in df.columns:
        agg.setdefault(c, "last")
    return df.resample(rule).agg(agg).dropna(how="all")


def resample_to(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    return resample_ohlc(df, PANDAS_RULE[validate(tf)])
