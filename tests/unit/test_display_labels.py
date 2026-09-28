from production_control.ui.display_labels import (
    display_datetime,
    gate_type_label,
    process_label,
    readiness_label,
    risk_label,
    status_label,
)


def test_readiness_and_risk_are_localized_for_display() -> None:
    assert readiness_label("READY") == "계산 완료"
    assert readiness_label("WAIT") == "입력 대기"
    assert risk_label("NORMAL") == "정상"
    assert risk_label("WARNING") == "주의"
    assert risk_label("URGENT") == "긴급"


def test_status_labels_are_localized_without_changing_unknown_future_values() -> None:
    assert status_label("ACTIVE") == "진행 중"
    assert status_label("PLANNED") == "예정"
    assert status_label("HOLD") == "보류"
    assert status_label("FUTURE_STATUS") == "FUTURE_STATUS"


def test_gate_and_process_labels_use_korean_terms() -> None:
    assert gate_type_label("SHIPPING_INSPECTION") == "출하검사"
    assert process_label("TAPING") == "테이핑"
    assert process_label("GENERAL_ASSEMBLY") == "일반 조립"
    assert process_label("TUNING") == "튜닝"
    assert process_label("FINISH_ASSEMBLY") == "마무리 조립"
    assert process_label("FINAL_TEST") == "최종 성능시험"


def test_display_datetime_uses_compact_seoul_time() -> None:
    assert display_datetime("2026-10-05T13:00+09:00") == "2026-10-05 13:00"
    assert display_datetime("2026-09-28T02:30+00:00") == "2026-09-28 11:30"
    assert display_datetime("—") == "—"
