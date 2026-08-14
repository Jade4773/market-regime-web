from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class RuleSettings:
    ftd_min_gain_pct: float = 1.0
    ftd_ideal_last_day: int = 7
    ftd_early_distribution_window: int = 5
    distribution_min_loss_pct: float = -0.20
    distribution_window_days: int = 25
    distribution_rally_expiry_pct: float = 5.0
    distribution_warning_count: int = 4
    distribution_sell_count: int = 6
    distribution_cluster_window: int = 11
    distribution_cluster_count: int = 4
    stall_max_gain_pct: float = 0.40
    stall_prior_gain_pct: float = 0.20
    rally_lookback_days: int = 60
    min_ftd_day: int = 4


SETTINGS = RuleSettings()


def analyze_index(meta: dict[str, str], history: pd.DataFrame) -> dict[str, Any]:
    df = prepare(history)
    if len(df) < 60:
        raise ValueError("not enough history")

    rally, follow_through = find_active_market_cycle(
        df,
        meta.get("ftd_min_gain_pct", SETTINGS.ftd_min_gain_pct),
    )
    distribution_days = filter_distribution_days_for_current_cycle(
        df,
        find_distribution_days(df),
        follow_through,
    )
    active_distribution_days = [item for item in distribution_days if item["is_active"]]
    active_count = len(active_distribution_days)
    cluster_count = sum(
        1
        for item in active_distribution_days
        if item["age_sessions"] < SETTINGS.distribution_cluster_window
    )
    distribution_clustered = cluster_count >= SETTINGS.distribution_cluster_count

    regime, score, explanation = classify_regime(
        has_ftd=follow_through is not None and follow_through["is_active"],
        ftd_quality=follow_through["quality"] if follow_through else None,
        distribution_count=active_count,
        distribution_clustered=distribution_clustered,
        close_above_ma50=bool(df.iloc[-1]["close_above_ma50"]),
        close_above_ma200=bool(df.iloc[-1]["close_above_ma200"]),
    )
    if follow_through and follow_through["quality"] in {"주의", "늦은 확인", "실패"}:
        explanation = follow_through["quality_reason"]

    latest = df.iloc[-1]
    previous = df.iloc[-2]
    trend_signal = analyze_trend_signal(df)
    risk_signal = analyze_risk_signal(df, active_count, distribution_clustered)
    oneil_signal = {
        "name": "FTD/분산일 확인",
        "opinion": regime,
        "score": score,
        "explanation": explanation,
    }
    signals = {
        "oneil": oneil_signal,
        "trend": trend_signal,
        "risk": risk_signal,
    }
    consensus = build_consensus(signals)
    volume_source = latest.get("VolumeSource", meta.get("volume_ticker", meta["ticker"]))
    if pd.isna(volume_source):
        volume_source = meta.get("volume_ticker", meta["ticker"])
    return {
        "name": meta["name"],
        "ticker": meta["ticker"],
        "volume_ticker": str(volume_source),
        "currency": meta["currency"],
        "last_date": latest.name.strftime("%Y-%m-%d"),
        "data_source": latest.get("DataSource", "Yahoo Finance"),
        "data_status": latest.get("DataStatus", "마감 기준"),
        "source_note": latest.get("SourceNote", "야후 파이낸스 기준"),
        "close": float(latest["Close"]),
        "change_pct": float(latest["pct_change"]),
        "volume": int(latest["Volume"]) if pd.notna(latest["Volume"]) else 0,
        "value": float(latest["Value"]) if pd.notna(latest["Value"]) else 0,
        "volume_change_pct": _pct(latest["Volume"], previous["Volume"]),
        "ma50": float(latest["ma50"]) if pd.notna(latest["ma50"]) else None,
        "ma150": float(latest["ma150"]) if pd.notna(latest["ma150"]) else None,
        "ma200": float(latest["ma200"]) if pd.notna(latest["ma200"]) else None,
        "regime": regime,
        "score": score,
        "explanation": explanation,
        "rally": rally,
        "follow_through": follow_through,
        "ftd_min_gain_pct": meta.get("ftd_min_gain_pct", SETTINGS.ftd_min_gain_pct),
        "distribution_count": active_count,
        "distribution_cluster_count": cluster_count,
        "distribution_clustered": distribution_clustered,
        "distribution_days": active_distribution_days[-8:],
        "expired_distribution_days": [
            item for item in distribution_days if not item["is_active"]
        ][-8:],
        "distribution_scope": distribution_scope_label(follow_through),
        "signals": signals,
        "consensus": consensus,
    }


def filter_distribution_days_for_current_cycle(
    df: pd.DataFrame,
    distribution_days: list[dict[str, Any]],
    follow_through: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not follow_through or not follow_through.get("is_active"):
        return distribution_days

    ftd_pos = follow_through_position(df, follow_through)
    if ftd_pos is None:
        return distribution_days

    return [
        item
        for item in distribution_days
        if item.get("position", -1) > ftd_pos
    ]


def distribution_scope_label(follow_through: dict[str, Any] | None) -> str:
    if follow_through and follow_through.get("is_active"):
        return f"{follow_through['date']} FTD 이후"
    return f"최근 {SETTINGS.distribution_window_days}거래일"


def follow_through_position(
    df: pd.DataFrame, follow_through: dict[str, Any]
) -> int | None:
    if "position" in follow_through:
        return int(follow_through["position"])

    date = pd.to_datetime(follow_through.get("date"))
    matches = df.index.get_indexer([date])
    if len(matches) and matches[0] >= 0:
        return int(matches[0])
    return None


def prepare(history: pd.DataFrame) -> pd.DataFrame:
    df = history.sort_index().copy()
    df["pct_change"] = df["Close"].pct_change() * 100
    df["volume_up"] = df["Volume"] > df["Volume"].shift(1)
    df["ma20"] = df["Close"].rolling(20).mean()
    df["ema21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma150"] = df["Close"].rolling(150).mean()
    df["ma200"] = df["Close"].rolling(200).mean()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df["rsi14"] = 100 - (100 / (1 + rs))
    df["daily_return"] = df["Close"].pct_change()
    df["vol20"] = df["daily_return"].rolling(20).std() * (252**0.5) * 100
    df["vol20_median252"] = df["vol20"].rolling(252).median()
    df["vol20_ratio"] = df["vol20"] / df["vol20_median252"]
    df["return20"] = df["Close"].pct_change(20) * 100
    df["return60"] = df["Close"].pct_change(60) * 100
    df["return63"] = df["Close"].pct_change(63) * 100
    df["return126"] = df["Close"].pct_change(126) * 100
    df["return252"] = df["Close"].pct_change(252) * 100
    df["high252"] = df["Close"].rolling(252).max()
    df["low252"] = df["Close"].rolling(252).min()
    df["distance_high252"] = (df["Close"] / df["high252"] - 1) * 100
    df["distance_low252"] = (df["Close"] / df["low252"] - 1) * 100
    df["ma200_slope20"] = (df["ma200"] / df["ma200"].shift(20) - 1) * 100
    df["ema21_slope10"] = (df["ema21"] / df["ema21"].shift(10) - 1) * 100
    df["ma50_slope20"] = (df["ma50"] / df["ma50"].shift(20) - 1) * 100
    df["close_above_ma50"] = df["Close"] > df["ma50"]
    df["close_above_ma200"] = df["Close"] > df["ma200"]
    return df


def analyze_trend_signal(df: pd.DataFrame) -> dict[str, Any]:
    latest = df.iloc[-1]
    close = float(latest["Close"])
    ema21 = float(latest["ema21"]) if pd.notna(latest["ema21"]) else None
    ma50 = float(latest["ma50"]) if pd.notna(latest["ma50"]) else None
    ma200 = float(latest["ma200"]) if pd.notna(latest["ma200"]) else None
    return20 = float(latest["return20"]) if pd.notna(latest["return20"]) else 0.0
    return60 = float(latest["return60"]) if pd.notna(latest["return60"]) else 0.0
    return120 = float(latest["return126"]) if pd.notna(latest["return126"]) else 0.0
    return252 = float(latest["return252"]) if pd.notna(latest["return252"]) else None
    distance_high252 = (
        float(latest["distance_high252"]) if pd.notna(latest["distance_high252"]) else None
    )
    distance_low252 = (
        float(latest["distance_low252"]) if pd.notna(latest["distance_low252"]) else None
    )
    ma200_slope20 = (
        float(latest["ma200_slope20"]) if pd.notna(latest["ma200_slope20"]) else None
    )
    ema21_slope10 = (
        float(latest["ema21_slope10"]) if pd.notna(latest["ema21_slope10"]) else None
    )
    ma50_slope20 = (
        float(latest["ma50_slope20"]) if pd.notna(latest["ma50_slope20"]) else None
    )
    avg_volume20 = float(df["Volume"].rolling(20).mean().iloc[-1])
    volume = float(latest["Volume"]) if pd.notna(latest["Volume"]) else 0.0
    volume_ratio = volume / avg_volume20 if avg_volume20 else 0.0
    base = detect_trend_base(df)
    pivot = base["pivot"]
    pivot_distance = _pct(close, pivot) if pivot else None
    buy_low = pivot
    buy_high = pivot * 1.05 if pivot else None

    trend_checks = trend_checklist(
        close, ema21, ma50, ma200, ema21_slope10, ma50_slope20, ma200_slope20, distance_high252
    )
    trend_score = round(sum(100 if check["pass"] else 0 for check in trend_checks) / len(trend_checks))
    rs_score = relative_strength_score(return20, return60, return120, distance_high252)
    setup_score = setup_quality_score(base, pivot_distance, volume_ratio)
    score = round((trend_score * 0.45) + (rs_score * 0.30) + (setup_score * 0.25))
    trading_status, action_label, explanation = trend_trading_status(
        close=close,
        ema21=ema21,
        ma50=ma50,
        pivot=pivot,
        pivot_distance=pivot_distance,
        base_exists=base["base_exists"],
        volume_ratio=volume_ratio,
    )

    opinion = trend_opinion_from_status(trading_status, score)
    details = [
        f"Trend {trend_score}/100",
        f"Relative Strength {rs_score}/100",
        f"Setup {setup_score}/100",
        f"Action {action_label}",
    ]

    return {
        "name": "추세/모멘텀",
        "opinion": opinion,
        "score": score,
        "explanation": explanation,
        "details": details,
        "trend_score": trend_score,
        "relative_strength_score": rs_score,
        "setup_score": setup_score,
        "trading_status": trading_status,
        "action_label": action_label,
        "trend_checks": trend_checks,
        "metrics": {
            "20일 수익률": return20,
            "60일 수익률": return60,
            "120일 수익률": return120,
            "12개월 수익률": return252,
            "현재가": close,
            "21EMA": ema21,
            "50일선": ma50,
            "200일선": ma200,
            "21EMA 10거래일 변화": ema21_slope10,
            "50일선 20거래일 변화": ma50_slope20,
            "200일선 20거래일 변화": ma200_slope20,
            "52주 고점 대비": distance_high252,
            "52주 저점 대비": distance_low252,
            "52주 위치": high_position_label(distance_high252),
            "Base 기간": base["base_days"],
            "Base 깊이": base["base_depth_pct"],
            "Pivot": pivot,
            "Pivot 대비": pivot_distance,
            "Buy Zone 하단": buy_low,
            "Buy Zone 상단": buy_high,
            "오늘 거래량": volume,
            "20일 평균 거래량": avg_volume20,
            "Volume Ratio": volume_ratio,
        },
    }


def trend_checklist(
    close: float,
    ema21: float | None,
    ma50: float | None,
    ma200: float | None,
    ema21_slope10: float | None,
    ma50_slope20: float | None,
    ma200_slope20: float | None,
    distance_high252: float | None,
) -> list[dict[str, Any]]:
    return [
        {"label": "가격 > 21EMA", "pass": bool(ema21 and close > ema21)},
        {"label": "가격 > 50SMA", "pass": bool(ma50 and close > ma50)},
        {"label": "가격 > 200SMA", "pass": bool(ma200 and close > ma200)},
        {"label": "21EMA 상승", "pass": bool(ema21_slope10 is not None and ema21_slope10 > 0)},
        {"label": "50SMA 상승", "pass": bool(ma50_slope20 is not None and ma50_slope20 > 0)},
        {"label": "200SMA 상승", "pass": bool(ma200_slope20 is not None and ma200_slope20 > 0)},
        {"label": "52주 고점 -15% 이내", "pass": bool(distance_high252 is not None and distance_high252 >= -15)},
    ]


def relative_strength_score(
    return20: float,
    return60: float,
    return120: float,
    distance_high252: float | None,
) -> int:
    score = 0
    score += score_return_percentile_like(return20, [(8, 25), (4, 18), (0, 10), (-5, 5)])
    score += score_return_percentile_like(return60, [(15, 30), (8, 22), (0, 12), (-8, 5)])
    score += score_return_percentile_like(return120, [(25, 25), (12, 18), (0, 10), (-10, 5)])
    if distance_high252 is None:
        score += 8
    elif distance_high252 >= -5:
        score += 20
    elif distance_high252 >= -15:
        score += 14
    elif distance_high252 >= -25:
        score += 8
    else:
        score += 3
    return min(score, 100)


def score_return_percentile_like(value: float, bands: list[tuple[float, int]]) -> int:
    for threshold, score in bands:
        if value >= threshold:
            return score
    return 0


def detect_trend_base(df: pd.DataFrame) -> dict[str, Any]:
    base_days = 25
    window = df.iloc[-base_days - 1 : -1]
    if len(window) < base_days:
        return {"base_exists": False, "base_days": base_days, "base_depth_pct": None, "pivot": None}

    high = float(window["High"].max())
    low = float(window["Low"].min())
    close = float(df.iloc[-1]["Close"])
    ma50 = float(df.iloc[-1]["ma50"]) if pd.notna(df.iloc[-1]["ma50"]) else None
    depth = (high / low - 1) * 100 if low else None
    upper_half = close >= low + (high - low) * 0.5
    near_ma50 = ma50 is not None and close >= ma50 * 0.97
    base_exists = bool(depth is not None and depth <= 15 and upper_half and near_ma50)
    return {
        "base_exists": base_exists,
        "base_days": base_days,
        "base_depth_pct": depth,
        "pivot": high,
    }


def setup_quality_score(
    base: dict[str, Any],
    pivot_distance: float | None,
    volume_ratio: float,
) -> int:
    score = 0
    if base["base_exists"]:
        score += 30
    elif base["base_depth_pct"] is not None and base["base_depth_pct"] <= 20:
        score += 15
    if pivot_distance is not None:
        if 0 <= pivot_distance <= 5:
            score += 30
        elif -5 <= pivot_distance < 0:
            score += 24
        elif 5 < pivot_distance <= 10:
            score += 12
        elif -10 <= pivot_distance < -5:
            score += 10
    if volume_ratio >= 1.4:
        score += 25
    elif volume_ratio >= 1.0:
        score += 15
    elif volume_ratio >= 0.8:
        score += 8
    if pivot_distance is not None and pivot_distance > 5:
        score -= 15
    return max(0, min(score, 100))


def trend_trading_status(
    *,
    close: float,
    ema21: float | None,
    ma50: float | None,
    pivot: float | None,
    pivot_distance: float | None,
    base_exists: bool,
    volume_ratio: float,
) -> tuple[str, str, str]:
    if ma50 and close < ma50:
        return "RISK_WARNING", "회복 대기", "50SMA 아래라 신규 매수보다 회복 확인이 먼저입니다."
    if ema21 and close < ema21:
        return "RISK_WARNING", "단기 방어", "21EMA 아래로 내려와 단기 추세 방어가 필요합니다."
    if not base_exists or not pivot:
        return "WATCH", "베이스 관찰", "추세는 확인하되 유효한 Base/Pivot이 부족해 관찰 구간입니다."
    if pivot_distance is not None and pivot_distance > 5:
        return "EXTENDED", "추격 금지", "Buy Zone을 넘어 신규 진입은 추격 위험이 큽니다."
    if pivot_distance is not None and pivot_distance < 0:
        return "WAIT", "피벗 접근 대기", "피벗 아래에 있어 돌파와 거래량 확인을 기다립니다."
    if volume_ratio < 1.4:
        return "WAIT", "거래량 확인", "가격은 피벗을 돌파했지만 거래량 확인이 부족합니다."
    return "BUY", "매수 가능", "피벗 돌파와 거래량 확인이 함께 나온 정상 Buy Zone입니다."


def trend_opinion_from_status(status: str, score: int) -> str:
    if status == "BUY":
        return "매수 우위"
    if status in {"EXTENDED", "RISK_WARNING"}:
        return "매도/방어" if score < 55 else "주의"
    if status in {"WAIT", "WATCH"}:
        return "중립/관망" if score >= 45 else "매도/방어"
    return opinion_from_score(score)


def high_position_label(distance_high252: float | None) -> str:
    if distance_high252 is None:
        return "확인 필요"
    if distance_high252 >= -5:
        return "신고가 접근"
    if distance_high252 >= -15:
        return "정상 조정"
    if distance_high252 >= -25:
        return "깊은 조정"
    return "추세 훼손 가능성"


def analyze_risk_signal(
    df: pd.DataFrame, distribution_count: int, distribution_clustered: bool
) -> dict[str, Any]:
    latest = df.iloc[-1]
    close = float(latest["Close"])
    ma50 = float(latest["ma50"]) if pd.notna(latest["ma50"]) else None
    ma200 = float(latest["ma200"]) if pd.notna(latest["ma200"]) else None
    ma200_slope20 = (
        float(latest["ma200_slope20"]) if pd.notna(latest["ma200_slope20"]) else None
    )
    rsi = float(latest["rsi14"]) if pd.notna(latest["rsi14"]) else None
    distance_ma50 = _pct(close, ma50) if ma50 else 0.0
    drawdown_52w = (
        float(latest["distance_high252"]) if pd.notna(latest["distance_high252"]) else None
    )
    vol20 = float(latest["vol20"]) if pd.notna(latest["vol20"]) else None
    vol20_ratio = (
        float(latest["vol20_ratio"]) if pd.notna(latest["vol20_ratio"]) else None
    )

    component_scores = {
        "추세 방어력": score_trend_protection(close, ma50, ma200, ma200_slope20),
        "52주 낙폭": score_drawdown(drawdown_52w),
        "RSI 과열/침체": score_rsi_risk(rsi),
        "변동성 부담": score_volatility(vol20_ratio),
        "분산일 부담": score_distribution_risk(distribution_count, distribution_clustered),
    }
    score = round(sum(component_scores.values()) / len(component_scores))
    details = [f"{name} {value}점" for name, value in component_scores.items()]
    opinion = opinion_from_score(score)
    if opinion == "매수 우위":
        explanation = "추세 훼손, 낙폭, 과열, 변동성, 분산일 부담이 전반적으로 낮습니다."
    elif opinion == "중립/관망":
        explanation = "일부 위험 항목이 올라와 있어 무리한 추격은 피하는 구간입니다."
    else:
        explanation = "여러 위험 항목이 동시에 악화되어 방어적으로 봅니다."

    return {
        "name": "리스크 점검",
        "opinion": opinion,
        "score": score,
        "explanation": explanation,
        "details": details or ["특별한 부담 요인이 크지 않음"],
        "metrics": {
            "추세 방어력 점수": component_scores["추세 방어력"],
            "52주 낙폭 점수": component_scores["52주 낙폭"],
            "RSI 위험 점수": component_scores["RSI 과열/침체"],
            "변동성 점수": component_scores["변동성 부담"],
            "분산일 점수": component_scores["분산일 부담"],
            "RSI 14": rsi,
            "50일선 이격도": distance_ma50,
            "52주 고점 대비": drawdown_52w,
            "20일 연율화 변동성": vol20,
            "변동성 배율": vol20_ratio,
            "활성 분산일": distribution_count,
        },
    }


def score_trend_protection(
    close: float, ma50: float | None, ma200: float | None, ma200_slope20: float | None
) -> int:
    if ma50 and ma200 and close > ma50 and close > ma200 and (ma200_slope20 or 0) > 0:
        return 100
    if ma200 and close > ma200 and (ma200_slope20 or 0) >= 0:
        return 80
    if ma200 and close > ma200:
        return 65
    if ma50 and close > ma50:
        return 50
    return 25


def score_drawdown(drawdown_52w: float | None) -> int:
    if drawdown_52w is None:
        return 50
    if drawdown_52w >= -5:
        return 100
    if drawdown_52w >= -10:
        return 80
    if drawdown_52w >= -15:
        return 60
    if drawdown_52w >= -20:
        return 40
    return 20


def score_rsi_risk(rsi: float | None) -> int:
    if rsi is None:
        return 50
    if 45 <= rsi <= 65:
        return 100
    if 40 <= rsi < 45 or 65 < rsi <= 70:
        return 80
    if 35 <= rsi < 40 or 70 < rsi <= 75:
        return 55
    if 30 <= rsi < 35 or 75 < rsi <= 80:
        return 30
    return 10


def score_volatility(vol20_ratio: float | None) -> int:
    if vol20_ratio is None:
        return 50
    if vol20_ratio <= 0.8:
        return 100
    if vol20_ratio <= 1.0:
        return 85
    if vol20_ratio <= 1.25:
        return 65
    if vol20_ratio <= 1.5:
        return 45
    if vol20_ratio <= 2.0:
        return 25
    return 10


def score_distribution_risk(
    distribution_count: int, distribution_clustered: bool
) -> int:
    if distribution_count <= 1:
        score = 100
    elif distribution_count <= 3:
        score = 75
    elif distribution_count <= 5:
        score = 40
    else:
        score = 10
    if distribution_clustered:
        score = min(score, 40)
    return score


def build_consensus(signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    consensus_signals = [
        signals[key]
        for key in ["oneil", "trend"]
        if key in signals
    ]
    if not consensus_signals:
        consensus_signals = list(signals.values())
    opinions = [signal["opinion"] for signal in consensus_signals]
    average = round(sum(signal["score"] for signal in consensus_signals) / len(consensus_signals))
    buy_count = opinions.count("매수 우위")
    sell_count = opinions.count("매도/방어")

    if sell_count >= 2 or average < 45:
        opinion = "매도/방어"
        explanation = "여러 관점에서 방어적 판단이 우세합니다."
    elif buy_count >= 2 and average >= 65:
        opinion = "매수 우위"
        explanation = "다수 관점이 매수 우위에 동의합니다."
    else:
        opinion = "중립/관망"
        explanation = "의견이 엇갈려 추가 확인이 필요합니다."

    return {
        "name": "종합 의견",
        "opinion": opinion,
        "score": average,
        "explanation": explanation,
        "buy_count": buy_count,
        "sell_count": sell_count,
    }


def opinion_from_score(score: int | float) -> str:
    if score >= 65:
        return "매수 우위"
    if score >= 45:
        return "중립/관망"
    return "매도/방어"


def find_rally_attempt(df: pd.DataFrame) -> dict[str, Any] | None:
    start = max(1, len(df) - SETTINGS.rally_lookback_days)
    active_pos = None
    reset_count = 0
    last_reset_reason = None

    for pos in range(start, len(df)):
        row = df.iloc[pos]
        previous = df.iloc[pos - 1]
        day_range = row["High"] - row["Low"]
        closes_upper_half = bool(
            day_range > 0 and row["Close"] >= row["Low"] + day_range / 2
        )
        starts_rally = bool(row["Close"] > previous["Close"] or closes_upper_half)

        if active_pos is None:
            if starts_rally:
                active_pos = pos
            continue

        if row["Low"] < df.iloc[active_pos]["Low"]:
            reset_count += 1
            last_reset_reason = (
                f"{row.name.strftime('%Y-%m-%d')}에 랠리 첫날 저가 하향 돌파"
            )
            active_pos = pos if starts_rally else None

    if active_pos is None:
        return None
    low_row = df.iloc[active_pos]
    return {
        "start_date": low_row.name.strftime("%Y-%m-%d"),
        "start_close": float(low_row["Close"]),
        "start_low": float(low_row["Low"]),
        "start_pos": active_pos,
        "days_since_start": len(df) - active_pos,
        "reset_count": reset_count,
        "last_reset_reason": last_reset_reason,
    }


def find_active_market_cycle(
    df: pd.DataFrame, min_gain_pct: float
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    active_pos = None
    reset_count = 0
    last_reset_reason = None
    follow_through = None
    distribution_positions: list[int] = []

    for pos in range(1, len(df)):
        row = df.iloc[pos]
        previous = df.iloc[pos - 1]
        starts_rally = is_rally_start(row, previous)
        if is_distribution_signal_at(df, pos):
            distribution_positions.append(pos)

        if active_pos is None:
            if starts_rally:
                active_pos = pos
                follow_through = None
            continue

        rally_low = float(df.iloc[active_pos]["Low"])
        ftd_pos = follow_through_position(df, follow_through) if follow_through else None
        active_distribution_count = len(
            active_distribution_positions(
                df,
                distribution_positions,
                pos,
                min_position=ftd_pos,
            )
        )
        distribution_reset = (
            follow_through is not None
            and active_distribution_count >= SETTINGS.distribution_sell_count
        )
        if row["Low"] < rally_low or distribution_reset:
            reset_count += 1
            last_reset_reason = reset_reason(
                row,
                distribution_reset,
                active_distribution_count,
            )
            active_pos = pos if starts_rally else None
            follow_through = None
            continue

        if follow_through is None and is_follow_through_day(
            row,
            pos,
            active_pos,
            min_gain_pct,
        ):
            follow_through = build_follow_through(df, active_pos, pos, min_gain_pct)

    if active_pos is None:
        return None, None
    return build_rally_attempt(df, active_pos, reset_count, last_reset_reason), follow_through


def reset_reason(
    row: pd.Series,
    distribution_reset: bool,
    active_distribution_count: int,
) -> str:
    if distribution_reset:
        return (
            f"{row.name.strftime('%Y-%m-%d')}에 활성 분산 신호 "
            f"{active_distribution_count}회로 이전 팔로우쓰루데이 소멸"
        )
    return f"{row.name.strftime('%Y-%m-%d')}에 랠리 첫날 저가 하향 돌파"


def find_follow_through(
    df: pd.DataFrame, rally_start_pos: int, min_gain_pct: float
) -> dict[str, Any] | None:
    start = rally_start_pos + SETTINGS.min_ftd_day - 1
    rally_low = float(df.iloc[rally_start_pos]["Low"])
    for pos in range(start, len(df)):
        row = df.iloc[pos]
        if row["pct_change"] >= min_gain_pct and bool(row["volume_up"]):
            day_number = pos - rally_start_pos + 1
            later = df.iloc[pos + 1 :]
            invalidated = bool((later["Low"] < rally_low).any())
            early = df.iloc[
                pos + 1 : pos + 1 + SETTINGS.ftd_early_distribution_window
            ]
            early_distribution_count = sum(
                1
                for _, later_row in early.iterrows()
                if later_row["pct_change"] <= SETTINGS.distribution_min_loss_pct
                and bool(later_row["volume_up"])
            )
            if invalidated:
                quality = "실패"
                quality_reason = "팔로우쓰루데이 이후 랠리 첫날 저가를 하향 돌파했습니다."
            elif early_distribution_count:
                quality = "주의"
                quality_reason = (
                    f"팔로우쓰루데이 후 {SETTINGS.ftd_early_distribution_window}거래일 내 "
                    f"분산일이 {early_distribution_count}회 발생해 신호를 보수적으로 봅니다."
                )
            elif day_number > SETTINGS.ftd_ideal_last_day:
                quality = "늦은 확인"
                quality_reason = "통상적인 4~7일차보다 늦게 확인되었습니다."
            else:
                quality = "양호"
                quality_reason = "4~7일차에 거래량 증가를 동반해 확인되었습니다."
            return {
                "date": row.name.strftime("%Y-%m-%d"),
                "gain_pct": float(row["pct_change"]),
                "required_gain_pct": min_gain_pct,
                "day_number": day_number,
                "position": pos,
                "close": float(row["Close"]),
                "is_active": not invalidated,
                "quality": quality,
                "quality_reason": quality_reason,
                "early_distribution_count": early_distribution_count,
            }
    return None


def is_rally_start(row: pd.Series, previous: pd.Series) -> bool:
    day_range = row["High"] - row["Low"]
    closes_upper_half = bool(
        day_range > 0 and row["Close"] >= row["Low"] + day_range / 2
    )
    return bool(row["Close"] > previous["Close"] or closes_upper_half)


def is_follow_through_day(
    row: pd.Series,
    pos: int,
    rally_start_pos: int,
    min_gain_pct: float,
) -> bool:
    return bool(
        pos >= rally_start_pos + SETTINGS.min_ftd_day - 1
        and row["pct_change"] >= min_gain_pct
        and bool(row["volume_up"])
    )


def build_rally_attempt(
    df: pd.DataFrame,
    active_pos: int,
    reset_count: int,
    last_reset_reason: str | None,
) -> dict[str, Any]:
    low_row = df.iloc[active_pos]
    return {
        "start_date": low_row.name.strftime("%Y-%m-%d"),
        "start_close": float(low_row["Close"]),
        "start_low": float(low_row["Low"]),
        "start_pos": active_pos,
        "days_since_start": len(df) - active_pos,
        "reset_count": reset_count,
        "last_reset_reason": last_reset_reason,
    }


def build_follow_through(
    df: pd.DataFrame,
    rally_start_pos: int,
    ftd_pos: int,
    min_gain_pct: float,
) -> dict[str, Any]:
    row = df.iloc[ftd_pos]
    day_number = ftd_pos - rally_start_pos + 1
    early = df.iloc[ftd_pos + 1 : ftd_pos + 1 + SETTINGS.ftd_early_distribution_window]
    early_distribution_count = sum(
        1
        for _, later_row in early.iterrows()
        if later_row["pct_change"] <= SETTINGS.distribution_min_loss_pct
        and bool(later_row["volume_up"])
    )
    if early_distribution_count:
        quality = "주의"
        quality_reason = (
            f"팔로우쓰루데이 후 {SETTINGS.ftd_early_distribution_window}거래일 내 "
            f"분산일이 {early_distribution_count}회 발생해 신호를 보수적으로 봅니다."
        )
    elif day_number > SETTINGS.ftd_ideal_last_day:
        quality = "늦은 확인"
        quality_reason = "통상적인 4~7일차보다 늦게 확인되었습니다."
    else:
        quality = "양호"
        quality_reason = "4~7일차에 거래량 증가를 동반해 확인되었습니다."
    return {
        "date": row.name.strftime("%Y-%m-%d"),
        "gain_pct": float(row["pct_change"]),
        "required_gain_pct": min_gain_pct,
        "day_number": day_number,
        "position": ftd_pos,
        "close": float(row["Close"]),
        "is_active": True,
        "quality": quality,
        "quality_reason": quality_reason,
        "early_distribution_count": early_distribution_count,
    }


def is_distribution_signal_at(df: pd.DataFrame, pos: int) -> bool:
    row = df.iloc[pos]
    volume_confirms = bool(row["volume_up"])
    is_standard = bool(
        row["pct_change"] <= SETTINGS.distribution_min_loss_pct and volume_confirms
    )

    prior_two = df.iloc[max(0, pos - 2) : pos]
    prior_progress = bool(
        (prior_two["pct_change"] >= SETTINGS.stall_prior_gain_pct).any()
    )
    day_range = row["High"] - row["Low"]
    closes_lower_half = bool(
        day_range > 0 and row["Close"] <= row["Low"] + day_range / 2
    )
    is_stall = bool(
        0 <= row["pct_change"] < SETTINGS.stall_max_gain_pct
        and volume_confirms
        and closes_lower_half
        and prior_progress
    )
    return bool(is_standard or is_stall)


def active_distribution_positions(
    df: pd.DataFrame,
    distribution_positions: list[int],
    current_pos: int,
    min_position: int | None = None,
) -> list[int]:
    active = []
    for position in distribution_positions:
        if min_position is not None and position <= min_position:
            continue
        age_sessions = current_pos - position
        if age_sessions >= SETTINGS.distribution_window_days:
            continue
        later_high = df.iloc[position + 1 : current_pos + 1]["Close"].max()
        rallied_5_pct = bool(
            pd.notna(later_high)
            and later_high
            >= df.iloc[position]["Close"]
            * (1 + SETTINGS.distribution_rally_expiry_pct / 100)
        )
        if not rallied_5_pct:
            active.append(position)
    return active


def find_distribution_days(df: pd.DataFrame) -> list[dict[str, Any]]:
    days = []
    lookback = df.tail(SETTINGS.distribution_window_days + 1)
    start_pos = len(df) - len(lookback)

    for local_pos, (_, row) in enumerate(lookback.iterrows()):
        absolute_pos = start_pos + local_pos
        volume_confirms = bool(row["volume_up"])
        is_standard = bool(
            row["pct_change"] <= SETTINGS.distribution_min_loss_pct and volume_confirms
        )

        prior_two = df.iloc[max(0, absolute_pos - 2) : absolute_pos]
        prior_progress = bool(
            (prior_two["pct_change"] >= SETTINGS.stall_prior_gain_pct).any()
        )
        day_range = row["High"] - row["Low"]
        closes_lower_half = bool(
            day_range > 0 and row["Close"] <= row["Low"] + day_range / 2
        )
        is_stall = bool(
            0 <= row["pct_change"] < SETTINGS.stall_max_gain_pct
            and volume_confirms
            and closes_lower_half
            and prior_progress
        )

        is_distribution = bool(is_standard or is_stall)
        if not is_distribution:
            continue

        age_sessions = len(df) - absolute_pos - 1
        later_high = df.iloc[absolute_pos + 1 :]["Close"].max()
        rallied_5_pct = bool(
            pd.notna(later_high)
            and later_high
            >= row["Close"] * (1 + SETTINGS.distribution_rally_expiry_pct / 100)
        )
        is_active = bool(
            age_sessions < SETTINGS.distribution_window_days and not rallied_5_pct
        )
        expiry_reason = None
        if not is_active:
            expiry_reason = (
                "25거래일 경과"
                if age_sessions >= SETTINGS.distribution_window_days
                else "종가 대비 5% 상승"
            )

        days.append(
            {
                "date": row.name.strftime("%Y-%m-%d"),
                "change_pct": float(row["pct_change"]),
                "close": float(row["Close"]),
                "type": "스톨링" if is_stall else "분산일",
                "position": absolute_pos,
                "is_active": is_active,
                "age_sessions": age_sessions,
                "expiry_reason": expiry_reason,
            }
        )
    return days


def classify_regime(
    has_ftd: bool,
    ftd_quality: str | None,
    distribution_count: int,
    distribution_clustered: bool,
    close_above_ma50: bool,
    close_above_ma200: bool,
) -> tuple[str, int, str]:
    score = 0
    if has_ftd:
        score += 35
        if ftd_quality == "주의":
            score -= 10
        elif ftd_quality == "늦은 확인":
            score -= 5
    if close_above_ma50:
        score += 25
    if close_above_ma200:
        score += 20
    score -= min(distribution_count * 8, 48)

    if not has_ftd or ftd_quality == "실패":
        return "매도/방어", max(score, 0), "현재 유효한 팔로우쓰루데이가 확인되지 않습니다."
    if distribution_count >= SETTINGS.distribution_sell_count:
        return "매도/방어", max(score, 0), f"활성 분산 신호가 {distribution_count}회로 매도 압력이 큽니다."
    if ftd_quality in {"주의", "늦은 확인"}:
        return "주의", max(score, 0), "팔로우쓰루데이 신호를 보수적으로 확인해야 합니다."
    if distribution_clustered:
        return "주의", max(score, 0), "최근 11거래일에 분산일이 집중되어 있습니다."
    if distribution_count >= SETTINGS.distribution_warning_count and not close_above_ma50:
        return "주의", max(score, 0), "분산일 누적과 50일선 이탈을 함께 확인해야 합니다."
    if distribution_count >= SETTINGS.distribution_warning_count:
        return "주의", max(score, 0), "분산일 누적을 확인해야 합니다."
    if not close_above_ma50:
        return "주의", max(score, 0), "50일선 이탈을 확인해야 합니다."
    return "매수 우위", min(score, 100), "팔로우쓰루데이 이후 추세와 수급 조건이 우호적입니다."


def _pct(current: float, previous: float) -> float:
    if not previous or pd.isna(previous):
        return 0.0
    return float((current / previous - 1) * 100)
