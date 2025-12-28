> 이 문서는 Slack Digest Admin 프로젝트의 컨텍스트 전달용입니다.
> 대상: 외부 LLM/개발 에이전트, 신규 합류 개발자
> 업데이트 기준: 2025-12-24 / 구현 범위: Step 1~11 (현재 코드 기준)

# 다음 단계 계획 (Step 4~11)

## 현재 구현(Fact)
- Step 1~11 기능이 코드에 모두 존재하며 수동 실행/테스트로 확인 가능.

## 미구현/계획(Plan)
- Step4 Slack 연동: Slack 오류/재시도 로그를 구조화하고, join 실패 사유를 API 응답/로그에 노출(`app/slack_client.py`, `app/routers/api_channels.py`).
- Step5/6 Ingest: 폴링 결과 메트릭(수집 건수/오류)과 rate-limit 이벤트를 로깅하거나 DB에 적재하는 보조 테이블 추가 검토(`app/services/ingest_service.py`, `app/jobs/ingest.py`).
- Step6 Replies: 회전 폴링은 구현됨. 장기 미활성 스레드나 SQLite 환경에서도 동작하도록 lookback/DB 함수 분기 옵션 추가.
- Step7 Text render: 주요 케이스(멘션/채널/링크/코드) 단위 테스트 추가, Slack mrkdwn 변형 케이스 확장(`app/text_render.py`).
- Step8 Threads UI: 목록/타임라인에 페이지네이션·검색·로딩 표시 추가, 에러 메시지 UX 개선(`app/static/js/threads.js`, 템플릿).
- Step9 Stats: SQLite 호환 분기(파이썬 측 KST 변환) 및 간단한 쿼리 캐싱/메트릭 추가 검토(`app/services/stats_service.py`, `app/static/js/stats.js`).
- Step10 LLM: 오류/timeout 시 재시도 정책과 품질 로깅 추가, OpenAI 모델/토큰 검증 스크립트 마련(`app/llm_client.py`, `app/jobs/daily_report.py`).
- Step11 운영: ingest/report 주기 실행을 위한 cron/워크플로 구성(Railway cron, GitHub Actions 등)과 `.env`/Secret 관리 가이드 추가(`scripts/*.sh`, README/Runbook).
