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

> 현재 단계: Milestone 6 Streamlit dashboard — D061 read-only Overview 구현 중.

## Streamlit Overview

D061 Overview는 기존 FastAPI HTTP 경계만 사용하며 SQLite/SQLAlchemy에 직접 접근하지 않습니다.

```bash
pip install -e ".[dev]"
streamlit run src/production_control/ui/overview.py
```

기본 FastAPI 주소는 `http://127.0.0.1:8000`이며 환경변수로 변경할 수 있습니다.

```bash
export PRODUCTION_CONTROL_API_URL=http://127.0.0.1:8000
streamlit run src/production_control/ui/overview.py
```

현재 저장소에는 실행용 FastAPI runtime entrypoint가 아직 없으므로, API 서버가 실행 중이지 않으면 Overview는 연결 오류 상태를 표시하는 것이 정상입니다. 로컬/demo API runtime 구성은 D062에서 별도로 결정합니다.
