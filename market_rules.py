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

    latest = df.iloc[-1]
    previous = df.iloc[-2]
    return {
        "name": meta["name"],
        "ticker": meta["ticker"],
        "volume_ticker": meta.get("volume_ticker", meta["ticker"]),
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
        "ftd_min_gain_pct": meta.get("ftd_min_gain_pct", SETTINGS.ftd_min_gain_pct),
        "distribution_count": active_count,
        "distribution_cluster_count": cluster_count,
        "distribution_clustered": distribution_clustered,
        "distribution_days": active_distribution_days[-8:],
        "expired_distribution_days": [
            item for item in distribution_days if not item["is_active"]
        ][-8:],
    }


def prepare(history: pd.DataFrame) -> pd.DataFrame:
    df = history.sort_index().copy()
    df["pct_change"] = df["Close"].pct_change() * 100
    df["volume_up"] = df["Volume"] > df["Volume"].shift(1)
    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma200"] = df["Close"].rolling(200).mean()
    df["close_above_ma50"] = df["Close"] > df["ma50"]
    df["close_above_ma200"] = df["Close"] > df["ma200"]
    return df


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
                    f"분산일이 {early_distribution_count}회 발생했습니다."
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

    if not has_ftd or ftd_quality == "실패" or distribution_count >= SETTINGS.distribution_sell_count:
        return "매도/방어", max(score, 0), "팔로우쓰루데이가 없거나 분산일 부담이 큽니다."
    if ftd_quality in {"주의", "늦은 확인"}:
        return "주의", max(score, 0), "팔로우쓰루데이 품질을 추가로 확인해야 합니다."
    if distribution_clustered:
        return "주의", max(score, 0), "최근 11거래일에 분산일이 집중되어 있습니다."
    if distribution_count >= SETTINGS.distribution_warning_count or not close_above_ma50:
        return "주의", max(score, 0), "분산일 누적 또는 50일선 이탈을 확인해야 합니다."
    return "매수 우위", min(score, 100), "팔로우쓰루데이 이후 추세와 수급 조건이 우호적입니다."


def _pct(current: float, previous: float) -> float:
    if not previous or pd.isna(previous):
        return 0.0
    return float((current / previous - 1) * 100)
