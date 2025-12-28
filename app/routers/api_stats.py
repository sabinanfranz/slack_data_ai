from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.stats_service import get_channel_stats

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/channels/{channel_id}/stats")
def api_channel_stats(
    channel_id: str,
    days: int = Query(7, ge=1, le=60),
    top_n: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    try:
        return get_channel_stats(db, channel_id, days=days, top_n=top_n)
    except KeyError:
        raise HTTPException(status_code=404, detail="Channel not found")
