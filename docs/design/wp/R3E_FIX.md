# R3e 수정 — 5차 리뷰(`R3_REVIEW5.md`) (계약 .9 → .10). 결정 D13.
=====CORE3=====
소유: `backend/**`, `contracts/**`(계약 .10), `infra/**`, `docs/runbook.md`, `scripts/tasks.py`.
1. D13-1 materialized 읽기 모델(K2 전부·M6 일부) — `snapshot_view` 테이블·마이그레이션 0010(기존 발행분 materialize), 발행 트랜잭션에서 생성, 발행 리비전 GET은 저장본만, 보고서도 저장본. 기존 `snapshot_state`·값별 동결 경로는 저장본 생성으로 흡수(중복 제거). **불변 테스트**: 리비전 발행 → 이후 사실·강등·사람 확인·새 단지·호재 PATCH·생활권 편집·지역 이름 변경·입주물량 재수집·classify 재판정 → 그 리비전의 모든 GET·CSV·보고서 바이트 동일.
2. D13-2 사람 확인 의미 단위(K1 전부) — 강등·사람 확인·재검토를 같은 의미 키로; 리뷰 재현(무순위 새 공고 X, 기준 타입 칸 없는 새 공고, 이른 관측 늦은 시행, 계약금) 전부 테스트.
3. K3 REPORT_DIR 상대 경로(저장은 REPORT_DIR 기준 상대 이름, 다운로드는 같은 기준으로 해석) + runbook R4 경로.
4. D13-3(M1), D13-4(M2·minor 주간 리비전), D13-5(M3·M4 + 전 경로 테스트), M5(비교 스냅샷: published·같은 지역만), M6(재판정 필요: 지역 단위 이벤트 포함 — 실시간 리비전에서만 의미), M7(NaN 등 비유한 float 전 엔드포인트 422 — 공용 검증), M8(load_supply가 빠진 단지 행 삭제), M9(할인 판정: 허용 목록 방식 — "분양가 할인"·"공급금액 할인" 등 명시 + 타입 정확 일치만, 나머지는 후보로만 '추정'), M10(원 번호 인용 잔여 공고의 단지 후보: 이름·세대수는 버리되 입주월·일정 변경은 원 단지 후보로 받음, D11-4와 정합).
5. 백엔드 minor 전부(URL IDNA 무시 문자·%00, 이름 키 NFKC 순서·로마 숫자·블럭/BL 변형, 할인 low 음수 방지 + 서버 `discount_applied` 필드, redact 패턴, BACKUP_DIR settings, 이른 사람 확인 422, 보고서 강등 사유·재판정 배지, snapshot.json 설명, living_area 모호 법정동→'범위 경계(확인 불가)', notice_parser 원 번호·재공급 분류, market 시나리오 파라미터(계약 .10)).
완료: pytest 실패 0(2회, 1회 부하), regress(e2e 포함) 통과, ruff·format·mypy, 마이그레이션 왕복(SQLite·PG), gen·fixtures --check. 리뷰 ID별 테스트 표 + 발행 리비전 GET이 실시간 계산을 타지 않음을 보이는 grep/테스트.
=====FE4=====
소유: `frontend/**`, `e2e/**`. FE minor 전부(할인 문구는 서버 `discount_applied` 사용 — 계약 .10 전엔 MSW, 'ready' 기준 409 안내, 건수 라벨 근거, useJob 오류 폴링 중단, jobWatch 30분 제한 개선(발행 대기 잡이 끝날 때까지)·실패 잡 폴링 중단, G5 '이후' 캐시 문제, safeHref IDNA 무시 문자 차단, market 시나리오 전달). CORE3 머지 후 gen·맞춤.
