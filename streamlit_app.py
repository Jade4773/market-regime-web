from __future__ import annotations

import os
from typing import Any

import streamlit as st

from market_data import get_market_snapshot
from password_store import authenticate, change_password, export_users, get_users, set_enabled


st.set_page_config(
    page_title="Market Regime",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def get_secret(name: str, default: str = "") -> str:
    env_value = os.getenv(name)
    if env_value is not None:
        return env_value

    lower_name = name.lower()
    try:
        if name in st.secrets:
            return str(st.secrets[name])
        if lower_name in st.secrets:
            return str(st.secrets[lower_name])
        if "auth" in st.secrets and lower_name in st.secrets["auth"]:
            return str(st.secrets["auth"][lower_name])
    except FileNotFoundError:
        pass
    return default


def configure_runtime() -> None:
    users_json = get_secret("USERS_JSON")
    if users_json:
        os.environ["USERS_JSON"] = users_json


def format_number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:,.{digits}f}"


def format_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}%"


def login_screen() -> None:
    st.markdown(
        """
        <style>
        .block-container { max-width: 460px; padding-top: 15vh; }
        [data-testid="stForm"] {
            border: 1px solid #d9ded8;
            border-radius: 8px;
            padding: 28px;
            background: #ffffff;
            box-shadow: 0 20px 60px rgba(23, 32, 27, 0.08);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Private Market Dashboard")
    st.title("시장 국면 확인")

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("아이디", autocomplete="username")
        password = st.text_input("비밀번호", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("접속", use_container_width=True)

    if submitted:
        success, record = authenticate(username, password)
        if success and record:
            st.session_state["user"] = username.strip().lower()
            st.session_state["role"] = record.get("role", "user")
            st.session_state["force_change"] = record.get("force_change", False)
            st.rerun()
        st.error("아이디 또는 비밀번호가 맞지 않습니다.")


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
        st.caption(
            f"팔로우쓰루데이: {ftd['date']} · {format_pct(ftd['gain_pct'])} · {ftd['day_number']}일차"
        )
    else:
        st.caption("팔로우쓰루데이: 최근 랠리 시도 이후 확인 안 됨")

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

    top_left, top_right = st.columns([1, 0.18])
    with top_left:
        st.caption("William O'Neil Market Pulse")
        st.title("지수별 매수/매도 국면")
    with top_right:
        if st.button("로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    is_admin = st.session_state.get("role") == "admin"
    tabs = st.tabs(["계정", "시장 국면", "사용자 관리"] if is_admin else ["계정", "시장 국면"])
    account_tab, dashboard_tab = tabs[:2]

    with account_tab:
        render_account_settings()

    with dashboard_tab:
        render_market_dashboard()

    if is_admin:
        with tabs[2]:
            render_admin_settings()


def render_account_settings() -> None:
    st.subheader("내 비밀번호 변경")
    if st.session_state.get("force_change"):
        st.warning("임시 비밀번호를 사용 중입니다. 새 비밀번호로 변경해 주세요.")

    with st.form("change_own_password"):
        current = st.text_input("현재 비밀번호", type="password")
        new = st.text_input("새 비밀번호", type="password")
        confirm = st.text_input("새 비밀번호 확인", type="password")
        submitted = st.form_submit_button("비밀번호 변경")

    if submitted:
        success, _ = authenticate(st.session_state["user"], current)
        if not success:
            st.error("현재 비밀번호가 맞지 않습니다.")
        elif len(new) < 8:
            st.error("새 비밀번호는 8자 이상이어야 합니다.")
        elif new != confirm:
            st.error("새 비밀번호 확인이 일치하지 않습니다.")
        else:
            change_password(st.session_state["user"], new)
            st.session_state["force_change"] = False
            st.success("비밀번호가 변경되었습니다.")


def render_admin_settings() -> None:
    st.subheader("사용자 관리")
    users = get_users()
    usernames = [name for name in sorted(users) if name != "admin"]
    selected = st.selectbox("사용자", usernames)
    record = users[selected]
    st.caption(
        f"상태: {'사용 가능' if record.get('enabled', True) else '사용 중지'} · "
        f"비밀번호 변경 필요: {'예' if record.get('force_change', False) else '아니오'}"
    )

    with st.form("admin_reset_password"):
        reset_password = st.text_input("새 임시 비밀번호", type="password")
        reset_confirm = st.text_input("새 임시 비밀번호 확인", type="password")
        reset = st.form_submit_button("비밀번호 초기화")

    if reset:
        if len(reset_password) < 4:
            st.error("임시 비밀번호는 4자 이상이어야 합니다.")
        elif reset_password != reset_confirm:
            st.error("비밀번호 확인이 일치하지 않습니다.")
        else:
            change_password(selected, reset_password, force_change=True)
            st.success(f"{selected}의 비밀번호를 초기화했습니다.")

    enabled = record.get("enabled", True)
    if st.button("사용 중지" if enabled else "사용 허용"):
        set_enabled(selected, not enabled)
        st.success(f"{selected} 상태를 변경했습니다.")
        st.rerun()

    st.download_button(
        "사용자 목록 백업",
        data=export_users(),
        file_name="users-backup.json",
        mime="application/json",
    )


def render_market_dashboard() -> None:
    with st.spinner("야후 파이낸스에서 데이터를 가져오는 중입니다."):
        snapshot = get_market_snapshot()

    summary = snapshot["market_summary"]
    st.subheader(summary["regime"])
    st.info(summary["explanation"])
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

    items = list(snapshot["items"].values())
    for row_start in range(0, len(items), 2):
        cols = st.columns(2)
        for col, item in zip(cols, items[row_start : row_start + 2]):
            with col:
                render_market_card(item)

    st.caption(f"데이터는 최대 {snapshot['cache_seconds']}초 동안 캐시됩니다.")


def main() -> None:
    configure_runtime()
    if "user" not in st.session_state:
        login_screen()
    elif st.session_state.get("force_change"):
        st.title("비밀번호 변경 필요")
        render_account_settings()
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()
    else:
        dashboard()


if __name__ == "__main__":
    main()
