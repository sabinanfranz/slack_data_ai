> 이 문서는 Slack Digest Admin 프로젝트의 컨텍스트 전달용입니다.
> 대상: 외부 LLM/개발 에이전트, 신규 합류 개발자
> 업데이트 기준: 2025-12-24 / 구현 범위: Step 1~11 (현재 코드 기준)

# Channels UI

## 현재 구현(Fact)
- 템플릿: `app/templates/channels.html`, 스크립트: `app/static/js/channels.js`.
- 화면 구성: 채널 추가 폼(input+버튼), 등록된 채널 테이블(channel_id, name, active, last_ts, last_ingested_at, created_at, action).
- 동작 흐름:
  - 페이지 로드 → `loadChannels()` → `GET /api/channels` → 테이블 렌더.
  - Add 버튼 → `POST /api/channels` → 성공 시 입력 초기화 후 재조회.
  - 토글 버튼 → `PATCH /api/channels/{id}` → 성공 시 재조회.
  - Ingest Now 버튼 → `POST /api/channels/{id}/ingest` → running 상태 표시 후 ingest-status 폴링(채널 재조회).
  - 채널 row 클릭 → `/threads?channel_id=...` 이동 후 해당 채널 스레드 즉시 로드.
- 표시 규칙: name이 null이면 `-`; last_ts는 문자열 그대로 노출(신규 등록 시 KST now-14일 epoch 문자열로 초기화).
- 에러 처리: API 실패 시 `#channelsError` 박스에 detail 메시지 표시, 성공 시 숨김.

## 미구현/계획(Plan)
- 채널 이름/메타데이터 실시간 갱신(UI 상 별도 새로고침 버튼 없음).
- 입력 검증/UX 향상(엔터키 제출, 로딩 상태 등) 미구현.
- Ingest 상태 표시/스피너는 기본 수준(세밀한 진행률 미구현), running stuck 복구는 수동 재시도 필요.

# Thread Reports UI (신규)

## 현재 구현(Fact)
- 템플릿: `app/templates/thread_reports.html`, 스크립트: `app/static/js/thread_reports.js`.
- 메뉴: `/thread-reports` (네비게이션 추가됨).
- 화면 구성: 상단 채널 드롭다운+새로고침 버튼, 좌측 스레드 목록, 우측 리포트 상세(주제/역할/일별 진척).
- 데이터 플로우:
  - 채널 로드: `GET /api/thread-reports/channels` → 드롭다운.
  - 스레드 목록: `GET /api/thread-reports?channel_id=...&limit=200` → root 텍스트/one_line/reply_count/updated_at/리포트 여부 표시.
  - 리포트 조회: `GET /api/thread-reports/{channel_id}/{thread_ts}` → LLM 생성 리포트 렌더. 없으면 안내 메시지.
  - 리포트 강제 생성/갱신: 우측 “즉시 생성/새로고침” 버튼 → `POST /api/thread-reports/{channel_id}/{thread_ts}/refresh?force=true` 호출 후 즉시 렌더.
- UX: 첫 스레드를 자동 선택해 로드, 로딩/에러 시 상단 에러 박스 표시.

## 미구현/계획(Plan)
- 로딩 스피너/페이징/검색 등 UX 보강 미구현.
