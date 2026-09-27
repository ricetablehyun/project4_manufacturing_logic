"""Dependency helpers for the FastAPI boundary."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker


def build_session_dependency(session_factory: sessionmaker[Session]):
    """Return one request-scoped SQLAlchemy Session dependency."""

    def get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    return get_session


SessionDependency = Annotated[Session, Depends()]
