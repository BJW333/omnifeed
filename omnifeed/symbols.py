"""Symbols: infer what asset class a ticker is, and translate a canonical
symbol into whatever string a given venue expects.

Canonical forms the package speaks:
    crypto  BASE-QUOTE     e.g. BTC-USD, SOL-USD        (Coinbase-style dash)
    equity  bare ticker    e.g. AAPL, SPY
    forex   6-letter pair  e.g. EURUSD, GBPJPY          (or raw EURUSD=X)
    future  root           e.g. GC, CL, ES              (or raw GC=F)
    index   ^-prefixed     e.g. ^GSPC, ^VIX

You can always sidestep inference by passing asset=... to get_bars().
"""
from __future__ import annotations

from enum import Enum


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    EQUITY = "equity"
    FOREX = "forex"
    FUTURE = "future"
    INDEX = "index"


# quote currencies that mark a symbol as a crypto pair
_CRYPTO_QUOTES = {"USD", "USDT", "USDC", "USDD", "DAI", "BTC", "ETH", "EUR"}
_FIAT = {"USD", "EUR", "JPY", "GBP", "AUD", "CAD", "CHF", "NZD", "CNH",
         "HKD", "SGD", "SEK", "NOK", "MXN", "ZAR"}


def infer_asset_class(symbol: str) -> AssetClass:
    s = symbol.strip().upper()
    if s.endswith("=X"):
        return AssetClass.FOREX
    if s.endswith("=F"):
        return AssetClass.FUTURE
    if s.startswith("^"):
        return AssetClass.INDEX
    if "-" in s or "/" in s:
        base, _, quote = s.replace("/", "-").partition("-")
        if quote in _CRYPTO_QUOTES:
            return AssetClass.CRYPTO
    if s.endswith("USDT") or s.endswith("USDC"):
        return AssetClass.CRYPTO
    if len(s) == 6 and s.isalpha() and s[:3] in _FIAT and s[3:] in _FIAT:
        return AssetClass.FOREX
    return AssetClass.EQUITY


def _split_pair(s: str) -> tuple[str, str]:
    s = s.upper().replace("/", "-")
    if "-" in s:
        base, _, quote = s.partition("-")
        return base, quote
    if s.endswith(("USDT", "USDC", "USDD")):
        return s[:-4], s[-4:]
    if s.endswith("USD"):
        return s[:-3], "USD"
    return s, "USD"


def to_source_symbol(symbol: str, source: str, asset: AssetClass) -> str:
    """Translate a canonical symbol into the string `source` wants."""
    s = symbol.strip()
    src = source.split(":", 1)[0]  # 'ccxt:binance' -> 'ccxt'

    if src == "coinbase":
        return s.upper().replace("/", "-")

    if src == "ccxt":
        base, quote = _split_pair(s)
        return f"{base}/{quote}"

    if src == "yfinance":
        u = s.upper()
        if asset is AssetClass.FOREX:
            return u if u.endswith("=X") else f"{u}=X"
        if asset is AssetClass.FUTURE:
            return u if u.endswith("=F") else f"{u}=F"
        if asset is AssetClass.INDEX:
            return u if u.startswith("^") else f"^{u}"
        if asset is AssetClass.CRYPTO:
            base, quote = _split_pair(s)
            return f"{base}-{quote}"        # yfinance uses BTC-USD
        return u                             # equity / etf

    if src == "alpaca":
        return s.upper()                     # plain ticker

    if src == "bybit":
        base, quote = _split_pair(s)
        if quote == "USD":
            quote = "USDT"
        return f"{base}{quote}"              # BTCUSDT

    if src == "okx":
        base, quote = _split_pair(s)
        if quote == "USD":
            quote = "USDT"
        return f"{base}-{quote}-SWAP"        # BTC-USDT-SWAP

    if src == "hyperliquid":
        base, _ = _split_pair(s)
        return base.upper()                  # bare coin, e.g. BTC

    return s


def safe_filename(symbol: str, timeframe: str) -> str:
    """Filesystem-safe <SYMBOL>_<TF> tag (ported from the original scripts)."""
    safe = (symbol.replace("=X", "_FX").replace("=F", "_FUT").replace("^", "IDX_")
            .replace("-", "_").replace("=", "_").replace("/", "_").replace(":", "_"))
    return f"{safe}_{timeframe}"
