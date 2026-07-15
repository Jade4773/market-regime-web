from __future__ import annotations

import traceback

import streamlit as st


def main() -> None:
    st.set_page_config(
        page_title="Market Regime",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    try:
        from market_pulse.ui import dashboard

        dashboard()
    except Exception as exc:
        st.error("앱을 불러오는 중 문제가 발생했습니다. 잠시 후 새로고침해 주세요.")
        st.caption(f"오류 내용: {exc}")
        with st.expander("오류 상세"):
            st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
