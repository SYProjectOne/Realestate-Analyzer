# ADR-05 판정기 연결

- 상태: 채택, 실행·임계값은 DECISIONS D6 로 변경 (RA v1 §1)
- 결정: **`JudgeAdapter` Protocol + `JevMcpAdapter`(stdio MCP) + `MockAdapter`(픽스처 재생)**
- 버린 대안: HTTP 래퍼 서버

## 이유

- 오프라인 테스트와 판정기 교체를 같은 인터페이스로 한다.
- 호출 전 입력 해시 캐시는 어댑터 바깥(`judge/cache.py`)에 둔다 → "같은 입력 재호출 금지"를 코드가 강제.

## 변경 (D6)

- 실행 명령 기본값 `JEV_MCP_CMD="npx -y @jkudish/jev-mcp@latest"` — worker 이미지에 Node 포함(`infra/Dockerfile.worker`).
- 어댑터는 임계값을 넘기지 않는다(JEV 기본값). 도구가 돌려준 임계값·결정은 `judgment_log.output_json` 에 그대로 저장.
- `adapter_version = "<어댑터 코드 버전>+jev-mcp@<서버 버전>"` → 서버 버전이 바뀌면 전체 재판정 1회(runbook §4).

## 결과

- 선택: `JUDGE_ADAPTER=jev|mock` (테스트는 mock).
- 보안: payload 는 `judge/guard.py` 통과 필수(`core.redact` 패턴 재사용 가능). 로그는 `core.logging.log_payload_meta`
  (input_hash·길이만).

## 바꿀 신호

JEV 가 HTTP 를 제공할 때.
