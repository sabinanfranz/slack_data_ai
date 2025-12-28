> 이 문서는 Slack Digest Admin 프로젝트의 컨텍스트 전달용입니다.
> 대상: 외부 LLM/개발 에이전트, 신규 합류 개발자
> 업데이트 기준: 2025-12-24 / 구현 범위: Step 1~11 (현재 코드 기준)

# 로컬 실행 가이드

## 현재 구현(Fact)
- 필수 소프트웨어: Python 3.11+.
- 설치 및 서버 실행:
  1) `python -m venv .venv`
  2) 활성화 (PowerShell) `./.venv/Scripts/Activate.ps1` / (bash) `source .venv/bin/activate`
  3) `pip install -r requirements.txt`
  4) `.env` 작성 (예시 아래) 후 `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- .env 예시 (Postgres 권장):
  ```env
  DATABASE_URL=postgresql://postgres:postgres@localhost:5432/slack_digest
  TZ=Asia/Seoul
  # SLACK_BOT_TOKEN=xoxb-your-token (채널 등록/ingest 시 필요)
  # OPENAI_API_KEY=sk-... (daily_report 시 필요)
  ```
  *SQLite도 가능하지만 `stats`는 Postgres 시간 함수(`timezone`) 의존으로 SQLite에서 에러 발생.*
- 로컬 Postgres(docker):
  ```bash
  docker run --name slack-digest-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16
  # (옵션) DB 생성: docker exec -it slack-digest-db psql -U postgres -c "CREATE DATABASE slack_digest;"
  ```
- 헬스체크: `curl -s http://127.0.0.1:8000/healthz` → `{ "ok": true, "db": true|false }`
- Channels CRUD 시나리오:
  - `/channels` 접속 → 채널 ID 입력 후 Add → Slack info 성공 시 name 저장, 실패 시 에러 메시지.
  - 토글 버튼 → `PATCH /api/channels/{id}` 로 활성/비활성.
- 데이터 적재/요약:
  - 수집: `python -m app.jobs.ingest` (Slack 토큰/DB 필요)
  - 데일리 리포트: `python -m app.jobs.daily_report` (Slack 데이터 + OpenAI 키 필요, .env를 자동 로드하며 OPENAI_API_KEY/DATABASE_URL 없으면 명확한 RuntimeError로 종료)
- 패키지: requirements.txt에 `openai>=1.55.0` 포함(Structured Outputs용).

## 미구현/계획(Plan)
- SQLite 환경에서 `stats` 호환 분기 추가 필요.
- 자동 스케줄링(daily/ingest) 및 배포용 docker-compose/infra 문서화는 없음.
