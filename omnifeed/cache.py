"""Local cache + incremental fetch.

Your 5-year downloader had resume logic (skip what's already on disk, fetch only
the missing tail). This generalizes it so *every* source inherits it for free:
we keep a rolling parquet (or pickle) of everything ever fetched per
(kind, source, symbol, timeframe), and on each request fetch only the gap
before/after what we already have.

Cache home: $OMNIFEED_HOME, else ./.omnifeed in the current directory.
This is a cache, not your dataset — CSV export (--out) is separate and
untouched by this.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from .symbols import safe_filename

# Prefer parquet (portable, typed); fall back to pickle if pyarrow is absent.
try:
    import pyarrow  # noqa: F401
    _EXT = ".parquet"
    _READ, _WRITE = pd.read_parquet, "to_parquet"
except Exception:  # noqa: BLE001
    _EXT = ".pkl"
    _READ, _WRITE = pd.read_pickle, "to_pickle"


def home() -> Path:
    p = Path(os.environ.get("OMNIFEED_HOME", ".omnifeed"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(kind: str, source: str, symbol: str, timeframe: str) -> Path:
    d = home() / kind / source.replace(":", "_")
    d.mkdir(parents=True, exist_ok=True)
    return d / (safe_filename(symbol, timeframe) + _EXT)


def _load(path: Path) -> pd.DataFrame | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        df = _READ(path)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)
        return df.sort_index()
    except Exception:  # noqa: BLE001 - a corrupt cache should never be fatal
        return None


def _save(df: pd.DataFrame, path: Path) -> None:
    getattr(df, _WRITE)(path)


def _slice(df: pd.DataFrame, start, end) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return df
    return df.loc[(df.index >= start) & (df.index <= end)]


def get_or_update(fetch_fn, kind, source, symbol, timeframe, start, end,
                  use_cache: bool = True) -> pd.DataFrame:
    """Return rows in [start, end], fetching only what the cache lacks.

    `fetch_fn(a, b)` must return an already-normalized frame with a UTC
    DatetimeIndex. Schema-agnostic: works for bars or funding alike.
    """
    if not use_cache:
        return _slice(fetch_fn(start, end), start, end)

    path = _path(kind, source, symbol, timeframe)
    cached = _load(path)

    if cached is not None and len(cached):
        cmin, cmax = cached.index.min(), cached.index.max()
        parts = [cached]
        if start < cmin:
            parts.append(fetch_fn(start, cmin))     # backfill older history
        if end > cmax:
            parts.append(fetch_fn(cmax, end))       # extend to now
        if len(parts) == 1:
            merged = cached
        else:
            merged = pd.concat(parts)
            merged = merged[~merged.index.duplicated(keep="last")].sort_index()
            _save(merged, path)
    else:
        merged = fetch_fn(start, end)
        if merged is not None and len(merged):
            _save(merged, path)

    return _slice(merged, start, end)
