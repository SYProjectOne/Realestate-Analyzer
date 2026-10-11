# R3 9차 리뷰 (main 9102cf8, 계약 2026-10-09.13) — 새 critical 0 / major 4 / minor 19

8차 항목: N-C1 해결(파서·0013·devseed·픽스처·API 어느 경로도 파서 할인 '확인됨' 0건). N-M1·N-M2·N-M3·N-M4 해결(잔여는 새 major 1·2·3, m8), N-M5 부분(m7). minor 21 = 해결 17·부분 3(6→m5, 11→m10, 12→m9)·흡수 1(1·2는 D16-1로 소멸). m21 테스트는 잠금 UPDATE를 지운 변이 코드에서 실패 확인(docstring 서술은 틀림).

테스트 유효성: r3h 새 테스트 전부를 bb05d37에 복사해 실행. 백엔드 수정 전 실패 118·통과 27·수집 오류 1. 결함으로 실패 core6 19·migrations 2·redact 38·파서 할인 46. 수정 전 통과 27건은 모두 원래 맞던 동작의 가드(결함을 못 잡는 리뷰 ID 테스트 없음). 무작위 표본 5건 모두 결함 단언에서 실패. FE r3h 0/17·r3h2 4/15 통과(통과 4는 회귀 가드). 약해진 테스트 → m19. 담당이 말한 "수정 전 실패 확인" 표는 저장소에 없었음.

실행(부하: 리뷰 에이전트 4개 동시, CPU 50–82%, 메모리 85%): pytest 1 failed / 3762 passed — `test_d14_5_publish_job_1000x5…` "API 쓰기 최대 2.522s > 1.0s"(SQL 실행 잠금 대기 2.509s, COMMIT 0.001s, 잡 묶음 잠금 최대 0.862s), 단독 재실행 통과(→ m18). mypy 164 0, ruff·format(426) 통과, gen·fixtures --check exit 0, regress 715·T01–T18 PASS·e2e 흐름 3/3, vitest 686/686, build, audit 0, e2e 1차 `charts-gallery C05 normal` 부하 시간 초과 1건 → 재실행 45+20(T16 p50 16.7·p95 33.3ms), e2e:api 29. 재현: scratchpad `r9/a`(할인), `b`(마이그레이션·backfill), `c`(발행·스케줄러·체크포인터), `t`(수정 전), `r`(redact).

## Critical
없음.

## Major
1. **backfill 중단·겹침 시 발행 리비전 출처 서랍이 지워지고 현재 사실로 재생성** (WP0) `snapshot_view.py:1524-1531,1456-1537` — 표식을 내리고 서랍 행 전부 DELETE를 커밋한 뒤 `write_rows`는 별도 트랜잭션, backfill에 발행 임대 없음. 중단: `fp_591 '계약금 10%'` → 복구 뒤 `'20' 확인됨`. 동시: A IntegrityError, B가 빈 서랍으로 재생성. 0012·0013 뒤 업그레이드마다 지나는 구간. 실제 경로(조건부: worker 재시작·Ctrl+C, compose 자동 backfill과 CLI backfill 겹침). 정상 완료 경로는 바이트 불변.
2. **backfill이 빠진 키를 현재 사실로 채워 한 리비전에 시점이 다른 값이 섞임, S4 설명과 구현 불일치** (WP0, CEO 판단) `snapshot_view.py:1484,1430-1452` — 발행 뒤 계약금 10→20 + 일부만 쓴 상태 → 리비전 12 상세 `{"v":20,"label":"확인됨"}`, 같은 리비전 기본 목록은 옛 값. 발행 뒤 추가 단지가 새 시나리오 목록에 들어감(상세 404). 실제 경로지만 드묾(일부만 쓴 단위·0010 이전 발행분).
3. **실패한 이월 발행 잡 재시도 없음 → 리비전 `building` 영구 고착, 이후 쓰기는 그 리비전으로 끝없이 미뤄짐; 이월 분할로 ready 전환 직전 새 중단 구간** (WP7) `handlers.py:452-466,547-553` — `JOB2 done {'published': False, 'deferred_to': 13}`, `queued jobs []`; `RETRY failed publish_blocked: 판정·점수 미완료 rev1 building`. 실제 경로(조건부: SQLite 단계 사이 잠금 실패(시뮬레이션), worker 강제 종료).
4. **사람 확인 할인이 새 현재 공고에 퍼지지 않아 조용히 사라짐** (WP2, runbook WP0) `normalize/store.py:1009`, `api/demotion.py:780` `_spread_to_group` — 값이 있는 공고 행에만 복사. 새 공고(무순위·정정)가 현재 공고가 되면 할인 차감 사라짐, change_event·재검토 없음(`disc=(10000000,'확인됨')` → `disc=None`). `docs/runbook.md:347` 설명과 다름. 실제 경로.

## Minor
1 `0013_r3h.py:41` `reason` 덮어써 compare 채택 표식 지움(추정), change_event·rejudge 없음(실데이터 영향 0)(WP0·WP7). 2 `demotion.py:147,650-671` 사람 확인 할인 값 검사 구멍(할인 ≥ 가격, `'1,0'`→10, `',,5,,'`, 공백·전각·아랍 숫자, `'-0'`), FE 목과 불일치(WP5·WP6). 3 FE `complex/tabs.tsx:99,204` 기준 타입 아닌 타입에도 "사람 확인 시 반영" 안내, 폼에 기준 타입 표시 없음(WP6). 4 옛 공고 `entity_id` 201 무효, 기준 타입 변경 시 할인 잔존(추정)(WP5·WP2). 5 업그레이드 전 보고서 저장본 옛 `sc_`·`st_` id(리비전 11 223개·12 461개 서랍 없음, 10개 KPI 충돌), 변환·SHAPE_VERSION 없음, `reports/README.md:79` 옛 설명(WP8·WP0). 6 `runner.py:388,411` backfill 재시도가 worker 시작 때만, `migrate_row_human_checks` 예외 격리 없음(추정)(WP0·WP7). 7 runbook §11 compose 자동 마이그레이션·backfill과 CLI 겹침 위험, 중단 예외, 현재 사실 계산 설명 누락(WP0). 8 `catalysts.py:250-256` 좌표 소수 7자리 이상이면 매번 바뀜 판정(실제 경로)(WP5). 9 `reports.py:137-138` compare 생략 시 `default_compare` 준비 미검사(WP5). 10 `ops.py:325-326` 스키마 오류 + checked_at 범위 밖이면 checked_at 오류가 뒤로(F9)(WP5). 11 `runner.py:194-195,265-276` 재큐잉·stale 복구 카운터 서로 지움(합성)(WP7). 12 `core/db.py:139-144` 체크포인터 예외 무기록 삼킴(WAL 증가)(WP0). 13 `snapshot_view.py:1050-1059` 임대 잃은 이전 보유자 쓰기 재확인 없음(합성, 추정)(WP0). 14 `snapshots.py:159-161`, `catalysts.py:294-307` 스냅샷 없는 지역 PATCH 202 + job_id null(F3)(WP5). 15 D16-4 범위: `PATCH /ops/checklist`·이름만 `PATCH /regions` 200·발행 없음인데 report 본문에 들어감(설계 질문)(WP5). 16 `runner.py:90,330-334` `--once`·`run_until_idle` 재큐잉 대기 잡 남긴 채 exit 0(합성)(WP7). 17 redact 잔여(camelCase `accessKey=`, `pass:`, 키 없는 `sk-ant-…`·`ghp_…`, dict 정수 값), 'bearer' 뒤 산문 과잉 가림(WP0). 18 D14-5 측정 테스트가 전체 스위트 부하에서 실패(SQLite 개발 한정, 묶음 사이 잠금 대기)(WP0). 19 테스트 약점: `test_r3h_checkpointer.py:63` assert 없음, `test_r3g_k1_discount.py:67,233` 후보 미출력도 통과·퍼징 삭제, m21 docstring 틀림, `test_r3h_migrations` 서랍 바이트·중단·동시·발행 뒤 사실 변경 미시험, e2e `charts-gallery C05` 부하 시간 초과(WP0·WP2·WP9).

## 결함 없음 확인
D16-1 파서 '확인됨' 0건 전 경로, 사람 확인 할인 차감 단일 함수·타입별. D16-2 정상 경로: .11·옛 0012·.12 → head → backfill 기존 응답 2,750개 바이트 불변, 서랍 404 116 → 200, 503 기간 GET·`POST /reports` 503, 0013 앱 import 없음·멱등·PG 통과. D16-3 재큐잉·backoff 합 약 18.5분·유실 없음·livelock 없음·holder·DELETE 임대 조건. GC 예외 경로 복구. D16-5 FE `kstDay`.

## RA 대비 누락·부분
- 누락 0.
- 부분: §6-1·D16-1 할인(major 4, m2, m3); §7-1 G3 서랍·D11-1 발행 불변(major 1·2, m5); §10 운영(major 3, m6, m7); D14-5 SQLite 부하(m18); 규칙 6·13 redact(m17); D16-4 범위(m15).
- 해결로 바뀜: 파서 할인(N-C1), D15-3 표식(N-M1·N-M2·m3), 발행 잡 누락(N-M3·N-M4), KST 표시(m13), 규칙 12(m19).
- 수용(변동 없음): G7 배지 즉시 갱신, G8 html·pdf, T13 저장본 라벨, §10 rawdata 압축, T16 발행 비용, 잔여 일정.
- T1–T18 regress 전부 PASS. 규칙 4·11·15 위반 없음.
