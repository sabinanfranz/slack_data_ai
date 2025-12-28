from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Channel, Message, Thread, UserCache
from app.slack_client import SlackCallError, SlackClient
from app.services.user_service import upsert_user_cache

def _now_kst() -> datetime:
    return datetime.now(tz=ZoneInfo(settings.tz))


def _epoch(dt: datetime) -> float:
    return dt.timestamp()


def _ts_to_epoch(ts: str) -> float:
    return float(ts)


def _is_normal_message(msg: dict) -> bool:
    if msg.get("type") != "message":
        return False
    if msg.get("subtype"):
        return False
    return True


def ingest_channel_history_roots(
    db: Session, slack: SlackClient, channel: Channel
) -> dict:
    if not channel.last_ts_epoch or not channel.last_ts:
        dt = _now_kst() - timedelta(days=14)
        ep = _epoch(dt)
        channel.last_ts_epoch = ep
        channel.last_ts = str(ep)
        db.commit()
        db.refresh(channel)

    oldest = channel.last_ts
    cursor: str | None = None

    fetched = 0
    normal_candidates = 0
    root_count = 0
    max_ts_epoch = channel.last_ts_epoch or 0.0
    max_ts_str = channel.last_ts or "0"
    user_ids: set[str] = set()

    while True:
        try:
            msgs, next_cursor = slack.conversations_history_page(
                channel_id=channel.channel_id,
                oldest=oldest,
                cursor=cursor,
                limit=200,
                inclusive=True,
            )
        except SlackCallError as e:
            if e.error_code == "not_in_channel":
                try:
                    slack.join_channel(channel.channel_id)
                    msgs, next_cursor = slack.conversations_history_page(
                        channel_id=channel.channel_id,
                        oldest=oldest,
                        cursor=cursor,
                        limit=200,
                        inclusive=True,
                    )
                except Exception:
                    raise
            else:
                raise

        fetched += len(msgs)

        message_rows: list[dict] = []
        thread_rows: list[dict] = []

        for m in msgs:
            if not _is_normal_message(m):
                continue

            ts = m.get("ts")
            if not ts:
                continue

            ts_epoch = _ts_to_epoch(ts)
            if ts_epoch > max_ts_epoch:
                max_ts_epoch = ts_epoch
                max_ts_str = ts

            thread_ts = m.get("thread_ts") or ts
            thread_ts_epoch = _ts_to_epoch(thread_ts)

            message_rows.append(
                {
                    "channel_id": channel.channel_id,
                    "ts": ts,
                    "ts_epoch": ts_epoch,
                    "thread_ts": thread_ts,
                    "thread_ts_epoch": thread_ts_epoch,
                    "user_id": m.get("user"),
                    "text": m.get("text"),
                    "raw_json": m,
                }
            )
            normal_candidates += 1
            if m.get("user"):
                user_ids.add(str(m.get("user")))

            is_root = thread_ts == ts
            if is_root:
                root_count += 1
                thread_rows.append(
                    {
                        "channel_id": channel.channel_id,
                        "thread_ts": ts,
                        "thread_ts_epoch": ts_epoch,
                        "root_ts": ts,
                        "root_text": m.get("text"),
                        "reply_count": int(m.get("reply_count") or 0),
                        "last_reply_ts": ts,
                        "last_reply_ts_epoch": ts_epoch,
                        "needs_summary": True,
                    }
                )

        if message_rows:
            stmt = pg_insert(Message.__table__).values(message_rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["channel_id", "ts"])
            db.execute(stmt)

        if thread_rows:
            t = Thread.__table__
            stmt = pg_insert(t).values(thread_rows)
            excluded = stmt.excluded

            update_where = (
                (t.c.root_text.is_(None) & excluded.root_text.is_not(None))
                | (t.c.reply_count != excluded.reply_count)
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=["channel_id", "thread_ts"],
                set_={
                    "reply_count": excluded.reply_count,
                    "root_text": func.coalesce(t.c.root_text, excluded.root_text),
                    "last_reply_ts": func.coalesce(
                        t.c.last_reply_ts, excluded.last_reply_ts
                    ),
                    "last_reply_ts_epoch": func.coalesce(
                        t.c.last_reply_ts_epoch, excluded.last_reply_ts_epoch
                    ),
                    "updated_at": func.now(),
                },
                where=update_where,
            )
            db.execute(stmt)

        db.commit()

        if not next_cursor:
            break
        cursor = next_cursor

    if user_ids:
        _ensure_users_cached(db, slack, user_ids)

    if max_ts_epoch > (channel.last_ts_epoch or 0.0):
        channel.last_ts_epoch = max_ts_epoch
        channel.last_ts = max_ts_str

    channel.last_ingested_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(channel)

    return {
        "channel_id": channel.channel_id,
        "fetched": fetched,
        "saved_candidates": normal_candidates,
        "roots": root_count,
        "max_ts_epoch": max_ts_epoch,
        "new_last_ts": channel.last_ts,
    }


def _ensure_users_cached(db: Session, slack: SlackClient, user_ids: set[str]) -> None:
    if not user_ids:
        return

    existing_rows = db.query(UserCache.user_id).filter(UserCache.user_id.in_(user_ids)).all()
    known_ids = {row[0] for row in existing_rows if row and row[0]}

    to_fetch = [uid for uid in user_ids if uid and uid not in known_ids]
    if not to_fetch:
        return

    for uid in to_fetch:
        try:
            user_obj = slack.get_user_info(uid)
            upsert_user_cache(db, user_obj)
            db.commit()
        except SlackCallError:
            db.rollback()
            continue
        except Exception:
            db.rollback()
            continue


def ingest_channel_thread_replies(db: Session, slack: SlackClient, channel: Channel) -> dict:
    q = (
        db.query(Thread)
        .filter(Thread.channel_id == channel.channel_id)
        .order_by(Thread.updated_at.desc())
    )

    total_threads = q.count()
    if total_threads == 0:
        channel.last_ingested_at = datetime.now(timezone.utc)
        db.commit()
        return {
            "channel_id": channel.channel_id,
            "threads_polled": 0,
            "threads_with_new_replies": 0,
            "fetched": 0,
            "saved_candidates": 0,
            "max_threads_poll_per_run": settings.max_threads_poll_per_run,
        }

    max_poll = min(settings.max_threads_poll_per_run, total_threads)
    start_offset = 0
    if total_threads > max_poll:
        anchor = channel.last_ingested_at or datetime.now(timezone.utc)
        start_offset = int(anchor.timestamp()) % total_threads

    threads: list[Thread] = []
    if start_offset < total_threads:
        first = q.offset(start_offset).limit(max_poll).all()
        threads.extend(first)
        if len(threads) < max_poll:
            second = q.offset(0).limit(max_poll - len(threads)).all()
            threads.extend(second)
    else:
        threads = q.limit(max_poll).all()

    # Deduplicate in case of wrap-around overlap
    seen_ts: set[str] = set()
    unique_threads: list[Thread] = []
    for th in threads:
        if th.thread_ts in seen_ts:
            continue
        seen_ts.add(th.thread_ts)
        unique_threads.append(th)

    threads = unique_threads[:max_poll]

    total_threads = len(threads)
    threads_with_new = 0
    fetched_total = 0
    normal_candidates_total = 0

    for th in threads:
        try:
            r = ingest_single_thread_replies(db, slack, channel_id=channel.channel_id, thread=th)
            fetched_total += r["fetched"]
            normal_candidates_total += r["saved_candidates"]
            if r["new_reply"]:
                threads_with_new += 1
        except Exception:
            db.rollback()
            continue

    channel.last_ingested_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "channel_id": channel.channel_id,
        "threads_polled": total_threads,
        "threads_with_new_replies": threads_with_new,
        "fetched": fetched_total,
        "saved_candidates": normal_candidates_total,
        "max_threads_poll_per_run": settings.max_threads_poll_per_run,
    }


def ingest_single_thread_replies(
    db: Session, slack: SlackClient, *, channel_id: str, thread: Thread
) -> dict:
    oldest = thread.last_reply_ts or thread.thread_ts
    old_last_epoch = thread.last_reply_ts_epoch or thread.thread_ts_epoch

    cursor: str | None = None
    fetched = 0
    saved_candidates = 0

    max_ts_epoch = old_last_epoch
    max_ts_str = thread.last_reply_ts or thread.thread_ts

    root_reply_count: int | None = None
    root_text: str | None = None
    user_ids: set[str] = set()

    while True:
        try:
            msgs, next_cursor = slack.conversations_replies_page(
                channel_id=channel_id,
                thread_ts=thread.thread_ts,
                oldest=oldest,
                cursor=cursor,
                limit=200,
                inclusive=True,
            )
        except SlackCallError as e:
            if e.error_code == "not_in_channel":
                try:
                    slack.join_channel(channel_id)
                    msgs, next_cursor = slack.conversations_replies_page(
                        channel_id=channel_id,
                        thread_ts=thread.thread_ts,
                        oldest=oldest,
                        cursor=cursor,
                        limit=200,
                        inclusive=True,
                    )
                except Exception:
                    raise
            else:
                raise
        fetched += len(msgs)

        message_rows: list[dict] = []

        for m in msgs:
            if m.get("ts") == thread.thread_ts:
                try:
                    root_reply_count = int(m.get("reply_count") or 0)
                except Exception:
                    root_reply_count = 0
                root_text = m.get("text") or root_text

            if m.get("type") != "message":
                continue
            if m.get("subtype"):
                continue

            ts = m.get("ts")
            if not ts:
                continue

            ts_epoch = float(ts)

            if ts_epoch > max_ts_epoch:
                max_ts_epoch = ts_epoch
                max_ts_str = ts

            message_rows.append(
                {
                    "channel_id": channel_id,
                    "ts": ts,
                    "ts_epoch": ts_epoch,
                    "thread_ts": thread.thread_ts,
                    "thread_ts_epoch": thread.thread_ts_epoch,
                    "user_id": m.get("user"),
                    "text": m.get("text"),
                    "raw_json": m,
                }
            )
            saved_candidates += 1
            if m.get("user"):
                user_ids.add(str(m.get("user")))

        if message_rows:
            stmt = pg_insert(Message.__table__).values(message_rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["channel_id", "ts"])
            db.execute(stmt)

        db.commit()

        if not next_cursor:
            break
        cursor = next_cursor

    new_reply = max_ts_epoch > old_last_epoch
    changed = False

    if user_ids:
        _ensure_users_cached(db, slack, user_ids)

    if root_reply_count is not None and root_reply_count != (thread.reply_count or 0):
        thread.reply_count = root_reply_count
        changed = True

    if root_text and not thread.root_text:
        thread.root_text = root_text
        changed = True

    if new_reply:
        thread.last_reply_ts_epoch = max_ts_epoch
        thread.last_reply_ts = max_ts_str
        thread.needs_summary = True
        changed = True

    if changed:
        db.commit()
    else:
        db.rollback()

    return {
        "thread_ts": thread.thread_ts,
        "fetched": fetched,
        "saved_candidates": saved_candidates,
        "new_reply": new_reply,
        "new_last_reply_ts": thread.last_reply_ts,
    }
