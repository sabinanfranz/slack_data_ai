from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.llm_client import LLMClient
from app.models import Channel, Message, Thread, ThreadSummary, UserCache


class ActionItem(BaseModel):
    task: str
    owner_hint: str | None = None
    due_hint: str | None = None


class ThreadSummaryOut(BaseModel):
    one_line: str = Field(..., description="한 줄 요약")
    summary: str = Field(..., description="3~6문장 요약")
    key_points: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"


def _epoch_to_kst_str(epoch: float) -> str:
    kst = ZoneInfo(settings.tz)
    return (
        datetime.fromtimestamp(epoch, tz=timezone.utc)
        .astimezone(kst)
        .strftime("%Y-%m-%d %H:%M")
    )


def _build_user_map(db: Session, user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    rows = db.query(UserCache).filter(UserCache.user_id.in_(list(user_ids))).all()
    out: dict[str, str] = {}
    for r in rows:
        name = (r.display_name or r.real_name or r.user_id or "").strip()
        if name:
            out[r.user_id] = name
    return out


def _collect_user_ids(msgs: list[Message]) -> set[str]:
    ids: set[str] = set()
    for m in msgs:
        if m.user_id:
            ids.add(m.user_id)
    return ids


def _slice_messages_for_summary(msgs: list[Message], thread_ts: str) -> list[Message]:
    max_n = settings.max_messages_per_thread_for_summary
    if len(msgs) <= max_n:
        return msgs

    root = None
    for m in msgs:
        if m.ts == thread_ts:
            root = m
            break

    tail = msgs[-(max_n - 1) :]
    if root and (tail[0].ts != root.ts):
        return [root] + [m for m in tail if m.ts != root.ts]
    return tail


def summarize_thread(db: Session, llm: LLMClient, *, channel_id: str, thread: Thread) -> dict:
    msgs = (
        db.query(Message)
        .filter(Message.channel_id == channel_id)
        .filter(Message.thread_ts == thread.thread_ts)
        .order_by(Message.ts_epoch.asc())
        .all()
    )
    if not msgs:
        return {"thread_ts": thread.thread_ts, "skipped": "no_messages"}

    msgs = _slice_messages_for_summary(msgs, thread.thread_ts)

    user_ids = _collect_user_ids(msgs)
    user_map = _build_user_map(db, user_ids)

    items = []
    for m in msgs:
        author = None
        if m.user_id:
            author = user_map.get(m.user_id) or m.user_id
        items.append(
            {
                "t_kst": _epoch_to_kst_str(m.ts_epoch),
                "author": author,
                "text": (m.text or "")[:2000],
            }
        )

    source_latest_ts = thread.last_reply_ts or thread.thread_ts
    source_latest_ts_epoch = thread.last_reply_ts_epoch or thread.thread_ts_epoch

    instructions = f"""
너는 슬랙 스레드를 {settings.summary_language}로 요약하는 업무 비서다.
- 출력은 반드시 주어진 스키마를 만족해야 한다(Structured Outputs).
- 비어있는 항목은 빈 배열([])을 사용한다.
- one_line은 짧고 명확하게(가능하면 80자 이내).
- action_items는 가능하면 task 중심으로, owner_hint/due_hint는 추정 가능할 때만 채운다.
"""

    user_input = json.dumps(
        {
            "channel_id": channel_id,
            "thread_ts": thread.thread_ts,
            "reply_count": int(thread.reply_count or 0),
            "source_latest_ts": source_latest_ts,
            "messages": items,
        },
        ensure_ascii=False,
    )

    parsed: ThreadSummaryOut = llm.parse_structured(
        model=settings.openai_model,
        instructions=instructions.strip(),
        user_input=user_input,
        text_format=ThreadSummaryOut,
        max_output_tokens=1200,
        temperature=0.2,
    )

    summary_dict = parsed.model_dump() if hasattr(parsed, "model_dump") else parsed.dict()

    stmt = pg_insert(ThreadSummary.__table__).values(
        channel_id=channel_id,
        thread_ts=thread.thread_ts,
        summary_json=summary_dict,
        model=settings.openai_model,
        source_latest_ts=source_latest_ts,
        source_latest_ts_epoch=source_latest_ts_epoch,
        updated_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["channel_id", "thread_ts"],
        set_=dict(
            summary_json=summary_dict,
            model=settings.openai_model,
            source_latest_ts=source_latest_ts,
            source_latest_ts_epoch=source_latest_ts_epoch,
            updated_at=datetime.now(timezone.utc),
        ),
    )
    db.execute(stmt)

    thread.needs_summary = False
    thread.last_summarized_ts = source_latest_ts
    thread.last_summarized_ts_epoch = source_latest_ts_epoch
    thread.updated_at = datetime.now(timezone.utc)

    db.commit()

    return {"thread_ts": thread.thread_ts, "summarized": True}


def summarize_pending_threads(
    db: Session, llm: LLMClient, *, channel_id: str | None = None, limit: int = 50
) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).timestamp()

    q = (
        db.query(Thread)
        .join(Channel, Channel.channel_id == Thread.channel_id)
        .filter(Channel.is_active.is_(True))
        .filter(Thread.needs_summary.is_(True))
        .filter(Thread.thread_ts_epoch >= cutoff)
    )
    if channel_id:
        q = q.filter(Thread.channel_id == channel_id)

    threads = q.order_by(desc(Thread.updated_at)).limit(limit).all()

    ok = 0
    fail = 0
    for t in threads:
        try:
            summarize_thread(db, llm, channel_id=t.channel_id, thread=t)
            ok += 1
        except Exception:
            db.rollback()
            fail += 1

    return {"attempted": len(threads), "ok": ok, "fail": fail, "limit": limit}
