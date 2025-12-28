from __future__ import annotations

import logging

from app.db import get_session_factory, init_db
from app.models import Channel
from app.services.ingest_service import (
    ingest_channel_history_roots,
    ingest_channel_thread_replies,
)
from app.slack_client import SlackClient, SlackNotConfigured

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest-job")


def main() -> int:
    init_db()

    try:
        slack = SlackClient()
    except SlackNotConfigured as e:
        log.error("Slack not configured: %s", e)
        return 2

    SessionLocal = get_session_factory()
    if SessionLocal is None:
        log.error("DATABASE_URL is not set; cannot run ingest job.")
        return 2

    db = SessionLocal()
    try:
        channels = (
            db.query(Channel)
            .filter(Channel.is_active.is_(True))
            .order_by(Channel.created_at.asc())
            .all()
        )
        if not channels:
            log.info("No active channels. Nothing to ingest.")
            return 0

        log.info("Starting ingest for %d active channels", len(channels))

        for ch in channels:
            try:
                result_a = ingest_channel_history_roots(db, slack, ch)
                log.info("Ingest A OK: %s", result_a)

                result_b = ingest_channel_thread_replies(db, slack, ch)
                log.info("Ingest B OK: %s", result_b)
            except Exception as e:
                log.exception("Ingest failed for channel=%s: %s", ch.channel_id, e)
                continue

        log.info("Ingest finished.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
