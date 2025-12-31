> 이 문서는 Slack Digest Admin 프로젝트의 컨텍스트 전달용입니다.
> 대상: 외부 LLM/개발 에이전트, 신규 합류 개발자
> 업데이트 기준: 2025-12-24 / 구현 범위: Step 1~11 (현재 코드 기준)

# 용어집

## 현재 구현(Fact)
- channel_id: Slack 채널 고유 ID (예: C0123456789).
- ts: Slack 메시지 timestamp 문자열(예: "1700000000.0").
- thread_ts: 스레드 루트 메시지 ts (루트 메시지도 thread_ts=ts로 저장).
- last_ts / last_ts_epoch: 채널 수집 시작 기준(ts 문자열/float). 신규 채널은 KST now-14일로 초기화.
- last_ingested_at: 채널 최근 수집 시각(DateTime tz).
- reply_count: 루트 메시지의 Slack reply_count 값.
- needs_summary: 스레드 요약 필요 여부 플래그(threads.needs_summary).
- text_html: Slack 텍스트를 `app/text_render.py`로 변환한 안전한 HTML.
- one_line: thread_summaries.summary_json.one_line 값(스레드 리스트에서 사용).
- daily_reports.channel_id="__ALL__": 모든 채널 리포트에 대한 센티널 값.
- thread_summaries: 스레드 요약 JSON을 저장하는 테이블(LLM ThreadSummaryOut).
- thread_reports: 스레드 전체를 주제/참석자 역할/일별 진척으로 분석한 리포트 JSON 테이블(LLM ThreadReportOut).
- TZ: 기본 Asia/Seoul, KST 변환에 사용.

## 미구현/계획(Plan)
- 추가 용어 정의 필요 없음. 새로운 도메인 개념 추가 시 갱신.
