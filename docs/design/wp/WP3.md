# WP3 판정기 어댑터 — 작업 지시

소유: `backend/app/judge/`, `backend/tests/judge/`, `docs/adr/ADR-05-judge-smoke.md`.
참조: RA §3 `judgment_log`·`claim`, §4-1 JudgmentEnvelope, §4-3 `JudgeAdapter`·`ClaimSplitter`, §5 WP3 카드, §6-3, §6-5, §6-7, §9 T6·T7·T10·T14·T17·T18; meta §2-1(P1~P9), §2-2(명제 템플릿); **DECISIONS D6가 RA보다 우선**(임계값을 넘기지 않음, serverInfo.version → adapter_version, `@jkudish/jev-mcp@latest`).

## 할 일
1. `base.py`, `jev_mcp.py`(python `mcp` SDK stdio 클라이언트로 `JEV_MCP_CMD` 실행; 실제로 한 번 띄워 `tools/list`로 각 도구의 입력 스키마·응답 형식을 확인하고 `tests/judge/fixtures/jev_tools.json`에 저장; 도구 9개 매핑; 응답의 auto/review/escaped 등 → 봉투 status 매핑; 타임아웃·프로세스 사망 → `JudgeUnavailable`), `cache.py`(input_hash = sha256(canonical JSON{tool, purpose, payload, adapter_version}); 호출 전 `judgment_log` 조회 → cached 봉투), `log.py`(성공·실패·blocked 전부 행; 로그엔 hash·길이만), `mock.py`(픽스처 재생: input_hash로 찾고 없으면 status=review), `claims.py`(원자 분할), `payloads.py`(증거 카드 ≤2,000자, 사다리 명제 3 horizon × 4, decide 후보 ≤6 + 요건 사전 계산 문자열, rerank 전체 후보 1회), `guard.py`(전화번호·주민번호·이메일·설정 비밀값 → 거부 + status=blocked 행; `app.core.redact` 재사용 가능), `pipeline.py`(P1~P9 단계별: 입력 생성 → 어댑터 호출 → claim/ladder/decision 행 데이터로 변환. 전체 순서 실행은 WP7이 부른다).
2. 공개 텍스트만 나간다.

## 완료 기준
- [ ] Mock 재생 시 봉투 동일
- [ ] 같은 payload 2회 → 실제 호출 1회, 두 번째 cached=true (T17)
- [ ] "3개는 unlikely이고 나머지는 uncertain" → 주장 ≥2개; 복합 문장 그대로 verify로 가면 실패하는 테스트 (T6)
- [ ] guard → 거부 + blocked 행 + 로그에 원문 없음 (T14)
- [ ] 사다리 명제 3 horizon, `asof_plus_3y` 목표 시점이 단지 무관 동일 (T10)
- [ ] rerank 후보 변경 → 전체 1회 재호출 payload (T7)
- [ ] JudgeUnavailable 경로 (T18)
- [ ] serverInfo.version 변경 → input_hash 변경
- [ ] JEV 실제 연결 smoke 1회(`@pytest.mark.live`) — 실행 결과(도구 목록·버전·소요)를 `docs/adr/ADR-05-judge-smoke.md`에
