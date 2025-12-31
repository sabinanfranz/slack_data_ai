from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm_client import LLMClient
from app.models import Channel, Message, Thread, ThreadReport, ThreadSummary
from app.config import settings
from app.services.summary_service import summarize_thread
from app.services.thread_report_service import ensure_thread_report, generate_thread_report

router = APIRouter(prefix="/api/thread-reports", tags=["thread-reports"])


class ChannelOut(BaseModel):
    channel_id: str
    name: str | None

    class Config:
        from_attributes = True


@router.get("/channels", response_model=list[ChannelOut])
def list_active_channels(db: Session = Depends(get_db)):
    rows = (
        db.query(Channel)
        .filter(Channel.is_active.is_(True))
        .order_by(Channel.created_at.desc())
        .all()
    )
    return rows


class ThreadListItem(BaseModel):
    channel_id: str
    thread_ts: str
    reply_count: int
    updated_at: datetime
    title: str | None
    one_line: str | None = None
    has_report: bool


@router.get("", response_model=list[ThreadListItem])
def list_thread_reports(
    channel_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    ch = db.get(Channel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    root_subq = (
        db.query(Message.thread_ts, Message.text.label("root_text"))
        .filter(Message.channel_id == channel_id)
        .filter(Message.thread_ts == Message.ts)
        .subquery()
    )

    rows = (
        db.query(
            Thread.channel_id,
            Thread.thread_ts,
            Thread.reply_count,
            Thread.updated_at,
            root_subq.c.root_text,
            ThreadSummary.summary_json,
            ThreadReport.id.label("report_exists"),
        )
        .outerjoin(root_subq, Thread.thread_ts == root_subq.c.thread_ts)
        .outerjoin(
            ThreadSummary,
            (ThreadSummary.channel_id == Thread.channel_id)
            & (ThreadSummary.thread_ts == Thread.thread_ts),
        )
        .outerjoin(
            ThreadReport,
            (ThreadReport.channel_id == Thread.channel_id)
            & (ThreadReport.thread_ts == Thread.thread_ts),
        )
        .filter(Thread.channel_id == channel_id)
        .order_by(desc(Thread.updated_at))
        .limit(limit)
        .all()
    )

    out: list[ThreadListItem] = []
    for r in rows:
        title = (r.root_text or "").strip() or None
        if title:
            title = title[:120]
        one_line = None
        if r.summary_json:
            try:
                one_line = (r.summary_json or {}).get("one_line")
            except Exception:
                one_line = None
        out.append(
            ThreadListItem(
                channel_id=r.channel_id,
                thread_ts=r.thread_ts,
                reply_count=int(r.reply_count or 0),
                updated_at=r.updated_at,
                title=title,
                one_line=one_line,
                has_report=bool(r.report_exists),
            )
        )
    return out


class ThreadReportDetail(BaseModel):
    channel_id: str
    thread_ts: str
    report_json: dict
    model: str
    source_latest_ts: str
    source_latest_ts_epoch: float
    updated_at: datetime
    meta: dict | None = None


@router.get("/{channel_id}/{thread_ts}", response_model=ThreadReportDetail)
def get_thread_report(channel_id: str, thread_ts: str, db: Session = Depends(get_db)):
    thread = (
        db.query(Thread)
        .filter(Thread.channel_id == channel_id)
        .filter(Thread.thread_ts == thread_ts)
        .first()
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    row = (
        db.query(ThreadReport)
        .filter(ThreadReport.channel_id == channel_id)
        .filter(ThreadReport.thread_ts == thread_ts)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Thread report not found")
    latest_epoch = float(thread.last_reply_ts_epoch or thread.thread_ts_epoch or 0)
    meta = {
        "latest_epoch": latest_epoch,
        "report_source_latest_ts_epoch": float(row.source_latest_ts_epoch or 0),
        "is_stale": float(row.source_latest_ts_epoch or 0) < latest_epoch,
    }
    return ThreadReportDetail(
        channel_id=row.channel_id,
        thread_ts=row.thread_ts,
        report_json=row.report_json,
        model=row.model,
        source_latest_ts=row.source_latest_ts,
        source_latest_ts_epoch=row.source_latest_ts_epoch,
        updated_at=row.updated_at,
        meta=meta,
    )


class RefreshResult(BaseModel):
    thread_ts: str
    status: str
    source_latest_ts_epoch: float | None = None
    report_json: dict | None = None
    model: str | None = None
    source_latest_ts: str | None = None
    updated_at: datetime | None = None
    meta: dict | None = None


@router.post("/{channel_id}/{thread_ts}/refresh", response_model=RefreshResult)
def refresh_thread_report(
    channel_id: str,
    thread_ts: str,
    force: bool = False,
    db: Session = Depends(get_db),
):
    ch = db.get(Channel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    thread = (
        db.query(Thread)
        .filter(Thread.channel_id == channel_id)
        .filter(Thread.thread_ts == thread_ts)
        .first()
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if not (settings.openai_api_key or None):
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "code": "OPENAI_API_KEY_MISSING",
                "message": "Set OPENAI_API_KEY in .env or environment.",
            },
        )

    try:
        llm = LLMClient()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    latest_epoch = float(thread.last_reply_ts_epoch or thread.thread_ts_epoch or 0)
    summary_row = (
        db.query(ThreadSummary)
        .filter(ThreadSummary.channel_id == channel_id)
        .filter(ThreadSummary.thread_ts == thread.thread_ts)
        .first()
    )
    need_summary = (
        thread.needs_summary
        or (summary_row is None)
        or float((summary_row.source_latest_ts_epoch or 0)) < latest_epoch
    )
    if need_summary:
        try:
            summarize_thread(db, llm, channel_id=channel_id, thread=thread)
        except Exception:
            db.rollback()

    try:
        res = generate_thread_report(
            db, llm, channel_id=channel_id, thread=thread, force=True if not force else force
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    row = (
        db.query(ThreadReport)
        .filter(ThreadReport.channel_id == channel_id)
        .filter(ThreadReport.thread_ts == thread_ts)
        .first()
    )
    if not row:
        return RefreshResult(thread_ts=thread_ts, status="error", source_latest_ts_epoch=None)

    latest_epoch = float(thread.last_reply_ts_epoch or thread.thread_ts_epoch or 0)
    meta = {
        "latest_epoch": latest_epoch,
        "report_source_latest_ts_epoch": float(row.source_latest_ts_epoch or 0),
        "is_stale": float(row.source_latest_ts_epoch or 0) < latest_epoch,
    }

    return RefreshResult(
        thread_ts=thread_ts,
        status="refreshed" if not res.get("skipped") else res["skipped"],
        source_latest_ts_epoch=row.source_latest_ts_epoch,
        report_json=row.report_json,
        model=row.model,
        source_latest_ts=row.source_latest_ts,
        updated_at=row.updated_at,
        meta=meta,
    )
