# R7-QUEUE — G7 접수 확인 대기열 (D26-2, 계약 2026-10-09.19) (2026-10-13)

브랜치 `wp/r7-queue`(main `36894df` = "Merge wp/r6-intake" 기준). 계약 **`.19`** 를 이 브랜치가 냈다(`contracts/CHANGELOG.md` 맨 위 —
FE 차이 표 F1~F4). 마이그레이션·새 라이브러리 없음. `backend/app/scheduler`·`collectors`·`judge`·`normalize` 는 건드리지 않았다(R7-SITE 가
같은 때 접수 사유를 늘린다 — 대기열은 저장된 사유로 묶으므로 그쪽 변경에 맞춰 고칠 것이 없다).

## 1. 무엇을 만들었나

| 층 | 파일 | 내용 |
| --- | --- | --- |
| 계약 | `contracts/schemas/intake_queue.json`(새), `openapi.yaml`, `examples/intake_queue*.json` | `GET /ops/intake-queue?region_id=&snapshot=` → `IntakeQueue{region_id, snapshot_id, asof_date, revision, snapshot_status, total, groups[]}`, `IntakeQueueGroup{category, reason, count, items[]}`, `IntakeQueueItem{intake_id, complex_id, complex_name, status, reason, path, evidence_url, raw_document_id, screenshot_path, screenshot_raw_document_id, checked_at, http_status, note, judgment_ref, human_check_pending}`. 맨 숫자(`total`·`count`·`revision`·`http_status`)는 `x-nonfact` |
| 버전 | `app/core/protocols.py`, `openapi.yaml info.version`, `DECISIONS.md` 5행, 버전 테스트 3 | `2026-10-09.18` → `.19` |
| API | `backend/app/api/intake_queue.py`(새), `routers/ops.py` | 저장된 행만 읽는다(판정기 호출·DB 쓰기 없음 — 규칙 4). 단지마다 표시 접수 행(`analysis.scope.pick_intake`)이 '확인 불가'·'미정'이면 항목. 묶음 = `queue_key(status, reason, http_status)` |
| 화면 | `frontend/src/pages/ops/IntakeQueuePanel.tsx`(새), `ops/index.tsx`, `api/hooks.ts`·`types.ts`, `i18n/ko.json`(`page.G7.iq.*`), `mocks/handlers.extra.ts` | 분류(접이식, 판정 대상 아님·미정은 접힘) → 사유 묶음(건수) → 항목 표(단지 G3 링크·접수 배지·판정 로그 표식·HTTP·확인 시각·근거 페이지·스크린샷 미리보기(Bearer)·반영 대기 배지·'사람 확인 입력'). '사람 확인 입력' = 같은 `/ops` 의 HumanCheckForm 을 `?hc_complex=<id>&hc_field=intake_status#human-check` 로 미리 채움 → 기존 `POST /ops/human-checks`(접수 행 + 재판정 자동 등록, D12-5). 저장하면 대기열 쿼리를 무효화 → 그 항목에 '사람 확인 입력됨(값, 날짜) — 재판정·발행 대기' |

### 묶음 규칙(데이터 기준 — `queue_key`, 계약 `intake_queue.json` 설명과 같다)

| 순서 | 조건(저장된 값) | category | 묶음 이름 |
| --- | --- | --- | --- |
| 1 | status '미정' | `undecided` | 사유(없으면 '미정') |
| 2 | http_status 비 2xx, 또는 사유가 숫자뿐 | `collect_failed` | 숫자 사유(없으면 http_status) |
| 3 | 사유 앞 영문 낱말 ∈ DNS·timeout·connect·TLS·network·robots·robots.txt·invalid_url·render·blocked_host·blocked_by_robots(대소문자 무시) / 사유가 '접속 실패'·'수집 실패'·'타임아웃'·'원문 없음'으로 시작 | `collect_failed` | 그 낱말(원래 표기: 'connect: …' → 'connect', 'TLS(브라우저 재시도 실패)' → 'TLS') |
| 4 | '공식 홈페이지 동일성 미확인'·'공식 홈페이지가 다른 단지' / '문구로 판단 불가'·'접수 문구 없음' / '판정 미해결'·'접수 문구 미분류' / '판정 대상 아님'으로 시작 | `identity` / `no_phrase` / `unresolved` / `not_judged` | 저장 사유 그대로 |
| 5 | 그 밖(새 사유·'사람 확인' 등) | `other`('기타') | 저장 사유 그대로 |

R7-SITE 가 사유를 더해도(예 '판정 대상 아님(공공분양)'·'판정 대상 아님(범위 경계)' → `not_judged`, TLS 브라우저 재시도 실패 'TLS(…)' →
`collect_failed`·'TLS', OCR 관련 새 문구 → `other`) 코드·계약을 바꾸지 않는다. 사유 머리말 비교·낱말 자르기는 문자열 규칙이지 판단이 아니다(규칙 3).

`human_check_pending`: 그 스냅샷을 만든 뒤(`created_at` 이후) 들어온 접수 사람 확인(field `intake_status`) 중 같은 (단지, 확인 시각, 값)의
human_check 접수 행이 그 스냅샷에 없는 마지막 입력. 사람 확인 → 재판정이 새 리비전을 발행하면 그 리비전이 기본이 되어 항목이 빠지거나(가능·
미정·불가) '기타 · 사람 확인'(값 '확인 불가')으로 남는다.

## 2. 테스트 (먼저 쓰고 수정 전 실패 확인)

수정 전 = main `36894df` 의 임시 worktree 에 새 테스트 파일만 복사해 같은 venv 로 실행(백엔드), 화면은 `ops/index.tsx` 에서 패널을 뺀 상태로 실행.

| 테스트 | 확인하는 것 | 수정 전 |
| --- | --- | --- |
| `backend/tests/contracts/test_r7_queue_contract.py`(6) | 버전 `.19` 4곳(protocols·openapi 원본/번들·DECISIONS·CHANGELOG 맨 위), CHANGELOG `.19` FE 차이 표, operation 모양(파라미터 region_id·snapshot, 200·401·403·404·422·500), components 5 + `x-nonfact`, 예시 3개 스키마 통과·합계·순서, 모르는 category·unofficial_ref 경로 거절 | **6 실패**(`'2026-10-09.18' == '2026-10-09.19'`, `KeyError: '/ops/intake-queue'`, components 없음) |
| `backend/tests/api/test_r7_intake_queue.py::test_default_snapshot_queue_matches_contract` | devseed 스냅샷 12: 403·'접속 실패'·DNS → `collect_failed`, 미정 8 → `undecided`, 가능·unofficial_ref 만 있는 단지 없음, total 11, 계약 통과 | **실패**(404 Not Found) |
| `…::test_groups_follow_category_order_then_count` | 분류 순서 → 건수 내림차순 → 이름, 항목 단지 이름 순 | **실패**(`KeyError: 'groups'`) |
| `…::test_grouping_is_data_driven_from_stored_reason` | 저장 사유 11종(connect 세부·'TLS(브라우저 재시도 실패)'·404·동일성 2·문구 2·판정 미해결·'판정 대상 아님(공공분양)'·처음 보는 사유·사유 없는 503) → 기대 묶음 | **실패**(404) |
| `…::test_queue_key_rules[×15]` | 규칙 단위(숫자 사유·robots.txt 503·blocked_by_robots·render·소문자 dns·'수집 실패'·미분류·범위 경계·'사람 확인'·영문 새 사유·사유 없음·미정 2) | **15 실패**(`ModuleNotFoundError: app.api.intake_queue`) |
| `…::test_item_screenshot_and_judgment_ref`, `…::test_screenshot_found_by_path_when_row_points_elsewhere` | 스크린샷 원문 id(접수 행 원문이 그 경로면 그 행, 아니면 같은 경로 원문, 없으면 null — 지어내지 않음), 메모의 마지막 `jl_<seq>` | **실패**(404) |
| `…::test_human_check_pending_until_revision_has_it`, `…::test_human_check_before_snapshot_is_not_pending` | 접수 사람 확인 POST(201) → 발행 리비전 12 대기열에 반영 대기, 새 리비전(`snapshot=`)에서는 그 단지가 '가능'이라 없음. 스냅샷 전 옛 입력은 반영 대기 아님 | **실패**(404) |
| `…::test_region_without_snapshot_is_empty_200`, `…::test_explicit_snapshot_and_404s` | 스냅샷 없는 지역 200 + 빈 대기열, `snapshot=11`(리비전마다 따로), 없는 지역·스냅샷·다른 지역 스냅샷·범위 밖 id 404, 계약 밖 파라미터 422 | **실패**(404 / `KeyError: 'getIntakeQueue'`) |
| `…::test_readonly_token_reads_share_token_forbidden` | READONLY 200, 토큰 없음 401, 공유 링크 403 forbidden(D10-7) | **실패**(404) |
| `…::test_get_reads_only` | GET 3회 뒤 접수 행·사람 확인·잡·이벤트·스냅샷·판정 로그·원문 수 그대로, `app.judge.*` 새로 import 없음(규칙 4) | **실패**(404) |
| `backend/tests/api/test_schemathesis.py` | operation 40(새 경로 포함 — `test_contract` 가 getIntakeQueue 를 생성 예시로 검사), 앱 라우트에 빠짐 없음 | **실패**(`missing [('GET', '/ops/intake-queue')]`) |
| `backend/tests/contracts/test_openapi.py`·`test_protocols.py`·`test_core10_migrations.py` | 버전 단언 `.19`(core10 은 '.18 항목 유지 + .18 이상'), `IntakeQueue.total` 은 목록 건수(FACT_EXEMPT — `ComplexRowPage.total` 과 같음) | 계약만 올린 상태에서 실패 → 단언 갱신 |
| `frontend/src/pages/ops/intakeQueue.test.tsx`(6) | 분류·사유 건수·접힘·요청(스냅샷 지정, region_id 없음), 항목(G3 링크·배지·HTTP 메타·근거 링크·스크린샷·판정 로그·반영 대기·근거 없음), '사람 확인 입력' → URL `hc_complex=4&hc_field=intake_status#human-check` → 폼 값 → POST 본문 → 대기열 다시 읽어 반영 대기, 스냅샷 없음·빈 대기열 안내, 모르는 사유(other)도 그 이름 | 패널을 뺀 OpsPage 에서 **6 실패**(구역 없음) |
| `frontend/e2e/pages/pages.spec.ts` 'R7-QUEUE 화면'(MSW) | 사유별 건수·접힘 → '사람 확인 입력' → 폼 미리 채움 → 저장 → 반영 대기 | 새 테스트 |
| `frontend/e2e/api/writes15-r7queue.spec.ts`(실 API, 2) | 쓰기·읽기 전용 200·공유 링크 403·devseed 403/DNS → `collect_failed`; 화면에서 DNS 단지 → 폼 미리 채움 → 저장 201(재판정 자동 등록) → 반영 대기 → worker 1회(재판정·새 리비전 발행) → 새 리비전 대기열에서 '기타 · 사람 확인'(경로 사람 확인, 반영 대기 없음), /api 4xx·5xx 0 | 새 테스트 |

## 2-1. 조정자 추가 요청 — 자유 문장 입력의 '보이는 글자' 규칙(계약 `.19` F5·S1)

schemathesis RejectedPositiveData: `PATCH /claims/{id}` `{"text": "\u001e"}` 가 스키마(`minLength 1`)를 통과했는데 서버가 `strip()` 으로 비워
422 '비었다'. 요청 자유 문장 필드를 모두 보았다.

| 필드 | 서버(수정 전) | 어긋남 | 조치 |
| --- | --- | --- | --- |
| `ClaimPatch.text` | `strip()` 뒤 비면 422 · `"\x01"`·`"\ufeff"` 는 받아 재검증 잡으로 | 있음 | `pattern` + 서버 `has_visible` |
| `CatalystCreate.title` | 같음 | 있음 | 같음 |
| `RegionPatch.name` | `strip()` 뒤 비면 422(guard 문구) | 있음 | 같음 |
| `LivingAreaInput.name` | 정규화(`normalize.living_area` — 손대지 않음)가 `strip()` 뒤 비면 422 | 있음 | `pattern`(API `check_body` 가 정규화 전에 거절) |
| 사람 확인 `value_text`·`note`, `RegionCreate.name`·`query_text`, `ScenarioCreate.name`, 공유 링크 `label`, 체크리스트 `note`, 호재 `excerpt` | 공백만인 값을 거절하지 않음(그대로 저장·빈 값은 null) | 없음 | 그대로 |

규칙: `[^\u0000-\u0020\u007f-\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]` 가 한 번 이상(= C0·C1 제어, 파이썬 `str.isspace`
공백 전부, BOM 이 아닌 글자 1자 이상). 같은 문자열이 스키마 4곳의 `pattern` 과 `app.api.contract.VISIBLE_TEXT_PATTERN`(서버 `has_visible`)에 있다.
통과한 값은 `strip()` 해도 비지 않아 서버의 '비었다' 422 에 닿지 않는다.

| 테스트 | 수정 전(main) |
| --- | --- |
| `backend/tests/contracts/test_r7_visible_text.py`(5) — 4필드 `pattern` = 서버 상수, U+0000–02FF·U+1680·U+2000–206F·U+3000·BOM·ZWSP 등에서 스키마 통과 ⇔ `has_visible`, 통과 값 `strip()` 비지 않음, `str.isspace` 전부 불통 | 수집 오류(`ImportError: VISIBLE_TEXT_PATTERN`) |
| `backend/tests/api/test_r7_visible_text.py::test_contract_rejects_what_server_calls_empty[×3]` — 서버가 '비었다'로 거절하는 값을 계약(`check_body`)도 거절 | **3 실패**(`DID NOT RAISE ApiError` — RejectedPositiveData 재현) |
| `…::test_claim_revise_blank_text_is_schema_422[×6]` | `'\ufeff'`·`'\x01\x02'` **실패**(서버가 받음), 나머지 4 통과(서버 422) |
| `…::test_living_area_blank_name_is_schema_422` | **실패**(`"\x01"` 생활권 이름을 받음) |
| `…::test_catalyst_blank_title_is_schema_422`, `…::test_region_patch_blank_name_is_schema_422`, `…::test_claim_revise_visible_text_with_control_char_is_not_called_empty` | 통과(회귀 방지) |

## 3. 완료 검사 (결과는 보고와 같다)

main `80fca23`(Merge wp/r6-dong) 를 병합한 뒤(`git merge main` — 충돌 없음) 잰 값이다. 다른 에이전트 pytest 와 CPU 를 나눠 쓴 상태.

| 검사 | 결과 |
| --- | --- |
| `uv run pytest -p no:randomly -m "not live"`(backend 전체) | **4194 중 실패 0 · 오류 0 · 건너뜀 3**(1866초) |
| `ruff check app tests` · `ruff format --check` · `mypy app`(strict) | 통과 · 506 파일 정리됨 · 169 파일 문제 없음 |
| `gen_contracts.py --check` · `fixture_manifest.py --check` | 0 · 0(픽스처·매니페스트 변경 없음) |
| `python scripts/tasks.py regress` | T01~T18·모듈·흐름 전부 PASS, e2e 3 PASS(단계 종료 코드 [0, 0, 0]) |
| frontend `npm ci` · `typecheck` · `lint` · `format:check` | 통과 |
| `npm test`(vitest) | 65 파일 · 896 통과 |
| `npm run build` · `npm audit` | 성공(엔트리 청크 가드 `scripts/bundle-guards.test.ts` 통과) · 취약점 0 |
| `npm run e2e`(smoke + pages, 포트 6071·6072) | 46 · 23 통과(T16 perf 포함) |
| `npm run e2e:api`(새 `E2E_API_DATA`, 포트 18495·6091) | 47 통과(새 writes15 2 포함, /api 4xx·5xx 0) |
| `npm run lighthouse` | 13건 전부 80 이상 — `/ops` 데스크톱 성능 99 · 접근성 100 · 권장 100 · CLS 0.069, 모바일 최저 93 |

## 4. 하지 않은 것 · 제안

- **접수 행이 하나도 없는 단지**(청약홈에 공식 홈페이지 주소 없음 — 인천 5단지, 화면 '확인 불가(접수 행 없음)')는 대기열에 넣지 않았다(D26-2
  '확인 불가 접수 행' — 행 기준). 넣으려면 리비전 단지 목록(발행 저장본)을 읽어야 해 저장본 503(`materialize_pending`)을 떠안는다 — 필요하면
  다음 계약에서 `no_row` 분류로(제안).
- `docs/runbook.md` §2 '사유별 사람 확인 표'는 이 브랜치 소유 밖이라 고치지 않았다 — `SELECT reason, count(*) …` 대신 G7 '접수 확인 대기열'을
  쓰라는 한 줄과 분류 이름(수집 실패·공식 홈페이지 동일성·문구로 판단 불가·판정 미해결·판정 대상 아님·기타·접수 미정)을 runbook 담당이 더하기를 제안.
- 대기열은 발행 저장본(D13-1)에 넣지 않았다 — 운영 GET(`/ops/sources` 와 같음)이고 접수 행은 리비전마다 따로 저장되어 발행 리비전의 대기열이
  나중에 바뀌지 않는다(`human_check_pending` 만 그 뒤 사람 입력을 보인다).
