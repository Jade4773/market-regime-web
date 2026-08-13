from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from market_pulse.data import DEFAULT_CACHE_SECONDS, get_market_snapshot
from market_pulse.products import (
    build_etf_market_summary,
    build_etf_recommendations,
    fetch_public_els_products,
)


TAB_LABELS = {
    "overview": "개요",
    "oneil": "윌리엄 오닐",
    "trend": "추세/모멘텀",
    "risk": "리스크 점검",
    "products": "상품 추천",
}

APP_VERSION = "etf-full-screener-v4-liquidity-cache-3h"


@st.cache_data(ttl=DEFAULT_CACHE_SECONDS, show_spinner=False)
def get_els_products() -> dict[str, Any]:
    return fetch_public_els_products()


def format_number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:,.{digits}f}"


def format_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}%"


def format_cache_duration(seconds: int) -> str:
    if seconds % 3600 == 0:
        return f"{seconds // 3600}시간"
    if seconds % 60 == 0:
        return f"{seconds // 60}분"
    return f"{seconds}초"


def format_trading_value(value: float | None, candidate: dict[str, Any]) -> str:
    if value is None:
        return "-"
    if candidate.get("listing") == "국내상장 ETF":
        return f"{value / 100_000_000:,.1f}억원"
    return f"${value / 1_000_000:,.1f}M"


def data_meta_text(item: dict[str, Any]) -> str:
    source = item.get("data_source", "Yahoo Finance")
    status = item.get("data_status", "마감 기준")
    return f"{item['ticker']} · {item['last_date']} · {source} · {status}"


def data_source_badge(item: dict[str, Any]) -> str:
    source = item.get("data_source", "Yahoo Finance")
    status = item.get("data_status", "마감 기준")
    if source == "한국투자증권":
        return f'<span class="source-badge kis">한국투자 · {status}</span>'
    if source == "Npay 증권":
        return f'<span class="source-badge fallback">Npay 대체 · {status}</span>'
    if status == "장중 잠정":
        return f'<span class="source-badge provisional">장중 잠정</span>'
    return '<span class="source-badge">Yahoo</span>'


def badge_style(regime: str) -> str:
    if any(word in regime for word in ["매도", "방어", "금지", "조정", "손절"]):
        return "background:#ffe8e8;color:#d92d35;"
    if "매수" in regime:
        return "background:#e8f3ff;color:#1b64da;"
    if "주의" in regime:
        return "background:#fff0f0;color:#e5484d;"
    if any(word in regime for word in ["확인", "압박", "추격"]):
        return "background:#fff4de;color:#b7791f;"
    if "중립" in regime or "관망" in regime or "관심" in regime or "대기" in regime:
        return "background:#eef4fb;color:#4d6f9d;"
    return "background:#eef4fb;color:#4d6f9d;"


def regime_tone(regime: str) -> str:
    if any(word in regime for word in ["매도", "방어", "금지", "조정", "손절"]):
        return "negative"
    if "매수" in regime:
        return "positive"
    if "중립" in regime or "관망" in regime or "관심" in regime or "대기" in regime:
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
        f"{item.get('distribution_scope', '최근 25거래일')} · "
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
                f"랠리/FTD 사이클 재시작: "
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
        st.caption(f"{item.get('distribution_scope', '최근 25거래일')} 분산일 없음")

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
        .source-badge.kis {
            background:#e8f3ff;
            color:#1b64da;
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
        .reason-block {
            margin-top:16px;
            padding:14px;
            border:1px solid #e2ebf7;
            border-radius:8px;
            background:#fbfdff;
            color:#416b9f;
            font-size:13px;
            line-height:1.55;
        }
        .reason-block strong {
            display:block;
            color:#172b4d;
            font-size:13px;
            margin:4px 0 6px;
        }
        .reason-block ul {
            margin:0 0 12px 17px;
            padding:0;
        }
        .reason-block ul:last-child { margin-bottom:0; }
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
    with st.spinner("시장 데이터를 가져오는 중입니다."):
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
    elif active_tab == "products":
        render_products_tab(snapshot)

    st.caption(f"데이터는 최대 {format_cache_duration(snapshot['cache_seconds'])} 동안 캐시됩니다.")


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


def render_products_tab(snapshot: dict[str, Any]) -> None:
    st.markdown(
        """
        <div class="summary-card">
          <div class="summary-label">규칙 기반 상품 후보</div>
          <div class="summary-title neutral">상품 추천</div>
          <p class="summary-copy">
            공개 ELS 청약 정보와 윌리엄 오닐식 ETF 매수 후보를 분리해서 확인합니다.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.warning(
        "이 탭은 개인별 투자성향, 보유자산, 세금, 환율, 수수료를 반영하지 않은 "
        "규칙 기반 후보 화면입니다. 실제 청약이나 매수 전에는 투자설명서와 상품 위험등급을 확인해야 합니다."
    )
    render_els_products_section()
    render_etf_recommendation_section(snapshot)
    render_product_guide()


def render_els_products_section() -> None:
    st.markdown('<div class="section-title">공개 ELS 청약 모니터</div>', unsafe_allow_html=True)
    with st.spinner("공개 ELS 청약 정보를 확인하는 중입니다."):
        els = get_els_products()

    items = els.get("items", [])
    if els.get("api_status"):
        st.caption(f"데이터 확인: {els['api_status']}")
    if items:
        st.caption(f"{els.get('status', '공개 비교공시 기준')} · 청약 종료 또는 비지수형으로 판독된 항목은 제외")
        st.dataframe(items, hide_index=True, use_container_width=True)
    else:
        st.info(
            "자동으로 판독 가능한 지수형 ELS 청약 상품이 없습니다. "
            f"사유: {els.get('status', '확인 불가')}"
        )
        st.caption(
            "금융투자협회 비교공시는 증권사에서 직접 청약 가능한 공모 ELS·DLS·ELB·DLB를 모아 보여줍니다. "
            "자동 판독이 실패하거나 청약 시간이 끝난 경우에는 아래 공식 화면에서 직접 확인하세요."
        )

    link_cols = st.columns(3)
    with link_cols[0]:
        st.link_button("공개 비교공시", els.get("source_url"), use_container_width=True)
    with link_cols[1]:
        st.link_button("금투협 전자공시", els.get("guide_url"), use_container_width=True)
    with link_cols[2]:
        st.link_button("DART 공시검색", els.get("notice_url"), use_container_width=True)


def render_etf_recommendation_section(snapshot: dict[str, Any]) -> None:
    st.markdown('<div class="section-title">CAN SLIM ETF TOP 2</div>', unsafe_allow_html=True)
    st.caption(f"ETF screener version: {APP_VERSION}")
    render_etf_market_status(snapshot)
    candidates = build_etf_recommendations(snapshot)
    if not candidates:
        st.info(
            "현재 문서 기준을 통과한 주도 ETF 후보가 없습니다. "
            "FTD가 유지되고, 상대강도 상위권 ETF가 유효 베이스와 피봇 근처에 올 때 후보가 표시됩니다."
        )
        return

    st.caption(
        "점수와 매수 가능 여부를 분리합니다. 점수가 높아도 피봇 돌파와 거래량 확인 전이면 `대기`로 표시합니다."
    )
    summary = candidates[0].get("screen_summary", {})
    if summary:
        st.caption(
            f"검토 범위: {summary.get('universe_source', 'ETF universe')} "
            f"{summary.get('universe_count', 0):,}개 중 "
            f"주식형·유동성 필터 {summary.get('screenable_count', 0):,}개, "
            f"1차 상위권 {summary.get('preliminary_count', 0):,}개, "
            f"상세 재계산 {summary.get('analyzed_count', 0):,}개 · "
            f"최종 가격 기준: {summary.get('price_source', '-')}"
        )
    cols = st.columns(2)
    for col, candidate in zip(cols, candidates):
        with col:
            render_etf_candidate_card(candidate)


def render_etf_market_status(snapshot: dict[str, Any]) -> None:
    summaries = build_etf_market_summary(snapshot)
    cols = st.columns(2)
    for col, summary in zip(cols, summaries):
        with col:
            st.markdown(
                f"""
                <div class="region-card">
                  <div class="region-top">
                    <span class="region-name">{summary["label"]}</span>
                    <span class="regime-badge" style="{badge_style(summary["state_label"])}">{summary["state_label"]}</span>
                  </div>
                  <div class="stat-grid">
                    <div><span>Last FTD</span><strong>{summary["ftd"]}</strong></div>
                    <div><span>분산일</span><strong>{summary["distribution_count"]}</strong></div>
                    <div><span>추세 위치</span><strong>{summary["nasdaq_position"]}</strong></div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def etf_action_copy(candidate: dict[str, Any]) -> str:
    status = candidate.get("trading_status")
    copies = {
        "BUY_READY": "피봇 돌파와 거래량 확인이 함께 나온 정상 매수 준비 구간입니다.",
        "PIVOT_APPROACH": "피봇 5% 이내까지 접근했습니다. 돌파와 거래량을 기다립니다.",
        "BREAKOUT_NEEDS_VOLUME": "피봇은 넘었지만 거래량 확인이 부족해 추격하지 않습니다.",
        "HOLD": "이미 보유했다면 추세 추적 구간이지만 신규 추격매수는 피합니다.",
        "EXTENDED": "피봇 대비 +5%를 넘어 신규 진입은 기다립니다.",
        "FAR_FROM_PIVOT": "아직 피봇과 거리가 있어 선취매보다 관찰이 우선입니다.",
        "NO_VALID_BASE": "유효 베이스가 아직 부족해 매수 후보로 보지 않습니다.",
        "BROKEN": "50일선 아래라 신규 매수는 금지합니다.",
        "MARKET_WAIT": "시장 허가 조건이 약해 ETF 신규 매수는 보류합니다.",
        "SELL_WARNING": "단기 추세 훼손 가능성이 있어 보유분 방어를 점검합니다.",
    }
    return copies.get(status, "관찰 후보입니다. 피봇과 거래량 확인이 필요합니다.")


def render_etf_candidate_card(candidate: dict[str, Any]) -> None:
    label = candidate.get("action", candidate.get("leader_label", "관찰"))
    positive_list = "".join(f"<li>{escape(reason)}</li>" for reason in candidate["positive_reasons"])
    risk_list = "".join(f"<li>{escape(reason)}</li>" for reason in candidate["risk_signals"])
    st.markdown(
        f"""
        <div class="market-card">
          <div class="card-head">
            <div>
              <h3>#{candidate.get("display_rank", candidate["leader_rank"])} {candidate["ticker"]} · {candidate["name"]}</h3>
              <p>{candidate["listing"]} · 투자국가 {candidate["country"]} · {candidate["index"]}</p>
            </div>
            <span class="regime-badge" style="{badge_style(label)}">{label}</span>
          </div>
          <div class="price-row">
            <strong>{format_number(candidate["last_price"])}</strong>
            <span class="{'up' if candidate["change_pct"] >= 0 else 'down'}">{format_pct(candidate["change_pct"])}</span>
          </div>
          <p class="explain">
            <strong>{etf_action_copy(candidate)}</strong><br>
            기준 시장: {candidate["market"]} · {candidate["market_state_label"]}<br>
            {candidate["note"]}
          </p>
          <div class="signal-row">
            <span>ETF CAN SLIM Score</span>
            <div class="meter"><span style="width:{candidate["can_slim_score"]}%"></span></div>
            <strong>{candidate["can_slim_score"]}</strong>
          </div>
          <div class="stat-grid">
            <div><span>Action</span><strong>{candidate["action"]}</strong></div>
            <div><span>상대강도</span><strong>{candidate["leader_rank"]}위 · {candidate["leader_percentile"]}</strong></div>
            <div><span>60일 수익률</span><strong>{format_pct(candidate["return60"])}</strong></div>
          </div>
          <div class="ftd-line">
            <span>피봇</span><strong>{format_number(candidate["pivot"])} · 거리 {format_pct(candidate["pivot_distance_pct"])}</strong>
          </div>
          <div class="ftd-line">
            <span>매수 가능 구간</span>
            <strong>{format_number(candidate["buy_low"])} ~ {format_number(candidate["buy_high"])} · 거래량 {candidate["volume_ratio"]:.2f}배</strong>
          </div>
          <div class="ftd-line">
            <span>유동성</span>
            <strong>50일 거래량 {format_number(candidate["avg_volume50"], 0)} · 거래대금 {format_trading_value(candidate["avg_value50"], candidate)}</strong>
          </div>
          <div class="ftd-line">
            <span>21EMA / 50일선</span>
            <strong>{format_number(candidate["ma21"])} / {format_number(candidate["ma50"])}</strong>
          </div>
          <div class="ftd-line">
            <span>매도/방어</span>
            <strong>{candidate["sell_signal"]} · 손절 {format_number(candidate["stop_loss"])}</strong>
          </div>
          <div class="reason-block">
            <strong>Why Selected</strong>
            <ul>{positive_list}</ul>
            <strong>Risk Signals</strong>
            <ul>{risk_list}</ul>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    component_text = " · ".join(
        f"{name} {candidate['components'].get(name, 0)}점"
        for name in ["M 시장 방향", "L 상대강도", "추세", "베이스/피봇", "유동성"]
    )
    st.caption(
        f"{component_text} · ETF 가격/거래량: {candidate['data_source']} · 지수 판단: {candidate['data_status']}"
    )


def render_product_guide() -> None:
    with st.expander("상품 추천 탭 판정 방식", expanded=False):
        st.markdown(
            """
            **1. 공개 ELS 청약 모니터**

            - 1순위로 금융투자협회 `파생결합증권등 청약정보 비교공시 > 청약중인상품` 데이터를 확인합니다.
            - 이 비교공시에는 발행사, 신용등급, 상품명, 기초자산, 만기일, 조건 충족시 연 수익률, 청약시작일, 청약종료일, 상품유형, 발행사 상세 링크가 포함됩니다.
            - 금투협 조회가 실패하면 한국투자증권 별도 ELS API 설정, 미래에셋 공개 ELS/DLS 검색, 현대차증권 공개 청약 표, 대신증권 공개 청약 표 순서로 보조 확인합니다.
            - 상품명 또는 구조에 `ELS`, `주가연계증권`, `파생결합증권`이 있고, 기초자산이 `KOSPI`, `S&P`, `NASDAQ`, `EURO STOXX`, `NIKKEI`, `HSCEI` 같은 주가지수로만 구성된 상품을 순수 지수형 ELS로 분류합니다.
            - 청약 종료일이 지났거나 금투협 비고에 표시된 청약 종료 시간이 지난 상품은 목록에서 제외합니다.
            - 표시 항목은 증권사, 상품명, 기초자산, 쿠폰, 조기상환 조건, 만기/상환주기, 청약기간, 최대손실률, 신용등급, 상세 링크입니다.

            **2. CAN SLIM ETF TOP 2**

            ETF는 붙임 문서의 `ETF CAN SLIM Score` 방식에 맞춰 100점 만점으로 계산합니다.
            단, **점수가 높다는 것과 지금 매수 가능하다는 것은 분리**해서 보여줍니다.

            - **ETF universe:** 한국투자증권 국내/해외 종목정보파일에서 국내상장 ETF와 미국상장 ETF를 가져옵니다. 레버리지·인버스 ETF는 제외합니다.
            - **1차 점수화:** 전체 universe에서 비주식형·저유동성·레버리지·인버스 상품을 제외한 뒤, 20일·60일·120일 수익률과 추세 위치를 일괄 계산해 상대강도 백분위를 먼저 만듭니다.
            - **상세 재계산:** 1차 상위권 ETF는 한투 일봉 API를 우선 사용해 OHLCV, 21EMA, 50일선, 200일선, 베이스, 피봇, 거래량 비율을 다시 계산합니다. 한투 일봉이 실패하면 Yahoo 가격으로 대체합니다.

            - **M 시장 방향 20점:** 유효 FTD가 있고 분산일이 제한적이면 20점, 상승장이지만 압박을 받으면 10점, 조정장이면 0점입니다.
            - **L 상대강도 30점:** ETF 후보군 전체에서 20일·60일·120일 수익률 백분위를 계산합니다. 20일 10점, 60일 12점, 120일 8점으로 최근 강도를 더 크게 반영합니다.
            - **추세 20점:** 가격이 21EMA 위면 6점, 50일선 위면 7점, 50일선이 상승 중이면 4점, 200일선 위면 3점입니다.
            - **베이스/피봇 25점:** 25거래일 이상 베이스, 15% 이하 깊이, 피봇 -5% 이내 접근, 피봇 돌파, 돌파 시 거래량 1.4배 이상을 봅니다.
            - **유동성 5점:** 오닐식 수급 판단에 맞춰 50일 평균 거래량을 보고, ETF 실전 매매 보완 기준으로 50일 평균 거래대금도 함께 봅니다. 거래량과 거래대금이 모두 최소 기준을 넘으면 3점, 둘 다 기준의 3배 이상이면 5점입니다. 기본 최소 거래대금은 국내상장 ETF 10억 원, 미국상장 ETF 500만 달러입니다.

            **Action 판정**

            - **매수준비:** 상승장 확인, 피봇~피봇+5% 구간, 거래량 1.4배 이상이 함께 확인될 때입니다.
            - **피봇 접근:** 피봇보다 0~5% 아래에 있어 돌파와 거래량을 기다리는 상태입니다.
            - **거래량 확인:** 피봇은 넘었지만 거래량이 부족해 아직 확정 매수로 보지 않습니다.
            - **추격금지/보유:** 피봇보다 +5% 이상 높습니다. 이미 보유했다면 추세 추적, 신규 매수는 보류입니다.
            - **관찰/피봇 대기:** 유효 베이스가 부족하거나 피봇과 거리가 멀어 선취매하지 않는 상태입니다.
            - **매수금지/관망:** 50일선 아래이거나 시장이 조정장일 때입니다.

            이 탭의 후보는 개인 맞춤 투자권유가 아니라 **가장 강한 ETF가 무엇인지**와 **그 ETF를 지금 사도 되는지**를 분리해 보여주는 규칙 기반 관심 목록입니다.
            """
        )


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
            - **분산일:** 지수가 0.2% 이상 하락하고 거래량 기준 데이터가 전일보다 증가
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
            - **팔로우쓰루데이:** 랠리 4일차 이후 지수가 기준 상승률 이상 오르고 거래량 기준 데이터가 전일보다 증가
            - **상승률 기준:** KOSPI/KOSPI 200/S&P 500은 1.25% 이상, 나스닥종합은 1.70% 이상
            - **거래량 기준:** 한국 지수의 최근 네이버 구간은 Npay 지수 거래량을 우선 사용하고, 미국 지수와 과거 보강 구간은 ETF 대체 거래량을 사용
            - **분산일 카운트:** 유효한 팔로우쓰루데이가 있으면 그 FTD 이후 발생한 활성 분산일만 현재 상승 국면의 부담으로 계산
            - **신호 유지:** 한 번 확인된 팔로우쓰루데이는 랠리 첫날 저가 하향 돌파 또는 활성 분산 신호 6회 이상 등 소멸 조건이 나오기 전까지 유지
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
