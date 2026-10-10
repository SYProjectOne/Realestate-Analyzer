# R3g 수정 — 7차 리뷰(`R3_REVIEW7.md`) (계약 .11 → .12). 결정 D15.
=====CORE5=====
소유: `backend/**`, `contracts/**`(계약 .12), `infra/**`, `docs/runbook.md`, `scripts/tasks.py`.
1. K1 / D15-1 할인 허용 목록 — 리뷰 문구 전부 + scratchpad `r7/b/fuzz_disc.py` 퍼징을 테스트로(퍼징은 "허용 꼴이 아니면 '확인됨' 0건" 속성 테스트).
2. M1 / D15-2 출처 저장본 수집 범위(모든 시나리오·patch 행·`rd_`), m7(백엔드 쪽), m24 불변 테스트 확장.
3. M2 / D15-3 단위 완료 표식·backfill 재개·리비전별 실패 격리·저장 모양 버전(m9·m11 포함).
4. M3 / D15-4 이월 판단(m14 포함).
5. M4 / D15-5 보고서 §12.
6. M5 / D15-6 single-flight·후속 발행 잡·job_id 항상(m1·m13·m16 포함).
7. M6 / D15-7 시각 파싱 단일화·범위·KST 표시(m2·m3 포함).
8. 백엔드 minor 4·5·6·8·10·12·15, m24 테스트 이름.
9. 계약 .12 CHANGELOG에 FE 차이 표 필수(새 job_id, 503·422 code 변화, rd_ 서랍 snapshot_id 동작).
완료: pytest 실패 0(2회, 1회 부하), regress(e2e 포함), ruff·format·mypy, 마이그레이션 왕복(SQLite·PG), backfill 중단·재개 테스트, gen·fixtures --check, D14-5 성능 측정(부하 2회), 리뷰 ID별 테스트 표.
=====FE6=====
소유: `frontend/**`, `e2e/**`. 1단계(계약 무관): M7·M8 / D15-8, FE minor 17–23. T16 p95 여유(33.3ms ↔ 34ms) 원인 확인·개선. 2단계(CORE5 머지 후): gen:api·gen:msw, .12 FE 차이 표 반영, `rd_` snapshot_id 예외 제거.
