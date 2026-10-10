# R3 4차 리뷰 (main ce02e6e, 계약 2026-10-09.8) — 새 critical 5 / major 17 / minor 41
3차 C·M 14: 해결 10, 부분 4(C-2·C-3·M-4·M-10). minor 34: 해결 28, 부분 5(12·18·19·22·23), 수용 1. RA 누락 0, 부분 6(archive 압축 원문·백업·delta 표·§12·할인·runbook). 실행: 백엔드 3회 2890 통과(흔들림 0), regress 715+3, 프론트 523, e2e 45+20, e2e:api 24, audit 0.
간헐 실패 원인 확정: `test_t13_frontend_lint_flags_raw_number_outside_factcell` — 같은 frontend에서 `npm ci` 중 eslint stdout 비어 JSONDecodeError(8회 중 7회). 고칠 방향: 종료 코드 0·1 아니면 stderr 포함해 skip/실패 메시지, 순서 문서화.

## Critical
1. `facts_view.py:78-91,104-119`, `price_view.py:162-176` 강등이 (entity, 행 id)에 걸려, 같은 모순 가격·계약금을 실은 **새 공고 행**(무순위 병합 포함)이 오면 상세·목록·점수에 '추정'으로 복귀(강등·체크리스트는 열린 채). 재현: 새 공고 동일 가격 → `658,140,000 추정`.
2. `resolver.py:176-179`, `demotion.py:573-584` compare `adopted`가 source_rank 0(사람 확인)을 무시하고 이김 — 그런데 강등 복원·201·change_event는 남음 → 모순 값이 '확인됨'으로 점수 복귀.
3. '확인됨일 때만 할인 차감'이 표시용 price_range에만: 보고서(`reports/data.py:847`), `/compare` 계약금·자기자본(`routers/analysis.py:182`), 목록 가격 필터·정렬(`views.py:476-486,1322`)은 라벨 무관 차감 → 같은 단지 low 1,245,000,000(상세) / 1,235,000,000(보고서) / mid 1,271,500,000(compare). 보고서 '− 할인' 표기 없음(`data.py:993-1001`).
4. `reports/export.py:52-60` 보고서 파일 이름에 리비전·지역·잡 id 없음 → 같은 기준일 리비전 보고서끼리 `os.replace`로 덮어씀(다운로드 내용·sha256 불일치).
5. `pages/scenario/index.tsx:479,499-501` G5 실행 뒤 비교표 '이후' 값을 옛 리비전에서 읽음(rejudge는 새 리비전) → '변화 없음'/틀린 차이.

## Major
1 `views.py:371-378,553-558` '최신 리비전'에 building·미발행 포함 → '재판정 필요' 배지 소실. 2 `routers/ops.py:320,351` 사람 확인이 최신 published 기준일에 리비전 생성 — 더 새 기준일 미발행이면 옛 기준일에 기록. 3 (추정) `handlers.py:89-103`, `persist.py:503`, `pipeline.py:960` 사람 확인 뒤 rejudge는 제안만 → 다음 날 carry_forward가 옛 점수를 `created_at=now`로 복사해 바뀐 사실과 안 맞는 점수가 배지 없이 발행. 4 `handlers.py:252-310`, `living_area.py:245` 지역 선택에서 뺀 단지가 계속 '판정 대상'(사다리 호출), §12 '제외' 0. 5 `handlers.py:278-290` 리비전 1 미발행·최신 building이면 §12 누락. 6 `judge_version.py:89` 판정기 버전 변경이 미발행 리비전 1에서 감지되면 새 리비전 없음 → delta 표 없음. 7 complex.inclusion_class·living_area, region.living_areas, catalyst stage·kind, catalyst_link 제자리 갱신 → 옛 발행 리비전 상세·시장·보고서가 나중에 바뀜; 보고서 §5·상세에 '호재 아님' 포함(`s05.html.j2`, `data.py:1459-1481`, `complexes.py:316`). 8 `notice_parser.py:267-268` 공고문 PDF가 '최초 주택관리번호'로 원 단지 이름·세대수(3100→1)·공고문 전용 필드(resale·residency·regulated) 덮음. 9 `scheduler/backup.py:35-39,64-66`, `Dockerfile.worker` worker 이미지에 pg_dump 없음 → compose 백업 매일 실패; 백업 위치가 rawdata 볼륨 안. 10 `resolver.py:93-94` 사람 확인 값이 영구히 이김 — 다른 값 새 공식 공고에도 change_event·체크리스트 없음(**D12-1로 결정**). 11 `demotion.py:465-477` entity_id가 complex_type·payment_terms에서 같은 번호면 complex_type에 기록 → 가격 강등 안 풀림. 12 `notice_parser.py:735-747` 할인 줄 부분 문자열 매칭 → 다른 타입·계약금·발코니 할인이 '확인됨' 분양가 할인으로. 13 `catalysts.py:225-228` lat=NaN 스키마 통과 → 커밋 뒤 500. 14 `pipeline.py:559-562,606-608` 사람 호재 note에 '판정기: 호재 아님(jl_N)' 누적 → payload 변해 캐시 미스·재호출. 15 `hooks.ts:636-640` 외 잡 완료 후 `['regions']`·스냅샷 목록 미무효화 → 새 리비전 안 보임. 16 `pages/reports/index.tsx:89,153` + `routers/reports.py:66-77` 보고서 비교 선택이 기준일만(리비전 구별 불가), building 리비전도 보고서 생성 가능. 17 (추정) 같은 rank 다른 종류 원문 채택 보류 시 'new_source' 복원 기록 → 이후 compare가 모순 값 채택해도 재강등 없음(`facts_view.py:88-89`, `demotion.py:625-628`).

## Minor (41, 요약)
보안: site URL 표기 우회(전각 숫자·①·。·%2e·`.localhost`, `_text.py:119-133`); redact snake_case 키(`client_secret=`, `access_token`)·7자 이하 Bearer(`redact.py:117-122`); PATCH /regions `name` guard 없음; `/complexes/{id}?snapshot=` 지역 소속 미검사.
사람 확인·강등: `parse_human_value` '3년'→3개월, '1E1'→10(API 직접); change_event가 발행 스냅샷에 붙음; 출처 서랍 강등 표시 없음; minor 12 사람 done 후 다음 쓰기에서야 재오픈(`ops.py:261-273`).
오버레이 미적용: market 입주 마커 원본 move_in_ym·시나리오 미전달(`market.py:155`); 공급 `_supply` 원본 move_in_ym; diff `_scopes` 대체 계산 오버레이 없음.
리비전·보고서: 변경 없는 주간 수집 뒤 building 리비전 잔존; §12 요약이 사람 확인 리비전에도 "rerank 다시 실행"; 0008 downgrade가 끝난 backup·expand 잡 이력 삭제; 이름만 바꿔도 region.expand.
백업: 퍼센트 인코딩 비밀번호를 그대로 PGPASSWORD; keep_days 상한 없음; OSError가 stats 없이 failed.
이름 키·병합·체크리스트: '(1블록 잔여세대)'·'(3BL 무순위)'·'(Ⅱ 잔여세대)'·'(잔여세대 2차)' 지워짐; '1056-1외, 1056-2' 구역 미인식(`store.py:604`); 벤치마크 이름 키 AA1-31=AA13-1(`benchmark.py:106-111`); 병합 공고 type 행 선생성(추정); `judged._reresolve`가 `_foreign_unit_row` 미필터; 체크리스트 현재 공고 선택이 price_view와 다름(추정); M-8 unmatched 기록 테스트 없음; M-9 단지 제외 시 사람 항목도 auto로 닫힘; M-7 '(1블록 잔여세대)'.
호재·할인: catalyst_link를 점수에 안 쓰는데 연결 변경마다 rejudge·새 리비전; '호재 아님'도 연결 가능·G3 strong 배지; expected_ym null로 못 지움; 할인 음수·과대 미차단; 아카이브 우선 분양가가 압축 원문 못 읽고 조용히 폴백; minor 23 한 필드 발췌 합 2,000자 초과 시 절단.
화면: sampleCountFact가 중앙값 라벨 차용; closed_by 미표시; 할인 문구 툴팁에만(모바일); 409 뒤 재조회 없음; eslint 규칙 9 별칭 import 우회; 링크 reason에 `la_1` 노출.
운영·테스트: runbook D11 미반영; `infra/` README 없음; 골든 68건에 미확인·OCR 할인·대체 벤치마크 gap 케이스 없음; `test_auth` WRITES에 새 PATCH 2개 누락; 새로 고침 없는 리비전 전환·G5 실 API·G8 리비전 테스트 없음; t13 테스트 stderr 버림(간헐 실패 원인).
