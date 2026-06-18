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


SNAPSHOT_SCHEMA_VERSION = 6


INDEXES = {
    "kospi200": {"name": "KOSPI 200", "ticker": "^KS200", "volume_ticker": "069500.KS", "ftd_min_gain_pct": 1.0, "currency": "KRW"},
    "kospi": {"name": "KOSPI", "ticker": "^KS11", "volume_ticker": "069500.KS", "ftd_min_gain_pct": 1.0, "currency": "KRW"},
    "nasdaq_composite": {"name": "나스닥종합", "ticker": "^IXIC", "volume_ticker": "QQQ", "ftd_min_gain_pct": 1.0, "currency": "USD"},
    "sp500": {"name": "S&P 500", "ticker": "^GSPC", "volume_ticker": "SPY", "ftd_min_gain_pct": 1.0, "currency": "USD"},
}


@dataclass
class CacheItem:
    created_at: float
    value: dict[str, Any]
    schema_version: int


_CACHE: CacheItem | None = None


def get_market_snapshot() -> dict[str, Any]:
    global _CACHE
    ttl = int(os.getenv("CACHE_SECONDS", "900"))
    now = time.time()
    if (
        _CACHE
        and _CACHE.schema_version == SNAPSHOT_SCHEMA_VERSION
        and now - _CACHE.created_at < ttl
    ):
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
    _CACHE = CacheItem(
        created_at=now,
        value=snapshot,
        schema_version=SNAPSHOT_SCHEMA_VERSION,
    )
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
    korea = build_region_summary(
        [results.get("kospi200"), results.get("kospi")],
        "한국",
    )
    united_states = build_region_summary(
        [results.get("nasdaq_composite"), results.get("sp500")],
        "미국",
    )

    region_regimes = {korea["regime"], united_states["regime"]}
    if "매도/방어" in region_regimes:
        regime = "시장 전반 방어 우선"
        explanation = "한국 또는 미국 시장에서 방어 신호가 확인됩니다."
    elif "주의" in region_regimes:
        regime = "시장 전반 주의"
        explanation = "한국 또는 미국 시장에서 확인이 필요한 신호가 있습니다."
    else:
        regime = "시장 전반 양호"
        explanation = "한국과 미국 시장의 주요 지수 흐름이 모두 우호적입니다."

    return {
        "regime": regime,
        "explanation": explanation,
        "regions": {"korea": korea, "united_states": united_states},
    }


def build_region_summary(
    items: list[dict[str, Any] | None],
    region_name: str,
) -> dict[str, Any]:
    valid = [item for item in items if item and not item.get("error")]
    if not valid:
        return {
            "name": region_name,
            "regime": "데이터 오류",
            "explanation": "시장 데이터를 확인할 수 없습니다.",
            "has_valid_ftd": False,
        }

    has_valid_ftd = any(
        item.get("follow_through") and item["follow_through"].get("is_active")
        for item in valid
    )
    defensive_count = sum(item["regime"] == "매도/방어" for item in valid)
    pressured_count = sum(
        item["distribution_count"] >= 4 or item["distribution_clustered"]
        for item in valid
    )

    if not has_valid_ftd or defensive_count >= 2:
        regime = "매도/방어"
        explanation = (
            f"{region_name} 핵심 지수 중 유효 팔로우쓰루데이가 없거나 "
            "양쪽 모두 방어 국면입니다."
        )
    elif defensive_count or pressured_count:
        regime = "주의"
        explanation = (
            f"{region_name} 핵심 지수 중 하나 이상에서 분산일 또는 방어 신호가 있습니다."
        )
    else:
        regime = "매수 우위"
        explanation = (
            f"{region_name} 핵심 지수 중 하나 이상에서 유효 팔로우쓰루데이가 확인되고 "
            "분산일 부담이 제한적입니다."
        )

    return {
        "name": region_name,
        "regime": regime,
        "explanation": explanation,
        "has_valid_ftd": has_valid_ftd,
    }
