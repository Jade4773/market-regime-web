from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st
from werkzeug.security import check_password_hash

from market_data import get_market_snapshot
from user_store import load_users


st.set_page_config(
    page_title="Market Regime",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def get_secret(name: str, default: str = "") -> str:
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
    return os.getenv(name, default)


def load_allowed_users() -> dict[str, Any]:
    users_json = get_secret("USERS_JSON")
    if users_json:
        return json.loads(users_json)
    return load_users()


def authenticate(username: str, password: str) -> bool:
    users = load_allowed_users()
    record = users.get(username.strip().lower())
    if not record or not record.get("enabled", True):
        return False
    return check_password_hash(record["password_hash"], password)


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
        if authenticate(username, password):
            st.session_state["user"] = username.strip().lower()
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
                        "등락률": format_pct(day["change_pct"]),
                        "종가": format_number(day["close"]),
                    }
                    for day in distribution_days
                ],
                hide_index=True,
                use_container_width=True,
            )
    else:
        st.caption("최근 25거래일 내 분산일 없음")


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
            st.session_state.pop("user", None)
            st.rerun()

    with st.spinner("야후 파이낸스에서 데이터를 가져오는 중입니다."):
        snapshot = get_market_snapshot()

    items = list(snapshot["items"].values())
    for row_start in range(0, len(items), 2):
        cols = st.columns(2)
        for col, item in zip(cols, items[row_start : row_start + 2]):
            with col:
                render_market_card(item)

    st.caption(f"데이터는 최대 {snapshot['cache_seconds']}초 동안 캐시됩니다.")


def main() -> None:
    if "user" not in st.session_state:
        login_screen()
    else:
        dashboard()


if __name__ == "__main__":
    main()
