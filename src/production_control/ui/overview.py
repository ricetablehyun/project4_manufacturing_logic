"""Streamlit midterm-demo UI for production status, execution input, and replanning."""

from datetime import UTC, datetime
from os import environ
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st

from production_control.ui.api_client import ApiClientError, ProductionControlApiClient
from production_control.ui.display_labels import (
    display_datetime,
    event_type_label,
    gate_type_label,
    priority_rule_label,
    process_label,
    risk_label,
    status_label,
)
from production_control.ui.lot_dashboard_model import (
    build_lot_progress,
    build_process_execution_detail_rows,
    build_process_status_rows,
    format_duration_minutes,
    minimum_gate_slack,
    shipping_inspection_expected_finish,
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
from production_control.ui.replan_view_model import (
    build_replan_impact_rows,
    rank_replan_candidates,
    summarize_replan_status,
)

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


def _compact_datetime(value: object) -> str:
    parsed = parse_api_datetime(value)
    if parsed is None:
        return "—"
    return parsed.astimezone(SEOUL).strftime("%m/%d %H:%M")


def _window_text(start: object, end: object) -> str:
    compact_start = _compact_datetime(start)
    compact_end = _compact_datetime(end)
    if compact_start == "—" and compact_end == "—":
        return "—"
    return f"{compact_start} → {compact_end}"


def _plan_window_text(row: dict[str, object]) -> str:
    return _window_text(row.get("plan_start"), row.get("plan_end"))


def _lot_plan_end(plan_tasks: list[dict[str, object]], *, lot_id: str) -> str:
    values = [
        parse_api_datetime(task.get("target_end"))
        for task in plan_tasks
        if task.get("lot_id") == lot_id
    ]
    datetimes = [value for value in values if value is not None]
    if not datetimes:
        return "—"
    return display_datetime(max(datetimes))


def _inspection_finish_text(row: dict[str, object]) -> str:
    if str(row.get("gate_type")) != "SHIPPING_INSPECTION":
        return "—"
    planned_start = parse_api_datetime(row.get("planned_at"))
    if planned_start is None:
        return "—"
    return display_datetime(shipping_inspection_expected_finish(planned_start))


def _process_forecast_text(row: dict[str, object]) -> str:
    if bool(row.get("process_complete")):
        return "완료"
    forecast_end = row.get("forecast_end")
    if forecast_end in (None, "", "—"):
        return "계산 대기"
    return _compact_datetime(forecast_end)


def _forecast_status_text(readiness: object) -> str:
    text = str(readiness)
    if text == "READY":
        return "최신 실적 반영"
    if text == "WAIT":
        return "작업자 입력 대기"
    return "상태 미확인"


def _schedule_shift_text(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    minutes = float(value)
    if abs(minutes) < 0.01:
        return "변경 없음"
    direction = "앞당김" if minutes < 0 else "늦어짐"
    return f"{format_duration_minutes(abs(minutes))} {direction}"


def _render_lot_detail(
    *,
    lot_id: str,
    view: object,
    operations: list[dict[str, object]],
    plan_tasks: list[dict[str, object]],
) -> None:
    raw_process_rows = build_process_status_rows(
        operations,
        view.process_rows,
        lot_id=lot_id,
        plan_tasks=plan_tasks,
    )
    process_rows = [
        {
            "process_code": process_label(row["process_code"]),
            "plan_window": _plan_window_text(row),
            "forecast_end": _process_forecast_text(row),
            "progress": f"{row['completed']}/{row['total']}",
            "completed_count": len(row["completed_units"]),
            "running_count": len(row["running_units"]),
            "hold_count": len(row["hold_units"]),
            "waiting_count": len(row["waiting_units"]),
        }
        for row in raw_process_rows
    ]

    st.markdown("**공정별 계획 및 진행**")
    st.caption(
        "공식 계획은 LOT×공정 기간으로 관리합니다. Forecast는 현재 실적과 Unit Active time을 "
        "반영한 계산값이며 Unit별 완료예정시각은 표시하지 않습니다."
    )
    st.dataframe(
        process_rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "process_code": "공정",
            "plan_window": "승인 계획 기간",
            "forecast_end": "현재 생산 완료 예상",
            "progress": "진척",
            "completed_count": "완료",
            "running_count": "작업 중",
            "hold_count": "보류",
            "waiting_count": "대기",
        },
    )

    process_codes = [str(row["process_code"]) for row in raw_process_rows]
    if process_codes:
        st.markdown("**공정 내부 Unit 상세**")
        selected_process = st.selectbox(
            "확인할 공정",
            process_codes,
            format_func=process_label,
            key=f"lot-process-detail-{lot_id}",
        )
        unit_rows = [
            {
                "unit_code": row["unit_code"],
                "state": status_label(row["state"]),
                "attempt_no": row["attempt_no"],
                "active_minutes": f"{float(row['active_minutes']):.1f}",
                "result": row["result"] or "—",
            }
            for row in build_process_execution_detail_rows(
                operations,
                lot_id=lot_id,
                process_code=selected_process,
            )
        ]
        st.dataframe(
            unit_rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "unit_code": "Unit",
                "state": "상태",
                "attempt_no": "시도 회차",
                "active_minutes": "누적 작업시간(분)",
                "result": "결과",
            },
        )

    gate_rows = [
        {
            "gate_type": gate_type_label(row["gate_type"]),
            "planned_at": display_datetime(row["planned_at"]),
            "planned_finish_at": _inspection_finish_text(row),
            "forecast_at": display_datetime(row["forecast_at"]),
            "slack_text": format_duration_minutes(row["slack_minutes"]),
            "risk_level": risk_label(row["risk_level"]),
        }
        for row in view.gate_rows
        if row["lot_id"] == lot_id
    ]
    if gate_rows:
        st.markdown("**품질 통보 검사 일정**")
        st.caption(
            "출하검사 시작 전까지 내부 생산이 완료되어야 하며, 출하검사는 주말을 제외하고 "
            "3영업일 진행합니다."
        )
        st.dataframe(
            gate_rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "gate_type": "검사",
                "planned_at": "출하검사 시작",
                "planned_finish_at": "검사 예상 종료",
                "forecast_at": "생산 완료 예상",
                "slack_text": "검사 진입 여유",
                "risk_level": "위험도",
            },
        )


def _render_overview(
    *,
    view: object,
    operations: list[dict[str, object]],
    plan_tasks: list[dict[str, object]],
) -> None:
    plan_col, readiness_col, urgent_col, warning_col, waiting_col = st.columns(5)
    plan_col.metric("현재 승인 계획", f"v{view.plan_version}")
    readiness_col.metric("Forecast 상태", _forecast_status_text(view.readiness))
    urgent_col.metric("긴급 LOT", view.urgent_lot_count)
    warning_col.metric("주의 LOT", view.warning_lot_count)
    waiting_col.metric("입력 대기 작업", view.waiting_operation_count)

    st.caption(f"계획 ID: {view.plan_id} · Forecast 기준시각: {display_datetime(view.as_of)}")

    if view.readiness != "READY":
        st.warning(
            "생산 완료 예상 계산이 대기 중입니다. 현장 실적 입력에서 표시된 RUNNING 작업의 "
            "예상 잔여시간을 입력하면 다시 계산됩니다."
        )
    if view.missing_gate_ids:
        st.warning("예상 일정 입력이 없는 검사 Gate: " + ", ".join(view.missing_gate_ids))

    st.subheader("LOT 생산 현황")
    st.caption("LOT별 승인계획·현재 Forecast·납기위험과 실행상태를 확인합니다.")

    for row in view.lot_rows:
        lot_id = str(row["lot_id"])
        progress = build_lot_progress(operations, lot_id=lot_id)
        gate_slack = minimum_gate_slack(view.gate_rows, lot_id=lot_id)

        with st.container(border=True):
            title_col, plan_end_col, due_col, risk_col = st.columns([3.2, 2.4, 2.2, 1.2])
            title_col.markdown(f"### {row['lot_code']}")
            title_col.caption(f"{status_label(row['status'])} · {row['quantity']}대")
            plan_end_col.markdown("**내부생산 계획완료**")
            plan_end_col.markdown(_lot_plan_end(plan_tasks, lot_id=lot_id))
            due_col.markdown("**납기**")
            due_col.markdown(display_datetime(row["due_at"]))
            risk_col.markdown("**위험도**")
            risk_col.markdown(_risk_text(row["risk_level"]))

            st.caption(
                "현재 생산 완료 예상 · "
                f"{display_datetime(row['forecast_end'])} · "
                "출하검사 진입 여유 · "
                f"{format_duration_minutes(gate_slack)}"
            )

            st.markdown("**공정 진행**")
            process_columns = st.columns(len(progress.processes))
            for process_column, process in zip(process_columns, progress.processes, strict=True):
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
                    plan_tasks=plan_tasks,
                )


def _render_operator_input(
    *,
    api_url: str,
    operations: list[dict[str, object]],
    lot_code_by_id: dict[str, str],
    waiting_operation_ids: set[str],
) -> None:
    st.subheader("현장 작업실적 입력")
    st.caption(
        "중간발표에서는 Pico 대신 이 화면으로 WorkEvent를 입력합니다. 최종 단계에서는 같은 "
        "FastAPI 입력 경로를 Pico가 사용합니다."
    )

    waiting_rows = [
        row for row in operations if str(row.get("operation_id")) in waiting_operation_ids
    ]
    if waiting_rows:
        waiting_text = ", ".join(
            f"{row.get('unit_code')} {process_label(row.get('process_code'))}"
            for row in waiting_rows
        )
        st.warning(f"작업자 예상 잔여시간 입력 필요: {waiting_text}")

    lot_ids = sorted({str(row["lot_id"]) for row in operations})
    if not lot_ids:
        st.info("입력 가능한 UnitOperation이 없습니다.")
        return

    selected_lot = st.selectbox(
        "LOT",
        lot_ids,
        format_func=lambda lot_id: lot_code_by_id.get(lot_id, lot_id),
        key="operator_lot",
    )
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

    operation_id = str(operation["operation_id"])
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("현재 공정", process_label(operation["process_code"]))
    col2.metric("현재 상태", status_label(operation["state"]))
    col3.metric("시도 회차", int(operation["attempt_no"]))
    col4.metric("누적 작업시간", f"{float(operation['active_minutes']):.1f}분")
    st.caption(
        f"작업 ID: {operation_id} · 작업 가능시각: {display_datetime(operation['eligible_at'])}"
    )

    existing_remaining = operation.get("expected_remaining_minutes")
    needs_remaining = operation_id in waiting_operation_ids
    if str(operation.get("state")) == "RUNNING" and (
        needs_remaining or existing_remaining is not None
    ):
        with st.expander("예상 잔여 작업시간 입력/수정", expanded=needs_remaining):
            if needs_remaining:
                st.caption(
                    "현재 작업이 Pace 기준을 초과해 Forecast가 입력을 기다리고 있습니다. "
                    "작업을 계속한다고 봤을 때 앞으로 더 필요한 작업시간을 입력합니다."
                )
            initial_remaining = float(existing_remaining or 10.0)
            with st.form(f"expected-remaining-form-{operation_id}"):
                remaining_minutes = st.number_input(
                    "앞으로 더 필요한 작업시간(분)",
                    min_value=1.0,
                    value=initial_remaining,
                    step=5.0,
                    key=f"expected-remaining-input-{operation_id}",
                )
                remaining_submitted = st.form_submit_button(
                    "예상 잔여 작업시간 반영",
                    use_container_width=True,
                )
            if remaining_submitted:
                try:
                    with ProductionControlApiClient(base_url=api_url) as client:
                        client.update_expected_remaining(
                            unit_operation_id=operation_id,
                            expected_remaining_minutes=float(remaining_minutes),
                        )
                except (ApiClientError, ValueError) as exc:
                    st.error(f"예상 잔여시간을 반영하지 못했습니다: {exc}")
                else:
                    st.session_state["flash_message"] = (
                        f"{units[selected_unit]} 예상 잔여 작업시간 "
                        f"{float(remaining_minutes):g}분 반영 완료"
                    )
                    st.rerun()

    event_types = allowed_event_types(operation)
    if not event_types:
        st.info("현재 상태에서 입력 가능한 이벤트가 없습니다.")
        return

    event_type = st.selectbox(
        "작업 이벤트",
        [""] + list(event_types),
        format_func=lambda value: "이벤트 선택" if not value else event_type_label(value),
        key=f"operator-event-type-{operation_id}",
    )
    if not event_type:
        st.caption(
            "작업 시작·완료·보류·재개 등 실제 발생한 이벤트가 있을 때 선택합니다. "
            "예상 잔여 작업시간 입력과 HOLD는 서로 다른 입력입니다."
        )
        return

    suggested = default_event_time(operation, now=datetime.now(UTC)).astimezone(SEOUL)
    with st.form(f"operator-event-form-{operation_id}", clear_on_submit=False):
        event_date = st.date_input(
            "발생 날짜",
            value=suggested.date(),
            key=f"operator-event-date-{operation_id}",
        )
        event_clock = st.time_input(
            "발생 시각",
            value=suggested.time().replace(tzinfo=None, second=0, microsecond=0),
            key=f"operator-event-time-{operation_id}",
        )
        reason = st.text_input(
            "사유",
            placeholder="보류(HOLD) 또는 최종시험 불합격(FAIL)에서는 필수",
            key=f"operator-event-reason-{operation_id}",
        )
        expected_hold_minutes: float | None = None
        if event_type == "HOLD":
            st.caption(
                "예상 보류시간은 작업시간이 아니라 이 Unit이 다시 작업 가능해질 때까지의 "
                "대기 예상시간입니다."
            )
            expected_hold_minutes = float(
                st.number_input(
                    "예상 보류 지속시간(분, 경과시간)",
                    min_value=1.0,
                    value=480.0,
                    step=30.0,
                    key=f"operator-hold-minutes-{operation_id}",
                )
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
                unit_operation_id=operation_id,
                event_type=event_type,
                occurred_at=occurred_at,
                reason=reason.strip() or None,
                expected_hold_minutes=expected_hold_minutes,
            )
    except (ApiClientError, ValueError) as exc:
        st.error(f"실적을 반영하지 못했습니다: {exc}")
        return

    hold_suffix = (
        f" · 예상 보류 {expected_hold_minutes:g}분"
        if expected_hold_minutes is not None
        else ""
    )
    st.session_state["flash_message"] = (
        f"{lot_code_by_id.get(selected_lot, selected_lot)} / {units[selected_unit]} / "
        f"{process_label(operation['process_code'])}: "
        f"{event_type_label(event_type)} 반영 완료 · 상태 {status_label(result['state'])}"
        f"{hold_suffix}"
    )
    st.rerun()


def _candidate_process_code(
    task: dict[str, object],
    *,
    current_by_key: dict[tuple[str, str], dict[str, object]],
) -> object:
    key = (str(task.get("lot_id")), str(task.get("routing_step_id")))
    current = current_by_key.get(key)
    if current is None:
        return task.get("routing_step_id", "—")
    return current.get("process_code", task.get("routing_step_id", "—"))


def _candidate_tasks(candidate: dict[str, object]) -> list[dict[str, object]]:
    raw_tasks = candidate.get("tasks")
    if not isinstance(raw_tasks, list):
        return []
    return [task for task in raw_tasks if isinstance(task, dict)]


def _candidate_impacts(
    *,
    candidate: dict[str, object],
    plan_tasks: list[dict[str, object]],
    process_rows: object,
    lot_code_by_id: dict[str, str],
) -> tuple[dict[str, object], ...]:
    return build_replan_impact_rows(
        approved_tasks=plan_tasks,
        current_forecast_rows=process_rows,
        candidate_tasks=_candidate_tasks(candidate),
        lot_code_by_id=lot_code_by_id,
    )


def _render_replan(
    *,
    api_url: str,
    reference_time: datetime,
    view: object,
    plan_tasks: list[dict[str, object]],
    lot_code_by_id: dict[str, str],
) -> None:
    st.subheader("재계획")
    st.caption(
        "현재 실적을 반영한 Forecast가 검사 Gate에 미치는 영향을 확인하고, 납기 위험이 생기면 "
        "이후 남은 LOT×공정 일정을 다시 계산합니다."
    )

    status = summarize_replan_status(readiness=view.readiness, gate_rows=view.gate_rows)
    if status.readiness != "READY":
        st.session_state.pop("replan_snapshot", None)
        st.warning(
            "현재 상태: Forecast 입력 대기 · 생산 완료 예상이 확정되지 않아 재계획 여부를 "
            "판단할 수 없습니다. 현장 실적 입력에서 필요한 예상 잔여시간을 먼저 입력하세요."
        )
        return

    lot_code = (
        lot_code_by_id.get(status.lot_id, status.lot_id)
        if status.lot_id is not None
        else "해당 LOT"
    )
    gate_name = gate_type_label(status.gate_type) if status.gate_type else "검사 Gate"

    if status.risk_level == "NORMAL":
        st.session_state.pop("replan_snapshot", None)
        st.success("현재 상태: 정상 · 재계획 필요 없음")
        if status.slack_minutes is not None:
            st.caption(
                f"{lot_code} {gate_name} 진입 여유는 "
                f"{format_duration_minutes(status.slack_minutes)}입니다. 현재 승인계획을 유지합니다."
            )
        return

    if status.risk_level == "WARNING":
        st.session_state.pop("replan_snapshot", None)
        st.warning("현재 상태: 주의 · 공식계획은 유지하고 Forecast를 계속 감시합니다.")
        if status.slack_minutes is not None:
            st.caption(
                f"{lot_code} {gate_name} 진입 여유는 "
                f"{format_duration_minutes(status.slack_minutes)}입니다. WARNING에서는 후보를 "
                "생성하지 않습니다."
            )
        return

    if status.risk_level != "URGENT":
        st.session_state.pop("replan_snapshot", None)
        st.info("현재 Gate 위험도를 판단할 수 없어 재계획 후보를 생성하지 않습니다.")
        return

    if status.slack_minutes is not None and status.slack_minutes < 0:
        st.error(
            f"현재 문제: {lot_code} 생산 완료 예상이 {gate_name} 시작보다 "
            f"{format_duration_minutes(abs(status.slack_minutes))} 늦습니다."
        )
    else:
        st.error(
            f"현재 문제: {lot_code} {gate_name} 진입 여유가 없어 재계획 검토가 필요합니다."
        )

    st.markdown("**재계획에서 바꾸는 것**")
    st.caption(
        "현재 RUNNING 작업은 중단하지 않습니다. 그 이후 남은 LOT×공정의 시작·완료 예상과 "
        "우선순위를 FCFS / EDD / Slack / CR 네 방식으로 다시 계산합니다. 긴급납기 LOT 우선 "
        "정책을 위반한 안은 비교는 하되 승인할 수 없습니다."
    )

    if st.button("4개 재계획안 계산·비교", type="primary", use_container_width=True):
        try:
            with ProductionControlApiClient(base_url=api_url) as client:
                snapshot = client.create_replan_candidates(as_of=reference_time)
        except (ApiClientError, ValueError) as exc:
            st.error(f"재계획 후보를 계산하지 못했습니다: {exc}")
        else:
            st.session_state["replan_snapshot"] = snapshot

    snapshot = st.session_state.get("replan_snapshot")
    if not isinstance(snapshot, dict):
        st.info(
            "버튼을 누르면 같은 현재 상태에서 네 방법을 계산한 뒤 납기성과가 좋은 결과부터 "
            "정렬해 보여줍니다."
        )
        return

    candidates = snapshot.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        st.info("현재 상태에서는 관리자 승인이 필요한 재계획 후보가 없습니다.")
        return

    candidate_by_id = {
        str(candidate.get("candidate_id")): candidate
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("candidate_id") is not None
    }
    ranked_candidates = rank_replan_candidates(tuple(candidate_by_id.values()))
    ranking_by_id = {str(row["candidate_id"]): row for row in ranked_candidates}
    compliant_candidate_ids = [
        str(row["candidate_id"])
        for row in ranked_candidates
        if row["policy_compliant"] is True
    ]

    top_candidate_ids = [
        str(row["candidate_id"])
        for row in ranked_candidates
        if row["policy_compliant"] is True and row["rank"] == 1
    ]
    if len(top_candidate_ids) == 1:
        top = candidate_by_id[top_candidate_ids[0]]
        top_kpi = top.get("kpi", {})
        if not isinstance(top_kpi, dict):
            top_kpi = {}
        top_impacts = _candidate_impacts(
            candidate=top,
            plan_tasks=plan_tasks,
            process_rows=view.process_rows,
            lot_code_by_id=lot_code_by_id,
        )
        st.success(
            f"1순위 추천: {priority_rule_label(top.get('rule'))} · "
            f"지연 LOT {top_kpi.get('late_lot_count', '—')} · "
            f"총 지연 {format_duration_minutes(top_kpi.get('total_tardiness_minutes'))} · "
            f"현재 Forecast 대비 일정변경 공정 {len(top_impacts)}개"
        )
    elif len(top_candidate_ids) > 1:
        st.info(
            f"상위 {len(top_candidate_ids)}개 후보가 D029 기준 공동 1위입니다. 현재 조건에서는 "
            "납기성과와 기존계획 변경량으로 우열을 가릴 수 없습니다."
        )

    st.markdown("### 재계획 대안 순위")
    comparison_rows = []
    for ranked in ranked_candidates:
        candidate_id = str(ranked["candidate_id"])
        candidate = candidate_by_id[candidate_id]
        kpi = candidate.get("kpi", {})
        if not isinstance(kpi, dict):
            kpi = {}
        impacts = _candidate_impacts(
            candidate=candidate,
            plan_tasks=plan_tasks,
            process_rows=view.process_rows,
            lot_code_by_id=lot_code_by_id,
        )
        if ranked["policy_compliant"] is True:
            rank_number = int(ranked["rank"])
            rank_text = f"공동 {rank_number}위" if ranked["tied"] else f"{rank_number}위"
            policy_text = "정책 충족"
        else:
            rank_text = "순위 제외"
            policy_text = "승인 불가"
        comparison_rows.append(
            {
                "rank": rank_text,
                "rule": priority_rule_label(candidate.get("rule")),
                "policy_status": policy_text,
                "late_lot_count": kpi.get("late_lot_count"),
                "total_tardiness": format_duration_minutes(
                    kpi.get("total_tardiness_minutes")
                ),
                "changed_process_count": len(impacts),
                "priority_change_count": kpi.get("change_count"),
            }
        )

    st.dataframe(
        comparison_rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "rank": "추천 순위",
            "rule": "재계획 방법",
            "policy_status": "긴급납기 정책",
            "late_lot_count": "지연 LOT",
            "total_tardiness": "총 지연시간",
            "changed_process_count": "Forecast 대비 일정변경 공정",
            "priority_change_count": "우선순위 변경",
        },
    )
    st.caption(
        "순위는 별도 점수를 만들지 않고 기존 D029 기준을 그대로 사용합니다: 지연 LOT 수 → "
        "총 지연시간 → 추가근무 → 우선순위 변경량. 정확히 같은 결과는 공동 순위입니다."
    )

    if not compliant_candidate_ids:
        st.error(
            "현재 계산된 후보는 모두 긴급납기 운영정책을 위반해 승인할 수 없습니다. 현장 조건 "
            "또는 계획 입력을 다시 확인해야 합니다."
        )

    candidate_ids = [str(row["candidate_id"]) for row in ranked_candidates]

    def candidate_option_label(candidate_id: str) -> str:
        candidate = candidate_by_id[candidate_id]
        ranked = ranking_by_id[candidate_id]
        label = priority_rule_label(candidate.get("rule"))
        if ranked["policy_compliant"] is not True:
            return f"{label} · 정책 위반 · 승인 불가"
        rank_number = int(ranked["rank"])
        rank_text = f"공동 {rank_number}위" if ranked["tied"] else f"{rank_number}위"
        return f"{rank_text} · {label}"

    selected = st.selectbox(
        "상세 확인할 재계획안",
        candidate_ids,
        format_func=candidate_option_label,
        key="replan_candidate_selection",
    )
    selected_detail = candidate_by_id[selected]
    selected_compliant = selected_detail.get("policy_compliant") is True
    selected_violation_reason = selected_detail.get("policy_violation_reason")
    if not selected_compliant:
        reason_text = (
            str(selected_violation_reason)
            if selected_violation_reason
            else "긴급납기 LOT 우선 운영정책을 충족하지 않습니다."
        )
        st.error(f"이 후보는 승인할 수 없습니다. {reason_text}")

    kpi = selected_detail.get("kpi", {})
    if not isinstance(kpi, dict):
        kpi = {}
    tasks = _candidate_tasks(selected_detail)
    impacts = _candidate_impacts(
        candidate=selected_detail,
        plan_tasks=plan_tasks,
        process_rows=view.process_rows,
        lot_code_by_id=lot_code_by_id,
    )

    st.markdown("### 선택안 적용 시 예상 결과")
    effect_col1, effect_col2, effect_col3, effect_col4 = st.columns(4)
    effect_col1.metric("지연 LOT", kpi.get("late_lot_count", "—"))
    effect_col2.metric(
        "총 지연시간",
        format_duration_minutes(kpi.get("total_tardiness_minutes")),
    )
    effect_col3.metric("Forecast 대비 일정변경", f"{len(impacts)}개")
    effect_col4.metric("우선순위 변경", f"{kpi.get('change_count', '—')}건")

    st.markdown("### 승인계획 → 현재 Forecast → 재계획안")
    st.caption(
        "승인계획→현재 Forecast는 이미 발생한 실적 이탈이고, 현재 Forecast→재계획안이 이 "
        "후보를 승인했을 때 실제로 바뀌는 부분입니다."
    )
    if impacts:
        impact_rows = [
            {
                "lot_code": row["lot_code"],
                "process_code": process_label(row["process_code"]),
                "approved_window": _window_text(row["approved_start"], row["approved_end"]),
                "forecast_window": _window_text(row["forecast_start"], row["forecast_end"]),
                "candidate_window": _window_text(row["candidate_start"], row["candidate_end"]),
                "realized_drift": _schedule_shift_text(row["realized_end_drift_minutes"]),
                "replan_effect": _schedule_shift_text(row["replan_end_effect_minutes"]),
                "priority": (
                    f"{row['approved_rank']} → {row['candidate_rank']} "
                    f"({row['priority_movement']})"
                ),
            }
            for row in impacts
        ]
        st.dataframe(
            impact_rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "lot_code": "LOT",
                "process_code": "공정",
                "approved_window": "승인 계획",
                "forecast_window": "현재 Forecast",
                "candidate_window": "재계획 후",
                "realized_drift": "이미 발생한 계획 이탈",
                "replan_effect": "재계획 효과",
                "priority": "우선순위 변화",
            },
        )
    else:
        st.info(
            "이 방법은 현재 Forecast 대비 LOT×공정 시작·완료 예상과 우선순위가 동일합니다."
        )

    current_by_key = {
        (str(task.get("lot_id")), str(task.get("routing_step_id"))): task
        for task in plan_tasks
    }
    with st.expander("선택안 전체 계획 보기"):
        task_rows = [
            {
                "lot_code": lot_code_by_id.get(
                    str(task.get("lot_id")), str(task.get("lot_id"))
                ),
                "process_code": process_label(
                    _candidate_process_code(task, current_by_key=current_by_key)
                ),
                "target_start": display_datetime(task.get("target_start")),
                "target_end": display_datetime(task.get("target_end")),
                "priority_rank": task.get("priority_rank"),
            }
            for task in sorted(
                tasks,
                key=lambda row: (
                    int(row.get("priority_rank", 10**9)),
                    str(row.get("lot_id", "")),
                    str(row.get("routing_step_id", "")),
                ),
            )
        ]
        st.dataframe(
            task_rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "lot_code": "LOT",
                "process_code": "공정",
                "target_start": "재계획 시작",
                "target_end": "재계획 완료",
                "priority_rank": "우선순위",
            },
        )

    st.caption(f"후보 계산 기준시각: {display_datetime(snapshot.get('as_of'))}")
    selected_rule = selected_detail.get("rule")
    approval_clicked = st.button(
        f"{priority_rule_label(selected_rule)} 재계획 승인",
        type="primary",
        use_container_width=True,
        disabled=not selected_compliant,
    )
    if not approval_clicked:
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
        f"{priority_rule_label(selected_rule)} 승인 완료 · 새 승인계획 v{approval['version']}"
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
            reference_time = latest_execution_reference(operations, now=datetime.now(UTC))
            forecast = client.get_forecast(as_of=reference_time)
            current_plan = client.get_current_plan()
            lots = client.list_lots()
            gates = client.list_inspection_gates()
    except (ApiClientError, ValueError) as exc:
        st.error(f"FastAPI 데이터를 불러오지 못했습니다: {exc}")
        st.stop()

    view = build_overview_view(forecast=forecast, lots=lots, gates=gates)
    raw_plan_tasks = current_plan.get("tasks", [])
    plan_tasks = [row for row in raw_plan_tasks if isinstance(row, dict)]
    lot_code_by_id = {
        str(row["lot_id"]): str(row["lot_code"])
        for row in lots
        if "lot_id" in row and "lot_code" in row
    }
    waiting_operation_ids = {
        str(value) for value in forecast.get("waiting_operation_ids", [])
    }

    section = st.radio(
        "화면",
        ["생산현황", "현장 실적 입력", "재계획"],
        horizontal=True,
        label_visibility="collapsed",
        key="main_section",
    )

    if section == "생산현황":
        _render_overview(view=view, operations=operations, plan_tasks=plan_tasks)
    elif section == "현장 실적 입력":
        _render_operator_input(
            api_url=api_url,
            operations=operations,
            lot_code_by_id=lot_code_by_id,
            waiting_operation_ids=waiting_operation_ids,
        )
    else:
        _render_replan(
            api_url=api_url,
            reference_time=reference_time,
            view=view,
            plan_tasks=plan_tasks,
            lot_code_by_id=lot_code_by_id,
        )


if __name__ == "__main__":
    run()
