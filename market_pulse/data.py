from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests

from market_pulse.rules import analyze_index


SNAPSHOT_SCHEMA_VERSION = 18


INDEXES = {
    "kospi200": {"name": "KOSPI 200", "ticker": "^KS200", "volume_ticker": "069500.KS", "naver_code": "KPI200", "kis_domestic_code": "2001", "ftd_min_gain_pct": 1.25, "currency": "KRW"},
    "kospi": {"name": "KOSPI", "ticker": "^KS11", "volume_ticker": "069500.KS", "naver_code": "KOSPI", "kis_domestic_code": "0001", "ftd_min_gain_pct": 1.25, "currency": "KRW"},
    "nasdaq_composite": {"name": "나스닥종합", "ticker": "^IXIC", "volume_ticker": "QQQ", "kis_overseas_code": ".IXIC", "ftd_min_gain_pct": 1.7, "currency": "USD"},
    "sp500": {"name": "S&P 500", "ticker": "^GSPC", "volume_ticker": "SPY", "kis_overseas_code": ".SPX", "ftd_min_gain_pct": 1.25, "currency": "USD"},
}


@dataclass
class CacheItem:
    created_at: float
    value: dict[str, Any]
    schema_version: int


_CACHE: CacheItem | None = None
_KIS_TOKEN_CACHE: dict[str, Any] = {}


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
            history = fetch_history(meta)
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


def fetch_history(meta: dict[str, Any]) -> pd.DataFrame:
    ticker = meta["ticker"]
    volume_ticker = meta.get("volume_ticker")
    df = fetch_yahoo_chart(ticker)
    df = apply_naver_fallback(df, meta.get("naver_code"))
    df = apply_kis_priority(df, meta)
    if volume_ticker and volume_ticker != ticker:
        proxy = fetch_yahoo_chart(volume_ticker)[["Close", "Volume"]].rename(
            columns={"Close": "VolumeProxyClose", "Volume": "VolumeProxy"}
        )
        df = df.join(proxy, how="left")
        use_proxy = df["VolumeProxy"].notna() & df["DataSource"].eq("Yahoo Finance")
        df["Volume"] = df["Volume"].where(~use_proxy, df["VolumeProxy"])
        df["VolumeSource"] = df["VolumeSource"].where(~use_proxy, volume_ticker)
        value_price = df["Close"].where(
            ~use_proxy, df["VolumeProxyClose"].fillna(df["Close"])
        )
        df["Value"] = value_price * df["Volume"]
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
    df["DataSource"] = "Yahoo Finance"
    df["DataStatus"] = "마감 기준"
    df["SourceNote"] = "야후 파이낸스 기준"
    df["VolumeSource"] = ticker
    return df


def apply_naver_fallback(df: pd.DataFrame, naver_code: str | None) -> pd.DataFrame:
    if not naver_code:
        return df

    try:
        naver = fetch_naver_index_chart(naver_code)
    except Exception:
        return df

    if naver.empty:
        return df

    # Korean index rows from Yahoo can occasionally miss recent trading days while
    # still reporting a latest date. Prefer Naver for its available recent window so
    # daily changes are computed against the actual previous session.
    merged = pd.concat([df, naver], axis=0)
    return merged[~merged.index.duplicated(keep="last")].sort_index()


def apply_kis_priority(df: pd.DataFrame, meta: dict[str, Any]) -> pd.DataFrame:
    try:
        kis = fetch_kis_index_chart(meta)
    except Exception:
        return df

    if kis.empty:
        return df

    merged = pd.concat([df, kis], axis=0)
    return merged[~merged.index.duplicated(keep="last")].sort_index()


def fetch_kis_index_chart(meta: dict[str, Any]) -> pd.DataFrame:
    if not kis_credentials_available():
        return pd.DataFrame()

    if meta.get("kis_domestic_code"):
        return fetch_kis_domestic_index_chart(meta["kis_domestic_code"])
    if meta.get("kis_overseas_code"):
        code = kis_overseas_code(meta["ticker"], meta["kis_overseas_code"])
        return fetch_kis_overseas_index_chart(code)
    return pd.DataFrame()


def kis_credentials_available() -> bool:
    return bool(kis_config_value("KIS_APP_KEY") and kis_config_value("KIS_APP_SECRET"))


def kis_config_value(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value:
        return value

    if not streamlit_context_available():
        return default

    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
        kis_secrets = st.secrets.get("kis", {})
        section_key = name.removeprefix("KIS_").lower()
        if section_key in kis_secrets:
            return str(kis_secrets[section_key])
    except Exception:
        pass
    return default


def streamlit_context_available() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx(suppress_warning=True) is not None
    except Exception:
        return False


def kis_base_url() -> str:
    explicit = kis_config_value("KIS_BASE_URL")
    if explicit:
        return explicit.rstrip("/")

    env = (kis_config_value("KIS_ENV", "prod") or "prod").lower()
    if env in {"demo", "vts", "mock", "paper"}:
        return "https://openapivts.koreainvestment.com:29443"
    return "https://openapi.koreainvestment.com:9443"


def kis_get(
    path: str,
    tr_id: str,
    params: dict[str, str],
    tr_cont: str = "",
) -> tuple[dict[str, Any], str]:
    base_url = kis_base_url()
    app_key = kis_config_value("KIS_APP_KEY")
    app_secret = kis_config_value("KIS_APP_SECRET")
    access_token = kis_access_token(base_url, app_key, app_secret)
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": tr_id,
        "custtype": kis_config_value("KIS_CUSTTYPE", "P") or "P",
    }
    if tr_cont:
        headers["tr_cont"] = tr_cont

    response = requests.get(
        f"{base_url}{path}",
        headers=headers,
        params=params,
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("rt_cd") != "0":
        message = payload.get("msg1") or payload.get("msg_cd") or "KIS API error"
        raise ValueError(message)
    return payload, response.headers.get("tr_cont", "")


def kis_access_token(base_url: str, app_key: str | None, app_secret: str | None) -> str:
    if not app_key or not app_secret:
        raise ValueError("KIS credentials are not configured")

    cache_key = f"{base_url}:{app_key[-8:]}"
    cached = _KIS_TOKEN_CACHE.get(cache_key)
    now = time.time()
    if cached and cached["expires_at"] - 60 > now:
        return cached["token"]

    response = requests.post(
        f"{base_url}/oauth2/tokenP",
        headers={"content-type": "application/json; charset=utf-8"},
        json={
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecret": app_secret,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise ValueError(payload.get("error_description") or "KIS token was not issued")

    expires_in = int(payload.get("expires_in") or 86400)
    _KIS_TOKEN_CACHE[cache_key] = {
        "token": token,
        "expires_at": now + min(expires_in, 24 * 60 * 60),
    }
    return token


def fetch_kis_domestic_index_chart(index_code: str) -> pd.DataFrame:
    start_date, end_date = kis_date_range()
    rows = kis_paginated_rows(
        path="/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice",
        tr_id="FHKUP03500100",
        params={
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": index_code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
        },
    )
    return kis_rows_to_frame(
        rows,
        date_key="stck_bsop_date",
        open_key="bstp_nmix_oprc",
        high_key="bstp_nmix_hgpr",
        low_key="bstp_nmix_lwpr",
        close_key="bstp_nmix_prpr",
        volume_key="acml_vol",
        value_key="acml_tr_pbmn",
        source="한국투자증권",
        volume_source="한국투자증권 지수 거래량",
    )


def fetch_kis_overseas_index_chart(index_code: str) -> pd.DataFrame:
    start_date, end_date = kis_date_range()
    rows = kis_paginated_rows(
        path="/uapi/overseas-price/v1/quotations/inquire-daily-chartprice",
        tr_id="FHKST03030100",
        params={
            "FID_COND_MRKT_DIV_CODE": "N",
            "FID_INPUT_ISCD": index_code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
        },
    )
    return kis_rows_to_frame(
        rows,
        date_key="stck_bsop_date",
        open_key="ovrs_nmix_oprc",
        high_key="ovrs_nmix_hgpr",
        low_key="ovrs_nmix_lwpr",
        close_key="ovrs_nmix_prpr",
        volume_key="acml_vol",
        value_key="acml_tr_pbmn",
        source="한국투자증권",
        volume_source="한국투자증권 지수 거래량",
    )


def kis_paginated_rows(
    path: str,
    tr_id: str,
    params: dict[str, str],
    max_depth: int = 10,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    tr_cont = ""
    for _ in range(max_depth):
        payload, next_cont = kis_get(path, tr_id, params, tr_cont)
        output = payload.get("output2") or payload.get("output") or []
        if isinstance(output, dict):
            output = [output]
        rows.extend(output)
        if next_cont not in {"M", "F"}:
            break
        tr_cont = "N"
        time.sleep(0.1)
    return rows


def kis_rows_to_frame(
    rows: list[dict[str, Any]],
    *,
    date_key: str,
    open_key: str,
    high_key: str,
    low_key: str,
    close_key: str,
    volume_key: str,
    value_key: str,
    source: str,
    volume_source: str,
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        {
            "Open": [number_value(row.get(open_key)) for row in rows],
            "High": [number_value(row.get(high_key)) for row in rows],
            "Low": [number_value(row.get(low_key)) for row in rows],
            "Close": [number_value(row.get(close_key)) for row in rows],
            "Volume": [number_value(row.get(volume_key)) for row in rows],
            "Value": [number_value(row.get(value_key)) for row in rows],
        },
        index=[pd.to_datetime(row.get(date_key), format="%Y%m%d") for row in rows],
    )
    df = df.dropna(subset=["Close"]).sort_index().copy()
    df["Volume"] = df["Volume"].fillna(0)
    if df["Value"].isna().all():
        df["Value"] = df["Close"] * df["Volume"]
    df["DataSource"] = source
    df["DataStatus"] = market_data_status(df.index.max())
    df["SourceNote"] = "한국투자증권 Open API 기준"
    df["VolumeSource"] = volume_source
    return df


def kis_date_range() -> tuple[str, str]:
    now = datetime.now(timezone(timedelta(hours=9)))
    start = now - timedelta(days=560)
    return start.strftime("%Y%m%d"), now.strftime("%Y%m%d")


def kis_overseas_code(ticker: str, default: str) -> str:
    env_key = f"KIS_{ticker.strip('^').replace('.', '').upper()}_CODE"
    return kis_config_value(env_key, default) or default


def number_value(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def fetch_naver_index_chart(code: str) -> pd.DataFrame:
    url = f"https://api.stock.naver.com/chart/domestic/index/{code}?periodType=dayCandle"
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://stock.naver.com/"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("priceInfos") or []
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        {
            "Open": [row.get("openPrice") for row in rows],
            "High": [row.get("highPrice") for row in rows],
            "Low": [row.get("lowPrice") for row in rows],
            "Close": [row.get("closePrice") for row in rows],
            "Volume": [row.get("accumulatedTradingVolume") for row in rows],
        },
        index=[pd.to_datetime(row.get("localDate"), format="%Y%m%d") for row in rows],
    )
    df = df.dropna(subset=["Close"]).sort_index().copy()
    df["DataSource"] = "Npay 증권"
    df["DataStatus"] = naver_data_status(df.index.max())
    df["SourceNote"] = "야후 지연으로 네이버 대체 데이터 사용"
    df["VolumeSource"] = "Npay 지수 거래량"
    return df


def naver_data_status(latest_date: pd.Timestamp) -> str:
    return market_data_status(latest_date)


def market_data_status(latest_date: pd.Timestamp) -> str:
    now = datetime.now(timezone(timedelta(hours=9)))
    if latest_date.date() == now.date() and now.hour < 16:
        return "장중 잠정"
    return "마감 기준"


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
