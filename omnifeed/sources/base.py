"""Source interfaces. Add a venue == implement one of these + register it.

`fetch`/`fetch_funding` receive a *source-formatted* symbol and a UTC
[start, end] window, and must return a normalized frame (use schema.normalize_*).
Heavy/optional imports (ccxt, yfinance) belong inside methods, not at module
top, so importing a source class stays cheap.
"""
from __future__ import annotations

import pandas as pd

from ..symbols import AssetClass


class BarSource:
    name: str = "base"
    asset_classes: set[AssetClass] = set()
    requires_auth: bool = False

    def fetch(self, symbol: str, timeframe: str,
              start: pd.Timestamp, end: pd.Timestamp, **opts) -> pd.DataFrame:
        raise NotImplementedError


class FundingSource:
    name: str = "base"
    requires_auth: bool = False

    def fetch_funding(self, symbol: str,
                      start: pd.Timestamp, end: pd.Timestamp, **opts) -> pd.DataFrame:
        raise NotImplementedError
