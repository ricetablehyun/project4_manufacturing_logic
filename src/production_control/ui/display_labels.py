"""Korean display labels for the Streamlit administrator UI.

Backend/API values stay unchanged; this module only translates presentation text.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")

_READINESS_LABELS = {
    "READY": "계산 완료",
    "WAIT": "입력 대기",
    "UNKNOWN": "상태 미확인",
}

_RISK_LABELS = {
    "NORMAL": "정상",
    "WARNING": "주의",
    "URGENT": "긴급",
}

_STATUS_LABELS = {
    "ACTIVE": "진행 중",
    "RELEASED": "투입됨",
    "PLANNED": "예정",
    "PAUSED": "일시정지",
    "WAITING": "대기",
    "RUNNING": "작업 중",
    "HOLD": "보류",
    "COMPLETED": "완료",
    "CANCELLED": "취소",
    "UNKNOWN": "미확인",
}

_GATE_TYPE_LABELS = {
    "SHIPPING_INSPECTION": "출하검사",
    "VISUAL_INSPECTION": "외관검사",
    "CUSTOMER_FINAL_INSPECTION": "고객사 최종검사",
}

_PROCESS_LABELS = {
    "TAPING": "테이핑",
    "EXTERNAL_FEED_BONDING": "외부 피드 본딩",
    "GENERAL_ASSEMBLY": "일반 조립",
    "TUNING": "튜닝",
    "FINISH_ASSEMBLY": "마무리 조립",
    "FINAL_TEST": "최종 성능시험",
}

_EVENT_TYPE_LABELS = {
    "START": "작업 시작",
    "HOLD": "보류",
    "RESUME": "작업 재개",
    "COMPLETE": "작업 완료",
    "PASS": "합격",
    "FAIL": "불합격",
}

_PRIORITY_RULE_LABELS = {
    "FCFS": "FCFS · 먼저 들어온 LOT 우선",
    "EDD": "EDD · 납기가 가까운 LOT 우선",
    "SLACK": "Slack · 여유시간이 적은 LOT 우선",
    "CR": "CR · 긴급도가 높은 LOT 우선",
}

_ACTION_LABELS = {
    "KEEP_PLAN": "현재 계획 유지",
    "MONITOR_ONLY": "주의 관찰",
    "GENERATE_CANDIDATES": "재계획 후보 비교",
}


def _translate(value: object, labels: dict[str, str]) -> str:
    text = str(value)
    return labels.get(text, text)


def readiness_label(value: object) -> str:
    return _translate(value, _READINESS_LABELS)


def risk_label(value: object) -> str:
    return _translate(value, _RISK_LABELS)


def status_label(value: object) -> str:
    return _translate(value, _STATUS_LABELS)


def gate_type_label(value: object) -> str:
    return _translate(value, _GATE_TYPE_LABELS)


def process_label(value: object) -> str:
    return _translate(value, _PROCESS_LABELS)


def event_type_label(value: object) -> str:
    return _translate(value, _EVENT_TYPE_LABELS)


def priority_rule_label(value: object) -> str:
    return _translate(value, _PRIORITY_RULE_LABELS)


def action_label(value: object) -> str:
    return _translate(value, _ACTION_LABELS)


def display_datetime(value: object) -> str:
    """Render a timestamp compactly in Asia/Seoul for the administrator UI."""

    if value in (None, "", "—"):
        return "—"
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    else:
        return str(value)

    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        parsed = parsed.astimezone(SEOUL)
    return parsed.strftime("%Y-%m-%d %H:%M")
