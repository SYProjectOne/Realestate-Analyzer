# R3i 수정 — 9차 리뷰(`R3_REVIEW9.md`) major·minor (계약 .13 → .14). 결정 D17. R3 게이트는 통과(critical 0), R4 전 정리 라운드.
=====CORE7=====
소유: `backend/**`, `contracts/**`(계약 .14), `infra/**`, `docs/runbook.md`, `scripts/tasks.py`, `docs/design/DECISIONS.md` 5행 버전 표기.
1. major 1 / D17-1 backfill 임대·원자 재작성 — 중단(각 단계 사이 예외 주입)·동시 backfill 2개·발행과 backfill 겹침에서 기존 서랍·본문 바이트 불변 테스트.
2. major 2 / D17-2 `backfilled_at`·응답 메타 표지·목록 범위 제한, CHANGELOG S4·runbook 정정.
3. major 3 / D17-3 이월 발행 재시도·ready 전환 멱등·deferred 재등록.
4. major 4 / D17-4 사람 확인 의미 단위 유지(값 없는 새 공고), 기준 타입 표시용 필드(필요 시 계약).
5. D17-5 체크리스트·지역 이름 쓰기 발행 잡. D17-6 SQLite 측정 테스트 전체 스위트 부하 통과(묶음 사이 양보), m18.
6. minor 1, 2(서버 값 검사: 할인 ≥ 가격 거절, 숫자 형식 엄격), 4–14, 16, 17, 19(약한 테스트 보강: 체크포인터 assert, 할인 후보 출력 단언·퍼징 복원, 마이그레이션 서랍 바이트·중단·동시·발행 뒤 사실 변경).
7. 테스트 먼저 + 수정 전 실패 확인 표를 **보고와 `docs/design/wp/R3I_TESTS.md`에 남길 것**.
8. 계약 .14 CHANGELOG + FE 차이 표.
완료: pytest 실패 0 — 2회 모두 regress와 동시(부하), regress(e2e 포함, 마지막 커밋 뒤), ruff·format·mypy, 마이그레이션 왕복(SQLite·PG), gen·fixtures --check, D14-5 부하 2회 수치.
=====FE8=====
소유: `frontend/**`, `e2e/**`. 1단계(계약 무관): minor 3(기준 타입 아닌 타입 안내 문구 수정), FE 목 할인 값 검사를 서버와 일치(m2), e2e `charts-gallery C05` 부하 시간 초과 원인. 2단계(CORE7 머지 후): gen, .14 FE 차이 표, `backfilled_at` 리비전 표지 안내, 사람 확인 폼 기준 타입 표시.
