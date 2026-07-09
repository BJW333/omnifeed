"""Crypto bars from any CCXT exchange (default: coinbase).

Generalizes the two ccxt-based downloaders (the one whose docstring said
"Binance" but actually used ccxt.coinbase, and the 5yr one). Forward paging with
`since`; the cache layer handles resume, so this stays a plain fetcher.

Use via source="ccxt:binance", source="ccxt:kraken", etc. Bare source="ccxt"
uses coinbase.
"""
from __future__ import annotations

import time

import pandas as pd

from ..schema import normalize_bars
from ..symbols import AssetClass
from ..timeframe import resample_ohlc
from .base import BarSource

# canonical tf -> (ccxt timeframe, optional resample-up rule)
# most exchanges lack 4h? they usually have it; but 1y never exists -> build it.
_MAP = {
    "1m": ("1m", None), "5m": ("5m", None), "15m": ("15m", None),
    "30m": ("30m", None), "1h": ("1h", None), "4h": ("4h", None),
    "1d": ("1d", None), "1w": ("1w", None),
    "1mo": ("1M", None), "1y": ("1d", "1YS"),
}
_LIMIT = 1000


class CCXTSource(BarSource):
    asset_classes = {AssetClass.CRYPTO}
    requires_auth = False

    def __init__(self, exchange: str = "coinbase"):
        self.exchange_id = exchange
        self.name = f"ccxt:{exchange}"
        self._ex = None

    def _client(self):
        if self._ex is None:
            import ccxt  # lazy
            self._ex = getattr(ccxt, self.exchange_id)({"enableRateLimit": True})
        return self._ex

    def fetch(self, symbol, timeframe, start, end, **opts) -> pd.DataFrame:
        ex = self._client()
        ccxt_tf, rule = _MAP[timeframe]
        since = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        rows, cur = [], since
        while cur < end_ms:
            candles = self._page(ex, symbol, ccxt_tf, cur)
            if not candles:
                break
            candles = [c for c in candles if since <= c[0] < end_ms]
            if not candles:
                break
            rows.extend(candles)
            nxt = candles[-1][0] + 1
            if nxt <= cur:
                break
            cur = nxt
            time.sleep(ex.rateLimit / 1000)

        if not rows:
            return normalize_bars(None)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = normalize_bars(df)
        return resample_ohlc(df, rule) if rule and len(df) else df

    @staticmethod
    def _page(ex, symbol, tf, since):
        import ccxt  # lazy, for exception types
        for attempt in range(5):
            try:
                return ex.fetch_ohlcv(symbol, timeframe=tf, since=since, limit=_LIMIT)
            except ccxt.RateLimitExceeded:
                time.sleep(5)
            except ccxt.NetworkError:
                time.sleep(3)
            except Exception:  # noqa: BLE001
                if attempt == 4:
                    raise
                time.sleep(2)
        return []
