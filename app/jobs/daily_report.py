from __future__ import annotations

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(filename=".env", usecwd=True), override=False)

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.db import get_session_factory
from app.llm_client import LLMClient
from app.models import Channel, DailyReport, Message, Thread, ThreadSummary
from app.services.summary_service import summarize_thread


class DailyActionItem(BaseModel):
    task: str
    owner_hint: str | None = None
    context_thread_ts: str | None = None


class NotableThread(BaseModel):
    thread_ts: str
    one_line: str
    why: str


class DailyReportOut(BaseModel):
    date_kst: str
    highlights_top5: list[str] = Field(default_factory=list)
    agenda_progress: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    action_items: list[DailyActionItem] = Field(default_factory=list)
    notable_threads: list[NotableThread] = Field(default_factory=list)


ALL_CHANNEL_SENTINEL = "__ALL__"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--date", type=str, default=None, help="KST date YYYY-MM-DD. Default: yesterday(KST)")
    return p.parse_args()


def _resolve_report_date_kst(arg: str | None) -> date:
    kst = ZoneInfo(settings.tz)
    now_kst = datetime.now(tz=kst)
    if arg:
        return date.fromisoformat(arg)
    return now_kst.date() - timedelta(days=1)


def _kst_day_range_epoch(report_date_kst: date) -> tuple[float, float]:
    kst = ZoneInfo(settings.tz)
    start_dt = datetime.combine(report_date_kst, datetime.min.time(), tzinfo=kst)
    end_dt = start_dt + timedelta(days=1)
    return (
        start_dt.astimezone(timezone.utc).timestamp(),
        end_dt.astimezone(timezone.utc).timestamp(),
    )


def _ensure_thread_summaries(
    db, llm: LLMClient, channel_id: str, thread_ts_list: list[str]
) -> list[dict]:
    if not thread_ts_list:
        return []

    threads = (
        db.query(Thread)
        .filter(Thread.channel_id == channel_id)
        .filter(Thread.thread_ts.in_(thread_ts_list))
        .all()
    )
    th_map = {t.thread_ts: t for t in threads}

    sums = (
        db.query(ThreadSummary)
        .filter(ThreadSummary.channel_id == channel_id)
        .filter(ThreadSummary.thread_ts.in_(thread_ts_list))
        .all()
    )
    sum_map = {s.thread_ts: s for s in sums}

    out = []
    for ts in thread_ts_list:
        t = th_map.get(ts)
        if not t:
            continue

        need = False
        s = sum_map.get(ts)
        latest_epoch = t.last_reply_ts_epoch or t.thread_ts_epoch

        if (s is None) or (float(s.source_latest_ts_epoch or 0) < float(latest_epoch or 0)) or (
            t.needs_summary is True
        ):
            need = True

        if need:
            try:
                summarize_thread(db, llm, channel_id=channel_id, thread=t)
                s = (
                    db.query(ThreadSummary)
                    .filter(ThreadSummary.channel_id == channel_id)
                    .filter(ThreadSummary.thread_ts == ts)
                    .first()
                )
            except Exception:
                db.rollback()

        if not s:
            continue

        payload = s.summary_json or {}
        out.append(
            {
                "thread_ts": ts,
                "one_line": payload.get("one_line") or "",
                "summary": payload.get("summary") or "",
                "decisions": payload.get("decisions") or [],
                "blockers": payload.get("blockers") or [],
                "action_items": payload.get("action_items") or [],
            }
        )
    return out


def _build_daily_report(
    llm: LLMClient,
    *,
    report_date_kst: date,
    channel_id: str,
    channel_name: str | None,
    thread_summaries: list[dict],
) -> dict:
    instructions = f"""
너는 사업부 슬랙 대화를 {settings.summary_language}로 '데일리 리포트'로 정리한다.
- 출력은 반드시 주어진 스키마를 만족해야 한다(Structured Outputs).
- 과장 없이 사실 기반으로 요약하되, 실행 가능한 액션아이템을 우선한다.
- 비어있는 항목은 빈 배열([])을 사용한다.
"""

    user_input = json.dumps(
        {
            "date_kst": report_date_kst.isoformat(),
            "channel_id": channel_id,
            "channel_name": channel_name,
            "thread_summaries": thread_summaries,
        },
        ensure_ascii=False,
    )

    parsed = llm.parse_structured(
        model=settings.openai_model,
        instructions=instructions.strip(),
        user_input=user_input,
        text_format=DailyReportOut,
        max_output_tokens=1400,
        temperature=0.2,
    )
    return parsed.model_dump() if hasattr(parsed, "model_dump") else parsed.dict()


def _upsert_daily_report(
    db, *, report_date_kst: date, channel_id: str, payload: dict
) -> None:
    stmt = pg_insert(DailyReport.__table__).values(
        report_date=report_date_kst,
        channel_id=channel_id,
        payload_json=payload,
        model=settings.openai_model,
        created_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["report_date", "channel_id"],
        set_=dict(
            payload_json=payload,
            model=settings.openai_model,
            created_at=datetime.now(timezone.utc),
        ),
    )
    db.execute(stmt)
    db.commit()


def main() -> None:
    args = _parse_args()
    report_date_kst = _resolve_report_date_kst(args.date)
    start_epoch, end_epoch = _kst_day_range_epoch(report_date_kst)

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to .env or set environment variable OPENAI_API_KEY."
        )
    if not getattr(settings, "database_url", None) and not os.getenv("DATABASE_URL"):
        raise RuntimeError(
            "DATABASE_URL is missing. Add it to .env or set environment variable DATABASE_URL."
        )

    llm = LLMClient()

    SessionLocal = get_session_factory()
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not set; cannot run daily report job.")

    with SessionLocal() as db:
        channels = db.query(Channel).filter(Channel.is_active.is_(True)).all()

        per_channel_payloads = []
        for ch in channels:
            active_thread_ts = (
                db.query(Message.thread_ts)
                .filter(Message.channel_id == ch.channel_id)
                .filter(Message.ts_epoch >= start_epoch)
                .filter(Message.ts_epoch < end_epoch)
                .filter(Message.thread_ts.is_not(None))
                .distinct()
                .all()
            )
            thread_ts_list = [r[0] for r in active_thread_ts if r and r[0]]

            if not thread_ts_list:
                payload = _build_daily_report(
                    llm,
                    report_date_kst=report_date_kst,
                    channel_id=ch.channel_id,
                    channel_name=ch.name,
                    thread_summaries=[],
                )
                _upsert_daily_report(
                    db, report_date_kst=report_date_kst, channel_id=ch.channel_id, payload=payload
                )
                per_channel_payloads.append(
                    {"channel_id": ch.channel_id, "channel_name": ch.name, "report": payload}
                )
                continue

            top_threads = (
                db.query(Thread.thread_ts)
                .filter(Thread.channel_id == ch.channel_id)
                .filter(Thread.thread_ts.in_(thread_ts_list))
                .order_by(Thread.reply_count.desc(), Thread.updated_at.desc())
                .limit(settings.max_threads_per_daily_report)
                .all()
            )
            selected = [r[0] for r in top_threads if r and r[0]]

            summaries = _ensure_thread_summaries(db, llm, ch.channel_id, selected)

            payload = _build_daily_report(
                llm,
                report_date_kst=report_date_kst,
                channel_id=ch.channel_id,
                channel_name=ch.name,
                thread_summaries=summaries,
            )
            _upsert_daily_report(
                db, report_date_kst=report_date_kst, channel_id=ch.channel_id, payload=payload
            )
            per_channel_payloads.append(
                {"channel_id": ch.channel_id, "channel_name": ch.name, "report": payload}
            )

        overall_in = json.dumps(
            {"date_kst": report_date_kst.isoformat(), "channels": per_channel_payloads},
            ensure_ascii=False,
        )
        overall_instructions = f"""
너는 여러 채널의 데일리 리포트를 {settings.summary_language}로 종합한다.
- 출력은 반드시 주어진 스키마를 만족해야 한다(Structured Outputs).
- notable_threads / action_items의 context_thread_ts는 가능하면 \"channel_id|thread_ts\" 형태로 넣어라.
- 비어있는 항목은 빈 배열([])을 사용한다.
"""
        overall_parsed = llm.parse_structured(
            model=settings.openai_model,
            instructions=overall_instructions.strip(),
            user_input=overall_in,
            text_format=DailyReportOut,
            max_output_tokens=1600,
            temperature=0.2,
        )
        overall_payload = (
            overall_parsed.model_dump()
            if hasattr(overall_parsed, "model_dump")
            else overall_parsed.dict()
        )
        _upsert_daily_report(
            db,
            report_date_kst=report_date_kst,
            channel_id=ALL_CHANNEL_SENTINEL,
            payload=overall_payload,
        )

    print(f"[daily_report] done date_kst={report_date_kst.isoformat()}")


if __name__ == "__main__":
    main()
