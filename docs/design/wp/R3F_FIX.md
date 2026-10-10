# R3f 수정 — 6차 리뷰(`R3_REVIEW6.md`) (계약 .10 → .11). 결정 D14.
=====CORE4=====
소유: `backend/**`, `contracts/**`(계약 .11), `infra/**`, `docs/runbook.md`, `scripts/tasks.py`.
1. C1 / D14-2 할인 '확인됨' 엄격화 — 리뷰 문구 5개(층 괄호, 잔금 완납 시, 특별공급 한정, 최대, "할인 없음, 취득세 지원")를 실패 테스트로 먼저. 조건 토큰은 줄 전체 검사.
2. C2 / D14-1 출처 서랍·claims 목록 저장본 — `GET /provenance/{id}?snapshot_id=`(계약 .11), 저장 kind 추가, 발행 뒤 새 공고·재수집(supply 출처 행 삭제 포함)·강등·PATCH /claims에도 바이트 불변.
3. N-M1 / D14-3 사용자 시나리오 보고서(API·CLI `--scenario`), `diff.py` id 기준.
4. N-M2 / D14-4 저장본 `contract_version`·sha256 읽기 검증, `stored_view_mismatch`.
5. N-M3 / D14-5 materialize를 worker 잡으로(호재 연결 PATCH·사람 확인·생활권 편집 등 발행 유발 API 전부 202 + job_id), 나눠 쓰기 + 짧은 전환. 1000단지 × 시나리오 5 잡 ≤15초, 그동안 API 쓰기 잠금 ≤1초 측정 테스트.
6. N-M4 / D14-6 checked_at date-time·미래 422·KST 공용 비교, 같은 값 수용(m11), 재확인 시 재검토 닫기(m13), m12.
7. N-M5 / D14-7 단지 단위 이월·재판정 판단.
8. D14-8 T13 저장본 라벨 + 잡 통계, D14-9 0010 앱 import 제거 → backfill 단계 + 503 `materialize_pending`, devseed reset(m3).
9. 백엔드 minor 1–19, 27(불변 테스트 URL 목록에 market `?scenario=`·출처 서랍·claims·사용자 시나리오 보고서·compare 추가), 28(0010·backfill PG 왕복을 단지·시나리오 있는 픽스처로). m14는 backfill에서 행 단위 사람 확인을 의미 묶음으로 옮김.
10. 계약 .11 CHANGELOG에 FE 차이 표(엔드포인트·필드·오류 code·202 응답) 필수.
완료: pytest 실패 0(2회, 1회 부하), regress(e2e 포함) 통과, ruff·format·mypy, 마이그레이션 왕복(SQLite·PG), gen·fixtures --check, 리뷰 ID별 테스트 표.
=====FE5=====
소유: `frontend/**`, `e2e/**`. 1단계(계약 무관): FE minor 20–25, vitest 부하 타임아웃(r3d "PATCH /regions 이름만 변경" 5017ms) 안정화. 2단계(CORE4 머지 후): gen:api·gen:msw, 출처 서랍 `snapshot_id` 전달, 사람 확인 시간대 포함 date-time 입력·미래 422 표시, 발행 유발 쓰기 202 + job 감시, 새 오류 code(`scenario_not_in_revision`·`stored_view_mismatch`·`materialize_pending`) 안내, 보고서 화면 사용자 시나리오 선택 시 대상 리비전 검사.
