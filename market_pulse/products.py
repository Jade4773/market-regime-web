from __future__ import annotations

import io
import json
import math
import os
import re
import time
import zipfile
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

import pandas as pd
import requests

from market_pulse.data import (
    configured_cache_seconds,
    fetch_yahoo_chart,
    kis_date_range,
    kis_get,
    kis_rows_to_frame,
)


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

KIS_MASTER_BASE_URL = "https://new.real.download.dws.co.kr/common/master"
ETF_SCREENER_VERSION = "kis-universe-v4-liquidity-cache-3h"
ETF_SCREEN_CACHE_SECONDS = configured_cache_seconds("ETF_SCREEN_CACHE_SECONDS")
ETF_PRELIMINARY_LIMIT = int(os.getenv("ETF_PRELIMINARY_LIMIT", "180"))
ETF_FULL_ANALYSIS_LIMIT = int(os.getenv("ETF_FULL_ANALYSIS_LIMIT", "40"))
ETF_SPARK_BATCH_SIZE = int(os.getenv("ETF_SPARK_BATCH_SIZE", "80"))
ETF_SCREEN_MAX_UNIVERSE = int(os.getenv("ETF_SCREEN_MAX_UNIVERSE", "1000"))
ETF_DOMESTIC_MIN_PREV_VOLUME = int(os.getenv("ETF_DOMESTIC_MIN_PREV_VOLUME", "1000"))
ETF_DOMESTIC_MIN_AVG_VALUE = int(os.getenv("ETF_DOMESTIC_MIN_AVG_VALUE", "1000000000"))
ETF_US_MIN_AVG_VALUE = int(os.getenv("ETF_US_MIN_AVG_VALUE", "5000000"))
ETF_MIN_HISTORY_ROWS = 220

_ETF_RECOMMENDATION_CACHE: dict[str, Any] = {}
_ETF_UNIVERSE_CACHE: dict[str, Any] = {}

DOMESTIC_KOSPI_FIELD_SPECS = [
    2, 1, 4, 4, 4,
    1, 1, 1, 1, 1,
    1, 1, 1, 1, 1,
    1, 1, 1, 1, 1,
    1, 1, 1, 1, 1,
    1, 1, 1, 1, 1,
    1, 9, 5, 5, 1,
    1, 1, 2, 1, 1,
    1, 2, 2, 2, 3,
    1, 3, 12, 12, 8,
    15, 21, 2, 7, 1,
    1, 1, 1, 1, 9,
    9, 9, 5, 9, 8,
    9, 3, 1, 1, 1,
]

DOMESTIC_KOSPI_COLUMNS = [
    "그룹코드", "시가총액규모", "지수업종대분류", "지수업종중분류", "지수업종소분류",
    "제조업", "저유동성", "지배구조지수종목", "KOSPI200섹터업종", "KOSPI100",
    "KOSPI50", "KRX", "ETP", "ELW발행", "KRX100",
    "KRX자동차", "KRX반도체", "KRX바이오", "KRX은행", "SPAC",
    "KRX에너지화학", "KRX철강", "단기과열", "KRX미디어통신", "KRX건설",
    "Non1", "KRX증권", "KRX선박", "KRX섹터_보험", "KRX섹터_운송",
    "SRI", "기준가", "매매수량단위", "시간외수량단위", "거래정지",
    "정리매매", "관리종목", "시장경고", "경고예고", "불성실공시",
    "우회상장", "락구분", "액면변경", "증자구분", "증거금비율",
    "신용가능", "신용기간", "전일거래량", "액면가", "상장일자",
    "상장주수", "자본금", "결산월", "공모가", "우선주",
    "공매도과열", "이상급등", "KRX300", "KOSPI", "매출액",
    "영업이익", "경상이익", "당기순이익", "ROE", "기준년월",
    "시가총액", "그룹사코드", "회사신용한도초과", "담보대출가능", "대주가능",
]

OVERSEAS_MASTER_COLUMNS = [
    "National code",
    "Exchange id",
    "Exchange code",
    "Exchange name",
    "Symbol",
    "realtime symbol",
    "Korea name",
    "English name",
    "Security type",
    "currency",
    "float position",
    "data type",
    "base price",
    "Bid order size",
    "Ask order size",
    "market start time",
    "market end time",
    "DR",
    "DR code",
    "industry",
    "index constituent",
    "tick type",
    "ETF type",
    "tick detail",
]

EXCLUDED_ETF_TERMS = [
    "인버스",
    "레버리지",
    "곱버스",
    "선물인버스",
    "2X",
    "3X",
    "4X",
    "-1X",
    "-2X",
    "-3X",
    "BEAR",
    "BULL 2X",
    "BULL 3X",
    "ULTRA",
    "ULTRAPRO",
    "DIREXION DAILY",
    "PROSHARES ULTRA",
    "LEVERAGE SHARES",
]

NON_EQUITY_ETF_TERMS = [
    "채권",
    "국고",
    "회사채",
    "CD금리",
    "머니",
    "단기금리",
    "커버드콜",
    "월배당커버드",
    "BOND",
    "TREASURY",
    "CLO",
    "MONEY MARKET",
    "ULTRA SHORT",
    "COVERED CALL",
    "BUYWRITE",
    "OPTION INCOME",
    "FUTURES",
    "FUTURE",
    "COMMODITY",
    "COMMODITIES",
    "GOLD",
    "SILVER",
    "OIL",
    "NATURAL GAS",
    "TANKER",
    "SHIPPING",
    "FREIGHT",
    "BITCOIN",
    "ETHER",
    "CRYPTO",
    "원유",
    "금선물",
    "은선물",
    "비트코인",
    "가상자산",
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
    category: str | None = None,
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
        "category": category,
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
    etf_candidate(market_group="us", signal_key="nasdaq_composite", listing="미국상장 ETF", ticker="QQQM", yahoo_ticker="QQQM", name="Invesco NASDAQ 100 ETF", country="미국", index="NASDAQ 100", note="나스닥 성장주 핵심 ETF", min_avg_volume=100000),
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


def build_etf_screen_universe() -> list[dict[str, Any]]:
    cached = _ETF_UNIVERSE_CACHE.get("items")
    now = time.time()
    if cached and now - _ETF_UNIVERSE_CACHE.get("created_at", 0) < 24 * 60 * 60:
        return cached

    candidates: list[dict[str, Any]] = []
    try:
        candidates.extend(fetch_kis_domestic_etf_universe())
    except Exception:
        candidates.extend([item for item in ETF_CANDIDATES if item["listing"] == "국내상장 ETF"])

    try:
        candidates.extend(fetch_kis_overseas_etf_universe())
    except Exception:
        candidates.extend([item for item in ETF_CANDIDATES if item["listing"] == "미국상장 ETF"])

    unique = dedupe_etf_candidates(candidates)
    if not unique:
        unique = ETF_CANDIDATES

    _ETF_UNIVERSE_CACHE["items"] = unique
    _ETF_UNIVERSE_CACHE["created_at"] = now
    return unique


def fetch_kis_domestic_etf_universe() -> list[dict[str, Any]]:
    rows = download_zipped_master("kospi_code.mst.zip", "kospi_code.mst").decode("cp949").splitlines()
    candidates = []
    for row in rows:
        part1 = row[:-228]
        part2 = row[-228:]
        code = part1[:9].strip()
        name = part1[21:].strip()
        if not code or not name:
            continue
        details = pd.read_fwf(
            io.StringIO(part2),
            widths=DOMESTIC_KOSPI_FIELD_SPECS,
            names=DOMESTIC_KOSPI_COLUMNS,
        ).iloc[0].to_dict()
        if str(details.get("그룹코드", "")).strip() != "E":
            continue
        if is_excluded_etf_name(name):
            continue

        prev_volume = int_or_zero(details.get("전일거래량"))
        candidates.append(
            etf_candidate(
                market_group=domestic_market_group(name),
                signal_key=domestic_signal_key(name),
                listing="국내상장 ETF",
                ticker=code,
                yahoo_ticker=f"{code}.KS",
                name=name,
                country=infer_investment_country(name),
                index=infer_index_label(name),
                note="한국투자증권 국내 ETF 마스터 기준",
                min_avg_volume=max(1000, min(prev_volume, 100000)),
                category=infer_category_from_text(name),
            )
            | {
                "source_universe": "한국투자증권 국내 종목정보파일",
                "exchange_code": "KRX",
                "prelim_volume": prev_volume,
            }
        )
    return candidates


def fetch_kis_overseas_etf_universe() -> list[dict[str, Any]]:
    candidates = []
    for market_code in ["nas", "nys", "ams"]:
        file_name = f"{market_code.upper()}MST.COD"
        payload = download_zipped_master(f"{market_code}mst.cod.zip", file_name)
        df = pd.read_table(io.BytesIO(payload), sep="\t", encoding="cp949")
        df.columns = OVERSEAS_MASTER_COLUMNS
        filtered = df[
            df["Security type"].astype(str).eq("3")
            & df["ETF type"].astype(str).isin(["001", "005"])
            & df["currency"].astype(str).eq("USD")
        ]
        for _, row in filtered.iterrows():
            symbol = str(row["Symbol"]).strip()
            korean_name = str(row["Korea name"]).strip()
            english_name = str(row["English name"]).strip()
            name = english_name or korean_name or symbol
            if not symbol or is_excluded_etf_name(f"{symbol} {korean_name} {english_name}"):
                continue
            candidates.append(
                etf_candidate(
                    market_group="us",
                    signal_key=overseas_signal_key(name),
                    listing="미국상장 ETF",
                    ticker=symbol,
                    yahoo_ticker=symbol,
                    name=name,
                    country=infer_investment_country(f"{korean_name} {english_name}"),
                    index=infer_index_label(f"{korean_name} {english_name}"),
                    note="한국투자증권 해외 ETF 마스터 기준",
                    min_avg_volume=20000,
                    category=infer_category_from_text(f"{korean_name} {english_name}"),
                )
                | {
                    "source_universe": "한국투자증권 해외 종목정보파일",
                    "exchange_code": str(row["Exchange code"]).strip(),
                    "korean_name": korean_name,
                }
            )
    return candidates


def download_zipped_master(zip_name: str, member_name: str) -> bytes:
    response = requests.get(
        f"{KIS_MASTER_BASE_URL}/{zip_name}",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    response.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    if member_name not in archive.namelist():
        member_name = archive.namelist()[0]
    return archive.read(member_name)


def dedupe_etf_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for candidate in candidates:
        key = (candidate["listing"], candidate["ticker"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def is_excluded_etf_name(text: str) -> bool:
    upper = text.upper()
    return any(term.upper() in upper for term in EXCLUDED_ETF_TERMS)


def domestic_market_group(name: str) -> str:
    upper = name.upper()
    if any(term in upper for term in ["미국", "NASDAQ", "S&P", "필라델피아", "글로벌"]):
        return "us"
    return "korea"


def domestic_signal_key(name: str) -> str:
    upper = name.upper()
    if any(term in upper for term in ["NASDAQ", "나스닥", "반도체", "TECH", "필라델피아"]):
        return "nasdaq_composite"
    if any(term in upper for term in ["S&P", "미국", "글로벌"]):
        return "sp500"
    if "200" in upper:
        return "kospi200"
    return "kospi"


def overseas_signal_key(name: str) -> str:
    upper = name.upper()
    if any(term in upper for term in ["NASDAQ", "SEMICONDUCTOR", "SOFTWARE", "TECH"]):
        return "nasdaq_composite"
    return "sp500"


def infer_investment_country(text: str) -> str:
    upper = text.upper()
    for keyword, country in [
        ("KOREA", "대한민국"),
        ("한국", "대한민국"),
        ("JAPAN", "일본"),
        ("일본", "일본"),
        ("TAIWAN", "대만"),
        ("대만", "대만"),
        ("INDIA", "인도"),
        ("인도", "인도"),
        ("CHINA", "중국"),
        ("중국", "중국"),
        ("MEXICO", "멕시코"),
        ("멕시코", "멕시코"),
        ("EUROPE", "유럽"),
        ("유럽", "유럽"),
        ("GLOBAL", "글로벌"),
        ("글로벌", "글로벌"),
        ("US ", "미국"),
        ("USA", "미국"),
        ("미국", "미국"),
    ]:
        if keyword in upper:
            return country
    return "미국" if re.search(r"\b(S&P|NASDAQ|DOW|RUSSELL)\b", upper) else "글로벌"


def infer_index_label(text: str) -> str:
    upper = text.upper()
    if "NASDAQ" in upper or "나스닥" in upper:
        return "NASDAQ"
    if "S&P" in upper:
        return "S&P 500"
    if "SEMICONDUCTOR" in upper or "반도체" in upper:
        return "Semiconductors"
    if "KOSPI 200" in upper or "200" in upper and "KODEX" in upper:
        return "KOSPI 200"
    if "KOSPI" in upper or "코스피" in upper:
        return "KOSPI"
    if "MSCI" in upper:
        return "MSCI"
    if "RUSSELL" in upper:
        return "Russell"
    return "ETF"


def infer_category_from_text(text: str) -> str:
    upper = text.upper()
    if any(term in upper for term in ["채권", "BOND", "TREASURY", "국고", "회사채", "CLO", "머니", "CD금리"]):
        return "bond"
    if any(term in upper for term in ["SEMICONDUCTOR", "SOFTWARE", "TECH", "반도체", "2차전지", "바이오", "은행"]):
        return "sector"
    if any(term in upper for term in ["MSCI", "JAPAN", "INDIA", "TAIWAN", "CHINA", "KOREA", "일본", "인도", "대만", "중국"]):
        return "country"
    return "broad"


def int_or_zero(value: Any) -> int:
    try:
        if value is None or pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


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
    cache_key = etf_recommendation_cache_key(snapshot)
    cached = _ETF_RECOMMENDATION_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached["created_at"] < ETF_SCREEN_CACHE_SECONDS:
        return cached["items"]

    items = snapshot.get("items", {})
    market_gates = build_market_gates(items)
    universe = build_etf_screen_universe()
    screenable_count = len(select_screenable_etf_universe(universe))
    preliminary_candidates = rank_preliminary_etf_universe(universe)
    full_analysis_targets = preliminary_candidates[:ETF_FULL_ANALYSIS_LIMIT]
    analyzed_candidates = []

    for candidate in full_analysis_targets:
        market_gate = market_gates.get(candidate["market_group"])
        if not market_gate:
            continue
        market_item = market_gate["item"]
        benchmark_item = items.get(candidate["signal_key"]) or market_item
        if benchmark_item.get("error"):
            continue

        analyzed = analyze_etf_candidate(
            candidate,
            market_gate,
            benchmark_item,
        )
        if analyzed:
            analyzed_candidates.append(analyzed)

    ranked = rank_etf_candidates(analyzed_candidates)
    leaders = [
        item
        for item in ranked
        if item["leader_rank"] <= 12
        and item["can_slim_score"] >= 60
        and item["leader_percentile"] >= 65
        and item["components"]["유동성"] > 0
        and item["trading_status"] not in {"SELL", "BROKEN"}
    ]

    selected = sorted(
        leaders,
        key=lambda item: (
            item["action_rank"],
            -item["can_slim_score"],
            item["leader_rank"],
            item["ticker"],
        ),
    )[:2]
    for display_rank, item in enumerate(selected, start=1):
        item["display_rank"] = display_rank
        item["screen_summary"] = {
            "universe_count": len(universe),
            "screenable_count": screenable_count,
            "preliminary_count": len(preliminary_candidates),
            "analyzed_count": len(analyzed_candidates),
            "universe_source": "한국투자증권 종목정보파일",
            "price_source": item.get("data_source", "-"),
        }
    _ETF_RECOMMENDATION_CACHE[cache_key] = {"created_at": now, "items": selected}
    return selected


def etf_recommendation_cache_key(snapshot: dict[str, Any]) -> str:
    items = snapshot.get("items", {})
    parts = [ETF_SCREENER_VERSION]
    for key in sorted(items):
        item = items[key]
        parts.append(
            f"{key}:{item.get('last_date')}:{item.get('regime')}:{item.get('distribution_count')}"
        )
    return "|".join(parts)


def rank_preliminary_etf_universe(universe: list[dict[str, Any]]) -> list[dict[str, Any]]:
    screenable_universe = select_screenable_etf_universe(universe)
    histories = fetch_yahoo_spark_histories([item["yahoo_ticker"] for item in screenable_universe])
    scored = []
    for candidate in screenable_universe:
        series = histories.get(candidate["yahoo_ticker"])
        if series is None or len(series) < 140:
            continue
        prelim = preliminary_etf_metrics(series)
        if not prelim:
            continue
        item = {**candidate, **prelim}
        scored.append(item)

    if not scored:
        return ETF_CANDIDATES

    assign_preliminary_percentiles(scored)
    return sorted(
        scored,
        key=lambda item: (
            -item["preliminary_score"],
            -item["return60_universe_percentile"],
            item["ticker"],
        ),
    )[:ETF_PRELIMINARY_LIMIT]


def select_screenable_etf_universe(universe: list[dict[str, Any]]) -> list[dict[str, Any]]:
    screenable = [item for item in universe if is_screenable_equity_etf(item)]
    return sorted(
        screenable,
        key=lambda item: (
            item["listing"] != "국내상장 ETF",
            -int(item.get("prelim_volume", 0)),
            item["ticker"],
        ),
    )[:ETF_SCREEN_MAX_UNIVERSE]


def is_screenable_equity_etf(candidate: dict[str, Any]) -> bool:
    text = f"{candidate.get('ticker', '')} {candidate.get('name', '')} {candidate.get('korean_name', '')}"
    upper = text.upper()
    if any(term.upper() in upper for term in NON_EQUITY_ETF_TERMS):
        return False
    if candidate.get("category") == "bond":
        return False
    if candidate["listing"] == "국내상장 ETF":
        return int(candidate.get("prelim_volume", 0)) >= ETF_DOMESTIC_MIN_PREV_VOLUME
    return len(candidate["ticker"]) <= 5


def fetch_yahoo_spark_histories(symbols: list[str]) -> dict[str, pd.Series]:
    histories: dict[str, pd.Series] = {}
    unique_symbols = list(dict.fromkeys(symbol for symbol in symbols if symbol))
    for start in range(0, len(unique_symbols), ETF_SPARK_BATCH_SIZE):
        batch = unique_symbols[start : start + ETF_SPARK_BATCH_SIZE]
        histories.update(fetch_yahoo_spark_batch(batch))
    return histories


def fetch_yahoo_spark_batch(symbols: list[str]) -> dict[str, pd.Series]:
    if not symbols:
        return {}
    try:
        response = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/spark",
            params={
                "symbols": ",".join(symbols),
                "range": "18mo",
                "interval": "1d",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return split_spark_batch(symbols)

    histories: dict[str, pd.Series] = {}
    for symbol in symbols:
        data = payload.get(symbol) or {}
        timestamps = data.get("timestamp") or []
        closes = data.get("close") or []
        if not timestamps or not closes:
            continue
        frame = pd.DataFrame(
            {"Close": closes},
            index=[
                datetime.fromtimestamp(ts, tz=timezone.utc).date()
                for ts in timestamps
            ],
        )
        frame.index = pd.to_datetime(frame.index)
        series = frame["Close"].dropna().sort_index()
        if len(series) >= 140:
            histories[symbol] = series
    if not histories and len(symbols) > 1:
        return split_spark_batch(symbols)
    return histories


def split_spark_batch(symbols: list[str]) -> dict[str, pd.Series]:
    if len(symbols) <= 1:
        return {}
    midpoint = len(symbols) // 2
    histories = fetch_yahoo_spark_batch(symbols[:midpoint])
    histories.update(fetch_yahoo_spark_batch(symbols[midpoint:]))
    return histories


def preliminary_etf_metrics(close: pd.Series) -> dict[str, Any] | None:
    if len(close) < 140:
        return None
    latest = float(close.iloc[-1])
    ma21 = float(close.ewm(span=21, adjust=False).mean().iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    high120 = float(close.rolling(120).max().iloc[-1])
    return20 = pct(latest, close.iloc[-21])
    return60 = pct(latest, close.iloc[-61])
    return120 = pct(latest, close.iloc[-121])
    near_high = pct(latest, high120)
    trend_bonus = 0
    if latest > ma21:
        trend_bonus += 8
    if latest > ma50:
        trend_bonus += 10
    if ma200 and latest > ma200:
        trend_bonus += 5
    preliminary_score = return20 * 0.35 + return60 * 0.45 + return120 * 0.20 + trend_bonus
    if near_high >= -5:
        preliminary_score += 8
    elif near_high >= -10:
        preliminary_score += 4
    return {
        "prelim_last_price": latest,
        "prelim_ma50": ma50,
        "prelim_return20": return20,
        "prelim_return60": return60,
        "prelim_return120": return120,
        "preliminary_score": preliminary_score,
    }


def assign_preliminary_percentiles(candidates: list[dict[str, Any]]) -> None:
    for source_key, target_key in [
        ("prelim_return20", "return20_universe_percentile"),
        ("prelim_return60", "return60_universe_percentile"),
        ("prelim_return120", "return120_universe_percentile"),
    ]:
        values = sorted(item[source_key] for item in candidates)
        total = len(values)
        for item in candidates:
            item[target_key] = percentile_rank(values, item[source_key], total)


def build_etf_market_summary(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    gates = build_market_gates(snapshot.get("items", {}))
    return [
        summarize_market_gate("미국 시장", gates.get("us")),
        summarize_market_gate("한국 시장", gates.get("korea")),
    ]


def summarize_market_gate(label: str, gate: dict[str, Any] | None) -> dict[str, Any]:
    if not gate:
        return {
            "label": label,
            "state": "MARKET_CORRECTION",
            "state_label": "관망",
            "ftd": "-",
            "distribution_count": "-",
            "nasdaq_position": "-",
        }

    item = gate["item"]
    trend_metrics = item.get("signals", {}).get("trend", {}).get("metrics", {})
    follow_through = item.get("follow_through") or {}
    return {
        "label": label,
        "state": gate["state"],
        "state_label": gate["state_label"],
        "ftd": follow_through.get("date", "최근 FTD 없음"),
        "distribution_count": item.get("distribution_count", 0),
        "nasdaq_position": (
            "50일선 위"
            if numeric_or_zero(trend_metrics.get("50일선")) < numeric_or_zero(item.get("close"))
            else "50일선 아래/확인 필요"
        ),
    }


def build_market_gates(items: dict[str, Any]) -> dict[str, dict[str, Any]]:
    gates = {}
    korea = best_market_gate(items, ["kospi200", "kospi"])
    united_states = best_market_gate(items, ["nasdaq_composite", "sp500"])
    if korea:
        gates["korea"] = korea
    if united_states:
        gates["us"] = united_states
    return gates


def best_market_gate(items: dict[str, Any], keys: list[str]) -> dict[str, Any] | None:
    valid = []
    for key in keys:
        item = items.get(key)
        if not item or item.get("error"):
            continue
        oneil = item.get("signals", {}).get("oneil", {})
        follow_through = item.get("follow_through")
        state, score, label = market_state(item, oneil, follow_through)
        valid.append({"item": item, "state": state, "score": score, "state_label": label})
    if not valid:
        return None
    return sorted(
        valid,
        key=lambda gate: (
            -gate["score"],
            gate["item"].get("distribution_count", 99),
            gate["item"].get("name", ""),
        ),
    )[0]


def market_state(
    item: dict[str, Any],
    oneil: dict[str, Any],
    follow_through: dict[str, Any] | None,
) -> tuple[str, int, str]:
    if not follow_through or not follow_through.get("is_active"):
        return "MARKET_CORRECTION", 0, "조정장"
    if oneil.get("opinion") == "매도/방어" or item.get("distribution_count", 0) >= 6:
        return "MARKET_CORRECTION", 0, "조정장"
    if item.get("distribution_count", 0) >= 3 or oneil.get("opinion") == "주의":
        return "UPTREND_UNDER_PRESSURE", 10, "상승장 압박"
    return "CONFIRMED_UPTREND", 20, "상승장 확인"


def rank_etf_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []

    assign_relative_strength_components(candidates)
    for item in candidates:
        finalize_etf_candidate(item)

    ranked = sorted(
        candidates,
        key=lambda item: (
            -item["leader_percentile"],
            -item["can_slim_score"],
            item["action_rank"],
            item["ticker"],
        ),
    )
    for rank, item in enumerate(ranked, start=1):
        item["leader_rank"] = rank
        item["leader_label"] = leader_label(item)
    return ranked


def assign_relative_strength_components(candidates: list[dict[str, Any]]) -> None:
    for period_key, score_key, max_points in [
        ("return20", "20일 상대강도", 10),
        ("return60", "60일 상대강도", 12),
        ("return120", "120일 상대강도", 8),
    ]:
        values = sorted(item[period_key] for item in candidates)
        total = len(values)
        for item in candidates:
            universe_key = f"{period_key}_universe_percentile"
            percentile = int(item.get(universe_key) or percentile_rank(values, item[period_key], total))
            item[f"{period_key}_percentile"] = percentile
            item["components"][score_key] = round(percentile / 99 * max_points)


def percentile_rank(values: list[float], value: float, total: int) -> int:
    if total <= 1:
        return 99
    weaker_or_equal = sum(1 for candidate_value in values if candidate_value <= value)
    return round(weaker_or_equal / total * 99)


def finalize_etf_candidate(item: dict[str, Any]) -> None:
    rs_score = (
        item["components"]["20일 상대강도"]
        + item["components"]["60일 상대강도"]
        + item["components"]["120일 상대강도"]
    )
    item["relative_strength_score"] = rs_score
    item["leader_percentile"] = round(
        item["return20_percentile"] * 0.35
        + item["return60_percentile"] * 0.40
        + item["return120_percentile"] * 0.25
    )
    item["components"]["L 상대강도"] = rs_score
    item["components"]["추세"] = trend_score(item)
    item["components"]["베이스/피봇"] = base_pivot_score(item)
    item["components"]["유동성"] = liquidity_score(item)
    item["can_slim_score"] = (
        item["components"]["M 시장 방향"]
        + item["components"]["L 상대강도"]
        + item["components"]["추세"]
        + item["components"]["베이스/피봇"]
        + item["components"]["유동성"]
    )
    trading_status, action, action_rank = etf_trading_status(item)
    item["trading_status"] = trading_status
    item["action"] = action
    item["action_rank"] = action_rank
    item["sell_signal"] = current_sell_signal(item)
    item["positive_reasons"], item["risk_signals"] = etf_reasons(item)


def leader_label(item: dict[str, Any]) -> str:
    if item["trading_status"] in {"SELL", "BROKEN"}:
        return "방어"
    if item["trading_status"] == "BUY_READY":
        return "매수준비"
    if item["trading_status"] == "PIVOT_APPROACH":
        return "피봇 접근"
    if item["leader_rank"] <= 5 and item["leader_percentile"] >= 75:
        return "주도 ETF"
    if item["leader_rank"] <= 8:
        return "주도 후보"
    return item["action"]


def analyze_etf_candidate(
    candidate: dict[str, Any],
    market_gate: dict[str, Any],
    benchmark_item: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        history, history_source = fetch_sufficient_etf_history(candidate)
        df = prepare_etf_history(history)
    except Exception:
        return None
    if len(df) < ETF_MIN_HISTORY_ROWS:
        return None

    market_item = market_gate["item"]
    latest = df.iloc[-1]
    previous = df.iloc[-2]
    close = float(latest["Close"])
    ma21 = float(latest["ema21"]) if pd.notna(latest["ema21"]) else None
    ma50 = float(latest["ma50"]) if pd.notna(latest["ma50"]) else None
    ma200 = float(latest["ma200"]) if pd.notna(latest["ma200"]) else None
    ma50_slope = float(latest["ma50_slope20"]) if pd.notna(latest["ma50_slope20"]) else 0.0
    base = detect_flat_base(df)
    pivot = base.get("pivot")
    pivot_distance_pct = pct(close, pivot) if pivot else None
    avg_volume20 = float(latest["avg_volume20"]) if pd.notna(latest["avg_volume20"]) else 0.0
    avg_volume50 = float(latest["avg_volume50"]) if pd.notna(latest["avg_volume50"]) else 0.0
    avg_value50 = float(latest["avg_value50"]) if pd.notna(latest["avg_value50"]) else 0.0
    volume_ratio = float(latest["Volume"] / avg_volume20) if avg_volume20 else 0.0
    volume_change = pct(latest["Volume"], previous["Volume"])
    return20 = float(latest["return20"]) if pd.notna(latest["return20"]) else 0.0
    return60 = float(latest["return60"]) if pd.notna(latest["return60"]) else 0.0
    return120 = float(latest["return120"]) if pd.notna(latest["return120"]) else 0.0
    distance_high252 = (
        float(latest["distance_high252"]) if pd.notna(latest["distance_high252"]) else None
    )

    benchmark_metrics = benchmark_item.get("signals", {}).get("trend", {}).get("metrics", {})
    benchmark_return60 = numeric_or_zero(benchmark_metrics.get("3개월 수익률"))
    benchmark_return120 = numeric_or_zero(benchmark_metrics.get("6개월 수익률"))
    follow_through = market_item.get("follow_through")
    ftd_text = f"{follow_through['date']} FTD" if follow_through else "FTD 확인 필요"
    buy_high = pivot * 1.05 if pivot else None
    return {
        **candidate,
        "category": candidate.get("category") or infer_etf_category(candidate),
        "market": market_item["name"],
        "benchmark_market": benchmark_item["name"],
        "market_state": market_gate["state"],
        "market_state_label": market_gate["state_label"],
        "opinion": market_item.get("signals", {}).get("oneil", {}).get("opinion", "-"),
        "can_slim_score": 0,
        "components": {"M 시장 방향": market_gate["score"]},
        "action": "관찰",
        "trading_status": "WATCH",
        "action_rank": 9,
        "last_price": close,
        "change_pct": float(latest["pct_change"]) if pd.notna(latest["pct_change"]) else 0.0,
        "return20": return20,
        "return60": return60,
        "return120": return120,
        "rs_vs_market60": return60 - benchmark_return60,
        "rs_vs_market120": return120 - benchmark_return120,
        "relative_strength_score": 0,
        "leader_percentile": 0,
        "leader_rank": 999,
        "leader_label": "관찰",
        "ma21": ma21,
        "ma50": ma50,
        "ma200": ma200,
        "ma50_slope": ma50_slope,
        "pivot": pivot,
        "pivot_distance_pct": pivot_distance_pct,
        "buy_low": pivot,
        "buy_high": buy_high,
        "stop_loss": pivot * 0.92 if pivot else None,
        "profit_low": pivot * 1.20 if pivot else None,
        "profit_high": pivot * 1.25 if pivot else None,
        "base_exists": base["base_exists"],
        "base_days": base["base_days"],
        "base_depth_pct": base["base_depth_pct"],
        "near_pivot": pivot_distance_pct is not None and -5 <= pivot_distance_pct <= 5,
        "breakout": pivot_distance_pct is not None and pivot_distance_pct >= 0,
        "volume_ratio": volume_ratio,
        "avg_volume20": avg_volume20,
        "avg_volume50": avg_volume50,
        "avg_value50": avg_value50,
        "min_avg_value": min_avg_value_for_etf(candidate),
        "volume_change_pct": volume_change,
        "sell_signal": "관찰",
        "basis": (
            f"{market_item['name']} {market_gate['state_label']}, {ftd_text}, "
            f"활성 분산일 {market_item.get('distribution_count', 0)}회, "
            f"{benchmark_item['name']} 대비 60일 초과수익 {return60 - benchmark_return60:+.2f}%"
        ),
        "data_source": history_source,
        "data_status": market_item.get("data_status", "-"),
    }


def fetch_sufficient_etf_history(candidate: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    history, history_source = fetch_etf_history(candidate)
    if len(history) >= ETF_MIN_HISTORY_ROWS or history_source.startswith("Yahoo"):
        return history, history_source

    try:
        fallback = fetch_yahoo_chart(candidate["yahoo_ticker"])
    except Exception:
        return history, history_source

    if len(fallback) > len(history):
        return fallback, "Yahoo Finance ETF 가격"
    return history, history_source


def fetch_etf_history(candidate: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    try:
        if candidate["listing"] == "국내상장 ETF":
            return fetch_kis_domestic_etf_chart(candidate["ticker"]), "한국투자증권 ETF 일봉"
        if candidate["listing"] == "미국상장 ETF":
            return fetch_kis_overseas_etf_chart(
                candidate["ticker"],
                candidate.get("exchange_code", ""),
            ), "한국투자증권 해외 ETF 일봉"
    except Exception:
        pass
    return fetch_yahoo_chart(candidate["yahoo_ticker"]), "Yahoo Finance ETF 가격"


def fetch_kis_domestic_etf_chart(code: str) -> pd.DataFrame:
    start_date, end_date = kis_date_range()
    rows = kis_paginated_rows_for_etf(
        path="/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
        tr_id="FHKST03010100",
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        },
    )
    return kis_rows_to_frame(
        rows,
        date_key="stck_bsop_date",
        open_key="stck_oprc",
        high_key="stck_hgpr",
        low_key="stck_lwpr",
        close_key="stck_clpr",
        volume_key="acml_vol",
        value_key="acml_tr_pbmn",
        source="한국투자증권",
        volume_source="한국투자증권 ETF 거래량",
    )


def fetch_kis_overseas_etf_chart(symbol: str, exchange_code: str) -> pd.DataFrame:
    exchange = normalize_kis_overseas_exchange(exchange_code)
    payload, _ = kis_get(
        "/uapi/overseas-price/v1/quotations/dailyprice",
        "HHDFS76240000",
        {
            "AUTH": "",
            "EXCD": exchange,
            "SYMB": symbol,
            "GUBN": "0",
            "BYMD": "",
            "MODP": "0",
        },
    )
    rows = payload.get("output2") or payload.get("output") or []
    if isinstance(rows, dict):
        rows = [rows]
    return flexible_rows_to_frame(
        rows,
        date_keys=["xymd", "stck_bsop_date", "ovrs_bsop_date"],
        open_keys=["open", "ovrs_prod_oprc", "stck_oprc"],
        high_keys=["high", "ovrs_prod_hgpr", "stck_hgpr"],
        low_keys=["low", "ovrs_prod_lwpr", "stck_lwpr"],
        close_keys=["clos", "last", "ovrs_nmix_prpr", "stck_clpr"],
        volume_keys=["tvol", "acml_vol", "evol"],
        source="한국투자증권",
        volume_source="한국투자증권 해외 ETF 거래량",
    )


def kis_paginated_rows_for_etf(
    path: str,
    tr_id: str,
    params: dict[str, str],
    max_depth: int = 8,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    tr_cont = ""
    for _ in range(max_depth):
        payload, next_cont = kis_get(path, tr_id, params, tr_cont)
        chunk = payload.get("output2") or payload.get("output") or []
        if isinstance(chunk, dict):
            chunk = [chunk]
        rows.extend(chunk)
        if next_cont not in {"M", "F"}:
            break
        tr_cont = "N"
        time.sleep(0.1)
    return rows


def normalize_kis_overseas_exchange(exchange_code: str) -> str:
    upper = (exchange_code or "").upper()
    if upper in {"NAS", "NASD", "NASDAQ"}:
        return "NAS"
    if upper in {"NYS", "NYSE"}:
        return "NYS"
    if upper in {"AMS", "AMEX", "ASE"}:
        return "AMS"
    return upper or "NAS"


def flexible_rows_to_frame(
    rows: list[dict[str, Any]],
    *,
    date_keys: list[str],
    open_keys: list[str],
    high_keys: list[str],
    low_keys: list[str],
    close_keys: list[str],
    volume_keys: list[str],
    source: str,
    volume_source: str,
) -> pd.DataFrame:
    normalized = []
    for row in rows:
        date = first_row_value(row, date_keys)
        close = numeric_or_none(first_row_value(row, close_keys))
        if not date or close is None:
            continue
        volume = numeric_or_none(first_row_value(row, volume_keys)) or 0
        normalized.append(
            {
                "date": date,
                "Open": numeric_or_none(first_row_value(row, open_keys)) or close,
                "High": numeric_or_none(first_row_value(row, high_keys)) or close,
                "Low": numeric_or_none(first_row_value(row, low_keys)) or close,
                "Close": close,
                "Volume": volume,
                "Value": close * volume,
            }
        )
    if not normalized:
        return pd.DataFrame()
    df = pd.DataFrame(normalized)
    df.index = pd.to_datetime(df.pop("date"), format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["Close"]).sort_index().copy()
    df["DataSource"] = source
    df["DataStatus"] = "마감 기준"
    df["SourceNote"] = "한국투자증권 Open API 기준"
    df["VolumeSource"] = volume_source
    return df


def first_row_value(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return None


def numeric_or_none(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def prepare_etf_history(history: pd.DataFrame) -> pd.DataFrame:
    df = history.sort_index().copy()
    if "Value" not in df.columns or df["Value"].isna().all():
        df["Value"] = df["Close"] * df["Volume"]
    df["pct_change"] = df["Close"].pct_change() * 100
    df["ema21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["ma20"] = df["Close"].rolling(20).mean()
    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma200"] = df["Close"].rolling(200).mean()
    df["ma50_slope20"] = df["ma50"].pct_change(20) * 100
    df["avg_volume20"] = df["Volume"].rolling(20).mean()
    df["avg_volume50"] = df["Volume"].rolling(50).mean()
    df["avg_value20"] = df["Value"].rolling(20).mean()
    df["avg_value50"] = df["Value"].rolling(50).mean()
    df["return20"] = df["Close"].pct_change(20) * 100
    df["return60"] = df["Close"].pct_change(60) * 100
    df["return120"] = df["Close"].pct_change(120) * 100
    df["return252"] = df["Close"].pct_change(252) * 100
    df["high252"] = df["Close"].rolling(252).max()
    df["distance_high252"] = (df["Close"] / df["high252"] - 1) * 100
    return df


def detect_flat_base(df: pd.DataFrame) -> dict[str, Any]:
    base_days = 25
    window = df.iloc[-base_days - 1 : -1]
    if len(window) < base_days:
        return {"base_exists": False, "base_days": base_days, "base_depth_pct": None, "pivot": None}

    base_high = float(window["High"].max())
    base_low = float(window["Low"].min())
    latest = df.iloc[-1]
    close = float(latest["Close"])
    ma50 = float(latest["ma50"]) if pd.notna(latest["ma50"]) else None
    base_depth_pct = (base_high / base_low - 1) * 100 if base_low else None
    upper_half = close >= base_low + (base_high - base_low) * 0.5
    near_50ma = ma50 is not None and close >= ma50 * 0.97
    volatility_contracting = volatility_is_contracting(df)
    base_exists = bool(
        base_depth_pct is not None
        and base_depth_pct <= 15
        and near_50ma
        and upper_half
        and volatility_contracting
    )
    return {
        "base_exists": base_exists,
        "base_days": base_days,
        "base_depth_pct": base_depth_pct,
        "pivot": base_high,
    }


def volatility_is_contracting(df: pd.DataFrame) -> bool:
    ranges = ((df["High"] - df["Low"]) / df["Close"]).dropna()
    if len(ranges) < 45:
        return True
    recent = ranges.iloc[-10:].mean()
    previous = ranges.iloc[-35:-10].mean()
    return bool(recent <= previous * 1.15)


def trend_score(item: dict[str, Any]) -> int:
    score = 0
    if item["ma21"] and item["last_price"] > item["ma21"]:
        score += 6
    if item["ma50"] and item["last_price"] > item["ma50"]:
        score += 7
    if item["ma50_slope"] > 0:
        score += 4
    if item["ma200"] and item["last_price"] > item["ma200"]:
        score += 3
    return score


def base_pivot_score(item: dict[str, Any]) -> int:
    score = 0
    if item["base_exists"]:
        score += 5
    if item["base_days"] >= 25:
        score += 4
    if item["base_depth_pct"] is not None and item["base_depth_pct"] <= 15:
        score += 4
    if item["pivot_distance_pct"] is not None and item["pivot_distance_pct"] >= -5:
        score += 4
    if item["breakout"]:
        score += 4
    if item["breakout"] and item["volume_ratio"] >= 1.4:
        score += 4
    return score


def liquidity_score(item: dict[str, Any]) -> int:
    min_volume = float(item.get("min_avg_volume", 0))
    min_value = float(item.get("min_avg_value", 0))
    if min_volume <= 0 or min_value <= 0:
        return 0
    volume_ok = item["avg_volume50"] >= min_volume
    value_ok = item["avg_value50"] >= min_value
    if item["avg_volume50"] >= min_volume * 3 and item["avg_value50"] >= min_value * 3:
        return 5
    if volume_ok and value_ok:
        return 3
    return 0


def min_avg_value_for_etf(candidate: dict[str, Any]) -> int:
    if candidate["listing"] == "국내상장 ETF":
        return ETF_DOMESTIC_MIN_AVG_VALUE
    return ETF_US_MIN_AVG_VALUE


def etf_trading_status(item: dict[str, Any]) -> tuple[str, str, int]:
    close = item["last_price"]
    pivot = item["pivot"]
    ma50 = item["ma50"]
    ma21 = item["ma21"]
    pivot_distance = item["pivot_distance_pct"]
    market_state_value = item["market_state"]
    heavy_volume = item["volume_ratio"] >= 1.2

    if market_state_value == "MARKET_CORRECTION":
        return "MARKET_WAIT", "관망", 8
    if ma50 and close < ma50:
        return "BROKEN", "매수금지", 7
    if not item["base_exists"] or not pivot:
        return "NO_VALID_BASE", "관찰", 6
    if pivot_distance is not None and pivot_distance < -5:
        return "FAR_FROM_PIVOT", "피봇 대기", 5
    if pivot_distance is not None and -5 <= pivot_distance < 0:
        return "PIVOT_APPROACH", "피봇 접근", 2
    if pivot_distance is not None and 0 <= pivot_distance <= 5:
        if item["volume_ratio"] >= 1.4 and market_state_value == "CONFIRMED_UPTREND":
            return "BUY_READY", "매수준비", 1
        return "BREAKOUT_NEEDS_VOLUME", "거래량 확인", 3
    if pivot_distance is not None and pivot_distance > 5:
        if ma21 and close > ma21:
            return "HOLD", "보유/추격금지", 4
        if heavy_volume:
            return "SELL_WARNING", "매도주의", 4
        return "EXTENDED", "추격금지", 5
    return "WATCH", "관찰", 6


def current_sell_signal(item: dict[str, Any]) -> str:
    close = item["last_price"]
    pivot = item["pivot"]
    ma21 = item["ma21"]
    ma50 = item["ma50"]
    if item["market_state"] == "MARKET_CORRECTION":
        return "시장 조정장: 신규 매수 보류"
    if pivot and close <= pivot * 0.92:
        return "피봇 대비 -8% 손절선 이탈"
    if ma50 and close < ma50 and item["volume_ratio"] >= 1.0:
        return "거래량 동반 50일선 이탈"
    if ma21 and close < ma21 and item["volume_ratio"] >= 1.2:
        return "21EMA 대량거래 이탈: 일부 방어"
    if item["market_state"] == "UPTREND_UNDER_PRESSURE":
        return "시장 분산일 누적: 신규 매수 축소"
    if item["category"] != "broad" and pivot and close >= pivot * 1.20:
        return "섹터/테마 ETF 20~25% 이익보호 구간"
    return "특별한 매도 신호 없음"


def etf_reasons(item: dict[str, Any]) -> tuple[list[str], list[str]]:
    positives = []
    risks = []
    if item["market_state"] == "CONFIRMED_UPTREND":
        positives.append("시장 FTD가 유지되어 ETF 탐색이 허용됩니다.")
    elif item["market_state"] == "UPTREND_UNDER_PRESSURE":
        risks.append("시장 상승장은 유지되지만 분산일 부담이 있습니다.")
    else:
        risks.append("시장 조정장으로 신규 매수는 보류합니다.")

    positives.append(f"후보군 내 상대강도 백분위 {item['leader_percentile']}입니다.")
    if item["last_price"] > (item["ma21"] or float("inf")) and item["last_price"] > (item["ma50"] or float("inf")):
        positives.append("현재 가격이 21EMA와 50일선 위에 있습니다.")
    if item["base_exists"]:
        positives.append(f"{item['base_days']}거래일 베이스 깊이가 {item['base_depth_pct']:.2f}%입니다.")
    else:
        risks.append("문서 기준의 유효 베이스가 아직 확인되지 않았습니다.")
    if item["pivot_distance_pct"] is not None:
        if item["pivot_distance_pct"] < -5:
            risks.append(f"피봇까지 {abs(item['pivot_distance_pct']):.2f}% 남아 있어 선취매 구간입니다.")
        elif item["pivot_distance_pct"] > 5:
            risks.append(f"피봇보다 {item['pivot_distance_pct']:.2f}% 높아 추격금지 구간입니다.")
    if item["breakout"] and item["volume_ratio"] < 1.4:
        risks.append(f"돌파는 보이지만 거래량 비율이 {item['volume_ratio']:.2f}배로 강한 확인에는 부족합니다.")
    if item["avg_volume50"] < float(item.get("min_avg_volume", 0)):
        risks.append("50일 평균 거래량이 최소 유동성 기준보다 낮습니다.")
    if item["avg_value50"] < float(item.get("min_avg_value", 0)):
        risks.append("50일 평균 거래대금이 최소 유동성 기준보다 낮습니다.")
    if not risks:
        risks.append("주요 위험 신호는 제한적입니다.")
    return positives[:4], risks[:4]


def infer_etf_category(candidate: dict[str, Any]) -> str:
    text = f"{candidate.get('index', '')} {candidate.get('note', '')}".lower()
    sector_words = [
        "semiconductor",
        "software",
        "technology",
        "communication",
        "consumer",
        "financial",
        "industrial",
        "energy",
        "health",
        "반도체",
        "2차전지",
        "섹터",
        "테마",
    ]
    if "msci" in text and candidate.get("ticker") not in {"SPY", "VOO"}:
        return "country"
    if any(word in text for word in sector_words):
        return "sector"
    return "broad"


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
