"""Alpaca stock bars — years of intraday history the ORB "stocks in play" edge
needs. Ported from download_alpaca.py.

Auth: your own ALPACA_KEY / ALPACA_SECRET (env or opts). These are read locally
and sent only to Alpaca's own API — the package never transmits them anywhere
else. Free tier = IEX feed (a volume subset); pass feed="sip" if you have it.

ORB workflow is preserved via opts: session_only=True filters to the NY regular
session and `bar` resamples (e.g. "5min"), matching the original script's output.

Survivorship caveat (unchanged): Alpaca only lists stocks that exist today, so
delisted names are missing and can inflate backtests.
"""
from __future__ import annotations

import os

import pandas as pd

from ..http import RateLimiter, get_json
from ..schema import normalize_bars
from ..symbols import AssetClass
from ..transforms import regular_session
from .base import BarSource

_BASE = "https://data.alpaca.markets/v2/stocks/{sym}/bars"

# canonical tf -> Alpaca timeframe string
_TF = {"1m": "1Min", "5m": "5Min", "15m": "15Min", "30m": "30Min",
       "1h": "1Hour", "1d": "1Day"}


class AlpacaSource(BarSource):
    name = "alpaca"
    asset_classes = {AssetClass.EQUITY}
    requires_auth = True

    def __init__(self, key: str | None = None, secret: str | None = None):
        self._key = key or os.environ.get("ALPACA_KEY")
        self._secret = secret or os.environ.get("ALPACA_SECRET")
        self._rl = RateLimiter(0.35)   # ~170 req/min, under the 200 free limit

    @staticmethod
    def has_keys() -> bool:
        return bool(os.environ.get("ALPACA_KEY") and os.environ.get("ALPACA_SECRET"))

    def _keys(self, opts):
        k = opts.get("key") or self._key
        s = opts.get("secret") or self._secret
        if not k or not s:
            raise SystemExit(
                "Alpaca keys missing. Set ALPACA_KEY and ALPACA_SECRET (or pass "
                "key=/secret=). Free at https://alpaca.markets -> Dashboard.")
        return k, s

    def fetch(self, symbol, timeframe, start, end, **opts) -> pd.DataFrame:
        key, secret = self._keys(opts)
        feed = opts.get("feed", "iex")
        session_only = opts.get("session_only", False)
        bar = opts.get("bar")  # optional extra resample target, e.g. "5min"

        # For ORB (session filtering) we need fine bars first, then filter, then
        # resample. Otherwise request the requested timeframe directly.
        api_tf = "1Min" if (session_only or bar) else _TF[timeframe]

        rows = self._fetch_bars(symbol, api_tf, start, end, key, secret, feed)
        if not rows:
            return normalize_bars(None)

        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = normalize_bars(df)

        if session_only:
            # regular_session drops tz; re-localize to UTC to keep the schema
            df = regular_session(df, drop_tz=False)
            df.index = df.index.tz_convert("UTC")
        if bar:
            from ..timeframe import resample_ohlc
            df = resample_ohlc(df, bar)
        return df

    def _fetch_bars(self, sym, api_tf, start, end, key, secret, feed):
        start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = end.strftime("%Y-%m-%dT%H:%M:%SZ")
        headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        url = _BASE.format(sym=sym)
        rows, page_token = [], None
        while True:
            params = {"start": start_iso, "end": end_iso, "timeframe": api_tf,
                      "limit": 10000, "adjustment": "raw", "feed": feed}
            if page_token:
                params["page_token"] = page_token
            j = get_json(url, params=params, headers=headers, timeout=60,
                         rate_limiter=self._rl)
            for b in (j.get("bars") or []):
                rows.append((b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]))
            page_token = j.get("next_page_token")
            if not page_token:
                break
        return rows
