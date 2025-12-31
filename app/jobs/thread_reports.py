from __future__ import annotations

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(filename=".env", usecwd=True), override=False)

import argparse
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc

from app.config import settings
from app.db import get_session_factory, init_db
from app.llm_client import LLMClient
from app.models import Channel, Thread
from app.services.thread_report_service import ensure_thread_report


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--channel", type=str, default=None, help="Channel ID filter")
    p.add_argument("--days", type=int, default=14, help="Lookback days (default 14)")
    p.add_argument("--limit", type=int, default=200, help="Max threads to process")
    p.add_argument("--force", action="store_true", help="Force refresh even if up-to-date")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to .env or set environment variable OPENAI_API_KEY."
        )
    if not getattr(settings, "database_url", None) and not os.getenv("DATABASE_URL"):
        raise RuntimeError(
            "DATABASE_URL is missing. Add it to .env or set environment variable DATABASE_URL."
        )

    init_db()
    SessionLocal = get_session_factory()
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not set; cannot run thread report job.")

    llm = LLMClient()
    lookback_epoch = (datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp()

    with SessionLocal() as db:
        q = (
            db.query(Thread)
            .join(Channel, Channel.channel_id == Thread.channel_id)
            .filter(Channel.is_active.is_(True))
            .filter(Thread.thread_ts_epoch >= lookback_epoch)
            .order_by(desc(Thread.updated_at))
        )
        if args.channel:
            q = q.filter(Thread.channel_id == args.channel.strip().upper())

        threads = q.limit(args.limit).all()

        processed = 0
        ok = 0
        skipped = 0
        for th in threads:
            processed += 1
            try:
                res = ensure_thread_report(
                    db,
                    llm,
                    channel_id=th.channel_id,
                    thread=th,
                    force=args.force,
                )
                if res.get("skipped"):
                    skipped += 1
                else:
                    ok += 1
            except Exception:
                db.rollback()
                continue

    print(
        f"[thread_reports] processed={processed} ok={ok} skipped={skipped} "
        f"channel={args.channel or 'ALL'} days={args.days}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
