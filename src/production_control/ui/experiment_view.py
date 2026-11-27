"""Streamlit section for the recorded closed-loop experiment results.

It reads the experiment's CSV files only; it never recomputes the numbers.
"""

import csv
import json
from os import environ
from pathlib import Path

import streamlit as st

from production_control.ui import charts

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXPERIMENT_DIR = _REPO_ROOT / "experiments" / "main30"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def experiment_dir() -> Path:
    return Path(environ.get("PRODUCTION_CONTROL_EXPERIMENT_DIR", DEFAULT_EXPERIMENT_DIR))


def render_experiment_results() -> None:
    directory = experiment_dir()
    st.subheader("가상 현장 폐루프 실험 결과")
    summary_path, runs_path = directory / "summary.csv", directory / "runs.csv"
    if not summary_path.is_file() or not runs_path.is_file():
        st.warning(f"실험 결과 파일이 없습니다: {directory}")
        return

    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    summary = charts.summary_records(_read_csv(summary_path))
    runs = _read_csv(runs_path)
    violations = sum(int(row["violations"]) for row in runs)
    failures_path = directory / "failures.json"
    failures = (
        json.loads(failures_path.read_text(encoding="utf-8")) if failures_path.is_file() else []
    )

    seeds = config.get("seeds", [])
    total_col, seed_col, violation_col, failure_col = st.columns(4)
    total_col.metric("실행 수", f"{len(runs)}회")
    seed_col.metric("반복(seed)", f"{len(seeds)}회")
    violation_col.metric("공장 규칙 위반", f"{violations}건")
    failure_col.metric("실패한 실행", f"{len(failures)}건")
    st.caption(
        f"시작 상태: {config.get('start')} 중간발표 데모 상태, 기준계획 FCFS. "
        "조건 3개 × (KEEP + 재계획 4방법 × 추가근무 끔/켬) × seed. "
        f"결과 파일: experiments/{directory.name}"
    )

    st.markdown("#### 출하검사 진입 지연 (평균 ± 95% 신뢰구간)")
    st.altair_chart(charts.gate_delay_chart(summary, width=250), use_container_width=False)
    st.caption(
        "KEEP은 계획을 유지한 기준선입니다. 연한 막대(+OT)는 평일 17~19시 추가근무를 허용한 "
        "구성입니다. 조건마다 세로축 범위가 다릅니다."
    )

    st.markdown("#### 실행별 분포")
    st.altair_chart(charts.run_distribution_chart(runs, width=250), use_container_width=False)
    st.caption("점 하나가 한 번의 실행(seed)입니다. 평균 뒤의 편차와 드문 큰 지연을 보여줍니다.")

    st.markdown("#### 추가근무의 효과와 비용")
    st.altair_chart(charts.overtime_tradeoff_chart(summary, width=250), use_container_width=False)
    st.caption(
        "원(정규 근무) → 삼각형(추가근무 허용). 아래로 갈수록 지연이 줄고 오른쪽으로 갈수록 "
        "추가 가동시간이 늘어납니다. 정상·작업시간 +20% 조건에서 EDD와 SLACK은 같은 점이라 "
        "겹쳐 보입니다. 추가 가동시간은 17시부터 창 안 마지막 작업 종료까지이며 대기도 포함합니다."
    )

    with st.expander("요약표 (summary.csv)"):
        st.dataframe(
            [
                {
                    "조건": row["condition_label"],
                    "구성": row["policy"],
                    "n": row["n"],
                    "진입 지연 평균(분)": round(float(row["gate_delay"]), 1),
                    "±95% CI": round(float(row["gate_delay_ci"]), 1),
                    "KEEP 대비(분)": round(float(row["vs_keep"]), 1),
                    "최종납기 지각 평균(분)": round(float(row["due_tardiness"]), 1),
                    "추가 가동(분)": round(float(row["overtime_minutes"]), 1),
                    "승인 횟수": round(float(row["approvals"]), 1),
                }
                for row in summary
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.info(
        "해석 범위: 작업정지·재작업 조건은 일부 작업에 240분을 더하는 지연 모델이며 "
        "HOLD/RESUME 이벤트를 보내지 않습니다. 최종납기 지각은 대시보드와 같은 출하검사 "
        "규칙(Gate 시작 또는 생산 완료 후 시작, 시작일 포함 3근무일 17시 종료)을 그대로 "
        "적용한 값이며, 검사 자체의 지연·불합격은 가정하지 않습니다. 실험의 가상 단말은 "
        "TestClient로 API를 호출합니다. 실제 소켓 통신은 별도 테스트로 확인했습니다. "
        "Pico 하드웨어는 연동하지 않았습니다."
    )
