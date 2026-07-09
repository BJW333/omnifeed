"""Shared HTTP plumbing: one browser-UA session, one retry policy, one rate
limiter. Every raw-REST source (Coinbase, Alpaca, funding) uses these instead
of hand-rolling `for attempt in range(5): ... time.sleep(...)` five times over.
"""
from __future__ import annotations

import time

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def session(headers: dict | None = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    if headers:
        s.headers.update(headers)
    return s


class RateLimiter:
    """Enforce a minimum interval between calls (single-threaded, wall clock)."""

    def __init__(self, min_interval: float):
        self.min_interval = float(min_interval)
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        gap = time.monotonic() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.monotonic()


def get_json(url, params=None, headers=None, timeout=30, retries=5,
             backoff=2.0, sess: requests.Session | None = None,
             rate_limiter: RateLimiter | None = None):
    """GET -> parsed JSON, retrying transient failures with linear backoff.

    Raises the last exception if every attempt fails. Callers that want to
    *tolerate* a bad status (e.g. Coinbase paging past listing date) should use
    a plain session .get() and inspect status_code themselves.
    """
    s = sess or session(headers)
    last = None
    for attempt in range(retries):
        if rate_limiter:
            rate_limiter.wait()
        try:
            r = s.get(url, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:          # noqa: BLE001 - retry any transient error
            last = e
            if attempt == retries - 1:
                raise
            time.sleep(backoff * (attempt + 1))
    raise last  # unreachable


def post_json(url, json_body, headers=None, timeout=30, retries=5,
              backoff=2.0, sess: requests.Session | None = None,
              rate_limiter: RateLimiter | None = None):
    """POST a JSON body -> parsed JSON, with the same retry policy as get_json.
    Used by venues whose read API is POST-only (e.g. Hyperliquid's /info)."""
    s = sess or session(headers)
    last = None
    for attempt in range(retries):
        if rate_limiter:
            rate_limiter.wait()
        try:
            r = s.post(url, json=json_body, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt == retries - 1:
                raise
            time.sleep(backoff * (attempt + 1))
    raise last  # unreachable
