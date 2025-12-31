> 이 문서는 Slack Digest Admin 프로젝트의 컨텍스트 전달용입니다.
> 대상: 외부 LLM/개발 에이전트, 신규 합류 개발자
> 업데이트 기준: 2025-12-24 / 구현 범위: Step 1~11 (현재 코드 기준)

# DB 스키마

## 현재 구현(Fact)
- 모델 정의: `app/models.py`
- JSON 타입: Postgres는 JSONB, SQLite는 JSON (`JSONB().with_variant(JSON(), "sqlite")`).
- 타임스탬프: `created_at/updated_at`는 timezone-aware, server_default=now(), `onupdate=now()` (해당 컬럼 가진 모델에 한함).

### channels (Channel)
- 컬럼: channel_id(PK Text), name(Text, nullable), is_active(Boolean, default True), last_ts(Text, nullable), last_ts_epoch(Float, nullable), last_ingested_at(DateTime tz, nullable), ingest_status(Text, default idle), ingest_started_at(DateTime tz, nullable), ingest_finished_at(DateTime tz, nullable), ingest_error_message(Text, nullable), ingest_last_result_json(JSONB/JSON, nullable), created_at/updated_at.
- 관계: messages, threads (lazy=noload).

### users_cache (UserCache)
- 컬럼: user_id(PK Text), display_name(Text, nullable), real_name(Text, nullable), updated_at(DateTime tz, server_default=now, onupdate=now).

### messages (Message)
- 컬럼: id(PK Integer), channel_id(FK → channels.channel_id), ts(Text), ts_epoch(Float), thread_ts(Text, nullable), thread_ts_epoch(Float, nullable), user_id(Text, nullable), text(Text, nullable), raw_json(JSONB/JSON), created_at(DateTime tz, server_default=now).
- 제약/인덱스: UNIQUE(channel_id, ts) `uq_messages_channel_ts`; 인덱스 `ix_messages_channel_ts_epoch`(channel_id, ts_epoch), `ix_messages_channel_thread_ts_epoch`(channel_id, thread_ts_epoch).

### threads (Thread)
- 컬럼: id(PK Integer), channel_id(FK), thread_ts(Text), thread_ts_epoch(Float), root_ts(Text), root_text(Text, nullable), reply_count(Integer, default 0), last_reply_ts(Text, nullable), last_reply_ts_epoch(Float, nullable), needs_summary(Boolean, default True), last_summarized_ts(Text, nullable), last_summarized_ts_epoch(Float, nullable), updated_at(DateTime tz, server_default=now, onupdate=now).
- 제약/인덱스: UNIQUE(channel_id, thread_ts) `uq_threads_channel_threadts`; 인덱스 `ix_threads_channel_updated_at`(channel_id, updated_at), `ix_threads_channel_thread_ts_epoch`(channel_id, thread_ts_epoch).

### thread_summaries (ThreadSummary)
- 컬럼: id(PK Integer), channel_id(Text), thread_ts(Text), summary_json(JSONB/JSON), model(Text), source_latest_ts(Text), source_latest_ts_epoch(Float), created_at/updated_at(DateTime tz, server_default=now, onupdate=now via mixin).
- 제약/인덱스: UNIQUE(channel_id, thread_ts) `uq_thread_summaries_channel_threadts`; 인덱스 `ix_thread_summaries_channel_updated_at`(channel_id, updated_at).

### thread_reports (ThreadReport)
- 컬럼: id(PK Integer), channel_id(Text), thread_ts(Text), report_json(JSONB/JSON), model(Text), source_latest_ts(Text), source_latest_ts_epoch(Float), updated_at(DateTime tz, server_default=now, onupdate=now).
- 제약/인덱스: UNIQUE(channel_id, thread_ts) `uq_thread_reports_channel_threadts`; 인덱스 `ix_thread_reports_channel_updated_at`(channel_id, updated_at).

### daily_reports (DailyReport)
- 컬럼: id(PK Integer), report_date(Date), channel_id(Text, NOT NULL), payload_json(JSONB/JSON), model(Text), created_at(DateTime tz, server_default=now).
- 제약: UNIQUE(report_date, channel_id) `uq_daily_reports_date_channel`. 전체 리포트는 channel_id="__ALL__" 센티널 값 사용.

## 미구현/계획(Plan)
- 스키마 마이그레이션 도구는 없음(create_all만 사용). 변경 시 수동 마이그레이션 필요.
