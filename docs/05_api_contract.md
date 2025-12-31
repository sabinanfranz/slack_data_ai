> 이 문서는 Slack Digest Admin 프로젝트의 컨텍스트 전달용입니다.
> 대상: 외부 LLM/개발 에이전트, 신규 합류 개발자
> 업데이트 기준: 2025-12-24 / 구현 범위: Step 1~11 (현재 코드 기준)

# API 계약 (Base: `/api`)
- 에러 형식: `{ "detail": "..." }`
- DB/Slack/OpenAI 의존: Postgres 권장(`stats`는 Postgres 시간 함수 사용), Slack 토큰/LLM 키 없으면 관련 엔드포인트/잡 실패.

## Channels

### GET /channels
- 목적: 채널 목록 조회(생성일 내림차순).
- 응답 예시:
```json
[
  {
    "channel_id": "C0750UMQAD6",
    "name": "general",
    "is_active": true,
    "last_ts": "1700000000.0",
    "last_ts_epoch": 1700000000.0,
    "last_ingested_at": "2025-12-23T03:00:00+00:00",
    "created_at": "2025-12-23T12:00:00+09:00",
    "updated_at": "2025-12-23T12:00:00+09:00"
  }
]
```
- curl: `curl -s http://127.0.0.1:8000/api/channels`

### POST /channels
- 목적: 채널 신규 등록 (Slack conversations.info 후 저장, join 시도, creator users.info 캐시).
- 요청 예시:
```json
{ "channel_id": "C0750UMQAD6" }
```
- 동작: channel_id 형식 검증 → Slack info 실패 시 400/502 → join best-effort → 기존 존재 시 이름만 갱신 후 기존 레코드 반환(멱등).
- 에러: 400(잘못된 ID 또는 Slack에서 channel_not_found/invalid_auth/not_authed/account_inactive), 500(SLACK_BOT_TOKEN 미설정), 502(Slack 기타 오류).
- curl:
```bash
curl -s -X POST http://127.0.0.1:8000/api/channels \
  -H 'Content-Type: application/json' \
  -d '{"channel_id":"C0750UMQAD6"}'
```

### PATCH /channels/{channel_id}
- 목적: 채널 활성/비활성 토글.
- 요청 예시: `{ "is_active": false }`
- 에러: 404(채널 없음).
- curl:
```bash
curl -s -X PATCH http://127.0.0.1:8000/api/channels/C0750UMQAD6 \
  -H 'Content-Type: application/json' \
  -d '{"is_active":false}'
```

### POST /channels/{channel_id}/ingest
- 목적: 단일 채널 Slack 수집을 웹에서 트리거(BackgroundTasks).
- 요청 예시: `{ "backfill_days": 14, "mode": "full" }` (mode: full | threads_only)
- 응답: `{ "status": "started", "channel_id": "...", "job_id": "..." }`
- 에러: 404(채널 없음), 400(비활성/SLACK_BOT_TOKEN 없음), 409(이미 running).
- curl:
```bash
curl -s -X POST http://127.0.0.1:8000/api/channels/C0750UMQAD6/ingest \
  -H 'Content-Type: application/json' \
  -d '{"backfill_days":14,"mode":"full"}'
```

### GET /channels/{channel_id}/ingest-status
- 목적: 채널 ingest 상태 조회.
- 응답 필드: ingest_status("idle|running|ok|error"), ingest_started_at, ingest_finished_at, ingest_error_message, ingest_last_result_json.
- 에러: 404(채널 없음).
- curl: `curl -s http://127.0.0.1:8000/api/channels/C0750UMQAD6/ingest-status`

## Threads

### GET /channels/{channel_id}/threads
- 목적: 채널의 스레드 목록 조회.
- 쿼리: `limit`(1~200, 기본 50), `offset`(0~100000, 기본 0).
- 응답 필드: channel_id, thread_ts, reply_count, root_text, updated_at, one_line(요약 존재 시).
- 에러: 404(채널 없음).
- curl: `curl -s "http://127.0.0.1:8000/api/channels/C0750UMQAD6/threads?limit=50&offset=0"`

### GET /channels/{channel_id}/threads/{thread_ts}
- 목적: 스레드 타임라인 조회(HTML 렌더 포함).
- 응답 필드: channel_id, thread_ts, reply_count, root_text, updated_at, messages[{ts, ts_epoch, user_id, author_name, text, text_html, is_root}].
- 에러: 404(채널 없음 또는 스레드 없음).
- curl: `curl -s "http://127.0.0.1:8000/api/channels/C0750UMQAD6/threads/1700000000.0"`

## Stats

### GET /channels/{channel_id}/stats
- 목적: 채널 메시지/스레드 통계(KST 기준). Postgres 시간 함수 의존.
- 쿼리: `days`(1~60, 기본 7), `top_n`(1~50, 기본 10).
- 응답 필드: channel_id, channel_name, days, top_n, start_date_kst, end_date_kst_exclusive, total_messages, total_threads, unique_users, daily_messages[{date_kst,message_count}], top_threads[{thread_ts,reply_count,root_text,updated_at}], top_users[{user_id,name,message_count}].
- 에러: 404(채널 없음).
- curl: `curl -s "http://127.0.0.1:8000/api/channels/C0750UMQAD6/stats?days=7&top_n=10"`

## Thread Reports

### GET /thread-reports/channels
- 목적: 활성 채널 목록(리포트 페이지용).
- 응답 필드: channel_id, name.
- curl: `curl -s http://127.0.0.1:8000/api/thread-reports/channels`

### GET /thread-reports
- 목적: 채널별 스레드 리스트(리포트 존재 여부 포함).
- 쿼리: `channel_id`(필수), `limit`(1~200, 기본 50).
- 응답 필드: channel_id, thread_ts, reply_count, updated_at, title(루트 메시지 앞부분), one_line(ThreadSummary one_line), has_report(boolean).
- 에러: 404(채널 없음).
- curl: `curl -s "http://127.0.0.1:8000/api/thread-reports?channel_id=C0750UMQAD6&limit=50"`

### GET /thread-reports/{channel_id}/{thread_ts}
- 목적: 단일 스레드 리포트 상세 조회.
- 응답 필드: channel_id, thread_ts, report_json(LLM 결과), model, source_latest_ts, source_latest_ts_epoch, updated_at, meta{latest_epoch, report_source_latest_ts_epoch, is_stale}.
- 에러: 404(리포트 없음/채널/스레드 없음).
- curl: `curl -s "http://127.0.0.1:8000/api/thread-reports/C0750UMQAD6/1700000000.0"`

### POST /thread-reports/{channel_id}/{thread_ts}/refresh
- 목적: 리포트 강제 생성/갱신(LLM 호출 필요).
- 쿼리/바디: force는 쿼리스트링 또는 기본값 False.
- 응답 필드: status, channel_id, thread_ts, report_json, model, source_latest_ts, source_latest_ts_epoch, updated_at, meta{latest_epoch, report_source_latest_ts_epoch, is_stale}.
- 에러: 404(채널/스레드 없음), 500(LLM 키/DB 오류 등).
- curl: `curl -s -X POST "http://127.0.0.1:8000/api/thread-reports/C0750UMQAD6/1700000000.0/refresh"`

## Utils

### POST /utils/render
- 목적: Slack 텍스트를 안전한 HTML로 변환(멘션/채널/링크/코드 처리 후 bleach sanitize).
- 요청 예시: `{ "text": "Hello <@U123> <!here> <#C123|general> <https://example.com|link> \`code\`", "user_map": {"U123": "Alice"} }`
- 응답 예시: `{ "text_html": "Hello @Alice @here #general <a href=\"https://example.com\" target=\"_blank\" rel=\"noopener noreferrer\">link</a> <code>code</code>" }`
- 에러: 일반 HTTPException(detail).
- curl:
```bash
curl -s -X POST http://127.0.0.1:8000/api/utils/render \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello <@U123> <!here> <#C123|general> <https://example.com|link> `code`","user_map":{"U123":"Alice"}}'
```
