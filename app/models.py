from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONB_TYPE = JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Channel(Base, TimestampMixin):
    __tablename__ = "channels"

    channel_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    last_ts: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_ts_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)

    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    messages = relationship("Message", back_populates="channel", lazy="noload")
    threads = relationship("Thread", back_populates="channel", lazy="noload")


class UserCache(Base):
    __tablename__ = "users_cache"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    real_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("channel_id", "ts", name="uq_messages_channel_ts"),
        Index("ix_messages_channel_ts_epoch", "channel_id", "ts_epoch"),
        Index("ix_messages_channel_thread_ts_epoch", "channel_id", "thread_ts_epoch"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    channel_id: Mapped[str] = mapped_column(
        Text, ForeignKey("channels.channel_id"), nullable=False
    )

    ts: Mapped[str] = mapped_column(Text, nullable=False)
    ts_epoch: Mapped[float] = mapped_column(Float, nullable=False)

    thread_ts: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_ts_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)

    user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_json: Mapped[dict] = mapped_column(JSONB_TYPE, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    channel = relationship("Channel", back_populates="messages", lazy="noload")


class Thread(Base):
    __tablename__ = "threads"
    __table_args__ = (
        UniqueConstraint("channel_id", "thread_ts", name="uq_threads_channel_threadts"),
        Index("ix_threads_channel_updated_at", "channel_id", "updated_at"),
        Index("ix_threads_channel_thread_ts_epoch", "channel_id", "thread_ts_epoch"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    channel_id: Mapped[str] = mapped_column(
        Text, ForeignKey("channels.channel_id"), nullable=False
    )

    thread_ts: Mapped[str] = mapped_column(Text, nullable=False)
    thread_ts_epoch: Mapped[float] = mapped_column(Float, nullable=False)

    root_ts: Mapped[str] = mapped_column(Text, nullable=False)
    root_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    reply_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_reply_ts: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_reply_ts_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)

    needs_summary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_summarized_ts: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_summarized_ts_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    channel = relationship("Channel", back_populates="threads", lazy="noload")


class ThreadSummary(Base, TimestampMixin):
    __tablename__ = "thread_summaries"
    __table_args__ = (
        UniqueConstraint("channel_id", "thread_ts", name="uq_thread_summaries_channel_threadts"),
        Index("ix_thread_summaries_channel_updated_at", "channel_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    channel_id: Mapped[str] = mapped_column(Text, nullable=False)
    thread_ts: Mapped[str] = mapped_column(Text, nullable=False)

    summary_json: Mapped[dict] = mapped_column(JSONB_TYPE, nullable=False)

    model: Mapped[str] = mapped_column(Text, nullable=False)

    source_latest_ts: Mapped[str] = mapped_column(Text, nullable=False)
    source_latest_ts_epoch: Mapped[float] = mapped_column(Float, nullable=False)


class DailyReport(Base):
    __tablename__ = "daily_reports"
    __table_args__ = (
        UniqueConstraint("report_date", "channel_id", name="uq_daily_reports_date_channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    channel_id: Mapped[str] = mapped_column(Text, nullable=False)

    payload_json: Mapped[dict] = mapped_column(JSONB_TYPE, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
