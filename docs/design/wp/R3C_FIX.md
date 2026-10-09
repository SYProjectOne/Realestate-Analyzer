# R3c 수정 — 3차 리뷰(`R3_REVIEW3.md`) 배정 (계약 2026-10-09.7 → .8)
방식 변경: 병렬 수정이 서로 엇갈려 새 critical을 만든 패턴을 끊기 위해 **핵심 정합(CORE)은 에이전트 1명**이 백엔드 전체를 맡고, 독립 영역(FE·SEC)만 병렬. 결정 D11.

=====CORE=====
소유: `backend/app/**`(단 `collectors/official_site/{egress,render}.py`·`core/redact.py`·`core/settings.py` 보안 줄은 SEC와 공유 — SEC가 먼저 머지되면 merge로 받기), `backend/tests/**`, `contracts/**`(계약 .8 소유), 마이그레이션 0008.
1. D11-1 스냅샷 리비전(M-2, §10 delta 표, minor 3·4) — 모델·마이그레이션·persist·pipeline·API(최신 리비전)·보고서 diff.
2. D11-3 강등 오버레이(C-3, C-4, M-3, M-4, minor 9~14·20·21) — `app/facts_view.py` 단일 읽기 함수, human_check 0순위 후보(resolver), 해제 조건, 가격 대상 필드, GET은 DB 쓰기 금지, 실제 동작 테스트(spy 금지).
3. C-1 점수 입력은 그 스냅샷(리비전)의 벤치마크만 + minor 25; M-6 보고서도 동일.
4. D11-4(C-2, M-7, M-8, minor 18) + M-9 체크리스트(근거 사라짐·강등 시 닫기, 자동/사람 na 구별, 재포함 시 복원).
5. D11-2(M-10), D11-5 catalyst_link + `PATCH /catalysts/{id}` + catalyst expected_ym·lat·lon 필드 채움 경로, D11-6 할인, D11-7 지역 확장 API + §12, D11-8 백업 잡, M-1(사다리 숨김은 해당 시나리오 run 기준), minor 1·2·5·6·7·17·19(site URL 안전 정규화)·23·24.
6. RA 부분: trustee·officetel_units·options_text 파서, `archive.py` 연결 + 벤치마크 분양가 "자체 아카이브 공고 우선", §6-7 접근성(A·C에 공통 조건 AND, B·D 공급 경로 검사)·규제(재당첨·규제지역), 사다리 목표 계산 중복 제거(한 구현), D6 임계값 미전달 9개 도구 검사·서버 버전 변경 이벤트 테스트, D5 OCR 페이지당 30초 테스트(엔진 없으면 skip), human_check note·value_text 길이 제한+guard, 매니페스트 사유 재사용 금지(변경마다 새 사유), README 주인 검사 frontend·e2e 포함, devseed C 시나리오 정합.
7. 성능: `/complexes` size 1000을 0.5초 이하로(쿼리 최적화) — 경계 흔들림 근절.
완료: `uv run pytest -m "not live"` 실패 0(성능 포함, 부하 상태 2회), `python scripts/tasks.py regress` 통과, ruff·mypy, 마이그레이션 왕복, gen --check, fixtures --check. 리뷰 ID별 테스트 표.

=====FE=====
소유: `frontend/**`(단 `src/api/schema.d.ts`·`handlers.gen.ts`는 CORE 계약 .8 머지 후 재생성만), `e2e/**`.
- npm audit 37건(critical 2·high 13) 해소(의존성 갱신, 깨지면 고침); 최대 청크 1.1MB → 코드 분할(echarts 등)로 500kB 이하.
- FactCell 규칙 강화: `lib/format` 함수 결과를 JSX에 직접 쓰는 것도 금지(라벨 없는 숫자) — `market/index.tsx:198`, `dashboard/index.tsx:199-200`, `ops/JudgmentStatsPanel.tsx:172` 등 전부 FactCell(또는 명시적 "비수치 메타" 컴포넌트)로.
- `delta_rerank` 표시(G1 TOP5·G4 비교·G5 diff), C8 custom 라벨 시리즈, minor 15(PATCH /claims 뒤 캐시 무효화), 16(VITE_API_TOKEN 고려), T3 실데이터 문구 테스트(devseed 스위첸 403 → "확인 불가(403, 날짜)"), T18 배너 G1·스냅샷 degraded 테스트, `e2e/perf/t16.perf.ts` D10-8 기준(p50≤17·p95≤34).
- CORE의 계약 .8이 머지되면 받을 화면: HumanCheckForm 강등 필드 지정(M-5), catalyst 위치 확인 UI(D11-5), 지역 확장 UI(D11-7), 리비전 선택(SnapshotPicker에 리비전). — CORE 머지 전에는 계약 초안(`R3C_FIX.md` 아래 "계약 .8 초안")에 맞춰 MSW로 개발하고, 머지 후 gen 재생성.

=====SEC=====
소유: `backend/app/collectors/official_site/{egress,render}.py`, `backend/app/core/redact.py`, `backend/app/core/settings.py`(prod 가드만), `backend/app/judge/jev_mcp.py`(stderr 가림만), 해당 테스트.
- minor 26~30(egress 포트 검사·포트 허용 목록 80/443/8080?(공개 웹만: 80·443), 프록시 인증 토큰, IPv4/IPv6 순서(연결 시도 폴백), 락 밖 DNS), minor 22·31(redact 패턴), minor 32(판정기 자격 증명 env 목록을 Settings로 + stderr 가림), D11-9 prod+SQLite 거부, minor 33(0006 downgrade 손실 문서·재upgrade 경로 테스트 — 마이그레이션 파일 수정은 CORE 소유이므로 테스트·문서만, 수정 필요하면 CORE 요청).

## 계약 .8 초안 (CORE가 확정)
- `Snapshot.revision:int`, `GET /regions/{id}/snapshots` 리비전 포함, `?snapshot=`은 리비전 snapshot id.
- `HumanCheck.field` enum → 강등 가능한 (entity, field) 목록 + `entity_id`; `HumanCheck.note` maxLength 500, `value_text` maxLength 200.
- `PATCH /catalysts/{id}` `{location_confirmed, lat?, lon?, living_area_ids?, complex_ids?}` → `Catalyst` + links.
- `PATCH /regions/{id}` `{selections}` → `Region` + job(rejudge new revision).
- `payment_terms.discount_won`(타입별 json) / `PriceView.discount`.
- `catalyst.stage` enum에 '호재 아님'.
