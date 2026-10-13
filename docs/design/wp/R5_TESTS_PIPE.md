# R5-PIPE — P6 맥락·N16 비성공 경로·P1 재screen·rerank 상한·실패 행·T7/T16·픽스처 테스트와 수정 전 실패 확인 (2026-10-13)

원문: `docs/design/wp/R5_FINAL.md` =====PIPE 1~4 + OPS 7(픽스처 — 이번 라운드 PIPE 소유), 결정 `docs/design/DECISIONS.md` **D25**.
브랜치 `wp/r5-pipe`(main `1dec271` 기준), 계약 **2026-10-09.18 그대로**(스키마·openapi 변경 없음 — CHANGELOG `.18` 'fixtures' 절에 픽스처 사유만 추가).

**방법.** 고치기 전에 테스트를 먼저 썼다(커밋 `e85118a [R5-PIPE] 테스트 먼저: …`). 그 커밋의 트리(앱 코드는 main 그대로)에서 새 테스트를 돌린
실제 출력이 "수정 전" 열이다. 실패 행(규칙 7) 테스트와 매니페스트 테스트는 수정과 같은 작업 묶음에서 썼고, 수정 전 상태는 아래 표에 적은 방식으로
확인했다. 실제 판정기·외부 사이트는 부르지 않았다(가짜 판정기 `SynthJev` 계열 — 전송 계층 `tools/call` — 와 저장소 녹화 재생 `r4b`·`r4d`).

## 1. 항목별 수정·테스트·수정 전 실패

| # · 결정 | 수정 | 테스트 | 수정 전 실제 결과 | 수정 후 |
| --- | --- | --- | --- | --- |
| **PIPE 1** major — P6 맥락(meta §2-1 P6) | `scheduler/inputs.py`: `RegionContext`(이 스냅샷이 인용하는 벤치마크·입주물량·미분양·생활권 + auto 로 해결된 연결 호재 + 제도 필드 라벨)·`region_context`·`evidence_card(…, ctx=)` → 카드 **벤치마크**(생활권 분양가→입주 후 실거래 중앙 사례·최근 3년 분양 사례 수)·**공급**(입주 후 1년 목표 해 ±1년 생활권 입주 물량·생활권 미분양 최근 값)·**호재**(classify auto 만, '호재 아님'·review 제외)·**비고**(제도: 규제지역·분양가상한제·택지·주택 유형·재당첨 제한) 줄. `policy_text`(제도 + 전매·거주의무), `benchmark_text`(생활권마다 최근 3년 분양분 / 그 이전 분양분, meta §2-2). `scheduler/payloads.py`: `judge_inputs`(P6·P7·P8·미리보기 공용) · 미리보기 noul 도 같은 컨텍스트(벤치마크 screen 캐시 판정을 따라감 — 캐시가 없으면 통과 가정 추정, 그때 noul 은 어차피 전부 미스라 히트·미스 수가 같다; 미리보기 `calls_by_tool` 에 `screen` 키가 생길 수 있다). `scheduler/pipeline.py`: P6 앞에서 카드(가격 갭 포함)·컨텍스트를 만들고, 벤치마크 텍스트는 **P1 screen**(`judge.pipeline.p1_screen_benchmark`, skip 이면 재screen) 통과분만 noul `context.benchmark` 로, `policy_text` 는 `context.policy` 로. P6 뒤 ScoreInputs 는 사다리만 다시(`inputs.with_ladders`) — 카드는 P6 앞뒤 같다 | `tests/scheduler/test_r5_pipe_p6_context.py` 3개, `tests/judge/test_r5_pipe.py::test_noul_payload_carries_benchmark_and_policy_context`·`::test_card_lines_benchmark_supply_catalysts` | `test_noul_rerank_decide_payloads_carry_regional_context`: **`noul context id ['card'] (card·benchmark·policy 필요)` × 모든 noul** · `연결된 auto 호재 '테스트 철도 연장선'가 카드 '호재' 줄에 없음` · `벤치마크 텍스트 P1 screen 이 noul 전에 없음` · `rerank 후보 카드에 벤치마크·공급 줄 없음` · `rerank 후보 카드에 연결 호재 없음` · `decide evidence 에 벤치마크·가격 갭 줄 없음` / `test_benchmark_screen_not_usable_drops_benchmark_context`: **`AssertionError: ['card']`**(policy 없음) / `test_preview_noul_payloads_match_pipeline`: 통과(수정 전에도 미리보기 = 파이프라인 — 회귀 방지용) / judge 단위 2개: 통과(빌더 `noul_payload`·`EvidenceCard` 는 이미 받을 수 있었고 **호출자**가 안 넘긴 것이 결함) | 전부 통과 |
| **PIPE 1** 픽스처 | `record_synth_judgments.py` 로 `judgments_synth/` 재생성: **noul 33·rerank 1·decide 5 = 39개 input_hash 재매핑, 봉투 내용(`input_hash`·`input_len` 외) 바이트 동일** + 벤치마크 screen 봉투 1개 추가(255개). extract·classify·verify·screen(공고문) 137개 hash 그대로. 회귀 골든 변경 없음 | `record_synth_judgments.py --check` · `tests/fixtures_contract` · 회귀 T1~T18 | `--check` → `judgments_synth 불일치 81개` | `judgments_synth 일치 (255개 봉투)` · 골든 그대로 통과(§3) |
| **PIPE 2** major 확인 — N16 비성공 경로 | `scheduler/pipeline.run_pipeline` `except JudgeUnavailable`: degraded 표시 뒤 `_sync_checklist`(그때까지 커밋된 사실 = 주간 단계 트랙 (A) 후보·P4 포함 분류)로 체크리스트를 맞춘다. 이월(carry) 경로는 고칠 것이 없었다(아래) | `tests/scheduler/test_r5_pipe_n16_paths.py` — `test_degraded_bootstrap_then_same_day_daily[r4b·r4d]`(판정기가 P6~P9 첫 호출에서 장애 → degraded bootstrap → 그 직후 체크리스트 = 사실로 다시 맞춘 것 · 복구 뒤 같은 날 `collect.daily` 조립 체크리스트 변경 0 · 두 번째 daily 행 그대로) · `test_carry_publish_then_same_day_daily[r4b·r4d]`(성공 bootstrap → 같은 날 `collect.weekly`(이월/빈 리비전 정리) → 같은 날 daily: 체크리스트 = 사실 · 변경 0 · 사실 이벤트 0) · `test_flaky_jev_raises_unavailable` | degraded **`[r4b] [degraded bootstrap 직후] 체크리스트가 그 시점 사실과 어긋남 — 다시 맞추면 {'inserted': 6, 'closed': 2}` · `[복구 뒤 같은 날 첫 daily] 수집 조립 체크리스트 동기화가 행을 바꿈 {'inserted': 6, 'closed': 2}`** · `[r4d]` 같은 2건 `{'inserted': 6, 'closed': 3}` / 이월 `[r4b]`·`[r4d]` **통과**(수정 전에도 — 성공 bootstrap 뒤 같은 날 weekly 는 사실 변경이 없으면 이월·빈 리비전 정리만 하고 체크리스트 근거를 바꾸지 않는다) | 5개 통과 |
| **PIPE 3** minor — P1 재screen(meta §2-1 P1) | `judge/pipeline.p1_screen_retry`: verdict skip 이면 purpose `<purpose>:retry`·다른 검사 목적·**다른 입력**으로 1회 재screen(block·review 는 재screen 없음). 공고문 조각 screen(`scheduler/pipeline._extract_one`, 입력 = '추출 대상: <필드 설명>' 머리 + 같은 조각)과 벤치마크 screen(`p1_screen_benchmark`, 입력 = 사례 줄만)에 적용 | `tests/judge/test_r5_pipe.py::test_p1_skip_rescreens_with_other_purpose_and_input`·`::test_p1_block_is_not_rescreened`·`::test_p1_pass_is_screened_once` | 3개 **`AttributeError: module 'app.judge.pipeline' has no attribute 'p1_screen_retry'`**(수정 전에는 skip 이면 그대로 버렸다 — `_extract_one` 의 `screen skip — OCR 값 점수 입력 제외`) | 통과 |
| **PIPE 3** minor — rerank > 250 | `judge.payloads.RERANK_MAX`(250) · `judge.pipeline.p7_rerank`: 넘으면 판정기를 부르지 않고 status `error`·items 없음 앵커(나누면 §6-5 한 호출 앵커가 깨진다) → rerank 성분 '미판정(판정기 error)'. 파이프라인은 잡 stats `skipped.rerank` 에 사유 | `tests/judge/test_r5_pipe.py::test_p7_rerank_over_cap_is_failure_not_crash` | **`ValueError: rerank 후보는 250개까지`**(잡 크래시) | 통과 |
| **PIPE 3** minor — 실패 행(규칙 7) | `scheduler/collect.py`: `mark_process_failure`·`clear_process_failure`·`PROCESS_FAILURE_PREFIXES` — 원문 저장(정규화) 실패는 그 원문 행 `error_text = 'store_failed: <예외>…'`, 파이프라인 공고문 파서 예외는 `'parse_failed: <예외>…'`(잡 stats 도 그대로). 같은 단계가 성공하면 지운다. 수집기가 쓴 사유(403·빈 데이터셋·OCR 표식)는 덮지 않는다. 문구는 `assemble.safe_error`(비밀값 가림, 시각 없음 — 멱등) | `tests/scheduler/test_r5_pipe_failure_rows.py` 2개 | 새 함수가 없어 **`ImportError: cannot import name 'PROCESS_FAILURE_PREFIXES'`** — 동작으로는 수정 전 코드에서 원문 행 `error_text` 를 쓰는 곳이 없다(`store_docs` 는 `res.store_errors` 만, `_p1_p3` 는 `res.skipped` 만) | 통과 |
| **PIPE 4** minor — T7 공회전 | `tests/regress/test_t07_rerank_anchor.py`: Σ w·s 검사 행 수 `checked ≥ 1` 단언(가중치 없음·종합 전부 null 이면 실패) | 같은 테스트 | 강화(수정 전 코드에서도 통과 — 회귀 픽스처는 종합 값이 있는 단지가 있다. 공회전 가능성을 막는 단언) | 통과 |
| **PIPE 4** minor — T16 size 1000 | `tests/regress/test_t16_perf.py::test_t16_g2_first_request_size_1000_under_1s`: 워밍업 뒤 5회, **중앙값** < 1 s(이전: 3회 중 **최솟값**). 한두 번 튀는 부하는 견딘다 | 같은 테스트 | 강화 | 통과(§3 — 단독 재실행 여부 기록) |
| **OPS 7** — 매니페스트 과거 사유 | `backend/scripts/fixture_manifest.py`: `missing_reasons`(지금 사유 + `history` 의 모든 과거 사유가 CHANGELOG 에 문장 그대로 있는가), `--check` 가 함께 검사. CHANGELOG `.18` fixtures 절에 누락돼 있던 과거 사유 1건 보완 | `tests/regress/test_r5_fixture_manifest.py::test_every_manifest_reason_is_in_changelog`·`::test_missing_reasons_detects_dropped_history` | **`CHANGELOG 에 없는 매니페스트 사유(과거 포함): ['R3f CORE4: T3 사람 확인 checked_at 을 시간대 붙은 RFC3339 로(계약 .11 D14-6)']`** · 두 번째도 같은 누락 때문에 실패(스크립트 쪽 함수는 테스트와 같은 묶음에서 작성) | 통과 · `fixture_manifest.py --check` exit 0 |
| **OPS 7** — README 주의 7 | `contracts/fixtures/incheon_gimpo_2026-10-08/README.md` 주의 7: '세대수 파일 없음 → 확인 불가' → 공식 사본(`reference/jumin_households_202609.csv`·`jscode20260930.zip`)을 `reference.refresh` 가 집계, 골든 v2 세대수 실측값은 **사람이 2026-10-09 확인**(DECISIONS 1-5b), `region.json` 의 null 은 입력 행 원값 | `::test_fixture_readme_households_is_current` | README 를 먼저 고쳤다 — HEAD(`1dec271`) 문구에 대해 같은 단언을 돌려 `old phrase present: True`(실패 조건 성립) 확인 | 통과 |

## 2. 픽스처 변경과 이유

- `judgments_synth/` — 위 PIPE 1 행. 재매핑 대조 스크립트 출력: `keys only new: [('screen', 'screen:benchmark:region:1', ('full',))]` ·
  `same hash 137 remapped 39 {'decide': 5, 'noul': 33, 'rerank': 1} content diffs 0`.
- `README.md` 주의 7 — OPS 7.
- `contracts/fixtures.sha256.json` — 사유 `R5-PIPE P6 맥락(벤치마크·제도·갭) 반영으로 judgments_synth noul·rerank·decide input_hash 재매핑(봉투 내용 동일)·벤치마크 screen 1개 추가·README 주의 7 현행화`
  (CHANGELOG `.18` fixtures 절에 같은 문장).
- `judgments/`(보고서 재구성 녹화)·`expected_scores*.json`·`complexes.json` 등 생성기 출력은 그대로.

## 3. 완료 검사

| 검사 | 결과 |
| --- | --- |
| 전체 `pytest -p no:randomly -m "not live"`(다른 에이전트 스위트와 동시 실행) | 1회차: 실패 4 — `tests/api/test_r25.py::test_preview_cache_hits_follow_payload_hashes`(미리보기가 벤치마크 screen 캐시가 없을 때 noul payload 를 None 으로 둬 '미스 noul' 이 사라짐 → **고침**: 캐시 없음 = 통과 가정 추정, 히트·미스 수는 같다), `tests/api/test_perf_r3c.py::test_list_responses_match_golden`(미리보기 응답 `calls_by_tool` 에 `screen` 이 들어가 바이트가 바뀜 — 의도한 변경, `UPDATE_GOLDEN=1` 로 preview 2항목만 갱신), 성능 2(`test_cold_size1000_published_under_0_2s` 0.236 s · `test_d14_5_publish_job…` 30.6 s, sys CPU 100%) — 단독 재실행 통과. 2회차(최종 코드): 실패 1 — `test_d14_5_publish_job_1000x5_under_30s…` 33.6 s(sys CPU 96~100%), **단독 재실행 통과**. 그 밖 전부 통과 |
| `ruff check app tests` · `ruff format --check app tests` · `mypy app` | 통과 · 484 files already formatted · no issues in 167 files |
| `gen_contracts.py --check` · `fixture_manifest.py --check` · `record_synth_judgments.py --check` | exit 0 · exit 0 · 일치(255개 봉투) |
| `python scripts/tasks.py regress` | 백엔드 회귀 **677 passed**(7분 12초, T1~T18 골든 변경 없음) + e2e **3 passed**(G8 PDF · G7 사람 확인 재판정 · G0 bootstrap) |

```bash
cd backend
uv run pytest -p no:randomly -m "not live"            # 전체
uv run ruff check app tests && uv run ruff format --check app tests && uv run mypy app
uv run python scripts/gen_contracts.py --check
uv run python scripts/fixture_manifest.py --check
uv run python ../contracts/fixtures/tools/record_synth_judgments.py --check
cd .. && python scripts/tasks.py regress                 # 회귀 + e2e
```

## 4. 남은 것·요청

- `/ops/sources` 의 `failing_targets` 는 `path`·`http_status` 로만 실패를 가른다(`api/routers/ops.py::_ok`, api 소유). 처리 실패 표식은 지금
  `last_error_text` 에만 보인다 — 실패 목록에도 넣으려면 `_ok` 가 `error_text` 의 `store_failed:`·`parse_failed:` 접두를 실패로 보게 하는 변경이
  필요하다(계약 변경 없음, API 담당 요청).
- 운영 DB 는 배포 뒤 첫 재판정에서 noul·rerank·decide 가 1회 전부 다시 판정된다(runbook §10-16).
