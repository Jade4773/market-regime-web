from __future__ import annotations

import io
import json
import math
import os
import re
import time
import zipfile
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any
import xml.etree.ElementTree as ET

import pandas as pd
import requests

requests.packages.urllib3.disable_warnings()

from market_pulse.data import (
    configured_cache_seconds,
    fetch_yahoo_chart,
    kis_date_range,
    kis_get,
    kis_rows_to_frame,
)


KOFIA_ELS_PAGE_URL = (
    "https://dis.kofia.or.kr/websquare/index.jsp?"
    "w2xPath=/wq/etcann/DISDLSSubscribing.xml"
    "&divisionId=MDIS04007001000000&serviceId=SDIS04007001000"
)
KOFIA_ELS_SERVICE_URL = "https://dis.kofia.or.kr/proframeWeb/XMLSERVICES/"
KOFIA_DISCLOSURE_HOME_URL = "https://dis.kofia.or.kr/"
MIRAE_ELS_SEARCH_URL = "https://securities.miraeasset.com/hks/hks4023/n01.do?bbsCode=dls"
MIRAE_ELS_AJAX_URL = "https://securities.miraeasset.com/hks/hks4022/a01.json"
MIRAE_ELS_NOTICE_URL = "https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=7"
HMSEC_ELS_URL = "https://www.hmsec.com/goMenu.do?scr_menu_id=PD030803"
DAISHIN_ELS_URL = "https://m.daishin.com/g.ds?m=1012&p=1647&v=1127"
DART_DERIVATIVE_URL = "https://dart.fss.or.kr/dsab007/main.do"

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
ETF_SCREENER_VERSION = "kis-universe-v5-exit-strategy"
ETF_SCREEN_CACHE_SECONDS = configured_cache_seconds("ETF_SCREEN_CACHE_SECONDS")
ETF_PRELIMINARY_LIMIT = int(os.getenv("ETF_PRELIMINARY_LIMIT", "180"))
ETF_FULL_ANALYSIS_LIMIT = int(os.getenv("ETF_FULL_ANALYSIS_LIMIT", "40"))
ETF_SPARK_BATCH_SIZE = int(os.getenv("ETF_SPARK_BATCH_SIZE", "80"))
ETF_SCREEN_MAX_UNIVERSE = int(os.getenv("ETF_SCREEN_MAX_UNIVERSE", "1000"))
ETF_DOMESTIC_MIN_PREV_VOLUME = int(os.getenv("ETF_DOMESTIC_MIN_PREV_VOLUME", "1000"))
ETF_DOMESTIC_MIN_AVG_VALUE = int(os.getenv("ETF_DOMESTIC_MIN_AVG_VALUE", "1000000000"))
ETF_US_MIN_AVG_VALUE = int(os.getenv("ETF_US_MIN_AVG_VALUE", "5000000"))
ETF_MIN_HISTORY_ROWS = 220
ETF_VOLUME_THRESHOLD = float(os.getenv("ETF_VOLUME_THRESHOLD", "1.4"))
ETF_BUY_ZONE_MAX_PCT = float(os.getenv("ETF_BUY_ZONE_MAX_PCT", "5"))
ETF_STOP_LOSS_PCT = float(os.getenv("ETF_STOP_LOSS_PCT", "6"))
ETF_PYRAMID2_MIN_PCT = float(os.getenv("ETF_PYRAMID2_MIN_PCT", "2.0"))
ETF_PYRAMID2_MAX_PCT = float(os.getenv("ETF_PYRAMID2_MAX_PCT", "2.5"))
ETF_PYRAMID3_MIN_PCT = float(os.getenv("ETF_PYRAMID3_MIN_PCT", "4.0"))
ETF_PYRAMID3_MAX_PCT = float(os.getenv("ETF_PYRAMID3_MAX_PCT", "5.0"))
ETF_HIGH_VOLUME_RATIO = float(os.getenv("ETF_HIGH_VOLUME_RATIO", "1.2"))
ETF_STRONG_VOLUME_RATIO = float(os.getenv("ETF_STRONG_VOLUME_RATIO", "1.4"))
ETF_PROFIT_ZONE_START_PCT = float(os.getenv("ETF_PROFIT_ZONE_START_PCT", "20"))
ETF_PROFIT_ZONE_END_PCT = float(os.getenv("ETF_PROFIT_ZONE_END_PCT", "25"))
ETF_ROUND_TRIP_TRIGGER_GAIN_PCT = float(os.getenv("ETF_ROUND_TRIP_TRIGGER_GAIN_PCT", "10"))
ETF_ROUND_TRIP_REMAINING_GAIN_PCT = float(os.getenv("ETF_ROUND_TRIP_REMAINING_GAIN_PCT", "2"))
ETF_FAST_LEADER_GAIN_PCT = float(os.getenv("ETF_FAST_LEADER_GAIN_PCT", "20"))
ETF_FAST_LEADER_SESSIONS = int(os.getenv("ETF_FAST_LEADER_SESSIONS", "15"))
ETF_RS_WEAKENING_DAYS = int(os.getenv("ETF_RS_WEAKENING_DAYS", "5"))
ETF_FAILED_BREAKOUT_SESSIONS = int(os.getenv("ETF_FAILED_BREAKOUT_SESSIONS", "5"))
ETF_BUY_READY_LIMIT = int(os.getenv("ETF_BUY_READY_LIMIT", "5"))
ETF_WATCHLIST_LIMIT = int(os.getenv("ETF_WATCHLIST_LIMIT", "2"))
ETF_HOLDING_LOOKBACK_SESSIONS = int(os.getenv("ETF_HOLDING_LOOKBACK_SESSIONS", "40"))
ETF_HOLDING_DISPLAY_LIMIT = int(os.getenv("ETF_HOLDING_DISPLAY_LIMIT", "12"))
ELS_TOP_LIMIT = int(os.getenv("ELS_TOP_LIMIT", "5"))
ELS_MAX_PER_ISSUER = int(os.getenv("ELS_MAX_PER_ISSUER", "2"))

ETF_STATUS_PRIORITY = {
    "DATA_INCOMPLETE": 0,
    "MARKET_NOT_CONFIRMED": 1,
    "LIQUIDITY_FAIL": 2,
    "BELOW_50SMA": 3,
    "NO_VALID_BASE": 4,
    "NO_VALID_PIVOT": 5,
    "EXTENDED": 6,
    "PIVOT_APPROACH": 7,
    "VOLUME_CONFIRM": 8,
    "BUY_READY": 9,
}

ETF_ACTION_LABELS = {
    "BUY_READY": "현재 매수 가능",
    "VOLUME_CONFIRM": "거래량 확인 대기",
    "PIVOT_APPROACH": "피봇 접근 관찰",
    "NO_VALID_BASE": "베이스 형성 관찰",
    "NO_VALID_PIVOT": "피봇 재산출 대기",
    "EXTENDED": "추격 매수 금지",
    "BELOW_50SMA": "회복 대기",
    "MARKET_NOT_CONFIRMED": "신규 매수 보류",
    "LIQUIDITY_FAIL": "유동성 기준 미달",
    "DATA_INCOMPLETE": "데이터 부족",
}

ETF_REASON_LABELS = {
    "DATA_INCOMPLETE": "가격·거래량 또는 피봇 계산 데이터가 부족합니다.",
    "MARKET_NOT_CONFIRMED": "기준 시장이 확정 상승장 상태가 아닙니다.",
    "LIQUIDITY_FAIL": "50일 평균 거래량 또는 거래대금이 최소 기준에 미달합니다.",
    "BELOW_50SMA": "현재 가격이 50일선 위에 있고 50일선이 상승해야 하는 필터를 통과하지 못했습니다.",
    "NO_VALID_BASE": "유효 베이스가 아직 확인되지 않았습니다.",
    "NO_VALID_PIVOT": "신뢰할 피봇 가격을 산출하지 못했습니다.",
    "ABOVE_BUY_ZONE": "피봇 대비 +5% 매수구간을 넘어 추격 매수 구간입니다.",
    "BELOW_PIVOT": "아직 피봇을 돌파하지 않았습니다.",
    "FAR_FROM_PIVOT": "피봇까지 5% 넘게 남아 있어 아직 진입 시점이 아닙니다.",
    "VOLUME_NOT_CONFIRMED": f"돌파 거래량이 {ETF_VOLUME_THRESHOLD:.1f}배 기준에 미달합니다.",
}

_ETF_RECOMMENDATION_CACHE: dict[str, Any] = {}
_ETF_UNIVERSE_CACHE: dict[str, Any] = {}
_ETF_BENCHMARK_HISTORY_CACHE: dict[str, pd.DataFrame] = {}

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


def fetch_public_els_products() -> dict[str, Any]:
    attempts = []
    for fetcher in [
        fetch_kofia_els_products,
        fetch_els_products_from_configured_kis_api,
        fetch_mirae_els_products,
        fetch_hmsec_els_products,
        fetch_daishin_els_products,
    ]:
        result = fetcher()
        attempts.append(result.get("status", fetcher.__name__))
        if result.get("items"):
            result["api_status"] = "금투협 비교공시를 우선 확인하고, 실패 시 공개 증권사 화면을 보조로 확인합니다."
            return result

    result = empty_els_result(
        "공개 소스에서 현재 청약 가능한 순수 지수형 ELS를 찾지 못했습니다. "
        f"확인 결과: {' / '.join(attempts[:4])}"
    )
    result["api_status"] = "금투협, 한국투자 별도 API 설정, 미래에셋, 현대차증권, 대신증권 순서로 확인"
    return result


def fetch_kis_els_products() -> dict[str, Any]:
    # Backward-compatible wrapper for the Streamlit cache function name.
    return fetch_public_els_products()


def fetch_kofia_els_products() -> dict[str, Any]:
    request_xml = (
        "<message>"
        "<proframeHeader>"
        "<pfmAppName>FS-DIS2</pfmAppName>"
        "<pfmSvcName>DISDlsOfferSO</pfmSvcName>"
        "<pfmFnName>selectSubscribing</pfmFnName>"
        "</proframeHeader>"
        "<systemHeader></systemHeader>"
        "<DISDlsDTO>"
        "<val1></val1><val2></val2><val3></val3><val4></val4><val5></val5><val6>0</val6>"
        "</DISDlsDTO>"
        "</message>"
    )
    try:
        response = requests.post(
            KOFIA_ELS_SERVICE_URL,
            data=request_xml.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=UTF-8",
                "User-Agent": "Mozilla/5.0",
                "Referer": KOFIA_ELS_PAGE_URL,
            },
            timeout=20,
            verify=False,
        )
        response.raise_for_status()
    except Exception as exc:
        return empty_els_result(f"금투협 비교공시 호출 실패: {exc}", source_url=KOFIA_ELS_PAGE_URL)

    products, stats = kofia_xml_to_els_products(response.content)
    if not products:
        return empty_els_result(
            (
                "금투협 비교공시에서 청약중 상품 "
                f"{stats.get('rows', 0)}건을 확인했지만, 현재 시각 기준 청약 가능한 순수 지수형 ELS가 없습니다."
            ),
            source_url=KOFIA_ELS_PAGE_URL,
        )

    return {
        "items": limit_els_products(products),
        "status": (
            "금융투자협회 청약정보 비교공시 기준 "
            f"· 전체 {stats.get('rows', 0)}건 중 순수 지수형 ELS {stats.get('matched', 0)}건"
        ),
        "issuer_summary": summarize_els_issuers(products),
        "matched_count": len(products),
        "source_url": KOFIA_ELS_PAGE_URL,
        "guide_url": KOFIA_DISCLOSURE_HOME_URL,
        "notice_url": DART_DERIVATIVE_URL,
    }


def kofia_xml_to_els_products(xml_bytes: bytes) -> tuple[list[dict[str, str]], dict[str, int]]:
    products: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return [], {"rows": 0, "matched": 0}

    rows = root.findall(".//DISDlsDTO")
    for row in rows:
        vals = {child.tag: clean_text(child.text) for child in row}
        product = kofia_row_to_product(vals)
        if product:
            products.append(product)

    return dedupe_products(products), {"rows": len(rows), "matched": len(products)}


def kofia_row_to_product(vals: dict[str, str]) -> dict[str, str] | None:
    name = vals.get("val6", "")
    underlyings = strip_html_text(vals.get("val8", ""))
    structure = strip_html_text(vals.get("val18", ""))
    row_text = " ".join([name, underlyings, structure])
    if not looks_like_open_index_els(row_text, underlyings=underlyings):
        return None
    if not is_subscription_current(vals.get("val16"), vals.get("val17"), vals.get("val21")):
        return None

    detail_link = vals.get("val20", "")
    return {
        "증권사": vals.get("val4", "-"),
        "상품명": name or "-",
        "기초자산": underlyings or "-",
        "쿠폰": format_coupon(vals.get("val15")),
        "조기상환 조건": extract_early_redemption_terms(structure),
        "만기/상환주기": extract_maturity_cycle(structure, vals.get("val14")),
        "청약기간": format_subscription_period(vals.get("val16"), vals.get("val17")),
        "청약 상태": subscription_status(vals.get("val16"), vals.get("val17"), vals.get("val21")),
        "최대손실률": format_loss_rate(vals.get("val23")),
        "신용등급": vals.get("val5", "-"),
        "상품코드": vals.get("val22", "-"),
        "출처": "금투협 비교공시",
        "상세 링크": detail_link or KOFIA_ELS_PAGE_URL,
    }


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
        "items": limit_els_products(products),
        "status": "한국투자증권 Open API 기준",
        "issuer_summary": summarize_els_issuers(products),
        "matched_count": len(products),
        "source_url": KOFIA_ELS_PAGE_URL,
        "guide_url": KOFIA_DISCLOSURE_HOME_URL,
        "notice_url": DART_DERIVATIVE_URL,
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
            "증권사": field_by_keywords(row, ["증권사", "issuer", "company"], "한국투자증권"),
            "상품명": field_by_keywords(row, ["상품", "종목", "회차", "prdt", "prod"], text[:80]),
            "기초자산": field_by_keywords(row, ["기초", "자산", "under"], infer_underlyings(text)),
            "청약기간": field_by_keywords(row, ["청약", "모집", "subsc"], infer_date_range(text)),
            "쿠폰": field_by_keywords(row, ["수익", "쿠폰", "yield", "coupon"], "-"),
            "조기상환 조건": field_by_keywords(row, ["상환", "조건", "redemption"], "-"),
            "만기/상환주기": field_by_keywords(row, ["만기", "maturity"], "-"),
            "청약 상태": infer_subscription_status(dates),
            "최대손실률": field_by_keywords(row, ["손실", "loss"], "-"),
            "신용등급": field_by_keywords(row, ["등급", "rating"], "-"),
            "출처": "한국투자 별도 API 설정",
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


def fetch_mirae_els_products() -> dict[str, Any]:
    try:
        response = requests.post(
            MIRAE_ELS_AJAX_URL,
            data={
                "omkt_drvs_tcd": "1",
                "dlbr_term_yn": "",
                "itm_nm": "",
                "prgs_scd": "01",
                "qry_sort_tp": "0",
                "qry_sort_sqn": "0",
                "next_key": "",
            },
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": MIRAE_ELS_SEARCH_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=15,
        )
        response.raise_for_status()
    except Exception as exc:
        return empty_els_result(f"미래에셋 공개 ELS 조회 실패: {exc}", source_url=MIRAE_ELS_SEARCH_URL)

    try:
        payload = response.json()
    except ValueError:
        return empty_els_result("미래에셋 공개 ELS 응답을 JSON으로 읽지 못했습니다.", source_url=MIRAE_ELS_SEARCH_URL)

    products = mirae_rows_to_els_products(payload.get("grid01") or [])
    if not products:
        return empty_els_result("미래에셋 공개 검색에서 현재 청약 가능한 순수 지수형 ELS가 없습니다.", source_url=MIRAE_ELS_SEARCH_URL)

    return {
        "items": limit_els_products(products),
        "status": f"미래에셋 공개 ELS/DLS 검색 기준 · 순수 지수형 ELS {len(products)}건",
        "issuer_summary": summarize_els_issuers(products),
        "matched_count": len(products),
        "source_url": MIRAE_ELS_SEARCH_URL,
        "guide_url": MIRAE_ELS_SEARCH_URL,
        "notice_url": MIRAE_ELS_NOTICE_URL,
    }


def mirae_rows_to_els_products(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    products = []
    for row in rows:
        text = " ".join(str(value) for value in row.values() if value not in {None, ""})
        underlyings = clean_text(row.get("uast_cn") or infer_underlyings(text))
        if not looks_like_open_index_els(text, underlyings=underlyings):
            continue
        if not is_subscription_current(row.get("apy_strt_dt"), row.get("apy_end_dt"), ""):
            continue
        products.append(
            {
                "증권사": "미래에셋증권",
                "상품명": clean_text(row.get("itm_nm")) or "-",
                "기초자산": strip_html_text(underlyings) or "-",
                "쿠폰": format_coupon(row.get("omkt_drv_frcs_ern_r")),
                "조기상환 조건": clean_text(row.get("omkt_drv_rpy_cycl_cn")) or "-",
                "만기/상환주기": combine_maturity_cycle(
                    row.get("omkt_drv_exrt_cycl_cn"),
                    row.get("omkt_drv_rpy_cycl_cn"),
                ),
                "청약기간": format_subscription_period(row.get("apy_strt_dt"), row.get("apy_end_dt")),
                "청약 상태": clean_text(row.get("prgs_stat_nm")) or infer_subscription_status(parse_dates(text)),
                "최대손실률": format_loss_rate(row.get("max_abl_los_r")),
                "신용등급": "-",
                "상품코드": clean_text(row.get("itm_no")) or "-",
                "출처": "미래에셋 공개검색",
                "상세 링크": MIRAE_ELS_SEARCH_URL,
            }
        )
    return dedupe_products(products)


def fetch_hmsec_els_products() -> dict[str, Any]:
    return fetch_html_els_products(
        HMSEC_ELS_URL,
        "현대차증권",
        "현대차증권 공개 청약 표에서 현재 청약 가능한 순수 지수형 ELS가 없습니다.",
    )


def fetch_daishin_els_products() -> dict[str, Any]:
    return fetch_html_els_products(
        DAISHIN_ELS_URL,
        "대신증권",
        "대신증권 공개 청약 표에서 현재 청약 가능한 순수 지수형 ELS가 없습니다.",
    )


def fetch_html_els_products(url: str, issuer: str, empty_message: str) -> dict[str, Any]:
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
    except Exception as exc:
        return empty_els_result(f"{issuer} 공개 청약 표 호출 실패: {exc}", source_url=url)

    products = parse_els_products(response.text, issuer=issuer)
    if not products:
        return empty_els_result(empty_message, source_url=url)

    return {
        "items": limit_els_products(products),
        "status": f"{issuer} 공개 청약 표 기준 · 순수 지수형 ELS {len(products)}건",
        "issuer_summary": summarize_els_issuers(products),
        "matched_count": len(products),
        "source_url": url,
        "guide_url": url,
        "notice_url": DART_DERIVATIVE_URL,
    }


def empty_els_result(reason: str, *, source_url: str = KOFIA_ELS_PAGE_URL) -> dict[str, Any]:
    return {
        "items": [],
        "status": reason,
        "source_url": source_url,
        "guide_url": KOFIA_DISCLOSURE_HOME_URL,
        "notice_url": DART_DERIVATIVE_URL,
    }


def parse_els_products(html: str, *, issuer: str = "-") -> list[dict[str, str]]:
    parser = TableTextParser()
    parser.feed(html)
    products = []

    for table in parser.tables:
        if len(table) < 2:
            continue
        headers = [normalize_header(value) for value in table[0]]
        for row in table[1:]:
            text = " ".join(row)
            underlyings = infer_underlyings(text)
            if not looks_like_open_index_els(text, underlyings=underlyings):
                continue

            dates = parse_dates(text)
            if dates and not is_subscription_current(min(dates), max(dates), ""):
                continue

            product = row_to_product(headers, row, issuer=issuer)
            product["청약 상태"] = infer_subscription_status(dates)
            products.append(product)

    return dedupe_products(products)


def looks_like_open_index_els(text: str, *, underlyings: str | None = None) -> bool:
    upper = text.upper()
    if "ELB" in upper or "DLB" in upper or "사채" in text:
        return False
    if not ("ELS" in upper or "주가연계증권" in text or "파생결합증권" in text):
        return False
    parts = split_underlyings(underlyings or infer_underlyings(text))
    if parts:
        return all(is_index_underlying(part) for part in parts)
    return any(keyword.upper() in upper for keyword in INDEX_KEYWORDS)


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


def row_to_product(headers: list[str], row: list[str], *, issuer: str = "-") -> dict[str, str]:
    fields = {headers[idx] if idx < len(headers) else f"항목{idx + 1}": value for idx, value in enumerate(row)}
    row_text = " · ".join(value for value in row if value)
    return {
        "증권사": issuer,
        "상품명": first_present(fields, ["상품명", "종목명", "회차"], row_text[:80]),
        "기초자산": first_present(fields, ["기초자산"], infer_underlyings(row_text)),
        "청약기간": first_present(fields, ["청약기간", "모집기간"], infer_date_range(row_text)),
        "쿠폰": first_present(fields, ["수익조건"], "-"),
        "조기상환 조건": first_present(fields, ["상환조건"], "-"),
        "만기/상환주기": first_present(fields, ["만기"], "-"),
        "최대손실률": first_present(fields, ["조건미충족시손실률"], "-"),
        "신용등급": "-",
        "출처": f"{issuer} 공개표",
        "상세 링크": "-",
    }


def first_present(fields: dict[str, str], keys: list[str], fallback: str) -> str:
    for key in keys:
        value = fields.get(key)
        if value:
            return value
    return fallback


def infer_underlyings(text: str) -> str:
    cleaned = strip_html_text(text)
    found = [keyword for keyword in INDEX_KEYWORDS if keyword.upper() in cleaned.upper()]
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


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(unescape(str(value)).split())


def strip_html_text(value: Any) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"(?i)<br\s*/?>", ", ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_text(text).strip(" ,")


def split_underlyings(value: str) -> list[str]:
    cleaned = strip_html_text(value)
    if not cleaned or cleaned == "-":
        return []
    return [part.strip() for part in re.split(r"[,/·\n]+", cleaned) if part.strip()]


def is_index_underlying(value: str) -> bool:
    upper = value.upper().replace(" ", "")
    index_markers = [
        "INDEX",
        "KOSPI",
        "S&P",
        "SPX",
        "NASDAQ",
        "NIKKEI",
        "EUROSTOXX",
        "EURO",
        "STOXX",
        "HSCEI",
        "HANGSENG",
        "HANG SENG",
        "항셍",
        "코스피",
        "나스닥",
        "닛케이",
    ]
    return any(marker.replace(" ", "") in upper for marker in index_markers)


def parse_yyyymmdd(value: Any) -> Any:
    text = re.sub(r"\D", "", str(value or ""))
    if len(text) < 8:
        return None
    try:
        return datetime(int(text[:4]), int(text[4:6]), int(text[6:8])).date()
    except ValueError:
        return None


def parse_subscription_end_datetime(note: Any) -> Any:
    text = clean_text(note)
    match = re.search(r"(20\d{2})[.\-/년 ]+(\d{1,2})[.\-/월 ]+(\d{1,2}).*?(\d{1,2})시\s*(\d{1,2})?분?", text)
    if not match:
        return None
    minute = int(match.group(5) or 0)
    try:
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            int(match.group(4)),
            minute,
            tzinfo=timezone(timedelta(hours=9)),
        )
    except ValueError:
        return None


def is_subscription_current(start_value: Any, end_value: Any, note: Any) -> bool:
    now = datetime.now(timezone(timedelta(hours=9)))
    start_date = start_value if hasattr(start_value, "year") else parse_yyyymmdd(start_value)
    end_date = end_value if hasattr(end_value, "year") else parse_yyyymmdd(end_value)
    if start_date and now.date() < start_date:
        return False
    if end_date and now.date() > end_date:
        return False
    end_datetime = parse_subscription_end_datetime(note)
    if end_datetime and now > end_datetime:
        return False
    return bool(start_date or end_date)


def format_yyyymmdd(value: Any) -> str:
    date_value = parse_yyyymmdd(value)
    return date_value.strftime("%Y-%m-%d") if date_value else "-"


def format_subscription_period(start_value: Any, end_value: Any) -> str:
    start = format_yyyymmdd(start_value)
    end = format_yyyymmdd(end_value)
    if start == "-" and end == "-":
        return "-"
    if start == end:
        return start
    return f"{start} ~ {end}"


def format_coupon(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return "-"
    if "연" in text or "%" in text:
        return text
    try:
        return f"연 {float(text):.2f}%"
    except ValueError:
        return text


def format_loss_rate(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return "-"
    if "%" in text:
        return text
    try:
        return f"{float(text):.0f}%"
    except ValueError:
        return text


def subscription_status(start_value: Any, end_value: Any, note: Any) -> str:
    end_datetime = parse_subscription_end_datetime(note)
    if end_datetime:
        return f"청약 가능 ({end_datetime.strftime('%m/%d %H:%M')}까지)"
    dates = [date for date in [parse_yyyymmdd(start_value), parse_yyyymmdd(end_value)] if date]
    return infer_subscription_status(dates)


def extract_maturity_cycle(structure: str, maturity_value: Any) -> str:
    text = clean_text(structure)
    match = re.search(r"(\d+년\s*만기)\s*(\d+개월\s*단위\s*조기상환형)", text)
    if match:
        return f"{match.group(1)} / {match.group(2)}"
    maturity = format_yyyymmdd(maturity_value)
    return f"만기 {maturity}" if maturity != "-" else "-"


def extract_early_redemption_terms(structure: str) -> str:
    text = clean_text(structure)
    match = re.search(r"((?:Lizard)?StepDown형)\[([^\]]+)\]", text, re.IGNORECASE)
    if match:
        label = "리자드 스텝다운" if "Lizard" in match.group(1) else "스텝다운"
        raw_terms = match.group(2)
        parts = raw_terms.split("/")
        early = parts[0]
        floor = "/".join(parts[1:]) if len(parts) > 1 else ""
        if floor:
            return f"{label} {early} / 만기·낙인 기준 {floor}"
        return f"{label} {early}"
    return text[:120] if text else "-"


def combine_maturity_cycle(maturity: Any, cycle: Any) -> str:
    values = [clean_text(maturity), clean_text(cycle)]
    values = [value for value in values if value and value != "-"]
    return " / ".join(values) if values else "-"


def dedupe_products(products: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    unique = []
    for product in products:
        key = (product.get("증권사"), product.get("상품명"), product.get("기초자산"), product.get("청약기간"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(product)
    return unique


def limit_els_products(products: list[dict[str, str]]) -> list[dict[str, str]]:
    ranked = rank_els_products(products)
    limit = max(1, ELS_TOP_LIMIT)
    selected = []
    issuer_counts: dict[str, int] = {}

    for product in ranked:
        issuer = product.get("증권사") or "-"
        if issuer_counts.get(issuer, 0) >= ELS_MAX_PER_ISSUER:
            continue
        selected.append(product)
        issuer_counts[issuer] = issuer_counts.get(issuer, 0) + 1
        if len(selected) >= limit:
            return selected

    selected_keys = {
        (product.get("증권사"), product.get("상품명"), product.get("상품코드"))
        for product in selected
    }
    for product in ranked:
        key = (product.get("증권사"), product.get("상품명"), product.get("상품코드"))
        if key in selected_keys:
            continue
        selected.append(product)
        if len(selected) >= limit:
            break
    return selected


def rank_els_products(products: list[dict[str, str]]) -> list[dict[str, str]]:
    scored = [score_els_product(product) for product in products]
    return sorted(
        scored,
        key=lambda product: (
            float(product.get("ELS 점수", 0)),
            parse_number(product.get("쿠폰")),
            product.get("신용등급", ""),
        ),
        reverse=True,
    )


def score_els_product(product: dict[str, str]) -> dict[str, str]:
    coupon = parse_number(product.get("쿠폰"))
    underlyings = split_underlyings(product.get("기초자산", ""))
    terms = f"{product.get('조기상환 조건', '')} {product.get('만기/상환주기', '')}"
    barrier_profile = extract_els_barrier_profile(terms)
    barriers = barrier_profile["early_barriers"]
    final_barrier = barrier_profile["final_barrier"]
    avg_barrier = sum(barriers) / len(barriers) if barriers else None
    no_knock_in = barrier_profile["no_knock_in"]
    knock_in = barrier_profile["knock_in"]
    early_months = infer_redemption_interval_months(terms)

    protection_score, protection_note = score_els_protection(
        final_barrier, avg_barrier, knock_in, no_knock_in
    )
    underlying_score, underlying_note = score_els_underlyings(underlyings)
    coupon_score, coupon_note = score_els_coupon(coupon)
    issuer_score, issuer_note = score_els_issuer(product.get("신용등급", ""))
    term_score, term_note = score_els_term(product.get("만기/상환주기", ""), early_months)

    total = round(
        protection_score + underlying_score + coupon_score + issuer_score + term_score,
        1,
    )
    grade = els_score_grade(total)
    reasons = [
        protection_note,
        coupon_note,
        underlying_note,
        issuer_note,
        term_note,
    ]
    warnings = els_warning_notes(product, coupon, final_barrier, knock_in, no_knock_in, underlyings)

    return {
        "ELS 점수": f"{total:.1f}",
        "판정": grade,
        "핵심 근거": " · ".join(note for note in reasons if note),
        "주의 요인": " · ".join(warnings) if warnings else "특이 위험 요인 제한적",
        **product,
        "상세 점수": (
            f"방어 {protection_score:.1f}/35 · 기초자산 {underlying_score:.1f}/20 · "
            f"쿠폰 {coupon_score:.1f}/20 · 신용 {issuer_score:.1f}/15 · 기간 {term_score:.1f}/10"
        ),
    }


def parse_number(value: Any) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or "").replace(",", ""))
    return float(match.group(0)) if match else 0.0


def extract_els_barrier_profile(text: str) -> dict[str, Any]:
    no_knock_in = bool(re.search(r"\bNoKI\b|노낙인|노\s*낙인", text, re.IGNORECASE))
    early_text, floor_text = split_stepdown_barrier_text(text)
    early_barriers = extract_barrier_numbers(remove_lizard_barriers(early_text))

    if not early_barriers:
        early_barriers = extract_barrier_numbers(remove_lizard_barriers(text))

    final_barrier = early_barriers[-1] if early_barriers else None
    knock_in = infer_knock_in_barrier(text, floor_text, no_knock_in)
    return {
        "early_barriers": early_barriers,
        "final_barrier": final_barrier,
        "knock_in": knock_in,
        "no_knock_in": no_knock_in,
    }


def split_stepdown_barrier_text(text: str) -> tuple[str, str]:
    patterns = [
        r"StepDown형\[([^\]]+)\]",
        r"스텝다운\s*\(([^)]+)\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        body = match.group(1)
        if "/" in body:
            early, floor = body.split("/", 1)
            return early, floor
        return body, ""
    match = re.search(r"Step[-\s]?Down형\s*([0-9][0-9./\-\s]+)", text, re.IGNORECASE)
    if match:
        return match.group(1), ""
    return text, ""


def remove_lizard_barriers(text: str) -> str:
    return re.sub(r"\(L\d{2,3}(?:\.\d+)?\)", "", text, flags=re.IGNORECASE)


def extract_barrier_numbers(text: str) -> list[float]:
    values = []
    for raw in re.findall(r"(?<!\d)(\d{2,3}(?:\.\d+)?)(?!\d)", text):
        value = float(raw)
        if 30 <= value <= 100:
            values.append(value)
    return values[:14]


def infer_knock_in_barrier(text: str, floor_text: str, no_knock_in: bool) -> float | None:
    if no_knock_in:
        return None
    ki_match = re.search(r"(\d{2,3}(?:\.\d+)?)\s*(?:KI|낙인|Knock)", text, re.IGNORECASE)
    if not ki_match:
        ki_match = re.search(r"Knock\s*In\s*(\d{2,3}(?:\.\d+)?)", text, re.IGNORECASE)
    if not ki_match:
        ki_match = re.search(r"(?:KI|낙인|Knock)\s*(\d{2,3}(?:\.\d+)?)", text, re.IGNORECASE)
    if ki_match:
        return float(ki_match.group(1))
    floor_barriers = extract_barrier_numbers(floor_text)
    if floor_barriers:
        return floor_barriers[-1]
    return None


def infer_redemption_interval_months(text: str) -> int | None:
    match = re.search(r"(\d+)\s*개월", text)
    return int(match.group(1)) if match else None


def score_els_protection(
    final_barrier: float | None,
    avg_barrier: float | None,
    knock_in: float | None,
    no_knock_in: bool,
) -> tuple[float, str]:
    if final_barrier is None:
        final_score = 6
        final_note = "만기상환 배리어 확인 필요"
    elif final_barrier <= 50:
        final_score = 14
        final_note = f"만기상환 기준 {final_barrier:g}%"
    elif final_barrier <= 55:
        final_score = 12
        final_note = f"만기상환 기준 {final_barrier:g}%"
    elif final_barrier <= 60:
        final_score = 10
        final_note = f"만기상환 기준 {final_barrier:g}%"
    elif final_barrier <= 65:
        final_score = 8
        final_note = f"만기상환 기준 {final_barrier:g}%"
    else:
        final_score = 5
        final_note = f"만기상환 기준 {final_barrier:g}%"

    if no_knock_in:
        knock_score = 12
        knock_note = "노낙인 구조"
    elif knock_in is None:
        knock_score = 5
        knock_note = "낙인 조건 확인 필요"
    elif knock_in <= 35:
        knock_score = 10
        knock_note = f"낙인 {knock_in:g}%"
    elif knock_in <= 40:
        knock_score = 8
        knock_note = f"낙인 {knock_in:g}%"
    elif knock_in <= 45:
        knock_score = 6
        knock_note = f"낙인 {knock_in:g}%"
    else:
        knock_score = 4
        knock_note = f"낙인 {knock_in:g}%"

    if avg_barrier is None:
        early_score = 4
    elif avg_barrier <= 75:
        early_score = 9
    elif avg_barrier <= 80:
        early_score = 7
    elif avg_barrier <= 85:
        early_score = 5
    else:
        early_score = 3

    return final_score + knock_score + early_score, f"{final_note}, {knock_note}"


def score_els_underlyings(underlyings: list[str]) -> tuple[float, str]:
    count = len(underlyings)
    count_score = {1: 8, 2: 6, 3: 4}.get(count, 2)
    if not underlyings:
        return 8, "기초자산 확인 필요"

    quality_scores = [underlying_quality_score(name) for name in underlyings]
    quality_score = sum(quality_scores) / len(quality_scores)
    score = count_score + quality_score
    return min(score, 20), f"기초자산 {count}개"


def underlying_quality_score(name: str) -> float:
    upper = name.upper().replace(" ", "")
    if "S&P500" in upper or "EUROSTOXX50" in upper:
        return 12
    if "KOSPI200" in upper or "NIKKEI225" in upper:
        return 11
    if "NASDAQ" in upper:
        return 9
    if "HSCEI" in upper or "HANGSENG" in upper or "항셍" in name:
        return 7
    return 9


def score_els_coupon(coupon: float) -> tuple[float, str]:
    if coupon <= 0:
        return 0, "쿠폰 확인 필요"
    if coupon < 8:
        score = 8
    elif coupon < 12:
        score = 13
    elif coupon < 18:
        score = 18
    elif coupon <= 24:
        score = 20
    elif coupon <= 30:
        score = 16
    else:
        score = 12
    return score, f"쿠폰 연 {coupon:g}%"


def score_els_issuer(rating: str) -> tuple[float, str]:
    normalized = rating.replace(" ", "").upper()
    table = {
        "AAA": 15,
        "AA+": 14,
        "AA": 13,
        "AA-": 12,
        "A+": 10,
        "A": 8,
        "A-": 6,
    }
    return table.get(normalized, 5), f"신용등급 {rating or '확인 필요'}"


def score_els_term(maturity: str, interval_months: int | None) -> tuple[float, str]:
    interval_score = 5 if interval_months and interval_months <= 3 else 4 if interval_months == 4 else 3
    maturity_score = 5 if "3년" in maturity or "2029" in maturity else 4
    note = f"{interval_months}개월 조기상환" if interval_months else "조기상환 주기 확인 필요"
    return maturity_score + interval_score, note


def els_score_grade(score: float) -> str:
    if score >= 80:
        return "우선 검토"
    if score >= 70:
        return "검토 가능"
    if score >= 60:
        return "조건부 검토"
    return "주의"


def els_warning_notes(
    product: dict[str, str],
    coupon: float,
    final_barrier: float | None,
    knock_in: float | None,
    no_knock_in: bool,
    underlyings: list[str],
) -> list[str]:
    warnings = []
    if coupon >= 25:
        warnings.append("고쿠폰 구조")
    if final_barrier and final_barrier >= 65:
        warnings.append("만기상환 기준 높음")
    if knock_in and knock_in >= 45 and not no_knock_in:
        warnings.append("낙인 기준 높음")
    if len(underlyings) >= 3:
        warnings.append("기초자산 3개 이상")
    if re.search(r"USD|달러", product.get("조기상환 조건", ""), re.IGNORECASE):
        warnings.append("외화 발행")
    return warnings


def summarize_els_issuers(products: list[dict[str, str]]) -> str:
    counts: dict[str, int] = {}
    for product in products:
        issuer = product.get("증권사") or "-"
        counts[issuer] = counts.get(issuer, 0) + 1
    if not counts:
        return ""

    summary = [f"{issuer} {count}건" for issuer, count in sorted(counts.items())]
    if len(summary) <= 8:
        return ", ".join(summary)
    shown = ", ".join(summary[:8])
    return f"{shown} 외 {len(summary) - 8}개사"


def build_etf_recommendations(snapshot: dict[str, Any]) -> dict[str, Any]:
    cache_key = etf_recommendation_cache_key(snapshot)
    cached = _ETF_RECOMMENDATION_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached["created_at"] < ETF_SCREEN_CACHE_SECONDS:
        return cached["result"]

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
    screen_summary = {
        "universe_count": len(universe),
        "screenable_count": screenable_count,
        "preliminary_count": len(preliminary_candidates),
        "analyzed_count": len(analyzed_candidates),
        "universe_source": "한국투자증권 종목정보파일",
        "price_source": first_price_source(ranked),
        "volume_threshold": ETF_VOLUME_THRESHOLD,
        "buy_zone_max_pct": ETF_BUY_ZONE_MAX_PCT,
        "holding_lookback_sessions": ETF_HOLDING_LOOKBACK_SESSIONS,
    }

    buy_now = sorted(
        [item for item in ranked if item["trading_status"] == "BUY_READY"],
        key=lambda item: (
            -item["setup_score"],
            -item["leadership_score"],
            item["leader_rank"],
            item["ticker"],
        ),
    )[:ETF_BUY_READY_LIMIT]

    watchable = [
        item
        for item in ranked
        if item["display_group"] == "WATCHLIST"
        and item["leader_rank"] <= 20
        and item["can_slim_score"] >= 60
        and item["leader_percentile"] >= 65
        and item["trading_status"] != "BUY_READY"
    ]
    watchlist = sorted(
        watchable,
        key=lambda item: (
            watch_priority(item),
            -item["can_slim_score"],
            item["leader_rank"],
            item["ticker"],
        ),
    )[:ETF_WATCHLIST_LIMIT]

    for display_rank, item in enumerate(buy_now, start=1):
        item["display_rank"] = display_rank
    for display_rank, item in enumerate(watchlist, start=1):
        item["display_rank"] = display_rank

    result = {
        "buy_now": buy_now,
        "watchlist": watchlist,
        "holding_reviews": build_etf_holding_reviews(ranked),
        "ranked": ranked,
        "screen_summary": screen_summary,
    }
    _ETF_RECOMMENDATION_CACHE[cache_key] = {"created_at": now, "result": result}
    return result


def first_price_source(items: list[dict[str, Any]]) -> str:
    for item in items:
        source = item.get("data_source")
        if source:
            return source
    return "-"


def watch_priority(item: dict[str, Any]) -> int:
    status_priority = {
        "VOLUME_CONFIRM": 1,
        "PIVOT_APPROACH": 2,
        "NO_VALID_BASE": 3,
        "NO_VALID_PIVOT": 4,
        "EXTENDED": 5,
        "MARKET_NOT_CONFIRMED": 6,
    }
    return status_priority.get(item.get("trading_status"), 9)


def build_etf_holding_reviews(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reviews = [
        item["holding_review"]
        for item in ranked
        if item.get("holding_review")
    ]
    return sorted(
        reviews,
        key=lambda review: (
            holding_action_priority(review["holding_status"]),
            -review["age_sessions"],
            -review["return_pct"],
            review["ticker"],
        ),
    )[:ETF_HOLDING_DISPLAY_LIMIT]


def holding_action_priority(status: str) -> int:
    priorities = {
        "SELL_CUT_LOSS": 0,
        "SELL": 1,
        "FAILED_BREAKOUT_WARNING": 2,
        "STRONG_SELL_WARNING": 3,
        "PARTIAL_SELL": 4,
        "ROUND_TRIP_WARNING": 5,
        "SELL_WARNING": 6,
        "DEFENSE": 7,
        "RS_WEAKENING": 8,
        "LOW_VOLUME_HIGH_WARNING": 9,
        "PROFIT_ZONE_STRONG": 10,
        "PROFIT_ZONE": 11,
        "EIGHT_WEEK_HOLD_CANDIDATE": 12,
        "PYRAMID_READY_3": 13,
        "PYRAMID_READY_2": 14,
        "HOLD": 15,
    }
    return priorities.get(status, 9)


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
            "benchmark": "-",
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
        "benchmark": item.get("name", "-"),
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
        ("return20", "20일 상대강도", 15),
        ("return60", "60일 상대강도", 20),
        ("return120", "120일 상대강도", 10),
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
    item["components"]["추세 정렬"] = leadership_trend_score(item)
    item["components"]["신고가/리더"] = leadership_high_score(item)
    item["components"]["Leadership 원점수"] = (
        rs_score + item["components"]["추세 정렬"] + item["components"]["신고가/리더"]
    )
    item["leadership_score"] = round(item["components"]["Leadership 원점수"] / 60 * 100)

    setup_components = setup_score_components(item)
    item["components"].update(setup_components)
    item["components"]["Setup 원점수"] = sum(setup_components.values())
    item["setup_score"] = round(item["components"]["Setup 원점수"] / 40 * 100)

    classification = classify_etf_candidate(item)
    item.update(classification)
    if item["trading_status"] == "NO_VALID_BASE":
        item["setup_score"] = min(item["setup_score"], 45)
    elif item["trading_status"] == "EXTENDED":
        item["setup_score"] = min(item["setup_score"], 55)
    item["can_slim_score"] = round(item["leadership_score"] * 0.60 + item["setup_score"] * 0.40)
    item["action"] = item["action_label"]
    item["action_rank"] = 10 - ETF_STATUS_PRIORITY.get(item["trading_status"], 0)
    item["sell_signal"] = current_sell_signal(item)
    item["holding_review"] = build_holding_review(item, item.get("recent_buy_ready_event"))
    item["positive_reasons"], item["risk_signals"] = etf_reasons(item)


def leader_label(item: dict[str, Any]) -> str:
    if item["trading_status"] in {"BELOW_50SMA", "LIQUIDITY_FAIL", "DATA_INCOMPLETE"}:
        return "방어"
    if item["trading_status"] == "BUY_READY":
        return "현재 매수 가능"
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
    rs_metrics = recent_relative_strength_metrics(df, candidate)
    follow_through = market_item.get("follow_through")
    ftd_text = f"{follow_through['date']} FTD" if follow_through else "FTD 확인 필요"
    buy_high = pivot * 1.05 if pivot else None
    recent_buy_ready_event = find_recent_buy_ready_event(df, candidate, market_item)
    return {
        **candidate,
        "category": candidate.get("category") or infer_etf_category(candidate),
        "market": market_item["name"],
        "benchmark_market": benchmark_item["name"],
        "market_state": market_gate["state"],
        "market_state_label": market_gate["state_label"],
        "opinion": market_item.get("signals", {}).get("oneil", {}).get("opinion", "-"),
        "can_slim_score": 0,
        "components": {},
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
        "rs_trend5_pct": rs_metrics["rs_trend5_pct"],
        "rs_weakening_days": rs_metrics["rs_weakening_days"],
        "rs_benchmark_ticker": rs_metrics["benchmark_ticker"],
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
        "stop_loss": pivot * (1 - ETF_STOP_LOSS_PCT / 100) if pivot else None,
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
        "distance_high252": distance_high252,
        "min_avg_value": min_avg_value_for_etf(candidate),
        "volume_change_pct": volume_change,
        "distribution_days": market_item.get("distribution_count", 0),
        "sell_signal": "관찰",
        "recent_buy_ready_event": recent_buy_ready_event,
        "holding_review": None,
        "basis": (
            f"{market_item['name']} {market_gate['state_label']}, {ftd_text}, "
            f"활성 분산일 {market_item.get('distribution_count', 0)}회, "
            f"{benchmark_item['name']} 대비 60일 초과수익 {return60 - benchmark_return60:+.2f}%"
        ),
        "data_source": history_source,
        "data_status": market_item.get("data_status", "-"),
    }


def recent_relative_strength_metrics(
    df: pd.DataFrame,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    benchmark_ticker = benchmark_ticker_for_etf(candidate)
    if not benchmark_ticker or benchmark_ticker == candidate.get("yahoo_ticker"):
        return {"benchmark_ticker": benchmark_ticker or "-", "rs_trend5_pct": 0.0, "rs_weakening_days": 0}

    benchmark = benchmark_history(benchmark_ticker)
    if benchmark.empty:
        return {"benchmark_ticker": benchmark_ticker, "rs_trend5_pct": 0.0, "rs_weakening_days": 0}

    aligned = (
        pd.DataFrame({"etf": df["Close"]})
        .join(benchmark["Close"].rename("benchmark"), how="inner")
        .dropna()
    )
    if len(aligned) < ETF_RS_WEAKENING_DAYS + 1:
        return {"benchmark_ticker": benchmark_ticker, "rs_trend5_pct": 0.0, "rs_weakening_days": 0}

    recent = aligned.tail(ETF_RS_WEAKENING_DAYS + 1)
    etf_return = pct(recent["etf"].iloc[-1], recent["etf"].iloc[0])
    benchmark_return = pct(recent["benchmark"].iloc[-1], recent["benchmark"].iloc[0])
    daily_rs = recent.pct_change().dropna()
    rs_daily = (daily_rs["etf"] - daily_rs["benchmark"]) * 100
    return {
        "benchmark_ticker": benchmark_ticker,
        "rs_trend5_pct": etf_return - benchmark_return,
        "rs_weakening_days": int((rs_daily < 0).sum()),
    }


def benchmark_ticker_for_etf(candidate: dict[str, Any]) -> str:
    if candidate.get("market_group") == "korea":
        return "069500.KS" if candidate.get("signal_key") == "kospi200" else "226490.KS"
    if candidate.get("signal_key") == "nasdaq_composite":
        return "QQQM"
    return "SPY"


def benchmark_history(ticker: str) -> pd.DataFrame:
    cached = _ETF_BENCHMARK_HISTORY_CACHE.get(ticker)
    if cached is not None:
        return cached
    try:
        history = fetch_yahoo_chart(ticker)
    except Exception:
        history = pd.DataFrame()
    _ETF_BENCHMARK_HISTORY_CACHE[ticker] = history
    return history


def find_recent_buy_ready_event(
    df: pd.DataFrame,
    candidate: dict[str, Any],
    market_item: dict[str, Any],
) -> dict[str, Any] | None:
    start = max(0, len(df) - ETF_HOLDING_LOOKBACK_SESSIONS)
    buy_ready_events = []
    for pos in range(start, len(df)):
        partial = df.iloc[: pos + 1]
        if len(partial) < ETF_MIN_HISTORY_ROWS:
            continue
        event_item = historical_etf_signal_item(partial, candidate, market_item)
        if not event_item:
            continue
        classification = classify_etf_candidate(event_item)
        if classification["trading_status"] != "BUY_READY":
            continue
        row = partial.iloc[-1]
        buy_ready_events.append(
            {
                "position": pos,
                "date": row.name.strftime("%Y-%m-%d"),
                "entry_price": event_item["last_price"],
                "pivot": event_item["pivot"],
                "buy_high": event_item["pivot"] * (1 + ETF_BUY_ZONE_MAX_PCT / 100),
                "stop_loss": event_item["last_price"] * (1 - ETF_STOP_LOSS_PCT / 100),
                "volume_ratio": event_item["volume_ratio"],
            }
        )

    if not buy_ready_events:
        return None

    streak = [buy_ready_events[-1]]
    for event in reversed(buy_ready_events[:-1]):
        if event["position"] == streak[0]["position"] - 1:
            streak.insert(0, event)
        else:
            break

    event = dict(streak[0])
    last_event = streak[-1]
    event["last_signal_date"] = last_event["date"]
    event["signal_count"] = len(streak)
    event["sessions_ago"] = len(df) - event["position"] - 1
    event["quick_20pct"] = quick_twenty_percent_move(df, event["position"], event["pivot"])
    hold_until_pos = min(len(df) - 1, event["position"] + ETF_HOLDING_LOOKBACK_SESSIONS)
    event["hold_until_date"] = df.iloc[hold_until_pos].name.strftime("%Y-%m-%d")
    event.update(holding_event_metrics(df, event))
    return event


def holding_event_metrics(df: pd.DataFrame, event: dict[str, Any]) -> dict[str, Any]:
    start_pos = event["position"]
    window = df.iloc[start_pos:].copy()
    latest = df.iloc[-1]
    latest_close = float(latest["Close"])
    highest_price = float(window["High"].max()) if "High" in window else float(window["Close"].max())
    current_return_pct = pct(latest_close, event["entry_price"])
    max_unrealized_gain_pct = pct(highest_price, event["entry_price"])
    latest_down_pct = float(latest["pct_change"]) if pd.notna(latest.get("pct_change")) else 0.0
    down_days = df["pct_change"].iloc[start_pos:].dropna()
    largest_down_pct = float(down_days.min()) if not down_days.empty else 0.0
    close_location = close_location_ratio(latest)
    latest_high = float(latest["High"]) if pd.notna(latest.get("High")) else latest_close
    window_high = float(window["High"].max()) if "High" in window else highest_price
    largest_down_day = latest_down_pct < 0 and math.isclose(latest_down_pct, largest_down_pct, abs_tol=0.01)
    return {
        "highest_price": highest_price,
        "max_unrealized_gain_pct": max_unrealized_gain_pct,
        "current_return_pct": current_return_pct,
        "gain_giveback_pct": max(0.0, max_unrealized_gain_pct - current_return_pct),
        "largest_down_day": bool(largest_down_day),
        "latest_down_pct": latest_down_pct,
        "largest_down_pct": largest_down_pct,
        "close_location": close_location,
        "new_high": bool(latest_high >= window_high * 0.999),
    }


def close_location_ratio(row: pd.Series) -> float | None:
    high = float(row["High"]) if pd.notna(row.get("High")) else None
    low = float(row["Low"]) if pd.notna(row.get("Low")) else None
    close = float(row["Close"]) if pd.notna(row.get("Close")) else None
    if high is None or low is None or close is None or high <= low:
        return None
    return (close - low) / (high - low)


def historical_etf_signal_item(
    partial: pd.DataFrame,
    candidate: dict[str, Any],
    market_item: dict[str, Any],
) -> dict[str, Any] | None:
    latest = partial.iloc[-1]
    close = float(latest["Close"])
    ma50 = float(latest["ma50"]) if pd.notna(latest["ma50"]) else None
    ma50_slope = float(latest["ma50_slope20"]) if pd.notna(latest["ma50_slope20"]) else 0.0
    avg_volume20 = float(latest["avg_volume20"]) if pd.notna(latest["avg_volume20"]) else 0.0
    avg_volume50 = float(latest["avg_volume50"]) if pd.notna(latest["avg_volume50"]) else 0.0
    avg_value50 = float(latest["avg_value50"]) if pd.notna(latest["avg_value50"]) else 0.0
    base = detect_flat_base(partial)
    pivot = base.get("pivot")
    if pivot is None:
        return None
    return {
        "last_price": close,
        "pivot": pivot,
        "pivot_distance_pct": pct(close, pivot),
        "ma50": ma50,
        "ma50_slope": ma50_slope,
        "market_state": market_state_for_buy_ready_date(market_item, latest.name),
        "avg_volume50": avg_volume50,
        "avg_value50": avg_value50,
        "min_avg_volume": candidate.get("min_avg_volume", 0),
        "min_avg_value": min_avg_value_for_etf(candidate),
        "base_exists": base["base_exists"],
        "volume_ratio": float(latest["Volume"] / avg_volume20) if avg_volume20 else 0.0,
    }


def market_state_for_buy_ready_date(market_item: dict[str, Any], date: Any) -> str:
    follow_through = market_item.get("follow_through") or {}
    if not follow_through.get("is_active"):
        return "MARKET_CORRECTION"
    ftd_date = pd.to_datetime(follow_through.get("date"), errors="coerce")
    signal_date = pd.to_datetime(date, errors="coerce")
    if pd.isna(ftd_date) or pd.isna(signal_date) or signal_date < ftd_date:
        return "MARKET_CORRECTION"
    return "CONFIRMED_UPTREND"


def quick_twenty_percent_move(df: pd.DataFrame, start_pos: int, pivot: float | None) -> bool:
    if not pivot:
        return False
    end_pos = min(len(df), start_pos + ETF_FAST_LEADER_SESSIONS + 1)
    if end_pos <= start_pos:
        return False
    max_close = float(df.iloc[start_pos:end_pos]["Close"].max())
    return max_close >= pivot * (1 + ETF_FAST_LEADER_GAIN_PCT / 100)


def build_holding_review(
    item: dict[str, Any],
    event: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not event:
        return None
    entry_price = event["entry_price"]
    close = item["last_price"]
    pivot = event["pivot"]
    return_pct = pct(close, entry_price)
    pivot_gain_pct = pct(close, pivot)
    status, action_label, explanation, signal_level, sell_reasons = classify_holding_action(item, event)
    defense_line, defense_line_label = holding_defense_line(item, event, return_pct)
    category = item.get("category") or "sector"
    return {
        "ticker": item["ticker"],
        "name": item["name"],
        "listing": item["listing"],
        "country": item["country"],
        "index": item["index"],
        "category": category,
        "etf_type_label": etf_type_label(category),
        "market": item["market"],
        "data_source": item.get("data_source", "-"),
        "data_status": item.get("data_status", "-"),
        "signal_date": event["date"],
        "last_signal_date": event.get("last_signal_date", event["date"]),
        "signal_count": event.get("signal_count", 1),
        "age_sessions": event["sessions_ago"],
        "entry_price": entry_price,
        "last_price": close,
        "highest_price": event.get("highest_price", close),
        "return_pct": return_pct,
        "pivot": pivot,
        "pivot_gain_pct": pivot_gain_pct,
        "stop_loss": event["stop_loss"],
        "profit_low": pivot * (1 + ETF_PROFIT_ZONE_START_PCT / 100) if pivot else None,
        "profit_high": pivot * (1 + ETF_PROFIT_ZONE_END_PCT / 100) if pivot else None,
        "defense_line": defense_line,
        "defense_line_label": defense_line_label,
        "ma21": item.get("ma21"),
        "ma50": item.get("ma50"),
        "volume_ratio": item.get("volume_ratio", 0.0),
        "market_state": item.get("market_state", "-"),
        "market_state_label": item.get("market_state_label", "-"),
        "distribution_days": item.get("distribution_days", 0),
        "rs_trend5_pct": item.get("rs_trend5_pct", 0.0),
        "rs_weakening_days": item.get("rs_weakening_days", 0),
        "rs_benchmark_ticker": item.get("rs_benchmark_ticker", "-"),
        "max_unrealized_gain_pct": event.get("max_unrealized_gain_pct", max(return_pct, 0.0)),
        "gain_giveback_pct": event.get("gain_giveback_pct", 0.0),
        "latest_down_pct": event.get("latest_down_pct", 0.0),
        "largest_down_pct": event.get("largest_down_pct", 0.0),
        "close_location": event.get("close_location"),
        "new_high": event.get("new_high", False),
        "holding_status": status,
        "action_label": action_label,
        "explanation": explanation,
        "sell_signal_level": signal_level,
        "sell_reason_codes": sell_reasons,
        "sell_signal": item.get("sell_signal", "-"),
        "quick_20pct": event.get("quick_20pct", False),
        "hold_until_date": event.get("hold_until_date", "-"),
        "pyramid_plan": evaluate_pyramiding(return_pct),
        "can_slim_score": item.get("can_slim_score", 0),
        "leader_rank": item.get("leader_rank", 999),
    }


def classify_holding_action(
    item: dict[str, Any],
    event: dict[str, Any],
) -> tuple[str, str, str, int, list[str]]:
    close = item["last_price"]
    entry_price = event["entry_price"]
    pivot = event["pivot"]
    ma21 = item.get("ma21")
    ma50 = item.get("ma50")
    volume_ratio = item.get("volume_ratio", 0.0)
    return_pct = pct(close, entry_price)
    pivot_gain_pct = pct(close, pivot)
    category = item.get("category") or "sector"
    broad_index = category == "broad"
    distribution_days = int(item.get("distribution_days") or 0)
    rs_trend5_pct = float(item.get("rs_trend5_pct") or 0.0)
    rs_weakening_days = int(item.get("rs_weakening_days") or 0)
    below_21ema = bool(ma21 and close < ma21)
    below_50sma = bool(ma50 and close < ma50)
    high_volume = volume_ratio >= ETF_HIGH_VOLUME_RATIO
    strong_volume = volume_ratio >= ETF_STRONG_VOLUME_RATIO
    rs_weakening = rs_trend5_pct < 0 and rs_weakening_days >= min(3, ETF_RS_WEAKENING_DAYS)

    def result(
        status: str,
        label: str,
        explanation: str,
        level: int,
        reasons: list[str],
    ) -> tuple[str, str, str, int, list[str]]:
        return status, label, explanation, level, reasons

    if close <= event["stop_loss"] or return_pct <= -ETF_STOP_LOSS_PCT:
        return result(
            "SELL_CUT_LOSS",
            "매도/손절",
            f"BUY_READY 가정 매수가 대비 -{ETF_STOP_LOSS_PCT:g}% 손절 기준을 이탈했습니다.",
            4,
            ["HARD_STOP"],
        )
    if event.get("sessions_ago", 0) <= ETF_FAILED_BREAKOUT_SESSIONS and pivot and close < pivot:
        if below_21ema and high_volume:
            return result(
                "FAILED_BREAKOUT_WARNING",
                "조기매도 검토",
                "피벗 돌파 후 5거래일 안에 피벗과 21EMA를 거래량 증가와 함께 이탈했습니다.",
                3,
                ["FAILED_BREAKOUT", "21EMA_HIGH_VOLUME_BREAK"],
            )
        return result(
            "FAILED_BREAKOUT_WARNING",
            "돌파 실패 경고",
            "피벗 돌파 직후 다시 피벗 아래로 내려와 돌파 성공 여부를 다시 확인해야 합니다.",
            2,
            ["FAILED_BREAKOUT"],
        )
    if below_50sma and high_volume:
        return result(
            "SELL",
            "매도",
            "50SMA를 거래량 증가와 함께 이탈해 포지션 대부분 또는 전량 매도를 검토합니다.",
            4,
            ["50SMA_HIGH_VOLUME_BREAK"],
        )
    if below_50sma:
        return result(
            "STRONG_SELL_WARNING",
            "강한 매도 경계",
            "50SMA 아래로 내려와 중기 추세 훼손 가능성이 커졌습니다.",
            3,
            ["50SMA_BREAK"],
        )
    if item.get("market_state") == "MARKET_CORRECTION":
        return result(
            "DEFENSE",
            "방어 강화",
            "기준 시장이 조정장으로 바뀌어 신규 추가매수는 멈추고 보유 비중 축소를 우선 검토합니다.",
            3,
            ["MARKET_CORRECTION"],
        )
    if below_21ema and strong_volume and return_pct >= ETF_ROUND_TRIP_TRIGGER_GAIN_PCT:
        return result(
            "PARTIAL_SELL",
            "일부 매도 검토",
            "수익권에서 21EMA를 강한 거래량으로 이탈해 1/3~1/2 일부매도를 검토합니다.",
            3,
            ["21EMA_STRONG_VOLUME_BREAK"],
        )
    if below_21ema and high_volume and return_pct > 0:
        return result(
            "PARTIAL_SELL",
            "일부 매도 검토",
            "수익권에서 21EMA를 거래량 증가와 함께 이탈했습니다.",
            2,
            ["21EMA_HIGH_VOLUME_BREAK"],
        )
    if below_21ema:
        return result(
            "SELL_WARNING",
            "매도 경계",
            "21EMA 아래로 내려와 다음 거래일 회복 여부를 확인해야 합니다.",
            1,
            ["21EMA_BREAK"],
        )
    if (
        event.get("max_unrealized_gain_pct", 0.0) >= ETF_ROUND_TRIP_TRIGGER_GAIN_PCT + 5
        and return_pct <= ETF_ROUND_TRIP_REMAINING_GAIN_PCT + 1
    ):
        return result(
            "ROUND_TRIP_WARNING",
            "수익 반납 경고",
            "한때 큰 미실현 이익이 있었지만 대부분 반납해 초기 손절선까지 기다리지 않는 방어가 필요합니다.",
            2,
            ["ROUND_TRIP_RISK"],
        )
    if (
        event.get("max_unrealized_gain_pct", 0.0) >= ETF_ROUND_TRIP_TRIGGER_GAIN_PCT
        and return_pct <= ETF_ROUND_TRIP_REMAINING_GAIN_PCT
    ):
        return result(
            "ROUND_TRIP_WARNING",
            "수익 반납 경고",
            "미실현 이익이 크게 줄어든 상태라 보유 강도를 낮춰 봅니다.",
            2,
            ["ROUND_TRIP_RISK"],
        )
    if (
        return_pct >= 8
        and event.get("largest_down_day")
        and high_volume
        and event.get("close_location") is not None
        and event["close_location"] < 0.35
    ):
        return result(
            "PARTIAL_SELL",
            "일부 매도 검토",
            "매수 이후 가장 큰 하락일이 거래량 증가와 함께 나왔고 종가가 저가권에 머물렀습니다.",
            2,
            ["LARGEST_DOWN_DAY"],
        )
    if distribution_days >= 4 and below_21ema and rs_trend5_pct < 0:
        return result(
            "PARTIAL_SELL",
            "일부 매도 검토",
            "시장 분산일 부담이 커진 가운데 ETF가 21EMA 아래이고 상대강도도 약해졌습니다.",
            2,
            ["MARKET_DISTRIBUTION_CLUSTER", "RS_WEAKENING"],
        )
    if rs_weakening and not broad_index:
        return result(
            "RS_WEAKENING",
            "상대강도 약화",
            f"{item.get('rs_benchmark_ticker', '기준 ETF')} 대비 최근 {ETF_RS_WEAKENING_DAYS}거래일 상대강도가 약해졌습니다.",
            1,
            ["RS_WEAKENING"],
        )
    if event.get("new_high") and volume_ratio < 1.0:
        return result(
            "LOW_VOLUME_HIGH_WARNING",
            "신고가 거래량 부족",
            "신고가 근처지만 거래량이 평균보다 적어 추세 확인 강도는 낮게 봅니다.",
            1,
            ["LOW_VOLUME_HIGH"],
        )
    if event.get("quick_20pct") and event.get("sessions_ago", 0) < ETF_HOLDING_LOOKBACK_SESSIONS:
        return result(
            "EIGHT_WEEK_HOLD_CANDIDATE",
            "8주 보유 후보",
            "3주 안에 +20% 이상 오른 강한 ETF라 명확한 매도 신호 전까지 8주 보유 후보로 봅니다.",
            0,
            ["EIGHT_WEEK_HOLD_CANDIDATE"],
        )
    if not broad_index and pivot_gain_pct >= ETF_PROFIT_ZONE_END_PCT:
        return result(
            "PROFIT_ZONE_STRONG",
            "이익 보호 강화",
            f"섹터/테마형 ETF가 피벗 대비 +{ETF_PROFIT_ZONE_END_PCT:g}%를 넘어 분할 환매와 이익 보호를 적극 검토합니다.",
            1,
            ["PROFIT_ZONE_STRONG"],
        )
    if not broad_index and pivot_gain_pct >= ETF_PROFIT_ZONE_START_PCT:
        return result(
            "PROFIT_ZONE",
            "이익실현 검토",
            f"섹터/테마형 ETF가 피벗 대비 +{ETF_PROFIT_ZONE_START_PCT:g}~{ETF_PROFIT_ZONE_END_PCT:g}% 이익실현 검토 구간에 들어왔습니다.",
            1,
            ["PROFIT_ZONE"],
        )

    pyramid = evaluate_pyramiding(return_pct)
    if pyramid["status"] != "NO_ADD":
        return result(
            pyramid["status"],
            pyramid["label"],
            pyramid["explanation"],
            0,
            [pyramid["status"]],
        )
    return result(
        "HOLD",
        "보유 유지",
        "손절선, 이익실현 구간, 주요 이동평균 이탈 신호가 아직 확인되지 않았습니다.",
        0,
        [],
    )


def evaluate_pyramiding(return_pct: float) -> dict[str, str]:
    if ETF_PYRAMID2_MIN_PCT <= return_pct <= ETF_PYRAMID2_MAX_PCT:
        return {
            "status": "PYRAMID_READY_2",
            "label": "2차 추가매수 후보",
            "explanation": f"최초 BUY_READY 가정 매수가 대비 +{ETF_PYRAMID2_MIN_PCT:g}~{ETF_PYRAMID2_MAX_PCT:g}% 구간입니다. 하락 물타기가 아니라 수익 포지션에만 추가하는 후보입니다.",
        }
    if ETF_PYRAMID3_MIN_PCT <= return_pct <= ETF_PYRAMID3_MAX_PCT:
        return {
            "status": "PYRAMID_READY_3",
            "label": "3차 추가매수 후보",
            "explanation": f"최초 BUY_READY 가정 매수가 대비 +{ETF_PYRAMID3_MIN_PCT:g}~{ETF_PYRAMID3_MAX_PCT:g}% 구간입니다. 이미 2차 추가가 끝난 포지션이라면 3차 후보입니다.",
        }
    return {"status": "NO_ADD", "label": "추가매수 없음", "explanation": "추가매수 구간이 아닙니다."}


def holding_defense_line(
    item: dict[str, Any],
    event: dict[str, Any],
    return_pct: float,
) -> tuple[float | None, str]:
    ma21 = item.get("ma21")
    pivot = event.get("pivot")
    if return_pct >= 10 and ma21:
        return ma21, "21EMA 방어선"
    if return_pct >= 5 and pivot:
        return pivot, "Pivot/본전 방어선"
    return event.get("stop_loss"), f"-{ETF_STOP_LOSS_PCT:g}% 초기 손절선"


def etf_type_label(category: str) -> str:
    if category == "broad":
        return "Broad Index ETF"
    return "Sector/Theme ETF"


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


def leadership_trend_score(item: dict[str, Any]) -> int:
    score = 0
    if item["ma21"] and item["last_price"] > item["ma21"]:
        score += 3
    if item["ma50"] and item["last_price"] > item["ma50"]:
        score += 3
    if item["ma50_slope"] > 0:
        score += 2
    if item["ma200"] and item["last_price"] > item["ma200"]:
        score += 2
    return min(score, 10)


def leadership_high_score(item: dict[str, Any]) -> int:
    distance = item.get("distance_high252")
    if distance is None:
        return 2
    if distance >= -5:
        return 5
    if distance >= -10:
        return 4
    if distance >= -15:
        return 3
    return 1


def setup_score_components(item: dict[str, Any]) -> dict[str, int]:
    return {
        "유효 베이스": setup_base_score(item),
        "피벗 품질": setup_pivot_quality_score(item),
        "피벗 거리": setup_pivot_distance_score(item),
        "거래량 확인": setup_volume_score(item),
        "리스크 구조": setup_risk_score(item),
    }


def setup_base_score(item: dict[str, Any]) -> int:
    score = 0
    if item["base_exists"]:
        score += 5
    if item["base_days"] >= 25:
        score += 3
    if item["base_depth_pct"] is not None and item["base_depth_pct"] <= 15:
        score += 4
    return min(score, 12)


def setup_pivot_quality_score(item: dict[str, Any]) -> int:
    score = 0
    if item["pivot"]:
        score += 3
    if item["base_exists"]:
        score += 3
    if item["base_depth_pct"] is not None and item["base_depth_pct"] <= 12:
        score += 2
    return min(score, 8)


def setup_pivot_distance_score(item: dict[str, Any]) -> int:
    distance = item["pivot_distance_pct"]
    if distance is None:
        return 0
    if 0 <= distance <= ETF_BUY_ZONE_MAX_PCT:
        return 8
    if -ETF_BUY_ZONE_MAX_PCT <= distance < 0:
        return 6
    if ETF_BUY_ZONE_MAX_PCT < distance <= 10:
        return 3
    if -10 <= distance < -ETF_BUY_ZONE_MAX_PCT:
        return 3
    return 1


def setup_volume_score(item: dict[str, Any]) -> int:
    if item["breakout"] and item["volume_ratio"] >= ETF_VOLUME_THRESHOLD:
        return 8
    score = 0
    if item["breakout"] and item["volume_ratio"] >= 1.0:
        score += 4
    elif item["volume_ratio"] >= 1.0:
        score += 2
    if liquidity_passes(item):
        score += 4
    return min(score, 8)


def setup_risk_score(item: dict[str, Any]) -> int:
    score = 4
    if item["ma50"] and item["last_price"] < item["ma50"]:
        score -= 3
    if item["pivot_distance_pct"] is not None and item["pivot_distance_pct"] > ETF_BUY_ZONE_MAX_PCT:
        score -= 2
    if item["base_depth_pct"] is not None and item["base_depth_pct"] > 20:
        score -= 1
    return max(0, score)


def liquidity_passes(item: dict[str, Any]) -> bool:
    min_volume = float(item.get("min_avg_volume", 0))
    min_value = float(item.get("min_avg_value", 0))
    if min_volume <= 0 or min_value <= 0:
        return False
    return item["avg_volume50"] >= min_volume and item["avg_value50"] >= min_value


def min_avg_value_for_etf(candidate: dict[str, Any]) -> int:
    if candidate["listing"] == "국내상장 ETF":
        return ETF_DOMESTIC_MIN_AVG_VALUE
    return ETF_US_MIN_AVG_VALUE


def classify_etf_candidate(item: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    close = item["last_price"]
    pivot = item["pivot"]
    ma50 = item["ma50"]
    pivot_distance = item["pivot_distance_pct"]

    if any(value is None for value in [close, ma50]) or pivot_distance is None:
        reasons.append("DATA_INCOMPLETE")
    if item["market_state"] != "CONFIRMED_UPTREND":
        reasons.append("MARKET_NOT_CONFIRMED")
    if not liquidity_passes(item):
        reasons.append("LIQUIDITY_FAIL")
    if not (ma50 and close > ma50 and item["ma50_slope"] > 0):
        reasons.append("BELOW_50SMA")
    if not item["base_exists"]:
        reasons.append("NO_VALID_BASE")
    if not pivot:
        reasons.append("NO_VALID_PIVOT")

    if reasons:
        status = highest_priority_status(reasons)
        return etf_classification_result(status, False, reasons)

    if pivot_distance > ETF_BUY_ZONE_MAX_PCT:
        return etf_classification_result("EXTENDED", False, ["ABOVE_BUY_ZONE"])
    if pivot_distance < 0:
        pending = ["BELOW_PIVOT"]
        if pivot_distance < -ETF_BUY_ZONE_MAX_PCT:
            pending.append("FAR_FROM_PIVOT")
        return etf_classification_result("PIVOT_APPROACH", False, pending)
    if item["volume_ratio"] < ETF_VOLUME_THRESHOLD:
        return etf_classification_result("VOLUME_CONFIRM", False, ["VOLUME_NOT_CONFIRMED"])
    return etf_classification_result("BUY_READY", True, [])


def highest_priority_status(reasons: list[str]) -> str:
    return sorted(
        reasons,
        key=lambda reason: ETF_STATUS_PRIORITY.get(reason, 99),
    )[0]


def etf_classification_result(
    status: str,
    eligible: bool,
    reasons: list[str],
) -> dict[str, Any]:
    excluded_statuses = {"DATA_INCOMPLETE", "LIQUIDITY_FAIL", "BELOW_50SMA"}
    display_group = "BUY_NOW" if status == "BUY_READY" else "EXCLUDED" if status in excluded_statuses else "WATCHLIST"
    return {
        "eligible": eligible,
        "ineligibility_reasons": reasons,
        "ineligibility_reason_labels": [ETF_REASON_LABELS.get(reason, reason) for reason in reasons],
        "trading_status": status,
        "display_group": display_group,
        "action_label": ETF_ACTION_LABELS.get(status, "관찰"),
    }


def current_sell_signal(item: dict[str, Any]) -> str:
    close = item["last_price"]
    pivot = item["pivot"]
    ma21 = item["ma21"]
    ma50 = item["ma50"]
    if item["market_state"] == "MARKET_CORRECTION":
        return "시장 조정장: 신규 매수 보류"
    if pivot and close <= pivot * (1 - ETF_STOP_LOSS_PCT / 100):
        return f"피봇 대비 -{ETF_STOP_LOSS_PCT:g}% 손절선 이탈"
    if ma50 and close < ma50 and item["volume_ratio"] >= 1.0:
        return "거래량 동반 50일선 이탈"
    if ma21 and close < ma21 and item["volume_ratio"] >= 1.2:
        return "21EMA 대량거래 이탈: 일부 방어"
    if item["market_state"] == "UPTREND_UNDER_PRESSURE":
        return "시장 분산일 누적: 신규 매수 축소"
    if item["category"] != "broad" and pivot and close >= pivot * (1 + ETF_PROFIT_ZONE_START_PCT / 100):
        return f"섹터/테마 ETF +{ETF_PROFIT_ZONE_START_PCT:g}~{ETF_PROFIT_ZONE_END_PCT:g}% 이익보호 구간"
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

    for reason in item.get("ineligibility_reason_labels", []):
        if reason not in risks:
            risks.append(reason)

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
