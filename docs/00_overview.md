> 이 문서는 Slack Digest Admin 프로젝트의 컨텍스트 전달용입니다.
> 대상: 외부 LLM/개발 에이전트, 신규 합류 개발자
> 업데이트 기준: 2025-12-24 / 구현 범위: Step 1~11 (현재 코드 기준)

# 개요

## 현재 구현(Fact)
- 프로젝트 한 줄 소개: Slack 채널 메시지를 수집·요약하는 관리자 웹앱 + 배치 잡.
- 제공 UI: `/channels`(채널 CRUD/토글), `/threads`(스레드 목록+타임라인), `/stats`(통계), `/thread-reports`(스레드 리포트 조회). 템플릿 `app/templates/*`, JS `app/static/js/*`.
- API: Channels `GET/POST/PATCH /api/channels`, Threads `GET /api/channels/{channel_id}/threads`, `GET /api/channels/{channel_id}/threads/{thread_ts}`, Stats `GET /api/channels/{channel_id}/stats`, Utils `POST /api/utils/render`, Thread Reports `GET /api/thread-reports*`, `POST /api/thread-reports/{channel_id}/{thread_ts}/refresh`.
- 수집/요약 파이프라인: `python -m app.jobs.ingest`(history+replies upsert), `python -m app.jobs.daily_report`(thread_summaries/daily_reports upsert, OpenAI 필요), `python -m app.jobs.thread_reports`(thread_reports upsert, OpenAI 필요).
- 배포/실행 스크립트: `scripts/start_web.sh`, `scripts/run_ingest.sh`, `scripts/run_daily_report.sh`. Postgres 기준으로 동작(Stats는 Postgres 시간 함수 의존).

## 미구현/계획(Plan)
- Stats를 SQLite에서도 동작하도록 타임존 계산 분기 추가 필요.
- ingest/report 자동 스케줄링은 외부 크론/서비스 구성 필요(코드에는 수동 실행만 존재).
- 운영/관리 기능: 인증/권한, 모니터링, 알림은 없음.
- 테스트/검증 스크립트 미비(수동 curl/페이지 확인에 의존).
- README/Runbook에 Railway 외 배포 옵션(AWS 등) 추가 가능성.
- Thread Reports 기능 품질/UX 보강(리트라이/로깅/캐싱 등) 필요.
