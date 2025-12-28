## 전체 구현 단계(세분화 버전)

1. **레포 스캐폴딩 + 3개 메뉴 UI 뼈대 + healthz** ✅ _(이번 답변에서 상세 지시문 제공)_
2. DB 연결/세션 + 모델(channels/messages/threads/users_cache/… 기본 틀) + create_all
3. Channels API(GET/POST/PATCH) + Channels 화면(테이블/추가/토글) + last_ts 14일 백필 규칙
4. Slack client 래퍼 + 채널 추가 시 join/info + users_cache(users.info) 기초 적재
5. Ingest Job A: conversations.history로 루트 수집 → messages/threads upsert + last_ts 전진
6. Ingest Job B: threads 대상으로 conversations.replies 증분 폴링 + needs_summary 플래그 갱신 + 레이트리밋/재시도
7. Slack 텍스트 렌더러: 멘션/채널태그/링크 변환 + XSS 안전(bleach) + API 응답에 text_html 포함
8. Threads API + Threads 화면: 채널 선택 → 스레드 리스트 → 클릭 시 타임라인 렌더
9. Stats API + Stats 화면: ①②③④⑤ 지표(KST 기준) + Top N
10. LLM 요약: thread_summaries 생성/업데이트 + daily_reports 생성(KST 날짜)
11. Railway 운영 패키징: 서비스 3개(web/ingest-cron/report-cron) 커맨드/cron/README 정리
