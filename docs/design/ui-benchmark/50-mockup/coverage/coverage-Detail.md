# 대응표 — G3 단지 상세 → Detail.dc.html + DetailTabs.dc.html + Mobile.dc.html

- 현재 소스: `frontend/src/pages/complex/` 전체(index.tsx · tabs.tsx · ComplexHeader.tsx · JudgmentsTab.tsx · ProvenanceTab.tsx · CompetitionSummaryLine.tsx · useHashTab.ts) + 차트 `charts/C01` · `C02` · `C08` · `C09` · `ChartFrame.tsx` + 쓰는 공통 부품(`pages/_shared` · `components/*` · `layout/PageShell.tsx`) + `i18n/ko.json`
- 보드: `boards/Detail.dc.html`(기본 보드) · `boards/DetailTabs.dc.html`(기본 보드에 없는 부분 · 탭 2~7 · 다른 상태 · 휴대폰) · `boards/Mobile.dc.html`(휴대폰 상세)
- 보드 칸에는 셋 중 어느 보드인지 적는다. 공통 부품(출처 창 · 용어 창 · 불러오기/오류)은 `Shell` 보드에 있어 `다른 보드(Shell)`로 적는다.
- 경로는 `frontend/src/` 기준. API 줄은 "그 응답이 그리는 칸이 보드에 있으면 있음"으로 적었다(목업은 호출을 그리지 않는다).
- "문구로만" = 보드에 그림 없이 설명 글로만 있음. 동작(키보드·해시·스크롤)은 그림이 안 되므로 설명이 있으면 문구로만, 없으면 빠짐.

## 1. 화면 틀 · 데이터 (`pages/complex/index.tsx`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 1 | h1 제목 (`index.tsx` PageShell · `page.G3.title` "단지 상세") | Detail · 현재 위치 줄 "단지 찾기 › 시티오씨엘 8단지" / Mobile · 위 막대 "단지 상세" | h1 → 현재 위치 줄(데스크톱) | 있음 |
| 2 | 목록으로 링크, 전역 쿼리 유지 (`index.tsx` · `page.common.backToList` "단지 리스트로") | DetailTabs · 머리 "단지 목록으로" / Detail · 현재 위치 줄 "단지 찾기" / Mobile · "뒤로" | 단지 리스트로 → 단지 목록으로 | 있음 |
| 3 | 출처 범례 한 줄 (`layout/PageShell.tsx` legend → `components/ProvenanceLegend.tsx` · `label.legend` "밑줄 친 숫자를 누르면 출처·확인일이 열립니다") | Detail · 바닥 문구 "… 숫자를 누르면 출처가 열려요" / DetailTabs · 바닥 문구 | → 점선 밑줄 숫자를 누르면 출처가 열려요 | 있음 |
| 4 | 라벨 뜻 펼침 ⓘ + 정의 6개 (`ProvenanceLegend.tsx` · `label.legendHelp` "라벨 뜻", `label.help.*`) | DetailTabs · 바닥 "라벨 뜻 보기" + Shell · 3 펼친 모습 | 라벨 뜻 ⓘ → 라벨 뜻 보기 | 있음 |
| 5 | 라벨 뜻 Esc 로 닫기 (`ProvenanceLegend.tsx` onKeyDown) | Detail · "구현할 때 지금 동작 그대로 유지" 상자 |  | 문구로만(고침 DT-7) |
| 6 | 불러오는 중 (`pages/_shared` QueryState · `app.loading` "불러오는 중…") | Shell · 7 "불러오는 중…" | | 다른 보드(Shell) |
| 7 | 불러오기 오류 (`_shared` QueryError · `page.common.loadError` "불러오지 못했습니다: {detail}") | Shell · 7 "불러오지 못했어요 · 다시 시도" | 지금 일반 오류엔 다시 시도 버튼 없음(목업은 있음) | 다른 보드(Shell) |
| 8 | 발행 리비전 준비 중 · 자동 재시도 · 다시 시도 (`_shared` MaterializePending · `page.common.materializePending` / `materializePendingStill` / `app.retry`) | Shell · 7 "이 기준일 결과를 만드는 중이에요 … 다시 시도" | | 다른 보드(Shell) |
| 9 | 발행 뒤 만든 시나리오 결과 없음 + 실행 링크 (`_shared` isScenarioMissing · `page.common.scenarioMissing` / `scenarioMissingRun`) | Shell · 7 "이 상황의 결과가 아직 없어요 · 내 조건 화면에서 실행하기" | | 다른 보드(Shell) |
| 10 | 저장본 검증 실패 (`lib/errorText.ts` · `page.common.storedViewMismatch`) | Shell · 7 "보던 기준일과 저장된 화면이 다를 때도 안내가 떠요" | | 다른 보드(Shell) |
| 11 | API `GET /complexes/{id}?snapshot=&scenario=` (`api/hooks.ts` useComplexDetail) | Detail · DetailTabs · Mobile 전체(실데이터 값) | | 있음 |

## 2. 탭 (`index.tsx` · `useHashTab.ts`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 12 | 가로 탭 줄 role=tablist · aria-selected · aria-controls · tabIndex (`index.tsx` · `page.G3.tabs` "단지 상세 탭") | Detail · "자세히 보기" 탭 줄 / DetailTabs · 탭 줄(aria-label 단지 상세 탭) | | 있음 |
| 13 | 탭 1 (`page.G3.tab.price` "타입별 가격") | Detail · 자세히 보기 "평형별 가격" / DetailTabs · 탭 줄 | 타입별 가격 → 평형별 가격 | 있음 |
| 14 | 탭 2 (`page.G3.tab.payment` "내야 할 돈·일정") | Detail · DetailTabs · 탭 줄 "납부 일정 전체" | → 납부 일정 전체 | 있음 |
| 15 | 탭 3 (`page.G3.tab.events` "경쟁률·추가 모집") | Detail · DetailTabs · 탭 줄 "경쟁률 전체" | → 경쟁률 전체 | 있음 |
| 16 | 탭 4 (`page.G3.tab.gap` "주변 시세 비교") | Detail · 탭 줄 "주변 실거래" / DetailTabs · 탭 줄 "주변 시세 비교" | Detail 에서만 → 주변 실거래 | 있음 |
| 17 | 탭 5 (`page.G3.tab.ladder` "가격 전망(판정기)") | Detail · 탭 줄 "가격 전망" / DetailTabs "가격 전망 (판정기)" | | 있음 |
| 18 | 탭 6 (`page.G3.tab.catalysts` "개발 소식(호재)") | Detail · DetailTabs · 탭 줄 "개발 소식" | 개발 소식(호재) → 개발 소식 | 있음 |
| 19 | 탭 7 (`page.G3.tab.provenance` "근거 원문") | Detail · DetailTabs · 탭 줄 "출처·원문" | 근거 원문 → 출처·원문 | 있음 |
| 20 | 보이는 탭 순서(주변 시세 비교 → 가격 전망, `G3_VISIBLE_TABS`) | Detail · DetailTabs · 탭 줄 같은 순서 | | 있음 |
| 21 | 빈 호재 탭 이름 "(0)" (`page.G3.tab.countZero` "{name} (0)") | DetailTabs · 탭 줄 "개발 소식 (0)" · 휴대폰 고르기 상자 | | 있음 |
| 22 | 탭 = URL 해시 `#payment`, replace (`useHashTab.ts`) | DetailTabs · 탭 줄 아래 안내 "탭은 주소 끝(#payment 처럼)에 기억돼요" |  | 문구로만(고침 DX-13) |
| 23 | G1 변경 피드 ChangeEvent.tab 해시로 해당 탭 바로 열기 (`G3_TABS`) | DetailTabs · 같은 안내 "홈의 '바뀐 것' 알림을 누르면 해당 탭이 바로 열려요" |  | 문구로만(고침 DX-13) |
| 24 | 모르는 해시면 첫 탭 (`useHashTab.ts`) | Detail · "구현할 때 지금 동작 그대로 유지" 상자 |  | 문구로만(고침 DT-7) |
| 25 | `#judgments` → 근거 원문 탭 + 판정 기록 구획 자동 펼침 (`index.tsx` details open) | Detail · "구현할 때 지금 동작 그대로 유지" 상자 |  | 문구로만(고침 DT-7) |
| 26 | 키보드 ← → 탭 이동(끝에서 돌아감, 포커스 이동) (`index.tsx` onKeyDown) | DetailTabs · 탭 줄 아래 안내 "키보드 ←→로 탭을 옮길 수 있어요" |  | 문구로만(고침 DX-13) |
| 27 | 활성 탭만 마운트 · 근거 원문은 열 때 처음 로드 (`index.tsx`) | DetailTabs · 탭 7 "원문은 이 탭을 열 때 처음 불러와요" |  | 문구로만(고침 DX-13) |
| 28 | 모바일 탭 고르기 상자 (`index.tsx` isMobile · `page.G3.tabSelect` "보기", aria-label `page.G3.tabs`) | DetailTabs · 휴대폰 "보기 [고르기 상자]" / Mobile · "더 자세히" 고르기 상자 | 보기 → 더 자세히(Mobile) | 있음 |
| 29 | 탭 패널 role=tabpanel · aria-labelledby(모바일은 aria-label=탭 이름) (`index.tsx`) | Detail · "구현할 때 지금 동작 그대로 유지" 상자 |  | 문구로만(고침 DT-7) |
| 30 | 판정 기록 접힌 구획(근거 원문 탭 안) (`index.tsx` details · `page.G3.tab.judgments` "판정 기록(운영자용)") | DetailTabs · 탭 7 아래 접힘 "판정 기록 (운영자용) · … 기록 10건" | | 있음 |

## 3. 머리 — 단지 (`ComplexHeader.tsx` 1단)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 31 | 3단 머리 구조(단지 → 지금 상태 → 돈 · 조건 → 점수, `data-tier`) (`ComplexHeader.tsx`) | Detail · 머리 카드 → "언제, 얼마를 내야 하나요?" → "청약 전에 꼭 확인할 조건" → "일정은 어디쯤 왔나요?" → "작년 청약 때 얼마나 몰렸나요?" → "점수는 왜 이렇게 나왔나요?" → "자세히 보기" | 3단 머리 → 질문형 섹션(일정 · 경쟁률은 따로 섹션) | 있음 |
| 32 | 단지 이름 h2 (`ComplexHeader.tsx`) | Detail · 머리 카드 이름 / Mobile · 이름 | h2 → h1 | 있음 |
| 33 | 이름 누르면 이름 출처 서랍 (`_shared` NameWithProvenance · `page.common.nameProv.open` "이름 출처 보기: {name} · {label}") | DetailTabs · "이름·상태 줄에 더할 것" "← 이름을 누르면 이름의 출처(청약홈 공고)가 열려요" (title 이름 출처 보기: … · 확인됨) | | 있음 |
| 34 | 이름 라벨 배지 확인됨 / 비공식 (`_shared` NameWithProvenance · LabelBadge) | DetailTabs · 이름·상태 줄 "확인됨" · "아직 청약홈 공고 전" 예시 "[단지 이름] 비공식" | | 있음 |
| 35 | 공고 예정 후보 배지(트랙 A, applyhome_id 없음) (`page.G3.header.upcoming` "공고 예정 후보(청약홈 미등록)") | DetailTabs · "다른 단지일 때 · 아직 청약홈 공고 전" "공고 예정 후보 (청약홈에 아직 없음)" | 미등록 → 아직 없음 | 있음 |
| 36 | 공고 전 배지(트랙 A 아님) (`page.G3.header.preNotice` "공고 전(청약홈 미등록)") | DetailTabs · 같은 곳 "공고 전 (청약홈에 아직 없음)" | | 있음 |
| 37 | 배지 title 안내 (`page.G3.header.upcomingHint`) | DetailTabs · 같은 곳 설명 문단 + title "청약홈 공고 전 단지예요" | title → 보이는 설명 | 있음 |
| 38 | 공고문 원문 보기 버튼 → 공고일 출처 서랍 (`ComplexHeader.tsx` notice-original · `page.G3.summary.noticeOriginal`) | Detail · 머리 카드 "모집 공고문 원문 (PDF)" / DetailTabs "공고문 원문 보기" / Mobile "모집 공고문 원문 보기" | 지금은 출처 서랍을 연다 — 목업 이름엔 'PDF' | 있음 |
| 39 | 공식 홈페이지 외부 링크 (`components/ExternalLink.tsx` · `page.G3.header.officialSite`) | Detail · 머리 카드 "공식 홈페이지" / DetailTabs | | 있음 |
| 40 | 생활권 이름 (`header.living_area_name` → `living_area`) | Detail · 이름 아래 줄 "생활권 미추홀구 · 총 …" / Mobile · 이름 아래 "생활권 미추홀구" |  | 있음(고침 DT-2 · MB-2) |
| 41 | 총 세대 (`page.G3.summary.unitsTotal` "총") | Detail · 이름 아래 줄 "총 1,349세대" / Mobile "1,349세대" | | 있음 |
| 42 | 입주 (`page.G3.header.moveIn` "입주") | Detail · 이름 아래 줄 "입주 2029년 7월" / Mobile "입주 2029.07" | | 있음 |
| 43 | 주소 한 줄(없으면 `empty.unknown`) (`page.G3.header.address` "주소") | DetailTabs · 이름·상태 줄 "주소 …" | | 있음 |
| 44 | 모바일 주소 접힘 (`page.G3.summary.info` "단지 정보") | DetailTabs · 휴대폰 "[단지 정보] 주소 …" / Mobile · 이름 아래 "단지 정보" 접힘 |  | 있음(고침 MB-2) |

## 4. 머리 — 지금 상태 (`ComplexHeader.tsx` 1단 · `CompetitionSummaryLine.tsx`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 45 | 구획 제목 (`page.G3.summary.status` "지금 상태") | Detail · 머리 카드 맨 위 상태 줄 / Mobile · 맨 위 | 지금 상태(구획) → 이름 위 상태 줄 | 있음 |
| 46 | 접수 상태 배지 상태 · 경로 · 공급 종류 · 확인일 title (`components/IntakeBadge.tsx` · `intake.status.*` / `intake.path.*` / `intake.withSupply`) | Detail · 상태 줄 "지금 접수 가능 · 무순위 · 선착순 계약 · 공식 홈페이지 10월 13일 확인" / DetailTabs "공식 홈페이지 화면을 찍어 확인 · 10월 13일 19:28" / Mobile | 접수 가능 → 지금 접수 가능, 렌더 캡처 → 공식 홈페이지 화면을 찍어 확인 | 있음 |
| 47 | 접수 상태 없음 (`intake.none` "접수 상태 확인 불가") | DetailTabs · 다른 단지 예시 "접수 상태 확인 못 함" / Shell · 4 | → 접수 상태 확인 못 함 | 있음 |
| 48 | 확인 불가 · 불가 사유와 날짜(쉬운 말, 원 사유 title) (`IntakeBadge.tsx` · `intake.withReasonDate`) | DetailTabs · 이름·상태 줄 "다른 단지일 때 · 접수 상태를 확인 못 함" "접수 상태 확인 못 함(자동 확인이 끝나지 않음, 2026-10-14)" |  | 있음(고침 DX-1) |
| 49 | 접수 상태 용어 ⓘ (`components/Term.tsx` · glossary `intake_status`) | DetailTabs · 이름·상태 줄 "접수 상태 뜻 보기 ?" | ⓘ → ? | 있음 |
| 50 | 접수 근거 원문 버튼 → 원문 출처 서랍 (`page.G3.header.intakeEvidence` "접수 근거 원문") | DetailTabs · 이름·상태 줄 "접수 근거 원문 보기 (홈페이지 화면)" | | 있음 |
| 51 | 다른 단지 홈페이지 원문 버튼 (`page.G3.header.siteOtherEvidence`) | DetailTabs · "다른 단지일 때 · 공식 홈페이지가 다른 단지 페이지" | | 있음 |
| 52 | 동일성 미확인 원문 버튼 (`page.G3.header.siteUnconfirmedEvidence`) | DetailTabs · "다른 단지일 때 · 같은 단지 페이지인지 확인 전" | 동일성 미확인 → 같은 단지인지 확인 전 | 있음 |
| 53 | 현재 적용 공고 (`page.G3.summary.currentNotice` "현재 적용 공고: {kind}") | DetailTabs · 이름·상태 줄 "지금 적용 중인 공고 · 무순위 공고 (2026.01.26부터 적용)" | | 있음 |
| 54 | 다른 단지 안내 + 사람 확인 링크(G7 폼, intake_status) (`page.G3.header.siteOtherHint` / `siteOtherHumanCheck`) | DetailTabs · "공식 홈페이지가 다른 단지 페이지" 문단 + "접수 상태 사람 확인하기 →" | | 있음 |
| 55 | 동일성 미확인 안내 + 같은 링크 (`page.G3.header.siteUnconfirmedHint`) | DetailTabs · "같은 단지 페이지인지 확인 전" 문단 + 링크 | | 있음 |
| 56 | 머리 경쟁률 요약 — 최고 경쟁률 + 그 주택형 (`CompetitionSummaryLine.tsx` · `page.G3.competition.maxRatio` "최고 경쟁률(1순위 해당지역)") | Detail · "작년 청약 때 얼마나 몰렸나요?" 타입별 1순위 경쟁률 목록(59㎡ 6.22 대 1 맨 위) | 최고 경쟁률 한 값 → 타입별 경쟁률 목록 | 있음 |
| 57 | 머리 경쟁률 요약 — 미달 주택형 수 (`page.G3.competition.shortfallTypes` "미달 주택형") | Detail · 같은 곳 "신청이 모자랐던 타입 8개 중 5개" | 미달 주택형 → 신청이 모자랐던 타입 | 있음 |
| 58 | 요약 기준 문구 title (`summary.basis`) | Detail · 같은 곳 부제 "1순위 · 인천 거주자 접수 기준 · 청약홈" | title → 보이는 부제 | 있음 |
| 59 | 기준 행 없으면 서버 '확인 불가(사유)' (`CompetitionSummaryLine.tsx`) | Detail · "작년 청약 때 얼마나 몰렸나요?" 아래 "기준 줄이 없는 단지: 최고 경쟁률 확인 불가(서버가 준 사유)" |  | 있음(고침 DT-6) |
| 60 | 일정 — 접수 일정 줄(종류 · 시작~끝, D±) (`ComplexHeader.tsx` ScheduleRow · `page.G3.summary.schedule` "일정") | Detail · "일정은 어디쯤 왔나요?" / DetailTabs · 이름·상태 줄 "접수 일정"(특별공급 · 1순위 지역 거주자 …) / Mobile · 일정 | 일정 → 일정은 어디쯤 왔나요? | 있음 |
| 61 | 일정 없음 (`page.G3.summary.noScheduleReason` "공고 일정 미수집") | DetailTabs · 돈 카드 "다른 단지일 때 나오는 메모" "접수 일정 확인 불가(공고 일정을 아직 못 모음)" | | 있음 |
| 62 | 당첨자 발표 (`page.G3.summary.winnerDate`) | Detail · 일정 "당첨자 발표 2025.12.09" / DetailTabs "당첨자 발표 · 계약" / Mobile | | 있음 |
| 63 | 계약 일정(있을 때만) (`page.G3.summary.contract` "계약") | Detail · 일정 "정당 계약 2025.12.21 ~ 24" / DetailTabs / Mobile | 계약 → 정당 계약 | 있음 |

## 5. 머리 — 내야 할 돈 (`ComplexHeader.tsx` 2단 · `tabs.tsx` 할인 · 보류 부품)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 64 | 구획 (`page.G3.summary.money` "내야 할 돈") | Detail · "언제, 얼마를 내야 하나요?" / Mobile · "언제, 얼마를 내나요?" | 내야 할 돈 → 언제, 얼마를 내야 하나요? | 있음 |
| 65 | 현재 구매가 낮은~높은 (`page.G3.header.price` "현재 구매가") | Detail · 머리 카드 "분양가 · 84C타입 … 5억 9,850만 ~ 6억 5,090만원" / Mobile | 현재 구매가 → 분양가 | 있음 |
| 66 | 현재 구매가 용어 ⓘ (glossary `current_price`) | Detail · 머리 카드 "분양가 설명 ?" | | 있음 |
| 67 | 기준 타입 (`page.G3.header.priceBasis` "기준 타입 {type}") | Detail · "분양가 · 84C타입" / DetailTabs · 돈 카드 "84C 타입 기준 (판정 기준 타입)" | | 있음 |
| 68 | 가격 구성 (`page.G3.summary.priceComposition` "구성") | DetailTabs · "돈 카드에 더할 것" "가격 구성 · 공급가 + 발코니 1,950만" / Detail · "발코니 확장 1,950만원 포함" | 구성 → 가격 구성 | 있음 |
| 69 | 기준 타입 가격 채택 보류 — 긴 안내(.16 저장본) (`tabs.tsx` HeldPriceNote · `page.G3.price.held`) | DetailTabs · 돈 카드 "다른 단지일 때 나오는 메모" "[타입] 가격을 아직 정하지 못했어요 — …" | | 있음 |
| 70 | 채택 보류 — 짧은 안내(.17 서버 사유가 이미 보류) (`page.G3.price.heldBasis` "기준 타입 {type}") | DetailTabs · 돈 카드 메모 "서버가 이미 보류 사유를 준 경우 (짧은 메모)" "기준 타입 [타입] · 보류된 자료 값 …" |  | 있음(고침 DX-2) |
| 71 | 보류된 출처 값 (`page.G3.price.heldValue` "보류된 출처") | DetailTabs · 같은 메모 "보류된 자료 값 [값] 확인 불가(자료끼리 값이 달라 확인 중)" | 보류된 출처 → 보류된 자료 값 | 있음 |
| 72 | 최고 공급금액 사람 확인 링크(G7, max_price_won) (`page.G3.price.heldHumanCheck`) | DetailTabs · 같은 메모 "최고 공급금액 사람 확인하기 →" | | 있음 |
| 73 | 머리 할인 줄 (`page.G3.header.discount` "할인") | DetailTabs · 같은 메모 "할인 (공고에 적힌 것) [값]" | 할인 → 할인 (공고에 적힌 것) | 있음 |
| 74 | 할인 짧은 문구 '뺌' + 긴 title (`discountAppliedShort` "구매가에서 뺌" / `discountApplied`) | DetailTabs · 같은 메모 "확인됨 · 가격에서 이미 뺐어요" | | 있음 |
| 75 | 할인 짧은 문구 '표시만' + 긴 title (`discountNotAppliedShort` / `discountNotApplied`) | DetailTabs · 같은 메모 "확인됨 · 표시만 했어요 (가격에서 빼지 않음) — 확인된 값이 아니거나 뺄 수 없는 금액이에요" | | 있음 |
| 76 | '추정' 할인 안내 + 할인 사람 확인 링크 (`tabs.tsx` EstimatedDiscountNote · `discountEstimatedBasis` / `discountHumanCheck`) | DetailTabs · 같은 메모 "추정 공고문에서 찾은 할인이에요 … (기준 타입 [타입]) 할인 사람 확인하기 →" | | 있음 |
| 77 | '추정' 할인 안내 — 기준 타입 모를 때 (`page.G3.price.discountEstimated`) | DetailTabs · 같은 메모 "할인 … 추정 … (기준 타입을 모를 때 · 타입 표기 없음)" |  | 있음(고침 DX-2) |
| 78 | 계약금 비율 + 용어 ⓘ (`page.G3.summary.down` "계약금", glossary `down`) | Detail · 돈 "계약금 5% ?" / Mobile | | 있음 |
| 79 | 1차 계약금 금액 (`page.G3.summary.downFirst` "1차") | DetailTabs · 돈 카드 "계약하는 날 먼저 내는 돈 (1차 계약금) ? 1,000만원" | 1차 → 계약하는 날 먼저 내는 돈 (1차 계약금) | 있음 |
| 80 | 계약금 금액(서버 산술 Fact) (`page.G3.summary.downWon` "계약금 금액") | Detail · 돈 "3,124만원" / Mobile | 칸 이름 없이 계약금 칸 안 금액 | 있음 |
| 81 | 금액 계산값 없음(옛 저장본) (`page.G3.summary.downWonMissing` "계산값 미제공") | DetailTabs · 같은 메모 "계약금 금액 확인 불가(계산값 없음) — 예전에 저장한 자료라 금액 계산이 없어요" | 계산값 미제공 → 계산값 없음 | 있음 |
| 82 | 중도금 비율 · 금액 + 용어 ⓘ (`page.G3.summary.interim`, glossary `interim`) | Detail · 돈 "중도금 60% ? 3억 7,482만원" / Mobile | | 있음 |
| 83 | 중도금 조건 공고 문구 (`page.G3.summary.interimTerms` "조건: {text}(공고 문구)") | DetailTabs · 돈 카드 "중도금 조건 (공고 문구 그대로)" | | 있음 |
| 84 | 잔금 비율 · 금액 + 용어 ⓘ (`page.G3.summary.balance`, glossary `balance`) | Detail · 돈 "잔금 35% ? 2억 1,865만원" / Mobile | | 있음 |
| 85 | 납부 조건 없음 (`page.G3.summary.noPayment` "납부 조건 미수집") | DetailTabs · 같은 메모 "계약금 확인 불가(납부 조건을 아직 못 모음)" | | 있음 |
| 86 | 계산식 + title (`page.G3.summary.formula` "계산: {formula}") | DetailTabs · 돈 카드 "계산 방법 · 금액 = …" / Detail · 돈 설명 "중간 가격 … 공고문 비율대로 나눈 값이에요" | 계산: → 계산 방법 | 있음 |
| 87 | 자세히 링크 → `#payment` (`page.G3.summary.moreMoney` "내야 할 돈·일정 자세히") | DetailTabs · 돈 카드 "내야 할 돈·일정 자세히 →" | | 있음 |

## 6. 머리 — 청약 전 꼭 볼 조건 (`ComplexHeader.tsx` 2단)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 88 | 구획 + 안내 (`page.G3.summary.conditions` "청약 전 꼭 볼 조건" / `conditionsHint`) | Detail · "청약 전에 꼭 확인할 조건" + 설명 / Mobile · "꼭 확인할 조건" | → 청약 전에 꼭 확인할 조건 | 있음 |
| 89 | 전매 종료 + 용어 ⓘ + "팔 수 있게 되는 날" + D± + 없으면 확인 불가 (`page.G3.header.resaleEnd` / `summary.resaleEndPlain`) | Detail · 조건 "되팔기 (전매) ? 2026.12.09부터 · 56일 남음 · 추정" / Mobile | 전매 종료 → 되팔기 (전매) | 있음 |
| 90 | 거주의무 + 용어 ⓘ (`page.G3.summary.residency`) | Detail · 조건 "꼭 살아야 하나요 (실거주) ? 의무 없음 0개월" / Mobile "실거주 의무" | 거주의무 → 꼭 살아야 하나요 (실거주) | 있음 |
| 91 | 재당첨 제한 + 용어 ⓘ (`page.G3.summary.rewin`) | Detail · 조건 "다시 청약 제한 (재당첨) ?" / Mobile | | 있음 |
| 92 | 규제지역 + 용어 ⓘ (`page.G3.summary.regulated`) | Detail · 조건 "규제지역 ? 아님 · 비규제" / Mobile | | 있음 |
| 93 | 분양가 상한제 + 용어 ⓘ (`page.G3.summary.priceCap`) | Detail · 조건 "분양가 상한제 ? 적용 안 됨 · 민간택지" / Mobile · 꼭 확인할 조건 "분양가 상한제" |  | 있음(고침 MB-3) |
| 94 | 공급 일반 · 특별 + 용어 ⓘ (`page.G3.summary.supply` / `unitsGeneral` / `unitsSpecial`, glossary `special_supply`) | Detail · 이름 아래 줄 "(일반 674 · 특별공급 675)" / DetailTabs · 돈 카드 "특별공급 ? 일반 674세대 · 특별 675세대" | | 있음 |
| 95 | 특별공급 안내 (`page.G3.summary.specialHint`) | DetailTabs · 같은 곳 "— 특별공급 자격·소득 기준은 공고문에서 확인하세요" | | 있음 |

## 7. 머리 — 점수 · 분류 (`ComplexHeader.tsx` 2단)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 96 | 구획 (`page.G3.summary.score` "점수·분류 (상대 비교 · 투자 권유 아님)") | Detail · "점수는 왜 이렇게 나왔나요?" + "상대 비교예요. 투자 권유가 아니에요." / DetailTabs · "점수 카드에 더할 것" / Mobile · 점수 | → 점수는 왜 이렇게 나왔나요? | 있음 |
| 97 | 종합 점수 (`page.G3.header.total` "종합 점수") | Detail · 점수 "4.83 / 10" / Mobile | | 있음 |
| 98 | 종합 점수 용어 ⓘ (glossary `total`) | Detail · 점수 "종합 점수 ?" / Mobile · 점수 제목 옆 ? |  | 있음(고침 DT-4 · MB-4) |
| 99 | 점수 없음 → 확인 불가 (`FactCell fact=null`) | Detail · 점수 "점수가 없는 단지: 종합 점수 확인 불가(점수 계산 전)" / Mobile · 점수 카드 |  | 있음(고침 DT-4 · MB-4) |
| 100 | 순위 배지 (`page.common.rank` "{rank}위") | Detail · "점수 매긴 6곳 중 1위" / DetailTabs "1위" / Mobile | | 있음 |
| 101 | 동률 배지 (`components/TieBadge.tsx` · `badge.tie` / `badge.tieWithConfidence`) | DetailTabs · 점수 카드 "이럴 때 점수 옆에 붙는 배지" 동률 | | 있음 |
| 102 | 순위 불안정 배지 (`components/UnstableBadge.tsx` · `badge.unstable`) | DetailTabs · 같은 곳 "순위 불안정" | | 있음 |
| 103 | 판정 범위 배지 (`_shared` JudgeScopeBadge · `page.common.judgeScope.*`) | DetailTabs · 같은 곳 "점수 계산 대상 / 보류 — 공고 뒤 다시 계산 / 참고 후보 (순위만) / 분류 확인 중 (미해결) / 제외" | 판정 대상 → 점수 계산 대상, 미해결 → 분류 확인 중 (미해결) | 있음 |
| 104 | 재판정 필요 배지 + title (`_shared` RejudgeNeededBadge · `page.common.rejudgeNeeded` / `rejudgeNeededHint`) | DetailTabs · 같은 곳 "다시 계산 필요 …" | 재판정 필요 → 다시 계산 필요 | 있음 |
| 105 | 판정기 순위 변화 (`page.common.deltaRerank` "판정기 순위 변화(이전 실행 대비)") | DetailTabs · 점수 카드 "비슷한 단지들 사이 순위 점수 — 지난번 계산 대비 변화 ? 0.00점 변화 없음" | | 있음 |
| 106 | 단지 분류 + 분류 확률 + 용어 ⓘ (`page.G3.header.inclusion` "단지 분류", `page.common.inclusion.*`) | DetailTabs · 점수 카드 "단지 종류 (분류) ? 민간분양 아파트 · 이렇게 분류될 확률 87%" | 단지 분류 → 단지 종류 (분류) | 있음 |
| 107 | 점수 계산 범위 사유(서버 문자열 그대로) + 용어 ⓘ (`_shared` ScopeReason · `page.G3.header.scopeReason`) | DetailTabs · 점수 카드 "점수를 계산한 이유 (점수 계산 범위) ? 포함 확정 · 접수 가능" | 서버 문자열 그대로(고침 DX-3 — 쉬운 문장 뺌, 규칙 3) | 있음(고침 DX-3) |
| 108 | 재판정 필요 시 사유 덧붙임 (`page.common.scopeReasonCurrent`) | DetailTabs · 같은 곳 "'다시 계산 필요'일 때: … 지금 사실 기준 — 다시 판정한 뒤 범위의 이유" |  | 있음(고침 DX-3) |
| 109 | 자격 판정 아님 (`page.G3.summary.notQualification`) | Detail · 바닥 문구 / DetailTabs · 바닥 문구 / Mobile · 바닥 | | 있음 |

## 8. 숫자 · 용어 공통 (`components/FactCell.tsx` · `Term.tsx` · `ProvenancePanel.tsx`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 110 | 숫자 옆 라벨 배지 확인됨 · 추정 · 확인 불가(사유) (`FactCell.tsx` / `LabelBadge.tsx` · `label.*`) | Detail · DetailTabs 전체 "확인됨" / "추정" 칩 | | 있음 |
| 111 | 숫자 누르면 출처 서랍 (`FactCell.tsx` → `ProvenancePanel.tsx` · `provenance.*`) | Shell · 3 "숫자를 누르면 열리는 '출처' 창" | 출처 → 이 값은 어디서 왔나요? | 다른 보드(Shell) |
| 112 | 용어 ⓘ 팝오버(Esc · 바깥 클릭 닫기, 모바일 아래 시트, 용어 모음 링크) (`Term.tsx` · `glossary.more` / `glossary.close`) | Shell · 3 "용어 '?' 를 눌렀을 때" | ⓘ → ? | 다른 보드(Shell) |

## 9. 탭 1 타입별 가격 (`tabs.tsx` PriceTab)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 113 | 현재 구매가 (`page.G3.header.price`) | DetailTabs · 탭 1 "타입마다 가격이 어떻게 나뉘나요?" "현재 가격 5억 9,850만 ~ 6억 5,090만 확인됨" | 현재 구매가 → 현재 가격 | 있음 |
| 114 | 탭 안 채택 보류 안내 (`HeldPriceNote` testId held-price-note-tab) | DetailTabs · 탭 1 "다른 단지일 때 탭 1 모습" 보류 메모 |  | 있음(고침 DX-4) |
| 115 | 탭 안 할인 줄 + 차감 문구 + 추정 안내 (`page.G3.price.discount` "할인(공고 명시)" / `discountApplied` / `discountNotApplied`) | DetailTabs · 같은 곳 "할인 (공고에 적힌 것) [값] 확인됨 · 가격에서 뺐어요 / 추정 · 빼지 않았어요" |  | 있음(고침 DX-4) |
| 116 | 구성 (`page.G3.price.composition`) | DetailTabs · 탭 1 "구성 · 공급가 + 발코니 1,950만" | | 있음 |
| 117 | 최초 대비 가격 변화 (`page.G3.price.change` "최초 대비") | DetailTabs · 탭 1 "처음 공고 대비 가격 변화 · 값 없음 (…)" | 최초 대비 → 처음 공고 대비 가격 변화 | 있음 |
| 118 | 타입 없음 "없음" (`page.common.none`) | DetailTabs · 같은 곳 "타입 정보가 하나도 없는 단지: 없음" |  | 있음(고침 DX-4) |
| 119 | 표 열 타입(행 머리) (`page.G3.price.type` "타입") | DetailTabs · 탭 1 표 "타입" / Detail · 자세히 보기 표 "평형 (흔히 부르는 크기)" | Detail 은 → 평형 | 있음 |
| 120 | 판정 기준 배지 (`page.G3.price.basis` "판정 기준") | DetailTabs · 탭 1 표 "84C 판정 기준"(title) / Detail · 표 "· 위 가격 기준" | | 있음 |
| 121 | 표 열 전용면적 (`page.G3.price.area`) | DetailTabs · 탭 1 표 "전용면적" (Detail 표는 평형 칸에 ㎡ · 평) | | 있음 |
| 122 | 표 열 세대 (`page.G3.price.units`) | DetailTabs · 탭 1 표 "세대" / Detail "세대수" | | 있음 |
| 123 | 표 열 최고가 (`page.G3.price.max`) | DetailTabs · 탭 1 표 "최고가" / Detail "가장 높은 가격" | | 있음 |
| 124 | 표 열 최저가 층 가격 (`page.G3.price.floorSample`) | DetailTabs · 탭 1 표 "가장 낮은 층 가격" / Detail "가장 낮은 층" | 최저가 층 가격 → 가장 낮은 층 가격 | 있음 |
| 125 | 표 열 최저가 층 (`page.G3.price.floorText`) | DetailTabs · 탭 1 표 "가장 낮은 층" | | 있음 |
| 126 | 표 열 발코니 (`page.G3.price.balcony`) | DetailTabs · 탭 1 표 "발코니" | | 있음 |
| 127 | 표 열 필수 옵션 (`page.G3.price.options`) | DetailTabs · 탭 1 표 "필수 옵션" | | 있음 |
| 128 | 표 열 할인(현재 공고에 타입별 할인 있을 때만) (`page.G3.price.discount`) | DetailTabs · 같은 곳 할인 열 표 "할인" 열 |  | 있음(고침 DX-4) |
| 129 | 타입 할인 안내 3가지(기준 타입 추정 + 링크 / 다른 타입 추정 / 다른 타입 확인됨) (`TypeDiscountCell` · `discountEstimatedBasis` / `discountEstimatedNonBasis` / `discountNonBasis`) | DetailTabs · 같은 표 할인 칸 안내 3가지(기준 타입 추정 + 링크 / 다른 타입 추정 / 다른 타입 확인됨) |  | 있음(고침 DX-4) |
| 130 | 그 타입 할인 없음 "없음" (`TypeDiscountCell`) | DetailTabs · 같은 표 "[타입 D] … 없음" |  | 있음(고침 DX-4) |
| 131 | 필수 옵션 고지 각주 ① (`page.G3.price.noteRef` "①" / `noteTitle` "① 공고문 고지") | DetailTabs · 같은 표 "[금액] ①" + "① 공고문 고지: …" | ① 공고문 고지 → ① 공고문 안내 | 있음(고침 DX-4) |
| 132 | 필수 옵션 고지 칸 안 글(타입마다 다를 때) (`options_text`) | DetailTabs · 같은 표 필수 옵션 칸 "[옵션 고지 글 — 타입마다 다르면 칸 안에 그대로]" |  | 있음(고침 DX-4) |

## 10. 탭 2 내야 할 돈 · 일정 (`tabs.tsx` PaymentTab)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 133 | 납부 조건 없음 "없음" | DetailTabs · 탭 2 "납부 조건이 하나도 없는 단지: 없음" |  | 있음(고침 DX-5) |
| 134 | 공고별 구획 제목 + 공고 종류 배지 + 현재 적용 배지 (`page.G3.payment.notice` "공고" / `payment.current` "현재 적용") | DetailTabs · 탭 2 "언제, 몇 번에 나눠 내나요?" 표 "두 공고 나란히 보기" 열 머리 "지금 적용 · 무순위 공고 2025910275 [지금 적용]" / "처음 공고 · 본청약 2025000560" | 공고별 카드 → 두 공고 나란히 표의 열 | 있음 |
| 135 | 적용일 (`page.G3.payment.effective`) | DetailTabs · 같은 표 "적용 시작일" | | 있음 |
| 136 | 계약금 (`page.G3.payment.down`) | DetailTabs · 같은 표 "계약금" | | 있음 |
| 137 | 1차 계약금 (`page.G3.payment.downFirst`) | DetailTabs · 같은 표 "계약하는 날 먼저 내는 돈 (1차 계약금)" | | 있음 |
| 138 | 중도금 (`page.G3.payment.interim`) | DetailTabs · 같은 표 "중도금 60%(6번 × 10%)" | | 있음 |
| 139 | 잔금 (`page.G3.payment.balance`) | DetailTabs · 같은 표 "잔금 35% 추정 (100 − 계약금 − 중도금)" | | 있음 |
| 140 | 중도금 조건(없으면 "없음") (`page.G3.payment.interimTerms`) | DetailTabs · 같은 표 "중도금 조건 (공고 문구)" | | 있음 |
| 141 | 최초 공고 대비 계약금 변화 (`page.G3.payment.changeVsFirst`) | DetailTabs · 같은 표 "처음 공고 대비 계약금 변화 0%p 같아요" | | 있음 |
| 142 | 중도금 일정 표 — 회차 · 날짜(D±) · 비율 (`page.G3.payment.schedule` / `payment.seq` "{n}회차") | DetailTabs · 탭 2 표 "중도금 일정 · 두 공고 모두 같아요" (회차 · 낼 날짜 · 비율) | 공고마다 표 → 같으면 한 표 | 있음 |

## 11. 탭 3 경쟁률 · 추가 모집 (`tabs.tsx` EventsTab)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 143 | 구획 (`page.G3.competition.title` "경쟁률") | DetailTabs · 탭 3 "회차·타입별로 얼마나 몰렸나요?" | | 있음 |
| 144 | 탭 안 경쟁률 요약 줄 (`CompetitionSummaryLine.tsx`) | DetailTabs · 탭 3 "가장 높았던 경쟁률 (1순위 · 지역 거주자) 6.22 대 1 · 59타입" + "신청이 모자랐던 타입 5개" | | 있음 |
| 145 | 경쟁률 없음 "없음" | DetailTabs · "경쟁률 표 — 다른 칸 모습" "경쟁률 줄이 없으면 '없음'" | | 문구로만 |
| 146 | 표 열 회차 (`page.G3.competition.round`) | DetailTabs · 탭 3 경쟁률 표 "회차" | | 있음 |
| 147 | 표 열 구분(`chart.C08.kind.*` 값) (`page.G3.competition.kind`) | DetailTabs · 같은 표 "구분" | | 있음 |
| 148 | 표 열 타입 (`page.G3.competition.type`) | DetailTabs · 같은 표 "타입" | | 있음 |
| 149 | 표 열 공급 (`page.G3.competition.supply`) | DetailTabs · 같은 표 "공급" | | 있음 |
| 150 | 표 열 접수 (`page.G3.competition.applied`) | DetailTabs · 같은 표 "접수" | | 있음 |
| 151 | 표 열 경쟁률(미달이면 모자란 세대) (`page.G3.competition.ratio`) | DetailTabs · 같은 표 "경쟁률 (모자라면 미달 세대)" | | 있음 |
| 152 | 표 열 당첨 가점(최저~최고 · 평균) (`page.G3.competition.points`) | DetailTabs · 같은 표 "당첨된 사람 가점 (최저~최고 · 평균) ?" | | 있음 |
| 153 | 미달 표기 "미달 {n}세대" + 원문 title (`shortfallUnits` · `page.G3.competition.shortfall`) | DetailTabs · 같은 표 "미달 26세대" | 원문 title 은 목업에 없음 | 있음 |
| 154 | 경쟁률 원문 그대로 · 없으면 확인 불가 (`ratio_or_shortfall_text` · `empty.unknown`) | DetailTabs · 같은 표 "6.11 대 1" · "-" | 목업은 "대 1"을 붙임(표기) | 있음 |
| 155 | 가점 값 최저~최고 · 평균 (`PointsCell` · `page.G3.competition.pointsAvg` "평균") | DetailTabs · "경쟁률 표 — 다른 칸 모습" "42 ~ 63점 평균 48.50점" | | 있음 |
| 156 | 가점제 당첨자 없음(모두 0 · 팝업 '-') (`page.G3.competition.noPointWinners`) | DetailTabs · 같은 곳 + 표 줄 | | 있음 |
| 157 | 가점 당첨자 없음(미달) (`page.G3.competition.noPointWinnersShortfall`) | DetailTabs · 같은 곳 "가점 당첨자 없음 (미달)" | | 있음 |
| 158 | 발표 전 (`page.G3.competition.pointsBeforeAnnounce`) | DetailTabs · 같은 곳 "발표 전" | | 있음 |
| 159 | 가점 미수집 (`page.G3.competition.pointsNotCollected`) | DetailTabs · 같은 곳 + 표 줄 "가점 미수집" | | 있음 |
| 160 | 가점 열 숨김 + 안내 (`showPointsColumn` · `page.G3.competition.pointsMissing`) | DetailTabs · 같은 곳 "가점 값이 하나도 없으면 가점 열을 숨기고 …를 표 아래에 적어요" | | 문구로만 |

## 12. 차트 C08 잔여 이력 (`charts/C08`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 161 | 차트 틀 + 제목 (`C08/index.tsx` ChartFrame · `chart.C08.title` "잔여 이력") | DetailTabs · 탭 3 그림 "남은 집을 다시 모집한 이력" | 잔여 이력 → 남은 집을 다시 모집한 이력 | 있음 |
| 162 | x축 시간(공고일, 앞뒤 한 달 여유) (`C08/buildOption.ts`) | DetailTabs · 같은 그림 눈금 2025.11 ~ 2026.11 + "축: 공고일(월)" | | 있음 |
| 163 | y축 종류 4줄 (`chart.C08.kind.*`) | DetailTabs · 같은 그림 줄 "본청약 · 무순위 · 임의공급 · 선착순" | | 있음 |
| 164 | 범례 종류 4개 (`legend data`) | DetailTabs · 탭 3 그림 아래 범례 "본청약 · 무순위 · 임의공급 · 선착순"(모양 4가지) |  | 있음(고침 DX-7) |
| 165 | 종류별 마커 모양 · 본청약 강조색 (`C08/types.ts` C08_SYMBOLS) | DetailTabs · 같은 그림 무순위 네모 1개 + 범례 모양(본청약 원 · 무순위 네모 · 임의공급 세모 · 선착순 마름모) | 무순위 마름모 → 네모(지금 코드 모양) | 있음(고침 DX-7) |
| 166 | 마커 라벨 잔여 세대 · 짧은 경쟁률, 가까우면 위아래 엇갈림 (`labelItems` · `chart.C08.labels`) | DetailTabs · 같은 그림 "01.26 · 36세대 · 75타입 6.11 대 1 · 136P 10.00 대 1" | 지금은 12자 넘는 경쟁률은 라벨에서 뺌 — 목업은 긴 표기도 라벨 | 있음 |
| 167 | 툴팁(종류 · 공고일 · 공고 번호 · 라벨 · 결과) | DetailTabs · 같은 곳 "툴팁 예시" (종류 · 공고일 · 공고 번호 · 라벨 · 결과) |  | 있음(고침 DX-7) |
| 168 | 라벨 배지(공고일 · 세대 라벨) (`ChartFrame` labels) | DetailTabs · 같은 그림 "확인됨" | | 있음 |
| 169 | 빈 상태 (`chart.C08.empty` "본청약만") | DetailTabs · "경쟁률 표 — 다른 칸 모습" "다시 모집 이력이 없으면 차트 자리에 '본청약만 있어요(다시 모집 없음)'" | 본청약만 → 본청약만 있어요(다시 모집 없음) | 문구로만 |
| 170 | 표로 보기 / 표 닫기 (`components/DataTableToggle.tsx` · `table.show` / `table.hide`) | DetailTabs · 그림 아래 "표로 보기" + "버튼 글자는 '표 닫기'로 바뀌어요" | | 있음 |
| 171 | 표 열 구분 (`chart.col.kind`) | DetailTabs · "표로 보기 — 남은 집 다시 모집 이력" "종류" | 구분 → 종류 | 있음 |
| 172 | 표 열 공고 번호 (`chart.col.noticeNo`) | DetailTabs · 같은 표 "공고 번호" | | 있음 |
| 173 | 표 열 공고일(D±) (`chart.col.noticeDate`) | DetailTabs · 같은 표 "공고일 2026.01.26 · 261일 지남" | | 있음 |
| 174 | 표 열 세대 (`chart.col.units`) | DetailTabs · 같은 표 "세대" | | 있음 |
| 175 | 표 열 경쟁률 (`chart.col.ratio`) | DetailTabs · 같은 표 "경쟁률 · 결과" | 경쟁률 + 표시 두 열 → 한 열 | 있음 |
| 176 | 표 열 표시(결과) (`chart.col.flags` "표시") | DetailTabs · 같은 표 "경쟁률 · 결과" | | 있음 |
| 177 | 차트 aria-label (`EChart` ariaLabel) | DetailTabs · 그림 aria-label "남은 집 추가 모집 이력: …" | | 있음 |

## 13. 탭 4 주변 시세 비교 (`tabs.tsx` GapTab · `charts/C02`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 178 | 가격 갭 (`page.G3.gap.pct` "가격 갭(주변 대비)") | DetailTabs · 탭 4 "주변 새 아파트 실거래와 비교하면 어떤가요?" "주변 시세와 가격 차이 ? +8.1%" / Detail · 머리 카드 "주변보다 8.1% 높아요" / Mobile | 가격 갭(주변 대비) → 주변 시세와 가격 차이 | 있음 |
| 179 | 미보정 가격 갭 (`page.G3.gap.unadjusted`) | DetailTabs · 탭 4 "같은 계산 · 연식 보정 안 한 가운데값 기준 +8.1%" | | 있음 |
| 180 | 가격 갭 점수 0~10 (`page.G3.gap.score`) | DetailTabs · 탭 4 "가격 차이 점수 (0~10) 2.98 / 10" | | 있음 |
| 181 | 부호 뜻 (`page.G3.gap.meaning`) | DetailTabs · 탭 4 "+는 … −는 낮다는 뜻이에요." | | 있음 |
| 182 | 비교 기준 (`page.G3.gap.basis`) | DetailTabs · 탭 4 "비교 기준: 같은 생활권 · 2020년 이후 준공 · …" | | 있음 |
| 183 | 비교 단지 수 (`page.G3.gap.comps` "비교 단지 {n}곳") | DetailTabs · 탭 4 "비교 단지 17곳" | | 있음 |
| 184 | 대체 단지 배지 (`page.G3.gap.substitute` "대체 단지 포함(거래 3건 미만)") | DetailTabs · "주변 시세 · 가격 전망 — 다른 상태" | | 있음 |
| 185 | 차트 틀 + 제목 (`C02/index.tsx` · `chart.C02.title` "가격 갭") | DetailTabs · 탭 4 그림 "이 단지 가격 vs 주변 실거래" | 가격 갭 → 이 단지 가격 vs 주변 실거래 | 있음 |
| 186 | 점 + 위스커(하단~상단, 가운데 점) 모양 (`C02/buildOption.ts` custom) | DetailTabs · 같은 그림 가로 막대(범위) + 점(가운데값) | 세로 위스커 → 가로 막대 | 있음 |
| 187 | 값 축 억 단위 (`formatEok`) | DetailTabs · 같은 그림 "3억 4억 5억 6억 7억 8억" + "단위: 원 (가운데값)" | | 있음 |
| 188 | 단지 축 라벨 + 신축(연도) (`compBadge` · `badge.newBuild`) | DetailTabs · 같은 그림 줄 이름 옆 "2024년 · 6건" | 신축(2024) → 2024년 · n건 | 있음 |
| 189 | 단지 축 라벨 대체(연도) (`badge.substitute`) | DetailTabs · 탭 4 그림 "[대체 단지] 대체([준공년]) · 모양 예시" 줄 |  | 있음(고침 DX-8) |
| 190 | 현재 구매가 범위 강조 (`chart.C02.current` "현재 구매가") | DetailTabs · 같은 그림 "이 단지 (84C 분양가)" 강조 줄 | 현재 구매가 → 이 단지 (분양가) | 있음 |
| 191 | 연식 보정 중앙값 점(점선 빈 점) + 범례 (`chart.C02.adjusted`) | DetailTabs · 같은 줄 점선 빈 점 + 범례 "연식 보정 가운데값 (대체 단지만)" |  | 있음(고침 DX-8) |
| 192 | 범례 실거래 범위 (`chart.C02.range`) | DetailTabs · 같은 그림 범례 "비교 단지 실거래 범위" | | 있음 |
| 193 | 툴팁(하단~상단 · 중앙/미보정 · 보정) | DetailTabs · 같은 그림 "툴팁 예시" (가장 낮은 값~가장 높은 값 · 가운데값(보정 안 함) · 보정 줄) |  | 있음(고침 DX-8) |
| 194 | 보정 배지 "추정(대체·보정 c=…)" (`adjustedBadges`) | DetailTabs · "주변 시세 · 가격 전망 — 다른 상태" "추정 (대체·연식 보정) 차트 제목 옆" | | 있음 |
| 195 | 라벨 배지 (`ChartFrame` labels) | DetailTabs · 같은 그림 "재가공 (실거래 통계) · 확인됨" | | 있음 |
| 196 | 빈 상태 (`chart.C02.empty` "비교군 없음({reason})") | DetailTabs · 다른 상태 "비교할 단지가 없어요 (사유)" | | 있음 |
| 197 | 표로 보기 (`table.show`) | DetailTabs · 그림 아래 "표로 보기" | | 있음 |
| 198 | 표 열 이름 (`chart.col.name`) | DetailTabs · "표로 보기 — 주변 시세 비교" "이름" | | 있음 |
| 199 | 표 열 구분 (`chart.col.kind`) | DetailTabs · 같은 표 "준공 · 구분" | | 있음 |
| 200 | 표 열 하단 (`chart.col.low`) | DetailTabs · 같은 표 "가장 낮은 값" | | 있음 |
| 201 | 표 열 중앙값 (`chart.col.median`) | DetailTabs · 같은 표 "가운데값" | 중앙값 → 가운데값 | 있음 |
| 202 | 표 열 상단 (`chart.col.high`) | DetailTabs · 같은 표 "가장 높은 값" | | 있음 |
| 203 | 표 열 보정 중앙값(대체 아니면 빈 칸) (`chart.col.adjusted`) | DetailTabs · "표로 보기 — 주변 시세 비교" "연식 보정 가운데값"(대체 아니면 빈 칸) | 대체 아니면 빈 칸(고침 DX-9) | 있음(고침 DX-9) |
| 204 | 표 열 거래 기간 (`chart.col.window`) | DetailTabs · 같은 표 "거래 기간" 열 |  | 있음(고침 DX-9) |

## 14. 탭 5 가격 전망 (`tabs.tsx` LadderTab · `charts/C01`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 205 | 안내 (`page.G3.ladder.note` "당첨 확률이 아닙니다 · 보장 아님 · 상대 비교") | DetailTabs · 탭 5 "목표 시점에 값이 오를 가능성은 어느 정도인가요?" 설명 | 제목 '입주 뒤' → '목표 시점에'(목표 시점이 기준일 + 3·5년일 수도 있음) | 있음(고침 DX-10) |
| 206 | 목표 시점 고르기 radiogroup 3개 + 대상 반기 (`page.G3.ladder.horizons`, `chart.C01.horizon.*`) | DetailTabs · 탭 5 radiogroup "입주 + 1년 · 2030 하반기" … | 입주+1년 → 입주 + 1년 | 있음 |
| 207 | 미해결 시점 회색 + "· 미해결" (`page.common.unresolved`) | DetailTabs · "주변 시세 · 가격 전망 — 다른 상태" "기준일 + 5년 · [시점] · 미해결" | | 있음 |
| 208 | 판정기에 물은 문장 (`page.G3.ladder.proposition`) | DetailTabs · 탭 5 "판정기에 물은 문장 “…”" | | 있음 |
| 209 | 차트 틀 + 제목 (`C01/index.tsx` · `chart.C01.title` "상승 확률 사다리") | DetailTabs · 탭 5 그림 "현재 가격보다 얼마나 오를까 — 가능성 사다리" | → 가능성 사다리 | 있음 |
| 210 | 막대 4개 (`chart.C01.bar.*` "+5% · +10% · +20% · 보합·하락") | DetailTabs · 같은 그림 "5% 넘게 오를 가능성 … 그대로이거나 내릴 가능성" | | 있음 |
| 211 | x축 0~1 확률 눈금 (`buildOption` xAxis) | DetailTabs · 탭 5 그림 "가능성 눈금" 0% ~ 100% |  | 있음(고침 DX-10) |
| 212 | 기준선 0.15 · 0.85 (`chart.C01.threshold.*`) | DetailTabs · 같은 그림 "가능성 낮음 기준 15% · 가능성 높음 기준 85%" | 0.15 → 15% | 있음 |
| 213 | 막대 라벨 값 · 판정 (`chart.C01.verdict.*`) | DetailTabs · 같은 그림 막대 옆 "53% 중간" | 불확실 → 중간 | 있음 |
| 214 | 필요 연율(툴팁 안) (`chart.C01.annualized` "필요 연율 {pct}") | DetailTabs · 같은 그림 "· 해마다 2.6%" + 머리 "판정 · 필요한 연 상승률" | 툴팁 → 보이는 글 | 있음 |
| 215 | 툴팁 | DetailTabs · 같은 그림 "툴팁 예시" (항목 · 값 · 판정 · 필요한 연 상승률) |  | 있음(고침 DX-10) |
| 216 | 부제 (`chart.C01.subtitle` "목표 시점 {target}") | DetailTabs · 같은 그림 "목표 시점 2030 하반기 · 84C 타입 …" | | 있음 |
| 217 | 라벨 배지 (`ChartFrame` labels) | DetailTabs · 같은 그림 "추정 (판정기)" | | 있음 |
| 218 | 미해결 배지 + 회색 바탕 막대 + "미해결" 라벨 (`unresolvedBadge` · `badge.unresolved`) | DetailTabs · 다른 상태 "판정이 끝나지 않은 시점은 회색 + 차트 제목 옆 배지" | | 있음 |
| 219 | 빈 상태 (`chart.C01.empty` "사다리 판정 없음") | DetailTabs · 다른 상태 "가능성 판정이 없어요" | | 있음 |
| 220 | 표로 보기 (`table.show`) | DetailTabs · 그림 아래 "표로 보기" | | 있음 |
| 221 | 표 열 시점 (`chart.col.horizon`) | DetailTabs · "표로 보기 — 가격 전망 사다리" "목표 시점"(입주 + 1년) | 시점 ↔ 목표 시점 머리 이름이 서로 바뀜 | 있음 |
| 222 | 표 열 목표 시점 (`chart.col.target`) | DetailTabs · 같은 표 "시점"(2030 하반기) | | 있음 |
| 223 | 표 열 +5% (`chart.C01.bar.p5`) | DetailTabs · 같은 표 "+5%" | | 있음 |
| 224 | 표 열 +10% (`chart.C01.bar.p10`) | DetailTabs · 같은 표 "+10%" | | 있음 |
| 225 | 표 열 +20% (`chart.C01.bar.p20`) | DetailTabs · 같은 표 "+20%" | | 있음 |
| 226 | 표 열 보합·하락 (`chart.C01.bar.p_flat`) | DetailTabs · 같은 표 "그대로·내림" | 보합·하락 → 그대로·내림 | 있음 |
| 227 | 표 열 상태 (`chart.col.status`, `chart.status.*`) | DetailTabs · 같은 표 "상태 · 정상" | 판정 → 정상 | 있음 |

## 15. 탭 6 개발 소식 (`tabs.tsx` CatalystsTab · `charts/C09` compact)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 228 | 차트 틀 + 제목 (`C09/index.tsx` · `chart.C09.title` "호재 단계") | DetailTabs · 탭 6 "주변에 개발 소식이 있나요?" 그림 "개발 소식 단계" | 호재 단계 → 개발 소식 단계 | 있음 |
| 229 | 단계 보드 5칸 (`chart.C09.stage.*`) | DetailTabs · 같은 그림 "확정 · 계획 · 추진 · 언론 보도만 · 아직 정해지지 않음" | 언론 → 언론 보도만, 미확정 → 아직 정해지지 않음 | 있음 |
| 230 | 단계 배지 색(확정 강조 · 언론/미확정 회색) | DetailTabs · 탭 6 설명 "언론 보도만 있거나 아직 정해지지 않은 소식은 회색이에요" | | 문구로만 |
| 231 | 보드 칸 안 항목(이름 · 종류 · 예정 연월 · 위치 미확정) + 라벨 배지 | DetailTabs · 탭 6 "소식이 있을 때 단계 칸 안 모습" |  | 있음(고침 DX-11) |
| 232 | 판정 제외 한 줄 (`chart.C09.excluded` "호재 아님(판정 제외) {n}건 — 보드에 넣지 않음") | DetailTabs · 같은 곳 "개발 소식 아님(판정 제외) [n]건 — 보드에 넣지 않음" | 호재 아님 → 개발 소식 아님 | 있음(고침 DX-11) |
| 233 | 빈 상태 그림 대신 한 줄 (`chart.C09.empty` "호재 없음") | DetailTabs · 같은 그림 단계 칸마다 "없음" | 한 줄 → 다섯 칸 '없음' | 있음 |
| 234 | 표로 보기 (`table.show`) | DetailTabs · 그림 아래 "표로 보기" | | 있음 |
| 235 | 표 열 이름 (`chart.col.name`) | DetailTabs · 탭 6 "표로 보기 — 개발 소식 단계" "이름" |  | 있음(고침 DX-11) |
| 236 | 표 열 구분 (`chart.col.kind`) | DetailTabs · 같은 표 "구분" |  | 있음(고침 DX-11) |
| 237 | 표 열 단계 (`chart.col.stage`) | DetailTabs · 같은 표 "단계" |  | 있음(고침 DX-11) |
| 238 | 표 열 확률 (`chart.col.prob`) | DetailTabs · 같은 표 "확률" |  | 있음(고침 DX-11) |
| 239 | 표 열 예정 (`chart.col.expected`) | DetailTabs · 같은 표 "예정" |  | 있음(고침 DX-11) |
| 240 | 표 열 위치 확정 (`chart.col.location`) | DetailTabs · 같은 표 "위치 확정" |  | 있음(고침 DX-11) |
| 241 | 목록 구획 (`page.G3.catalyst.list` "호재 목록") | DetailTabs · 탭 6 "개발 소식 목록" | | 있음 |
| 242 | 목록 없음 (`chart.C09.empty`) | DetailTabs · 같은 곳 "이 단지에 연결된 개발 소식이 없어요" | | 있음 |
| 243 | 항목 이름 | DetailTabs · "소식이 있을 때 한 줄 모습" "[소식 이름 — 기사 제목]" | | 있음 |
| 244 | 종류 배지 (`page.G3.catalystKind.*`) | DetailTabs · 같은 줄 "생활 시설" | 생활인프라 → 생활 시설 | 있음 |
| 245 | 단계 배지 (`chart.C09.stage.*`) | DetailTabs · 같은 줄 "아직 정해지지 않음" | | 있음 |
| 246 | 단계 확률 | DetailTabs · 같은 줄 "이 단계일 가능성 68% 추정 (판정기)" | | 있음 |
| 247 | 예정 (`page.G3.catalyst.expected`) | DetailTabs · 같은 줄 "예정 확인 불가(예정 시기가 안 적힘)" | | 있음 |
| 248 | 거리 (`page.G3.catalyst.distance`) | DetailTabs · 같은 줄 "거리 [거리]m" | | 있음 |
| 249 | 단지 연결 없음 (`chart.C09.noLink`) | DetailTabs · 같은 줄 "위치 미확정 · 단지 연결 없음" | | 있음 |
| 250 | 미해결 배지(decision ≠ auto) (`page.common.unresolved`) | DetailTabs · 같은 줄 "판정 미해결" | | 있음 |
| 251 | 출처 링크 (`page.G3.catalyst.source` "출처") | DetailTabs · 같은 줄 "출처 기사 열기" | | 있음 |
| 252 | 메모 (note) | DetailTabs · 같은 줄 "[기사 발췌 한두 줄]" | | 있음 |
| 253 | 언론 · 미확정 줄 회색 | DetailTabs · 같은 줄(회색 글) | | 있음 |

## 16. 탭 7 근거 원문 (`ProvenanceTab.tsx` · `components/RawDocumentPreview.tsx`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 254 | 값 목록 제목 (`page.G3.provenance.fields` "출처가 있는 값") | DetailTabs · 탭 7 "이 숫자는 어디에서 왔나요?" "출처가 있는 값 23개" | | 있음 |
| 255 | 안내 (`page.G3.provenance.pick`) | DetailTabs · 탭 7 설명 "왼쪽에서 값을 고르면 오른쪽 원문에서 그 부분을 파랗게 칠해 보여 줘요" | | 있음 |
| 256 | 값 버튼 aria-pressed · 선택 강조 · 첫 값 기본 선택 | DetailTabs · 같은 목록(첫 줄 눌림) | | 있음 |
| 257 | 값 옆 숫자 + 라벨(누르면 그 값 선택) (`FactCell onOpenProvenance`) | DetailTabs · 같은 목록 줄 "값 · 확인됨/추정" | | 있음 |
| 258 | 항목 현재 구매가 낮은 · 높은 (`page.G2.col.price`) | DetailTabs · 같은 목록 "현재 가격 (낮은 값) / (높은 값)" | 현재 구매가 → 현재 가격 (낮은 값 · 높은 값) | 있음 |
| 259 | 항목 단지 이름 (`page.G3.provenance.name`) | DetailTabs · 같은 목록 "단지 이름" | | 있음 |
| 260 | 항목 총 세대 (`page.G3.headerFields.units_total`) | DetailTabs · 같은 목록 "총 세대" | | 있음 |
| 261 | 항목 공고일 (`headerFields.notice_date`) | DetailTabs · 같은 목록 "공고일" | | 있음 |
| 262 | 항목 당첨자 발표 (`headerFields.winner_date`) | DetailTabs · 같은 목록 "당첨자 발표" | | 있음 |
| 263 | 항목 입주 (`headerFields.move_in_ym`) | DetailTabs · 같은 목록 "입주" | | 있음 |
| 264 | 항목 전매 제한(개월) (`headerFields.resale_months`) | DetailTabs · 같은 목록 "되팔기 제한 기간" | → 되팔기 제한 기간 | 있음 |
| 265 | 항목 전매 종료 (`headerFields.resale_end`) | DetailTabs · 같은 목록 "되팔기 가능 날짜" | → 되팔기 가능 날짜 | 있음 |
| 266 | 항목 거주의무(개월) (`headerFields.residency_months`) | DetailTabs · 같은 목록 "꼭 살아야 하는 기간" | → 꼭 살아야 하는 기간 | 있음 |
| 267 | 항목 재당첨 제한(년) (`headerFields.rewin_restriction_years`) | DetailTabs · 같은 목록 "다시 청약 제한" | → 다시 청약 제한 | 있음 |
| 268 | 항목 택지유형 (`headerFields.land_type`) | DetailTabs · 같은 목록 "땅 종류" | 택지유형 → 땅 종류 | 있음 |
| 269 | 항목 분양가 상한제 (`headerFields.price_cap`) | DetailTabs · 같은 목록 "분양가 상한제" | | 있음 |
| 270 | 항목 규제지역 (`headerFields.regulated`) | DetailTabs · 같은 목록 "규제지역" | | 있음 |
| 271 | 항목 주택 구분 (`headerFields.housing_type`) | DetailTabs · 같은 목록 "주택 구분" | | 있음 |
| 272 | 항목 타입별 최고가 (`page.G3.price.max` "최고가 {type}") | DetailTabs · 같은 목록 "최고가 59 … 최고가 136P" | | 있음 |
| 273 | 출처 있는 값 없음 (`page.common.none`) | DetailTabs · "출처·원문 — 다른 상태" "출처 있는 값이 없으면: '없음'" | | 문구로만 |
| 274 | 원문 제목 (`page.G3.provenance.raw` "원문") | DetailTabs · 탭 7 "원문 · 현재 가격(낮은 값) 5억 9,850만" | | 있음 |
| 275 | 출처 라벨 배지(label · reason) (`LabelBadge`) | DetailTabs · 탭 7 원문 메타 "확인됨" | | 있음 |
| 276 | 확인일 | DetailTabs · 같은 메타 "확인일 2026-10-13" | | 있음 |
| 277 | 원문 주소 외부 링크 (`ExternalLink`) | DetailTabs · 같은 메타 "청약홈 공고 첨부파일 열기 ↗" | | 있음 |
| 278 | 단위 근거 (`provenance.unitBasis` "단위 근거") | DetailTabs · 다른 상태 "표의 단위를 바꿔 읽은 값이면: 단위 근거 줄 (표 머리 문구)" | | 문구로만 |
| 279 | 출처 불러오는 중 / 리비전 준비 중 (`app.loading` / `page.common.materializePending`) | DetailTabs · 다른 상태 "공개본 자료를 준비 중이면: …" | | 문구로만 |
| 280 | 출처 조회 오류 (`lib/errorText.ts` queryErrorText) | DetailTabs · "출처·원문 — 다른 상태" 오류 모습 "불러오지 못했어요: [사유]"(+ 준비 중 · 저장본 검증 실패 문구) |  | 있음(고침 DX-12) |
| 281 | 원문 미리보기 / 닫기 aria-expanded (`provenance.rawPreview` / `rawPreviewHide`) | DetailTabs · 탭 7 "미리보기 닫기" | | 있음 |
| 282 | 원문 파일 저장(Bearer fetch → Blob) (`provenance.rawSave`) | DetailTabs · 탭 7 "원문 파일 저장" | | 있음 |
| 283 | 내려받는 중 (`download.pending`) | DetailTabs · 다른 상태 "'내려받는 중…'" | | 문구로만 |
| 284 | 내려받기 오류 (`download.error` "내려받지 못했습니다: {detail}") | DetailTabs · 같은 곳 "원문 파일 저장" 옆 "내려받지 못했어요: [사유]" |  | 있음(고침 DX-12) |
| 285 | 그림 원문 미리보기 (`provenance.rawImageAlt`) | DetailTabs · 다른 상태 "그림 원문은 이미지로 보여요" | | 문구로만 |
| 286 | 미리보기 미지원 형식 (`provenance.rawPreviewUnsupported`) | DetailTabs · 다른 상태 "이 형식([형식])은 미리보기를 지원하지 않아요 — 저장해서 여세요" | | 문구로만 |
| 287 | 앞 n자만 (`provenance.rawTruncated` "앞 {n}자만 표시합니다") | DetailTabs · 다른 상태 "아주 긴 원문: '앞 200,000자만 보여요'" | | 문구로만 |
| 288 | 원문 불러오는 중 · 오류 (`provenance.rawLoading` / `rawError`) | DetailTabs · 다른 상태 "'원문 불러오는 중…' · '원문을 불러오지 못했어요'" | | 문구로만 |
| 289 | 원문 파일 없음 + 발췌 인용 (`page.G3.provenance.noRaw`) | DetailTabs · 다른 상태 "원문 파일이 없으면: '원문 파일 없음' + 발췌 인용" | | 문구로만 |
| 290 | 원문 텍스트 + 발췌 강조 mark (`page.G3.provenance.highlight` "발췌 위치") | DetailTabs · 탭 7 원문 상자 + mark aria-label "발췌 위치" | | 있음 |
| 291 | 강조 위치로 스크롤(가운데) (`mark ref scrollIntoView`) | DetailTabs · "구현할 때 지금 동작 그대로 유지" 상자 |  | 문구로만(고침 DX-13) |
| 292 | 오프셋 안 맞으면 문자열 검색 + 안내 (`highlightExcerpt` · `page.G3.provenance.excerptNotFound`) | DetailTabs · 다른 상태 "원문에서 위치를 못 찾으면: …" | | 문구로만 |
| 293 | 발췌 못 찾음 → 안내 + 발췌 인용 | DetailTabs · 다른 상태 같은 줄 "+ 발췌 인용" | | 문구로만 |
| 294 | API `GET /provenance/{id}?snapshot=` (`api/hooks.ts` useProvenance) | DetailTabs · 탭 7 원문 메타 | | 있음 |
| 295 | API `GET /raw/{id}?as=text` (`useRawText`) | DetailTabs · 탭 7 원문 상자 | | 있음 |
| 296 | API `GET /raw/{id}` 미리보기 · 저장 (`useRawFile` · `rawDocumentRequest`) | DetailTabs · 탭 7 "미리보기 닫기 · 원문 파일 저장" | | 있음 |

## 17. 판정 기록 (`JudgmentsTab.tsx`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 297 | 기록 없음 (`page.G3.judgment.none` "판정 기록 없음") | DetailTabs · "판정 기록 (운영자용) — 펼친 모습" "기록이 0건이면 '판정 기록 없음'" | | 문구로만 |
| 298 | 표 열 번호 (`page.G3.judgment.seq`) | DetailTabs · 판정 기록 표 "번호" | | 있음 |
| 299 | 표 열 도구 (`page.G3.judgment.tool`) | DetailTabs · 같은 표 "판정 종류" | 도구 → 판정 종류 | 있음 |
| 300 | 표 열 목적 (`page.G3.judgment.purpose`) | DetailTabs · 같은 표 "무엇을 물었나"(쉬운 설명 + 목적 원문) | 목적 → 무엇을 물었나 | 있음 |
| 301 | 표 열 상태 (`page.G3.judgment.status`) | DetailTabs · 같은 표 "상태" | | 있음 |
| 302 | 표 열 모델 (`page.G3.judgment.model`) | DetailTabs · 같은 표 "모델" | | 있음 |
| 303 | 표 열 신뢰도(없으면 확인 불가) (`page.G3.judgment.confidence`) | DetailTabs · 같은 표 "자신감" · "확인 불가" | 신뢰도 → 자신감 | 있음 |
| 304 | 표 열 소요 (`page.G3.judgment.duration` / `judgment.ms`) | DetailTabs · 같은 표 "걸린 시간" | 소요 → 걸린 시간 | 있음 |
| 305 | 표 열 시각 (`page.G3.judgment.createdAt`) | DetailTabs · 같은 표 "시각" | | 있음 |
| 306 | 미해결 줄 회색 + 미해결 배지 (`isUnresolved` · `page.common.unresolved`) | DetailTabs · 같은 곳 "'미해결'(검토·질문 남김·차단·오류) 줄은 회색" + "다른 상태: … 미해결" | | 있음 |
| 307 | 상태 배지 (`page.common.status.*`) | DetailTabs · 같은 곳 "정상 / 검토 / 질문 남김 / 차단 / 오류" | | 있음 |
| 308 | 캐시 배지 (`components/CachedBadge.tsx` · `badge.cached`) | DetailTabs · 같은 곳 "저장된 결과 재사용 (캐시)" | 캐시 → 저장된 결과 재사용 (캐시) | 있음 |
| 309 | 오류 문구 한 줄 (`error_text`) | DetailTabs · 같은 곳 "+ 오류 문구 한 줄" | | 있음 |
| 310 | 로컬 배지 + title (`page.G3.judgment.local` / `localHint`) | DetailTabs · 같은 곳 "로컬 처리"(title 판정기가 모델을 부르지 않은 로컬 처리) | 로컬 → 로컬 처리 | 있음 |
| 311 | provider 괄호 (`page.G3.judgment.provider` "({provider})") | DetailTabs · 같은 표 "jev-1.13.0 (typesafe)" | | 있음 |
| 312 | 모델 기록 없음 (`page.G3.judgment.modelNone` "기록 없음") | DetailTabs · 같은 곳 "모델 칸이 비면 '기록 없음'" | | 있음 |

## 요약

전체 312 · 있음 280 · 문구로만 25 · 다른 보드 7 · 빠짐 0

(2026-10-16 목업 고침 뒤 다시 셈. 고치기 전: 있음 245 · 문구로만 25 · 다른 보드 7 · 빠짐 35. 고친 곳 목록은 `../fixes/fixes-Detail.md` · `fixes-DetailTabs.md` · `fixes-Mobile.md`)

보드별 있음 위치: 머리 · 질문형 섹션은 대부분 Detail, 다른 상태 · 탭 2~7 · 판정 기록 · 휴대폰 고르기 상자는 DetailTabs, 휴대폰 화면은 Mobile(Mobile 에 분양가 상한제 · 주소 접힘을 더함 — 고침 MB-2 · MB-3).

빠짐 목록: 없음

고침으로 빠짐 → 문구로만이 된 것(그림으로 못 그리는 동작 — 보드 맨 아래 "구현할 때 지금 동작 그대로 유지" 상자):
- #5 라벨 뜻 Esc 로 닫기 · #24 모르는 해시면 첫 탭 · #25 `#judgments` 로 판정 기록 구획 자동 펼침 · #29 탭 패널 role=tabpanel — Detail 상자(고침 DT-7)
- #291 강조 위치로 스크롤 — DetailTabs 상자(고침 DX-13)

고치기 전 빠짐 목록(기록용, 모두 고침):
- ~~#5 라벨 뜻 Esc 로 닫기 — 목업에 없음~~
- ~~#24 모르는 해시면 첫 탭 — 목업에 없음(동작)~~
- ~~#25 `#judgments` 로 판정 기록 구획 자동 펼침 — 목업에 없음~~
- ~~#29 탭 패널 role=tabpanel · aria-labelledby — 목업에 없음~~
- ~~#40 생활권 이름 — 목업은 구 · 동 주소로 대신~~
- ~~#48 접수 확인 불가 사유 · 날짜 — 상세 보드에 없음(ListTable 에만)~~
- ~~#59 경쟁률 요약 기준 행 없을 때 '확인 불가(사유)' — 목업에 없음~~
- ~~#70 채택 보류 짧은 안내(.17 `heldBasis`) — 목업은 긴 안내만~~
- ~~#77 추정 할인 안내 — 기준 타입 모를 때(`discountEstimated`) — 목업에 없음~~
- ~~#98 종합 점수 용어 ⓘ — 목업 점수 칸에 ? 없음~~
- ~~#99 점수 없음 → 확인 불가 — 목업에 없음~~
- ~~#114 탭 1 안 채택 보류 안내 — 머리 메모만 그림~~
- ~~#115 탭 1 할인(공고 명시) 줄 + 차감 문구 — 목업에 없음~~
- ~~#118 타입 없음 "없음" — Coverage 보드가 생략 표시~~
- ~~#130 그 타입 할인 없음 "없음" — 목업에 없음~~
- ~~#132 필수 옵션 고지 칸 안 글(타입마다 다를 때) — 목업에 없음~~
- ~~#133 납부 조건 없음 "없음" — Coverage 보드가 생략 표시~~
- ~~#164 C08 범례 — 줄 이름이 대신~~
- ~~#167 C08 툴팁 — 정적 목업~~
- ~~#189 C02 단지 축 라벨 대체(연도) — 대체 단지 모양 없음~~
- ~~#191 C02 연식 보정 중앙값 점 + 범례 — 목업에 없음~~
- ~~#193 C02 툴팁 — 정적 목업~~
- ~~#204 C02 표 열 거래 기간 — 목업은 '거래 수'로 바꿈~~
- ~~#211 C01 x축 확률 눈금 — 기준선 · 막대 끝 %만~~
- ~~#215 C01 툴팁 — 정적 목업~~
- ~~#231 C09 단계 칸 안 항목 모양 — 0건 단지라 없음~~
- ~~#235~#240 C09 표로 보기 표 6열(이름 · 구분 · 단계 · 확률 · 예정 · 위치 확정) — 버튼만 있고 표 내용 없음 (빠짐 6줄을 여기 한 줄로 묶음)~~
- ~~#280 출처 조회 오류 문구 — 목업에 없음~~
- ~~#284 원문 파일 내려받기 오류 — 목업에 없음~~
- ~~#291 강조 위치로 스크롤 — 목업에 없음(동작)~~

다른 보드(Shell): #6 불러오는 중 · #7 불러오기 오류 · #8 준비 중 · #9 시나리오 결과 없음 · #10 저장본 검증 실패 · #111 출처 서랍 · #112 용어 팝오버

## 새로 더한 것 (기존에 없던 것)

| # | 새 기능 | 새 목업 위치 (보드 · 섹션 제목) | 메모 |
|---|---|---|---|
| 1 | 지금 상태 요약 문장("본 청약은 … 끝났고, 지금은 남은 집을 … 되팔기 제한은 …") | Detail · 머리 카드 / Mobile · 머리 | 고침 DT-1 · MB-1: 판단성 요약 문장을 서버 필드 사실 줄(현재 적용 공고 · 접수 상태 · 전매 종료 · 거주의무)로 바꿈 |
| 2 | 상세에서 비교에 담기 | Detail · 머리 카드 "비교에 담기" / Mobile · 위 막대 버튼 | 지금은 G2 트레이에서만 담음 — 트레이 상태를 화면 사이에 공유해야 함 |
| 3 | 평수 환산 "약 34평" | Detail · 분양가 · 자세히 보기 표 / Mobile | FactCell 숫자 포맷 규칙 추가 |
| 4 | "층에 따라 달라요" 가격 설명 | Detail · 머리 카드 분양가 | |
| 5 | 주변 거래 비교 작은 카드(이 단지 중간 · 주변 거래 중간 · n% 높아요 · 근처 n개 단지 실거래 n건 · 국토교통부) | Detail · 머리 카드 / Mobile "주변 거래보다 8.1% 높아요" | 고침 DT-3: 서버에 없는 '주변 거래 중간'(전체 가운데값)·막대를 뺌 → [값] API 필요. 가격 갭 % · 이 단지 가운데값 · 비교 단지 수 · 거래 수(개수 세기)만 |
| 6 | 납부 비율 띠 그래프(role=img) | Detail · 돈 / Mobile · 돈 | |
| 7 | 계약금 · 중도금 · 잔금을 언제 내는지 쉬운 설명 | Detail · 돈 / Mobile · 돈 | ko.json 문구 추가 |
| 8 | 조건 값 쉬운 말(의무 없음 · 제한 없음 · 아님 · 적용 안 됨) + 전매 남은 날 "56일 남음" | Detail · 조건 / Mobile · 조건 | |
| 9 | 일정 진행 타임라인(오늘 점 · '지금' 단계 · 되팔기 가능 · 입주 줄) | Detail · "일정은 어디쯤 왔나요?" / Mobile · 일정 | 되팔기 가능 · 입주 줄은 기존 Fact 를 일정에 합친 것 |
| 10 | 타입별 1순위 경쟁률 요약 목록 + 당첨 가점 범위(30~63점) + 가점 ? | Detail · "작년 청약 때 얼마나 몰렸나요?" | 고침 DT-6: 가점 범위(30~63점)는 화면이 묶은 값이라 [값] + API 필요로 바꿈 |
| 11 | 점수 분해 6성분(쉬운 이름 · 비중 · 성분 점수 · 근거 한 줄) | Detail · "점수는 왜 이렇게 나왔나요?" / Mobile · 점수 4개 + "6가지 기준 모두 보기" | 지금 G3 에 없음(G1 · G4 에 있음) |
| 12 | 자세히 보기 안 간단 가격표(평형 · 세대수 · 가장 낮은 층 · 가장 높은 가격) + "타입 2개 더 보기" 접기 | Detail · "자세히 보기" | |
| 13 | 표 · 차트마다 출처 한 줄("자료: … · 확인 …") | Detail · DetailTabs 곳곳 | |
| 14 | 공급 종류 문구가 여럿이라는 안내 "공급 종류 문구가 여럿이에요 (무순위·선착순)" | DetailTabs · 이름·상태 줄 | ko.json 에 없는 문구 · 계약 확인 필요 |
| 15 | 새 용어 ? — 1차 계약금 · 순위 변화 · 가격 차이(G3 안) · 가점 | DetailTabs · 돈 카드 · 점수 카드 · 탭 3 · 탭 4 / Detail · 경쟁률 | glossary 항목 추가 |
| 16 | 납부 순서 목록(탭 2) | DetailTabs · 탭 2 `<ol>` 납부 순서 | |
| 17 | 중도금 '다음 납부' 표시 | DetailTabs · 탭 2 중도금 일정 "D-54 · 다음 납부" / Mobile · 아래 "다음 납부 2026.12.07 D-54" | |
| 18 | 경쟁률 보는 범위 고르기(1순위 지역 거주자 + 무순위 / 전체 34줄, aria-pressed) + 줄 수 | DetailTabs · 탭 3 | 새 필터 |
| 19 | 무순위 줄 강조 배경 | DetailTabs · 탭 3 경쟁률 표 | |
| 20 | 최고 경쟁률 계산식 "접수 454 ÷ 공급 73" | DetailTabs · 탭 3 요약 | 고침 DX-6: 계산식 뺌 → '기준: 본청약 1순위 · 지역 거주자 (서버 요약 값)' |
| 21 | C08 기준일 세로선 "기준일 10.14" | DetailTabs · 탭 3 그림 | |
| 22 | C02 비교 단지 전체 가운데값 세로 점선 + 범례 | DetailTabs · 탭 4 그림 | 고침 DX-8: 서버에 없는 값이라 세로 점선 · 범례 · 설명 문장을 뺌 |
| 23 | C02 거래 수(줄 메타 · 표 열) + "거래 94건(이상한 값 11건 뺌)" | DetailTabs · 탭 4 | 거래 기간 열은 다시 넣음(고침 DX-9) — 거래 수 열은 n_trades 로 함께 둠 |
| 24 | C01 "점수에 씀" 표시(+10%) · 판정 기록 번호 · '필요한 연 상승률' 풀이 문단 | DetailTabs · 탭 5 | |
| 25 | 원문 메타 "1순위 자료 · 채택" · 칠한 줄 풀이 문장 · 원문 전체 글자 수 | DetailTabs · 탭 7 | 풀이 문장은 서버 문구 필요 |
| 26 | 판정 기록 '무엇을 물었나' 쉬운 설명(목적 원문 위) | DetailTabs · 판정 기록 펼친 모습 | |
| 27 | 휴대폰 위 막대(뒤로 · 비교 담기) + 아래 주 메뉴 | Mobile | 공통 틀 쪽 · 아래 주 메뉴는 지금 3개(홈 · 단지 리스트 · 용어)로 고침(MB-5) |
