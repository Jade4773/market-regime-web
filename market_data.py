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
    "kospi200": {"name": "KOSPI 200", "ticker": "^KS200", "volume_ticker": "069500.KS", "ftd_min_gain_pct": 1.0, "currency": "KRW"},
    "kospi": {"name": "KOSPI", "ticker": "^KS11", "volume_ticker": "069500.KS", "ftd_min_gain_pct": 1.0, "currency": "KRW"},
    "nasdaq100": {"name": "NASDAQ 100", "ticker": "^NDX", "volume_ticker": "QQQ", "ftd_min_gain_pct": 1.0, "currency": "USD"},
    "sp500": {"name": "S&P 500", "ticker": "^GSPC", "volume_ticker": "SPY", "ftd_min_gain_pct": 1.0, "currency": "USD"},
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
            history = fetch_history(meta["ticker"], meta["volume_ticker"])
            results[key] = analyze_index(meta, history)
        except Exception as exc:
            results[key] = {
                "name": meta["name"],
                "ticker": meta["ticker"],
                "error": f"데이터를 가져오지 못했습니다: {exc}",
            }

    snapshot = {"items": results, "market_summary": build_market_summary(results), "cache_seconds": ttl}
    _CACHE = CacheItem(created_at=now, value=snapshot)
    return snapshot


def fetch_history(ticker: str, volume_ticker: str | None = None) -> pd.DataFrame:
    df = fetch_yahoo_chart(ticker)
    if volume_ticker and volume_ticker != ticker:
        proxy = fetch_yahoo_chart(volume_ticker)[["Close", "Volume"]].rename(
            columns={"Close": "VolumeProxyClose", "Volume": "VolumeProxy"}
        )
        df = df.join(proxy, how="left")
        df["Volume"] = df["VolumeProxy"].where(df["VolumeProxy"].notna(), df["Volume"])
        df["Value"] = df["VolumeProxyClose"].fillna(df["Close"]) * df["Volume"]
    else:
        df["Value"] = df["Close"] * df["Volume"]
    return df


def fetch_yahoo_chart(ticker: str) -> pd.DataFrame:
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
    return df


def build_market_summary(results: dict[str, Any]) -> dict[str, Any]:
    valid = [item for item in results.values() if not item.get("error")]
    pressured = [item for item in valid if item["distribution_count"] >= 4 or item["distribution_clustered"]]
    defensive = [item for item in valid if item["regime"] == "매도/방어"]
    if len(defensive) >= 2 or len(pressured) >= 3:
        return {"regime": "광범위한 매도 압력", "explanation": "여러 주요 지수에서 분산일 부담이 동시에 높습니다."}
    if len(pressured) >= 2:
        return {"regime": "시장 전반 주의", "explanation": "복수 지수에서 분산일이 누적되고 있습니다."}
    return {"regime": "시장 전반 양호", "explanation": "주요 지수 전반의 분산일 부담이 제한적입니다."}
