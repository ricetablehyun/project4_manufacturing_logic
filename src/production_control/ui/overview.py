"""Streamlit read-only Overview page for production-control administrators."""

from os import environ

import streamlit as st

from production_control.ui.api_client import ApiClientError, ProductionControlApiClient
from production_control.ui.overview_model import build_overview_view

_DEFAULT_API_URL = "http://127.0.0.1:8000"


def _render_overview(*, api_url: str) -> None:
    try:
        with ProductionControlApiClient(base_url=api_url) as client:
            forecast = client.get_forecast()
            lots = client.list_lots()
            gates = client.list_inspection_gates()
    except (ApiClientError, ValueError) as exc:
        st.error(f"FastAPI 데이터를 불러오지 못했습니다: {exc}")
        st.stop()

    view = build_overview_view(forecast=forecast, lots=lots, gates=gates)

    plan_col, readiness_col, urgent_col, warning_col, waiting_col = st.columns(5)
    plan_col.metric("Approved Plan", f"v{view.plan_version}")
    readiness_col.metric("Forecast", view.readiness)
    urgent_col.metric("URGENT LOT", view.urgent_lot_count)
    warning_col.metric("WARNING LOT", view.warning_lot_count)
    waiting_col.metric("WAIT Operation", view.waiting_operation_count)

    st.caption(f"Plan ID: {view.plan_id} · Forecast 기준시각: {view.as_of}")

    if view.readiness != "READY":
        st.warning(
            "Forecast가 READY가 아닙니다. WAIT operation 또는 미확정 입력을 확인해야 합니다."
        )
    if view.missing_gate_ids:
        st.warning("Forecast 입력이 없는 Gate: " + ", ".join(view.missing_gate_ids))

    st.subheader("LOT 현황")
    st.dataframe(
        list(view.lot_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "lot_id": "LOT ID",
            "lot_code": "LOT Code",
            "status": "상태",
            "quantity": "수량",
            "due_at": "납기",
            "forecast_end": "예상 완료",
            "risk_level": "Risk",
        },
    )

    st.subheader("Inspection Gate Risk")
    st.dataframe(
        list(view.gate_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "gate_id": "Gate ID",
            "lot_id": "LOT",
            "gate_type": "Gate Type",
            "status": "상태",
            "planned_at": "예정",
            "forecast_at": "Forecast",
            "slack_minutes": "Slack (min)",
            "risk_level": "Risk",
            "completed_at": "완료",
        },
    )

    st.subheader("LOT × Process Forecast")
    st.dataframe(
        list(view.process_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "lot_id": "LOT",
            "process_code": "Process",
            "forecast_start": "Forecast Start",
            "forecast_end": "Forecast End",
            "scheduled_operation_count": "Operation 수",
        },
    )

    st.caption("현재 화면은 D061 read-only Overview입니다. 편집과 재계획 승인은 후속 화면에서 연결합니다.")


def run() -> None:
    st.set_page_config(page_title="생산진도 관리자 Overview", layout="wide")
    st.title("생산진도 관리자 Overview")
    st.caption("현장 실적을 반영한 Forecast와 납기 위험을 한 화면에서 확인합니다.")

    configured_url = environ.get("PRODUCTION_CONTROL_API_URL", _DEFAULT_API_URL)
    api_url = st.sidebar.text_input("FastAPI URL", value=configured_url)
    st.sidebar.caption("환경변수 PRODUCTION_CONTROL_API_URL로 기본값을 변경할 수 있습니다.")
    st.sidebar.button("새로고침", use_container_width=True)

    _render_overview(api_url=api_url)


if __name__ == "__main__":
    run()
