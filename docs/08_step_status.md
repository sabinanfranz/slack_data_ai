> 이 문서는 Slack Digest Admin 프로젝트의 컨텍스트 전달용입니다.
> 대상: 외부 LLM/개발 에이전트, 신규 합류 개발자
> 업데이트 기준: 2025-12-24 / 구현 범위: Step 1~11 (현재 코드 기준)

# 단계별 상태

## 현재 구현(Fact)
| Step | 상태 | 근거(파일/라우트) |
| --- | --- | --- |
| 1 | Done | `app/main.py` routes + templates/base UI skeleton, `/healthz` |
| 2 | Done | `app/db.py` init_db/get_db, `app/models.py` 테이블 정의/unique/index |
| 3 | Done | `app/routers/api_channels.py`, `app/static/js/channels.js`, last_ts -14일 초기화 |
| 4 | Done | `app/slack_client.py` conversations.info/join/users.info 래퍼, POST /api/channels 연동 |
| 5 | Done | `app/services/ingest_service.py` history upsert + channels.last_ts 전진, `app/jobs/ingest.py` |
| 6 | Done | replies 폴링(회전 offset), needs_summary 갱신, `ingest_single_thread_replies` |
| 7 | Done | Slack 텍스트 렌더러 `app/text_render.py`, API `POST /api/utils/render` |
| 8 | Done | Threads API/UI `app/routers/api_threads.py`, `app/static/js/threads.js` |
| 9 | Done | Stats API/UI `app/routers/api_stats.py`, `app/static/js/stats.js` (Postgres 시간 함수 의존) |
| 10 | Done | 요약/데일리 리포트 `app/services/summary_service.py`, `app/jobs/daily_report.py`, OpenAI Structured Outputs |
| 11 | Done | 실행 스크립트 `scripts/*.sh`, Runbook `README.md` |

## 미구현/계획(Plan)
- 단계별 추가 구현 없음. 개선 사항은 `docs/09_next_steps_step4_to_11.md` 참고.
