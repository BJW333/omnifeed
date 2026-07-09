#!/usr/bin/env python3
"""omnifeed smoke test — tiny LIVE pulls to confirm each asset class works.

Run after:  pip install -e ".[all]"
Optional:   export ALPACA_KEY / ALPACA_SECRET   (adds the Alpaca intraday check)

Exits 0 only if every *required* check passes (Coinbase + funding, plus the
yfinance-backed checks when yfinance is installed). Optional deps / missing
Alpaca keys show as SKIPPED, not FAIL.
"""
from __future__ import annotations

import importlib.util
import sys

import pandas as pd

import omnifeed as mf
from omnifeed.sources.alpaca import AlpacaSource

OHLCV = ["open", "high", "low", "close", "volume"]


def _have(mod: str) -> bool:
    return importlib.util.find_spec(mod) is not None


HAVE_YF = _have("yfinance")
rows = []  # (label, status, detail, required)


def _assert_bars(df: pd.DataFrame) -> str:
    assert df is not None and not df.empty, "empty frame"
    assert isinstance(df.index, pd.DatetimeIndex), "index is not a DatetimeIndex"
    assert str(df.index.tz) == "UTC", f"index tz {df.index.tz!r} != UTC"
    assert df.index.is_monotonic_increasing, "index not sorted ascending"
    assert not df.index.has_duplicates, "duplicate timestamps"
    for c in OHLCV:
        assert c in df.columns, f"missing column {c!r}"
    assert df[["open", "high", "low", "close"]].notna().all().all(), "NaNs in OHLC"
    return f"{len(df)} bars  {df.index[0].date()} -> {df.index[-1].date()}"


def check_bars(label, required, **kw):
    try:
        detail = _assert_bars(mf.get_bars(**kw))
        rows.append((label, "PASS", detail, required))
    except Exception as e:  # noqa: BLE001
        rows.append((label, "FAIL", f"{type(e).__name__}: {e}", required))


def check_funding(label, required, **kw):
    try:
        df = mf.get_funding(**kw)
        assert not df.empty, "empty frame"
        assert str(df.index.tz) == "UTC", f"index tz {df.index.tz!r} != UTC"
        assert "funding_rate" in df.columns, "missing funding_rate"
        assert df.index.is_monotonic_increasing, "index not sorted"
        ann = mf.annualized_funding_pct(df)   # inferred from settlement cadence
        rows.append((label, "PASS",
                     f"{len(df)} points  avg ~{ann:.1f}%/yr", required))
    except Exception as e:  # noqa: BLE001
        rows.append((label, "FAIL", f"{type(e).__name__}: {e}", required))


def skip(label, reason, required=False):
    rows.append((label, "SKIP", reason, required))


def main() -> int:
    print("omnifeed smoke test — tiny live pulls\n" + "-" * 60)

    # --- crypto spot (core dep only) -------------------------------------
    check_bars("crypto  (Coinbase)  BTC-USD 1d", True,
               symbol="BTC-USD", timeframe="1d", years=0.2)

    # --- crypto via CCXT (optional) --------------------------------------
    if _have("ccxt"):
        check_bars("crypto  (CCXT:coinbase) ETH-USD 1d", False,
                   symbol="ETH-USD", timeframe="1d", years=0.2, source="ccxt:coinbase")
    else:
        skip("crypto  (CCXT)", "ccxt not installed  (pip install '.[ccxt]')")

    # --- yfinance-backed classes -----------------------------------------
    if HAVE_YF:
        check_bars("equity  (yfinance)  SPY 1d", True,
                   symbol="SPY", timeframe="1d", years=0.2)
        check_bars("forex   (yfinance)  EURUSD 1d", True,
                   symbol="EURUSD", timeframe="1d", years=0.2, asset="forex")
        check_bars("future  (yfinance)  GC 1d", True,
                   symbol="GC", timeframe="1d", years=0.2, asset="future")
        check_bars("index   (yfinance)  ^GSPC 1d", True,
                   symbol="^GSPC", timeframe="1d", years=0.5, asset="index")
    else:
        for lbl in ("equity", "forex", "future", "index"):
            skip(f"{lbl:<7} (yfinance)", "yfinance not installed  (pip install '.[stocks]')")

    # --- perp funding (core dep only) ------------------------------------
    # Hyperliquid is the US-accessible default; Bybit/OKX geo-block US IPs.
    check_funding("funding (Hyperliquid) BTC", True,
                  symbol="BTC-USD", source="hyperliquid", years=0.1)

    # --- Alpaca intraday (needs keys) ------------------------------------
    if AlpacaSource.has_keys():
        check_bars("equity  (Alpaca)   AAPL 5m", False,
                   symbol="AAPL", timeframe="5m", years=0.03, source="alpaca")
        check_bars("equity  (Alpaca ORB) AAPL 5m NY-session", False,
                   symbol="AAPL", timeframe="5m", years=0.03, source="alpaca",
                   session_only=True, bar="5min")
    else:
        skip("equity  (Alpaca)", "ALPACA_KEY / ALPACA_SECRET not set")

    # --- cache sanity: second call must not error, cache dir must exist ---
    try:
        from pathlib import Path
        mf.get_bars("BTC-USD", "1d", years=0.2)          # served from cache
        mf.get_bars("BTC-USD", "1d", years=0.2, use_cache=False)  # bypass path
        ok = Path(mf.__dict__.get("__file__", ".")).parent  # noqa: F841
        cache_ok = Path(".omnifeed").exists()
        rows.append(("cache   (repeat + bypass)", "PASS" if cache_ok else "FAIL",
                     ".omnifeed present" if cache_ok else "cache dir missing", True))
    except Exception as e:  # noqa: BLE001
        rows.append(("cache   (repeat + bypass)", "FAIL", str(e), True))

    # --- report ----------------------------------------------------------
    print()
    width = max(len(r[0]) for r in rows)
    for label, status, detail, _ in rows:
        mark = {"PASS": "✓", "FAIL": "✗", "SKIP": "–"}[status]
        print(f"  {mark} {status:<4} {label:<{width}}  {detail}")

    failed = [r for r in rows if r[1] == "FAIL" and r[3]]
    passed = sum(1 for r in rows if r[1] == "PASS")
    skipped = sum(1 for r in rows if r[1] == "SKIP")
    print("-" * 60)
    print(f"  {passed} passed, {len(failed)} required-fail, {skipped} skipped")
    if failed:
        print("\n  REQUIRED CHECKS FAILED — see errors above.")
        return 1
    print("\n  All required checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
