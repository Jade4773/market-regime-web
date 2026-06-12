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
    if regime == "매수 우위":
        return "background:#e1f4eb;color:#146b4b;"
    if regime == "주의":
        return "background:#fff3d8;color:#8a5a00;"
    return "background:#fae4e4;color:#a73535;"


def render_market_card(item: dict[str, Any]) -> None:
    if item.get("error"):
        st.subheader(item["name"])
        st.error(item["error"])
        return

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
          <div class="meter"><span style="width:{item["score"]}%"></span></div>
          <p class="explain">{item["explanation"]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("분산일", f"{item['distribution_count']}회")
    c2.metric("거래량", f"{item['volume']:,.0f}")
    c3.metric("거래량 변화", format_pct(item["volume_change_pct"]))
    c4.metric("50일선", format_number(item["ma50"]))
    st.caption(
        f"거래량 기준: {item['volume_ticker']} · "
        f"최근 11거래일 분산 신호: {item['distribution_cluster_count']}회"
    )
    if item["distribution_clustered"]:
        st.warning("최근 11거래일에 분산 신호가 집중되어 있습니다.")

    ftd = item.get("follow_through")
    if ftd:
        ftd_quality = ftd.get("quality", "기존 신호")
        ftd_quality_reason = ftd.get(
            "quality_reason", "이전 계산 결과입니다. 다음 데이터 갱신 시 품질이 재평가됩니다."
        )
        st.caption(
            f"팔로우쓰루데이: {ftd['date']} · {format_pct(ftd['gain_pct'])} · "
            f"{ftd['day_number']}일차 · 품질: {ftd_quality}"
        )
        st.caption(ftd_quality_reason)
    else:
        st.caption("팔로우쓰루데이: 최근 랠리 시도 이후 확인 안 됨")

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


def dashboard() -> None:
    st.markdown(
        """
        <style>
        .block-container { max-width: 1180px; padding-top: 32px; }
        .market-card {
            border: 1px solid #d9ded8;
            border-radius: 8px;
            padding: 18px 18px 12px;
            background: #ffffff;
            margin-bottom: 14px;
        }
        .card-head, .price-row {
            display: flex;
            justify-content: space-between;
            gap: 14px;
            align-items: flex-start;
        }
        .card-head h3 { margin: 0 0 4px; font-size: 22px; }
        .card-head p, .explain { color: #667067; margin: 0; }
        .regime-badge {
            border-radius: 999px;
            padding: 6px 10px;
            font-size: 13px;
            font-weight: 800;
            white-space: nowrap;
        }
        .price-row { align-items: baseline; margin-top: 18px; }
        .price-row strong { font-size: 34px; line-height: 1; }
        .up { color: #146b4b; font-weight: 800; }
        .down { color: #a73535; font-weight: 800; }
        .meter {
            height: 8px;
            background: #edf0ec;
            border-radius: 999px;
            overflow: hidden;
            margin: 18px 0 12px;
        }
        .meter span { display: block; height: 100%; background: #245c73; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.caption("William O'Neil Market Pulse")
    st.title("지수별 매수/매도 국면")
    render_market_dashboard()


def render_market_dashboard() -> None:
    with st.spinner("야후 파이낸스에서 데이터를 가져오는 중입니다."):
        snapshot = get_market_snapshot()

    summary = snapshot["market_summary"]
    st.subheader(summary["regime"])
    st.info(summary["explanation"])
    region_cols = st.columns(2)
    for col, key in zip(region_cols, ["korea", "united_states"]):
        region = summary["regions"][key]
        with col:
            st.metric(f"{region['name']} 시장", region["regime"])
            st.caption(region["explanation"])
            st.caption(
                "유효 팔로우쓰루데이: "
                + ("확인" if region["has_valid_ftd"] else "미확인")
            )
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
        st.markdown(
            """
            - **랠리 첫날:** 지수가 전일보다 상승 마감하거나 일중 범위 상단 절반에서 마감
            - **카운트 재시작:** 이후 지수가 랠리 첫날 저가를 하향 돌파
            - **팔로우쓰루데이:** 랠리 4일차 이후 지수가 최소 1% 상승하고 ETF 대체 거래량 증가
            - **미국시장 확인:** 나스닥종합 또는 S&P 500 중 하나에서 유효 팔로우쓰루데이가 발생하면 인정
            - **품질 양호:** 통상적인 4~7일차에 확인
            - **늦은 확인:** 8일차 이후 확인
            - **품질 주의:** 확인 후 5거래일 내 분산일 발생
            - **실패:** 확인 후 랠리 첫날 저가 하향 돌파
            """
        )

    items = list(snapshot["items"].values())
    for row_start in range(0, len(items), 2):
        cols = st.columns(2)
        for col, item in zip(cols, items[row_start : row_start + 2]):
            with col:
                render_market_card(item)

    st.caption(f"데이터는 최대 {snapshot['cache_seconds']}초 동안 캐시됩니다.")


def main() -> None:
    dashboard()


if __name__ == "__main__":
    main()
