"""Coinbase spot candles via the public Exchange REST endpoint (no key).

Ported from the crypto path of the original download_data.py. Coinbase caps at
300 candles/request and has no native 4h/1w/1mo/1y candle, so those are built by
resampling a finer native granularity. Paging walks *backward* from end to start.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from ..http import RateLimiter, session
from ..schema import OHLCV, normalize_bars
from ..symbols import AssetClass
from ..timeframe import resample_ohlc
from .base import BarSource

_URL = "https://api.exchange.coinbase.com/products/{p}/candles"

# native granularities Coinbase actually serves, in seconds
_NATIVE = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "1d": 86400}

# tf -> ("native", seconds) | ("resample", base_tf, pandas_rule)
_SPEC = {
    "1m": ("native", 60), "5m": ("native", 300), "15m": ("native", 900),
    "30m": ("resample", "15m", "30min"),
    "1h": ("native", 3600),
    "4h": ("resample", "1h", "4h"),
    "1d": ("native", 86400),
    "1w": ("resample", "1d", "1W"),
    "1mo": ("resample", "1d", "1MS"),
    "1y": ("resample", "1d", "1YS"),
}


class CoinbaseSource(BarSource):
    name = "coinbase"
    asset_classes = {AssetClass.CRYPTO}
    requires_auth = False

    def __init__(self):
        self._sess = session()
        self._rl = RateLimiter(0.34)   # polite to the public rate limit

    def fetch(self, symbol, timeframe, start, end, **opts) -> pd.DataFrame:
        kind, *rest = _SPEC[timeframe]
        if kind == "native":
            raw = self._native(symbol, rest[0], start, end)
        else:
            base_tf, rule = rest
            raw = self._native(symbol, _NATIVE[base_tf], start, end)
            raw = resample_ohlc(raw, rule) if len(raw) else raw
        return normalize_bars(raw)

    def _native(self, product, gran, start, end) -> pd.DataFrame:
        rows = []
        cur_end = end.floor("s").to_pydatetime()
        start_dt = start.floor("s").to_pydatetime()
        step = timedelta(seconds=gran * 300)
        while cur_end > start_dt:
            cur_start = max(start_dt, cur_end - step)
            self._rl.wait()
            r = self._sess.get(
                _URL.format(p=product),
                params={"granularity": gran,
                        "start": cur_start.isoformat(),
                        "end": cur_end.isoformat()},
                timeout=30,
            )
            if r.status_code != 200:
                # invalid product or paged before listing date: stop gracefully
                break
            batch = r.json()
            if not batch:
                break
            rows += batch
            oldest = min(c[0] for c in batch)
            cur_end = datetime.fromtimestamp(oldest, tz=timezone.utc) - timedelta(seconds=gran)

        if not rows:
            return pd.DataFrame()
        # Coinbase candle = [time, low, high, open, close, volume]
        df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = (df.drop(columns=["time"])
                .drop_duplicates("timestamp")
                .set_index("timestamp")
                .sort_index())
        return df[OHLCV]
