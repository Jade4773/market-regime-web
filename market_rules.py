from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class RuleSettings:
    ftd_min_gain_pct: float = 1.25
    distribution_min_loss_pct: float = -0.20
    distribution_window_days: int = 25
    distribution_warning_count: int = 4
    distribution_sell_count: int = 6
    rally_lookback_days: int = 35
    min_ftd_day: int = 4


SETTINGS = RuleSettings()


def analyze_index(meta: dict[str, str], history: pd.DataFrame) -> dict[str, Any]:
    df = prepare(history)
    if len(df) < 60:
        raise ValueError("not enough history")

    rally = find_rally_attempt(df)
    follow_through = find_follow_through(df, rally["start_pos"]) if rally else None
    distribution_days = find_distribution_days(df)
    active_distribution_days = distribution_days[-SETTINGS.distribution_window_days :]
    active_count = sum(1 for item in active_distribution_days if item["is_distribution"])

    regime, score, explanation = classify_regime(
        has_ftd=follow_through is not None,
        distribution_count=active_count,
        close_above_ma50=bool(df.iloc[-1]["close_above_ma50"]),
        close_above_ma200=bool(df.iloc[-1]["close_above_ma200"]),
    )

    latest = df.iloc[-1]
    previous = df.iloc[-2]
    return {
        "name": meta["name"],
        "ticker": meta["ticker"],
        "currency": meta["currency"],
        "last_date": latest.name.strftime("%Y-%m-%d"),
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
        "distribution_count": active_count,
        "distribution_days": [d for d in active_distribution_days if d["is_distribution"]][-8:],
    }


def prepare(history: pd.DataFrame) -> pd.DataFrame:
    df = history.sort_index().copy()
    df["pct_change"] = df["Close"].pct_change() * 100
    df["volume_up"] = df["Volume"] > df["Volume"].shift(1)
    df["value_up"] = df["Value"] > df["Value"].shift(1)
    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma200"] = df["Close"].rolling(200).mean()
    df["close_above_ma50"] = df["Close"] > df["ma50"]
    df["close_above_ma200"] = df["Close"] > df["ma200"]
    return df


def find_rally_attempt(df: pd.DataFrame) -> dict[str, Any] | None:
    window = df.tail(SETTINGS.rally_lookback_days)
    low_pos = int(df.index.get_loc(window["Close"].idxmin()))
    if low_pos >= len(df) - SETTINGS.min_ftd_day:
        return None
    low_row = df.iloc[low_pos]
    return {
        "start_date": low_row.name.strftime("%Y-%m-%d"),
        "start_close": float(low_row["Close"]),
        "start_pos": low_pos,
        "days_since_start": len(df) - low_pos,
    }


def find_follow_through(df: pd.DataFrame, rally_start_pos: int) -> dict[str, Any] | None:
    start = rally_start_pos + SETTINGS.min_ftd_day - 1
    for pos in range(start, len(df)):
        row = df.iloc[pos]
        if row["pct_change"] >= SETTINGS.ftd_min_gain_pct and (
            bool(row["volume_up"]) or bool(row["value_up"])
        ):
            return {
                "date": row.name.strftime("%Y-%m-%d"),
                "gain_pct": float(row["pct_change"]),
                "day_number": pos - rally_start_pos + 1,
                "close": float(row["Close"]),
            }
    return None


def find_distribution_days(df: pd.DataFrame) -> list[dict[str, Any]]:
    days = []
    for _, row in df.tail(SETTINGS.distribution_window_days).iterrows():
        is_distribution = row["pct_change"] <= SETTINGS.distribution_min_loss_pct and (
            bool(row["volume_up"]) or bool(row["value_up"])
        )
        days.append(
            {
                "date": row.name.strftime("%Y-%m-%d"),
                "change_pct": float(row["pct_change"]) if pd.notna(row["pct_change"]) else 0,
                "close": float(row["Close"]),
                "is_distribution": bool(is_distribution),
            }
        )
    return days


def classify_regime(
    has_ftd: bool,
    distribution_count: int,
    close_above_ma50: bool,
    close_above_ma200: bool,
) -> tuple[str, int, str]:
    score = 0
    if has_ftd:
        score += 35
    if close_above_ma50:
        score += 25
    if close_above_ma200:
        score += 20
    score -= min(distribution_count * 8, 48)

    if not has_ftd or distribution_count >= SETTINGS.distribution_sell_count:
        return "매도/방어", max(score, 0), "팔로우쓰루데이가 없거나 분산일 부담이 큽니다."
    if distribution_count >= SETTINGS.distribution_warning_count or not close_above_ma50:
        return "주의", max(score, 0), "상승 추세는 있으나 분산일 또는 50일선 이탈을 확인해야 합니다."
    return "매수 우위", min(score, 100), "팔로우쓰루데이 이후 추세와 수급 조건이 우호적입니다."


def _pct(current: float, previous: float) -> float:
    if not previous or pd.isna(previous):
        return 0.0
    return float((current / previous - 1) * 100)
