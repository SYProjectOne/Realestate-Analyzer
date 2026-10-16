# 대응표 — G0 지역 입력 (`/regions/new`) → RegionNew.dc.html

소스: `frontend/src/pages/region-new/index.tsx`, `applyhomeWindow.ts`, 공통 `components/JobProgress.tsx`(JobProgress·JobProgressView·JobRequeueNote), `pages/_shared`(Section·useDebounced·enumText), `app/toast.tsx`, 문자열 `i18n/ko.json`(`page.G0.*`, `job.*`, `page.common.*`, `auth.readOnlyHint`).
보드: `boards/RegionNew.dc.html`(섹션: 머리 "어느 지역을 분석할까요?" · "1 지역 찾기" · "2 고른 지역 확인 · 이름" · "3 분석 시작" · "4 분석 진행 상황" · "펼친 모습 · 다른 상태").
머리줄 지역 선택·메뉴는 공통 틀이라 Shell 보드에서 다룬다(이 표에는 없음).

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 |
|---|---|---|---|---|
| 1 | 화면 제목 h1 (`index.tsx` PageShell · `page.G0.title` "지역 입력") | RegionNew · 머리 h1 "어느 지역을 분석할까요?" | 지역 입력 → 어느 지역을 분석할까요? | 있음 |
| 2 | 안내 문단 (`index.tsx` · `page.G0.intro` "분석할 지역을 자유 지명으로…") | RegionNew · 머리 안내 "동·구·시 이름을 넣고 나오는 후보에서 고르세요…" | 문구 쉬운 말로 | 있음 |
| 3 | 후보 블록 Section (`index.tsx` · `page.G0.candidates` "후보") | RegionNew · "1 지역 찾기" | 후보 → 1 지역 찾기 | 있음 |
| 4 | 검색칸 라벨 (`index.tsx` · `page.G0.search` "지역 검색") | RegionNew · "1 지역 찾기" 라벨 "지역 이름 (동·구·시)" | 지역 검색 → 지역 이름 (동·구·시) | 있음 |
| 5 | 검색 입력칸 type=search, autoComplete=off (`index.tsx` · placeholder `page.G0.searchPlaceholder` "지명 2자 이상") | RegionNew · "1 지역 찾기" 입력칸 placeholder "2글자 이상" | 지명 2자 이상 → 2글자 이상 | 있음 |
| 6 | 검색 안내 줄 (`index.tsx` · `page.G0.searchHint` "2자 이상 입력하면 후보를 보여 줍니다") | RegionNew · "1 지역 찾기" 칸 아래 "2글자 이상 넣으면 후보를 보여 줘요" | 문구 쉬운 말로 | 있음 |
| 7 | 1글자일 때 후보를 부르지 않음(2자 이상만 표시, `debounced.trim().length >= 2`) | RegionNew · 펼친 모습 "지역 찾기 · 다른 상태" → "한 글자만 넣었을 때" | — | 있음 |
| 8 | 찾는 중 표시 (`resolve.isFetching` · `page.G0.searching` "찾는 중…") | RegionNew · 펼친 모습 "찾는 동안 · 찾는 중…" | — | 있음 |
| 9 | 300ms 디바운스 자동완성 (`DEBOUNCE_MS`, `useDebounced`) | — | — | 빠짐(목업에 없음 — 입력 지연 동작은 그리거나 적지 않음) |
| 10 | 후보 없음 빈 상태 (`EmptyState` · `page.G0.noCandidates` "일치하는 후보가 없습니다") | RegionNew · 펼친 모습 "후보가 없을 때" "일치하는 후보가 없어요. 동·구·시 이름을 다르게 넣어 보세요." | 안내 한 줄 더함 | 있음 |
| 11 | 검색 오류 (`resolve.error` · `page.common.loadError` "불러오지 못했습니다: {detail}") | RegionNew · 펼친 모습 "검색이 실패했을 때" "불러오지 못했어요: [오류 내용]" | — | 있음 |
| 12 | 후보 목록 ul aria-label "후보" (`index.tsx`) | RegionNew · "1 지역 찾기" "후보에서 고르세요 여러 개 골라도 돼요" 목록 | 후보 → 후보에서 고르세요 | 있음 |
| 13 | 후보 다중 선택 체크박스(토글, `toggle`) | RegionNew · "1 지역 찾기" 각 후보 체크박스 | — | 있음 |
| 14 | 후보 전체 이름 (`c.full_name`) | RegionNew · "1 지역 찾기" 후보 줄 이름 | — | 있음 |
| 15 | 후보 종류 배지 (`page.common.candidateKind.*` 시도·시군구·행정동·법정동) | RegionNew · "1 지역 찾기" 후보 줄 "행정동/법정동" + 아래 범례 "종류: 시도 · 시군구 · 행정동 · 법정동" | — | 있음 |
| 16 | 일치 정도 배지 (`page.common.match.*` 정확·앞부분·부분 일치, exact=strong) | RegionNew · "1 지역 찾기" 후보 줄 "이름이 같아요/앞부분이 같아요" + 범례 | 정확 일치 → 이름이 같아요, 앞부분 일치 → 앞부분이 같아요, 부분 일치 → 일부가 같아요 | 있음 |
| 17 | 법정동 수 (`page.G0.dongCount` "법정동 {n}개", MetaText count) | RegionNew · "1 지역 찾기" 후보 줄 "법정동 1개" | — | 있음 |
| 18 | 선택 블록 Section (`page.G0.selected` "선택한 후보") | RegionNew · "2 고른 지역 확인 · 이름" | 선택한 후보 → 고른 지역 확인 · 이름 | 있음 |
| 19 | 선택 없음 문구 (`page.G0.noneSelected` "선택한 후보가 없습니다") | RegionNew · 펼친 모습 "아직 아무것도 고르지 않았을 때 (2단계 칸)" "고른 곳이 없어요. 왼쪽 후보에서 골라 주세요." | — | 있음 |
| 20 | 선택 칩 목록 ul aria-label "선택한 후보" + 칩 이름 | RegionNew · "2 고른 지역 확인 · 이름" "고른 곳 1곳" 칩 | 선택한 후보 → 고른 곳 n곳 | 있음 |
| 21 | 칩 빼기 버튼 (aria-label `page.common.remove` "{name} 빼기", × 표시) | RegionNew · "2 …" 칩 버튼 aria-label "인천광역시 연수구 송도동 빼기" + × 아이콘 | — | 있음 |
| 22 | 지역 이름 라벨·입력칸 (`page.G0.name` "지역 이름", placeholder `page.G0.namePlaceholder` "화면에 보일 이름") | RegionNew · "2 …" "지역 이름 (화면에 보일 이름)" 입력칸 | — | 있음 |
| 23 | 조회 기간(고급) 접이식 details role=group aria-label (`page.G0.window.title` "청약홈 조회 기간(고급)") | RegionNew · "2 …" details "청약홈에서 찾을 기간 (고급 · 선택)" | 청약홈 조회 기간(고급) → 청약홈에서 찾을 기간 (고급 · 선택) | 있음 |
| 24 | 조회 기간 안내 (`page.G0.window.hint` "비워 두면 서버 기본 조회 창(지난 24개월 + 향후 12개월)…형식 YYYY-MM") | RegionNew · 펼친 모습 "청약홈에서 찾을 기간 (고급) · 펼친 모습" 안내 | 문구 쉬운 말로 | 있음 |
| 25 | 시작월 입력칸 (`page.G0.window.from` "조회 시작월", placeholder YYYY-MM, inputMode numeric, maxLength 7) | RegionNew · 펼친 모습 "찾기 시작하는 달" | 조회 시작월 → 찾기 시작하는 달 | 있음 |
| 26 | 끝월 입력칸 (`page.G0.window.to` "조회 끝월") | RegionNew · 펼친 모습 "찾기 끝나는 달" | 조회 끝월 → 찾기 끝나는 달 | 있음 |
| 27 | 형식 오류 role=alert + aria-invalid (`checkWindow` invalid · `page.G0.window.invalid` "YYYY-MM 형식(월 01~12)으로 입력하세요") | RegionNew · 펼친 모습 "YYYY-MM 모양(월은 01~12)으로 넣어 주세요" (값 2025-13 예시) | — | 있음 |
| 28 | 순서 오류 role=alert (`reversed` · `page.G0.window.order` "조회 시작월이 끝월보다 늦습니다") | RegionNew · 펼친 모습 "시작하는 달이 끝나는 달보다 늦어요" | — | 있음 |
| 29 | 서버 422 조회 기간 오류 (`isApplyhomeQueryLoc` · `page.G0.window.server` "조회 기간을 서버가 받지 않았습니다: {detail}") | RegionNew · 펼친 모습 "찾을 기간을 서버가 받지 않았어요: [서버 메시지]" | — | 있음 |
| 30 | 오류가 있으면 details 자동 펼침 (`open={windowOpen \|\| windowBlocked \|\| serverErrors}`) | RegionNew · 펼친 모습 "오류가 있으면 이 칸은 저절로 펼쳐지고, 분석 시작 버튼이 꺼져요." | — | 문구로만 |
| 31 | 비우면 `applyhome_query` 키를 보내지 않음 / 입력한 칸만 보냄 (`checkWindow().query`) | RegionNew · "2 …" details "비워 두면 지난 24개월 + 앞으로 12개월을 찾아요." | — | 문구로만 |
| 32 | 분석 시작 버튼 (`page.G0.start` "분석 시작") | RegionNew · "3 분석 시작" 버튼 "'송도' 분석 시작" | 분석 시작 → '{이름}' 분석 시작 | 있음 |
| 33 | 시작 꺼짐 안내 (`page.G0.startDisabled` "후보를 1개 이상 고르고 이름을 입력하세요") | RegionNew · 펼친 모습 "분석 시작 버튼이 꺼졌을 때" "후보를 1개 이상 고르고 이름을 넣어 주세요" | — | 있음 |
| 34 | 읽기 전용: 버튼 꺼짐 + title·안내 (`useCanWrite` · `auth.readOnlyHint` "읽기 전용 토큰으로는 저장·실행할 수 없습니다") | RegionNew · 펼친 모습 버튼 title + "읽기 전용 토큰으로는 저장·실행할 수 없어요" | — | 있음 |
| 35 | 그 밖의 꺼짐 조건(기간 오류·보내는 중 `isPending`·이미 시작 `created`) | RegionNew · 펼친 모습 "이 밖에 꺼지는 때: 찾을 기간 칸에 오류가 있을 때 · 시작을 보내는 중일 때 · 이미 시작했을 때" | — | 문구로만 |
| 36 | 시작 요청 오류 role=alert (`create.error` · `page.common.loadError`) | RegionNew · 펼친 모습 "불러오지 못했어요: [시작 요청 오류 내용]" | — | 있음 |
| 37 | 시작 성공 토스트 (`page.G0.started` "지역을 만들고 분석을 시작했습니다") | RegionNew · 펼친 모습 "잠깐 뜨는 알림" "지역을 만들고 분석을 시작했어요" | — | 있음 |
| 38 | 진행 표시 JobProgress (region.bootstrap 잡, `created.job_id`) | RegionNew · "4 분석 진행 상황 (분석 시작을 누른 뒤의 모습)" role=status | — | 있음 |
| 39 | 진행 제목·잡 이름 (`job.title` "작업 진행" + `job.job_name`) | RegionNew · "4 …" "'송도' 지역 자료를 모으고 있어요" · "작업: 지역 첫 수집" | 작업 진행 → 분석 진행 상황, region.bootstrap → 지역 첫 수집 | 있음 |
| 40 | 상태 '대기' (`job.status.queued`) | RegionNew · 펼친 모습 "진행 상황 · 상태별 모습" "대기 순서를 기다리고 있어요" | — | 있음 |
| 41 | 상태 '실행 중' (`job.status.running`) | RegionNew · "4 …" "실행 중" | — | 있음 |
| 42 | 진행 수 (`job.progress` "{done}/{total}") | RegionNew · "4 …" "[n] / [m] 단계" | — | 있음 |
| 43 | 진행 단계 (`job.step` "단계 {step}") | RegionNew · "4 …" "[단계 이름]" | — | 있음 |
| 44 | 진행 막대(진행 수 있으면 결정 막대) `<progress>` aria-label=상태 | RegionNew · "4 …" role=progressbar aria-label "실행 중" | — | 있음 |
| 45 | 진행 수가 없을 때 미정(indeterminate) 막대 | — | — | 빠짐(목업에 없음 — 결정 막대 한 모양만 그림) |
| 46 | 상태 '완료' (`job.status.done`) + 완료 콜백 | RegionNew · 펼친 모습 "완료 분석이 끝났어요" | — | 있음 |
| 47 | 완료 토스트 (`page.G0.done` "분석이 끝났습니다") | RegionNew · 펼친 모습 "잠깐 뜨는 알림" "분석이 끝났어요" | — | 있음 |
| 48 | 상태 '실패' + 오류 (`job.status.failed`, `job.error` "오류: {detail}") | RegionNew · 펼친 모습 "실패 오류: [오류 내용]" | — | 있음 |
| 49 | 빈 데이터셋 재시도 상한 실패 문구 (`degradedFailureText` · `job.degradedFailed`) | RegionNew · 펼친 모습 "수집 자료가 [max]번 다시 모아도 불완전해 멈췄을 때: '발행하지 않았어요: [사유]'" | — | 있음 |
| 50 | 빈 데이터셋 재큐잉 안내 (`JobRequeueNote` · `job.requeuedDegraded` + `job.requeuedAt`) | RegionNew · 펼친 모습 "수집 자료가 불완전해([사유]) 발행하지 않고 다시 모아요 (다시 대기 [n]/[max]회, [시각] 이후) — 아직 실패가 아니에요." | — | 있음 |
| 51 | 재큐잉 시각 없을 때 (`job.requeuedSoon` "곧 다시 시도") | — | — | 빠짐(목업에 없음 — "[시각] 이후" 모양만 있음) |
| 52 | 첫 적재 안내 (`job.requeuedDegradedBootstrap` "지역 첫 적재 중 — 발행 리비전은 아직 없습니다.") | RegionNew · 펼친 모습 "지역 첫 수집 중이라 아직 발행된 수정본은 없어요." | 리비전 → 수정본 | 있음 |
| 53 | 발행 busy 재큐잉 (`job.requeued` "같은 리비전의 다른 발행이 끝나길 기다리는 중(다시 대기 {n}회)…") | RegionNew · 펼친 모습 "다른 발행이 끝나길 기다리는 중(다시 대기 [n]회)" | — | 있음 |
| 54 | 발행 예외 재시도 (`job.requeuedError` "({n}/{max}회) — 아직 실패가 아닙니다") | RegionNew · 펼친 모습 "발행 중 오류로 다시 시도하는 중([n]/[max]회) — 아직 실패가 아니에요" | — | 있음 |
| 55 | 일시 조회 오류 동안 마지막 상태 유지 + 다시 확인 줄 (`job.retrying` "상태를 받지 못해 다시 확인하는 중: {detail}") | RegionNew · 펼친 모습 "상태를 받지 못해 다시 확인하는 중: [오류 내용]" | — | 있음 |
| 56 | 잡을 받기 전 조회 오류 (`error && !job` → `job.error`) | — | — | 빠짐(목업에 없음 — '실패' 상태의 오류 줄만 그림) |
| 57 | 잡 없음 (`job.none` "진행 중인 작업 없음") | RegionNew · 펼친 모습 "작업을 아직 못 받았으면 '진행 중인 작업 없음'" | — | 문구로만 |
| 58 | 진행 aria-live=polite 알림 | RegionNew · "4 …" role=status | — | 있음 |
| 59 | 완료 뒤 홈 링크 (`page.G0.goDashboard` "홈 대시보드로", `/?region={id}`, done일 때만) | RegionNew · 펼친 모습 "완료" 링크 "홈으로 (이 지역 보기)" + "4 …" "'홈으로' 버튼은 분석이 끝나면 나와요" | 홈 대시보드로 → 홈으로 (이 지역 보기) | 있음 |
| 60 | 생활권 편집 링크 (`page.G0.goLivingAreas` "생활권 편집", `/regions/{id}/living-areas`, 시작 직후부터) | RegionNew · "4 …" 링크 "생활권 나누기 바꾸기 (생활권 편집)" | 생활권 편집 → 생활권 나누기 바꾸기 | 있음 |
| 61 | 폴링 2초(queued/running 동안 GET /jobs/{id}) | — | — | 빠짐(목업에 없음 — 동작) |
| 62 | API `GET /regions/resolve?q=` (`useResolveRegion`) | RegionNew · "1 지역 찾기" 검색칸(호출 주체) | — | 있음 |
| 63 | API `POST /regions` {name, query_text, selections, applyhome_query?} (`useCreateRegion`) | RegionNew · "3 분석 시작" 버튼(호출 주체) | — | 있음 |
| 64 | API `GET /jobs/{id}` (`useJob`) | RegionNew · "4 분석 진행 상황"(호출 주체) | — | 있음 |

요약: 전체 64 · 있음 55 · 문구로만 4 · 다른 보드 0 · 빠짐 5

빠짐 목록:
- #9 300ms 디바운스 자동완성 — 목업에 없음(동작)
- #45 진행 수가 없을 때 미정 진행 막대 — 목업에 없음
- #51 재큐잉 시각 없을 때 "곧 다시 시도" — 목업에 없음
- #56 잡을 받기 전 조회 오류(`job.error`) — 목업에 없음
- #61 잡 폴링 2초 — 목업에 없음(동작)
- (참고) `job.requeuedDegradedDaily`는 G0(region.bootstrap 잡)에서 나오지 않아 이 표에 넣지 않음 — Ops·Market 표에서 다룸

## 새로 더한 것 (기존에 없던 것)

| # | 새 기능 | 위치 (보드 · 섹션) | 비고 |
|---|---|---|---|
| N1 | 단계 안내 1 찾기 → 2 확인 → 3 시작 → 4 진행 | RegionNew · 머리 단계 목록 | 표시만 |
| N2 | 후보 개수 표시 "후보 9개" | "1 지역 찾기" 검색칸 아래 | 서버 응답 길이 |
| N3 | "'법정동'과 '행정동'은 무엇이 다른가요?" `?` 설명 버튼 | "1 지역 찾기" | 용어 설명 팝오버 |
| N4 | 종류·일치 정도 범례 줄 | "1 지역 찾기" 목록 아래 | |
| N5 | 칩 안내 "칩을 누르면 빠져요" | "2 고른 지역 확인 · 이름" | |
| N6 | 이름 칸 안내 "홈 화면 위쪽 지역 고르기에 이 이름으로 나와요" | "2 …" | |
| N7 | 시작 버튼에 지역 이름 넣기 "'송도' 분석 시작" | "3 분석 시작" | 문구만 |
| N8 | 공개 자료 안내 "공고·실거래·통계 같은 공개 자료만 모아요. 처음에는 몇 분에서 수십 분…" | "3 분석 시작" | |
| N9 | 진행 머리말 "'송도' 지역 자료를 모으고 있어요" | "4 분석 진행 상황" | |
| N10 | 안내 "이 창을 닫아도 분석은 계속돼요. 끝나면 '분석이 끝났어요' 알림이 떠요." | "4 분석 진행 상황" | |
