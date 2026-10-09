# app/judge

- **주인**: WP3
- **읽기 허용**: WP4, WP7
- 쓰기 금지 이유(RA §2): 판정 로직을 다른 곳에서 흉내 내면 "같은 입력 재호출 금지"가 무너진다

## 범위 (RA §2·§5, DECISIONS D6)

판정기 어댑터: `base.py`(CachedJudgeAdapter: guard → hash → 캐시 → 호출 → 행), `jev_mcp.py`(stdio MCP 전송 +
JEV 응답 정규화, 실행 명령 `settings.jev_mcp_cmd`), `mock.py`(녹화 재생), `cache.py`(input_hash 조회), `log.py`,
`claims.py`(원자 분할), `payloads.py`(P1~P9 입력), `guard.py`, `pipeline.py`(P1~P9 단계 함수 → LadderRow·
RerankAnchor·DecisionSet·Claim). 판정기를 직접 부르는 코드는 이 디렉터리 밖에 없다(규칙 4).

- 어댑터 선택: `app.judge.get_adapter(settings, fixture_dir=…)` — `settings.judge_adapter` (`jev` | `mock`).
- 행에 snapshot·complex 를 남기려면 `adapter.call(tool, payload, purpose, snapshot_id=…, complex_id=…)`.
- 실제 연결 smoke 결과·JEV 응답 형식: `docs/adr/ADR-05-judge-smoke.md`, `tests/judge/fixtures/`.
- 임계값은 넘기지 않는다 — JEV 기본값을 따른다(D6).
- `guard.py` 는 `app.core.redact.find_sensitive(text, secrets=settings.secret_values())` 를 재사용할 수 있다
  (전화·주민번호·이메일·환경변수 값).
- 로그는 `app.core.logging.log_payload_meta(input_hash, length, tool=…, cached=…)` 만 쓴다(규칙 13).
- 정규 JSON 은 `app.core.snapshot.canonical_json`.
- 계약 2026-10-09.3: 정규화 결과는 `judgment_log.result_json`(캐시 봉투도 그것을 쓴다, NULL 옛 행만 재정규화).
  접수 상태 분류 `pipeline.p4_classify_intake`(4클래스 open/pending/closed/unknown → 가능/미정/불가/확인 불가,
  미해결 = '확인 불가(판정 미해결)'), 포함/제외 배치 `p4_classify_inclusion_batch`(≤64개 1회),
  "남은 contradicted" 단일 정의 `claims.remaining_contradicted`(WP7 publish·WP8 보고서 공용).

## 규칙

- 이 디렉터리와 `backend/tests/judge/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15).
