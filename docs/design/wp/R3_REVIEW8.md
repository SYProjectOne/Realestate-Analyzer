# R3 8차 리뷰 (main cbc31c1, 계약 2026-10-09.12) — 새 critical 1 / major 5 / minor 21

7차 항목: K1 부분(7차 문구 10건은 막힘, 새 꼴 누출 → N-C1). major 8 = 해결 5(M3·M4·M6·M7·M8)·부분 3(M1 0012 이전 리비전 → N-M1, M2 마이그레이션 추정 구멍 → N-M2·m3, M5 다중 worker·위치/예정월 PATCH → N-M3·N-M4). minor 24 = 해결 18·부분 6(5→m15, 7→N-M1, 10→m12, 19→m16, 20→m17, 24→m20).

테스트 유효성(수정 전 5746ba0 대비): `test_r3g_core5.py` 31건 중 28 실패(결함 잡음)·3 통과. 새 API 의존으로만 실패하던 13건은 새 API 없이 재현하도록 고쳐 수정 전 코드에서 13건 모두 실패 확인(`scratchpad/r8/m/test_r8_core5_adapt.py`). 결함을 못 잡는 테스트: `test_flip_transaction_takes_write_lock_first`(m21). `test_r3g_k1_discount` 185건 중 111 수정 전 실패, 단 속성 테스트 오라클이 구현과 같은 금지어 방식(m2).

실행: pytest 3621 passed(부하, 1424s), mypy 164 0, ruff·format(419) 통과, gen·fixtures --check exit 0, regress 715 passed·T01–T18 PASS·e2e 흐름 3/3, vitest 655/655, build, audit 0, e2e 45+20(T16 p50 16.7·p95 16.8ms), e2e:api 27. 재현: scratchpad `r8/a`(할인), `b`(저장본·마이그레이션·single-flight·WAL), `c`(이월·후속 잡·보고서·시각·redact), `m`(테스트 유효성).

## Critical
- **N-C1 조건부 할인이 아직 '확인됨'으로 차감** (K1 부분, D15-1, WP2) `normalize/notice_parser.py:776-793` `_next_line_conditional`, `:871-875` — 허용 목록이 줄 하나에만, 문맥은 다음 첫 줄 + 금지어. (a) 타입 나열 뒤 공통 각주 `'84A …원\n59B …원\n(1~3층에 한함)'` → 84A 확인됨, (b) 목록 밖 조건(`무주택자만 적용`, `할부 시 미적용`, `법인 불가`, `타입별 상이`…), (c) 앞 줄·머리줄 조건(`[1~3층 한정]\n84A …`), (d) 떨어진 각주(`■ 유의사항\n※ 상기 할인은 1~3층`). 500,000,000 → 490,000,000 차감. 실제 녹화 공고 59건에는 할인 줄 0건.

## Major
- **N-M1 0012 이전 발행 리비전 출처 서랍이 .11 범위 그대로** (M1·m7 부분, WP0) `0012_r3g.py:107-150`, `snapshot_view.py:1409-1411` — 색인 묶음 수만 맞으면 done → backfill이 넓힌 범위로 다시 안 씀. 업그레이드 뒤 non-200 60건(`rd_` 56, `st_2`–`st_5`). FE가 `rd_`에도 snapshot_id를 넘기므로 .11에서 200이던 서랍이 404.
- **N-M2 '시나리오 사이 최대 행 수' 추정이 일부만 써진 기본 시나리오 단위를 done으로** (M2 부분, WP0) `0012_r3g.py:111-116,140-148` — 16 중 8만 남은 DB → `done=1,rows=8`, `pending_count 0`, `GET /api/complexes/9?snapshot=12&scenario=base` 영구 404.
- **N-M3 worker 2개 이상에서 발행 계산 중 변경 누락·재시도 없음** (M5 부분, D15-6·F12, WP7·WP0) `handlers.py:441-444,482-491,503-522`, `snapshot_view.py:1270-1284` — 후속 잡이 busy면 `failed publish_in_progress`, 먼저 돈 발행 `followups_included []`.
- **N-M4 `PATCH /catalysts`에서 예정월·좌표만 바꾸면 발행 잡 없음** (WP5) `catalysts.py:272` — `202 job_id None`, 발행 상세 옛 값.
- **N-M5 `docs/runbook.md:327-330` 할인 설명이 D14-2 금지어 방식, 0012 뒤 서랍 범위 안내 없음** (WP0).

## Minor
1 `notice_parser.py:771-774` 무조건 할인이 흔한 머리줄 다음이면 '추정' 과강등(WP2). 2 `test_r3g_k1_discount.py` 오라클이 구현과 같은 금지어 방식, 생성기가 앞 줄·3줄 블록·목록 밖 조건 미생성(WP2·WP9). 3 `snapshot_view.py:382-395,1393-1394,1534` 행 있고 표식 없는 단위 영구 404, pending·backfill 둘 다 놓침(WP0). 4 `snapshot_view.py:1092,1219-1220,1231-1232,1285-1286` 임대 넘겨받은 뒤 이전 보유자 정리 DELETE에 임대 조건 없음(추정)(WP0). 5 `handlers.py:504`, `snapshot_view.py:1280` 그 자리 발행 holder `pid:` → 넘겨받기 15분 TTL만, 포함된 후속 잡 `publish_job_id` null(F15)(WP7). 6 보고서 저장본 `sc_<component.id>`·`st_<total.id>`가 서랍 id 모양 아님(`sc_` 507·`st_` 52 서랍 없음, 일부 충돌)(WP8). 7 `handlers.py:146-147` 점수만 재계산 rejudge(`complex_ids=[]`) 실패가 이월 판단에 빠짐(WP7). 8 `handlers.py:179-181` 판정기 버전 변경 이벤트 무시(WP7). 9 `handlers.py:148` 판정 시각 기준 `finished_at` → 실행 중 이벤트를 판정됨으로(WP7). 10 `handlers.py:131-135` prev 포함을 리비전 키 비교로(WP7). 11 `ops.py:300` 다른 필드도 틀려도 `checked_at_*`, `kind` 틀리면 field_errors에서 checked_at 빠짐(F14)(WP5). 12 `reports.py:160-176` 비교 리비전 `report_diff` 준비 미검사(WP5). 13 `views.py:253`, `complexes.py:994` → FE `lib/format.ts:172`, `IntakeBadge.tsx:15` checked_at 앞 10자 UTC 날짜 표시(D15-7)(WP5·WP6). 14 `redact.py:116-120,161-167` 환경변수 꼴(`DATA_GO_KR_KEY=` 등), Cookie/Set-Cookie, 단독 JWT·소문자 bearer·Slack webhook, `password`, `api%5Fkey=`, 쌍 리스트, `key`·`auth`·`signature` 미가림(WP0). 15 설정된 비밀값의 base64·대문자·공백 변형 누출(WP0). 16 FE `jobWatch.ts:355-358` done + `publish_in_progress`를 '발행 막힘'으로 잠깐 표시, 사슬 6단계 상한 테스트 없음(WP6). 17 FE `HumanCheckForm.tsx:266-287` 여러 칸 오류 시 다른 칸 오류·detail 사라짐, 제출 전 검사(:95) 브라우저 시계(WP6). 18 FE `market/index.tsx:36-37` 지역 변경 시 `locResult`·잡 진행 잔존(WP6). 19 FE `jobWatch.ts:342,358` `publish_blocked: contradicted ${n}` 영문·미포맷 숫자(규칙 12)(WP6). 20 `test_r3e_invariant.py` 서랍 id 수집이 기본 시나리오·`prov` 문자열뿐(D15-2)(WP9·WP5). 21 `test_r3g_core5.py::test_flip_transaction_takes_write_lock_first` 수정 전에도 통과(WP0).

## RA 대비 누락·부분
- 누락 0.
- 부분: §6-1/D11-6/D15-1 할인(N-C1); §7-1 G3 서랍 0012 이전 리비전(N-M1); D14-9/D15-3 backfill·표식(N-M2, m3); §10 발행 잡 누락(N-M3·N-M4); D15-7 KST 표시(m13); 규칙 6·13 redact(m14·m15); 규칙 12(m19).
- 해결로 바뀜: §8 WP8 §12(M4), §10 이월(M3), D14-6 범위(M6), 503 placeholder(M7·M8).
- 수용(변동 없음): G7 배지 즉시 갱신, G8 html·pdf, T13 저장본 라벨, §10 rawdata 압축, T16 발행 비용, 잔여 일정.
- T1–T18 regress 전부 PASS. 규칙 4·15 위반 없음.
