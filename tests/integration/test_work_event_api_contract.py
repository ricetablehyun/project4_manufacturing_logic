from pathlib import Path

from production_control.api import create_app
from production_control.persistence.database import create_session_factory, create_sqlite_engine


def test_work_event_contract_is_exposed_in_openapi(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "openapi.db")
    session_factory = create_session_factory(engine)
    app = create_app(session_factory=session_factory)

    operation = app.openapi()["paths"]["/work-events"]["post"]

    assert operation["responses"]["201"]["description"] == "Successful Response"
    schema_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert schema_ref.endswith("/WorkEventRequest")
