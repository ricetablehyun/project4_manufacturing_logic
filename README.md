# project4_manufacturing_logic

현장 작업실적(Unit 단위)으로 LOT 생산진도를 추정하고, 출하검사 Gate에 늦을 위험이 생기면 재계획 후보를 계산해 관리자 승인을 받은 뒤, 승인된 계획대로 현장 작업지시가 바뀌는 **생산 진도관리·재계획 시스템**입니다. 공학프로젝트4 기말 버전입니다.

```text
Unit 작업실적(WorkEvent) ─▶ LOT×공정 Pace ─▶ 유한용량 Forecast ─▶ Gate 위험 판단
        ▲                                                            │ URGENT
        │                                                            ▼
  현장 작업지시(/work-orders) ◀── 승인된 계획 ◀── 관리자 승인 ◀── 재계획 후보
                                                      FCFS / EDD / Slack / CR (+ 추가근무)
```

## 구현 범위

| 구분 | 내용 | 근거 |
|---|---|---|
| 구현 | 작업실적 입력(START/HOLD/RESUME/COMPLETE/PASS/FAIL), 중복 전송 무시 | `tests/integration/test_work_event_api.py` |
| 구현 | Pace 기반 Forecast, 작업자 잔여시간 입력, 재작업(FINAL_TEST→TUNING→FINAL_TEST) | `test_live_forecast_*`, `test_rework_pace_duration.py` |
| 구현 | 재계획 후보 4방법 + 평일 17~19시 추가근무 후보(D078), D029 순위 | `test_replan_candidate_api.py`, `test_overtime_replan.py` |
| 구현 | 승인 → 새 계획 → 현장 작업지시 변경(폐루프) | `test_closed_loop.py`, `test_closed_loop_over_network.py` |
| 구현 | 가상 현장 시뮬레이터와 반복 실험 (810회) | `experiments/main30/` |
| 구현 | Streamlit 관리자 화면: 생산현황·간트차트·실적 입력·재계획·실험 결과 | `src/production_control/ui/` |
| 미구현 | Raspberry Pi Pico 2 WH 하드웨어 단말 연동 | 가상 단말(HTTP)로만 검증 |
| 미구현 | 인증·권한, 외부망 배포, 설비·자원 관리 UI | 로컬 데모 범위 |

## 빠른 시작

```bash
python -m pip install -e ".[dev]"          # 그림 생성까지 하려면 ".[dev,figures]"
python -m pytest                           # 384 tests
```

### 시연 환경 (중간발표 지연 상황)

```bash
python -m production_control.demo.init_db --reset          # data/demo.db 초기화
python -m production_control.demo.prepare_delay_smoke      # U030 튜닝 RUNNING, 10/22 13:17

# 터미널 1: API (추가근무 후보를 켜려면 PRODUCTION_CONTROL_OVERTIME_END 지정)
PRODUCTION_CONTROL_OVERTIME_END=19:00 \
python -m uvicorn production_control.api.runtime:app --host 127.0.0.1 --port 8000

# 터미널 2: 관리자 화면 (데모 데이터가 2026년 10월이므로 시연 시각을 고정)
PRODUCTION_CONTROL_DEMO_TIME=2026-10-22T13:17:00+09:00 \
python -m streamlit run src/production_control/ui/overview.py --server.address 127.0.0.1
```

- 두 환경변수를 지정하지 않으면 중간발표와 똑같이 동작합니다(추가근무 후보 없음, 실제 시계 사용).
- 시연 흐름: 현장 실적 입력에서 U030 예상 잔여시간 480분 입력 → 생산현황에서 LOT-001 출하검사 진입 4시간 57분 지연(URGENT) 확인 → 재계획에서 후보 계산 → 추가근무안 승인 → 지연이 2시간 57분으로 줄어든 Forecast 확인. 이 수치는 `tests/integration/test_midterm_kpi_regression.py`, `tests/integration/test_demo_overtime_option.py`가 고정합니다.
- 모든 서버는 `127.0.0.1`에만 바인딩합니다(`docs/security/local_demo.md`).
- 화면의 LOT 코드(LOT-001~003)는 내부 ID(LOT-101~103)와 같은 LOT입니다.

### 반복 실험과 그림 재현

```bash
python -m production_control.sim.experiment --reps 30 --workers 4 --out experiments/main30   # 약 3시간, 중단 시 같은 명령으로 이어서 실행
python -m production_control.sim.figures --experiment experiments/main30 --out docs/figures
```

결과와 해석은 [`experiments/main30/README.md`](experiments/main30/README.md)에 있습니다. 요약하면 다음과 같습니다(30회 반복, 출하검사 진입 지연 평균).

| 조건 | 계획 유지(KEEP) | EDD 재계획 |
|---|---|---|
| 정상 | 190분 | 0분 (30회 모두 0) |
| 작업시간 +20% | 1,523분 | 0분 (30회 모두 0) |
| 작업정지·재작업 | 2,433분 | 14.6분 (30회 중 5회 지연) |

추가근무는 지연이 남는 방법(CR, FCFS 등)에서 지연을 줄이지만, 정상 조건의 EDD처럼 이미 지연이 0인 경우에도 예측이 비관적이라 평균 108분을 엽니다. 810회 모두 공장 규칙 위반 0건, 최종 납기 지각 0건입니다.

## 용어와 지표

- **출하검사 진입 지연**: LOT의 마지막 최종시험 합격 시각 − 출하검사 Gate 예정 시작(`InspectionGate.planned_at`). 시스템의 재계획 KPI(지연 LOT 수, 총 지연시간)가 이 값을 씁니다. 중간발표의 "4시간 57분"도 이 지표입니다.
- **최종 납기 지각**: 출하검사 종료(출하) 시각 − 고객 납기(`Lot.due_at`). 출하검사 규칙은 `core/shipping_inspection.py` 하나를 대시보드와 실험이 함께 씁니다. 검사는 Gate 예정 시각에 시작하고, 생산이 늦으면 완료 후 다음 근무시각에 시작합니다. 시작일을 포함해 3근무일째 17:00에 끝납니다. 검사 자체의 대기·불합격·지연은 모델링하지 않습니다.
- **추가 가동시간**: 추가근무 날마다 17:00부터 추가근무 창 안의 마지막 작업 종료까지입니다. 중간 대기를 포함하며, 순수 작업시간의 합이 아닙니다.
- **작업정지·재작업 조건(STOPPAGE_REWORK)**: 3%의 작업에 240분을 더하는 지연 모델과 8%의 최종시험 불합격입니다. HOLD/RESUME 이벤트는 보내지 않습니다. HOLD/RESUME 처리는 API 테스트로 따로 검증합니다.

## 한계

- Pico 2 WH 하드웨어는 연동하지 않았습니다. 가상 단말이 같은 HTTP API를 호출합니다. 반복 실험은 FastAPI TestClient(프로세스 내부)를 쓰고, 실제 TCP 소켓은 `test_closed_loop_over_network.py`에서 따로 확인합니다.
- 가상 현장의 실제 작업시간 분포(로그정규, σ 0.15)와 교란 확률은 가정값이며 실제 공장 데이터로 보정하지 않았습니다.
- 재계획은 결정 시점의 Forecast로 고릅니다. 예측이 비관적이면 필요 없는 추가근무를 고를 수 있습니다(실험 결과에 그대로 보고).
- 데모 고객 납기는 출하검사 이후로 넉넉하게 잡힌 예시 날짜라, 이 세계에서는 최종 납기 지각이 나타나지 않았습니다.

## 문서

- `docs/verification.md`: 주장별 검증 근거(테스트·실험 파일·명령)
- `docs/api/`: API 계약
- `docs/midterm_demo_scope.md`: 중간발표 범위와 식별자 규칙
- `experiments/pilot/`, `experiments/main30/`: 실험 원자료와 해석
- `docs/figures/`: 보고서·발표용 그림(위 명령으로 재생성)
