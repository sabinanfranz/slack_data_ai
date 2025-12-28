from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.thread_service import get_thread_messages_with_html, list_threads
from app.text_render import render_slack_text_to_safe_html

router = APIRouter(prefix="/api", tags=["utils", "threads"])


class RenderIn(BaseModel):
    text: str
    user_map: dict[str, str] | None = None


class RenderOut(BaseModel):
    text_html: str


@router.post("/utils/render", response_model=RenderOut)
def render_utils(payload: RenderIn) -> RenderOut:
    html_out = render_slack_text_to_safe_html(payload.text, payload.user_map)
    return RenderOut(text_html=html_out)


class ThreadListItem(BaseModel):
    channel_id: str
    thread_ts: str
    reply_count: int
    root_text: str | None
    updated_at: datetime
    one_line: str | None = None


@router.get("/channels/{channel_id}/threads", response_model=list[ThreadListItem])
def api_list_threads(
    channel_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100000),
    db: Session = Depends(get_db),
):
    try:
        return list_threads(db, channel_id, limit=limit, offset=offset)
    except KeyError:
        raise HTTPException(status_code=404, detail="Channel not found")


class ThreadMessageOut(BaseModel):
    ts: str
    ts_epoch: float
    user_id: str | None
    author_name: str | None
    text: str | None
    text_html: str
    is_root: bool


class ThreadDetailOut(BaseModel):
    channel_id: str
    thread_ts: str
    reply_count: int
    root_text: str | None
    updated_at: datetime
    messages: list[ThreadMessageOut]


@router.get("/channels/{channel_id}/threads/{thread_ts}", response_model=ThreadDetailOut)
def api_thread_detail(channel_id: str, thread_ts: str, db: Session = Depends(get_db)):
    try:
        return get_thread_messages_with_html(db, channel_id, thread_ts)
    except KeyError as e:
        msg = str(e)
        if "Channel" in msg:
            raise HTTPException(status_code=404, detail="Channel not found")
        raise HTTPException(status_code=404, detail="Thread not found")
