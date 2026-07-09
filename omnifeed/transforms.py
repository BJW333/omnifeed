"""Optional post-processing the *data layer* deliberately does not bake in.

Fetching returns UTC bars, always. Strategy-specific reshaping — e.g. the ORB
edge needs New-York regular-session bars — lives here so it's explicit and
reusable rather than hard-coded into a downloader.
"""
from __future__ import annotations

import pandas as pd

from .timeframe import resample_ohlc


def to_tz(df: pd.DataFrame, tz: str) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return df
    out = df.copy()
    out.index = out.index.tz_convert(tz)
    return out


def regular_session(df: pd.DataFrame, start="09:30", end="16:00",
                    tz="America/New_York", drop_tz=True) -> pd.DataFrame:
    """Keep only the regular cash session, in the exchange's local time.

    Reproduces the Alpaca ORB downloader: convert to ET, slice 09:30-16:00 so
    the opening range is real, then drop tz for tz-naive CSVs.
    """
    if df is None or len(df) == 0:
        return df
    out = to_tz(df, tz).between_time(start, end)
    if drop_tz:
        out.index = out.index.tz_localize(None)
    return out


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return resample_ohlc(df, rule)
