# 대응표 — 공통 틀(layout · app · components · _shared 공용 조각 · 404 · /__charts) → Shell.dc.html

- 소스 위치는 `frontend/src/` 기준. ko 키는 `frontend/src/i18n/ko.json`.
- 새 목업 위치 표기: `Shell · §n 제목`(Shell 보드 섹션 번호), `Shell · 머리줄`(맨 위 header). 다른 보드는 `보드 · 섹션 제목`.
- 화면 하나에만 쓰는 차트 배지(`badge.substitute`·`newBuild`·`sampleEstimated*`)는 그 차트를 쓰는 화면 대응표(G3·G4·G6)에서 다룬다. `badge.unjudged`는 coverage-Main.md(C06)에 있다.
- "동작"이라고 적은 줄은 화면에 그림이 없는 행동(URL 공유·포커스·폴링 등)이다. 목업에 표시가 없으면 정직하게 `빠짐`으로 적었다. 구현 때 지금 테스트로 지킨다.

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 1 | [틀] 스킵 링크 (`layout/AppLayout.tsx` · `app.skipToContent` "본문으로 건너뛰기", 평소 숨김·포커스 때 보임) | Shell · 맨 위 왼쪽 링크 | 같음 (목업은 늘 보이게 그림) | 있음 | `SH` 스킵 링크는 main#main 을 가리키고, 본문은 main 랜드마크 |
| 2 | [틀] 본문 랜드마크 `main#main` (`layout/AppLayout.tsx`) | Shell · `<main id="main">` | 같음 | 있음 | `SH` 스킵 링크는 main#main 을 가리키고, 본문은 main 랜드마크 |
| 3 | [틀] 화면 조각 불러오는 동안 (`layout/AppLayout.tsx` Suspense · `app.loading` "불러오는 중…") | Shell · §7 불러오는 중 · 오류 · 빈 상태 (첫 카드) | 같음 | 있음 | `SC` Skeleton: 뼈대 줄(장식) + "불러오는 중…"(role=status, N9) |
| 4 | [틀] 하단 고정 문구 footer role=contentinfo (`layout/AppLayout.tsx` Disclaimer · `app.disclaimer` "투자 권유 아님 · 상대 비교") | Shell · §9 없는 주소 · 바닥 문구 | "투자 권유가 아니에요 · 단지끼리의 상대 비교예요" | 있음 | `SH` 바닥 문구는 D7 원문 그대로(투자 권유 아님 · 상대 비교)<br>`RT` 모든 화면 하단에 "투자 권유 아님 · 상대 비교" 고정 문구 |
| 5 | [틀] 모바일 읽기 전용 안내 (`layout/AppLayout.tsx` · `app.mobileReadOnly` "모바일에서는 읽기 전용입니다") | Shell · §2 알림 띠 (맨 아래 회색 칩) | "휴대폰에서는 보기만 할 수 있어요" | 있음 | `SH` 휴대폰 칩 문구(SH-9): 보기만 / 컴퓨터에서 — 없는 주소도 보기만<br>`RT` 모바일(≤768px): G1은 읽기 전용 안내, G7은 데스크톱 안내 |
| 6 | [틀] 모바일 미지원 화면 안내 (`layout/AppLayout.tsx` · `app.mobileUnsupported`) | Shell · §2 알림 띠 (맨 아래 회색 칩) | "이 화면은 컴퓨터에서 써 주세요" | 있음 | `SH` 휴대폰 칩 문구(SH-9): 보기만 / 컴퓨터에서 — 없는 주소도 보기만<br>`RT` 모바일(≤768px): G1은 읽기 전용 안내, G7은 데스크톱 안내 |
| 7 | [틀] 모바일 읽기 전용이면 쓰기 UI 숨김 (`data-readonly`·`data-write`, `hooks/useMobileLayout.ts`) | Ops · 펼친 모습 · 다른 상태 — 모든 묶음 공통 상태 ("입력 칸·버튼이 꺼져요") | 숨김 → "꺼져요"로 적힘 (뜻 차이 주의) | 다른 보드(Ops, 문구로만) | `RT` 모바일(≤768px): G1은 읽기 전용 안내, G7은 데스크톱 안내 |
| 8 | [틀] 띠 순서: 판정기 장애 → 지역 적재 → 재계산 → 탭 고정 → 읽기 전용 (`layout/AppLayout.tsx`) | Shell · §2 알림 띠 | 목업 순서는 읽기 전용이 탭 고정보다 위 · 고침 후: 탭 고정이 읽기 전용보다 위(지금 순서) | 있음(고침 SH-5) | `SH` 띠 순서(#8): 판정기 장애 → 지역 처음 분석 → 다시 계산한 값 → 읽기 전용<br>`SH` 띠 순서(#8): … 다시 계산한 값 → 탭 고정(SH-5) — 새 열쇠 사용 버튼 |
| 9 | [틀] 출처 서랍에 지금 보는 리비전 알리기 (`useProvenanceSnapshot`, 동작) | — | — | 문구로만(고침 SH-21) | `R3F2` G1 숫자 셀 → 출처 서랍 GET /provenance/{id}?snapshot_id=12, 충돌 출처 열기도 같은 snapshot_id |
| 10 | [머리줄] 머리줄 위에 붙음 sticky (`layout/Header.tsx`) | Shell · 머리줄 + 첫 문단 "모든 화면 꼭대기에 붙어 있어요" | 같음 | 있음 | `SH` 앱 이름 "청약 한눈에"는 표지와 함께 홈 링크이고 지역·상황 쿼리를 싣는다 |
| 11 | [머리줄] 앱 이름 (`layout/Header.tsx` · `app.name` "청약 분석", 글자만) | Shell · 머리줄 왼쪽 로고 "청약 한눈에" (홈 링크) | 청약 분석 → 청약 한눈에 | 있음 | `SH` 앱 이름 "청약 한눈에"는 표지와 함께 홈 링크이고 지역·상황 쿼리를 싣는다 |
| 12 | [머리줄] 메뉴 `nav.G1` "홈" (NavLink end) | Shell · 머리줄 주 메뉴 "홈" | 같음 | 있음 | `SH` 메뉴 이름(D30-2): 홈·단지 찾기·비교하기·지역 시장·보고서 │ 내 조건(시나리오)·데이터·운영 · 용어 사전<br>`CX` 데스크톱 메뉴: 홈·단지 리스트·비교·지역 시장·보고서 │ 시나리오·데이터·운영(옆) · 용어 |
| 13 | [머리줄] 메뉴 `nav.G2` "단지 리스트" | Shell · 머리줄 주 메뉴 | 단지 리스트 → 단지 찾기 | 있음 | `SH` 메뉴 이름(D30-2): 홈·단지 찾기·비교하기·지역 시장·보고서 │ 내 조건(시나리오)·데이터·운영 · 용어 사전 |
| 14 | [머리줄] 메뉴 `nav.G4` "비교" | Shell · 머리줄 주 메뉴 | 비교 → 비교하기 | 있음 | `SH` 메뉴 이름(D30-2): 홈·단지 찾기·비교하기·지역 시장·보고서 │ 내 조건(시나리오)·데이터·운영 · 용어 사전 |
| 15 | [머리줄] 메뉴 `nav.G6` "지역 시장" | Shell · 머리줄 주 메뉴 | 같음 | 있음 | `SH` 메뉴 이름(D30-2): 홈·단지 찾기·비교하기·지역 시장·보고서 │ 내 조건(시나리오)·데이터·운영 · 용어 사전 |
| 16 | [머리줄] 메뉴 `nav.G8` "보고서" | Shell · 머리줄 주 메뉴 | 같음 | 있음 | `SH` 메뉴 이름(D30-2): 홈·단지 찾기·비교하기·지역 시장·보고서 │ 내 조건(시나리오)·데이터·운영 · 용어 사전 |
| 17 | [머리줄] 구분선 뒤 작은 메뉴 `nav.G5` "시나리오" | Shell · 머리줄 (구분선 뒤 작은 글씨) | 시나리오 → 내 조건(시나리오) | 있음 | `SH` 메뉴 이름(D30-2): 홈·단지 찾기·비교하기·지역 시장·보고서 │ 내 조건(시나리오)·데이터·운영 · 용어 사전 |
| 18 | [머리줄] 구분선 뒤 작은 메뉴 `nav.G7` "데이터·운영" | Shell · 머리줄 (구분선 뒤 작은 글씨) | 같음 | 있음 | `SH` 메뉴 이름(D30-2): 홈·단지 찾기·비교하기·지역 시장·보고서 │ 내 조건(시나리오)·데이터·운영 · 용어 사전 |
| 19 | [머리줄] 메뉴 구분선 | Shell · 머리줄 (세로선) | 같음 | 있음 | `SH` 앱 이름 "청약 한눈에"는 표지와 함께 홈 링크이고 지역·상황 쿼리를 싣는다 |
| 20 | [머리줄] 용어 링크 오른쪽 끝 (`glossary.nav` "용어" → /glossary) | Shell · 머리줄 오른쪽 "용어 사전" 버튼 | 용어 → 용어 사전 | 있음 | `SH` 메뉴 이름(D30-2): 홈·단지 찾기·비교하기·지역 시장·보고서 │ 내 조건(시나리오)·데이터·운영 · 용어 사전 |
| 21 | [머리줄] 지금 화면 메뉴 강조 (NavLink isActive) | Shell · 머리줄 "홈" 파란 바탕 | 같음 | 있음 | `SH` 지금 화면 메뉴만 aria-current=page(강조) |
| 22 | [머리줄] 메뉴 이동 때 `?region·snapshot·scenario` 유지 (location.search, 동작) | — | — | 문구로만(고침 SH-21) | `R5` 헤더 네비 링크 8개(화면 7 + 용어 모음, R9-UI P6)가 모두 scenario·snapshot 을 싣고, 클릭하면 그대로 이동한다<br>`SH` 머리줄에는 메뉴가 없고 하단 고정 바에 홈·단지 찾기·용어 사전(쿼리 유지) |
| 23 | [머리줄] 모바일 메뉴 = 홈·단지 리스트 + 용어만 (`NAV_MOBILE`) | Mobile · 아래 탭 줄 "홈 · 단지 찾기 · 비교 · 지역 시장" | 항목이 다름: 비교·지역 시장(모바일 미지원 화면)이 들어가고 용어가 빠짐 — 주의 | 다른 보드(Mobile · Shell §10에 지금 메뉴 3개로 그림, 고침 SH-19) | `SH` 머리줄에는 메뉴가 없고 하단 고정 바에 홈·단지 찾기·용어 사전(쿼리 유지)<br>`CX` 모바일: 메뉴는 홈·단지 리스트(+용어), 상황은 전체 이름 select, 토큰·테마는 "설정" 안 |
| 24 | [머리줄] 메뉴 줄과 선택 줄 배치 (현재: 위=선택칸, 아래=메뉴) | Shell · 머리줄 (위=로고·메뉴, 아래=지역·기준일·상황·열쇠·화면) | 위아래 바뀜 | 있음 | `SH` 윗줄(표지·메뉴·접속 열쇠·화면) 다음 아랫줄(지역·기준일·상황) |
| 25 | [지역] 라벨 (`components/RegionPicker.tsx` · `header.region` "지역") | Shell · 머리줄 둘째 줄 "지역" | 같음 | 있음 | `SH` 윗줄(표지·메뉴·접속 열쇠·화면) 다음 아랫줄(지역·기준일·상황)<br>`RT` 헤더에 RegionPicker(+지역 추가)·SnapshotPicker·ScenarioToggle·테마 토글이 있다 |
| 26 | [지역] 지역 고르기 select (서버 지역 이름, GET /regions) | Shell · 머리줄 select + §1 기준일·상황 선택칸을 펼친 모습 "지역 고르기" | 같음 | 있음 | `SH` 윗줄(표지·메뉴·접속 열쇠·화면) 다음 아랫줄(지역·기준일·상황)<br>`RT` 헤더에 RegionPicker(+지역 추가)·SnapshotPicker·ScenarioToggle·테마 토글이 있다 |
| 27 | [지역] 마지막 항목 `header.regionAdd` "+ 지역 추가" → /regions/new | Shell · §1 "지역 고르기" 목록 끝 링크(RegionNew) | 같음 | 있음 | `CT` RegionPicker: "지역 추가" 선택 → onAddRegion<br>`RT` 헤더에 RegionPicker(+지역 추가)·SnapshotPicker·ScenarioToggle·테마 토글이 있다 |
| 28 | [지역] 지역 0개 `header.regionNone` "지역 없음" | Shell · §1 "지역 고르기" 아래 문구 | 같음 | 있음(고침 SH-10) | `SH` 지역이 없으면 "지역 없음" + 지역 추가, 기준일이 없으면 "기준일 없음"으로 칸이 꺼진다 |
| 29 | [지역] 지역 바꾸면 URL `?region=`·기준일은 그 지역 최신으로 (`hooks/useActiveRegion`·`useSnapshot`) | Shell · §1 "지역 고르기" 문구 "기준일은 그 지역의 가장 최근 날짜로 돌아가요" | 같음 | 문구로만 | `SH` 지역을 바꾸면 ?region= 이 바뀌고 기준일은 그 지역 최신으로(?snapshot= 을 뺀다, #29) |
| 30 | [기준일] 라벨 (`components/SnapshotPicker.tsx` · `header.snapshot` "기준일") | Shell · 머리줄 "기준일" | 같음 | 있음 | `SH` 윗줄(표지·메뉴·접속 열쇠·화면) 다음 아랫줄(지역·기준일·상황) |
| 31 | [기준일] 기준일 select (GET /regions/{id}/snapshots, 옵션 = asof_date) | Shell · 머리줄 select + §1 "기준일 고르기" 목록 | 같음 | 있음 | `CT` SnapshotPicker: 선택 → onChange(id)<br>`RT` 헤더에 RegionPicker(+지역 추가)·SnapshotPicker·ScenarioToggle·테마 토글이 있다 |
| 32 | [기준일] 리비전 2 이상 `picker.revision` "{date} · 리비전 {n}" | Shell · §1 "2026-10-14 · 8번째 수정본" | 리비전 n → n번째 수정본 | 있음 | `SC` 기준일 옵션 문구: n번째 수정본 · 일부 수집 실패 · 만드는 중<br>`SP` 리비전 1(또는 필드 없음)은 날짜만, 2 이상은 "· 리비전 n" + 사유 툴팁 |
| 33 | [기준일] 옵션 title `picker.revisionReason` "리비전 {n}: {reason}" | Shell · 머리줄 select title "수정본이 왜 생겼는지 이유가 여기 떠요" | 리비전 → 수정본 | 문구로만 | `SP` 리비전 1(또는 필드 없음)은 날짜만, 2 이상은 "· 리비전 n" + 사유 툴팁 |
| 34 | [기준일] degraded `picker.snapshotDegraded` "{date} · 일부 수집 실패" | Shell · §1 "2번째 수정본 · 일부 수집 실패" | 같음 | 있음 | `SC` 기준일 옵션 문구: n번째 수정본 · 일부 수집 실패 · 만드는 중<br>`CC` RegionPicker·SnapshotPicker: 숫자 id(계약)도 받는다 |
| 35 | [기준일] building `picker.snapshotBuilding` "{date} · 생성 중" | Shell · §1 "3번째 수정본 · 만드는 중" | 생성 중 → 만드는 중 | 있음 | `SC` 기준일 옵션 문구: n번째 수정본 · 일부 수집 실패 · 만드는 중<br>`SP` 기본 = 최신 기준일의 최신 published 리비전(생성 중 리비전은 건너뛴다) |
| 36 | [기준일] 목록 비면 `header.snapshotNone` "스냅샷 없음" + select 꺼짐 | Shell · §1 "기준일 고르기" 아래 문구 "기준일 없음" | 스냅샷 없음 → 기준일 없음 (꺼짐 표시는 없음) | 있음(고침 SH-10) | `SH` 지역이 없으면 "지역 없음" + 지역 추가, 기준일이 없으면 "기준일 없음"으로 칸이 꺼진다 |
| 37 | [기준일] 기본 선택 = 최신 기준일의 최신 발행 리비전 (`defaultSnapshot`, 동작) | Shell · §1 (8번째 수정본이 골라진 모습) | 규칙 설명은 없음 | 문구로만(고침 SH-21) | `SP` 기본 = 최신 기준일의 최신 published 리비전(생성 중 리비전은 건너뛴다) |
| 38 | [상황] radiogroup 라벨 (`components/ScenarioToggle.tsx` · `header.scenario` "상황") | Shell · 머리줄 "상황" 토글 | 같음 | 있음 | `SH` 상황 토글 묶음 앞에 이름 "상황"이 보이고 → 키로 다음 상황(URL ?scenario=) |
| 39 | [상황] 옵션 = 서버 시나리오 목록(내장 5 + 사용자, GET /scenarios), 값 없으면 첫 항목 선택 | Shell · 머리줄 5개 버튼 (기본 선택) + §1 휴대폰 select 의 "내 조건: 우리집 기준" | 같음 | 있음 | `E2S` G1 골격이 MSW 응답으로 렌더된다<br>`CT` ScenarioToggle: 클릭·화살표 키로 onChange |
| 40 | [상황] ←/→ 키로 이동 (roving tabindex) | Shell · §1 "상황(시나리오) 고르기" 문구 "화살표 키 ← → 로도" | 같음 | 문구로만 | `CT` ScenarioToggle: 클릭·화살표 키로 onChange<br>`SH` 상황 토글 묶음 앞에 이름 "상황"이 보이고 → 키로 다음 상황(URL ?scenario=) |
| 41 | [상황] 꺼짐 disabled prop | — | — | 있음(고침 SH-10) | `SC` 상황 고르기 꺼짐(disabled): 묶음 aria-disabled + 버튼 모두 꺼짐 |
| 42 | [상황] 시나리오 늦게 와도 자리 미리 잡기 (CLS, 동작) | — | — | 문구로만(고침 SH-21) | `SH` 상황 목록이 늦게 와도 자리를 미리 잡는다(CLS, #42) |
| 43 | [상황] 모바일 = select (`layout/Header.tsx` · `header.scenario`) | Shell · §1 "휴대폰 모습" select | 같음 | 있음 | `CX` 모바일: 메뉴는 홈·단지 리스트(+용어), 상황은 전체 이름 select, 토큰·테마는 "설정" 안 |
| 44 | [상황] 선택은 URL `?scenario=`로 공유 (`hooks/useScenario`, 동작) | — | — | 문구로만(고침 SH-21) | `E2S` 상황 토글이 URL ?scenario=로 공유된다(내장 시나리오 = code)<br>`SH` 상황 토글 묶음 앞에 이름 "상황"이 보이고 → 키로 다음 상황(URL ?scenario=) |
| 45 | [열쇠] 헤더 버튼 (`app/TokenDialog.tsx` TokenButton · `auth.button` "API 토큰" · 상태, aria-haspopup=dialog) | Shell · 머리줄 "접속 열쇠 · 쓰기 가능" | API 토큰 → 접속 열쇠 | 있음 | `SH` 접속 열쇠 버튼 네 상태(SH-14): 없음·쓰기 가능·읽기 전용·설정됨 |
| 46 | [열쇠] 상태 `auth.state.none` "토큰 없음" | — | — | 있음(고침 SH-14) | `SH` 접속 열쇠 버튼 네 상태(SH-14): 없음·쓰기 가능·읽기 전용·설정됨 |
| 47 | [열쇠] 상태 `auth.state.write` "쓰기 토큰" | Shell · 머리줄 버튼 "쓰기 가능" · §5 "지금: 쓰기 가능한 열쇠" | 쓰기 토큰 → 쓰기 가능(한 열쇠) | 있음(고침 SH-14) | `SH` 접속 열쇠 버튼 네 상태(SH-14): 없음·쓰기 가능·읽기 전용·설정됨 |
| 48 | [열쇠] 상태 `auth.state.read` "읽기 전용 토큰" | Shell · §2 읽기 전용 띠 (버튼 글자 모습은 없음) | 읽기 전용 열쇠 | 있음(고침 SH-14) | `SH` 접속 열쇠 버튼 네 상태(SH-14): 없음·쓰기 가능·읽기 전용·설정됨 |
| 49 | [열쇠] 상태 `auth.state.unknown` "토큰 설정됨" | — | — | 있음(고침 SH-14) | `SH` 접속 열쇠 버튼 네 상태(SH-14): 없음·쓰기 가능·읽기 전용·설정됨 |
| 50 | [화면] 테마 버튼 (`layout/ThemeToggle.tsx` · `header.theme` "테마" + `header.themeLight` "라이트", aria-pressed) | Shell · 머리줄 "화면: 밝게" (aria-pressed) | 테마: 라이트 → 화면: 밝게 | 있음 | `SH` 화면 밝기 버튼: "화면: 밝게" ↔ "화면: 어둡게"(aria-pressed) · html.dark · sa.theme 기억 |
| 51 | [화면] 다크 상태 문구 `header.themeDark` "다크" | — | — | 있음(고침 SH-20) | `SH` 화면 밝기 버튼: "화면: 밝게" ↔ "화면: 어둡게"(aria-pressed) · html.dark · sa.theme 기억 |
| 52 | [화면] 다크 모드 자체 (`lib/theme.tsx` html.dark + CSS 토큰) | — | — | 있음(고침 SH-20) | `SH` 화면 밝기 버튼: "화면: 밝게" ↔ "화면: 어둡게"(aria-pressed) · html.dark · sa.theme 기억<br>`TK` 다크 모드는 유지 — 기존 다크 토큰(바탕 #0D1117 · 카드 #161B22 · 글자 #E6EDF3 · 강조 #60A5FA)<br>`E2P` 다크 테마: html.dark + 배경색 전환 |
| 53 | [화면] 테마 기억 localStorage `sa.theme`·시스템 설정 따르기 (동작) | — | — | 문구로만(고침 SH-21) | `SH` 화면 밝기 버튼: "화면: 밝게" ↔ "화면: 어둡게"(aria-pressed) · html.dark · sa.theme 기억 |
| 54 | [머리줄] 모바일 '설정' 접기 안에 열쇠·테마 (`header.settings` "설정") | — | — | 있음(고침 SH-19) | `SH` '설정'은 처음에 접혀 있고 안에 접속 열쇠·화면 버튼, 바닥 문구는 하단 바 위<br>`CX` 모바일: 메뉴는 홈·단지 리스트(+용어), 상황은 전체 이름 select, 토큰·테마는 "설정" 안 |
| 55 | [머리줄] 발행 감시 30분 멈춤 안내 (`layout/Header.tsx` · `job.watchExpired`, role=status) | Shell · §2 "새 기준일이 올라오는지 30분 동안 지켜봤지만 아직이에요." · Ops · ①③⑦ 작업 진행 칸의 다른 문구 | 문구 쉬워짐 | 있음 | `R3G` 헤더: 30분 넘은 발행 대기 리비전 + /jobs 403 → 상한 안내와 다시 확인 버튼<br>`SH` 문구는 원래 뜻을 되살린다(미판정 모드·발행 순간 값·다른 탭·API_TOKEN) |
| 56 | [머리줄] 감시 멈춤 다시 확인 버튼 (`job.watchRecheck` "다시 확인", 기준일 목록 refetch) | Shell · §2 "다시 확인" 버튼 | 같음 | 있음 | `R3G` 헤더: 30분 넘은 발행 대기 리비전 + /jobs 403 → 상한 안내와 다시 확인 버튼 |
| 57 | [띠] 판정기 장애 띠 (`app/DegradedBanner.tsx` · `app.degraded`, GET /health status/judge=degraded, role=alert) | Shell · §2 첫 띠 "(서버나 판정기가 불안정할 때도 같은 띠가 떠요)" · Ops · ⑥ 판정기 장애 때 "판정기 장애 — 판정 쉬는 모드: …" | 미판정 모드 → 판정 쉬는 모드 · 고침 후: '판정기를 지금 쓸 수 없어요(미판정 모드)' — 기준일 띠와 둘로 나눔 | 있음(고침 SH-2) | `SH` 판정기 장애(/health degraded) → role=alert 주의 띠 + 경고 아이콘(SH-2)<br>`OPS` 판정기 degraded → 전역 배너 |
| 58 | [띠] 기준일 스냅샷 degraded 띠 (`app.degradedSnapshot` "이 기준일 스냅샷은 미판정 모드(degraded)로 만들어졌습니다") | Shell · §2 첫 띠 "일부 자료를 못 모았어요. 이 기준일의 몇몇 값은 비어 있을 수 있어요." | 뜻 바뀜 주의: 미판정 모드 → 자료 못 모음 · 고침 후: '이 기준일 자료는 판정기를 못 쓰는 상태(미판정 모드)에서 만들어졌어요' | 있음(고침 SH-3) | `SH` 기준일 스냅샷 degraded 는 다른 문구·아이콘 없음(SH-3) |
| 59 | [띠] 지역 첫 적재 중 (`app/RegionLoadingBanner.tsx` · `app.regionBootstrapping`, role=status) | Shell · §2 "이 지역을 처음 분석하고 있어요. 끝나면 화면이 채워져요." | 문구 쉬워짐 | 있음 | `SH` 지역 처음 분석 중/실패 띠: 굵은 한 줄 + 데이터·운영 링크(/ops?region=)<br>`R4F12` 지역 status bootstrapping(발행 리비전 없음) → 화면 … |
| 60 | [띠] 지역 첫 적재 실패 (`app.regionFailed`, 빨강 글자) | Shell · §2 "지역 분석이 실패했어요." | 같은 뜻 | 있음 | `SH` 지역 처음 분석 중/실패 띠: 굵은 한 줄 + 데이터·운영 링크(/ops?region=) |
| 61 | [띠] 띠 안 링크 /ops?region= (`nav.G7` "데이터·운영") | Shell · §2 "데이터·운영에서 진행 보기" / "데이터·운영에서 이유 보기" | 링크 글자 늘어남 | 있음 | `SH` 지역 처음 분석 중/실패 띠: 굵은 한 줄 + 데이터·운영 링크(/ops?region=) |
| 62 | [띠] 재계산 값 포함 (`app/BackfilledBanner.tsx` · `app.backfilled` "업그레이드 때 다시 계산한 값이 포함(발행 순간 값이 아닐 수 있음) — 다시 계산한 날 {date}", KST) | Shell · §2 "이 기준일은 나중에 채워 넣은 자료예요 (2026-10-13에 보충)." | "발행 순간 값이 아닐 수 있음" 빠짐 — 주의 · 고침 후: '발행 순간 값과 다를 수 있음' 되살림 | 있음(고침 SH-4) | `R3I2` 보고 있는 리비전에 backfilled_at → 안내(KST 날짜), 문구는 ko.json<br>`SH` 문구는 원래 뜻을 되살린다(미판정 모드·발행 순간 값·다른 탭·API_TOKEN) |
| 63 | [띠] 탭 고정 띠 (`app/TokenDialog.tsx` TokenPinnedBanner · `auth.pinnedBanner` "다른 탭에서 저장된 토큰이 바뀌었습니다 — 이 탭은 기존 토큰을 유지합니다") | Shell · §2 "이 탭은 공유받은 열쇠로 고정돼 있어요." | 뜻 바뀜 주의: '다른 탭이 바꿈'이 '공유받은 열쇠로 고정'으로 · 고침 후: '다른 탭에서 저장한 열쇠가 바뀌었어요. 이 탭은 원래 열쇠를 그대로 써요' | 있음(고침 SH-5) | `SH` 띠 순서(#8): … 다시 계산한 값 → 탭 고정(SH-5) — 새 열쇠 사용 버튼<br>`SHR` 다른 탭 변경으로 고정된 토큰이면 배너 + "새 토큰 사용" → 고정 해제 |
| 64 | [띠] 탭 고정 풀기 버튼 (`auth.useNewToken` "새 토큰 사용", 고정 풀고 모든 쿼리 다시) | Shell · §2 "새 열쇠 사용" | 토큰 → 열쇠 | 있음 | `SH` 띠 순서(#8): … 다시 계산한 값 → 탭 고정(SH-5) — 새 열쇠 사용 버튼<br>`SHR` 다른 탭 변경으로 고정된 토큰이면 배너 + "새 토큰 사용" → 고정 해제 |
| 65 | [띠] 읽기 전용 토큰 띠 (ReadOnlyBanner · `auth.readOnlyBanner`) | Shell · §2 "공유받은 읽기 전용 열쇠로 보고 있어요. 저장·실행 버튼은 눌리지 않아요." | "공유받은"이 더해짐, "쓰기 토큰(API_TOKEN)으로 바꾸세요" 빠짐 · 고침 후: '공유받은' 뺌, '쓰기 열쇠(API_TOKEN)로 바꿔 주세요' 되살림 | 있음(고침 SH-6) | `SH` 읽기 전용 띠(SH-6): 열쇠 바꾸기 → 열쇠 창(머리줄 버튼으로 연 이유)<br>`TD` 읽기 전용 토큰 → 저장(role=read) · 안내 배너 · 쓰기 버튼 비활성 |
| 66 | [띠] 읽기 전용 띠의 바꾸기 버튼 (`auth.change` "토큰 바꾸기") | Shell · §2 "열쇠 바꾸기" | 토큰 → 열쇠 | 있음 | `SH` 읽기 전용 띠(SH-6): 열쇠 바꾸기 → 열쇠 창(머리줄 버튼으로 연 이유) |
| 67 | [쓰기] 쓰기 버튼 꺼짐 + title `auth.readOnlyHint` (`api/auth` useCanWrite) | Ops · 모든 묶음 공통 상태 · Scenario · 가끔만 나오는 모습 "D · 읽기 전용 열쇠일 때" | "읽기 전용 열쇠로는 저장·실행할 수 없어요" | 다른 보드(Ops·Scenario, 문구로만) | `TD` 읽기 전용 토큰 → 저장(role=read) · 안내 배너 · 쓰기 버튼 비활성 |
| 68 | [쓰기] 쓰기 요청 403 → 읽기 전용으로 표시 (`markReadOnly`, 동작) | — | — | 문구로만(고침 SH-21) | `AU` 쓰기 요청이 403 forbidden → 읽기 전용으로 표시(쓰기 버튼 끔) |
| 69 | [알림] 알림 구역 aria-label (`app/toast.tsx` · `app.notifications` "알림") | Shell · §6 작업 진행 · 알림 (role=region "알림") | 같음 | 있음 | `SC` 어두운 바탕 알림 · 행동 버튼은 실행 후 닫힘 · × 로 닫힘 · 최대 4개 |
| 70 | [알림] 알림 한 줄 (role=status, aria-live=polite) | Shell · §6 "시나리오를 저장했어요" | 같음 | 있음 | `SC` 어두운 바탕 알림 · 행동 버튼은 실행 후 닫힘 · × 로 닫힘 · 최대 4개 |
| 71 | [알림] 알림 행동 버튼 (누르면 실행 후 닫힘) | Shell · §6 "재시도 작업을 등록했어요 [보기]" | 같음 | 있음 | `SC` 어두운 바탕 알림 · 행동 버튼은 실행 후 닫힘 · × 로 닫힘 · 최대 4개 |
| 72 | [알림] 닫기 × (`app.toastClose` "알림 닫기") | Shell · §6 × (aria-label "알림 닫기") | 같음 | 있음 | `SC` 어두운 바탕 알림 · 행동 버튼은 실행 후 닫힘 · × 로 닫힘 · 최대 4개 |
| 73 | [알림] 최대 4개 | Shell · §6 "화면 아래에 최대 4개" | 같음 | 문구로만 | `SC` 어두운 바탕 알림 · 행동 버튼은 실행 후 닫힘 · × 로 닫힘 · 최대 4개 |
| 74 | [알림] 8초 뒤 자동 닫힘 | Shell · §6 "8초 뒤 사라져요" | 같음 | 문구로만 | `SC` 기본 8초 뒤 닫힘, duration 0 은 남는다 |
| 75 | [알림] duration 0 = 직접 닫을 때까지 | — | — | 문구로만(고침 SH-21) | `SC` 기본 8초 뒤 닫힘, duration 0 은 남는다 |
| 76 | [열쇠 창] 열리는 때: 401 자동 / 헤더 버튼 (`api/client.ts` requestToken) | Shell · §5 문구 "서버가 401을 주면 이 창이 자동으로 열려요" | 같음 | 문구로만 | `TD` 토큰 없이 401 → 다이얼로그(토큰 필요) → 틀린 토큰은 거절<br>`AU` 401 → 토큰 다이얼로그 요청(토큰 없음 = missing, 있음 = invalid) |
| 77 | [열쇠 창] 모달 (배경 어둡게, aria-modal=true) | Shell · §5 창만 그림 (role=dialog) | 배경·모달 표시 없음 | 있음(고침 SH-13) | `SH` 뒤 화면 어둡게(aria-modal) · 안내(API_TOKEN·READONLY_TOKEN·이 브라우저에만) · 입력칸 포커스 · Esc 로 닫힘 |
| 78 | [열쇠 창] 제목 `auth.title` "API 토큰 설정" | Shell · §5 접속 열쇠(토큰) 창 "접속 열쇠 넣기" | 바뀜 | 있음 | `SH` 뒤 화면 어둡게(aria-modal) · 안내(API_TOKEN·READONLY_TOKEN·이 브라우저에만) · 입력칸 포커스 · Esc 로 닫힘 |
| 79 | [열쇠 창] 사유 `auth.reason.invalid` (role=alert, 빨강) | Shell · §5 "열쇠가 맞지 않아요(401). 다시 넣어 주세요." | 토큰 → 열쇠 | 있음(고침 SH-13) | `AU` 401 → 토큰 다이얼로그 요청(토큰 없음 = missing, 있음 = invalid) |
| 80 | [열쇠 창] 사유 `auth.reason.missing` "이 서버는 API 토큰이 필요합니다" | — | — | 있음(고침 SH-13) | `TD` 토큰 없이 401 → 다이얼로그(토큰 필요) → 틀린 토큰은 거절 |
| 81 | [열쇠 창] 사유 `auth.reason.manual` "토큰을 바꾸거나 지울 수 있습니다" | — | — | 있음(고침 SH-13) | `SH` 읽기 전용 띠(SH-6): 열쇠 바꾸기 → 열쇠 창(머리줄 버튼으로 연 이유) |
| 82 | [열쇠 창] 안내 `auth.intro` "서버의 API_TOKEN(쓰기) 또는 READONLY_TOKEN(읽기 전용)… 이 브라우저에만 저장됩니다." | Shell · §5 "이 컴퓨터의 서버에 들어가는 열쇠예요." | 환경변수 이름·"이 브라우저에만 저장" 빠짐 — 주의 · 고침 후: 환경변수 이름·'이 브라우저에만 저장돼요' 되살림 | 있음(고침 SH-13) | `SH` 뒤 화면 어둡게(aria-modal) · 안내(API_TOKEN·READONLY_TOKEN·이 브라우저에만) · 입력칸 포커스 · Esc 로 닫힘 |
| 83 | [열쇠 창] 지금 상태 `auth.current` "현재: {state}" | Shell · §5 "지금: 쓰기 가능한 열쇠" | 현재 → 지금 | 있음 | `TD` 헤더 버튼으로 열고, 저장한 토큰을 지울 수 있다 |
| 84 | [열쇠 창] 입력 라벨 `auth.label` "토큰" | Shell · §5 "열쇠" | 토큰 → 열쇠 | 있음 | `TD` 토큰 없이 401 → 다이얼로그(토큰 필요) → 틀린 토큰은 거절 |
| 85 | [열쇠 창] 입력칸 password·autocomplete off·열 때 포커스 | Shell · §5 password 입력칸 | 포커스는 표시 없음 | 있음 | `TD` 토큰 없이 401 → 다이얼로그(토큰 필요) → 틀린 토큰은 거절<br>`SH` 뒤 화면 어둡게(aria-modal) · 안내(API_TOKEN·READONLY_TOKEN·이 브라우저에만) · 입력칸 포커스 · Esc 로 닫힘<br>`SH` "열쇠 보이기"를 켜면 입력칸이 글자로 보인다 |
| 86 | [열쇠 창] 보이기 체크 `auth.show` "토큰 보이기" | Shell · §5 "열쇠 보이기" | 토큰 → 열쇠 | 있음 | `SH` "열쇠 보이기"를 켜면 입력칸이 글자로 보인다 |
| 87 | [열쇠 창] 저장 `auth.save` "확인 후 저장" (확인 = GET /regions + POST /jobs `{}` 로 읽기/쓰기 판별) | Shell · §5 "확인하고 저장" | 확인 후 → 확인하고 | 있음 | `TD` 쓰기 토큰 → 저장(role=write) · 배너 없음 · 생성 버튼 켜짐 |
| 88 | [열쇠 창] 확인 중 `auth.checking` "토큰 확인 중…" (버튼 꺼짐) | Shell · §5 아래 문구 "확인 중에는 '열쇠 확인 중…'" | 토큰 → 열쇠 | 있음(고침 SH-13) | `SH` 비어 있으면 "열쇠를 넣어 주세요"(role=alert), 확인 중에는 버튼이 꺼지고 "열쇠 확인 중…" |
| 89 | [열쇠 창] 검증 오류: 비어 있음 `auth.empty` "토큰을 입력하세요" | Shell · §5 아래 문구 "비어 있음" | — | 있음(고침 SH-13) | `SH` 비어 있으면 "열쇠를 넣어 주세요"(role=alert), 확인 중에는 버튼이 꺼지고 "열쇠 확인 중…" |
| 90 | [열쇠 창] 검증 오류: 틀림 `auth.invalid` "토큰이 맞지 않습니다(401)" | Shell · §5 아래 문구 "틀림" | — | 있음(고침 SH-13) | `TD` 토큰 없이 401 → 다이얼로그(토큰 필요) → 틀린 토큰은 거절 |
| 91 | [열쇠 창] 검증 오류: 확인 실패 `auth.checkError` "{detail}" | Shell · §5 아래 문구 "확인 실패" | — | 있음(고침 SH-13) | `SH` 확인 요청이 실패하면 "열쇠를 확인하지 못했어요: …"(role=alert) |
| 92 | [열쇠 창] 지우기 `auth.clear` "저장한 토큰 지우기" (저장돼 있을 때만) | Shell · §5 "저장한 열쇠 지우기" | 조건부 표시는 안 적힘 | 있음(고침 SH-13) | `TD` 헤더 버튼으로 열고, 저장한 토큰을 지울 수 있다<br>`SH` 뒤 화면 어둡게(aria-modal) · 안내(API_TOKEN·READONLY_TOKEN·이 브라우저에만) · 입력칸 포커스 · Esc 로 닫힘 |
| 93 | [열쇠 창] 닫기 `auth.close` | Shell · §5 "닫기" | 같음 | 있음 | `TD` 헤더 버튼으로 열고, 저장한 토큰을 지울 수 있다 |
| 94 | [열쇠 창] Esc로 닫기 | — | — | 문구로만(고침 SH-21) | `SH` 뒤 화면 어둡게(aria-modal) · 안내(API_TOKEN·READONLY_TOKEN·이 브라우저에만) · 입력칸 포커스 · Esc 로 닫힘 |
| 95 | [열쇠 창] 저장 알림 `auth.savedWrite` "쓰기 토큰을 저장했습니다" | — | — | 있음(고침 SH-15) | `TD` 저장소 쓰기가 막혀도 이 탭에서는 동작하고 안내한다<br>`SH` 열쇠 저장·지움 알림 문구(SH-15)는 해요체 |
| 96 | [열쇠 창] 저장 알림 `auth.savedRead` "…저장·실행 버튼은 꺼집니다" | — | — | 있음(고침 SH-15) | `SH` 열쇠 저장·지움 알림 문구(SH-15)는 해요체<br>`TD` 읽기 전용 토큰 → 저장(role=read) · 안내 배너 · 쓰기 버튼 비활성 |
| 97 | [열쇠 창] 저장소 못 씀 `auth.notPersisted` "… 이 탭에서만 유지됩니다" | — | — | 있음(고침 SH-15) | `TD` 저장소 쓰기가 막혀도 이 탭에서는 동작하고 안내한다 |
| 98 | [열쇠 창] 지움 알림 `auth.cleared` | — | — | 있음(고침 SH-15) | `SH` 열쇠 저장·지움 알림 문구(SH-15)는 해요체<br>`TD` 헤더 버튼으로 열고, 저장한 토큰을 지울 수 있다 |
| 99 | [열쇠 창] 저장·지움 뒤 모든 쿼리 다시 (동작) | — | — | 문구로만(고침 SH-21) | `TD` 읽기 전용 토큰 → 저장(role=read) · 안내 배너 · 쓰기 버튼 비활성 |
| 100 | [출처] 숫자 누르면 출처 창 (`components/FactCell.tsx` 점선 밑줄 버튼 → ProvenanceProvider) | Shell · §3 숫자를 누르면 열리는 '출처' 창 "밑줄 점선이 있는 숫자는 모두 누를 수 있어요" | 같음 | 있음 | `FC` 클릭하면 onOpenProvenance(prov)를 부른다<br>`CC` 상충 그룹(채택·미채택)과 원문 발췌 하이라이트를 보여 준다 |
| 101 | [출처] 오른쪽 서랍 role=dialog aria-modal=false (`components/ProvenancePanel.tsx`) | Shell · §3 aside "출처 창 예시" | 오른쪽 붙음 여부는 안 그림 | 있음 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 102 | [출처] 제목 `provenance.title` "출처" | Shell · §3 "이 값은 어디서 왔나요?" | 출처 → 이 값은 어디서 왔나요? | 있음 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 103 | [출처] 종류 `provenance.kind.field` "공고·수집 값" | Shell · §3 제목 옆 칩 "공고·수집 값" | 같음 | 있음 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 104 | [출처] 종류 `provenance.kind.score_component` "점수 성분" | Shell · §3 아래 안내 "출처 종류는 … 점수 성분 …" | 같음 | 문구로만 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음"<br>`CC` 점수 성분 출처는 산출식을 보여 주고, Esc로 닫힌다 |
| 105 | [출처] 종류 `provenance.kind.score_total` "종합 점수" | Shell · §3 아래 안내 | 같음 | 문구로만 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 106 | [출처] 종류 `provenance.kind.judgment` "판정기 로그" | Shell · §3 아래 안내 | 판정기 로그 → 판정기 기록 | 문구로만 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 107 | [출처] 종류 `provenance.kind.human_check` "사람 확인" | Shell · §3 아래 안내 | 같음 | 문구로만 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 108 | [출처] 종류 `provenance.kind.raw_document` "원문" | Shell · §3 아래 안내 | 같음 | 문구로만 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 109 | [출처] 종류 `provenance.kind.comparable_set` "비교군" | Shell · §3 아래 안내 | 비교군 → 비교 단지 | 문구로만 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 110 | [출처] 닫기 `provenance.close` (열 때 닫기에 포커스) | Shell · §3 "닫기" | 포커스 표시 없음 | 있음 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 111 | [출처] Esc로 닫기 | — | — | 문구로만(고침 SH-21) | `CC` 점수 성분 출처는 산출식을 보여 주고, Esc로 닫힌다 |
| 112 | [출처] 불러오는 중 `app.loading` / 준비 중 `page.common.materializePending` | Shell · §7 (공통 모양) | 같음 | 다른 보드(Shell §7 공통 상태) | `R3F2` 출처 서랍 503 → 준비 중 → 자동 재시도 뒤 내용 |
| 113 | [출처] 오류 `provenance.error` "출처를 불러오지 못했습니다({detail})" | Shell · §7 "불러오지 못했어요" (공통 모양) | 공통 문구로 | 다른 보드(Shell §7 공통 상태) | `SC` 출처를 못 불러오면 "출처를 불러오지 못했어요(…)" |
| 114 | [출처] 저장본 검증 실패 `page.common.storedViewMismatch` | — | — | 있음(고침 SH-17) | `R3F2` stored_view_mismatch(500) → 서버 오류(저장본 검증 실패) 문구, 재시도 없음<br>`SC` 저장본 검증 실패(SH-17) = 주의 카드 role=alert |
| 115 | [출처] 대상·필드 줄 (entity · field) | Shell · §3 dt "무엇" "시티오씨엘 8단지 · 기준 타입(84C) 최고 공급금액" | 줄 이름 "무엇" 새로 | 있음 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 116 | [출처] 값 `provenance.value` "값" | Shell · §3 "값 631,400,000원" | 같음 | 있음 | `CC` 상충 그룹(채택·미채택)과 원문 발췌 하이라이트를 보여 준다 |
| 117 | [출처] 라벨 `provenance.label` "라벨" + 라벨 전문(full) | Shell · §3 "라벨 확인됨" | 같음 | 있음 | `CC` full 이면(출처 패널) 줄이지 않는다 |
| 118 | [출처] 강등 배지 `provenance.demoted` "강등됨(검증 모순)" | Shell · §3 아래 안내 "낮춤(검증 모순) 표시" | 강등됨 → 낮춤 | 있음(고침 SH-11) | `SC` 검증 모순으로 낮춘 값: '낮춤(검증 모순)' 배지 + 풀리는 조건 문장<br>`R3D` 출처 서랍: 강등 중(label 확인 불가 · reason 검증 모순 — …)이면 강등 배지·해제 조건, 아니면 없다 |
| 119 | [출처] 강등 해제 조건 `provenance.demotedHint` | Shell · §3 아래 안내 "이유가 함께 떠요" (해제 조건 문장 없음) | 해제 조건(사람 확인·새 원문) 빠짐 | 있음(고침 SH-11) | `SC` 검증 모순으로 낮춘 값: '낮춤(검증 모순)' 배지 + 풀리는 조건 문장<br>`R3D` 출처 서랍: 강등 중(label 확인 불가 · reason 검증 모순 — …)이면 강등 배지·해제 조건, 아니면 없다 |
| 120 | [출처] 확인일 `provenance.checkedAt` "확인일" | Shell · §3 "확인한 날" | 확인일 → 확인한 날 | 있음 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 121 | [출처] 원문 주소 `provenance.url` (ExternalLink 새 탭, safeHref) | Shell · §3 "원문 주소" 링크 | 같음 | 있음 | `SF` 허용 URL → <a target=_blank rel=noopener> |
| 122 | [출처] 출처 종류·순위 `provenance.source` + `provenance.sourceRank` "{rank}순위 출처" | Shell · §3 "출처 종류 · 공고문 PDF · 1순위 출처" | 같음 | 있음 | `CC` 상충 그룹(채택·미채택)과 원문 발췌 하이라이트를 보여 준다 |
| 123 | [출처] HTTP 상태 `provenance.httpStatus` | Shell · §3 "응답 상태 정상(200)" | HTTP 상태 → 응답 상태 | 있음 | `SC` 출처 창: 응답 상태·판정 기록 번호 · 원문 앞뒤 보기 ↔ 원문 닫기 · 다른 출처의 단위 근거 |
| 124 | [출처] 산출식 `provenance.formula` | Shell · §3 "계산식" | 산출식 → 계산식 | 있음 | `CC` 점수 성분 출처는 산출식을 보여 주고, Esc로 닫힌다 |
| 125 | [출처] 판정 로그 번호 `provenance.judgment` "#n" | Shell · §3 "판정 기록 #1298 출처 비교" (링크) | 판정 로그 → 판정 기록, 링크로 | 있음 | `SC` 출처 창: 응답 상태·판정 기록 번호 · 원문 앞뒤 보기 ↔ 원문 닫기 · 다른 출처의 단위 근거 |
| 126 | [출처] 원문 발췌 `provenance.excerpt` + 값 `<mark>` | Shell · §3 "원문 발췌" + 노란 표시 | 같음 | 있음 | `CC` 상충 그룹(채택·미채택)과 원문 발췌 하이라이트를 보여 준다 |
| 127 | [출처] 원문에서 보기 `provenance.rawText` (GET /raw/{id}?as=text, 발췌 위치 앞뒤 160자) | Shell · §3 "원문에서 앞뒤 보기" | 원문에서 보기 → 원문에서 앞뒤 보기 | 있음 | `CC` 원문 텍스트를 열면 excerpt 오프셋 구간을 하이라이트한다 |
| 128 | [출처] 원문 닫기 `provenance.rawTextHide` | — | — | 있음(고침 SH-11) | `SC` 출처 창: 응답 상태·판정 기록 번호 · 원문 앞뒤 보기 ↔ 원문 닫기 · 다른 출처의 단위 근거 |
| 129 | [출처] 원문 텍스트 불러오는 중·실패 `provenance.rawLoading`/`rawError` | Ops · ② 화면 캡처 미리보기 펼친 모습 · DetailTabs · 출처·원문 — 다른 상태 | 같은 뜻 | 다른 보드(Ops·DetailTabs) | `CC` 원문 텍스트를 열면 excerpt 오프셋 구간을 하이라이트한다<br>`RD` 실패하면 오류 문구 |
| 130 | [출처] 단위 근거 `provenance.unitBasis` | Shell · §3 "단위 근거 표 머리 '단위: 원'" | 같음 | 있음 | `R4F10` 출처 서랍: 발췌 본문 + …(단위 근거) |
| 131 | [출처] 상충 출처 `provenance.conflicts` | Shell · §3 "다른 출처" | 상충 출처 → 다른 출처 | 있음 | `CC` 상충 그룹(채택·미채택)과 원문 발췌 하이라이트를 보여 준다 |
| 132 | [출처] 상충 없음 `provenance.noConflicts` "상충 없음" | Shell · §3 "다른 출처가 없으면 '엇갈리는 출처 없음'" | 상충 없음 → 엇갈리는 출처 없음 | 문구로만 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 133 | [출처] 상충 항목 값 (value_text) | Shell · §3 상충 칸 "631,400,000" / "63,140 (만원)" | 같음 | 있음 | `CC` 상충 그룹(채택·미채택)과 원문 발췌 하이라이트를 보여 준다 |
| 134 | [출처] 채택/미채택 배지 `provenance.chosen`/`notChosen` | Shell · §3 "채택" / "미채택" | 같음 | 있음 | `CC` 상충 그룹(채택·미채택)과 원문 발췌 하이라이트를 보여 준다 |
| 135 | [출처] 상충 항목 라벨 | Shell · §3 상충 칸 "확인됨" | 같음 | 있음 | `CC` 상충 그룹(채택·미채택)과 원문 발췌 하이라이트를 보여 준다 |
| 136 | [출처] 상충 항목 출처 종류 · 순위 | Shell · §3 "공고문 PDF · 1순위" / "청약홈 상세 · 2순위" | 같음 | 있음 | `CC` 상충 그룹(채택·미채택)과 원문 발췌 하이라이트를 보여 준다 |
| 137 | [출처] 상충 항목 발췌 (값 강조) | Shell · §3 따옴표 발췌 | 강조 표시 없음 | 있음(고침 SH-11) | `CC` 상충 그룹(채택·미채택)과 원문 발췌 하이라이트를 보여 준다 |
| 138 | [출처] 상충 항목 단위 근거 | — | — | 있음(고침 SH-11) | `SC` 출처 창: 응답 상태·판정 기록 번호 · 원문 앞뒤 보기 ↔ 원문 닫기 · 다른 출처의 단위 근거 |
| 139 | [출처] 상충 항목 원문 주소 링크 | — | — | 있음(고침 SH-11) | `SF` 본 출처·상충 후보 url 모두 글자만 |
| 140 | [출처] 이 출처 열기 `provenance.openConflict` (같은 창 안 이동) | Shell · §3 "이 출처 열기" | 같음 | 있음 | `R3F2` G1 숫자 셀 → 출처 서랍 GET /provenance/{id}?snapshot_id=12, 충돌 출처 열기도 같은 snapshot_id<br>`CC` 상충 그룹(채택·미채택)과 원문 발췌 하이라이트를 보여 준다 |
| 141 | [출처] 원문 파일 줄 (sr-only `provenance.rawDocument`) + RawDocumentPreview | Shell · §3 dt "원문 파일" | 숨김 제목 → 보이는 줄 이름 | 있음 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| 142 | [출처] 연 순간 리비전으로 고정 (화면 리비전 바뀌어도 안 따라감, 동작) | — | — | 문구로만(고침 SH-21) | `R3G` minor 17: 서랍을 연 채 리비전이 바뀌어도 서랍은 연 Fact 의 리비전(12)으로 남는다(404 없음) |
| 143 | [출처] API GET /provenance/{id}?snapshot_id= | Shell · §3 출처 창 | 호출 표시는 없음 | 있음 | `R3F2` G1 숫자 셀 → 출처 서랍 GET /provenance/{id}?snapshot_id=12, 충돌 출처 열기도 같은 snapshot_id |
| 144 | [원문] 미리보기 `provenance.rawPreview` (`components/RawDocumentPreview.tsx`, 열 때만 GET /raw/{id} Bearer) | Shell · §3 "원문 미리보기" | 같음 | 있음 | `RD` 열기 전에는 받지 않고, 텍스트는 화면 안에 보인다 |
| 145 | [원문] 미리보기 닫기 `provenance.rawPreviewHide` | Ops · ② 화면 캡처 미리보기 펼친 모습 "미리보기 닫기" · DetailTabs · 출처·원문 | 같음 | 다른 보드(Ops·DetailTabs) | `SC` 긴 원문 텍스트는 앞부분만 보이고 그렇다고 알린다 |
| 146 | [원문] 파일 저장 `provenance.rawSave` (`api/download` useDownload) | Shell · §3 "원문 파일 저장" | 같음 | 있음 | `RD` 저장 → fetch(Bearer) → 응답 파일 이름으로 저장 |
| 147 | [원문] 저장 중 `download.pending` "내려받는 중…" | Ops · ② 화면 캡처 미리보기 펼친 모습 | 같음 | 다른 보드(Ops) | `RD` 저장 → fetch(Bearer) → 응답 파일 이름으로 저장 |
| 148 | [원문] 저장 실패 `download.error` | Ops · ② 화면 캡처 미리보기 펼친 모습 | 같음 | 다른 보드(Ops) | `RD` 실패하면 오류 문구 |
| 149 | [원문] 불러오는 중 `provenance.rawLoading` | Ops · ② 화면 캡처 미리보기 펼친 모습 | 같음 | 다른 보드(Ops) | `RD` 열기 전에는 받지 않고, 텍스트는 화면 안에 보인다 |
| 150 | [원문] 실패 `provenance.rawError` | Ops · ② 화면 캡처 미리보기 펼친 모습 | 같음 | 다른 보드(Ops) | `RD` 실패하면 오류 문구 |
| 151 | [원문] 이미지 미리보기 + alt `provenance.rawImageAlt` | Ops · ② "[공식 홈페이지 화면 캡처 이미지]" · DetailTabs · 출처·원문 — 다른 상태 "그림 원문은 이미지로" | 같음 | 다른 보드(Ops·DetailTabs) | `RD` PNG 는 object URL 이미지로 |
| 152 | [원문] 텍스트 미리보기 `<pre>` | DetailTabs · 출처·원문 탭 (원문 칸) | 같음 | 다른 보드(DetailTabs) | `RD` 열기 전에는 받지 않고, 텍스트는 화면 안에 보인다 |
| 153 | [원문] 긴 원문 줄임 `provenance.rawTruncated` "앞 {n}자만 표시합니다" | DetailTabs · 출처·원문 — 다른 상태 "앞 200,000자만 보여요" | 같음 | 다른 보드(DetailTabs) | `SC` 긴 원문 텍스트는 앞부분만 보이고 그렇다고 알린다 |
| 154 | [원문] 미리보기 안 되는 형식 `provenance.rawPreviewUnsupported` | DetailTabs · 출처·원문 — 다른 상태 · Ops · ② | 같음 | 다른 보드(DetailTabs·Ops) | `RD` HTML 은 미리보기 대신 저장 안내 |
| 155 | [작업] 작업 진행 머리 `job.title` "작업 진행" (`components/JobProgress.tsx` JobProgressView, role=status aria-live) | Shell · §6 작업 진행 · 알림 카드 (role=status) · Ops · "작업 진행 · 다시 판정 · 실행 중" | Shell 카드는 머리 글자 대신 작업 이름 | 있음 | `SC` 작업 이름·단계는 쉬운 말(모르는 값은 원문), 서버 원문은 title |
| 156 | [작업] 작업 이름 (job_name 서버 값 그대로) | Shell · §6 "지역 처음 분석" | 영문 잡 이름 → 쉬운 이름 (새 번역 필요) | 있음 | `SC` 작업 이름·단계는 쉬운 말(모르는 값은 원문), 서버 원문은 title |
| 157 | [작업] 상태 `job.status.queued/running/done/failed` "대기/실행 중/완료/실패" | Shell · §6 "진행 중" + 문구 "대기 · 진행 중 · 완료 · 실패" | 실행 중 → 진행 중 | 있음 | `SC` 작업 이름·단계는 쉬운 말(모르는 값은 원문), 서버 원문은 title<br>`CT` JobProgressView: 상태 텍스트 |
| 158 | [작업] 진행 수 `job.progress` "{done}/{total}" | Shell · §6 "62 / 100" | 같음 | 있음 | `CC` JobProgressView: 계약 progress(done/total·step)를 보여 준다<br>`SC` 작업 이름·단계는 쉬운 말(모르는 값은 원문), 서버 원문은 title |
| 159 | [작업] 단계 `job.step` "단계 {step}" | Shell · §6 "단계: 공고문 읽기" | 같음 | 있음 | `CC` JobProgressView: 계약 progress(done/total·step)를 보여 준다<br>`SC` 작업 이름·단계는 쉬운 말(모르는 값은 원문), 서버 원문은 title |
| 160 | [작업] 진행 막대 (진행 수 있으면 결정 막대) | Shell · §6 파란 막대 | 같음 | 있음 | `CC` JobProgressView: 계약 progress(done/total·step)를 보여 준다 |
| 161 | [작업] 진행 수 없을 때 미정 막대 | — | — | 있음(고침 SH-16) | `SC` 진행 수가 없으면 끝을 모르는 줄무늬 막대(role=progressbar, 값 없음) |
| 162 | [작업] 작업 없음 `job.none` "진행 중인 작업 없음" | Market · 작업 진행 · 상태 모음 "없음" · Ops · ①③⑦ · RegionNew | 같음 | 다른 보드(Market·Ops·RegionNew) | `SC` 작업 없음 · 오류 문구 |
| 163 | [작업] 오류 `job.error` "오류: {detail}" | Market · 작업 진행 · 상태 모음 "실패 오류: [오류 내용]" · Ops · ①③⑦ | 같음 | 다른 보드(Market·Ops) | `SC` 작업 없음 · 오류 문구 |
| 164 | [작업] 상태 못 받음 `job.retrying` (마지막 상태 유지) | Ops · ①③⑦ · RegionNew · Reports | 같음 | 다른 보드(Ops·RegionNew·Reports) | `R3F` JobProgressView: 받아 둔 잡이 있으면 일시 오류 동안 마지막 상태 + 다시 확인 중 줄 |
| 165 | [작업] 발행 busy 재대기 `job.requeued` | Ops · ⑤ 작업 대기열 다른 상태 · Market · 상태 모음 "기다림" | 리비전 → 수정본 | 다른 보드(Ops·Market) | `R4F12` JobProgressView: 발행 busy 재큐잉 문구는 그대로(회귀) |
| 166 | [작업] 발행 예외 재시도 `job.requeuedError` "({n}/{max}회)" | Shell · §6 문구 "잠시 뒤 다시 시도(3/5)" · Ops · ⑤ | 문구 짧아짐 | 문구로만 | `R3I2` publishPhase: 재시도 queued = waiting, 5회 넘어 failed(재등록 없음) = 실패(코드 접두 없이) |
| 167 | [작업] 빈 데이터셋 재수집 `job.requeuedDegraded` + `requeuedAt`/`requeuedSoon` | Ops · ⑤ 작업 대기열 다른 상태 · RegionNew · Market | 같은 뜻 | 다른 보드(Ops·RegionNew·Market) | `R4F12` requeueInfo: degraded_source 재큐잉은 kind degraded(n·상한 6·다음 시도·사유) — busy 가 아니다 |
| 168 | [작업] 재수집 덧붙임 `job.requeuedDegradedBootstrap` / `requeuedDegradedDaily` | Ops · ⑤ "지역 첫 적재 중이라 발행본은 아직 없어요 / 이전 발행본이 그대로 기본 화면이에요" | 리비전 → 발행본 | 다른 보드(Ops) | `R4F12` JobProgressView(collect.daily): 이전 발행 리비전이 그대로 기본이라고 밝힌다 |
| 169 | [작업] 재수집 상한 실패 `job.degradedFailed` (degradedFailureText) | Ops · ⑤ "실패 … 발행하지 않았어요: [사유]" | 같음 | 다른 보드(Ops) | `R4F12` JobProgressView: 6회 넘어 failed(degraded_source) — 코드 접두 없이 멈춘 이유 |
| 170 | [작업] 2초 폴링 GET /jobs/{id}, done/failed에서 멈춤, onDone/onFailed 1회 (동작) | — | — | 문구로만(고침 SH-21) | `R3E` jobRefetchInterval: 4xx error → false, done·failed → false, 진행 중 → 간격 |
| 171 | [발행] 발행 기다림 `job.publishPending` (`PublishJobProgress`) | Shell · §6 문구 "결과 올리는 중" · Ops · 작업 진행 칸 "작업이 끝나 새 수정본이 발행될 때까지 …" | 리비전 → 수정본 | 문구로만 | `R3H` publishPhase: 기다림(리비전 목록이 published 를 보이면 발행됨) |
| 172 | [발행] 발행 완료 `job.publishDone` | Shell · §6 문구 "올렸어요" · Ops · ①③⑦ "새 수정본이 발행됐어요 …" | 같은 뜻 | 문구로만 | `R3H` publishPhase: 기다림(리비전 목록이 published 를 보이면 발행됨) |
| 173 | [발행] 막힘(사유) `job.publishBlocked` | Ops · ①③⑦ "발행이 막혔어요(남은 모순 주장 등) — …: [설명]" | 같음 | 다른 보드(Ops) | `R3H` 화면: 서버 사유(failed publish_blocked: …)는 코드 접두를 떼고 보인다 |
| 174 | [발행] 막힘(모순 주장 n건) `job.publishBlockedContradicted` | Shell · §6 문구 "막혔어요(모순 주장 2건)" · Ops · ①③⑦ · Market · 상태 모음 | 같음 | 문구로만 | `R3H` publishPhase: 막힘은 남은 모순 주장 수(숫자)로 — 영문 문구를 만들지 않는다 |
| 175 | [발행] 막힘(사유 모름) `job.publishBlockedUnknown` | Ops · ①③⑦ "이유 확인 불가" | 같음 | 다른 보드(Ops) | `R3H` 화면: 서버 사유(failed publish_blocked: …)는 코드 접두를 떼고 보인다 |
| 176 | [발행] 사슬 상한 `job.publishChainCapped` | Ops · ①③⑦ "[n]단계까지 따라갔지만 …" · Market | 같음 | 다른 보드(Ops·Market) | `R3H` 사슬은 ${PUBLISH_CHAIN_MAX}단계에서 멈추고 그렇다고 알린다(조용히 기다리지 않는다) |
| 177 | [발행] 발행 실패 `job.publishFailed` | Ops · ①③⑦ "발행 작업이 실패했어요 …" | 같음 | 다른 보드(Ops) | `R3I2` publishPhase: 재시도 queued = waiting, 5회 넘어 failed(재등록 없음) = 실패(코드 접두 없이) |
| 178 | [발행] 미룸 `job.publishDeferred` | Ops · ①③⑦ · Market · 상태 모음 "미뤄짐" | 같음 | 다른 보드(Ops·Market) | `R3H` publishPhase: 서버 모양 그대로의 미룸(done, published false, deferred_to)도 막힘이 아니다 |
| 179 | [발행] 다시 등록 `job.publishRedeferred` | Ops · ①③⑦ "미뤄 둔 수정본의 발행이 끝내 실패해 …" | 같음 | 다른 보드(Ops) | `R3I2` 화면: rejudge → 발행 잡 미룸(deferred) → 나중에 redeferred_job_id → 새 잡 done = 발행됨, 재등록 안내 |
| 180 | [발행] 30분 상한 `job.publishExpired` | Shell · §6 문구 "30분 넘게 걸려요" · Ops · ①③⑦ | 같음 | 문구로만 | `R3E` snapshotsRefetchInterval: 잡이 남으면 30분이 지나도 폴링, 잡이 없으면 멈춤, 못 읽었으면 한 번 더 |
| 181 | [발행] 사슬 따라가기(`publish_job_id`, 뒤 잡마다 진행 줄) + 1분마다 상한 다시 보기 (동작) | Ops · "①③⑦ 작업 진행 칸의 다른 문구 (발행까지 따라가는 진행)" | 여러 줄 모습은 안 그림 | 다른 보드(Ops, 문구로만) | `R3H` 사슬은 ${PUBLISH_CHAIN_MAX}단계에서 멈추고 그렇다고 알린다(조용히 기다리지 않는다)<br>`R3G` G6: 호재 위치 저장 뒤 리비전이 바뀌어 시장을 새로 받아도 저장 결과·발행 잡 진행은 남는다 |
| 182 | [틀] 화면 골격 h1 (`layout/PageShell.tsx` title) | Shell · h1 "모든 화면에 공통으로 쓰는 부품" (각 보드 h1) | 같음 | 있음 | `RT` %s %s → 제목을 렌더한다 |
| 183 | [틀] 제목 옆 도구 자리 (PageShell actions) | 각 화면 보드 (예: Main "접수 가능 단지 모두 보기") | 같음 | 다른 보드(각 화면) | `RT` %s %s → 제목을 렌더한다 |
| 184 | [틀] 제목 아래 한 줄 안내 (PageShell intro) | Shell · h1 아래 p | 같음 | 있음 | `GR` 머리: 질문형 h1 + 개수 안내 + 검색칸 자리 글 |
| 185 | [범례] 출처 범례 한 줄 `label.legend` "밑줄 친 숫자를 누르면 출처·확인일이 열립니다" (`components/ProvenanceLegend.tsx`) | Shell · §3 "밑줄 점선이 있는 숫자는 모두 누를 수 있어요" | 같은 뜻 | 있음 | `CC` 출처 범례: 한 줄 안내 + 라벨 뜻(펼침) 6가지<br>`SC` 여섯 줄 = 라벨 이름(배지 모양) + label.help 한 문장, Esc 로 접힘 |
| 186 | [범례] 라벨 뜻 펼침 `label.legendHelp` "라벨 뜻 ⓘ" (aria-expanded) | Shell · §3 "라벨 뜻 [접기]" (aria-expanded=true) | ⓘ → 접기 버튼 | 있음 | `CC` 출처 범례: 한 줄 안내 + 라벨 뜻(펼침) 6가지<br>`SC` 여섯 줄 = 라벨 이름(배지 모양) + label.help 한 문장, Esc 로 접힘 |
| 187 | [범례] Esc로 접기 | — | — | 문구로만(고침 SH-21) | `SC` 여섯 줄 = 라벨 이름(배지 모양) + label.help 한 문장, Esc 로 접힘 |
| 188 | [범례] `label.help.confirmed` "확인됨 — 공식 자료(공고문·청약홈 등)에서 확인한 값" | Shell · §3 라벨 뜻 목록 "확인됨 공식 자료(공고문·청약홈·국토부)에 적힌 그대로예요." | 같은 뜻 · 고침 후: label.help.* 원문을 쉬운 말로 한 번 정한 문장(Glossary 라벨 카드와 같음) | 있음(고침 SH-1) | `GR` 라벨 카드 6장 = 출처 범례 라벨 뜻(label.help) 한 원본(GL-1·SH-1)<br>`SC` 여섯 줄 = 라벨 이름(배지 모양) + label.help 한 문장, Esc 로 접힘 |
| 189 | [범례] `label.help.estimated` "추정 — 계산이나 가정으로 만든 값(괄호 안이 계산 방법)" | Shell · §3 "추정 공식 값으로 계산했거나 판정기가 낸 값이에요." | "괄호 안이 계산 방법" 빠짐 · 고침 후: label.help.* 원문을 쉬운 말로 한 번 정한 문장(Glossary 라벨 카드와 같음) | 있음(고침 SH-1) | `GR` 라벨 카드 6장 = 출처 범례 라벨 뜻(label.help) 한 원본(GL-1·SH-1) |
| 190 | [범례] `label.help.unofficial` | Shell · §3 "비공식 언론·분양 광고 등 …" | 보도·블로그·홍보 → 언론·분양 광고 · 고침 후: label.help.* 원문을 쉬운 말로 한 번 정한 문장(Glossary 라벨 카드와 같음) | 있음(고침 SH-1) | `GR` 라벨 카드 6장 = 출처 범례 라벨 뜻(label.help) 한 원본(GL-1·SH-1) |
| 191 | [범례] `label.help.reprocessed` | Shell · §3 "재가공 다른 서비스가 가공한 값을 옮긴 거예요." | 같은 뜻 · 고침 후: label.help.* 원문을 쉬운 말로 한 번 정한 문장(Glossary 라벨 카드와 같음) | 있음(고침 SH-1) | `GR` 라벨 카드 6장 = 출처 범례 라벨 뜻(label.help) 한 원본(GL-1·SH-1) |
| 192 | [범례] `label.help.unknown` "확인 불가 — 찾지 못한 값(괄호 안이 이유)" | Shell · §3 "확인 불가(사유, 날짜) 값을 못 구했어요. 이유를 함께 적어요." | 같은 뜻 · 고침 후: label.help.* 원문을 쉬운 말로 한 번 정한 문장(Glossary 라벨 카드와 같음) | 있음(고침 SH-1) | `GR` 라벨 카드 6장 = 출처 범례 라벨 뜻(label.help) 한 원본(GL-1·SH-1) |
| 193 | [범례] `label.help.human` "사람 확인됨 — 사람이 전화·방문으로 확인한 값" | Shell · §3 "사람 확인 운영자가 전화·방문으로 직접 확인한 값이에요." | 사람 확인됨 → 사람 확인 · 고침 후: label.help.* 원문을 쉬운 말로 한 번 정한 문장(Glossary 라벨 카드와 같음) | 있음(고침 SH-1) | `GR` 라벨 카드 6장 = 출처 범례 라벨 뜻(label.help) 한 원본(GL-1·SH-1) |
| 194 | [라벨] 확인됨 = 작은 회색 글자 (`components/LabelBadge.tsx` data-tone=quiet, `label.confirmed`) | Shell · §3 "확인됨" (작은 초록 글자) | 회색 → 초록 | 있음 | `SC` LabelBadge: '확인됨'은 조용한 글자, 나머지·사람 확인됨은 점선 배지(D28-2) |
| 195 | [라벨] 추정 테두리 배지 `label.estimated` | Shell · §3 점선 배지 "추정" | 같음 | 있음 | `SC` LabelBadge: '확인됨'은 조용한 글자, 나머지·사람 확인됨은 점선 배지(D28-2) |
| 196 | [라벨] 비공식 `label.unofficial` | Shell · §3 "비공식" 배지 | 같음 | 있음 | `SC` LabelBadge: '확인됨'은 조용한 글자, 나머지·사람 확인됨은 점선 배지(D28-2) |
| 197 | [라벨] 재가공 `label.reprocessed` | Shell · §3 "재가공" 배지 | 같음 | 있음 | `SC` LabelBadge: '확인됨'은 조용한 글자, 나머지·사람 확인됨은 점선 배지(D28-2) |
| 198 | [라벨] 확인 불가(사유, 확인일) `empty.unknownWithReasonDate` / `empty.unknownWithReason` / `empty.unknown` | Shell · §3 "확인 불가(사유, 날짜)" 배지 | 같음 | 있음 | `CC` 확인 불가 → "확인 불가(사유, 확인일)"<br>`SC` LabelBadge: '확인됨'은 조용한 글자, 나머지·사람 확인됨은 점선 배지(D28-2) |
| 199 | [라벨] 사람 접두 `label.humanPrefix` "사람 {label}" → "사람 확인됨" | Shell · §3 "사람 확인" 배지 | 사람 확인됨 → 사람 확인 · 고침 후: '사람 확인됨' | 있음(고침 SH-1) | `CC` human=true → "사람 확인됨"<br>`SC` LabelBadge: '확인됨'은 조용한 글자, 나머지·사람 확인됨은 점선 배지(D28-2) |
| 200 | [라벨] 한정어 `label.withReason` "{label}({reason})" 예: 추정(대체·보정 c=0.015) | Compare · 위 화면에서 접혀 있거나 가끔만 나오는 모습 "추정(대체·보정 [계수])" | 같음 | 다른 보드(Compare) | `CC` 다른 라벨의 한정어 → "<라벨>(<사유>)" |
| 201 | [라벨] 사유 40자 넘으면 줄임 `label.truncated` "{text}…(전체는 숫자를 눌러 보기)" + title 전문 | — | — | 있음(고침 SH-12) | `CC` 사유가 40자를 넘으면 화면은 줄여 보이고 title 에 전문을 둔다(라벨 글자는 그대로) |
| 202 | [라벨] 쉬운 말 사유 + 원 사유 title `empty.reasonOriginal` "원래 사유: {reason}" | — | — | 있음(고침 SH-12) | `CC` 코드로 쉬운 말을 보이고 원 사유는 같은 요소 title<br>`SC` EmptyState: 문장 속 '확인 불가(사유)'는 점선 배지(SH-12), 블록은 role=status 상자 |
| 203 | [라벨] 좁은 칸 줄바꿈 wrap (동작) | — | — | 문구로만(고침 SH-21) | `SC` 좁은 칸(wrap)에서는 라벨이 다음 줄로 내려간다(whitespace-normal) |
| 204 | [빈 값] EmptyState 블록 (점선 상자, role=status) (`components/EmptyState.tsx`) | Shell · §7 카드들 | 상자 모양 | 있음 | `SC` EmptyState: 문장 속 '확인 불가(사유)'는 점선 배지(SH-12), 블록은 role=status 상자<br>`CT` EmptyState: 확인 불가(사유) |
| 205 | [빈 값] 표 데이터 없음 `empty.noData` "데이터 없음" | Shell · §8 "값이 없으면 '자료가 없어요(이유)'" | 데이터 없음 → 자료가 없어요 | 있음(고침 SH-18) | `SC` 표 이름(caption)을 보이고, 줄이 없으면 머리 + "데이터 없음" 한 줄 |
| 206 | [사유] `empty.reasonPlain.fetch_failed` "공식 페이지를 받지 못함" (+ `fetch_failedWith`) | List · 카드 목록 아래 "공식 홈페이지가 열리지 않거나 …" | 같은 뜻 | 다른 보드(List, 문구로만) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title)<br>`FMT` 수집 실패(fetch_failed)는 짧은 기술 사유를 함께 |
| 207 | [사유] `empty.reasonPlain.not_collected` "아직 수집하지 않음" | — | — | 있음(고침 SH-12) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 208 | [사유] `empty.reasonPlain.pre_notice` "아직 공고 전(분양가 미공고)" | DetailTabs · 이름·상태 줄에 더할 것 "'공고 전'으로 보여요" | 같은 뜻 | 다른 보드(DetailTabs) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 209 | [사유] `empty.reasonPlain.parse_failed` "공고문에서 자동으로 읽지 못함 — 원문에서 확인" | List · 카드 목록 아래 "공고를 아직 못 읽은 단지" | 같은 뜻 | 다른 보드(List, 문구로만) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 210 | [사유] `empty.reasonPlain.source_missing` "출처 자료가 없음" | — | — | 있음(고침 SH-12) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 211 | [사유] `empty.reasonPlain.demoted` "검증에서 모순이 나와 쓰지 않음" | Shell · §3 아래 안내 "검증에서 모순이 나온 값은 …" | 같은 뜻 | 문구로만 | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 212 | [사유] `empty.reasonPlain.conflict_hold` "출처끼리 값이 달라 확인 중" | DetailTabs · 돈 카드에 더할 것 "확인 불가(자료끼리 값이 달라 확인 중)" | 출처끼리 → 자료끼리 | 다른 보드(DetailTabs) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 213 | [사유] `empty.reasonPlain.partial_missing` "일부 값이 빠짐" | — | — | 있음(고침 SH-12) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 214 | [사유] `empty.reasonPlain.identity_unconfirmed` | ListTable · 표 단지 줄 "공식 홈페이지가 이 단지 것인지 확인 전" · DetailTabs · 이름·상태 줄에 더할 것 | 같음 | 다른 보드(ListTable·DetailTabs) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 215 | [사유] `empty.reasonPlain.other_complex_site` | DetailTabs · 이름·상태 줄에 더할 것 "다른 단지의 페이지" | 같은 뜻 | 다른 보드(DetailTabs) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 216 | [사유] `empty.reasonPlain.no_phrase` "접수 문구를 찾지 못함" | Ops · 접수 상태를 사람이 확인해야 하는 단지 "접수 문구 없음" | 같은 뜻 | 다른 보드(Ops) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 217 | [사유] `empty.reasonPlain.phrase_inconclusive` "문구로는 판단할 수 없음" | Ops · 접수 상태를 사람이 확인해야 하는 단지 "문구로 판단 불가" | 같은 뜻 | 다른 보드(Ops) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 218 | [사유] `empty.reasonPlain.not_target` "점수 계산 대상 아님" | ListTable · 표 단지 줄 "점수 계산 대상 아님(공공분양)" | 같음 | 다른 보드(ListTable) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 219 | [사유] `empty.reasonPlain.input_blocked` "입력이 막혀 판정하지 않음" | — | — | 있음(고침 SH-12) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 220 | [사유] `empty.reasonPlain.unresolved` "자동 확인이 끝나지 않음" | ListTable · 표 단지 줄 | 같음 | 다른 보드(ListTable) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 221 | [사유] `empty.reasonPlain.unjudged` "점수 계산 전" | ListTable · 표 단지 줄 | 같음 | 다른 보드(ListTable) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 222 | [사유] `empty.reasonPlain.not_entered` "내 조건(시나리오)에 입력하지 않음" | — | (Scenario의 요건 칸 "미입력"은 다른 표시) | 있음(고침 SH-12) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 223 | [사유] `empty.reasonPlain.no_sample` "비교할 거래가 없음" | Compare · 위 화면에서 접혀 있거나 가끔만 나오는 모습 "비교할 거래가 없어요([사유])" | 같은 뜻 | 다른 보드(Compare) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 224 | [사유] `empty.reasonPlain.human_check` "사람 확인 기다림" | — | (Ops "다시 판정·발행 기다리는 중"은 다른 뜻) | 있음(고침 SH-12) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 225 | [사유] `empty.reasonPlain.no_value` "공고에 값이 없음" | ListTable · 표 단지 줄 | 같음 | 다른 보드(ListTable) | `SC` 값이 빈 사유 코드는 쉬운 말 배지(no_value 는 서버 사유 그대로, 원 사유는 title) |
| 226 | [접수 배지] 접수 가능 = 강조 (`components/IntakeBadge.tsx` · `intake.status.가능` "접수 가능") | Shell · §4 상태 표시(배지) 모음 "접수 가능" (파란 바탕) | 같음 | 있음 | `SC` IntakeBadge 알약(목업 §4): 가능 = 주색+점, 미정 = 테두리, 확인 불가 = 회색, 불가 = 상태 글자 취소선<br>`CT` IntakeBadge: 상태 · 경로, 없으면 확인 불가 |
| 227 | [접수 배지] `intake.status.미정` "접수 미정" (회색) | Shell · §4 "접수 일정 미정" | 접수 미정 → 접수 일정 미정 | 있음 | `SC` IntakeBadge 알약(목업 §4): 가능 = 주색+점, 미정 = 테두리, 확인 불가 = 회색, 불가 = 상태 글자 취소선<br>`SH` 메뉴·용어 사전·접수 미정·공식 홈페이지 안내문 이름 |
| 228 | [접수 배지] `intake.status.확인 불가` "접수 확인 불가" (회색) | Shell · §4 "확인 못 함" | 확인 불가 → 확인 못 함 | 있음 | `SC` IntakeBadge 알약(목업 §4): 가능 = 주색+점, 미정 = 테두리, 확인 불가 = 회색, 불가 = 상태 글자 취소선 |
| 229 | [접수 배지] `intake.status.불가` "접수 불가" (보통) | Shell · §4 "접수 불가" (취소선) | 같음 | 있음 | `SC` IntakeBadge 알약(목업 §4): 가능 = 주색+점, 미정 = 테두리, 확인 불가 = 회색, 불가 = 상태 글자 취소선 |
| 230 | [접수 배지] 접수 정보 없음 `intake.none` "접수 상태 확인 불가" | ListTable · 필터 "접수 상태 확인 못 함" · Shell · §4 "확인 못 함" | 확인 불가 → 확인 못 함 | 있음 | `CT` IntakeBadge: 상태 · 경로, 없으면 확인 불가 |
| 231 | [접수 배지] 경로 `intake.path.human_check` "사람 확인" | Shell · §4 "어떻게 확인했나: 사람 확인" | 같음 | 있음 | `CC` IntakeBadge: 확인 불가 → 사유·확인일, human_check → "사람" 접두 |
| 232 | [접수 배지] 경로 `intake.path.official_popup` "공식 팝업" | Shell · §4 "공식 팝업" | 같음 | 있음 | `CT` IntakeBadge: 상태 · 경로, 없으면 확인 불가 |
| 233 | [접수 배지] 경로 `intake.path.headless_shot` "렌더 캡처" | Shell · §4 "홈페이지 화면 캡처" | 렌더 캡처 → 홈페이지 화면 캡처 | 있음 | `SC` IntakeBadge 알약(목업 §4): 가능 = 주색+점, 미정 = 테두리, 확인 불가 = 회색, 불가 = 상태 글자 취소선 |
| 234 | [접수 배지] 경로 `intake.path.unofficial_ref` "비공식 참고" | Shell · §4 "비공식 참고" | 같음 | 있음 | `CT` IntakeBadge: 상태 · 경로, 없으면 확인 불가 |
| 235 | [접수 배지] 공급 종류 `intake.withSupply` "{status}({kind})" | Shell · §4 "공급 종류(무순위 등)" · Main · 접수 가능 카드 "무순위 · 선착순 계약" | 괄호 → 옆 칩 | 있음 | `CC` 공급 종류(.20 supply_kind)가 있으면 접수 배지에 함께, 근거 문구는 title |
| 236 | [접수 배지] 사유·날짜 `intake.withReason`/`withReasonDate` | ListTable · 표 단지 줄 "자동 확인이 끝나지 않음 · 10.14" | 같은 뜻 | 다른 보드(ListTable) | `CC` IntakeBadge: 확인 불가 → 사유·확인일, human_check → "사람" 접두 |
| 237 | [접수 배지] 사유를 배지 밑 작은 글씨로 (reasonBelow · `intake.reasonDate` "{reason} · {date}") | ListTable · 표 접수 칸 | 같음 | 다른 보드(ListTable) | `CX` 접수 칸: 상태 배지 + 아래 작은 사유(쉬운 말, 원 사유 title) |
| 238 | [접수 배지] title = 확인 시각 D± · 원 사유 · 공급 종류 근거(supply_kind_basis) | Shell · §4 "확인한 날" (문구) | 공급 종류 근거는 없음 | 문구로만 | `CC` 공급 종류(.20 supply_kind)가 있으면 접수 배지에 함께, 근거 문구는 title |
| 239 | [점수 배지] 동률 `badge.tie` (`components/TieBadge.tsx`) | Shell · §4 "동률" | 같음 | 있음 | `SC` 점수 배지 톤: 동률·재사용 = 회색 점선, 흔들림·근거와 달라요 = 주의 점선(글자 그대로)<br>`CT` Cached/Tie/Mismatch/Unstable: 참일 때만 렌더 |
| 240 | [점수 배지] 동률(신뢰도) `badge.tieWithConfidence` | Shell · §4 "동률(믿음 정도 0.62)" | 신뢰도 → 믿음 정도 | 있음 | `SC` 점수 배지 톤: 동률·재사용 = 회색 점선, 흔들림·근거와 달라요 = 주의 점선(글자 그대로) |
| 241 | [점수 배지] 순위 불안정 `badge.unstable` (`UnstableBadge`) | Shell · §4 "순위가 흔들려요" | 순위 불안정 → 순위가 흔들려요 | 있음 | `SC` 점수 배지 톤: 동률·재사용 = 회색 점선, 흔들림·근거와 달라요 = 주의 점선(글자 그대로) |
| 242 | [점수 배지] 증거와 상이 `badge.mismatch` (`MismatchBadge`) | Shell · §4 "근거와 달라요" | 증거와 상이 → 근거와 달라요 | 있음 | `SC` 점수 배지 톤: 동률·재사용 = 회색 점선, 흔들림·근거와 달라요 = 주의 점선(글자 그대로) |
| 243 | [점수 배지] 캐시 `badge.cached` (`CachedBadge`) | Shell · §4 "이전 결과 재사용" | 캐시 → 이전 결과 재사용 | 있음 | `SC` 점수 배지 톤: 동률·재사용 = 회색 점선, 흔들림·근거와 달라요 = 주의 점선(글자 그대로) |
| 244 | [범위 배지] 판정 대상(표·카드에선 숨김) (`pages/_shared` JudgeScopeBadge · `page.common.judgeScope.판정 대상`) | Shell · §4 점수 계산 범위 "점수 대상(보통 표시 안 함)" | 판정 대상 → 점수 대상 | 있음 | `JS` G2 표: 판정 대상이 아닌 행에 범위 배지(미해결·참고·보류 표시 문구) |
| 245 | [범위 배지] `page.common.judgeScope.보류` "보류 — 공고 후 재판정" | Shell · §4 "보류 — 공고 뒤 다시 판정" | 같은 뜻 | 있음 | `JS` ko.json 표시 문구: 보류·참고·미해결 |
| 246 | [범위 배지] `page.common.judgeScope.참고` "참고 후보(순위만)" | Shell · §4 "참고 후보(순위만)" | 같음 | 있음 | `JS` ko.json 표시 문구: 보류·참고·미해결 |
| 247 | [범위 배지] `page.common.judgeScope.미해결` "미해결(분류 판정 미해결)" | Shell · §4 "분류 미해결" | 짧아짐 | 있음 | `JS` ko.json 표시 문구: 보류·참고·미해결 |
| 248 | [범위 배지] `page.common.judgeScope.제외` "제외" | Shell · §4 "제외" | 같음 | 있음 | `JS` G2 표: 판정 대상이 아닌 행에 범위 배지(미해결·참고·보류 표시 문구) |
| 249 | [범위 배지] 재판정 필요 `page.common.rejudgeNeeded` (RejudgeNeededBadge) | Shell · §4 "다시 판정 필요" | 재판정 필요 → 다시 판정 필요 | 있음 | `RN` G2 표: rejudge_needed 행에만 배지(가상 스크롤 행 그대로) |
| 250 | [범위 배지] 재판정 필요 title `page.common.rejudgeNeededHint` | Compare · 위 화면에서 접혀 있거나 가끔만 나오는 모습 "범위가 저장값과 달라 다시 판정해야 해요" | 같은 뜻 | 다른 보드(Compare) | `RN` G3 헤더: 점수 행 rejudge_needed → 배지 |
| 251 | [범위 사유] ScopeReason 사유 한 줄 + `page.common.scopeReasonCurrent` | Shell · §4 "이유 한 줄이 옆에 붙어요 … (지금 사실 기준 — 다시 판정한 뒤 바뀔 수 있음)" | 같은 뜻 | 있음 | `R4F11` G3 머리: rejudge_needed 면 사유가 현재 사실(재판정 뒤) 범위의 것임을 밝힌다 |
| 252 | [범위 사유] title 머리 `page.common.scopeReason` "판정 범위 사유" | Ops · 지역 경계에 걸친 단지가 있나요? (⑧ 범위 경계 다른 상태) "판정 범위 이유: [이유]" | 사유 → 이유 | 다른 보드(Ops) | `R4F11` G2 목록 행: rejudge_needed 행의 사유에는 현재 사실 기준 안내(title) |
| 253 | [이름 출처] 이름 옆 라벨 배지/이름 버튼 (NameLabelBadge·NameWithProvenance · `page.common.nameProv.open`/`openNoLabel`) | DetailTabs · 이름·상태 줄에 더할 것 · ListTable · 표 "이름 출처" | 같음 | 다른 보드(DetailTabs·ListTable) | `R4F10` G3 머리: 이름 클릭 → 출처 서랍(GET /provenance/fp_8801), 이름 옆 … |
| 254 | [배지] 의미는 색이 아니라 글자 (`components/Badge.tsx` tone neutral/muted/strong) | Shell · §4 (모든 배지에 글자) | 색이 더 많이 쓰임 — 글자는 유지 | 있음 | `SC` Badge: 의미는 글자(톤 7종 모두 글자를 그린다) |
| 255 | [숫자] FactCell 포맷(억·만·%·㎡·D±) + 값 없으면 "확인 불가(사유, 확인일)" | Shell · §3 예 "계약금 3,124만원 추정" | 같음 | 있음 | `FC` 포맷한 값과 라벨 배지(텍스트)를 함께 렌더한다 |
| 256 | [숫자] 사실 아닌 숫자 표시 `data-meta` (MetaValue/MetaText, 동작·테스트 속성) | — | — | 문구로만(고침 SH-21) | `R3C` data-meta 로 종류를 남기고 lib/format 과 같은 문자열 |
| 257 | [링크] 외부 링크 안전 검사 safeHref, 위험 URL은 글자만 (`components/ExternalLink.tsx`) | Shell · §3 "원문 주소" 링크 (검사는 표시 없음) | — | 문구로만(고침 SH-21) | `SF` javascript:·data: → 링크 없이 글자만 |
| 258 | [용어] ⓘ 버튼 + aria-label `glossary.open` "{term} 뜻 보기" (`components/Term.tsx`) | Shell · §3 "용어 '?' 를 눌렀을 때" | ⓘ → ? | 있음 | `SC` 동그란 '?' 버튼 · 팝오버에 이름·뜻·'용어 사전에서 보기'(쿼리 유지)<br>`GL` 버튼 aria-expanded·aria-controls, 팝오버에 한 줄 정의와 용어 모음 링크, Esc 로 닫힘 |
| 259 | [용어] 팝오버: 용어 이름 + 한 줄 정의 (`glossary.items.*`) | Shell · §3 팝오버 "전매 …" | 같음 | 있음 | `SC` 동그란 '?' 버튼 · 팝오버에 이름·뜻·'용어 사전에서 보기'(쿼리 유지) |
| 260 | [용어] `glossary.more` "용어 모음에서 보기" → /glossary#key (지역·기준일·상황 쿼리 유지) | Shell · §3 "용어 사전에서 보기" | 용어 모음 → 용어 사전 (쿼리 유지는 표시 없음) | 있음 | `SC` 동그란 '?' 버튼 · 팝오버에 이름·뜻·'용어 사전에서 보기'(쿼리 유지) |
| 261 | [용어] Esc·바깥 누르면 닫힘 | Shell · §3 "Esc나 바깥을 누르면 닫혀요" | 같음 | 문구로만 | `GL` 버튼 aria-expanded·aria-controls, 팝오버에 한 줄 정의와 용어 모음 링크, Esc 로 닫힘 |
| 262 | [용어] 모바일 아래 시트 | Shell · §3 "휴대폰에서는 아래에서 올라오는 판으로" | 같음 | 있음(고침 SH-19) | `SC` 휴대폰은 아래에서 올라오는 판 + 뒤 어둡게 + 닫기(SH-19) |
| 263 | [용어] 모바일 시트 닫기 `glossary.close` "닫기" | — | — | 있음(고침 SH-19) | `SC` 휴대폰은 아래에서 올라오는 판 + 뒤 어둡게 + 닫기(SH-19) |
| 264 | [용어] 라우터 밖이면 링크 없음 (동작) | — | — | 문구로만(고침 SH-21) | `SC` 라우터 밖(차트 갤러리 등)에서는 '용어 사전에서 보기' 링크가 없다(#264) |
| 265 | [상태] QueryState 로딩 `app.loading` (`pages/_shared/index.tsx`, role=status) | Shell · §7 첫 카드 "불러오는 중…" (뼈대 줄 3개) | 뼈대 줄 새로 | 있음 | `SC` 불러오는 중 = 뼈대 + "불러오는 중…" |
| 266 | [상태] 일반 오류 `page.common.loadError` "불러오지 못했습니다: {detail}" (EmptyState) | Shell · §7 "불러오지 못했어요 / 잠시 뒤 다시 해 주세요 / [다시 시도]" | 일반 오류에 다시 시도 버튼이 새로 생김 (현재는 준비 중일 때만) | 있음 | `SC` 일반 오류 = "불러오지 못했어요: 내용" + 잠시 뒤 + 다시 시도(N10) |
| 267 | [상태] 준비 중 `page.common.materializePending` (503 재시도 중) | Shell · §7 "이 기준일 결과를 만드는 중이에요 / 자동으로 다시 불러와요" | 같은 뜻 | 있음 | `SC` 만드는 중(503) = 상태 카드 + 다시 시도<br>`R3F2` G1 대시보드: 503 동안 … |
| 268 | [상태] 아직 준비 중 `page.common.materializePendingStill` + 다시 시도 `app.retry` | Shell · §7 "오래 걸리면 다시 시도를 눌러 주세요" | 같은 뜻 | 문구로만 | `SC` 만드는 중(503) = 상태 카드 + 다시 시도<br>`R3G` minor 18: G2 목록 결과가 재시도 중 실패 사유와 다시 시도(refetch)를 넘긴다 |
| 269 | [상태] 발행 뒤 만든 시나리오 결과 없음 `page.common.scenarioMissing` | Shell · §7 "이 상황의 결과가 아직 없어요" | 시나리오 #n → 이 상황 | 있음 | `R3E` G1 ?scenario=9(발행 뒤 생성) → 404 → 안내 + 시나리오 실행 링크(전역 쿼리 유지) |
| 270 | [상태] 시나리오 실행 링크 `page.common.scenarioMissingRun` "시나리오 실행 화면으로" | Shell · §7 "내 조건 화면에서 실행하기" | 같은 뜻 | 있음 | `R3E` G1 ?scenario=9(발행 뒤 생성) → 404 → 안내 + 시나리오 실행 링크(전역 쿼리 유지) |
| 271 | [상태] 이전 값 보이는 동안 새 조건 준비 중 (isPlaceholderData + 준비 중, M7) | Shell · §7 "보던 기준일과 저장된 화면이 다를 때도 안내가 떠요" | 뜻이 같은지 불분명 | 문구로만(고침 SH-21) | `R3G` G2: 같은 리비전·시나리오에서 필터만 바꾸면 이전 행을 잠깐 둔다(placeholder 유지) |
| 272 | [상태] 데이터 빈 경우 문구 (QueryState empty) | 각 화면 보드 빈 상태 | 화면마다 | 다른 보드(각 화면) | `SC` QueryState 빈 데이터 = 호출 측 문구 상자, Section = 카드 + h2 + 한 줄 안내 |
| 273 | [상태] 기준일 없음 `app.noSnapshot` (NoSnapshot) | Shell · §7 "아직 기준일이 없어요" | 같은 뜻 | 있음 | `SH` 발행 기준일이 없으면 "아직 기준일이 없어요" |
| 274 | [상태] 지역 첫 적재 중 `app.noSnapshotBootstrapping` | Shell · §7 "지역을 처음 분석 중이면 끝날 때까지 기다려 주세요." | 같은 뜻 | 있음 | `R4F12` 지역 status bootstrapping(발행 리비전 없음) → 화면 … |
| 275 | [상태] 카드 구역 Section (h2 + 본문) | 각 화면 보드 카드 | 같음 | 다른 보드(각 화면) | `SC` QueryState 빈 데이터 = 호출 측 문구 상자, Section = 카드 + h2 + 한 줄 안내 |
| 276 | [차트 틀] 제목 h3 (`charts/ChartFrame.tsx` figure/figcaption) | Shell · §8 모든 차트의 틀 "차트 제목 (무엇을 · 언제부터 언제까지)" | 같음 | 있음 | `CG` 정상 상태 카드는 라벨 배지(텍스트)를 단다<br>`E2G` ${id} ${state} |
| 277 | [차트 틀] 데이터 라벨 배지(중복 제거) | Shell · §8 "추정" | 같음 | 있음 | `CG` 정상 상태 카드는 라벨 배지(텍스트)를 단다 |
| 278 | [차트 틀] 추가 배지 자리(불안정·동률 등) | Compare · 점수 비교 줄 "동률·순위가 흔들려요·근거와 달라요·다시 판정 필요 배지는 서버가 준 값 그대로" | 같음 | 다른 보드(Compare) | `CG` 특수 상태 배지: 미해결·표본·미판정·동률·질문·순위 불안정 |
| 279 | [차트 틀] 부제 | Shell · §8 "한 줄 부제" | 같음 | 있음 | `E2G` ${id} ${state} |
| 280 | [차트 틀] 빈 상태 emptyReason → EmptyState | Shell · §8 "값이 없으면 '자료가 없어요(이유)'" | 같은 뜻 | 있음(고침 SH-18) | `CG` 빈 상태 카드는 차트 대신 빈 상태 문구를 보여 준다 |
| 281 | [차트 틀] 표로 보기 `table.show` (`components/DataTableToggle.tsx`, aria-expanded) | Shell · §8 "표로 보기" | 같음 | 있음 | `CT` "표로 보기"로 열면 Fact·숫자·빈 값을 포맷해 보여 준다<br>`CG` 표로 보기 → Fact 셀 클릭이 출처 패널로 이어진다 |
| 282 | [차트 틀] 표 닫기 `table.hide` | DetailTabs · 표로 보기 — 가격 전망 사다리 "버튼 글자는 '표 닫기'로 바뀌어요" | 같음 | 다른 보드(DetailTabs) | `SC` 표 이름(caption)을 보이고, 줄이 없으면 머리 + "데이터 없음" 한 줄 |
| 283 | [차트 틀] 표 caption (sr-only `table.caption` "{title} 데이터") | — | — | 있음(고침 SH-18) | `SC` 표 이름(caption)을 보이고, 줄이 없으면 머리 + "데이터 없음" 한 줄 |
| 284 | [차트 틀] 표 빈 행 `empty.noData` | — | — | 있음(고침 SH-18) | `SC` 표 이름(caption)을 보이고, 줄이 없으면 머리 + "데이터 없음" 한 줄 |
| 285 | [차트 틀] 표 칸: Fact → FactCell(출처 열기) · 숫자 → 파생값 · 글자 · 빈 값 "확인 불가" | — | 펼친 표 모습은 Shell에 없음 (화면별 표 열은 각 화면 대응표) | 있음(고침 SH-18) | `CT` "표로 보기"로 열면 Fact·숫자·빈 값을 포맷해 보여 준다 |
| 286 | [차트] 화면에 들어올 때 불러오기 + 자리표시 `chart.notRendered` "차트 준비 중" (`charts/EChart.tsx`) | Shell · §8 "차트 자리" (점선 상자) | 문구 "차트 준비 중" 없음 | 있음(고침 SH-18) | `LZ` 화면 밖: 플레이스홀더만 있고 SVG·echarts 런타임이 없다 → 진입하면 그린다 |
| 287 | [차트] 차트 role=img + aria-label(제목) | Main · 미분양 카드 svg role=img aria-label | 같음 | 다른 보드(Main) | `E2G` ${id} ${state} |
| 288 | [차트] SVG 그리기·다크 색판 (`charts/palette.ts`, 동작) | — | — | 있음(고침 SH-20) | `E2G` ${id} normal (다크)<br>`TK` %s: 글자색 토큰은 자기 바탕 위에서 4.5:1 이상 |
| 289 | [404] 없는 주소 h1 `page.notFound.title` "페이지를 찾을 수 없습니다" (`pages/not-found/index.tsx`) | Shell · §9 "찾는 화면이 없어요" | 바뀜 | 있음 | `SH` "찾는 화면이 없어요" + 홈으로(쿼리 유지)<br>`RT` 없는 경로는 404 제목 |
| 290 | [404] 모바일 읽기 전용 정책 handle | Shell · §2 휴대폰 칩 (화면 목록에 404 없음) | — | 있음(고침 SH-9) | `SH` 휴대폰 칩 문구(SH-9): 보기만 / 컴퓨터에서 — 없는 주소도 보기만 |
| 291 | [/__charts] 개발 전용 차트 갤러리 (`app/ChartGalleryPage.tsx` · `chart.gallery.title` "차트 갤러리", `chart.gallery.note`, 상태 `chart.gallery.state.*`) | Coverage · 그림으로 그리지 않은 것 "차트 갤러리(/__charts)" | — | 문구로만(고침 SH-21) | `SH` 머리줄 안에서 갤러리 제목을 그린다(목업에 그리지 않음 — 지금 그대로) |
| 292 | [/__charts] 갤러리 불러오는 동안 `app.loading` | — | — | 문구로만(고침 SH-21) | `SH` 머리줄 안에서 갤러리 제목을 그린다(목업에 그리지 않음 — 지금 그대로) |
| 293 | [API] GET /health (판정기 상태 띠) | Shell · §2 첫 띠 | 호출 표시 없음 | 있음 | `SH` 판정기 장애(/health degraded) → role=alert 주의 띠 + 경고 아이콘(SH-2) |
| 294 | [API] GET /regions (지역 고르기·열쇠 확인) | Shell · 머리줄 지역 select | 호출 표시 없음 | 있음 | `E2S` G1 골격이 MSW 응답으로 렌더된다<br>`RT` 헤더에 RegionPicker(+지역 추가)·SnapshotPicker·ScenarioToggle·테마 토글이 있다 |
| 295 | [API] GET /regions/{id}/snapshots (기준일·감시 멈춤 다시 확인) | Shell · 머리줄 기준일 select · §2 "다시 확인" | 호출 표시 없음 | 있음 | `SP` 헤더: 계약 응답에 같은 기준일 리비전 2(published)가 있으면 옵션에 보인다<br>`R3G` 헤더: 30분 넘은 발행 대기 리비전 + /jobs 403 → 상한 안내와 다시 확인 버튼 |
| 296 | [API] GET /scenarios (상황 토글) | Shell · 머리줄 상황 토글 | 호출 표시 없음 | 있음 | `E2S` G1 골격이 MSW 응답으로 렌더된다 |
| 297 | [API] POST /jobs `{}` (열쇠 쓰기 권한 확인 — 403이면 읽기 전용) | Shell · §5 "확인하고 저장" | 호출 표시 없음 | 있음 | `TD` 읽기 전용 토큰 → 저장(role=read) · 안내 배너 · 쓰기 버튼 비활성 |
| 298 | [API] GET /raw/{id}?as=text · GET /raw/{id} (원문 앞뒤 보기·미리보기·저장) | Shell · §3 "원문에서 앞뒤 보기"·"원문 미리보기"·"원문 파일 저장" | 호출 표시 없음 | 있음 | `RD` 열기 전에는 받지 않고, 텍스트는 화면 안에 보인다<br>`CC` 원문 텍스트를 열면 excerpt 오프셋 구간을 하이라이트한다 |
| 299 | [API] GET /jobs/{id} (작업 진행·발행 사슬 폴링) | Shell · §6 작업 진행 카드 | 호출 표시 없음 | 있음 | `CC` JobProgressView: 계약 progress(done/total·step)를 보여 준다<br>`R3E` GET /jobs/{id} 404 → 한 번 실패 뒤 다시 부르지 않는다 |

## 테스트 열(R11-SHELL, 2026-10-16)

'테스트' 칸은 그 줄을 지키는 자동 테스트 이름(`줄임` 파일 › it 이름)이다. 줄임표:

- `AU` = `frontend/src/api/auth.test.ts`
- `CC` = `frontend/src/components/components.contract.test.tsx`
- `CG` = `frontend/src/charts/gallery/ChartGallery.test.tsx`
- `CT` = `frontend/src/components/components.test.tsx`
- `CX` = `frontend/src/pages/complexes/complexes.test.tsx`
- `E2G` = `frontend/tests/e2e/charts-gallery.spec.ts`
- `E2P` = `frontend/e2e/pages/pages.spec.ts`
- `E2S` = `frontend/tests/e2e/smoke.spec.ts`
- `FC` = `frontend/src/components/FactCell.test.tsx`
- `FMT` = `frontend/src/lib/format.test.ts`
- `GL` = `frontend/src/pages/glossary/glossary.test.tsx`
- `GR` = `frontend/src/pages/glossary/glossaryR11.test.tsx`
- `JS` = `frontend/src/pages/judgeScope.test.tsx`
- `LZ` = `frontend/src/charts/lazy.test.tsx`
- `OPS` = `frontend/src/pages/ops/ops.test.tsx`
- `R3C` = `frontend/src/pages/r3c.test.tsx`
- `R3D` = `frontend/src/pages/r3d.test.tsx`
- `R3E` = `frontend/src/pages/r3e.test.tsx`
- `R3F` = `frontend/src/pages/r3f.test.tsx`
- `R3F2` = `frontend/src/pages/r3f2.test.tsx`
- `R3G` = `frontend/src/pages/r3g.test.tsx`
- `R3H` = `frontend/src/pages/r3h.test.tsx`
- `R3I2` = `frontend/src/pages/r3i2.test.tsx`
- `R4F10` = `frontend/src/pages/r4fe10.test.tsx`
- `R4F11` = `frontend/src/pages/r4fe11.test.tsx`
- `R4F12` = `frontend/src/pages/r4fe12.test.tsx`
- `R5` = `frontend/src/pages/r5fe.test.tsx`
- `RD` = `frontend/src/components/RawDocumentPreview.test.tsx`
- `RN` = `frontend/src/pages/rejudgeNeeded.test.tsx`
- `RT` = `frontend/src/routes.test.tsx`
- `SC` = `frontend/src/components/shell-components.test.tsx`
- `SF` = `frontend/src/lib/safeHref.test.tsx`
- `SH` = `frontend/src/layout/shell.test.tsx`
- `SHR` = `frontend/src/pages/share/share.test.tsx`
- `SP` = `frontend/src/components/SnapshotPicker.test.tsx`
- `TD` = `frontend/src/app/TokenDialog.test.tsx`
- `TK` = `frontend/src/layout/tokens.test.ts`

## 요약

전체 299 · 있음 202 · 문구로만 43 · 다른 보드 54 · 빠짐 0

(2026-10-16 목업 고침 반영 — 상태 칸에 '고침 SH-n'이 붙은 줄 85개. 고친 내용은 `../fixes/fixes-Shell.md`)

### 빠짐 목록

- 없음 — 2026-10-16 목업 고침으로 모두 그렸거나(있음) 보드 맨 아래 '구현할 때 지금 동작 그대로 유지' 상자에 적었어요(문구로만). 목록: `../fixes/fixes-Shell.md`



## 새로 더한 것 (기존에 없던 것)

| # | 새 요소 | 새 목업 위치 | 메모 | 테스트 |
|---|---|---|---|---|
| N1 | 로고 아이콘 + 앱 이름이 홈 링크 | Shell · 머리줄 | 지금은 글자만, 링크 아님 | `SH` 앱 이름 "청약 한눈에"는 표지와 함께 홈 링크이고 지역·상황 쿼리를 싣는다 |
| N2 | 앱 이름 "청약 한눈에" | Shell · 머리줄 | `app.name` 값 바꿈 | `SH` 앱 이름 "청약 한눈에"는 표지와 함께 홈 링크이고 지역·상황 쿼리를 싣는다 |
| N3 | 선택칸을 펼친 모습 설명 카드 3장(기준일·지역·상황) | Shell · §1 | 설명 문장 새로 | `SH` 지역이 없으면 "지역 없음" + 지역 추가, 기준일이 없으면 "기준일 없음"으로 칸이 꺼진다 |
| N4 | 알림 띠 경고 아이콘 | Shell · §2 첫 띠 | | `SH` 판정기 장애(/health degraded) → role=alert 주의 띠 + 경고 아이콘(SH-2) |
| N5 | 출처 창 "무엇" 줄 이름 | Shell · §3 | 지금은 이름 없는 작은 글씨 | `SC` 제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음" |
| N6 | 판정 기록 번호가 링크 | Shell · §3 "#1298 출처 비교" | 지금은 번호 글자만, 링크 대상 정해야 함 | `SC` 출처 창: 응답 상태·판정 기록 번호 · 원문 앞뒤 보기 ↔ 원문 닫기 · 다른 출처의 단위 근거 |
| N7 | "계산식: 없음(공고 값 그대로)" 처럼 빈 칸도 보이기 | Shell · §3 | 지금은 값 없으면 줄을 안 그림 | — (하지 않음: 산출식 없을 때 "없음(공고 값 그대로)"는 화면이 사실을 지어내는 문구라 넣지 않음) |
| N8 | 접수 상태 "어떻게 확인했나" 설명 줄 | Shell · §4 | | `SC` IntakeBadge 알약(목업 §4): 가능 = 주색+점, 미정 = 테두리, 확인 불가 = 회색, 불가 = 상태 글자 취소선 |
| N9 | 로딩 뼈대 줄(skeleton) | Shell · §7 | | `SC` 불러오는 중 = 뼈대 + "불러오는 중…" |
| N10 | 일반 오류 카드의 "다시 시도" 버튼 | Shell · §7 | 지금은 준비 중(503)일 때만 버튼 | `SC` 일반 오류 = "불러오지 못했어요: 내용" + 잠시 뒤 + 다시 시도(N10) |
| N11 | 차트 틀 바닥줄 "자료: 출처 · 기준일" | Shell · §8 | | — (R11-CHARTS 소관: ChartFrame 바닥줄) |
| N12 | 404 화면 "홈으로" 링크 | Shell · §9 | 지금은 제목만 | `SH` "찾는 화면이 없어요" + 홈으로(쿼리 유지) |
| N13 | 작업 이름·단계 이름을 쉬운 말로("지역 처음 분석", "공고문 읽기") | Shell · §6 | 지금은 서버 값(region.bootstrap 등) 그대로 — 번역표 필요 | `SC` 작업 이름·단계는 쉬운 말(모르는 값은 원문), 서버 원문은 title |
| N14 | 알림(토스트) 어두운 바탕 + 행동 버튼 테두리 | Shell · §6 | 모양만 | `SC` 어두운 바탕 알림 · 행동 버튼은 실행 후 닫힘 · × 로 닫힘 · 최대 4개 |
| N15 | 휴대폰 아래 탭 줄(홈·단지 찾기·비교·지역 시장) | Mobile | 지금 모바일 메뉴와 항목이 다름(#23) | `SH` 머리줄에는 메뉴가 없고 하단 고정 바에 홈·단지 찾기·용어 사전(쿼리 유지) |

## 참고: ko.json 에만 있고 코드에서 안 쓰는 공통 키

`app.error`, `provenance.open`, `label.legendHelpTitle` — 기능이 아니라서 표에 넣지 않았다.
