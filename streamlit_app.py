from __future__ import annotations

from typing import Any

import streamlit as st

from market_data import get_market_snapshot


st.set_page_config(
    page_title="Market Regime",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def format_number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:,.{digits}f}"


def format_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}%"


def badge_style(regime: str) -> str:
    if "매수" in regime:
        return "background:#e8f3ff;color:#1b64da;"
    if "중립" in regime or "관망" in regime:
        return "background:#eef4fb;color:#4d6f9d;"
    if "주의" in regime:
        return "background:#fff0f0;color:#e5484d;"
    return "background:#ffe8e8;color:#d92d35;"


def regime_tone(regime: str) -> str:
    if "매수" in regime:
        return "positive"
    if "중립" in regime or "관망" in regime:
        return "neutral"
    if "주의" in regime:
        return "caution"
    return "negative"


def card_explanation(item: dict[str, Any]) -> str:
    follow_through = item.get("follow_through")
    if follow_through and follow_through.get("quality") == "주의":
        count = follow_through.get("early_distribution_count", 0)
        return (
            f"팔로우쓰루데이 후 5거래일 내 분산일이 {count}회 발생해 "
            "신호를 보수적으로 봅니다."
        )
    return item["explanation"]


def render_market_card(item: dict[str, Any]) -> None:
    if item.get("error"):
        st.subheader(item["name"])
        st.error(item["error"])
        return

    ftd = item.get("follow_through")
    ftd_summary = (
        f"{ftd['date']} · {ftd['day_number']}일차 · {ftd.get('quality', '기존 신호')}"
        if ftd
        else "최근 신호 없음"
    )
    st.markdown(
        f"""
        <div class="market-card">
          <div class="card-head">
            <div>
              <h3>{item["name"]}</h3>
              <p>{item["ticker"]} · {item["last_date"]}</p>
            </div>
            <span class="regime-badge" style="{badge_style(item["regime"])}">{item["regime"]}</span>
          </div>
          <div class="price-row">
            <strong>{format_number(item["close"])}</strong>
            <span class="{'up' if item["change_pct"] >= 0 else 'down'}">{format_pct(item["change_pct"])}</span>
          </div>
          <p class="explain">{card_explanation(item)}</p>
          <div class="signal-row">
            <span>시장 신호</span>
            <div class="meter"><span style="width:{item["score"]}%"></span></div>
            <strong>{item["score"]}</strong>
          </div>
          <div class="stat-grid">
            <div><span>분산일</span><strong>{item['distribution_count']}회</strong></div>
            <div><span>거래량 변화</span><strong>{format_pct(item["volume_change_pct"])}</strong></div>
            <div><span>50일선</span><strong>{format_number(item["ma50"])}</strong></div>
          </div>
          <div class="ftd-line">
            <span>팔로우쓰루데이</span><strong>{ftd_summary}</strong>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if item["distribution_clustered"]:
        st.warning("최근 11거래일에 분산 신호가 집중되어 있습니다.")

    if ftd:
        ftd_quality_reason = ftd.get(
            "quality_reason", "이전 계산 결과입니다. 다음 데이터 갱신 시 품질이 재평가됩니다."
        )
        st.caption(ftd_quality_reason)
    else:
        st.caption("팔로우쓰루데이: 최근 랠리 시도 이후 확인 안 됨")
    st.caption(
        f"거래량 기준 {item['volume_ticker']} · "
        f"최근 11거래일 분산 신호 {item['distribution_cluster_count']}회"
    )

    rally = item.get("rally")
    if rally:
        with st.expander("랠리 시도 상태"):
            st.write(
                f"시작일: {rally['start_date']} · 첫날 저가: "
                f"{format_number(rally.get('start_low'))} · "
                f"현재 {rally['days_since_start']}일차"
            )
            st.write(
                f"최근 60거래일 내 저가 돌파로 재시작: "
                f"{rally.get('reset_count', 0)}회"
            )
            if rally.get("last_reset_reason"):
                st.caption(rally["last_reset_reason"])

    distribution_days = item.get("distribution_days") or []
    if distribution_days:
        with st.expander("최근 분산일"):
            st.dataframe(
                [
                    {
                        "날짜": day["date"],
                        "유형": day["type"],
                        "등락률": format_pct(day["change_pct"]),
                        "종가": format_number(day["close"]),
                        "경과": f"{day['age_sessions']}거래일",
                    }
                    for day in distribution_days
                ],
                hide_index=True,
                use_container_width=True,
            )
    else:
        st.caption("최근 25거래일 내 분산일 없음")

    expired = item.get("expired_distribution_days") or []
    if expired:
        with st.expander("제거된 분산 신호"):
            st.dataframe(
                [
                    {
                        "날짜": day["date"],
                        "유형": day["type"],
                        "제거 사유": day["expiry_reason"],
                    }
                    for day in expired
                ],
                hide_index=True,
                use_container_width=True,
            )


def render_consensus_card(item: dict[str, Any]) -> None:
    if item.get("error"):
        st.subheader(item["name"])
        st.error(item["error"])
        return

    consensus = item["consensus"]
    signals = item["signals"]
    st.markdown(
        f"""
        <div class="market-card">
          <div class="card-head">
            <div>
              <h3>{item["name"]}</h3>
              <p>{item["ticker"]} · {item["last_date"]}</p>
            </div>
            <span class="regime-badge" style="{badge_style(consensus["opinion"])}">{consensus["opinion"]}</span>
          </div>
          <div class="price-row">
            <strong>{format_number(item["close"])}</strong>
            <span class="{'up' if item["change_pct"] >= 0 else 'down'}">{format_pct(item["change_pct"])}</span>
          </div>
          <p class="explain">{consensus["explanation"]}</p>
          <div class="signal-row">
            <span>종합 점수</span>
            <div class="meter"><span style="width:{consensus["score"]}%"></span></div>
            <strong>{consensus["score"]}</strong>
          </div>
          <div class="opinion-list">
            <div><span>윌리엄 오닐</span><strong class="{regime_tone(signals["oneil"]["opinion"])}">{signals["oneil"]["opinion"]}</strong></div>
            <div><span>추세/모멘텀</span><strong class="{regime_tone(signals["trend"]["opinion"])}">{signals["trend"]["opinion"]}</strong></div>
            <div><span>리스크 점검</span><strong class="{regime_tone(signals["risk"]["opinion"])}">{signals["risk"]["opinion"]}</strong></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_signal_card(item: dict[str, Any], signal_key: str) -> None:
    if item.get("error"):
        st.subheader(item["name"])
        st.error(item["error"])
        return

    signal = item["signals"][signal_key]
    metrics = signal.get("metrics", {})
    details = signal.get("details", [])
    st.markdown(
        f"""
        <div class="market-card">
          <div class="card-head">
            <div>
              <h3>{item["name"]}</h3>
              <p>{signal["name"]}</p>
            </div>
            <span class="regime-badge" style="{badge_style(signal["opinion"])}">{signal["opinion"]}</span>
          </div>
          <p class="explain">{signal["explanation"]}</p>
          <div class="signal-row">
            <span>관점 점수</span>
            <div class="meter"><span style="width:{signal["score"]}%"></span></div>
            <strong>{signal["score"]}</strong>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(" · ".join(details))
    if metrics:
        st.dataframe(
            [
                {
                    "지표": name,
                    "값": format_pct(value)
                    if "수익률" in name or "이격도" in name
                    else format_number(value)
                    if isinstance(value, (int, float))
                    else value,
                }
                for name, value in metrics.items()
            ],
            hide_index=True,
            use_container_width=True,
        )


def dashboard() -> None:
    st.markdown(
        """
        <style>
        :root { color-scheme: light; }
        .stApp { background: #f3f7fd; color: #172b4d; }
        .block-container { max-width: 1120px; padding-top: 38px; padding-bottom: 72px; }
        h1, h2, h3, p { letter-spacing: 0; }
        h1 { font-size: 34px !important; line-height: 1.25 !important; margin-bottom: 8px !important; }
        [data-testid="stCaptionContainer"] { color: #8b95a1; }
        .page-kicker { color: #3182f6; font-size: 14px; font-weight: 700; margin-bottom: 8px; }
        .page-subtitle { color: #6f87a8; font-size: 16px; margin: 0 0 28px; }
        .summary-card {
            background: #3182f6;
            border: 1px solid #3182f6;
            border-radius: 8px;
            padding: 24px;
            margin: 2px 0 24px;
            box-shadow: 0 8px 24px rgba(49,130,246,.14);
        }
        .summary-label { color: #dbeaff; font-size: 13px; font-weight: 700; margin-bottom: 8px; }
        .summary-title { font-size: 26px; font-weight: 800; margin-bottom: 8px; }
        .summary-title.positive { color: #ffffff; }
        .summary-title.neutral { color: #eaf3ff; }
        .summary-title.caution, .summary-title.negative { color: #ffd2d4; }
        .summary-copy { color: #eaf3ff; font-size: 15px; margin: 0; }
        .region-card {
            min-height: 142px;
            background: #ffffff;
            border: 1px solid #e2ebf7;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 22px;
            box-shadow: 0 2px 10px rgba(35,76,126,.04);
        }
        .region-top { display:flex; justify-content:space-between; gap:12px; align-items:center; }
        .region-name { color:#6f87a8; font-size:14px; font-weight:700; }
        .region-regime { color:#172b4d; font-size:22px; font-weight:800; margin:10px 0 7px; }
        .region-regime.neutral { color:#4d6f9d; }
        .region-regime.caution, .region-regime.negative { color:#d92d35; }
        .region-copy { color:#8295b1; font-size:13px; line-height:1.55; margin:0; }
        .section-title { font-size: 20px; font-weight: 800; margin: 26px 0 14px; }
        .market-card {
            border: 1px solid #e2ebf7;
            border-radius: 8px;
            padding: 22px;
            background: #ffffff;
            margin-bottom: 10px;
            box-shadow: 0 2px 10px rgba(35,76,126,.04);
        }
        .card-head, .price-row {
            display: flex;
            justify-content: space-between;
            gap: 14px;
            align-items: flex-start;
        }
        .card-head h3 { margin: 0 0 4px; font-size: 20px; color:#172b4d; }
        .card-head p { color: #8ba0bc; margin: 0; font-size:13px; }
        .explain { color:#6f87a8; margin:12px 0 0; font-size:14px; line-height:1.55; min-height:44px; }
        .regime-badge {
            border-radius: 999px;
            padding: 6px 10px;
            font-size: 13px;
            font-weight: 800;
            white-space: nowrap;
        }
        .price-row { align-items: baseline; margin-top: 22px; }
        .price-row strong { font-size: 32px; line-height: 1; color:#172b4d; }
        .up { color: #3182f6; font-weight: 800; }
        .down { color: #e5484d; font-weight: 800; }
        .signal-row { display:grid; grid-template-columns:auto 1fr auto; gap:10px; align-items:center; margin-top:18px; }
        .signal-row > span { color:#8ba0bc; font-size:12px; }
        .signal-row > strong { color:#4d6f9d; font-size:12px; }
        .meter {
            height: 5px;
            background: #e8eef7;
            border-radius: 999px;
            overflow: hidden;
        }
        .meter span { display: block; height: 100%; background: #3182f6; border-radius:999px; }
        .stat-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:1px; background:#e5edf8; margin-top:18px; }
        .stat-grid > div { background:#fff; padding:14px 10px 10px 0; min-width:0; }
        .stat-grid span, .ftd-line span { display:block; color:#8ba0bc; font-size:12px; margin-bottom:5px; }
        .stat-grid strong { display:block; color:#28466f; font-size:16px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .ftd-line { background:#f0f6ff; border-radius:8px; padding:13px 14px; margin-top:16px; }
        .ftd-line strong { color:#416b9f; font-size:13px; font-weight:700; }
        .opinion-list { display:grid; gap:10px; margin-top:18px; }
        .opinion-list > div {
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:12px;
            padding:12px 0;
            border-top:1px solid #e5edf8;
        }
        .opinion-list span { color:#8ba0bc; font-size:13px; }
        .opinion-list strong { color:#172b4d; font-size:14px; }
        .opinion-list strong.positive { color:#1b64da; }
        .opinion-list strong.neutral { color:#4d6f9d; }
        .opinion-list strong.caution, .opinion-list strong.negative { color:#d92d35; }
        div[data-testid="stExpander"] { background:#fff; border-color:#e2ebf7; border-radius:8px; }
        div[data-testid="stAlert"] { border-radius:8px; }
        @media (max-width: 700px) {
            .block-container { padding: 24px 16px 56px; }
            h1 { font-size: 28px !important; }
            .summary-card { padding:20px; }
            .summary-title { font-size:23px; }
            .region-card { min-height:0; }
            .market-card { padding:18px; }
            .price-row strong { font-size:29px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="page-kicker">O’NEIL MARKET PULSE</div>', unsafe_allow_html=True)
    st.title("지수별 매수/매도 국면")
    st.markdown(
        '<p class="page-subtitle">추세와 수급 신호를 한눈에 확인하세요.</p>',
        unsafe_allow_html=True,
    )
    render_market_dashboard()


def render_market_dashboard() -> None:
    with st.spinner("야후 파이낸스에서 데이터를 가져오는 중입니다."):
        snapshot = get_market_snapshot()

    items = list(snapshot["items"].values())
    valid_items = [item for item in items if not item.get("error")]
    overview = build_overview(valid_items)
    overview_tab, oneil_tab, trend_tab, risk_tab = st.tabs(
        ["개요", "윌리엄 오닐", "추세/모멘텀", "리스크 점검"]
    )

    with overview_tab:
        render_overview_tab(valid_items, overview)

    with oneil_tab:
        render_oneil_tab(snapshot)

    with trend_tab:
        render_signal_tab(items, "trend", "추세/모멘텀")

    with risk_tab:
        render_signal_tab(items, "risk", "리스크 점검")

    st.caption(f"데이터는 최대 {snapshot['cache_seconds']}초 동안 캐시됩니다.")


def build_overview(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {
            "opinion": "데이터 오류",
            "score": 0,
            "explanation": "시장 데이터를 확인할 수 없습니다.",
        }

    average = round(sum(item["consensus"]["score"] for item in items) / len(items))
    defensive_count = sum(item["consensus"]["opinion"] == "매도/방어" for item in items)
    buy_count = sum(item["consensus"]["opinion"] == "매수 우위" for item in items)

    if defensive_count >= 2 or average < 45:
        opinion = "시장 전반 방어 우선"
        explanation = "여러 지수의 종합 의견에서 방어 신호가 우세합니다."
    elif buy_count >= 3 and average >= 65:
        opinion = "시장 전반 매수 우위"
        explanation = "대부분 지수에서 매수 우위 의견이 확인됩니다."
    else:
        opinion = "시장 전반 중립/관망"
        explanation = "지수와 관점별 의견이 엇갈려 확인이 더 필요합니다."

    return {"opinion": opinion, "score": average, "explanation": explanation}


def render_overview_tab(items: list[dict[str, Any]], overview: dict[str, Any]) -> None:
    st.markdown(
        f"""
        <div class="summary-card">
          <div class="summary-label">오늘의 종합 판단</div>
          <div class="summary-title {regime_tone(overview['opinion'])}">{overview["opinion"]}</div>
          <p class="summary-copy">{overview["explanation"]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for row_start in range(0, len(items), 2):
        cols = st.columns(2)
        for col, item in zip(cols, items[row_start : row_start + 2]):
            with col:
                render_consensus_card(item)


def render_oneil_tab(snapshot: dict[str, Any]) -> None:
    summary = snapshot["market_summary"]
    st.markdown(
        f"""
        <div class="summary-card">
          <div class="summary-label">윌리엄 오닐 관점</div>
          <div class="summary-title {regime_tone(summary['regime'])}">{summary["regime"]}</div>
          <p class="summary-copy">{summary["explanation"]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_region_summary(summary)
    items = list(snapshot["items"].values())
    for row_start in range(0, len(items), 2):
        section_name = "한국 시장" if row_start == 0 else "미국 시장"
        st.markdown(f'<div class="section-title">{section_name}</div>', unsafe_allow_html=True)
        cols = st.columns(2)
        for col, item in zip(cols, items[row_start : row_start + 2]):
            with col:
                render_market_card(item)

    render_oneil_rules()


def render_region_summary(summary: dict[str, Any]) -> None:
    region_cols = st.columns(2)
    for col, key in zip(region_cols, ["korea", "united_states"]):
        region = summary["regions"][key]
        with col:
            ftd_status = "FTD 확인" if region["has_valid_ftd"] else "FTD 미확인"
            st.markdown(
                f"""
                <div class="region-card">
                  <div class="region-top">
                    <span class="region-name">{region['name']} 시장</span>
                    <span class="regime-badge" style="{badge_style(region['regime'])}">{ftd_status}</span>
                  </div>
                  <div class="region-regime {regime_tone(region['regime'])}">{region['regime']}</div>
                  <p class="region-copy">{region['explanation']}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_signal_tab(items: list[dict[str, Any]], signal_key: str, title: str) -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    for row_start in range(0, len(items), 2):
        cols = st.columns(2)
        for col, item in zip(cols, items[row_start : row_start + 2]):
            with col:
                render_signal_card(item, signal_key)

    with st.expander(f"{title} 판정 기준"):
        if signal_key == "trend":
            st.markdown(
                """
                - **20일선·50일선:** 현재 가격이 주요 이동평균 위에 있으면 우호적으로 봅니다.
                - **50일선과 200일선:** 50일선이 200일선보다 높으면 중기 상승 추세로 봅니다.
                - **20·60거래일 수익률:** 최근 상승 탄력이 살아 있는지 확인합니다.
                """
            )
        else:
            st.markdown(
                """
                - **RSI 14:** 40~70은 안정, 75 이상은 단기 과열로 봅니다.
                - **50일선 이격도:** 50일선 대비 지나치게 멀어지면 추격 매수 부담으로 봅니다.
                - **분산일:** 분산일 누적과 집중 여부를 리스크 요인으로 반영합니다.
                """
            )


def render_oneil_rules() -> None:
    st.markdown('<div class="section-title">판정 기준</div>', unsafe_allow_html=True)
    with st.expander("분산일 판정 기준"):
        st.markdown(
            """
            - **분산일:** 지수가 0.2% 이상 하락하고 ETF 대체 거래량이 전일보다 증가
            - **스톨링:** 0% 이상 0.4% 미만 상승, 일중 범위 하단 절반 마감, 거래량 증가,
              직전 2일 중 하루가 0.2% 이상 상승
            - **제거:** 발생 후 25거래일 경과 또는 해당 종가 대비 지수가 5% 상승
            - **집중 경고:** 최근 11거래일 내 활성 분산 신호 4회 이상
            """
        )
    with st.expander("팔로우쓰루데이 판정 기준"):
        st.info(
            "신호 평가는 팔로우쓰루데이가 얼마나 믿을 만한지 보여줍니다. "
            "발생 시점과 발생 직후 시장 움직임을 함께 확인합니다."
        )
        st.markdown(
            """
            - **랠리 첫날:** 지수가 전일보다 상승 마감하거나 일중 범위 상단 절반에서 마감
            - **카운트 재시작:** 이후 지수가 랠리 첫날 저가를 하향 돌파
            - **팔로우쓰루데이:** 랠리 4일차 이후 지수가 최소 1% 상승하고 ETF 대체 거래량 증가
            - **미국시장 확인:** 나스닥종합 또는 S&P 500 중 하나에서 유효 팔로우쓰루데이가 발생하면 인정
            - **신호 평가 - 양호:** 통상적인 4~7일차에 거래량 증가와 함께 발생
            - **신호 평가 - 주의:** 발생 후 5거래일 안에 분산일이 나타나 매도 압력이 확인됨
            - **신호 평가 - 늦은 확인:** 랠리 8일차 이후 늦게 발생해 일반적인 신호보다 보수적으로 판단
            - **신호 평가 - 실패:** 발생 후 랠리 첫날 저가를 깨서 상승 시도가 무효화됨
            """
        )


def main() -> None:
    dashboard()


if __name__ == "__main__":
    main()
