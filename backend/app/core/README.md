# app/core

- **주인**: WP0 (WP0-B 뼈대: 아래 모듈 / WP0-A 계약: `protocols.py`, `contracts_gen.py`)
- **읽기 허용**: 전체
- 쓰기 금지 이유(RA §2): 공통 도구가 바뀌면 병렬 중인 모든 WP가 깨진다. 필요한 변경은 요청으로 남긴다.

| 모듈 | 내용 |
| --- | --- |
| `settings.py` | pydantic-settings. RA §10 환경변수 전부(+`RAW_DIR`, `REFERENCE_DIR`, `REPORT_DIR`, `TZ`, `HTTP_*`, `JUDGE_CALL_TIMEOUT_S`·`JUDGE_START_TIMEOUT_S`). 비밀값은 `SecretStr`, `Settings.secret_values()`. 테스트는 `set_settings()` |
| `db.py` | `get_engine()`, `get_session()`(컨텍스트: commit/rollback), `session_dependency`(FastAPI), `ping()`, `load_metadata()`(`app.models` 지연 import). SQLite = WAL·foreign_keys·busy_timeout + pysqlite BEGIN 끔·`begin` 이벤트가 BEGIN(SAVEPOINT·`begin_nested()` 정상), Postgres = pool |
| `http.py` | `HttpClient`/`AsyncHttpClient` → `FetchResult{url, status, headers, content, error, error_kind, elapsed_ms, attempts, blocked_by_robots, robots_status, robots_error_kind, robots_error, final_url, fetched_at}`(+`robots_reason`). 호스트별 속도 제한, 5xx·타임아웃·연결 오류만 지수 백오프 재시도, robots.txt(RFC 9309) 캐시 — `HTTP_ROBOTS_EXEMPT_HOSTS`(키 인증 공식 API)는 robots 검사 예외. 예외를 던지지 않는다 |
| `logging.py` | `configure_logging()` JSON 한 줄 로그 + 마스킹, `log_payload_meta(input_hash, length, **짧은 메타)` |
| `redact.py` | `find_sensitive`/`contains_sensitive`/`redact_text`/`redact_obj` — 전화·주민번호·이메일·비밀값(URL 인코딩 포함)·URL 키 파라미터 |
| `time.py` | `KST`, `now_kst()`, `today_kst()`(기준일), `d_day()`, `format_d_day()` → `D-3`/`D-day`/`D+2` |
| `paths.py` | `raw_path(source, day, sha256, ext)` = `{RAW_DIR}/{source}/{yyyy-mm-dd}/{sha256}.{ext}` (ADR-8), `raw_relpath`, `resolve_raw_path`(경로 탈출 차단) |
| `snapshot.py` | `sha256_*`, `canonical_json`, `base_date()`, `store_raw()`(원자적·멱등 저장) |

공용 테스트 fixture(`backend/tests/conftest.py`): `test_settings`, `raw_dir`, `db_engine`, `db_session`.
테스트: `backend/tests/core/`.
