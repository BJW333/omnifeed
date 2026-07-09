"""Perpetual funding-rate history, no key.

Venue notes for a US-based operator:
  * Binance fapi is geo-blocked (HTTP 451) for US IPs.
  * Bybit blocks US retail/API access (HTTP 403).
  * OKX has exited the US market.
  So the default is HYPERLIQUID: an on-chain perps DEX whose read-only /info
  endpoint is permissionless (no key, no signature) and answers from US IPs.
  Bybit/OKX remain available via source= for non-US use.

Output schema is funding, not OHLCV: a UTC 'time' index with funding_rate +
mark_price. Hyperliquid settles hourly; Bybit/OKX every 8h — annualization is
handled downstream from the data's own cadence (schema.annualized_funding_pct).
"""
from __future__ import annotations

import time

import pandas as pd

from ..http import get_json, post_json, session
from ..schema import normalize_funding
from .base import FundingSource

_BYBIT = "https://api.bybit.com/v5/market/funding/history"
_OKX = "https://www.okx.com/api/v5/public/funding-rate-history"
_HYPERLIQUID = "https://api.hyperliquid.xyz/info"

VENUES = ("hyperliquid", "bybit", "okx")


class FundingSourceImpl(FundingSource):
    requires_auth = False

    def __init__(self, venue: str = "hyperliquid"):
        if venue not in VENUES:
            raise ValueError(f"funding venue must be one of {VENUES}")
        self.venue = venue
        self.name = venue
        self._sess = session()

    def fetch_funding(self, symbol, start, end, **opts) -> pd.DataFrame:
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        fn = {"hyperliquid": self._hyperliquid,
              "bybit": self._bybit,
              "okx": self._okx}[self.venue]
        rows = fn(symbol, start_ms, end_ms)
        if not rows:
            return normalize_funding(None)
        df = pd.DataFrame(rows, columns=["time", "funding_rate"]).drop_duplicates("time")
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        df["mark_price"] = float("nan")
        return normalize_funding(df.set_index("time"))

    # --- Hyperliquid: POST /info, forward paging (~500 rows/response) --------
    def _hyperliquid(self, coin, start_ms, end_ms):
        rows, cur = [], start_ms
        while cur < end_ms:
            data = post_json(_HYPERLIQUID,
                             {"type": "fundingHistory", "coin": coin,
                              "startTime": cur, "endTime": end_ms},
                             sess=self._sess)
            if not data:
                break
            for r in data:
                rows.append((int(r["time"]), float(r["fundingRate"])))
            newest = max(int(r["time"]) for r in data)
            if newest <= cur:            # no forward progress -> done
                break
            cur = newest + 1
            time.sleep(0.15)
        return rows

    # --- Bybit v5: backward paging via endTime (non-US only) ----------------
    def _bybit(self, symbol, start_ms, end_ms):
        rows, cursor = [], end_ms
        while cursor > start_ms:
            j = get_json(_BYBIT, params={"category": "linear", "symbol": symbol,
                                         "endTime": cursor, "limit": 200},
                         sess=self._sess)
            lst = (j.get("result") or {}).get("list") or []
            if not lst:
                break
            for row in lst:
                rows.append((int(row["fundingRateTimestamp"]), float(row["fundingRate"])))
            oldest = min(int(r["fundingRateTimestamp"]) for r in lst)
            if oldest >= cursor:
                break
            cursor = oldest - 1
            time.sleep(0.2)
        return rows

    # --- OKX: backward paging via 'after' (non-US only) ---------------------
    def _okx(self, symbol, start_ms, end_ms):
        rows, after = [], end_ms
        while after > start_ms:
            j = get_json(_OKX, params={"instId": symbol, "after": after, "limit": 100},
                         sess=self._sess)
            lst = j.get("data") or []
            if not lst:
                break
            for row in lst:
                key = "realizedRate" if "realizedRate" in row else "fundingRate"
                rows.append((int(row["fundingTime"]), float(row[key])))
            oldest = min(int(r["fundingTime"]) for r in lst)
            if oldest >= after:
                break
            after = oldest - 1
            time.sleep(0.2)
        return rows
