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

> 현재 단계: Milestone 6 Streamlit dashboard — D062 local/demo FastAPI runtime 연결.

## Local demo runtime

D062는 **파일 SQLite + 명시적 초기화/reset** 방식을 사용합니다. 서버 시작은 DB를 자동 생성하거나 seed하지 않습니다.

먼저 개발 의존성을 설치합니다.

```bash
python -m pip install -e ".[dev]"
```

### 1. Demo DB 초기화

기본 경로는 `data/demo.db`입니다. 기존 DB가 있으면 `--reset` 없이는 덮어쓰지 않습니다.

```bash
python -m production_control.demo.init_db --reset
```

다른 경로를 쓰려면 `--db` 또는 `PRODUCTION_CONTROL_DB_PATH`를 사용합니다.

```bash
python -m production_control.demo.init_db --db data/another-demo.db --reset
export PRODUCTION_CONTROL_DB_PATH=data/another-demo.db
```

### 2. FastAPI 실행

```bash
python -m uvicorn production_control.api.runtime:app --reload
```

기본 API 주소는 `http://127.0.0.1:8000`입니다. DB가 초기화되지 않았다면 runtime은 자동 seed하지 않고 시작에 실패합니다.

### 3. Streamlit Overview 실행

다른 터미널에서 실행합니다.

```bash
python -m streamlit run src/production_control/ui/overview.py
```

D061 Overview는 FastAPI HTTP 경계만 사용하며 SQLite/SQLAlchemy에 직접 접근하지 않습니다.

`python -m streamlit`을 사용하면 활성화된 가상환경의 Python으로 Streamlit을 실행하므로, Conda의 전역 `streamlit` 실행기가 먼저 잡히는 환경 충돌을 피할 수 있습니다.

FastAPI 주소를 변경하려면 다음 환경변수를 사용합니다.

```bash
export PRODUCTION_CONTROL_API_URL=http://127.0.0.1:8000
python -m streamlit run src/production_control/ui/overview.py
```

Demo DB는 로컬 파일로 유지되므로 WorkEvent 입력이나 Replan 승인 결과가 서버 실행 중/재시작 후에도 남습니다. 초기 Fixture 상태로 되돌릴 때만 init 명령의 `--reset`을 다시 실행합니다.
