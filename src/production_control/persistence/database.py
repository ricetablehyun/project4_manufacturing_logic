"""SQLite engine/session helpers for V1 persistence."""

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from production_control.persistence.models import Base


def create_sqlite_engine(path: str | Path = ":memory:") -> Engine:
    """Create a SQLite engine with foreign-key enforcement enabled."""

    database = str(path)
    url = "sqlite+pysqlite:///:memory:" if database == ":memory:" else f"sqlite+pysqlite:///{database}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
