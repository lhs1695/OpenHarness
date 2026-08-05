"""SQLAlchemy engine/session setup.

SQLite is the default (works without external services); set
``FORGEFLOW_DATABASE_URL`` to a PostgreSQL URL (see docker-compose.yml).
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


DEFAULT_DATABASE_URL = "sqlite:///./forgeflow.db"


def create_database_engine(database_url: str | None = None) -> Engine:
    url = database_url or os.environ.get("FORGEFLOW_DATABASE_URL") or DEFAULT_DATABASE_URL
    connect_args: dict[str, bool] = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
