> 이 문서는 Slack Digest Admin 프로젝트의 컨텍스트 전달용입니다.
> 대상: 외부 LLM/개발 에이전트, 신규 합류 개발자
> 업데이트 기준: 2025-12-24 / 구현 범위: Step 1~11 (현재 코드 기준)

# 아키텍처

## 현재 구현(Fact)
- 웹 서비스: FastAPI + Jinja2 (`app/main.py`, `app/routers/*`, `app/templates/*`, `app/static/*`), uvicorn 실행.
- 데이터 계층: SQLAlchemy 2.0 (`app/db.py`, `app/models.py`), Postgres 권장(JSONB, timezone 함수 사용). `init_db()`가 startup에서 create_all.
- Slack 연동: `app/slack_client.py`(재시도, not_in_channel 시 자동 재-join), 채널 생성·ingest에서 사용.
- 수집 잡: `app/jobs/ingest.py` → `app/services/ingest_service.py`로 history+replies 수집, messages/threads upsert, users_cache 업데이트.
- 요약/리포트 잡: `app/jobs/daily_report.py` → `app/services/summary_service.py` → OpenAI(Structured Outputs)로 thread_summaries/daily_reports upsert.
- 스레드 리포트 잡: `app/jobs/thread_reports.py` → `app/services/thread_report_service.py`로 thread_reports upsert(주제/역할/일별 진척), ThreadSummary를 컨텍스트로 활용.
- 배포/실행 스크립트: `scripts/start_web.sh`, `scripts/run_ingest.sh`, `scripts/run_daily_report.sh` (thread_reports는 수동 실행 스크립트 미제공, 직접 python -m 호출).
- 설정 로드: daily_report/thread_reports 실행 시 `python-dotenv`로 `.env`를 우선 로드(find_dotenv usecwd=True, override=False) 후 settings 사용.

### 데이터 흐름(현재)
```mermaid
flowchart LR
  UI[Web UI (/channels,/threads,/stats)] --> API[FastAPI /api]
  API --> DB[(Postgres/SQLAlchemy)]
  API --> Slack[Slack Web API]
  Ingest[app.jobs.ingest] --> Slack
  Ingest --> DB
  Render[POST /api/utils/render] --> Text[app/text_render.py]
  Daily[app.jobs.daily_report] --> LLM[OpenAI]
  ThreadRpt[app.jobs.thread_reports] --> LLM
  LLM --> DB
```

## 미구현/계획(Plan)
- Stats의 시간대 계산은 Postgres 함수에 의존 → SQLite 호환 분기 필요.
- 운영 편의: 인증/권한, 로깅/모니터링, 스케줄러(ingest/report 자동 실행)는 별도 인프라 필요.
- CI/테스트 파이프라인 및 마이그레이션 도구는 없음(수동 create_all).
- thread_reports용 실행 스크립트/크론 설정은 제공되지 않음(수동 실행 필요).
