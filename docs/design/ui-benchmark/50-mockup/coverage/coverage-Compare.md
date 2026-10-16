# 대응표 — 비교 G4 (`/compare?ids=`, `frontend/src/pages/compare` + C01·C02·C06·C07·C10) → Compare.dc.html

입력: `frontend/src/pages/compare/index.tsx`, `pages/_shared/index.tsx`, `charts/C01·C02·C06·C07·C10`, `charts/ChartFrame.tsx`, `components/*Badge·FactCell·Term·DataTableToggle`, `layout/PageShell.tsx`, `i18n/ko.json` · 보드: `boards/Compare.dc.html` ("펼친 모습 · 다른 상태" A~L 포함)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 1 | [틀] 화면 제목 h1 (`pages/compare/index.tsx` PageShell · `page.G4.title` "비교") | Compare · 머리 h1 "세 단지를 나란히 놓고 볼게요" (위치 줄 "단지 찾기 › 비교하기") | 비교 → 세 단지를 나란히 놓고 볼게요 | 있음 |
| 2 | [틀] 출처 범례 한 줄 + "라벨 뜻" 버튼 (`layout/PageShell.tsx` legend · `components/ProvenanceLegend.tsx` · `label.legend` "밑줄 친 숫자를 누르면 출처·확인일이 열립니다" · `label.legendHelp`) | Compare · 머리 오른쪽 "밑줄 친 숫자를 누르면 출처·확인일이 열려요 · [?] 라벨 뜻" (펼친 라벨 목록은 Shell · 3) | 라벨 뜻 → [?] 라벨 뜻 | 있음 |
| 3 | [틀] 요약 줄 (`pages/compare/index.tsx` `page.G4.summary` "{n}곳 · 상황: {name} · 상대 비교 · 투자 권유 아님") | Compare · 머리 "3곳 · 상황: 기본 · 상대 비교 · 투자 권유 아님" | — | 있음 |
| 4 | [상태] ids 2~6 검사, 벗어나면 빈 상태 (`pages/compare/index.tsx` parseIds·MIN_IDS·MAX_IDS · `page.G4.invalidIds` "비교할 단지를 2~6개 고르세요(지금 {n}개)") | Compare · 펼친 모습 A "비교할 단지가 1곳이거나 7곳 이상일 때" — "비교할 단지를 2~6개 골라 주세요 / 지금 1개를 골랐어요." | — | 있음 |
| 5 | [상태] 링크 단지 리스트로 (/complexes + 전역 쿼리) (`pages/compare/index.tsx` `page.common.backToList` "단지 리스트로") | Compare · A "단지 찾기로 돌아가기" | 단지 리스트로 → 단지 찾기로 돌아가기 | 있음 |
| 6 | [상태] 기준일 스냅샷 없음 (`pages/_shared/index.tsx` NoSnapshot · `app.noSnapshot`) | Compare · B "기준일 자료가 없을 때" | — | 있음 |
| 7 | [상태] 지역 첫 적재 중 (`pages/_shared/index.tsx` NoSnapshot · `app.noSnapshotBootstrapping`) | Compare · B "첫 자료를 모으는 중일 때: …" | — | 있음 |
| 8 | [상태] 불러오는 중 (`pages/_shared/index.tsx` QueryState · `app.loading` "불러오는 중…") | Compare · C "불러오는 중 · 못 불러왔을 때" role=status | — | 있음 |
| 9 | [상태] 불러오기 오류 (`pages/_shared/index.tsx` QueryError → EmptyState queryErrorText) | Compare · C "불러오지 못했어요: [오류 내용] [다시 시도]" | 일반 오류에도 [다시 시도] 버튼이 붙음(기존은 준비 중 오류에만) | 있음 |
| 10 | [상태] 준비 중(503 materialize_pending) 자동 재시도 (`pages/_shared/index.tsx` MaterializePending · `page.common.materializePending`) | Compare · C "이 기준일의 화면 자료를 준비하는 중이에요 — 잠시 뒤 자동으로 다시 불러와요." | 발행 리비전 → 기준일 | 있음 |
| 11 | [상태] 준비 중 오류 + 다시 시도 버튼 (`pages/_shared/index.tsx` QueryError · `app.retry`) | Compare · C 같은 줄 [다시 시도] | — | 있음 |
| 12 | [상태] 이전 값을 두고 새 조건 준비 중 줄을 함께 표시 (`pages/_shared/index.tsx` QueryState isPlaceholderData) | Compare · 바닥 "구현할 때 지금 동작 그대로 유지" 상자 | — | 문구로만(고침 CP-22) |
| 13 | [상태] 발행 리비전에 없는 시나리오 안내 (`pages/_shared/index.tsx` isScenarioMissing · `page.common.scenarioMissing`) | Compare · C "이 기준일에는 내 조건 #[번호] 결과가 없어요(…)" | 시나리오 → 내 조건 | 있음 |
| 14 | [상태] 링크 시나리오 실행 화면으로 (`pages/_shared/index.tsx` `page.common.scenarioMissingRun`) | Compare · C [내 조건으로 다시 보기] | 시나리오 실행 화면으로 → 내 조건으로 다시 보기 | 있음 |
| 15 | [틀] 블록 순서 조건 비교 → 점수·판정기 → 가격 갭 → 점수 분해 → 가격 전망 → 상황별 판정 → 민감도 (`pages/compare/index.tsx` data-block) | Compare · 본문 섹션 순서 같음 | — | 있음 |
| 16 | [틀] 차트 구역 sr-only h2 (`pages/compare/index.tsx` `page.common.charts` "차트") | Compare · 바닥 "구현할 때 지금 동작 그대로 유지" 상자 | — | 문구로만(고침 CP-22) |
| 17 | [조건 비교] 구역 제목 (`pages/compare/index.tsx` TermsTable · `page.G4.termsFirst` "조건 비교(공고 값·산술)") | Compare · "조건 비교 · 공고에 적힌 값과 단순 계산" / h2 "얼마를 내고, 언제까지 묶이나요?" | 조건 비교(공고 값·산술) → 얼마를 내고, 언제까지 묶이나요? | 있음 |
| 18 | [조건 비교] 열 = 단지 이름(URL ids 순서) (`pages/compare/index.tsx` orderRows) | Compare · 조건 비교 표 머리 3단지 | — | 있음 |
| 19 | [조건 비교] 행 접수 IntakeBadge (`pages/compare/index.tsx` · `page.G4.row.intake` "접수") | Compare · 조건 비교 "지금 청약·계약 받나요 (접수)" — 접수 가능 + 경로·확인일 | 접수 → 지금 청약·계약 받나요 (접수) | 있음 |
| 20 | [조건 비교] 행 현재 구매가 하단~상단 Fact (`page.G4.term.price` "현재 구매가") | Compare · "지금 사는 값 (구매가, 84㎡ 최저~최고)" | 현재 구매가 → 지금 사는 값 | 있음 |
| 21 | [조건 비교] 행 전매 종료 날짜 + D± (`page.G4.term.resale_end` "전매 종료") | Compare · "되팔 수 있는 날 (전매 제한 끝)" "2026.12.09 56일 남음" | 전매 종료 → 되팔 수 있는 날 | 있음 |
| 22 | [조건 비교] 행 거주의무 (`page.G4.term.residency_months` "거주의무(개월)") | Compare · "꼭 들어가 살아야 하는 기간 (거주의무)" | — | 있음 |
| 23 | [조건 비교] 행 계약금 비율 (`page.G4.term.down_payment_pct`) | Compare · "계약금은 집값의 몇 % (계약금 비율)" | — | 있음 |
| 24 | [조건 비교] 행 계약금 (`page.G4.term.down_payment_won`) | Compare · "계약할 때 낼 돈 (계약금)" | — | 있음 |
| 25 | [조건 비교] 행 필요 자기자본 + 용어 ⓘ (`page.G4.term.required_equity_won` · Term `equity`) | Compare · "내 돈이 얼마 있어야 하나 (필요 자기자본) [?]" | — | 있음 |
| 26 | [조건 비교] 행 중도금 조건 텍스트, 없으면 "없음" (`page.G4.term.interim_terms_text` · `page.common.none`) | Compare · "중도금 조건" — "공고에 따로 적힌 조건 없음" | 없음 → 공고에 따로 적힌 조건 없음 | 있음 |
| 27 | [조건 비교] 조건 행이 없는 칸 EmptyState inline "확인 불가" (`empty.unknown`) | Compare · "확인 불가(내 조건 미입력)" | — | 있음 |
| 28 | [조건 비교] 숫자 칸 라벨 배지(확인됨·추정) — FactCell (`components/FactCell.tsx`) | Compare · 칸마다 "확인됨" / "추정 · 계산" | — | 있음 |
| 29 | [점수·판정기] 구역 제목 (`pages/compare/index.tsx` CompareGrid · `page.G4.scores` "점수·판정기") | Compare · "점수·판정기" / h2 "점수와 판정기는 어떻게 봤나요?" | — | 있음 |
| 30 | [점수·판정기] 두 지표 차이 설명 (`page.G4.rankVsDecide`) | Compare · 같은 구역 번호 1·2 설명 두 줄 | 한 문단 → 두 줄 | 있음 |
| 31 | [점수·판정기] 표 이름 (`page.G4.grid` "비교 표") | Compare · 표 aria-label "비교 표" | — | 있음 |
| 32 | [점수·판정기] 열 머리 = 단지 상세 링크 (/complexes/{id} + 전역 쿼리) | Compare · 비교 표 머리 링크 3개 | — | 있음 |
| 33 | [점수·판정기] 행 종합 점수 (`page.G4.row.total` "종합 점수") | Compare · "종합 점수 (10점 만점)" | — | 있음 |
| 34 | [점수·판정기] 행 순위 MetaValue (`page.G4.row.rank` "순위") | Compare · "순위 (점수 매긴 곳 중)" 1위·2위 | — | 있음 |
| 35 | [점수·판정기] 순위가 없을 때 "확인 불가" (`empty.unknown`) | Compare · 펼친 모습 G "순위가 없을 때: 확인 불가 + 배지" | — | 있음(고침 CP-18) |
| 36 | [점수·판정기] 순위 칸 동률 배지 (`components/TieBadge.tsx` · `badge.tie`) | Compare · 비교 표 "2위 동률" · G "[n]위 동률" | — | 있음 |
| 37 | [점수·판정기] 순위 칸 순위 불안정 배지 (`components/UnstableBadge.tsx` · `badge.unstable` "순위 불안정") | Compare · G "순위가 흔들려요" | 순위 불안정 → 순위가 흔들려요 | 있음 |
| 38 | [점수·판정기] 순위 칸 재판정 필요 배지 + 설명 title (`pages/_shared/index.tsx` RejudgeNeededBadge · `page.common.rejudgeNeeded` · `rejudgeNeededHint`) | Compare · G "다시 판정 필요" + 설명 문장 | 재판정 필요 → 다시 판정 필요 | 있음 |
| 39 | [점수·판정기] 행 +10% 상승 가능성 (`page.G4.row.p10`) | Compare · 점수·판정기 "10% 넘게 오를 가능성 [?]" + "목표 시점: 입주 + 1년 (상황 '기본' 설정)" + "당첨 확률이 아니에요 · 보장 아님" | 가격 +10% 상승 가능성(판정기) → 입주 1년 뒤 10% 넘게 오를 가능성 | 있음(고침 CP-1) |
| 40 | [점수·판정기] 행 판정기 순위 변화 (`page.common.deltaRerank`) | Compare · "판정기 줄 세우기가 지난번보다 바뀐 정도 (판정기 순위 변화)" | — | 있음 |
| 41 | [점수·판정기] 순위 변화 없음 사유 (`page.common.deltaRerankNone` "이전 실행 없음") | Compare · G "확인 불가(이전 실행 없음)" | — | 있음 |
| 42 | [점수·판정기] 행 접수 IntakeBadge (`page.G4.row.intake`) | Compare · 비교 표 "접수" | — | 있음 |
| 43 | [점수·판정기] 행 판정기 선택 확률(상황) (`page.G4.row.decision` "판정기 선택 확률(상황 {name})") | Compare · "'기본' 상황에서 판정기가 고를 확률" | — | 있음 |
| 44 | [점수·판정기] 확률 칸 선택 배지 (`chart.chosen` "선택") | Compare · "판정기 선택" | 선택 → 판정기 선택 | 있음 |
| 45 | [점수·판정기] 확률 칸 동률 배지(확정 봉투일 때만) | Compare · 펼친 모습 G "'판정기가 고를 확률' 칸: [n]% · 판정기 선택 · 동률 · 근거와 달라요" (동률은 확정일 때만) | — | 있음(고침 CP-18) |
| 46 | [점수·판정기] 확률 칸 증거와 상이 배지 (`components/MismatchBadge.tsx` · `badge.mismatch` "증거와 상이") | Compare · 같은 G 줄 [근거와 달라요] | 증거와 상이 → 근거와 달라요 | 있음(고침 CP-18) |
| 47 | [C02 가격 갭] 구역 제목 (`pages/compare/index.tsx` `page.G4.gaps` "가격 갭 나란히") | Compare · "가격 갭 나란히" / h2 "주변 아파트 시세보다 높은가요, 낮은가요?" | — | 있음 |
| 48 | [C02 가격 갭] 단지마다 차트 1장, 제목 = 단지 이름 (`charts/C02` title) | Compare · 카드 3장 h3 단지 이름 | — | 있음 |
| 49 | [C02 가격 갭] 그림: 현재 구매가 범위(강조색) + 비교 단지 실거래 점+위스커 (`charts/C02` buildOption) | Compare · 가로 띠 — 이 단지 분양가 띠 + 주변 단지별 거래 띠·중간값 눈금 | 점+위스커 → 가로 범위 띠 | 있음 |
| 50 | [C02 가격 갭] 값 축 억 단위 (formatEok) | Compare · 띠 아래 "3억 5억 7억 9억" | — | 있음 |
| 51 | [C02 가격 갭] 범주 축 비교 단지 이름 + 신축/대체 배지 (`charts/C02` compBadge) | Compare · 가격 갭 "'주변 거래' 줄을 단지별로 펼친 모습" — 줄 이름 = 비교 단지 이름 + 신축(연도)/대체(연도) 배지 | — | 있음(고침 CP-3) |
| 52 | [C02 가격 갭] 범례 (`chart.C02.range` "실거래 범위" · `chart.C02.adjusted` "연식 보정 중앙값") | Compare · 가격 갭 카드 범례 "분양가 최저~최고 · 단지별 거래 중간값 · 연식 보정 중앙값(대체 단지만)" | 범례 항목이 바뀜 | 있음(고침 CP-2) |
| 53 | [C02 가격 갭] 연식 보정 중앙값 점(점선 빈 점) (`charts/C02` series adjusted) | Compare · 같은 펼친 모습 — 점선 빈 점 = 연식 보정 중앙값 + 범례 | — | 있음(고침 CP-3) |
| 54 | [C02 가격 갭] 툴팁 하단~상단·중앙값·미보정/보정 중앙값 (`chart.C02.unadjusted`) | Compare · 같은 펼친 모습 — 툴팁 예시(이름·배지 / 하단~상단 / 미보정 중앙값 / 보정 중앙값 있으면 한 줄) | — | 있음(고침 CP-3) |
| 55 | [C02 가격 갭] 라벨 배지 (`charts/C02` collectLabels) | Compare · 카드 머리 "확인됨" | — | 있음 |
| 56 | [C02 가격 갭] 대체·보정 배지 "추정(대체·보정 c=…)" (`charts/C02` adjustedBadges) | Compare · H "추정(대체·보정 [계수]) 거래가 3건보다 적어 다른 단지로 대신했을 때" | — | 있음 |
| 57 | [C02 가격 갭] 빈 상태 (`chart.C02.empty` "비교군 없음({reason})") | Compare · H "비교할 거래가 없어요([사유])" | 비교군 없음 → 비교할 거래가 없어요 | 있음 |
| 58 | [C02 가격 갭] 표로 보기 버튼 (`components/DataTableToggle.tsx` · `table.show`) | Compare · 카드마다 [표로 보기] | — | 있음 |
| 59 | [C02 가격 갭] 표 열 이름 (`chart.col.name`) | Compare · K "이름" | — | 있음 |
| 60 | [C02 가격 갭] 표 열 구분 신축/대체 (`chart.col.kind` · `badge.newBuild` · `badge.substitute`) | Compare · K "구분" 신축(2024) · "대체([연도])" | — | 있음 |
| 61 | [C02 가격 갭] 표 열 하단 (`chart.col.low`) | Compare · K "하단" | — | 있음 |
| 62 | [C02 가격 갭] 표 열 중앙값 (`chart.col.median`) | Compare · K "중앙값" | — | 있음 |
| 63 | [C02 가격 갭] 표 열 상단 (`chart.col.high`) | Compare · K "상단" | — | 있음 |
| 64 | [C02 가격 갭] 표 열 보정 중앙값 (`chart.col.adjusted`) | Compare · K "보정 중앙값" | — | 있음 |
| 65 | [C02 가격 갭] 표 열 거래 기간 (`chart.col.window`) | Compare · K "기간" | 거래 기간 → 기간 | 있음 |
| 66 | [C02 가격 갭] 표 첫 줄 현재 구매가 (`chart.C02.current`) | Compare · K "이 단지 분양가" | 현재 구매가 → 이 단지 분양가 | 있음 |
| 67 | [C06 점수 분해] 차트 제목 (`charts/C06` · `chart.C06.title` "종합 점수 분해") | Compare · "종합 점수 분해" / h2 "종합 점수는 무엇으로 이루어졌나요?" | — | 있음 |
| 68 | [C06 점수 분해] 부제 가중치 (`chart.C06.weights` "가중치 {weights}") | Compare · 범례마다 "{기준} 비중 {w}" | 가중치 → 비중 | 있음 |
| 69 | [C06 점수 분해] 라벨 배지 (total 라벨) | Compare · "추정 · 6가지 중 일부가 판정기 값" | — | 있음 |
| 70 | [C06 점수 분해] 순위 불안정 배지(차트 머리) | Compare · 종합 점수 분해 머리 "붙을 때만: 순위가 흔들려요" | — | 있음(고침 CP-4) |
| 71 | [C06 점수 분해] 동률 배지(차트 머리) | Compare · 종합 점수 분해 머리 [동률] 배지 | — | 있음(고침 CP-4) |
| 72 | [C06 점수 분해] 미판정 배지 + 빗금·점선 0길이 막대 + 메모 (`badge.unjudged` · `chart.C06.unjudgedNote`) | Compare · H "빗금 = 아직 판정 안 한 기준(점수 0) 미판정" | — | 있음 |
| 73 | [C06 점수 분해] 누적 가로 막대(성분 6개 가중 기여, orientation horizontal) | Compare · 막대 3줄 × 6칸 | — | 있음 |
| 74 | [C06 점수 분해] 범주 축 단지 이름 + 종합 점수 | Compare · 막대 왼쪽 이름·합계 | — | 있음 |
| 75 | [C06 점수 분해] 값 축 점수 (formatScore) | Compare · "0 1 2 3 4 5점" | — | 있음 |
| 76 | [C06 점수 분해] 범례 성분 6개 (`chart.C06.component.*`) | Compare · 범례 6개 "입주 뒤 값이 오를 가능성 … 되팔기 쉬움" | +10% 상승 가능성 → 입주 뒤 값이 오를 가능성 · 판정기 순위 → 비슷한 단지들 사이 순위 · 가격 갭 → 주변 시세와 가격 차이 · 벤치마크 → 근처 새 아파트가 입주 뒤 오른 정도 · 공급 → 같은 시기 입주 물량 · 유동성 → 되팔기 쉬움 | 있음 |
| 77 | [C06 점수 분해] 종합 점수 내림차순 정렬 (`charts/C06` sortedRows) | Compare · 1위부터 아래로 | — | 있음 |
| 78 | [C06 점수 분해] 툴팁 점수×가중치·기여·원값·formula_text (`chart.C06.contribution` · `chart.C06.raw` · `chart.C06.unjudgedTip`) | Compare · 종합 점수 분해 툴팁 예시 2개(점수 × 비중 · 기여 · 원값 · 계산식 / 미판정 — 최대 기여) | — | 있음(고침 CP-5) |
| 79 | [C06 점수 분해] 빈 상태 (`chart.C06.empty` "점수 없음") | Compare · H "점수 없음" | — | 있음 |
| 80 | [C06 점수 분해] 표로 보기 버튼 | Compare · "기준별 점수와 원래 값 표로 보기" | — | 있음 |
| 81 | [C06 점수 분해] 표 열 순위 (`chart.col.rank`) | Compare · 펼친 표 첫 행 "순위" (1위 · 2위 동률) | — | 있음(고침 CP-6) |
| 82 | [C06 점수 분해] 표 열 이름 (`chart.col.name`) | Compare · 펼친 표 열 머리 = 단지 이름 (행·열 뒤바뀜) | — | 있음 |
| 83 | [C06 점수 분해] 표 열 종합 (`chart.col.total`) | Compare · 펼친 표 둘째 행 "종합 (10점 만점)" | — | 있음(고침 CP-6) |
| 84 | [C06 점수 분해] 표 열 성분 6개 점수 | Compare · 펼친 표 행 6개(첫 행 '오를 가능성'에 목표 시점·당첨 확률 아님·보장 아님) | 성분 열 → 기준 행(원값 함께) | 있음(고침 CP-16) |
| 85 | [C01 가격 전망] 구역 제목 (`pages/compare/index.tsx` LadderOverlay · `page.G4.ladder` "가격 전망 겹쳐 보기") | Compare · "가격 전망 겹쳐 보기" / h2 "값이 오를 가능성, 세 곳을 겹쳐 보면?" | — | 있음 |
| 86 | [C01 가격 전망] 목표 시점 라디오 3개 role=radiogroup (`page.G3.ladder.horizons` · `chart.C01.horizon.*`) | Compare · "언제를 기준으로 볼까요? (목표 시점)" 라디오 3개 | 입주+1년 → 입주하고 1년 뒤 · 기준일+3년 → 기준일부터 3년 뒤 · 기준일+5년 → 기준일부터 5년 뒤 | 있음 |
| 87 | [C01 가격 전망] 차트 제목 (`charts/C01` · `chart.C01.title` "상승 확률 사다리") | Compare · 구역 h2만 있고 차트 자체 제목 없음 | 상승 확률 사다리 → 값이 오를 가능성 | 있음 |
| 88 | [C01 가격 전망] 부제 목표 시점 (`chart.C01.subtitle` "목표 시점 {target}") | Compare · 회색 상자 "목표 시점 · 단지별 2030 하반기 …" | — | 있음 |
| 89 | [C01 가격 전망] 라벨 배지 | Compare · 범례 옆 "판정기 추정" | — | 있음 |
| 90 | [C01 가격 전망] 겹침 그림: 단지별 기호 산점 overlay (`charts/C01` buildOption overlay) | Compare · 단지별 색 막대 묶음(4묶음 × 3단지) | 산점 → 묶음 막대 | 있음 |
| 91 | [C01 가격 전망] 확률 축 0~1 (formatProb) | Compare · "100% 50% 0%" | — | 있음 |
| 92 | [C01 가격 전망] 범주 축 +5% · +10% · +20% · 보합·하락 (`chart.C01.bar.*`) | Compare · "5% 넘게 오를 가능성 · 10% … · 20% … · 그대로거나 내릴 가능성" | 보합·하락 → 그대로거나 내릴 가능성 | 있음 |
| 93 | [C01 가격 전망] 범례 단지 이름·기호 | Compare · 범례 3단지 기호(원·네모·세모) | — | 있음 |
| 94 | [C01 가격 전망] 기준선 0.85 · 0.15 (`chart.C01.threshold.likely` · `chart.C01.threshold.unlikely`) | Compare · 점선 2개 + 설명 "위 점선 85%… 아래 점선 15%…" | — | 있음 |
| 95 | [C01 가격 전망] 판정 문구 (`chart.C01.verdict.*` 가능성 높음·불확실·가능성 낮음) | Compare · 가격 전망 "판정기 판정(막대마다 서버 값 그대로): 중간 12개 · …" + 막대 아래 판정 | 불확실 → 중간 | 있음(고침 CP-7) |
| 96 | [C01 가격 전망] 필요 연율 (`chart.C01.annualized` "필요 연율 {pct}") | Compare · 막대 아래 "필요 연율 연 1.3% · 1.0% · 2.0%" | — | 있음 |
| 97 | [C01 가격 전망] 툴팁 단지·막대·확률·판정·연율 | Compare · 가격 전망 툴팁 예시(단지 / 막대 · 확률 · 판정 / 필요 연율, 미해결이면 '미해결') | — | 있음(고침 CP-8) |
| 98 | [C01 가격 전망] 미해결이면 회색 + "미해결" 배지 (`charts/C01` unresolvedBadge · `badge.unresolved`) | Compare · 펼친 모습 H "가격 전망이 미해결인 단지" 회색 바탕 막대 + 미해결 | — | 있음(고침 CP-19) |
| 99 | [C01 가격 전망] 빈 상태 (`chart.C01.empty` "사다리 판정 없음") | Compare · H "사다리 판정 없음" | — | 있음 |
| 100 | [C01 가격 전망] 표로 보기 버튼 | Compare · 꼬리말 [표로 보기] | — | 있음 |
| 101 | [C01 가격 전망] 표 열 이름 (`chart.col.name`) | Compare · I "단지 · 목표 시점" | — | 있음 |
| 102 | [C01 가격 전망] 표 열 시점 (`chart.col.horizon`) | Compare · 펼친 모습 I "시점" 열(입주 + 1년) | — | 있음(고침 CP-20) |
| 103 | [C01 가격 전망] 표 열 목표 시점 (`chart.col.target`) | Compare · I "단지 · 목표 시점" 칸에 합침 | — | 있음 |
| 104 | [C01 가격 전망] 표 열 +5% (`chart.C01.bar.p5`) | Compare · I "5% 넘게" | — | 있음 |
| 105 | [C01 가격 전망] 표 열 +10% | Compare · I "10% 넘게" | — | 있음 |
| 106 | [C01 가격 전망] 표 열 +20% | Compare · I "20% 넘게" | — | 있음 |
| 107 | [C01 가격 전망] 표 열 보합·하락 | Compare · I "그대로·내림" | — | 있음 |
| 108 | [C01 가격 전망] 표 열 상태 (`chart.col.status` · `chart.status.*` 판정/미해결(검토·질문·차단·오류)) | Compare · I "판정" 열 — 값이 '중간'(판정 문구) | 상태 → 판정 (봉투 상태 대신 판정 문구) | 있음 |
| 109 | [상황별 판정] 구역 제목 (`pages/compare/index.tsx` DecisionPanel · `page.G4.decision` "상황별 판정") | Compare · "상황별 판정" / h2 "상황이 다르면 판정기는 어디를 고르나요?" | — | 있음 |
| 110 | [상황별 판정] 상황 라디오(판정 키가 2개 이상일 때) (`page.G4.decisionScenario` "상황 {name}") | Compare · "상황 고르기" 라디오 5개 | — | 있음 |
| 111 | [상황별 판정] 판정 없음 (`page.G4.noDecision` "이 상황의 판정이 없습니다") | Compare · F "이 상황의 판정이 없어요." | — | 있음 |
| 112 | [C07 판정기 확률] 차트 제목 (`charts/C07` · `chart.C07.title` "판정기 확률") | Compare · h3 "판정기가 고를 확률 · {상황}" | 판정기 확률 → 판정기가 고를 확률 | 있음 |
| 113 | [C07 판정기 확률] 부제 신뢰도 (`chart.C07.confidence` "신뢰도 {confidence}") | Compare · "믿음 정도 0.61" | 신뢰도 → 믿음 정도 | 있음 |
| 114 | [C07 판정기 확률] 라벨 배지 | Compare · "판정기 추정" | — | 있음 |
| 115 | [C07 판정기 확률] 동률 배지(신뢰도 포함) (`badge.tieWithConfidence`) | Compare · D "동률(믿음 정도 0.31)" | — | 있음 |
| 116 | [C07 판정기 확률] 증거와 상이 배지 | Compare · D "근거와 달라요" + 설명 | 증거와 상이 → 근거와 달라요 | 있음 |
| 117 | [C07 판정기 확률] 캐시 배지 (`components/CachedBadge.tsx` · `badge.cached` "캐시") | Compare · F "이전 결과 재사용" | 캐시 → 이전 결과 재사용 | 있음 |
| 118 | [C07 판정기 확률] 질문 남김 배지 + 빈 상태 "질문 남김: {질문}" (`chart.C07.escape`) | Compare · F "질문 남김" + "질문 남김: [판정기 질문 문장]" | — | 있음 |
| 119 | [C07 판정기 확률] 판정 미해결 배지 (`chart.C07.unresolved`) | Compare · F "판정 미해결" | — | 있음 |
| 120 | [C07 판정기 확률] 미해결이면 막대 회색 + 값 옆 "미해결" | Compare · 펼친 모습 F 회색 막대 2줄 "[n]% · 미해결" | — | 있음(고침 CP-19) |
| 121 | [C07 판정기 확률] 가로 막대(선택 = 강조, 후보 = 보통, 보류 선택지 = 회색) | Compare · 판정기가 고를 확률 막대 | — | 있음 |
| 122 | [C07 판정기 확률] 막대 라벨 확률 · 선택 · 동률 · 상이 | Compare · 막대 오른쪽 % + "판정기 선택"·"동률"·"근거와 달라요" | — | 있음 |
| 123 | [C07 판정기 확률] 가상 후보 표시 (`chart.C07.virtual` "가상 후보") | Compare · 막대 라벨 "가상 후보" | — | 있음 |
| 124 | [C07 판정기 확률] 범주 축 후보 이름 | Compare · 막대 왼쪽 후보 이름 | — | 있음 |
| 125 | [C07 판정기 확률] 확률 축 0~1 눈금 | Compare · 판정기가 고를 확률 막대 아래 확률 축 0% 25% 50% 75% 100% | — | 있음(고침 CP-9) |
| 126 | [C07 판정기 확률] 툴팁 | Compare · 판정기가 고를 확률 툴팁 예시 2개(이름 / 확률 / 표시) | — | 있음(고침 CP-10) |
| 127 | [C07 판정기 확률] 빈 상태 (`chart.C07.empty` "판정 없음") | Scenario · H "판정 없음" | — | 다른 보드(Scenario) |
| 128 | [C07 판정기 확률] 표로 보기 버튼 | Compare · [표로 보기] | — | 있음 |
| 129 | [C07 판정기 확률] 표 열 이름 (`chart.col.name`) | Compare · L "이름" | — | 있음 |
| 130 | [C07 판정기 확률] 표 열 확률 (`chart.col.prob`) | Compare · L "확률" | — | 있음 |
| 131 | [C07 판정기 확률] 표 열 표시 (`chart.col.flags`) | Compare · L "표시" (판정기 선택 · 판정기 보류 선택지) | 질문 남김 → 판정기 보류 선택지 | 있음 |
| 132 | [상황별 판정] 가상 후보 목록 (`pages/compare/index.tsx` VirtualCandidates · `page.G4.virtual` · `page.G4.virtualCandidate` · `page.G4.row.prob` "선택 확률") | Compare · "가상 후보: 모집공고 대기 … 고를 확률 1%" (E) | 선택 확률 → 고를 확률 | 있음 |
| 133 | [상황별 판정] 가상 후보 줄의 선택·동률·상이 배지 | Compare · 가상 후보 상자에 선택·동률·근거와 달라요 배지 자리 + 펼친 모습 E 예시 줄 | — | 있음(고침 CP-11) |
| 134 | [상황별 판정] 판정기 경고 목록 (`page.G4.warnings` "경고") | Compare · E role=note "판정기 경고" [문구 1·2] | — | 있음 |
| 135 | [요건 표] 표 이름 (`pages/compare/index.tsx` RequirementsTable · `page.G4.requirements` "요건") | Compare · h3 "이 상황의 3가지 요건을 단지마다 채우나요?" | — | 있음 |
| 136 | [요건 표] 열 단지 (`page.G5.req.complex`) | Compare · "단지" | — | 있음 |
| 137 | [요건 표] 열 접근 (`page.G5.req.access`) | Compare · "지금 신청할 수 있나 (접근)" | — | 있음 |
| 138 | [요건 표] 열 규제 (`page.G5.req.regulation`) | Compare · "규제와 부딪히지 않나 (규제)" | — | 있음 |
| 139 | [요건 표] 열 자금 (`page.G5.req.funds`) | Compare · "내 돈으로 되나 (자금)" | — | 있음 |
| 140 | [요건 표] 칸 사전 계산 상태 배지 (`page.G5.reqStatus.*` 충족·미충족·미입력·확인 불가) | Compare · 칸 배지 4종 | — | 있음 |
| 141 | [요건 표] 칸 판정기 결론 배지 (check.judge) | Compare · "판정기도 충족으로 봄" · "판정기는 미충족으로 봄" · "판정기 판단 못 함" | 서버 값 그대로 → 문장 | 있음 |
| 142 | [요건 표] 칸 증거와 상이 배지 | Compare · 칸 "근거와 달라요" | — | 있음 |
| 143 | [요건 표] 칸 근거 문장 (pre.evidence) | Compare · 요건 표 배지 아래 근거(서버 문장 그대로 — 고친 문구 예시 위 안내) | — | 있음(고침 CP-12) |
| 144 | [요건 표] 가상 후보 행 배지 (`chart.C07.virtual`) | Compare · E "모집공고 대기 가상 후보" | — | 있음 |
| 145 | [요건 표] 사전 계산 없는 칸 EmptyState inline "확인 불가" | Compare · E "사전 계산 없음" | 확인 불가 → 사전 계산 없음 | 있음 |
| 146 | [C10 민감도] 응답 있을 때만 블록 표시 · 빈 상태 (`chart.C10.empty` "민감도 없음") | Compare · H "민감도 없음" | — | 있음 |
| 147 | [C10 민감도] 차트 제목 (`charts/C10` · `chart.C10.title` "가중치 민감도") | Compare · "가중치 민감도" / h2 "어떤 기준의 비중을 10%p 늘리거나 줄이면 순위가 바뀌나요?" | — | 있음 |
| 148 | [C10 민감도] 용어 ⓘ 비중 (Term `weight`) | Compare · "'비중'이 뭔가요? [?]" + 설명 상자 | — | 있음 |
| 149 | [C10 민감도] 용어 ⓘ 민감도 (Term `sensitivity`) | Compare · 가중치 민감도 "'민감도'가 뭔가요? [?]" | — | 있음(고침 CP-15) |
| 150 | [C10 민감도] 순위 불안정 배지(차트 머리) | Scenario · 가중치 민감도 "순위가 흔들려요 · {단지 이름}" (Compare 민감도 구역에는 없음) | 순위 불안정 → 순위가 흔들려요 | 다른 보드(Scenario) |
| 151 | [C10 민감도] 변동 없는 성분 배지 (`chart.C10.stable`) | Compare · 가중치 민감도 결과 상자 [비중을 바꿔도 순위가 그대로인 기준 있음] | — | 있음(고침 CP-13) |
| 152 | [C10 민감도] 설명 문단 (`chart.C10.explain`) | Compare · 설명 상자 두 문단 | — | 있음 |
| 153 | [C10 민감도] HTML 표 행 = 변형 12개 (`chart.C10.variantLabel`) | Compare · 행 6개(기준) × 열 "줄이면" / "늘리면" | 12행 → 6행 × 2열 | 있음 |
| 154 | [C10 민감도] 표 열 비중 바꾼 항목 (`chart.col.variant`) | Compare · "기준 (지금 비중) · 무엇을 보나요" | — | 있음 |
| 155 | [C10 민감도] 표 열 1~5위(TOP 5, 실제 순위 괄호) | Compare · 기준별 표 "→ 1위·2위·3위"(서버 순위만, 화면이 비교해 쓴 '1위 그대로/바뀌어요' 줄은 뺌) | TOP 5(지역) → 비교 단지 순서 | 있음(고침 CP-14) |
| 156 | [C10 민감도] 표 열 순위 변동 (`chart.C10.changedCol` · `changedNo` · `changedYes`) | Compare · 칸 아래 "순위 변동(상위 5곳 바뀜): 없음" | — | 있음 |
| 157 | [C10 민감도] 진입·이탈 단지 + 굵게 (`chart.C10.entered` · `chart.C10.exited` · `changedWith`) | Compare · 펼친 모습 M "표시 (들어옴·빠짐)" 열 — 진입 이름 굵게 | — | 있음(고침 CP-21) |
| 158 | [C10 민감도] 변동 없는 행 회색 (text-grayed) | Scenario · "회색 칸 = 상위 5곳 변동 없음" | — | 다른 보드(Scenario) |
| 159 | [C10 민감도] 순위 선 차트 (`charts/C10` buildOption) | Compare · h3 "기준별로 비중을 바꾸면 각 단지는 몇 위가 되나요?" | — | 있음 |
| 160 | [C10 민감도] 선 차트 x축 변형 짧은 이름 (`chart.C10.variantShort`) | Compare · "6가지 기준 × (줄이면 / 늘리면)" | — | 있음 |
| 161 | [C10 민감도] 선 차트 y축 순위(위가 1위) | Compare · "1위 2위 3위" | — | 있음 |
| 162 | [C10 민감도] 선 차트 범례 기준 TOP 5 단지 | Compare · 범례 3단지 | TOP 5 → 비교 단지 3곳 | 있음 |
| 163 | [C10 민감도] 선 차트 툴팁 | Compare · 순위 선 차트 툴팁 예시(비중 바꾼 항목 / 단지별 순위, 없으면 확인 불가) | — | 있음(고침 CP-17) |
| 164 | [C10 민감도] 표로 보기 버튼 | Compare · [표로 보기] | — | 있음 |
| 165 | [C10 민감도] 표 열 비중 바꾼 항목 (`chart.col.variant`) | Compare · 펼친 모습 M "비중 바꾼 항목" 열 | — | 있음(고침 CP-21) |
| 166 | [C10 민감도] 표 열 순위 변동 (`chart.C10.changedCol`) | Compare · 펼친 모습 M "순위 변동" 열 | — | 있음(고침 CP-21) |
| 167 | [C10 민감도] 표 열 TOP 5 (`chart.col.top5`) | Compare · 펼친 모습 M "상위 5곳 (TOP 5)" 열 | — | 있음(고침 CP-21) |
| 168 | [C10 민감도] 표 열 표시(진입·이탈) (`chart.col.flags`) | Compare · 펼친 모습 M "표시 (들어옴·빠짐)" 열 | — | 있음(고침 CP-21) |
| 169 | [공통] 숫자 누르면 출처 서랍 (FactCell → `components/ProvenancePanel.tsx` · GET /provenance/{id}) | Shell · 3 "숫자를 누르면 열리는 '출처' 창" (Compare는 바닥 문구 "숫자를 누르면 출처가 열려요") | — | 다른 보드(Shell) |
| 170 | [공통] 용어 ⓘ 팝오버 — Esc·바깥 클릭 닫기, 모바일 아래 시트 (`components/Term.tsx` · `glossary.more`) | Shell · 3 "용어 '?'를 눌렀을 때" | — | 다른 보드(Shell) |
| 171 | [공통] 표로 보기 토글 aria-expanded · 표 닫기 (`components/DataTableToggle.tsx` · `table.hide`) | Compare · 접힌 버튼 + 펼친 모습 I·K·L (틀은 Shell · 8) | — | 있음 |
| 172 | [공통] 상황 토글 공유(전역 ?scenario=) (`pages/_shared/index.tsx` usePageContext) | Compare · 머리줄 "상황 기본 · 머리줄에서 바꿔요" | — | 있음 |
| 173 | [키보드] 라디오 버튼(role=radio) Tab·Enter/Space 선택 — 목표 시점·상황 | Compare · role=radiogroup / role=radio 버튼 | — | 있음 |
| 174 | [API] GET /snapshots/{sid}/compare?ids=&scenario= (ids 2~6일 때만) (`api/hooks.ts` useCompare) | Compare · 본문 전체 | — | 있음 |
| 175 | [API] GET /snapshots/{sid}/sensitivity?scenario= (`api/hooks.ts` useSensitivity) | Compare · 가중치 민감도 | — | 있음 |
| 176 | [API] GET /scenarios (상황 이름) (`api/hooks.ts` useScenarios) | Compare · 요약 줄·상황 라디오 이름 | — | 있음 |

## 요약

전체 176 · 있음 169 · 문구로만 2 · 다른 보드 5 · 빠짐 0 (2026-10-16 목업 고침 반영 — `../fixes/fixes-Compare.md`)

### 빠짐 목록

- 없음 — 모두 고침(보드에 그리거나 "구현할 때 지금 동작 그대로 유지" 상자에 적음)

## 새로 더한 것 (기존 화면에 없던 것)

| # | 목업에 새로 생긴 것 | 목업 위치 (섹션) | 비고 |
|---|---|---|---|
| N1 | 비교 단지 카드 줄(구·세대수·입주·종합·순위·접수 배지, 단지별 색·기호) | 비교하는 단지 | "아래 표·차트의 열 순서와 색이 이 카드와 같아요" |
| N2 | [단지 더 담기 (2~6곳)] 링크 | 머리 오른쪽 | 기존엔 단지 리스트에서만 고름 |
| N3 | 위치 줄(빵부스러기) "단지 찾기 › 비교하기" | 머리 | — |
| N4 | 전매·오를 가능성 [?] 용어 버튼 | 조건 비교 · 점수·판정기 | 기존 Term은 필요 자기자본에만 |
| N5 | 조건 표 첫 칸 머리 "조건" | 조건 비교 | — |
| N6 | 중도금 조건 긴 글 [전체 보기] 펼침 | 조건 비교 · J | — |
| N7 | "'내 돈이 얼마 있어야 하나'는 … [내 조건으로 다시 보기]" 안내 링크 | 조건 비교 아래 | — |
| N8 | 섹션마다 '자료: … · 확인일' 꼬리말 | 모든 섹션 | — |
| N9 | 가격 갭 카드 머리 "주변보다 8.1% 높아요/낮아요" + 비교 단지 수·거래 수·뺀 건수 설명 | 가격 갭 나란히 | "주변 거래 중간 ○억"은 뺌(서버에 없는 값) — 비교 단지 수·거래 수·뺀 건수만 (고침 CP-2) |
| N10 | 가격 갭 '주변 전체 중간값' 점선 | 가격 갭 나란히 | 뺌 — 서버에 없는 값을 화면이 계산(고침 CP-2) |
| N11 | 점수 분해 설명 문장(막대 한 칸 = 기준 하나) | 종합 점수 분해 | — |
| N12 | 점수 분해 펼친 표에 기준별 원래 값(확률·순위·%·세대·년) | 종합 점수 분해 | — |
| N13 | 가격 전망 설명 "당첨 확률이 아니에요 · 보장 아님" | 가격 전망 겹쳐 보기 | — |
| N14 | 가격 전망 펼친 표에 필요 연율 "연 n%" | I | — |
| N15 | 상황별 판정 설명 "이 비교의 세 곳 말고 다른 후보도 함께 나와요" | 상황별 판정 | — |
| N16 | 믿음 정도 [?] 설명 버튼 | 상황별 판정 · C07 머리 | — |
| N17 | C07 꼬리말 "회색 막대 = 더 묻기·더 조사·해당 없음 선택지" | 상황별 판정 | — |
| N18 | 가상 후보 설명 문장 "새 공고가 나올 때까지 기다리기" | 상황별 판정 | — |
| N19 | 요건 표 설명·꼬리말 "이 표는 개인의 청약 자격을 판정하지 않아요" | 요건 표 | — |
| N20 | 민감도 '한 줄 답' 요약 + "1위가 바뀌어요 → …" 줄 | 가중치 민감도 | 한 줄 답 문장 → 서버 값 개수 줄 "순위 변동: 있음 n · 없음 n"(고침 CP-13), "1위가 바뀌어요 → …" 줄은 뺌(고침 CP-14) |
| N21 | 민감도 표 기준마다 "공식 용어: …" · 무엇을 보나요 설명 | 가중치 민감도 | — |
| N22 | "지금(기본 비중) 순서: …" 줄과 '줄인 만큼 나머지에 비율대로' 설명 | 가중치 민감도 | — |
| N23 | 화면 바닥 고지 + 라벨 범례(확인됨·추정·재가공) | 바닥 | — |

## 참고

- 표의 '열마다 한 줄'은 비교 화면 특성상 열 = 단지라서, 행(조건·점수 항목)을 한 줄씩 적었다. 차트 '표로 보기'는 실제 열마다 한 줄.
- 툴팁은 정적 목업에 그릴 수 없어 '빠짐(호버 없음)'으로 정직하게 적었다. 같은 값이 막대 라벨·펼친 표로 보이면 그 사실을 위치 칸에 적었다.
- 출처 서랍·용어 팝오버·작업 진행 등 공통 부품은 Shell(공통 부품) 보드에 있다.
