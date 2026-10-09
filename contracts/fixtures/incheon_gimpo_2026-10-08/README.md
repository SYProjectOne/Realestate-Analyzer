# 인천·김포 회귀 픽스처 (기준일 2026-10-08) — WP9

원천: `docs/source/incheon_gimpo_report.md`(보고서 기준일·확인일 2026-10-07, 같은 데이터). 계약: 2026-10-09.2.
상위 규칙은 [`../README.md`](../README.md)(디렉터리·MockAdapter·지역 정의)이고, 여기에는 이 픽스처의 내용과 T1~T18 매핑만 적는다.

## 만드는 법

`expected_scores.json`(WP0-A 시드)와 이 README를 뺀 모든 파일은 생성기로 만든다. **손으로 고치지 않는다** —
`backend/tests/fixtures_contract/test_tools.py`가 생성기 출력과 커밋된 파일의 바이트 일치를 검사한다.

```bash
cd backend
uv run python ../contracts/fixtures/tools/build_incheon_gimpo.py          # 다시 생성
uv run python ../contracts/fixtures/tools/build_incheon_gimpo.py --check  # 일치 검사
uv run python ../contracts/fixtures/tools/hash.py --tool screen --purpose screen:notice:1 payload.json  # input_hash 1개
uv run python ../contracts/fixtures/tools/synth.py --n 1000 --out /tmp/synth.json                      # T16 합성 단지
uv run pytest tests/fixtures_contract                                      # 스키마·라벨·해시·매핑 검사
```

원천 값은 `tools/incheon_gimpo_complexes.py`(1~6번)·`incheon_gimpo_complexes_b.py`(7~16번)·`incheon_gimpo_judgments.py`
(부록 A #1~132)에 보고서 절 번호와 함께 있다. 픽스처를 고치면 사유를 `contracts/CHANGELOG.md`에 적는다.

## 파일

| 경로 | 스키마 | 내용 |
| --- | --- | --- |
| `region.json` | `region.json` | 지역 1개(DECISIONS D3): 송도동 + 검단 법정동 10개(검단구 28290 현행 코드) + 계양구 + 김포시, 생활권 4개(시군구당 1개) |
| `complexes.json` | `complex.json#/$defs/ComplexBundle` ×16 | complex_id 1~16 = `expected_scores.json`·`contracts/examples` 번호. 수치는 전부 Fact |
| `provenance.json` | `provenance.json` ×N | Fact의 `prov`(fp_…)가 가리키는 출처 행: URL·확인일·라벨·발췌·원문 오프셋 |
| `snapshots.json` | `snapshot.json` ×2 | 11 = 2026-10-07(인천 8, 판정 #1~89), 12 = 2026-10-08(통합 16, #90~132) — T15용 두 스냅샷 |
| `expected_scores.json` | `expected_scores.json` | RA §9 (a)단계 골든(WP0-A 시드, 이 WP는 수정하지 않음) |
| `judgments/_meta.json` | — | `adapter_version = "mock-fixture-2026-10-08"` — MockAdapter 전용 고정값(실제 어댑터의 `<코드>+jev-mcp@<서버>+<model>`과 일부러 다름, 바꾸면 모든 hash·파일 이름이 바뀜). `note`·`index`에 설명 |
| `judgments/_index.json` | — | 녹화 132개의 `judgment_seq · tool · purpose · input_hash · file · payload` — payload로 해시를 다시 계산할 수 있다 |
| `judgments/<tool>/<hex>.json` | `judgment_envelope.json` | 봉투 1개. `<hex>` = input_hash에서 `sha256:`을 뺀 64자 |
| `raw/documents.json` | `raw_document.json` ×N | 원문 행(성공·실패). 발췌 txt·PNG·목록 파일의 sha256과 일치 |
| `raw/notice/`, `raw/applyhome_detail/`, `raw/official_site/`, `raw/news/` | — | 출처별 **재구성 발췌** txt(아래 '데이터 주의') |

## 데이터 주의 (숨기지 않는 것)

1. **발췌 txt는 재구성이다.** 공고문 PDF 원문이 아니라 보고서에 적힌 값을 원문 표기에 가깝게 한 줄씩 옮겼다(파일 머리 주석에
   원문 URL 명시). WP2 파서 테스트는 이 txt로 "가격이 expected와 원 단위 일치"를 검사할 수 있지만, 실제 PDF 표 파싱 검증은
   WP1 `http/` 녹화 몫이다.
2. **보고서에 없는 값은 `확인 불가(사유)`.** 사유 문자열에 '보고서 미기재', '공고 전', '공고 문구 미확인' 등을 적었다.
3. **산술 값은 `추정`(reason '산술' 또는 구체 사유)**, 식은 `provenance.formula_text`. 예: 전매 종료일, 경쟁률×공급으로 낸 접수 건수,
   공고일이 없을 때 접수 시작일로 대체한 `effective_from`(reason '접수 시작일로 대체').
4. **판정기 출력은 `추정` + `prov = jl_<seq>`**(예: inclusion_prob).
5. **판정 녹화 payload는 보고서 '입력 요약'의 재구성**이다. 보고서에 없는 출력(개별 추출 필드명, 주장 문장 대부분)은 지어내지 않고
   `counts`·`known_claims`로만 남겼다. 시각이 없어 `created_at`은 날짜만, `duration_ms`는 null. 배치 classify(#62·64·110·111)는
   `result.label = "batch"`, `prob` = auto 비율, 후보별 값은 `result.items`(계약 2026-10-09.2 `ClassifyItem`).
   audit 항목 중 보고서에 p_wrong이 없는 것은 null로 두고(계약 2026-10-09.2: AuditItem.p_wrong nullable) `raw.note`에 적었다. noul은 '입주 후 1년'(move_in_plus_1y)만
   판정됐다 — asof_plus_3y·5y는 녹화가 없어 MockAdapter가 `review`를 돌려준다(의도).
6. **법정동 코드**는 행정표준코드관리시스템 법정동코드 전체자료 **공식 사본**(`contracts/fixtures/reference/legal_dong_full.zip`,
   WP1b 수집)에서 생성기가 그대로 발췌한다(`raw/reference/legal_dong_excerpt.tsv` — 생성기 표와 이름·존재 여부가 다르면 생성 실패).
   2026-07 분구로 서구(28260)는 폐지, 검단 법정동은 검단구(28290) 현행 코드다. 옛 서구 코드는 발췌에 폐지 행으로 남긴다.
   (이전 gist 사본 기반 서구 코드는 계약 2026-10-09.2에서 교체.)
7. **생활권 세대수**는 주민등록 세대 현황 파일이 없어 `확인 불가`다(WP1b reference 수집 후 채움).
8. **complex_id 6(더샵 AB23)·11(고촌센트럴자이)·12(마리나베이)의 applyhome_id는 null** — 보고서에 그 단지 최초 공고의 주택관리번호가 없다.
9. 칸타빌(7)의 판정 기준 타입은 84B(84.7529㎡가 84㎡에 가장 가까움, complex_type 규칙). 보고서 본문은 84A로 서술한다.

## T1~T18 → 픽스처 매핑 (RA §9)

경로는 이 디렉터리 기준(백틱). `test_t_mapping.py`가 표의 경로 존재와 사례별 핵심 값을 검사한다.

| # | 사례 | 픽스처 | 기대 결과 요약 | WP |
| --- | --- | --- | --- | --- |
| T1 | 통합 TOP 5 재현 | `expected_scores.json` `complexes.json` | 구성 점수 고정 + 기본 가중치 → 5.87 > 5.70 > 5.33 > 5.00 > 4.61 = 4.61 | WP4 |
| T2 | 상황 B 동률 | `judgments/_index.json`(#127 → `judgments/decide/`) `expected_scores.json` | 칸타빌 0.54·엘리프 0.42·conf 0.48 → tie=true | WP4·WP6 |
| T3 | 스위첸 홈페이지 403 | `raw/documents.json`(official_site 403 행) `complexes.json`(id 4 intake) `raw/human_check/t3_switzen_possible.json` | 확인 불가(403) → 사람 확인 '가능' → intake 행 + rejudge 1 | WP1·WP5·WP7 |
| T4 | 메트로자이 2단지 11억 이상치 | `raw/rtms/t4_metroxi2_84.json` | 1.5×IQR 밖 1건 제외 + comparable_set '이상치 제외', 원본 행 유지 | WP4 |
| T5 | 해링턴 세대수 1,573 vs 1,769 | `raw/t5_harrington/candidates.json` `raw/t5_harrington/applyhome_detail.txt` `raw/t5_harrington/notice.txt` | conflict_group 1, chosen = 청약홈 상세(rank 1), compare 미호출 | WP2 |
| T6 | verify 복합 주장 contradicted(0.35) | `raw/claims/t6_composite.json` `judgments/_index.json`(#131) | ClaimSplitter → 주장 ≥ 2 | WP3 |
| T7 | rerank 8 → 16 | `judgments/_index.json`(#71·#124 → `judgments/rerank/`) `expected_scores.json` | 후보 변경 시 1회 호출, delta_rerank, 새 호출 값만 | WP3·WP4 |
| T8 | 변경 없는 날 | `raw/applyhome_list/2026-10-07.json` `raw/applyhome_list/2026-10-08.json` `raw/official_site/t8_popup_pairs.json` `raw/official_site/elif_popup_2026-10-08_changed.png` | 같은 목록·같은 해시 → change_event 0·판정 0; 변경 쌍 → critical 1 | WP7 |
| T9 | 임의공급 계약금 10% → 5% | `complexes.json`(id 7 payment_terms 2행) `raw/notice/07_n.txt` `raw/notice/07_r2.txt` | 행 2개, 현재 = 최신, change_event critical | WP2·WP4 |
| T10 | 사다리 시점 불일치 | `complexes.json`(id 11 즉시 입주, id 9 2031-01) `judgments/_index.json`(#119·#120) | horizon 3종, asof_plus_3y 목표 시점 동일 | WP3·WP4 |
| T11 | 스위첸 비교군 대체 | `raw/rtms/t11_switzen_comparables.json` | substitute=true, 보정·미보정 중앙값, '추정(대체·보정 c=0.015)' | WP4·WP6 |
| T12 | 민감도 | `expected_scores.json`(t12_sensitivity) | 12 변형, TOP 5 변동·unstable | WP4 |
| T13 | 출처 없는 수치 | `raw/t13_missing_provenance/complexes.json` `raw/t13_missing_provenance/provenance.json` `raw/t13_missing_provenance/expected.json` | dev contract_violation / prod '확인 불가(출처 누락)' | WP5·WP6 |
| T14 | 보안 guard | `raw/guard/t14_payloads.json` | 전화·이메일·주민번호·환경변수 값 → blocked 행, 로그에 원문 없음 | WP3 |
| T15 | 보고서 | `snapshots.json` `complexes.json` `judgments/_index.json` `provenance.json` | 스냅샷 11·12로 html·pdf + diff | WP8 |
| T16 | 성능 | `contracts/fixtures/tools/synth.py` | 합성 1,000단지(`generate(1000)`) | WP5·WP6 |
| T17 | 멱등성 | `raw/applyhome_list/2026-10-07.json` `raw/documents.json` `judgments/_index.json` | 같은 원문 2회 → raw_document 증가 0; 같은 payload 2회 → 실제 호출 1 | WP1·WP3 |
| T18 | 판정기 다운 | `raw/scenarios/t18_judge_down.json` `raw/documents.json` | degraded=true, 점수 미계산, 복구 후 rejudge 1 | WP7 |

## R3 통합 회귀 매핑 (WP9 R3, 계약 2026-10-09.3)

위 표의 각 사례를 **시스템 경계**(devseed 적재 + reference.refresh 오프라인 → API·worker → 응답·DB 행)에서 다시 검사하는
테스트. 위치 `backend/tests/regress/` (모두 `@pytest.mark.regress`), e2e 는 저장소 루트 `e2e/`. 실행:
`python scripts/tasks.py regress` (요약 출력) — 백엔드만 `--no-e2e`, T16 프론트 측정 추가 `--perf`.

| 사례 | 회귀 테스트(backend/tests/regress/) | 경계 | e2e |
| --- | --- | --- | --- |
| R3·T1 | test_t01_top5.py — (a) 대시보드·리스트 = expected_scores.json, (b) DB 입력 → v2 골든·파일 입력 → v2 골든 | API · DB→점수 입력 | — |
| R3·T2 | test_t02_tie.py — #127 B tie·chosen(API compare·dashboard), 낮은 confidence decide → top2 tie(worker) | API · worker | — |
| R3·T3 | test_t03_switzen_403.py — 403 확인 불가·D 제외 → 사람 확인 → rejudge 1 → 후보 포함(판정기 fake·mock) | API · worker | flows/2-g7-human-check-rejudge |
| R3·T4 | test_t04_outlier.py — collect.weekly(rtms 사본) → comparable_set '이상치 제외', 원본 행 유지 | worker · API | — |
| R3·T5 | test_t05_conflict.py — conflict_group 1, 청약홈 chosen, compare 미호출, 출처 패널 둘 다 | store · worker · API | — |
| R3·T6 | test_t06_claim_split.py — 복합 문장 분할, verify 입력 원자 주장만, 복합 문장 거부 | judge 경로 · worker | — |
| R3·T7 | test_t07_rerank_anchor.py — #71→#124, 후보 8→16 1회 호출·delta_rerank·새 호출 값만 | API · worker | — |
| R3·T8 | test_t08_no_change_day.py — 같은 목록·팝업 → 이벤트·rejudge·호출 0, 바뀐 팝업 → critical 1·rejudge 1 | worker | — |
| R3·T9 | test_t09_payment_terms.py — 공고 2건 → payment_terms 2행·현재=최신·critical·유동성 +1 | worker · API | — |
| R3·T10 | test_t10_ladder_horizons.py — 3 horizon·asof_plus_3y 같은 목표·연율 | worker · API | — |
| R3·T11 | test_t11_substitute.py — substitute·보정/미보정 중앙값·라벨 c=0.015·API 미보정 갭 | worker · API | — |
| R3·T12 | test_t12_sensitivity.py — /sensitivity 12 변형 = 골든, unstable 플래그 | API · worker | — |
| R3·T13 | test_t13_missing_provenance.py — dev 500 contract_violation / prod 확인 불가(출처 누락)+경고 / 프론트 lint | API · eslint | — |
| R3·T14 | test_t14_guard.py — 차단·blocked 행·로그 원문 없음(실제 어댑터·mock) | judge 경로 · API | — |
| R3·T15 | test_t15_report.py — POST /reports html·pdf(11·12, diff) → worker → 다운로드 검사, contradicted 거부 | API · worker | flows/1-g8-report-pdf |
| R3·T16 | test_t16_perf.py — uvicorn HTTP 첫 페이지 < 1 s(size 50·G2 의 size 1000) | HTTP | perf/t16.perf.ts(rAF 프레임 간격) |
| R3·T17 | test_t17_idempotency.py — 수집 2회 raw 증가 0, 같은 payload 실제 호출 1, 재판정 2회차 호출 0 | worker · adapter | — |
| R3·T18 | test_t18_judge_down.py — degraded·점수 미계산·/health·대시보드 배너 데이터, 복구 후 rejudge 1 | worker · API | — |
| (D2) | test_flow_g0_bootstrap.py — '송도' → POST /regions → bootstrap(청약홈 녹화 재생) → G1·G2, 기존 지역 불변 | API · worker | flows/3-g0-region-bootstrap |

판정기: `fake` = 실제 어댑터(JevMcpAdapter: guard·캐시·judgment_log)에 결정적 가짜 전송, `mock` = JUDGE_ADAPTER=mock 녹화 재생.
**주의**: 이 픽스처의 녹화 payload 는 보고서 재구성이라 파이프라인 payload 와 hash 가 다르다(위 '데이터 주의' 5) → Mock 으로
재판정하면 전부 review 가 되어 종합 점수가 미계산이 된다(T3 mock 변형·e2e 흐름 2 실패 원인). R4 실호출 녹화로 대체 예정(runbook §10-5).

## 판정 녹화 쓰는 법 (WP3 MockAdapter)

```python
from app.core.protocols import input_hash
idx = json.load(open(".../judgments/_index.json", encoding="utf-8"))
row = next(r for r in idx if r["judgment_seq"] == 127)
h = input_hash(row["tool"], row["purpose"], row["payload"], "mock-fixture-2026-10-08")  # == row["input_hash"]
envelope = json.load(open(f".../judgments/{row['file']}", encoding="utf-8"))           # cached=False로 녹화됨
```

녹화 원본은 `cached=false`다. MockAdapter가 돌려줄 때 `cached=true`로 바꾼다(contracts/fixtures/README.md 규칙 2).
