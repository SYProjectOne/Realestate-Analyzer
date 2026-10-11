# ADR-05 부록 — JEV 실제 연결 smoke (WP3, R1)

- 일시: 2026-10-09 (Windows 11, Node 24.19.0, python `mcp` 2.3.0)
- 명령: `JEV_MCP_CMD="npx -y @jkudish/jev-mcp@latest"` (DECISIONS D6 기본값)
- 재현: `cd backend && uv run pytest -m live tests/judge/test_live.py -s` → `JEV_SMOKE {...}` 한 줄 출력

## 결과

| 항목 | 값 |
| --- | --- |
| `initialize.serverInfo` | `jev-mcp` **0.14.1** (protocol 2025-11-25) |
| adapter_version | `0.1.0+jev-mcp@0.14.1` |
| 응답의 `model` | `jev-1.13.0` (`JEV_MCP_MODEL` 미설정 → `jev-latest`) |
| tools/list | 12개: `jev_audit, jev_classify, jev_compare, jev_decide, jev_extract, jev_find, jev_gate, jev_noul, jev_rerank, jev_review, jev_screen, jev_verify` — 계약 9개 모두 있음, find·gate·review 미사용 |
| 기동(initialize+tools/list) | 8.6초 (npx 캐시 있음, 첫 실행은 더 김) / 별도 측정 1.8초 |
| 실제 호출(어댑터 전체 경로, screen 1건) | 343ms, status=ok, verdict=pass, 같은 입력 2회째 cached=true(판정기 호출 없음) |
| 도구별 형식 확인 호출(합성 공개 텍스트, 도구당 1회) | 187~297ms |

도구 입력 스키마 전부와 initialize 응답은 `backend/tests/judge/fixtures/jev_tools.json`,
도구별 실제 응답은 `backend/tests/judge/fixtures/jev_samples.json`에 저장했다(테스트가 이것으로 payload 모양과
정규화를 검증한다).

## 응답에 담겨 오는 기본 임계값 (어댑터는 넘기지 않음, D6)

| 도구 | 기본값 (응답의 `thresholds` 등) |
| --- | --- |
| screen | block_at 0.75 · review_at 0.25 |
| extract · classify · compare | auto_accept 0.85 · minimum_margin 0.5 |
| noul | auto_accept 0.85 |
| audit | wrong_at 0.7 |
| verify | auto_accept 0.8 · subject_at 0.5 |
| decide | 임계 인자 없음(escape hatch 기본 on) |

## 확인한 연결 사실 (구현에 반영)

1. **자격 증명 전달**: python `mcp` 의 `stdio_client`는 자식 프로세스에 PATH 등 기본 변수만 넘긴다.
   JEV 는 `TYPESAFE_API_KEY`(또는 OPENROUTER·Cloudflare·AI Gateway 키)가 있어야 판정한다 → `jev_mcp.subprocess_env()`가
   `JEV_*`·`TYPESAFE_*`·`OPENROUTER_*`·`AI_GATEWAY_*`·`CLOUDFLARE_*`·`NODE_*`·프록시 변수만 골라 넘긴다
   (`DATA_GO_KR_KEY` 등 이 프로그램의 비밀값은 넘기지 않는다). 그 값들은 guard 의 비밀값 목록에도 들어간다.
2. **입력은 strict**: 모르는 인자는 거부된다 → 우리 메타(시점·단지 id)는 payload 가 아니라 purpose 키와 후보 id 에 담는다.
3. **결과 형식**: 모든 도구가 `content[0].text` 에 JSON 문자열 하나(structuredContent 없음). 실패는 `isError=true` +
   `{"tool", "error"}` 또는 SDK 검증 메시지 → 어댑터는 error 행 + `JudgeUnavailable`.
4. **decide 후보 id 는 slug**(`^[a-z][a-z0-9_-]*$`) → `complex_<id>` 로 보내고 결과에서 `complex:<id>` 로 되돌린다.
5. **Windows**: `npx` 는 `shutil.which` 로 `npx.cmd` 경로를 찾아 실행한다.

## 남은 위험

- `jev-latest` 모델이 바뀌어도 serverInfo.version 은 그대로일 수 있다 → input_hash 가 안 바뀌어 재판정이 일어나지 않는다.
  모델 버전은 각 응답의 `model` 로만 보인다(output_json 에 남음). 고정하려면 `JEV_MCP_MODEL` 을 명시하거나
  adapter_version 에 모델을 넣는 계약 변경이 필요하다(완료 보고 '제안').
- pyproject 는 `mcp>=1.2` 인데 lock 은 2.3.0(대규모 API 변경판)이다. 어댑터는 `server_info`/`serverInfo` 둘 다 읽지만
  `mcp>=2,<3` 고정을 제안한다.

## R4 실데이터 실행 (2026-10-12)

결과는 [`docs/design/wp/R4_RESULT.md`](../design/wp/R4_RESULT.md)·runbook §10-6. 요점: jev-mcp 0.14.1 은 `jev_extract` 가 모델을 부르지
않는 경로(provider none)에서 `model: "jev-latest"`, 그 밖에는 `"jev-1.13.0"` 을 준다 — 응답 모델을 adapter_version 에 넣는 위 보강(D6)
때문에 버전이 호출마다 바뀌어 2회차에 숨은 실제 호출이 생긴다(R4 결함 C1).
