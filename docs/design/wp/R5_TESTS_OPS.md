# R5-OPS — 최종 정리(OPS) 테스트·수정 전 실패 확인 (2026-10-13)

원문 `docs/design/wp/R5_FINAL.md` =====OPS, 결정 `docs/design/DECISIONS.md` **D25**(D25-1·D25-8·D25-9, D19-2). 브랜치 `wp/r5-ops`
(main `1dec271` 기준), 계약 **2026-10-09.18 그대로**(계약 파일 변경 없음). OPS 7(fixture README·fixture_manifest)은 PIPE 담당이라 손대지 않았다.

**방법.** 고치기 전에 테스트를 먼저 썼다(커밋 `e72e6c9 [R5-OPS] 테스트 먼저: …`). 끝에 `git archive 1dec271`(수정 전 저장소 전체)에 새 테스트·
바뀐 테스트만 얹어(공용 `tests/conftest.py` 는 수정 전 것 그대로 — 격리 없음) 한 번 더 돌린 실제 출력이 아래 "수정 전" 열이다(scratchpad
`r5ops/prefix_final.txt`, `import app` 이 수정 전 트리를 가리키는 것 확인). 환경은 CI 와 같은 `JUDGE_ADAPTER=mock`, `ENV_FILE` 은 없는 경로,
사용자 환경변수(판정기 키 이름 2개 — 값은 출력 안 함)는 그대로 두었다.

## 1. 항목별 수정·테스트·수정 전 실패

| OPS 항목 | 수정 | 테스트 | 수정 전(1dec271) 실제 실패 | 수정 후 |
| --- | --- | --- | --- | --- |
| **1** [CI 실패] `tests/contracts` PG 왕복 — 리눅스 pgserver 소켓 | 원인: `tests/contracts/conftest.py` 가 pgserver URI 를 `uri.rpartition('/')` 로 잘라 DB 이름을 바꿨다. 리눅스 URI 는 `postgresql://postgres:@/postgres?host=/tmp/…/pgdata0` 이라 마지막 `/` 가 소켓 폴더 경로 안에 있어 `host=/tmp/pytest-of-runner/pytest-0/contracts_test`(없는 폴더)가 됐다(CI 로그와 같은 경로). → `_support.pgserver_database_url`(SQLAlchemy `make_url().set(database=…)`) — 로컬 pgserver 경로 유지. CI 는 `backend-tests` 에 **postgres:16 서비스 컨테이너**(trust 인증, 비밀번호 없음) + `TEST_POSTGRES_URL`(D25-8). CI 에서 `TEST_POSTGRES_URL` 이 없으면 skip 이 아니라 실패 | `tests/contracts/test_r5_ops_contracts.py::test_pgserver_database_url_keeps_unix_socket_host` · `::test_pgserver_database_url_tcp` · `tests/core/test_r5_ci_layout.py::test_ci_backend_tests_use_postgres_service` | `ImportError: cannot import name 'pgserver_database_url'`(2건) · `AssertionError: backend-tests 에 postgres 서비스 없음`. 옛 식 재현: 위 리눅스 URI → `postgresql+psycopg://postgres:@/postgres?host=/tmp/pytest-of-runner/pytest-0/contracts_test` | 통과. 로컬 pgserver(Windows TCP)로 PG 왕복 테스트 전부 통과 |
| **2** [CI 실패] `test_f1b_render_prod_refuses_allow_private` — Settings 검증 오류 | 원인(CI 로그): `.env` 가 아니라 **워크플로 env `JUDGE_ADAPTER=mock`** 이 테스트의 `Settings(env='prod', …)` 로 새어 prod 가드(`ENV=prod 에서는 JUDGE_ADAPTER=mock 을 쓸 수 없다`)가 터졌다. 로컬은 그 env 가 없어 통과했다. 같은 종류 의존: 사용자 PC 의 판정기 키(`TYPESAFE_API_KEY`·`OPENROUTER_API_KEY`)가 테스트 프로세스·판정기 자식 env 에 보였고, `tests/reports/conftest.py` 만 세션 단위로 env 를 지워 **실행 순서에 따라** f1b 가 통과·실패했다(수정 전 트리에서 reports 테스트 뒤에 돌면 통과, 단독이면 실패 — 아래 표). → `tests/conftest.py` `pytest_configure`(`-m live` 제외): Settings 가 읽는 env 전부·`ENV_FILE`·판정기 자격 증명 이름을 지우고, `Settings()` 의 암묵적 `.env` 읽기(`model_config.env_file=None`)와 `ENV_FILE` 이 없을 때의 기본 경로(`settings.DEFAULT_ENV_FILE` → 없는 경로)를 막는다. `_env_file=`·`ENV_FILE` 명시 읽기는 그대로 | `tests/core/test_r5_ops.py::test_settings_env_vars_are_absent_during_tests` · `::test_cwd_dotenv_is_invisible_to_settings` · `::test_cwd_dotenv_is_invisible_to_judge_child_env` · `::test_explicit_env_file_still_works` · (CI 실패 그 테스트) `tests/collectors/official_site/test_r3b_g1_render_sec.py::test_f1b_render_prod_refuses_allow_private` | `테스트 세션에 새어 든 환경변수(이름만): ['ENV_FILE', 'JUDGE_ADAPTER', 'OPENROUTER_API_KEY', 'TYPESAFE_API_KEY']` · 작업 폴더 `.env` 를 읽음 `assert (7.0 == 1.0)` · 판정기 자식 env 에 `TYPESAFE_API_KEY` · f1b 단독(`JUDGE_ADAPTER=mock`): **`Value error, ENV=prod 에서는 JUDGE_ADAPTER=mock 을 쓸 수 없다(jev 만)`**(CI 와 같은 메시지, scratchpad `r5ops/prefix_f1b.txt`) | 통과. 적대적 환경 전체 스위트(§2)로 다른 의존 없음 확인 |
| **3** [major] 백업 `pg_dump` 가 PATH 만 — 이 PC(D19) 매일 03:00 실패 | `Settings.pg_dump_path`(`PG_DUMP_PATH` — 실행 파일 또는 bin 폴더, 큰따옴표 `.env` 로 생긴 제어 문자는 검증 오류). `scheduler/backup.resolve_pg_dump`: 설정이 있으면 그것만(없으면 실패 — PATH 의 다른 판으로 넘어가지 않음), 없으면 PATH. stats `db.pg_dump`·`db.pg_dump_version`(`--version`). `infra/.env.example`·runbook §8·§8-1(D19 PG17 절차·복구) | `tests/scheduler/test_r5_backup.py`(5) · `tests/core/test_r5_ops.py::test_pg_dump_path_setting` | `RuntimeError: DB 백업 실패: pg_dump 없음(PATH)`(PATH 에 가짜 '틀린 판'만 있어도 설정이 없어 그걸 씀 → `wrong.txt` 생김) · `'PG_DUMP_PATH' in env_var_names()` 실패 · runbook·.env.example 에 없음 | 통과. **실기 확인**(§3): 운영 DB(PG17) — `PG_DUMP_PATH` 없이 '`pg_dump 없음(PATH)`' 실패, PG17 bin 을 주면 성공(`pg_dump (PostgreSQL) 17.9`) |
| **4** [major] API 가 판정기를 직접 부르지 않음 — AST 경계 | (코드 위반 없음 — 테스트만). 예외 1건: `app/api/views.py` 가 옛 판정 행 재정규화에 `app.judge.jev_mcp.normalize`(순수 함수)만 지연 import — 이름 단위로만 허용하고 제안으로 남김 | `tests/api/test_r5_judge_boundary.py::test_api_does_not_import_judge_adapters`(api·main·serve: 어댑터 이름·`judge.mock`·`judge.base`·MCP SDK·`get_adapter`·`import_module` 우회) · `::test_no_adapter_construction_outside_judge`(judge 밖 생성·상속 0, `get_adapter` 는 scheduler 만) · `::test_api_process_does_not_load_adapter_modules`(새 프로세스에서 `create_app()` 뒤 `sys.modules` 에 어댑터 모듈·`mcp` 없음) · `::test_detector_catches_synthetic_violations`(음성 대조 10종) | 수정 전에도 통과(위반 없음 — 새 경계 고정). 음성 대조로 검사기가 공회전하지 않음을 확인 | 통과 |
| **5** [minor] 공유 링크 TTL `le=30` | `share_token_ttl_days: Field(ge=1, le=30)` | `test_r5_ops.py::test_share_token_ttl_days_is_capped_at_30` | `Failed: DID NOT RAISE ValidationError`(31일 허용) | 통과 |
| **5** 마이그레이션 ↛ `app`(D14-9) | (위반 없음 — 테스트만) | `test_r5_ops_contracts.py::test_migration_versions_do_not_import_app[0001…0016]`(16) · `::test_app_import_detector_catches_synthetic` | 수정 전에도 통과(위반 없음) | 통과 |
| **5** Collector Protocol 적합성(8개) | (위반 없음 — 테스트만) | `test_r5_ops.py::test_collector_conforms_to_protocol[applyhome·notice_pdf·official_site·rtms·stats_unsold·stats_households·news·reference]`(인자 이름·순서·타입 힌트 = Protocol, 인자 없이 생성, `isinstance(…, Collector)`, source_kind ⊆ 계약 enum) · `::test_every_collector_class_is_covered`(AST 로 `fetch(self, region, snapshot, since)` 클래스 전수 = 목록) | 수정 전에도 통과 | 통과 |
| **5** pre-commit `tsc --noEmit` 훅 | `.pre-commit-config.yaml` `typecheck`(`npm --prefix frontend run typecheck` = `tsc -b --noEmit`, frontend ts·tsconfig·`contracts/openapi*.yaml`) | `test_r5_ci_layout.py::test_precommit_has_typecheck_hook` · `test_repo_layout.py::test_precommit_config` | `pre-commit 에 typecheck(tsc --noEmit) 훅 없음` · `Extra items in the left set: 'typecheck'` | 통과 |
| **5** README 주인 줄 | `backend/app/models/README.md`(새, WP0) · `contracts/README.md`(WP0, fixtures 만 WP9) · `infra/README.md`(WP0) | `test_repo_layout.py::test_owner_lines[…]`(3) | `backend/app/models/README.md 없음` · `contracts/README.md 에 '주인' 줄 없음` · `infra/README.md 에 '주인' 줄 없음` | 통과 |
| **5** CI matrix 빈 `models` | matrix·`changes` 출력·필터에서 `models` 제거(`app/models` 는 `shared` 필터가 본다). `test_repo_layout` 의 기대 모듈도 `models` → `contracts` | `test_r5_ci_layout.py::test_ci_matrix_matches_backend_test_dirs`(matrix = 실제 `tests/<모듈>` − regress) | `tests/models 가 없다 — 빈 matrix 항목` | 통과 |
| **6** 차트 리눅스 기준 이미지(D25-9) | run 38326346203 산출물 `chart-snapshots-linux` 40장을 `frontend/tests/e2e/charts-gallery.spec.ts-snapshots/*-chromium-linux.png` 로 커밋(이름 = win32 40장과 1:1, 한글 글꼴 렌더 확인). CI `frontend-e2e` 는 `--update-snapshots` 없이 비교만, 기준 이미지가 없으면 실패. 옛 산출물 업로드 단계 삭제(실패 시 actual 은 기존 `frontend-e2e` 아티팩트 `test-results/`) | `test_r5_ci_layout.py::test_linux_chart_baselines_committed` · `::test_ci_compares_chart_snapshots_without_update` · (바뀐 기존) `test_r3_f3.py::test_minor2_ci_installs_chromium_and_runs_e2e`(D11-9 옛 규칙 '없으면 만들어 아티팩트' → D25-9) | `linux 기준 이미지 누락: ['C01-empty-chromium', …]` · `'--update-snapshots' is contained here` · (바뀐 기존 테스트) 같은 메시지 | 통과(CI 실행은 CEO 푸시로 확인) |
| **6** 보고서 ECharts 인라인 테스트 CI skip | CI `backend-tests` reports 잡에 `setup-node` + `frontend npm ci --ignore-scripts`(echarts 번들). `tests/reports/test_html.py`: 번들이 없을 때 `CI` 환경이면 **실패**, 로컬만 skip | `test_html.py::test_echarts_missing_bundle_fails_in_ci` · `test_r5_ci_layout.py::test_ci_reports_job_prepares_echarts_bundle` | `reports 에 Node 준비 없음`(CI 로그: reports 잡에서 이 테스트는 `echarts.min.js 없음` skip). `test_echarts_missing_bundle_fails_in_ci` 는 테스트 파일 자체가 수정이라 수정 전 열에서 통과 | 통과 |
| **7** fixture README·manifest | **하지 않음**(PIPE 담당 — 지시) | — | — | — |

수정 전 합계(`prefix_final.txt`, 새·바뀐 테스트 파일 + f1b): **실패 23 · 통과 101 · skip 1**. 수정 전에도 통과한 새 테스트는 경계·적합성
테스트(OPS 4·5 — 코드 위반이 없어 고정만)와 테스트 파일 자체가 수정인 ECharts CI 검사뿐이다. f1b 는 그 묶음 안에서는 reports conftest 가 env 를
지운 뒤라 통과했고, 단독 실행에서 CI 와 같은 오류로 실패했다(위 2행).

## 2. 전체 스위트 — `.env`·사용자 환경 없이(격리로)

`.env` 는 이름을 바꾸거나 고치지 않았다. 이 worktree 에는 `.env` 가 없고, 아래 두 실행 모두 `ENV_FILE` 을 직접 지정했다.

| 실행 | 환경 | 결과 |
| --- | --- | --- |
| 수정 전 코드(1dec271, 실행 도중 이 브랜치의 ci.yml 이 바뀐 구간 있음 — 참고용) | CI 흉내: `JUDGE_ADAPTER=mock`, 사용자 판정기 키 제거, `ENV_FILE`=없는 경로 (`run_ci_env.sh` → `before_full_ci_env.log`) | **4 실패** · 3954 통과 · 5 skip (50분): `test_f1b_render_prod_refuses_allow_private`(**CI 와 같은 실패 재현**) · `test_perf_r3c.py::test_cold_size1000_published_under_0_2s`(부하 — 중앙값 0.206s > 0.2s, 다른 에이전트 스위트와 동시) · `test_r3_f3.py::test_minor2_…`·`test_repo_layout.py::test_ci_workflow`(실행 중에 이 브랜치가 ci.yml 을 바꿔 옛 테스트가 새 ci.yml 을 읽음 — 오염, 수정 후 둘 다 갱신·통과). 그 밖의 `.env`·env 의존 실패 없음 |
| **수정 후**(`8ac4b42`) | **적대적**: `ENV=prod`·`DATABASE_URL`=가짜 Postgres·`JUDGE_ADAPTER=mock`·`API_TOKEN`·`DATA_GO_KR_KEY`·`NEWS_API_KEY`·`HTTP_RATE_PER_HOST=7`·`SHARE_TOKEN_TTL_DAYS=99`·`OPENROUTER_API_KEY` 를 프로세스 env 에, `ENV_FILE`=가짜 운영 `.env`(가짜 Postgres 주소·prod) (`run_hostile_env.sh` → `after_full_hostile.log`) — 격리가 하나라도 새면 Settings 생성부터 실패한다 | 1 실패 · **4010 통과** · 5 skip (46분). 실패 1 = `test_r3f_perf_publish.py::test_d14_5_publish_job_1000x5_under_30s…`(`잡 34.4s > 30.0s` — 부하). **같은 적대적 환경에서 성능 테스트 2파일 단독 재실행 5/5 통과**(`after_perf_rerun.log`). → `.env`·사용자 환경 의존 0 |

skip 5 는 두 실행이 같다: `rapidocr` 미설치 3(OCR 선택 의존성), `R4_REPLAY_MANIFEST` 없음 2(로컬 전체 재생 — 의도된 선택 실행).
`-m live` 13 은 deselect(실제 외부 접속).

## 3. 백업 실기 확인 (D19 운영 DB, 읽기만)

`load_settings(<메인 체크아웃>/.env)` 로 운영 설정을 읽어(값 출력 없음 — `DATABASE_URL` 이 Postgres 인지 여부만) `run_backup` 을 scratchpad 로
두 번 돌리고 덤프는 지웠다(`r5ops/backup_smoke.py`):

```
db_is_postgres: True | PG_DUMP_PATH set in .env: False
without_PG_DUMP_PATH -> FAILED: DB 백업 실패: pg_dump 없음(PATH) — PG_DUMP_PATH 에 서버와 같은 판 pg_dump 를 적는다(runbook §8)
with_PG_DUMP_PATH_pg17_bin -> OK kind=postgres size_bytes=147647 version=pg_dump (PostgreSQL) 17.9
```

**사람/CEO 할 일**: 운영 `.env` 에 `PG_DUMP_PATH=C:\Program Files\PostgreSQL\17\bin\pg_dump.exe`(따옴표 없이)를 넣고 worker 재시작
(`.env` 는 이 라운드에서 건드리지 않았다). 큰따옴표로 감싸면 `\b` 가 백스페이스로 읽혀 경로가 깨진다 — 이제 설정 검증 오류로 바로 드러난다.

## 4. 완료 기준 실행 기록 (브랜치 끝, scratchpad 로그)

| 명령 | 결과 |
| --- | --- |
| `uv run pytest -p no:randomly -m "not live"` (적대적 env, §2) | 4010 통과 · 실패 1(부하 성능 — 단독 재실행 통과) · skip 5 |
| `uv run ruff check app tests` · `ruff format --check app tests` · `mypy app` | 통과 · 485 files already formatted · `Success: no issues found in 167 source files` |
| `uv run python scripts/gen_contracts.py --check` · `scripts/fixture_manifest.py --check` | 0 · 0 |
| `npm --prefix frontend run typecheck`(새 pre-commit 훅의 명령) | 0 |
| `python scripts/tasks.py regress` | **통과** — T01~T18·모듈 analysis·fixtures_contract(608)·흐름 2 + e2e 흐름 3 전부 PASS, 단계 종료 코드 [0, 0] |
| GitHub CI | 재실행은 CEO 푸시로 확인(이 브랜치는 푸시하지 않음) |

## 5. 남은 것·제안

- 운영 `.env` 에 `PG_DUMP_PATH` 한 줄(§3) — 사람/CEO. 넣기 전까지 운영 03:00 백업은 계속 '`pg_dump 없음(PATH)`' 로 실패한다(이제 사유가 설정 이름을 안내).
- (WP3 제안) `judge/jev_mcp.normalize` 를 어댑터 모듈 밖(`judge/normalize.py`)으로 옮기면 API 의 지연 import 예외(§1 OPS-4)가 없어진다.
- (WP6 제안) `frontend/src/charts/README.md` 의 "기준 이미지는 win32. 갱신은 `--update-snapshots`" 문구에 linux 기준 이미지(CI 비교, D25-9) 갱신 절차를 더한다.
- `tests/reports/conftest.py` 의 세션 env 지우기는 이제 공용 격리와 겹친다(무해 — 지우지 않았다).
- CI postgres 서비스는 `backend-tests` matrix 모든 모듈에서 뜬다(서비스는 조건부로 끌 수 없음 — 수 초 비용). Postgres 를 쓰는 것은 `tests/contracts` 뿐이다.
