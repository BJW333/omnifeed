"""Ticker-universe helpers. Ported from the S&P 600 fetcher in download_data.py
and generalized so you can pull a constituent list or load one from a file to
feed the downloader.
"""
from __future__ import annotations

import io
import urllib.request
from pathlib import Path

import pandas as pd

from .http import UA

_WIKI = {
    "sp600": ["https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
              "https://en.m.wikipedia.org/wiki/List_of_S%26P_600_companies"],
    "sp500": ["https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
              "https://en.m.wikipedia.org/wiki/List_of_S%26P_500_companies"],
}


def _fetch_constituents(urls) -> list[str]:
    last_err = None
    for url in urls:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA,
                              "Accept": "text/html,application/xhtml+xml"})
            html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
            for t in pd.read_html(io.StringIO(html)):
                cols = [str(c).lower() for c in t.columns]
                col = next((t.columns[i] for i, c in enumerate(cols)
                            if "symbol" in c or "ticker" in c), None)
                if col is not None:
                    syms = [str(x).strip().replace(".", "-") for x in t[col].tolist()
                            if isinstance(x, str) and 1 <= len(x) <= 6]
                    if len(syms) > 100:
                        return sorted(set(syms))
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise SystemExit(f"Could not fetch constituent list (last error: {last_err}). "
                     f"Save tickers one-per-line and pass --symbols-file instead.")


def sp600() -> list[str]:
    return _fetch_constituents(_WIKI["sp600"])


def sp500() -> list[str]:
    return _fetch_constituents(_WIKI["sp500"])


def load_tickers(path: str) -> list[str]:
    return sorted({ln.strip().upper() for ln in Path(path).read_text().splitlines()
                   if ln.strip()})
