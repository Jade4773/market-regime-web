from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests

from market_rules import analyze_index


INDEXES = {
    "kospi200": {"name": "KOSPI 200", "ticker": "^KS200", "currency": "KRW"},
    "kospi": {"name": "KOSPI", "ticker": "^KS11", "currency": "KRW"},
    "nasdaq100": {"name": "NASDAQ 100", "ticker": "^NDX", "currency": "USD"},
    "sp500": {"name": "S&P 500", "ticker": "^GSPC", "currency": "USD"},
}


@dataclass
class CacheItem:
    created_at: float
    value: dict[str, Any]


_CACHE: CacheItem | None = None


def get_market_snapshot() -> dict[str, Any]:
    global _CACHE
    ttl = int(os.getenv("CACHE_SECONDS", "900"))
    now = time.time()
    if _CACHE and now - _CACHE.created_at < ttl:
        return _CACHE.value

    results = {}
    for key, meta in INDEXES.items():
        try:
            history = fetch_history(meta["ticker"])
            results[key] = analyze_index(meta, history)
        except Exception as exc:
            results[key] = {
                "name": meta["name"],
                "ticker": meta["ticker"],
                "error": f"데이터를 가져오지 못했습니다: {exc}",
            }

    snapshot = {"items": results, "cache_seconds": ttl}
    _CACHE = CacheItem(created_at=now, value=snapshot)
    return snapshot


def fetch_history(ticker: str) -> pd.DataFrame:
    encoded = quote(ticker, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
        "?range=18mo&interval=1d&includePrePost=false"
    )
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise ValueError(chart["error"].get("description", "Yahoo Finance error"))

    result = (chart.get("result") or [None])[0]
    if not result or not result.get("timestamp"):
        raise ValueError("Yahoo Finance returned no rows")

    quote_data = result["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "Open": quote_data.get("open"),
            "High": quote_data.get("high"),
            "Low": quote_data.get("low"),
            "Close": quote_data.get("close"),
            "Volume": quote_data.get("volume"),
        },
        index=[
            datetime.fromtimestamp(ts, tz=timezone.utc).date()
            for ts in result["timestamp"]
        ],
    )
    df.index = pd.to_datetime(df.index)
    df = df.dropna(subset=["Close"]).sort_index().copy()
    df["Value"] = df["Close"] * df["Volume"]
    return df
