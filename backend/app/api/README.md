# app/api

- **주인**: WP5
- **읽기 허용**: WP6 (계약 `contracts/openapi.yaml` 으로만)
- 쓰기 금지 이유(RA §2): —

## 범위 (RA §2·§4·§5, DECISIONS D2-3·D4)

`contracts/openapi.yaml` 의 operation 31개 중 `/health`(app.main, WP0)를 뺀 30개를 그대로 구현한다.

| 모듈 | 내용 |
| --- | --- |
| `routers/regions.py` | `GET/POST /regions`, `/regions/resolve`(normalize.region_resolve), `GET /regions/{id}`, `PUT …/living-areas`(normalize.living_area, 422 = 누락·중복·지역 밖), `GET …/snapshots` |
| `routers/snapshots.py` | 대시보드(G1, KPI 5·TOP 5·변경·미분양 24개월), 단지 표(G2, 필터·정렬·페이지)·CSV(BOM, `<열>_label`·`<열>_checked_at`), 변경 피드 |
| `routers/complexes.py` | 단지 상세(G3), 출처 패널(`fp_ sc_ st_ jl_ hc_ rd_ cs_`), 원문 파일(`?as=text`) |
| `routers/analysis.py` | 비교(G4, DecisionSet), 민감도(저장된 score_component 로 `analysis.sensitivity` 계산 + 단지 이름), 시나리오 목록·저장·미리보기 |
| `routers/market.py` | 지역 시장(G6): 벤치마크·입주 물량·미분양·호재·규제 카드·생활권 시세 |
| `routers/jobs.py`, `jobs.py` | `job_run` 등록(payload = job_payloads 스키마 검증)·조회. **api 는 판정기를 부르지 않는다** |
| `routers/ops.py` | 소스 상태, 판정기 호출 집계, 체크리스트, 사람 확인(T3: intake 행 + change_event critical + rejudge 잡 제안) |
| `routers/reports.py` | 보고서 = `report` 잡(id = job_run.id), contradicted claim 있으면 409 publish_blocked, 완료 파일 다운로드 |
| `deps.py` | Bearer 인증(쓰기 = API_TOKEN, 읽기 전용 = READONLY_TOKEN → GET 만, 그 밖 403), 계약에 없는 조회 파라미터 거부, 스냅샷(최신 published → ready)·시나리오(code 또는 id) 해석 |
| `facts.py` | Fact 래핑(T13): field_provenance chosen 행 → `{v, label, prov, checked_at}`. 값은 있는데 출처 행이 없으면 ENV=dev `contract_violation`(500), prod `확인 불가(출처 누락)` + 경고 로그 |
| `views.py` | DB 행 → 응답 모양. 목록은 관련 행을 한 번에 읽고 페이지 안만 Fact 로 만든다(T16: 1,000단지 첫 페이지 < 1초) |
| `reason_codes.py` | 계약 .20(D28-5 Q5): '확인 불가'·접수 사유 문자열 → `ReasonCode`(머리말·낱말 규칙 — 판단 아님). `facts.unknown`·접수 행·대기열이 같은 함수 |
| `change_text.py` | 계약 .20(D28-5 Q5): 변경 피드 `field_label`·`summary`·`value_kind`(필드 이름 표 + 값 모양 — 해시는 접는다, 원값 그대로) |
| `contract.py` | `contracts/openapi.bundled.yaml` 로 요청 본문 검증(JSON Schema 2020-12 + 형식), 문서화된 상태 코드 조회 |
| `errors.py` | 모든 오류 본문 = 계약 `Error`. 요청 검증 실패는 그 operation 이 422 를 문서화했으면 422, 아니고 404 만 있으면 404 |
| `devseed.py` | 개발·e2e 픽스처 적재(아래) |

## 연결 (WP0 뼈대와의 접점)

- `app/api/__init__.py` 의 `router` 를 `app.main.create_app()` 이 `API_PREFIX`(기본 `/api`) 아래에 붙이고,
  `install(app)`(오류 처리기·끝 슬래시 리다이렉트 끔)을 부른다 — `app/main.py` 에 그 호출 1줄을 더했다(WP5 R2).
- DB 세션: `Depends(app.core.db.session_dependency)`, commit 은 쓰기 라우터가 명시적으로 한다.
- 두 토큰이 모두 비어 있으면(개발 기본값) 인증 없이 연다. ENV=prod 는 설정 검증이 API_TOKEN 을 강제한다.

## Fact·출처 규칙 (요약)

- 사실 테이블 값의 출처 키 = `field_provenance(entity, entity_id = 행 id, field = 컬럼 이름, chosen = true)` (WP2 와 같음).
  json 목록 컬럼(`apply_dates`·`contract_dates`·`interim_schedule`)은 필드 하나에 출처 행 하나, 공고별 가격은
  `price_by_type.<type>.<항목>`, 시장 원자료는 `benchmark`·`supply`·`unsold`(`total`·`post_completion`)·`rtms_trade.price_won`.
- 산술 값(현재 구매가 범위·중앙, 전매 종료일, 계약금 금액, 필요 자기자본)은 라벨 `추정`(reason `산술`), prov = 첫 원천.
  원천 하나라도 `확인 불가`면 그 사유로 `확인 불가`.
- 점수 `sc_<run>_<complex>_<component>`·`st_<run>_<complex>`, 판정기 값 `jl_<seq>`(라벨 추정), 사람 확인 `hc_<id>`,
  원문 `rd_<id>`, 비교군 `cs_<id>`.
- `judge_scope`(판정 대상/보류/참고/제외) = 점수 실행이 저장한 `score_total.judge_scope`(계약 2026-10-09.3, WP7 — 그
  스냅샷의 마지막 run). 저장 값이 없을 때만(제외 단지·점수 전 스냅샷·옛 행) 사실 규칙: 제외 = 포함/제외 분류 제외·범위 경계,
  보류 = 판정 기준 타입 가격 없음, 그 밖 = 판정 대상(사다리로 '참고'를 추정하지 않는다).
- 시나리오 미리보기 `cache_hits`·`cache_misses`·`calls_by_tool` = `app.scheduler.payloads.scenario_payloads`(재판정 때
  파이프라인이 보낼 noul·rerank·decide payload)의 input_hash 마다 judgment_log 최종 행이 있는지(같은 입력 재호출 금지 규칙).
  adapter_version 은 마지막 judgment_log 행의 값. 앞 단계(noul·rerank)가 미스면 decide 도 미스로 센다.
- 판정 봉투 `result`: judgment_log.result_json(계약 2026-10-09.3). NULL 인 옛 행만 `judge.jev_mcp.normalize` 로 다시 만든다.

## devseed — DB 가 비어 있어도 화면 연결

```bash
cd backend
uv run python -m app.api.devseed                    # DATABASE_URL(SQLite)을 지우고 인천·김포 픽스처로 다시 만든다
uv run python -m app.api.devseed --reference full   # 법정동 전국(기본 region = 픽스처 지역 시도만, none = 생략)
uv run python -m app.api.devseed --synth 1000       # + T16 합성 단지 1,000개
uv run uvicorn app.main:app --port 8000
```

적재: 참조(legal_dong·admin_dong·매핑, `contracts/fixtures/reference/`), 내장 시나리오 5, `region.json`·`snapshots.json`
(11·12), 원문 67건(파일은 RAW_DIR 로 복사), 단지 16(+ Fact 마다 출처 행), 판정 녹화 132건(judgment_log, 판정기 호출 없음),
사다리·호재·decide, 점수(`expected_scores_v2.json` 입력 + `expected_scores.json` (a)단계 고정 성분 → 내장 시나리오 5개
run — 기본 상황 TOP 5 = RA §9 T1), 시장 원자료, 변경·체크리스트(`contracts/examples`). 운영 DB 에는 쓰지 않는다(SQLite 전용).

## 테스트

```bash
uv run pytest tests/api                       # 계약(schemathesis)·인증·T3·T13·T16·엔드포인트
ST_MAX_EXAMPLES=300 uv run pytest tests/api/test_schemathesis.py   # 깊게
cd ../frontend && npx playwright test -c e2e/api                     # MSW 끄고 실제 API(devseed)로 G1·G2·G3
```

## 규칙

- 이 디렉터리와 `backend/tests/api/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15).
