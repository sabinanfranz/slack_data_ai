> 이 문서는 Slack Digest Admin 프로젝트의 컨텍스트 전달용입니다.
> 대상: 외부 LLM/개발 에이전트, 신규 합류 개발자
> 업데이트 기준: 2025-12-24 / 구현 범위: Step 1~11 (현재 코드 기준)

# 코딩 컨벤션

## 현재 구현(Fact)
- 라우터 구조: 페이지 라우터 `app/routers/pages.py`, API 라우터 `api_channels.py`/`api_threads.py`/`api_stats.py` 모두 prefix `/api` 사용.
- DB 세션: `app/db.py`의 `get_db()` dependency generator 사용, 세션 종료는 finally에서 close. 수동 세션은 `get_session_factory()` 후 `with SessionLocal()` 패턴.
- 시간 처리: 기본 TZ는 `settings.tz`(Asia/Seoul). KST epoch 계산 → `.timestamp()`, stats는 Postgres `timezone(to_timestamp(...))` 활용.
- Slack 클라이언트: `SlackClient._call_with_retry` 재시도 + rate limit 대기, `not_in_channel` 시 join 재시도 후 계속.
- Upsert 패턴: SQLAlchemy `insert(...).on_conflict_do_*` (messages/threads/thread_summaries/daily_reports).
- 오류 응답: FastAPI `HTTPException(detail=...)` 형태로 반환, 프론트 JS는 `detail` 우선 노출.
- 프론트 JS: `apiJson()`에서 JSON 파싱 후 `res.ok` 확인, 에러는 throw → 상단 에러 박스에 표시. 날짜 포맷은 `toLocaleString` 사용.

## 미구현/계획(Plan)
- 테스트/린트 규칙, 코드 포맷터 설정 없음(수동 점검 필요).
- 인증/권한, rate-limit/SLI 모니터링 컨벤션 미정.
