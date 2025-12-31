from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.llm_client import LLMClient
from app.models import Message, Thread, ThreadReport, ThreadSummary, UserCache
from app.services.summary_service import summarize_thread


class ParticipantRole(BaseModel):
    name: str
    role: str
    evidence: list[str] = Field(default_factory=list)


class DailyProgress(BaseModel):
    date_kst: str
    progress: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)


class ThreadReportOut(BaseModel):
    topic: str
    participants_roles: list[ParticipantRole] = Field(default_factory=list)
    timeline_daily: list[DailyProgress] = Field(default_factory=list)


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


def _epoch_to_kst_strings(epoch: float) -> tuple[str, str]:
    kst = ZoneInfo(settings.tz)
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(kst)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m-%d %H:%M")


def _collect_messages_for_report(
    db: Session, *, channel_id: str, thread_ts: str
) -> tuple[list[dict], dict[str, str]]:
    msgs = (
        db.query(Message)
        .filter(Message.channel_id == channel_id)
        .filter(Message.thread_ts == thread_ts)
        .order_by(Message.ts_epoch.asc())
        .all()
    )
    if not msgs:
        return [], {}

    # Collect user IDs
    user_ids: set[str] = set()
    for m in msgs:
        if m.user_id:
            user_ids.add(m.user_id)

    user_map = _build_user_map(db, user_ids)

    max_n = settings.max_messages_per_thread_for_report
    if len(msgs) > max_n:
        # Keep root + latest tail
        root = None
        for m in msgs:
            if m.ts == thread_ts:
                root = m
                break
        tail = msgs[-(max_n - 1) :]
        sampled = []
        if root:
            sampled.append(root)
        for m in tail:
            if root and m.ts == root.ts:
                continue
            sampled.append(m)
        msgs = sampled

    items: list[dict] = []
    for m in msgs:
        date_kst, t_kst = _epoch_to_kst_strings(m.ts_epoch)
        author = None
        if m.user_id:
            author = user_map.get(m.user_id) or m.user_id
        items.append(
            {
                "t_kst": t_kst,
                "date_kst": date_kst,
                "author": author,
                "text": (m.text or "")[:2000],
            }
        )

    return items, user_map


def _latest_epoch_for_thread(thread: Thread) -> float:
    return float(thread.last_reply_ts_epoch or thread.thread_ts_epoch or 0.0)


def ensure_thread_report(
    db: Session,
    llm: LLMClient,
    *,
    channel_id: str,
    thread: Thread,
    force: bool = False,
) -> dict:
    """
    Generate or refresh thread report if stale.
    """
    latest_epoch = _latest_epoch_for_thread(thread)
    latest_ts = thread.last_reply_ts or thread.thread_ts

    existing = (
        db.query(ThreadReport)
        .filter(ThreadReport.channel_id == channel_id)
        .filter(ThreadReport.thread_ts == thread.thread_ts)
        .first()
    )
    if existing and (not force) and float(existing.source_latest_ts_epoch or 0) >= float(latest_epoch):
        return {
            "thread_ts": thread.thread_ts,
            "skipped": "up_to_date",
            "source_latest_ts_epoch": existing.source_latest_ts_epoch,
        }

    # Ensure summary is fresh for additional context
    try:
        summarize_thread(db, llm, channel_id=channel_id, thread=thread)
    except Exception:
        db.rollback()

    summary_row = (
        db.query(ThreadSummary)
        .filter(ThreadSummary.channel_id == channel_id)
        .filter(ThreadSummary.thread_ts == thread.thread_ts)
        .first()
    )
    summary_payload = summary_row.summary_json if summary_row else {}

    messages, _ = _collect_messages_for_report(
        db, channel_id=channel_id, thread_ts=thread.thread_ts
    )
    if not messages:
        return {"thread_ts": thread.thread_ts, "skipped": "no_messages"}

    user_input = json.dumps(
        {
            "channel_id": channel_id,
            "thread_ts": thread.thread_ts,
            "reply_count": int(thread.reply_count or 0),
            "thread_summary": summary_payload or {},
            "messages": messages,
        },
        ensure_ascii=False,
    )

    instructions = f"""
너는 슬랙 스레드 전체를 {settings.summary_language}로 분석해 구조화 리포트를 작성한다.
- topic: 논의의 주제를 한 줄로 요약한다.
- participants_roles: 대화에서 보인 행동/기여 기반으로 역할을 추정(예: 의사결정, 실행, 질문/검증, 조율, 리스크 제기 등)하고 evidence에 짧은 근거를 남긴다.
- timeline_daily: date_kst 오름차순, 해당 날짜에 실제 발언이 있을 때만 생성한다. progress/decisions/open_questions를 사실 기반으로 채운다.
- 과장 없이 보수적으로 작성하고, 근거가 없으면 비워둔다.
- 모든 필드는 주어진 스키마(Structured Outputs)를 따른다. 비어있으면 빈 배열([])을 사용한다.
"""

    parsed: ThreadReportOut = llm.parse_structured(
        model=settings.openai_model,
        instructions=instructions.strip(),
        user_input=user_input,
        text_format=ThreadReportOut,
        max_output_tokens=1400,
        temperature=0.2,
    )

    report_dict = parsed.model_dump() if hasattr(parsed, "model_dump") else parsed.dict()

    stmt = pg_insert(ThreadReport.__table__).values(
        channel_id=channel_id,
        thread_ts=thread.thread_ts,
        report_json=report_dict,
        model=settings.openai_model,
        source_latest_ts=latest_ts,
        source_latest_ts_epoch=latest_epoch,
        updated_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["channel_id", "thread_ts"],
        set_=dict(
            report_json=report_dict,
            model=settings.openai_model,
            source_latest_ts=latest_ts,
            source_latest_ts_epoch=latest_epoch,
            updated_at=datetime.now(timezone.utc),
        ),
    )
    db.execute(stmt)
    db.commit()

    return {
        "thread_ts": thread.thread_ts,
        "report_created": True,
        "source_latest_ts_epoch": latest_epoch,
    }


# Backwards-compat alias
def generate_thread_report(
    db: Session,
    llm: LLMClient,
    *,
    channel_id: str,
    thread: Thread,
    force: bool = False,
) -> dict:
    return ensure_thread_report(db, llm, channel_id=channel_id, thread=thread, force=force)
