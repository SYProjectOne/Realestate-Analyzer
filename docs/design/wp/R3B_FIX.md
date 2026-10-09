# R3b 수정 라운드 — 재리뷰(`R3_REVIEW2.md`) 배정 (계약 2026-10-09.5 → .6)
규칙: `R1_COMMON.md`. **각자 소유 파일만**. 실패 테스트 먼저. 리뷰 ID별 테스트 표로 보고. 결정은 DECISIONS D10.

=====G1=====
# G1 데이터·정규화·판정 입력 (collectors, normalize, judge, core/redact·http, collectors/*)
소유: `backend/app/collectors/**`, `backend/app/normalize/**`, `backend/app/judge/**`, `backend/app/core/{redact,http,protocols}.py`, 해당 테스트.
- N-C4 (D10-4), N-M1 (D10-5) + 부정 테스트(리뷰 재현 사례 3개), N-M2 (D10-6: screen 입력 생성·호재 분류 클래스 "호재 아님"·kind 분류 payload — 파이프라인 연결은 G2), N-M5(checklist 안정 키: 값이 아니라 (complex, kind, field) 기준, 값 바뀌면 같은 항목 갱신).
- 부분 항목: M6 catalyst 출처 행(field_provenance) 생성, M16 provenance 테이블 목록을 모델 메타데이터에서(supply·household_stat·remaining_event·catalyst 포함), C3 OCR 필드 32개 초과 시 잘리지 않게 분할 extract payload.
- m4: 일일 수집 10분을 모든 collector(청약홈·공고문·공식 홈페이지·실거래·통계·뉴스) FakeClock 합산으로.
- 재리뷰 minor 중 F1a·F1b 줄 전부(checklist kind '계약', 분양권 API 수집으로 is_presale, 벤치마크 라벨·note·74㎡ 비교, 법정동 변환 실패 기록, N+1, 첫 수집 과거 잔여 공고 이벤트 폭주 방지(최초 적재는 info), 경쟁률 페이지 순회, 인코딩 키 마스킹, SSRF 잔여(CGNAT·DNS rebinding·Playwright goto 검사·prod에서 allow_private 거부), 팝업 서명 쿼리 정규화, ADAPTER_CODE_VERSION 증가(정준화 변경), Mock·합성 판정 행 '합성' 표식, redact 잔여). benchmark snapshot_id는 계약 변경 → G3에 요청.

=====G2=====
# G2 점수·파이프라인·API 저장값 (analysis, scheduler, api/views·snapshots 점수 부분)
소유: `backend/app/analysis/**`, `backend/app/scheduler/**`, `backend/app/api/views.py`, `backend/app/api/routers/snapshots.py`(dashboard·KPI·TOP5 부분), 해당 테스트.
- N-C1 (D10-1): API·KPI·TOP 5·complexes 목록·상세의 범위·순위·총점·성분은 저장값; 현재 범위가 다르면 `rejudge_needed` 표시(계약 필드가 없으면 G3에 요청, 그 전까지 내부 플래그).
- N-C2 (D10-2): 접수 분류 복사(text hash 동일), 변경 없는 날 범위·순위 불변 테스트(리뷰 재현 그대로), persist가 분류도 복사.
- N-M8: 판정기 다운+전부 캐시 시 adapter_version 재호출 없이 완료.
- N-M2 파이프라인: 뉴스 후보 → P1 screen → P4 classify(호재 아님이면 후보 폐기·기록).
- N-M4: 점수 식 문구에 '대체(지역 전체)' 표기, 대체 라벨 전달.
- C3: screen 거부·extract 실패 시 OCR 값은 점수 입력에서 null.
- M2: winner_date 라벨 포함. m13: 사람 확인 critical 알림을 서버 쪽에서(토스트 클릭 불필요), sent_ids 영속. m23: 도구별 cached_hits 실제 집계, bootstrap 통계 포함.
- 재리뷰 minor F2 줄 전부(judged_count 식, wait_new 12개월 필터·미해결·보류 제외, 가격 출처 라벨, 미해결 단지 checklist 처리 = na가 아니라 유지, pick_intake 기준 통일).
- 통합 테스트: 벤치마크 생성 → 종합 점수 계산(실데이터 녹화 기반).

=====G3=====
# G3 API·프론트·계약 .6·운영
소유: `contracts/**`(fixtures는 재생성 도구 실행만), `backend/app/models/**`, `backend/app/core/{settings,db}.py`, `backend/app/main.py`, `backend/app/api/**`(단 `views.py`·`routers/snapshots.py` 점수 부분은 G2), `frontend/**`, `infra/**`, `.github/**`, `docs/runbook.md`, 해당 테스트. **계약 .6 소유자**.
- N-C3 (D10-3): claims PATCH 대상 검사, 사실 강등·복원, 체크리스트 "사실 재확인", POST /jobs의 `claim.reverify` 직접 등록 차단(PATCH 경유만).
- 계약 .6: `rejudge_needed`(G2), claim 대상 필드, 강등 라벨, benchmark.snapshot_id(G1 요청 — 발행 스냅샷 인용 보존), 기타 요청 수신.
- N-M3 G1 화면 "벤치마크 없음(사유)" 표시(API 필드 + 화면), N-M4 G3 `sample_n`은 자기 생활권 표본만, N-M7 공유 링크 열 때 기존 쓰기 토큰 덮어쓰기 확인 다이얼로그 + 다른 탭 storage 처리, D10-7 공유 토큰 GET 범위.
- 부분 항목: m2(CI 스냅샷 비교 — linux 기준 이미지 생성 잡 또는 OS별 기준), m26(프론트 C6 빗금 0길이 막대 가시화: 범례/라벨로 "미판정" 표시), m34(runbook 경로·worker 이미지), m37(D10-8 기준으로 테스트 정리).
- 재리뷰 minor F3 줄 전부(압축 원문 스트리밍 해제, catalysts URL 정규화·중복 방지, 프록시 헤더 허용 목록, share decodeURIComponent 예외, 409 후 목록 갱신, G4 wait_new 표시, 낡은 docstring, C07 기준 이미지 갱신), perf 테스트 경계 안정화(측정 반복·중앙값).

=====G4=====
# G4 보고서 (진행 중인 WP8 범위 수정 에이전트에 추가 지시)
N-M6(공용 함수 사용 — 사본 제거), N-M3 보고서 "벤치마크 없음" 사유, N-M4 대체 행 중복 집계 제거·대체 표기, F4 minor(_seed 중복, wait_new 근거·테스트), D10-1(보고서도 스냅샷 저장값 기준).
