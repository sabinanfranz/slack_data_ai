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
- 표시 규칙: name이 null이면 `-`; last_ts는 문자열 그대로 노출(신규 등록 시 KST now-14일 epoch 문자열로 초기화).
- 에러 처리: API 실패 시 `#channelsError` 박스에 detail 메시지 표시, 성공 시 숨김.

## 미구현/계획(Plan)
- 채널 이름/메타데이터 실시간 갱신(UI 상 별도 새로고침 버튼 없음).
- 입력 검증/UX 향상(엔터키 제출, 로딩 상태 등) 미구현.
