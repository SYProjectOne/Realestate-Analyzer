# 대응표 — G0 지역 입력 (`/regions/new`) → RegionNew.dc.html

소스: `frontend/src/pages/region-new/index.tsx`, `applyhomeWindow.ts`, 공통 `components/JobProgress.tsx`(JobProgress·JobProgressView·JobRequeueNote), `pages/_shared`(Section·useDebounced·enumText), `app/toast.tsx`, 문자열 `i18n/ko.json`(`page.G0.*`, `job.*`, `page.common.*`, `auth.readOnlyHint`).
보드: `boards/RegionNew.dc.html`(섹션: 머리 "어느 지역을 분석할까요?" · "1 지역 찾기" · "2 고른 지역 확인 · 이름" · "3 분석 시작" · "4 분석 진행 상황" · "펼친 모습 · 다른 상태").
머리줄 지역 선택·메뉴는 공통 틀이라 Shell 보드에서 다룬다(이 표에는 없음).

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 1 | 화면 제목 h1 (`index.tsx` PageShell · `page.G0.title` "지역 입력") | RegionNew · 머리 h1 "어느 지역을 분석할까요?" | 지역 입력 → 어느 지역을 분석할까요? | 있음 | `RN11` 머리: 현재 위치 줄 · 질문형 h1 · 안내 · 진행 순서 4단계(첫 단계가 지금 단계)<br>`RT` 라우트 10개 — G0 /regions/new → 제목을 렌더한다<br>`ACC` G0 /regions/new: 지역 검색창·분석 시작 버튼 |
| 2 | 안내 문단 (`index.tsx` · `page.G0.intro` "분석할 지역을 자유 지명으로…") | RegionNew · 머리 안내 "동·구·시 이름을 넣고 나오는 후보에서 고르세요…" | 문구 쉬운 말로 | 있음 | `RN11` 머리: 현재 위치 줄 · 질문형 h1 · 안내 · 진행 순서 4단계(첫 단계가 지금 단계) |
| 3 | 후보 블록 Section (`index.tsx` · `page.G0.candidates` "후보") | RegionNew · "1 지역 찾기" | 후보 → 1 지역 찾기 | 있음 | `RN11` 머리: 현재 위치 줄 · 질문형 h1 · 안내 · 진행 순서 4단계(첫 단계가 지금 단계)<br>`RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress |
| 4 | 검색칸 라벨 (`index.tsx` · `page.G0.search` "지역 검색") | RegionNew · "1 지역 찾기" 라벨 "지역 이름 (동·구·시)" | 지역 검색 → 지역 이름 (동·구·시) | 있음 | `RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress<br>`ACC` G0 /regions/new: 지역 검색창·분석 시작 버튼<br>`E2P` G0 지역 입력: 자동완성 → 후보 선택 → 분석 시작 → 작업 진행 |
| 5 | 검색 입력칸 type=search, autoComplete=off (`index.tsx` · placeholder `page.G0.searchPlaceholder` "지명 2자 이상") | RegionNew · "1 지역 찾기" 입력칸 placeholder "2글자 이상" | 지명 2자 이상 → 2글자 이상 | 있음 | `RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress<br>`E2A` G0 지역 입력: 자유 지명 resolve → 후보 선택 → 분석 시작 활성(POST 없음) |
| 6 | 검색 안내 줄 (`index.tsx` · `page.G0.searchHint` "2자 이상 입력하면 후보를 보여 줍니다") | RegionNew · "1 지역 찾기" 칸 아래 "2글자 이상 넣으면 후보를 보여 줘요" | 문구 쉬운 말로 | 있음 | `RN11` 후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요" |
| 7 | 1글자일 때 후보를 부르지 않음(2자 이상만 표시, `debounced.trim().length >= 2`) | RegionNew · 펼친 모습 "지역 찾기 · 다른 상태" → "한 글자만 넣었을 때" | — | 있음 | `RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress |
| 8 | 찾는 중 표시 (`resolve.isFetching` · `page.G0.searching` "찾는 중…") | RegionNew · 펼친 모습 "찾는 동안 · 찾는 중…" | — | 있음 | `RN11` 찾는 동안 '찾는 중…'(role=status) |
| 9 | 300ms 디바운스 자동완성 (`DEBOUNCE_MS`, `useDebounced`) | — | — | 문구로만(고침 RN-4 — "구현 때 유지" 상자) | `RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress |
| 10 | 후보 없음 빈 상태 (`EmptyState` · `page.G0.noCandidates` "일치하는 후보가 없습니다") | RegionNew · 펼친 모습 "후보가 없을 때" "일치하는 후보가 없어요. 동·구·시 이름을 다르게 넣어 보세요." | 안내 한 줄 더함 | 있음 | `RN11` 검색 실패는 role=alert 오류 줄, 후보가 없으면 다른 이름을 넣어 보라는 안내 |
| 11 | 검색 오류 (`resolve.error` · `page.common.loadError` "불러오지 못했습니다: {detail}") | RegionNew · 펼친 모습 "검색이 실패했을 때" "불러오지 못했어요: [오류 내용]" | — | 있음 | `RN11` 검색 실패는 role=alert 오류 줄, 후보가 없으면 다른 이름을 넣어 보라는 안내 |
| 12 | 후보 목록 ul aria-label "후보" (`index.tsx`) | RegionNew · "1 지역 찾기" "후보에서 고르세요 여러 개 골라도 돼요" 목록 | 후보 → 후보에서 고르세요 | 있음 | `RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress<br>`RN11` 후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요"<br>`E2P` G0 지역 입력: 자동완성 → 후보 선택 → 분석 시작 → 작업 진행 |
| 13 | 후보 다중 선택 체크박스(토글, `toggle`) | RegionNew · "1 지역 찾기" 각 후보 체크박스 | — | 있음 | `RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress<br>`RN11` 후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요" |
| 14 | 후보 전체 이름 (`c.full_name`) | RegionNew · "1 지역 찾기" 후보 줄 이름 | — | 있음 | `RN11` 후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요"<br>`FL3` G0 송도 → 후보 선택 → POST /regions → bootstrap(재생) → G1 결과 |
| 15 | 후보 종류 배지 (`page.common.candidateKind.*` 시도·시군구·행정동·법정동) | RegionNew · "1 지역 찾기" 후보 줄 "행정동/법정동" + 아래 범례 "종류: 시도 · 시군구 · 행정동 · 법정동" | — | 있음 | `RN11` 후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요" |
| 16 | 일치 정도 배지 (`page.common.match.*` 정확·앞부분·부분 일치, exact=strong) | RegionNew · "1 지역 찾기" 후보 줄 "이름이 같아요/앞부분이 같아요" + 범례 | 정확 일치 → 이름이 같아요, 앞부분 일치 → 앞부분이 같아요, 부분 일치 → 일부가 같아요 | 있음 | `RN11` 후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요" |
| 17 | 법정동 수 (`page.G0.dongCount` "법정동 {n}개", MetaText count) | RegionNew · "1 지역 찾기" 후보 줄 "법정동 1개" | — | 있음 | `RN11` 후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요" |
| 18 | 선택 블록 Section (`page.G0.selected` "선택한 후보") | RegionNew · "2 고른 지역 확인 · 이름" | 선택한 후보 → 고른 지역 확인 · 이름 | 있음 | `RN11` 머리: 현재 위치 줄 · 질문형 h1 · 안내 · 진행 순서 4단계(첫 단계가 지금 단계)<br>`RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress |
| 19 | 선택 없음 문구 (`page.G0.noneSelected` "선택한 후보가 없습니다") | RegionNew · 펼친 모습 "아직 아무것도 고르지 않았을 때 (2단계 칸)" "고른 곳이 없어요. 왼쪽 후보에서 골라 주세요." | — | 있음 | `RN` 칩의 × → 선택 해제<br>`RN11` 머리: 현재 위치 줄 · 질문형 h1 · 안내 · 진행 순서 4단계(첫 단계가 지금 단계) |
| 20 | 선택 칩 목록 ul aria-label "선택한 후보" + 칩 이름 | RegionNew · "2 고른 지역 확인 · 이름" "고른 곳 1곳" 칩 | 선택한 후보 → 고른 곳 n곳 | 있음 | `RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress<br>`RN11` 후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요" |
| 21 | 칩 빼기 버튼 (aria-label `page.common.remove` "{name} 빼기", × 표시) | RegionNew · "2 …" 칩 버튼 aria-label "인천광역시 연수구 송도동 빼기" + × 아이콘 | — | 있음 | `RN` 칩의 × → 선택 해제 |
| 22 | 지역 이름 라벨·입력칸 (`page.G0.name` "지역 이름", placeholder `page.G0.namePlaceholder` "화면에 보일 이름") | RegionNew · "2 …" "지역 이름 (화면에 보일 이름)" 입력칸 | — | 있음 | `RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress<br>`RN11` 시작 버튼에 이름이 들어간다('{이름}' 분석 시작) · 꺼진 이유 · 공개 자료 안내<br>`FE9` 기본은 비움 — 안내(지난 24개월 + 향후 12개월), 본문에 applyhome_query 없음 |
| 23 | 조회 기간(고급) 접이식 details role=group aria-label (`page.G0.window.title` "청약홈 조회 기간(고급)") | RegionNew · "2 …" details "청약홈에서 찾을 기간 (고급 · 선택)" | 청약홈 조회 기간(고급) → 청약홈에서 찾을 기간 (고급 · 선택) | 있음 | `FE9` 기본은 비움 — 안내(지난 24개월 + 향후 12개월), 본문에 applyhome_query 없음<br>`E2W11` F3·F4 G0 조회 기간(고급) → POST applyhome_query 201 → 저장 그대로, 형식 오류는 폼과 서버가 같이 막는다 |
| 24 | 조회 기간 안내 (`page.G0.window.hint` "비워 두면 서버 기본 조회 창(지난 24개월 + 향후 12개월)…형식 YYYY-MM") | RegionNew · 펼친 모습 "청약홈에서 찾을 기간 (고급) · 펼친 모습" 안내 | 문구 쉬운 말로 | 있음 | `FE9` 기본은 비움 — 안내(지난 24개월 + 향후 12개월), 본문에 applyhome_query 없음 |
| 25 | 시작월 입력칸 (`page.G0.window.from` "조회 시작월", placeholder YYYY-MM, inputMode numeric, maxLength 7) | RegionNew · 펼친 모습 "찾기 시작하는 달" | 조회 시작월 → 찾기 시작하는 달 | 있음 | `FE9` 입력하면 그 키만 보낸다: from_ym·to_ym 'YYYY-MM' |
| 26 | 끝월 입력칸 (`page.G0.window.to` "조회 끝월") | RegionNew · 펼친 모습 "찾기 끝나는 달" | 조회 끝월 → 찾기 끝나는 달 | 있음 | `FE9` 두 칸 모두 → {from_ym, to_ym} |
| 27 | 형식 오류 role=alert + aria-invalid (`checkWindow` invalid · `page.G0.window.invalid` "YYYY-MM 형식(월 01~12)으로 입력하세요") | RegionNew · 펼친 모습 "YYYY-MM 모양(월은 01~12)으로 넣어 주세요" (값 2025-13 예시) | — | 있음 | `FE9` 형식이 틀리면(월 13·'2024/10') 칸 안내 + 시작 막힘(POST 없음), 시작 > 끝도 막힘<br>`E2W11` F3·F4 G0 조회 기간(고급) → POST applyhome_query 201 → 저장 그대로, 형식 오류는 폼과 서버가 같이 막는다 |
| 28 | 순서 오류 role=alert (`reversed` · `page.G0.window.order` "조회 시작월이 끝월보다 늦습니다") | RegionNew · 펼친 모습 "시작하는 달이 끝나는 달보다 늦어요" | — | 있음 | `FE9` 형식이 틀리면(월 13·'2024/10') 칸 안내 + 시작 막힘(POST 없음), 시작 > 끝도 막힘 |
| 29 | 서버 422 조회 기간 오류 (`isApplyhomeQueryLoc` · `page.G0.window.server` "조회 기간을 서버가 받지 않았습니다: {detail}") | RegionNew · 펼친 모습 "찾을 기간을 서버가 받지 않았어요: [서버 메시지]" | — | 있음 | `FE9` 서버 422(applyhome_query 칸) → 조회 기간 칸에 서버 안내 |
| 30 | 오류가 있으면 details 자동 펼침 (`open={windowOpen \|\| windowBlocked \|\| serverErrors}`) | RegionNew · 펼친 모습 "오류가 있으면 이 칸은 저절로 펼쳐지고, 분석 시작 버튼이 꺼져요." | — | 문구로만(고침 RN-4 — "구현 때 유지" 상자에도 적음) | `FE9` 형식이 틀리면(월 13·'2024/10') 칸 안내 + 시작 막힘(POST 없음), 시작 > 끝도 막힘<br>`FE9` 서버 422(applyhome_query 칸) → 조회 기간 칸에 서버 안내 |
| 31 | 비우면 `applyhome_query` 키를 보내지 않음 / 입력한 칸만 보냄 (`checkWindow().query`) | RegionNew · "2 …" details "비워 두면 지난 24개월 + 앞으로 12개월을 찾아요." | — | 문구로만(고침 RN-4 — "구현 때 유지" 상자에도 적음) | `FE9` 기본은 비움 — 안내(지난 24개월 + 향후 12개월), 본문에 applyhome_query 없음<br>`FE9` 입력하면 그 키만 보낸다: from_ym·to_ym 'YYYY-MM'<br>`FE9` 두 칸 모두 → {from_ym, to_ym} |
| 32 | 분석 시작 버튼 (`page.G0.start` "분석 시작") | RegionNew · "3 분석 시작" 버튼 "'송도' 분석 시작" | 분석 시작 → '{이름}' 분석 시작 | 있음 | `RN11` 시작 버튼에 이름이 들어간다('{이름}' 분석 시작) · 꺼진 이유 · 공개 자료 안내<br>`RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress<br>`FE9` 입력하면 그 키만 보낸다: from_ym·to_ym 'YYYY-MM' |
| 33 | 시작 꺼짐 안내 (`page.G0.startDisabled` "후보를 1개 이상 고르고 이름을 입력하세요") | RegionNew · 펼친 모습 "분석 시작 버튼이 꺼졌을 때" "후보를 1개 이상 고르고 이름을 넣어 주세요" | — | 있음 | `RN11` 시작 버튼에 이름이 들어간다('{이름}' 분석 시작) · 꺼진 이유 · 공개 자료 안내<br>`ACC` G0 /regions/new: 지역 검색창·분석 시작 버튼 |
| 34 | 읽기 전용: 버튼 꺼짐 + title·안내 (`useCanWrite` · `auth.readOnlyHint` "읽기 전용 토큰으로는 저장·실행할 수 없습니다") | RegionNew · 펼친 모습 버튼 title + "읽기 전용 토큰으로는 저장·실행할 수 없어요" | — | 있음 | `RN11` 읽기 전용 토큰이면 시작 버튼이 꺼지고 그 이유를 보인다 |
| 35 | 그 밖의 꺼짐 조건(기간 오류·보내는 중 `isPending`·이미 시작 `created`) | RegionNew · 펼친 모습 "이 밖에 꺼지는 때: 찾을 기간 칸에 오류가 있을 때 · 시작을 보내는 중일 때 · 이미 시작했을 때" | — | 문구로만(고침 RN-4 — "구현 때 유지" 상자에도 적음) | `FE9` 형식이 틀리면(월 13·'2024/10') 칸 안내 + 시작 막힘(POST 없음), 시작 > 끝도 막힘<br>`RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress |
| 36 | 시작 요청 오류 role=alert (`create.error` · `page.common.loadError`) | RegionNew · 펼친 모습 "불러오지 못했어요: [시작 요청 오류 내용]" | — | 있음 | `FE9` 서버 422(applyhome_query 칸) → 조회 기간 칸에 서버 안내 (시작 요청 오류 role=alert) |
| 37 | 시작 성공 토스트 (`page.G0.started` "지역을 만들고 분석을 시작했습니다") | RegionNew · 펼친 모습 "잠깐 뜨는 알림" "지역을 만들고 분석을 시작했어요" | — | 있음 | `RN11` 4 진행 상황: 서버 지역 이름으로 머리말 · 끝나기 전 안내, 끝나면 "홈으로" 링크(?region=) · 생활권 링크는 시작 직후부터 |
| 38 | 진행 표시 JobProgress (region.bootstrap 잡, `created.job_id`) | RegionNew · "4 분석 진행 상황 (분석 시작을 누른 뒤의 모습)" role=status | — | 있음 | `RN11` 4 진행 상황: 서버 지역 이름으로 머리말 · 끝나기 전 안내, 끝나면 "홈으로" 링크(?region=) · 생활권 링크는 시작 직후부터<br>`RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress<br>`FL3` G0 송도 → 후보 선택 → POST /regions → bootstrap(재생) → G1 결과 |
| 39 | 진행 제목·잡 이름 (`job.title` "작업 진행" + `job.job_name`) | RegionNew · "4 …" "'송도' 지역 자료를 모으고 있어요" · "작업: 지역 첫 수집" | 작업 진행 → 분석 진행 상황, region.bootstrap → 지역 첫 수집 | 있음 | `RN11` 4 진행 상황: 서버 지역 이름으로 머리말 · 끝나기 전 안내, 끝나면 "홈으로" 링크(?region=) · 생활권 링크는 시작 직후부터<br>`CT` JobProgressView: 상태 텍스트 |
| 40 | 상태 '대기' (`job.status.queued`) | RegionNew · 펼친 모습 "진행 상황 · 상태별 모습" "대기 순서를 기다리고 있어요" | — | 있음 | `CT` JobProgressView: 상태 텍스트 |
| 41 | 상태 '실행 중' (`job.status.running`) | RegionNew · "4 …" "실행 중" | — | 있음 | `CT` JobProgressView: 상태 텍스트 |
| 42 | 진행 수 (`job.progress` "{done}/{total}") | RegionNew · "4 …" "[n] / [m] 단계" | — | 있음 | `CC` JobProgressView: 계약 progress(done/total·step)를 보여 준다 |
| 43 | 진행 단계 (`job.step` "단계 {step}") | RegionNew · "4 …" "[단계 이름]" | — | 있음 | `CC` JobProgressView: 계약 progress(done/total·step)를 보여 준다 |
| 44 | 진행 막대(진행 수 있으면 결정 막대) `<progress>` aria-label=상태 | RegionNew · "4 …" role=progressbar aria-label "실행 중" | — | 있음 | `CC` JobProgressView: 계약 progress(done/total·step)를 보여 준다 |
| 45 | 진행 수가 없을 때 미정(indeterminate) 막대 | — | — | 있음(고침 RN-1 — 펼친 모습 "진행 상황 · 상태별 모습" 대기 칸에 줄무늬 미정 막대) | `SC` 진행 수가 없으면 끝을 모르는 줄무늬 막대(role=progressbar, 값 없음) |
| 46 | 상태 '완료' (`job.status.done`) + 완료 콜백 | RegionNew · 펼친 모습 "완료 분석이 끝났어요" | — | 있음 | `RN11` 4 진행 상황: 서버 지역 이름으로 머리말 · 끝나기 전 안내, 끝나면 "홈으로" 링크(?region=) · 생활권 링크는 시작 직후부터<br>`FL3` G0 송도 → 후보 선택 → POST /regions → bootstrap(재생) → G1 결과 |
| 47 | 완료 토스트 (`page.G0.done` "분석이 끝났습니다") | RegionNew · 펼친 모습 "잠깐 뜨는 알림" "분석이 끝났어요" | — | 있음 | `RN11` 4 진행 상황: 서버 지역 이름으로 머리말 · 끝나기 전 안내, 끝나면 "홈으로" 링크(?region=) · 생활권 링크는 시작 직후부터 |
| 48 | 상태 '실패' + 오류 (`job.status.failed`, `job.error` "오류: {detail}") | RegionNew · 펼친 모습 "실패 오류: [오류 내용]" | — | 있음 | `CT` JobProgressView: 상태 텍스트<br>`FE12` JobProgressView: 6회 넘어 failed(degraded_source) — 코드 접두 없이 멈춘 이유 |
| 49 | 빈 데이터셋 재시도 상한 실패 문구 (`degradedFailureText` · `job.degradedFailed`) | RegionNew · 펼친 모습 "수집 자료가 [max]번 다시 모아도 불완전해 멈췄을 때: '발행하지 않았어요: [사유]'" | — | 있음 | `FE12` JobProgressView: 6회 넘어 failed(degraded_source) — 코드 접두 없이 멈춘 이유 |
| 50 | 빈 데이터셋 재큐잉 안내 (`JobRequeueNote` · `job.requeuedDegraded` + `job.requeuedAt`) | RegionNew · 펼친 모습 "수집 자료가 불완전해([사유]) 발행하지 않고 다시 모아요 (다시 대기 [n]/[max]회, [시각] 이후) — 아직 실패가 아니에요." | — | 있음(고침 RN-2 — 문구를 "[시각] 이후 다시 시도"로 맞춤) | `FE12` JobProgressView(G0 bootstrap): '불완전한 수집 — 다시 수집(2/6회, 01:30 이후)' + '적재 중', 발행 busy 문구·영문 코드·오류 줄 없음<br>`FE12` requeueInfo: degraded_source 재큐잉은 kind degraded(n·상한 6·다음 시도·사유) — busy 가 아니다 |
| 51 | 재큐잉 시각 없을 때 (`job.requeuedSoon` "곧 다시 시도") | — | — | 있음(고침 RN-2 — "곧 다시 시도" 줄) | `FE12` requeueInfo: degraded_source 재큐잉은 kind degraded(n·상한 6·다음 시도·사유) — busy 가 아니다 |
| 52 | 첫 적재 안내 (`job.requeuedDegradedBootstrap` "지역 첫 적재 중 — 발행 리비전은 아직 없습니다.") | RegionNew · 펼친 모습 "지역 첫 수집 중이라 아직 발행된 수정본은 없어요." | 리비전 → 수정본 | 있음 | `FE12` JobProgressView(G0 bootstrap): '불완전한 수집 — 다시 수집(2/6회, 01:30 이후)' + '적재 중', 발행 busy 문구·영문 코드·오류 줄 없음 |
| 53 | 발행 busy 재큐잉 (`job.requeued` "같은 리비전의 다른 발행이 끝나길 기다리는 중(다시 대기 {n}회)…") | RegionNew · 펼친 모습 "다른 발행이 끝나길 기다리는 중(다시 대기 [n]회)" | — | 있음 | `FE12` JobProgressView: 발행 busy 재큐잉 문구는 그대로(회귀)<br>`R3H2` JobProgressView: 대기 + "다른 발행이 끝나길 기다리는 중(재시도 3회)" — 오류 줄 없음 |
| 54 | 발행 예외 재시도 (`job.requeuedError` "({n}/{max}회) — 아직 실패가 아닙니다") | RegionNew · 펼친 모습 "발행 중 오류로 다시 시도하는 중([n]/[max]회) — 아직 실패가 아니에요" | — | 있음 | `R3I2` JobProgressView: "발행 오류 — 다시 시도하는 중(2/5회)", 영문 코드·오류 줄 없음 |
| 55 | 일시 조회 오류 동안 마지막 상태 유지 + 다시 확인 줄 (`job.retrying` "상태를 받지 못해 다시 확인하는 중: {detail}") | RegionNew · 펼친 모습 "상태를 받지 못해 다시 확인하는 중: [오류 내용]" | — | 있음 | `R3F` JobProgressView: 받아 둔 잡이 있으면 일시 오류 동안 마지막 상태 + 다시 확인 중 줄 |
| 56 | 잡을 받기 전 조회 오류 (`error && !job` → `job.error`) | — | — | 있음(고침 RN-3 — "작업 정보를 아직 못 받았을 때" 칸의 "오류: [오류 내용]") | `R3F` GET /jobs/{id} 503 한 번 → 다시 조회해 running → done 까지 따라간다<br>`R3E` GET /jobs/{id} 404 → 한 번 실패 뒤 다시 부르지 않는다 |
| 57 | 잡 없음 (`job.none` "진행 중인 작업 없음") | RegionNew · 펼친 모습 "작업을 아직 못 받았으면 '진행 중인 작업 없음'" | — | 있음(고침 RN-3 — 같은 칸의 "진행 중인 작업 없음") | `CT` JobProgressView: 상태 텍스트 |
| 58 | 진행 aria-live=polite 알림 | RegionNew · "4 …" role=status | — | 있음 | `RN11` 4 진행 상황: 서버 지역 이름으로 머리말 · 끝나기 전 안내, 끝나면 "홈으로" 링크(?region=) · 생활권 링크는 시작 직후부터<br>`FL3` G0 송도 → 후보 선택 → POST /regions → bootstrap(재생) → G1 결과 |
| 59 | 완료 뒤 홈 링크 (`page.G0.goDashboard` "홈 대시보드로", `/?region={id}`, done일 때만) | RegionNew · 펼친 모습 "완료" 링크 "홈으로 (이 지역 보기)" + "4 …" "'홈으로' 버튼은 분석이 끝나면 나와요" | 홈 대시보드로 → 홈으로 (이 지역 보기) | 있음 | `RN11` 4 진행 상황: 서버 지역 이름으로 머리말 · 끝나기 전 안내, 끝나면 "홈으로" 링크(?region=) · 생활권 링크는 시작 직후부터<br>`FL3` G0 송도 → 후보 선택 → POST /regions → bootstrap(재생) → G1 결과 |
| 60 | 생활권 편집 링크 (`page.G0.goLivingAreas` "생활권 편집", `/regions/{id}/living-areas`, 시작 직후부터) | RegionNew · "4 …" 링크 "생활권 나누기 바꾸기 (생활권 편집)" | 생활권 편집 → 생활권 나누기 바꾸기 | 있음 | `RN11` 4 진행 상황: 서버 지역 이름으로 머리말 · 끝나기 전 안내, 끝나면 "홈으로" 링크(?region=) · 생활권 링크는 시작 직후부터<br>`RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress |
| 61 | 폴링 2초(queued/running 동안 GET /jobs/{id}) | — | — | 문구로만(고침 RN-4 — "구현 때 유지" 상자) | `R3E` jobRefetchInterval: 4xx error → false, done·failed → false, 진행 중 → 간격<br>`R3F` GET /jobs/{id} 503 한 번 → 다시 조회해 running → done 까지 따라간다 |
| 62 | API `GET /regions/resolve?q=` (`useResolveRegion`) | RegionNew · "1 지역 찾기" 검색칸(호출 주체) | — | 있음 | `RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress<br>`E2A` G0 지역 입력: 자유 지명 resolve → 후보 선택 → 분석 시작 활성(POST 없음) |
| 63 | API `POST /regions` {name, query_text, selections, applyhome_query?} (`useCreateRegion`) | RegionNew · "3 분석 시작" 버튼(호출 주체) | — | 있음 | `RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress<br>`FE9` 입력하면 그 키만 보낸다: from_ym·to_ym 'YYYY-MM'<br>`FL3` G0 송도 → 후보 선택 → POST /regions → bootstrap(재생) → G1 결과 |
| 64 | API `GET /jobs/{id}` (`useJob`) | RegionNew · "4 분석 진행 상황"(호출 주체) | — | 있음 | `RN` 자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress<br>`RN11` 4 진행 상황: 서버 지역 이름으로 머리말 · 끝나기 전 안내, 끝나면 "홈으로" 링크(?region=) · 생활권 링크는 시작 직후부터 |

요약: 전체 64 · 있음 59 · 문구로만 5 · 다른 보드 0 · 빠짐 0 (2026-10-16 고침 반영 — fixes/fixes-RegionNew.md)

빠짐 목록: 없음 (2026-10-16 고침 반영)
- 고침 전 빠짐 5개: #45·#51·#56 → 있음(고침 RN-1·RN-2·RN-3), #9·#61 → 문구로만(고침 RN-4 "구현 때 유지" 상자)
- (참고) `job.requeuedDegradedDaily`는 G0(region.bootstrap 잡)에서 나오지 않아 이 표에 넣지 않음 — Ops·Market 표에서 다룸

## 새로 더한 것 (기존에 없던 것)

| # | 새 기능 | 위치 (보드 · 섹션) | 비고 | 테스트 |
|---|---|---|---|---|
| N1 | 단계 안내 1 찾기 → 2 확인 → 3 시작 → 4 진행 | RegionNew · 머리 단계 목록 | 표시만 | `RN11` 머리: 현재 위치 줄 · 질문형 h1 · 안내 · 진행 순서 4단계(첫 단계가 지금 단계) |
| N2 | 후보 개수 표시 "후보 9개" | "1 지역 찾기" 검색칸 아래 | 서버 응답 길이 | `RN11` 후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요" |
| N3 | "'법정동'과 '행정동'은 무엇이 다른가요?" `?` 설명 버튼 | "1 지역 찾기" | 용어 설명 팝오버 | `RN11` 후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요" |
| N4 | 종류·일치 정도 범례 줄 | "1 지역 찾기" 목록 아래 | | `RN11` 후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요" |
| N5 | 칩 안내 "칩을 누르면 빠져요" | "2 고른 지역 확인 · 이름" | | `RN11` 후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요" |
| N6 | 이름 칸 안내 "홈 화면 위쪽 지역 고르기에 이 이름으로 나와요" | "2 …" | | `RN11` 시작 버튼에 이름이 들어간다('{이름}' 분석 시작) · 꺼진 이유 · 공개 자료 안내 |
| N7 | 시작 버튼에 지역 이름 넣기 "'송도' 분석 시작" | "3 분석 시작" | 문구만 | `RN11` 시작 버튼에 이름이 들어간다('{이름}' 분석 시작) · 꺼진 이유 · 공개 자료 안내 |
| N8 | 공개 자료 안내 "공고·실거래·통계 같은 공개 자료만 모아요. 처음에는 몇 분에서 수십 분…" | "3 분석 시작" | | `RN11` 시작 버튼에 이름이 들어간다('{이름}' 분석 시작) · 꺼진 이유 · 공개 자료 안내 |
| N9 | 진행 머리말 "'송도' 지역 자료를 모으고 있어요" | "4 분석 진행 상황" | | `RN11` 4 진행 상황: 서버 지역 이름으로 머리말 · 끝나기 전 안내, 끝나면 "홈으로" 링크(?region=) · 생활권 링크는 시작 직후부터 |
| N10 | 안내 "이 창을 닫아도 분석은 계속돼요. 끝나면 '분석이 끝났어요' 알림이 떠요." | "4 분석 진행 상황" | | `RN11` 4 진행 상황: 서버 지역 이름으로 머리말 · 끝나기 전 안내, 끝나면 "홈으로" 링크(?region=) · 생활권 링크는 시작 직후부터 |

## 테스트 열(R11-SETUP, 2026-10-16)

약어(경로는 저장소 기준):
- `RN` = `frontend/src/pages/region-new/region-new.test.tsx` · `RN11` = `frontend/src/pages/region-new/regionNew.r11.test.tsx`
- `LA` = `frontend/src/pages/living-areas/living-areas.test.tsx` · `LA11` = `frontend/src/pages/living-areas/livingAreas.r11.test.tsx` · `RX` = `frontend/src/pages/living-areas/regionExpand.test.tsx`
- `RP` = `frontend/src/pages/reports/reports.test.tsx` · `RP11` = `frontend/src/pages/reports/reports.r11.test.tsx`
- `SHR` = `frontend/src/pages/share/share.test.tsx` · `SHR11` = `frontend/src/pages/share/share.r11.test.tsx`
- `ACC` = `frontend/src/pages/acceptance.test.tsx` · `RT` = `frontend/src/routes.test.tsx` · `TD` = `frontend/src/app/TokenDialog.test.tsx`
- `R3D`·`R3E`·`R3F`·`R3F2`·`R3G`·`R3H2`·`R3I2` = `frontend/src/pages/r3*.test.tsx` · `FE9` = `frontend/src/pages/r4fe9.test.tsx` · `FE12` = `frontend/src/pages/r4fe12.test.tsx`
- `CT` = `frontend/src/components/components.test.tsx` · `CC` = `frontend/src/components/components.contract.test.tsx` · `SC` = `frontend/src/components/shell-components.test.tsx`
- `AU` = `frontend/src/api/auth.test.ts` · `DL` = `frontend/src/api/download.test.ts`
- `E2P` = `frontend/e2e/pages/pages.spec.ts` · `E2A` = `frontend/e2e/api/screens.spec.ts` · `E2W7`·`E2W8`·`E2W10`·`E2W11` = `frontend/e2e/api/writes7-r3d·writes8·writes10-r3i·writes11-r4.spec.ts`
- `FL1` = `e2e/flows/1-g8-report-pdf.spec.ts` · `FL3` = `e2e/flows/3-g0-region-bootstrap.spec.ts`
