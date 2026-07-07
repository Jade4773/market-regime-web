from __future__ import annotations

from typing import Any

import streamlit as st

from market_pulse.data import get_market_snapshot


TAB_LABELS = {
    "overview": "개요",
    "oneil": "윌리엄 오닐",
    "trend": "추세/모멘텀",
    "risk": "리스크 점검",
}


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


def data_meta_text(item: dict[str, Any]) -> str:
    source = item.get("data_source", "Yahoo Finance")
    status = item.get("data_status", "마감 기준")
    return f"{item['ticker']} · {item['last_date']} · {source} · {status}"


def data_source_badge(item: dict[str, Any]) -> str:
    source = item.get("data_source", "Yahoo Finance")
    status = item.get("data_status", "마감 기준")
    if source == "Npay 증권":
        return f'<span class="source-badge fallback">Npay 대체 · {status}</span>'
    if status == "장중 잠정":
        return f'<span class="source-badge provisional">장중 잠정</span>'
    return '<span class="source-badge">Yahoo</span>'


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
              <p>{data_meta_text(item)}</p>
            </div>
            <div class="badge-stack">
              {data_source_badge(item)}
              <span class="regime-badge" style="{badge_style(item["regime"])}">{item["regime"]}</span>
            </div>
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
              <p>{data_meta_text(item)}</p>
            </div>
            <div class="badge-stack">
              {data_source_badge(item)}
              <span class="regime-badge" style="{badge_style(consensus["opinion"])}">{consensus["opinion"]}</span>
            </div>
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
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_signal_jump_buttons(signals, item["ticker"])


def render_signal_jump_buttons(signals: dict[str, Any], key_prefix: str) -> None:
    st.caption("관점별 의견을 누르면 해당 탭으로 이동합니다.")
    for signal_key, label in [
        ("oneil", "윌리엄 오닐"),
        ("trend", "추세/모멘텀"),
        ("risk", "리스크 점검"),
    ]:
        opinion = signals[signal_key]["opinion"]
        if st.button(
            f"{label}  ·  {opinion}",
            key=f"jump_{key_prefix}_{signal_key}",
            use_container_width=True,
        ):
            set_active_tab(signal_key)
            st.rerun()


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
              <p>{signal["name"]} · {item.get("data_source", "Yahoo Finance")} · {item.get("data_status", "마감 기준")}</p>
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
                    if (
                        "수익률" in name
                        or "이격도" in name
                        or "대비" in name
                        or "변화" in name
                        or "연율화" in name
                    )
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
        .tab-menu {
            display:flex;
            flex-wrap:wrap;
            gap:8px;
            margin: 0 0 20px;
            padding: 6px;
            width: fit-content;
            max-width: 100%;
            background:#eaf3ff;
            border:1px solid #d7e8ff;
            border-radius:999px;
        }
        .tab-menu a {
            display:inline-flex;
            align-items:center;
            justify-content:center;
            min-height:36px;
            padding: 0 16px;
            border-radius:999px;
            color:#416b9f;
            font-size:14px;
            font-weight:800;
            text-decoration:none;
            white-space:nowrap;
            transition: background .15s ease, color .15s ease, box-shadow .15s ease;
        }
        .tab-menu a:hover {
            background:#dbeaff;
            color:#1b64da;
        }
        .tab-menu a.active {
            background:#3182f6;
            color:#ffffff;
            box-shadow:0 5px 16px rgba(49,130,246,.22);
        }
        div[data-testid="stButton"] > button {
            min-height: 38px;
            border-radius: 999px;
            border: 1px solid #d7e8ff;
            font-weight: 800;
            transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
        }
        div[data-testid="stButton"] > button:hover {
            border-color: #3182f6;
            box-shadow: 0 5px 16px rgba(49,130,246,.14);
            transform: translateY(-1px);
        }
        div[data-testid="stButton"] > button[kind="primary"] {
            background:#3182f6 !important;
            border-color:#3182f6 !important;
            color:#ffffff !important;
            box-shadow:0 5px 16px rgba(49,130,246,.18);
        }
        div[data-testid="stButton"] > button[kind="secondary"] {
            background:#ffffff !important;
            color:#416b9f !important;
        }
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
        .badge-stack {
            display:flex;
            flex-direction:column;
            align-items:flex-end;
            gap:6px;
        }
        .source-badge {
            border-radius:999px;
            padding:4px 8px;
            background:#f0f6ff;
            color:#6f87a8;
            font-size:11px;
            font-weight:800;
            white-space:nowrap;
        }
        .source-badge.fallback {
            background:#fff7e8;
            color:#b76b00;
        }
        .source-badge.provisional {
            background:#fff0f0;
            color:#d92d35;
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
        .opinion-list { display:grid; gap:0; margin-top:18px; }
        .opinion-list a {
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:12px;
            padding:13px 8px;
            border-top:1px solid #e5edf8;
            border-radius:8px;
            color:inherit;
            text-decoration:none;
            cursor:pointer;
            transition: background .15s ease;
        }
        .opinion-list a:hover {
            background:#f0f6ff;
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
            .badge-stack { align-items:flex-start; }
            .price-row strong { font-size:29px; }
            .tab-menu { width:100%; border-radius:16px; }
            .tab-menu a { flex:1 1 45%; }
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
    active_tab = get_active_tab()
    render_tab_menu(active_tab)

    if active_tab == "overview":
        render_overview_tab(valid_items, overview)
    elif active_tab == "oneil":
        render_oneil_tab(snapshot)
    elif active_tab == "trend":
        render_signal_tab(items, "trend", "추세/모멘텀")
    elif active_tab == "risk":
        render_signal_tab(items, "risk", "리스크 점검")

    st.caption(f"데이터는 최대 {snapshot['cache_seconds']}초 동안 캐시됩니다.")


def get_active_tab() -> str:
    if "active_tab" not in st.session_state:
        tab = st.query_params.get("tab", "overview")
        if isinstance(tab, list):
            tab = tab[0] if tab else "overview"
        st.session_state.active_tab = tab if tab in TAB_LABELS else "overview"
    return st.session_state.active_tab


def set_active_tab(tab: str) -> None:
    if tab in TAB_LABELS:
        st.session_state.active_tab = tab


def render_tab_menu(active_tab: str) -> None:
    cols = st.columns(len(TAB_LABELS))
    for col, (key, label) in zip(cols, TAB_LABELS.items()):
        with col:
            if st.button(
                label,
                key=f"nav_{key}",
                type="primary" if key == active_tab else "secondary",
                use_container_width=True,
            ):
                set_active_tab(key)
                st.rerun()


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

    render_overview_guide()


def render_overview_guide() -> None:
    st.markdown('<div class="section-title">개요 탭 판정 설명서</div>', unsafe_allow_html=True)
    with st.expander("종합 의견은 이렇게 정해집니다", expanded=False):
        st.markdown(
            """
            **개요 탭은 세 가지 관점의 의견을 합산해 최종 의견을 냅니다.**

            - **윌리엄 오닐:** 팔로우쓰루데이, 분산일, 스톨링, 랠리 실패 여부를 봅니다.
            - **추세/모멘텀:** 50·150·200일선 배열, 200일선 방향, 3개월·6개월 수익률, 52주 위치를 봅니다.
            - **리스크 점검:** RSI, 50일선 이격도, 분산일 누적과 집중 여부를 봅니다.

            각 관점은 0~100점으로 계산되고, 지수별 **종합 점수**는 세 관점 점수의 평균입니다.
            """
        )
        st.markdown(
            """
            **지수별 최종 의견**

            - **매수 우위:** 세 관점 중 2개 이상이 매수 우위이고, 종합 점수가 65점 이상일 때
            - **중립/관망:** 매수와 방어 의견이 엇갈리거나, 종합 점수가 애매한 중간 구간일 때
            - **매도/방어:** 세 관점 중 2개 이상이 매도/방어이거나, 종합 점수가 45점 미만일 때
            """
        )
        st.markdown(
            """
            **시장 전반 판단**

            - **시장 전반 매수 우위:** 4개 지수 중 3개 이상이 매수 우위이고, 평균 점수가 65점 이상일 때
            - **시장 전반 중립/관망:** 지수별 의견이 엇갈려 방향 확인이 더 필요할 때
            - **시장 전반 방어 우선:** 4개 지수 중 2개 이상이 매도/방어이거나, 평균 점수가 45점 미만일 때

            `중립/관망`은 매수와 매도가 반반이라는 뜻보다는, **아직 한쪽으로 강하게 결론 내리기 어렵다**는 의미입니다.
            """
        )
        st.markdown(
            """
            **데이터 출처 표시**

            - **Yahoo:** 야후 파이낸스에서 최신 종가가 정상 확인된 상태입니다.
            - **Npay 대체:** 야후의 한국 지수 데이터가 늦거나 비어 있어 Npay 증권 값을 대신 사용한 상태입니다.
            - **장중 잠정:** 당일 장중 값일 수 있어, 장마감 후 신호가 달라질 수 있습니다.
            """
        )


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
    if signal_key == "trend":
        st.info(
            "새 추세/모멘텀 기준: 50·150·200일선 추세 템플릿, 200일선 방향, "
            "3개월·6개월 수익률, 52주 고점·저점 대비 위치를 함께 봅니다."
        )
    for row_start in range(0, len(items), 2):
        cols = st.columns(2)
        for col, item in zip(cols, items[row_start : row_start + 2]):
            with col:
                render_signal_card(item, signal_key)

    if signal_key == "trend":
        with st.expander("추세/모멘텀 판정방식 해설", expanded=False):
            render_trend_scoring_guide()
    else:
        with st.expander("리스크 점검 판정 기준", expanded=False):
            render_risk_scoring_guide()


def render_trend_scoring_guide() -> None:
    st.markdown(
        """
        이 탭은 **Minervini식 추세 템플릿**과 **IBD식 상대강도 사고방식**을 지수 판단용으로 단순화한 보조 모델입니다.
        개별 종목 선별 공식이 아니라, 지수의 추세가 얼마나 건강한지 0~100점으로 요약합니다.
        """
    )
    st.dataframe(
        [
            {
                "구분": "추세 위치",
                "조건": "현재 지수가 50일선 위",
                "점수": "15점",
                "해석": "단기와 중기 사이의 가격 흐름이 살아 있다고 봅니다.",
            },
            {
                "구분": "추세 위치",
                "조건": "현재 지수가 150일선 위",
                "점수": "15점",
                "해석": "중기 추세가 훼손되지 않았는지 확인합니다.",
            },
            {
                "구분": "추세 위치",
                "조건": "현재 지수가 200일선 위",
                "점수": "15점",
                "해석": "장기 상승 추세 안에 있는지 확인합니다.",
            },
            {
                "구분": "이동평균 배열",
                "조건": "50일선 > 150일선 > 200일선",
                "점수": "15점",
                "해석": "단기 평균이 중기와 장기 평균보다 높아 상승 배열로 봅니다.",
            },
            {
                "구분": "장기 추세 방향",
                "조건": "200일선이 20거래일 전보다 상승",
                "점수": "10점",
                "해석": "장기 추세선 자체가 위로 기울고 있는지 봅니다.",
            },
            {
                "구분": "상대강도/모멘텀",
                "조건": "3개월 수익률 플러스",
                "점수": "10점",
                "해석": "최근 분기의 상승 탄력이 살아 있는지 봅니다.",
            },
            {
                "구분": "상대강도/모멘텀",
                "조건": "6개월 수익률 플러스",
                "점수": "10점",
                "해석": "반년 단위의 중기 모멘텀이 양호한지 봅니다.",
            },
            {
                "구분": "52주 위치",
                "조건": "52주 고점 대비 -15% 이내",
                "점수": "5점",
                "해석": "고점에서 너무 깊게 밀리지 않았는지 봅니다.",
            },
            {
                "구분": "52주 위치",
                "조건": "52주 저점 대비 +20% 이상",
                "점수": "5점",
                "해석": "저점권을 벗어나 충분히 회복했는지 봅니다.",
            },
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.markdown(
        """
        **판정 구간**

        - **매수 우위:** 65점 이상. 추세 배열과 모멘텀이 대체로 우호적입니다.
        - **중립/관망:** 45점 이상 65점 미만. 일부 조건은 좋지만 아직 확신하기 어렵습니다.
        - **매도/방어:** 45점 미만. 주요 이동평균 또는 중기 모멘텀이 약해 방어적으로 봅니다.

        이 점수는 윌리엄 오닐 탭의 팔로우쓰루데이/분산일 판정을 대체하지 않고, **추세와 상대강도 관점의 보조 의견**으로 사용합니다.
        """
    )
    st.caption("앱 버전: trend-v2-score-guide")


def render_risk_scoring_guide() -> None:
    st.markdown(
        """
        이 탭은 CNN Fear & Greed Index처럼 여러 위험 항목을 각각 0~100점으로 환산한 뒤 평균내는 방식에서 아이디어를 가져왔습니다.
        다만 옵션, 채권, VIX 같은 외부 심리 데이터는 쓰지 않고, 현재 앱이 안정적으로 가져오는 지수 가격·거래량 데이터만 사용합니다.

        **최종 리스크 점수 산식**

        `최종 점수 = (추세 방어력 + 52주 낙폭 + RSI 과열/침체 + 변동성 부담 + 분산일 부담) / 5`
        """
    )
    st.dataframe(
        [
            {
                "항목": "추세 방어력",
                "점수 산식": "가격이 50·200일선 위이고 200일선 상승: 100점 / 200일선 위와 200일선 보합 이상: 80점 / 200일선 위: 65점 / 50일선 위: 50점 / 그 외: 25점",
                "의미": "추세가 무너지지 않았는지 보는 방어력 점수입니다.",
            },
            {
                "항목": "52주 낙폭",
                "점수 산식": "52주 고점 대비 -5% 이내: 100점 / -10% 이내: 80점 / -15% 이내: 60점 / -20% 이내: 40점 / 그보다 깊으면 20점",
                "의미": "고점 대비 낙폭이 깊을수록 회복 부담이 크다고 봅니다.",
            },
            {
                "항목": "RSI 과열/침체",
                "점수 산식": "RSI 45~65: 100점 / 40~45 또는 65~70: 80점 / 35~40 또는 70~75: 55점 / 30~35 또는 75~80: 30점 / 30 미만 또는 80 초과: 10점",
                "의미": "과열과 침체를 모두 위험으로 봅니다.",
            },
            {
                "항목": "변동성 부담",
                "점수 산식": "20일 변동성 / 최근 1년 중앙값 <= 0.8배: 100점 / <=1.0배: 85점 / <=1.25배: 65점 / <=1.5배: 45점 / <=2.0배: 25점 / 초과: 10점",
                "의미": "평소보다 변동성이 커질수록 위험 점수를 낮춥니다.",
            },
            {
                "항목": "분산일 부담",
                "점수 산식": "활성 분산일 0~1회: 100점 / 2~3회: 75점 / 4~5회: 40점 / 6회 이상: 10점. 최근 11거래일 집중이면 최대 40점으로 제한",
                "의미": "기관성 매도 압력이 누적되거나 짧은 기간에 몰리면 위험하게 봅니다.",
            },
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.markdown(
        """
        **최종 점수 계산**

        다섯 항목의 점수를 같은 비중으로 평균냅니다.

        예: 추세 방어력 80점, 52주 낙폭 60점, RSI 100점, 변동성 65점, 분산일 75점이면  
        `(80 + 60 + 100 + 65 + 75) / 5 = 76점`입니다.

        **판정 구간**

        - **매수 우위:** 65점 이상. 주요 위험 항목이 전반적으로 낮습니다.
        - **중립/관망:** 45점 이상 65점 미만. 일부 위험이 올라와 있어 추격보다 확인이 필요합니다.
        - **매도/방어:** 45점 미만. 추세 훼손, 낙폭, 과열/침체, 변동성, 분산일 부담 중 여러 항목이 악화된 상태입니다.

        이 점수는 공식 투자등급이 아니라, **현재 지수에서 방어가 필요한지 확인하는 보조 위험 점검표**입니다.
        """
    )
    st.caption("앱 버전: risk-v3-score-formula")


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
            - **팔로우쓰루데이:** 랠리 4일차 이후 지수가 기준 상승률 이상 오르고 ETF 대체 거래량이 전일보다 증가
            - **상승률 기준:** KOSPI/KOSPI 200/S&P 500은 1.25% 이상, 나스닥종합은 1.70% 이상
            - **미국시장 확인:** 나스닥종합 또는 S&P 500 중 하나에서 유효 팔로우쓰루데이가 발생하면 인정
            - **신호 평가 - 양호:** 통상적인 4~7일차에 거래량 증가와 함께 발생
            - **신호 평가 - 주의:** 발생 후 5거래일 안에 분산일이 나타나 매도 압력이 확인됨
            - **신호 평가 - 늦은 확인:** 랠리 8일차 이후 늦게 발생해 일반적인 신호보다 보수적으로 판단
            - **신호 평가 - 실패:** 발생 후 랠리 첫날 저가를 깨서 상승 시도가 무효화됨
            """
        )


def main() -> None:
    try:
        dashboard()
    except Exception as exc:
        st.error("앱을 불러오는 중 문제가 발생했습니다. 잠시 후 새로고침해 주세요.")
        st.caption(f"오류 내용: {exc}")


if __name__ == "__main__":
    main()
