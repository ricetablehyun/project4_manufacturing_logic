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
```

- 계획/납기 관리 단위: LOT
- 실행/실적 기록 단위: Unit
- Forecast: LOT × 공정 Pace 기반
- 자원 제약: Worker Pool, Tuning Station, Test Station
- 재작업: FINAL_TEST → TUNING → FINAL_TEST
- 공식 계획: Baseline / Forecast / Replan 분리

## Implementation order

1. Core calculation + pytest
2. Calendar / Resource finite scheduling
3. Priority rules / Gate risk / Replanning
4. SQLite persistence
5. FastAPI
6. Streamlit dashboard
7. Raspberry Pi Pico 2 WH terminal

> 현재 단계: Milestone 0~1 Core bootstrap.
