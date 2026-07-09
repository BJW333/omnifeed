"""Yahoo Finance via yfinance — one adapter, five asset classes.

Handles equities, ETFs, forex (EURUSD=X), futures (GC=F) and indices (^GSPC):
the symbol suffix is applied upstream in symbols.to_source_symbol, so the fetch
logic is identical for all of them. Ported from the stock path of the original
download_data.py, including the intraday-history clamps Yahoo requires.

Caveat (unchanged from before): Yahoo only serves ~60d of sub-hourly and ~730d
of hourly bars. For years of stock minute data, route to Alpaca instead.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd

from ..schema import OHLCV, normalize_bars
from ..symbols import AssetClass
from ..timeframe import resample_ohlc
from .base import BarSource

# canonical tf -> (yfinance interval, optional resample-up rule)
_MAP = {
    "1m": ("1m", None), "5m": ("5m", None), "15m": ("15m", None),
    "30m": ("30m", None),
    "1h": ("60m", None),
    "4h": ("60m", "4h"),
    "1d": ("1d", None),
    "1w": ("1wk", None),
    "1mo": ("1mo", None),
    "1y": ("1d", "1YS"),
}
# Yahoo intraday history caps (days) keyed by yfinance interval
_CAPS = {"1m": 7, "5m": 59, "15m": 59, "30m": 59, "60m": 720, "90m": 59}


class YFinanceSource(BarSource):
    name = "yfinance"
    asset_classes = {AssetClass.EQUITY, AssetClass.FOREX,
                     AssetClass.FUTURE, AssetClass.INDEX, AssetClass.CRYPTO}
    requires_auth = False

    def fetch(self, symbol, timeframe, start, end, **opts) -> pd.DataFrame:
        import yfinance as yf  # lazy

        interval, rule = _MAP[timeframe]

        # clamp start so intraday requests are valid instead of returning nothing
        if interval in _CAPS:
            max_start = end - timedelta(days=_CAPS[interval])
            if start < max_start:
                start = max_start

        df = yf.download(symbol, start=start.date(), end=end.date(),
                         interval=interval, auto_adjust=False, progress=False)
        if df is None or df.empty:
            return normalize_bars(None)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        df.columns = [str(c).lower() for c in df.columns]
        df = df.rename(columns={"adj close": "adj_close"})
        df.index.name = "timestamp"

        cols = [c for c in OHLCV if c in df.columns]
        if "adj_close" in df.columns:
            cols.append("adj_close")
        df = df[cols]

        df = normalize_bars(df)
        return resample_ohlc(df, rule) if rule and len(df) else df
