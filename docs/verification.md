# 검증 근거 (주장 → 증거)

보고서·발표의 주장마다 그것을 뒷받침하는 테스트, 데이터 파일, 재현 명령을 적었습니다. 이 표에 없는 주장은 보고서·발표에 쓰지 않습니다.

전체 테스트: `python -m pytest` (384 tests, CI: Python 3.11 / 3.13, `.github/workflows`).

## 1. 시스템 기능

| 주장 | 근거 |
|---|---|
| 작업실적 이벤트를 저장하고, 같은 event_id 재전송은 한 번만 반영한다 | `tests/integration/test_work_event_api.py::test_duplicate_event_returns_200_without_second_row` |
| 잘못된 상태 전이(예: 시작 전 완료)는 409로 거부하고 저장하지 않는다 | `test_work_event_api.py::test_invalid_state_transition_returns_409_without_persisting` |
| HOLD는 예상 보류시간을 요구하고 RESUME이 해제한다 | `test_work_event_api.py::test_hold_requires_worker_expected_hold_minutes`, `::test_hold_estimate_sets_and_resume_clears_hold_until` |
| 중간발표 수치(LOT-001 출하검사 진입 4시간 57분 지연, EDD/Slack/CR 297분, FCFS 549분)가 그대로 재현된다 | `tests/integration/test_midterm_kpi_regression.py` |
| 4시간 57분은 출하검사 진입 지연이며 고객 납기(10/29 17:00)와 다른 기준이다 | 같은 테스트의 `customer_due_at` 검사 |
| 추가근무 후보는 켰을 때만 나오고, 승인하면 근무달력(OVERTIME)과 Forecast·현장 실행에 같이 반영된다 | `tests/integration/test_overtime_replan.py` (3개 테스트) |
| 시연 상황에서 EDD+추가근무(10/22 2시간)는 지연을 297→177분으로 줄이지만 없애지는 못한다 | `tests/integration/test_demo_overtime_option.py` |
| 추가 가동시간은 17시~창 안 마지막 작업 종료(대기 포함)로 센다 | `tests/unit/test_experiment_metrics.py::test_overtime_is_extra_operating_time_not_busy_minutes`, `core/overtime.py` |
| 승인된 계획이 실제로 현장 작업 순서를 바꾼다(폐루프) | `tests/integration/test_closed_loop.py::test_approval_changes_the_executed_order` |
| 실제 시간이 표준시간과 같으면 현장 결과가 승인 시점 Forecast와 일치한다 | `test_closed_loop.py::test_deterministic_plant_realises_the_plan_forecast` |
| 잡음·재작업·이벤트 재전송이 있어도 폐루프가 끝까지 돈다 | `test_closed_loop.py::test_noisy_plant_with_rework_and_resent_events_completes` |
| 폐루프가 실제 TCP 소켓(uvicorn + httpx)에서도 동작한다 | `tests/integration/test_closed_loop_over_network.py` |
| 17:00 정각 결정 시 진행 중 작업은 다음 날 아침에 이어진다 | `tests/unit/test_event_scheduler.py::test_running_work_paused_at_closing_time_resumes_next_opening` |

## 2. 실험

| 주장 | 근거 |
|---|---|
| 810회 실행, 공장 규칙 위반 0, 실패 0 | `experiments/main30/runs.csv` (`violations` 열), `failures.json` |
| 첫 실행의 실패 3회와 그 원인·수정 | `experiments/main30/failures_before_3a7ff6e.json`, `experiments/main30/README.md` |
| 조건·방법별 평균과 95% 신뢰구간, KEEP 대비 짝지은 차이 | `experiments/main30/summary.csv` |
| seed 1~10은 파일럿과 같은 결과 | `experiments/pilot/runs.jsonl` vs `experiments/main30/runs.jsonl` |
| 최종 납기 지각 0건(810회) | `summary.csv`의 `due_tardiness_minutes_mean`; 규칙은 `core/shipping_inspection.py` |
| 그림은 위 CSV에서만 그린다 | `python -m production_control.sim.figures` → `docs/figures/` |
| 실험 재현 명령과 파라미터 | `experiments/main30/config.json`, `python -m production_control.sim.experiment --reps 30` |

## 3. 검증하지 않은 것 (보고서에 한계로 명시)

- Pico 2 WH 하드웨어 연동: 미구현.
- 실제 공장 데이터로 시뮬레이터 보정: 하지 않음(작업시간 분포·교란 확률은 가정값).
- 출하검사 자체의 대기·불합격·지연: 모델링하지 않음.
- 실험에서 HOLD/RESUME 이벤트: 보내지 않음(작업정지는 작업시간에 더하는 지연 모델).
- 인증·권한, 외부망 운영: 범위 밖(로컬 데모).
