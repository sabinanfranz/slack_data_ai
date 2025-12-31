from __future__ import annotations

import logging
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

log = logging.getLogger(__name__)


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is not None:
        return _engine

    if not settings.database_url:
        return None

    url = _normalize_database_url(settings.database_url)
    _engine = create_engine(
        url,
        pool_pre_ping=True,
        future=True,
    )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is not None:
        return _SessionLocal

    engine = get_engine()
    if engine is None:
        return None

    _SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    return _SessionLocal


def init_db() -> bool:
    engine = get_engine()
    if engine is None:
        return False

    from app.models import Base

    Base.metadata.create_all(bind=engine)

    if settings.auto_migrate:
        _ensure_schema_patches(engine)

    return True


def check_db() -> bool:
    engine = get_engine()
    if engine is None:
        return False

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_db() -> Generator[Session, None, None]:
    SessionLocal = get_session_factory()
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not set; DB session is unavailable")

    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_schema_patches(engine) -> None:
    """
    Minimal auto-migration for channels ingest_* columns to prevent runtime 500s.
    """
    missing = set()
    try:
        with engine.connect() as conn:
            if engine.dialect.name == "sqlite":
                res = conn.execute(text("PRAGMA table_info('channels')")).fetchall()
                cols = {row[1] for row in res}
            else:
                res = conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'channels'"
                    )
                ).fetchall()
                cols = {row[0] for row in res}
            expected = {
                "ingest_status",
                "ingest_started_at",
                "ingest_finished_at",
                "ingest_error_message",
                "ingest_last_result_json",
            }
            missing = expected - cols
            if not missing:
                return

            log.warning("Applying schema patch for channels columns: %s", ", ".join(sorted(missing)))
            if engine.dialect.name == "postgresql":
                clauses = []
                if "ingest_status" in missing:
                    clauses.append("ADD COLUMN IF NOT EXISTS ingest_status VARCHAR(16) DEFAULT 'idle'")
                if "ingest_started_at" in missing:
                    clauses.append("ADD COLUMN IF NOT EXISTS ingest_started_at TIMESTAMPTZ")
                if "ingest_finished_at" in missing:
                    clauses.append("ADD COLUMN IF NOT EXISTS ingest_finished_at TIMESTAMPTZ")
                if "ingest_error_message" in missing:
                    clauses.append("ADD COLUMN IF NOT EXISTS ingest_error_message TEXT")
                if "ingest_last_result_json" in missing:
                    clauses.append("ADD COLUMN IF NOT EXISTS ingest_last_result_json JSONB")
                if clauses:
                    conn.execute(text(f"ALTER TABLE channels {', '.join(clauses)}"))
                    conn.execute(
                        text(
                            "UPDATE channels SET ingest_status='idle' WHERE ingest_status IS NULL"
                        )
                    )
            elif engine.dialect.name == "sqlite":
                if "ingest_status" in missing:
                    conn.execute(text("ALTER TABLE channels ADD COLUMN ingest_status TEXT"))
                    conn.execute(
                        text("UPDATE channels SET ingest_status='idle' WHERE ingest_status IS NULL")
                    )
                if "ingest_started_at" in missing:
                    conn.execute(text("ALTER TABLE channels ADD COLUMN ingest_started_at TIMESTAMP"))
                if "ingest_finished_at" in missing:
                    conn.execute(
                        text("ALTER TABLE channels ADD COLUMN ingest_finished_at TIMESTAMP")
                    )
                if "ingest_error_message" in missing:
                    conn.execute(text("ALTER TABLE channels ADD COLUMN ingest_error_message TEXT"))
                if "ingest_last_result_json" in missing:
                    conn.execute(text("ALTER TABLE channels ADD COLUMN ingest_last_result_json TEXT"))
            conn.commit()
    except Exception as e:
        log.error("Schema patch failed (missing=%s): %s", missing, e)
