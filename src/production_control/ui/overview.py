"""Streamlit midterm-demo UI for production status, execution input, and replanning."""

from datetime import UTC, datetime
from os import environ
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st

from production_control.ui.api_client import ApiClientError, ProductionControlApiClient
from production_control.ui.display_labels import (
    action_label,
    display_datetime,
    event_type_label,
    gate_type_label,
    priority_rule_label,
    process_label,
    readiness_label,
    risk_label,
    status_label,
)
from production_control.ui.lot_dashboard_model import (
    build_lot_progress,
    build_process_unit_rows,
    minimum_gate_slack,
)
from production_control.ui.operator_model import (
    allowed_event_types,
    current_operation_for_unit,
    default_event_time,
    latest_execution_reference,
    parse_api_datetime,
    reason_required,
)
from production_control.ui.overview_model import build_overview_view

_DEFAULT_API_URL = "http://127.0.0.1:8000"
SEOUL = ZoneInfo("Asia/Seoul")


def _risk_text(value: object) -> str:
    risk = str(value)
    if risk == "URGENT":
        return f":red[{risk_label(risk)}]"
    if risk == "WARNING":
        return f":orange[{risk_label(risk)}]"
    if risk == "NORMAL":
        return f":green[{risk_label(risk)}]"
    return risk_label(risk)


def _unit_codes_text(value: object) -> str:
    if not isinstance(value, tuple) or not value:
        return "—"
    return ", ".join(str(item) for item in value)


def _render_lot_detail(
    *,
    lot_id: str,
    view: object,
    operations: list[dict[str, object]],
) -> None:
    process_unit_rows = [
        {
            "process_code": process_label(row["process_code"]),
            "progress": f"{row['completed']}/{row['total']}",
            "completed_units": _unit_codes_text(row["completed_units"]),
            "running_units": _unit_codes_text(row["running_units"]),
            "hold_units": _unit_codes_text(row["hold_units"]),
            "waiting_units": _unit_codes_text(row["waiting_units"]),
        }
        for row in build_process_unit_rows(operations, lot_id=lot_id)
    ]

    st.markdown("**공정별 Unit 현황**")
    st.dataframe(
        process_unit_rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "process_code": "공정",
            "progress": "완료",
            "completed_units": "완료 Unit",
            "running_units": "작업 중 Unit",
            "hold_units": "보류 Unit",
            "waiting_units": "대기 Unit",
        },
    )

    process_rows = [
        {
            "process_code": process_label(row["process_code"]),
            "forecast_start": display_datetime(row["forecast_start"]),
            "forecast_end": display_datetime(row["forecast_end"]),
        }
        for row in view.process_rows
        if row["lot_id"] == lot_id
    ]
    st.markdown("**공정 예상 일정**")
    st.dataframe(
        process_rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "process_code": "공정",
            "forecast_start": "예상 시작",
            "forecast_end": "예상 종료",
        },
    )

    gate_rows = [
        {
            "gate_type": gate_type_label(row["gate_type"]),
            "planned_at": display_datetime(row["planned_at"]),
            "forecast_at": display_datetime(row["forecast_at"]),
            "slack_minutes": row["slack_minutes"],
            "risk_level": risk_label(row["risk_level"]),
        }
        for row in view.gate_rows
        if row["lot_id"] == lot_id
    ]
    if gate_rows:
        st.markdown("**검사 일정**")
        st.dataframe(
            gate_rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "gate_type": "검사",
                "planned_at": "검사 예정",
                "forecast_at": "예상 도달",
                "slack_minutes": "여유시간(분)",
                "risk_level": "위험도",
            },
        )


def _render_overview(
    *,
    view: object,
    operations: list[dict[str, object]],
) -> None:
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

    st.subheader("LOT 생산 현황")
    st.caption("LOT별 납기·예상완료·위험도와 공정 진행을 먼저 확인합니다.")

    for row in view.lot_rows:
        lot_id = str(row["lot_id"])
        progress = build_lot_progress(operations, lot_id=lot_id)
        gate_slack = minimum_gate_slack(view.gate_rows, lot_id=lot_id)

        with st.container(border=True):
            title_col, due_col, forecast_col, risk_col = st.columns([3.2, 2.2, 2.2, 1.4])
            title_col.markdown(f"### {row['lot_code']}")
            title_col.caption(f"{status_label(row['status'])} · {row['quantity']}대")

            due_col.markdown("**납기**")
            due_col.markdown(display_datetime(row["due_at"]))

            forecast_col.markdown("**예상 완료**")
            forecast_col.markdown(display_datetime(row["forecast_end"]))

            risk_col.markdown("**위험도**")
            risk_col.markdown(_risk_text(row["risk_level"]))

            gate_text = "—" if gate_slack is None else f"{gate_slack:.0f}분"
            st.caption(f"가장 촉박한 검사 여유 · {gate_text}")

            st.markdown("**공정 진행**")
            process_columns = st.columns(len(progress.processes))
            for process_column, process in zip(
                process_columns,
                progress.processes,
                strict=True,
            ):
                process_column.caption(process_label(process.process_code))
                process_column.progress(process.fraction)
                process_column.caption(f"{process.completed}/{process.total} 완료")
                if process.running:
                    process_column.caption(f"작업 중 {process.running}")
                if process.hold:
                    process_column.caption(f"보류 {process.hold}")

            with st.expander(f"{row['lot_code']} 공정별 상세"):
                _render_lot_detail(
                    lot_id=lot_id,
                    view=view,
                    operations=operations,
                )


def _render_operator_input(
    *,
    api_url: str,
    operations: list[dict[str, object]],
) -> None:
    st.subheader("현장 작업실적 입력")
    st.caption(
        "중간발표에서는 Pico 대신 이 화면으로 WorkEvent를 입력합니다. "
        "최종 단계에서는 같은 FastAPI 입력 경로를 Pico가 사용합니다."
    )

    lot_ids = sorted({str(row["lot_id"]) for row in operations})
    if not lot_ids:
        st.info("입력 가능한 UnitOperation이 없습니다.")
        return

    selected_lot = st.selectbox("LOT", lot_ids, key="operator_lot")
    lot_operations = [row for row in operations if row.get("lot_id") == selected_lot]
    units = {str(row["unit_id"]): str(row["unit_code"]) for row in lot_operations}
    selected_unit = st.selectbox(
        "Unit",
        sorted(units),
        format_func=lambda unit_id: units[unit_id],
        key="operator_unit",
    )
    operation = current_operation_for_unit(
        operations,
        lot_id=selected_lot,
        unit_id=selected_unit,
    )
    if operation is None:
        st.success("이 Unit의 내부 공정 작업이 모두 완료되었습니다.")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("현재 공정", process_label(operation["process_code"]))
    col2.metric("현재 상태", status_label(operation["state"]))
    col3.metric("시도 회차", int(operation["attempt_no"]))
    col4.metric("누적 작업시간", f"{float(operation['active_minutes']):.1f}분")
    st.caption(
        f"작업 ID: {operation['operation_id']} · 작업 가능시각: "
        f"{display_datetime(operation['eligible_at'])}"
    )

    event_types = allowed_event_types(operation)
    if not event_types:
        st.info("현재 상태에서 입력 가능한 이벤트가 없습니다.")
        return

    suggested = default_event_time(operation).astimezone(SEOUL)
    with st.form("operator-event-form", clear_on_submit=False):
        event_type = st.selectbox(
            "작업 이벤트",
            event_types,
            format_func=event_type_label,
        )
        event_date = st.date_input("발생 날짜", value=suggested.date())
        event_clock = st.time_input(
            "발생 시각",
            value=suggested.time().replace(tzinfo=None, second=0, microsecond=0),
        )
        reason = st.text_input(
            "사유",
            placeholder="보류(HOLD) 또는 최종시험 불합격(FAIL)에서는 필수",
        )
        submitted = st.form_submit_button("실적 반영", use_container_width=True)

    if not submitted:
        return

    occurred_at = datetime.combine(event_date, event_clock, tzinfo=SEOUL)
    required_reason = reason_required(
        event_type=event_type,
        process_code=str(operation["process_code"]),
    )
    if required_reason and not reason.strip():
        st.error("이 이벤트는 사유 입력이 필요합니다.")
        return

    eligible_at = parse_api_datetime(operation.get("eligible_at"))
    if event_type == "START" and eligible_at is not None and occurred_at < eligible_at:
        st.error("작업 시작시각은 작업 가능시각보다 빠를 수 없습니다.")
        return

    try:
        with ProductionControlApiClient(base_url=api_url) as client:
            result = client.create_work_event(
                event_id=f"UI-{uuid4().hex}",
                unit_operation_id=str(operation["operation_id"]),
                event_type=event_type,
                occurred_at=occurred_at,
                reason=reason.strip() or None,
            )
    except (ApiClientError, ValueError) as exc:
        st.error(f"실적을 반영하지 못했습니다: {exc}")
        return

    st.session_state["flash_message"] = (
        f"{selected_lot} / {units[selected_unit]} / "
        f"{process_label(operation['process_code'])}: "
        f"{event_type_label(event_type)} 반영 완료 · 상태 {status_label(result['state'])}"
    )
    st.rerun()


def _render_replan(
    *,
    api_url: str,
    reference_time: datetime,
) -> None:
    st.subheader("재계획 후보 비교 및 승인")
    st.caption(
        "현재 Forecast 위험도를 기준으로 FCFS / EDD / Slack / CR 후보를 서버에서 계산합니다. "
        "긴급 상태가 아니면 후보를 만들지 않습니다."
    )

    if st.button("현재 상태로 재계획 후보 계산", use_container_width=True):
        try:
            with ProductionControlApiClient(base_url=api_url) as client:
                snapshot = client.create_replan_candidates(as_of=reference_time)
        except (ApiClientError, ValueError) as exc:
            st.error(f"재계획 후보를 계산하지 못했습니다: {exc}")
        else:
            st.session_state["replan_snapshot"] = snapshot

    snapshot = st.session_state.get("replan_snapshot")
    if not isinstance(snapshot, dict):
        st.info("필요할 때 위 버튼을 눌러 현재 상태의 재계획 후보를 계산합니다.")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("현재 위험", risk_label(snapshot.get("risk_level")))
    col2.metric("시스템 동작", action_label(snapshot.get("action")))
    col3.metric("기준 계획", f"v{snapshot.get('parent_plan_version', '—')}")
    recommended = snapshot.get("recommended_candidate_id")
    col4.metric("추천 후보", priority_rule_label(recommended) if recommended else "없음")
    st.caption(f"후보 계산 기준시각: {display_datetime(snapshot.get('as_of'))}")

    candidates = snapshot.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        st.info("현재 상태에서는 관리자 승인이 필요한 재계획 후보가 없습니다.")
        return

    rows = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        kpi = candidate.get("kpi", {})
        if not isinstance(kpi, dict):
            kpi = {}
        candidate_id = str(candidate.get("candidate_id", ""))
        rows.append(
            {
                "candidate_id": candidate_id,
                "rule": priority_rule_label(candidate.get("rule")),
                "recommended": "추천" if candidate_id == recommended else "",
                "late_lot_count": kpi.get("late_lot_count"),
                "total_tardiness_minutes": kpi.get("total_tardiness_minutes"),
                "overtime_minutes": kpi.get("overtime_minutes"),
                "change_count": kpi.get("change_count"),
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "candidate_id": "후보 ID",
            "rule": "우선순위 규칙",
            "recommended": "추천",
            "late_lot_count": "지연 LOT 수",
            "total_tardiness_minutes": "총 지각시간(분)",
            "overtime_minutes": "초과근무(분)",
            "change_count": "계획 변경 수",
        },
    )
    st.caption(
        "V1의 초과근무 용량 모델은 아직 미구현이므로 overtime_minutes는 현재 비교에서 0입니다."
    )

    candidate_ids = [row["candidate_id"] for row in rows]
    selected = st.selectbox(
        "승인할 후보",
        candidate_ids,
        format_func=lambda value: (
            f"{priority_rule_label(value)}{' · 추천' if value == recommended else ''}"
        ),
    )
    selected_detail = next(
        (
            candidate
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("candidate_id") == selected
        ),
        None,
    )
    if isinstance(selected_detail, dict):
        tasks = selected_detail.get("tasks")
        if isinstance(tasks, list):
            with st.expander("선택 후보 작업순서 보기"):
                task_rows = [
                    {
                        "lot_id": task.get("lot_id"),
                        "routing_step_id": task.get("routing_step_id"),
                        "target_start": display_datetime(task.get("target_start")),
                        "target_end": display_datetime(task.get("target_end")),
                        "priority_rank": task.get("priority_rank"),
                    }
                    for task in tasks
                    if isinstance(task, dict)
                ]
                st.dataframe(task_rows, use_container_width=True, hide_index=True)

    if not st.button("선택 후보 승인", type="primary", use_container_width=True):
        return

    candidate_as_of = parse_api_datetime(snapshot.get("as_of"))
    parent_plan_id = snapshot.get("parent_plan_id")
    if candidate_as_of is None or not isinstance(parent_plan_id, str):
        st.error("후보 스냅샷의 승인 정보가 올바르지 않습니다. 후보를 다시 계산해주세요.")
        return

    try:
        with ProductionControlApiClient(base_url=api_url) as client:
            approval = client.approve_replan(
                parent_plan_id=parent_plan_id,
                candidate_id=selected,
                candidate_as_of=candidate_as_of,
            )
    except (ApiClientError, ValueError) as exc:
        st.error(f"재계획을 승인하지 못했습니다: {exc}")
        return

    st.session_state.pop("replan_snapshot", None)
    st.session_state["flash_message"] = (
        f"{priority_rule_label(selected)} 승인 완료 · 새 승인계획 v{approval['version']}"
    )
    st.rerun()


def run() -> None:
    st.set_page_config(page_title="생산진도 관리자 대시보드", layout="wide")
    st.title("생산진도 관리자 대시보드")
    st.caption("현장 실적 → Forecast → 위험 판단 → 재계획 승인을 한 화면에서 시연합니다.")

    configured_url = environ.get("PRODUCTION_CONTROL_API_URL", _DEFAULT_API_URL)
    api_url = st.sidebar.text_input("FastAPI 주소", value=configured_url)
    st.sidebar.caption("로컬 데모는 127.0.0.1에서만 실행하고 외부 포트를 열지 않습니다.")
    st.sidebar.button("새로고침", use_container_width=True)

    flash_message = st.session_state.pop("flash_message", None)
    if flash_message:
        st.success(str(flash_message))

    try:
        with ProductionControlApiClient(base_url=api_url) as client:
            operations = client.list_unit_operations()
            reference_time = latest_execution_reference(
                operations,
                now=datetime.now(UTC),
            )
            forecast = client.get_forecast(as_of=reference_time)
            lots = client.list_lots()
            gates = client.list_inspection_gates()
    except (ApiClientError, ValueError) as exc:
        st.error(f"FastAPI 데이터를 불러오지 못했습니다: {exc}")
        st.stop()

    view = build_overview_view(forecast=forecast, lots=lots, gates=gates)

    overview_tab, operator_tab, replan_tab = st.tabs(
        ["생산현황", "현장 실적 입력", "재계획"]
    )
    with overview_tab:
        _render_overview(view=view, operations=operations)
    with operator_tab:
        _render_operator_input(api_url=api_url, operations=operations)
    with replan_tab:
        _render_replan(api_url=api_url, reference_time=reference_time)


if __name__ == "__main__":
    run()
