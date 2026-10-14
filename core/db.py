"""SQLite (WAL) engine, sessions, and Alembic migrations run at startup."""
from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def make_engine(db_url: str) -> Engine:
    if db_url.startswith("sqlite:///"):
        os.makedirs(os.path.dirname(db_url[len("sqlite:///"):]) or ".", mode=0o700, exist_ok=True)
    eng = create_engine(db_url, connect_args={"check_same_thread": False, "timeout": 10}, future=True)

    @event.listens_for(eng, "connect")
    def _pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.close()

    return eng


def make_session_factory(eng: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=eng, expire_on_commit=False, future=True)


def alembic_config(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def upgrade(db_url: str) -> None:
    """Bring the schema to the newest migration (idempotent)."""
    command.upgrade(alembic_config(db_url), "head")
