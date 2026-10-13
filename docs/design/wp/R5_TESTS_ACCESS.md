# R5-ACCESS — D25-11 A·C 접근 요건 접수 AND · 합성 녹화·API 골든 재생성 · ops 처리 실패 표식 (2026-10-13)

결정: `docs/design/DECISIONS.md` **D25-11**(RA §6-7 접근 가능성의 `intake_status ∈ {가능}` and path ≠ unofficial_ref 는 A·B·C·D 공통 조건),
R5-PIPE 보고 §4 요청(`/ops/sources` 처리 실패 표식). 근거 자료: `R5_TESTS_NORM.md` 3b 영향 표·부록 패치, `R5_TESTS_PIPE.md` 녹화 재생성 방법.
브랜치 `wp/r5-access`(main `c642c32` = "Merge wp/r5-pipe" 포함). 계약 **2026-10-09.18 그대로**(스키마·openapi 변경 없음 — CHANGELOG `.18`
'fixtures' 절에 픽스처 사유 한 줄만).

**방법.** 테스트를 먼저 썼다(커밋 `5eb6334 [R5-ACCESS] 테스트 먼저`). 그 커밋 트리(앱 코드는 main 그대로)에서 새 테스트를 돌린 실제 출력이
"수정 전" 열이다. NORM 이 '깨진다'고 한 테스트 4개는 **새 코드 + 옛 녹화**(재생성 전) 상태에서 돌려 실패를 재현한 뒤, 녹화·골든을 다시
만들고 통과를 확인했다. 실제 판정기·외부 사이트는 부르지 않았다.

## 1. 항목별 수정·테스트·수정 전 실패

| # | 수정 | 테스트 | 수정 전 실제 결과 | 수정 후 |
| --- | --- | --- | --- | --- |
| **1** D25-11 A·C 접수 AND | `analysis/scenarios.py`: `_intake_part`(접수 부분 — 상태·화살표 없는 근거)·`_priority_supply`(A)·`_resale_before_exit`(C)를 (상태, 근거) 쌍으로 분리, `_and_intake` 가 A·C 결과를 접수 부분과 AND — 상태는 약한 쪽(`_PRE_ORDER`: 미충족 > 확인 불가 > 미입력 > 충족), 근거는 RA 예시 모양 **"접수 …; 상황 조건 … → 상태"**(화살표 1개). 비공식 경로만이면 어떤 상황이든 미충족(기존 공통 조건, 맨 앞 그대로). B·D·기본은 바뀌지 않음 | `tests/analysis/test_r5_access_d25_11.py` 31개 | **16 실패 / 15 통과**(통과 = 결과가 상황 조건과 같은 조합·B·D·기본 가드·비공식 가드). 대표 단언: C 접수 미정 `assert '충족' == '미충족'`(근거 `전매 종료 2028-09 (등기 시 해제) ≤ 매도 시작 2031-10(기준일 + 보유 5년) → 충족`) · A 접수 불가 `assert '충족' == '미충족'` · 접수 확인 불가 `assert '충족' == '확인 불가'` · RA 예시 모양 `'전매 종료 2028-0...+ 보유 5년) → 충족' == '접수 가능(공식 팝업,...+ 보유 5년) → 충족'` · 미입력 조합 `'미입력' == '확인 불가'` | 31 통과 |
| **4** PIPE 요청 — `/ops/sources` 처리 실패 | `api/routers/ops.py::_ok`: `error_text` 가 `PROCESS_FAILURE_PREFIXES`(`store_failed:`·`parse_failed:` — `scheduler.collect` 의 같은 이름 상수와 같은 값을 ops 에 둔다. collect 를 import 하면 API 프로세스에 `judge.base` 가 올라와 R5-OPS 경계 테스트가 깨진다; 두 값이 같은지는 새 테스트가 단언)로 시작하면 실패. 같은 `_ok` 를 쓰는 `failing_targets`·`successes_7d`·`failures_7d`·`last_success_at` 이 함께 맞는다. 수집기 표식(`scan`·`scan_partial:<p>`)은 원문이 있으면 그대로 성공. 응답 모양 그대로(계약 변경 없음) | `tests/api/test_r5_access_ops_failure.py` 2개 | `test_process_failure_marks_are_failing_targets`: **`official_site: 'store_failed: RuntimeError: 정규화 실패(테스트)' 행이 failing_targets 에 없음`** / `test_collector_markers_without_failure_prefix_stay_success`: 통과(가드) | 2 통과 |

### NORM 이 '깨진다'고 한 테스트 (새 코드 + 옛 녹화 → 재생성 뒤)

| 테스트 | 새 코드 + 옛 녹화(실제 출력) | 원인 | 조치 | 기대값 변경 |
| --- | --- | --- | --- | --- |
| `tests/fixtures_contract/test_judgments_synth.py::test_recorder_is_reproducible` | `judgments_synth 불일치 5개: ['judgments/_index.json', 'judgments/decide/1d1aca2d….json', 'judgments/decide/2d4f54e3….json', 'judgments/decide/565e49d7….json', 'judgments/decide/63f3b721….json']` | decide A·C payload 증거의 '요건 사전 계산' 줄이 바뀌어 input_hash 가 바뀜 | `record_synth_judgments.py` 재생성(§2) | **없음** — 테스트 그대로 통과 |
| `tests/regress/test_d91_scope.py::test_d91_scope_after_mock_rejudge_matches_readme` | `[('decide', 'decide:scenario_A'), ('decide', 'decide:scenario_C')] == []` | 녹화에 없는 payload → MockAdapter review | 같음 | **없음** |
| `tests/regress/test_t03_switzen_403.py::test_t03_human_check_rejudge_mock_judge_d91` | `합성 녹화에 없는 payload(→ review): [('decide', 'decide:scenario_A'), ('decide', 'decide:scenario_C')]` | 같음 | 같음 | **없음** |
| `tests/api/test_perf_r3c.py::test_list_responses_match_golden` | `골든과 다른 응답: ['plain:compare', 'rich:compare', 'synth:compare']` | `/compare` 응답의 `decisions.A·C.items[*].requirements.access.pre`(요건 사전 계산은 응답 시 계산) | `UPDATE_GOLDEN=1` 로 3항목 재생성(§3) — 다른 71개 항목 sha256 그대로 | 골든 3항목(의도한 변경, 줄마다 §3) |

세 테스트(d91·t03·recorder)는 **기대값을 고치지 않았다** — D25-11 이 바꾸는 것은 decide 입력(증거 문자열)뿐이고, 녹화 봉투의 판정 내용(선택·
확률·확신도·요건 판정)은 보고서 값 그대로라 재생성만으로 맞는다.

## 2. 픽스처 변경과 이유 (`contracts/fixtures/**`)

- `judgments_synth/` — `record_synth_judgments.py` 로 재생성. 전후 대조(스크래치 스크립트: (tool, purpose, runs) 키별 hash·봉투 비교):
  `keys only old/new: 없음` · **바뀐 hash 2개(`decide:scenario_A` 2d4f54e3… → 63f3b721…, input_len 5,851 → 6,057 · `decide:scenario_C`
  1d1aca2d… → 565e49d7…, input_len 6,747 → 7,005), 봉투 내용 차이 0**(`input_hash`·`input_len` 외 바이트 동일, status ok 그대로) ·
  나머지 253개 파일 바이트 동일 · `_index.json` 은 두 행의 hash·file·payload 만 바뀜. 255개 봉투(수 그대로).
- payload 차이는 decide 증거 안의 단지별 `요건 사전 계산: 접근 가능성=…` 한 줄뿐이다(아래 영향 표 B).
- `contracts/fixtures.sha256.json` — 사유 `R5-ACCESS D25-11 A·C 접근 요건에 접수 상태 AND(decide 증거의 요건 사전 계산 변경)로 judgments_synth decide A·C input_hash 재매핑(봉투 내용 동일)`
  (직전 R5-PIPE 사유는 history 로). CHANGELOG `.18` fixtures 절에 같은 문장.
- `judgments/`(보고서 재구성 녹화)·`expected_scores.json`·`expected_scores_v2.json`·`complexes.json` 등 생성기 출력 **그대로**(회귀 골든 불변).

## 3. 영향 표 (단지 · 상황 · 필드 · 수정 전 → 수정 후)

### A. 골든 v2 입력(16단지, 기준일 2026-10-08) 요건 사전 계산 — `tests/analysis/_gen_expected_v2.build_inputs()` × 내장 시나리오 5개

덤프 240칸(5 상황 × 16 단지 × 요건 3) 중 **바뀐 것 30칸, 전부 A·C 의 access**. 기본·B·D 와 규제·자금은 0칸. 골든 v2 는 base 시나리오만
점수화하므로 `expected_scores_v2.json` 재생성 바이트 영향 없음(회귀 그대로 — §4).

| 상황 | 단지 | 필드 | 수정 전 → 수정 후 | 근거(수정 후) |
| --- | --- | --- | --- | --- |
| A | kaive_yubora(15) | access_pre | 충족 → **미충족** | 접수 미정(경로 미상); 가점제 1순위 공급(본청약·예정 공고) 있음 → 미충족 |
| A | grandforet(16) | access_pre | 충족 → **미충족** | 접수 미정(경로 미상); 가점제 1순위 공급(본청약·예정 공고) 있음 → 미충족 |
| A | granter·elif·hannaedeul·switzen·thesharp_ab23·cantavil·gracent2·riverfront·lottecastle·gochon_centralxi·marinabay·harrington_1bl·gnheim (13) | access_pre | 미충족 → 미충족(근거만) | '접수 …; 가점제 1순위 공급 없음(무순위·임의·선착순 경로만) → 미충족' — 접수 부분이 앞에 붙음 |
| C | granter(1) | access_pre | 충족 → **미충족** | 접수 미정(공식 팝업); 전매 종료 2026-12 ≤ 매도 시작 2031-10(기준일 + 보유 5년) → 미충족 |
| C | thesharp_ab23(6) | access_pre | 충족 → **미충족** | 접수 미정(공식 팝업); 전매 종료 2029-07 (등기 시 해제) ≤ … → 미충족 |
| C | gracent2(8) | access_pre | 충족 → **미충족** | 접수 미정(공식 팝업); 전매 종료 2029-04 (등기 시 해제) ≤ … → 미충족 |
| C | riverfront(9) | access_pre | 충족 → **미충족** | 접수 미정(경로 미상); 전매 종료 2029-08 (등기 시 해제) ≤ … → 미충족 |
| C | lottecastle(10) | access_pre | 충족 → **미충족** | 접수 미정(경로 미상); 전매 종료 2025-10 ≤ … → 미충족 |
| C | gochon_centralxi(11) | access_pre | 충족 → **미충족** | 접수 미정(경로 미상); 전매 종료 2024-05 ≤ … → 미충족 |
| C | marinabay(12) | access_pre | 충족 → **미충족** | 접수 불가(경로 미상); 전매 종료 2026-09 ≤ … → 미충족 |
| C | switzen(4) | access_pre | 충족 → **확인 불가** | 접수 상태 확인 불가(경로 미상); 전매 종료 2028-07 (등기 시 해제) ≤ … → 확인 불가 |
| C | harrington_1bl(13) | access_pre | 충족 → **확인 불가** | 접수 상태 확인 불가(경로 미상); 전매 종료 2026-01 ≤ … → 확인 불가 |
| C | gnheim(14) | access_pre | 충족 → **확인 불가** | 접수 상태 확인 불가(경로 미상); 전매 종료 2026-07 ≤ … → 확인 불가 |
| C | kaive_yubora(15) | access_pre | 확인 불가 → **미충족** | 접수 미정(경로 미상); 전매제한 기간 확인 불가 → 미충족 |
| C | grandforet(16) | access_pre | 확인 불가 → **미충족** | 접수 미정(경로 미상); 전매제한 기간 확인 불가 → 미충족 |
| C | elif(2)·hannaedeul(3)·cantavil(7) | access_pre | 충족 → 충족(근거만) | 접수 가능(공식 팝업, 기준일 2026-10-08); 전매 종료 … ≤ 매도 시작 2031-10(기준일 + 보유 5년) → 충족 |
| A·C | centreville_educity(5) | access_pre | 미충족 → 미충족(변경 없음) | 접수 미정(비공식 경로만, 판정 미사용) → 미충족 — 비공식 경로 공통 조건이 먼저 |

상태 변화 합계: A 2(충족 → 미충족), C 12(충족 → 미충족 7 · 충족 → 확인 불가 3 · 확인 불가 → 미충족 2). NORM 3b 표와 상태가 모두 같다.

### B. 파이프라인 decide 입력(합성 녹화 `judgments_synth` — devseed + reference.refresh DB, 접수 확인 시각 있음)

decide 후보 단지의 증거 줄 `요건 사전 계산: 접근 가능성=…`(RA §6-7 "decide 증거에 삽입"):

| 상황 | 단지 | 필드 | 수정 전 → 수정 후 | 근거(수정 후) |
| --- | --- | --- | --- | --- |
| A | complex_1 더샵 송도그란테르 | decide 증거 access | 충족 → **미충족** | 접수 미정(공식 팝업, 확인 2026-10-07(D+1)); 가점제 1순위 공급(본청약·예정 공고) 있음 → 미충족 |
| A | complex_5 검단 센트레빌 에듀시티 | decide 증거 access | 충족 → **미충족** | 접수 미정(공식 팝업, 확인 2026-10-07(D+1)); 가점제 1순위 공급(본청약·예정 공고) 있음 → 미충족 |
| A | complex_2 엘리프·complex_3 한내들 | decide 증거 access | 미충족 → 미충족(근거만) | 접수 가능(공식 팝업, 확인 2026-10-07(D+1), 기준일 2026-10-08); 가점제 1순위 공급 없음(…) → 미충족 |
| A | complex_6 더샵 검단레이크파크 AB23 | decide 증거 access | 미충족 → 미충족(근거만) | 접수 미정(공식 팝업, 확인 2026-10-07(D+1)); 가점제 1순위 공급 없음(…) → 미충족 |
| C | complex_1 더샵 송도그란테르 | decide 증거 access | 충족 → **미충족** | 접수 미정(공식 팝업, 확인 2026-10-07(D+1)); 전매 종료 2026-12(추정) ≤ 매도 시작 2031-10(기준일 + 보유 5년) → 미충족 |
| C | complex_5 검단 센트레빌 에듀시티 | decide 증거 access | 충족 → **미충족** | 접수 미정(공식 팝업, 확인 2026-10-07(D+1)); 전매 종료 2028-10 (등기 시 해제) ≤ … → 미충족 |
| C | complex_6 더샵 검단레이크파크 AB23 | decide 증거 access | 충족 → **미충족** | 접수 미정(공식 팝업, 확인 2026-10-07(D+1)); 전매 종료 2029-07 ≤ … → 미충족 |
| C | complex_2 엘리프·complex_3 한내들·complex_7 칸타빌 | decide 증거 access | 충족 → 충족(근거만) | 접수 가능(공식 팝업, 확인 2026-10-07(D+1), 기준일 2026-10-08); 전매 종료 … ≤ … → 충족 |
| A·C | decide 봉투 2개 | input_hash · input_len | 2d4f54e3… → 63f3b721…(5,851 → 6,057) · 1d1aca2d… → 565e49d7…(6,747 → 7,005) | 판정 내용(선택·확률·확신도·요건 판정) 그대로 |

(골든 v2 입력 표와 DB 단지 데이터가 달라 — 예: DB 의 그란테르·에듀시티는 공식 팝업 '미정' + 1순위 공급 있음 — 두 표의 단지별 값이 다르다.
같은 규칙이 두 입력에 각각 적용된 결과다.)

### C. API 응답 골든 `backend/tests/api/snapshots/list_r3c.json` — 바뀐 3항목, 줄마다

`/api/snapshots/12/compare?ids=2,3,4,5,7`(G4 비교)의 `decisions` 는 저장된 decide 판정(seq 126·128 — devseed 보고서 녹화) + **응답 시 계산한** 요건
사전 계산이다. 재생성 전후 본문을 뽑아(임시 덤프 테스트, 커밋 안 함) 경로별로 비교했고, 뽑은 본문의 sha256 이 새 골든 값과 같다(아래 해시).

| 골든 항목 | bytes · sha256 (전 → 후) |
| --- | --- |
| `plain:compare` | 83,439 · 65cb9a71… → 83,917 · 98dd2aae… |
| `rich:compare` | 83,147 · 57a4bee8… → 83,625 · 9acde324… |
| `synth:compare` | 83,147 · 57a4bee8… → 83,625 · 9acde324… (rich 와 같은 본문 — 전에도 같았다) |

세 본문의 차이는 **같은 18개 경로**다(plain·rich·synth 동일):

| 경로 | 단지 | 전 → 후 | 설명 |
| --- | --- | --- | --- |
| `decisions.A.items[2].requirements.access.pre.evidence` | 엘리프(2) | `가점제 1순위 공급 없음(…) → 미충족` → `접수 가능(공식 팝업, 기준일 2026-10-08); 가점제 1순위 공급 없음(…) → 미충족` | 근거에 접수 부분(상태 그대로) |
| `decisions.A.items[3]…evidence` | 칸타빌(7) | 같은 모양(접수 가능 부분 추가) | 근거만 |
| `decisions.A.items[4]…evidence` | 그란테르(1) | `… → 미충족` → `접수 미정(공식 팝업); 가점제 1순위 공급 없음(…) → 미충족` | 근거만 |
| `decisions.A.items[5]…evidence` | 한내들(3) | 접수 가능 부분 추가 | 근거만(이 행의 단지 mismatch=true 는 전에도 — 자금 요건(사전 충족 vs 판정기 contradicted) 때문, access mismatch 는 false 그대로) |
| `decisions.A.items[6]…evidence` | 스위첸(4) | `… → 미충족` → `접수 상태 확인 불가(경로 미상); 가점제 1순위 공급 없음(…) → 미충족` | 근거만 |
| `decisions.C.items[0]…evidence` | 엘리프(2) | `전매 종료 2028-09 (등기 시 해제) ≤ … → 충족` → `접수 가능(공식 팝업, 기준일 2026-10-08); 전매 종료 … → 충족` | 근거만 |
| `decisions.C.items[1]…evidence` | 한내들(3) | 접수 가능 부분 추가 | 근거만 |
| `decisions.C.items[2]…evidence` · `…pre.status` | 스위첸(4) | `충족` → **`확인 불가`**, 근거 `접수 상태 확인 불가(경로 미상); 전매 종료 2028-07 (등기 시 해제) ≤ … → 확인 불가` | 접수 상태 확인 불가 AND. 판정기 supported 와 '확인 불가'는 불일치 아님(규칙) → mismatch false 그대로 |
| `decisions.C.items[3]…evidence` | 칸타빌(7) | 접수 가능 부분 추가 | 근거만 |
| `decisions.C.items[4]…evidence` · `…pre.status` | 그란테르(1) | `충족` → **`미충족`**, 근거 `접수 미정(공식 팝업); 전매 종료 2026-12 ≤ … → 미충족` | 접수 미정 AND |
| `decisions.C.items[4].requirements.access.mismatch` · `decisions.C.items[4].mismatch` | 그란테르(1) | `false` → **`true`** | 사전 미충족 vs 판정기(seq 128) supported → '증거와 상이' 배지(RA §6-7 "둘 다 저장하고 mismatch=true"). NORM 3b 표가 예측한 행 |

(A 항목 경로 5개 × evidence 1 + C 경로: evidence 5 + status 2 + mismatch 2 = 18.) 같은 골든의 다른 71개 항목(전체 74)(목록·CSV·대시보드 C·시장·상세·
미리보기 base)은 sha256 그대로 — 대시보드·목록은 요건 사전 계산을 싣지 않고, 미리보기 골든은 기본 시나리오다.

## 4. 완료 검사

(브랜치 끝 커밋 `0b30982` 코드 기준. 이후 커밋은 이 문서뿐.)

| 검사 | 결과 |
| --- | --- |
| 전체 `pytest -p no:randomly -m "not live"` 1회차(`0b30982` 직전 코드) | 4,080 통과 · 7 skip · **1 실패** — `tests/api/test_r5_judge_boundary.py::test_api_process_does_not_load_adapter_modules` `API 프로세스에 어댑터 모듈이 올라왔다: LOADED=app.judge.base`. 원인: 항목 4 첫 구현이 `ops.py` 에서 `app.scheduler.collect` 를 import → 그 모듈이 `judge.base` 를 끌어온다(R5-OPS 판정기 경계). **고침**(`0b30982`): 접두 튜플을 `ops.PROCESS_FAILURE_PREFIXES` 값으로 두고, 테스트가 `scheduler.collect` 값과 같은지 단언 |
| 전체 2회차(최종 코드) | **4,088 중 4,081 통과 · 7 skip · 실패 0 · 오류 0**(junit, 1,863 s). 성능 테스트(`test_r3f_perf_publish` 등)도 이번엔 통과 — 재실행 불필요 |
| `ruff check app tests` · `ruff format --check app tests` · `mypy app` | 통과 · 495 files already formatted · no issues in 167 source files |
| `gen_contracts.py --check` · `fixture_manifest.py --check` · `record_synth_judgments.py --check` | exit 0 · exit 0 · `judgments_synth 일치 (255개 봉투)` |
| `python scripts/tasks.py regress` | 백엔드 회귀 **677 passed**(5분 7초, T1~T18 골든·`expected_scores*.json` 변경 없음) + e2e **3 passed**(G8 PDF · G7 사람 확인 재판정 · G0 bootstrap), exit 0 |

```bash
cd backend
uv run pytest -p no:randomly -m "not live"            # 전체
uv run ruff check app tests && uv run ruff format --check app tests && uv run mypy app
uv run python scripts/gen_contracts.py --check
uv run python scripts/fixture_manifest.py --check
uv run python ../contracts/fixtures/tools/record_synth_judgments.py --check
cd .. && python scripts/tasks.py regress                 # 회귀 + e2e
```

## 5. 남은 것·요청·가정

- **NORM 부록 패치와 다른 점**: 부록은 근거를 `접수 … → 상태; 상황 조건 … → 상태`(화살표 2개)로 붙이고, 상황 조건이 이미 미충족이면 접수
  부분을 빼고 상황 조건 근거만 냈다. 여기서는 RA §6-7 예시("접수 가능(공식 팝업 2026-10-07); 전매 종료 … → 충족")대로 **항상 접수 부분;
  상황 조건 → 최종 상태**(화살표 1개)로 썼다 — 화면·decide 증거에서 최종 상태와 다른 중간 화살표가 보이지 않게. 그래서 A 의 상태 불변
  행도 근거가 바뀐다(영향 표 A·B·C '근거만' 행). 상태는 부록 패치와 모두 같다.
- **계약 설명 갱신 요청(WP0, 모양 변경 없음)**: `contracts/schemas/scenario.json` RequirementRule `access` 설명(생성물 `frontend/src/api/schema.d.ts`
  4640행에 그대로 보임)이 `priority_supply: 가점제 1순위 공급(본청약·예정 공고) 존재` 로 접수 조건을 적지 않는다. D25-11 뒤로는 'intake_status ∈ {가능}
  AND …'가 A·C 에도 붙는다고 설명만 고치면 된다(다음 계약 버전 때 — 이번 라운드는 `.18` 유지라 고치지 않았다). 내장 시나리오 A 의 요건 문구
  (`가점제 1순위 공급(본청약·예정 공고)으로 접근 가능`, 마이그레이션 0001 시드)도 같은 이유로 그대로 두었다.
- **프론트(FE2 동시 작업)**: MSW 핸들러(`frontend/src/mocks/handlers.gen.ts`)는 openapi 예시에서 만들고 openapi 는 그대로라 영향 없음. `frontend/`·`e2e/`
  에 바뀐 근거 문자열('매도 시작'·'가점제 1순위 공급 …')을 단언하는 테스트·목은 없다(grep). 프론트는 고치지 않았다.
- **운영 DB**: 배포 뒤 첫 재판정에서 decide A·C 가 1회 다시 판정된다(입력 hash 변경, 캐시 미적중). 그란테르 C 처럼 사전 계산이 판정기와 반대가
  되면 '증거와 상이' 배지가 새로 뜰 수 있다(의도).
- `/ops/sources`: 처리 실패 표식 행은 이제 `successes_7d` 대신 `failures_7d` 로 세어지고 `last_success_at` 이 되지 않는다(실패 목록과 같은 판정을
  쓰므로). 표식은 같은 단계가 다음에 성공하면 R5-PIPE 코드가 지운다 → 그때 다시 성공으로 보인다.
