# omnifeed

**One interface for market data across every asset class.**

`omnifeed` collapses a pile of one-off download scripts into a single installable
package. Ask for a symbol, get back a clean, UTC-indexed OHLCV frame — no matter
whether it came from a crypto exchange, a stock API, or Yahoo. Paging, retries,
rate-limiting, symbol translation, and an incremental on-disk cache are handled
once, in one place, for every source.

<p>
<img alt="Python" src="https://img.shields.io/badge/python-3.9%2B-blue">
<img alt="License" src="https://img.shields.io/badge/license-MIT-green">
<img alt="Status" src="https://img.shields.io/badge/status-alpha-orange">
</p>

```python
from omnifeed import get_bars, get_funding

get_bars("BTC-USD", "1h", years=2)              # crypto  -> Coinbase
get_bars("AAPL",    "1d", years=5)              # equity  -> yfinance / Alpaca
get_bars("EURUSD",  "1d", years=5)              # forex   -> yfinance
get_bars("GC", "1d", years=5, asset="future")   # gold futures
get_bars("^GSPC",   "1d", years=10)             # index
get_funding("BTC-USD", years=4)                 # perp funding -> Hyperliquid
```

---

## Why

Every quant project accretes its own data-fetching code: one script pages
Coinbase, another wraps CCXT, a third pulls Alpaca minute bars, a fourth scrapes
funding rates — each reinventing pagination, rate limits, timezone handling, and
CSV layout, each with subtly different output. `omnifeed` is that layer, done
once:

- **One call, any asset class.** `get_bars(symbol, timeframe, years=...)`
  auto-routes by asset class. Override with `source=` whenever you want control.
- **One schema.** Every source returns the same UTC-indexed OHLCV frame, so
  downstream code never cares where the bytes came from.
- **Shared plumbing.** Retries, rate-limiting, symbol formats, and an incremental
  cache live in the core — add a venue by writing one adapter.

---

## Coverage

| Asset class | Source(s) | Notes |
|---|---|---|
| Crypto spot | Coinbase (default), any CCXT exchange | full history, no key |
| Crypto perp funding | **Hyperliquid** (default), Bybit, OKX | Hyperliquid is US-accessible; Bybit/OKX block US IPs |
| Equities & ETFs | yfinance (daily+), Alpaca (intraday) | Alpaca needs a free key; years of minute bars |
| Forex | yfinance (`=X`) | daily solid; intraday ~60d only |
| Futures / commodities | yfinance (`=F`) | — |
| Indices | yfinance (`^`) | — |

Not (yet) covered: options chains, cash bonds/rates (futures proxies only),
L2/order-book depth, on-chain data, and deep intraday forex. Each is a one-file
adapter away — the interface doesn't change.

---

## Install

```bash
git clone https://github.com/BJW333/omnifeed.git
cd omnifeed
pip install -e ".[all]"
```

Extras (install only what you need):

| Extra | Adds | Unlocks |
|---|---|---|
| `stocks` | yfinance, lxml | equities, ETFs, forex, futures, indices |
| `ccxt` | ccxt | crypto on any CCXT exchange |
| `fast` | pyarrow | faster/typed cache (else falls back to pickle) |
| `yaml` | pyyaml | YAML run-configs (JSON always works) |
| `all` | all of the above | everything |

Core (`pandas` + `requests`) alone covers Coinbase and Hyperliquid funding.

For Alpaca intraday data, set your own keys (read locally, sent only to Alpaca):

```bash
export ALPACA_KEY=...  ALPACA_SECRET=...
```

---

## Quickstart

### Python

```python
import omnifeed as of

# bars — returns a UTC-indexed OHLCV DataFrame
df = of.get_bars("SOL-USD", "15m", years=1)

# write a CSV too (tz-naive UTC by default, for compatibility with other tools)
of.get_bars("SPY", "1d", years=5, out="data/SPY_1d.csv")

# force a specific source
of.get_bars("ETH-USD", "1h", years=2, source="ccxt:binance")

# funding + annualized carry (inferred from settlement cadence)
f = of.get_funding("BTC-USD", years=2)
print(of.annualized_funding_pct(f), "%/yr")

# batch download
of.download(["BTC-USD", "ETH-USD"], ["1h", "1d"], asset="crypto",
            years=3, out_dir="data")
```

### CLI

```bash
# mixed pull across asset classes, straight to CSV
omnifeed bars --crypto BTC-USD ETH-USD --stocks SPY AAPL \
              --fx EURUSD GBPUSD --futures GC CL --index ^GSPC \
              --timeframes 1h 1d --years 3

# ORB "stocks in play" data: years of 5-min NY-session bars via Alpaca
omnifeed bars --stocks AAPL TSLA NVDA --source alpaca \
              --intraday --session-only --bar 5min --years 3 --out intraday_data

# perp funding history (Hyperliquid by default)
omnifeed funding --symbols BTC-USD ETH-USD SOL-USD --years 4

# run a whole batch from a config file
omnifeed run pull.json

omnifeed sources     # list what each source covers
```

### Run-config (JSON, or YAML with the `yaml` extra)

```json
{
  "bars": [
    {"symbols": ["BTC-USD", "ETH-USD"], "asset": "crypto",
     "timeframes": ["15m", "1h", "1d"], "years": 5, "out": "data"},
    {"symbols": ["SPY", "AAPL", "NVDA"], "timeframes": ["1d"], "years": 5,
     "out": "data"},
    {"symbols": ["EURUSD", "GBPUSD"], "asset": "forex",
     "timeframes": ["1d"], "years": 8, "out": "data/fx"},
    {"symbols": ["AAPL", "TSLA"], "asset": "equity", "source": "alpaca",
     "session_only": true, "bar": "5min", "timeframes": ["1m"], "years": 3,
     "out": "intraday_data"}
  ],
  "funding": [
    {"symbols": ["BTC-USD", "ETH-USD"], "source": "hyperliquid",
     "years": 4, "out": "funding_data"}
  ]
}
```

`omnifeed run pull.json` executes every job in one shot.

---

## API reference

| Function | Purpose |
|---|---|
| `get_bars(symbol, timeframe="1d", years=..., asset=None, source=None, out=None)` | One symbol → OHLCV frame (+ optional CSV) |
| `get_funding(symbol, source="hyperliquid", years=4, out=None)` | Funding-rate history frame |
| `download(symbols, timeframes, asset=..., source=..., out_dir=...)` | Batch → CSVs + summary |
| `annualized_funding_pct(df)` | Annualized mean funding, inferred from cadence |
| `to_csv(df, path, tz_naive=True)` | Write a frame (tz-naive UTC by default) |
| `list_sources()` | Map of source → coverage |

**Timeframes:** `1m 5m 15m 30m 1h 4h 1d 1w 1mo 1y`
**Sources (`source=`):** `coinbase`, `yfinance`, `alpaca`, `ccxt:<exchange>`
(e.g. `ccxt:binance`, `ccxt:kraken`); funding: `hyperliquid`, `bybit`, `okx`.

---

## Schema

- **Bars:** `DatetimeIndex` named `timestamp` (UTC, sorted, unique) + float
  `open, high, low, close, volume` (plus `adj_close` when a source provides it).
- **Funding:** `DatetimeIndex` named `time` (UTC) + `funding_rate`, `mark_price`.

In-memory frames are tz-aware UTC. `to_csv(tz_naive=True)` (the default) strips
the tz on write so output matches typical CSV readers.

---

## Cache

Fetches are cached under `$OMNIFEED_HOME` (default `./.omnifeed`) per
`(kind, source, symbol, timeframe)`. Repeat requests fetch only the missing
head/tail and merge — so re-running a pull is cheap and resumable. This is a
cache, separate from your `--out` datasets. Bypass with `use_cache=False` /
`--no-cache`.

---

## Extending

Implement `BarSource.fetch` (or `FundingSource.fetch_funding`) in
`omnifeed/sources/`, return a normalized frame via `schema.normalize_*`, and
register it in `router.py`. Natural next adapters: **OANDA** or **Twelve Data**
for real intraday forex depth (Yahoo only serves ~60d of FX intraday).

---

## Caveats

- **yfinance intraday history** is capped (~60d sub-hourly, ~730d hourly). For
  years of stock minute bars, use `--source alpaca`.
- **Alpaca free tier = IEX feed** (a volume subset; pass `--feed sip` if you have
  it) and only lists stocks that exist *today* → survivorship bias.
- **US geo-blocking:** Binance derivatives (451), Bybit (403), and OKX are not
  reachable from US IPs. Hyperliquid is the US-accessible funding default.
- **Funding cadence varies** (Hyperliquid hourly, Bybit/OKX 8h);
  `annualized_funding_pct` infers it from the data rather than assuming.

---

## Roadmap

- [ ] OANDA / Twelve Data adapter for intraday forex
- [ ] Options-chain source
- [ ] Optional Parquet dataset export (alongside CSV)
- [ ] Async batch fetching

---

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

`omnifeed` is a data-retrieval tool, not financial advice. Market data may be
incomplete, delayed, or subject to survivorship bias; validate before relying on
it for trading or research decisions.
