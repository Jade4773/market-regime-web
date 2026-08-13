from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

import pandas as pd
import requests

from market_pulse.data import fetch_yahoo_chart, kis_get


ELS_SUBSCRIPTION_URL = (
    "https://securities.koreainvestment.com/main/banking/opensubsc/DervSubsc.jsp"
)
ELS_GUIDE_URL = (
    "https://securities.koreainvestment.com/main/mall/openels/_static/TF02ce050000.jsp"
)
ELS_NOTICE_URL = (
    "https://securities.koreainvestment.com/main/mall/openels/"
    "EdlsInfo.jsp?cmd=TF02cd010001&img_check=img_on_4"
)

INDEX_KEYWORDS = [
    "KOSPI",
    "코스피",
    "S&P",
    "SPX",
    "NASDAQ",
    "나스닥",
    "EURO",
    "STOXX",
    "유로스톡스",
    "NIKKEI",
    "닛케이",
    "HSCEI",
    "항셍",
]


def etf_candidate(
    *,
    market_group: str,
    signal_key: str,
    listing: str,
    ticker: str,
    yahoo_ticker: str,
    name: str,
    country: str,
    index: str,
    note: str,
    min_avg_volume: int,
) -> dict[str, Any]:
    return {
        "market_group": market_group,
        "signal_key": signal_key,
        "listing": listing,
        "ticker": ticker,
        "yahoo_ticker": yahoo_ticker,
        "name": name,
        "country": country,
        "index": index,
        "note": note,
        "min_avg_volume": min_avg_volume,
    }


ETF_CANDIDATES = [
    etf_candidate(market_group="korea", signal_key="kospi200", listing="국내상장 ETF", ticker="069500", yahoo_ticker="069500.KS", name="KODEX 200", country="대한민국", index="KOSPI 200", note="한국 대형주 대표지수", min_avg_volume=20000),
    etf_candidate(market_group="korea", signal_key="kospi200", listing="국내상장 ETF", ticker="102110", yahoo_ticker="102110.KS", name="TIGER 200", country="대한민국", index="KOSPI 200", note="한국 대형주 대표지수", min_avg_volume=20000),
    etf_candidate(market_group="korea", signal_key="kospi", listing="국내상장 ETF", ticker="226490", yahoo_ticker="226490.KS", name="KODEX 코스피", country="대한민국", index="KOSPI", note="코스피 시장 전체 노출", min_avg_volume=10000),
    etf_candidate(market_group="korea", signal_key="kospi200", listing="국내상장 ETF", ticker="091160", yahoo_ticker="091160.KS", name="KODEX 반도체", country="대한민국", index="KRX 반도체", note="국내 반도체 업종 주도 여부 확인", min_avg_volume=10000),
    etf_candidate(market_group="korea", signal_key="kospi200", listing="국내상장 ETF", ticker="305720", yahoo_ticker="305720.KS", name="KODEX 2차전지산업", country="대한민국", index="2차전지 산업", note="국내 성장 테마 주도 여부 확인", min_avg_volume=10000),
    etf_candidate(market_group="us", signal_key="sp500", listing="국내상장 ETF", ticker="360750", yahoo_ticker="360750.KS", name="TIGER 미국S&P500", country="미국", index="S&P 500", note="국내 계좌로 미국 대형주 지수 노출", min_avg_volume=20000),
    etf_candidate(market_group="us", signal_key="sp500", listing="국내상장 ETF", ticker="379800", yahoo_ticker="379800.KS", name="KODEX 미국S&P500TR", country="미국", index="S&P 500", note="총수익 지수형 미국 대형주 노출", min_avg_volume=20000),
    etf_candidate(market_group="us", signal_key="nasdaq_composite", listing="국내상장 ETF", ticker="133690", yahoo_ticker="133690.KS", name="TIGER 미국나스닥100", country="미국", index="NASDAQ 100", note="나스닥 성장주 대체 관찰", min_avg_volume=20000),
    etf_candidate(market_group="us", signal_key="nasdaq_composite", listing="국내상장 ETF", ticker="379810", yahoo_ticker="379810.KS", name="KODEX 미국나스닥100TR", country="미국", index="NASDAQ 100", note="나스닥 성장주 대체 관찰", min_avg_volume=20000),
    etf_candidate(market_group="us", signal_key="nasdaq_composite", listing="국내상장 ETF", ticker="381180", yahoo_ticker="381180.KS", name="TIGER 미국필라델피아반도체나스닥", country="미국", index="PHLX Semiconductor", note="미국 반도체 주도 업종", min_avg_volume=10000),
    etf_candidate(market_group="us", signal_key="nasdaq_composite", listing="국내상장 ETF", ticker="390390", yahoo_ticker="390390.KS", name="KODEX 미국반도체MV", country="미국", index="US Semiconductor", note="미국 반도체 주도 업종", min_avg_volume=10000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="SPY", yahoo_ticker="SPY", name="SPDR S&P 500 ETF Trust", country="미국", index="S&P 500", note="미국 대형주 대표지수", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="VOO", yahoo_ticker="VOO", name="Vanguard S&P 500 ETF", country="미국", index="S&P 500", note="미국 대형주 대표지수", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="nasdaq_composite", listing="미국상장 ETF", ticker="QQQ", yahoo_ticker="QQQ", name="Invesco QQQ Trust", country="미국", index="NASDAQ 100", note="나스닥 대형 성장주", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="nasdaq_composite", listing="미국상장 ETF", ticker="ONEQ", yahoo_ticker="ONEQ", name="Fidelity Nasdaq Composite ETF", country="미국", index="Nasdaq Composite", note="나스닥종합 직접 추종", min_avg_volume=20000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="IWM", yahoo_ticker="IWM", name="iShares Russell 2000 ETF", country="미국", index="Russell 2000", note="미국 중소형주 주도 여부 확인", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="nasdaq_composite", listing="미국상장 ETF", ticker="SMH", yahoo_ticker="SMH", name="VanEck Semiconductor ETF", country="미국", index="Semiconductors", note="반도체 주도 업종", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="nasdaq_composite", listing="미국상장 ETF", ticker="SOXX", yahoo_ticker="SOXX", name="iShares Semiconductor ETF", country="미국", index="Semiconductors", note="반도체 주도 업종", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="nasdaq_composite", listing="미국상장 ETF", ticker="IGV", yahoo_ticker="IGV", name="iShares Expanded Tech-Software ETF", country="미국", index="Software", note="소프트웨어 주도 업종", min_avg_volume=50000),
    etf_candidate(market_group="us", signal_key="nasdaq_composite", listing="미국상장 ETF", ticker="VGT", yahoo_ticker="VGT", name="Vanguard Information Technology ETF", country="미국", index="Information Technology", note="미국 기술주 주도 업종", min_avg_volume=50000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="XLK", yahoo_ticker="XLK", name="Technology Select Sector SPDR", country="미국", index="Technology", note="S&P 기술 섹터", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="XLC", yahoo_ticker="XLC", name="Communication Services SPDR", country="미국", index="Communication Services", note="커뮤니케이션 섹터", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="XLY", yahoo_ticker="XLY", name="Consumer Discretionary SPDR", country="미국", index="Consumer Discretionary", note="임의소비재 섹터", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="XLF", yahoo_ticker="XLF", name="Financial Select Sector SPDR", country="미국", index="Financials", note="금융 섹터", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="XLI", yahoo_ticker="XLI", name="Industrial Select Sector SPDR", country="미국", index="Industrials", note="산업재 섹터", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="XLE", yahoo_ticker="XLE", name="Energy Select Sector SPDR", country="미국", index="Energy", note="에너지 섹터", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="XLV", yahoo_ticker="XLV", name="Health Care Select Sector SPDR", country="미국", index="Health Care", note="헬스케어 섹터", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="EWJ", yahoo_ticker="EWJ", name="iShares MSCI Japan ETF", country="일본", index="MSCI Japan", note="일본 주식시장 주도 여부 확인", min_avg_volume=100000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="EWT", yahoo_ticker="EWT", name="iShares MSCI Taiwan ETF", country="대만", index="MSCI Taiwan", note="대만 반도체/기술주 노출", min_avg_volume=50000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="INDA", yahoo_ticker="INDA", name="iShares MSCI India ETF", country="인도", index="MSCI India", note="인도 주식시장 주도 여부 확인", min_avg_volume=50000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="EWY", yahoo_ticker="EWY", name="iShares MSCI South Korea ETF", country="대한민국", index="MSCI Korea", note="한국 시장의 미국상장 대체 ETF", min_avg_volume=50000),
    etf_candidate(market_group="us", signal_key="sp500", listing="미국상장 ETF", ticker="EWW", yahoo_ticker="EWW", name="iShares MSCI Mexico ETF", country="멕시코", index="MSCI Mexico", note="멕시코 주식시장 주도 여부 확인", min_avg_volume=20000),
]


class TableTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._in_table = True
            self._current_table = []
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
        elif self._in_row and tag in {"td", "th"}:
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell:
            cell = " ".join("".join(self._current_cell).split())
            self._current_row.append(cell)
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if any(self._current_row):
                self._current_table.append(self._current_row)
            self._in_row = False
        elif tag == "table" and self._in_table:
            if self._current_table:
                self.tables.append(self._current_table)
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)


def fetch_kis_els_products() -> dict[str, Any]:
    api_result = fetch_els_products_from_configured_kis_api()
    if api_result["attempted"] and api_result["items"]:
        return api_result

    fallback = fetch_els_products_from_public_site()
    fallback["api_status"] = api_result["status"]
    return fallback


def fetch_els_products_from_configured_kis_api() -> dict[str, Any]:
    # The public KIS Open API catalog does not currently expose an ELS/DLS
    # subscription-product endpoint. If KIS provides one separately, configure
    # these root-level Streamlit secrets so they are available as env vars.
    path = os.getenv("KIS_ELS_PRODUCTS_PATH")
    tr_id = os.getenv("KIS_ELS_PRODUCTS_TR_ID")
    if not path or not tr_id:
        return {
            "attempted": False,
            "items": [],
            "status": (
                "한국투자 Open API 공개 문서에서 ELS/DLS 청약 상품 조회 엔드포인트가 "
                "확인되지 않아 API 조회가 설정되지 않았습니다."
            ),
        }

    params = {}
    params_json = os.getenv("KIS_ELS_PRODUCTS_PARAMS_JSON", "{}")
    try:
        params = json.loads(params_json)
    except json.JSONDecodeError:
        return {
            "attempted": True,
            "items": [],
            "status": "KIS_ELS_PRODUCTS_PARAMS_JSON 형식이 올바른 JSON이 아닙니다.",
        }

    try:
        payload, _ = kis_get(path, tr_id, {str(k): str(v) for k, v in params.items()})
    except Exception as exc:
        return {
            "attempted": True,
            "items": [],
            "status": f"한국투자 ELS API 호출 실패: {exc}",
        }

    rows = payload.get("output") or payload.get("output1") or payload.get("output2") or []
    if isinstance(rows, dict):
        rows = [rows]
    products = api_rows_to_els_products(rows)
    if not products:
        return {
            "attempted": True,
            "items": [],
            "status": "한국투자 ELS API 응답에서 청약 가능한 지수형 ELS를 찾지 못했습니다.",
        }

    return {
        "attempted": True,
        "items": products[:12],
        "status": "한국투자증권 Open API 기준",
        "source_url": ELS_SUBSCRIPTION_URL,
        "guide_url": ELS_GUIDE_URL,
        "notice_url": ELS_NOTICE_URL,
        "api_status": "한국투자 ELS API 조회 성공",
    }


def api_rows_to_els_products(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    today = datetime.now(timezone(timedelta(hours=9))).date()
    products = []
    for row in rows:
        text = " ".join(str(value) for value in row.values() if value not in {None, ""})
        if not looks_like_open_index_els(text):
            continue
        dates = parse_dates(text)
        if dates and max(dates) < today:
            continue
        product = {
            "상품명": field_by_keywords(row, ["상품", "종목", "회차", "prdt", "prod"], text[:80]),
            "기초자산": field_by_keywords(row, ["기초", "자산", "under"], infer_underlyings(text)),
            "청약기간": field_by_keywords(row, ["청약", "모집", "subsc"], infer_date_range(text)),
            "수익조건": field_by_keywords(row, ["수익", "쿠폰", "yield", "coupon"], "-"),
            "만기": field_by_keywords(row, ["만기", "maturity"], "-"),
            "숙려/청약 상태": infer_subscription_status(dates),
        }
        products.append(product)
    return dedupe_products(products)


def field_by_keywords(row: dict[str, Any], keywords: list[str], fallback: str) -> str:
    for key, value in row.items():
        normalized = str(key).replace("_", "").lower()
        if value is None or value == "":
            continue
        if any(keyword.lower() in normalized for keyword in keywords):
            return str(value)
    return fallback


def fetch_els_products_from_public_site() -> dict[str, Any]:
    try:
        response = requests.get(
            ELS_SUBSCRIPTION_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        response.raise_for_status()
    except Exception as exc:
        return empty_els_result(f"한국투자증권 청약 화면에 접속하지 못했습니다: {exc}")

    html = response.text
    if "login.jsp" in response.url or "로그인" in html and "청약" not in html:
        return empty_els_result("청약 종목 조회 화면이 로그인 세션을 요구합니다.")

    products = parse_els_products(html)
    if not products:
        return empty_els_result("현재 자동으로 판독 가능한 지수형 ELS 청약 상품이 없습니다.")

    return {
        "items": products[:12],
        "status": "한국투자증권 청약 화면에서 자동 판독",
        "source_url": ELS_SUBSCRIPTION_URL,
        "guide_url": ELS_GUIDE_URL,
        "notice_url": ELS_NOTICE_URL,
    }


def empty_els_result(reason: str) -> dict[str, Any]:
    return {
        "items": [],
        "status": reason,
        "source_url": ELS_SUBSCRIPTION_URL,
        "guide_url": ELS_GUIDE_URL,
        "notice_url": ELS_NOTICE_URL,
    }


def parse_els_products(html: str) -> list[dict[str, str]]:
    parser = TableTextParser()
    parser.feed(html)
    today = datetime.now(timezone(timedelta(hours=9))).date()
    products = []

    for table in parser.tables:
        if len(table) < 2:
            continue
        headers = [normalize_header(value) for value in table[0]]
        for row in table[1:]:
            text = " ".join(row)
            if not looks_like_open_index_els(text):
                continue

            dates = parse_dates(text)
            if dates and max(dates) < today:
                continue

            product = row_to_product(headers, row)
            product["숙려/청약 상태"] = infer_subscription_status(dates)
            products.append(product)

    return dedupe_products(products)


def looks_like_open_index_els(text: str) -> bool:
    upper = text.upper()
    return "ELS" in upper and any(keyword.upper() in upper for keyword in INDEX_KEYWORDS)


def normalize_header(value: str) -> str:
    compact = value.replace(" ", "")
    if "상품" in compact or "종목" in compact or "회차" in compact:
        return "상품명"
    if "기초" in compact or "자산" in compact:
        return "기초자산"
    if "청약" in compact or "모집" in compact:
        return "청약기간"
    if "수익" in compact or "쿠폰" in compact:
        return "수익조건"
    if "만기" in compact:
        return "만기"
    return value or "항목"


def row_to_product(headers: list[str], row: list[str]) -> dict[str, str]:
    fields = {headers[idx] if idx < len(headers) else f"항목{idx + 1}": value for idx, value in enumerate(row)}
    row_text = " · ".join(value for value in row if value)
    return {
        "상품명": first_present(fields, ["상품명", "종목명", "회차"], row_text[:80]),
        "기초자산": first_present(fields, ["기초자산"], infer_underlyings(row_text)),
        "청약기간": first_present(fields, ["청약기간", "모집기간"], infer_date_range(row_text)),
        "수익조건": first_present(fields, ["수익조건"], "-"),
        "만기": first_present(fields, ["만기"], "-"),
    }


def first_present(fields: dict[str, str], keys: list[str], fallback: str) -> str:
    for key in keys:
        value = fields.get(key)
        if value:
            return value
    return fallback


def infer_underlyings(text: str) -> str:
    found = [keyword for keyword in INDEX_KEYWORDS if keyword.upper() in text.upper()]
    return ", ".join(dict.fromkeys(found)) or "-"


def infer_date_range(text: str) -> str:
    dates = parse_dates(text)
    if not dates:
        return "-"
    if len(dates) == 1:
        return dates[0].strftime("%Y-%m-%d")
    return f"{min(dates).strftime('%Y-%m-%d')} ~ {max(dates).strftime('%Y-%m-%d')}"


def infer_subscription_status(dates: list[Any]) -> str:
    if not dates:
        return "청약 가능 여부 확인 필요"
    today = datetime.now(timezone(timedelta(hours=9))).date()
    if min(dates) <= today <= max(dates):
        return "청약/숙려기간 진행 중"
    if today < min(dates):
        return "청약 예정"
    return "청약 종료"


def parse_dates(text: str) -> list[Any]:
    dates = []
    for match in re.finditer(r"(20\d{2})[.\-/년 ]+(\d{1,2})[.\-/월 ]+(\d{1,2})", text):
        try:
            dates.append(
                datetime(
                    int(match.group(1)), int(match.group(2)), int(match.group(3))
                ).date()
            )
        except ValueError:
            continue
    return dates


def dedupe_products(products: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    unique = []
    for product in products:
        key = (product.get("상품명"), product.get("기초자산"), product.get("청약기간"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(product)
    return unique


def build_etf_recommendations(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    items = snapshot.get("items", {})
    market_gates = build_market_gates(items)
    analyzed_candidates = []

    for candidate in ETF_CANDIDATES:
        market_item = market_gates.get(candidate["market_group"])
        if not market_item:
            continue
        benchmark_item = items.get(candidate["signal_key"]) or market_item
        if benchmark_item.get("error"):
            continue

        oneil = market_item.get("signals", {}).get("oneil", {})
        follow_through = market_item.get("follow_through")
        analyzed = analyze_etf_candidate(
            candidate,
            market_item,
            oneil,
            follow_through,
            benchmark_item,
        )
        if analyzed:
            analyzed_candidates.append(analyzed)

    ranked = rank_etf_candidates(analyzed_candidates)
    leaders = [
        item
        for item in ranked
        if item["leader_rank"] <= 12
        and item["can_slim_score"] >= 68
        and item["relative_strength_score"] >= 60
        and item["action"] != "매도/방어"
    ]

    return sorted(
        leaders,
        key=lambda item: (
            item["leader_rank"],
            -item["relative_strength_score"],
            item["ticker"],
        ),
    )[:2]


def build_market_gates(items: dict[str, Any]) -> dict[str, dict[str, Any]]:
    gates = {}
    korea = best_valid_market(items, ["kospi200", "kospi"])
    united_states = best_valid_market(items, ["sp500", "nasdaq_composite"])
    if korea:
        gates["korea"] = korea
    if united_states:
        gates["us"] = united_states
    return gates


def best_valid_market(items: dict[str, Any], keys: list[str]) -> dict[str, Any] | None:
    valid = []
    for key in keys:
        item = items.get(key)
        if not item or item.get("error"):
            continue
        oneil = item.get("signals", {}).get("oneil", {})
        follow_through = item.get("follow_through")
        if qualifies_oneil_buy(item, oneil, follow_through):
            valid.append(item)
    if not valid:
        return None
    return sorted(
        valid,
        key=lambda item: (
            -item.get("signals", {}).get("oneil", {}).get("score", 0),
            item.get("distribution_count", 99),
            item.get("name", ""),
        ),
    )[0]


def rank_etf_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []

    scores = sorted(item["relative_strength_score"] for item in candidates)
    total = len(scores)
    for item in candidates:
        weaker_or_equal = sum(1 for score in scores if score <= item["relative_strength_score"])
        percentile = round(weaker_or_equal / total * 99)
        item["leader_percentile"] = percentile
        item["components"]["ETF 상대강도 순위"] = percentile

    ranked = sorted(
        candidates,
        key=lambda item: (
            -item["leader_percentile"],
            -item["can_slim_score"],
            item["ticker"],
        ),
    )
    for rank, item in enumerate(ranked, start=1):
        item["leader_rank"] = rank
        item["leader_label"] = leader_label(item)
    return ranked[:18]


def leader_label(item: dict[str, Any]) -> str:
    if item["action"] == "매도/방어":
        return "방어"
    if item["leader_rank"] <= 5:
        return "주도 ETF"
    if item["leader_rank"] <= 8 and item["action"] in {"매수 후보", "관심/대기"}:
        return "주도 후보"
    if item["action"] == "추격 주의":
        return "추격 주의"
    return item["action"]


def analyze_etf_candidate(
    candidate: dict[str, Any],
    market_item: dict[str, Any],
    oneil: dict[str, Any],
    follow_through: dict[str, Any] | None,
    benchmark_item: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        df = prepare_etf_history(fetch_yahoo_chart(candidate["yahoo_ticker"]))
    except Exception:
        return None
    if len(df) < 220:
        return None

    latest = df.iloc[-1]
    previous = df.iloc[-2]
    close = float(latest["Close"])
    ma50 = float(latest["ma50"]) if pd.notna(latest["ma50"]) else None
    ma200 = float(latest["ma200"]) if pd.notna(latest["ma200"]) else None
    pivot = float(latest["pivot55"]) if pd.notna(latest["pivot55"]) else None
    avg_volume50 = float(latest["avg_volume50"]) if pd.notna(latest["avg_volume50"]) else 0.0
    volume_change = pct(latest["Volume"], previous["Volume"])
    return63 = float(latest["return63"]) if pd.notna(latest["return63"]) else 0.0
    return126 = float(latest["return126"]) if pd.notna(latest["return126"]) else 0.0
    return252 = float(latest["return252"]) if pd.notna(latest["return252"]) else 0.0
    distance_high252 = (
        float(latest["distance_high252"]) if pd.notna(latest["distance_high252"]) else None
    )

    benchmark_metrics = benchmark_item.get("signals", {}).get("trend", {}).get("metrics", {})
    benchmark_return63 = numeric_or_zero(benchmark_metrics.get("3개월 수익률"))
    benchmark_return126 = numeric_or_zero(benchmark_metrics.get("6개월 수익률"))

    components = score_can_slim_etf(
        close=close,
        ma50=ma50,
        ma200=ma200,
        pivot=pivot,
        return63=return63,
        return126=return126,
        benchmark_return63=benchmark_return63,
        benchmark_return126=benchmark_return126,
        distance_high252=distance_high252,
        avg_volume50=avg_volume50,
        min_avg_volume=float(candidate.get("min_avg_volume", 0)),
    )
    raw_rs_score = relative_strength_score(
        return63=return63,
        return126=return126,
        return252=return252,
        distance_high252=distance_high252,
    )
    score = sum(components.values())
    action = etf_action(score, close, pivot)
    sell_signal = current_sell_signal(market_item, close, ma50, pivot, latest, avg_volume50)
    if "매도" in sell_signal or "방어" in sell_signal:
        action = "매도/방어"

    ftd_text = f"{follow_through['date']} FTD" if follow_through else "FTD 확인 필요"
    return {
        **candidate,
        "market": market_item["name"],
        "benchmark_market": benchmark_item["name"],
        "opinion": oneil.get("opinion", "-"),
        "can_slim_score": score,
        "components": components,
        "action": action,
        "last_price": close,
        "change_pct": float(latest["pct_change"]) if pd.notna(latest["pct_change"]) else 0.0,
        "return63": return63,
        "return126": return126,
        "return252": return252,
        "rs_vs_market63": return63 - benchmark_return63,
        "rs_vs_market126": return126 - benchmark_return126,
        "relative_strength_score": raw_rs_score,
        "leader_percentile": 0,
        "leader_rank": 999,
        "leader_label": action,
        "ma50": ma50,
        "ma200": ma200,
        "pivot": pivot,
        "buy_low": pivot,
        "buy_high": pivot * 1.05 if pivot else None,
        "stop_loss": pivot * 0.92 if pivot else None,
        "profit_low": pivot * 1.20 if pivot else None,
        "profit_high": pivot * 1.25 if pivot else None,
        "avg_volume50": avg_volume50,
        "volume_change_pct": volume_change,
        "sell_signal": sell_signal,
        "basis": (
            f"{market_item['name']} {oneil.get('opinion', '-')}, {ftd_text}, "
            f"활성 분산일 {market_item.get('distribution_count', 0)}회, "
            f"{benchmark_item['name']} 대비 ETF 상대강도 원점수 {raw_rs_score}점"
        ),
        "data_source": "Yahoo Finance ETF 가격",
        "data_status": market_item.get("data_status", "-"),
    }


def prepare_etf_history(history: pd.DataFrame) -> pd.DataFrame:
    df = history.sort_index().copy()
    df["pct_change"] = df["Close"].pct_change() * 100
    df["ma20"] = df["Close"].rolling(20).mean()
    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma200"] = df["Close"].rolling(200).mean()
    df["avg_volume50"] = df["Volume"].rolling(50).mean()
    df["return63"] = df["Close"].pct_change(63) * 100
    df["return126"] = df["Close"].pct_change(126) * 100
    df["return252"] = df["Close"].pct_change(252) * 100
    df["high252"] = df["Close"].rolling(252).max()
    df["distance_high252"] = (df["Close"] / df["high252"] - 1) * 100
    # Recent 11-week closing high is a practical ETF proxy for an O'Neil-style pivot.
    df["pivot55"] = df["Close"].shift(1).rolling(55).max()
    return df


def relative_strength_score(
    *,
    return63: float,
    return126: float,
    return252: float,
    distance_high252: float | None,
) -> int:
    score = 0
    if return63 > 0:
        score += min(30, max(0, int(return63 * 1.2)))
    if return126 > 0:
        score += min(30, max(0, int(return126 * 0.8)))
    if return252 > 0:
        score += min(25, max(0, int(return252 * 0.35)))
    if distance_high252 is not None:
        if distance_high252 >= -5:
            score += 15
        elif distance_high252 >= -10:
            score += 10
        elif distance_high252 >= -15:
            score += 5
    return min(score, 100)


def score_can_slim_etf(
    *,
    close: float,
    ma50: float | None,
    ma200: float | None,
    pivot: float | None,
    return63: float,
    return126: float,
    benchmark_return63: float,
    benchmark_return126: float,
    distance_high252: float | None,
    avg_volume50: float,
    min_avg_volume: float,
) -> dict[str, int]:
    trend_score = 0
    if ma50 and close > ma50:
        trend_score += 10
    if ma200 and close > ma200:
        trend_score += 8
    if ma50 and ma200 and ma50 > ma200:
        trend_score += 7

    rs_score = 0
    if return63 > benchmark_return63:
        rs_score += 10
    if return126 > benchmark_return126:
        rs_score += 10

    position_score = 0
    if pivot and pivot <= close <= pivot * 1.05:
        position_score = 20
    elif pivot and pivot * 0.95 <= close < pivot:
        position_score = 14
    elif pivot and close > pivot * 1.05:
        position_score = 8
    elif distance_high252 is not None and distance_high252 >= -15:
        position_score = 8

    liquidity_score = 10 if avg_volume50 >= min_avg_volume else 5

    return {
        "M 시장 방향": 25,
        "L 상대강도": rs_score,
        "추세 템플릿": trend_score,
        "매수 위치": position_score,
        "유동성": liquidity_score,
    }


def etf_action(score: int, close: float, pivot: float | None) -> str:
    if pivot and pivot <= close <= pivot * 1.05 and score >= 80:
        return "매수 후보"
    if pivot and close > pivot * 1.05 and score >= 75:
        return "추격 주의"
    if score >= 65:
        return "관심/대기"
    return "제외"


def current_sell_signal(
    market_item: dict[str, Any],
    close: float,
    ma50: float | None,
    pivot: float | None,
    latest: pd.Series,
    avg_volume50: float,
) -> str:
    if market_item.get("regime") == "매도/방어" or market_item.get("distribution_count", 0) >= 6:
        return "시장 매도/방어 신호"
    if pivot and close <= pivot * 0.92:
        return "매수 기준가 대비 -8% 손절선 이탈"
    if ma50 and close < ma50 and latest.get("Volume", 0) > avg_volume50:
        return "거래량 동반 50일선 이탈"
    if market_item.get("distribution_count", 0) >= 4:
        return "분산일 누적 주의"
    if pivot and close >= pivot * 1.20:
        return "20~25% 이익 보호 구간"
    return "보유/관찰"


def pct(current: Any, previous: Any) -> float:
    if previous in {None, 0} or pd.isna(previous) or pd.isna(current):
        return 0.0
    return (float(current) / float(previous) - 1) * 100


def numeric_or_zero(value: Any) -> float:
    try:
        if value is None or pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def qualifies_oneil_buy(
    item: dict[str, Any],
    oneil: dict[str, Any],
    follow_through: dict[str, Any] | None,
) -> bool:
    return bool(
        oneil.get("opinion") == "매수 우위"
        and follow_through
        and follow_through.get("is_active")
        and item.get("distribution_count", 0) < 4
    )
