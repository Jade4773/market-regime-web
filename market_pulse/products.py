from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

import requests


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


ETF_CANDIDATES = [
    {
        "signal_key": "kospi200",
        "listing": "국내상장 ETF",
        "ticker": "069500",
        "name": "KODEX 200",
        "country": "대한민국",
        "index": "KOSPI 200",
        "note": "한국 대형주 대표지수 추종",
    },
    {
        "signal_key": "kospi200",
        "listing": "국내상장 ETF",
        "ticker": "102110",
        "name": "TIGER 200",
        "country": "대한민국",
        "index": "KOSPI 200",
        "note": "한국 대형주 대표지수 추종",
    },
    {
        "signal_key": "kospi",
        "listing": "국내상장 ETF",
        "ticker": "226490",
        "name": "KODEX 코스피",
        "country": "대한민국",
        "index": "KOSPI",
        "note": "코스피 시장 전체에 가까운 노출",
    },
    {
        "signal_key": "sp500",
        "listing": "국내상장 ETF",
        "ticker": "360750",
        "name": "TIGER 미국S&P500",
        "country": "미국",
        "index": "S&P 500",
        "note": "국내 계좌로 미국 대형주 지수 노출",
    },
    {
        "signal_key": "sp500",
        "listing": "국내상장 ETF",
        "ticker": "379800",
        "name": "KODEX 미국S&P500TR",
        "country": "미국",
        "index": "S&P 500",
        "note": "총수익 지수형 미국 대형주 노출",
    },
    {
        "signal_key": "nasdaq_composite",
        "listing": "국내상장 ETF",
        "ticker": "133690",
        "name": "TIGER 미국나스닥100",
        "country": "미국",
        "index": "NASDAQ 100",
        "note": "나스닥종합의 성장주 흐름을 나스닥100으로 대체 관찰",
    },
    {
        "signal_key": "nasdaq_composite",
        "listing": "국내상장 ETF",
        "ticker": "379810",
        "name": "KODEX 미국나스닥100TR",
        "country": "미국",
        "index": "NASDAQ 100",
        "note": "나스닥종합의 성장주 흐름을 나스닥100으로 대체 관찰",
    },
    {
        "signal_key": "sp500",
        "listing": "미국상장 ETF",
        "ticker": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "country": "미국",
        "index": "S&P 500",
        "note": "미국 대형주 대표지수 추종",
    },
    {
        "signal_key": "sp500",
        "listing": "미국상장 ETF",
        "ticker": "SPY",
        "name": "SPDR S&P 500 ETF Trust",
        "country": "미국",
        "index": "S&P 500",
        "note": "거래량이 큰 미국 대형주 대표 ETF",
    },
    {
        "signal_key": "nasdaq_composite",
        "listing": "미국상장 ETF",
        "ticker": "ONEQ",
        "name": "Fidelity Nasdaq Composite Index ETF",
        "country": "미국",
        "index": "Nasdaq Composite",
        "note": "나스닥종합 지수를 직접 추종하는 ETF",
    },
    {
        "signal_key": "nasdaq_composite",
        "listing": "미국상장 ETF",
        "ticker": "QQQ",
        "name": "Invesco QQQ Trust",
        "country": "미국",
        "index": "NASDAQ 100",
        "note": "나스닥 성장주 대표 ETF, 나스닥종합의 대체 관찰용",
    },
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
    candidates = []

    for candidate in ETF_CANDIDATES:
        item = items.get(candidate["signal_key"])
        if not item or item.get("error"):
            continue

        oneil = item.get("signals", {}).get("oneil", {})
        follow_through = item.get("follow_through")
        if not qualifies_oneil_buy(item, oneil, follow_through):
            continue

        ftd_text = (
            f"{follow_through['date']} FTD"
            if follow_through
            else "FTD 확인 필요"
        )
        candidates.append(
            {
                **candidate,
                "market": item["name"],
                "opinion": oneil.get("opinion", "-"),
                "score": oneil.get("score", 0),
                "basis": (
                    f"{item['name']} 윌리엄 오닐 신호 {oneil.get('opinion', '-')}, "
                    f"{ftd_text}, 활성 분산일 {item.get('distribution_count', 0)}회"
                ),
                "data_source": item.get("data_source", "-"),
                "data_status": item.get("data_status", "-"),
            }
        )

    return sorted(candidates, key=lambda item: (item["listing"], -item["score"], item["ticker"]))


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
