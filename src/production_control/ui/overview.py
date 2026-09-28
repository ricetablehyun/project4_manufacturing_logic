"""Streamlit read-only Overview page for production-control administrators."""

from os import environ

import streamlit as st

from production_control.ui.api_client import ApiClientError, ProductionControlApiClient
from production_control.ui.display_labels import (
    display_datetime,
    gate_type_label,
    process_label,
    readiness_label,
    risk_label,
    status_label,
)
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
    plan_col.metric("현재 승인 계획", f"v{view.plan_version}")
    readiness_col.metric("예상 일정 상태", readiness_label(view.readiness))
    urgent_col.metric("긴급 LOT", view.urgent_lot_count)
    warning_col.metric("주의 LOT", view.warning_lot_count)
    waiting_col.metric("입력 대기 작업", view.waiting_operation_count)

    st.caption(
        f"계획 ID: {view.plan_id} · 예상 일정 기준시각: {display_datetime(view.as_of)}"
    )

    if view.readiness != "READY":
        st.warning(
            "예상 일정 계산이 완료되지 않았습니다. "
            "입력 대기 작업 또는 아직 확정되지 않은 입력값을 확인해야 합니다."
        )
    if view.missing_gate_ids:
        st.warning("예상 일정 입력이 없는 검사 Gate: " + ", ".join(view.missing_gate_ids))

    lot_rows = [
        {
            **row,
            "status": status_label(row["status"]),
            "due_at": display_datetime(row["due_at"]),
            "forecast_end": display_datetime(row["forecast_end"]),
            "risk_level": risk_label(row["risk_level"]),
        }
        for row in view.lot_rows
    ]

    st.subheader("LOT 현황")
    st.dataframe(
        lot_rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "lot_id": "LOT ID",
            "lot_code": "LOT 코드",
            "status": "상태",
            "quantity": "수량",
            "due_at": "납기",
            "forecast_end": "예상 완료",
            "risk_level": "위험도",
        },
    )

    gate_rows = [
        {
            **row,
            "gate_type": gate_type_label(row["gate_type"]),
            "status": status_label(row["status"]),
            "planned_at": display_datetime(row["planned_at"]),
            "forecast_at": display_datetime(row["forecast_at"]),
            "risk_level": risk_label(row["risk_level"]),
            "completed_at": display_datetime(row["completed_at"]),
        }
        for row in view.gate_rows
    ]

    st.subheader("검사 Gate 위험")
    st.dataframe(
        gate_rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "gate_id": "검사 Gate ID",
            "lot_id": "LOT",
            "gate_type": "검사 종류",
            "status": "상태",
            "planned_at": "검사 예정",
            "forecast_at": "예상 도달",
            "slack_minutes": "여유시간(분)",
            "risk_level": "위험도",
            "completed_at": "완료 시각",
        },
    )

    process_rows = [
        {
            **row,
            "process_code": process_label(row["process_code"]),
            "forecast_start": display_datetime(row["forecast_start"]),
            "forecast_end": display_datetime(row["forecast_end"]),
        }
        for row in view.process_rows
    ]

    st.subheader("LOT × 공정 예상 일정")
    st.dataframe(
        process_rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "lot_id": "LOT",
            "process_code": "공정",
            "forecast_start": "예상 시작",
            "forecast_end": "예상 종료",
            "scheduled_operation_count": "작업 수",
        },
    )

    st.caption(
        "현재 화면은 읽기 전용 생산진도 현황판입니다. "
        "편집과 재계획 승인은 후속 관리자 화면에서 연결합니다."
    )


def run() -> None:
    st.set_page_config(page_title="생산진도 관리자 대시보드", layout="wide")
    st.title("생산진도 관리자 대시보드")
    st.caption("현장 실적을 반영한 예상 일정과 납기 위험을 한 화면에서 확인합니다.")

    configured_url = environ.get("PRODUCTION_CONTROL_API_URL", _DEFAULT_API_URL)
    api_url = st.sidebar.text_input("FastAPI 주소", value=configured_url)
    st.sidebar.caption("환경변수 PRODUCTION_CONTROL_API_URL로 기본값을 변경할 수 있습니다.")
    st.sidebar.button("새로고침", use_container_width=True)

    _render_overview(api_url=api_url)


if __name__ == "__main__":
    run()
