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

    rally = find_rally_attempt(df)
    follow_through = (
        find_follow_through(
            df,
            rally["start_pos"],
            meta.get("ftd_min_gain_pct", SETTINGS.ftd_min_gain_pct),
        )
        if rally
        else None
    )
    distribution_days = find_distribution_days(df)
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
        "name": "윌리엄 오닐",
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
    return {
        "name": meta["name"],
        "ticker": meta["ticker"],
        "volume_ticker": meta.get("volume_ticker", meta["ticker"]),
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
        "signals": signals,
        "consensus": consensus,
    }


def prepare(history: pd.DataFrame) -> pd.DataFrame:
    df = history.sort_index().copy()
    df["pct_change"] = df["Close"].pct_change() * 100
    df["volume_up"] = df["Volume"] > df["Volume"].shift(1)
    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma200"] = df["Close"].rolling(200).mean()
    df["ma20"] = df["Close"].rolling(20).mean()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df["rsi14"] = 100 - (100 / (1 + rs))
    df["return20"] = df["Close"].pct_change(20) * 100
    df["return60"] = df["Close"].pct_change(60) * 100
    df["close_above_ma50"] = df["Close"] > df["ma50"]
    df["close_above_ma200"] = df["Close"] > df["ma200"]
    return df


def analyze_trend_signal(df: pd.DataFrame) -> dict[str, Any]:
    latest = df.iloc[-1]
    close = float(latest["Close"])
    ma20 = float(latest["ma20"]) if pd.notna(latest["ma20"]) else None
    ma50 = float(latest["ma50"]) if pd.notna(latest["ma50"]) else None
    ma200 = float(latest["ma200"]) if pd.notna(latest["ma200"]) else None
    return20 = float(latest["return20"]) if pd.notna(latest["return20"]) else 0.0
    return60 = float(latest["return60"]) if pd.notna(latest["return60"]) else 0.0

    score = 0
    reasons = []
    if ma20 and close > ma20:
        score += 20
        reasons.append("20일선 위")
    if ma50 and close > ma50:
        score += 25
        reasons.append("50일선 위")
    if ma50 and ma200 and ma50 > ma200:
        score += 25
        reasons.append("50일선이 200일선 위")
    if return20 > 0:
        score += 15
        reasons.append("20거래일 수익률 양호")
    if return60 > 0:
        score += 15
        reasons.append("60거래일 수익률 양호")

    opinion = opinion_from_score(score)
    if opinion == "매수 우위":
        explanation = "중기 추세와 최근 모멘텀이 대체로 우호적입니다."
    elif opinion == "중립/관망":
        explanation = "추세 조건이 엇갈려 방향 확인이 필요합니다."
    else:
        explanation = "주요 이동평균 또는 최근 모멘텀이 약합니다."

    return {
        "name": "추세/모멘텀",
        "opinion": opinion,
        "score": score,
        "explanation": explanation,
        "details": reasons or ["확인 가능한 우호 조건이 제한적"],
        "metrics": {
            "20일 수익률": return20,
            "60일 수익률": return60,
            "20일선": ma20,
            "50일선": ma50,
            "200일선": ma200,
        },
    }


def analyze_risk_signal(
    df: pd.DataFrame, distribution_count: int, distribution_clustered: bool
) -> dict[str, Any]:
    latest = df.iloc[-1]
    close = float(latest["Close"])
    ma50 = float(latest["ma50"]) if pd.notna(latest["ma50"]) else None
    rsi = float(latest["rsi14"]) if pd.notna(latest["rsi14"]) else None
    distance_ma50 = _pct(close, ma50) if ma50 else 0.0

    score = 60
    details = []
    if ma50 and close > ma50:
        score += 15
        details.append("50일선 위에서 유지")
    else:
        score -= 20
        details.append("50일선 아래 또는 근접")
    if rsi is not None:
        if 40 <= rsi <= 70:
            score += 15
            details.append("RSI가 과열·침체 구간 밖")
        elif rsi > 75:
            score -= 20
            details.append("RSI 과열권")
        elif rsi < 35:
            score -= 15
            details.append("RSI 침체권")
    if distance_ma50 > 12:
        score -= 30
        details.append("50일선 대비 단기 과열")
    if distance_ma50 > 20:
        score -= 15
        details.append("50일선 대비 이격도 매우 큼")
    if distribution_count >= SETTINGS.distribution_warning_count:
        score -= 20
        details.append("분산일 누적")
    if distribution_clustered:
        score -= 15
        details.append("최근 분산일 집중")

    score = max(0, min(score, 100))
    opinion = opinion_from_score(score)
    if opinion == "매수 우위":
        explanation = "과열과 매도 압력 부담이 제한적입니다."
    elif opinion == "중립/관망":
        explanation = "일부 부담 요인이 있어 무리한 추격은 피하는 구간입니다."
    else:
        explanation = "과열, 추세 이탈, 분산일 부담 중 하나 이상이 큽니다."

    return {
        "name": "리스크 점검",
        "opinion": opinion,
        "score": score,
        "explanation": explanation,
        "details": details or ["특별한 부담 요인이 크지 않음"],
        "metrics": {
            "RSI 14": rsi,
            "50일선 이격도": distance_ma50,
            "활성 분산일": distribution_count,
        },
    }


def build_consensus(signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    opinions = [signal["opinion"] for signal in signals.values()]
    average = round(sum(signal["score"] for signal in signals.values()) / len(signals))
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
                "close": float(row["Close"]),
                "is_active": not invalidated,
                "quality": quality,
                "quality_reason": quality_reason,
                "early_distribution_count": early_distribution_count,
            }
    return None


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
    if distribution_count >= SETTINGS.distribution_warning_count or not close_above_ma50:
        return "주의", max(score, 0), "분산일 누적 또는 50일선 이탈을 확인해야 합니다."
    return "매수 우위", min(score, 100), "팔로우쓰루데이 이후 추세와 수급 조건이 우호적입니다."


def _pct(current: float, previous: float) -> float:
    if not previous or pd.isna(previous):
        return 0.0
    return float((current / previous - 1) * 100)
