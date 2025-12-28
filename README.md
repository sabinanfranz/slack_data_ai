# Slack Digest Admin (scaffold)

## Run (local)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

* http://127.0.0.1:8000/healthz
* http://127.0.0.1:8000/channels
* http://127.0.0.1:8000/threads
* http://127.0.0.1:8000/stats

## Local Postgres (docker)
```bash
docker run --name slack-digest-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16
# create db (optional)
# docker exec -it slack-digest-db psql -U postgres -c "CREATE DATABASE slack_digest;"
```

## Env
```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/slack_digest
```

## Verify
* Start server: `uvicorn app.main:app --reload`
* Check: `GET /healthz` should return `{ "ok": true, "db": true }`
* Script: `REQUIRE_DB=true ./scripts/healthz_check.sh`

## Slack Setup
- Bot token is required: `SLACK_BOT_TOKEN=xoxb-...`
- Required scopes: `channels:read`, `channels:join`, `channels:history`, `users:read`
- Test: start server, add a channel_id in `/channels`, and verify the name is populated
- Check DB: `users_cache` should include the channel creator when available

## Ingest (history + replies)
환경변수:
- DATABASE_URL
- SLACK_BOT_TOKEN

실행:
```bash
python -m app.jobs.ingest
```

결과:
- messages / threads 테이블에 데이터가 쌓이고,
- channels.last_ts / channels.last_ingested_at 이 갱신됩니다.

### Replies polling
`MAX_THREADS_POLL_PER_RUN` (default 300): 한 번 실행에서 채널당 replies를 폴링할 스레드 수 상한

## Slack text render test
서버 실행:
```bash
uvicorn app.main:app --reload
```

렌더링 테스트:
```bash
curl -s -X POST http://127.0.0.1:8000/api/utils/render \\
  -H "Content-Type: application/json" \\
  -d '{"text":"Hello <@U123> <!here> <#C123|general> <https://example.com|link> `code`","user_map":{"U123":"Alice"}}' | jq
```

기대:
- @Alice / @here / #general 표시
- 링크는 `<a href="https://example.com" ...>link</a>`
- `<script>` 같은 입력은 실행되지 않고 제거/이스케이프됨

## View threads
1) 채널을 Channels 페이지에서 추가
2) ingest 실행:
```bash
python -m app.jobs.ingest
```
3) Threads 페이지에서 채널 선택 → 스레드 클릭 → 타임라인 확인

## Stats
1) 먼저 ingest로 데이터 적재:
```bash
python -m app.jobs.ingest
```
2) 웹에서 `/stats` 접속 → 채널 선택 → days/top_n 설정 → 조회

- 지표는 KST(Asia/Seoul) 날짜 기준으로 집계됩니다.
- Threads 수는 “기간 내 활동한 thread_ts distinct” 기준입니다.

## LLM summaries & daily reports

### 1) Thread summaries (자동)
데일리 리포트 job이 필요한 스레드의 요약을 자동으로 생성/업데이트합니다.

### 2) Daily report 생성 (DB 저장)
```bash
# 기본: 어제(KST)
python -m app.jobs.daily_report

# 특정 날짜(KST)
python -m app.jobs.daily_report --date 2025-12-22
```

결과:
- thread_summaries 테이블에 스레드 요약 JSON 저장
- daily_reports 테이블에 채널별/전체(\"__ALL__\") 리포트 JSON 저장

## Deploy to Railway (Runbook)

이 프로젝트는 Railway에서 3개 서비스를 운영합니다.

- web: 관리자 UI (상시 실행)
- ingest-cron: Slack 수집 (매시간)
- report-cron: LLM 요약 + daily_reports 생성 (매일 1회)

### 0) 중요한 전제
- Railway cron schedule은 UTC 기준입니다.
- Cron job은 실행 후 프로세스가 종료되어야 하며, 종료되지 않으면 다음 스케줄이 스킵될 수 있습니다.

### 1) Railway 프로젝트 생성 + Postgres 추가
1. Railway에서 새 Project 생성
2. Add Service → PostgreSQL 추가
3. Postgres 서비스가 제공하는 DATABASE_URL을 web/cron 서비스에 연결합니다.
   - DATABASE_URL은 Postgres 서비스 변수로 제공됩니다.

### 2) Shared Variables (권장)
Project Settings → Shared Variables에서 아래를 만들고, web/ingest-cron/report-cron 서비스에 모두 공유하세요.

- SLACK_BOT_TOKEN
- OPENAI_API_KEY
- OPENAI_MODEL (예: gpt-4o-mini)
- TZ=Asia/Seoul
- (옵션) MAX_THREADS_POLL_PER_RUN, MAX_MESSAGES_PER_THREAD_FOR_SUMMARY, MAX_THREADS_PER_DAILY_REPORT, SUMMARY_LANGUAGE

### 3) web 서비스 생성
1. GitHub repo에서 Deploy (또는 Railway CLI로 railway up)
2. Service Settings:
   - Start Command: `bash scripts/start_web.sh`
   - Healthcheck Path: `/healthz`
3. Networking:
   - Generate Domain (기본은 public URL이 없을 수 있음)

### 4) ingest-cron 서비스 생성
1. web 서비스를 Duplicate(복제)해서 만들면 변수/소스 설정이 편합니다.
2. Service Settings:
   - Start Command: `bash scripts/run_ingest.sh`
   - Cron Schedule(UTC): `0 * * * *`

### 5) report-cron 서비스 생성
1. ingest-cron을 Duplicate해서 만들면 편합니다.
2. Service Settings:
   - Start Command: `bash scripts/run_daily_report.sh`
   - Cron Schedule(UTC): `10 15 * * *`  # KST 00:10

### 6) 운영 확인
- web: /healthz 확인
- channels에서 채널 추가 후 ingest-cron 로그에서 수집이 진행되는지 확인
- report-cron 로그에서 daily_reports가 생성되는지 확인

### 로컬 실행 권한
```bash
chmod +x scripts/*.sh
```

## Docs
- docs/00_overview.md
- docs/02_runbook_local.md
- docs/05_api_contract.md
