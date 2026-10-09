# app/judge

- **주인**: WP3
- **읽기 허용**: WP4, WP7
- 쓰기 금지 이유(RA §2): 판정 로직을 다른 곳에서 흉내 내면 "같은 입력 재호출 금지"가 무너진다

## 범위 (RA §2·§5, DECISIONS D6)

판정기 어댑터: `base.py`(Protocol·봉투), `jev_mcp.py`(stdio MCP, 실행 명령 `settings.jev_mcp_cmd`), `mock.py`,
`cache.py`(input_hash), `log.py`, `claims.py`(원자 분할), `payloads.py`, `guard.py`.
판정기를 직접 부르는 코드는 이 디렉터리 밖에 없다(규칙 4).

- 어댑터 선택: `settings.judge_adapter` (`jev` | `mock`, 테스트는 mock).
- 임계값은 넘기지 않는다 — JEV 기본값을 따른다(D6).
- `guard.py` 는 `app.core.redact.find_sensitive(text, secrets=settings.secret_values())` 를 재사용할 수 있다
  (전화·주민번호·이메일·환경변수 값).
- 로그는 `app.core.logging.log_payload_meta(input_hash, length, tool=…, cached=…)` 만 쓴다(규칙 13).
- 정규 JSON 은 `app.core.snapshot.canonical_json`.

## 규칙

- 이 디렉터리와 `backend/tests/judge/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15).
