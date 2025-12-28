from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Channel, Message, Thread, UserCache


@dataclass
class KstRange:
    start_date_kst: date
    end_date_kst_exclusive: date
    start_epoch_utc: float
    end_epoch_utc: float


def _kst_range(days: int) -> KstRange:
    kst = ZoneInfo(settings.tz)
    now_kst = datetime.now(tz=kst)
    start_date = now_kst.date() - timedelta(days=days - 1)
    end_date_excl = now_kst.date() + timedelta(days=1)

    start_dt_kst = datetime.combine(start_date, time.min, tzinfo=kst)
    end_dt_kst = datetime.combine(end_date_excl, time.min, tzinfo=kst)

    start_epoch = start_dt_kst.astimezone(timezone.utc).timestamp()
    end_epoch = end_dt_kst.astimezone(timezone.utc).timestamp()

    return KstRange(
        start_date_kst=start_date,
        end_date_kst_exclusive=end_date_excl,
        start_epoch_utc=start_epoch,
        end_epoch_utc=end_epoch,
    )


def get_channel_stats(db: Session, channel_id: str, *, days: int, top_n: int) -> dict:
    ch = db.get(Channel, channel_id)
    if not ch:
        raise KeyError("Channel not found")

    r = _kst_range(days)

    total_messages = (
        db.query(func.count())
        .select_from(Message)
        .filter(Message.channel_id == channel_id)
        .filter(Message.ts_epoch >= r.start_epoch_utc)
        .filter(Message.ts_epoch < r.end_epoch_utc)
        .scalar()
        or 0
    )

    total_threads = (
        db.query(func.count(func.distinct(Message.thread_ts)))
        .filter(Message.channel_id == channel_id)
        .filter(Message.ts_epoch >= r.start_epoch_utc)
        .filter(Message.ts_epoch < r.end_epoch_utc)
        .scalar()
        or 0
    )

    unique_users = (
        db.query(func.count(func.distinct(Message.user_id)))
        .filter(Message.channel_id == channel_id)
        .filter(Message.ts_epoch >= r.start_epoch_utc)
        .filter(Message.ts_epoch < r.end_epoch_utc)
        .filter(Message.user_id.is_not(None))
        .scalar()
        or 0
    )

    kst_day = func.date(
        func.timezone(settings.tz, func.to_timestamp(Message.ts_epoch))
    ).label("kst_day")

    daily_rows = (
        db.query(kst_day, func.count().label("cnt"))
        .filter(Message.channel_id == channel_id)
        .filter(Message.ts_epoch >= r.start_epoch_utc)
        .filter(Message.ts_epoch < r.end_epoch_utc)
        .group_by(kst_day)
        .all()
    )

    daily_map = {row[0].isoformat(): int(row[1]) for row in daily_rows if row[0] is not None}
    day_list = [(r.start_date_kst + timedelta(days=i)).isoformat() for i in range(days)]
    daily_messages = [
        {"date_kst": d, "message_count": daily_map.get(d, 0)} for d in day_list
    ]

    user_counts = (
        db.query(Message.user_id, func.count().label("cnt"))
        .filter(Message.channel_id == channel_id)
        .filter(Message.ts_epoch >= r.start_epoch_utc)
        .filter(Message.ts_epoch < r.end_epoch_utc)
        .filter(Message.user_id.is_not(None))
        .group_by(Message.user_id)
        .order_by(desc("cnt"))
        .limit(top_n)
        .all()
    )
    top_user_ids = [u for (u, _) in user_counts if u]
    user_name_map = {}
    if top_user_ids:
        rows = db.query(UserCache).filter(UserCache.user_id.in_(top_user_ids)).all()
        for u in rows:
            user_name_map[u.user_id] = (u.display_name or u.real_name or u.user_id)

    top_users = []
    for uid, cnt in user_counts:
        top_users.append(
            {
                "user_id": uid,
                "name": user_name_map.get(uid) or uid,
                "message_count": int(cnt),
            }
        )

    active_threads_subq = (
        db.query(Message.thread_ts.label("thread_ts"))
        .filter(Message.channel_id == channel_id)
        .filter(Message.ts_epoch >= r.start_epoch_utc)
        .filter(Message.ts_epoch < r.end_epoch_utc)
        .filter(Message.thread_ts.is_not(None))
        .distinct()
        .subquery()
    )

    top_threads_rows = (
        db.query(Thread)
        .join(active_threads_subq, (Thread.thread_ts == active_threads_subq.c.thread_ts))
        .filter(Thread.channel_id == channel_id)
        .order_by(Thread.reply_count.desc(), Thread.updated_at.desc())
        .limit(top_n)
        .all()
    )

    top_threads = []
    for t in top_threads_rows:
        top_threads.append(
            {
                "thread_ts": t.thread_ts,
                "reply_count": int(t.reply_count or 0),
                "root_text": t.root_text,
                "updated_at": t.updated_at,
            }
        )

    return {
        "channel_id": channel_id,
        "channel_name": ch.name,
        "days": days,
        "top_n": top_n,
        "start_date_kst": r.start_date_kst.isoformat(),
        "end_date_kst_exclusive": r.end_date_kst_exclusive.isoformat(),
        "total_messages": int(total_messages),
        "total_threads": int(total_threads),
        "unique_users": int(unique_users),
        "daily_messages": daily_messages,
        "top_threads": top_threads,
        "top_users": top_users,
    }
