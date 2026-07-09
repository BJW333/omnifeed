"""omnifeed — one interface for market data across every asset class.

    from omnifeed import get_bars, get_funding

    get_bars("BTC-USD", "1h", years=2)          # crypto  (Coinbase)
    get_bars("AAPL", "1d", years=5)             # equity  (yfinance / Alpaca)
    get_bars("EURUSD", "1d", years=5)           # forex   (yfinance)
    get_bars("GC", "1d", years=5, asset="future")   # gold futures
    get_bars("^GSPC", "1d", years=10)           # index
    get_funding("BTCUSDT", years=4)             # perp funding (Bybit/OKX)

Every bar call returns a UTC-indexed OHLCV DataFrame regardless of source.
Pass out="path.csv" to also write a (tz-naive UTC by default) CSV.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .cache import get_or_update
from .router import get_bar_source, get_funding_source
from .schema import (annualized_funding_pct, empty_bars, empty_funding,
                     normalize_bars, normalize_funding, resolve_window)
from .symbols import AssetClass, infer_asset_class, safe_filename, to_source_symbol
from .timeframe import CANON as TIMEFRAMES
from .timeframe import validate as _validate_tf

__version__ = "0.1.0"

__all__ = [
    "get_bars", "get_funding", "download", "to_csv",
    "annualized_funding_pct", "AssetClass", "TIMEFRAMES",
    "list_sources", "__version__",
]


def to_csv(df: pd.DataFrame, path, tz_naive: bool = True) -> Path:
    """Write a frame to CSV. Default tz_naive=True strips tz to UTC-naive so the
    output matches the original download scripts (and your existing readers)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    if tz_naive and isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    out.reset_index().to_csv(path, index=False)
    return path


def get_bars(symbol: str, timeframe: str = "1d", *, start=None, end=None,
             years=None, asset: str | None = None, source: str | None = None,
             use_cache: bool = True, out=None, tz_naive_csv: bool = True,
             **opts) -> pd.DataFrame:
    """Fetch OHLCV bars for one symbol. See module docstring for examples."""
    _validate_tf(timeframe)
    ac = AssetClass(asset) if asset else infer_asset_class(symbol)
    src = get_bar_source(ac, source, timeframe, **opts)
    s, e = resolve_window(start, end, years, default_years=5.0)
    sym = to_source_symbol(symbol, src.name, ac)

    def fetch(a, b):
        return src.fetch(sym, timeframe, a, b, **opts)

    df = get_or_update(fetch, "bars", src.name, symbol, timeframe, s, e, use_cache)
    df = normalize_bars(df)
    if out:
        to_csv(df, out, tz_naive=tz_naive_csv)
    return df


def get_funding(symbol: str, *, source: str = "hyperliquid", start=None, end=None,
                years=None, use_cache: bool = True, out=None,
                tz_naive_csv: bool = True) -> pd.DataFrame:
    """Fetch perpetual funding-rate history.

    source is 'hyperliquid' (default, US-accessible), 'bybit', or 'okx'.
    Bybit and OKX geo-block US IPs — use Hyperliquid from the US.
    """
    src = get_funding_source(source)
    s, e = resolve_window(start, end, years, default_years=4.0)
    sym = to_source_symbol(symbol, src.name, AssetClass.CRYPTO)

    def fetch(a, b):
        return src.fetch_funding(sym, a, b)

    df = get_or_update(fetch, "funding", src.name, symbol, "funding", s, e, use_cache)
    df = normalize_funding(df)
    if out:
        # funding CSVs keep 'time' as a column (matches download_funding.py)
        to_csv(df, out, tz_naive=tz_naive_csv)
    return df


def download(symbols, timeframes=("1d",), *, asset=None, source=None,
             years=5, out_dir="data", use_cache=True, verbose=True,
             **opts) -> list[dict]:
    """Batch-download bars for many symbols/timeframes into out_dir/<TAG>.csv.

    Returns a summary list (one row per successful file).
    """
    out_dir = Path(out_dir)
    summary = []
    for sym in symbols:
        for tf in timeframes:
            tag = safe_filename(sym, tf)
            if verbose:
                print(f"[{sym} @ {tf}] ...", flush=True)
            try:
                df = get_bars(sym, tf, years=years, asset=asset, source=source,
                              use_cache=use_cache, **opts)
            except Exception as e:  # noqa: BLE001
                if verbose:
                    print(f"    [error] {e}")
                continue
            if df.empty:
                if verbose:
                    print("    [skip] no data")
                continue
            path = to_csv(df, out_dir / f"{tag}.csv")
            summary.append({"symbol": sym, "timeframe": tf, "rows": len(df),
                            "first": df.index[0], "last": df.index[-1], "path": path})
            if verbose:
                print(f"    saved {path}  ({len(df)} bars, "
                      f"{df.index[0].date()} -> {df.index[-1].date()})")
    return summary


def list_sources() -> dict:
    """Human-readable map of what each source covers."""
    return {
        "coinbase": "crypto spot (REST, no key) — default for crypto",
        "ccxt:<exchange>": "crypto spot on any CCXT exchange (binance, kraken, ...)",
        "yfinance": "stocks, ETFs, forex (=X), futures (=F), indices (^) — no key",
        "alpaca": "stock intraday minute bars (key) — years of history for ORB",
        "hyperliquid": "perp funding-rate history (no key) — default, US-accessible",
        "bybit / okx": "perp funding-rate history (no key) — non-US (US IPs blocked)",
    }
