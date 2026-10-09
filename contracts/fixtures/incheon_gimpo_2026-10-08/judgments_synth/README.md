# 합성 판정 녹화 (라벨: 합성) — CEO 결정 W2, WP9-후속

**실제 JEV 응답이 아니다.** 결정적 가짜 판정기로 만든 봉투다. 회귀·e2e 의 Mock 재판정(JUDGE_ADAPTER=mock)이 재생한다.
R4 실호출 녹화가 생기면 교체한다(runbook §10-5).

## 왜 있나

`../judgments/`(보고서 부록 A #1~#132 재구성 녹화)는 payload 가 보고서 '입력 요약'이라 실제 파이프라인 payload 와
input_hash 가 다르다 → Mock 재판정이 전부 `review`('no recording')가 되어 종합 점수가 미계산이 된다(R3 WP9 발견, T3 mock·e2e 흐름 2).
여기 녹화는 **실제 파이프라인을 한 번 돌려 그 payload hash 그대로** 저장했다. `../judgments/` 는 그대로 둔다 — devseed
judgment_log·T2·T6·T7 등 보고서 대조용.

## 만드는 법

```bash
cd backend
uv run python ../contracts/fixtures/tools/record_synth_judgments.py          # 다시 쓴다(이 README 는 유지)
uv run python ../contracts/fixtures/tools/record_synth_judgments.py --check  # 커밋본과 바이트 비교
```

`complexes.json`·`../judgments/`·파이프라인 payload 규칙(app/judge/payloads.py 등)이 바뀌면 hash 가 바뀐다 → 다시 만들고
`tests/fixtures_contract/test_judgments_synth.py` 를 돌린다. 손으로 고치지 않는다.

| 흐름(run) | 시작 DB | 하는 일 | 쓰는 곳 |
| --- | --- | --- | --- |
| `full` | devseed + reference.refresh(공식 사본), 시계 2026-10-09 06:00 KST | rejudge(스냅샷 12, 단지 전부, 시나리오 전부) | 회귀 mock 재판정 기본 payload |
| `t3` | 같음 | POST /ops/human-checks(`raw/human_check/t3_switzen_possible.json`) → 응답 suggested_job(rejudge [4]) | 회귀 T3 mock, e2e 흐름 (b) |

## 값은 어디서 왔나 (봉투 `raw.synth.basis` 에 같은 문구)

| 도구 | 값 |
| --- | --- |
| classify 포함/제외 | `complexes.json` inclusion = 보고서 #62·#110(클래스·decision·확률). 스위첸·지엔하임·그랑포레 = review → D9-1 '미해결' |
| classify 호재 단계 | 보고서 #64·#111 의 같은 이름 항목(없으면 invalid → review) |
| classify 접수 상태 | `complexes.json` 공식 경로 접수 행(가능→open, 미정→pending, 불가→closed, 확인 불가→unknown) |
| noul | 입주 후 1년 = 보고서 #65~70·#118~123 단지별 p5·p10·p20·보합(라벨·auto 그대로). 3년·5년 = 보고서에 없음 → `review`(지어내지 않음) — 상황 C(기준일+5년)는 종합 미계산 |
| rerank | #124 relevance. 후보 안에서 relevance 내림차순, 같은 값 = 같은 순위 |
| decide | 상황별 #125~#129. 선택·확률·확신도 = 보고서 그대로(대체 선택·경고 경로 없음 — 보고서 선택이 후보에 없으면 녹화 실패). 요건 판정은 후보에 있는 것만. 상황 A 는 가상 후보 `wait_new`(모집공고 대기, 계약 2026-10-09.5 policy.include_wait_new)가 decide 후보에 있어 보고서 선택 wait_new .94(conf .93) 그대로 |
| verify | 보고서 §8-5·§12-5-5 최종 검증 = verified(auto). 파이프라인 주장 문장과 1:1 대응은 없음 |
| screen·extract·audit·compare | WP7 SynthJev 기본(pass·not_found·ok·same_fact) — 보고서에 필드별 값 없음 |

## 파일

- `judgments/_meta.json`: `adapter_version` = `../judgments/_meta.json` 과 같은 `mock-fixture-2026-10-08`(devseed judgment_log 와 버전이
  다르면 mock 재판정이 '판정기 버전 변경' critical + 전체 재판정을 만든다), `label` = 합성, 흐름·도구별 개수.
- `judgments/_index.json`: `[{tool, purpose, input_hash, file, status, complex_id, basis, runs, payload}]` — payload 로 hash 재계산 가능.
- `judgments/<tool>/<hex>.json`: 봉투(`cached=false`, `judgment_seq=null`, `created_at` 고정, `raw.synth = {label, basis}`).
- MockAdapter 는 `<fixture_dir>/judgments/` 구조를 읽으므로 fixture_dir = 이 디렉터리(`JUDGE_FIXTURE_DIR`).
