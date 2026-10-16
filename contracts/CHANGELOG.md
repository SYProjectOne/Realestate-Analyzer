# 계약 변경 기록

버전 = `날짜.연번`. 에이전트는 **맨 위 항목 하나만** 가정한다(AGENTS.md). 계약을 바꾸는 쪽은 오케스트레이터뿐이다.

## 2026-10-09.22

R11 목업 구현 결정(CEO **D30**, `docs/design/DECISIONS.md`) — **D30-5** 목업의 "API 필요" 값 4종 확인(없는 것만 추가), **D30-6** 서버
문구(요건 이유의 `P_mid` → '중간 가격', 판정 범위 사유의 영어 분류명 → 한국어). 계약 소유자 = **R11-BE**(브랜치 `wp/r11-be`, CEO 위임).
마이그레이션 **0019**(`score_component.median_won` 열 — 데이터 채움 없음). **필드 삭제 없음, 새 필드는 모두 선택**(옛 발행 저장본에 키가
없어도 계약 통과) → 저장 모양 버전(`SHAPE_VERSION`) **그대로 1**(.20·.21 과 같은 까닭 — 올리면 발행 리비전 저장본 전부가 500
`stored_view_mismatch`). 새 엔드포인트 없음, 새 스키마 정의 1(`UnsoldLatest`). 판정기 호출 없음 — 저장값 그대로·같은 함수 재사용·문자열
표(AGENTS 규칙 3·4).

### "API 필요" 값 4종 — 지금 응답에 있는가(D30-5)

| # | 화면 · 목업 표시 | 결과 | 어디서 |
| --- | --- | --- | --- |
| A1 | G6 지역 시장 요약 카드 '미분양 지역 합계'·'다 지은 뒤에도 안 팔린 집'(Market MK-1) | **추가** — 대시보드 `kpis.unsold` 에만 있었다(시장 응답 `unsold[]` 는 단위별 점이라 화면이 더하면 규칙 3·5 위반) | `GET /snapshots/{sid}/market` → **`unsold_latest`**(`UnsoldLatest`: `ym`·`total`·`post_completion`·`breakdown`) — `kpis.unsold` 와 같은 함수(`app.api.routers.snapshots.latest_unsold`), `living_area` 를 주면 그 생활권 단위만 |
| A2 | G3 상세 가격 갭 '비교 단지 전체 가운데값'(Detail C2 옆) | **추가** — 점수 실행이 계산만 하고 저장·응답하지 않았다(`comps[]` 는 단지별 중앙값이라 묶으면 계산) | `GET /complexes/{id}` `gap.`**`comps_median`**·**`comps_median_unadjusted`**(비교 `GET /snapshots/{sid}/compare` `gaps[]` 도 같은 `Gap`) — `score_component.median_won`(0019)·`unadjusted_median_won`(0004) 저장값 |
| A3 | G3 상세 '당첨된 사람 가점' 최저~최고(Detail DT-6) | **이미 있음** | `GET /complexes/{id}` `competition_summary.winning_score_min`·`winning_score_max`(계약 .20 Q4·.21 no_winner 제외 규칙) — 타입별 가점을 화면이 묶지 않는다 |
| A4 | G1 '공식 자료 n곳 확인'·'점수를 매긴 단지 n곳 / 전체 n곳'(Main HM-2) | **이미 있음**(개수 세기, D25-3) | `GET /snapshots/{sid}/complexes` `total`(필터 없이 — 병합되지 않은 지역 단지 전체, `size=1` 이면 충분) |
| A5 | G7 '모순 주장' 상태별 수 '맞음 n · 사람 검토 n'(Ops OP-9) | **이미 있음**(개수 세기, D25-3) | `GET /snapshots/{sid}/claims`(`status` 없이 = 전체) 행의 `verify_status` 별 세기(`verified`·`contradicted`·`unsupported`·`review`·null), 막는 주장 = `remaining=true` 행 수 |

### FE 차이(화면이 맞출 것)

| # | 대상 | .21 | .22 | 결정 |
| --- | --- | --- | --- | --- |
| F1 | G6 `Market.unsold_latest` | 없음 — 목업 '[값] API 필요' | `ym`(값이 있는 가장 최근 달) · `total`·`post_completion`(Fact, reason '지역 합계(시군구 n곳)', 단위 하나라도 확인 불가면 '확인 불가(일부 누락 n건)') · `breakdown`(그 달 단위별 `UnsoldPoint`). 자료 없으면 `ym` null · '확인 불가(미분양 자료 없음)' · `[]`. 화면은 `unsold[]` 를 더하지 않는다 | D30-5 |
| F2 | G3·G4 `Gap.comps_median` | 없음 — 목업 '[값] API 필요' | gap_pct 기준 비교군 전체 중앙값(원). 대체 단지 섞이면 '추정'(reason '비교군 실거래 n건 중앙값(대체 단지 연식 보정)'), 아니면 '재가공'(reason '비교군 실거래 n건 중앙값'), prov `sc_<실행>_<단지>_gap.raw`. gap_pct 확인 불가면 그 사유. 0019 전 실행 중 대체가 있던 것은 '확인 불가(옛 점수 실행(재판정 뒤 표시))' | D30-5 |
| F3 | `Gap.comps_median_unadjusted` | 없음 | gap_pct_unadjusted 의 기준(미보정 중앙값, '재가공', reason '…중앙값(미보정)'). gap_pct_unadjusted 가 null 이면 null | D30-5 |
| F4 | G1 전체 단지 수 · G7 모순 주장 상태별 수 · G3 가점 범위 | — | 위 A3·A4·A5 필드를 쓴다(새 필드 없음) | D30-5 · D25-3 |

### 문구 변경(같은 필드, 다른 문자열 — 모양 그대로, D30-6)

| # | 대상 | .21 | .22 |
| --- | --- | --- | --- |
| W1 | 자금 요건 사전 계산 근거(`RequirementPre.evidence` — `GET /scenarios/{id}/preview` `requirements_pre[].funds`, 비교 요건 칸, decide 입력 근거) | `'계약금 비율 확인 불가(P_mid 5.468억) → 확인 불가'` | `'계약금 비율 확인 불가(중간 가격 5.468억) → 확인 불가'` |
| W2 | 원 금액 Fact reason(목록 `ComplexRow.down_payment_won`·상세 `price.payment_amounts.*`·비교 `TermsRow.down_payment_won`) | `'산술(P_mid × 계약금 5%)'`·`'산술(P_mid × 중도금 60%)'`·`'산술(P_mid × 잔금 35%)'` | `'산술(중간 가격 × 계약금 5%)'`·`'산술(중간 가격 × 중도금 60%)'`·`'산술(중간 가격 × 잔금 35%)'` |
| W3 | `PaymentAmounts.formula`(툴팁) | `'금액 = P_mid(현재 구매가 중앙, 대표 타입) × …'` | `'금액 = 중간 가격(현재 구매가 중앙, 대표 타입) × …'` |
| W4 | `judge_scope_reason`(목록 행·상세 머리)·보고서 범위 사유 — 제외 클래스 | `'포함/제외 classify 제외 클래스(public_sale)'` | `'포함/제외 classify 제외 클래스(공공분양)'` — 공공임대·민간임대·비아파트·범위 밖(ko.json `inclusion` 과 같은 말, `app.analysis.scope.CLASS_TEXT`) |
| W5 | 같은 사유 — 미해결 | `'포함/제외 classify 미해결(review, 미분류)'`·`'…(manual_review, public_sale)'` | `'포함/제외 classify 미해결(검토, 미분류)'`·`'…(사람 검토, 공공분양)'`(decision review→검토, manual_review→사람 검토, escaped→질문 남김 — `DECISION_TEXT`. 모르는 값·'auto'·'분류 전'은 그대로) |

점수 성분 식(`ScoreComponent.formula_text` — 'clamp(5 − gap%/4, 0, 10) = … (gap …%: P_mid 7.584억, 비교군 중앙 …)')의 식 기호
`P_mid` 는 바꾸지 않는다(RA §6 식 표기, 회귀 골든 `expected_scores_v2.json` 불변 — '요건 이유'가 아니다). 화면은 서버 문자열을 그대로 보인다.

### 스키마 변경

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `market.json` | 선택 `unsold_latest`(anyOf `UnsoldLatest` · null), `$defs.UnsoldLatest`(KpiUnsold 와 같은 모양, `breakdown` 필수 배열) |
| 2 | `complex_detail.json` | `$defs.Gap` 선택 `comps_median`·`comps_median_unadjusted`(anyOf Fact · null) |
| 3 | `openapi.yaml` | `info.version` 2026-10-09.22, 컴포넌트 `UnsoldLatest`(번들 재생성). 경로 변경 없음 |
| 4 | `examples/market.json`·`complex_detail_elif.json`·`complex_detail_kaive.json`·`compare_b.json`·`complexes_page.json` | 새 필드 예시 · 문구 W1~W3 |
| 5 | `complex.json`·`complex_row.json`(`judge_scope_reason`·`down_payment_won`)·`complex_detail.json`(`PaymentAmounts`) | 설명 속 예시 문자열만 W2·W4·W5 로(모양 그대로). 식 설명('P_mid × 비율')은 식 표기라 그대로 |

### 마이그레이션·검증

- **0019**(`contracts/migrations/versions/0019_r11_be_gap_median.py`): `score_component.median_won`(BIGINT NULL — gap 성분만). 쓰기 = 점수
  실행 persist(엔진이 `analysis.gap.unadjusted_tags` 태그 `median_won=` 로 싣고 저장 때 열로 옮긴다 — flags 에는 남기지 않는다). 데이터
  채움 없음 — 다음 재판정부터 채워진다. downgrade: 열 삭제.
- `CONTRACT_VERSION`(`app/core/protocols.py`)·`info.version`·`docs/design/DECISIONS.md` = `2026-10-09.22`. 생성물(`openapi.bundled.yaml`,
  `contracts_gen.py`) 재생성(`gen_contracts.py --check`), 프론트 `src/api/schema.d.ts` 재생성. **`src/mocks/handlers.gen.ts`(`npm run
  gen:msw`)는 이 브랜치가 다시 만들지 않았다**(R11-BE 는 프론트 파일 중 `schema.d.ts` 만 쓴다 — 페이지 에이전트·CEO 가 재생성).

### fixtures

- `contracts/fixtures/**` 녹화·매니페스트 변경 없음(`fixture_manifest.py --check`). 픽스처 원문의 'P_mid'(보고서 문장 녹화)는 원문이라 그대로.

### 알려진 한계

- 운영 DB 의 옛 점수 실행 중 대체 단지가 있던 단지는 다음 재판정 전까지 `comps_median` 이 '확인 불가'(0019 전에는 보정 중앙값을 저장하지
  않았다 — 역산하지 않는다).
- W1 은 decide 입력 근거 문자열이라, 계약금 비율이 확인 불가이고 자기자본·대출한도가 입력된 상황의 decide 는 운영 첫 재판정에서 캐시
  미스로 다시 판정된다(같은 입력 재호출 아님 — 입력이 바뀌었다).

## 2026-10-09.21

R9 데이터 후속 결정(CEO **D29**, `docs/design/DECISIONS.md`) — **D29-3** 체크리스트 kind '청약 접수'·'당첨자 발표', **D29-2** 같은 사업
중복 단지 행 병합(목록·점수에서 빠짐), 당첨 가점 '-' 사유 구별(R10 과제 3). 계약 소유자 = **R10-FOLLOW**(브랜치 `wp/r10-follow`).
마이그레이션 **0018**(`checklist_item.kind` CHECK 값 2 추가 · `complex.merged_into_id` 열 — 데이터 채움 없음). 필드 삭제 없음, **enum 값 추가 2곳**
(`ChecklistItem.kind` +2, `ReasonCode` +1 `no_winner`), 새 엔드포인트·새 필드 없음 → 저장 모양 버전(`SHAPE_VERSION`) **그대로 1**(.20 과 같은
까닭 — 옛 발행 저장본은 새 값이 없을 뿐 계약을 통과한다. 올리면 발행 리비전 저장본 전부가 500 `stored_view_mismatch`). 판정기 호출 없음 —
날짜 정리·문자열 대조·표 조회뿐(AGENTS 규칙 3·4). 테스트 표(결함 · 테스트 · 수정 전 실패 확인)는 `docs/design/wp/R10_TESTS_FOLLOW.md`.

**프론트가 맞출 것** — 아래 'FE 차이' 표. 이 브랜치가 FE 도 맞췄다(`npm run gen:api`·`gen:msw` 재생성, G1 다가오는 일정·G7 캘린더·
G3 경쟁률 당첨 가점 칸).

### FE 차이(화면이 맞출 것)

| # | 대상 | .20 | .21 | 결정 |
| --- | --- | --- | --- | --- |
| F1 | `ChecklistItem.kind` '청약 접수' (`GET /ops/checklist` — G1 다가오는 일정·G7 체크리스트·캘린더) | 없음 — 청약 접수일은 일정에 없었다(G1 '청약 접수일은 아직 일정에 없습니다(수집 전)' 안내) | 단지 청약 일정(`complex.apply_dates` — R9-PARSE `{kind, start, end}`, 옛 `{kind, date}`)에서 동기화가 만든다: 순위·구분(특별공급·1순위·2순위·일반공급)과 **기간이 같은** 항목을 하나로, 거주지역 구분은 제목 괄호 — title `'1순위 청약 접수(해당지역·기타지역)'`·`'특별공급 청약 접수'`, 잔여·임의 공고의 전체 접수 한 칸은 `'청약 접수'`. `due_date` = **접수 시작일**, note `'자동: 청약홈 청약 일정 <시작>[~<끝>]'`(여러 날이면 기간). 접수가 끝나지 않은 것(끝날짜 ≥ 기준일)만 — 접수 중이면 기한이 지난 시작일이어도 있다. 화면은 안내 문구를 지우고 종류 배지 '청약 접수' + 제목(어느 순위인지)을 보인다 | D29-3 |
| F2 | `ChecklistItem.kind` '당첨자 발표' | 없음 | `complex.winner_date` 에서: title `'당첨자 발표'`, `due_date` = 발표일(기준일 이후만), note `'자동: 청약홈 당첨자 발표일'` | D29-3 |
| F3 | 같은 사업 중복 단지 행(D29-2 — 인천 도화 39/99) — 목록 `GET /snapshots/{sid}/complexes`·대시보드·시장·민감도 | 같은 이름 두 줄(임의공급 번호 행 99 가 점수·순위 대상), G7 캘린더에 같은 일정 두 번(R9-PARSE 가 캘린더만 막음) | 잔여·임의 공고문이 원 공고 번호를 인용하면(R9-PARSE 정규식) 그 공고 자기 번호로 따로 생긴 행을 원 단지에 병합(`complex.merged_into_id` — 계약 응답 필드 아님). 병합된 행은 **새 리비전부터** 목록·대시보드·시장·점수·판정·체크리스트·수집 대상에서 빠진다. 이미 발행된 리비전은 저장본 그대로(D11-1 — 그 리비전 목록에는 남는다). 병합 change_event: entity `complex`, field `merged_into`, entity_id = 병합된 행, complex_id = 원 단지, critical(재판정) — `field_label` '같은 사업 단지 병합', `summary` '중복 단지 행 병합: <원 단지>에 병합 — 같은 사업(…)'. 화면 변경 없음(변경 피드가 summary 를 그대로 보인다). 병합된 행 상세(`GET /complexes/{id}`)는 여전히 200(옛 리비전 링크) | D29-2 · D11-1 |
| F4 | `Competition.winning_score_min/max/avg` 가 '확인 불가'일 때 사유 · `ReasonCode` 새 값 `no_winner` | 값이 없으면 모두 '확인 불가(가점 미수집)'(`not_collected`) — 청약홈 팝업 칸 '-'(가점 당첨자 없음)도 같은 문구 | 셋으로 나눈다(날짜 비교·원문 대조): ① 당첨자 발표일 > 기준일 → `'발표 전(당첨자 발표 YYYY-MM-DD)'`(`not_published`), ② 팝업 칸 '-'(발표 뒤 관측) → 그 행 경쟁률 원문이 미달('△')이면 `'가점 당첨자 없음(미달)'`, 아니면 `"가점 당첨자 없음(청약홈 '-')"`(**`no_winner`**, prov = 팝업 출처 행 `fp_…` — 원문 1클릭), ③ 그 밖 `'가점 미수집'`(`not_collected`). 화면: 가점 칸에 `no_winner` → '가점 당첨자 없음(미달)'/'가점 당첨자 없음', `not_published` → '발표 전', `not_collected` → '가점 미수집'(원 사유는 title). 표에 가점 열을 보일지 = 값 또는 `no_winner`·`not_published` 행이 하나라도 있으면 | R10 과제 3 · D29-4 |
| F5 | `CompetitionSummary.winning_score_min/max` | 기준 행(1순위 해당지역) 하나라도 '확인 불가'면 그 사유 | `no_winner` 행은 빼고 센다 — reason `'산술(1순위 해당지역 행 중 최저, 가점 당첨자 없는 n행 제외)'`. 모두 `no_winner` 면 그 사유 | R10 과제 3 |

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.20) | 이후(.21) | 결정 |
| --- | --- | --- | --- | --- |
| S1 | `ReasonCode` 규칙 `not_published` | '공고 전'으로 시작·'분양가 미공개'·'공고 전' 포함 | + '발표 전'으로 시작(당첨 가점 F4 ①) | R10 |
| S2 | 지역 단지 집합(목록·대시보드·시장·민감도·보고서·판정·점수·입주 물량·체크리스트·공식 홈페이지 수집·원 공고 다시 받기·법정동 재배정) | 지역의 모든 단지 행 | 병합되지 않은 단지 행(`merged_into_id IS NULL`) — 병합된 행이 없으면 같다(회귀 골든 불변) | D29-2 |

### 스키마 변경

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `checklist_item.json` | `kind` enum + '청약 접수'·'당첨자 발표', 설명(만드는 규칙·병합된 행) |
| 2 | `fact.json` | `$defs.ReasonCode` enum + `no_winner`(human_check 다음, no_value 앞 — 서버 규칙 순서), 설명(not_published '발표 전', no_winner) |
| 3 | `competition.json` | `winning_score_min` · `CompetitionSummary` 설명(사유 셋 · no_winner 행 제외) — 모양 그대로 |
| 4 | `openapi.yaml` | `info.version` 2026-10-09.21(번들 재생성). 경로·컴포넌트 변경 없음 |
| 5 | `examples/checklist.json` | MSW 데이터에 새 종류 2항목(61 '1순위 청약 접수(해당지역·기타지역)', 62 '당첨자 발표') |

### 마이그레이션·검증

- **0018**(`contracts/migrations/versions/0018_r10_follow.py`): `checklist_item.kind` CHECK 에 두 값, `complex.merged_into_id`(NULL, FK complex.id).
  데이터 채움 없음 — 새 항목은 다음 체크리스트 동기화(`collect.daily` 조립·판정 뒤 D24-1)가, 병합은 다음 `collect.daily`(받아 둔 원문 재정규화)가
  change_event 와 함께 한다(runbook §10-23). downgrade: 새 kind 항목 삭제(자동 항목), 열 삭제.
- `CONTRACT_VERSION`(`app/core/protocols.py`)·`info.version`·`docs/design/DECISIONS.md` = `2026-10-09.21`. 생성물(`openapi.bundled.yaml`,
  `contracts_gen.py`) 재생성(`gen_contracts.py --check`), 프론트 `src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 재생성.

### fixtures

- `contracts/fixtures/**` 녹화·매니페스트 변경 없음(`fixture_manifest.py --check`).

### 알려진 한계

- 청약 접수 항목은 단지(본청약) 일정만 — 원 단지에 묶인 잔여·임의 공고의 접수 기간(`remaining_event.apply_dates`)은 항목을 만들지 않는다(D29-3
  '데이터는 complex.apply_dates·winner_date 에서').
- 병합은 공고문 인용이 있을 때만 — 원 번호가 공고문에 없는 잔여 공고 행(연수 서해그랑블 5단지 1~4차)·9자리 오기 인용 행은 그대로(D29-2 후단).
  병합된 행에 사람이 넣은 사람 확인·호재 연결이 있으면 옮기지 않는다(운영 DB 의 도화 99 는 0건 — runbook §10-23 확인 SQL).

## 2026-10-09.20

초보자용 UI 개선(사람 답 + CEO **D28**, 원문 `docs/design/ui-benchmark/20-gap.md` §2-2 · `30-proposal.md`) 후속 — **D28-5** 데이터·API
요청 중 API 쪽 **Q1·Q4(API)·Q5·Q6·Q7·Q8·Q9**. 계약 소유자 = **R9-API**(브랜치 `wp/r9-api`). 마이그레이션 없음(DB 모양 그대로 — head 0016).
**필드 삭제 없음, 모든 새 필드는 선택**(옛 발행 저장본에 키가 없어도 계약 통과) → 저장 모양 버전(`SHAPE_VERSION`) **그대로 1**(D15-3: 모양이
바뀔 때만 올림 — 선택 필드 추가는 .16 `name_prov`·.17 `judge_scope_reason` 과 같은 관례. 올리면 이미 발행된 리비전 저장본 전부가 500
`stored_view_mismatch` 가 되고 backfill 은 모양이 다른 행을 다시 쓰지 않는다). 새 정렬 키 1(`sort=intake`), 새 스키마 정의 3(`ReasonCode`·
`CompetitionSummary`·`PaymentAmounts`). 판정기 호출 없음 — 모두 저장값의 산술·문자열 규칙(AGENTS 규칙 3·4). 읽기 전용 토큰 의미 그대로.
테스트 표(결함 · 테스트 · 수정 전 실패 확인)와 FE 연결 메모는 `docs/design/wp/R9_TESTS_API.md`.

**프론트가 맞출 것** — 아래 'FE 차이' 표. 이 브랜치는 FE 생성물(`src/api/schema.d.ts`·`src/mocks/handlers.gen.ts`)만 다시 만들었다(화면은
R9-UI 가 맞춘다 — `frontend/src/pages` 는 고치지 않았다).

### FE 차이(화면이 맞출 것)

| # | 대상 | .19 | .20 | 결정 |
| --- | --- | --- | --- | --- |
| F1 | **Q1** 단지 상세 `price.payment_amounts`(`PaymentAmounts`) · 목록 `ComplexRow.down_payment_won` | 원 금액 없음 — 화면은 계약금 %·1차 정액만, 원 금액 칸 '확인 불가(계산값 미제공)'(D28-4) | 대표 타입(판정 기준 타입 = `basis_type_code`) **P_mid × 현재 납부 조건 비율**: `down_payment_won`·`interim_won`(중도금 비율 합계 — 회차별 아님)·`balance_won` + 공고의 `down_payment_first_won`(정액 그대로) + `formula`(툴팁). 라벨 '추정', reason '산술(P_mid × 계약금 5%)', prov = `price_mid` 의 prov. 비율·가격이 확인 불가면 그 사유의 '확인 불가'. 목록 `down_payment_won` · 비교 `TermsRow.down_payment_won` 과 **같은 함수·같은 값**(`analysis.price.share_won` — RA §6-7 자금 요건 산술). 화면은 곱하지 않는다 | D28-5 Q1 · D28-4 |
| F2 | **Q4** `ComplexRow`·`ScoreRow`·`ComplexDetail` `competition_summary`(`CompetitionSummary`) · `Competition.winning_score_min/max/avg` | 경쟁률은 G3 경쟁률 탭에만, 가점 없음 | 요약 = 기준 행(kind '본청약' + 회차 '1순위…해당…') `rows`, `max_ratio`(접수 ÷ 공급 최댓값, 소수 2자리, reason '산술(접수 n ÷ 공급 m)', prov = 그 행 접수 출처), `max_ratio_type_code`, `shortfall_types`(접수 < 공급 행 수, unit count), `winning_score_min/max`. 기준 행이 없으면 rows 0 · '확인 불가(1순위 해당지역 경쟁률 없음)'. 당첨 가점은 **수집 전이라 지금은 모두 '확인 불가(가점 미수집)'**(reason_code `not_collected`) — 화면은 '제공하지 않음 — 청약홈 경쟁률에서 확인' 링크를 그대로 둔다(30-proposal §9-2) | D28-5 Q4 |
| F3 | **Q5** `Fact.reason_code`(label '확인 불가'일 때) · `Intake.reason_code` · `IntakeQueueItem.reason_code` | 사유가 자유 문자열 — 화면이 문자열 비교로 쉬운 말 매핑(`formatUnknown`) | `ReasonCode` enum 21개(`fetch_failed`·`not_collected`·`not_published`·`parse_failed`·`source_missing`·`demoted`·`conflict_hold`·`partial_missing`·`identity_unconfirmed`·`other_complex_site`·`no_phrase`·`phrase_inconclusive`·`not_target`·`input_blocked`·`unresolved`·`unjudged`·`not_entered`·`no_sample`·`human_check`·`no_value`·`other`). 서버 한 함수(`app.api.reason_codes.reason_code` — 저장 사유 머리말·낱말 규칙, 계약 `fact.json` 설명 순서)가 정한다. **원문 reason 은 그대로**(title·출처 패널). 화면 매핑을 코드 기준으로 바꾸고, 코드가 없는 옛 저장본(.19 이전 발행 리비전)은 지금처럼 문자열로 | D28-5 Q5 · D28-4 |
| F4 | **Q5** G1 대시보드 `kpis.unsold`(합계 Fact reason) · 새 `kpis.unsold.breakdown` · `unsold_series[].*.reason` | 사유 = '연수 505·검단 737·계양 0·김포 787 합'(라벨 칸이 넘쳐 페이지 폭 1,603px — 갭 #5) | 사유 = **'지역 합계(시군구 n곳)'**, 단위별 값은 `breakdown`(그 달 시군구별 `UnsoldPoint` — 원천 Fact·prov fp_). `unsold_series` 합계 점도 같은 짧은 사유(단위별 값은 G6 시장 `unsold` 단위별 점) | D28-5 Q5 |
| F5 | **Q5** `ChangeEvent.field_label`·`summary`·`value_kind`(G1 변경 피드·`/changes`·G8 차이) | 화면이 `field`(예 `official_popup_hash`)와 64자리 해시 old/new 를 그대로 보였다 | `field_label` = 사람이 읽는 이름('공식 홈페이지 팝업'·'입주 예정월'·'84A 최고 공급가'·'중도금 1회차 납부일' …, 표에 없으면 field 그대로), `summary` = 한 줄('공식 홈페이지 팝업이 바뀌었습니다' · '계약금 비율(%): 10 → 5' · '새 공고: …'), `value_kind` = `plain`·`hash`(이름이 '…_hash' 이거나 16진 32자 이상)·`json`. 화면은 summary 를 보이고 `hash`·`json` 이면 old/new 를 '바뀐 값 보기' 접힘 안에 둔다(원값은 응답 그대로 — D25-2). 옛 저장본(변경 원장)에는 키가 없다 | D28-5 Q5 · D25-2 |
| F6 | **Q5** G6 시장 `supply[]`·`benchmark_flags[]`·`benchmarks[]`·`move_in_markers[]` `living_area_name` | 범례가 내부 id `la_1~la_10` | 생활권 표시 이름(`living_areas[].name` 과 같은 값, 없으면 null). 범례·표는 이 값을 쓴다 | D28-5 Q5 |
| F7 | **Q6** 단지 상세·비교 `Gap.gap_score`(새) · `Gap.score`(옛 이름) · `gap_pct`·`gap_pct_unadjusted`·`ScoreRow.components.*.raw` 의 prov | '가격 갭' 이름으로 8.1%(gap_pct)와 2.98(score — 성분 점수 s_gap)이 같이 보였다. 둘의 출처 id 가 같아(`sc_<실행>_<단지>_gap`) 퍼센트 칸을 눌러도 서랍 값이 2.98 | `gap_score` = **가격 갭 점수 s_gap(0~10)**(= `score` 와 같은 Fact — `score` 는 옛 이름으로 유지), 퍼센트는 `gap_pct`. 성분 **원값** Fact(gap% 등 — `gap_pct`·`gap_pct_unadjusted`·목록·점수 행 `gap_pct`·`components.gap/benchmark/supply/liquidity/move_in.raw`)의 prov = **`sc_<실행>_<단지>_<성분>.raw`**(서랍 kind `score_component`, field `<성분>.raw`, value_text = 원값). 점수 Fact 는 그대로 `sc_…_<성분>`. 화면: 점수 칸 이름 '가격 갭 점수(0~10)'(30-proposal §9-3) | D28-5 Q6 |
| F8 | **Q7** `ScoreRow.price_low`·`price_high`·`resale_end`·`move_in_ym`·`gap_pct`·`competition_summary`(대시보드 `top5`·비교 `rows`·상세 `score`) | TOP 카드가 목록 API 행을 complex_id 로 붙여 썼다(30-proposal 결정 14 (a)) | 같은 리비전 목록 행(`ComplexRow`)과 **같은 함수·같은 Fact**(발행 리비전은 저장본 값 — D10-1·D13-1). 화면은 조인을 지우고 이 값을 쓴다(결정 14 (b)). 옛 저장본에는 키가 없다(그때는 지금처럼 조인) | D28-5 Q7 · D10-1 |
| F9 | **Q8** `Intake.supply_kind`·`supply_kind_basis` | 접수 행에 공급 종류가 없다(32번 '접수 가능'이 무순위·선착순 안내문 기반인데 구분 없음) | **저장된 문구 후보가 이미 말한 것만**: 수집 경로(official_popup·headless_shot) + 상태 가능·미정·불가 행의 메모(판정 표식 조각 뺀 '문구 후보' 줄)에서 공식 홈페이지 파서 키워드(무순위·임의공급·선착순 — 파싱 정규식)가 정확히 한 종류면 SUPPLY_KIND 어휘('무순위'·'임의'·'선착순'), basis = 그 줄. 여럿이면 null + basis '공급 종류 문구가 여럿(…)', 없으면 null. '본청약'은 문구 키워드·판정기 출력에 공급 종류가 없어 지금은 내지 않는다. 사람 확인·비공식 참고·'확인 불가' 행은 null | D28-5 Q8 · 규칙 3 |
| F10 | **Q9** `GET /snapshots/{sid}/complexes?sort=intake`(·`-intake`)·CSV 같은 키 | 정렬 키에 접수 상태 없음 | 표시 접수 상태 가능 → 미정 → 확인 불가(접수 행 없음 포함) → 불가, 같은 상태 안 **접수 마감 임박**(단지 `apply_dates` 항목의 끝날짜(없으면 시작) 중 기준일 이후 가장 이른 날, 없으면 뒤) → complex_id. `-intake` 는 상태 순서만 거꾸로. 기본 정렬은 그대로 `-total`(D28-4 결정 4 (a) — 이 키는 옵션) | D28-5 Q9 · D28-4 |

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.19) | 이후(.20) | 결정 |
| --- | --- | --- | --- | --- |
| S1 | 성분 원값 Fact 의 prov(`gap_pct` 등 — F7) | `sc_<실행>_<단지>_<성분>`(점수와 같은 id — 서랍 value_text = 점수) | `sc_<실행>_<단지>_<성분>.raw`(서랍 value_text = 원값 — CSV `gap_pct_prov` 열도 같은 값). 발행 저장본 출처 서랍(D15-2)이 새 id 도 모은다. 옛 저장본의 원값 Fact 는 옛 id 그대로(그 서랍 = 점수) | D28-5 Q6 |
| S2 | 지역 합계 미분양 Fact reason(F4) | 단위 나열 '<이름> <값>·… 합'(120자에서 잘림) | '지역 합계(시군구 n곳)' — 값·라벨·prov 그대로 | D28-5 Q5 |
| S3 | 비교 `TermsRow.down_payment_won` reason | '산술' | '산술(P_mid × 계약금 n%)' — 값·라벨·prov 그대로(같은 함수로 합침) | D28-5 Q1 |

### 스키마 변경

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `fact.json` | `reason_code`(선택, `$defs.ReasonCode` enum 21) + `prov` 설명(`.raw` 꼬리) + 예시 2 |
| 2 | `intake.json` | `reason_code`·`supply_kind`(SUPPLY_KIND 어휘)·`supply_kind_basis`(선택) + 설명에 D27-1 예외(**D27-3** 설명만) |
| 3 | `complex_detail.json` | `competition_summary`(선택) · `PriceRange.payment_amounts`(선택, 새 `$defs.PaymentAmounts`) · `Gap.gap_score`(선택) · `Gap.score` 설명(옛 이름) · `intake_current` 설명(D27-1 — D27-3) |
| 4 | `complex_row.json` | `down_payment_won`·`competition_summary`(선택) · `gap_pct` 설명 |
| 5 | `score_row.json` | `price_low`·`price_high`·`resale_end`·`move_in_ym`·`gap_pct`·`competition_summary`(선택) |
| 6 | `competition.json` | `winning_score_min/max/avg`(선택) · 새 `$defs.CompetitionSummary` |
| 7 | `change_event.json` | `field_label`·`summary`·`value_kind`(선택) + 예시 1(해시) |
| 8 | `market.json` | `SupplyPoint`·`MoveInMarker`·`BenchmarkView`·`BenchmarkFlag` `living_area_name`(선택) · `UnsoldPoint` 설명 |
| 9 | `dashboard.json` | `KpiUnsold.breakdown`(선택) |
| 10 | `intake_queue.json` | `IntakeQueueItem.reason_code`(선택) |
| 11 | `scenario.json` | `RequirementRule` 설명 — access 공통 조건(D25-11 — **D25-13** 설명만) |
| 12 | `openapi.yaml` | `info.version` 2026-10-09.20 · `ComplexSort` 패턴 `…|intake` + 설명 · components `ReasonCode`·`CompetitionSummary`·`PaymentAmounts` |

### 마이그레이션·검증

- DB 마이그레이션 없음(head 0016). 저장본 변환·backfill 불필요 — `SHAPE_VERSION` 1 그대로(위 설명). 새 필드는 **새로 발행하는 리비전부터**
  저장본에 들어간다(이미 발행된 리비전은 불변 — D11-1. 화면은 키가 없으면 지금 동작).
- `CONTRACT_VERSION`(`app/core/protocols.py`)·`info.version`·`docs/design/DECISIONS.md` = `2026-10-09.20`. 생성물(`openapi.bundled.yaml`,
  `contracts_gen.py`) 재생성(`gen_contracts.py --check`), 프론트 `src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 재생성.
- 예시(`contracts/examples/` — MSW 데이터) 9개에 새 필드를 서버와 같은 함수로 채웠다(`tests/contracts/test_r9_api_contract.py` 가 맞춘다).

### fixtures

- `contracts/fixtures/**` 녹화·매니페스트 변경 없음(`fixture_manifest.py --check`).

### R9-PARSE 와 맞출 것(당첨 가점)

- 서버는 경쟁률 행 모델 `Competition` 에 **`winning_score_min`·`winning_score_max`·`winning_score_avg`** 컬럼이 있으면(그리고 같은 이름 출처 행
  — `field_provenance` entity `competition`, field 같은 이름) 그 값을 Fact 로 낸다(`app.api.views.winning_score_fact`). 컬럼이 없으면
  '확인 불가(가점 미수집)'. R9-PARSE 가 다른 테이블·이름을 쓰면 `winning_score_fact`·`WINNING_SCORE_FIELDS` 한 곳만 바꾼다(계약 그대로).

### 알려진 한계

- 경쟁률 요약의 기준 행은 회차 원문이 '1순위 … 해당…'인 행이다(청약홈 API `RESIDE_SENM` '해당지역'). 회차가 '1순위'뿐인 옛 웹 행
  (지역 구분 없음)은 기준 행이 아니다(rows 0) — 파서가 지역을 채우면 따라온다.
- `supply_kind` 는 문구 후보 키워드뿐이다 — 본청약(일반·특별공급) 구분·여러 공급이 섞인 문구는 null(판정기 classify 가 공급 종류를 내면
  그때 그 값을 쓴다 — 새 판단을 서버가 만들지 않는다).
- 중도금 금액은 비율 합계 × P_mid 하나다(회차별 금액 없음 — 회차 비율·일정은 `payment[].interim_schedule`).

## 2026-10-09.19

인천 첫 실운영 수집(`docs/design/wp/R6_TESTS_INTAKE.md` §6 제안 4 — 계약 변경 요청) 후속 — 사람 결정 **D26-2**(`docs/design/DECISIONS.md`):
'확인 불가' 접수 행을 G7 에서 사유별로 모아 한 번에 사람 확인하는 **접수 확인 대기열**. 계약 소유자 = **R7-QUEUE**(브랜치 `wp/r7-queue`).
마이그레이션 없음(DB 모양 그대로 — head 0016). 필드 삭제·의미 변경 없음, **새 엔드포인트 1**(`GET /ops/intake-queue`)·**새 스키마 1**
(`intake_queue.json` — `IntakeQueue`·`IntakeQueueCategory`·`IntakeQueueGroup`·`IntakeQueueItem`·`IntakeQueuePendingCheck`). 저장 모양 버전
(`SHAPE_VERSION`) 그대로 1 — 대기열은 발행 저장본(D13-1)이 아니라 운영 GET 이다(`/ops/sources` 처럼 저장된 행을 그 자리에서 읽는다 — 저장된
접수 행은 리비전마다 따로라 발행 리비전의 대기열도 바뀌지 않는다; `human_check_pending` 만 그 뒤 사람 입력을 보인다). 판정기 호출·DB 쓰기
없음(AGENTS 규칙 4). 테스트 표(결함 · 테스트 · 수정 전 실패 확인)는 `docs/design/wp/R7_TESTS_QUEUE.md`.

**프론트가 맞출 것** — 아래 'FE 차이' 표. 이 브랜치가 FE 도 맞췄다(`npm run gen:api`·`gen:msw` 재생성, G7 `IntakeQueuePanel`).

### FE 차이(화면이 맞출 것)

| # | 대상 | .18 | .19 | 결정 |
| --- | --- | --- | --- | --- |
| F1 | **`GET /ops/intake-queue?region_id=&snapshot=`**(`getIntakeQueue`) → `IntakeQueue` | 없음 — '확인 불가' 접수는 단지 상세 배지로만 보였고(운영자가 인천 89행을 한 곳에서 처리할 수 없음), 운영자는 runbook §2 의 SQL(`GROUP BY reason`)로 사유를 셌다 | **새 엔드포인트**: 기본 = 그 지역의 최신 published(없으면 ready) 스냅샷. 단지마다 표시 접수 행(human_check > official_popup > headless_shot)이 '확인 불가'·'미정'인 단지를 `groups[]`(`category`·`reason`·`count`·`items[]`)로. 묶음은 **저장된 사유·http_status 로 정한다**(데이터 기준 — 사유가 새로 생겨도 계약·코드 그대로): HTTP 비 2xx·숫자 사유·수집 실패 낱말(DNS·timeout·connect·TLS·network·robots·invalid_url·render …) → `collect_failed`(묶음 이름 = 그 낱말·코드, 'connect: …' → 'connect', 'TLS(…)' → 'TLS'), '공식 홈페이지 동일성 미확인'·'공식 홈페이지가 다른 단지' → `identity`, '문구로 판단 불가'·'접수 문구 없음' → `no_phrase`, '판정 미해결'·'접수 문구 미분류' → `unresolved`, '판정 대상 아님…'(D26-3 범위 경계·공공분양) → `not_judged`, 그 밖 → `other`('기타'), status '미정' → `undecided`. 순서 collect_failed → identity → no_phrase → unresolved → not_judged → other → undecided, 묶음은 건수 내림차순 | D26-2 |
| F2 | `IntakeQueueItem` | — | 항목 = 단지 이름(`complex_name` → G3 링크)·`status`·`reason`·`path`·`evidence_url`(근거 페이지)·`raw_document_id`·**`screenshot_raw_document_id`**(스크린샷 원문 — `GET /raw/{id}` image/png, 없으면 null)·`checked_at`·`http_status`(메타)·`note`·**`judgment_ref`**(메모의 마지막 `jl_<seq>` — 동일성·접수 classify 판정 로그, runbook §2)·**`human_check_pending`**(이 스냅샷을 만든 뒤 들어와 아직 반영 안 된 접수 사람 확인 `{id, value_text, checked_at, created_at}` — 같은 단지를 두 번 입력하지 않게 '사람 확인 입력됨 — 재판정·발행 대기'). 화면의 '사람 확인 입력'은 기존 G7 HumanCheckForm 을 그 단지·field `intake_status` 로 미리 채운다(`?hc_complex=<id>&hc_field=intake_status#human-check`) → `POST /ops/human-checks`(접수 행 + 재판정 자동 등록, D12-5 — 응답·동작 그대로) | D26-2 · D12-5 |
| F3 | 인증 | — | READONLY_TOKEN 은 GET 이라 200(D10-7 — 화면은 읽기 전용이면 '사람 확인 입력' 버튼을 끈다), 공유 링크 토큰은 `/ops/*` 라 403 | D10-7 |
| F4 | 빈 대기열 | — | 지역이 없거나 published·ready 스냅샷이 없으면 200 + `snapshot_id` null · `groups` [] · `total` 0. 없는 지역·스냅샷(또는 다른 지역 스냅샷) 404 | D26-2 |
| F5 | 자유 문장 입력 4곳 — `PATCH /claims/{id}` `text` · `POST /catalysts` `title` · `PATCH /regions/{id}` `name` · `PUT /regions/{id}/living-areas` `living_areas[].name` | 스키마는 `minLength 1` 만 — 공백·제어 문자만인 값(`"\u001e"`·`" \u3000"`)이 스키마를 통과한 뒤 서버가 `strip()` 으로 비워 422 '비었다'(schemathesis RejectedPositiveData), `"\x01"`·`"\ufeff"` 같은 값은 서버도 받았다(주장 재검증 잡·생활권 이름으로 들어감) | **보이는 글자 1자 이상**(스키마 `pattern` — S1). 어기면 스키마 단계 422 `validation_error`(field_errors loc `[body, text]`·`[body, title]`·`[body, name]`·`[body, living_areas, i, name]` — 응답 모양 그대로). 화면 변경 필요 없음(폼은 이미 앞뒤 공백을 지우고 빈 값을 막는다 — 제어 문자만 넣는 경우만 서버 422 문구로 보인다) | 조정자 요청(R7) |

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.18) | 이후(.19) | 결정 |
| --- | --- | --- | --- | --- |
| S1 | 사람이 넣는 자유 문장 4필드(F5) | 스키마 `minLength 1`, 서버는 `strip()` 후 비면 422(주장·호재·지역 이름), 생활권 이름은 정규화가 같은 규칙 — 둘이 다른 값을 거절 | 스키마 `pattern` = 서버 `app.api.contract.VISIBLE_TEXT_PATTERN`(같은 문자열, 테스트가 맞춘다): C0·C1 제어 문자, 파이썬 `str.isspace` 공백 전부(U+0020·U+00A0·U+1680·U+2000–200A·U+2028·U+2029·U+202F·U+205F·U+3000 …), BOM U+FEFF 가 **아닌** 글자가 1자 이상. 이 규칙을 지난 값은 `strip()` 해도 비지 않아 서버의 '비었다' 422 에 닿지 않는다(서버 검사도 같은 함수 `has_visible`). 다른 자유 문장 요청 필드(사람 확인 `value_text`·`note`, 시나리오·지역 생성 이름, 공유 링크 `label`, 체크리스트 `note`, 호재 `excerpt`)는 서버가 공백만인 값을 거절하지 않아(그대로 저장하거나 빈 값을 null 로) 어긋남이 없다 — 바꾸지 않았다 | 조정자 요청(R7) |

`POST /ops/human-checks`·접수 행·발행 저장본은 그대로.

### 스키마 변경

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `schemas/intake_queue.json`(새 파일) | `IntakeQueue`(region_id·snapshot_id·asof_date·revision·snapshot_status·total·groups) + `$defs` `IntakeQueueCategory`(enum 7)·`IntakeQueueGroup`·`IntakeQueueItem`·`IntakeQueuePendingCheck`. 맨 숫자(`total`·`count`·`revision`·`http_status`)는 `x-nonfact`(행 수·리비전·HTTP 메타 — 규칙 5 의 사실 아님) |
| 2 | `openapi.yaml` | `paths./ops/intake-queue.get`(`getIntakeQueue` — 200·401·403·404·422·500, 예시 `intake_queue.json`·`intake_queue_empty.json`), components 5개, `info.version` 2026-10-09.19 |
| 3 | `claim.json` `ClaimPatch.text` · `catalyst.json` `CatalystCreate.title` · `region.json` `RegionPatch.name` · `living_area.json` `LivingAreaInput.name` | `pattern`(보이는 글자 1자 이상 — S1) + description. 모양·필수 그대로 |

### 마이그레이션·검증

- DB 마이그레이션 없음(head 0016 그대로). 저장본 변환·backfill 불필요(발행 저장본 모양 그대로).
- `CONTRACT_VERSION`(`app/core/protocols.py`)·`info.version`·`docs/design/DECISIONS.md` = `2026-10-09.19`. 생성물(`openapi.bundled.yaml`,
  `contracts_gen.py`) 재생성(`gen_contracts.py --check`), 프론트 `src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 재생성.

### fixtures

- `contracts/fixtures/**` 녹화·매니페스트 변경 없음(`fixture_manifest.py --check`). 새 예시는 `contracts/examples/`(MSW 데이터)뿐이다.

### 알려진 한계

- 접수 행이 하나도 없는 단지(청약홈에 공식 홈페이지 주소 없음 — 인천 5단지, 화면 '확인 불가(접수 행 없음)')는 대기열에 없다(행 기준 —
  D26-2 '확인 불가 접수 행'). 이 단지들도 G7 사람 확인 폼(접수 상태)으로 입력할 수 있다.
- `human_check_pending` 은 같은 확인 시각·경로 human_check 의 접수 행이 그 스냅샷에 없을 때다 — 사람 확인 뒤 재판정이 새 리비전을 발행하면
  그 리비전이 기본이 되어 항목이 빠지거나(가능·미정·불가) '사람 확인' 사유로 남는다('확인 불가' 입력 → `other`).

## 2026-10-09.18

R4 4차 재시험(`docs/design/wp/R4_RESULT4.md` §10 — N13·N14·N15) 후속 — CEO 결정 **D23**(`docs/design/DECISIONS.md`). 계약 소유자 =
**R4-CORE10**(브랜치 `wp/r4-core10`). **데이터 마이그레이션 `0016`**(스키마 그대로 — 경쟁률 원 면적 코드 + R4 4차 중복 경쟁률 정리, 앱
import 없음). 필드 추가·삭제 없음, 응답 모양 그대로. 바뀐 것은 의미 3(경쟁률 `type_code` 식별·표시, 재정규화의 compare 표식 보존, 청약홈
API 빈 데이터셋 = 실패) + 새 실패 사유 문자열 1(`raw_document.error_text` · G7 실패 대상 `reason` = `empty_dataset: totalCount 0`) + 잡
stats 키 1(`collect.daily`·`region.bootstrap.daily` 의 `degraded_sources`). 저장 모양 버전(`SHAPE_VERSION`) 그대로 1. 테스트 표(결함 ·
테스트 · 수정 전 실패 확인)와 재정규화 멱등성 속성 테스트(D23-1)는 `docs/design/wp/R4_CORE10_TESTS.md`.

**프론트가 맞출 것** — 아래 'FE 차이' 표(F1~F4). 응답 모양이 같아 `npm run gen:api`·`gen:msw` 결과는 설명 문구(스키마 description)만
바뀐다 — `frontend/src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 는 이 브랜치에서 다시 만들지 않았다(frontend/** = FE 소유).

### FE 차이(화면이 맞출 것)

| # | 대상 | .17 | .18 | 결정 |
| --- | --- | --- | --- | --- |
| F1 | 단지 상세 `competition[].type_code`(G3 경쟁률 표·C8) | 저장 때 그 시점 단지 주택형과 대조한 코드 — 같은 날 재정규화가 같은 경쟁률을 다른 코드('84.9939' → '84' · '확인 불가(타입 모호)')로 **한 번 더** 만들어 같은 회차 행이 두 번 보였다(R4 4차 N13 — 발행 리비전 5·6 '확인됨' Fact 140개) | 행 하나 = (구분, 회차, 원 면적 코드). `type_code` 는 **읽기 시점 표시 주택형**(맞는 타입 1개 = 그 코드, 여럿 = '확인 불가(타입 모호)', 없음 = 원 코드 — 규칙은 .17 과 같다). 같은 회차에서 표시 코드가 겹치면 원 코드 순 첫 행만 그 코드, 나머지는 원 코드(예 웹 '84A' 행과 API '84.9582' 행이 같은 회차에 있으면 API 행은 '84.9582'). 이미 발행된 R4 4차 리비전 5·6 저장본의 중복 행은 그대로(D11-1 불변) — 다시 발행한 리비전부터 사라진다. 화면 변경은 필요 없다(같은 회차·같은 `type_code` 두 행이 더는 오지 않는다) | D23-2 · N13 |
| F2 | G7 `GET /ops/sources` — `applyhome_list`·`applyhome_detail` 의 `failures_7d`·`last_http_status`·`last_error_text`·`failing_targets[].reason` | 청약홈 API 데이터셋이 비어 있던 응답(200 · `totalCount 0`)도 성공으로 셌다(실패 0) | 실패 행(`http_status` **200** · `path` null · `error_text`/`reason` **`empty_dataset: totalCount 0`**). 상태 코드가 2xx 인 실패이므로 화면은 '확인 불가(200, 날짜)'가 아니라 사유 문자열을 보여야 한다(예 '확인 불가(빈 데이터셋 — 청약홈 적재 중, 날짜)') | D23-4 · N15 |
| F3 | G7 잡 목록 — `region.bootstrap`·`collect.daily` | 빈 데이터셋 수집도 `done`(bootstrap 은 불완전한 스냅샷을 published, 지역 `ready`) | 그 수집은 판정·발행(이월 포함)을 하지 않고 **지연 재큐잉**: 잡 `queued` + stats `requeue_count`·`not_before`(30분 뒤)·`requeue_reason`('degraded_source: … 청약홈 API 빈 데이터셋(조건 없는 totalCount 0 — 재적재 중) n건 — 발행하지 않고 재시도'), 일일 수집 stats `degraded_sources` = {`applyhome`: 사유}. 6회(3시간) 넘게 그대로면 `failed`(`degraded_source: …`). bootstrap 이 재큐잉된 동안 지역 `status` 는 `bootstrapping` 그대로(발행 리비전 없음 — 화면은 '적재 중'), `collect.daily` 면 이전 발행 리비전이 그대로 기본 리비전 | D23-4 · N15 |
| F4 | 단지 상세 Fact `reason`(가격·입주월·세대수 등 compare 로 푼 필드) | 같은 날 재수집 뒤 '판정기 compare 채택 jl_… (병기)' 근거가 이벤트 없이 사라졌다(R4 4차 N14, 47 필드) — 같은 rank 1차·1차 상충이면 값이 '확인 불가(출처 상충 — compare 대기)'로 돌아갈 수 있었다 | 같은 원문·같은 자리·같은 값이면 compare 채택·병기 표식이 재정규화 뒤에도 그대로(사유 문자열 그대로). 값이 실제로 바뀌면 표식이 옮겨지지 않고 change_event + 채택 보류(새 compare) — 화면 변경 없음 | D23-3 · N14 |

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.17) | 이후(.18) | 결정 |
| --- | --- | --- | --- | --- |
| S1 | 재정규화(같은 원문을 다시 저장 — 같은 날·다음 날 재수집) | 경쟁률 행을 그 시점 주택형 대조 코드로 찾아 새 행(N13), 같은 원문 출처 행 reason 을 파서 값으로 다시 써 compare 표식 소실(N14) | **멱등**: 같은 원문을 다시 정규화하면 모든 정규화 테이블(단지·타입·납부 조건·경쟁률·잔여 이력·출처 행과 채택 표식·체크리스트·접수 상태)이 바이트 단위로 그대로, 사실 change_event 0, 다음 재판정 `tools/call` 0 — R4 1~4차 녹화 재생 속성 테스트로 고정(순서를 섞어도·다음 날이어도) | D23-1 |
| S2 | `competition` 행 식별 | (단지, 구분, 회차, 그 시점 대조 코드) | (단지, 구분, 회차, **원 면적 코드**) — `competition.type_code` 저장값 = 원 면적 코드. 표시 주택형은 `app.normalize.competition.display_type_codes`(API 단지 상세·보고서 같은 함수) | D23-2 |
| S3 | 재정규화의 compare 표식 | 판정기 추출·감사 행만 보존(D22-1) | + 같은 원문이 같은 자리(엔티티·필드·발췌 위치)에 같은 값을 다시 내면 그 출처 행의 `COMPARE_ADOPTED`·`COMPARE_SIDE` 표식을 이번 후보에 다시 붙인다. 값이 바뀌면 옮기지 않는다 | D23-3 |
| S4 | 청약홈 공식 API 응답 `totalCount` 0 | 정상 0건(목록 0 → 웹으로도 안 감, 실패 행 없음) | 실패(`ApplyhomeApi.get` → `error` = `empty_dataset: totalCount 0`): 실패 행, 목록이면 그 시도 웹 경로, 상세·경쟁률이면 웹 상세·웹 경쟁률, 수집기 `empty_datasets` → 수집 `degraded` → 목록 diff·목록 단지 집합 기록 안 함 · 발행 안 함 · 재큐잉(F3). 조건에 맞는 것만 0건(`matchCount` 0, `totalCount` > 0)은 그대로 정상 | D23-4 |

### 스키마 변경(설명만 — 모양 그대로)

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `competition.json` `type_code` | description: 표시 주택형 · 원 면적 코드 식별 · 겹침 규칙(F1) |
| 2 | `raw_document.json` `error_text` | 값 목록에 `empty_dataset: totalCount 0`(200 · path null 실패 행 · sha256 규칙) |
| 3 | `source_status.json` `failing_targets[].reason` | 예시에 `empty_dataset: totalCount 0`(http_status 200) |
| 4 | `openapi.yaml` | `info.version` 2026-10-09.18 |

### 마이그레이션·검증

- **`0016`(데이터만, 스키마 diff 0)**: 경쟁률 출처 행 `entity_key`('<주택관리번호>:<구분>:<회차>:<원 코드>')의 넷째 칸으로 원 면적 코드를
  찾아 (단지, 구분, 회차, 원 코드)가 같은 행을 하나로(가장 앞 id 남김, 값은 가장 늦은 행, 같은 출처 행은 지우고 다른 출처 행은 남는 행으로
  옮기고 상충 묶음 이름도, 필드마다 chosen 하나, `change_event`·`fact_demotion`·`human_check` 의 (competition, 지운 id)는 남는 id 로),
  `type_code` = 원 코드(출처 행이 없는 행은 그대로). downgrade 는 데이터를 되돌리지 않는다. 왕복은 SQLite·임베디드 PG 테스트
  (`tests/contracts/test_core10_migrations.py`). 운영 DB(D19)·R4 DB 는 `alembic upgrade head` 로 적용한다(R4 DB 는 5차 재시험이 새로
  비우므로 적용 불필요 — R4 4차 리비전 5·6 의 발행 저장본은 불변).
- `CONTRACT_VERSION`(`app/core/protocols.py`)·`info.version`·`docs/design/DECISIONS.md` = `2026-10-09.18`. 생성물(`openapi.bundled.yaml`,
  `contracts_gen.py`) 재생성(`gen_contracts.py --check`).

### fixtures

- `contracts/fixtures/**` 녹화·매니페스트 변경 없음(`fixture_manifest.py --check`). (R4-CORE10 시점)
- **R5-PIPE(D25, 계약 버전 `.18` 그대로 — 스키마·openapi 변경 없음)**: P6 noul 입력에 지역 벤치마크·제도 컨텍스트·가격 갭(meta §2-1 P6),
  증거 카드 벤치마크·공급·호재·비고(제도) 줄이 채워져 noul·rerank·decide payload 가 바뀌었다 → 합성 판정 녹화(`judgments_synth/`)를
  `record_synth_judgments.py` 로 다시 만들었다. 바뀐 것은 **input_hash 재매핑뿐**(noul 33·rerank 1·decide 5 = 39개, 봉투 내용은
  `input_hash`·`input_len` 외 바이트 동일 — 결과·상태·확률·순위·선택 그대로) + 지역 벤치마크 P1 screen 봉투 1개 추가(SynthJev 기본 pass).
  `judgments/`(보고서 재구성 녹화)·회귀 골든(`expected_scores*.json`)은 그대로. 픽스처 README 주의 7(생활권 세대수) 현행화.
  매니페스트 사유: R5-PIPE P6 맥락(벤치마크·제도·갭) 반영으로 judgments_synth noul·rerank·decide input_hash 재매핑(봉투 내용 동일)·벤치마크 screen 1개 추가·README 주의 7 현행화
- **R5-ACCESS(D25-11, 계약 버전 `.18` 그대로 — 스키마·openapi 변경 없음)**: RA §6-7 접근 가능성의 `intake_status ∈ {가능}` 이 A(`priority_supply`)·
  C(`resale_before_exit`)에도 AND 로 들어가 요건 사전 계산 근거(decide payload 증거의 '요건 사전 계산' 줄)가 바뀌었다 → `judgments_synth/` 를
  `record_synth_judgments.py` 로 다시 만들었다. 바뀐 것은 **decide 2개(`decide:scenario_A`·`decide:scenario_C`) input_hash 재매핑뿐**(봉투 내용은
  `input_hash`·`input_len` 외 바이트 동일 — 선택·확률·확신도·요건 판정 그대로, 나머지 253개 hash 그대로). `judgments/`·회귀 골든(`expected_scores*.json`) 그대로.
  매니페스트 사유: R5-ACCESS D25-11 A·C 접근 요건에 접수 상태 AND(decide 증거의 요건 사전 계산 변경)로 judgments_synth decide A·C input_hash 재매핑(봉투 내용 동일)
- 매니페스트 과거 사유 보완(`fixture_manifest.py --check` 가 이력의 사유도 CHANGELOG 에서 찾는다 — R5): 이력에만 있고 CHANGELOG 에
  문장 그대로 없던 사유 1건 — R3f CORE4: T3 사람 확인 checked_at 을 시간대 붙은 RFC3339 로(계약 .11 D14-6) — 계약 .11 'fixtures' 절의
  'R3f-CORE4 T3 checked_at RFC3339 (contract .11 D14-6) fixture+builder' 와 같은 변경의 앞선 사유 문장이다.
- 새 테스트 녹화(`contracts/fixtures` 밖, 테스트 전용): `backend/tests/normalize/fixtures/r4d_core10.zip`(R4 4차 bootstrap 일일 단계
  원문 중 단지 18개 — 청약홈 목록 12(일일 단계 전부) · 상세 201 · 원 공고 21 · 공고문 51(추출 텍스트·표, PDF 제외) · 공식 홈페이지
  26(DOM 텍스트, HTML 제외) + 지역·법정동 565행, 1.8MB, 키·토큰·`.env` 값 검사 0건), `backend/tests/collectors/applyhome/fixtures/r4d_empty_dataset.json`(R4
  4차 첫 시도의 빈 데이터셋 응답 그대로, 82바이트).

### 알려진 한계

- 속성 테스트는 일일 단계(청약홈·공고문·공식 홈페이지 → `store`·잔여 이력·체크리스트·접수 상태)다. 주간 단계(실거래·분양권·미분양·
  입주물량·벤치마크·뉴스 호재·공고 예정 후보)는 수집기 적재(`load_trades` 등)라 이 속성 테스트에 들지 않는다(기존 단위 멱등 테스트).
- 이미 발행된 R4 4차 리비전 5·6 저장본의 중복 경쟁률 행·사라진 compare 근거는 그대로다(발행 불변 — 다시 발행해야 바뀐다).
- 빈 데이터셋 판정은 `totalCount` 가 0 일 때만이다(직전 대비 급감은 보지 않는다 — 적재 중 일부만 찬 데이터셋은 잡지 못한다).

## 2026-10-09.17

R4 3차 재시험(`docs/design/wp/R4_RESULT3.md` §10) 후속 — CEO 결정 **D22**(`docs/design/DECISIONS.md`). 계약 소유자 = **R4-CORE9**(브랜치
`wp/r4-core9`). 마이그레이션 없음(DB 모양 그대로 — head 0015). 필드 삭제 없음, **새 응답 필드 1**(`ComplexRow`·`Complex`(단지 상세
머리)의 `judge_scope_reason`, 선택), 새 사유 문자열 2(접수 '공식 홈페이지 동일성 미확인', 판정 범위·현재 구매가 '출처 상충 — compare 대기'
는 기존 Fact 사유 문자열을 새 자리에). 저장 모양 버전(`SHAPE_VERSION`) 그대로 1 — `judge_scope_reason` 은 선택 필드로 .17 이후 발행
저장본에만 있다(.16 이전 발행 리비전 저장본에는 키가 없다 = null, D14-4 변환 마이그레이션 불필요). 테스트 표(결함 · 테스트 · 수정 전 실패
확인)는 `docs/design/wp/R4_CORE9_TESTS.md`.

**프론트가 맞출 것** — 아래 'FE 차이' 표. `frontend/src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 는 이 브랜치에서 다시 만들지 않았다
(frontend/** = FE 소유) — 머지 뒤 `npm ci` → `npm run gen:api`·`gen:msw`. FE10 e2e `frontend/e2e/api/writes12-r4fe10.spec.ts` 의
`test.fail`(F1 이름 출처 서랍 — 발행 리비전 404)은 이 계약에서 200 이 되므로 **'예상 실패가 통과'로 알린다** — FE 가 표식을 지운다.

### FE 차이(화면이 맞출 것)

| # | 대상 | .16 | .17 | 결정 |
| --- | --- | --- | --- | --- |
| F1 | **`ComplexRow.judge_scope_reason`**, **`Complex.judge_scope_reason`**(단지 상세 `header`) | 없음 — FE 가 서버 `analysis.scope` 첫 행 규칙·`has_dong_name` 정규식을 옮겨 '범위 경계(주소에 동 없음)'를 만들었다(FE10 F5, 계약 변경 요청) | **새 선택 필드**(string\|null, ≤200): 서버 `analysis.scope.judge_scope` 의 `reason` 그대로 — '범위 경계(주소에 동 없음)'·'범위 경계(주소가 지역 법정동에 매칭 안 됨)'·'포함/제외 classify 미해결(review, 미분류)'·'포함/제외 classify 제외 클래스(…)'·'분양가 미공개(공고 전)'·'원 공고 미수집'·'출처 상충 — compare 대기'·'포함 확정 · 접수 가능'·'접수 확인 불가' 등. **현재 사실로 계산한** 범위의 사유 — `judge_scope`(점수 실행 저장값)와 다르면 `rejudge_needed`=true 이고 이 사유는 재판정 뒤 범위의 것. 목록 행·상세 머리 같은 값. .16 이전 발행 저장본에는 키가 없다(= null — 그때는 화면 규칙 폴백) | D22-5 |
| F2 | 발행 리비전 이름 출처 서랍 `GET /provenance/{name_prov}?snapshot_id=<발행 리비전>` | **404**('발행 리비전 … 저장본에 출처 fp_… 없음' — 저장본 출처 수집이 `"name_prov":` 를 모으지 않음) | **200**(.17 이후 발행한 리비전). .16 이전 발행 리비전은 다시 발행하기 전까지 404 그대로(저장본 불변 — D11-1). FE10 e2e `test.fail` 표식을 지운다 | D22-5 |
| F3 | 현재 구매가 `price_low`·`price_high`·`price_mid` Fact 사유(목록 행·상세 `price`·비교 입력) — 기준 타입 가격 **채택 보류**(출처 상충 — compare 대기) | '분양가 미공개' | **'출처 상충 — compare 대기'**(표시 '확인 불가(출처 상충 — compare 대기)'). 현재 구매가가 쓰는 필드(현재 공고 `price_by_type[기준 타입]` 칸, 없으면 타입 행)의 chosen 출처 행이 보류 표식일 때. 판정 범위 사유(F1)도 같은 문자열 | D22-5 |
| F4 | 접수 상태 `Intake.reason` | '공식 홈페이지가 다른 단지' 하나(동일성 판정이 review·unclear 여도) | 판정기가 auto `other_complex` 일 때만 **'공식 홈페이지가 다른 단지'**, review·unclear(미해결·불명)는 새 사유 **'공식 홈페이지 동일성 미확인'**(status '확인 불가' — 접수 근거로 쓰지 않는 것은 같다). 표시 '확인 불가(공식 홈페이지 동일성 미확인)' — FE10 F4 의 원문 버튼 문구('다른 단지 페이지 — 접수 근거 아님')를 이 사유에는 쓰지 않는다 | D22-4 · N11 |
| F5 | G1 첫 적재 요약 `change_event(region·first_load)` | 수집(일일·주간)마다 한 줄씩 생길 수 있었고, bootstrap 판정 단계 값 변경(판정기 추출 적용·compare 채택)은 change_event(critical 포함)로 남았다 | 같은 적재(지역·스냅샷)에 **한 줄** — 수집·판정 단계 값 기록·덮어쓰기를 모두 센다(문구 그대로 '첫 적재: 단지 n개, 값 k건(첫 적재 중 기록·덮어쓰기 — 변경 이벤트 대신 요약)') | D22-4 · m-b |
| F6 | change_event `complex·legal_dong_code`(critical, triggers_rejudge) | 없음 — 다른 출처 주소로 법정동을 보정해도 이벤트 0(조용한 변경) | 주소에 동 없는 단지의 법정동을 같은 단지 다른 출처 주소(잔여 공고 공급위치)로 보정하면 이벤트(첫 적재면 요약 수) — G1 '최근 변경'에 '법정동' 변경 행이 나올 수 있다(old null → new 법정동 코드) | D22-3 · N10 |

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.16) | 이후(.17) | 결정 |
| --- | --- | --- | --- | --- |
| S1 | 재정규화(같은 원문을 다시 저장 — 같은 날 재수집) | 같은 원문의 출처 행을 모두 후보에서 빼서 판정기 추출 행이 내려가고 파서 행('확인 불가')이 chosen — 사실 값은 그대로라 발행 저장본 '확인 불가(출처 누락)'(R4 3차 N9, `missing_provenance` 0 → 40) | 이번 파싱이 같은 자리(엔티티·필드·발췌 위치)를 여전히 판정기에 물으면 그 원문의 판정기 추출·감사 행을 후보로 유지 — '확인됨' 그대로, 이벤트 0. 파서가 이제 값을 읽으면 판정 행은 후보가 아니고 값이 바뀌면 change_event | D22-1 · N9 |
| S2 | P4 포함/제외 classify 재전송 | 미분류(review)인 단지는 입력이 같아도 매번 새 배치로(같은 스냅샷 재판정 `tools/call` 1, R4 3차 N8) | 직전 판정(같은 판정기 버전·같은 항목 텍스트)이 review·manual_review 면 다시 보내지 않는다. 판정 뒤 미분류로 되돌린 단지(범위 경계 → 미분류)는 다시 보낸다. 배치 항목은 단지 id 순 | D22-2 · N8 |
| S3 | 법정동 보정(다른 출처 주소, .16 S7) | 잔여 공고문이 원 단지 주소가 생기기 전에 저장되면 쓰지 못하고, 청약홈 잔여 공고 공급위치는 쓰지 않음 → 다음 날 재수집에서야 조용히 채워짐 | 첫 수집 안에서(저장 · 잔여 공고 이력 동기화 · 수집 실행 끝), 순서와 무관하게. 바뀌면 change_event(F6) | D22-3 · N10 |
| S4 | 공고문 원 번호 인용 | '최초 주택관리번호는 …' | + '최초 입주자모집공고일은 2023.09.25(월요일)이며, 주택관리번호는 2023000463' 변형(같은 줄). '최초' 없는 자기 번호 문장은 인용 아님 | D22-4 · N12 |
| S5 | 첫 적재 요약 | 수집 정규화 이벤트만 | + bootstrap 판정 단계(추출 적용·compare 채택) 값 변경, 같은 적재 한 줄(F5) | D22-4 · m-b |
| S6 | 발행 저장본 출처 서랍 수집 | Fact `prov` + 접수 근거 `raw_document_id` | + 단지 이름 `name_prov`(F2) | D22-5 |

### 스키마 변경

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `complex_row.json` | `judge_scope_reason`(string\|null, ≤200) 선택 — F1. 예시에 추가 |
| 2 | `complex.json` | 같음(단지 상세 `header`) — F1. 예시에 추가 |
| 3 | `openapi.yaml` | `info.version` 2026-10-09.17 |

### 마이그레이션·검증

- DB 마이그레이션 없음(head 0015 그대로). 저장본 변환·backfill 불필요(선택 필드, 모양 버전 그대로). .17 이후 발행하는 리비전부터 새 필드·이름
  출처 서랍이 저장본에 들어간다(발행 리비전 불변 — D11-1).
- `CONTRACT_VERSION`(`app/core/protocols.py`)·`info.version`·`docs/design/DECISIONS.md` = `2026-10-09.17`. 생성물(`openapi.bundled.yaml`,
  `contracts_gen.py`) 재생성(`gen_contracts.py --check`).

### fixtures

- `contracts/fixtures/**` 녹화·매니페스트 변경 없음(`fixture_manifest.py --check`).
- 새 테스트 녹화 `backend/tests/normalize/fixtures/r4c_core9/`(R4 3차 원문 50건 — 청약홈 API·웹 상세, 공고문 추출 텍스트·표, PDF 바이너리
  제외, 공고문 행 `path` = 텍스트 추출본, 키·토큰 검사 통과)는 `contracts/fixtures` 밖(테스트 전용)이다.

### 알려진 한계

- `judge_scope_reason` 은 현재 사실 범위의 사유다 — 화면 범위(저장값)와 다를 수 있다(그때 `rejudge_needed` true).
- 이미 발행된 .16 이전 리비전의 이름 출처 서랍은 다시 발행하기 전까지 404 다(저장본 불변).
- 같은 원문의 판정기 추출 행 보존은 '이번 파싱이 같은 발췌 위치를 여전히 판정기에 묻는' 경우만이다 — 파서·발췌 위치가 바뀌면(파서 개정)
  그 필드는 다음 재판정에서 다시 추출한다(그 사이 '확인 불가' — 이벤트는 남는다).

## 2026-10-09.16

R4 재시험(`docs/design/wp/R4_RESULT2.md` §10) 후속 — CEO 결정 **D21**(`docs/design/DECISIONS.md`). 계약 소유자 = **R4-CORE8**(브랜치
`wp/r4-core8`). 마이그레이션 없음(DB 모양 그대로 — head 0015). 필드 삭제 없음, **새 응답 필드 2**(`ComplexRow`·`Complex`(단지 상세
머리)의 `name_prov`·`name_label`, 선택), 새 사유 문자열 4, 출처 id 종류 추가 1(시장 실거래 Fact 의 `rd_`). 저장 모양 버전
(`SHAPE_VERSION`) 그대로 1 — 두 키는 선택 필드로 이름 출처 행이 있을 때만 나온다. .15 이전에 발행한 리비전 저장본·출처 행 없는
단지에는 **키가 없다**(D14-4 변환 마이그레이션 불필요, FE 는 없으면 null 로 본다). 테스트 표(결함 · 테스트 · 수정 전 실패 확인)는 `docs/design/wp/R4_CORE8_TESTS.md`.

**프론트가 맞출 것** — 아래 'FE 차이' 표. `frontend/src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 는 이 브랜치에서 다시 만들지 않았다
(frontend/** = FE 소유) — 머지 뒤 `npm ci` → `npm run gen:api`·`gen:msw`.

### FE 차이(화면이 맞출 것)

| # | 대상 | .15 | .16 | 결정 |
| --- | --- | --- | --- | --- |
| F1 | **`ComplexRow.name_prov`·`name_label`**, **`Complex.name_prov`·`name_label`**(단지 상세 `header`) | 없음 — 단지 이름은 맨 문자열(출처·라벨 없음) | **새 선택 필드**: `name_prov` = 이름의 chosen 출처 id(`fp_<id>` — `GET /provenance/{id}` 서랍), `name_label` = 그 라벨. 청약홈 공고 단지 '확인됨', 트랙 (A) 공고 예정 후보 = 언론 **'비공식'**. 출처 행이 없는 옛 행·시드(devseed 포함)·.15 이전 발행 저장본은 **두 키가 없다**(= null — 목록 1,000행 저장본 크기를 늘리지 않으려고 null 을 쓰지 않는다). 화면: 이름 옆 라벨 배지(공고 예정 후보 '비공식')·이름 클릭 → 출처 서랍 | D21-8 |
| F2 | 트랙 (A) 공고 예정 후보(`track` 'A' · `applyhome_id` null · 공고일 없음)의 **공고일·가격 Fact** | 공고일 '확인 불가(값 없음)', 가격 low·high·mid '확인 불가(분양가 미공개)' | 모두 **'확인 불가(공고 전)'**(reason `공고 전`) — 목록 행·상세 머리·상세 가격·비교 입력 | D21-8 |
| F3 | G3 시장 **`living_area_prices`** | 실거래 거래에 출처 행이 없어 블록 통째로 빠짐(빈 목록) | 생활권 84㎡ 6개월 시세 행이 있다. `median_won`·`low_won`·`high_won`·`n_trades` 의 `prov` = **`rd_<raw_document_id>`**(그 거래를 실은 실거래 API 원문 — 서랍은 원문 URL·확인일, D15-2 의 rd_ 서랍과 같은 모양), 라벨 '확인됨' | D21-4 |
| F4 | 접수 상태 `Intake.reason` | — | 새 사유 **'공식 홈페이지가 다른 단지'**(status '확인 불가') — 청약홈 등록 홈페이지가 지금 다른 단지 페이지라 판정기(동일성 classify)가 그 단지 페이지로 보지 않았다(review 포함). 표시 '확인 불가(공식 홈페이지가 다른 단지)' | D21-5 |
| F5 | 판정 범위 사유(범위 경계) | '범위 경계(주소가 지역 법정동에 매칭 안 됨)' 하나 | 단지 주소에 동 이름이 없고 다른 출처 주소로도 법정동을 못 찾으면 **'범위 경계(주소에 동 없음)'** | D21-6 |
| F6 | 가격 출처 행(서랍) | 공고문 금액은 표 단위를 보지 않고 원으로 읽음 | 공고문 금액 표 단위 환산: '(단위: 천원)'·'만원' 표에서 읽은 가격 서랍 발췌 끝에 `[단위 근거] <표 머리 줄>` 한 줄. 단위 표기 없는 표의 가격은 reason **'단위 표기 없음 — 원으로 봄'**(라벨 확인됨). 1차 출처끼리 10배 이상 다르면 가격 Fact '확인 불가(출처 상충 — compare 대기)'(기존 보류 표시와 같다) | D21-1 |
| F7 | G1 첫 적재 요약 `change_event(region·first_load)` 문구 | '첫 적재: 단지 n개, 값 k건(빈 값 → 값 — 변경 이벤트 대신 요약)' | '첫 적재: 단지 n개, 값 k건(**첫 적재 중 기록·덮어쓰기** — 변경 이벤트 대신 요약)' — 같은 bootstrap 안의 값 → 다른 값 덮어쓰기도 센다(첫날 G1 에 가격 critical 없음) | D21-7 |
| F8 | G7 판정 로그 purpose | — | 새 purpose **`classify:site_identity:batch<n>`**(공식 홈페이지 동일성, classify 3클래스 `same_complex`·`other_complex`·`unclear`) | D21-5 |

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.15) | 이후(.16) | 결정 |
| --- | --- | --- | --- | --- |
| S1 | 공고문 공급금액 표 금액 | 언제나 원 | 표 머리·근처의 단위 표기('(단위: 세대, 천원)'·'만원'·'원')로 환산. 단위 표기 없으면 원 + reason '단위 표기 없음 — 원으로 봄'. R4 재시험 N1(중흥S-클래스 84A 617,000원 '확인됨') | D21-1 |
| S2 | 가격 출처 상충(resolver) | 같은 rank 1차·1차만 compare, rank 다르면 rank 1 채택 | 가격 필드는 **다른 출처 종류의 1차 출처와 10배 이상** 다르면 rank 와 무관하게 채택 보류 + compare(P5 도 cross-rank). 공고별 타입 가격(`price_by_type`)은 같은 타입 청약홈 가격과 10배 이상이면 보류. compare same_fact → 단위가 분명한 출처 채택, contradicts·different_facts·review → 보류 유지(사람 확인) | D21-1 |
| S3 | 수집 텍스트 NUL·제어 문자 | 그대로 → Postgres `DataError`(그 공고문 정규화 전부 롤백), 인용 정규식 실패 | 원문 읽기(`read_raw_text`)가 공백 1자로 바꿈(오프셋 그대로, 원문 파일은 보존) + 출처 행 쓰기 마지막 방어 | D21-2 |
| S4 | 공고문 원 번호 인용 | '최초 주택관리번호는 2025000302' 만 | '2025-000302'·'2025 - 000302'(하이픈·공백)도 → 잔여 공고 번호 단지 행 없음, 같은 날 재수집 change_event 0(R4 재시험 N3·N4 재생 고정) | D21-3 |
| S5 | 시장 실거래 Fact 출처 | 거래 행 출처 행(없으면 출처 누락 → 블록 생략) | 출처 행 없으면 그 거래의 원문 문서 `rd_`(거래 행마다 출처 행을 만들지 않음) — 발행 stats `missing_provenance` 에서 실거래가 빠진다 | D21-4 |
| S6 | 접수 classify 입력 | 공식 홈페이지 문구 그대로 | 먼저 판정기 classify(단지 이름·위치 + 페이지 텍스트)로 그 단지 페이지인지 → auto `same_complex` 만 접수 classify. 같은 문구 다음 날은 분류 복사(호출 없음, D10-2) | D21-5 |
| S7 | 동 이름 없는 단지 주소 | 법정동 NULL → 범위 경계 | 같은 단지의 다른 출처 주소(원 단지에 묶인 잔여 공고의 공급위치·주소 출처 행)로 법정동(단지 주소는 그대로, 찾은 법정동은 재배정에도 유지), 지역 안이면 '범위 경계' → 미분류(P4 가 다시 분류) | D21-6 |
| S8 | 첫 적재(bootstrap) 이벤트 | 빈 값 → 값만 요약 | 같은 적재 안의 값 → 다른 값 덮어쓰기도 요약(수집 정규화 이벤트 전부) | D21-7 |
| S9 | P4 포함/제외 classify | 지역 단지 전부 배치(한 단지 입력이 바뀌면 전체 재판정) | **입력이 바뀌었거나 판정이 없는 단지만** 배치 — 나머지는 직전 판정(같은 판정기 버전) 그대로 | D21-7 |
| S10 | 보고서 §1-1 생활권 세대수 | `region.living_areas[].households`(지역 생성 때 null 이면 '확인 불가(출처 누락)') | API 와 같은 세대 현황 집계 Fact(라벨 추정, prov `rd_`) | D21-7 |
| S11 | 판정기 자식 프로세스 env | 프로세스 환경변수만 | + 설정 파일(`ENV_FILE`·`.env`)의 판정기 자격 증명 이름(`JUDGE_SECRET_ENV_NAMES`·`TYPESAFE_`·`OPENROUTER_`·`JEV_` …), 프로세스 환경변수가 이김, 값은 stderr·오류에서 가림 | D21-8 · D19-3 |

### 스키마 변경

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `complex.json` | `name_prov`(string\|null)·`name_label`(Label\|null) 선택 — F1. 예시에 추가 |
| 2 | `complex_row.json` | 같음 — F1. 예시에 추가 |
| 3 | `complex_detail.json` | 예시 머리(트랙 A 후보)에 `name_prov`·`name_label`('비공식') |
| 4 | `openapi.yaml` | `info.version` 2026-10-09.16 |

### 마이그레이션·검증

- DB 마이그레이션 없음(head 0015 그대로). 저장본 변환·backfill 불필요(선택 필드, 모양 버전 그대로).
- `CONTRACT_VERSION`(`app/core/protocols.py`)·`info.version`·`docs/design/DECISIONS.md` = `2026-10-09.16`. 생성물(`openapi.bundled.yaml`,
  `contracts_gen.py`) 재생성(`gen_contracts.py --check`).

### fixtures

- `contracts/fixtures/**` 녹화·매니페스트 변경 없음 — `judgments_synth` 는 `record_synth_judgments.py --check` 일치(254개 봉투: 회귀 흐름에는
  미분류 공식 홈페이지 접수 행이 없어 동일성 classify 호출이 없고, 포함/제외 배치는 devseed 판정 입력과 달라 그대로 전부 판정된다).
  생성기(`tools/record_synth_judgments.py`)는 동일성 classify(`same_complex`) 합성 응답을 알도록 고쳤다(다음 녹화 대비). 매니페스트
  사유: R4-CORE8 D21-5 record_synth_judgments.py knows site identity classify (recordings unchanged)
- 새 테스트 녹화 `backend/tests/normalize/fixtures/r4b_core8/`(R4 재시험 원문 33건 — 청약홈 API·웹 상세, 공고문 추출 텍스트·표, PDF 바이너리
  제외, 키·토큰 검사 통과)는 `contracts/fixtures` 밖(테스트 전용)이다.

### 알려진 한계

- 단위 상충(S2)에서 contradicts 면 어느 금액도 채택하지 않는다 — 사람 확인(G7)이 풀 때까지 그 타입 가격·현재 구매가는 '확인 불가'.
- 공고별 타입 가격이 단위 상충으로 보류되면 compare 가 청약홈 값을 채택해도 그 공고의 현재 구매가는 '확인 불가'로 남는다(옛 공고
  가격으로 돌아가지 않는다 — R3 3차 M-4 규칙).
- 동 이름 없는 주소의 대체 주소(S7)는 원 단지에 묶인 잔여 공고·주소 출처 행에서만 찾는다(공식 홈페이지 페이지 텍스트의 주소는 읽지
  않는다).

## 2026-10-09.15

R4 실데이터 시험(`docs/design/wp/R4_RESULT.md`) 후속 — CEO 결정 D18·**D20**(`docs/design/DECISIONS.md`). 계약 소유자 = **R4-FIX**(브랜치
`wp/r4-fix`, D20-1 위임). 마이그레이션 `0015`(`0015_r4fix.py`: 새 열 `judgment_log.model`·`judgment_log.provider` + 기존 행을 원응답에서
채움). 필드 삭제 없음, **새 응답 필드 2**(`JudgmentEnvelope.model`·`provider`), **새 요청 필드 1**(`POST /regions` `applyhome_query`),
`ApplyhomeQuery.to_ym` 새 키, 기본값 변경 1(청약홈 조회 창). 저장 모양 버전(`SHAPE_VERSION`) 그대로 1(봉투 두 키는 선택 필드 — 옛
저장본에는 없다). 테스트 표(결함·결정 ID · 테스트 · 수정 전 실패 확인)는 `docs/design/wp/R4_FIX_TESTS.md`.

**프론트가 맞출 것** — 아래 'FE 차이' 표. `frontend/src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 는 이 브랜치에서 다시 만들지 않았다
(frontend/** = FE 소유) — 머지 뒤 `npm ci` → `npm run gen:api`·`gen:msw`.

### FE 차이(화면이 맞출 것)

| # | 대상 | .14 | .15 | 결정 |
| --- | --- | --- | --- | --- |
| F1 | **`JudgmentEnvelope.model`·`provider`**(`GET /ops/judgments` items, 단지 상세 `judgments[]`) | 없음 — 응답 모델은 `raw.model` 안에만 | **새 선택 필드**(string\|null): 그 응답의 실제 모델(`jev-1.13.0`·로컬 처리 `jev-latest`)·provider(`typesafe`·`none`). `provider='none'` = 판정기가 모델을 부르지 않은 로컬 처리(비용 없음) — G7 판정 로그에 '로컬' 표시 권장. 캐시 키 `adapter_version` 의 모델(고정 모델)과 다를 수 있다 | D18-1 · D20-1 |
| F2 | **G7 `JudgmentStats.real_calls`** | judgment_log 행 수(blocked 포함) | **판정기로 실제 보낸 MCP `tools/call` 수**(잡 stats `tools_calls` 합 — 전송 계층에서 셈, 수집 단계 판정 포함), 계수가 없는 기간(이전 잡)은 blocked 제외 행 수가 하한. `total_calls = real_calls + cached_hits`. 도구별 `calls` 도 같은 규칙 | D18-2 |
| F3 | **`POST /regions` 본문 `applyhome_query`** | 없음(본문에 넣으면 422) | **선택 필드**(`ApplyhomeQuery`: `from_ym`·`to_ym` 'YYYY-MM', `areas`) — `region.applyhome_query` 에 그대로 저장. 형식이 틀리면 422 `validation_error`. G0 에 '조회 기간(고급)' 입력을 둘 수 있다(없으면 {} = 기본 창) | D20-1 |
| F4 | 청약홈 기본 조회 창 | 기준월 −10개월 ~ +1개월 | **지난 24개월 + 향후 12개월**(meta §1-4) — 지역 첫 수집 시간이 늘고 오래된 공고 단지가 목록에 더 나온다 | D20-1 · D18-8 |
| F5 | **트랙 (A) 공고 예정 단지**(G1·G2 목록·G3 상세) | 픽스처에만 | 주간 뉴스 수집 뒤 판정기(screen·extract·classify·compare)가 고른 **공고 전 단지 행**: `applyhome_id` null · `track` 'A' · 이름 출처 라벨 **'비공식'**(언론 URL) · 공고일·가격 '확인 불가(공고 전)' · 판정 범위 '보류 — 공고 후 재판정'(사유 '분양가 미공개(공고 전)'). 새 후보는 `change_event(entity=complex, field=track, severity=notice)`. 청약홈 공고가 같은 이름(옛 이름 포함)으로 오면 **같은 행**에 주택관리번호가 붙고 critical 새 공고 이벤트(`notice·applyhome_id`, '공고 예정 후보와 합침') | D20-2 |
| F6 | 판정 범위 사유 | 잔여 공고만 수집된 원 단지도 '분양가 미공개(공고 전)' | 주택관리번호가 있고 공고일이 없는 단지(잔여 공고문이 인용한 원 단지 — 원 공고를 못 받음)는 **'원 공고 미수집'** | D18-4 |
| F7 | 첫 적재(bootstrap) 변경 목록 | 빈 값 → 값 critical 수백 건 | `change_event(entity=region, field=first_load, severity=info)` **한 줄**(`첫 적재: 단지 n개, 값 k건 …`) — G1 '최근 변경' 첫날이 critical 로 차지 않는다 | D18-7 · m3 |
| F8 | 미분양 사실 | 출처 행 없음 → prod '확인 불가(출처 누락)', 대시보드 KPI '미분양 자료 없음'(틀린 사유) | 값마다 출처(`fp_`, 라벨 확인됨, 통계누리 원문 URL) — KPI·시장 화면에 값이 보인다 | D18-7 · M2 |

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.14) | 이후(.15) | 결정 |
| --- | --- | --- | --- | --- |
| S1 | `adapter_version`(캐시 키) | `…+<응답 model>` — 응답마다 모델이 다르면(로컬 처리 `jev-latest`) 실행 중 버전이 뒤집히고 캐시가 빗나가 숨은 재호출(R4 C1) | `…+<고정 모델>` = **모델을 실제로 부른 응답(provider ≠ none)** 의 model. 로컬 처리 응답의 model 은 무시. 실행 중 키 불변(replay 없음), 모델이 바뀌면 `change_event(judge·version·critical)` 후 다음 실행부터 새 키로 전체 재판정 | D18-1 |
| S2 | 잡 stats | `judge_calls` = 봉투 cached=false 수(파이프라인만) | `tools_calls`·`tools_calls_by_tool`(전송 계층 MCP tools/call 수, 수집 단계 판정 포함) 새 키. JevMcpAdapter 잡의 최상위 `judge_calls` = `tools_calls` | D18-2 · m2 |
| S3 | 실거래 `legal_dong_code` | 응답 `umdCd` 가 있을 때만(실제 응답엔 없음 → 전부 NULL) | `sggCd + umdNm` 을 참조 표로 매칭(실패·모호 NULL), 수집 stats `loaded.rtms_legal_dong`(매칭률), 기존 NULL 행 보정 | D18-3 |
| S4 | 잔여·임의·무순위·재공급 공고 | 자기 주택관리번호로 단지 행, 공고문 제목 줄이 단지 이름 후보 | 원 단지(사업)에 `remaining_event` 로 붙음(자기 행 없음), 제목 줄은 이름 후보 아님, 원 공고를 주택관리번호로 다시 받음(수집 stats `loaded.originals`) | D18-4 |
| S5 | 공고문 조각 판정 purpose | `…:rd<원문 id>:<n>` | 정규화 본문 해시(같은 조각은 한 번만 판정) | D18-5 |
| S6 | alembic DB URL | 환경변수 `DATABASE_URL` > ini | `DATABASE_URL` > **`ENV_FILE` 이 있으면 앱 설정의 URL**(못 읽으면 실패) > ini(dev.db) | D20-1 · M4 |
| S7 | 공유 공식 홈페이지 URL | 원문이 첫 단지에만 묶여 다른 단지 접수 행 없음·스크린샷 매번 새로 | 대상 단지마다 원문(같은 행), 직전 렌더는 URL 로만 | D18-6 · M5 |

### 스키마 변경

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `judgment_envelope.json` | `model`(string\|null, ≤64)·`provider`(string\|null, ≤32) 선택 — F1. `adapter_version` 설명(고정 모델, S1) |
| 2 | `region.json` | `ApplyhomeQuery.to_ym` 새 키, `from_ym`·`to_ym` 패턴 월 01~12, 기본 창 설명(F4). `RegionCreate.applyhome_query` 선택(F3) |
| 3 | `openapi.yaml` | `createRegion` 설명(applyhome_query), `info.version` 2026-10-09.15 |
| 4 | DB `0015` | `judgment_log.model` VARCHAR(64) NULL · `judgment_log.provider` VARCHAR(32) NULL + 기존 행 원응답(`output_json`)에서 채움. downgrade = 열 삭제 |

### 마이그레이션·검증

- `cd backend && uv run alembic upgrade head`(0015 — 앱 import 없음). R4 재시험처럼 `.env` 를 따로 두면 `ENV_FILE=../r4/.env uv run alembic upgrade head`
  (S6, 조용한 dev.db 없음). 저장본 backfill 불필요(모양 그대로).
- 왕복·데이터: `tests/contracts/test_r4fix_migrations.py`(SQLite·임베디드 Postgres 16 — 0014 행 → 0015 열 채움, 0014 ↔ head, autogenerate
  diff 0, ENV_FILE 폴백).
- `CONTRACT_VERSION`(`app/core/protocols.py`)·`info.version`·`docs/design/DECISIONS.md` = `2026-10-09.15`. 생성물(`openapi.bundled.yaml`,
  `contracts_gen.py`) 재생성(`gen_contracts.py --check`).

### fixtures

`contracts/fixtures/incheon_gimpo_2026-10-08/judgments_synth/**` 재녹화(`tools/record_synth_judgments.py`) — 공고문 조각 판정 purpose 가
정규화 본문 해시로 바뀌어(S5) extract·screen 녹화 파일 이름이 바뀌고 `_meta.counts.screen` 78 → 39(같은 조각 중복 제거). 다른 도구 녹화는
그대로. 매니페스트 사유: R4-FIX D18-5 judgments_synth re-recorded (chunk purpose = normalized text hash)

이어서 같은 녹화를 한 번 더 다시 만들었다 — 봉투 모양에 계약 .15 선택 필드 `model`·`provider`(F1)가 들어가 254개 파일 모두 두 키(이 녹화의 가짜
판정기 응답에는 provider 가 없어 null)가 붙었다. 값·hash·파일 이름은 그대로. 매니페스트 사유: R4-FIX contract .15 judgments_synth re-recorded (envelope model/provider)

### 알려진 한계

- 트랙 (A) 후보의 신호는 뉴스뿐이다(공식 홈페이지 신호는 주소가 있는 단지 — 청약홈 공고 뒤 — 의 접수 classify 'pending' 으로만). 후보에는
  주소·세대수가 없어 법정동·생활권이 비고, 청약홈 공고와의 합치기는 이름 키(옛 이름 포함)가 **같을 때만**이다.
- 녹화 재생(`WORKER_NET_MODE=replay`)은 녹화의 조회 창(`recorded_window`)으로 조회한다 — 녹화 zip 이 창을 정한다.

## 2026-10-09.14

R3 9차 리뷰(`docs/design/wp/R3_REVIEW9.md`) 후속 — CEO 결정 D17(`docs/design/DECISIONS.md`)과 R3i 배정(`docs/design/wp/R3I_FIX.md` CORE7).
계약 소유자 = R3i CORE7(브랜치 `wp/r3i-core7`). 마이그레이션 `0014`(`0014_r3i.py`: 새 열 `snapshot_view_unit.backfilled_at` + 보고서 저장본
점수 prov id 변환) · `0013` 수정(compare 채택 표식 보존 + 전환 표지 — 아직 0013 을 안 거친 DB 만 해당). 필드 삭제 없음, **새 응답 필드 3**
(`Snapshot.backfilled_at` · `HumanCheck.basis_type_code` · `ChecklistItem.job_id`(PATCH 응답)), **새 오류 code 2**(`discount_format` ·
`discount_not_below_price`), **응답 상태 추가 2**(`PATCH /ops/checklist/{id}` 202, `PATCH /regions/{id}` 이름만 → 202), 잡 상태 의미 변경
(`snapshot.publish` 예외 → 지연 재큐잉 재시도). 저장 모양 버전(`SHAPE_VERSION`) 그대로 1(0014 변환은 값(id)만 바꾼다 — D14-4 변환 마이그레이션).
테스트 표(리뷰 ID · 테스트 · 수정 전 실패 확인)는 `docs/design/wp/R3I_TESTS.md`.

**프론트(FE8)가 맞출 것** — 아래 'FE 차이' 표 하나만 보면 된다. `frontend/src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 는 이 브랜치에서 다시
만들지 않았다(frontend/** = FE8 소유) — 머지 뒤 `npm ci` → `npm run gen:api`·`gen:msw`.

### FE 차이(FE8 — 화면이 맞출 것)

| # | 대상 | .13 | .14 | 결정·리뷰 |
| --- | --- | --- | --- | --- |
| F1 | **`Snapshot.backfilled_at`**(`GET /regions/{id}/snapshots` 항목·`GET /regions/{id}` `latest_snapshot`) | 없음 — 업그레이드 backfill 이 발행 뒤 사실로 다시 계산해 채운 값이 섞여도 표지 없음 | **새 선택 필드**(string\|null, KST ISO): 그 발행 리비전 저장본에 backfill 이 **새로 계산해 채운** 값(빠진 단지 상세·시나리오·출처 서랍 등)이 있으면 가장 늦은 시각. 없으면 **키 자체가 없다**(발행 저장본 안 이 객체 바이트 그대로). 화면: 그 리비전을 볼 때 "업그레이드 때 다시 계산한 값 포함(발행 순간 값이 아닐 수 있음)" 안내 | D17-2 · major 2 |
| F2 | **`POST /ops/human-checks` 응답 `basis_type_code`** | 없음 | **새 필드**(string\|null): field=discount 면 그 할인이 들어간 기준 타입 코드('84C'), 아니면 null. 폼에는 입력 전부터 단지 상세 `price.basis_type_code`(이미 있음)를 '기준 타입 84C 할인(원)'으로 표시하고, 응답의 이 값으로 '기준 타입 84C 할인으로 반영' 확인. 기준 타입이 나중에 바뀌면(84㎡에 더 가까운 타입) 그 할인은 옛 타입 칸 표시만 남고 차감 없음 | D17-4 · m3 |
| F3 | **사람 확인 할인 값 검사**(`field=discount` 의 `value_text`) | 쉼표·공백을 지우고 유니코드 숫자로 읽음 — `'1,0'`→10, `',,5,,'`→5, `' 1 0 0 0 '`→1000, 전각·아랍 숫자 통과, `'-0'`→0, 가격 이상 할인 201(차감 없음) | 서버 규칙(FE 목·폼 검사를 이것과 같게): 앞뒤 공백을 뗀 값이 `^(?:[0-9]{1,3}(?:,[0-9]{3})+\|[0-9]+)원?$`(ASCII 숫자, 쉼표는 세 자리마다, '원'은 붙여서 하나) 이고 0 ~ 100,000,000,000 정수. 어기면 **422 `discount_format`**. 할인 ≥ 기준 타입 차감 바탕(min(대표층가, 최고가))이면 **422 `discount_not_below_price`**(0 = 할인 없음 확인은 통과). 둘 다 `field_errors = [{loc: ["body","value_text"], msg}]`(msg = detail). **다른 칸도 틀리면** `validation_error` + 모든 칸 | m2 |
| F4 | 사람 확인 다른 숫자 필드(`max_price_won`·`resale_months`·`residency_months`·`down_payment_pct`) | 위와 같은 느슨한 읽기 | 같은 엄격한 숫자(ASCII·쉼표 세 자리마다·숫자 사이 공백 없음), 단위 앞 공백은 한 칸까지('3 년' 허용), 음수 거절. 틀리면 그대로 `validation_error` | m2 |
| F5 | **`PATCH /ops/checklist/{id}`** 응답 | 200 + 항목(발행 없음 — 발행 리비전 보고서 체크리스트가 옛 값) | 상태·메모·기한이 실제로 바뀌면 **202** + 항목 + **`job_id`**(snapshot.publish — 단지 지역, 단지 없는 '지역 공통' 항목은 모든 지역 중 첫 잡). 바뀐 것이 없거나 발행할 리비전이 없으면 200 + `job_id` null. 화면: job_id 가 있으면 잡 감시(다른 발행 쓰기와 같은 규칙) | D17-5 · m15 |
| F6 | **`PATCH /regions/{id}`** 이름만 | 200 + `change_event`·`job_id` null(보고서 표지 옛 이름) | 발행 리비전이 있으면 **202** + `job_id`(snapshot.publish, `change_event` null), 없으면 200 + null. 선택이 바뀌는 경우는 그대로(202 region.expand) | D17-5 · m15 |
| F7 | `PATCH /catalysts/{id}` | 좌표 소수 7자리 이상이면 같은 본문 재전송도 202(새 잡). 스냅샷 없는 지역 202 + job null | 좌표는 소수 6자리로 반올림해 비교·저장(응답 `lat`·`lon` 도 6자리) → 같은 본문 재전송 **200** + null. 바뀌었어도 발행할 리비전이 없으면 **200** + null | m8 · m14 |
| F8 | `snapshot.publish` 잡 예외(이월 복사 중 잠금 실패·임대 잃음·worker 재시작 뒤) | failed(재시도 없음) — 그 리비전이 building 에 멈추고 뒤 쓰기가 끝없이 미뤄짐 | **지연 재큐잉 재시도**: status `queued`, stats `error_retries`(1~5)·`publish_error`(예외 이름)·`requeue_reason`(`publish_error: …`)·`not_before`(2·4·8·16·30초). 5번 넘으면 failed(error_text `publish_error: …`, stats `redeferred_job_id` — 아래 F9). 화면(jobWatch): .13 F4 와 같다 — queued + `requeue_reason` = 진행 중 | D17-3 · major 3 |
| F9 | 미뤄진 후속 잡(done, stats `deferred_to`) | 그 리비전이 실패로 멈추면 영영 발행 안 됨 | 그 리비전의 발행·재판정 잡이 끝내 실패하면 그 쓰기를 **새 후속 발행 잡**으로 다시 등록하고 미뤄진 잡 stats 에 **`redeferred_job_id`**. 새 잡은 멈춘 리비전을 끝까지(이월 이어 채움 → ready → 발행, stats `resumed_snapshot_id`) 가져가거나 재판정을 등록(stats `rejudge_job_id`, `deferred_to`). 화면: 감시하던 잡이 done + `deferred_to` 인데 나중에 `redeferred_job_id` 가 생기면 그 잡을 이어 감시 | D17-3 · major 3 |
| F10 | `POST /reports`(compare 생략) | 기본 비교(revision_of) 저장본 미완을 안 봐서 202 뒤 잡 실패 | 기본 비교 리비전의 report·report_diff 가 미완이면 **503** `materialize_pending`(202 전에) — 지정 비교와 같은 규칙 | m9 |
| F11 | `POST /ops/human-checks` 422 `field_errors` 순서 | 스키마 검사기 순서(checked_at 이 뒤일 수 있음), 스키마 오류가 있으면 값 칸 오류 빠짐 | **checked_at 오류가 늘 먼저**, 스키마 오류가 있어도 값 칸(형식·할인 상한) 오류를 함께 | m10 · m2 |
| F12 | 할인·계약금 사람 확인 뒤 새 공고(무순위·정정) | 새 공고가 그 값을 싣지 않으면 현재 공고 할인·계약금이 비고 차감이 조용히 사라짐(change_event·재검토 없음) | **의미 단위 유지**(값 없음 ≠ 다른 값): 새 공고 행에도 사람 확인 값(라벨 확인됨, reason `사람 확인(…)`)이 들어가 `payment[].discount_by_type`·`down_payment_pct`·`price.discount` 그대로. 새 공고가 **다른 값**을 내면 .12 그대로 D12-1(채택 + critical + '사람 확인 재검토'). 옛 공고 행을 `entity_id` 로 지정한 할인 사람 확인도 현재 공고에 들어간다 | D17-4 · major 4 · m4 |

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.13) | 이후(.14) | 결정·리뷰 |
| --- | --- | --- | --- | --- |
| S1 | backfill 동시성·중단 | 임대 없음. 출처 서랍을 다시 쓸 때 표식을 내리고 서랍 행 전부 DELETE 를 커밋한 뒤 따로 써서, 그 사이 중단(Ctrl+C·worker 재시작)·겹침(compose 자동 backfill + CLI)이면 발행 순간 서랍이 지워지고 다음 실행이 **지금 사실로** 다시 만들었다(리뷰 재현: `fp_591` '계약금 10%' → '20') | 리비전마다 **발행과 같은 임대**(`snapshot.publish_lease`, 보유자 `backfill:<pid>:<tid>`)를 잡는다 — 다른 발행·backfill 이 들고 있으면 그 리비전은 건너뛰고 결과 `busy` 에(다음 실행이 다시, worker 는 5분마다). 출처 서랍은 **한 트랜잭션**(임대 확인 → 옛 행 DELETE → 새 행 INSERT(있던 서랍 본문 바이트 그대로) → 표식). 새 키 행은 지우지 않고 더하기만, 묶음마다 임대 확인. 어느 시점에 끊겨도 저장된 본문·서랍 그대로 | D17-1 · major 1 |
| S2 | backfill 새 키·목록 범위(.13 S4 정정) | .13 S4 는 "키만 그 리비전 범위"였고 **목록 본문**(단지 목록·비교 입력)은 지금 단지 전부로 다시 계산했다(발행 뒤 단지가 옛 리비전 시나리오 2 목록에 나타남, 상세 404) | 단지 상세 키 **와** 단지 목록 본문 행·비교 입력 단지 = 그 리비전 단지 목록 저장본(어느 시나리오든)의 단지 ∪ 이미 있는 단지 상세 키(근거 저장본이 없으면 제한 없음). 대시보드·시장·민감도·보고서 본문은 다시 계산하면 그때 사실 범위다 — **새로 계산해 채운 단위에는 `backfilled_at`**(F1)이 남는다. 이미 있는 행·서랍은 바이트 그대로. 발행 뒤 사실이 바뀐 상태에서 일부만 쓴 단위를 채우면 한 리비전 안에 시점이 다른 값이 섞일 수 있다 — 그 표지가 F1 | D17-2 · major 2 |
| S3 | 보고서 저장본 점수 prov(.13 이전 저장분) | `sc_<성분 행>`·`st_<합계 행>`(서랍 없음, KPI `st_<실행>` 과 부딪힘 — 리비전 11 223개·12 461개) | 0014 가 `sc_<실행>_<단지>_<성분>`·`st_<실행>_<단지>`(API 서랍 id)로 바꾸고(본문·sha256 다시, 모양 그대로) 그 리비전 출처 서랍 단위를 미완으로 → backfill 이 새 id 서랍만 더한다 | m5 · D14-4 |
| S4 | 0013 파서 할인 '확인됨' → '추정' | 사유를 통째로 덮어써 compare 채택 표식을 지움, change_event·재판정 없음 | 사유가 있으면 뒤에 붙임(표식 보존) + 표지 `(0013 확인됨→추정)`. backfill 이 표지 붙은 채택 할인마다 critical·재판정 change_event 를 한 번(멱등) + 재판정 잡(결과 `discounts_relabelled`). **이미 .13 0013 을 거친 DB 는 표지가 없어 해당 없음**(녹화 공고 할인 줄 0건 — 실데이터 영향 0) | m1 |
| S5 | SQLite 개발 모드 발행 쓰기 | 저장본 묶음·이월 복사 단계가 연달아 쓰기 잠금을 잡아, 기다리던 API 쓰기(바쁨 처리기 1~100ms 간격 재시도)가 계속 놓쳐 2.5s | 묶음·단계 사이에 `core.db.SQLITE_WRITE_YIELD_S`(0.12s) 쉰다 — 기다리던 쓰기가 끼어든다. Postgres 는 해당 없음 | D17-6 · m18 |
| S6 | SQLite API 체크포인터 | 예외를 기록 없이 삼킴(WAL 이 자라도 모름) | 첫 실패·60번마다 경고 로그(`sqlite.checkpoint_failed`), 연달아 5번이면 요청 커밋 자동 체크포인트로 되돌림(`sqlite.checkpoint_fallback`), 다시 되면 끔 | m12 |
| S7 | 발행·backfill 나눠 쓰기 | 임대를 잃은 이전 보유자가 확인 없이 끝까지 씀 | 묶음 트랜잭션마다 첫 문장이 임대 확인(`LeaseLost` — 그 묶음부터 아무것도 쓰지 않음) | m13 |
| S8 | redact | — | camelCase 키(`accessKey=`)·`pass:`, 키 없는 공급자 토큰(`sk-ant-…`·`sk-…`·`ghp_…`·`github_pat_…`·`xox?-…`·`AKIA…`·`glpat-…`·`AIza…`), dict 비밀 키의 정수·실수 값(개수 키 `max_tokens` 등은 그대로), 'the/a/this bearer 소문자낱말' 산문은 가리지 않음(토큰은 그대로 가림) | m17 |
| S9 | worker backfill | 시작 때 한 번, 사람 확인 이전 예외가 리비전 채우기까지 막음 | 단계(`human_checks`·`discount_relabel`)·리비전마다 따로 실패(결과 `failed[].step`), 실패·busy 면 상주 루프가 5분마다 다시 | m6 |
| S10 | 잡 카운터 | 지연 재큐잉이 `stale_recoveries` 를, stale 회수가 `requeue_count` 를 지움 | 서로 이어 간다(`error_retries` 포함) | m11 |
| S11 | `python -m app.worker --once` | 재큐잉 대기 잡(`not_before`)을 남긴 채 0 으로 끝 | 그 시각까지 기다려 실행(최대 20분), 그래도 남으면 종료 코드 **3** | m16 |
| S12 | 이월 발행 building → ready | 이월 복사를 건너뛴 재실행은 ready 로 안 가 publish_blocked | 이월이 끝났으면(`persist.carry_done` — 점수 실행이 모두 이월 복사이고 시나리오를 다 덮음) 늘 ready → 발행(멱등). 이월이 아닌 판정 결과가 있으면 그 판정이 발행 | D17-3 |

### 스키마 변경

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `snapshot.json` | `backfilled_at`(string\|null, 선택) — F1 |
| 2 | `human_check.json` | `basis_type_code`(string\|null, 선택) — F2 |
| 3 | `checklist_item.json` | `job_id`(integer\|null, 선택 — PATCH 응답에만) — F5 |
| 4 | `error.json` | code enum 에 `discount_format`·`discount_not_below_price` — F3 |
| 5 | `openapi.yaml` | `updateChecklistItem` 202(예시 `checklist_item_patched.json`) + 설명, `updateRegion` 200/202 설명, `updateCatalyst`·`createHumanCheck` 설명. `info.version` 2026-10-09.14 |
| 6 | DB `0014` | `snapshot_view_unit.backfilled_at` VARCHAR(32) NULL + 보고서 점수 prov id 변환(S3). downgrade = 열 삭제(id 변환은 되돌리지 않음 — 새 id 는 .13 에서도 유효) |
| 7 | DB `0013`(수정) | 사유 보존 + 전환 표지(S4) — 아직 0013 을 거치지 않은 DB 만 |

### 마이그레이션·검증

- .13 DB: worker 정지 → `cd backend && uv run alembic upgrade head`(0014) → `uv run python -m app.snapshot_view backfill`(결과 `failed`·`busy`
  가 비면 끝, `busy` 면 다시) → worker 시작. compose 의 자동 backfill 과 CLI 가 겹쳐도 임대로 한 쪽만 쓴다(S1) — `docs/runbook.md` §11.
- 왕복·시나리오: `tests/contracts/test_r3i_migrations.py`(SQLite·임베디드 Postgres 16 — 업그레이드 직후 상태 + 발행 뒤 사실 변경에서 세 지점
  중단·동시 backfill 2개·backfill 중 같은 리비전 발행 → 원래 행·서랍 바이트 그대로, backfilled_at, 목록 범위, 0014 보고서 id 변환 왕복,
  0013 표식, 0014 왕복·autogenerate diff 0).
- `CONTRACT_VERSION`·`info.version` = `2026-10-09.14`. 생성물(`openapi.bundled.yaml`, `contracts_gen.py`) 재생성(`gen_contracts.py --check`).

### 측정

- **D14-5 / D17-6**(`tests/api/test_r3f_perf_publish.py` — devseed 16 + 합성 1,000 단지 × 시나리오 5, 기준 잡 ≤30s·API 쓰기 대기 ≤1s 그대로).
  9차 리뷰 실패(전체 스위트 부하에서 API 쓰기 2.522s — SQL 실행 잠금 대기 2.509s, COMMIT 0.001s)의 원인 = 저장본 묶음·이월 단계가 끝나자마자
  다음 묶음이 쓰기 잠금을 다시 잡아 SQLite 바쁨 처리기(1~100ms 간격 재시도)로 기다리던 API 쓰기가 계속 놓친 것. 수정 = S5(`WriteYield` —
  잠금을 이어서 0.2초 넘게 들었으면 0.12초 양보, 잡 stats `write_yields`). R3i 최종 코드:

  | 실행 | 잡 | API 쓰기 최대 / p50(건수) | SQL 실행 최대 / COMMIT 최대 | 묶음 잠금 최대·묶음·양보 | 이월 단계 잠금 최대·단계 |
  | --- | --- | --- | --- | --- | --- |
  | 전체 pytest A 안(regress 와 동시, 3860 통과) | 16.48s | 0.189s / 0.004s(301) | 0.185s / 0.000s | 0.042s·19·1 | 0.046s·8 |
  | 전체 pytest B 안(regress 와 동시, 3860 통과) | 16.63s | 0.196s / 0.004s(300) | 0.192s / 0.003s | 0.039s·19·1 | 0.048s·8 |
  | 별도 1(테스트 단독 + regress 동시, CPU 82%) | 22.95s | 0.258s / 0.004s(403) | 0.254s / 0.028s | 0.050s·19·1 | 0.053s·8 |
  | 별도 2(같은 조건, CPU 83%) | 22.46s | 0.263s / 0.004s(396) | 0.258s / 0.054s | 0.029s·19·1 | 0.061s·8 |

  저장본 5,439행·12.2MB, 출처 서랍 76,909개(.13 과 같음).

## 2026-10-09.13

R3 8차 리뷰(`docs/design/wp/R3_REVIEW8.md`) 후속 — CEO 결정 D16(`docs/design/DECISIONS.md`)과 R3h 배정(`docs/design/wp/R3H_FIX.md` CORE6).
계약 소유자 = R3h CORE6(브랜치 `wp/r3h-core6`). 마이그레이션 `0013`(`0013_r3h.py`, **데이터만** — 스키마 변경 없음). 필드 삭제 없음,
**enum 값 1 추가**(`HumanCheckField` `discount`), **응답 상태 1 추가**(`PATCH /catalysts/{id}` 200 — 바뀐 것 없음), 잡 상태 의미 변경
(발행 busy → 지연 재큐잉 queued). 저장 모양 버전(`SHAPE_VERSION`) 그대로 1.

**프론트(FE7)가 맞출 것** — 아래 'FE 차이' 표 하나만 보면 된다. `frontend/src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 는 이 브랜치에서 다시
만들지 않았다(frontend/** = FE7 소유) — 머지 뒤 `npm ci` → `npm run gen:api`·`gen:msw`.

### FE 차이(FE7 — 화면이 맞출 것)

| # | 대상 | .12 | .13 | 결정·리뷰 |
| --- | --- | --- | --- | --- |
| F1 | **사람 확인 `discount`**(`POST /ops/human-checks` `field`) | 없음(할인은 공고문 파서 '확인됨'만 차감) | **새 HumanCheckField 값 `discount`** = 기준 타입 할인. `value_text` = 원 단위 정수(쉼표·끝 '원' 허용, 0 ~ 1천억, 0 = 할인 없음 확인). 응답 `entity` = `payment_terms`, `entity_id` = 현재 공고(지정 `entity_id` 는 그 단지 납부 조건 행). 그 값이 라벨 **확인됨**(reason '사람 확인(kind)')으로 현재 공고 `discount_by_type.<기준 타입>` 에 들어가고 구매가에서 빠진다(상세·목록·비교·보고서·점수). 의미 단위(D13-2) — 그 단지 다른 공고의 같은 타입 할인 칸에도. 형·범위 틀리면 422 `field_errors[0].loc = ["body","value_text"]`. 201 + `rejudge_job_id`·`job_id` 는 다른 사실 필드와 같다. 화면: G7 사람 확인 폼에 '할인(기준 타입, 원)' 칸 | D16-1 · N-C1 |
| F2 | 할인 표시(`price.discount`·`payment[].discount_by_type`·`price.discount_applied`) | 허용 꼴('84A 분양가 할인 N원' 한 줄)만 공고문 파서 '확인됨'(차감) | 공고문 파서 할인은 **언제나 '추정'**(reason `공고문 자동 추출 — 조건 확인 필요`, 분양가 할인 명시 없는 줄이면 `…, 분양가 할인 명시 아님`) → `discount_applied` false. **'확인됨'(차감)은 사람 확인 할인뿐**(reason `사람 확인(phone)` 등). 화면: '추정' 할인 옆 "공고문에서 찾은 할인(조건 확인 필요) — 사람 확인 시 구매가에 반영" 안내 + G7 사람 확인(F1) 링크. 0013 이 기존 DB 의 파서 '확인됨' 할인을 '추정'으로 바꾼다 | D16-1 · N-C1 |
| F3 | `PATCH /catalysts/{id}` 응답 | 연결 집합이 바뀔 때만 202 + `job_id`. 예정월·좌표만 바꾸면 202 + `job_id` **null**(발행 상세 옛 값) | 보이는 값(위치 확인·`lat`·`lon`·`expected_ym`·연결) 중 **하나라도 바뀌면 202 + `job_id`**(발행 리비전이면 snapshot.publish carry, 발행 전이면 후속 발행 잡 — .12 F4 그대로). **바뀐 것이 없으면 200** + `job`·`job_id` null(새 잡·리비전·출처 행 없음). 화면: 200 이면 잡 감시 없이 끝 | D16-4 · N-M4 |
| F4 | `snapshot.publish` 잡이 busy(같은 리비전을 다른 발행이 들고 있음) | failed `publish_in_progress: …`(후속 잡이면 그 변경이 유실) | **지연 재큐잉**: status 가 다시 **`queued`**, `error_text` null, stats `requeue_count`(누적)·`not_before`(KST ISO — 그 전에는 worker 가 집지 않음, 2·4·8·16·30초…)·`requeue_reason`(`publish_in_progress: …`)·`publish_in_progress`(보유자). 40회(약 18분)를 넘으면 그때 failed `publish_in_progress`. 화면(jobWatch): queued + `requeue_reason` = **진행 중**(발행 막힘 아님, 30분 상한 그대로) — 잡이 done 이 될 때까지 감시 | D16-3 · N-M3 |
| F5 | 그 자리 발행(daily 이월·주간 마감·지역 확장·bootstrap) stats `publish_job_id` | 그 자리 발행이 busy 면 `publish_in_progress` + `publish_job_id` = 자기(발행 안 됨) | busy 면 그 리비전을 발행할 `snapshot.publish` 잡(들고 있는 잡이 그 리비전의 snapshot.publish 면 그 잡, 아니면 새 잡)을 `publish_job_id`(= `publish_retry_job_id`)로. 화면: `publish_job_id` ≠ 자기면 그 잡을 이어 감시(.12 F15 규칙 그대로) | D16-3 · m5 |
| F6 | 다른 발행에 포함돼 닫힌 후속 잡 stats `publish_job_id` | 그 자리 발행(holder 'pid:…')이 포함하면 **null** | 포함한 발행 잡 id(그 자리 발행이면 그 수집·확장·bootstrap 잡 id) — 늘 정수 | D16-3 · m5 · F15 |
| F7 | 발행 리비전 GET 503 `materialize_pending` | 행은 있는데 완료 표식이 없는 단위 → 404 `not_found`(영구) | **503**(backfill 이 표식을 쓰면 200). 업그레이드(0012·0013) 직후 backfill 이 끝날 때까지 모든 발행 리비전이 잠깐 503 — 화면은 .12 D15-8 그대로(같은 키 placeholder·재시도) | D16-2 · m3 · N-M1·N-M2 |
| F8 | `POST /reports`(비교 리비전 지정) | 비교 리비전 `report_diff` 미완을 안 봐서 202 뒤 잡 실패 | 비교 리비전의 그 시나리오 `report_diff`(또는 `report`)가 미완이면 **503** `materialize_pending`(202 전에). 비교 리비전에 그 시나리오가 없으면 그대로 202(delta 표 생략) | m12 |
| F9 | `POST /ops/human-checks` 422 — checked_at 과 **다른 칸도** 틀림 | `checked_at_*` code 로 다른 칸 오류가 사라지거나, 스키마 오류(kind 등)만 남고 checked_at 이 빠짐 | checked_at **만** 틀리면 `checked_at_format`·`checked_at_future`·`checked_at_before_source`(.12 F14 그대로). 다른 칸도 틀리면 **`validation_error`** + `field_errors` 에 **모든 칸**(`["body","checked_at"]` 포함, 순서: checked_at 먼저). 화면(HumanCheckForm): field_errors 전부를 칸마다 표시 | m11 · F14 |
| F10 | 보고서 HTML 점수 Fact 의 출처 id | `sc_<성분 행 id>`·`st_<합계 행 id>`(서랍 없음, KPI `st_<실행>` 과 충돌) | API 와 같은 `sc_<실행>_<단지>_<성분>`·`st_<실행>_<단지>` — 출처 서랍 200. 화면 영향 없음(보고서만) | m6 |

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.12) | 이후(.13) | 결정·리뷰 |
| --- | --- | --- | --- | --- |
| S1 | 공고문 파서 할인 | 허용 목록·다음 줄 조건 낱말로 '확인됨'/'추정' | 언제나 '추정'(허용 목록·금지 낱말 코드 삭제). 0원·경품·지원·'할인 없음' 줄은 후보 없음(그대로) | D16-1 |
| S2 | 0012 데이터 단계 | 행 묶음 = done, 일부만 쓴 단위는 '시나리오 사이 최대 행 수'·'서랍 색인 묶음 수 + 1' 추정으로 판단 | **전부 done=false**(rows = 지금 행 수). 0013 은 .12 DB 의 모든 표식을 done=false 로(재검증) | D16-2 · N-M1·N-M2 |
| S3 | 완결성 | 표식 목록에 없는 단위는 놓침 | 행이 있고 표식이 없는 단위 = 미완(`unit_states`·`pending_count`·GET 503·backfill) | D16-2 · m3 |
| S4 | backfill 새 키 범위 | 지금 계산한 키 전부(발행 뒤 생긴 단지·생활권도) | 그 리비전 단지 목록·시장 저장본의 단지·생활권 id ∪ 이미 있는 키만(근거 저장본이 없으면 제한 없음). 출처 서랍은 저장 본문 + 새로 넣은 행의 id 만(지금 계산의 다른 id 는 넣지 않는다) | D16-2 · D11-1 |
| S5 | 발행 busy | failed `publish_in_progress` | 지연 재큐잉(F4) — `runner.queued_ids` 가 `not_before` 를 본다(벽시계). 그 자리 발행은 holder = `job:<그 잡 id>` | D16-3 |
| S6 | 실패 정리 DELETE | '발행 전' 상태 조건만 | '발행 전' + **임대를 아직 든 동안**(`publish_lease = 내 임대`) — 넘겨받은 새 보유자의 행을 지우지 않는다 | D16-3 · m4 |
| S7 | 이월 판단(`changed_after_runs`) | 점수만 재계산 rejudge 실패·판정기 버전 변경 이벤트 무시, 판정 시각 = 끝 시각, 옛 리비전 판정은 키가 작으면 셈 | 점수만 재계산 실패 → 그 지역 전 단지 재판정(m7), `entity='judge'` 이벤트 = 전 단지(m8), 판정 기준 = **시작** 시각(m9), prev 가 아닌 리비전의 판정은 prev 생성 전에 끝난 것만(m10) | m7~m10 |
| S8 | redact | — | 환경변수 꼴 키(`DATA_GO_KR_KEY=`·`AWS_ACCESS_KEY_ID=`·`crtfc_key`)·`credentials`·`webhook_url`·`signature`·점 키(`jev.api.key`), Cookie/Set-Cookie, 단독 JWT, 'bearer' 뒤 8자 이상 토큰(소문자뿐도 — 'the bearer certificates' 같은 산문도 가린다), Slack·Discord 웹훅, `;`·퍼센트 인코딩 쿼리 키(`api%5Fkey=`·`serviceKey%3D`), 전각·JSON 이스케이프 키 이름, (이름, 값) 쌍 리스트, dict 키 `key`·`auth`·`sig`, 설정 비밀값의 base64(앞 글자 무관)·대소문자·공백류 변형 | m14·m15 |

### 스키마 변경

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `human_check.json` `HumanCheckField` | enum 에 `discount` 추가, 설명(F1) |
| 2 | `openapi.yaml` `updateCatalyst` | 응답 `200`(CatalystUpdated, job null) 추가, 설명(F3). `info.version` 2026-10-09.13 |
| 3 | `job_payloads/snapshot_publish.json` | 설명: busy → 지연 재큐잉(F4) |
| 4 | DB `0013` | 데이터만(S2·D16-1 할인 라벨). downgrade = 되돌림 없음 |

### 마이그레이션·검증

- .11·.12 DB: worker 정지 → `cd backend && uv run alembic upgrade head`(0012·0013) → `uv run python -m app.snapshot_view backfill` → 다시
  backfill(`snapshots=[]`) → worker 시작(`docs/runbook.md` §11 '업그레이드 뒤 backfill 절차').
- 왕복·시나리오: `tests/contracts/test_r3h_migrations.py`(SQLite·임베디드 Postgres 16 — .11 DB 좁은 서랍 + 일부만 쓴 기본 시나리오 단위 →
  head → backfill, 표식 없는 행 단위, .12 DB → 0013 → backfill·할인 라벨, 발행 뒤 단지 불변, autogenerate diff 0),
  `test_r3g_migrations.py`(0012 왕복·중단 재개 — 기대값 D16-2 로).
- `CONTRACT_VERSION`·`info.version` = `2026-10-09.13`. 생성물(`openapi.bundled.yaml`, `contracts_gen.py`) 재생성(`gen_contracts.py --check`).
- D14-5 측정: 아래 '측정' 절.

### 측정

- **D14-5**(`tests/api/test_r3f_perf_publish.py` — devseed 16 + 합성 1,000 단지 × 시나리오 5): 이월 복사를 한 트랜잭션으로 하던 중간
  측정 3회 중 1회가 이월 복사 잠금 1.06s·API 쓰기 응답 최대 **1.75s**(기준 1s 초과)였다 → `snapshot.publish` 이월 복사를 단계별 짧은
  트랜잭션(사다리·주장 → 비교군 → 시나리오 하나씩, 다시 돌면 이어 채움 — `persist.carry_incomplete`)으로 나눴다(잡 stats `carry_lock_s` =
  단계 중 최대, `carry_steps`). 그 뒤에도 전체 pytest 안에서 API 쓰기 최대 1.75s 가 한 번 더 나왔다 — 같은 측정에 GC 멈춤 시간을
  더해 보니 **API 쓰기 최대 지연 = 순환 GC 전체 수집 멈춤**(0.43s ↔ 0.435s 등, 시험은 잡·API 를 한 프로세스 두 스레드로 돈다)이라
  발행 계산·쓰기·전환 동안 GC 를 멈췄다(`publish_revision` — 쓰기 묶음 트랜잭션 안에서 GC 가 돌면 잠금도 그만큼 길어진다). 잡 끝 기록은
  UPDATE 한 문장(읽고 쓰면 부하에서 BUSY_SNAPSHOT 'database is locked' 이 한 번 났다). 그래도 전체 pytest 안에서 2.32s 가 한 번
  나와(GC 0, 잠금 최대 0.03s) 느린 쓰기 시각·WAL 크기를 기록해 보니 계산 구간에서 WAL 변화 없이 생긴 **같은 프로세스 스레드의 GIL
  지연**이었다 → 시험의 API 쓰기를 **다른 프로세스**(`tests/api/_perf_writer.py` — 운영처럼 api·worker 분리)로 바꿨다. 최종 코드로
  `python scripts/tasks.py regress` 와 동시 2회: 잡 17.7s·17.7s, API 쓰기 응답 최대 **0.484s·0.082s**(p50 0.004s, 321·322건), 저장본
  묶음 쓰기 잠금 최대 0.033·0.022s, 이월 복사 단계 잠금 최대 0.094·0.061s, 전환 0.002·0.003s, 잡 쪽 GC 멈춤 최대 0.019·0.021s. 저장본
  5,439행·12.2MB. 출처 서랍 76,909개(.12 의 112,380 → 줄었다: 보고서 점수 prov 가 API 서랍 id 와 같아져 겹친다 — m6).
- **CEO 검증에서 전체 스위트 1회 실패 후속**: 시험이 실패 때 측정값 전부(잡·API 최대/p50·느린 요청의 SQL 실행(잠금 대기)/COMMIT
  나눔·잠금·GC·WAL·스레드·메모리·DB 경로)를 assert 메시지와 파일(`PUBLISH_PERF_OUT`, 없으면 임시 폴더 `sa-perf-last.json`)로 남긴다.
  디스크 부하(fsync 큰 쓰기) + 전체 pytest + regress 연속 실행에서 재현: API 쓰기 최대 5.27·1.06·1.20s, **지연은 전부 COMMIT**(SQL 실행
  ≤0.2s) — 발행이 WAL 에 쓴 수십 MB 를 API 커밋이 자동 체크포인트(WAL→DB 복사·fsync)로 떠안았다(API 쪽 자동 체크포인트를 끄면 같은
  부하에서 COMMIT 최대 0.0~0.16s). 수정: SQLite 개발 모드 API 프로세스(`create_app` lifespan)는 요청 커밋이 체크포인트하지 않고
  (`wal_autocheckpoint=0`) 배경 스레드가 1초마다 PASSIVE 체크포인트(`core.db.sqlite_api_checkpointer` — 쓰기 잠금 없음, Postgres 는
  해당 없음). 측정 쓰기 프로세스 로그는 WARNING(요청 로그의 디스크 쓰기가 측정에 섞였다). 수정 뒤 디스크 부하 4회 API 최대 0.17~0.26s.
  최종 코드 전체 pytest 2회(각각 regress 를 처음부터 끝까지 연속 실행하며, junit 실패 0): 3763 passed·3763 passed, D14-5 잡 17.9·18.7s,
  API 쓰기 최대 0.205·0.257s(p50 0.004s), COMMIT 최대 0.000·0.001s, 묶음 쓰기 잠금 0.023·0.025s. 기준(30s·1s)은 그대로.

## 2026-10-09.12

R3 7차 리뷰(`docs/design/wp/R3_REVIEW7.md`) 후속 — CEO 결정 D15(`docs/design/DECISIONS.md`)와 R3g 배정(`docs/design/wp/R3G_FIX.md` CORE5).
계약 소유자 = R3g CORE5(브랜치 `wp/r3g-core5`). 마이그레이션 `0012`(`0012_r3g.py`: 새 테이블 `snapshot_view_unit`(완료 표식) +
`snapshot_view.shape_version` + `snapshot.publish_lease`). 필드 삭제 없음, **새 응답 필드 1**(`CatalystCreated.job_id`), 새 잡 payload 필드 1
(`snapshot.publish` `follow_up`), **새 오류 code 3**(`checked_at_format`·`checked_at_future`·`checked_at_before_source` — FE6 요청·CEO 승인,
F14), 잡 stats `publish_job_id`(F15). 응답 상태 코드 변경 없음(503 `materialize_pending` 이 나는 경우가 늘었다 — F5·F6·F7).

**프론트(FE6)가 맞출 것** — 아래 'FE 차이' 표 하나만 보면 된다. `frontend/src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 는 이 브랜치에서 다시
만들지 않았다(frontend/** = FE6 소유) — 머지 뒤 `npm ci` → `npm run gen:api`·`gen:msw`.

### FE 차이(FE6 — 화면이 맞출 것)

| # | 대상 | .11 | .12 | 결정·리뷰 |
| --- | --- | --- | --- | --- |
| F1 | `rd_` 출처 서랍(`GET /provenance/rd_<id>?snapshot_id=`) | 발행 리비전 저장본에 접수 근거 `rd_`(접수 행 `raw_document_id`)가 없어 404 — 화면이 `rd_` 만 snapshot_id 를 뺐다 | 저장본이 모든 본문의 `raw_document_id`(접수 행·경쟁률 행 등)를 `rd_<id>` 서랍으로 저장 → **`rd_` 도 늘 snapshot_id 를 넘긴다**(`provenanceSnapshot` 의 `rd_` 예외 제거). `data_freshness`·생활권 세대수의 `rd_` prov 도 같다 | D15-2 · m7 |
| F2 | 시나리오 A–D 화면의 출처 서랍 | 시나리오 patch 행에만 있는 prov(점수 실행 KPI `st_<run>` 등)는 발행 리비전 서랍 404 | 모든 시나리오·모든 kind 본문의 prov 가 저장본에 있다 → 200(발행 순간 값). 화면 변경 없음(이미 snapshot_id 를 넘긴다) | D15-2 · M1 |
| F3 | `POST /catalysts` 201 응답 | `{catalyst, job}` | **새 필드 `job_id`**(integer\|null, 필수 — `job.id`, 같은 URL·스냅샷 없음이면 null). 발행을 일으키는 쓰기 응답의 공통 이름 — 화면은 `job_id` 를 감시 | D15-6 · m16 |
| F4 | `PATCH /catalysts/{id}` 202 `job_id` | 가장 새 리비전이 발행 전(판정 중·발행 계산 중)이면 `job`·`job_id` **null**(변경이 발행 계산에서 빠질 수 있었다) | 연결이 바뀌면 **늘 job_id**: 가장 새 리비전이 발행됨 → 지금처럼 `snapshot.publish`(`carry_from_snapshot_id`); 발행 전 → **후속 발행 잡** `snapshot.publish` payload `{snapshot_id: 그 리비전, follow_up: true}`. 후속 잡의 끝: (a) 그 리비전 발행 계산이 이 쓰기를 읽었으면 그 발행이 잡을 `done`(stats `included_in_snapshot_id`)으로 닫는다, (b) 못 읽었으면 잡이 새 리비전을 발행(stats `published` true·`snapshot_id`), (c) 판정 중이면 `done` + stats `deferred_to`(그 리비전 발행 때 들어간다). 화면: 잡이 done 이면 regions·스냅샷 목록 무효화(지금과 같은 감시) | D15-6 · M5 |
| F5 | 발행 리비전 GET 503 `materialize_pending` | '그 kind 행이 하나라도 있으면 완료' — backfill 이 중간에 멈추면 나머지 시나리오·키가 **영구 404**, `POST /reports` 422 | (리비전, kind, 시나리오) **완료 표식**으로 판단: 표식 없음·미완·행 수 모자람 = 503 + `Retry-After`(backfill 이 그 단위의 빠진 행만 채우면 200). 그 kind 의 다른 시나리오는 완료인데 이 시나리오 표식이 없을 때만 404(발행 뒤 만든 시나리오). 대상 엔드포인트 목록은 .11 F12 그대로 | D15-3 · M2 |
| F6 | `GET /provenance/{id}`(snapshot_id 생략) | 그 지역 최신 발행 리비전 서랍 저장본이 없으면 건너뛰고 실시간 **200** | 어느 지역에서도 못 찾고 저장본이 미완인 지역이 있으면 **503** `materialize_pending`(발행 순간이 아닌 값을 내보내지 않는다). 화면은 늘 snapshot_id 를 넘기므로 영향 적음 | m6 |
| F7 | `POST /reports` | 기본 시나리오(생략)·비교 스냅샷의 저장본 준비를 보지 않아 202 뒤 잡 실패 | 대상 리비전의 그 시나리오(생략 = 기본) `report`·`report_diff`, 비교 리비전의 `report` 저장본이 미완이면 **503** `materialize_pending`(202 전에) | m10 |
| F8 | `POST /ops/human-checks` `checked_at` | 소문자 `t`/`z` 는 형식 통과 뒤 날짜를 UTC 로 잘랐다. `0001-01-01T00:00:00+14:00` 은 201 → 이후 지역 목록·CSV 404/500 | `T`·`Z` 대소문자 무관(같은 KST 날짜). **2000-01-01(KST) 이전·지금+10분 넘는 미래·overflow → 422**(`field_errors[0].loc = ["body","checked_at"]`) | D15-7 · M6 · m2 |
| F9 | 할인 표시(`price.discount`·`discount_applied`) | 줄 전체 조건 검사(금지 낱말) — '(1~3층에 한함)' 다음 줄·'(일부 세대)'·'(신혼부부)'·'예정'·범위 하한·'0원, 경품 1천만원' 등이 '확인됨'(차감) | **허용 목록**: 줄 전체가 `{타입} {분양가\|공급금액} 할인 {금액}원` 꼴이고 다음 줄이 조건 표지로 시작하지 않을 때만 '확인됨'(차감). 그 밖은 '추정'(표시만, `discount_applied` false). 0원·경품·지원 등 할인 아닌 금액은 할인 Fact 없음. 화면 규칙 그대로(값만 바뀜) | D15-1 · K1 |
| F10 | 보고서 HTML §12(사용자 시나리오) | 비교 기준에 그 시나리오가 없으면 12-1 순위표·TOP 5 진입·이탈을 기본 시나리오 순위와 섞음('12위 → 1위') | 같은 시나리오끼리만. 없으면 12-1 자리에 사유 문단('비교 기준 리비전에 이 시나리오가 없어 12-1 순위 비교와 TOP 5 진입·이탈은 생략했다'), 후보 건수 비교는 그대로 | D15-5 · M4 |
| F11 | 보고서 날짜 | 접수 확인일·실패 출처·참고 링크·판정 호출·변경 날짜 = 문자열 앞 10자(UTC 일 수 있음) | 모두 KST 날짜(`core.time.kst_day`) | D15-7 · m3 |
| F12 | `snapshot.publish` 잡 실패 문구 | 같은 리비전 발행 둘이 겹치면 한쪽 정리 DELETE 가 다른 쪽 저장본을 지워 published + 0행 | 리비전마다 발행 하나(single-flight). 겹친 쪽은 아무것도 지우지 않고 failed `error_text` = `publish_in_progress: …`(화면: 일반 잡 실패 안내 — 먼저 돈 잡이 발행한다) | D15-6 · m1 |
| F14 | `POST /ops/human-checks` checked_at **422 code** | 모두 `validation_error`(문구로만 구분) | **code 로 구분**(FE6 요청·CEO 승인): `checked_at_format` = 형식(스키마 `format: date-time` 포함)·KST 2000-01-01 이전·overflow, `checked_at_future` = 서버 지금 + 10분 넘는 미래, `checked_at_before_source` = 그 의미 필드에 확인일(KST)보다 뒤에 관측된 공식 공고가 **다른 값**으로 이미 있음(D13-2·D14-6). 셋 다 `field_errors[0].loc = ["body","checked_at"]`. checked_at 과 다른 필드가 함께 틀리거나 다른 필드만 틀리면 그대로 `validation_error` | D15-7 · FE6 요청 |
| F15 | 발행을 일으키는 잡의 **`publish_job_id`** + 쓰기 응답 `job_id` 의미 | 잡마다 달랐다(rejudge 는 발행 잡 id 를 남기지 않음) | 잡 stats `publish_job_id` = 발행을 하는(한) 잡: `rejudge` → 판정 뒤 등록한 `snapshot.publish` 잡, `snapshot.publish`(후속 포함) → 그 잡 자신(미룸이면 null + `deferred_to`, 다른 발행에 포함돼 닫힌 후속 잡 → 그 발행 잡), `region.expand`·`region.bootstrap`·`collect.daily` 이월·`collect.weekly` 마감(그 자리 발행) → 그 잡 자신, 발행이 예외로 실패해 재시도를 남겼으면 → 재시도 잡(`publish_retry_job_id` 와 같음). 화면: 응답 `job_id` 잡이 done 이면 `stats.publish_job_id` 가 자기와 다를 때 그 잡을 이어 감시, 같거나 `published` 가 있으면 끝. 쓰기 응답 `job_id`: `PATCH /catalysts` = snapshot.publish(carry 또는 follow_up) · `POST /catalysts` = rejudge · `PUT /regions/{id}/living-areas` = rejudge · `PATCH /regions/{id}`(선택 변경) = region.expand · `POST /ops/human-checks` = rejudge(= `rejudge_job_id`) | D15-6 · FE6 요청 |
| F13 | 500 `stored_view_mismatch` | 저장본 행의 계약 버전 문자열 ≠ 지금 계약이면 500(모양이 같은 계약 변경에도) | **저장 모양 버전**(정수) 또는 sha256 이 다를 때만 500. 계약 버전만 바뀐 경우 200 | D15-3 · m9 |

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.11) | 이후(.12) | 결정·리뷰 |
| --- | --- | --- | --- | --- |
| S1 | 저장본 완결성 | kind 행 하나라도 있으면 완료(`kind_ready`), backfill 은 '빠진 kind' 만 | `snapshot_view_unit` 완료 표식 = (리비전, kind, 시나리오) 단위, **그 단위의 마지막 쓰기와 같은 트랜잭션**에 `done`·`rows`. backfill 은 미완 단위(표식 없음·done=false·실제 행 < rows)만, **이미 있는 행은 그대로 두고(발행 순간 바이트) 빠진 키만** 넣는다(본문 통째 — patch 없음). 새 행이 출처 서랍에 없는 prov 를 가리키면 서랍 단위도 다시 쓴다(이미 있던 서랍 본문은 그대로). 리비전마다 따로 실패(`backfill()` 결과 `failed`) | D15-3 · M2 · m11 |
| S2 | 저장본 읽기 검증 | `contract_version` = 지금 계약 | `shape_version`(=`app.snapshot_view.SHAPE_VERSION`, 지금 1) + sha256. `contract_version` 은 기록만 | D15-3 · m9 |
| S3 | 출처 서랍 수집 범위 | 기본 시나리오 행·`"prov":"…"` 모양만(report·report_diff 제외) | 출처 서랍 자신을 뺀 **모든 kind·모든 시나리오**, patch 행 `"prov":{"$v":"…"}`, `raw_document_id` → `rd_<id>` | D15-2 · M1 · m7 |
| S4 | 시나리오 patch 행 | 같음 판정이 `!=` — `1`·`1.0`·`true` 를 같다고 보고 기본 시나리오 값으로 되살림(바이트 다름) | 저장 바이트가 같을 때만 같다(값이 같으면 직렬화 비교) | m8 |
| S5 | 발행 single-flight·정리 | 정리 DELETE 상태 조건 없음 — 두 발행이 겹치면 published 0행 → backfill 이 지금 값으로 재계산 | `snapshot.publish_lease` 조건부 UPDATE(보유자 = 잡 id — 그 잡이 running 이 아니거나 15분 지나면 넘겨받음). 정리 DELETE 는 `status != 'published'` 조건, 전환 UPDATE 는 임대 보유 조건. 전환 트랜잭션은 쓰기 잠금부터(SQLite BUSY_SNAPSHOT 방지) | D15-6 · m1 |
| S6 | 발행 계산 중 들어온 변경 | `republish` 가 발행 전 리비전이면 아무것도 안 함 → 계산이 이미 읽었으면 변경 유실 | 후속 발행 잡(F4). 계산 읽기 트랜잭션이 본 후속 잡 = 전환 트랜잭션에서 `done`(포함됨), 못 본 잡 = 남아 이어 발행. 잡 stats `followups_included` | D15-6 · M5 |
| S7 | 발행 실패 재시도 | bootstrap 만 재시도 잡 | daily 이월·주간 마감·지역 확장·bootstrap 모두 발행 예외 → `snapshot.publish` 재시도 잡(stats `publish_retry_job_id`) | D15-6 · m13 |
| S8 | 이월 판단 '판정됨' | 단지를 포함한 마지막 성공 판정 잡이면 어느 리비전이든 | 그 판정이 **복사 원본(prev) 리비전에 들어 있을 때만**(판정을 쓴 리비전 = prev 또는 prev 이전 발행 리비전 — 잡 stats `pipeline.snapshot_id`/`snapshot_id`). 시나리오 지정 rejudge 는 그 시나리오만 — 단지 기준 시각 = prev 점수 실행 시나리오 중 가장 이른 것 | D15-4 · M3 · m14 |
| S9 | 시각 파싱 | 여러 곳에서 `fromisoformat`·앞 10자 | `core.time.parse_datetime` 하나(T·Z 대소문자 무관, 예외 없음, overflow → None) + `kst_date`·`kst_day`·`kst_day_after`. 사람 확인 범위 = `checked_at_range_error`(2000-01-01 KST ~ 지금+10분) | D15-7 · M6 · m2 |
| S10 | redact | — | 이중 인코딩 JSON·소문자/변형 PEM(EC·OPENSSH·ENCRYPTED·PGP·CRLF·`\n` 이스케이프·END 없음)·공백 낀 키 이름('Secret Key:')·전각 콜론·여러 낱말 값·`privateKey` | m5 |
| S11 | 보고서 출처 누락 집계 | 보고서 저장본의 '출처 누락' 은 잡 stats `missing_provenance` 에 안 셈 | 셈(저장본 계산 중이면 ENV 와 무관하게 라벨 + 건수) | m12 |
| S12 | 보고서 CLI `--compare` | 순서·지역·발행 미검사 | API 와 같은 규칙(`reports.data.compare_problem`) — 어긋나면 exit 6 | m15 |

### 스키마 변경

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `catalyst.json` `CatalystCreated` | `job_id`(integer\|null, **필수**) 추가, `job` 설명 바로잡음(분류 rejudge 잡). 예시 `catalyst_created.json` 갱신 |
| 2 | `job_payloads/snapshot_publish.json` | `follow_up`(boolean, 선택) — 후속 발행 잡(F4). 설명에 single-flight(`publish_in_progress`) |
| 3 | `openapi.yaml` | `info.version` 2026-10-09.12. 경로·응답 코드 변경 없음. createHumanCheck 설명에 checked_at 422 code(F14) |
| 3a | `error.json` code enum | `checked_at_format`·`checked_at_future`·`checked_at_before_source` 추가(F14) |
| 4 | DB `0012` | 새 테이블 `snapshot_view_unit`(snapshot_id FK, kind CHECK = snapshot_view 와 같음, scenario, shape_version, rows, done; 유일 (snapshot_id, kind, scenario)) · `snapshot_view.shape_version`(INTEGER NOT NULL 기본 1) · `snapshot.publish_lease`(String 80, NULL). 데이터: 발행 리비전의 기존 (kind, 시나리오) 행 묶음 = done 표식(rows = 행 수), 그 리비전 시나리오(행·점수 실행) × kind 중 행 없는 단위 = done=false 표식(backfill 이 채운다). downgrade = 표·열 삭제 |

### 마이그레이션·검증

- 0011 DB: `cd backend && uv run alembic upgrade head`(0012) → `uv run python -m app.snapshot_view backfill`(또는 worker 재시작) — 미완 단위만 채운다.
  0012 이전에 backfill 이 중간에 멈춰 행이 일부만 있는 단위는 마이그레이션이 찾아 미완으로 표식한다(단지 상세·시장 = 시나리오 사이 최대 행 수,
  출처 서랍 = 색인 묶음 수 + 1). 한 시나리오의 단일 행 kind(대시보드 등) 전체가 빠진 경우는 행·점수 실행 시나리오 × kind 로 찾는다.
- 왕복: SQLite·Postgres 16(pgserver), devseed 픽스처(단지 16·시나리오 5) — `tests/contracts/test_r3g_migrations.py`(head → 0011 → head, 표식 재구성,
  backfill 중단·재개), `tests/contracts/test_r3f_migrations.py`(0009 → head → backfill → 0010 → head), autogenerate diff 0.
- `CONTRACT_VERSION`·`info.version` = `2026-10-09.12`. 생성물(`openapi.bundled.yaml`, `contracts_gen.py`) 재생성(`gen_contracts.py --check` 일치).
- **D14-5 측정**(`tests/api/test_r3f_perf_publish.py::test_d14_5_publish_job_1000x5_under_30s_and_api_writes_wait_under_1s` — devseed 16 + 합성
  1,000 단지 × 시나리오 5, 측정 DB 는 pytest basetemp 밖 전용 임시 폴더): `python scripts/tasks.py regress` 동시 실행(부하) 2회 = 잡 22.2s·21.9s,
  API 쓰기 응답 최대 0.72s·0.73s, 저장본 묶음 쓰기 잠금 최대 0.05s·0.02s, 이월 복사 잠금 0.33s·0.34s, 전환 0.002s, 저장본 5,419행·12.0MB,
  출처 서랍 112,380개(.11 의 71,600 + 시나리오 patch 행·`rd_`·report 의 prov — D15-2). 같은 시점 main(.11) 은 부하 없이 16.8s.
  비용 대책: patch 바이트 검증은 pickle 구조 비교(기본 시나리오 쪽 캐시), `kst_date` 캐시, `rd_` 서랍 일괄 조회, 묶음 0.5MB, 저장본 쓰기·전환
  연결의 WAL 자동 체크포인트 끔(커밋 안 체크포인트가 부하에서 쓰기 잠금 1.2~3.0s 를 만들었다 → 끝나고 PASSIVE), 이월 비교군 INSERT…SELECT.
  잡 stats 에 `carry_lock_s`(이월 복사 트랜잭션 시간) 추가. 동시 pytest 흔들림: 회귀 러너의 pytest 는 실행 전용 `--basetemp`(scripts/tasks.py),
  성능 측정 DB 는 basetemp 밖 — 기본 `pytest-of-<user>` 번호 폴더를 다른 회차와 같이 쓰지 않는다.

## 2026-10-09.11

R3 6차 리뷰(`docs/design/wp/R3_REVIEW6.md`) 후속 — CEO 결정 D14(`docs/design/DECISIONS.md`)와 R3f 배정(`docs/design/wp/R3F_FIX.md` CORE4).
계약 소유자 = R3f CORE4(브랜치 `wp/r3f-core4`). 마이그레이션 `0011`(`0011_r3f.py`: `snapshot_view.contract_version` 열 + kind CHECK 에
`provenance`·`claims`) + **`0010` 수정**(앱 코드 import·materialize 제거 — D14-9). 필드 삭제 없음. 응답 상태 코드 변경 3(202), 새 오류 code 3.

**프론트(FE5)가 맞출 것** — 아래 'FE 차이' 표 하나만 보면 된다. `frontend/src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 는 이 브랜치에서 다시
만들지 않았다(frontend/** = FE5 소유) — 머지 뒤 `npm ci` → `npm run gen:api`·`gen:msw`.

### FE 차이(FE5 — 화면이 맞출 것)

| # | 대상 | .10 | .11 | 결정·리뷰 |
| --- | --- | --- | --- | --- |
| F1 | `GET /provenance/{prov_id}` **쿼리** | 없음 | `?snapshot_id=<보고 있는 리비전 id>`(integer, 선택). 발행 리비전이면 **저장본**(발행 순간의 출처 행·chosen·충돌·강등 — 이후 새 공고·재수집·강등·PATCH /claims 에도 같은 바이트), 발행 전(building·ready) 리비전이면 실시간. 그 발행 리비전 화면에 없던 출처 = **404** `not_found`, 저장본 생성 전 = **503** `materialize_pending`. 생략하면 지역마다 최신 발행 리비전 저장본에서 찾고 어디에도 없으면 실시간 — **화면은 늘 넘긴다**(G3 ProvenanceTab·충돌 출처 클릭 포함) | D14-1 · C2 |
| F2 | `GET /snapshots/{sid}/claims` | 늘 지금 값(강등 상태·대기 잡) | 발행 리비전 = 발행 순간 저장한 목록(`demotion`·`pending_job_id` 포함 — 발행 리비전에는 남은 contradicted 가 없으므로 대기 잡도 없다). `?status=` 는 저장본에 적용. 발행 전 리비전만 지금 값. 저장본 생성 전 503 | D14-1 · m1 |
| F3 | `PATCH /catalysts/{id}` **상태** | 200, `job` 늘 null(요청 안에서 새 리비전 발행) | **202**. `job` = `snapshot.publish` 잡(연결이 바뀐 경우 — payload `{snapshot_id: 새 리비전, carry_from_snapshot_id: 바탕}`), 그대로면 null. **새 필드 `job_id`**(= job.id 또는 null). 잡이 끝날 때까지 이전 발행 리비전이 기본 화면 → 화면은 `job_id` 를 감시하고 끝나면 regions·스냅샷 목록을 무효화 | D14-5 · N-M3 |
| F4 | `PUT /regions/{id}/living-areas` **상태** | 200 | **202**(본문 같음 — `job_id` = rejudge 잡). 잡이 새 리비전을 판정·발행할 때까지 이전 발행 리비전 | D14-5 |
| F5 | `PATCH /regions/{id}` **상태** | 200 | 선택이 바뀌면 **202**(본문 같음 — `job_id` = region.expand), 이름만 바꾸면 **200**(change_event·job_id null, 그대로) | D14-5 |
| F6 | `POST /ops/human-checks` 응답 | `rejudge_job_id` | **201 그대로**(자원을 만드는 POST — e2e·화면 흐름 유지) + **새 필드 `job_id`**(= rejudge_job_id, 발행을 부르는 쓰기 응답의 공통 이름) | D14-5 |
| F7 | `POST /ops/human-checks` **`checked_at` 형식** | 문자열 10자 이상(`zzzzzzzzzz`·미래 날짜 201) | **시간대가 붙은 RFC3339**(`format: date-time` — 예 `2026-10-09T10:20:00+09:00`, `…Z` 도 됨). 날짜만·시간대 없음·형식 오류 → 422(`field_errors[0].loc = ["body","checked_at"]`). 서버 지금보다 **10분 넘게 미래** → 422. 화면 입력은 `datetime-local` + 시간대(또는 `toISOString()`) | D14-6 · N-M4 |
| F8 | `POST /ops/human-checks` 이른 확인일 422 | 그 의미 필드에 확인일보다 뒤에 관측된 공식 공고가 있으면 422 | 그 공고 값이 사람 확인 값과 **다를 때만** 422(detail `확인일 <KST날짜>(KST) 은 이미 수집된 공식 공고(관측 <일>, 다른 값)보다 이르다 …`). **같은 값이면 201**(재검토 항목 없음). 날짜 비교는 KST(`2026-10-09T20:00:00Z` = KST 10-10) | D14-6 · m11 · m12 |
| F9 | 체크리스트 `사람 확인 재검토: <필드>` | 같은 필드를 다시 사람 확인해도 open | 같은 (단지, 의미 필드)를 다시 사람 확인하면 **자동 done**(closed_by auto) | D14-6 · m13 |
| F10 | `POST /reports` | 사용자 시나리오가 대상 리비전에 없어도 202 → 잡 실패 | 대상 리비전에 그 시나리오 저장본이 없으면(그 리비전 발행 뒤 만든 시나리오) **422 `scenario_not_in_revision`**(`field_errors[0].loc = ["body","scenario_id"]` — 화면: '그 시나리오는 시나리오 실행이 만든 리비전에서 보고서를 만든다' 안내 + 대상 리비전 다시 고르기). 없는 시나리오 id = 404. 비교 스냅샷이 **대상과 같거나 더 새 리비전**이면 422(`compare_snapshot_id`). 저장본 생성 전 503 | D14-3 · N-M1 · m5 |
| F11 | 보고서 HTML §12 | 비교 기준에 시나리오가 없으면 잡 실패 | 보고서는 만들고 12-2 delta 표 자리에 '비교 기준에 이 시나리오 없음'(§12 후보 건수 비교는 그대로). 머리말 '생성' = 보고서를 만든 지금(`<time class="generated-at">`) | D14-3 · m4 |
| F12 | 새 오류 code | — | `scenario_not_in_revision`(422, F10) · `stored_view_mismatch`(500 — 발행 리비전 저장본 sha256·계약 버전 불일치, 화면은 일반 서버 오류 안내) · `materialize_pending`(503 + `Retry-After` 초 — 발행 리비전 저장본 생성 전, 화면은 '준비 중 — 잠시 뒤 다시' + 자동 재시도). 발행 리비전을 읽는 GET 전부(대시보드·단지 목록·CSV·단지 상세·출처 서랍·비교·민감도·시장·변경·주장)와 `POST /reports` 에 503 이 문서화됐다 | D14-3 · D14-4 · D14-9 |
| F13 | 할인 표시(`price.discount`·`discount_applied`) | 금액 앞만 조건 검사 — '…(1~3층)'·'잔금 완납 시'·'특별공급 당첨자 한정'·'최대' 할인도 '확인됨'으로 구매가에서 뺌 | **줄 전체**에 조건이 없을 때만 '확인됨'(차감, `discount_applied` true). 조건부 할인은 '추정'(표시만, `discount_applied` false). '할인 없음/미적용' 줄·취득세·중도금 이자·발코니·옵션 **지원**은 할인 Fact 를 만들지 않는다. 화면 규칙 그대로(`discount_applied` 만 본다) — 값이 바뀔 뿐 | D14-2 · C1 |
| F14 | 예시 `examples/market.json` | la_2·la_3 `n_trades` 0건 '재가공'/'비공식'(근거 '건수 미상'과 모순) | `v: null`, '확인 불가'(사유 '건수 미상…'·'실거래 원자료 미확보…') — MSW 예시만 | m8 |
| F15 | `GET /snapshots/{sid}/*` 발행 리비전 | 저장본(D13-1) | 같음. 단 저장본이 아직 없으면 500 → **503 `materialize_pending`** | D14-9 |

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.10) | 이후(.11) | 결정·리뷰 |
| --- | --- | --- | --- | --- |
| S1 | 출처 서랍·주장 목록 | 발행 리비전도 실시간(현재 출처 행·chosen·충돌·오버레이) — 발행 뒤 `fp_11 chosen True→False`, 입주물량 재수집이 출처 행을 지우면 404 | 발행 순간 **저장본**(kind `provenance` = 그 리비전 응답이 가리키는 출처 id 전부 + 그 서랍의 충돌 출처, 해시 묶음; kind `claims`) | D14-1 · C2 · m1 |
| S2 | 저장본 행 | sha256 만 저장, 읽을 때 검증 없음 | `contract_version`·`sha256` 를 **읽을 때 검증** — 다르면 500 `stored_view_mismatch` + 오류 로그(조용히 내보내지 않음). 시나리오 사이 같은 부분은 기본 시나리오 행 + 바뀐 부분 행으로 저장(읽을 때 같은 바이트로 되살림 — 1000 단지 저장본 26MB → 7.6MB) | D14-4 · N-M2 |
| S3 | 발행(materialize) | publish 트랜잭션 안에서 계산·쓰기 — 호재 PATCH 요청 안 발행, 1016 단지 × 5: 28.8s 동안 쓰기 잠금 | **worker 잡에서만**: 계산(읽기 전용 세션 — SQLite WAL 읽기 트랜잭션·Postgres REPEATABLE READ, 리비전은 메모리에서만 '발행됨', flush 금지) → 저장본 **나눠 쓰기**(묶음당 ≤2MB 짧은 트랜잭션) → 남은 contradicted 0 재확인 + `UPDATE … SET status='published' WHERE status='ready'` **짧은 전환**. 끝날 때까지 이전 발행 리비전이 기본. 잡 stats = `rows·bytes·missing_provenance·provenance_ids·compute_s·timing_s·write_chunks·write_max_lock_s·write_total_s·flip_s·total_s`. 측정 1016 단지 × 시나리오 5 = 아래 '검증' | D14-5 · N-M3 |
| S4 | 출처 누락(T13) | 발행 저장본 '확인 불가(출처 누락)'(통계 없음) | 같음 + 잡 stats `missing_provenance` 건수. 실시간 경로(발행 전 리비전) dev 500 · prod 라벨 그대로 | D14-8 |
| S5 | 0010 이전 발행분·새 종류 | 0010 마이그레이션이 앱 코드로 materialize | 마이그레이션은 테이블만. 채우기 = **멱등 backfill**(`cd backend && uv run python -m app.snapshot_view backfill` · worker 시작 때 자동 · `python scripts/tasks.py backfill`) — 빠진 종류만 계산·나눠 쓰기, 행 단위 사람 확인(.9) → 의미 묶음 이전(m14). 그 사이 GET 503 | D14-9 · m2 · m14 |
| S6 | 사용자 시나리오 보고서 | 비교 기준(revision_of)에 그 시나리오가 없으면 잡 실패, diff 는 code 로 시나리오를 찾음(사용자 시나리오 code NULL) | F10·F11. diff·§12 는 시나리오 **id** 로. §12 후보 건수는 비교 기준에 그 시나리오가 없으면 기본 시나리오 입력으로. CLI `--scenario` 도 같은 규칙(없으면 exit 4 `scenario_not_in_revision`) | D14-3 · N-M1 |
| S7 | 이월·재판정 판단 | 리비전 전체의 마지막 점수 실행 하나 기준 — 단지 A rejudge 실패 뒤 다른 단지만 판정한 실행이 성공하면 A 가 가려짐 | **단지 단위**: 단지마다 그 단지를 판정한 마지막 성공 잡(rejudge·region.bootstrap·region.expand) 끝 시각(기록 없으면 그 스냅샷 첫 점수 실행) 뒤 그 단지·지역 단위 change_event 또는 그 단지를 포함한 rejudge 실패가 있으면 재판정 | D14-7 · N-M5 |
| S8 | 사람 확인 날짜 | `checked_at[:10]` 문자열 비교 | 공용 `core.time.kst_date`·`kst_day` 하나(KST 달력 날짜 — resolver·demotion 전부 + 접수 행 `checked_at`: 표시 접수 행 고르기·상황 요건 근거·목록 CSV 확인일·보고서 Fact 확인일). 옛 날짜만 행도 읽는다 | D14-6 · m12 |
| S9 | 할인 줄 | 금액 앞 조건만 | F13(조건 토큰: 층·동·호·라인·타입 외·'~시'·한정·최대·조건·선착순·특별공급·잔금·완납·기간·까지·※·단·각주) | D14-2 · C1 |
| S10 | 정규화·보안 minor | — | redact: PEM 개인키 본문 전체·JSON `"private_key": "…"` 값 전체(m9). 홈페이지 URL: UTS46 무시 문자 전부(U+2064·U+E0100~E01EF·U+1BCA0~1BCA3 등, m10). 같은 블록 병합 잔여 공고의 입주 예정월도 원 단지 후보(m16 — 일정·당첨일 등은 D11-4 대로 버림). 모호 법정동이 기존 `legal_dong_code` 를 지우지 않음(m17). 의미 키 규칙 한 함수(m18) | m9 · m10 · m16 · m17 · m18 |
| S11 | worker·운영 | SQLite 같은 트랜잭션 읽기 뒤 rejudge 합치기 'database is locked'(BUSY_SNAPSHOT) | 읽기만 한 트랜잭션이면 새 트랜잭션에서 쓰기 잠금부터 다시(쓴 트랜잭션은 예외 그대로, m15). region.bootstrap 저장본 실패가 지역을 failed 로 만들지 않음 — 지역 ready + `snapshot.publish` 재시도 잡(stats `publish_retry_job_id`, m19). devseed `--reset` = 실제 테이블 반사 삭제 + alembic head 스탬프(m3) | m15 · m19 · m3 |
| S12 | 보고서 경로 | `x/C:outside.txt` 가 REPORT_DIR 밖을 가리킬 수 있음 | 드라이브·콜론 조각 거부 + 결과가 REPORT_DIR 안인지 확인(m6). diff 입력 이름 = 그 리비전 지역 단지만(m7) | m6 · m7 |

### 스키마 변경

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `error.json` code enum | `scenario_not_in_revision`·`stored_view_mismatch`·`materialize_pending` 추가 |
| 2 | `human_check.json` | `HumanCheckCreate.checked_at` `format: date-time`(설명: 시간대 필수·10분 넘는 미래 422). `HumanCheck.job_id`(integer\|null, 선택) 추가 — 예시 갱신 |
| 3 | `catalyst.json` `CatalystUpdated` | `job_id`(integer\|null, **필수**) 추가, `job` 설명(snapshot.publish 잡). 예시 `catalyst_updated.json` 갱신 |
| 4 | `job_payloads/snapshot_publish.json` | `carry_from_snapshot_id`(integer\|null, 선택) — 판정 없는 리비전 값(호재 연결) 발행 |
| 5 | `openapi.yaml` | getProvenance `snapshot_id` 쿼리·설명. updateCatalyst 200→**202**, updateLivingAreas 200→**202**, updateRegion **202**(선택 변경) + 200(이름만). createReport 설명(F10). 새 응답 `MaterializePending`(503, `Retry-After`) — getDashboard·listComplexes·exportComplexesCsv·getComplex·getProvenance·getCompare·getSensitivity·getMarket·listChanges·listClaims·createReport. InternalError 설명에 stored_view_mismatch. 새 예시 `error_503_materialize_pending.json` |
| 6 | DB `0011` | `snapshot_view.contract_version`(String 32, NOT NULL, 기본 '') · kind CHECK + `provenance`·`claims`. 데이터 = .10 행 식별 변환(`contract_version='2026-10-09.11'` — 기존 kind 모양 변화 없음) |
| 7 | DB `0010`(수정) | 앱 코드 import·materialize 제거(테이블만). 이미 0010 을 지난 DB 에는 영향 없음 |

### 마이그레이션·검증

- 0010 DB: `cd backend && uv run alembic upgrade head`(0011) → `uv run python -m app.snapshot_view backfill`(또는 worker 재시작). backfill 전 발행 리비전의
  출처 서랍·주장 목록 GET = 503 materialize_pending. 0009 이하 DB 도 같은 두 단계(저장본 전부를 backfill 이 만든다).
- 왕복: head → 0009 → head(저장본 0행) → backfill(발행 스냅샷마다 종류 전부, 시나리오 5 × 단지 16) → backfill 다시 0행(멱등) → 0011→0010 downgrade
  (새 종류·버전 열 삭제) → head(식별 변환) → backfill 은 새 종류만, autogenerate diff 0 — **devseed 픽스처(단지·시나리오 있음)** 로 SQLite·Postgres 16
  (pgserver) 둘 다(`tests/contracts/test_r3f_migrations.py`, R3 6차 m28).
- `CONTRACT_VERSION`·`info.version` = `2026-10-09.11`. 생성물(`openapi.bundled.yaml`, `contracts_gen.py`) 재생성(`gen_contracts.py --check` 일치).
- **D14-5 측정**(`tests/api/test_r3f_perf_publish.py` — devseed 16 + 합성 1,000 단지, 합성 단지마다 점수 실행 5 × 총점 + 성분 7, 발행 리비전 위
  새 리비전을 `snapshot.publish` 잡으로 발행하는 동안 다른 스레드가 `POST /api/share-links` 를 50ms 마다 보냄, `python scripts/tasks.py regress`
  동시 실행 = 부하, **한 프로세스** — CEO 2026-10-10 기준 30s): 잡 18.0s·18.1s, API 쓰기 응답 최대 0.72s·0.69s(기준 1s, p50 0.007s — 시험에서는
  API 와 잡이 같은 프로세스라 GIL 대기가 섞인다, 운영은 api·worker 별도 프로세스), 저장본 묶음 쓰기 잠금 최대 0.20s·0.12s, 전환 0.004s, 저장본 5,418행·
  11.9MB(시나리오 사이 같은 부분 = 기본 + 바뀐 부분). 같은 계산 안의 반복 적재는 메모(`app.api.memo`)로 한 번만.

### fixtures

`contracts/fixtures/incheon_gimpo_2026-10-08/raw/human_check/t3_switzen_possible.json` 의 `checked_at` 을 `2026-10-09T10:00:00+09:00` 로(F7 — 날짜만이면
422), 생성기 `tools/build_incheon_gimpo.py` 도 같게. 매니페스트 사유: R3f-CORE4 T3 checked_at RFC3339 (contract .11 D14-6) fixture+builder

## 2026-10-09.10

R3 5차 리뷰(`docs/design/wp/R3_REVIEW5.md`) 후속 — CEO 결정 D13(`docs/design/DECISIONS.md`)과 R3e 배정(`docs/design/wp/R3E_FIX.md`).
계약 소유자 = R3e CORE3(브랜치 `wp/r3e-core3`). 마이그레이션 `0010`(`0010_r3e.py`: 테이블 1개 추가 `snapshot_view` + 기존 발행 스냅샷
materialize + 0009 `snapshot_state` 삭제 — 0009 DB 는 `cd backend && uv run alembic upgrade head` 한 번). 필드 삭제 없음, **필드 형 변경 1**
(`LivingAreaPrice.n_trades` integer → Fact, FE4 요청·CEO 승인).

**프론트(FE4)가 생성 타입으로 옮기며 맞출 것** — 아래 'FE 차이' 표. `frontend/src/api/schema.d.ts`·`src/mocks/handlers.gen.ts` 는 이 브랜치에서
다시 만들지 않았다(frontend/** = FE4 소유) — 머지 뒤 `npm ci` → `npm run gen:api`·`gen:msw`.

### 의미 변경(같은 필드, 다른 동작)

| # | 대상 | 이전(.9) | 이후(.10) | 결정·리뷰 |
| --- | --- | --- | --- | --- |
| S1 | **발행 리비전 GET**(대시보드·단지 목록·CSV·상세·비교·시장·변경·민감도)·보고서 | 지금 사실·강등 오버레이로 다시 계산(분류·생활권·호재 단계/연결만 `snapshot_state` 로 동결) → 사실·강등·사람 확인·새 단지·호재 PATCH·생활권·지역 이름·입주물량·classify 가 옛 리비전을 바꿨다 | 발행 트랜잭션이 그 리비전의 응답 전부·보고서 입력을 **시나리오별로 저장**(`snapshot_view`)하고 발행 리비전 GET·보고서는 **저장본만** 읽는다 — 이후 무엇이 바뀌어도 그 리비전 응답 바이트가 같다. 목록·CSV 의 필터·정렬·페이지·`/changes` 의 since·compare_snapshot·severity 는 저장본(발행 때 원장)에 적용. 발행 전(building·ready) 리비전만 지금 사실로 계산. 대시보드 `data_freshness` 도 발행 시점 값 | D13-1 · K2 |
| S2 | 발행 리비전에 없는 것 | 지금 값으로 계산 | 발행 뒤 만든 시나리오(`?scenario=<id>`)·그 리비전에 없던 생활권(`market?living_area=`)·단지(상세·비교) → **404**(그 시나리오 결과는 시나리오 실행이 만드는 새 리비전에 있다). 저장본이 아예 없는 발행 리비전 → 500 internal(실시간 폴백 없음 — 0010 이 옛 발행분을 materialize) | D13-1 |
| S3 | 출처 누락(T13) | ENV=dev GET 500 | 발행 저장본은 ENV 와 무관하게 '확인 불가(출처 누락)'(+경고 로그, 발행을 막지 않는다). dev 500 은 발행 전 리비전 실시간 GET 에서 | D13-1 |
| S4 | '재판정 필요'(`rejudge_needed`) | 지역 가장 새 발행 리비전에서 실시간 비교, 단지 단위 이벤트만 | 발행 전 리비전에서 늘 실시간 비교(**지역 단위 이벤트** — 생활권 편집·지역 확장/축소 포함). 발행 리비전은 발행 순간 값이 저장본에 고정(사람 확인 등은 새 리비전·자동 재판정 잡으로 보인다). 보고서 '재판정 필요'도 점수 실행 뒤 사실 변경을 반영(범위가 같아도) | M6 · minor |
| S5 | 사람 확인 단위 | 행 1개(그 공고 행·타입 행) | **(단지, 의미 필드)** — 강등과 같은 키(가격 = 그 타입 공고문 타입 행 + 모든 공고 그 타입 가격, 계약금 = 모든 공고). 사람 확인 이전 관측 출처는 어느 공고 행이든(무순위 새 공고·기준 타입 칸 없는 공고·시행일만 늦은 공고) 진다. 이후 관측된 공식 1차 출처의 다른 값은 새 공고 행이어도 채택 + critical change_event + `사람 확인 재검토: <필드>` | D13-2 · K1 |
| S6 | `POST /ops/human-checks` 이른 확인일 | 201 + critical 이벤트 + 재판정(그런데 값은 지고 있음) | 그 의미 필드에 확인일보다 **뒤에** 관측된 공식 공고가 이미 있으면 **422**(`field_errors[0].loc = ["body","checked_at"]`, detail 에 그 관측일). 같은 날은 받는다 | D13-2 · minor |
| S7 | rejudge 잡 합치기 | queued 잡 payload 를 읽고 고쳐 씀(worker 가 그 사이 집으면 단지 누락·running 잡 id 응답) | `UPDATE … WHERE status='queued'`(0행이면 새 잡), Postgres `FOR UPDATE`·SQLite 쓰기 잠금 먼저 — `rejudge_job_id` 는 늘 실제로 그 단지를 판정할 잡 | D13-3 · M1 |
| S8 | 이월·주간 수집 | 직전 발행 리비전 자신에 붙은 이벤트는 빼고 이월, 주간 '변경 없는 리비전'은 바탕 복사·발행 | 변경 없는 주간 수집은 **새 리비전을 만들지 않는다**(만든 빈 리비전 삭제 — 직전 발행 유지). 이월·주간 마감은 이전 실행 뒤 모든 change_event(자기 리비전·지역 단위 포함)와 **실패한 rejudge** 를 보고 하나라도 있으면 그 단지 재판정(옛 점수를 now 로 발행하지 않는다) | D13-4 · M2 |
| S9 | change_event 리비전 | 재강등·`PATCH /regions` 이벤트가 발행 스냅샷에 붙음, 재강등 rejudge 없음, 채택 보류만 돼도 '다시 채택됨' | 모든 change_event 는 쓰기 가능 리비전에만(재강등 = 가장 새 리비전의 쓰기 가능 리비전 + rejudge 등록, 지역 선택 변경 = 오늘 기준일 쓰기 가능 리비전 — region.expand 가 그 리비전을 판정). 채택 보류는 재강등이 아니다 | D13-5 · M3 · M4 |
| S10 | `POST /reports` | 비교 스냅샷 발행·지역 미검사, 잡 `stats.path` = REPORT_DIR 를 붙인 경로(상대 REPORT_DIR 이면 다운로드 404) | 비교 스냅샷 발행 전 409, 다른 지역 422(`compare_snapshot_id`). `stats.path` = REPORT_DIR 기준 **상대 이름**, 다운로드도 같은 기준(옛 잡 경로 호환). 보고서 강등 가격 사유 '검증 모순'(API 와 같음) | M5 · K3 · minor |
| S11 | 쓰기 본문 숫자 | NaN·Infinity·1e400 이 스키마를 지나 커밋 뒤 500(이후 GET /scenarios 500) | 모든 JSON 쓰기 본문(check_body 공용)에서 422 `validation_error`(field_errors = 그 위치) | M7 |
| S12 | 정규화 | — | 입주물량: 입력에서 빠진 단지 추정 행·출처 행 삭제(M8). 할인: **허용 목록** — 분양가·공급금액 할인 명시 + 타입 정확 일치 + 층·동·호 조건 없음만 '확인됨', 그 밖의 할인 금액(가전·수수료·세금·잔금 완납·면적 표기·'84A-1')은 후보로만 '추정'(구매가에서 빼지 않음, M9). 원 번호 인용 잔여 공고의 입주 예정월은 원 단지 후보(이름·세대수는 계속 버림, M10). 이름 키: 공급 구분 괄호를 NFKC 전에 떼고 '2블럭'·'II'·'3bl'·'A-3BL'·'Ⅱ-1' 유지, 블록 표기 변형 같은 키. 공고 번호: '최초 주택관리번호' 줄 순서와 무관, '재공급' 제목 = 무순위. 같은 이름 읍면동으로 법정동 모호 → '범위 경계'. 할인이 대표층가 이상이면 빼지 않는다(low 음수 방지) | M8 · M9 · M10 · minor |
| S13 | 보안·설정 | — | 홈페이지 URL: IDNA 무시 문자(U+00AD·200B~200D·034F·180B~180F·2060·FE00~FE0F·FEFF) 지운 뒤 내부망 검사, 제어 문자·`%00` 거부. redact: `aws_secret_access_key=`·`private_key=`·`pwd=`·대소문자 무관 `bearer <짧은 토큰>`. `BACKUP_DIR` 는 Settings(`.env` 포함) | minor |

### 스키마 변경

| # | 대상 | 변경 |
| --- | --- | --- |
| 1 | `complex_detail.json` PriceRange | `discount_applied`(boolean, 선택·기본 false) 추가 — 서버가 low·high·mid 에서 **실제로 뺐는가**. 상세 응답은 늘 싣는다 |
| 2 | `openapi.yaml` getMarket | `scenario` 조회 파라미터(`#/components/parameters/Scenario`) — 입주 마커 판정 범위 = 그 시나리오 점수 실행 저장값. `living_area` 설명(발행 리비전은 그 리비전 생활권만, 없으면 404) |
| 3 | `market.json` LivingAreaPrice.`n_trades` | integer → **Fact**(v = 건수, unit `count`, label = 그 실거래 행들의 가장 약한 라벨, prov = 중앙값 실거래 출처, reason = 집계 식). FE4 요청·CEO 승인. 예시 `examples/market.json` 갱신 |
| 4 | `snapshot.json` | 설명: 발행 리비전 = 저장된 읽기 모델(S1). `revision_of` 설명을 S9(.9) 이후 동작(미발행 리비전 1 의 비교 기준 = 직전 발행)으로 |
| 5 | DB `snapshot_view`(0010) | (snapshot_id, kind, key, scenario, body = zlib JSON, sha256) 유일 (snapshot_id, kind, key, scenario), kind CHECK. `snapshot_state`(0009) 삭제. API 모양 변화 없음(S1·S2 동작) |

### FE 차이(FE4 — 화면이 맞출 것)

| 대상 | .9 | .10 |
| --- | --- | --- |
| 상세 `price.discount_applied` | 없음(화면이 할인 Fact 가 있으면 '구매가에서 뺌' 표시) | 서버 값 — true 일 때만 '구매가에서 뺌'(0·음수·과대·추정 할인은 false) |
| `GET /snapshots/{sid}/market` | 시나리오 없음 | `?scenario=` 전달(화면 시나리오와 같게). `living_area_prices[].n_trades` = **Fact**(FactCell 로 표시, 건수 라벨은 이 Fact 의 label — 화면이 라벨을 만들지 않는다) |
| 발행 리비전 화면 | 사람 확인·강등 뒤 같은 리비전 화면이 바뀜('재판정 필요' 배지 등장) | 발행 리비전은 바뀌지 않는다 — 사람 확인 등은 새 리비전(판정 중)과 `rejudge_job_id` 잡으로 나타나고, 잡이 끝나 발행되면 그 리비전이 기본 화면. '재판정 필요' 배지는 판정 중 리비전·발행 순간 값 |
| 발행 뒤 만든 시나리오 | 옛 리비전에서 '미판정' 행으로 보임 | 옛 발행 리비전 + 그 시나리오 = 404 → 화면은 시나리오 실행(새 리비전) 안내 |
| `POST /ops/human-checks` | 이른 확인일도 201 | 422(`checked_at`, detail 에 관측일) — 폼 오류로 보인다 |
| `POST /reports` 비교 선택 | building 만 거름 | 발행 전 409·다른 지역 422 — 비교 선택은 같은 지역 발행 리비전만 |
| `POST /scenarios` 등 숫자 | NaN 이 500 | 422 |
| 보고서 다운로드 | 상대 REPORT_DIR 이면 404 | 200(경로 규칙 서버) |

### 마이그레이션·검증

- `0010`: `snapshot_view` 생성 → 발행 스냅샷 materialize(백엔드 앱 코드 — `app.snapshot_view.materialize_missing`; 출처 누락은 라벨) → `snapshot_state`
  삭제. downgrade = `snapshot_view` 삭제(저장본 손실) + 빈 `snapshot_state`. head → 0009 → head 왕복·발행 스냅샷 materialize·유일·kind CHECK 를
  SQLite·Postgres 16(pgserver) 둘 다 테스트(`tests/contracts/test_migrations.py::check_0009_0010_roundtrip`), autogenerate diff 0.
- `CONTRACT_VERSION`·`info.version` = `2026-10-09.10`. 생성물(`openapi.bundled.yaml`, `contracts_gen.py`) 재생성(`gen_contracts.py --check` 일치).
- devseed 는 픽스처 발행 스냅샷(11·12)의 저장본을 만든다(`devseed.rematerialize` — devseed·T13·합성 도구만 저장본을 다시 쓴다).

### fixtures

`contracts/fixtures/` 변경 없음(`fixture_manifest.py --check` 일치). 예시 `contracts/examples/market.json` 의 `n_trades` 만 Fact 로.

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
