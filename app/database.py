"""
Embedded database layer.

This deliberately uses SQLite through SQLModel instead of a client/server
database. SQLite lives in a single file on disk (storage/jobhunter.db) --
there is nothing to install, run, or deploy separately. The whole app,
including its data, is one folder you can zip up or move anywhere.
"""
from sqlmodel import SQLModel, Session, create_engine

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Create all tables if they don't exist yet. Safe to call on every startup."""
    from app import models  # noqa: F401  (ensures models are registered)

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
