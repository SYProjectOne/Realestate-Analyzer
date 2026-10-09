# 지역 추가 절차 (화면 G0)

근거: DECISIONS D2(지역은 사용자가 자유 지명으로 입력), D2-3(REST), D2-4(잡), D2-5(화면), RA §10 "지역 추가".
프로그램에는 지역명이 하드코딩돼 있지 않다. 지역 = 사용자가 고른 법정동 묶음 하나(`region` 행).

## 준비 (최초 1회)

- `reference.refresh` 잡이 법정동·행정동·매핑·세대수 참조 파일을 받아 둔다(최초 기동 시 자동, 이후 매월 1일 05:00).
  다운로드가 실패해도 `contracts/fixtures/reference/` 사본으로 동작한다.
- G7(운영)에서 참조 데이터 기준일(`source_date`)을 확인한다. 오래됐으면 `reference.refresh` 를 수동 등록한다.

## 1. 지역 입력 — G0 `/regions/new`

1. 헤더 `RegionPicker` → "지역 추가" (지역이 하나도 없으면 `/` 가 G0 으로 보낸다).
2. 검색창에 자유 지명을 친다(예: 동 이름, "○○시", "○○구 ○○동"). 입력은 디바운스되어 `GET /regions/resolve?q=` 로 간다.
   - 후보 = 시도·시군구·행정동·법정동. 이름 부분 일치(공백·"시/군/구/동" 접미사 무시), 정확 일치가 위.
   - 문자열 매칭일 뿐 판정기 호출은 없다.
   - 분구·개편 직후에는 옛 코드와 새 코드가 둘 다 후보로 나올 수 있다 — 둘 다 고르거나 실제 주소 기준으로 고른다.
3. 후보를 여러 개 골라 칩으로 담는다. 고른 묶음의 법정동 전체가 이 지역의 범위가 된다.
4. 지역 이름을 입력하고 **분석 시작** → `POST /regions {name, query_text, selections[]}`.
   - 응답: `Region`(201) + `job_id`. 화면은 `JobProgress` 로 `region.bootstrap` 진행을 보여 준다.

## 2. 자동으로 일어나는 일 — `region.bootstrap`

1. `collect.daily` + `collect.weekly` 즉시 실행(청약홈은 `region.sido_codes` 로 조회 → 주소의 법정동이
   `region.legal_dong_codes` 에 속한 단지만 남김; 매칭 실패 단지는 버리지 않고 G7 "범위 경계"로).
2. 스냅샷 생성 → 판정 파이프라인 P1~P9 → 점수 → `snapshot.publish`.
3. 상태: `region.status` = resolving → bootstrapping → ready (실패 시 failed, G7 에 사유).

시간: 지역 1개 일일 수집 10분 이내가 목표(RA WP1). 판정 호출 수는 단지 수에 비례한다.

## 3. 생활권 편집 — G0-2 `/regions/:id/living-areas`

1. 기본값 = 시군구 1개당 생활권 1개(D1 #1). 카드마다 법정동 목록과 세대수(Fact, 라벨 "추정(주민등록 세대)")가 보인다.
2. 법정동을 드래그(또는 선택 후 이동)해 생활권을 나누거나 묶는다. 생활권 추가·이름 변경·삭제(빈 경우만).
3. **저장** → `PUT /regions/{id}/living-areas`. 모든 법정동은 정확히 한 생활권에 속해야 한다(아니면 422).
4. 저장하면 `change_event(critical)` + `rejudge` 잡이 등록되고, 단지의 `living_area` 가 법정동 코드로 다시 배정된다.

## 4. 계수 확인

| 계수 | 기본값 | 위치 |
| --- | --- | --- |
| 공급 기준치 `supply_ref_pct` | 생활권 세대수의 8% (라벨 추정) | `region.supply_ref_pct` (D1 #3) |
| 연식 보정 c | 0.015/년, 상한 8년 (라벨 추정) | 분석 설정 (D1 #2) |
| 상황 가중치 | RA §6-4 표 | 시나리오 (D1 #4) |

## 5. 마무리

1. rerank 는 후보 전체로 1회 다시 호출된다(RA §6-5) — 기존 지역과 통합 순위가 다시 계산된다.
2. 보고서: `report` 잡(`format: html|pdf`) 또는 `python -m app.reports.cli --snapshot <id> --format pdf`.
   보고서에 "지역 추가" 장이 붙는다.
3. G1 대시보드에서 새 지역을 고르고, 숫자 셀마다 출처 패널(URL·확인일·라벨)이 열리는지 확인한다.

## 문제가 생기면

| 증상 | 확인 |
| --- | --- |
| 후보가 안 나옴 | 참조 데이터 기준일(G7), `reference.refresh` 재실행, 철자·접미사 없이 다시 검색 |
| 단지가 0개 | `region.sido_codes`·법정동 매칭 결과, G7 "범위 경계" 목록 |
| bootstrap 이 failed | G7 잡 로그(상태 코드), 판정기 장애면 runbook §3 |
| 세대수가 "확인 불가" | 행정동↔법정동 매핑 누락 — 참조 데이터 갱신 후 재편집 |
