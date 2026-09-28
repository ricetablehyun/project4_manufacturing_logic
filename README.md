# project4_manufacturing_logic

현장 작업실적을 기반으로 LOT 생산진도를 모니터링하고, 납기/검사 Gate 위험 발생 시 재계획 후보를 비교하는 V1 생산관리 프로젝트입니다.

## Core idea

```text
Unit-level actual events
        ↓
LOT × Process pace
        ↓
Remaining work
        ↓
Finite-capacity forecast
        ↓
Gate risk
        ↓
FCFS / EDD / Slack / CR replanning candidates
        ↓
Manager approval
        ↓
New approved plan
```

- 계획/납기 관리 단위: LOT
- 실행/실적 기록 단위: Unit
- Forecast: LOT × 공정 Pace 기반
- 자원 제약: Worker Pool, Tuning Station, Test Station
- 재작업: FINAL_TEST → TUNING → FINAL_TEST
- 공식 계획: Baseline / Forecast / Replan 분리
- 관리자 경계: FastAPI → Streamlit; UI는 DB를 직접 수정하지 않음

## Implementation order

1. Core calculation + pytest
2. Calendar / Resource finite scheduling
3. Priority rules / Gate risk / Replanning
4. SQLite persistence
5. FastAPI
6. Streamlit dashboard
7. Raspberry Pi Pico 2 WH terminal

> 현재 단계: Milestone 6 Streamlit administrator dashboard.

## Streamlit Overview

D061 첫 UI slice는 read-only Overview입니다. 실행 중인 FastAPI에서 `/forecast`, `/lots`, `/inspection-gates`를 읽어 Approved Plan, Forecast readiness, LOT/Gate risk, LOT×Process Forecast를 표시합니다.

```bash
pip install -e ".[dev]"
export PRODUCTION_CONTROL_API_URL=http://127.0.0.1:8000
streamlit run src/production_control/ui/overview.py
```

`PRODUCTION_CONTROL_API_URL`을 생략하면 `http://127.0.0.1:8000`을 사용합니다. Streamlit은 API client 역할만 하며 생산계획 계산과 persistence는 기존 Core/FastAPI 계층을 그대로 사용합니다.
