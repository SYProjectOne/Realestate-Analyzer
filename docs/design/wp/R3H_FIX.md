# R3h 수정 — 8차 리뷰(`R3_REVIEW8.md`) (계약 .12 → .13). 결정 D16.
=====CORE6=====
소유: `backend/**`, `contracts/**`(계약 .13), `infra/**`, `docs/runbook.md`, `scripts/tasks.py`, `docs/design/DECISIONS.md` 5행 버전 표기.
1. N-C1 / D16-1 파서 할인 = 언제나 '추정'. 사람 확인 필드 `discount`(의미 단위)로만 '확인됨' → 차감. 7·8차 리뷰 문구 전부 + 퍼징: 파서 출력에 할인 '확인됨' 0건(속성). 사람 확인 할인 → 상세·목록·비교·보고서·점수 전 경로 차감 테스트. 할인 관련 m1·m2는 이 결정으로 흡수(과강등 개념 없어짐).
2. N-M1·N-M2·m3 / D16-2 0012 이전 단위 전부 미완, backfill 빠진 키만 채움(기존 바이트 불변 테스트), 표식 없는 행 단위 = 미완. `0013` 마이그레이션 필요하면 앱 import 금지(D14-9).
3. N-M3·m4·m5 / D16-3 busy 지연 재큐잉, holder = 잡 id, publish_job_id 기록, 정리 DELETE 임대 조건. m21 테스트를 수정 전 코드에서 실패하도록 다시 작성.
4. N-M4 / D16-4 호재 PATCH 전 필드.
5. N-M5 runbook(할인 D16-1, 업그레이드 backfill 절차).
6. 백엔드 minor 6–12, 13(백엔드 쪽: 보고서 KST 확인), 14–15 redact, 20(불변 테스트 서랍 id를 모든 시나리오·patch 행·`rd_`에서 수집).
7. **테스트 먼저**: 리뷰 ID마다 수정 전 코드에서 실패하는 것을 실행해 확인하고 보고 표에 "수정 전 실패 확인" 열을 둘 것.
8. 계약 .13 CHANGELOG + FE 차이 표.
완료: pytest 실패 0(2회, 1회 부하), regress(e2e 포함), ruff·format·mypy, 마이그레이션 왕복(SQLite·PG)·.11 DB → head → backfill 시나리오(일부만 쓴 단위 포함), gen·fixtures --check, D14-5 성능(부하 2회).
=====FE7=====
소유: `frontend/**`, `e2e/**`. 1단계(계약 무관): FE minor 13(checked_at KST 표시), 16–19. 2단계(CORE6 머지 후): gen, .13 FE 차이 표, D16-1 '추정' 할인 안내 + G7 사람 확인 링크, 사람 확인 폼에 할인 필드.
