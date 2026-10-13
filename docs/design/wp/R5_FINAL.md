# R5 최종 정리 — RA 100% 최종 감사(2026-10-13) 결과 보완. 결정 D25. critical 0, major 9, minor 다수.
감사 범위: WP0·계약·API·보안 / WP1–3 / WP4·7·8 / WP6·e2e / §9 T1–T18·게이트. 첫 GitHub CI(run 38326346203) 실패 2건 포함.
공통: 테스트 먼저(수정 전 실패 확인 표를 보고와 `docs/design/wp/R5_TESTS_<에이전트>.md`에), 계약 버전 `2026-10-09.18` 유지(계약 변경 금지 — 필요하면 보고에 요청으로), 키·비밀번호·접속 주소 값은 어디에도 출력·커밋 금지.

=====OPS (WP0·CI·core·api·scheduler/backup·infra·reports 테스트)=====
1. [CI 실패] `tests/contracts` PG 왕복: GitHub 리눅스에서 pgserver 소켓 연결 실패. CI는 postgres 서비스 컨테이너 + `TEST_POSTGRES_URL`로 돌린다(D25-8). 로컬 pgserver 경로는 유지.
2. [CI 실패] `tests/collectors/official_site/test_r3b_g1_render_sec.py::test_f1b_render_prod_refuses_allow_private`: CI에서 Settings 검증 오류 — 로컬 저장소 루트 `.env`(운영 Postgres 주소)에 기대 통과하던 테스트. 테스트가 `.env`·사용자 환경에 의존하지 않게 격리(필요하면 전역 fixture로 `.env` 읽기 차단)하고, 같은 의존이 다른 테스트에도 있는지 `.env` 없이 전체 스위트로 확인.
3. [major] 백업: `scheduler/backup.py`가 PATH의 `pg_dump`만 찾음 — 이 PC(D19)에는 PATH에 없어 매일 03:00 백업이 실패. `PG_DUMP_PATH` 설정(+`.env.example`)·테스트·runbook §8 D19 절. 운영 DB는 PG17이므로 PG17 `pg_dump`를 쓰는 절차.
4. [major] API가 판정기를 직접 부르지 않음(RA §1·규칙 4)을 강제하는 AST 경계 테스트: `app/api`·`app/main.py`가 어댑터(JevMcpAdapter·MockAdapter·base 전송)를 import하지 않고, `judge/` 밖에서 어댑터를 만들지 않음.
5. [minor] 공유 링크 TTL `le=30`. 마이그레이션 버전 파일이 `app`을 import하지 않음 AST 테스트(D14-9). Collector Protocol 적합성 parametrize 테스트(8개). pre-commit에 `tsc --noEmit`(typecheck) 훅. `backend/app/models/`·`contracts/`·`infra/` README "주인" 줄 + `test_repo_layout`. CI matrix의 빈 `models` 항목 정리.
6. [minor] 차트 리눅스 기준 이미지: CI 산출물 `chart-snapshots-linux`를 받아 커밋하고 CI가 `--update-snapshots` 없이 비교하게(D25-9). 보고서 ECharts 인라인 테스트가 CI에서 skip되지 않게(번들 준비 또는 CI에서 skip 금지).
7. [minor] fixture README 주의 7(세대수 확인 불가) 현행화. fixture_manifest가 CHANGELOG 과거 사유도 검사.
완료: `.env` 없는 환경(임시로 이름 바꾸지 말고 환경 격리로)에서 전체 pytest 실패 0, ruff·format·mypy, gen·fixtures --check, regress. GitHub CI 재실행은 CEO가 푸시로 확인.

=====PIPE (scheduler pipeline·inputs·judge·regress 테스트)=====
1. [major] P6 ladder(noul) 입력에 지역 벤치마크·정책 맥락·gap 누락(meta §2-1 P6): `scheduler/pipeline.py` P6 호출이 `benchmark_text`·`policy_text`·`gap`을 안 넘기고, `EvidenceCard`의 benchmark·supply·catalysts가 어디서도 채워지지 않음(`scheduler/inputs.py`). 채우고, noul·rerank·decide payload에 해당 맥락이 들어감을 단언하는 테스트. input_hash가 바뀌므로 Mock 녹화 fixture(`contracts/fixtures/.../judgments`)를 새 해시로 다시 매핑(응답 내용 동일, CHANGELOG 사유 기록). 운영 DB는 다음 실행에서 해당 도구 1회 전체 재판정이 일어남을 runbook에 적을 것.
2. [major 확인] D24-1 N16 수정(CORE11, main 머지됨)이 성공 경로에서만 체크리스트를 맞춤 — degraded·이월(carry) 발행 경로에서도 같은 날 daily가 이벤트 없이 체크리스트를 바꾸지 않는지 테스트로 확인하고 필요하면 고침.
3. [minor] P1 skip → 다른 purpose로 재screen(meta P1) 구현, 벤치마크 텍스트도 P1 통과. rerank 후보 > 250이면 `ValueError`로 잡 크래시 — 상한·분할 또는 실패 행으로. 파싱·저장 실패를 상태와 함께 행으로(규칙 7, `/ops/sources`에서 보이게; 계약 변경 없이 가능한 범위, 불가하면 요청).
4. [minor] T7 Σw·s 검사가 null 행만 있으면 공회전 — 최소 1행 검사 단언. T16 size 1000 첫 요청 검사 엄격화(min 대신 중앙값 등, 부하 내성은 유지).
완료: 전체 pytest 실패 0, ruff·format·mypy, gen·fixtures --check, regress(e2e 포함).

=====NORM (normalize·analysis)=====
1. [major] 이름 변경: 같은 `applyhome_id` 이름 변경 → `former_names`에 옛 이름, 행 id 불변, change_event 기록 테스트(구현 `normalize/store.py`).
2. [minor] 스캔 공고 → 해당 필드 '확인 불가(스캔)' 후보(지금은 후보 없음으로 하위 출처로 떨어짐). 선택품목 필수 공고에서 `options_required_won` 파싱 테스트(문구 보일러플레이트 오인 방지).
3. [minor, 골든 영향 규칙] RA §6-2: 신축 거래 1–2건·대체 단지 없음 → 라벨 '추정(표본 n)'. RA §6-7: A·C 접근 조건에 `intake_status ∈ {가능}` AND. **둘 다 먼저 회귀 골든(`expected_scores*.json`, T1·T2·T10·T11·T12)에 영향이 있는지 확인**: 영향 없으면 구현, 영향 있으면 구현하지 말고 영향 표를 보고(사람 확인 골든이라 CEO 결정 필요).
완료: 전체 pytest 실패 0, ruff·format·mypy, regress.

=====FE (frontend·e2e)=====
1. [major] `?scenario=`(·`snapshot=`)이 화면 이동(네비 링크, Top5 카드, 표 행)에서 유지되는 테스트.
2. [major] 차트 지연 로딩: 화면 밖 차트는 플레이스홀더(SVG 없음)였다가 스크롤 뒤 그려짐 테스트.
3. [minor] Lighthouse `TARGETS`에 G0(`/regions/new`)·G0-2 추가, 실측 1회 결과를 보고·`R5_TESTS_FE.md`에. 화면 문자열 `ko.json` 단일화 자동 검사(JSX 한글 리터럴 거부, 계약 enum·개발자 오류 메시지는 예외 목록). 트레이 6개 상한 테스트.
완료: typecheck·lint·vitest·build·audit·e2e·e2e:api 통과.
