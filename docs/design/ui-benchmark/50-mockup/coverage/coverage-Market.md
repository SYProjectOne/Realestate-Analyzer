# 대응표 — G6 지역 시장 (`/market`) → Market.dc.html

소스: `frontend/src/pages/market/index.tsx`(MarketPage·MarketBody·RegulationCard·LivingAreaCompare), `CatalystLocationPanel.tsx`, `CatalystUrlForm.tsx`, 차트 `frontend/src/charts/C03`·`C04`·`C05`·`C09` + `ChartFrame.tsx`, 공통 `components/DataTableToggle.tsx`·`FactCell.tsx`·`JobProgress.tsx`(PublishJobProgress·JobProgressView·JobRequeueNote), `pages/_shared`(QueryState·NoSnapshot·Section), 문자열 `i18n/ko.json`(`page.G6.*`, `chart.C03/C04/C05/C09.*`, `chart.col.*`, `badge.*`, `table.*`, `job.*`, `page.common.*`, `app.*`).
보드: `boards/Market.dc.html`(섹션: 머리 "인천 시장, 지금 어때요?" · "한눈에 보기" · "근처 새 아파트는 입주 뒤 얼마에 거래되나요?" · "언제 입주가 몰리나요?" · "안 팔린 집은 늘고 있나요?" · "어떤 규제가 걸려 있나요?" · "개발 소식은 어디까지 왔나요?" · "생활권마다 실거래 값은 얼마인가요?" · "개발 소식이 어느 동네에 해당하나요?" · "새 개발 소식을 알고 있나요?" · "펼친 모습 · 다른 상태").
머리줄(지역·기준일·상황 선택)과 출처 창은 공통 틀이라 Shell 보드에서 다룬다.

## 화면 틀·필터·상태

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 1 | 화면 제목 h1 (`index.tsx` · `page.G6.title` "지역 시장") | Market · 머리 h1 "인천 시장, 지금 어때요?" (탭·메뉴 이름 "지역 시장" 유지) | 지역 시장 → {지역} 시장, 지금 어때요? | 있음 |
| 2 | 생활권 필터 라벨 (`page.G6.livingArea` "생활권") | Market · 머리 "어느 생활권을 볼까요?" | 생활권 → 어느 생활권을 볼까요? | 있음 |
| 3 | 생활권 select 전체 옵션 (`page.G6.allAreas` "전체 생활권") | Market · 머리 select "전체 생활권" | — | 있음 |
| 4 | 생활권 select 옵션 = 응답 `living_areas`(이름) | Market · 머리 select 옵션 11개(제물포구 … 옹진군) | — | 있음 |
| 5 | 필터를 URL `?living_area=` 에 저장(replace) | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 6 | 스냅샷 없음 (`NoSnapshot` · `app.noSnapshot` "기준일 스냅샷이 없습니다. 지역 분석이 끝나면 나타납니다") | Market · 펼친 모습 "화면 전체" "기준일 자료가 아직 없을 때 지역 분석이 끝나면 나타나요" | — | 있음 |
| 7 | 첫 적재 중 (`app.noSnapshotBootstrapping` "지역 첫 적재 중 — 첫 발행 리비전이 나오면 나타납니다") | Market · 펼친 모습 "첫 수집 중이면 '첫 수정본이 나오면 나타나요'" | 리비전 → 수정본 | 있음 |
| 8 | 로딩 (`QueryState` · `app.loading` "불러오는 중…") | Market · 펼친 모습 "불러오는 중 불러오는 중…" | — | 있음 |
| 9 | 준비 중 503 + 다시 시도 (`page.common.materializePending`, `materializePendingStill`, `app.retry`) | Market · 펼친 모습 "준비 중 … 잠시 뒤 자동으로 다시 불러와요 [다시 시도]" | — | 있음 |
| 10 | 이전 값을 보이는 동안 새 조건이 준비 중이면 '준비 중' 줄 함께(M7 placeholder) | — | — | 있음(고침 MK-15 — 펼친 모습 "화면 전체" "생활권을 바꾼 뒤 새 자료가 준비 중일 때") |
| 11 | 조회 오류 (`page.common.loadError`) | Market · 펼친 모습 "불러오지 못함 불러오지 못했어요: [오류 내용]" | — | 있음 |
| 12 | 발행 뒤 만든 시나리오 결과 없음 + 실행 링크 (`page.common.scenarioMissing`, `scenarioMissingRun`) | Market · 펼친 모습 "다른 상황(시나리오) 결과가 없을 때 이 수정본에는 상황 #[n] 결과가 없어요 · 상황 실행 화면으로" | 시나리오 → 상황 | 있음 |
| 13 | 저장본 검증 실패 오류 (`page.common.storedViewMismatch`) | — | — | 있음(고침 MK-15 — 펼친 모습 "화면 전체" "저장된 화면 자료가 검증에 실패했을 때") |
| 14 | 차트 구역 sr-only h2 (`page.common.charts` "차트", 제목 순서 h1→h2→h3) | Market · 그림 섹션마다 h2 (sr-only 구역 제목은 없음) | 구역 제목 → 섹션별 h2 | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 15 | API `GET /snapshots/{sid}/market?living_area=&scenario=` (`useMarket`, 상황 토글 전달) | Market · 화면 전체(호출 주체) | — | 있음 |

## 근처 새 아파트 비교 (C03 벤치마크 + 표본 배지)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 16 | 벤치마크 없음 사유 배지 role=note (`index.tsx` · `page.common.benchmarkAbsent` "벤치마크 없음({reason})") | Market · 펼친 모습 "비교할 근처 새 아파트가 없을 때 비교할 단지 없음([사유])" | 벤치마크 없음 → 비교할 단지 없음 | 있음 |
| 17 | C03 차트 틀 제목 (`chart.C03.title` "벤치마크 분양가 → 실거래") | Market · "근처 새 아파트는 입주 뒤 얼마에 거래되나요?" "(공식 이름: 벤치마크 분양가 → 실거래)" | 공식 이름은 괄호로 유지 | 있음 | charts.r11 › 차트 이름(aria-label) = 제목 · e2e charts-gallery › C03 normal · pages/market/market.test(C03 제목) |
| 18 | C03 라벨 배지(분양가·실거래 Fact 라벨 모음, `ChartFrame` LabelBadge) | Market · C03 머리 "확인됨" · "추정 (한 해 평균 변화 · 대신 채운 줄)" | — | 있음 | ChartGallery.test › 정상 상태 카드는 라벨 배지 · e2e charts-gallery › C03 normal |
| 19 | C03 표본 배지 (`sampleBadges` · `badge.sampleEstimated` "표본 {n}, 추정" / `badge.sampleEstimatedArea` "{area} 표본 {n}, 추정", 표본 < 3) | Market · C03 "생활권마다 비교한 단지 수 (표본)" "영종구 2곳뿐 추정" + "3곳보다 적으면 '추정'으로 표시해요" | 표본 n, 추정 → n곳뿐 추정 | 있음 | charts.contract › C03 표본 < 3 → "표본 n, 추정" 배지(생활권별) · ChartGallery.test › 특수 상태 배지(표본) |
| 20 | C03 대체 배지 (`substituteBadge` · `badge.substituteRegion` "대체(지역 전체)") | Market · C03 범례 "지역 전체 자료로 대신 채운 줄" + "(공식 이름: 대체(지역 전체))" | 대체(지역 전체) → 지역 전체 자료로 대신 채운 줄 | 있음 | charts.contract › C03 N-M4 대체 행이 있으면 "대체(지역 전체)" 배지 문구 |
| 21 | C03 빈 상태 (`chart.C03.empty` "벤치마크 없음") | Market · 펼친 모습 "그림마다 자료가 없으면 … '비교할 단지 없음'" | — | 있음 | charts.contract › C03 0개 → "벤치마크 없음" · ChartGallery.test › 빈 상태 카드는 차트 대신 빈 상태 문구 |
| 22 | C03 y축 = 단지 이름(분양 연도) + 대체 접미 (`rowName`) | Market · C03 왼쪽 열 "단지 · 생활권 · 분양한 해" (예 "힐스테이트 송도 더스카이 / 연수구 · 2020년 분양") | 생활권 함께 표시 | 있음 | charts.contract › C03 행 라벨에 분양 연도, 툴팁에 연율 · charts.r11 › 라벨 사라짐 없음 |
| 23 | C03 x축 = 원 값, 억 단위 눈금 (`formatEok`) | Market · C03 눈금 "2억 4억 … 14억원" | — | 있음 | charts.r11 › C03 축 이름 |
| 24 | C03 분양가 → 실거래 중앙값 점선 (`dumbbell` custom) | Market · C03 회색 점선 | — | 있음 | charts.contract › C03 dumbbell(custom) + 고점 triangle + 분양권 diamond |
| 25 | C03 실거래 하단~상단 범위 막대 | Market · C03 파란 막대 + 범례 "실거래 가장 낮은 값 ~ 가장 높은 값" | — | 있음 | charts.contract › C03 dumbbell(custom) + 고점 triangle + 분양권 diamond · charts.r11 › C03 범례 |
| 26 | C03 실거래 중앙값 점 | Market · C03 파란 점 + 범례 "실거래 중간 값" | 중앙값 → 중간 값 | 있음 | charts.contract › C03 dumbbell(custom) + 고점 triangle + 분양권 diamond · charts.r11 › C03 범례 |
| 27 | C03 분양가 점: 원(일반)·마름모(분양권)·속 빈 원(대체) — 색이 아니라 모양으로 구분 | Market · C03 까만 점·마름모·빈 원 + 범례 "분양가" · "분양권 (입주 전 거래)" · "지역 전체 자료로 대신 채운 줄" | — | 있음 | charts.contract › C03 dumbbell(custom) + 고점 triangle + 분양권 diamond · charts.contract › C03 N-M4 표·축·툴팁에 "대체(지역 전체)" 표시, 마커는 속 빈 원 |
| 28 | C03 고점 삼각형 (`chart.C03.peak` "고점") | Market · C03 회색 삼각형 + 범례 "입주 뒤 가장 높았던 거래 (고점)" | — | 있음 | charts.contract › C03 dumbbell(custom) + 고점 triangle + 분양권 diamond · charts.r11 › C03 범례 |
| 29 | C03 범례 (계열 이름 `chart.C03.range`·`sale`·`peak`) | Market · C03 범례 6항목 | 범례 항목 늘어남 | 있음 | charts.r11 › C03 범례 |
| 30 | C03 툴팁: 이름·분양권, 분양가, 최근 실거래 하단~상단, 고점+연월, 연율 (`chart.C03.sale`·`trade`·`peak`·`presale`·`annualized` "연율 {pct}") | Market · C03 "줄에 마우스를 올리면 … 분양가 7억 7,380만원 최근 실거래 … 고점 … 한 해 평균 +7.0% 추정 · 거래 16건" | 연율 → 한 해 평균 | 있음(고침 MK-2 — 말풍선을 지금 툴팁 줄과 같게, 거래 수·출처 줄 뺌) | charts.contract › C03 행 라벨에 분양 연도, 툴팁에 연율 |
| 31 | C03 연율: 서버 `annualized_pct` 없을 때 화면에서 계산하는 폴백 (`annualizedPct`) | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) | charts.contract › C03 행 라벨에 분양 연도, 툴팁에 연율(asofYear 폴백) |
| 32 | C03 차트 aria-label = 제목 | Market · C03 role=img aria-label "근처 새 아파트 11줄의 분양가와 입주 뒤 실거래 범위. 표로 보기에서…" | 설명형으로 | 있음 | charts.r11 › 차트 이름(aria-label) = 제목 |
| 33 | C03 "표로 보기"/"표 닫기" 토글 (`DataTableToggle` · `table.show`·`table.hide`, aria-expanded) | Market · C03 "표로 보기" + 펼친 모습 "근처 새 아파트 비교 · 표로 보기 [표 닫기]" | — | 있음 | charts.r11 › ChartFrame 표로 보기 |
| 34 | C03 표 열: 이름(분양권·대체 접미) (`chart.col.name`) | Market · 펼친 모습 C03 표 "이름" ("시티오씨엘 6단지 · 분양권", "… · 대체(지역 전체)") | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C03 N-M4 표·축·툴팁 … |
| 35 | C03 표 열: 생활권 (`chart.col.livingArea`) | Market · 펼친 모습 C03 표 "생활권" | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C03 N-M4 표·축·툴팁 … |
| 36 | C03 표 열: 분양 연도 (`chart.col.saleYear`) | Market · 펼친 모습 C03 표 "분양한 해" | 분양 연도 → 분양한 해 | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C03 N-M4 표·축·툴팁 … |
| 37 | C03 표 열: 분양가(84㎡) (`chart.col.salePrice`) | Market · 펼친 모습 C03 표 "분양가 (84㎡)" | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C03 N-M4 표·축·툴팁 … |
| 38 | C03 표 열: 하단 (`chart.col.low`) | Market · 펼친 모습 C03 표 "실거래 가장 낮은" | 하단 → 실거래 가장 낮은 | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C03 N-M4 표·축·툴팁 … |
| 39 | C03 표 열: 중앙값 (`chart.col.median`) | Market · 펼친 모습 C03 표 "중간" | 중앙값 → 중간 | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C03 N-M4 표·축·툴팁 … |
| 40 | C03 표 열: 상단 (`chart.col.high`) | Market · 펼친 모습 C03 표 "가장 높은" | 상단 → 가장 높은 | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C03 N-M4 표·축·툴팁 … |
| 41 | C03 표 열: 고점 (`chart.col.peak`) | Market · 펼친 모습 C03 표 "고점" | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C03 N-M4 표·축·툴팁 … |
| 42 | C03 표 열: 연율 (`chart.col.annualized`, pct) | Market · 펼친 모습 C03 표 "한 해 평균 변화" ("+7.0% 추정") | 연율 → 한 해 평균 변화 | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C03 N-M4 표·축·툴팁 … |
| 43 | C03 표 열: 거래 기간 (`chart.col.window`) | Market · 펼친 모습 C03 표 "거래 기간" | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C03 N-M4 표·축·툴팁 … |
| 44 | 표 캡션 (`table.caption` "{title} 데이터", sr-only) | Market · 펼친 모습 C03 표 caption "121줄 중 5줄 · 84㎡ 기준 · 단위 원" | 보이는 캡션으로 | 있음 | charts.r11 › ChartFrame 표로 보기(캡션 "{제목} 데이터") |
| 45 | 표 Fact 셀 → 라벨·출처 창 (`FactCell`, 빈 칸 `EmptyState inline`) | Market · 표 셀 "추정" 배지 + 맨 아래 "밑줄 점선 숫자를 누르면 출처가 열려요" | — | 있음 | ChartGallery.test › 표로 보기 → Fact 셀 클릭이 출처 패널로 · e2e charts-gallery › 표로 보기: … Fact 셀 → 출처 패널 |
| 46 | 표가 비었을 때 (`DataTableToggle` · `empty.noData` "데이터 없음") | — | — | 있음(고침 MK-10 — 펼친 모습 "표로 보기 · 줄이 하나도 없을 때" "데이터 없음") | charts.r11 › ChartFrame 표로 보기(데이터 없음 한 줄) |
| 47 | 벤치마크 표본 목록 ul aria-label (`page.G6.flags` "벤치마크 표본") | Market · C03 아래 "생활권마다 비교한 단지 수 (표본)" | 벤치마크 표본 → 생활권마다 비교한 단지 수 (표본) | 있음 |
| 48 | 표본 배지 (`page.G6.flag` "{name}: 표본 {n}", 표본 < 3 이면 흐리게) | Market · 표본 목록 "연수구 10곳" · "영종구 2곳뿐 추정" | 표본 n → n곳 | 있음 |
| 49 | 최근 분양 사례 없음 (`page.G6.noRecentSale` "최근 분양 사례 없음") | Market · 표본 목록 "· 최근 분양 사례 없음" | — | 있음 |
| 50 | 표본 줄 대체 배지 (`badge.substituteRegion`, data-testid flag-substituted) | Market · 표본 목록 "제물포구 0곳 지역 전체로 대신 채움" | 대체(지역 전체) → 지역 전체로 대신 채움 | 있음 |

## 입주 물량 (C04)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 51 | C04 제목 (`chart.C04.title` "입주 물량") | Market · "언제 입주가 몰리나요?" "(공식 이름: 입주 물량)" | — | 있음 | charts.r11 › 차트 이름(aria-label) = 제목 · e2e charts-gallery › C04 normal |
| 52 | C04 부제 (`chart.C04.label` "추정 집계") | Market · C04 "추정 (입주 예정 단지 집계)" | — | 있음 | charts.contract › C04 라벨 "추정 집계", 0개 → "입주 물량 없음" |
| 53 | C04 라벨 배지(units Fact 라벨) | Market · C04 "추정" 배지 | — | 있음 | e2e charts-gallery › C04 normal(라벨 배지) |
| 54 | C04 연도별 생활권 쌓은 막대(stack, 색 순서) | Market · C04 막대 7개(2024~2030) 생활권별 색 | — | 있음 | charts.contract › C04 연도 x, 생활권 stack(이름), 판정 단지 입주 markPoint · charts.r11 › C04 나머지 |
| 55 | C04 범례 = 생활권 계열 이름 (서버 `living_area_name` → `living_areas` 폴백) | Market · C04 범례 "연수구 · 검단구 · 미추홀구 · 영종구 · 계양구 · 나머지 5곳 (…)" | 6위 이하는 "나머지 n곳"으로 묶음 | 있음 | charts.r11 › C04 범례(위) · charts.r11 › C04 생활권 묶기 · e2e charts-gallery › R11 C04 범례는 차트 위 · pages/wiring20.test(F6 C04 계열 이름) |
| 56 | C04 생활권 모름 계열 (`empty.unknown` "확인 불가") | — | — | 있음(고침 MK-5 — 범례 "확인 불가 (생활권을 모르는 입주 물량)" + 안내) | charts.r11 › C04 나머지(확인 불가 계열) · charts.r11 › C04 표 · e2e charts-gallery › R11 C04 범례는 차트 위 |
| 57 | C04 x축 연도(끊김 없이 채움) | Market · C04 "2024 … 2030" | — | 있음 | charts.contract › C04 연도 x(끊김 없이) |
| 58 | C04 y축 이름 "추정 집계" + 개수 눈금 | Market · C04 y축 "세대 16,000 … 0" | 축 이름 추정 집계 → 세대 | 있음 | charts.contract › C04 라벨 "추정 집계"(축 이름 세대) · charts.r11 › 축 눈금 |
| 59 | C04 판정 단지 입주 핀(markPoint, 같은 해는 핀 하나, 라벨 "이름\nYYYY-MM") (`chart.C04.marker` "판정 단지 입주") | Market · C04 핀 + 범례 "점수 매긴 단지 입주" | 판정 단지 입주 → 점수 매긴 단지 입주 | 있음 | charts.contract › C04 연도 x, … 판정 단지 입주 markPoint(같은 해 핀 하나) |
| 60 | C04 같은 해 여러 단지 핀 라벨 (`chart.C04.markerMore` "{name} 외 {n}") | Market · C04 2028 핀 "엘리프 검단 포레듀 외 3곳" | — | 있음 | charts.contract › C04 연도 x, … 판정 단지 입주 markPoint(같은 해 핀 하나) |
| 61 | C04 툴팁: "연도 · 추정 집계", 계열별 세대, 그 해 판정 단지 입주 목록 | Market · C04 "막대에 마우스를 올리면 · 2026년 · 추정 집계 …" + "핀에 마우스를 올리면 · 2028년 …" | — | 있음(고침 MK-4 — 해마다 한 말풍선: 생활권별 세대 + 점수 매긴 단지 입주 줄) | charts.r11 › C04 툴팁 · charts.contract › C04 라벨 "추정 집계"(말풍선 머리) |
| 62 | C04 aria-label = 제목 | Market · C04 role=img aria-label "연도별 입주 물량. 2024년 2,112 …세대(추정)." | 설명형으로 | 있음(고침 MK-3 — 설명에서 화면이 더한 연도 합계를 뺌, 막대 위 합계 숫자도 뺌) | charts.r11 › 차트 이름(aria-label) = 제목 |
| 63 | C04 표로 보기 | Market · C04 "표로 보기" + 펼친 모습 "입주 물량 · 표로 보기 [표 닫기]" | — | 있음 | charts.r11 › ChartFrame 표로 보기 |
| 64 | C04 표 열: 연도 (`chart.col.year`) | Market · 펼친 모습 C04 표 "연도" | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.r11 › C04 표 |
| 65 | C04 표 열: 생활권 (`chart.col.livingArea`) | Market · 펼친 모습 C04 표 "생활권" | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.r11 › C04 표 |
| 66 | C04 표 열: 세대 (`chart.col.units`, households) | Market · 펼친 모습 C04 표 "세대" | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.r11 › C04 표 |
| 67 | C04 표 열: 이름(단지 목록) (`chart.col.name`) | Market · 펼친 모습 C04 표 "단지" | 이름 → 단지 | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.r11 › C04 표 |
| 68 | C04 빈 상태 (`chart.C04.empty` "입주 물량 없음") | Market · 펼친 모습 "'입주 물량 자료 없음'" | — | 있음 | charts.contract › C04 0개 → "입주 물량 없음" · ChartGallery.test › 빈 상태 카드는 차트 대신 빈 상태 문구 |

## 미분양 추이 (C05)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 69 | C05 제목 (`chart.C05.title` "미분양 추이") | Market · "안 팔린 집은 늘고 있나요?" "(공식 이름: 미분양 추이)" | — | 있음 | charts.r11 › 차트 이름(aria-label) = 제목 · e2e charts-gallery › C05 normal |
| 70 | C05 부제 (`chart.C05.basis` "월말 기준" / `basisScope` "월말 기준 · {scope}") | Market · C05 "월말 기준 · 인천 부평구" | — | 있음 | charts.contract › C05 범위(scope)가 여럿이면 … 부제에 범위명 |
| 71 | C05 라벨 배지 | Market · C05 출처 줄 "확인됨" | — | 있음 | e2e charts-gallery › C05 normal(라벨 배지) |
| 72 | C05 범위 자동 선택(값 있는 달이 가장 많은 범위, `selectScope`) | Market · C05 select 기본값 "부평구 (자료가 가장 긴 구)" | 고를 수 있는 select로 바뀜(새로 더한 것 N7) | 있음 | charts.contract › C05 범위(scope)가 여럿이면 자료가 가장 많은 범위 하나 |
| 73 | C05 최근 24개월만 그림 (`C05_DEFAULT_MONTHS`) | — | — | 문구로만(고침 MK-6 — "가장 최근 24개월까지만 그려요" 안내) | charts.contract › C05 결측 월은 null로 남긴다(월 축은 끊김 없음), 최근 24개월 |
| 74 | C05 월 축 끊김 없이, 빈 달은 선을 끊음 (`connectNulls: false`) | Market · C05 "(자료가 빈 달은 '확인 불가', 선이 끊겨요)" + 펼친 모습 "자료가 빈 달은 선을 끊고 '확인 불가'로 적어요." | — | 있음 | charts.contract › C05 결측 월은 null로 남긴다 |
| 75 | C05 앞뒤가 빈 외톨이 달도 점으로 표시 (`showAllSymbol`) | — | — | 문구로만(고침 MK-6 — "혼자 남은 달도 점으로 보여요" 안내) | e2e charts-gallery › C05 special(외톨이 달 점) |
| 76 | C05 합계 실선 원 마커 (`chart.C05.total` "합계") | Market · C05 범례 "전체 안 팔린 집 (합계)" | 합계 → 전체 안 팔린 집 (합계) | 있음 | charts.r11 › C05 범례 |
| 77 | C05 준공 후 점선 네모 마커 (`chart.C05.postCompletion` "준공 후") — 색 아닌 선 모양 구분 | Market · C05 범례 "다 지은 뒤에도 안 팔린 집 (준공 후)" | 준공 후 → 다 지은 뒤에도 안 팔린 집 (준공 후) | 있음 | charts.r11 › C05 범례 |
| 78 | C05 y축 0부터, 개수 눈금 | Market · C05 "120 80 40 0" | — | 있음 | charts.r11 › C05 툴팁(축 이름 세대) · charts.r11 › 축 눈금 |
| 79 | C05 x축 월 | Market · C05 "2025.10 … 2026.8" | — | 있음 | charts.contract › C05 결측 월은 null로 남긴다(월 축은 끊김 없음), 최근 24개월 |
| 80 | C05 툴팁(값 개수 포맷, 없으면 `empty.unknown`) | Market · C05 "점에 마우스를 올리면 · 2025-12 · 합계 103세대 · 준공 후 26세대" | — | 있음(고침 MK-7 — 말풍선 2개: 값 있는 달 · 빈 달 "확인 불가") | charts.r11 › C05 툴팁 |
| 81 | C05 aria-label = 제목 | Market · C05 role=img aria-label "인천 부평구 미분양: 2025년 10월 32세대에서 …" | 설명형으로 | 있음 | charts.r11 › 차트 이름(aria-label) = 제목 |
| 82 | C05 표로 보기 | Market · C05 "표로 보기" + 펼친 모습 "안 팔린 집 · 표로 보기 (부평구) [표 닫기]" | — | 있음 | charts.r11 › ChartFrame 표로 보기 |
| 83 | C05 표 열: 월 (`chart.col.month`) | Market · 펼친 모습 C05 표 "월" | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 |
| 84 | C05 표 열: 합계 | Market · 펼친 모습 C05 표 "합계" | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 |
| 85 | C05 표 열: 준공 후 | Market · 펼친 모습 C05 표 "다 지은 뒤 (준공 후)" | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 |
| 86 | C05 빈 상태 (`chart.C05.empty` "미분양 자료 없음") | Market · 펼친 모습 "'미분양 자료 없음'" | — | 있음 | ChartGallery.test › 빈 상태 카드는 차트 대신 빈 상태 문구 |

## 규제 요약 (RegulationCard)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 87 | 규제 Section (`page.G6.regulation` "규제 요약") | Market · "어떤 규제가 걸려 있나요?" "(공식 이름: 규제 요약)" | — | 있음 |
| 88 | 규제 없음 (`EmptyState` `page.common.none` "없음") | Market · 펼친 모습 "규제·실거래 표는 '없음'" | — | 있음 |
| 89 | 항목 제목 dt (`item.title`) | Market · 규제 표 열 머리 "규제지역" · "분양가 상한제" | 항목 목록 → 생활권별 표(열) | 있음 |
| 90 | 항목 값 FactCell(라벨·출처·asof) | Market · 규제 표 칸 "비규제/적용/미적용" + "확인됨" | — | 있음 |
| 91 | 적용 범위 (`page.G6.regulationScope` "범위: {scope}") | Market · 규제 표 행 머리 "생활권 (범위)" | 범위: → 행 머리 | 있음 |
| 92 | 항목 메모 (`item.note`) | Market · 규제 표 열 "근거 단지" (메모 = 근거 단지로 가정) | 메모 → 근거 단지 | 있음 |
| 93 | 그 밖의 규제 항목 key: 전매(resale)·거주의무(residency)·대출(loan)·세제(tax)·토지거래허가(land_permit)·기타(other) | — | — | 있음(고침 MK-8 — "그 밖의 규제 항목" 전매제한·거주의무·대출·세제·토지거래허가·기타 [ ] 자리 줄) |

## 개발 소식 단계 (C09)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 94 | C09 제목 (`chart.C09.title` "호재 단계") | Market · "개발 소식은 어디까지 왔나요?" "(공식 이름: 호재 단계)" | 호재 → 개발 소식 | 있음 | charts.r11 › 차트 이름(aria-label) = 제목 · e2e charts-gallery › C09 normal |
| 95 | C09 라벨 배지(stage_prob 라벨) | Market · C09 "단계 · 확신 정도 모두 판정기 추정" | — | 있음 | e2e charts-gallery › C09 normal(라벨 배지) |
| 96 | 단계 보드 5열 고정 순서 + 단계 배지 (`C09_STAGES`, `chart.C09.stage.*` 확정·계획·추진·언론·미확정) | Market · C09 "1 확정 0건 · 2 계획 · 3 추진 중 · 4 언론 보도만 · 5 확인 안 됨 (미확정)" | 추진 → 추진 중, 언론 → 언론 보도만, 미확정 → 확인 안 됨 | 있음 | charts.contract › C09 보드 5열 묶음 + 언론·미확정 회색 + 위치 미확정 표시 · charts.r11 › C09 쉬운 단계 이름 · charts.r11 › C09 단계 보드 |
| 97 | 언론·미확정 열 회색 (`C09_GRAYED`) | Market · C09 "회색 단계(언론 보도만 · 확인 안 됨)는 아직 공식 계획으로 확인되지 않은 소식이에요" | — | 있음 | charts.contract › C09 보드 5열 묶음 + 언론·미확정 회색 · e2e charts-gallery › C09 normal |
| 98 | 항목 이름 | Market · C09 "확인 안 됨 · 5건" 목록 이름 | — | 있음 | charts.r11 › C09 단계 보드 · charts.contract › C09 보드 5열 …(위치 미확정) · e2e charts-gallery › C09 special |
| 99 | 항목 종류 (`c.kind`) | Market · C09 항목 "개발" 등 | — | 있음 | charts.r11 › C09 단계 보드 · charts.contract › C09 보드 5열 …(위치 미확정) · e2e charts-gallery › C09 special |
| 100 | 항목 예상 시기 FactCell(ym, 없으면 사유) | Market · C09 항목 "예상 시기 확인 불가(예정 시기 미기재)" | — | 있음 | charts.r11 › C09 단계 보드 · charts.contract › C09 보드 5열 …(위치 미확정) · e2e charts-gallery › C09 special |
| 101 | 위치 미확정 표시 (`chart.C09.noLink` "위치 미확정 · 단지 연결 없음") | Market · C09 항목 "위치 확인 전 · 단지와 아직 연결 안 됨" | — | 있음 | charts.r11 › C09 단계 보드 · charts.contract › C09 보드 5열 …(위치 미확정) · e2e charts-gallery › C09 special |
| 102 | 보드 밖 '호재 아님' 건수 (`chart.C09.excluded` "호재 아님(판정 제외) {n}건 — 보드에 넣지 않음") | Market · C09 출처 줄 "'호재 아님'으로 빠진 소식 0건" + 펼친 모습 "'호재 아님'(판정 제외) [n]건 — 단계 보드에 넣지 않았어요" | — | 있음 | charts.contract › C09 계약 .8 '호재 아님' 단계는 보드에 넣지 않고 따로 센다 |
| 103 | 확정 호재 타임라인(확정 + 예정 연월 있는 것만, 날짜순, time 축) (`chart.C09.timeline` "확정 호재 타임라인") | Market · C09 "확정된 소식 일정표" + 펼친 모습 "확정된 소식이 있을 때 · 일정표" | 확정 호재 타임라인 → 확정된 소식 일정표 | 있음 | charts.contract › C09 타임라인은 확정 + 예정 연월 있는 것만 |
| 104 | 타임라인 4단 엇갈림 + 겹치는 이름 숨김(hideOverlap) | Market · 펼친 모습 "이름이 겹치면 높이를 엇갈려 놓고, 다 못 보이면 표에 모두 있어요" | — | 있음 | charts.contract › C09 타임라인은 확정 + 예정 연월 있는 것만(4단 엇갈림) |
| 105 | 타임라인 툴팁(이름·종류·연월·메모) | Market · 펼친 모습 "점에 마우스를 올리면: [소식 이름] · [종류] · [YYYY-MM] · [메모]" | — | 있음(고침 MK-14 — 일정표 말풍선) | e2e charts-gallery › C09 normal(일정표) |
| 106 | 타임라인 항목 없으면 그리지 않음 | Market · C09 "확정 단계이면서 예상 시기가 있는 소식이 아직 없어 비어 있어요" | 숨김 → 빈 안내 문구 | 있음 | charts.r11 › C09 일정표 비었을 때 |
| 107 | 작게(compact) 모드 — 보드만, 타임라인 숨김 (G3에서 사용) | Market · 펼친 모습 "상세 화면에 들어가는 작은 보드는 일정표 없이 단계 칸만 보여요" (그림은 Detail 보드) | — | 다른 보드(Detail) | charts.r11 › C09 일정표 비었을 때(compact는 없음) |
| 108 | C09 표로 보기 | Market · C09 "표로 보기" + 펼친 모습 "개발 소식 단계 · 표로 보기 [표 닫기]" | — | 있음 | charts.r11 › ChartFrame 표로 보기 |
| 109 | C09 표 열: 이름 (`chart.col.name`) | Market · 펼친 모습 C09 표 "이름" | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C09 보드 5열 …(toTable 위치 확정) |
| 110 | C09 표 열: 구분 (`chart.col.kind`) | Market · 펼친 모습 C09 표 "종류" | 구분 → 종류 | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C09 보드 5열 …(toTable 위치 확정) |
| 111 | C09 표 열: 단계 (`chart.col.stage`) | Market · 펼친 모습 C09 표 "단계" | — | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C09 보드 5열 …(toTable 위치 확정) |
| 112 | C09 표 열: 확률 (`chart.col.prob`, prob) | Market · 펼친 모습 C09 표 "판정기 확신" ("53% 추정") | 확률 → 판정기 확신 | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C09 보드 5열 …(toTable 위치 확정) |
| 113 | C09 표 열: 예정 (`chart.col.expected`, ym Fact) | Market · 펼친 모습 C09 표 "예상 시기" | 예정 → 예상 시기 | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C09 보드 5열 …(toTable 위치 확정) |
| 114 | C09 표 열: 위치 확정 (`chart.col.location`, 값 `chart.yes` "예" / `chart.C09.noLink`) | Market · 펼친 모습 C09 표 "위치 확인" (값 "위치 미확정 · 단지 연결 없음"만 그림, "예"는 실데이터 0건) | 위치 확정 → 위치 확인 | 있음 | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C09 보드 5열 …(toTable 위치 확정) |
| 115 | C09 빈 상태 (`chart.C09.empty` "호재 없음") | Market · 펼친 모습 "'개발 소식 없음'" | — | 있음 | ChartGallery.test › 빈 상태 카드는 차트 대신 빈 상태 문구 |

## 생활권별 실거래 시세 (LivingAreaCompare)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 116 | Section·표 aria-label (`page.G6.prices` "생활권별 실거래 시세") | Market · "생활권마다 실거래 값은 얼마인가요?" "(공식 이름: 생활권별 실거래 시세)" | — | 있음 |
| 117 | 시세 없음 (`page.common.none`) | Market · 펼친 모습 "규제·실거래 표는 '없음'" | — | 있음 |
| 118 | 표 열: 생활권 (`page.G6.priceCol.name`, 행 머리) | Market · 시세 표 "생활권" | — | 있음 |
| 119 | 표 열: 하단 (`priceCol.low`, FactCell 억) | Market · 시세 표 "가장 낮은 값 (하단)" | 하단 → 가장 낮은 값 (하단) | 있음 |
| 120 | 표 열: 중앙값 (`priceCol.median`) | Market · 시세 표 "중간 값" | 중앙값 → 중간 값 | 있음 |
| 121 | 표 열: 상단 (`priceCol.high`) | Market · 시세 표 "가장 높은 값 (상단)" | — | 있음 |
| 122 | 표 열: 거래 수 (`priceCol.n`, `n_trades` Fact count) | Market · 시세 표 "거래 수" | — | 있음 |
| 123 | 표 열: 기간 (`priceCol.window`, `trade_window`) | Market · 시세 표 caption "기준일 전 6개월 (2026-04~2026-10)" + "거래 기간·기준이 생활권마다 다르면 표에 '기간'·'기준' 열이 따로 생겨요" | 열 → 같으면 캡션, 다르면 열 | 있음(고침 MK-9 — 펼친 모습 "기간이나 기준이 다를 때" 표의 "기간" 열) |
| 124 | 표 열: 기준 (`priceCol.basis`, `basis`) | Market · 시세 표 caption "분양권·해제 거래 빼고" + 위 안내 | 열 → 같으면 캡션, 다르면 열 | 있음(고침 MK-9 — 같은 표의 "기준" 열) |
| 125 | 기간 없음 (`empty.unknown` "확인 불가") | — | — | 있음(고침 MK-9 — 같은 표 둘째 줄 기간 "확인 불가") |
| 126 | 칸 FactCell 라벨·출처 | Market · 시세 표 아래 "모두 확인됨 · 국토교통부 실거래 · 확인 2026-10-13" | — | 있음 |

## 개발 소식 위치 확인 (CatalystLocationPanel)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 127 | Section·목록 aria-label (`page.G6.loc.title` "호재 위치 확인") | Market · "편집하는 사람용 · 개발 소식이 어느 동네에 해당하나요?" "(공식 이름: 호재 위치 확인)" | — | 있음 |
| 128 | 안내 (`page.G6.loc.intro` "호재 위치를 사람이 확인해야 단지와 연결됩니다…") | Market · 같은 섹션 안내 문단 | 가중치 1 → 계산 계수 1 | 있음 |
| 129 | 호재 없음 (`page.G6.loc.none` "호재가 없습니다") | Market · 펼친 모습 "개발 소식이 하나도 없으면: '개발 소식이 없어요'" | — | 있음 |
| 130 | 줄: 호재 이름 | Market · 위치 확인 목록 이름 5줄 | — | 있음 |
| 131 | 줄: 단계 배지 (`chart.C09.stage.*`, '호재 아님'은 흐리게 `chart.C09.stage.호재 아님` "호재 아님(제외)") | Market · 목록 "확인 안 됨" + 펼친 모습 "[호재 아님으로 빠진 소식] 호재 아님 (제외)" | — | 있음 |
| 132 | 줄: 위치 상태 배지 (`page.G6.loc.confirmed` "위치 확인됨" / `unconfirmed` "위치 미확정") | Market · 목록 "위치 확인 전" + 펼친 모습 "위치 확인됨" | 위치 미확정 → 위치 확인 전 | 있음 |
| 133 | 위치 확인 버튼 (`page.G6.loc.open` "위치 확인", aria-expanded) | Market · 목록 "위치 확인" / 열린 줄 "위치 확인 닫기" | 열렸을 때 "위치 확인 닫기" | 있음 |
| 134 | 한 번에 한 줄만 열림 (`openId`) | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 135 | 위치 확인 취소 버튼 (`page.G6.loc.unconfirm` "위치 확인 취소", 확인된 줄만) | Market · 펼친 모습 "[위치를 확인한 소식] … [위치 확인] [위치 확인 취소]" + "위치를 확인한 소식에는 '위치 확인 취소' 버튼이 함께 나오고" | — | 있음 |
| 136 | 취소 버튼 저장 중 꺼짐 (`update.isPending`) | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 137 | '호재 아님' 줄은 버튼 없음 | Market · 펼친 모습 "연결 대상이 아니라 버튼 없음" | — | 있음 |
| 138 | 읽기 전용: 버튼 꺼짐 + title (`auth.readOnlyHint`) | Market · 펼친 모습 "[읽기 전용으로 볼 때] [위치 확인](꺼짐, title) 읽기 전용 토큰으로는 저장·실행할 수 없어요" | — | 있음 |
| 139 | 위치 폼 aria-label (`page.G6.loc.formFor` "{name} 위치 확인") | — | — | 있음(재확인 — 열린 폼에 aria-label "… 위치 확인"이 이미 있음, 고침 아님) |
| 140 | 위도 입력칸 (`page.G6.loc.lat` "위도(선택)", inputMode decimal) | Market · 열린 폼 "위도 (선택)" placeholder "예: 37.123456" | — | 있음 |
| 141 | 경도 입력칸 (`page.G6.loc.lon` "경도(선택)") | Market · 열린 폼 "경도 (선택)" | — | 있음 |
| 142 | 예상 시기 month 입력 (`page.G6.loc.expectedYm` "예상 시기(선택, 사람 확인)") | Market · 열린 폼 "예상 시기 (선택 · 사람 확인)" type=month | — | 있음 |
| 143 | 영향 생활권 fieldset·체크박스 (`page.G6.loc.areas` "영향 생활권") | Market · 열린 폼 fieldset "영향 받는 생활권" 11개 | 영향 생활권 → 영향 받는 생활권 | 있음 |
| 144 | 영향 단지 다중 select size 4 (`page.G6.loc.complexes` "영향 단지(여러 개 선택)") | Market · 열린 폼 "영향 받는 단지 (여러 개 고르기)" + "Ctrl(맥은 ⌘)을 누른 채 여러 개 고르기" | — | 있음 |
| 145 | 영향 단지 초깃값 = 이미 연결된 단지 (`linked_complex_ids`) | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 146 | 제출 버튼 (`page.G6.loc.submit` "위치 확인 → 단지 연결") | Market · 열린 폼 "위치 확인하고 단지와 연결" | — | 있음 |
| 147 | 저장 중 제출 꺼짐 | Market · 펼친 모습 "위치 확인 폼 · 오류" "저장 중에는 버튼이 꺼져요." | — | 문구로만 |
| 148 | 좌표 오류 (`page.G6.loc.badCoord` "위도는 -90~90, 경도는 -180~180 사이 숫자여야 합니다") | Market · 펼친 모습 "위도는 -90~90, 경도는 -180~180 사이 숫자여야 해요" | — | 있음 |
| 149 | 좌표 한쪽만 (`page.G6.loc.bothCoord` "위도와 경도는 함께 입력하세요") | Market · 펼친 모습 "위도와 경도는 함께 넣어 주세요" | — | 있음 |
| 150 | 예상 시기 형식 (`page.G6.loc.badYm`) | Market · 펼친 모습 "예상 시기는 YYYY-MM 모양으로 넣어 주세요" | — | 있음 |
| 151 | 영향 범위 필수 (`page.G6.loc.needTarget` "영향 생활권·단지를 하나 이상 고르세요(좌표만으로는 연결하지 않습니다)") | Market · 펼친 모습 "영향 받는 생활권이나 단지를 하나 이상 골라 주세요 (좌표만으로는 연결하지 않아요)" | — | 있음 |
| 152 | 서버 오류 (`page.common.loadError`) | Market · 펼친 모습 "불러오지 못했어요: [서버 오류 내용]" | — | 있음 |
| 153 | 저장 뒤 폼 닫힘 (`setOpenId(null)`) | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 154 | 연결 결과 표 caption (`page.G6.loc.links` "{name} 단지 연결") | Market · 펼친 모습 "위치 확인 저장 뒤 · 단지 연결 결과" caption "[소식 이름] 단지 연결" | — | 있음 |
| 155 | 결과 표 열: 단지 (`page.G6.loc.col.complex`) + 목록에 없으면 (`page.G6.loc.unknownComplex` "(목록에 없는 단지)") | Market · 펼친 모습 결과 표 "단지" · "(목록에 없는 단지)" | — | 있음 |
| 156 | 결과 표 열: 거리 FactCell m (`page.G6.loc.col.distance`; 좌표 없으면 '확인 불가(<서버 근거>)') | Market · 펼친 모습 결과 표 "거리" "[n]m 추정" · "확인 불가(같은 생활권(계양구, 단지 좌표 없음))" | — | 있음 |
| 157 | 거리 사유가 서버에 없을 때 폴백 (`page.G6.loc.noCoord` "단지 좌표 없음 — 같은 생활권 가중치 1") | — | — | 있음(고침 MK-16 — 결과 표 마지막 줄 "확인 불가(단지 좌표 없음 — 같은 생활권 가중치 1)") |
| 158 | 결과 표 열: 가중치 (`page.G6.loc.col.weight`, 소수 2자리, null → `page.common.none` "없음") | Market · 펼친 모습 결과 표 "계산 계수 (가중치)" "[0.00]" · "1.00" · "없음" | 가중치 → 계산 계수 (가중치) | 있음 |
| 159 | 결과 표 열: 연결 근거 (`page.G6.loc.col.reason`) — 생활권 id를 이름으로 바꿈 (`livingAreaReason`) | Market · 펼친 모습 결과 표 "연결 근거" "같은 생활권(계양구, 단지 좌표 없음)" | — | 있음 |
| 160 | 연결 0곳 (`page.G6.loc.noLinks` "위치를 확인했지만 연결된 단지가 없습니다") | Market · 펼친 모습 "연결 단지가 0곳이면: '위치를 확인했지만 연결된 단지가 없어요'" | — | 있음 |
| 161 | 취소 뒤 (`page.G6.loc.cleared` "위치 확인을 취소했습니다 — 단지 연결을 지웠습니다") | Market · 펼친 모습 "취소하면: '위치 확인을 취소했어요 — 단지 연결을 지웠어요'" | — | 있음 |
| 162 | 발행 잡 안내 (`page.G6.loc.jobHint` "위치·좌표·예정월·연결 중 바뀐 값이 있어 새 리비전 발행 잡이 등록됐습니다") | Market · 펼친 모습 "바뀐 값이 있어 새 수정본 발행 작업을 등록했어요" + 폼 "저장하면 새 수정본을 만들어 발행해요" | — | 있음 |
| 163 | 바뀐 것 없음 (`page.G6.loc.unchanged` "발행할 변경이 없습니다…") | Market · 펼친 모습 "바뀐 것이 없으면: '발행할 변경이 없어요 — 지금 화면 그대로예요'" | 좌표 6자리 비교 설명 생략 | 있음 |
| 164 | 결과·진행이 리비전 전환으로 패널이 다시 그려져도 남음 (MarketPage가 보관) | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 165 | 다른 지역으로 바꾸면 결과·진행·열린 폼 지움 (8차 m18) | Market · 펼친 모습 "다른 지역으로 바꾸면 이 결과와 진행 상태는 사라져요" | — | 문구로만 |
| 166 | API `GET /snapshots/{sid}/complexes?page=1&size=1000&sort=name` (단지 이름·선택지) | Market · 열린 폼 "영향 받는 단지" 선택지(호출 주체) | — | 있음 |
| 167 | API `PATCH /catalysts/{id}` {location_confirmed, lat?, lon?, expected_ym?, living_area_ids, complex_ids} (`useUpdateCatalystLocation`) | Market · "위치 확인하고 단지와 연결" · "위치 확인 취소"(호출 주체) | — | 있음 |

## 새 개발 소식 주소 넣기 (CatalystUrlForm)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 168 | Section·폼 aria-label (`page.G6.catalyst.title` "호재 URL 입력") | Market · "편집하는 사람용 · 새 개발 소식을 알고 있나요?" "(공식 이름: 호재 URL 입력)" | — | 있음 |
| 169 | 안내 (`page.G6.catalyst.intro` "공개 기사·공고 주소를 넣으면…개인정보는 넣지 마세요.") | Market · 같은 섹션 안내 | 호재 후보 → 개발 소식 후보 | 있음 |
| 170 | 주소 입력칸 type=url placeholder "https://" (`page.G6.catalyst.url` "주소(http:// 또는 https://)") | Market · "주소 (http:// 또는 https://)" | — | 있음 |
| 171 | 제목 입력칸 maxLength 200 (`page.G6.catalyst.titleField` "제목(필수, 200자 이내)") | Market · "제목 (꼭 넣기 · 200자 이내)" | 필수 → 꼭 넣기 | 있음 |
| 172 | 발췌 textarea maxLength 2000 (`page.G6.catalyst.excerpt` "발췌(선택, 2000자 이내)") | Market · "발췌 (선택 · 2,000자 이내)" | — | 있음 |
| 173 | 저장 버튼 (`page.G6.catalyst.submit` "호재 후보 저장") | Market · "후보로 저장" | 호재 후보 저장 → 후보로 저장 | 있음 |
| 174 | 읽기 전용: 입력칸·버튼 꺼짐 + title | Market · "읽기 전용으로 들어오면 입력칸과 버튼이 꺼져요." | — | 문구로만 |
| 175 | 지역이 없으면(regionId null) 꺼짐 | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 176 | 저장 중 버튼 꺼짐 (`create.isPending`) | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 177 | 주소 오류 (`page.G6.catalyst.badUrl` "주소는 http:// 또는 https:// 로 시작하는 공개 페이지여야 합니다") | Market · 펼친 모습 "개발 소식 주소 넣기 · 오류와 저장 뒤" 같은 문구 | — | 있음 |
| 178 | 제목 없음 (`page.G6.catalyst.titleRequired` "제목을 입력하세요") | Market · 펼친 모습 "제목을 넣어 주세요" | — | 있음 |
| 179 | 서버 오류 (`page.common.loadError`) | Market · 펼친 모습 "불러오지 못했어요: [서버 오류 내용]" | — | 있음 |
| 180 | 저장 완료 role=status (`page.G6.catalyst.saved` "호재 후보를 저장했습니다: {name}") | Market · 펼친 모습 "개발 소식 후보를 저장했어요: [제목]" | — | 있음 |
| 181 | 분류 잡 → 발행까지 진행 PublishJobProgress (`job_id`) | Market · 펼친 모습 "작업 진행 [분류 작업] 대기" | — | 있음 |
| 182 | 잡 없음 (`page.G6.catalyst.noJob` "이 지역에 스냅샷이 없어 분류 잡을 등록하지 않았습니다…") | Market · 펼친 모습 "이 지역에 기준일 자료가 없으면: '분류 작업을 등록하지 않았어요 — 다음 자동 수집 때 분류해요'" | — | 있음 |
| 183 | 저장 뒤 입력칸 비움 | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 184 | 화면 로딩 중에는 폼을 그리지 않음 (`isLoading`) | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 185 | 지역이 바뀌면 폼·결과·진행 지움 (`key={regionId}`) | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 186 | API `POST /catalysts` {region_id, url, title(≤200), excerpt(≤2000)\|null} (`useCreateCatalyst`) | Market · "후보로 저장"(호출 주체) | — | 있음 |

## 작업 진행 (PublishJobProgress · JobProgressView · JobRequeueNote — 위치 확인·주소 넣기 공통)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 187 | 진행 제목 + 잡 이름 (`job.title` "작업 진행" + `job_name`) | Market · 펼친 모습 "작업 진행 새 수정본 발행" | snapshot.publish → 새 수정본 발행 | 있음 |
| 188 | 발행 대기 안내 (`job.publishPending`) | Market · 펼친 모습 "새 수정본이 발행될 때까지 화면은 지금 수정본을 보여요" | 리비전 → 수정본 | 있음 |
| 189 | 상태 대기 (`job.status.queued`) | Market · "작업 진행 · 상태 모음" "대기 순서를 기다려요" | — | 있음 |
| 190 | 상태 실행 중 + 진행 수·단계 (`job.status.running`, `job.progress`, `job.step`) | Market · "상태 모음" "실행 중 [n]/[m] · 단계 [단계 이름]" | — | 있음 |
| 191 | 진행 막대(결정) aria-label=상태 | Market · 펼친 모습 role=progressbar aria-label "실행 중" | — | 있음 |
| 192 | 진행 수 없을 때 미정 막대 | — | — | 있음(고침 MK-11 — "상태 모음" 줄무늬 미정 막대) |
| 193 | 발행 완료 (`job.status.done` + `job.publishDone` "새 리비전이 발행됐습니다 — 화면 기본이 새 리비전으로 바뀝니다") | Market · "상태 모음" "완료 새 수정본이 발행됐어요 — 화면이 새 수정본으로 바뀌어요" | — | 있음 |
| 194 | 실패 + 오류 (`job.status.failed`, `job.error` "오류: {detail}") | Market · "상태 모음" "실패 오류: [오류 내용]" | — | 있음 |
| 195 | 발행 실패 (`job.publishFailed` "…화면은 지금 발행 리비전을 계속 보입니다: {detail}") | Market · "상태 모음" "화면은 지금 수정본을 계속 보여요" | — | 있음 |
| 196 | 빈 데이터셋 상한 실패 (`job.degradedFailed`) | Market · "상태 모음" "다시 모아도 자료가 불완전해 멈췄으면 '발행하지 않았어요: [사유]'" | — | 있음 |
| 197 | 잡 없음 (`job.none` "진행 중인 작업 없음") | Market · "상태 모음" "없음 작업을 아직 못 받았으면 '진행 중인 작업 없음'" | — | 있음 |
| 198 | 발행 예외 재시도 (`job.requeuedError`) | Market · "상태 모음" "다시 시도 발행 중 오류가 나 다시 시도하는 중([n]/[max]회) — 아직 실패가 아니에요" | — | 있음 |
| 199 | 조회 일시 오류 (`job.retrying`) | Market · "상태 모음" "상태를 못 받으면 '다시 확인하는 중'" | — | 있음 |
| 200 | 잡을 받기 전 조회 오류 (`error && !job` → `job.error`) | — | — | 있음(고침 MK-13 — "상태 모음" "조회 오류" 줄) |
| 201 | 발행 막힘 — 남은 모순 주장 수 (`job.publishBlockedContradicted`) | Market · "상태 모음" "막힘 발행이 막혔어요(남은 모순 주장 [n]건) — 데이터·운영 화면에서 고치면 다시 발행돼요" | — | 있음 |
| 202 | 발행 막힘 — 서버 사유 (`job.publishBlocked` "…: {detail}") | Ops · 펼친 모습 "①③⑦ 작업 진행 칸의 다른 문구" "발행이 막혔어요(남은 모순 주장 등) — … [설명]" | — | 다른 보드(Ops) |
| 203 | 발행 막힘 — 사유 모름 (`job.publishBlockedUnknown`) | Ops · 펼친 모습 같은 줄 "이유 확인 불가" | — | 다른 보드(Ops) |
| 204 | 30분 상한 멈춤 (`job.publishExpired`) | Market · "상태 모음" "멈춤 30분 동안 끝을 확인하지 못해 확인을 멈췄어요 — 기준일 목록에서 확인하세요" | — | 있음 |
| 205 | 사슬 상한 멈춤 (`job.publishChainCapped` "발행 작업을 {n}단계까지 따라갔지만…") | Market · "상태 모음" "발행 작업을 [n]단계까지 따라갔지만 끝을 확인하지 못했을 때도 같아요" | — | 있음 |
| 206 | 발행 busy 재큐잉 (`job.requeued`) | Market · "상태 모음" "기다림 같은 수정본의 다른 발행이 끝나길 기다리는 중(다시 대기 [n]회) — 실패가 아니에요" | — | 있음 |
| 207 | 빈 데이터셋 재큐잉 (`job.requeuedDegraded` + `job.requeuedAt`) | Market · "상태 모음" "수집 자료가 불완전하면 다시 모으는 중([n]/[max]회, [시각] 이후)" | — | 있음 |
| 208 | 재큐잉 시각 없음 (`job.requeuedSoon` "곧 다시 시도") | — | — | 있음(고침 MK-12 — "상태 모음" "곧 다시 시도") |
| 209 | 일일 수집 재큐잉 안내 (`job.requeuedDegradedDaily` "이전 발행 리비전이 그대로 기본 화면입니다.") | Market · "상태 모음" "— 이전 수정본이 그대로 기본 화면이에요" | — | 있음 |
| 210 | 첫 적재 재큐잉 안내 (`job.requeuedDegradedBootstrap`) | RegionNew · 펼친 모습 "진행 상황 · 상태별 모습" | — | 다른 보드(RegionNew) |
| 211 | 미룸 (`job.publishDeferred`) | Market · "상태 모음" "미뤄짐 이 변경은 지금 판정 중인 새 수정본에 들어가 함께 반영돼요" | — | 있음 |
| 212 | 재등록 (`job.publishRedeferred`) | Market · "상태 모음" "미뤄 둔 수정본 발행이 끝내 실패하면 새 발행 작업으로 다시 등록하고 이어서 보여 줘요" | — | 있음 |
| 213 | 사슬의 후속 잡(rejudge → publish …)마다 진행 줄 추가 (`chain.slice(1)` JobProgressView) | Market · "상태 모음" "발행 작업을 [n]단계까지 따라갔지만…" (후속 잡 줄은 그리지 않음) | — | 문구로만 |
| 214 | 1분마다 상한 다시 계산 (미룸·겹친 발행 뒤에도 30분 상한 알림) | — | — | 문구로만(고침 MK-17 — "구현 때 유지" 상자) |
| 215 | API `GET /jobs/{id}` 사슬 폴링 + `GET /regions/{id}/snapshots` (발행 확인) | Market · "작업 진행"(호출 주체) | — | 있음 |
| 216 | 숫자를 누르면 출처 창이 열림(FactCell 공통) | Market · 머리 "밑줄 점선이 있는 숫자를 누르면 출처가 열려요" + 맨 아래 범례 (출처 창 그림은 Shell) | — | 문구로만 |

요약: 전체 216 · 있음 191 · 문구로만 21 · 다른 보드 4 (Detail 1 · Ops 2 · RegionNew 1) · 빠짐 0 (2026-10-16 고침 반영 — fixes/fixes-Market.md)

빠짐 목록: 없음 (2026-10-16 고침 반영)
- 고침 전 빠짐 27개: #10·#13 → 있음(MK-15), #46 → 있음(MK-10), #56 → 있음(MK-5), #93 → 있음(MK-8), #125 → 있음(MK-9), #157 → 있음(MK-16), #192 → 있음(MK-11), #200 → 있음(MK-13), #208 → 있음(MK-12), #139 → 있음(재확인, 보드에 이미 있었음)
- #73·#75 → 문구로만(MK-6 안내)
- #5·#14·#31·#134·#136·#145·#153·#164·#175·#176·#183·#184·#185·#214 → 문구로만(MK-17 "구현 때 유지" 상자)

## 새로 더한 것 (기존에 없던 것)

| # | 새 기능 | 위치 (보드 · 섹션) | 비고 |
|---|---|---|---|
| N1 | 맥락 줄 "인천 · 기준일 2026년 10월 14일 (7번째 수정본) · 상대 비교예요, 투자 권유가 아니에요" + 안내 문단 | 머리 | 지금은 intro 없음 |
| N2 | 생활권 `?` 설명 버튼 + "생활권 = 생활이 이어지는 동네 묶음이에요." + "묶음 바꾸기" 링크(생활권 편집) | 머리 | |
| N3 | 요약 카드 4장: 안 팔린 집(합계·준공 후·가장 많은 곳) · 입주가 가장 몰리는 해(+다음 해) · 생활권별 실거래 중간 값 최고/최저 · 규제지역 여부(+상한제 생활권) | "한눈에 보기" | 고침 MK-1: 최대·최소 고르기와 생활권 값 더하기를 뺌 — 서버 값(지역 합계는 대시보드 kpi.unsold, "API 필요" 표시)과 줄 개수만 |
| N4 | 섹션마다 `?` 설명 버튼(근처 새 아파트·표본·입주 물량·미분양·규제지역·분양가 상한제·호재 단계·호재 위치 확인) | 각 섹션 제목 | 용어 설명 팝오버 |
| N5 | C03 읽는 법 안내 "까만 점(분양가)에서 파란 점까지 오른쪽으로 길수록…" + 오른쪽 열 "한 해 평균 변화" | 근처 새 아파트 | |
| N6 | C03 처음 11줄만 + "121줄 모두 보기" 버튼, 줄 수 설명 "121줄 중 11줄 (자기 생활권 40줄 + 대신 채운 줄 81줄)" | 근처 새 아파트 | 접기 |
| N7 | C05 구 고르기 select "어느 구를 볼까요?" | 안 팔린 집 | 지금은 자동 선택만 |
| N8 | C05 "2026년 8월, 구마다 몇 세대가 안 팔렸나요?" 구별 가로 막대 + 구 이름 개편 안내 | 안 팔린 집 | 새 그림 |
| N9 | ~~C04 막대 위 연도 합계 숫자~~(고침 MK-3에서 뺌 — 화면 합계), 범례 6위 이하 "나머지 n곳" 묶음 | 입주 물량 | 고침 MK-3 |
| N10 | 규제 요약 알약 "'비규제' 9곳"(고침 MK-8에서 "9곳 모두 아님"을 개수 문구로) · "분양가 상한제 3곳 적용" + 생활권별 표로 바꿈 | 규제 | 개수 세기(D25-3) |
| N11 | 시세 표 "값 범위 (0 ~ 15억)" 막대 열 + 중간 값 높은 순 정렬 + "옹진군은 이 표에 없어요 (자료 없음)" | 생활권마다 실거래 값 | 정렬은 화면 동작(지금은 서버 순서) |
| N12 | C09 항목에 "판정기 확신 {n}% 추정" + "기사 원문" 링크, 단계 열 번호(1~5)·건수 | 개발 소식 단계 | |
| N13 | 타임라인 빈 안내 "확정 단계이면서 예상 시기가 있는 소식이 아직 없어 비어 있어요" | 개발 소식 단계 | 지금은 그리지 않음 |
| N14 | "편집하는 사람용" 표시, 위도·경도 placeholder 예시, 다중 선택 Ctrl 안내, "저장하면 새 수정본을 만들어 발행해요" | 위치 확인 | |
| N15 | 진행 "멈춤" 줄의 "다시 확인" 버튼 | 작업 진행 · 상태 모음 | 지금은 머리줄(Header `job.watchRecheck`)에만 있음 |
| N16 | 맨 아래 면책 "이 화면은 개인의 청약 자격을 판정하지 않아요. 최종 기준은 입주자 모집 공고문이에요." + 라벨 범례(확인됨·추정) | 새 개발 소식 아래 | 지금 G6은 `legend` 없음 |
