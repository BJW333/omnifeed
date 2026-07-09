"""omnifeed command line — one command to pull anything.

    omnifeed bars --crypto BTC-USD ETH-USD --stocks SPY AAPL \
                    --fx EURUSD GBPUSD --futures GC CL --index ^GSPC \
                    --timeframes 1h 1d --years 3

    omnifeed bars --stocks AAPL TSLA NVDA --intraday --bar 5min \
                    --session-only --source alpaca --years 3   # ORB data

    omnifeed funding --symbols BTCUSDT ETHUSDT SOLUSDT --years 4

    omnifeed run pull.json     # everything in a config, one shot (run_all-style)

    omnifeed sources           # what each source covers
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import (TIMEFRAMES, __version__, download, get_funding, list_sources)
from .universes import load_tickers, sp500, sp600

# CLI flag -> asset class understood by get_bars
_GROUPS = {"crypto": "crypto", "stocks": "equity", "fx": "forex",
           "futures": "future", "index": "index"}


def _out_dir(args, default):
    return args.out or default


def _run_bars(args) -> int:
    bad = [t for t in args.timeframes if t not in TIMEFRAMES]
    if bad:
        raise SystemExit(f"unknown timeframe(s): {bad}. valid: {TIMEFRAMES}")

    # assemble (asset -> symbols)
    groups: dict[str, list[str]] = {}
    for flag, asset in _GROUPS.items():
        vals = list(getattr(args, flag) or [])
        if vals:
            groups.setdefault(asset, []).extend(vals)

    if args.stocks and args.sp600:
        groups.setdefault("equity", []).extend(sp600())
    if args.stocks_file:
        groups.setdefault("equity", []).extend(load_tickers(args.stocks_file))
    if args.sp600 and not args.stocks:
        groups.setdefault("equity", []).extend(sp600())
    if args.sp500:
        groups.setdefault("equity", []).extend(sp500())

    if not groups:
        raise SystemExit("nothing to download — pass --crypto/--stocks/--fx/"
                         "--futures/--index (or --sp600/--sp500/--stocks-file).")

    opts = {}
    if args.feed:
        opts["feed"] = args.feed
    if args.intraday or args.session_only:
        opts["session_only"] = bool(args.session_only)
    if args.bar:
        opts["bar"] = args.bar

    total = 0
    for asset, syms in groups.items():
        syms = sorted(set(syms))
        summ = download(syms, args.timeframes, asset=asset, source=args.source,
                        years=args.years, out_dir=_out_dir(args, "data"),
                        use_cache=not args.no_cache, **opts)
        total += len(summ)
    print(f"\nDone. {total} file(s) written to {_out_dir(args, 'data')}/")
    return 0


def _run_funding(args) -> int:
    out = _out_dir(args, "funding_data")
    n = 0
    for sym in args.symbols:
        df = get_funding(sym, source=args.source, years=args.years,
                         use_cache=not args.no_cache)
        if df.empty:
            print(f"[{args.source}] {sym}: no data (check symbol format)")
            continue
        from . import annualized_funding_pct, to_csv
        ann = annualized_funding_pct(df)   # inferred from settlement cadence
        tag = sym.replace("-USDT-SWAP", "USDT").replace("-", "")
        path = to_csv(df, Path(out) / f"{tag}_funding.csv")
        n += 1
        print(f"[{args.source}] {sym}: saved {path} ({len(df)} pts, "
              f"avg ~{ann:.1f}%/yr)")
    print(f"\nDone. {n} funding file(s) in {out}/")
    return 0


def _run_config(args) -> int:
    """Execute a JSON (or YAML if pyyaml present) batch spec — the run_all path."""
    text = Path(args.config).read_text()
    if args.config.endswith((".yaml", ".yml")):
        import yaml  # optional
        cfg = yaml.safe_load(text)
    else:
        cfg = json.loads(text)

    from . import to_csv
    files = 0
    for job in cfg.get("bars", []):
        summ = download(job["symbols"], job.get("timeframes", ["1d"]),
                        asset=job.get("asset"), source=job.get("source"),
                        years=job.get("years", 5), out_dir=job.get("out", "data"),
                        use_cache=job.get("use_cache", True),
                        **{k: job[k] for k in ("feed", "bar", "session_only")
                           if k in job})
        files += len(summ)
    for job in cfg.get("funding", []):
        for sym in job["symbols"]:
            df = get_funding(sym, source=job.get("source", "bybit"),
                             years=job.get("years", 4))
            if df.empty:
                continue
            tag = sym.replace("-USDT-SWAP", "USDT").replace("-", "")
            to_csv(df, Path(job.get("out", "funding_data")) / f"{tag}_funding.csv")
            files += 1
    print(f"\nDone. {files} file(s) written from {args.config}.")
    return 0


def _run_sources(_args) -> int:
    for name, desc in list_sources().items():
        print(f"  {name:<22} {desc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="omnifeed",
                                 description="Unified market-data downloader.")
    ap.add_argument("--version", action="version", version=f"omnifeed {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bars", help="download OHLCV bars")
    b.add_argument("--crypto", nargs="*", default=[])
    b.add_argument("--stocks", nargs="*", default=[])
    b.add_argument("--fx", nargs="*", default=[])
    b.add_argument("--futures", nargs="*", default=[])
    b.add_argument("--index", nargs="*", default=[])
    b.add_argument("--sp600", action="store_true", help="add all S&P 600 tickers")
    b.add_argument("--sp500", action="store_true", help="add all S&P 500 tickers")
    b.add_argument("--stocks-file", default=None, help="one ticker per line")
    b.add_argument("--timeframes", nargs="+", default=["1d"],
                   help=f"any of: {' '.join(TIMEFRAMES)}")
    b.add_argument("--years", type=float, default=5)
    b.add_argument("--source", default=None,
                   help="force a source: coinbase|yfinance|alpaca|ccxt:<exchange>")
    b.add_argument("--intraday", action="store_true",
                   help="equity intraday via Alpaca (fetch 1Min under the hood)")
    b.add_argument("--session-only", action="store_true",
                   help="keep only NY regular session (for ORB)")
    b.add_argument("--bar", default=None, help="extra resample target, e.g. 5min")
    b.add_argument("--feed", default=None, choices=["iex", "sip"],
                   help="Alpaca feed (default iex)")
    b.add_argument("--out", default=None, help="output dir (default: data)")
    b.add_argument("--no-cache", action="store_true")
    b.set_defaults(func=_run_bars)

    f = sub.add_parser("funding", help="download perp funding-rate history")
    f.add_argument("--symbols", nargs="+", required=True)
    f.add_argument("--source", default="hyperliquid",
                   choices=["hyperliquid", "bybit", "okx"],
                   help="hyperliquid is US-accessible; bybit/okx block US IPs")
    f.add_argument("--years", type=float, default=4)
    f.add_argument("--out", default=None, help="output dir (default: funding_data)")
    f.add_argument("--no-cache", action="store_true")
    f.set_defaults(func=_run_funding)

    r = sub.add_parser("run", help="run a JSON/YAML batch config (run_all-style)")
    r.add_argument("config")
    r.set_defaults(func=_run_config)

    s = sub.add_parser("sources", help="list available sources")
    s.set_defaults(func=_run_sources)

    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
