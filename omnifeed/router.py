"""Route a (symbol, asset class, timeframe) to the right source — the bit that
lets callers say get_bars("AAPL") or get_bars("BTC-USD") and not care where the
data lives. Explicit source= always wins.

Defaults:
    crypto                         -> Coinbase       (your preferred venue)
    equity intraday + Alpaca keys  -> Alpaca         (years of minute bars)
    equity daily+ / fx / futures / index -> yfinance
    source="ccxt:binance"          -> that exchange via CCXT
"""
from __future__ import annotations

from .sources import (AlpacaSource, CCXTSource, CoinbaseSource,
                      FundingSourceImpl, YFinanceSource)
from .symbols import AssetClass

_INTRADAY = {"1m", "5m", "15m", "30m", "1h"}


def get_bar_source(asset: AssetClass, source: str | None, timeframe: str, **opts):
    if source:
        if source.startswith("ccxt"):
            _, _, ex = source.partition(":")
            return CCXTSource(ex or "coinbase")
        table = {
            "coinbase": CoinbaseSource,
            "yfinance": YFinanceSource,
            "alpaca": AlpacaSource,
        }
        if source not in table:
            raise ValueError(f"unknown source {source!r}; "
                             f"try one of {list(table)} or 'ccxt:<exchange>'")
        return table[source]()

    if asset is AssetClass.CRYPTO:
        return CoinbaseSource()
    if asset is AssetClass.EQUITY and timeframe in _INTRADAY and AlpacaSource.has_keys():
        return AlpacaSource()
    # equity daily+, forex, futures, indices
    return YFinanceSource()


def get_funding_source(venue: str = "hyperliquid") -> FundingSourceImpl:
    return FundingSourceImpl(venue)
