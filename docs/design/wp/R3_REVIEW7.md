# R3 7차 리뷰 (main 76ff439, 계약 2026-10-09.11) — 새 critical 1 / major 8 / minor 24

6차 항목: critical 2 모두 부분(C1 할인 변형 누출 → K1, C2 서랍 1,404개 불변이나 시나리오 A–D KPI 서랍 404 → M1). major 5 = 해결 1(N-M2)·부분 4(N-M1→M4, N-M3→M5·M2·m1, N-M4→M6·m2, N-M5→M3). minor 28 = 해결 22·부분 5(9→m5, 12→m2·m3, 14→m4, 19→m13, 27→m24)·수용 1(16, D11-4). 6차 RA 부분 4건 모두 아직 부분.

실행: pytest `-m "not live"` 3264 passed(부하, 1200s, 실패 0), mypy 164 files 0, ruff·format(412) 통과, gen·fixtures --check exit 0, regress T01–T18 PASS·fixtures_contract 647·e2e 흐름 3/3, 프론트 typecheck·lint 0, vitest 623/623, build, audit 0, e2e 45+20(T16 3회 중앙값 p50 16.7ms·p95 33.3ms — 기준 34ms까지 0.7ms), e2e:api 27. D14-5 성능 10회 중 9 통과(실패 1회는 동시 pytest 회차, basetemp 충돌 추정), 잡 13.8s·13.9s, API 쓰기 최대 0.543s·0.564s, 저장본 쓰기 잠금 최대 0.069s, 5,418행·11.9MB. 재현: scratchpad `r7/a`(저장본·backfill), `b`(할인·checked_at·redact), `c`(보고서·발행·이월), `d`(FE), `m`(직접 검증).

## Critical
- **K1 조건부·비할인 금액이 아직 '확인됨'으로 구매가에서 빠짐** (C1 부분, D14-2 위반, WP2) `normalize/notice_parser.py:819-859`(줄 단위 `_line_spans`), `:758` `_CONDITIONAL_RE`(금지 낱말 목록). `confirmed=True`: 다음 줄 조건 `'84A 분양가 할인 10,000,000원\n(1~3층에 한함)'`, `(일부 세대)`, `(계약자에 한하여)`, `(신혼부부)`, `(1F~3F)`, `(2026.10.31.)`, `… 예정`, 범위 `10,000,000원 ~ 30,000,000원`(하한), `'84A 분양가 할인 0원, 경품 10,000,000원'` → (10000000, 확인됨). 퍼징 50건+. `price_view.py:211` 전 경로 차감.

## Major
- **M1 시나리오 A–D 대시보드 KPI 출처 서랍 발행 리비전 404** (C2 부분, D14-1, WP0·WP5) `snapshot_view.py:557-562`(정규식 `:505`) — 시나리오 patch 행 prov `{"$v":"st_2"}` 모양이 수집에서 빠짐(st_2–5, st_12–15 404).
- **M2 backfill 중간 중단 시 시나리오 A–D 영구 404** (D14-9, WP0) `snapshot_view.py:267-276` `kind_ready`, `:941-964`, `:977` `pending_count`가 "그 종류 행 하나라도 있으면 완료" — 재실행해도 404, `POST /reports` 422, `pending_count: 0`.
- **M3 다른 리비전의 재판정 성공이 이월 대상 단지를 가림** (N-M5 부분, D14-7, WP7) `scheduler/handlers.py:79-85,113-121` — 미발행 리비전 R의 rejudge done을 판정으로 침, prev 점수 복사 → 사건 이전 점수가 새 기준일로 발행.
- **M4 사용자 시나리오 보고서 §12 12-1 순위표·TOP 5가 비교 기준의 기본 시나리오 값과 섞임** (N-M1 부분, D14-3, WP8) `reports/data.py:2128-2139` → `_extra` `:2232-2250` — "12위 → 1위".
- **M5 발행 계산 중 들어온 호재 PATCH가 발행에서 빠지고 잡 없음** (N-M3 부분, D14-5, WP7·WP5) `scheduler/snapshots.py:157` `republish` — `PATCH2 202 job_id None`, queued 0.
- **M6 `checked_at` 0001년 + 양수 오프셋 → 201 뒤 지역 목록·CSV 404** (N-M4 부분, D14-6, WP5·WP0) `core/time.py:72` OverflowError 미처리, `demotion.py:571`.
- **M7 FE 503 `materialize_pending` 재시도 동안 이전 리비전·시나리오 값이 새 리비전 헤더 아래 보임** (WP6) `api/hooks.ts:335,361,581`(`keepPreviousData`), `_shared/index.tsx:98`, `retryPolicy.ts:10` — 최대 약 20분.
- **M8 FE G5 '이후' 열 출처 404** (퇴행, WP6) `pages/scenario/index.tsx:668-678` — 새 리비전 Fact를 `AppLayout.tsx:27`의 옛 발행 리비전으로 조회.

## Minor
1 `snapshot_view.py:825-826,840-845` 정리 DELETE 상태 조건 없음 → 동시 두 번 발행 시 published 0행·backfill이 지금 값으로 재계산(WP0). 2 소문자 `t`/`z` checked_at이 형식 통과 후 `kst_date` None → UTC 날짜(`demotion.py:545,717`, `resolver.py:134`)(WP5·WP0). 3 `reports/data.py:178,1786` 접수 `checked_at[:10]` UTC 표시(WP8). 4 `snapshot_view.py:931` → `demotion.py:759` m14 이전 시 `snapshot_id=None` critical 이벤트·rejudge 없음(D13-5)(WP5·WP0). 5 `redact.py` 이중 인코딩 JSON·소문자/변형 PEM·공백 키 이름·전각 콜론·여러 단어 값(WP0). 6 `complexes.py:746-761` snapshot_id 생략 + 최신 발행 저장본 없음 → 503 대신 실시간 200(WP5). 7 `rd_` 저장본 없음(`snapshot_view.py:505-511`), FE가 `rd_` 전부 snapshot_id 뺌(`hooks.ts:484-489`) → `data_freshness`·생활권 세대수 `rd_`도 리비전 없이(WP6·WP0). 8 `snapshot_view.py:175` `_diff` `!=`로 `1`·`1.0`·`true` 같음(WP0). 9 `snapshot_view.py:204` 계약 버전 완전 일치 → 모양 안 바뀐 계약 변경에도 발행 GET 500, backfill 자기 복구 없음(WP0). 10 `reports.py:76-95` 기본 시나리오 POST·비교 스냅샷 저장본 준비 미검사 → 202 뒤 실패(WP5). 11 `snapshot_view.py:941-960` backfill 한 리비전 예외로 전체 중단(추정)(WP0). 12 `reports/data.py:675-683` 보고서 출처 누락이 `missing_provenance` 미집계(WP8). 13 `handlers.py:191-194,329-333,532-534` expand·daily 이월·주간 마감 발행 실패 재시도 없음(WP7). 14 시나리오 지정 rejudge 성공이 다른 시나리오까지 '판정됨'(WP7). 15 `reports/cli.py:38-45` `--compare` 순서 미검사(WP8). 16 `catalysts.py:169` POST /catalysts 응답 `job_id` 없음(WP5). 17 FE `ProvenancePanel.tsx:364-373` 연 채 리비전 바뀌면 404(WP6). 18 FE `hooks.ts:365-372`, `complexes/index.tsx:123` G2 503 '준비 중'·다시 시도 없음(WP6). 19 FE `JobProgress.tsx:121-146` rejudge·expand done을 발행 완료로 봄, `publish_blocked` 미안내(WP6). 20 FE `HumanCheckForm.tsx:242` 422 구분을 클라이언트 시계로(WP6). 21 FE `jobWatch.ts:180-188` 30분 상한 도달 시 조용히 멈춤(WP6). 22 FE `reports/index.tsx:109,121-127,153` 지역 변경 시 `create.error`·`jobId` 잔존(WP6). 23 FE `retryPolicy.ts` `stored_view_mismatch` 1회 재시도·Retry-After 30초 절단, 추천 리비전 버튼 숨김(추정)(WP6). 24 불변 테스트가 서랍 id를 기본 시나리오에서만 수집, `test_r3f_perf_publish.py:72` 이름 `under_15s` ↔ 30s(WP5·WP9).

## RA 대비 누락·부분
- 누락 0.
- 부분: §6-1/D11-6/D14-2 할인(K1); §7-1 G1·G3 ProvenancePanel·규칙 5(M1·M8); §8 WP8 사용자 시나리오 §12(M4); §10 이월·미처리 rejudge(M3)·발행 잡 누락(M5); D14-9 backfill(M2); D14-6 checked_at 범위(M6).
- 수용: G7 배지 즉시 갱신(D11-1·D13-1), G8 html·pdf(D4), T13 저장본 라벨(D14-8), §10 rawdata 압축(runbook 수동), T16 발행 비용(D14-5 30s), m16 잔여 일정(D11-4).
- AGENTS 규칙 4·12·15 위반 없음, 6·13은 redact m5.
