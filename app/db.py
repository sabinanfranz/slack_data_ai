from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


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
