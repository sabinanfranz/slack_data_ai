from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Channel
from app.slack_client import SlackCallError, SlackClient, SlackNotConfigured
from app.services.user_service import upsert_user_cache

router = APIRouter(prefix="/api", tags=["channels"])

CHANNEL_ID_RE = re.compile(r"^C[A-Z0-9]+$")


def now_kst() -> datetime:
    return datetime.now(tz=ZoneInfo(settings.tz))


def kst_epoch(dt: datetime) -> float:
    return dt.timestamp()


class ChannelOut(BaseModel):
    channel_id: str
    name: str | None
    is_active: bool
    last_ts: str | None
    last_ts_epoch: float | None
    last_ingested_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChannelCreateIn(BaseModel):
    channel_id: str = Field(..., examples=["C0750UMQAD6"])


class ChannelPatchIn(BaseModel):
    is_active: bool


def _channel_name_from_info(ch_info: dict) -> str | None:
    return ch_info.get("name")


@router.get("/channels", response_model=list[ChannelOut])
def list_channels(db: Session = Depends(get_db)):
    rows = db.query(Channel).order_by(Channel.created_at.desc()).all()
    return rows


@router.post("/channels", response_model=ChannelOut)
def create_channel(payload: ChannelCreateIn, db: Session = Depends(get_db)):
    channel_id = payload.channel_id.strip().upper()

    if not CHANNEL_ID_RE.match(channel_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid channel_id format (expected like C0750UMQAD6)",
        )

    try:
        slack = SlackClient()
    except SlackNotConfigured as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        ch_info = slack.get_channel_info(channel_id)
    except SlackCallError as e:
        err_code = e.error_code or ""
        if err_code in {"channel_not_found", "invalid_auth", "not_authed", "account_inactive"}:
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=502, detail=str(e))

    name = _channel_name_from_info(ch_info)

    slack.join_channel(channel_id)

    existing = db.get(Channel, channel_id)
    if existing:
        if name and existing.name != name:
            existing.name = name
            db.commit()
            db.refresh(existing)

        creator = ch_info.get("creator")
        if creator:
            try:
                user_obj = slack.get_user_info(creator)
                _upsert_user_cache(db, user_obj)
                db.commit()
            except Exception:
                db.rollback()
        return existing

    dt = now_kst() - timedelta(days=14)
    epoch = kst_epoch(dt)

    ch = Channel(
        channel_id=channel_id,
        name=name,
        is_active=True,
        last_ts=str(epoch),
        last_ts_epoch=epoch,
        last_ingested_at=None,
    )

    db.add(ch)
    db.commit()
    db.refresh(ch)
    creator = ch_info.get("creator")
    if creator:
        try:
            user_obj = slack.get_user_info(creator)
            _upsert_user_cache(db, user_obj)
            db.commit()
        except Exception:
            db.rollback()

    return ch


@router.patch("/channels/{channel_id}", response_model=ChannelOut)
def patch_channel(channel_id: str, payload: ChannelPatchIn, db: Session = Depends(get_db)):
    channel_id = channel_id.strip().upper()
    ch = db.get(Channel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    ch.is_active = payload.is_active
    db.commit()
    db.refresh(ch)
    return ch
