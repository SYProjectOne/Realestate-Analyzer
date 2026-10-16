# 대응표 — G1 홈 (`pages/dashboard`, 차트 C05·C06) → Main.dc.html

- 소스 위치는 `frontend/src/` 기준. 화면 코드는 모두 `pages/dashboard/index.tsx`(아래에서 `dashboard`), 차트는 `charts/C05`·`charts/C06`. ko 키는 `frontend/src/i18n/ko.json`.
- Main 보드 섹션 이름(제목이 없는 곳은 aria-label·첫 글자로 부름): "첫 줄(hero)", "지금 접수 가능한 단지"(카드 3장), "곧 청약 접수가 시작돼요" 띠, "다가오는 일정", "인천 시장 한눈에", "점수 순서 · 상황: 기본", "최근에 바뀐 것", "바닥 글".
- Main 보드의 머리줄에는 기준일·상황·열쇠·화면 칸이 없다. 그 칸들은 coverage-Shell.md 에 있다.

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 1 | [화면] 지역이 하나도 없으면 /regions/new 로 보냄 (`dashboard` Navigate) | Shell · §1 기준일·상황 선택칸을 펼친 모습 "지역이 없으면 … 홈은 지역 추가 화면으로 넘어가요" | 같음 | 다른 보드(Shell, 문구로만) |
| 2 | [화면] h1 `page.G1.title` "홈" | Main · 첫 줄 h1 "지금 청약을 넣을 수 있는 단지는 3곳이에요" | h1이 문장으로 ("홈"은 메뉴에만) | 있음 |
| 3 | [화면] 출처 범례 한 줄 `label.legend` (PageShell legend) | Main · 바닥 글 "… 숫자를 누르면 출처가 열려요" | 위치 맨 위 → 맨 아래 | 있음(고침 HM-16) |
| 4 | [화면] 라벨 뜻 ⓘ 펼침 `label.legendHelp` | Shell · §3 "라벨 뜻 [접기]" (Main 바닥 글은 확인됨·추정 두 개만) | — | 다른 보드(Shell) |
| 5 | [화면] 기준일 없음 NoSnapshot `app.noSnapshot`/`app.noSnapshotBootstrapping` | Shell · §7 불러오는 중 · 오류 · 빈 상태 | — | 다른 보드(Shell) |
| 6 | [화면] 대시보드 불러오는 중 `app.loading` | Shell · §7 | — | 다른 보드(Shell) |
| 7 | [화면] 대시보드 오류 `page.common.loadError` | Shell · §7 | — | 다른 보드(Shell) |
| 8 | [화면] 준비 중(503) `page.common.materializePending` | Shell · §7 | — | 다른 보드(Shell) |
| 9 | [화면] 발행 뒤 만든 시나리오 결과 없음 `page.common.scenarioMissing` | Shell · §7 | — | 다른 보드(Shell) |
| 10 | [화면] 헤더 상황 토글 → 대시보드 다시 부름 (`?scenario=`) | Shell · 머리줄 상황 토글 (Main 머리줄엔 없음) | — | 다른 보드(Shell) |
| 11 | [화면] 헤더 기준일 → 대시보드 다시 부름 (`?snapshot=`) | Shell · 머리줄 기준일 (Main 머리줄엔 없음, 첫 줄 글에 "기준일 2026년 10월 14일") | — | 다른 보드(Shell) |
| 12 | [API] GET /snapshots/{id}/dashboard?scenario= (`api/hooks` useDashboard) | Main · 화면 전체 | 호출 표시 없음 | 있음 |
| 13 | [화면] 구역 순서 (data-section: openNow·upcoming → top → region → changes → C06·C05) | Main · 첫 줄 → 접수 가능 카드 → 곧 접수 띠 → 다가오는 일정 + 시장 → 점수 순서 → 최근에 바뀐 것 | 지역 현황이 점수 위로, 차트는 점수 순서·시장 카드에 합침 | 있음 |
| 14 | [재판정] 안내 `page.G1.rejudgeNotice` "재판정 필요 — 이 화면의 판정 범위·순위·점수는 스냅샷에 저장된 값입니다 …" (role=note) | Shell · §2 화면 위에 뜨는 알림 띠 "새로 바뀐 사실이 있어 점수를 다시 매겨야 해요. 상위 단지를 다시 판정할까요? (홈)" | "저장된 값"이라는 설명 빠짐 · 고침 후: (Shell SH-7) '저장된 값' 설명 되살림 | 다른 보드(Shell · 고침 SH-7) |
| 15 | [재판정] 버튼 `page.G1.rejudgeRun` "재판정 잡 등록" | Shell · §2 "다시 판정하기" | 재판정 잡 등록 → 다시 판정하기 | 다른 보드(Shell) |
| 16 | [API] POST /jobs `rejudge` (대상 = 재판정 필요 단지, 없으면 null · 사유 `page.G1.rejudgeReason`) | Shell · §2 "다시 판정하기" | 호출 표시 없음 | 다른 보드(Shell) |
| 17 | [재판정] 읽기 전용 열쇠면 꺼짐 + title `auth.readOnlyHint` | Scenario · 가끔만 나오는 모습 "D · 읽기 전용 열쇠일 때" · Ops · 모든 묶음 공통 상태 | — | 다른 보드(Scenario·Ops, 문구로만) |
| 18 | [재판정] 보내는 중·등록한 뒤 꺼짐 | Scenario · "D · 읽기 전용 열쇠일 때" "저장·판정 요청을 보내는 중이거나 … 버튼이 잠깐 꺼져요" | — | 다른 보드(Scenario, 문구로만) |
| 19 | [재판정] 모바일 읽기 전용이면 숨김 (`data-write`) | Shell · §2 "휴대폰에서는 보기만 할 수 있어요" | — | 다른 보드(Shell, 문구로만) |
| 20 | [재판정] 등록 실패 `page.common.loadError` (role=alert) | — | — | 다른 보드(Shell · 고침 SH-7) |
| 21 | [재판정] 등록 뒤 작업 진행 JobProgress | Shell · §6 작업 진행 · 알림 | — | 다른 보드(Shell) |
| 22 | [재판정] 끝나면 그 기준일 화면 새로 고침 (invalidate, 동작) | — | — | 문구로만(고침 HM-17) |
| 23 | [벤치마크] 배지 `page.common.benchmarkAbsent` "벤치마크 없음({reason})" (role=note) | Shell · §2 "근처 새 아파트 실적 없음(이 지역에 비교할 사례 없음)" | 벤치마크 → 근처 새 아파트 실적 | 다른 보드(Shell · 고침 SH-8) |
| 24 | [벤치마크] 안내 `page.G1.benchmarkAbsentHint` "벤치마크 성분이 없어 종합 점수를 계산하지 않았습니다" | Shell · §2 "이 기준은 점수에서 빠져 있어요." | 뜻 바뀜 주의: '종합 점수 계산 안 함' → '이 기준만 빠짐' · 고침 후: (Shell SH-8) '근처 새 아파트 실적이 없어 종합 점수를 계산하지 않았어요' | 다른 보드(Shell · 고침 SH-8) |
| 25 | [접수 가능] 제목 `page.G1.openNow.title` "지금 접수 가능" (h2) | Main · 첫 줄 h1 "지금 청약을 넣을 수 있는 단지는 …" | 문장으로 | 있음 |
| 26 | [접수 가능] 용어 ⓘ `intake_status` (Term) | — | — | 있음(고침 HM-1) |
| 27 | [접수 가능] 값 FactCell `kpis.intake_open_count` (count) | Main · 첫 줄 "3곳" | 같음 | 있음(고침 HM-1) |
| 28 | [접수 가능] 그 값의 라벨 배지 | — | — | 있음(고침 HM-1) |
| 29 | [접수 가능] 그 값 누르면 출처 창(점선 밑줄 버튼) | — | — | 있음(고침 HM-1) |
| 30 | [접수 가능] 단위 `page.G1.openNow.unit` "곳" | Main · 첫 줄 "3곳" | 같음 | 있음 |
| 31 | [접수 가능] 링크 `page.G1.openNow.link` "접수 가능 단지 보기" → /complexes?intake_status=가능 (전역 쿼리 유지) | Main · 첫 줄 파란 버튼 "접수 가능 단지 모두 보기" | 보기 → 모두 보기 | 있음 |
| 32 | [접수 가능] 안내 `page.G1.openNow.hint` "공식 자료로 확인한 접수 상태 기준입니다. 접수 기간은 단지 상세에서 확인하세요." | Main · 첫 줄 설명 "각 단지 공식 홈페이지와 청약홈에서 확인한 접수 상태예요. 카드를 누르면 …" | "접수 기간은 단지 상세에서" → "카드를 누르면 … 한 화면에서" | 있음 |
| 33 | [일정] 제목 `page.G1.upcoming.title` "다가오는 일정(4주)" | Main · 다가오는 일정 | "(4주)" 빠짐 · 고침 후: '다가오는 일정(4주)' | 있음(고침 HM-3) |
| 34 | [API] GET /ops/checklist (`useChecklist`) | Main · 다가오는 일정 | 호출 표시 없음 | 있음 |
| 35 | [일정] 열린 항목 + 기준일부터 28일 안만 거르기 | — | 기간 표시 없음 | 있음(고침 HM-3) |
| 36 | [일정] 최대 5건 | — | 목업은 7건 그림 · 고침 후: 5건으로 줄임 | 있음(고침 HM-3) |
| 37 | [일정] 날짜순 정렬 | Main · 다가오는 일정 아래 안내 "… 날짜순으로 보여 줘요" | 같음 | 있음 |
| 38 | [일정] 종류 배지 `page.common.scheduleKind.*` (청약 접수·당첨자 발표·계약·중도금 납부·전매 가능 시작·공고 예상·기한 만료·확인할 것·사실 재확인) | Main · 다가오는 일정 오른쪽 칩 "전매 제한 끝 · 청약 접수 · 중도금 · 계약 · 당첨자 발표" | 전매 가능 시작 → 전매 제한 끝, 중도금 납부 → 중도금 (공고 예상·기한 만료·확인할 것·사실 재확인 예는 없음) · 고침 후: '전매 가능 시작'·'중도금 납부' | 있음(고침 HM-3) |
| 39 | [일정] 날짜 + D± (formatDate) | Main · 다가오는 일정 왼쪽 상자 "오늘 / D-1 / D-5" + "10월 14일" | D± 상자 크게 | 있음 |
| 40 | [일정] 단지 이름 링크 → 단지 상세 | Main · 다가오는 일정 (이름이 글자일 뿐 링크 아님) | — | 있음(고침 HM-3) |
| 41 | [일정] 단지 없는 항목은 제목 글자 | — | — | 있음(고침 HM-4) |
| 42 | [일정] 항목 title(마우스 올림) = 원래 제목 | — | — | 문구로만(고침 HM-17) |
| 43 | [일정] 계산 기준 `page.common.scheduleBasis` "계산 기준: {basis}" | — | — | 있음(고침 HM-3) |
| 44 | [일정] 순위·구분 둘째 줄 (scheduleDetail) | Main · 다가오는 일정 "1순위 청약 접수 (인천·기타지역)" | 문장형 | 있음 |
| 45 | [일정] 403 `page.G1.upcoming.noAccess` "이 링크로는 일정을 볼 수 없습니다(운영 화면 권한 필요)" | — | — | 있음(고침 HM-4) |
| 46 | [일정] 오류 `page.common.loadError` (inline) | Shell · §7 | — | 다른 보드(Shell) |
| 47 | [일정] 불러오는 중 `app.loading` | Shell · §7 | — | 다른 보드(Shell) |
| 48 | [일정] 없음 `page.G1.upcoming.none` "4주 안의 일정이 없습니다" | — | — | 있음(고침 HM-4) |
| 49 | [일정] 전체 링크 `page.G1.upcoming.all` "전체 일정 보기" → /ops | Main · 다가오는 일정 "달력으로 보기" (href="#") | 이름 바뀜, 이동할 곳 미정 (Ops "2026년 10월 · 10건" 달력으로 보임) · 고침 후: '전체 일정 보기' → Ops | 있음(고침 HM-3) |
| 50 | [점수] 구역 제목 `page.G1.top5` "종합 점수 상위 단지" | Main · 점수 순서 · 상황: 기본 | 종합 점수 상위 단지 → 점수 순서 | 있음 |
| 51 | [점수] `page.G1.top5Scenario` "상황: {name}" | Main · 점수 순서 제목 "· 상황: 기본" | 같음 | 있음 |
| 52 | [점수] `page.G1.top5Note` "상대 비교 · 투자 권유 아님" | Main · 점수 순서 설명 "… 10점 만점 상대 비교예요 … 투자 권유가 아니에요." | 같은 뜻 | 있음 |
| 53 | [점수] 머리 "종합" `page.G1.total` + 용어 ⓘ `total` | Main · 점수 순서 "점수는 어떻게 매기나요?" 링크 (href="#") | ⓘ 팝오버 → 링크 (대상 미정) · 고침 후: 링크 대신 '종합 ?' 용어 버튼 | 있음(고침 HM-6) |
| 54 | [점수] 머리 `page.G1.p10` "가격 +10% 상승 가능성(판정기)" + 용어 ⓘ `p10` | — | — | 있음(고침 HM-6) |
| 55 | [점수] 5곳 미만 `page.G1.top5Fewer` | Main · 점수 순서 아래 "점수가 있는 단지가 3곳뿐이에요. 나머지는 단지 찾기에서 …" | 같은 뜻 | 있음 |
| 56 | [점수] 순위 5 이하(순위 없는 행 포함)만 | Main · 점수 순서 3줄 | 같음 | 있음 |
| 57 | [점수] 목록 ul (aria-label = 구역 제목), 카드 격자 | Main · 점수 순서 ol 줄 목록 | 카드 → 한 줄씩 | 있음 |
| 58 | [점수] 카드 빈 곳 누르면 단지 상세 (안쪽 버튼·링크는 제외) | — | 목업은 이름만 링크 | 문구로만(고침 HM-17) |
| 59 | [점수] 이름 링크 + aria-label `page.G1.open` "{name} 상세 보기" | Main · 점수 순서 이름 링크 | aria-label 없음 | 있음 |
| 60 | [점수] 순위 배지 (MetaValue rank) | Main · 점수 순서 동그라미 숫자 | 배지 → 동그라미 | 있음 |
| 61 | [점수] 생활권 이름 | Main · 점수 순서 둘째 줄 "미추홀구" | 같음 | 있음 |
| 62 | [점수] 접수 배지 IntakeBadge | — | 접수 가능 카드에만 있음 | 있음(고침 HM-7) |
| 63 | [점수] 동률 배지 TieBadge | Main · 점수 순서 "동률" | 같음 | 있음 |
| 64 | [점수] 동률(신뢰도) | Shell · §4 "동률(믿음 정도 0.62)" | 신뢰도 → 믿음 정도 | 다른 보드(Shell) |
| 65 | [점수] 순위 불안정 UnstableBadge | Shell · §4 "순위가 흔들려요" | — | 다른 보드(Shell) |
| 66 | [점수] 판정 범위 배지 JudgeScopeBadge (판정 대상은 숨김) | Shell · §4 점수 계산 범위 | — | 다른 보드(Shell) |
| 67 | [점수] 재판정 필요 배지 RejudgeNeededBadge | Shell · §4 "다시 판정 필요" | — | 다른 보드(Shell) |
| 68 | [점수] 현재 구매가 `page.G1.card.price` FactCell price_low ~ price_high (eok) | Main · 점수 순서 둘째 줄 "5억 9,850만~6억 5,090만" | 칸 이름 없이 줄 안 글, 7.49억 → 억·만 표기 | 있음(고침 HM-7) |
| 69 | [점수] 전매 종료 `page.G1.card.resaleEnd` FactCell (date, D±) | Main · 점수 순서 둘째 줄 "되팔기 2026.12.09" | 전매 종료 → 되팔기, D± 빠짐 · 고침 후: '전매 종료 2026.12.09 D-56' + 라벨 | 있음(고침 HM-7) |
| 70 | [점수] 가격 갭 `page.G1.card.gap` FactCell (pct) | Main · 점수 순서 둘째 줄 "주변보다 8.1% 높음" | 가격 갭 → 주변보다 n% 높음/낮음 | 있음 |
| 71 | [점수] 사실 칸(가격·전매·갭) 라벨 배지 + 출처 창 버튼 | — | — | 있음(고침 HM-7) |
| 72 | [점수] 빈 사유 `page.G1.noListRow` "이 기준일 자료에 없음" | — | — | 있음(고침 HM-7) |
| 73 | [점수] 종합 FactCell total (score) | Main · 점수 순서 오른쪽 "4.83" | 라벨은 바닥 "점수 모두 추정" 한 번 | 있음 |
| 74 | [점수] +10% 상승 가능성 FactCell p10 (prob) | Main · 점수 순서 "… 10% 넘게 오를 가능성 53% 판정기 추정" | 가격 +10% 상승 가능성 → 10% 넘게 오를 가능성 · 고침 후: '+10% 이상 오를 가능성' | 있음(고침 HM-5) |
| 75 | [점수] 목표 시점 `page.G1.p10Target` "목표 시점 {target}" (상황의 p10_horizon) | Main · 점수 순서 "입주 1년 뒤 …" | 문장 안으로 · 고침 후: '목표 시점: 입주+1년'을 따로 적음 | 있음(고침 HM-5) |
| 76 | [점수] `page.G1.p10Note` "당첨 확률이 아닙니다 · 보장 아님" | Main · 점수 순서 "당첨 확률이 아니에요" | "보장 아님" 빠짐 — 주의 · 고침 후: '보장 아님' 되살림 | 있음(고침 HM-5) |
| 77 | [API] GET /scenarios (목표 시점 p10_horizon 찾기) | Main · 점수 순서 "입주 1년 뒤" | 호출 표시 없음 | 있음 |
| 78 | [지역 현황] 구역 제목 `page.G1.region` "지역 현황" | Main · 인천 시장 한눈에 | 지역 현황 → {지역} 시장 한눈에 (지역 이름은 서버 값) | 있음 |
| 79 | [지역 현황] 모바일이면 접기(details) | — | — | 있음(고침 HM-15) |
| 80 | [지역 현황] 판정 대상 `page.G1.kpi.judged` "판정 대상(점수 계산 대상)" | Main · 시장 카드 "점수를 매긴 단지" + "점수 계산 대상(판정 대상)이에요" | 바뀜 | 있음 |
| 81 | [지역 현황] 판정 대상 용어 ⓘ `judge_scope` | — | — | 있음(고침 HM-10) |
| 82 | [지역 현황] FactCell `kpis.judged_count` (count) | Main · 시장 카드 "6곳 추정" | 같음 ("/ 100곳" 새로) · 고침 후: '/ [값]곳'(지금 응답에 없음 — API 필요) | 있음(고침 HM-10) |
| 83 | [지역 현황] 미분양 제목 `page.G1.kpi.unsold` "미분양" | Main · 시장 카드 "안 팔린 집 (미분양)" | 쉬운 말 더함 | 있음 |
| 84 | [지역 현황] FactCell `kpis.unsold.total` (households) | Main · 시장 카드 "3,729세대" | 라벨 없음 | 있음 |
| 85 | [지역 현황] 부제 `page.G1.kpi.unsoldSub` "{ym} 기준 · 준공 후" | Main · 시장 카드 "다 지었는데 안 팔린 집" | "{ym} 기준" 빠짐(그래프 범위 글로만) · 고침 후: '2026년 8월 기준' 되살림 | 있음(고침 HM-10) |
| 86 | [지역 현황] FactCell `kpis.unsold.post_completion` | Main · 시장 카드 "1,401세대" | 라벨 없음 | 있음 |
| 87 | [지역 현황] 시군구별 펼침 `page.G1.kpi.unsoldBreakdown` "시군구별 보기" | Main · 시장 카드 "구별로 보기" 링크 | 시군구별 → 구별로, 펼침 → 링크 모양 | 있음 |
| 88 | [지역 현황] 시군구별 내역 (이름 + FactCell, 출처 1클릭) | — | — | 있음(고침 HM-11) |
| 89 | [지역 현황] 입주 많은 해 `page.G1.kpi.movePeak` "입주가 가장 많은 해" | Main · 시장 카드 "입주가 가장 몰리는 해" | 많은 → 몰리는 | 있음 |
| 90 | [지역 현황] FactCell `kpis.move_in_peak.year` (text) | Main · 시장 카드 "2026년" | 같음 | 있음 |
| 91 | [지역 현황] FactCell `kpis.move_in_peak.units` (households) | Main · 시장 카드 "이 해에 14,710세대 입주 추정" | 문장형 | 있음 |
| 92 | [지역 현황] 마지막 수집 `page.G1.kpi.freshness` "마지막 수집" | Main · 시장 카드 "마지막으로 모은 때" | 바뀜 | 있음 |
| 93 | [지역 현황] FactCell `kpis.data_freshness.last_success_at` (date, D±) | Main · 시장 카드 "10.13 19:39" | D± → 시각 | 있음 |
| 94 | [지역 현황] `page.G1.kpi.freshnessSub` "수집 실패 {failing}곳 · 늦어진 곳 {stale}곳" (MetaText) | Main · 시장 카드 "수집 실패 0곳 · 늦어진 곳 1곳" | 같음 | 있음 |
| 95 | [지역 현황] 칸 값들의 라벨 배지·출처 창 버튼 (미분양·준공 후·마지막 수집) | — | 판정 대상·입주 세대만 "추정" 보임 | 있음(고침 HM-10) |
| 96 | [변경] 구역 제목 `page.G1.changes` "최근 변경" | Main · 최근에 바뀐 것 | 바뀜 | 있음 |
| 97 | [변경] 모바일이면 접기(details) | — | — | 있음(고침 HM-15) |
| 98 | [변경] 없음 `page.G1.noChanges` "최근 변경 없음" | Main · 최근에 바뀐 것 아래 "변경이 없으면 '최근 변경 없음'이 나와요" | 같음 | 문구로만 |
| 99 | [변경] 중요도 배지 `page.common.severity.*` 정보·알림·중요 | Main · 최근에 바뀐 것 "중요" + 아래 "정보 · 알림 · 중요 세 단계" | 같음 | 있음 |
| 100 | [변경] 재판정 대상 배지 `page.G1.rejudge` "재판정 대상" | Main · 최근에 바뀐 것 "다시 판정해요" | 재판정 대상 → 다시 판정해요 | 있음 |
| 101 | [변경] 단지 이름 | Main · 최근에 바뀐 것 단지 이름 | 같음 | 있음 |
| 102 | [변경] 단지 없는 변경의 대상 이름 `page.common.changeEntity.*` | — | — | 있음(고침 HM-14) |
| 103 | [변경] 서버 한 줄 요약(summary), title = 필드 이름 | Main · 최근에 바뀐 것 "공식 홈페이지 안내 팝업이 바뀌었어요" | title 없음 | 있음(고침 HM-14) |
| 104 | [변경] 요약 없을 때 `page.G1.changeSentence` "{field} 변경" + `page.common.changeField.*` | — | — | 있음(고침 HM-14) |
| 105 | [변경] 지역 첫 적재(first_load) 요약 문장 한 줄 | — | — | 있음(고침 HM-14) |
| 106 | [변경] 바로 보이는 값(plain): 필드 + "이전 → 이후" | — | — | 있음(고침 HM-14) |
| 107 | [변경] 감지 시각 detected_at (D±) | Main · 최근에 바뀐 것 "10.14 22:42" | D± → 시각 | 있음 |
| 108 | [변경] 줄 누르면 단지 상세 해당 탭(#tab) | Main · 최근에 바뀐 것 단지 이름 링크 | 탭 지정은 목업에서 확인 안 됨 | 있음 |
| 109 | [변경] 바뀐 값 펼침 `page.G1.changeShowValue` "바뀐 값 보기" | Main · 최근에 바뀐 것 첫 줄 details "바뀐 값 보기" | 같음 | 있음 |
| 110 | [변경] 바뀐 값 `page.common.arrow` "{old} → {new}" | Main · 펼친 글 "이전 식별값 90b9b7… → 새 식별값 ed830f…" | 문장형 설명 더함 | 있음 |
| 111 | [변경] 처음 3건만 | Main · 최근에 바뀐 것 3줄 | 같음 | 있음 |
| 112 | [변경] 더 보기 `page.G1.changesMore` (aria-expanded) | Main · "변경 2건 더 보기" | 남은 개수가 붙음 | 있음 |
| 113 | [변경] 접기 `page.G1.changesLess` "변경 접기" | — | — | 있음(고침 HM-14) |
| 114 | [C06] 종합 점수 분해 차트 (세로 쌓은 막대, `charts/C06`) | Main · 점수 순서 줄마다 가로 막대 | 차트 하나 → 줄별 막대, 점수 순서 구역에 합침 | 있음 | charts.contract › C06 stacked 6 시리즈, 정렬 = 종합 내림차순 · e2e charts-gallery › C06 normal |
| 115 | [C06] 제목 `chart.C06.title` "종합 점수 분해" | Main · 점수 순서 (제목 합침), 막대 aria-label "{이름} 점수 구성" | 종합 점수 분해 → 점수 구성 | 있음 | charts.r11 › 차트 이름(aria-label) = 제목 · e2e charts-gallery › C06 normal |
| 116 | [C06] 부제 가중치 `chart.C06.weights` "가중치 {weights}" | — | — | 있음(고침 HM-6) | charts.r11 › C06 비중 · charts.contract › C06 제목 부제 = 가중치 |
| 117 | [C06] 라벨 배지(종합 점수 라벨) | Main · 점수 순서 바닥 "점수 모두 추정" | 같음 | 있음 | ChartGallery.test › 정상 상태 카드는 라벨 배지 · e2e charts-gallery › C06 normal |
| 118 | [C06] 순위 불안정 배지 | Shell · §4 "순위가 흔들려요" | — | 다른 보드(Shell) | e2e charts-gallery › C06 normal(순위 불안정 배지) |
| 119 | [C06] 동률 배지 | Main · 점수 순서 줄마다 "동률" | 차트 머리 → 줄마다 | 있음 | e2e charts-gallery › C06 normal(동률 배지) |
| 120 | [C06] 미판정 `badge.unjudged` + 빗금 + 메모 `chart.C06.unjudgedNote` + 툴팁 `chart.C06.unjudgedTip` | Compare · 위 화면에서 접혀 있거나 가끔만 나오는 모습 "빗금 = 아직 판정 안 한 기준(점수 0)" | 미판정 → 아직 판정 안 한 기준 | 다른 보드(Compare) | charts.contract › C06 null component → 빗금 + "미판정" · charts.contract › C06 m26 … · charts.r11 › C06 미판정 범례 · ChartGallery.test › 특수 상태 배지 |
| 121 | [C06] 범례 `chart.C06.component.p10` "+10% 상승 가능성" | Main · 점수 순서 색 범례 "입주 뒤 오를 가능성" | 바뀜 · 고침 후: '+10% 오를 가능성'(입주 뒤 뺌 — 목표 시점은 상황마다 다름) | 있음(고침 HM-5) | charts.r11 › C06 비중 · rawKeys › C06 점수 분해: 축·범례·표 |
| 122 | [C06] 범례 `chart.C06.component.rerank` "판정기 순위" | Main · 색 범례 "비슷한 단지 사이 순위" | 바뀜 | 있음 | charts.r11 › C06 비중 · rawKeys › C06 점수 분해: 축·범례·표 |
| 123 | [C06] 범례 `chart.C06.component.gap` "가격 갭" | Main · 색 범례 "주변 시세와 차이" | 바뀜 | 있음 | charts.r11 › C06 비중 · rawKeys › C06 점수 분해: 축·범례·표 |
| 124 | [C06] 범례 `chart.C06.component.benchmark` "벤치마크" | Main · 색 범례 "근처 새 아파트 실적" | 바뀜 | 있음 | charts.r11 › C06 비중 · rawKeys › C06 점수 분해: 축·범례·표 |
| 125 | [C06] 범례 `chart.C06.component.supply` "공급" | Main · 색 범례 "같은 시기 입주 물량" | 바뀜 | 있음 | charts.r11 › C06 비중 · rawKeys › C06 점수 분해: 축·범례·표 |
| 126 | [C06] 범례 `chart.C06.component.liquidity` "유동성" | Main · 색 범례 "되팔기 쉬움" | 바뀜 | 있음 | charts.r11 › C06 비중 · rawKeys › C06 점수 분해: 축·범례·표 |
| 127 | [C06] 범례 `chart.C06.component.move_in` "입주 시기" (가중치 있을 때만 그림) | — | — | 있음(고침 HM-6) | charts.r11 › C06 색은 기준을 따른다 · charts.contract › C06 상황 A·D의 move_in 성분도 키로 받는다 |
| 128 | [C06] 이름 축(이름 + 종합 점수) | Main · 점수 순서 왼쪽 이름 · 오른쪽 점수 | 같음 | 있음 | charts.contract › C06 stacked 6 시리즈(이름 + 종합) |
| 129 | [C06] 점수 축(0부터, 눈금) | — | 10점 만점 길이 막대만 | 있음(고침 HM-8) | charts.r11 › C06 값 축 |
| 130 | [C06] 툴팁: 기여 `chart.C06.contribution` "기여 {value}" | Main · 막대 title "입주 뒤 오를 가능성 1.85점" | 기여 → n점 | 있음 | charts.contract › C06 stacked 6 시리즈(툴팁 = formula_text + 원값) |
| 131 | [C06] 툴팁: 점수 × 가중치, 원값 `chart.C06.raw`, 산출식 formula_text | — | — | 있음(고침 HM-8) | charts.contract › C06 stacked 6 시리즈(툴팁 = formula_text + 원값) |
| 132 | [C06] 종합 점수 큰 순 정렬(같으면 이름) | Main · 점수 순서 4.83 → 4.76 → 4.76 | 같음 | 있음 | charts.contract › C06 stacked 6 시리즈(정렬) |
| 133 | [C06] 표로 보기 | Main · 점수 순서 바닥 "표로 보기" | 같음 | 있음 | charts.r11 › ChartFrame 표로 보기 |
| 134 | [C06] 표 열 `chart.col.rank` "순위" | — | — | 있음(고침 HM-9) | buildOption.test › toTable(빈 데이터) 열 정의 · rawKeys › C06 점수 분해: 축·범례·표 |
| 135 | [C06] 표 열 `chart.col.name` "이름" | — | — | 있음(고침 HM-9) | buildOption.test › toTable(빈 데이터) 열 정의 · rawKeys › C06 점수 분해: 축·범례·표 |
| 136 | [C06] 표 열 `chart.col.total` "종합" | — | — | 있음(고침 HM-9) | buildOption.test › toTable(빈 데이터) 열 정의 · rawKeys › C06 점수 분해: 축·범례·표 |
| 137 | [C06] 표 열 성분별 점수 (`chart.C06.component.*`) | — | — | 있음(고침 HM-9) | buildOption.test › toTable(빈 데이터) 열 정의 · rawKeys › C06 점수 분해: 축·범례·표 |
| 138 | [C06] 빈 상태 `chart.C06.empty` "점수 없음" | Shell · §8 모든 차트의 틀 "자료가 없어요(이유)" | — | 다른 보드(Shell) | ChartGallery.test › 빈 상태 카드는 차트 대신 빈 상태 문구 |
| 139 | [C05] 미분양 추이 차트 (선 2개, 높이 200 작게, `charts/C05`) | Main · 인천 시장 한눈에 미분양 카드 작은 선 그래프 | 카드 안으로 줄어듦 | 있음 | charts.contract › C05 line 2개(합계·준공 후), connectNulls=false · e2e charts-gallery › C05 normal |
| 140 | [C05] 제목 `chart.C05.title` "미분양 추이" | Main · 미분양 카드 svg aria-label "미분양 추이: …" | 보이는 제목은 카드 이름 | 있음 | charts.r11 › 차트 이름(aria-label) = 제목 · e2e charts-gallery › C05 normal |
| 141 | [C05] 부제 `chart.C05.basis`/`basisScope` "월말 기준 · {scope}" | Main · 미분양 카드 "국토교통부 · 월말 기준" | 범위 이름 빠짐, 출처 이름 더함 | 있음 | charts.contract › C05 범위(scope)가 여럿이면 … 부제에 범위명 |
| 142 | [C05] 라벨 배지 | — | — | 있음(고침 HM-10) | e2e charts-gallery › C05 normal(라벨 배지) |
| 143 | [C05] 선 `chart.C05.total` "합계" (실선·동그라미) | Main · 미분양 카드 "실선 전체" | 합계 → 전체 | 있음(고침 HM-12) | charts.r11 › C05 범례 |
| 144 | [C05] 선 `chart.C05.postCompletion` "준공 후" (점선·네모 표시) | Main · 미분양 카드 "점선 다 지은 뒤" | 준공 후 → 다 지은 뒤 (네모 표시 없음) | 있음(고침 HM-12) | charts.r11 › C05 범례 |
| 145 | [C05] 월 축 | Main · 미분양 카드 범위 글 "2025.10 ~ 2026.08" | 눈금 → 범위 글 | 있음 | charts.contract › C05 결측 월은 null로 남긴다(월 축은 끊김 없음), 최근 24개월 |
| 146 | [C05] 세대 수 축 | — | — | 있음(고침 HM-12) | charts.r11 › C05 툴팁(축 이름 세대) · charts.r11 › 축 눈금 |
| 147 | [C05] 툴팁(월별 값) | — | — | 있음(고침 HM-12) | charts.r11 › C05 툴팁 |
| 148 | [C05] 자료 없는 달은 끊어 그림 | — | — | 문구로만(고침 HM-17) | charts.contract › C05 결측 월은 null로 남긴다 |
| 149 | [C05] 최근 24개월 | — | — | 문구로만(고침 HM-17) | charts.contract › C05 결측 월은 null로 남긴다(월 축은 끊김 없음), 최근 24개월 |
| 150 | [C05] 범위(시군구) 여럿이면 값 많은 범위 고르기 (동작) | — | — | 문구로만(고침 HM-17) | charts.contract › C05 범위(scope)가 여럿이면 … |
| 151 | [C05] 표로 보기 | Main · 미분양 카드 "표로 보기" 링크 | 버튼 → 링크 모양 | 있음 | charts.r11 › ChartFrame 표로 보기 |
| 152 | [C05] 표 열 `chart.col.month` "월" | — | — | 있음(고침 HM-13) | buildOption.test › toTable(빈 데이터) 열 정의 |
| 153 | [C05] 표 열 `chart.C05.total` "합계" | — | — | 있음(고침 HM-13) | buildOption.test › toTable(빈 데이터) 열 정의 |
| 154 | [C05] 표 열 `chart.C05.postCompletion` "준공 후" | — | — | 있음(고침 HM-13) | buildOption.test › toTable(빈 데이터) 열 정의 |
| 155 | [C05] 빈 상태 `chart.C05.empty` "미분양 자료 없음" | Shell · §8 "자료가 없어요(이유)" | — | 다른 보드(Shell) | ChartGallery.test › 빈 상태 카드는 차트 대신 빈 상태 문구 |
| 156 | [틀] 하단 고정 문구 `app.disclaimer` | Shell · §9 없는 주소 · 바닥 문구 | — | 다른 보드(Shell) |

## 요약

전체 156 · 있음 119 · 문구로만 7 · 다른 보드 30 · 빠짐 0

(2026-10-16 목업 고침 반영 — 상태 칸에 '고침 HM-n'이 붙은 줄 65개. 고친 내용은 `../fixes/fixes-Main.md`)

### 빠짐 목록

- 없음 — 2026-10-16 목업 고침으로 모두 그렸거나(있음) 보드 맨 아래 '구현할 때 지금 동작 그대로 유지' 상자에 적었어요(문구로만). 목록: `../fixes/fixes-Main.md`



## 새로 더한 것 (기존에 없던 것)

| # | 새 요소 | 새 목업 위치 | 메모 |
|---|---|---|---|
| N1 | 첫 줄 앞글 "{지역} · 기준일 {날짜} · 공식 자료 100곳 확인" | Main · 첫 줄 | '공식 자료 n곳'은 지금 대시보드 응답에 없는 값일 수 있음 — 계약 확인 필요 · 고침 HM-2: '[값]곳 · API 필요'로 바꿈 |
| N2 | 접수 가능 단지 카드 목록(지금 접수 가능한 단지마다 1장) | Main · 지금 접수 가능한 단지 | 지금 홈은 개수만 보임. 카드에 접수 배지·공급 종류 칩·구·세대수·분양가(84㎡)·계약금(추정)·되팔 수 있는 날(n일 남음)·입주(약 n년 뒤) |
| N3 | "곧 청약 접수가 시작돼요" 띠 (단지 1곳 + 특공·1순위·2순위·당첨자 발표 D-day + "일정·필요한 돈 보기") | Main · 곧 청약 접수 띠 | 어떤 단지를 고르는지 규칙 정해야 함 |
| N4 | 일정 줄의 문장형 설명("되팔기 제한이 끝나요", "중도금 3회차를 내는 날") + 바닥 안내 | Main · 다가오는 일정 | |
| N5 | 시장 카드 "/ 100곳"(전체 단지 수) | Main · 인천 시장 한눈에 | 고침 HM-2: Kpis에 없는 값 — '/ [값]곳 · API 필요'로 바꿈 |
| N6 | "지역 시장 자세히" · "데이터·운영에서 보기" 링크 | Main · 인천 시장 한눈에 | |
| N7 | 점수 순서 색 범례(성분 6색) + "점수는 어떻게 매기나요?" 링크 | Main · 점수 순서 | 고침 HM-6: 링크를 '종합 ?' 용어 버튼으로 바꿈 |
| N8 | 점수 바닥 "판정기 계산 2026-10-14" 날짜 | Main · 점수 순서 | |
| N9 | 변경 구역 부제 "10월 14일 밤 수집에서 찾은 변경 n건" + 중요도 설명 | Main · 최근에 바뀐 것 | |
| N10 | 바닥 글 "이 화면은 개인의 청약 자격을 판정하지 않아요. 최종 기준은 입주자 모집 공고문이에요." + 라벨 두 개 뜻 | Main · 바닥 글 | |
| N11 | 머리줄 "용어 사전" 버튼 아이콘 | Main · 머리줄 | |

## 참고: ko.json 에만 있고 코드에서 안 쓰는 G1 키

`page.G1.kpis`, `page.G1.kpi.intakeOpen`, `page.G1.kpi.movePeakSub`, `page.G1.unsoldSmall` — 기능이 아니라서 표에 넣지 않았다.
