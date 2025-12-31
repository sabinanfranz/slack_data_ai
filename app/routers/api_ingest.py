from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db, get_session_factory, init_db
from app.models import Channel
from app.services.ingest_service import ingest_channel
from app.slack_client import SlackClient, SlackNotConfigured

router = APIRouter(prefix="/api", tags=["ingest"])


class IngestRequest(BaseModel):
    backfill_days: int = Field(default=14, ge=1, le=90)
    mode: str = Field(default="full", pattern="^(full|threads_only)$")


class IngestResponse(BaseModel):
    status: str
    channel_id: str
    counts: dict | None = None
    last_ts_epoch: float | None = None


@router.post("/channels/{channel_id}/ingest", response_model=IngestResponse)
def trigger_ingest(
    channel_id: str,
    payload: IngestRequest,
    db: Session = Depends(get_db),
):
    ch = db.get(Channel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    if not ch.is_active:
        raise HTTPException(status_code=400, detail="Channel is not active")

    try:
        slack = SlackClient()
    except SlackNotConfigured as e:
        raise HTTPException(status_code=400, detail=str(e))

    ch.ingest_status = "running"
    ch.ingest_started_at = datetime.now(timezone.utc)
    ch.ingest_finished_at = None
    ch.ingest_error_message = None
    db.commit()

    try:
        res = ingest_channel(
            db,
            slack,
            channel=ch,
            backfill_days=payload.backfill_days,
            mode=payload.mode,
        )
        ch.ingest_status = "ok"
        ch.ingest_finished_at = datetime.now(timezone.utc)
        ch.ingest_last_result_json = res
        ch.last_ingested_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        db.rollback()
        ch = db.get(Channel, channel_id)
        if ch:
            ch.ingest_status = "error"
            ch.ingest_error_message = str(e)
            ch.ingest_finished_at = datetime.now(timezone.utc)
            db.commit()
        raise HTTPException(status_code=500, detail=str(e))

    counts = {}
    try:
        counts["history_messages"] = res.get("history", {}).get("saved_candidates")
        counts["history_roots"] = res.get("history", {}).get("roots")
        counts["replies_messages"] = res.get("replies", {}).get("saved_candidates")
        counts["replies_threads_with_new"] = res.get("replies", {}).get("threads_with_new_replies")
        last_ts_epoch = res.get("history", {}).get("max_ts_epoch") or ch.last_ts_epoch
    except Exception:
        last_ts_epoch = ch.last_ts_epoch

    return IngestResponse(
        status="ok",
        channel_id=channel_id,
        counts=counts or None,
        last_ts_epoch=last_ts_epoch,
    )
