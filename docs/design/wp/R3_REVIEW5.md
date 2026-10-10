# R3 5차 리뷰 (main ae7f896, 계약 2026-10-09.9) — 하위 점검 4건 종합
4차 critical 5 전부 해결, major 17: 해결 13·부분 4(M-3·M-7·M-10·M-12), minor 45: 해결 40·부분 4·수용 1. e2e 45+20, e2e:api 26 통과. 재현 스크립트: scratchpad `a1/`(core·sub_fe·sub_rev·sub_misc), `a2/`, `b1/`, `b2/`.

## Critical
- **K1 사람 확인이 행(id)에만 걸림** `facts_view.py:279-282,298-302`, `demotion.py:593-602`, `store.py:968-1016`, `price_view.py:126-128,183`: 사람 확인 복원이 의미 필드 강등을 영구히 끄지만 사람 확인 값은 행 하나에만 → 새 공고 행(무순위 등)이 모순 값 X를 실어 오면 화면·점수로 복귀(690,000,000 → 700,000,000, 점수 703,140,000). 공고일이 사람 확인보다 앞이면 사람 확인이 이겨야(D12-1) 하고, 뒤면 '사람 확인 재검토' 항목이 생겨야 하는데 둘 다 안 됨. 변형: 새 공고에 기준 타입 칸이 없으면 원 공고 행으로 돌아가 모순 값 노출. 사람 확인보다 먼저 관측된 공고라도 시행일만 늦으면 사람 확인을 이김(668,280,000). 계약금도 동일(10% → 20%).
- **K2 발행 리비전 불변이 부분적** `catalysts.py:270-276`, `snapshot_state.py:41-42,142-145`, `complexes.py:190-212`, `views.py:365-371,665`, `snapshots.py:283`, `supply.py:205-206`, `market.py:118`, `reports/data.py:1353,1826-1866`: 연결 그대로 `expected_ym`만 PATCH → 새 리비전 없음, 발행 화면이 얼린 옛 값 + 지금 출처 행(null로 지우면 상세 500). 얼리지 않는 것: 사실(가격·전매)·강등 오버레이·단지 목록(새 단지 16→17)·체크리스트(10→68)·지역 이름·참고 원문·호재 stage_prob/judgment_seq/name/note·inclusion_prob·입주 물량 생활권(la_2 12,203→11,534). 저장 점수와 같은 화면의 사실이 어긋남.
- **K3 REPORT_DIR 상대 경로면 다운로드 404** `routers/reports.py:82-93`, `reports/export.py:125,140`, `core/settings.py:68` (기본 `./data/reports`, runbook R4 `../r4/reports`).

## Major
- M1 `scheduler/rejudge.py:52-63` enqueue_rejudge가 queued 잡 payload 수정 시 상태 재확인 없음 → worker가 집은 뒤 추가된 단지 누락, 응답 rejudge_job_id는 running 잡, 이벤트 영구 누락(Postgres 재현; SQLite는 database is locked 500).
- M2 `handlers.py:83,104,185-212` 이월이 직전 발행 스냅샷 자신의 변경 이벤트를 빼고, `_finish_unchanged_revision`은 changed_after_runs·degraded 미확인 → 사람 확인 리비전 rejudge 실패/지역 축소 후 expand 실패 시 옛 점수가 `created_at=now`로 발행.
- M3 `api/demotion.py:621-643` 재강등 change_event가 발행 스냅샷에 붙고 rejudge 미등록; 채택 보류만 돼도 "다시 채택됨" 이벤트.
- M4 `routers/regions.py:285-291` PATCH /regions change_event가 발행 스냅샷에.
- M5 `routers/reports.py:72-73` 비교 스냅샷 발행 여부·같은 지역 미검사(building·ready·타 지역 비교 202→done); FE도 building만 거름.
- M6 `api/views.py:368-371,426-437` '재판정 필요'가 단지 단위 이벤트만(지역 단위 complex_id NULL 무시), 얼린 분류로 현재 범위 계산 → 지역 축소 직후 배지 없음.
- M7 `analysis.py:299-321` POST /scenarios NaN → 커밋 후 500, 이후 GET /scenarios 계속 500.
- M8 `scheduler/supply.py:178-208`(`load_supply`) upsert만, 빠진 단지 추정 행 미삭제 → 강등·범위 경계·입주월 삭제 뒤에도 옛 입주물량이 시장·보고서·점수에.
- M9 (추정) `notice_parser.py:731-772` 할인 제외 단어 방식 — 잔금 완납·조기납부·저층 한정·빌트인 가전·중개수수료·취득세 할인·`84A-1` 표기가 '확인됨' 분양가 할인.
- M10 (추정) `store.py:547` 원 번호 인용 잔여 공고의 단지 후보 전부 건너뜀 → 정당한 입주 지연(2028-03→2028-09) 소실.

## Minor
- `_text.py:128-132` IDNA 무시 문자(U+00AD·200B·034F·FE00·180B·2060)로 내부망 우회, `%00` NUL 저장; FE safeHref도 통과.
- `benchmark.py:113`, `remaining.py:299,323,331` NFKC 먼저 → Ⅱ→II 후 삭제, '(Ⅱ 잔여세대)'·'(Ⅲ 잔여세대)'·'(잔여세대)' 같은 키; '(2블럭 …)'·'(II …)'·'(3bl …)'·'A-3BL'.
- `price_view.py:209` 할인이 대표층가보다 크고 최고가보다 작으면 low 음수.
- FE `pages/complex/tabs.tsx:14-27` 서버가 안 뺀 할인(0·음수·최고가 이상)도 "구매가에서 뺌" 표시 → 서버가 `applied` 여부 내보내기.
- FE `pages/reports/index.tsx:23-29,50-57,132-139` 'ready' 기준 생성 시 409 conflict 무음.
- `redact.py:113-118` `aws_secret_access_key=`·`private_key=`·소문자 `bearer`(추정).
- FE `_shared/index.tsx:186` 건수 라벨 '확인됨'을 근거 없이 생성(추정).
- `handlers.py:185-212` 변경 없는 주간 수집도 매번 같은 내용 리비전 발행(결정 필요 — D13-4).
- `backup.py:38` `.env`의 BACKUP_DIR 무시(os.environ만).
- FE `hooks.ts:549` useJob 오류 시 무한 폴링, `jobWatch.ts` 30분 후 폴링 중단·실패 잡 building도 폴링.
- `ops.py:329-343`, `resolver.py:207-212` 이미 관측된 공고보다 이른 checked_at 사람 확인은 지는데 201·critical change_event·rejudge 발생.
- `reports/data.py:985-988` 강등 가격 사유 '분양가 미공개'(API는 '검증 모순'); `reports/data.py:306-308` 보고서 '재판정 필요'가 바뀐 사실 미반영.
- `contracts/schemas/snapshot.json:14` revision_of 설명이 S9 이후와 다름.
- (추정) `living_area.py:252-262` 읍면동 이름 겹쳐 법정동 미정이면 판정 대상 잔류; `notice_parser.py:63,267,272-280` 공고 번호 줄 순서로 원 번호 오인·'재공급' 제목이 '본청약'; G5 '이후' 캐시 값으로 잠깐 '변화 없음'.
- market 시나리오 미전달(`load_bundles` scenario 없음, 계약에 파라미터 없음).
