# R10-FIX — 같은 날 다시 수집할 때 `complex.apply_dates` 가 새 → 옛 → 새로 오가던 결함 (D23-1 위반) (2026-10-14)

브랜치 `wp/r10-fix`(main `1879c6e` = "Merge wp/r10-follow"). 계약 `.21` 그대로 — **계약·마이그레이션·새 라이브러리 없음**.
소유: `backend/app/normalize`(store·fields·judged), 그 테스트, `tests/scheduler`(D23-1 속성 테스트 확장), runbook §10-24.

운영 DB(`subscription_analyzer`, 인천 지역 1)는 **읽기 전용**으로만 봤다(`SET TRANSACTION READ ONLY`, SELECT 만 + 원문 파일 읽기). URL·비밀값은
출력하지 않았다.

## 1. 증상 (운영 DB 읽기 전용)

| 관측 | 값 |
| --- | --- |
| 스냅샷 6(R9-PARSE 뒤 첫 `collect.daily` #17) | `apply_dates` 62건 — 단지마다 1건 옛 → 새(정상), 같은 수집에 `options_text` 276·`balance_pct` 30·`interim_schedule` 4(정상 1회 변경) |
| 스냅샷 7(같은 날 `collect.daily` #20, R10 배포 뒤) | `apply_dates` **92건 = 46 단지 × 2**(새 `[{kind,start,end}]` → 옛 `[{kind:'1순위',date}]` → 새), `official_popup_hash` 5(정상), `merged_into` 1(정상) |
| 단지 2 출처 행 | rd 13 = 청약홈 공식 API 원문(JSON), rd 15 = 웹 상세(HTML) — 둘 다 출처 종류 `applyhome_detail`. fp 112(rd 13)·134(rd 15) = 옛 모양(R9-PARSE 전 파서, chosen false, 표식 없음), fp 27946(rd 13)·27947(rd 15, chosen) = 새 모양. 옛 행과 새 행의 발췌 위치는 같다(199·2892) |
| 옛 파싱 행이 남은 (원문, 묶음) | `apply_dates` 112 · `options_text` 276 · `balance_pct` 33 · `interim_schedule` 4 · `resale_months` 5·`residency_months` 1·`down_payment_pct` 2·`interim_pct` 1(판정기 추출 행 포함 — 값 같음) |
| 같은 묶음을 **두 원문**이 쓰는 경우 | `apply_dates` 62 단지(API·웹 상세)뿐. `options_text`·`balance_pct`·`interim_schedule`·`interim_pct`·`down_payment_pct`·당첨가점(`winning_score_*` 570 묶음)·`resale_months`·`residency_months` 는 모두 원문 1건/묶음 |
| 옛 모양이 남은 단지 | 34(지난 공고 33 + 병합된 99) — 원문 1건(과거 공고 상세)이고 일일 수집이 다시 받지 않아 다시 정규화되지 않음(뒤집힘 없음) |

## 2. 원인

`apply_dates` 를 쓰는 코드가 옛 모양을 내는 것이 아니다 — 두 파서(`applyhome_api_parser`·`applyhome_parser._schedule`) 모두 같은
`apply_items` 로 새 모양을 낸다(운영 원문 rd 13·15 를 지금 파서로 다시 읽어 확인, §5 건식 확인). 원인은 **같은 원문이 옛 파서로 남긴 출처 행**이다.

1. `provenance.upsert_provenance` 는 (원문·값 표기·발췌 위치·라벨)이 같으면 기존 행을 고쳐 쓰고, 다르면 새 행을 만든다. 옛 행은 지우지 않고 chosen
   false 로 둔다(옛 발행 리비전의 출처 근거). R9-PARSE 가 값 표기('1순위 2026-10-19; …' → '1순위 해당지역 2026-10-19 ~ 2026-10-22; …')를 바꿔
   원문마다 옛 행 + 새 행이 생겼다.
2. `store._reparse_existing` 은 원문 A 를 정규화할 때 A 의 출처 행은 빼고(이번 파싱이 대신) **다른 원문 B 의 출처 행은 모두** 후보로 되살린다 — B 의
   옛 행도.
3. resolver 는 같은 출처 종류끼리 최신(원문 번호 큰 쪽, 같은 원문이면 먼저 만든 행)을 고른다. A = API(rd 13)를 먼저 정규화하면 B = 웹(rd 15)의 옛 행
   (fp 134 < 27947)이 이겨 단지 값이 옛 모양으로(이벤트), 이어서 B 를 정규화하면 B 의 새 행 + A 의 새 행(A 의 옛 행은 이제 '다른 원문'이라 후보지만
   rd 13 < 15)으로 새 모양(이벤트). 매 수집 2건. 46/62 인 것은 수집이 그 날 두 원문을 다 정규화한 단지·순서에 따른다.
4. 스냅샷 6 은 옛 → 새 1건이었다(단지 값이 처음 옛 모양 — 첫 원문 차례에 옛 값이 이겨 '변화 없음', 둘째에서 새 값). 다른 R9-PARSE 필드는 묶음마다
   원문이 1건이라(이번 원문의 옛 행은 후보가 아니다) 뒤집히지 않았다 — 그러나 같은 묶음을 두 원문이 쓰면 똑같이 뒤집힌다(§4 공고문 두 사본 테스트).
5. change_event 비교(`changes.fmt_value`)는 이미 정준 JSON(`sort_keys`)이다 — 두 값은 표기만 다른 것이 아니라 **다른 값**(옛 모양엔 거주지역·마감일이
   없다)이라 정준형 비교로는 막을 수 없다. 고칠 곳은 후보(옛 파싱 행이 채택되지 않게)다.

## 3. 고친 것

| 파일 | 내용 |
| --- | --- |
| `normalize/fields.py` | `SUPERSEDED_REASON`('옛 파싱(같은 원문을 지금 파서로 다시 읽어 대체됨)')·`is_superseded`·`with_superseded`(reason 머리, compare·보류 표식은 뗌, 120자) |
| `normalize/store.py` `retire_superseded` | 원문 R 을 정규화한 뒤 이번 후보와 같은 묶음(엔티티·행·필드)·같은 파싱 키(entity_key)의 R 파서 행 중 이번 출처 행 갱신에 들지 않은 것 = 옛 파서 행 → 표식·chosen false·conflict_group NULL(P5 compare 대상에서도 빠짐). **지우지 않는다**. 판정기 추출·감사 행·사람 확인 행은 건드리지 않는다 |
| `normalize/store.py` `current_rows` | 후보로 되살릴 출처 행에서 표식 행을 빼고, 한 원문이 같은 묶음·같은 파싱 키에 파서 행을 둘 이상 남겼으면 그 원문을 지금 파서로 다시 읽어(원문마다 1회) 지금 파싱과 같은 자리(값 표기·발췌 위치·라벨)인 행만 남기고 나머지는 표식 — 표식 전 DB(배포 직후 첫 수집)에서도 순서와 무관하게 뒤집히지 않는다. 원문을 못 읽거나 같은 행이 하나도 없으면 그대로(추측하지 않음). 정상 다중 행(같은 칸을 여러 자리에서 냄)은 모두 지금 파싱이라 그대로 |
| `normalize/store.py` 사용처 | `_reparse_existing`(저장 경로) · `resolve_field_group`(사람 확인·D21-1 가격 다시 보기) · `price_refs`(표식 행 제외) |
| `normalize/judged.py` `_reresolve` | 판정 결과 반영(추출·compare)도 `current_rows` — 저장 경로와 같은 후보 |

판단은 늘지 않았다(규칙 3) — 원문을 같은 파서로 다시 읽어 출처 자리를 대조할 뿐. 판정기 호출 경로 변경 없음. 수집기·스케줄러 코드 변경 없음(쓰는 순서는
원인이 아니다).

## 4. 수정 전 실패 표

수정 전 = `git archive 1879c6e backend contracts`(main)를 scratch 에 풀고 새·바뀐 테스트 파일(`tests/normalize/test_r10_fix.py`,
`tests/scheduler/_idem.py`·`test_core10_idempotency.py`)만 복사해 같은 venv 로 `python -m pytest -p no:randomly`(`app` 은 그 디렉터리에서 import —
확인함). **새 테스트 12 중 9 실패 · 2 통과(회귀 가드) · 1 건너뜀(r4d-full)**.

| 테스트 | 확인하는 것 | 수정 전 |
| --- | --- | --- |
| `tests/normalize/test_r10_fix.py::test_upgrade_run_writes_one_value_with_one_event` | 실제 녹화 원문(공식 API 상세 + 웹 상세, 2026000367) 옛 파서로 저장 → 지금 파서 수집 1회: 일정 새 모양 하나·이벤트 ≤ 1(옛 → 새) · 같은 날 다시(순서 그대로·거꾸로) 0 | **실패**(같은 날 다시 → `apply_dates` 2건) |
| `…::test_ops_snapshot7_state_rerun_makes_no_apply_dates_events[api_first]` | 운영 스냅샷 7 직전 모양(두 원문 모두 옛 행 + 새 행, 표식 없음, 값 = 새 모양) → 같은 날 수집: `apply_dates` 이벤트 0, 옛 행 표식·chosen false·상충 묶음 없음, 한 번 더 → 출처 행·단지 바이트 동일 | **실패**(새 → 옛, 옛 → 새 2건) |
| `…[web_first]` | 같은 것, 웹 상세 먼저 | **실패**(1건 새 → 옛 — 뒤에 정규화한 API 원문 차례에 웹 상세의 옛 행이 이겨 **옛 모양으로 끝남**) |
| `…::test_superseded_rows_are_not_candidates_in_field_reresolve` | 사람 확인·가격 다시 보기(`resolve_field_group`)·판정 결과 반영(`judged._reresolve`)이 옛 행을 채택하지 않음 | **실패**(`resolve_field_group` → 새 → 옛 1건) |
| `…::test_unreadable_other_document_is_left_as_is` | 다른 원문 파일이 없으면 그 원문의 출처 행에 표식하지 않음(추측 금지) | 통과(가드) |
| `…::test_notice_fields_two_writers_same_day_rerun_is_quiet` | R9-PARSE 공고문 필드(필수 옵션 설명·중도금 회차·잔금 비율)를 두 원문(같은 공고문 두 사본)이 쓰면: 업그레이드 수집은 묶음마다 이벤트 1, 같은 날 다시(순서 그대로·거꾸로) 0·값 그대로·출처 행 동일 | **실패**(옛 고지문 '상기 공급금액에는 … 미포함된 가격이며' 가 다른 사본의 옛 행으로 되살아나 남음) |
| `…::test_change_detection_compares_canonical_json` | JSON 일정 비교는 정준형(키 순서 무관), 옛/새 모양은 다른 값 | 통과(가드 — 이미 정준형) |
| `tests/scheduler/test_core10_idempotency.py::test_parser_upgrade_then_same_day_renormalize_is_quiet[r4]` | **D23-1 확장**: 옛 파서로 `region.bootstrap` → 지금 파서 `collect.daily`(단지마다 `apply_dates` ≤ 1, 사실 이벤트는 apply_dates 뿐, 이벤트 난 단지는 새 모양) → 수정 전 배포 모양(표식 없음)으로 되돌려 같은 날 다시 ×3(그대로·섞어서 2) — 사실 이벤트 0 · DB 스냅샷 동일 · `tools/call` 0 | **실패**(3 단계 모두 `apply_dates` 2건) |
| `…[r4b]` | 같은 것(R4 2차 녹화) | **실패**(4·4·3건, DB 차이 complex 1·field_provenance 2) |
| `…[r4c]` | 같은 것(R4 3차 녹화) | **실패**(12·8·9건, DB 차이) |
| `…[r4d]` | 같은 것(R4 4차 녹화 zip — 18 단지) | **실패**(14·9·10건, DB 차이 complex 5·field_provenance 10) |
| `…[r4d-full]` | 로컬 전체 재생(`R4_REPLAY_MANIFEST`) | 건너뜀(매니페스트 없음 — 기존 r4d-full 과 같은 조건) |

바뀐 옛 테스트: 없음(기존 테스트 기대값 변경 없음). `tests/scheduler/_idem.py` 에 옛 청약 일정 파서·표식 되돌리기 도우미 추가.

## 5. 완료 기준 실행 결과

| 기준 | 명령 | 결과 |
| --- | --- | --- |
| 백엔드 전체 | `uv run pytest -p no:randomly -m "not live"` | **4,408 통과 · 9 건너뜀 · 0 실패** |
| 새 테스트 | `uv run pytest -p no:randomly tests/normalize/test_r10_fix.py "tests/scheduler/test_core10_idempotency.py::test_parser_upgrade_then_same_day_renormalize_is_quiet"` | 11 통과 · 1 건너뜀(r4d-full) — 수정 전 9 실패 |
| 정규화 전체 | `uv run pytest -p no:randomly tests/normalize -m "not live"` | 통과 |
| 정적 검사 | `uv run ruff check app tests` · `ruff format --check app tests` · `uv run mypy app` | 통과 · 통과 · 175 파일 문제 없음 |
| 생성물 | `uv run python scripts/gen_contracts.py --check` · `scripts/fixture_manifest.py --check` | 0 · 0 |
| 회귀 | `python scripts/tasks.py regress` | T01~T18·모듈·흐름·e2e 3 모두 PASS(종료 코드 [0, 0, 0, 0]) — 골든 변경 없음 |
| 운영 DB 건식 확인 | 읽기 전용 — 파서 행이 둘 이상인 (원문, 묶음)마다 운영 원문(`backend/data/raw`)을 지금 파서로 다시 읽어 `current_rows` 규칙 적용 | `apply_dates` 112 묶음 → 각 옛 모양 1행 표식·남는 행 1 · `options_text` 276 · `balance_pct` 32 · `interim_schedule` 4 → 각 1행 표식 · 정상 다중 행(경쟁률 36 · 주택형 12) 그대로 · 읽기 실패 0 → 다음 수집 `apply_dates` 이벤트 0 예상 |

## 6. 하지 않은 것 / 가정한 것

- **옛 행을 지우지 않았다** — 옛 발행 리비전·출처 서랍의 근거(D11-1)이고 `judgment.original_fp_id` 등 FK 가 있다. 표식(reason 머리)으로 후보에서만 뺀다.
  라이브 출처 서랍의 '다른 출처' 목록에는 '옛 파싱(…)' 사유로 보인다(이력).
- 판정기 추출·감사 행은 표식하지 않았다. 지금 파싱이 그 자리를 판정기에 묻지 않게 된 원문의 추출 행이 다른 원문 정규화에서 후보가 되는 것은 기존 동작
  그대로다(D22-1 은 같은 원문 정규화만 정했다) — 운영에서 관측되지 않음, 같은 모양의 잠재 결함 후보로 남긴다.
- 원문 하나가 같은 칸을 여러 자리에서 내는 정상 다중 행 묶음은 그 원문을 쓰는 다른 원문을 정규화할 때마다 다시 읽는다(HTML 상세 — 운영 48 묶음). 비용은
  작다고 봤다.
- 지난 공고 33 단지(+ 병합된 99)의 옛 모양 `apply_dates` 는 바꾸지 않았다 — 그 원문을 다시 정규화하는 경로가 일일 수집에 없다(뒤집힘이 아니라 재정규화
  범위). 화면 일정·체크리스트는 옛 모양도 읽는다.
- 같은 수집 안의 이벤트를 합치는(A → B → A 를 0 으로 접는) 안전망은 넣지 않았다 — 결함을 가린다. 대신 속성 테스트가 '수집 1회 = 실제 변경마다 ≤ 1건'을 단언한다.
- 수집기(`collectors/applyhome`)·스케줄러 쓰기 순서는 바꾸지 않았다 — 원인이 아니다.

## 7. 제안

- 새 라이브러리 없음. 계약 변경 요청 없음.
- DECISIONS: D23-1 범위에 **파서 변경 배포**(옛 파서로 적재 → 지금 파서 수집 → 같은 날 다시)를 넣는다 — 이번 확장 테스트가 그 기준.
- 지난 공고 원문 재정규화 명령(지역·원문 종류 지정, 원문 재다운로드 없음) — 옛 모양 34 단지와 앞으로의 파서 변경을 한 번에 맞춘다(WP7 후보).
