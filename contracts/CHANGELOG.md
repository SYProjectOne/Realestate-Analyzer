# 계약 변경 기록

버전 = `날짜.연번`. 에이전트는 **맨 위 항목 하나만** 가정한다(AGENTS.md). 계약을 바꾸는 쪽은 오케스트레이터뿐이다.

## 2026-10-09.2

R1 계약 변경 요청 일괄 반영(`docs/design/wp/CONTRACT_CHANGES_R1.md` 승인 목록 전부 + CEO 추가 승인 4건). 마이그레이션 `0002_r1`
(컬럼 추가만, 모두 NULL 허용 — 0001 DB 는 `alembic upgrade head` 한 번). 필드 삭제·의미 변경 없음(AuditItem.p_wrong 의 null 허용만 넓힘).

### 요청별 반영

| # | 출처 | 대상 | 변경 | 영향 WP |
| --- | --- | --- | --- | --- |
| 1 | WP4 #1 | `schemas/score_inputs.json` LivingAreaScoreInput | `unsold_scope_codes: string[]`(기본 []) — 생활권 ↔ 미분양 scope_code(시군구 5자리). 비면 '지역 합계' | WP7(채움), WP4(사용 — 이번에 반영) |
| 2 | WP4 #2 | ComplexScoreInput | `intake_checked_at`(ISO, 날짜만 허용) | WP7, WP4(근거 문구 — 반영) |
| 3 | WP4 #3 | ComplexScoreInput | 공고 필드 라벨 `down_payment_label`·`resale_label`·`residency_label`(Label\|null) | WP7, WP4(확인 불가 처리 — 반영) |
| 4 | WP2 #1 | `schemas/field_candidate.json` | entity enum 에 `intake_status`(field='status_text', 문구 후보 — 분류는 판정기/사람) | WP2, WP7 |
| 5 | WP2 #2 | FieldCandidate · ProvenanceRow | `observed_on`(원문 시점, 공고일) + `field_provenance.observed_on` String(10) | WP2 |
| 6 | WP2 #3 | ProvenanceRow · `field_provenance` | `value_norm`(정규화 값 정준 문자열, Text) | WP2 |
| 7 | WP2 #4 | `schemas/complex_type.json` · `complex_type` | `notice_type_code`(공고상 주택형 원문 '084.9582A', String(32)) | WP2, WP5 |
| 8 | WP2 #5 | `schemas/payment_terms.json` · `payment_terms` | `price_by_type`(json: {type_code: NoticeTypePrice{max_price_won, floor_sample_price_won, floor_sample_text, units, notice_type_code}}) — 임의공급 공고별 가격. 출처 행 field=`price_by_type.<type>.<항목>` | WP2, WP4, WP5 |
| 9 | WP1b #1 | `schemas/raw_document.json` · `raw_document` | `meta`(json\|null, 수집기 부가 정보) | WP1b, WP1a, WP2 |
| 10 | WP1a #2 | raw_document | `table_path`(공고문 표 JSON 상대 경로, Text) — notice_pdf 수집기가 채움(이번에 반영) | WP1a, WP2 |
| 11 | WP1a #1 | raw_document.error_text | 값 목록 명시: DNS·timeout·connect·TLS·network·robots·`robots.txt <코드>`·invalid_url·render / scan·ocr·`scan_partial:<p>`·`ocr_partial:<p>`·`pdf_parse: …`·not_pdf | WP1a, WP1b, WP2, WP6 |
| 12 | WP1a #3 | `schemas/region.json` | `$defs/ApplyhomeQuery{from_ym 'YYYY-MM', areas {sido_code: 약칭}}` 키 정의. `Region.applyhome_query` 는 자유 객체(additionalProperties) 유지 | WP1a, WP5 |
| 13 | WP9 #2 | `schemas/judgment_envelope.json` ClassifyResult | 배치 분류 `items[]: ClassifyItem{id, candidate, complex_id, label, prob, decision, distribution}`; 최상위 = 요약(label 'batch', prob = auto 비율, decision = 모두 auto일 때만 auto). 봉투 status = 모든 항목이 유효 응답이면 ok — 항목별 미해결은 `items[].decision`으로 거른다 | WP3(이번에 정규화 맞춤), WP4, WP7, WP9 |
| 14 | WP9 #3 | AuditItem | `p_wrong: number\|null` — 판정기가 안 주면 null(0·1로 지어내지 않음) | WP3(이번에 반영), WP9(픽스처 null) |
| 15 | WP9 #4·WP1b #2 | `examples/*`, 스키마 예시 | 폐지 코드 교체: 서구 28260 → 검단구 28290, 2826011400/500/600/700/800 → 2829010400(당하)/500(원당)/300(마전)/600(대곡)/700(금곡), 행정동 2826058500 → 2829051000(검단동 = 마전·금곡). 생활권 이름 '서구(검단)' → '검단구' | WP5, WP6(MSW 데이터) |
| 16 | WP9 #1 | `fixtures/README.md`, `judgments/_meta.json`·`_index.json` | MockAdapter adapter_version `"mock-fixture-2026-10-08"` 명시, `_index.json` 설명 | WP3, WP9 |
| 17 | WP9 주의·WP1b #2 | `fixtures/incheon_gimpo_2026-10-08/` | 법정동 사본을 gist → 공식 사본(`fixtures/reference/legal_dong_full.zip`) 발췌로 교체, 검단 법정동 현행 2829 코드, 생성기 재실행 | WP2, WP4, WP9 |
| 18 | WP3 제안 | DECISIONS D6 · `judgment_envelope` 설명 · protocols | adapter_version = `<코드>+jev-mcp@<서버>+<응답 model>`(예 `0.1.0+jev-mcp@0.14.1+jev-1.13.0`) — 모델이 바뀌어도 재판정. 모델을 모르면 접미 없이 | WP3(이번에 반영), WP7 |
| 19 | CEO 추가 1 | `schemas/living_area.json` | `legal_dongs: LegalDongRef[]{code, name, full_name}`(선택, 응답에서 서버가 채움) | WP5, WP6a |
| 20 | CEO 추가 2 | `schemas/sensitivity.json` | SensitivityRank `name`(선택), Sensitivity `complex_names{id: name}`(선택) | WP4, WP5, WP6 |
| 21 | CEO 추가 3 | 속성 없는 object 전부 | `additionalProperties: true` 명시(job_run.payload·stats, JobCreate.payload, envelope result·raw, RequirementRule.params, RetryHint.payload, region.applyhome_query) → TS `Record<string, unknown>`. 프론트 생성 `defaultNonNullable: false` | WP6 |

### WP0 직접 항목 (계약 밖 공통 코드)

- `core/db.py`: SQLite 연결에서 pysqlite 자체 BEGIN 을 끄고(`isolation_level=None`) `begin` 이벤트가 `BEGIN` 을 낸다(SQLAlchemy 문서 방식) —
  `session.begin_nested()`(SAVEPOINT) 롤백이 바깥 트랜잭션을 깨지 않는다(WP2 요청).
- `core/http.py`: `FetchResult.robots_status·robots_error_kind·robots_error` + `robots_reason`(차단 원인 보존 — 수집기가 robots.txt 를 다시 받지 않음).
  키 인증 공식 API 호스트(`HTTP_ROBOTS_EXEMPT_HOSTS`, 기본 `apis.data.go.kr,openapi.naver.com`)는 robots 검사 예외(크롤링 아님, 약관이 규율). 속도 제한·재시도는 그대로(WP1b 요청).
- `core/settings.py`: `JUDGE_CALL_TIMEOUT_S=120`, `JUDGE_START_TIMEOUT_S=300`(JevMcpAdapter 기본값), `HTTP_ROBOTS_EXEMPT_HOSTS`. `infra/.env.example` 갱신, `NEWS_API_KEY=<ClientID>:<Secret>`.
- `backend/pyproject.toml`: `mcp>=2,<3`, `[project.optional-dependencies] ocr = ["rapidocr>=3.10,<4", "onnxruntime>=1.18"]`(D5 채택), `uv lock`.
- CI: 백엔드 테스트 매트릭스에 `fixtures_contract`·`contracts` 추가.
- 테스트: 계약 버전 검사는 CHANGELOG 맨 위 항목과 비교한다. 0001→0002 왕복(SQLite·Postgres) 테스트 추가.
- 프론트(WP0 소유 설정): `scripts/gen-api.ts` `defaultNonNullable: false`, `src/api/types.ts` 보정 코드(`Loosen`·`Fact.human` 재정의) 제거,
  `lighthouse@12` devDependency, `npm run e2e` = 스모크(`tests/e2e`) + 화면(`e2e/pages`) 둘 다(`e2e:smoke`·`e2e:pages` 개별).

### 영향 WP 코드 적응(이번 변경에 포함, 최소)

- WP3 `judge/`: adapter_version 에 model(위 #18, `base.py`·`cache.last_adapter_version`·`log.record` 재키), 배치 classify 요약(#13),
  audit p_wrong null(#14), JevMcpAdapter 기본 timeout = 설정값.
- WP4 `analysis/`: `supply_component` 가 `unsold_scope_codes` 로 생활권 미분양을 고른다(없으면 기존대로 scope_code = 생활권 id, 그것도
  없으면 지역 합계). 요건 사전 계산이 `*_label`('확인 불가' → 값 미사용, 추정 등 → 근거에 표기)과 `intake_checked_at`('확인 날짜(D±n)')을 쓴다.
- WP1a `notice_pdf`: `table_path` 를 채운다. WP1a/1b/WP2 raw_document DTO 변환에 `table_path`·`meta`.
- WP1b `rawstore.fetch_failure`: robots 차단 원인을 `FetchResult.robots_*` 로 가린다(robots.txt 재요청 없음). news 테스트: 키 인증 API robots 예외.
- WP9 `fixtures_contract`: `expected_scores_v2.json` 을 `score_inputs.json`(key inputs)으로 검증(기존 매핑 누락으로 실패하던 테스트).

### 회귀·픽스처 메모

- 픽스처 지역의 검단 법정동은 이제 검단구(28290) 현행 코드다. 공식 사본에서 서구(28260)·그 법정동은 폐지라 `/regions/resolve?q=검단`은
  검단구만 낸다(D3 보강: 옛 코드가 폐지되면 새 코드만).
- `expected_scores.json` 은 그대로다. `expected_scores_v2.json`(WP4 생성기 재실행)은 검단 생활권 id 가 28260 → 28290(생활권 id = 시군구
  코드 관례), contract_version, 입력의 새 기본 필드(`unsold_scope_codes: []`)만 바뀌고 점수·순위·성분 값은 같다(재계산 diff 0 확인).

## 2026-10-09.1

최초 계약(R0, WP0-A). 원본: `docs/source/RA_v1.md` §3·§4, `docs/design/DECISIONS.md` v1.1(D2 지역 입력, D4 보고서 HTML/PDF, D6 판정기).

### 들어 있는 것

| 파일 | 내용 |
| --- | --- |
| `openapi.yaml` | OpenAPI 3.1 원본. RA §4-2 전부 + D2-3 지역 4개 + `/health` + 목록용 `GET /jobs`·`GET /reports` = 31 operation. bearer 인증(읽기 전용 토큰은 GET만), 에러 응답 401/403/404/409/422/500/503, 모든 JSON 본문에 인천·김포 보고서 기반 예시(`examples/*.json` 49개) |
| `openapi.bundled.yaml` | 생성물: 외부 `$ref` 없는 자립 번들(components = 스키마 파일 전부). 프론트 `openapi-typescript`·MSW는 이것을 쓴다 |
| `schemas/**/*.json` | JSON Schema 2020-12 원본 50개(공통 Fact·Label·Intake·JudgmentEnvelope·Error, 지역, 단지, 점수, 시나리오, 화면 응답, 잡 페이로드 7개, 내부 DTO, expected_scores) |
| `migrations/` | Alembic `0001_init`: 33 테이블(RA §3 29개 + D2-1 4개), 유일 제약·CHECK·인덱스, 내장 시나리오 5개 시드. SQLite·Postgres 16 |
| `fixtures/README.md`, `fixtures/incheon_gimpo_2026-10-08/expected_scores.json` | 픽스처 계약과 RA §9 (a)단계 골든 시드(T1·T2·T7·T12) |
| `backend/app/models/` | SQLAlchemy 2 typed 모델(마이그레이션과 1:1, autogenerate diff 0) |
| `backend/app/core/protocols.py` | RA §4-3 Protocol 8개 + `JudgeUnavailable` + `input_hash()` 정의 |
| `backend/app/core/contracts_gen.py` | 생성물: 스키마 → pydantic v2 모델 |

### RA에 없거나 RA를 구체화한 결정 (구현 WP는 이것을 따른다)

1. **Fact** = `{v, label, prov, checked_at}` + 선택 `reason`·`unit`·`human`.
   - `label`은 5종 enum, '확인 불가'의 사유는 `reason`에 따로(`label: "확인 불가", reason: "403"`). 다른 라벨의 한정어도 `reason`(예 `추정` + `대체·보정 c=0.015`).
   - 표시 문자열: `확인 불가(<reason>, <checked_at>)` / `<label>(<reason>)` / `<label>`; `human=true`면 '사람 확인됨'(라벨은 확인됨).
   - label≠'확인 불가'면 `v`·`prov` 필수(값 없으면 라벨이 '확인 불가'). `prov` 접두어: fp_ sc_ st_ jl_ hc_ rd_ cs_.
   - 판정기 출력 확률·순위는 label '추정', prov `jl_<seq>`. 참/거짓 공고 항목은 한국어 문자열 v(`비규제`, `적용`, `등기 시 해제`).
   - WP0-C 요청 1(`reason`, `human`) 반영.
2. **ScoreRow.components** 각 항목 = `ComponentView{score: Fact, raw: Fact|null, formula_text, weight, contribution}` — formula_text를 성분별로 내보낸다(C6 툴팁, WP0-C 요청 2). `total.v`는 원값의 소수 2자리 ROUND_HALF_UP 표시값(4.995 → 5.00), 순위·동점은 원값.
3. **동점 규칙**(RA §6-4 구체화): total 내림차순(동률 complex_id), 그룹 리더와 |ΔS| < 0.05면 같은 rank(경쟁 순위)·같은 tie_group, 반올림 전 10진 원값으로 비교. **TOP 5 집합** = rank ≤ 5 전부(공동 5위 포함). 민감도 변형 = w_i ± 0.10 (0~1로 자름), 나머지 비례 재정규화.
4. **needs_compare**(RA §3 표 정리): 값이 다른 최상위 후보가 모두 1차이고 source_rank가 같을 때만. 청약홈 상세(1) vs 공고문(2) 세대수 같은 rank 차이는 compare 없이 rank 1 채택(T5).
5. **judgment_log**: status='error' 행은 같은 input_hash 재시도 때 UPDATE(행 추가 아님). `input_hash()`는 `app.core.protocols`에 한 곳 정의(WP3 cache, WP5 미리보기 공용).
6. **raw_document 실패 행**: http_status(403 등) 또는 null+error_text(DNS·timeout), sha256 = sha256('fail:'+url+':'+상태+':'+날짜) — 같은 날 재시도 중복 없음.
7. **에러 코드** 추가: `unauthorized`(401) `forbidden`(403) `validation_error`(422) `conflict`·`publish_blocked`(409) `internal`(500) — RA의 `intake_unknown`·`judge_unavailable`·`contract_violation`·`not_found`와 함께.
8. **엔드포인트** 추가: `GET /jobs`(G7 큐), `GET /reports`(G8 목록, Report.id = report 잡의 job_run.id), `/changes?compare_snapshot=`(G8 diff), `/raw/{id}?as=text`(원문 하이라이트), `/market?living_area=`. `servers: [{url: /api}]`, 경로는 접두 없이(`/regions`), `/health`는 `/`와 `/api` 둘 다(WP0-C 요청 3).
9. **보고서**: `format: html|pdf`(D4). md·docx·32KB 분할 없음.
10. **컬럼**(RA §3에 더함): snapshot.degraded·published_at · complex.legal_dong_code·official_site_url·inclusion_judgment_seq·track · payment_terms.notice_kind · competition.raw_document_id · intake_status.raw_document_id·reason · raw_document.region_id·error_text·image_hash · field_provenance.entity_key·reason·excerpt·excerpt_start·excerpt_end·compare_judgment_seq · benchmark.n_trades·note · rtms_trade.legal_dong_code·completed_year·is_presale · comparable_set.n_trades·low/median/adjusted_median/high_won·outliers_excluded·excluded_reason·note · catalyst.decision·judgment_seq·source_url·note · supply.ym·reason·complex_id · unsold.scope_code·scope_name·raw_document_id · judgment_log.input_len·adapter_version·error_text · claim.parent_claim_id·ordinal · scenario.code·policy·created_at · score_run.prev_score_run_id · score_component.reason·delta·flags · ladder.months_from_asof·status·proposition_text · decision.option_key(escape hatch 행은 complex_id NULL) · human_check.created_at · change_event.complex_id · job_run.locked_by·progress · household_stat.reason. score_total.total은 Numeric(8,4) 원값.
11. **열거 확장**: catalyst.kind에 `생활인프라`·`기타`(병원 등), complex.inclusion_class에 `범위 경계`(D2-6)·`미분류`, score_component.component에 `move_in`(A·D).
12. **시나리오 시드**: 기본은 자기자본·한도 미입력(RA §6-7 '미입력' — 보고서 §8-2의 '자기자본 4억'과 다름), A 가점 60·자기자본 3억, B 가점 20·2억, C 4억·보유 5년·p10 시점 asof_plus_5y, D 3억·접수 불가 제외. 대출한도 6억(보고서 §1 잔금대출 한도). 요건은 규칙 코드(`RequirementRule.code`)로.
13. **Protocol 시그니처 보충**: `ClaimSplitter.split(text, *, section="", snapshot_id=None, complex_id=None)`, `RequirementPrecalc.evaluate(complex, scenario, *, asof_date)` — RA의 위치 인자는 그대로, 키워드만 더함. `JudgeAdapter`는 `adapter_version` 속성을 가진다. 메서드는 동기.
14. **Region**: D2-2 컬럼 전부, `age_premium_coef = {c_per_year: 0.015, cap_years: 8, label: 추정}`, `supply_ref_pct` 0.08.
15. **ScoreInputs**(WP7→WP4): 생활권 거래·벤치마크·공급·미분양 원자료 + 단지별 사다리 봉투 값 + `fixed_components`(회귀 (a)단계 전용).

### 회귀 기대값 메모 (expected_scores.json)

- T1은 보고서 §12-4-3 통합 값과 같다(5.87 / 5.70 / 5.33 / 5.00 / 4.61 = 4.61). §6-5·§7·§8-1의 엘리프 5.73·한내들 5.35는 인천 8후보 rerank(#71) 기준이라 T1이 아니다(t7_incheon_only에 기록).
- RA 동점 규칙으로는 리버프론트 3.94·롯데캐슬 3.90·고촌센트럴자이 3.895가 공동 9위(보고서 9·10·10). TOP 5는 같다.
- rerank 성분은 보고서 = relevance×10, RA §6-4 = 10×(N−rank)/(N−1) — (a)단계는 보고서 값 고정, (b)단계(expected_scores_v2)에서 RA 식.

### 알려진 한계

- 예시 응답의 단지·가격·확률·순위는 보고서 값이고, 보고서에 없는 id·해시·법정동 코드·세대수·일부 날짜는 형식 예시용 가상값이다. asof_plus_3y·5y 사다리는 보고서가 돌리지 않아 예시에서 `status=review`(미판정)이다.
- `backend/uv.lock`이 dev 의존성 추가(openapi-spec-validator, pgserver)로 바뀌었다 — WP0-B 변경과 겹치면 머지 후 `uv lock` 재생성.
