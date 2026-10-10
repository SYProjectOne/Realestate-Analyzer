# 계약 변경 기록

버전 = `날짜.연번`. 에이전트는 **맨 위 항목 하나만** 가정한다(AGENTS.md). 계약을 바꾸는 쪽은 오케스트레이터뿐이다.

## 2026-10-09.9

R3 4차 리뷰(`docs/design/wp/R3_REVIEW4.md`) 후속 — CEO 결정 D12(`docs/design/DECISIONS.md`)와 R3d 배정(`docs/design/wp/R3D_FIX.md`).
계약 소유자 = R3d CORE2(브랜치 `wp/r3d-core2`). 마이그레이션 `0009`(`0009_r3d.py`: 테이블 1개 추가 — 0008 DB 는 `alembic upgrade head`
한 번). 필드 삭제 없음. `0008` downgrade 는 끝난 `backup`·`region.expand` 잡 이력이 있으면 거부하도록 바꿨다(이력 손실 방지 — 대기 잡만 지운다).

**프론트(FE3)가 생성 타입으로 옮기며 맞출 것** — 아래 'FE 차이' 표. `frontend/src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 는 이 브랜치에서
다시 만들지 않았다(frontend/** = FE3 소유) — 머지 뒤 `npm ci` → `npm run gen:api`·`gen:msw` 로 다시 만든다.

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.8) | 이후(.9) | 결정·리뷰 |
| --- | --- | --- | --- | --- |
| S1 | 강등 오버레이(`app.facts_view`) | (entity, 행 id, field, 모순 값) — 같은 모순 가격·계약금을 실은 **새 공고 행**(무순위 병합 포함)이 오면 '추정'으로 복귀 | **(단지, 의미 필드, 모순 값)**: 의미 필드 = 가격(그 타입의 공고문 타입 행 + 모든 공고의 `price_by_type.<타입>.max_price_won`)·납부 조건 필드(모든 공고의 같은 필드)·단지 필드. 그 묶음의 어느 행이든 chosen 값이 모순 값이면 '확인 불가(검증 모순)'. 상태는 **지금 쓰는 행**(현재 구매가 max_ref·현재 공고·단지 행)으로: 사람 확인 → 복원, 원문의 **다른 값** → 복원(옛 행의 모순 값은 계속 가림), 값 없음·**채택 보류** → 유지(M-17), 새 출처로 풀린 뒤 모순 값이 다시 채택되면 재강등(critical change_event) | D12-2 · C-1 · M-17 |
| S2 | 사람 확인 우선순위(resolver) | 0순위지만 compare `adopted` 가 이김, 이후 새 공식 공고도 영구히 짐 | compare 채택은 사람 확인을 **이기지 못한다**. 사람 확인 **이후에** 관측된(observed_on > 사람 확인일) 공식 1차 출처(공고문·청약홈)가 **다른 값**이면 그 값 채택 + critical change_event(triggers_rejudge) + 체크리스트 '사실 재확인' 항목(제목 `사람 확인 재검토: <필드>`) | D12-1 · C-2 · M-10 |
| S3 | 할인 차감 | 표시 가격만 '확인됨일 때만', 보고서·`/compare` 계약금·자기자본·목록 필터·정렬은 라벨 무관 차감 | `analysis.price_view.current_price(…, discount_label=)` **필수 인자 하나**로 모든 경로(상세·목록 값·필터·정렬·비교·자금 요건·보고서·점수). 라벨 모름(None)이면 빼지 않는다. 0·음수·최고가 이상 할인은 확인됨이어도 빼지 않는다. 보고서 구매가 사유에 '− 할인 N만' | D12-3 · C-3 |
| S4 | '최신 리비전'(`rejudge_needed`) | 지역의 가장 새 스냅샷(building·미발행 포함) | 가장 새 **발행** (기준일, 리비전) — 판정 중 리비전이 생겨도 '재판정 필요' 배지가 사라지지 않는다 | D12-4 · M-1 |
| S5 | 사람 확인·생활권 편집·강등의 재판정 | 최신 published 기준일에 리비전, rejudge 는 제안(`suggested_job`) | 그 지역 **가장 새 (기준일, 리비전)** 의 쓰기 가능 리비전(발행됐으면 새 리비전)에 change_event + rejudge **자동 등록**(`HumanCheck.rejudge_job_id`; `suggested_job` 은 그 잡과 같은 payload — `POST /jobs` 로 보내도 대기 중인 같은 rejudge 를 돌려준다, 중복 없음). 일일 '변경 없는 날' 이월은 직전 발행 리비전의 점수 실행 뒤 다른 스냅샷에 붙은 사실 변경(triggers_rejudge)이 있으면 그 단지를 재판정(옛 점수를 now 로 복사하지 않는다) | D12-5 · M-2 · M-3 |
| S6 | 리비전 시점 값 | 분류·생활권·호재 단계/연결이 제자리 갱신 → 옛 발행 리비전 상세·시장·보고서가 나중에 바뀜 | 발행(`snapshots.publish`) 순간 `snapshot_state` 에 얼리고(region 생활권 · complex 분류·생활권·법정동 · catalyst 단계·종류·위치·연결) 그 스냅샷을 읽는 상세·목록·시장·대시보드·비교·보고서·diff 가 얼린 값을 쓴다. 얼린 값이 없는 스냅샷(발행 전·0009 이전)은 지금 값. '호재 아님'은 상세 catalysts·시장 보드·보고서 §5 에서 뺀다 | D12-4 · M-7 |
| S7 | 호재 연결 변경(`PATCH /catalysts`) | rejudge 잡 등록(점수에 쓰지 않는데 판정 파이프라인) | rejudge 없이 가장 새 발행 리비전의 새 리비전을 만들어 파생 행 복사 → 바로 발행(그 시점 연결을 얼림). 응답 `job` 은 늘 null. '호재 아님' 후보 연결·NaN/범위 밖 좌표는 422, `expected_ym: null` 은 지움 | D12-4 · minor · M-13 |
| S8 | 지역 선택 축소 | 빠진 단지가 '판정 대상'으로 남음(사다리 호출), §12 '제외' 0 | 법정동이 지역 밖이 된 단지는 분류와 무관하게 '범위 경계'(판정 범위 제외). §12 후보군 = 점수 실행의 rerank 범위(판정 대상·참고·보류) | M-4 |
| S9 | 비교 기준(revision_of) | 미발행 리비전 1 에서 지역 확장·판정기 버전 변경이면 비교 기준 없음 → §12·delta 표 누락 | 미발행 스냅샷에 비교 기준이 없으면 직전 발행 스냅샷을 `revision_of` 로 단다 | M-5 · M-6 |
| S10 | 보고서 | 같은 기준일 리비전 보고서 파일이 덮어써짐, building 리비전도 생성 | 파일 이름 `report_r<지역>_<기준일>-r<리비전>[_vs_<기준일>-r<리비전>][_<시나리오>]_j<잡 id>.<형식>`. 발행 전 스냅샷은 `POST /reports` 409(conflict). §12 요약은 rerank 를 다시 부르지 않은 리비전에 '다시 실행했다'고 쓰지 않는다 | C-4 · M-16 · minor |
| S11 | 정규화 | 잔여 공고 PDF 가 '최초 주택관리번호'로 원 단지 이름·세대수·전매·거주·규제를 덮음, 할인 줄 부분 문자열 매칭 | 그 공고의 **단지(complex) 후보는 건너뛴다**(납부 조건·타입 가격만). 할인 줄 = 타입 표기 토큰 전체 + 선납·계약금·중도금·발코니·옵션 할인 제외 + 다른 타입이 같은 줄이면 미채택 | M-8 · M-12 |
| S12 | 사람 확인 대상 | `entity_id` 가 complex_type·payment_terms 같은 번호면 complex_type | 화면·점수가 쓰는 현재 구매가 행 우선. 값: 단위 접미는 그 필드 단위만('N년'은 개월 필드에서 ×12), 지수·16진 표기 거부 | M-11 · minor |
| S13 | 기타 | — | `PATCH /regions` 이름만 바뀌면 change_event·job 없음(이름 guard 422). '사실 재확인' 을 강등 중 done 으로 닫으면 응답이 바로 open. `GET /provenance/fp_N` 은 강등 중이면 label '확인 불가'·reason '검증 모순 — …'. `GET /complexes/{id}?snapshot=` 다른 지역 스냅샷 404 | minor |

### 스키마 변경(선택 필드 추가·nullable — 옛 입력도 그대로 검증)

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `human_check.json` HumanCheck | `rejudge_job_id`(integer\|null) 추가 — 자동 등록한 rejudge 잡. `suggested_job` 은 그 잡과 같은 payload(호환, '기타'면 null). `POST /jobs` rejudge 는 같은 스냅샷 대기 rejudge 에 합쳐진다(중복 잡 없음). 예시 갱신 |
| 2 | `region.json` RegionPatched | `change_event` → change_event\|null, `job_id` → integer\|null(이름만 바꾼 경우) |
| 3 | `catalyst.json` | CatalystPatch 설명(위 S7), CatalystUpdated.job 설명(늘 null). 예시 요약 |
| 4 | `job_payloads/backup.json` | `keep_days` maximum 3650, 설명에 compose 백업 볼륨 |
| 5 | `report.json`·`openapi.yaml` createReport | `filename` 형식 설명·예시(`reports_list.json`·`jobs_list.json`), 409 에 발행 전 스냅샷 |
| 6 | DB `snapshot_state`(0009) | API 모양 변화 없음(S6 의 읽기 동작만) |

### FE 차이(FE3 — 화면이 맞출 것)

| 대상 | .8 | .9 |
| --- | --- | --- |
| `POST /ops/human-checks` 응답 | `suggested_job` 으로 화면이 `POST /jobs`(토스트 '재판정 실행') | `rejudge_job_id` = 이미 등록된 잡 — 화면은 잡 진행만 보이면 된다. `suggested_job` 은 같은 payload 로 남아(호환) 토스트 버튼으로 다시 보내도 같은 잡이 돌아온다(새 잡 없음). '기타'는 둘 다 null |
| `PATCH /regions/{id}` 응답 | change_event·job_id 늘 있음 | 이름만 바꾸면 둘 다 null |
| `PATCH /catalysts/{id}` 응답 | 연결이 바뀌면 `job`(rejudge) | `job` 늘 null — 연결이 바뀌면 새 리비전이 바로 발행되므로 regions·스냅샷 목록을 무효화한다(M-15 와 같은 처리) |
| `POST /reports` | building 리비전도 202 | 발행 전 스냅샷 409 — 비교·생성 선택에서 building 리비전 제외(M-16 화면) |
| 보고서 `filename` | `report_<기준일>[_vs_<기준일>].<형식>` | 위 S10 형식(그대로 표시) |
| 체크리스트 | — | 새 항목 제목 `사람 확인 재검토: <필드>`(kind '사실 재확인'). '사실 재확인' PATCH done 이 강등 중이면 응답 status 가 open(화면은 응답을 그대로 반영) |
| 단지 상세 `catalysts`·시장 보드 | '호재 아님' 포함 가능 | 빠진다. 발행 리비전은 그 시점 단계·연결 |
| `rejudge_needed` | building 리비전이 있으면 false | 가장 새 **발행** 리비전 기준 |
| 사람 확인 값 | '3년' = 3, '1E1' = 10 | '3년' = 36(개월), '1E1' 422 |
| `GET /provenance/fp_N` | 원 라벨 | 강등 중이면 '확인 불가(검증 모순 — …)' |

### 마이그레이션·검증

- `0009`: `snapshot_state`(id, snapshot_id FK·index, entity CHECK region·complex·catalyst, entity_id, data JSON, 유일 (snapshot_id, entity, entity_id)).
  upgrade = 테이블 생성(기존 발행 스냅샷은 행 없음 — 지금 값으로 읽는다), downgrade = 삭제(얼린 값 손실). head → 0008 → head 왕복과 0008 downgrade 의
  잡 이력 거부를 SQLite·Postgres 16(pgserver) 둘 다 테스트(`tests/contracts/test_migrations.py::check_0008_0009_roundtrip`), autogenerate diff 0.
- `CONTRACT_VERSION`·`info.version` = `2026-10-09.9`. 백엔드 생성물(`openapi.bundled.yaml`, `contracts_gen.py`) 재생성(`gen_contracts.py --check` 일치).
- infra(D12-6·M-9): worker 이미지에 PGDG `postgresql-client-16`(서버 postgres:16 과 같은 판 pg_dump), compose 백업 볼륨 `backups:/backups` +
  worker `BACKUP_DIR=/backups`(원문 볼륨과 분리). 계약 스키마 변경 아님.

### fixtures (R3d CORE2 — 계약 .9)

매니페스트(`contracts/fixtures.sha256.json`) 사유: R3d CORE2: 계약 .9 사람 확인 재판정 자동 등록(D12-5)으로 합성 판정 녹화 도구가 suggested_job 대신 rejudge_job_id 를 쓴다 — 녹화 데이터(봉투 293개)는 그대로
생성기(`tools/record_synth_judgments.py`) `--check` 일치(봉투 293개 — payload 변화 없음). 계약 스키마 외 데이터 변경 없음.

## 2026-10-09.8

R3 3차 리뷰(`docs/design/wp/R3_REVIEW3.md`) 후속 — CEO 결정 D11(`docs/design/DECISIONS.md`)과 R3c 배정(`docs/design/wp/R3C_FIX.md`).
계약 소유자 = R3c CORE(브랜치 `wp/r3c-core`). 마이그레이션 `0008`(`0008_r3c.py`: 컬럼 9개 추가 + 유일 제약 1개 교체 + CHECK 값 3개 추가 —
0007 DB 는 `alembic upgrade head` 한 번). 필드 삭제 없음.

**프론트가 초안(`R3C_FIX.md` '계약 .8 초안')과 다르게 받을 것** — 아래 #6·#2·#4·#5 굵은 글씨:
초안 `payment_terms.discount_won` → **`discount_by_type`**(컬럼 형 정책: `*_won` = BigInteger), `PATCH /catalysts` 응답은 Catalyst 가 아니라
**`CatalystUpdated {catalyst, links, job}`**, `PATCH /regions` 응답은 **`RegionPatched {region, change_event, job_id, added, removed}`**(잡 = `region.expand`,
rejudge 아님), HumanCheck 대상은 (entity, field) 쌍 목록이 아니라 **`field` enum(`HumanCheckField`) + 선택 `entity_id`**(entity 는 서버가 정해 응답에 싣는다).

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전 | 이후 | 결정·리뷰 |
| --- | --- | --- | --- | --- |
| S1 | 발행 스냅샷 | 재판정·사람 확인·같은 기준일 재수집이 발행 스냅샷 행을 고쳐 썼다 | **발행 스냅샷은 불변.** 그 기준일 최신 리비전이 발행됐으면 새 리비전(`revision`+1, `revision_of` = 바탕, `revision_reason`)을 만들어 거기에 쓴다(접수 상태 행은 복사, 파생 행은 비대상만 복사·대상은 새로 판정). `?snapshot=` 은 리비전의 snapshot id. 화면은 `GET /regions/{id}/snapshots` 의 가장 큰 리비전을 기본으로 | D11-1 · C-1 · M-2 |
| S2 | 사실 강등(`fact_demotion`) | 강등 때 사실 테이블 값을 비우고 출처 행을 바꿨다(재수집이 값을 되살림, GET 이 행을 고침) | **읽기 시점 오버레이**: 강등은 (entity, entity_id, field, `value_norm`) 기록만. chosen 값이 강등 값과 같은 동안 API·점수 입력·보고서·CSV 가 '확인 불가(검증 모순)'로 본다. 풀림 = 사람 확인(0순위 후보) 또는 **다른 값**의 새 원문뿐 — 같은 원문 재수집은 풀지 않는다. GET 은 쓰지 않는다 | D11-3 · C-3 · C-4 · M-3 · M-4 |
| S3 | 사람 확인 | `field` 자유 문자열, `intake_status` 만 반영 | `field` = `HumanCheckField` enum. 사실 필드면 resolver **0순위 후보**(`FieldCandidate.source_rank` 0, 라벨 확인됨, reason '사람 확인(…)')로 들어가 재정규화에도 원문을 이긴다 + 강등 해제 + change_event + 쓰기 가능 리비전에 rejudge 제안. `entity_id` 로 행 지정(가격 = payment_terms 또는 complex_type, 계약금 = payment_terms), 없으면 현재 공고·기준 타입. 강등 대상이 아닌 field·값 형식 오류는 422 | D11-3 · M-5 · minor 10 |
| S4 | 벤치마크 범위 | 화면·보고서·점수가 지역의 최신 벤치마크 행을 섞어 읽었다 | 모두 `api.benchmarks.benchmarks_for(snapshot)` 한 함수: 그 스냅샷 조립분 → 없으면 그 이전 가장 최근 조립분 → 없으면 snapshot_id NULL 행. 같은 기준일 두 번째 주간 수집이 표본 수를 바꾸지 않는다. 0006 이전 NULL 자동 행을 새 조립이 넘겨받지 않는다(minor 25) | C-1 · M-6 · minor 25 |
| S5 | 잔여(무순위·임의·잔여세대) 공고 병합 | 병합된 잔여 공고가 원 단지의 단지 단위 필드(입주월·세대수 등)를 덮었다, 이름 키가 '(2차 잔여세대)'의 차수까지 지웠다 | 병합 공고는 **자기 공고 단위**(payment_terms·remaining_event)만 쓴다. 이름 키는 공급 구분 괄호(회차·무순위·임의·잔여…)만 지우고 차수·단지·블록은 남긴다 — '(22차)'·'(2차)'는 다른 단지 | D11-4 · C-2 · M-7 · M-8 · minor 18 |
| S6 | 체크리스트 닫힘 | 근거가 사라져도 열린 채, 사람 'na' 와 자동 닫힘 구별 없음 | `closed_by`: auto = 동기화가 닫음(근거 사실 사라짐·강등·단지 제외 — 근거가 돌아오면 다시 연다), human = 사람이 PATCH 로 닫음(동기화가 다시 열지 않는다). 강등 중 사람이 done 해도 '사실 재확인'은 다시 열린다 | M-9 · minor 12 |
| S7 | '호재 아님' | 판정기 '호재 아님'이면 catalyst 행을 지웠다(연결·출처까지) | 지우지 않는다. 뉴스 후보 → `stage` '호재 아님'(목록·보드·점수에서 제외), 사람이 넣은 호재 → 단계 유지 + note 에 '판정기: 호재 아님' 병기. `catalysts_discarded` 항목에 `kept: true` | D11-2 · M-10 |
| S8 | `rejudge_needed` | 저장 범위 ≠ 현재 범위면 어느 스냅샷이든 true | 그 지역 **최신 리비전**에서, score_run 실행 **뒤** 바뀐 사실로 범위가 달라질 때만 true(발행된 옛 리비전은 늘 false). 목록 CSV 에 `rejudge_needed` 열(0/1) | minor 2 · minor 5 |
| S9 | 상황 B·D 접근성 | 접수 상태만 봤다 | §6-7: A·C = 비공식 경로 포함 접수 가능 AND 통장 조건, B·D = **현재 조건 공고의 공급 경로**(`ComplexScoreInput.current_supply_kind` 무순위·임의·선착순)이고 접수 가능일 때만 충족. 규제 = 재당첨제한·규제지역도 본다 | RA 부분(§6-7) |
| S11 | `ComplexScoreInput` 라벨(파이프라인·미리보기) | `price_label` = 최고가 출처 라벨만, 미리보기는 null. 값이 있는데 출처 행이 없으면 null(→ '확인됨'으로 합성) | `price_label` = 구매가 low·high 구성 필드(공급가·대표층가·발코니·옵션·할인) 출처 라벨 중 가장 약한 것(API `price_range` 와 같음, 출처 행이 하나라도 없으면 null → gap '확인 불가(가격 출처 누락)'). 파이프라인은 값이 있는데 출처 행이 없는 사실 라벨을 **'확인 불가'** 로 싣는다(null 의미 '값이 있으면 확인됨'은 외부 입력용으로만 남음) | minor 6 |
| S10 | 계약 외 메서드 | 매개변수 경로와 모양이 같은 글자 경로(`/regions/resolve` PATCH)가 422 | 계약에 없는 메서드면 405 + `Allow`(글자 그대로 경로 우선 매칭) | D11-7 후속 |

### 스키마 추가(선택 필드 — 옛 입력도 그대로 검증)

| # | 대상 | 변경 | 결정·리뷰 |
| --- | --- | --- | --- |
| 1 | `snapshot.json` Snapshot | `revision`(integer ≥1, **선택·기본 1** — 서버 응답엔 늘 실림), `revision_of`(integer\|null), `revision_reason`(string\|null). 유일 (region_id, asof_date) → (region_id, asof_date, revision). 예시 `snapshots_list.json` 등 갱신 | D11-1 |
| 2 | `human_check.json` | `$defs/HumanCheckField` enum(`intake_status`·`max_price_won`·`move_in_ym`·`resale_months`·`residency_months`·`down_payment_pct`·`other`), HumanCheckCreate `field` → enum·`entity_id`(선택)·`value_text` maxLength 200·`note` maxLength 500, HumanCheck `entity`·`entity_id`(바뀐 사실 행, 접수 상태·기타·옛 행 null). 마이그레이션 `human_check.entity·entity_id` | D11-3 · M-5 |
| 3 | `field_candidate.json` | `source_rank` minimum 1 → **0**(0 = 사람 확인) | D11-3 |
| 4 | `catalyst.json` + `PATCH /catalysts/{id}`(operationId `updateCatalyst`) | `stage` enum 에 '호재 아님', Catalyst `lat`·`lon`(사람 확인 좌표, null), `$defs/CatalystPatch {location_confirmed, lat?, lon?, living_area_ids?, complex_ids?, expected_ym?}`, `$defs/CatalystLinkView {complex_id, distance_m, weight, label, reason}`, `$defs/CatalystUpdated {catalyst, links, job}`. location_confirmed=true 면 생활권·단지로 catalyst_link 생성(좌표 거리 없으면 distance_m null, weight 1, 라벨 추정), false 면 연결 삭제, 영향 범위 없이 true 는 422. 연결이 바뀌면 rejudge 잡. `ComplexDetail.catalysts` 가 연결된 호재로 채워진다. 마이그레이션 `catalyst_link.label·reason`, `catalyst.stage` CHECK | D11-5 · D11-2 |
| 5 | `region.json` + `PATCH /regions/{id}`(operationId `updateRegion`) | `$defs/RegionPatch {selections, name?}`(바뀐 뒤 전체), `$defs/RegionPatched`. 법정동·시군구·생활권 재계산(기존 생활권 그대로, 추가 시군구는 새 생활권), change_event critical, `region.expand` 잡. 그대로면 409 | D11-7 |
| 6 | `payment_terms.json` `discount_by_type` · `complex_detail.json` PriceView `discount` | 공고에 적힌 할인(타입별 Fact, 원). 라벨 확인됨일 때만 low·high·mid 에서 빼고 composition 에 '− 할인' 표기, 아니면 표시만. 마이그레이션 `payment_terms.discount_by_type`(JSON) | D11-6 |
| 7 | `checklist_item.json` | `closed_by`('auto'·'human'·null). 마이그레이션 `checklist_item.closed_by` | M-9 |
| 8 | `job_run.json` JobName · JobCreateName, `job_payloads/backup.json`·`region_expand.json` | 잡 이름 `backup`(매일 03:00 worker — DB 백업 + 원문 증분 복사, `keep_days` 선택, POST /jobs 가능), `region.expand`(PATCH /regions 만 — JobCreateName 에서 제외). 마이그레이션 `job_run.job_name` CHECK | D11-8 · D11-7 |
| 9 | `score_inputs.json` ComplexScoreInput `current_supply_kind` | 현재 조건 공고의 공급 경로(본청약·무순위·임의·선착순 등, null = 미상) — S9 | RA §6-7 |
| 10 | `fact_demotion.value_norm`(DB 만 — API FactDemotion 모양 그대로) | 강등한 모순 값의 정준 문자열(S2 오버레이 비교) | D11-3 |

### 마이그레이션·검증

- `0008`: 위 컬럼 + 유일 제약 교체 + CHECK 3개. SQLite 는 batch(재생성 정의 고정, 제약 이름 `op.f`), Postgres 는 ALTER.
  downgrade 는 리비전 2 이상 스냅샷이 있으면 **실패**(유일 제약을 되돌리면 리비전 행이 지워져야 해서 — 데이터 손실 방지), '호재 아님'
  catalyst → '미확정', 새 잡 이름 행 삭제, 나머지 컬럼 삭제. head → 0007 → head 왕복 SQLite·Postgres 16(pgserver) 테스트, autogenerate diff 0.
- `0006` docstring 에 downgrade 손실 표(fact_demotion·claim 대상 컬럼·'사실 재확인' 항목 — 재upgrade 뒤 재강등 가능) 추가(CEO 요청).
- `infra/.env.example`: `ENV=prod` + Postgres `DATABASE_URL` 기본, 로컬 dev(SQLite) 안내는 주석으로(D11-9 prod+SQLite 거부와 맞춤).
  새 설정 `JUDGE_SECRET_ENV_NAMES`(쉼표 구분 — 판정기 자격 증명 env 이름, 그 값은 판정기 stderr·오류에서 가림; CEO 요청 minor 32 후속).
  계약 스키마 변경 아님.
- `CONTRACT_VERSION`·`info.version` = `2026-10-09.8`. 백엔드 생성물(`openapi.bundled.yaml`, `contracts_gen.py`) 재생성.
  MSW 예시: `catalyst_patch_req.json`·`catalyst_updated.json`·`region_patch_req.json`·`region_patched.json` 추가, 스냅샷·지역 예시에 revision.
- 프론트 생성물(`src/api/schema.d.ts`·`src/mocks/handlers.gen.ts`)은 main(R3c FE 머지 뒤) 위에서 `npm ci` → `npm run gen:api`·`gen:msw`
  로 다시 만들어 커밋했다. `npm run typecheck` 통과(오류 0). 화면은 아직 초안 타입(`frontend/src/api/contract8.ts`)을 쓴다 — 아래 차이를
  FE 가 생성 타입으로 옮기며 맞춘다.

### FE 초안 타입(`frontend/src/api/contract8.ts`)과 확정 계약의 차이

typecheck 를 깨는 차이는 없다(초안 타입은 생성 타입과 따로 선언돼 있다). 런타임·화면에서 맞춰야 할 것:

| 대상 | 초안(contract8.ts) | 확정(.8) |
| --- | --- | --- |
| `PATCH /regions/{id}` 응답 | `RegionPatched {region, job: JobRun}` | `RegionPatched {region, change_event, job_id, added, removed}` — 잡은 객체가 아니라 `job_id`(region.expand), 변경 이벤트·추가/제거 선택이 같이 온다 |
| `PATCH /regions/{id}` 본문 | `{selections}` | `{selections, name?}` |
| `PATCH /catalysts/{id}` 응답 | `CatalystPatched {catalyst, links}` | `CatalystUpdated {catalyst, links, job}` — `job` 필수(연결이 그대로면 null, 바뀌면 rejudge 잡) |
| catalyst_link 행 | `CatalystLink {complex_id, distance_m, weight: number, label}` | `CatalystLinkView {complex_id, distance_m, weight: number\|null, label, reason}` — `reason`('같은 생활권'·'사람 지정') 필수 |
| `PATCH /catalysts/{id}` 본문 | `living_area_ids?`·`complex_ids?` 배열 | 같은 이름, null 허용 + `expected_ym?`(YYYY-MM) 추가. 영향 범위 없이 `location_confirmed=true` 는 422 |
| 사람 확인 값 범위(`HUMAN_CHECK_RULES`) | `max_price_won` min 1, `move_in_ym` 형식만 | 서버: `max_price_won` 10,000,000 ~ 100,000,000,000(원), `move_in_ym` 2000-01 ~ 2100-12, `down_payment_pct` 소수 둘째 자리까지, 정수 필드 소수는 422(자르지 않음) |
| `HumanCheck` 응답 | (초안에 없음) | `entity`·`entity_id`(서버가 정한 사실 행, 접수 상태·기타는 null) |
| `HumanCheckField`·길이 상한·Snapshot `revision*`·stage '호재 아님' | — | 초안과 같다 |

### fixtures (R3c CORE — 계약 .8)

이 브랜치에서 두 번 다시 만들었다(변경마다 새 사유 — 매니페스트 history):
1. 매니페스트 사유: R3c CORE: 계약 .8 스냅샷 리비전(발행 스냅샷 재판정은 새 리비전 — 봉투 snapshot_id 12→13)과 §6-7 상황 B·D 접근성(현재 공고 공급 경로)으로 상황 decide payload 3건 변경 — 합성 판정 녹화 재생성
2. 매니페스트(`contracts/fixtures.sha256.json`) 사유: R3c CORE: minor 6 파이프라인 구매가 라벨 = 구성 필드(공급가·발코니·옵션) 중 가장 약한 라벨(API 와 같음)로 카드·명제의 가격 라벨이 바뀌어 decide 5·noul 30·rerank 1 payload 변경 — 합성 판정 녹화 재생성

생성기(`tools/record_synth_judgments.py`)로만 다시 만들었고 `--check` 일치(봉투 293개). 계약 스키마 외 데이터 변경 없음.

## 2026-10-09.7

R3b 마무리(CEO 위임, 브랜치 `wp/r3b-closing`) — R3b 가 '계약 .6 요청'으로 남긴 두 자리. 계약 소유자 = R3b 마무리.
마이그레이션 `0007`(`0007_r3b_closing.py`: 컬럼 1개 추가 + 데이터 채움 — 0006 DB 는 `alembic upgrade head` 한 번). 필드 삭제 없음.
의미 변경 = 대체 벤치마크 판별 근거가 note 문자열 → 컬럼(아래 #2). 둘 다 선택 필드(기본 null/false)라 옛 입력도 그대로 검증된다.

### 요청별 반영

| # | 출처 | 대상 | 변경 | 영향 |
| --- | --- | --- | --- | --- |
| 1 | R3 M2(재리뷰 부분) · G2 요청 | `score_inputs.json` ComplexScoreInput `winner_label` | 당첨자 발표일(winner_date) 값의 Fact 라벨(label 또는 null). 전매 종료 = 당첨일 + 전매 기간이므로 **유동성 성분 라벨·요건 사전 계산(전매 종료) 라벨 = resale_label 과 winner_label 중 약한 것**(`analysis.complex_input.resale_input_label`). 입력 조립: 파이프라인 `scheduler.inputs.load_facts`(chosen 출처 행 라벨 → labels['winner']) → `analysis.complex_input.build_complex_input`, API 시나리오 미리보기(`routers/analysis.py`)도 같은 키. 이 때문에 요건 근거 문구('전매 종료 … (추정)')가 바뀌어 상황 decide payload 1건이 달라졌다 → 합성 판정 녹화 재생성(아래 fixtures) | analysis(라벨 합성), scheduler(입력 조립), API(미리보기) |
| 2 | R3b G1·G2 요청(N-M4 후속) | `score_inputs.json` BenchmarkInput `substitute`(boolean, 기본 false), 테이블 `benchmark.substitute`(Boolean NOT NULL, 기본 false), `market.json` BenchmarkView.substitute 설명 | 지역 전체 대체 행(D9-2: 생활권 자체 표본 0 → 지역 전체 표본 복사, 라벨 추정) 표식을 **컬럼**으로. 판별부 전부 교체: 정규화(`normalize.benchmark` 가 대체 행에 true 를 쓴다), 점수(`analysis.score.benchmark_component` 가 `BenchmarkInput.substitute` 로 '대체(지역 전체)' 표기 — `run_detailed(substitute_benchmarks=…)`·`scheduler.inputs.substitute_benchmark_ids` 삭제), API(`api.benchmarks.is_substitute`), 보고서(`reports.data`). note 의 '추정(대체: 지역 전체)' 문구는 사람이 읽는 설명으로만 남는다(문구만 있고 컬럼 false 인 행은 대체가 아니다) | normalize, analysis, scheduler, API, reports |
| 3 | R3b 마무리 지시 2 | `complex.official_site_url`(기존 컬럼 — 스키마 변경 없음) | 정규화가 채운다: 청약홈 API 상세 `HMPG_ADRES`·웹 상세 '당첨자 발표일' 칸의 홈페이지 링크 → `normalize._text.normalize_site_url`(http/https 만, 스킴 없으면 http://, 빈 경로 '/', 청약홈 자신·'없음' 제외) → 후보(rank 1, 확인됨, 발췌 = 원문 조각) → 출처 행 + complex.official_site_url. official_site 수집기는 targets 가 없으면 이 컬럼을 대상으로 쓴다(수집 단계 순서 applyhome → official_site 라 같은 수집 잡에서 이어진다) | normalize, collectors(official_site) |

### 마이그레이션·검증

- `0007`: `benchmark.substitute`(Boolean, server_default false, NOT NULL). upgrade 는 기존 행 중 note 에 '추정(대체: 지역 전체)' 가 있는 행을 true 로
  채운다(파이썬에서 부분 문자열 판별 — DB 별 LIKE·인코딩 차이 없이). downgrade 는 컬럼 삭제(note 는 남는다). 0006 → head → 0006 → head
  왕복을 SQLite·Postgres 16(pgserver) 둘 다 테스트(`tests/contracts/test_migrations.py::test_sqlite_0006_0007_roundtrip`, Postgres 같은 함수),
  autogenerate diff 0.
- `CONTRACT_VERSION`·`info.version` = `2026-10-09.7`. 생성물(`openapi.bundled.yaml`, `contracts_gen.py`, 프론트 `schema.d.ts`) 재생성(MSW 예시 변경 없음).

### fixtures (R3b 마무리 — 계약 .7)

매니페스트(`contracts/fixtures.sha256.json`) 사유: R3b 마무리: 계약 .7 winner_label(당첨일 라벨이 전매 종료 요건 근거에 합쳐짐)로 상황 decide payload 1건 변경 — 합성 판정 녹화 재생성
생성기(`tools/record_synth_judgments.py`)로만 다시 만들었고 `--check` 일치(봉투 293개, decide 1건 hash 교체). 계약 스키마 외 데이터 변경 없음.

## 2026-10-09.6

R3 재리뷰(`docs/design/wp/R3_REVIEW2.md`) 후속 — CEO 결정 D10(`docs/design/DECISIONS.md`)과 R3b 수정 라운드 배정
(`docs/design/wp/R3B_FIX.md`). 계약 소유자 = R3b G3. 마이그레이션 `0006`(`0006_r3b.py`: 테이블 1개 추가 + 컬럼 4개 추가 +
checklist_item CHECK 값 1개 추가 — 0005 DB 는 `alembic upgrade head` 한 번). 필드 삭제 없음. 의미 변경 = 아래 #5(POST /jobs 의
claim.reverify 거부)·#4(BenchmarkFlag.sample_n = 자기 생활권 표본만) 두 가지.

### 요청별 반영

| # | 출처 | 대상 | 변경 | 영향 |
| --- | --- | --- | --- | --- |
| 1 | G2 요청 · N-C1 · D10-1 | `score_row.json`·`complex_row.json`·`dashboard.json` `rejudge_needed` | boolean(선택, 기본 false). 행의 judge_scope·rank·total·성분은 그 스냅샷 score_run **저장값**이고, 현재 사실로 계산한 범위가 저장 범위와 다르면 true — 화면은 '재판정 필요' 배지 + rejudge 잡 제안만(저장값·현재값을 한 행에 섞지 않는다). Dashboard 는 top5·KPI 중 하나라도 true 면 true | G2(씀, `api/views.py`·`routers/snapshots.py`), G3(프론트 배지), G4(보고서 표기 선택) |
| 2 | N-C3 · D10-3 | `claim.json` Claim·ClaimView `entity`·`entity_id`·`field`, 마이그레이션 `claim.entity·entity_id·field` | 주장이 생성된 DB 사실(field_provenance 의 entity·entity_id·field). P9 사실 문장 주장만 채운다 — NULL = 사실 주장 아님 또는 0006 이전 행(API 는 P9 문장 형식으로 대상을 되찾아 PATCH 때 채운다: `app.api.claim_target`). ClaimView 에 `field_name`(표시 이름)·`demotion`(FactDemotion) | G2(P9 저장 시 채움 — 요청), G3(API·G7), G1(ClaimSplitter 는 그대로) |
| 3 | N-C3 · D10-3 | `claim.json#/$defs/FactDemotion`, 테이블 `fact_demotion`, `checklist_item.kind` '사실 재확인', `fact.json` reason '검증 모순', PATCH /claims 422 | **강등 라벨 = '확인 불가(검증 모순)'**(label '확인 불가' + reason '검증 모순'). PATCH /claims/{id} 는 같은 대상(section·complex·field)만 허용(원자 주장마다 원 field 용어 있음·다른 사실 필드 용어 없음·다른 단지 이름만 가리키지 않음 — 문자열 대조, 어기면 422 `error_422_claim_target`). 사실 주장이면 접수와 함께 강등: 사실 테이블 값 비움(점수·요건 입력에서 빠짐) + chosen 출처 행 = 강등 행(원래 chosen 행은 chosen=false 보관) + 체크리스트 '사실 재확인: <필드 이름>(검증 모순)' + change_event critical(triggers_rejudge) + 그 단지 rejudge 잡. 복원 = 사람 확인(POST /ops/human-checks 같은 단지·같은 field — 그 값이 사실, 라벨 확인됨 reason '사람 확인(…)') 또는 새 원문(정규화가 다른 출처 행을 chosen 으로 올림 — 다음 조회 때 `restored_by='new_source'`로 기록), 체크리스트 done | G3(API·G7), G2(점수 입력은 값 null 로 자연히 빠짐 — 변경 없음), G1(체크리스트 동기화가 '사실 재확인' 항목을 건드리지 않음) |
| 4 | G1 요청 · F1a minor(`models/market.py:39`) | `benchmark.snapshot_id`(FK snapshot.id, NULL, 색인), `market.json` BenchmarkView `snapshot_id`·`substitute` | 벤치마크 행을 조립한 스냅샷 — 재조립이 발행 스냅샷이 인용한 행을 지우지 않게(G1 이 씀). API(G6 market)는 그 스냅샷 행(snapshot_id = sid)을, 없으면 sid 이전 가장 최근 조립분을, 그것도 없으면 NULL 행(이전 행·사람 입력)을 보인다. `substitute` = 지역 전체 대체 행(note '추정(대체: 지역 전체)') | G1(씀), G3(읽음), G4(보고서 인용 — 선택) |
| 5 | N-M3 · N-M4 · D9-2 | `market.json#/$defs/BenchmarkAbsence`, Market·Dashboard `benchmark_absence`, BenchmarkFlag `substituted`·`sample_n` 의미 | 벤치마크 없음 사유: 점수에 쓸 벤치마크 행(분양권 제외)이 지역에 0이면 `{code, reason}`(not_collected 실거래 수집 전 · presale_only 분양권 사례만 · no_sample 생활권·지역 전체 표본 0), 있으면 null. 화면 '벤치마크 없음(<reason>)'. **sample_n = 자기 생활권 표본만**(대체 행·분양권 제외 — 대체까지 세면 '표본 3 미만' 배지가 빠지던 N-M4), substituted = 자기 표본 0 → 지역 전체 대체 | G3(API·G1·G6), G4(보고서 §5 사유 — 같은 함수 `app.api.benchmarks.benchmark_absence` 사용 권장) |
| 6 | N-C3(F3 minor) | `job_run.json#/$defs/JobCreateName`, JobCreate.job_name | POST /jobs 로 등록할 수 있는 잡 = JobName − claim.reverify. claim.reverify 는 PATCH /claims/{id} 로만(같은 대상 검사·강등 우회 방지) → POST /jobs 는 422 | G3, 프론트(G5·G7 잡 등록 폼 타입). SourceStatus.retry(RetryHint).job_name 도 JobCreateName(POST /jobs 로 그대로 보내는 값) |
| 7 | D10-7 | bearerAuth 설명 | 공유 링크 토큰은 화면 조회 GET 만 — `/ops/*`·`/jobs`·`/jobs/*` 는 GET 도 403. READONLY_TOKEN 은 모든 GET | G3 |

### 마이그레이션·검증

- `0006`: `claim.entity·entity_id·field` + `benchmark.snapshot_id`(FK·색인) + `fact_demotion` 테이블 + `checklist_item.kind` CHECK '사실 재확인'.
  SQLite 는 batch(재생성 정의 고정), Postgres 는 ALTER. downgrade 는 fact_demotion 삭제 → '사실 재확인' 항목을 '법적 확인'으로 → CHECK·컬럼
  되돌림(강등으로 비운 사실 값은 되돌리지 않는다 — 출처 행은 남는다). head → 0005 → head 왕복을 SQLite·Postgres 16(pgserver) 둘 다 테스트
  (`tests/contracts/test_migrations.py::test_sqlite_0005_0006_roundtrip`, Postgres 같은 함수), autogenerate diff 0.
- `CONTRACT_VERSION`·`info.version` = `2026-10-09.6`. 생성물(`openapi.bundled.yaml`, `contracts_gen.py`, 프론트 `schema.d.ts`·MSW) 재생성.

### fixtures (R3b G1 — 계약 .6)

매니페스트(`contracts/fixtures.sha256.json`) 사유: R3b G1: 호재 분류 payload 에 '호재 아님' 클래스(D10-6) — 합성 판정 녹화 재생성
생성기(`tools/record_synth_judgments.py`)로만 다시 만들었다(classify 호재 단계 녹화의 hash 가 바뀜). 계약 스키마 변경 없음.

### fixtures (R3b G2 — 계약 .6)

매니페스트(`contracts/fixtures.sha256.json`) 사유: R3b G2: 호재 종류 classify·단계 입력(종류 제외)·wait_new 근거(미해결 제외) — 합성 판정 녹화 재생성
생성기(`tools/record_synth_judgments.py`)로만 다시 만들었다 — P4 호재 종류 classify 추가(D10-6), 호재 판정 입력에서 수집 kind 를 뺌
(종류 classify 결과가 다음 입력을 바꾸지 않게), 상황 A decide 의 가상 후보 근거에서 포함 분류 미해결 단지 제외(재리뷰 F2). 계약 스키마 변경 없음.

## 2026-10-09.5

R3 마무리(CEO 위임, 브랜치 `wp/r3-closure`) — 상황 A decide 의 가상 후보 '모집공고 대기'(보고서 §8-2·§12-5-2: decide 후보 =
TOP 5 + "모집공고 대기" + escape hatch). 소규모 변경: 필드 1개 추가(선택, 기본 false) + 데이터 마이그레이션 `0005_wait_new`
(DDL 없음). 필드 삭제·의미 변경 없음. decision 의 `option_key` 'wait_new'·`complex_id` null·`label` 은 계약 .1 부터 있던 자리다.

### 요청별 반영

| # | 출처 | 대상 | 변경 | 영향 |
| --- | --- | --- | --- | --- |
| 1 | R3 마무리 3c · 보고서 §8-2·§12-5-2(#84·#126) | `schemas/scenario.json#/$defs/ScenarioPolicy` | `include_wait_new`(boolean, 선택, 기본 false) — P8 decide 에 가상 후보 `wait_new`("12개월 내 공고 예정 단지를 기다림")를 넣는다. 단지 후보는 순위 상위 ≤5 + wait_new(합 ≤6, `judge/payloads.DECIDE_MAX`). 근거 = 지역 (A) 트랙 공고 예정 목록 요약(decide evidence `[wait_new]` 블록, `scheduler.payloads.wait_new_evidence`). decision 행 = option_key 'wait_new'·complex_id null·요건 판정(판정기 판정만, 사전 계산 없음) | scheduler(P8·미리보기), judge(payload·DecisionSet), API(compare 요건 표시), 프론트 C7('가상 후보' 표시) |
| 2 | 같음 | 마이그레이션 `0005_wait_new`, `analysis.scenarios.BUILTIN_SCENARIOS`, `examples/scenarios_list.json`·`scenario_created.json` | 내장 시나리오 policy 에 `include_wait_new` 명시 — **A(가점 높음·실거주)만 true**(보고서 #126 상황 A 재판정 '후보 6(+wait_new)'). 사용자 시나리오는 건드리지 않는다(키 없음 = false) | 위와 같음 |

### 마이그레이션·검증

- `0005_wait_new`: scenario.policy(JSON) 데이터만 — 내장 5개에 `include_wait_new` 기록(base·B·C·D false, A true).
  downgrade 는 모든 행에서 키를 지운다(옛 ScenarioPolicy 는 additionalProperties=false). head → 0004 → head 왕복 테스트
  (`tests/contracts/test_migrations.py::test_sqlite_0004_0005_roundtrip`, Postgres 같은 함수).
- `CONTRACT_VERSION`·`info.version` = `2026-10-09.5`. 생성물(`openapi.bundled.yaml`, `contracts_gen.py`, 프론트 `schema.d.ts`·MSW) 재생성.

### fixtures (R3 마무리 2026-10-09 — CEO 결정·계약 .5)

매니페스트(`contracts/fixtures.sha256.json`) 사유: R3 마무리: 마리나베이 접수 '미정'(CEO 결정) + 상황 A 가상 후보 wait_new(계약 .5)·mock 재생 judgment_log 기록으로 합성 판정 녹화 재생성
모두 생성기(`tools/build_incheon_gimpo.py`·`tools/record_synth_judgments.py`)로 다시 만들었고 `--check` 바이트 일치.

- **`incheon_gimpo_2026-10-08/complexes.json` — 12 더샵 송도마리나베이 접수 '불가' → '미정'** (원천 `tools/incheon_gimpo_complexes_b.py`).
  사유(CEO 결정): 보고서 표기 '마감(4회차 미정)'은 공고 이력(무순위 1~3회차)이 있고 추가 공급이 미정이다 → meta §1-3-4 상
  '미정'(그란테르 W1 과 같은 논리). 골든 v2 inputs 의 judge_scope '판정 대상'과 일치한다(v2 intake_status '불가'는 보고서 표기 그대로라
  T1(b) DB 경로는 이 필드를 점수 무관 차이로 둔다 — 둘 다 '가능'이 아니다). 연쇄: D9-1 판정 대상 10 → 11, 사다리 30 → 33(파이프라인 테스트),
  README 'D9-1로 인한 차이' 표에서 마리나베이 행 삭제.
- **`incheon_gimpo_2026-10-08/judgments_synth/` 재생성** — (1) 마리나베이 판정 대상화로 noul·rerank·decide payload 변경, (2) 상황 A
  decide 에 가상 후보 wait_new(계약 .5) → 보고서 #126 선택 wait_new .94(conf .93) **그대로** 녹화(합성 녹화의 '보고서 선택이 후보에
  없으면 확률 최대 후보로 대체 + 경고' 경로 삭제 — 이제 그런 경우 녹화 실패), (3) 녹화 흐름이 재생(MockAdapter)과 같게 judgment_log 에
  남겨 judgment_seq 를 단다(아래 앱 변경) — 녹화 흐름의 점수·순위가 재생과 같아져 decide 후보가 회귀·e2e 재생과 일치. 봉투 파일 형식은 같다.
- 앱 변경(같은 브랜치): `app.judge.mock.MockAdapter(session_factory=)` — 재생한 녹화 봉투를 judgment_log 에 남기고 judgment_seq 를
  단다(`get_adapter` 가 설정 DB 를 넘긴다). 전에는 mock 재판정의 판정 확률이 전부 '확인 불가(출처 누락)'(prov 없음)라 종합 점수가
  미계산이었다(W2 의 목적이 반만 이뤄짐 — test_d91_scope 첫 테스트는 마리나베이의 남은 사다리 행 덕분에만 통과하고 있었다).

## 2026-10-09.4

R3 독립 리뷰(`docs/design/wp/R3_REVIEW.md`) 후속 — CEO 결정 D9(`docs/design/DECISIONS.md`)와 R3 수정 라운드 F3 카드
(`docs/design/wp/R3_FIX.md`). 계약 소유자 = R3 F3. 마이그레이션 `0004_r3`(테이블 1개 추가 + job_run CHECK 값 1개 추가 —
0003 DB 는 `alembic upgrade head` 한 번 — 컬럼·CHECK·유일 제약 변경 포함, 아래). 필드 삭제 없음. 의미 변경 = JudgeScope 값 하나 추가(아래 #1)뿐.

### 요청별 반영

| # | 출처 | 대상 | 변경 | 영향 |
| --- | --- | --- | --- | --- |
| 1 | C2 · D9-1 · F2 요청 | `schemas/score_row.json#/$defs/JudgeScope`, `enums.JUDGE_SCOPE` | 값 `미해결` 추가(판정 대상·보류·참고·**미해결**·제외). 포함/제외 classify 가 review·escaped·미분류면 미해결 — 판정 대상 아님, 사다리·점수 없음. 설명에 D9-1 규칙 5개(공용 함수 `analysis/scope.py judge_scope()`) | F2(씀), F3·F4(읽음·표시) |
| 2 | M8 · RA §10 | `GET /snapshots/{sid}/claims?status=`, `PATCH /claims/{id}`, `schemas/claim.json#/$defs/ClaimView·ClaimPatch`, `job_payloads/claim_reverify.json`, JobName `claim.reverify` | contradicted 목록(remaining = 분할 자식 없는 contradicted = publish 막는 것, pending_job_id) + 사람 문장 수정 → `claim.reverify` 잡(202). worker 가 원자 분할(ClaimSplitter) → 원 주장 근거로 verify → parent_claim_id 자식 행. 원 주장이 contradicted 아님·이미 분할·잡 대기 중이면 409 | F3(API·G7·worker 핸들러), WP3(splitter·verify 재사용) |
| 3 | M6 · D1-6 | `POST /catalysts`, `schemas/catalyst.json#/$defs/CatalystCreate·CatalystCreated` | 사람이 넣는 호재 URL(http(s)만)+제목+발췌 → `normalize.catalyst` 공개 함수(F1a)로 후보 행(stage 미확정, location_confirmed=false) → 지역 최신 스냅샷에 rejudge(complex_ids=[] → P4 classify) 등록 | F1a(후보 함수), F3(API·G6), F2(P4) |
| 4 | M9 · RA §10 보안 5 | `GET·POST /share-links`, `DELETE /share-links/{id}`, `schemas/share_link.json`, 테이블 `share_link`, bearerAuth 설명 | 읽기 전용 공유 토큰 발급(쓰기 토큰만) — 만료 = 발급 + `SHARE_TOKEN_TTL_DAYS`(기본 30), sha256 만 저장, 만료·회수 401, GET 이외 403, 공유 토큰으로 목록 403. 링크 = `<origin>/share#<token>` | F3 |
| 5 | M11 | bearerAuth 설명 | 두 환경 토큰이 모두 비면 루프백 접속만(그 밖 401) + 127.0.0.1 바인드(`python -m app.serve`) | F3, infra |
| 6 | minor 15 | `schemas/human_check.json#/$defs/EnteredByRole`, `enums.ENTERED_BY_ROLE` | HumanCheckCreate.entered_by = 역할 enum(`운영자`·`검토자`) — 자유 입력 금지(RA §10 보안 2). DB CHECK 는 두지 않는다(옛 행 보존) | F3(API·G7 폼) |
| 8 | M8 | `schemas/snapshot.json` contradicted_claims, `POST /reports` 409 | 의미 명시: **남은** contradicted 수(분할 재검증 자식이 있는 주장은 빼고 센다 — `judge.claims.remaining_contradicted`). 보고서 생성 거부(409 publish_blocked)도 같은 함수 — 문장 수정·재검증 후 막히지 않는다 | F3(API), F4·F2(같은 함수) |
| 9 | W7 (WP9 통합 발견) · F2 요청 | `score_component.unadjusted_gap_pct`(Numeric(18,6))·`unadjusted_median_won`(BigInteger), `ComplexDetail.gap.gap_pct_unadjusted` | gap 성분의 미보정 갭%·중앙값. 점수 엔진은 flags 태그(`analysis.gap.unadjusted_tags`)로 싣고 `scheduler/persist.py` 가 컬럼으로 옮긴다(태그는 flags 에서 뺀다). API 는 컬럼(없으면 옛 행 태그)을 Fact(prov `sc_<run>_<cx>_gap`, reason '미보정 중앙값 기준')로, 없으면 null | F2(씀), F3(읽음) |
| 10 | F2 요청 | `score_inputs.json` ComplexScoreInput `move_in_label` | 입주월 값의 Fact 라벨(입주 성분 라벨 합성, R3 M2). 파이프라인·미리보기 라벨 키 `move_in` | F2, F3 |
| 11 | F2 요청 · minor 25 | `score_row.json` delta_rerank | 설명·단위 = 이전 run 대비 rerank **점수(0~10) 차**, unit `score`(예시 갱신). API `views.score_row` unit 'score' | F2, F3, 프론트 |
| 12 | F2 요청 · W12b | `score_component.score_0_10` | Numeric(6,3) → Numeric(7,4)(점수 엔진 정밀도 4자리) | F2 |
| 13 | F2 요청 · M3 | API `routers/analysis.py`(compare·미리보기) | 현재 구매가 = `views.bundle_price(b)`(§6-1 최신 공고 가격 우선), 미리보기 `score_input(b, labels, asof_date=기준일)`·미해결 제외 | F3 |
| 14 | F1b 요청 · M1 | `schemas/resolved_fields.json` needs_compare 설명 | '채택 보류' 규칙(대표 출처 행 reason '출처 상충 — compare 대기', ResolvedFields.chosen 은 '확인 불가' 후보) — 계약 의미 명시, 필드 변경 없음 | F1b |
| 15 | F1b 요청 · W4 | `complex` 유일 제약 | `applyhome_id` → `(region_id, applyhome_id)`(같은 공고 단지가 지역마다 따로) — `normalize.store` 가 다른 지역 행을 건너뛰지 않고 자기 행을 만든다 | F1b |
| 16 | F1b 요청 · minor 17 | Settings `HTTP_ALLOW_PRIVATE_HOSTS`(bool, 기본 false) | 사설 IP·localhost 목적지 허용(로컬 녹화 서버 테스트만) | F1b, infra |
| 17 | F1b 요청 · M13 | `schemas/raw_document.json` meta 설명 | official_site `render.signature`, `popups[].text_sha256·dhash·signature`(시각·애니메이션 무시 안정 해시) 문서화 | F1b |
| 18 | F1a 요청 · M6 | `POST /catalysts` | 후보 함수 = `app.normalize.catalyst.catalyst_candidate(session, region_id, url=, title=, excerpt=)`, `CatalystInputError` → 422 | F1a, F3 |
| 19 | F1a 요청 · M7 | `checklist_item.kind`(CHECK·enum) | 값 `계약` 추가(계약일 항목; downgrade 는 '만료'로 되돌린다) | F1a, 프론트 |
| 20 | F1b 요청(CEO 위임) · M1 | `scheduler/pipeline.py` P5 | compare 결과가 same_fact·different_facts 여도 `apply_compare` 호출(채택 보류는 compare 결과로만 푼다) | F3(이번 처리) |
| 7 | minor 29 | 응답 스키마의 맨 숫자 | 응답에 나가는 숫자 필드는 Fact 이거나 `x-nonfact: "<근거>"` 주석(비수치 메타 — 식별자·개수·가중치 가정·설정값·판정기 봉투 원값)을 단다. 이름 규칙 `id`·`*_id(s)`·`*_seq`·`page`·`size` 는 메타. 테스트 `tests/contracts/test_r3_contract.py` 가 강제 | F3, 프론트(표시 규칙) |

### 마이그레이션·검증

- `0004_r3`: `share_link(id, token_sha256 UNIQUE, label, created_at, expires_at, revoked_at)` + `job_run.job_name` CHECK 에 `claim.reverify`
  + `score_component.unadjusted_gap_pct·unadjusted_median_won`, `score_0_10` (7,4), `complex` (region_id, applyhome_id) 유일, `checklist_item.kind` '계약'.
  SQLite 는 batch(재생성 정의 고정), Postgres 는 ALTER. head → 0003 → head 왕복을 SQLite·Postgres 16(pgserver) 둘 다 테스트
  (downgrade 는 `claim.reverify` 잡 행을 먼저 지운다 — 옛 CHECK 를 통과할 수 없는 큐의 일시 행). autogenerate diff 0, CHECK 리터럴 일치.
- 픽스처 변경 사유 강제(minor 6): `contracts/fixtures.sha256.json`(픽스처 sha256 + 사유) — 픽스처를 바꾸면
  `uv run python scripts/fixture_manifest.py --reason '<사유>'` 로 다시 만들고 같은 사유를 여기 적는다(`tests/contracts/test_fixture_manifest.py`).
  사유: R3 F3: 픽스처 매니페스트 도입(minor 6) — 데이터 변경 없음
- `CONTRACT_VERSION`·`info.version` = `2026-10-09.4`. 생성물(`openapi.bundled.yaml`, `contracts_gen.py`, 프론트 `schema.d.ts`·MSW) 재생성.

### fixtures (WP9-후속 2026-10-09 — 계약 버전 변경 없음, CEO 결정 W1·W2·W5 / D9-1)

사유: R3 WP9 통합 회귀 실패(T1 b·T3 mock·T11·T7, e2e 흐름 2)의 CEO 결정(`docs/design/wp/R3_FIX.md` 'WP9 통합 발견 배정').
매니페스트(`contracts/fixtures.sha256.json`) 사유: WP9-후속: 픽스처 갱신(W1 complexes.json 골든 v2 정렬, W2 judgments_synth 합성 판정 녹화, W5 T11 하위 생활권 변형)
모두 생성기(`tools/build_incheon_gimpo.py`·`tools/record_synth_judgments.py`)로 다시 만들었고 `--check` 바이트 일치.

- **W1 `incheon_gimpo_2026-10-08/complexes.json` ← 골든 v2 inputs(사람 승인)** — 원천 `tools/incheon_gimpo_complexes*.py` 수정. 차이 목록(DB 입력 빌더 기준):

  | 단지 | 필드 | 이전 | 이후(= v2) | 라벨·근거 |
  | --- | --- | --- | --- | --- |
  | 1 더샵 송도그란테르 | 접수 상태(official_popup) | 불가 '마감(추가 공고 미정)' | 미정 '추가 공급 미정(…공고 이력 있음)' | meta §1-3-4(공고 이력 있음 = 미정) |
  | 1 더샵 송도그란테르 | winner_date / resale_end | 2026-05-28 / 2026-11-28 | 2026-06-02 / 2026-12-02 | 추정 — 보고서 '2026-05-28~06-02 기준' 블록별 마지막 |
  | 3 송도 한내들 센트럴리버 | 현재 조건 계약금 | 5% | 2.92% | 추정 — (1차 500만 + 입주 때까지 2,000만) ÷ P_mid 8.56억 |
  | 3 송도 한내들 센트럴리버 | 84A floor(현재 구매가 하단) | 842,100,000(본청약 2층) | 813,400,000 → 8.13~8.99억 | 추정 — 보고서 현재 구매가(84㎡ 묶음: 임의공급 84D 최저) |
  | 4 오퍼스 한강 스위첸 | 84A floor | 없음(→ 6.99억 단일) | 620,000,000(84C 1층) → 6.26~6.99억 | 추정 — 보고서 '6.26~6.99억' |
  | 6 더샵 검단레이크파크 AB23 | 84A floor | 없음(→ 6.68억 단일) | 645,900,000(84C 최고가) → 6.51~6.68억 | 추정 — 보고서 '84C 6.51억' |
  | 12 더샵 송도마리나베이 | winner_date / resale_months | 확인 불가 / 확인 불가 | 2026-09-15 / 0 | 추정 — 이번 무순위 접수일 대체, 전매제한 도과 |
  | 2·5·8·9·12 | 현재 구매가(원 단위) | 공고 값(예 578,140,000) | 그대로 | **가격 반올림 규칙**: v2 는 보고서 표기(억 소수 2~3자리) — 원 단위와 50만원 이하 차이는 같은 값(T1 b 테스트) |

  맞추지 않은 것(앱 규칙 — 픽스처로 맞추면 사실을 바꾼다): 칸타빌(7) 기준 타입 84B(84㎡ 최근접) 6.70~7.04억 vs v2 84A 6.64~6.97억;
  즉시 입주 단지(11·12) move_in_ym(준공월)·completed_year=None(입력 빌더) vs v2 move_in None·completed_year; 공고 전(15·16) 표시 접수 행 없음 vs v2 '미정'
  (비공식 접수 행만 — 점수 무관); has_priority_supply·재당첨·중도금 문구·라벨(입력 빌더가 사실 행에서 만든다, 점수 무관).
  T1(b) DB 경로 기대 = v2 inputs + D9-1 범위 + 칸타빌 기준 타입 가격(`backend/tests/regress/test_t01_top5.py`).
  파생 파일: `provenance.json`·`raw/documents.json`·`raw/notice/01_n.txt`·`03_n.txt`·`raw/official_site/03_site.txt`(발췌 줄 변경).
- **W2 `incheon_gimpo_2026-10-08/judgments_synth/`(신규, 라벨 '합성')** — 생성기 `tools/record_synth_judgments.py`: devseed DB 에서 실제
  파이프라인(rejudge 전체 + T3 사람 확인 흐름)을 결정적 가짜 판정기(WP7 SynthJev + 보고서 값: classify #62·#110, noul #65~70·#118~123, rerank #124,
  decide #125~129)로 돌려 payload hash 그대로 봉투 247개를 저장. adapter_version 은 `judgments/_meta.json` 과 같다. 회귀·e2e mock 재판정용
  (`JUDGE_FIXTURE_DIR`). `judgments/`(보고서 재구성)는 그대로 — devseed·T2·T6·T7 보고서 대조용.
- **W5 `raw/rtms/t11_switzen_subarea.json`(신규)** — T11 하위 생활권(장기·운양) 변형: 생활권 편집 + 한강센트럴자이 1·2단지(2017) 거래 6건(보고서
  범위 4.5~5.2억, 날짜·층 합성) + 생활권 밖 리버시티·고촌 센트럴자이 거래. `raw/rtms/t11_switzen_comparables.json` 설명만 수정(그대로 = 신축, 대체 아님).
- `README.md`: 파일 표(judgments_synth·T11 변형), 데이터 주의 10(W1), T7(delta_rerank = 점수 차)·T11 행, R3 매핑 표, 'D9-1로 인한 차이' 표.

## 2026-10-09.3

R2 WP5·WP7 요청(`docs/design/wp/CONTRACT_CHANGES_R1.md` "R2 WP5·WP7 요청"·"R2 (WP0 처리 대기)") 반영. 마이그레이션 `0003_r2`
(컬럼 추가만, 모두 NULL 허용 — 0002 DB 는 `alembic upgrade head` 한 번). 필드 삭제·의미 변경 없음.

### 요청별 반영

| # | 출처 | 대상 | 변경 | 영향 WP |
| --- | --- | --- | --- | --- |
| 1 | WP5-1 | `schemas/health.json`, `openapi.yaml` getHealth, `app/main.py` | `/health` 응답 = 계약 `Health{status, contract_version, app_version, db, judge, time}`. judge = 지역마다 최신 스냅샷의 degraded(하나라도 → degraded, 모두 정상 → ok, 스냅샷 없음·DB 장애 → unknown). DB 장애면 **503 + 같은 Health 본문**(문서화, 예시 `health_db_down.json`) — 판정기 장애만이면 200 | WP5, WP6(전역 배너) |
| 2 | WP5-2 | `openapi.yaml` | listJobs·getJudgmentOps·listChecklist·listSourceStatus·listReports 에 422(ValidationError) | WP5, WP6 |
| 3 | WP5-3 | `judgment_log.result_json`(JSON) | 정규화 결과(봉투 result)를 저장한다(WP3 `log.record`). `output_json._result` 관례 폐지 — 읽는 쪽은 `result_json`, NULL(옛 행)이면 `output_json` 을 다시 정규화 | WP3(씀), WP5·WP8(읽음), devseed |
| 4 | WP5-4 | `score_total.judge_scope`(String(8), 값 = score_row `JudgeScope`) | 점수 실행이 쓴 판정 범위를 저장(WP7). API 의 사다리 기반 추정 제거 — 행이 없을 때만(제외·옛 행) 규칙(제외/보류/판정 대상)으로 채운다 | WP7(씀), WP5(읽음) |
| 5 | WP5-5 | WP7 `scheduler.payloads.scenario_payloads` | 시나리오 → 판정 payload(tool, purpose, payload) 목록 빌더 공개. 미리보기 `cache_hits`/`cache_misses` = 같은 input_hash 의 최종 judgment_log 행 존재 여부 | WP5, WP7 |
| 6 | WP7 | WP3 `judge.payloads.classify_intake_payload`·`pipeline.p4_classify_intake` | 접수 상태 classify(공식 홈페이지 DOM 텍스트·팝업 문구 → 가능/미정/불가/확인 불가, 배치). review·manual_review = '확인 불가(판정 미해결)'. WP7 파이프라인이 수집 후 '접수 문구 미분류' 행(official_popup·headless_shot)을 분류해 갱신 | WP3, WP7, WP4(요건 사전 계산이 쓰는 값) |
| 7 | WP7 | WP2 `normalize.judged.apply_extracted`·`apply_compare` | needs_extract 추출값 → 사실 테이블·출처 행(라벨: extract auto + audit 통과 = 확인됨, audit 전·미해결 = 추정(판정기 추출), extract review = 미반영, audit flagged = 미반영·'확인 불가(판정기 감사 flagged)'). compare contradicts → 1차 공고 자료(공고문·청약홈) 채택·나머지 병기(conflict_group 유지) | WP2, WP7 |
| 8 | WP7 제안 | WP3 `classify_inclusion_payload(items=…)` | 포함/제외 classify 배치화: 지역 단지(범위 경계 제외) 64개씩 1회(계약 2026-10-09.2 ClassifyResult.items[]) | WP3, WP7 |
| 9 | R2 WP8 | `infra/Dockerfile.worker`, Settings `REPORT_ECHARTS_JS` | worker 이미지에 echarts 6.1.0 `echarts.min.js` 포함, 경로는 Settings(`report_echarts_js`)로 | WP8, WP0 |
| 10 | R2 WP8·WP7 | WP3 `judge.claims.remaining_contradicted` | "남은 contradicted" = 분할 자식(parent_claim_id 로 가리키는 행) 없는 contradicted. 보고서 생성 거부(WP8)와 publish 검사(WP7)가 같은 함수 | WP7, WP8 |

### 마이그레이션·검증

- `0003_r2`: `judgment_log.result_json` JSON, `score_total.judge_scope` String(8). head → 0002 → head 왕복(행 유지, 값 NULL)을
  SQLite·Postgres 16(pgserver) 둘 다 테스트. autogenerate diff 0.
- 열거 `enums.JUDGE_SCOPE`(CHECK 없음 — SQLite ADD/DROP COLUMN 호환) = `score_row.json#/$defs/JudgeScope`.

### 픽스처 문서 (WP9 R3 — 계약 버전 변경 없음, 데이터 무변경)

- `fixtures/incheon_gimpo_2026-10-08/README.md`: 'R3 통합 회귀 매핑' 절 추가(T1~T18 → `backend/tests/regress/` 테스트·e2e 흐름).
  사유: R3 통합 회귀 매핑 표 갱신(WP9 지시). 픽스처 파일·생성기 출력은 그대로(`test_tools.py` 바이트 일치 유지).

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
