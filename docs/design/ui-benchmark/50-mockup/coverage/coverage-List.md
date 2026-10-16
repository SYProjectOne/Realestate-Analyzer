# 대응표 — G2 단지 리스트 → List.dc.html + ListTable.dc.html

- 현재 소스: `frontend/src/pages/complexes/` 전체(index.tsx · ComplexTable.tsx · ComplexCards.tsx · FilterBar.tsx · params.ts) + 쓰는 공통 부품(`pages/_shared` · `components/*` · `layout/PageShell.tsx`) + `i18n/ko.json`
- 보드: `boards/List.dc.html`(데스크톱 카드 보기) · `boards/ListTable.dc.html`(표 보기 · 펼친 모습 · 다른 상태 · 휴대폰)
- 보드 칸에는 둘 중 어느 보드인지 적는다. 공통 부품(출처 창 · 용어 창 · 시나리오 안내)은 `Shell` 보드에 있어 `다른 보드(Shell)`로 적는다.
- 경로는 `frontend/src/` 기준. API 줄은 "그 응답이 그리는 칸이 보드에 있으면 있음"으로 적었다.
- "문구로만" = 보드에 그림 없이 설명 글로만 있음. 동작(URL · 저장 · 스크롤)은 설명이 있으면 문구로만, 없으면 빠짐.
- 지금 카드 목록(ComplexCards)은 휴대폰 전용이다. List 보드의 데스크톱 카드 보기는 새로 더한 것이고, 지금 카드 기능은 ListTable 의 "휴대폰" 부분에 대응한다.

## 1. 화면 틀 · 데이터 (`pages/complexes/index.tsx`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 1 | h1 제목 (`index.tsx` PageShell · `page.G2.title` "단지 리스트") | List · ListTable · h1 "인천 분양 단지 100곳" / ListTable · 휴대폰 "단지 찾기" | 단지 리스트 → {지역} 분양 단지 {n}곳 (주 메뉴 이름 '단지 찾기') | 있음 |
| 2 | 안내 (`page.G2.intro`) | ListTable · 머리 안내 "표로 한눈에 비교해요. 단지 이름을 누르면 상세가 열리고, …" / List · 머리 안내 | | 있음 |
| 3 | 출처 범례 한 줄 (`components/ProvenanceLegend.tsx` · `label.legend`) | ListTable · 바닥 문구 "… 숫자를 누르면 출처가 열려요" | → 점선 밑줄 숫자를 누르면 출처가 열려요 | 있음(List 보드에는 없음) |
| 4 | 라벨 뜻 펼침 ⓘ + 정의 6개 (`label.legendHelp` / `label.help.*`) | ListTable · 바닥 "라벨 뜻 보기" + Shell · 3 펼친 모습 | 라벨 뜻 ⓘ → 라벨 뜻 보기 | 있음 |
| 5 | CSV 내려받기 버튼(스냅샷 있을 때만) (`index.tsx` · `page.G2.csv` "CSV 내려받기") | ListTable · 머리 "엑셀용 파일(CSV) 내려받기" | → 엑셀용 파일(CSV) 내려받기 | 있음 |
| 6 | CSV 내려받는 중 · 버튼 잠김 (`api/download.ts` useDownload · `download.pending`) | ListTable · "내려받기 · 비교 바구니 상태" "내려받는 중…" | | 있음 |
| 7 | CSV 오류 role=alert (`download.error` "내려받지 못했습니다: {detail}") | ListTable · 같은 곳 "내려받지 못했어요: [사유]" | | 있음 |
| 8 | CSV 특수 오류 문구(준비 중 · 저장본 검증 실패) (`lib/errorText.ts` specialErrorText · `page.common.materializePendingStill` / `storedViewMismatch`) | — | | 빠짐(목업에 없음) |
| 9 | CSV 에 지금 필터 · 정렬 그대로 (`complexesCsvRequest(snapshotId, listParams)`) | ListTable · 같은 곳 "파일에는 지금 고른 필터·정렬이 그대로 들어가요" | | 문구로만 |
| 10 | API `GET /snapshots/{sid}/complexes.csv` (`api/hooks.ts` complexesCsvRequest) | ListTable · CSV 버튼 | | 있음 |
| 11 | API `GET /snapshots/{sid}/complexes` filter[...] · sort · scenario (`useComplexesProgressive`) | ListTable · 단지 표 / List · 카드 / ListTable · 휴대폰 카드 | | 있음 |
| 12 | 첫 100곳 먼저 → 나머지 1000곳씩 이어 받기 (`FIRST_PAGE_SIZE` / `PAGE_SIZE`) | ListTable · "개수 줄 · 불러오기" "처음 100곳을 먼저 보여 주고 나머지를 이어 받아 같은 표 아래에 붙여요" | | 문구로만 |
| 13 | 기준일 없음 (`_shared` NoSnapshot · `app.noSnapshot`) | ListTable · 같은 곳 "아직 기준일 자료가 없어요. 지역 분석이 끝나면 나타나요" | | 있음 |
| 14 | 첫 적재 중 (`app.noSnapshotBootstrapping`) | ListTable · 같은 줄 괄호 "(첫 적재 중이면 …)" | | 있음 |
| 15 | 불러오는 중 (`_shared` QueryState · `app.loading`) | ListTable · 같은 곳 "불러오는 중…" | | 있음 |
| 16 | 불러오기 오류 (`page.common.loadError`) | ListTable · 같은 곳 "불러오지 못했어요: [사유] · 다시 시도" | 지금 일반 오류엔 다시 시도 버튼 없음(목업은 있음) | 있음 |
| 17 | 리비전 준비 중 · 자동 재시도 · 다시 시도 (`page.common.materializePending` / `app.retry`) | ListTable · 같은 곳 "이 기준일(n번째 수정본)의 화면 자료를 준비하는 중이에요 — …" | | 있음 |
| 18 | 필터 바꾸는 동안 이전 목록 + 준비 중 줄 (`QueryState` isPlaceholderData, M7) | — | | 빠짐(목업에 없음) |
| 19 | 발행 뒤 만든 시나리오 결과 없음 + 실행 링크 (`page.common.scenarioMissing` / `scenarioMissingRun`) | Shell · 7 "이 상황의 결과가 아직 없어요" | | 다른 보드(Shell) |
| 20 | 저장본 검증 실패(목록) (`page.common.storedViewMismatch`) | Shell · 7 "보던 기준일과 저장된 화면이 다를 때도 안내가 떠요" | | 다른 보드(Shell) |
| 21 | 개수 줄 aria-live (`page.G2.count` "{shown} / {total}곳") | ListTable · 표 위 "100곳 중 {n}곳을 보여요 · 정렬 …" / 휴대폰 "100곳 중 100곳" | → {total}곳 중 {shown}곳을 보여요 | 있음 |
| 22 | 나머지 불러오는 중 role=status (`page.G2.loadingMore`) | ListTable · "개수 줄 · 불러오기" "나머지 단지를 불러오는 중…" | | 있음 |
| 23 | 빈 결과 (`page.G2.empty` "조건에 맞는 단지가 없습니다") | ListTable · "조건에 맞는 단지가 없을 때" | | 있음 |
| 24 | 읽기 전용(휴대폰 ≤768px) → 표 대신 카드 · 비교 담기 · 열 고르기 숨김 (`readOnly` · `data-write`) | ListTable · "휴대폰 (폭 768px 이하) · 표 대신 카드, 비교 담기 없음(읽기 전용), 필터는 전체 화면 시트" | | 있음 |

## 2. 비교 트레이 (`index.tsx` CompareTray)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 25 | 트레이 aside (`page.G2.tray` "비교 트레이") | ListTable · aside "비교 바구니" | 비교 트레이 → 비교 바구니 | 있음 |
| 26 | 선택 수 (`page.G2.trayCount` "{n}개 선택") | ListTable · 같은 곳 "{n}개 골랐어요" | → {n}개 골랐어요 | 있음 |
| 27 | 고른 단지 칩 × 빼기 (`page.common.remove` "{name} 빼기") | ListTable · 같은 곳 칩(aria "… 빼기") | | 있음 |
| 28 | 이름 모르면 "#id" (`names.get(id) ?? #id`) | — | | 빠짐(목업에 없음) |
| 29 | 안내 (`page.G2.trayHint` "2~6개를 고르면 비교할 수 있습니다") | ListTable · 같은 곳 + 다른 상태 "1개 골랐어요 · 2~6개를 고르면 비교할 수 있어요" | | 있음 |
| 30 | 최대 안내 (`page.G2.trayMax` "최대 6개까지 비교합니다") | ListTable · 다른 상태 "6개 골랐어요 · 최대 6개까지 비교해요 — 다른 단지 체크 칸은 잠겨요" | | 있음 |
| 31 | 선택 해제(1개 이상일 때) (`page.G2.clearSelection`) | ListTable · 같은 곳 "선택 해제" | | 있음 |
| 32 | 비교 링크 2~6개 → `/compare?ids=` (전역 쿼리 유지) (`page.G2.compare` "비교") | ListTable · 같은 곳 "나란히 비교하기" | 비교 → 나란히 비교하기 | 있음 |
| 33 | 비교 버튼 잠김(1개 이하) | ListTable · 다른 상태 "나란히 비교하기 (잠김)" | | 있음 |
| 34 | 트레이 화면 아래 고정 + 표 높이에서 트레이 자리 비움 (`sticky bottom-10` · `TRAY_RESERVE`) | ListTable · 같은 곳 "비교 바구니 (화면 아래에 붙어 따라와요)" | | 문구로만 |
| 35 | 6개 넘게 담기 막음 · 나머지 체크 잠김 (`MAX_COMPARE` · checkbox disabled) | ListTable · 표 체크 칸 잠김(title "최대 6개까지 비교해요") | | 있음 |

## 3. 필터 · 정렬 ↔ URL (`params.ts` · `index.tsx`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 36 | 필터 값 = URL 쿼리, 바꿀 때 replace (`readFilters` · `setFilter`) | — | | 빠짐(목업에 없음 — 동작) |
| 37 | 가격 억 입력 → API 원 변환 (`toApiFilter` EOK) | ListTable · 필터 이름 "가격 최소 (억원)" | | 문구로만 |
| 38 | 기본 정렬 종합 점수 내림차순 (`DEFAULT_SORT` "-total") | ListTable · 개수 줄 "정렬 종합 점수 큰 값부터"(기본) | List 보드 정렬 상자 첫 값은 '접수 가능 먼저'(다름) | 있음 |
| 39 | 모르는 정렬 키 → 기본 정렬 (`readSort`) | — | | 빠짐(목업에 없음 — 동작) |
| 40 | URL 전용 정렬 키 rank (`SORT_KEYS`) | ListTable · "정렬 · 머리 버튼" "판정기 순위(점수 순위)로도 정렬할 수 있어요(주소창 sort=rank)" | | 문구로만 |
| 41 | URL 전용 정렬 키 price_low (`SORT_KEYS`) | — (List 정렬 상자 "가격 낮은 순"이 어느 키인지 목업에 없음) | | 빠짐(목업에 키 표기 없음) |
| 42 | 머리 누름 순서: 새 열은 큰 값부터 · 같은 열은 뒤집기 · 접수는 가능 먼저 (`nextSort` · `ASC_FIRST`) | ListTable · "정렬 · 머리 버튼" 설명 + 목업 동작 | | 있음 |
| 43 | 필터 초기화가 정렬도 지움 (`resetFilters` sort 삭제) | — | | 빠짐(목업에 없음) |

## 4. 필터 — 데스크톱 (`FilterBar.tsx` DesktopFilterBar)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 44 | 필터 form role=search (`page.G2.filters` "필터") | ListTable · form role=search aria-label 필터 | | 있음 |
| 45 | 단지명 글 입력 (`page.G2.filter.q` "단지명") | ListTable · "단지 이름" 검색칸(예: 시티오씨엘) / List · "단지 이름 검색" | 단지명 → 단지 이름 | 있음 |
| 46 | 접수 고르기 상자 4개 상태 (`page.G2.filter.intake_status` "접수", `intake.status.*`) | ListTable · "접수 상태 ?" (접수 가능 · 접수 일정 미정 · 접수 상태 확인 못 함 · 지금은 접수 안 됨) | 접수 → 접수 상태, 접수 미정 → 접수 일정 미정, 접수 확인 불가 → 접수 상태 확인 못 함, 접수 불가 → 지금은 접수 안 됨 | 있음 |
| 47 | 생활권 고르기 상자(지역의 생활권 목록) (`page.G2.filter.living_area` "생활권") | ListTable · "생활권(구) ?" / List · "구" | 생활권 → 생활권(구) · List 는 구 | 있음 |
| 48 | 고르기 상자 '전체' 값 (`page.common.all`) | ListTable · 각 상자 "전체" / List "구 전체" · "가격 전체" | | 있음 |
| 49 | 지금 접수 가능만 칩 aria-pressed (`page.G2.openNowChip` / `openNowChipOff` "전체 보기") | ListTable · 칩 "지금 접수 가능만 보기 / 전체 보기" / List · 칩 "지금 접수 가능 3" | | 있음 |
| 50 | 필터 더 보기 (적용 n) / 필터 접기, aria-expanded · aria-controls (`page.G2.filtersMore` / `filtersLess`) | ListTable · 같은 버튼 | | 있음 |
| 51 | 숨은 필터에 값 있으면 자동 펼침 (`useEffect applied`) | ListTable · 빈 결과 아래 설명 "'필터 더 보기' 안에 값이 있으면 … 펼쳐서 보여 줘요" | | 문구로만 |
| 52 | 필터 초기화 (`page.G2.clearFilters`) | ListTable · 버튼 "필터 초기화" | | 있음 |
| 53 | 택지 종류 고르기 상자 (`page.G2.filter.land_type`, `page.G2.landType.*`) | ListTable · 더 보기 "땅 종류 (공공·민간 택지)" | 택지 종류(공공·민간) → 땅 종류 (공공·민간 택지) | 있음 |
| 54 | 이 날짜 전 전매 종료 date (`page.G2.filter.resale_end_before`) | ListTable · 더 보기 "이 날짜 전에 되팔 수 있게 됨" | 전매 종료 → 되팔 수 있게 됨 | 있음 |
| 55 | 가격 하한(억) number · decimal (`page.G2.filter.price_min`) | ListTable · 더 보기 "가격 최소 (억원)" (예: 5) / List · "가격대" 고르기(구간 3개) | 가격 하한(억) → 가격 최소 (억원) | 있음 |
| 56 | 가격 상한(억) (`page.G2.filter.price_max`) | ListTable · 더 보기 "가격 최대 (억원)" (예: 7.5) / List · "가격대" | | 있음 |
| 57 | 입주연도 number · numeric (`page.G2.filter.move_in_year`) | ListTable · 더 보기 "입주 연도" (예: 2029) | | 있음 |
| 58 | 단지 분류 고르기 상자 9개 (`page.G2.filter.inclusion_class`, `page.common.inclusion.*`) | ListTable · 더 보기 "단지 종류 (분류) ?" | 비아파트 → 아파트 아님, 미분류 → 아직 분류 안 됨 | 있음 |
| 59 | 점수 계산 범위 고르기 상자 5개 (`page.G2.filter.judge_scope`, `page.common.judgeScope.*`) | ListTable · 더 보기 "점수 계산 범위 ?" | 판정 대상 → 점수 계산 대상 | 있음 |
| 60 | 숫자 칸 잘못된 값은 조용히 무시(오류 문구 없음) (`toApiFilter` Number.isFinite / isInteger) | — | | 빠짐(목업에 입력 검증 모습 없음 — 지금도 화면 오류 문구는 없음) |

## 5. 필터 — 휴대폰 (`FilterBar.tsx` MobileFilterBar)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 61 | 단지명 칸 | ListTable · 휴대폰 "단지 이름" | | 있음 |
| 62 | 필터 (적용 n) 버튼, aria-haspopup=dialog, 단지명은 셈에서 뺌 (`page.G2.card.filterSheet`) | ListTable · 휴대폰 "필터 (적용 2)" | | 있음 |
| 63 | 지금 접수 가능만 칩 | ListTable · 휴대폰 "지금 접수 가능만 보기" | | 있음 |
| 64 | 전체 화면 시트 dialog aria-modal + 필터 10칸 (`page.G2.filters`) | ListTable · 휴대폰 dialog "필터" 10칸 | | 있음 |
| 65 | 시트 Esc 로 닫기 | ListTable · 시트 안 "Esc로 닫기" | | 문구로만 |
| 66 | 적용(시트 닫기) (`page.G2.card.filterApply`) | ListTable · 시트 "적용" | | 있음 |
| 67 | 초기화 (`page.G2.card.filterReset`) | ListTable · 시트 "초기화" | | 있음 |

## 6. 표 (`ComplexTable.tsx`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 68 | 열 선택 펼침 details (`ColumnChooser` · `page.G2.columns` "열 선택") | ListTable · "보여 줄 열 고르기 ({n}개 켜짐)" | 열 선택 → 보여 줄 열 고르기 | 있음 |
| 69 | 숨길 수 있는 열 체크 14개 | ListTable · 같은 곳 열 목록(+ '숨김' 표시) | | 있음 |
| 70 | 열 선택 저장 localStorage `sa.g2.columns`(v2, 옛 저장값 옮기기) (`readVisibility` / `saveVisibility`) | ListTable · 같은 곳 "고른 열은 이 브라우저에 기억돼요" | 옛 저장값 옮기기는 목업 대상 아님 | 문구로만 |
| 71 | 기본 8열 · 단지와 비교 열은 늘 보임 (`DEFAULT_HIDDEN` · enableHiding false) | ListTable · 같은 곳 "기본 8열은 켜져 있어요 … '단지'와 '비교 담기' 열은 늘 보여요" | | 있음 |
| 72 | 표 aria-label · aria-rowcount (`page.G2.table` "단지 표") | ListTable · role=table aria-label "단지 표" aria-rowcount | | 있음 |
| 73 | 가상 스크롤 · 창 높이 맞춤 · 범위 붙잡기(R8-JITTER) (`useVirtualizer` · `useFitHeight` · `nextHeldRange`) | ListTable · 표 아래 "아래로 내리면 나머지 단지가 이어서 나와요" | | 문구로만 |
| 74 | 머리줄 고정 (`thead sticky top-0`) | ListTable · 표 머리 칸(position sticky) | | 있음 |
| 75 | 정렬 버튼 + aria-sort + ▲▼↕ + title (`SortButton` · `page.G2.sortAsc` / `sortDesc`) | ListTable · 머리 버튼(위 · 아래 삼각형, title "… 큰 값부터 정렬") + "정렬 · 머리 버튼" "정렬 안 함 / 작은 값부터 / 큰 값부터" | 오름차순 → 작은 값부터, 내림차순 → 큰 값부터 | 있음 |
| 76 | 정렬되는 열 10개 (`SORT_OF`) | ListTable · "정렬할 수 있는 열: 단지 이름 · 생활권 · 접수 · …" | | 있음 |
| 77 | 열 제목 용어 ⓘ 9개 (`TERM_OF` · `Term.tsx`) | ListTable · 머리 ? 버튼(같은 9열) | ⓘ → ? | 있음 |
| 78 | 고른 행 aria-selected | ListTable · 행 aria-selected(+ 배경 강조) | | 있음 |
| 79 | 열 비교 선택 체크 (`page.G2.col.select` "비교 선택" sr-only · `page.G2.select` "{name} 비교에 담기") | ListTable · 열 "비교 담기" + 체크 aria "… 비교에 담기" | 비교 선택 → 비교 담기 | 있음 |
| 80 | 열 단지 — 상세 링크 (`page.G2.col.name` "단지") | ListTable · 열 "단지" 이름 링크 | | 있음 |
| 81 | 열 단지 — 이름 라벨 배지 → 출처 서랍 (`_shared` NameLabelBadge) | ListTable · 같은 칸 "확인됨" 버튼(title 이름 출처 보기) | | 있음 |
| 82 | 열 단지 — 이름 아래 생활권 | ListTable · 같은 칸 아래 "미추홀구" | | 있음 |
| 83 | 열 접수 — 배지(경로 없이) + 사유 · 날짜 아래 줄 (`page.G2.col.intake`, IntakeBadge reasonBelow) | ListTable · 열 "접수 ?" 상태 알약 + 아래 메모("자동 확인이 끝나지 않음 · 10.14") | | 있음 |
| 84 | 열 현재 구매가 억 단위 낮은~높은 (`page.G2.col.price`) | ListTable · 열 "현재 가격 (분양가) ?" "5.99억 ~ 6.51억" | 현재 구매가 → 현재 가격 (분양가) | 있음 |
| 85 | 열 계약금 비율 (`page.G2.col.down_payment`) | ListTable · 열 "계약금 비율 ?" | | 있음 |
| 86 | 열 전매 종료(D±) (`page.G2.col.resale_end`) | ListTable · 열 "되팔기 가능 날짜 ?" "2026.12.09 D-56 추정" | 전매 종료 → 되팔기 가능 날짜 | 있음 |
| 87 | 열 입주 (`page.G2.col.move_in`) | ListTable · 열 "입주" | | 있음 |
| 88 | 열 가격 갭 (`page.G2.col.gap` "가격 갭(주변 대비)") | ListTable · 열 "주변 시세와 가격 차이 ?" | → 주변 시세와 가격 차이 | 있음 |
| 89 | 열 종합 점수 + 순위 배지 (`page.G2.col.total` "종합 점수(상대 비교)", `page.common.rank`) | ListTable · 열 "종합 점수 (상대 비교) ?" + "1위" | | 있음 |
| 90 | 점수 칸 동률 배지 (`TieBadge`) | ListTable · 점수 칸 "동률"(title) + "점수 칸에 붙는 배지" | | 있음 |
| 91 | 점수 칸 순위 불안정 (`UnstableBadge`) | ListTable · "점수 칸에 붙는 배지" "순위 불안정" | | 있음 |
| 92 | 점수 칸 판정 범위 배지('판정 대상'은 생략) (`JudgeScopeBadge hideTarget`) | ListTable · 점수 칸 + "표에서는 '점수 계산 대상'은 기본이라 배지를 생략해요" | | 있음 |
| 93 | 점수 칸 재판정 필요 (`RejudgeNeededBadge`) | ListTable · "점수 칸에 붙는 배지" "다시 계산 필요" | 재판정 필요 → 다시 계산 필요 | 있음 |
| 94 | 열 생활권(기본 숨김) (`page.G2.col.living_area`) | ListTable · "숨김 열을 모두 켠 모습" "생활권(구)" | | 있음 |
| 95 | 열 +10% 상승 가능성(기본 숨김) (`page.G2.col.p10`) | ListTable · 같은 표 "입주 뒤 10% 넘게 오를 가능성 (판정기)" | | 있음 |
| 96 | 열 단지 분류 + 검토 배지(decision ≠ auto) (`page.G2.col.inclusion`, `page.common.status.review`) | ListTable · 같은 표 "단지 종류 · 점수 계산 범위 이유" + "검토 중" | 단지 분류 → 단지 종류, 검토 → 검토 중 | 있음 |
| 97 | 단지 분류 칸 점수 계산 범위 사유(서버 문자열, 잘림 · title) (`ScopeReason compact`) | ListTable · 같은 칸 아래 작은 글씨 | 목업 설명은 '서버가 준 문장을 쉬운 말로' — 지금은 서버 문자열 그대로(규칙 3) | 있음 |
| 98 | 사유 재판정 덧붙임(title) (`page.common.scopeReasonCurrent`) | ListTable · 같은 표 아래 "'다시 계산 필요' 배지가 붙은 단지는 이 이유가 지금 사실 기준이라 …" | | 문구로만 |
| 99 | 열 택지 종류(기본 숨김) (`page.G2.col.land_type`) | ListTable · 같은 표 "땅 종류" | 택지 종류 → 땅 종류 | 있음 |
| 100 | 열 총 세대(기본 숨김) (`page.G2.col.units_total`) | ListTable · 같은 표 "총 세대" | | 있음 |
| 101 | 열 계약금 금액(기본 숨김) (`page.G2.col.down_payment_won`) | ListTable · 같은 표 "계약금 금액 · 추정 (계산)" | | 있음 |
| 102 | 열 경쟁률(기본 숨김) 최고 + 주택형, 없으면 확인 불가 (`page.G2.col.competition`) | ListTable · 같은 표 "가장 높았던 경쟁률 (1순위 · 지역 거주자)" | | 있음 |
| 103 | 열 마지막 변경(기본 숨김) 필드 · 날짜 · 중요도 (`page.G2.col.last_change`, `page.common.changeField.*` / `severity.*`) | ListTable · 같은 표 "마지막으로 바뀐 것" | | 있음 |
| 104 | 마지막 변경 없음 "없음" (`page.common.none`) | — | | 빠짐(목업에 없음 — 예시 줄 모두 값 있음) |
| 105 | 값 없는 칸 확인 불가(사유) (`FactCell`) | ListTable · 예 "확인 불가(공고에 값이 없음)" · "확인 불가(점수 계산 전)" | | 있음 |

## 7. 카드 — 휴대폰 (`ComplexCards.tsx`)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 106 | 카드 목록 (`page.G2.cards` "단지 카드") | ListTable · 휴대폰 카드 / List · 데스크톱 카드 | | 있음 |
| 107 | 카드 생활권 | ListTable · 휴대폰 "미추홀구" / List "미추홀구 · 1,349세대" | | 있음 |
| 108 | 카드 이름 링크 + 라벨 배지 | ListTable · 휴대폰 "시티오씨엘 8단지 확인됨" / List · 카드 이름(라벨 없음) | | 있음 |
| 109 | 카드 접수 배지(사유 아래) | ListTable · 휴대폰 "접수 가능" / List · 상태 알약 + 메모 | | 있음 |
| 110 | 카드 전매 종료 (`page.G2.card.resaleEnd`) | ListTable · 휴대폰 "되팔기 가능 2026.12.09 · D-56 추정" / List "되팔기 가능 D-56" | 전매 종료 → 되팔기 가능 | 있음 |
| 111 | 카드 현재 구매가 낮은~높은 | ListTable · 휴대폰 "5억 9,850만 ~ 6억 5,090만원" / List | | 있음 |
| 112 | 카드 계약금 비율 + 금액 (`page.G2.card.down`) | ListTable · 휴대폰 "계약금 5% · 3,124만 추정" / List "계약금 추정 3,124만" | | 있음 |
| 113 | 카드 입주 (`page.G2.card.moveIn`) | ListTable · 휴대폰 "입주 2029.07" | | 있음(List 카드에는 없음) |
| 114 | 카드 종합 + 순위 (`page.G2.card.total` "종합") | ListTable · 휴대폰 "종합 4.83 1위" | | 있음(List 카드에는 없음) |
| 115 | 카드 동률 · 판정 범위 · 재판정 배지 | — | | 빠짐(휴대폰 카드에 배지 모습 없음 — 배지 모음은 표 칸 기준) |
| 116 | 카드 상대 비교 (`page.G2.card.relative`) | ListTable · 휴대폰 "상대 비교" | | 있음 |
| 117 | 카드 더 보기 details 가격 갭 · +10% (`page.G2.card.more`) | ListTable · 휴대폰 "더 보기 (주변 시세와 가격 차이 · 오를 가능성)" | | 있음 |
| 118 | 단지 더 보기 30개씩 (`page.G2.card.showMore` "단지 더 보기 ({shown} / {total}곳)") | ListTable · 휴대폰 "단지 더 보기 (30 / 100곳)" / List "92곳 더 보기" | | 있음 |

## 8. 숫자 · 용어 공통

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 119 | 숫자 누르면 출처 서랍 (`FactCell.tsx` → `ProvenancePanel.tsx`) | Shell · 3 "숫자를 누르면 열리는 '출처' 창" | | 다른 보드(Shell) |
| 120 | 용어 ⓘ 팝오버(Esc · 바깥 클릭 닫기, 모바일 아래 시트, 용어 모음 링크) (`Term.tsx`) | Shell · 3 "용어 '?' 를 눌렀을 때" | ⓘ → ? | 다른 보드(Shell) |

## 요약

전체 120 · 있음 96 · 문구로만 10 · 다른 보드 4 · 빠짐 10

보드별 있음 위치: 표 · 필터 · 비교 바구니 · 다른 상태 · 휴대폰은 ListTable, 데스크톱 카드 보기는 List(지금 기능 중 List 에만 있는 것은 없음 — List 칸은 ListTable 위치에 덧붙여 적음).

빠짐 목록:
- #8 CSV 특수 오류 문구(준비 중 · 저장본 검증 실패) — 목업에 없음
- #18 필터 바꾸는 동안 이전 목록 + 준비 중 줄 — 목업에 없음
- #28 트레이 이름 모르면 "#id" — 목업에 없음
- #36 필터 값 = URL 쿼리 — 목업에 없음(동작)
- #39 모르는 정렬 키 → 기본 정렬 — 목업에 없음(동작)
- #41 URL 전용 정렬 키 price_low — 목업에 키 표기 없음(List '가격 낮은 순'의 키 불명)
- #43 필터 초기화가 정렬도 지움 — 목업에 없음
- #60 숫자 칸 잘못된 값 처리(입력 검증) — 목업에 없음(지금도 오류 문구 없음)
- #104 마지막 변경 없음 "없음" — 목업에 없음
- #115 휴대폰 카드 동률 · 판정 범위 · 재판정 배지 — 휴대폰 카드에 없음

다른 보드(Shell): #19 시나리오 결과 없음 · #20 저장본 검증 실패 · #119 출처 서랍 · #120 용어 팝오버

## 새로 더한 것 (기존에 없던 것)

| # | 새 기능 | 새 목업 위치 (보드 · 섹션 제목) | 메모 |
|---|---|---|---|
| 1 | 카드 / 표 보기 전환(보기 방식 group) | ListTable · 머리 "카드 · 표" / List | 지금은 화면 폭으로만 갈림 |
| 2 | 데스크톱 카드 보기 | List 전체 | 지금 카드는 휴대폰 전용 |
| 3 | 정렬 고르기 상자(접수 가능 먼저 · 점수 높은 순 · 되팔기 가까운 순 · 가격 낮은 순) | List · 필터 줄 "정렬" | 키는 기존 intake · -total · resale_end · price_low/price_mid 로 맞춰야 함 |
| 4 | 빠른 칩 "되팔기 제한 곧 끝남" · "실거주 의무 없음" | List · 칩 줄 | 지금 API 필터 키에 없음 — 계약 변경 필요(residency 필터) 또는 resale_end_before 로 대신 |
| 5 | 칩에 개수 표시("지금 접수 가능 3" · "전체 100") | List · 칩 줄 | 개수는 서버 total 필요 |
| 6 | 가격대 구간 고르기(5억 이하 · 5억~7억 · 7억 이상) | List · "가격대" | price_min · price_max 로 풀기 |
| 7 | 생활권 대신 '구' 이름 고르기 | List · "구" | 생활권은 사용자가 편집하는 단위 — 구와 같지 않음, 이름 확정 필요 |
| 8 | 기준일 표시(칩 줄 끝) | List | 공통 틀에도 있음 |
| 9 | 카드 내용 — 공급 종류 메모("무순위 · 선착순", "공급 종류는 상세에서", "이유는 상세에서") · 구 · 세대 수 · 작년 경쟁률 | List · 카드 | 경쟁률은 competition_summary 재사용 |
| 10 | '접수 상태 확인 못 함' 풀이 바닥 문구 | List · 바닥 | |
| 11 | 필터 칸 용어 ?(접수 상태 · 생활권 · 단지 분류 · 점수 계산 범위) | ListTable · 필터 | glossary 항목 재사용 |
| 12 | 입력칸 예시 placeholder(예: 시티오씨엘 · 5 · 7.5 · 2029) | ListTable · 필터 / List | 예시 단지명은 지역명 하드코딩 금지(규칙 15) — 문구 정할 때 주의 |
| 13 | 개수 줄에 정렬 이름 "· 정렬 종합 점수 큰 값부터" | ListTable · 개수 줄 | |
| 14 | 열 고르기에 '숨김' 표시 · 켜진 개수 · 안내 문구 | ListTable · 보여 줄 열 고르기 | |
| 15 | 접수 칸 '가능'에도 확인 경로 · 날짜 메모("10.13 공식 홈페이지 확인") | ListTable · 열 "접수" | 지금은 showPath=false 이고 사유는 확인 불가 · 불가만 |
| 16 | 가격 차이 칸 "높아요 / 낮아요" 글 | ListTable · 열 "주변 시세와 가격 차이" | 평가 말이 아니라 부호 풀이로 유지 |
| 17 | 빈 결과에 '필터 초기화' 버튼 + "필터를 줄이거나 초기화해 보세요" | ListTable · 조건에 맞는 단지가 없을 때 | |
| 18 | 고른 행 배경 강조 | ListTable · 단지 표 | |
| 19 | 표 아래 안내(가격 단위 억원 · D-숫자 뜻 · 점선 밑줄) | ListTable · 표 아래 | |
| 20 | 점수 칸 배지 뜻 모음 | ListTable · "점수 칸에 붙는 배지" | |
| 21 | 머리 정렬 아이콘 3상태(정렬 안 함 · 작은 값부터 · 큰 값부터) 설명 | ListTable · "정렬 · 머리 버튼" | 기능은 #75 와 같고 그림이 새로움 |
