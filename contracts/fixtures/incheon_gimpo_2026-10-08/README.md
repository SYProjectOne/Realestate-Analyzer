# 인천·김포 회귀 픽스처 (기준일 2026-10-08) — WP9

원천: `docs/source/incheon_gimpo_report.md`(보고서 기준일·확인일 2026-10-07, 같은 데이터). 계약: 2026-10-09.3
(WP9-후속 2026-10-09: W1 골든 v2 정렬·W2 합성 판정 녹화·W5 T11 변형 — `contracts/CHANGELOG.md` 'fixtures' 소절).
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
uv run python ../contracts/fixtures/tools/record_synth_judgments.py [--check]                            # judgments_synth/ (W2)
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
| `judgments_synth/` | `judgment_envelope.json` | **합성 판정 녹화(라벨 '합성', W2)** — 실제 파이프라인 payload hash 그대로. 회귀·e2e 의 mock 재판정이 재생(`JUDGE_FIXTURE_DIR`). 값 출처·흐름은 `judgments_synth/README.md` |
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
   → 현재 구매가가 골든 v2(84A 6.64~6.97억)와 다르다(84B 6.70~7.04억) — T1(b) DB 경로는 이 차이를 규칙 차이로 둔다(W1).
10. **W1(골든 v2 정렬, 2026-10-09)**: 기준 타입 floor(현재 구매가 하단)는 보고서 '현재 구매가' 범위의 하단이다 — 한내들(3)·스위첸(4)·
   더샵 AB23(6)은 84㎡ 타입 묶음의 최저(다른 84 타입 가격)라 라벨 `추정`(reason '보고서 현재 구매가 범위(타입 묶음)'). 한내들 계약금
   2.92%(정액 2,500만 ÷ P_mid 8.56억, 추정), 그란테르 접수 '미정'(추가 공급 미정·공고 이력 있음)·당첨 발표 2026-06-02(블록별 마지막,
   추정), 마리나베이 당첨일 = 무순위 접수일 2026-09-15(추정)·전매 0개월(도과). 골든 v2 가격은 보고서 표기(억 소수 2~3자리)라 원 단위
   공고 값과 50만원 이하 차이는 같은 값으로 본다(가격 반올림 규칙).

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
| T7 | rerank 8 → 16 | `judgments/_index.json`(#71·#124 → `judgments/rerank/`) `expected_scores.json` | 후보 변경 시 1회 호출, delta_rerank(= rerank **점수(0~10) 차**, §6-5·F2; `expected_scores.json` t7 열은 보고서 정의 relevance 차 — 보고서 대조용), 새 호출 값만 | WP3·WP4 |
| T8 | 변경 없는 날 | `raw/applyhome_list/2026-10-07.json` `raw/applyhome_list/2026-10-08.json` `raw/official_site/t8_popup_pairs.json` `raw/official_site/elif_popup_2026-10-08_changed.png` | 같은 목록·같은 해시 → change_event 0·판정 0; 변경 쌍 → critical 1 | WP7 |
| T9 | 임의공급 계약금 10% → 5% | `complexes.json`(id 7 payment_terms 2행) `raw/notice/07_n.txt` `raw/notice/07_r2.txt` | 행 2개, 현재 = 최신, change_event critical | WP2·WP4 |
| T10 | 사다리 시점 불일치 | `complexes.json`(id 11 즉시 입주, id 9 2031-01) `judgments/_index.json`(#119·#120) | horizon 3종, asof_plus_3y 목표 시점 동일 | WP3·WP4 |
| T11 | 스위첸 비교군 대체 | `raw/rtms/t11_switzen_comparables.json` `raw/rtms/t11_switzen_subarea.json` | (W5) 그대로(김포시 전체): 리버시티(2020)·고촌 센트럴자이(2024) = 신축, 대체 아님. 하위 생활권(장기·운양) 변형: 신축 0건 → 대체 = 한강센트럴자이(2017), 보정 c×min(2028−2017, 8) = 0.12, 보정·미보정 중앙값, '추정(대체·보정 c=0.015)' | WP4·WP6 |
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
| R3·T1 | test_t01_top5.py — (a) 대시보드·리스트 = expected_scores.json(보고서 고정 입력), (b) 파일 입력 → v2 골든 / DB 입력 = v2 inputs(W1, 가격 반올림 규칙) → v2 골든 + D9-1 범위 + 칸타빌 기준 타입 규칙 | API · DB→점수 입력 | — |
| R3·T2 | test_t02_tie.py — #127 B tie·chosen(API compare·dashboard), 낮은 confidence decide → top2 tie(worker) | API · worker | — |
| R3·T3 | test_t03_switzen_403.py — 403 확인 불가·D 제외 → 사람 확인 → rejudge 1 → fake(classify auto): 후보 포함 / mock(합성 녹화 = 보고서 classify review): D9-1 미해결, TOP 5 유지·녹화 누락 0 | API · worker | flows/2-g7-human-check-rejudge(mock, G3 배지 '접수 가능·사람 확인', D 후보 아님) |
| R3·T4 | test_t04_outlier.py — collect.weekly(rtms 사본) → comparable_set '이상치 제외', 원본 행 유지 | worker · API | — |
| R3·T5 | test_t05_conflict.py — conflict_group 1, 청약홈 chosen, compare 미호출, 출처 패널 둘 다 | store · worker · API | — |
| R3·T6 | test_t06_claim_split.py — 복합 문장 분할, verify 입력 원자 주장만, 복합 문장 거부 | judge 경로 · worker | — |
| R3·T7 | test_t07_rerank_anchor.py — #71→#124(relevance 차 = 보고서, 점수 차 = §6-5), 후보 8→16 1회 호출·delta_rerank(점수 차)·새 호출 값만 | API · worker | — |
| R3·T8 | test_t08_no_change_day.py — 같은 목록·팝업 → 이벤트·rejudge·호출 0, 바뀐 팝업 → critical 1·rejudge 1 | worker | — |
| R3·T9 | test_t09_payment_terms.py — 공고 2건 → payment_terms 2행·현재=최신·critical·유동성 +1 | worker · API | — |
| R3·T10 | test_t10_ladder_horizons.py — 3 horizon·asof_plus_3y 같은 목표·연율 | worker · API | — |
| R3·T11 | test_t11_substitute.py — (a) 그대로 = 신축(대체 아님) (b) W5 변형: PUT 생활권 편집 → 대체 한강센트럴자이·0.12·보정/미보정 중앙값·라벨 c=0.015 (b-API 라벨·c API 미보정 갭 = F3 W6·W7) | worker · API | — |
| R3·T12 | test_t12_sensitivity.py — /sensitivity 12 변형 = 골든, unstable 플래그 | API · worker | — |
| R3·T13 | test_t13_missing_provenance.py — dev 500 contract_violation / prod 확인 불가(출처 누락)+경고 / 프론트 lint | API · eslint | — |
| R3·T14 | test_t14_guard.py — 차단·blocked 행·로그 원문 없음(실제 어댑터·mock) | judge 경로 · API | — |
| R3·T15 | test_t15_report.py — POST /reports html·pdf(11·12, diff) → worker → 다운로드 검사, contradicted 거부 | API · worker | flows/1-g8-report-pdf |
| R3·T16 | test_t16_perf.py — uvicorn HTTP 첫 페이지 < 1 s(size 50·G2 의 size 1000) | HTTP | perf/t16.perf.ts(rAF 프레임 간격) |
| R3·T17 | test_t17_idempotency.py — 수집 2회 raw 증가 0, 같은 payload 실제 호출 1, 재판정 2회차 호출 0 | worker · adapter | — |
| R3·T18 | test_t18_judge_down.py — degraded·점수 미계산·/health·대시보드 배너 데이터, 복구 후 rejudge 1 | worker · API | — |
| (D2) | test_flow_g0_bootstrap.py — '송도' → POST /regions → bootstrap(청약홈 녹화 재생) → G1·G2, 기존 지역 불변 | API · worker | flows/3-g0-region-bootstrap |
| (D9-1) | test_d91_scope.py — mock 전체 재판정 → API judge_scope = 아래 'D9-1로 인한 차이' 표, 참고 단지 종합 미판정(xfail: 남은 사다리 행이 점수에 쓰임 — F2 보고) | worker · API | — |

판정기: `fake` = 실제 어댑터(JevMcpAdapter: guard·캐시·judgment_log)에 결정적 가짜 전송, `mock` = JUDGE_ADAPTER=mock 녹화 재생 —
**재생 녹화는 `judgments_synth/`(합성, W2)**: `judgments/`(보고서 재구성)는 payload 가 보고서 요약이라 파이프라인 hash 와 달라
mock 재판정이 전부 review 가 되던 문제(R3 T3 mock·e2e 흐름 2)를 실제 파이프라인 hash 녹화로 해결했다. 회귀 conftest·`e2e/env.ts` 가
`JUDGE_FIXTURE_DIR=judgments_synth` 로 둔다. R4 실호출 녹화로 교체 가능(runbook §10-5).

### D9-1로 인한 차이 (보고서·골든 v2 판정 범위 vs 파이프라인·DB 경로)

보고서(§3·§12-1-3)는 classify review 단지도 '1차 자료상 민간'이면 포함해 판정했고, 골든 v2 inputs 는 그 범위를 내장한다(T1 (a)·(b) 파일 입력은
그대로 재현). 파이프라인·DB 경로는 DECISIONS D9-1(`app/analysis/scope.py`)을 따른다 — 녹화 classify 결과는 보고서와 같다(#62·#110).

| 단지 | 보고서·골든 v2 | D9-1 | 근거(녹화) | 영향 |
| --- | --- | --- | --- | --- |
| 4 오퍼스 한강 스위첸 | 판정 대상(통합 4위 5.00 / v2 5위 4.97) | 미해결(분류 판정 미해결) — 계약 .4 전 score_total '제외' | #110 review .72 | T1(b) DB 경로 종합 없음, T3 mock·e2e (b) 사람 확인 '가능' 뒤에도 후보 아님 |
| 12 더샵 송도마리나베이 | 판정 대상(v2 9위 4.14) | 참고(접수 '불가' — 마감, 4회차 미정) | #62 auto .99 · 접수 불가 | 사다리 미실행 → 종합 미판정이어야 함(현재 남은 사다리 행으로 점수가 나옴 — test_d91_scope xfail) |
| 14 사우역 지엔하임 | 참고 | 미해결 | #110 review .70 | rerank 후보에서도 빠짐 |
| 16 검단 센트레빌 그랑포레 | 보류(공고 전) | 미해결 | #62 review .84 | rerank 후보에서도 빠짐 |

그란테르(1)는 W1(접수 '미정')로 보고서·골든 v2 와 같은 '판정 대상'이다. 해링턴(13) '참고'·카이브 유보라(15) '보류'는 같다.

## 판정 녹화 쓰는 법 (WP3 MockAdapter)

```python
from app.core.protocols import input_hash
idx = json.load(open(".../judgments/_index.json", encoding="utf-8"))
row = next(r for r in idx if r["judgment_seq"] == 127)
h = input_hash(row["tool"], row["purpose"], row["payload"], "mock-fixture-2026-10-08")  # == row["input_hash"]
envelope = json.load(open(f".../judgments/{row['file']}", encoding="utf-8"))           # cached=False로 녹화됨
```

녹화 원본은 `cached=false`다. MockAdapter가 돌려줄 때 `cached=true`로 바꾼다(contracts/fixtures/README.md 규칙 2).
