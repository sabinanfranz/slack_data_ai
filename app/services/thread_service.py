from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import Channel, Message, Thread, ThreadSummary, UserCache
from app.text_render import render_slack_text_to_safe_html

_RE_MENTION = re.compile(r"<@([A-Z0-9]+)")


def list_threads(db: Session, channel_id: str, *, limit: int = 50, offset: int = 0) -> list[dict]:
    ch = db.get(Channel, channel_id)
    if not ch:
        raise KeyError("Channel not found")

    rows = (
        db.query(Thread)
        .filter(Thread.channel_id == channel_id)
        .order_by(Thread.updated_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    thread_ts_list = [t.thread_ts for t in rows]
    one_line_map: dict[str, str] = {}
    if thread_ts_list:
        sums = (
            db.query(ThreadSummary)
            .filter(ThreadSummary.channel_id == channel_id)
            .filter(ThreadSummary.thread_ts.in_(thread_ts_list))
            .all()
        )
        for s in sums:
            try:
                ol = (s.summary_json or {}).get("one_line")
                if ol:
                    one_line_map[s.thread_ts] = str(ol)
            except Exception:
                continue

    out = []
    for t in rows:
        out.append(
            {
                "channel_id": t.channel_id,
                "thread_ts": t.thread_ts,
                "reply_count": t.reply_count,
                "root_text": t.root_text,
                "updated_at": t.updated_at,
                "one_line": one_line_map.get(t.thread_ts),
            }
        )
    return out


def _collect_user_ids(messages: list[Message]) -> set[str]:
    ids: set[str] = set()
    for m in messages:
        if m.user_id:
            ids.add(m.user_id)
        if m.text:
            for uid in _RE_MENTION.findall(m.text):
                ids.add(uid)
    return ids


def _build_user_map(db: Session, user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    rows = db.query(UserCache).filter(UserCache.user_id.in_(list(user_ids))).all()
    m: dict[str, str] = {}
    for r in rows:
        name = (r.display_name or r.real_name or r.user_id or "").strip()
        if name:
            m[r.user_id] = name
    return m


def get_thread_messages_with_html(db: Session, channel_id: str, thread_ts: str) -> dict:
    ch = db.get(Channel, channel_id)
    if not ch:
        raise KeyError("Channel not found")

    th = (
        db.query(Thread)
        .filter(Thread.channel_id == channel_id)
        .filter(Thread.thread_ts == thread_ts)
        .first()
    )
    if not th:
        raise KeyError("Thread not found")

    msgs = (
        db.query(Message)
        .filter(Message.channel_id == channel_id)
        .filter(Message.thread_ts == thread_ts)
        .order_by(Message.ts_epoch.asc())
        .all()
    )

    user_ids = _collect_user_ids(msgs)
    user_map = _build_user_map(db, user_ids)

    items = []
    for m in msgs:
        author_name = None
        if m.user_id:
            author_name = user_map.get(m.user_id) or m.user_id
        text_html = render_slack_text_to_safe_html(m.text, user_map)

        items.append(
            {
                "ts": m.ts,
                "ts_epoch": m.ts_epoch,
                "user_id": m.user_id,
                "author_name": author_name,
                "text": m.text,
                "text_html": text_html,
                "is_root": (m.ts == thread_ts),
            }
        )

    return {
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "reply_count": th.reply_count,
        "root_text": th.root_text,
        "updated_at": th.updated_at,
        "messages": items,
    }
