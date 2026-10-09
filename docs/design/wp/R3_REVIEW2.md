# R3 재리뷰 (main d31ae48, 계약 2026-10-09.5) — 새 발견 critical 4 / major 8 / minor 31

1차 58건: 해결 40 / 부분 16 / 미해결 1(m4) / 수용 1(m36). 부분: C1(벤치마크 없음 사유·언론 역산·is_presale 경로), C2(보고서 사본·API 혼합), C3(OCR extract 강제 안 됨: 32필드 초과 잘림, screen 거부·extract 실패 시 OCR 값이 점수에 남음 `pipeline.py:314-338`), M2(winner_date 라벨 누락), M3(보고서 사본), M6(P4가 kind 미결정 '기타' 고정, catalyst_link 0, catalyst 출처 행 없음 `pipeline.py:497-505`, `catalyst.py:101`), M7, M8, M16(테이블 목록 `provenance.py:47` 손으로 씀 — supply·household_stat·remaining_event·catalyst 누락), m2(스냅샷 비교 `--ignore-snapshots`, win32 기준 이미지), m13(사람 확인 critical 알림이 토스트 클릭 시에만, `sent_ids` 메모리), m21(보고서 `data.py:836-840`), m23(도구별 값 0, bootstrap 통계 누락 `ops.py:116-137`, `handlers.py:187`), m26(프론트 C6 0길이 막대 빗금 안 보임 `C06/buildOption.ts:169-186`), m34(런북 경로 깨짐), m37(T16 기준 60fps→p95 34ms 결정 기록 없음 `e2e/pages/perf.spec.ts:34-50`). 미해결 m4: 일일 수집 10분을 청약홈만 FakeClock으로 잼.

## Critical
- **N-C1** `api/views.py:355-363`, `:964-966`, `api/routers/snapshots.py:615-618` — API가 현재 사실로 다시 계산한 판정 범위와 저장된 순위·종합 점수를 섞어 표시(`stored_scope` `views.py:296` 미사용). devseed 기본에서 TOP 5의 4번 단지가 '미해결'인데 rank 4·5.0; 1위에 사람 확인 '불가' → scope '참고'인데 rank 1·5.87, p10 성분 3.9인데 p10 사실값 null; judged_count 11→10으로 KPI와 TOP 5 불일치.
- **N-C2** `scheduler/collect.py:141-175`(매 수집마다 새 '확인 불가/미분류' 접수 행), `persist.py:407`(이전 분류 미복사), `handlers.py:89-96`(P4 없이 publish) — 변경 없는 날 published 스냅샷에서 판정 대상이 '참고'로 바뀌는데 순위 유지; 다음 변경일에 단지마다 D9-3 critical 이벤트 폭주.
- **N-C3** `scheduler/reverify.py:60-130` — PATCH /claims로 문장만 고치면 publish가 풀리지만 contradicted 판정의 근거가 된 DB 사실은 그대로 점수·화면에 나감; 새 문장이 원 주장과 같은 대상·필드인지 검사 없음.
- **N-C4** `normalize/store.py:272`, `_ROUND_PAREN_RE` `:568` — W12c 같은 블록 병합이 모든 새 주택관리번호에 적용, "(1차)/(2차)" 괄호 제거로 이름 키가 같아지고 주소("…일원")도 같으면 2차가 1차 행을 덮어씀(데이터 손실, 이름 휴리스틱이 판단 대체).

## Major
- **N-M1** `normalize/benchmark.py:441-449`, `:103` — 이름 포함(contains) 매칭 + 준공 ±1 + 블록 번호 제거로 D9-2보다 느슨: '더샵 송도 퍼스트'→'더샵송도퍼스트파크2단지', '힐스테이트 송도'→'…2차', AA13-1·AA13-2 동일 취급.
- **N-M2** `normalize/catalyst.py:134-159`, `judge/payloads.py:120-142` — '<지역> 분양' 뉴스가 전부 호재 후보; P4에 '호재 아님' 클래스가 없어 분양 기사가 호재로 G3·보고서에; 매주 판정 호출 증가.
- **N-M3** G1 `views.py:834-838`·보고서 `s05.html.j2:17`("확인 불가(수집 전)" 고정) — D9-2 "벤치마크 없음" 사유 미표시/오표시, 테스트 없음.
- **N-M4** 지역 전체 대체 표시 누락: 점수 식 문구에 '대체' 없음(`score.py:249-254`), G3 `sample_n`이 대체 행까지 세어 '표본 3 미만' 배지 누락(`market.py:97`), 보고서는 대체 행을 생활권마다 중복 집계.
- **N-M5** `normalize/checklist.py:150-246` — 제목에 값이 들어가 사실이 바뀌면 옛 open 항목 잔존(resale_months 12→24 → "전매제한 종료" 2개).
- **N-M6** 보고서가 공용 함수 대신 `reports/policy.py` 사본: 접수 행 선택(`data.py:836-840`), 납부 조건 정렬, `has_price`가 출처 유무에 묶임 → API와 판정 범위 갈림.
- **N-M7** `pages/share/index.tsx:25`, `api/auth.ts:130-143` — `/share#token`이 확인 없이 쓰기 토큰을 덮어씀; 다른 탭도 storage 이벤트로 즉시 읽기 전용.
- **N-M8** (추정) `scheduler/pipeline.py:861-863` — 판정기 다운 + 판정 전부 캐시면 try 밖 `adapter_version`이 서버 재호출 → 스냅샷 ready 커밋 후 잡 예외.

## Minor
- F1a: `checklist.py:8,160` kind '계약' 미사용; `rtms/collector.py:53` 분양권 API 미수집 → is_presale 운영 불가; `benchmark.py:599-638` 분양가 라벨이 실거래 라벨과 섞임·대체 행 note "확인됨"; `benchmark.py:532,354` 법정동 변환 실패 공고 무기록 소실, 84㎡ 최근접이 74㎡여도 80~85㎡ 실거래와 비교; `benchmark.py:284-324`, `remaining.py:145-171` 원문 재읽기·N+1; `remaining.py:435-441` 배포 후 첫 수집 때 과거 잔여 공고 전부 critical+재판정(추정); `applyhome/api.py:115-122` 경쟁률 perPage=100 페이지 미순회 잘림; `applyhome/api.py:224` 오류 문구 인코딩된 키 미마스킹; `models/market.py:39` benchmark에 snapshot_id 없음 → 발행 스냅샷 인용 벤치마크 소실 가능.
- F2: `snapshots.py:624` judged_count 값과 출처 식 불일치; `payloads.py:118-134` wait_new "12개월 내" 필터 없음·미해결·보류 포함; `inputs.py:241` 가격 출처 없으면 타입 행 라벨 대용; `checklist.py:38,221` 미해결 단지를 제외로 닫음; `persist.py:417`·`pick_intake` 기준 불일치 → 가짜 D9-3(추정).
- F3: `runbook.md:102` worker 이미지에 infra/ 없음·`raw_archive.sh` 상대 경로 실패; `complexes.py:686` 압축 원문을 요청마다 tar 전체 메모리 해제; 공유 토큰으로 `/ops/judgments`·`/raw`·`/jobs` GET 가능(설계 확인); `catalysts.py:98` URL 미정규화 중복·같은 URL rejudge 재등록; `serve.py:44` 프록시 헤더 허용 `*`(추정); POST /jobs로 `claim.reverify` 넣으면 PATCH 검사 우회; 프론트: `share/index.tsx:8` decodeURIComponent 예외 미처리, 409 뒤 목록 미갱신, G4 wait_new 미표시; `views.py:359,1123` 낡은 docstring; C07 기준 이미지가 tie·wait_new 전.
- F4: `tests/reports/_seed.py:160` devseed 중복 적재(claims·접수 2배); 보고서 wait_new 근거·테스트 없음.
- F1b: SSRF 잔여(CGNAT 100.64/10 미차단, DNS rebinding, Playwright `page.goto` 미검사, prod+`HTTP_ALLOW_PRIVATE_HOSTS` 허용); `render.py:120` 팝업 서명에 `?v=` 쿼리 포함(추정); `protocols.py` 정준화 정의 변경에 `ADAPTER_CODE_VERSION` 미증가; Mock·합성 판정 행에 '합성' 표식 없음; prod+SQLite(devseed DB) 차단 없음; redact 잔여(`82-10-…`, `Bearer`, `redis://:pw@`).
- 기타: perf 테스트 1초 경계 흔들림(`tests/api/test_perf_r3.py`); 통합 테스트 부재 — 벤치마크 생성→종합 점수, 벤치마크 오매칭 부정 테스트, 보고서 wait_new.
