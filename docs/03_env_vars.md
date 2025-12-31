> 이 문서는 Slack Digest Admin 프로젝트의 컨텍스트 전달용입니다.
> 대상: 외부 LLM/개발 에이전트, 신규 합류 개발자
> 업데이트 기준: 2025-12-24 / 구현 범위: Step 1~11 (현재 코드 기준)

# 환경변수

## 현재 사용(Fact)
| Env | 기본값 | 사용처 | 비고 |
| --- | --- | --- | --- |
| APP_ENV | local | `app/config.py` | 동작 분기 없음(정보용). |
| TZ | Asia/Seoul | `app/config.py`, 시간 계산 전역 | `stats`/요약/ingest/리포트에서 KST 변환. |
| DATABASE_URL | 없음 | `app/db.py`, `app/jobs/ingest.py`, `app/jobs/daily_report.py`, `app/jobs/thread_reports.py` | Postgres 권장(JSONB, timezone 함수). 없으면 DB 세션 생성 실패. |
| SLACK_BOT_TOKEN | 없음 | `app/slack_client.py`, `/api/channels` POST, ingest | 없으면 Slack 호출 시 500/에러 로그. |
| MAX_THREADS_POLL_PER_RUN | 300 | `app/services/ingest_service.py` | replies 폴링 대상 스레드 상한(회전 방식). |
| OPENAI_API_KEY | 없음 | `app/llm_client.py`, `app/jobs/daily_report.py`, `app/jobs/thread_reports.py` | 없으면 실행 시 RuntimeError. |
| OPENAI_MODEL | gpt-4o-mini | `app/config.py`, 요약/리포트 | Structured Outputs 모델명. |
| MAX_MESSAGES_PER_THREAD_FOR_SUMMARY | 80 | `app/services/summary_service.py` | 요약 입력 메시지 수 상한. |
| MAX_MESSAGES_PER_THREAD_FOR_REPORT | 200 | `app/services/thread_report_service.py` | 스레드 리포트 입력 메시지 수 상한. |
| SUMMARY_LANGUAGE | ko | `app/services/summary_service.py`, `app/jobs/daily_report.py`, `app/services/thread_report_service.py` | 요약/리포트 언어. |
| MAX_THREADS_PER_DAILY_REPORT | 60 | `app/jobs/daily_report.py` | 채널별 리포트에 포함할 최대 스레드 수. |
| .env 로드 | - | `app/jobs/daily_report.py`, `app/jobs/thread_reports.py` | `python-dotenv`로 `find_dotenv(filename=".env", usecwd=True)` 호출 후 load(override=False). 환경변수가 우선. |

## 미구현/계획(Plan)
- 추가 환경변수 계획 없음. 필요 시 코드 반영 후 문서 갱신.
