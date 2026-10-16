# 대응표 — G0-2 생활권 편집 (`/regions/:id/living-areas`) → LivingAreas.dc.html

소스: `frontend/src/pages/living-areas/index.tsx`(LivingAreasPage·Editor·AreaCard·validate·moveCodes), `RegionExpandPanel.tsx`, 공통 `components/JobProgress.tsx`(PublishJobProgress), `components/FactCell.tsx`, `pages/_shared`(QueryState·Section·useDebounced·enumText), `app/toast.tsx`, 문자열 `i18n/ko.json`(`page.G0_2.*`, `page.G0.*` 일부, `page.common.*`, `app.*`, `auth.readOnlyHint`).
보드: `boards/LivingAreas.dc.html`(섹션: 머리 "인천을 어떤 동네 묶음으로 볼까요?" · 옮기기 도구줄 · "생활권 카드" · 저장 줄 · "지역 범위를 넓히거나 줄일까요?" · "펼친 모습 · 다른 상태").
머리줄(지역·기준일 선택)은 Shell 보드에서 다룬다. 발행 진행의 결과 문구(막힘·실패·멈춤 등)는 Market 보드 "작업 진행 · 상태 모음"에 모아 그렸다고 보드에 적혀 있다.

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 1 | 화면 제목 h1 (`index.tsx` · `page.G0_2.title` "생활권 편집") | LivingAreas · 머리 h1 "인천을 어떤 동네 묶음으로 볼까요?" (브레드크럼·탭 제목 "생활권 나누기") | 생활권 편집 → 생활권 나누기 / {지역}을 어떤 동네 묶음으로 볼까요? | 있음 | `LA11` 머리: '생활권이 뭐예요?' 한 줄 답이 맨 위(지역을 받기 전부터) · 현재 위치 줄 · 생활권·법정동 개수 · #range 링크<br>`RT` 라우트 10개 — G0-2 /regions/rg_1/living-areas → 제목을 렌더한다<br>`E2P` G0-2 생활권 편집: 생활권 카드 · 세대수 · 저장 |
| 2 | 안내 문단 (`page.G0_2.intro` "법정동을 옮겨 생활권을 나누거나 묶습니다. 모든 법정동은 정확히 한 생활권에…") | LivingAreas · 머리 "동(법정동)을 옮겨 묶음을 나누거나 합쳐요. 모든 동은 꼭 한 생활권에만…" | 문구 쉬운 말로 | 있음 | `LA11` 머리: '생활권이 뭐예요?' 한 줄 답이 맨 위(지역을 받기 전부터) · 현재 위치 줄 · 생활권·법정동 개수 · #range 링크 |
| 3 | 화면 로딩 (`QueryState` · `app.loading` "불러오는 중…") | LivingAreas · 펼친 모습 "화면 전체" "불러오는 중…" | — | 있음 | `R3F2` (F15 503 materialize_pending → 준비 중 → 자동 재시도) · `SH` QueryState 공용(coverage-Shell) |
| 4 | 준비 중 503 materialize_pending (`page.common.materializePending`) + 다시 시도 버튼 (`app.retry`) | LivingAreas · 펼친 모습 "화면 전체" "준비 중 — 잠시 뒤 자동으로 다시 불러와요 [다시 시도]" | — | 있음 | `R3F2` (F15 503 materialize_pending → 준비 중 → 자동 재시도) · `SH` QueryState 공용(coverage-Shell) |
| 5 | 조회 오류 (`queryErrorText` · `page.common.loadError`) | LivingAreas · 펼친 모습 "화면 전체" "불러오지 못했어요: [오류 내용]" | — | 있음 | `R3F2` (F15 503 materialize_pending → 준비 중 → 자동 재시도) · `SH` QueryState 공용(coverage-Shell) |
| 6 | 옮길 생활권 선택 라벨·select (`page.G0_2.moveTo` "선택한 법정동 옮길 생활권", 기본 = 첫 생활권) | LivingAreas · 옮기기 도구줄 "옮길 생활권" select | 선택한 법정동 옮길 생활권 → 옮길 생활권 | 있음 | `LA` 생활권 추가 → 법정동 선택 후 이동 → 이름 변경 → 저장(PUT) → 잡 진행<br>`R3F2` F4 생활권 PUT 202 → 발행 대기 안내 + 잡 진행 |
| 7 | select 옵션 = 생활권 이름(이름 없으면 key) | LivingAreas · 도구줄 select 옵션(제물포구 … 새 생활권 1) | — | 있음 | `LA` 생활권 추가 → 법정동 선택 후 이동 → 이름 변경 → 저장(PUT) → 잡 진행 |
| 8 | 옮기기 버튼 (`page.G0_2.move` "옮기기", 고른 동 없으면 꺼짐) | LivingAreas · 도구줄 "이리로 옮기기" + 펼친 모습 "'이리로 옮기기'는 고른 동이 없으면 꺼져요." | 옮기기 → 이리로 옮기기 | 있음 | `LA11` 도구줄: 고른 동 수 · 고른 동이 없으면 "이리로 옮기기" 꺼짐 · 고른 동이 있는 카드는 강조<br>`LA` 생활권 추가 → 법정동 선택 후 이동 → 이름 변경 → 저장(PUT) → 잡 진행 |
| 9 | 끌어다 놓기 안내 (`page.G0_2.dropHint` "법정동을 끌어다 놓거나, 선택 후 옮기세요") | LivingAreas · 도구줄 "동을 끌어다 다른 카드에 놓아도 돼요" | 문구 쉬운 말로 | 있음 | `LA11` 도구줄: 고른 동 수 · 고른 동이 없으면 "이리로 옮기기" 꺼짐 · 고른 동이 있는 카드는 강조 |
| 10 | 생활권 추가 버튼 (`page.G0_2.add` "생활권 추가") | LivingAreas · 도구줄 "+ 생활권 추가" | — | 있음 | `LA` 생활권 추가 → 법정동 선택 후 이동 → 이름 변경 → 저장(PUT) → 잡 진행<br>`R3F2` F4 생활권 PUT 202 → 발행 대기 안내 + 잡 진행 |
| 11 | 새 생활권 이름 자동 번호 (`page.G0_2.newName` "새 생활권 {n}") | LivingAreas · 카드 "새 생활권 1" + 펼친 모습 "'새 생활권 2', '새 생활권 3' 이름으로 생겨요" | — | 있음 | `LA` 생활권 추가 → 법정동 선택 후 이동 → 이름 변경 → 저장(PUT) → 잡 진행<br>`LA11` 끌어다 놓기: 고르지 않은 동은 그 동만, 고른 동을 끌면 고른 동 전부 옮기고 고른 표시를 지운다(#26~#28) |
| 12 | 미배정 법정동 블록 aria-label (`page.G0_2.unassigned` "어느 생활권에도 없는 법정동 {n}개", 첫 카드 위) | LivingAreas · 펼친 모습 "어느 생활권에도 없는 동이 있을 때" "어느 생활권에도 없는 동 [n]개 · 카드로 옮겨 주세요" + "이 블록은 첫 카드 위에 나와요" | 법정동 → 동 | 있음 | `LA` 모든 법정동은 정확히 한 생활권에 (미배정 계산) · `LA11` 끌어다 놓기: 고르지 않은 동은 그 동만, 고른 동을 끌면 고른 동 전부 옮기고 고른 표시를 지운다(#26~#28) |
| 13 | 미배정 동 목록(체크박스·끌기 가능) | LivingAreas · 펼친 모습 미배정 블록 체크박스 [동 이름][동 코드] | — | 있음 | `LA` 모든 법정동은 정확히 한 생활권에 |
| 14 | 생활권 카드 격자 section aria-label=이름 | LivingAreas · "생활권 카드" 카드 11+1장 | — | 있음 | `LA` 세대수(Fact) 표시 · 법정동이 있으면 삭제 불가<br>`ACC` G0-2 /regions/1/living-areas: 생활권 카드(이름 입력)와 저장 버튼 |
| 15 | 카드 이름 입력칸 (라벨 sr-only `page.G0_2.areaName` "생활권 이름") | LivingAreas · 카드마다 라벨 "생활권 이름" + 입력칸 | 라벨이 보이게 바뀜 | 있음 | `LA` 세대수(Fact) 표시 · 법정동이 있으면 삭제 불가<br>`ACC` G0-2 /regions/1/living-areas: 생활권 카드(이름 입력)와 저장 버튼<br>`E2P` G0-2 생활권 편집: 생활권 카드 · 세대수 · 저장 |
| 16 | 생활권 삭제 버튼 (`page.G0_2.delete` "생활권 삭제", 빈 카드만) | LivingAreas · 카드 "지우기" + 펼친 모습 "카드 · 지우기 버튼" [빈 생활권] 켜짐 | 생활권 삭제 → 지우기 | 있음 | `LA` 세대수(Fact) 표시 · 법정동이 있으면 삭제 불가<br>`LA11` 끌어다 놓기: 고르지 않은 동은 그 동만, 고른 동을 끌면 고른 동 전부 옮기고 고른 표시를 지운다(#26~#28) |
| 17 | 삭제 꺼짐 title (`page.G0_2.deleteDisabled` "법정동이 남아 있으면 삭제할 수 없습니다") | LivingAreas · 카드 "지우기" title "법정동이 남아 있으면 지울 수 없어요" + 펼친 모습 "마우스를 올리면: …" | — | 있음 | `LA11` 저장 줄: 생활권 저장 · 안내 · 변경 표시, 읽기 전용이면 꺼지고 이유를 보인다 |
| 18 | 세대수 칸 (`page.G0_2.households` "세대수" + `FactCell` unit households, 라벨 배지·출처) | LivingAreas · 카드 "세대수 51,419 추정" + 아래 "밑줄 점선 숫자를 누르면 출처가 열려요" | — | 있음 | `LA` 세대수(Fact) 표시 · 법정동이 있으면 삭제 불가<br>`E2P` G0-2 생활권 편집: 생활권 카드 · 세대수 · 저장 |
| 19 | 세대수 없음 (FactCell `emptyReason` `page.common.none` "없음" — 새 생활권) | LivingAreas · 카드 "새 생활권 1" "세대수 없음" + 펼친 모습 "세대수를 모르는 새 생활권은 '없음'으로 보여요" | — | 있음 | `LA` 세대수(Fact) 표시 · 법정동이 있으면 삭제 불가 (새 생활권 '없음') |
| 20 | 카드 법정동 수 (`page.G0_2.dongs` "법정동" + `page.G0_2.dongCount` "법정동 {n}개") | LivingAreas · 카드 "법정동 51개" | — | 있음 | `LA11` 카드: 법정동은 처음 5개 + "나머지 n개 더 보기"(누르면 모두 · 접기) |
| 21 | 카드 안 동 목록 (모든 동을 다 보임) | LivingAreas · 카드 동 5개 + "나머지 46개 더 보기" 버튼 | 처음 5개만 보이고 더 보기로 접음 | 있음 | `LA11` 카드: 법정동은 처음 5개 + "나머지 n개 더 보기"(누르면 모두 · 접기) |
| 22 | 동 체크박스 aria-label (`page.G0_2.selectDong` "{name} 선택") | LivingAreas · 카드 동 체크박스 aria-label "만석동 고르기" | 선택 → 고르기 | 있음 | `LA` 생활권 추가 → 법정동 선택 후 이동 → 이름 변경 → 저장(PUT) → 잡 진행<br>`LA11` 도구줄: 고른 동 수 · 고른 동이 없으면 "이리로 옮기기" 꺼짐 · 고른 동이 있는 카드는 강조 |
| 23 | 동 이름 + 코드(이름이 코드와 다를 때만 코드 표시) | LivingAreas · 카드 동 줄 "만석동 2812510100" | — | 있음 | `LA11` 끌어다 놓기: 고르지 않은 동은 그 동만, 고른 동을 끌면 고른 동 전부 옮기고 고른 표시를 지운다(#26~#28) |
| 24 | 이름을 모를 때 코드만 표시 (`dongName` 폴백) | — | — | 있음(고침 LA-2 — 펼친 모습 "동 이름을 모를 때" 코드만 보이는 줄) | `LA11` 카드: 법정동은 처음 5개 + "나머지 n개 더 보기"(누르면 모두 · 접기) (이름 없는 동 = 코드만, 고르기 이름도 '코드 고르기') |
| 25 | 빈 카드 안내 (`EmptyState` · `page.G0_2.dropHint`) | LivingAreas · "새 생활권 1" 카드 "동을 여기로 끌어다 놓거나, 체크한 뒤 위에서 '이리로 옮기기'를 누르세요" | 문구 길게 | 있음 | `LA11` 끌어다 놓기: 고르지 않은 동은 그 동만, 고른 동을 끌면 고른 동 전부 옮기고 고른 표시를 지운다(#26~#28) |
| 26 | 동 끌어다 다른 카드에 놓기 (draggable·onDrop) | LivingAreas · 도구줄 "동을 끌어다 다른 카드에 놓아도 돼요" | — | 문구로만(고침 LA-3 — "구현 때 유지" 상자에도 적음) | `LA11` 끌어다 놓기: 고르지 않은 동은 그 동만, 고른 동을 끌면 고른 동 전부 옮기고 고른 표시를 지운다(#26~#28) |
| 27 | 고른 동을 끌면 고른 동 전부를 옮김 (`selected.has(code) ? [...selected]`) | — | — | 문구로만(고침 LA-3 — "구현 때 유지" 상자) | `LA11` 끌어다 놓기: 고르지 않은 동은 그 동만, 고른 동을 끌면 고른 동 전부 옮기고 고른 표시를 지운다(#26~#28) |
| 28 | 옮긴 뒤 고른 표시 지움 (`setSelected(new Set())`) | — | — | 문구로만(고침 LA-3 — "구현 때 유지" 상자) | `LA11` 끌어다 놓기: 고르지 않은 동은 그 동만, 고른 동을 끌면 고른 동 전부 옮기고 고른 표시를 지운다(#26~#28)<br>`LA` 생활권 추가 → 법정동 선택 후 이동 → 이름 변경 → 저장(PUT) → 잡 진행 |
| 29 | 저장 전 검사: 모든 동은 정확히 한 생활권 (`validate` — 미배정·중복·빈 이름) | LivingAreas · 펼친 모습 "저장 전에 막힐 때 · 저장 오류" "고칠 것이 있으면 꺼져요" | — | 있음 | `LA` 모든 법정동은 정확히 한 생활권에 |
| 30 | 저장 버튼 (`page.G0_2.save` "저장") | LivingAreas · 저장 줄 "생활권 저장" | 저장 → 생활권 저장 | 있음 | `LA` 생활권 추가 → 법정동 선택 후 이동 → 이름 변경 → 저장(PUT) → 잡 진행<br>`ACC` G0-2 /regions/1/living-areas: 생활권 카드(이름 입력)와 저장 버튼<br>`E2P` G0-2 생활권 편집: 생활권 카드 · 세대수 · 저장 |
| 31 | 저장 꺼짐: 읽기 전용·검사 실패·저장 중 (+ title `auth.readOnlyHint`) | LivingAreas · 펼친 모습 "읽기 전용 토큰이면 저장 버튼이 꺼지고 '읽기 전용 토큰으로는 저장·실행할 수 없어요'가 보여요" + 꺼진 버튼 | — | 있음 | `LA11` 저장 줄: 생활권 저장 · 안내 · 변경 표시, 읽기 전용이면 꺼지고 이유를 보인다 |
| 32 | 저장 안 한 변경 (`page.G0_2.dirty` "저장하지 않은 변경이 있습니다") | LivingAreas · 저장 줄 "저장하지 않은 변경이 있어요" | — | 있음 | `LA` 생활권 추가 → 법정동 선택 후 이동 → 이름 변경 → 저장(PUT) → 잡 진행<br>`LA11` 저장 → 저장 줄 아래 발행 진행(쓰기 토큰) |
| 33 | 중복 오류 role=alert (`page.G0_2.duplicated` "두 생활권 이상에 있는 법정동 {n}개") | LivingAreas · 펼친 모습 "두 생활권 이상에 들어 있는 동 [n]개" | — | 있음 | `LA` 모든 법정동은 정확히 한 생활권에 |
| 34 | 빈 이름 오류 role=alert (`page.G0_2.emptyName` "이름이 빈 생활권이 있습니다") | LivingAreas · 펼친 모습 "이름이 빈 생활권이 있어요" | — | 있음 | `LA` 모든 법정동은 정확히 한 생활권에 |
| 35 | 저장 오류 role=alert (`page.G0_2.saveError` "저장하지 못했습니다: {detail}") | LivingAreas · 펼친 모습 role=alert "저장하지 못했어요: [서버 오류 내용]" | — | 있음 | `LA` 422 → 필드 오류 표시 |
| 36 | 서버 422 칸별 오류 목록 (`fieldErrors` "loc: msg") | LivingAreas · 펼친 모습 "- [칸 위치]: [칸 오류 내용]" | — | 있음 | `LA` 422 → 필드 오류 표시 |
| 37 | 저장 성공 토스트 (`page.G0_2.saved` "생활권을 저장했습니다 — 재판정 잡이 등록됐습니다") | LivingAreas · 펼친 모습 "생활권을 저장한 뒤" "생활권을 저장했어요 — 다시 판정하는 작업을 등록했어요" | 재판정 잡 → 다시 판정하는 작업 | 있음 | `LA11` 저장 → 저장 줄 아래 발행 진행(쓰기 토큰) |
| 38 | 저장 뒤 발행 진행 PublishJobProgress (job_id) — 작업 이름·상태·진행 | LivingAreas · 펼친 모습 "생활권을 저장한 뒤" role=status "작업 진행 [작업 이름] 실행 중 [n]/[m] · 단계 [단계 이름]" | — | 있음(고침 LA-1 — 진행 수가 없을 때 줄무늬 미정 막대 추가) | `LA` 생활권 추가 → 법정동 선택 후 이동 → 이름 변경 → 저장(PUT) → 잡 진행<br>`LA11` 저장 → 저장 줄 아래 발행 진행(쓰기 토큰)<br>`R3F2` F4 생활권 PUT 202 → 발행 대기 안내 + 잡 진행 |
| 39 | 발행 대기 안내 (`job.publishPending` "작업이 끝나 새 리비전이 발행될 때까지 화면은 지금 발행 리비전을 보입니다") | LivingAreas · 펼친 모습 "새 수정본이 발행될 때까지 화면은 지금 수정본을 보여요" + 저장 줄 "끝날 때까지 지금 화면 그대로예요" | 리비전 → 수정본 | 있음 | `R3F2` F4 생활권 PUT 202 → 발행 대기 안내 + 잡 진행 |
| 40 | 발행 완료 (`job.publishDone`) | LivingAreas · 펼친 모습 "끝나면 '새 수정본이 발행됐어요'" | — | 있음 | `R3D` G1 재판정 잡 done → 리비전 목록 갱신 → ready 폴링 → published → 헤더·대시보드가 리비전 2 |
| 41 | 발행 막힘·실패·멈춤·미룸·재등록 등 결과 문구 (`job.publishBlocked*`·`publishFailed`·`publishExpired`·`publishChainCapped`·`publishDeferred`·`publishRedeferred`) | Market · "작업 진행 · 상태 모음" (LivingAreas 보드: "발행이 막히거나 실패하면 이유가 이 칸에 나와요 (지역 시장 보드 … 와 같아요)") | — | 다른 보드(Market) | coverage-Market.md 행의 테스트(PublishJobProgress 결과 문구) |
| 42 | 지역 범위 확장 Section (`RegionExpandPanel` · `page.G0_2.expand.title` "지역 범위 확장(지역 추가)") | LivingAreas · "지역 범위를 넓히거나 줄일까요?" (id=range) "(공식 이름: 지역 범위 확장)" | 지역 범위 확장(지역 추가) → 지역 범위를 넓히거나 줄일까요? | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행<br>`E2P` G0-2 생활권 편집: 생활권 카드 · 세대수 · 저장<br>`LA11` 지역 범위: 안내 · 마지막 하나는 뺄 수 없다는 title · 후보 없음 문구 |
| 43 | 범위 확장 안내 (`page.G0_2.expand.intro` "지금 지역 선택에 시도·시군구·동을 더하거나 뺍니다. 저장하면…'지역 추가' 장…") | LivingAreas · "지역 범위를 …" 안내 문단 | 리비전 → 수정본 | 있음 | `LA11` 지역 범위: 안내 · 마지막 하나는 뺄 수 없다는 title · 후보 없음 문구 |
| 44 | 현재 선택 목록 ul aria-label (`page.G0_2.expand.current` "현재 지역 선택") | LivingAreas · "지역 범위를 …" "지금 고른 곳" | 현재 지역 선택 → 지금 고른 곳 | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행<br>`RX` 선택이 하나뿐이면 뺄 수 없다 |
| 45 | 선택 배지 "{이름} · {종류}" (`page.common.candidateKind.*`) | LivingAreas · "지금 고른 곳" "인천광역시 시도" | — | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행 |
| 46 | 새로 더한 선택 강조 (`data-added`, Badge strong) | LivingAreas · "지금 고른 곳" "경기도 김포시 시군구 · 새로 추가" | 색 강조 → "새로 추가" 글자 | 있음 | `LA11` 지역 범위 저장 → 토스트 · 새로 추가 표시 · 잡 안내 · 끝나면 다시 읽는다는 안내 |
| 47 | 선택 빼기 × 버튼 (aria-label `page.G0_2.expand.remove` "{name} 빼기") | LivingAreas · "지금 고른 곳" × 버튼 aria-label "경기도 김포시 빼기" | — | 있음 | `RX` 선택이 하나뿐이면 뺄 수 없다 |
| 48 | 마지막 하나는 뺄 수 없음(버튼 꺼짐) | LivingAreas · "지금 고른 곳" 꺼진 × title "마지막 하나는 뺄 수 없어요" + 펼친 모습 "하나만 남으면 뺄 수 없어요" | — | 있음 | `RX` 선택이 하나뿐이면 뺄 수 없다<br>`LA11` 지역 범위: 안내 · 마지막 하나는 뺄 수 없다는 title · 후보 없음 문구 |
| 49 | 지역 이름 입력칸 (`page.G0_2.expand.name` "지역 이름", 읽기 전용이면 꺼짐) | LivingAreas · "지역 범위를 …" "지역 이름" 입력칸 | — | 있음 | `RX` 이름만 바꿔도 저장할 수 있고 본문에 name 이 실린다 |
| 50 | 지역 이름 최대 100자 (`maxLength={100}`) | — | — | 문구로만(고침 LA-3 — "구현 때 유지" 상자, 입력칸 maxlength=100) | `RX` 이름만 바꿔도 저장할 수 있고 본문에 name 이 실린다 (maxLength=100 속성) |
| 51 | 추가할 지역 검색칸 (`page.G0_2.expand.search` "추가할 지역 검색", placeholder `page.G0.searchPlaceholder`) | LivingAreas · "더할 곳 찾기" 입력칸 placeholder "2글자 이상" | 추가할 지역 검색 → 더할 곳 찾기 | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행<br>`R3F2` F5 지역 선택 PATCH 202 → 발행 대기 안내 + region.expand 진행 |
| 52 | 검색 2자 이상 + 300ms 디바운스 | — | — | 문구로만(고침 LA-3 — "구현 때 유지" 상자) | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행 |
| 53 | 후보 없음 (`page.G0.noCandidates`) | LivingAreas · 펼친 모습 "범위 찾기 · 다른 상태" "일치하는 후보가 없어요" | — | 있음 | `LA11` 지역 범위: 안내 · 마지막 하나는 뺄 수 없다는 title · 후보 없음 문구 |
| 54 | 추가 후보 목록 ul aria-label (`page.G0_2.expand.candidates` "추가 후보") — 이름·종류 배지·법정동 수 | LivingAreas · "더할 곳 찾기" 아래 후보 3줄 "경기도 김포시 시군구 법정동 72개" | — | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행 |
| 55 | 후보 추가 버튼 (`page.G0_2.expand.add` "추가") | LivingAreas · 후보 줄 "추가" | — | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행 |
| 56 | 이미 있는 후보 (`page.G0_2.expand.have` "이미 있음", 꺼짐) | LivingAreas · 후보 줄 꺼진 "이미 있음" | — | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행 |
| 57 | 저장 전 바뀐 점 (`page.G0_2.expand.diff` "추가 {added} · 제거 {removed} — 저장하지 않음") | LivingAreas · "추가 1 · 빼기 0 — 아직 저장 안 함" | 제거 → 빼기 | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행<br>`E2W8` D11-7 지역 확장: 시군구 추가 → PATCH → added·change_event·region.expand 잡 |
| 58 | 범위 저장 버튼 (`page.G0_2.expand.submit` "범위 저장 → 새 리비전 재판정") | LivingAreas · "범위 저장하고 새 수정본에서 다시 판정" | 문구 쉬운 말로 | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행<br>`E2W8` D11-7 지역 확장: 시군구 추가 → PATCH → added·change_event·region.expand 잡 |
| 59 | 범위 저장 꺼짐: 바뀐 것 없음·읽기 전용·저장 중 (+ title `auth.readOnlyHint`) | LivingAreas · 펼친 모습 "읽기 전용이면 이름 칸·추가·빼기·저장 버튼이 꺼져요. 바뀐 것이 없으면 저장 버튼이 꺼져요." | — | 문구로만 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행<br>`RX` 선택이 하나뿐이면 뺄 수 없다 |
| 60 | 범위 저장 오류 role=alert (`page.common.loadError`) | LivingAreas · 펼친 모습 "불러오지 못했어요: [서버 오류 내용]" | — | 있음 | `RX` 서버 409(선택이 그대로) → detail 을 보인다 |
| 61 | 범위 저장 토스트 (`page.G0_2.expand.saved` "지역 범위를 저장했습니다 — 새 리비전 재판정 잡이 등록됐습니다") | LivingAreas · 펼친 모습 "범위를 저장한 뒤" "지역 범위를 저장했어요 — 새 수정본에서 다시 판정하는 작업을 등록했어요" | — | 있음 | `LA11` 지역 범위 저장 → 토스트 · 새로 추가 표시 · 잡 안내 · 끝나면 다시 읽는다는 안내 |
| 62 | 이름만 바꾼 토스트 (`page.G0_2.expand.savedNameOnly` "지역 이름만 바꿨습니다 — 재판정 없음") | LivingAreas · 펼친 모습 "이름만 바꿨을 때" "지역 이름만 바꿨어요 — 다시 판정하지 않아요" | — | 있음 | `R3D` PATCH /regions 이름만 변경 → change_event·job_id null → 잡 진행 없이 "이름만 바뀜" |
| 63 | 저장 결과 (`page.G0_2.expand.result` "저장됨 — 추가 {added} · 제거 {removed}") | LivingAreas · 펼친 모습 "저장됨 — 추가 [n] · 빼기 [n]" | — | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행<br>`E2W8` D11-7 지역 확장: 시군구 추가 → PATCH → added·change_event·region.expand 잡 |
| 64 | 추가·제거한 이름 (`page.G0_2.expand.addedNames` "추가: {names}", `removedNames` "제거: {names}") | LivingAreas · 펼친 모습 "추가: [추가한 곳 이름] · 빼기: [뺀 곳 이름]" | 제거 → 빼기 | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행 |
| 65 | 변경 이벤트 심각도 배지 + 내용 (`page.common.severity.*` + `change_event.new_text`) | LivingAreas · 펼친 모습 "중요 [바뀐 내용]" | — | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행 |
| 66 | 잡 안내 (`page.G0_2.expand.jobHint` "새 리비전에서 후보 전체 판정기 순위 다시 매기기 1회 + 보고서 '지역 추가' 장") | LivingAreas · 펼친 모습 "새 수정본에서 모든 후보의 판정기 순위를 한 번 다시 매기고, 보고서에 '지역 추가' 장을 만들어요" | — | 있음 | `LA11` 지역 범위 저장 → 토스트 · 새로 추가 표시 · 잡 안내 · 끝나면 다시 읽는다는 안내 |
| 67 | 범위 저장 뒤 발행 진행 PublishJobProgress | LivingAreas · 펼친 모습 "범위를 저장한 뒤"(진행 칸은 생활권 저장 뒤와 같은 모양 — 따로 그리지 않음) | — | 문구로만 | `R3F2` F5 지역 선택 PATCH 202 → 발행 대기 안내 + region.expand 진행 |
| 68 | 잡 끝나면 기준일 목록·사실 화면 다시 읽기 (`invalidateQueries(snapshots)`, `invalidateFactViews`) | LivingAreas · 펼친 모습 "작업이 끝나면 기준일 목록과 화면 숫자를 새로 불러와요" | — | 문구로만 | `LA11` 지역 범위 저장 → 토스트 · 새로 추가 표시 · 잡 안내 · 끝나면 다시 읽는다는 안내 (안내 문구) · `R3F2` F5 지역 선택 PATCH 202 → 발행 대기 안내 + region.expand 진행 |
| 69 | 이름만 + 발행 리비전 있음 (`page.G0_2.expand.nameOnlyPublish` "…이름이 발행 리비전 보고서(표지·제목)에 들어가 발행 작업이 등록됐습니다") | LivingAreas · 펼친 모습 "발행된 수정본이 있으면: … 발행 작업을 등록했어요 (+ 진행 막대)" | — | 있음 | `R3I2` 화면: 이름만 202 → 이름만 안내 + 발행 진행(재판정 안내 아님)<br>`E2W10` F6 지역 이름만 변경 → 202 + snapshot.publish → 이름만 안내 + 발행 → worker → 발행됨 |
| 70 | 이름만 + 발행 리비전 없음 (`page.G0_2.expand.nameOnly` "…재판정이 없고, 발행할 리비전이 없어 발행 작업도 없습니다(이름만 바뀜)") | LivingAreas · 펼친 모습 "발행된 수정본이 없으면: … 다시 판정도, 발행 작업도 없어요 (이름만 바뀜)" | — | 있음 | `R3D` PATCH /regions 이름만 변경 → change_event·job_id null → 잡 진행 없이 "이름만 바뀜" |
| 71 | 저장 뒤 선택·이름을 서버 응답 값으로 맞춤 | — | — | 문구로만(고침 LA-3 — "구현 때 유지" 상자) | `RX` 이름만 바꿔도 저장할 수 있고 본문에 name 이 실린다<br>`RX` 서버 409 뒤 지역을 다시 받는다(화면이 본 선택이 낡았다 — 4차 minor) |
| 72 | 화면의 지역명은 서버 값만 사용(하드코딩 없음) | LivingAreas · 모든 이름이 실데이터 | — | 있음 | `LA11` 머리: '생활권이 뭐예요?' 한 줄 답이 맨 위(지역을 받기 전부터) · 현재 위치 줄 · 생활권·법정동 개수 · #range 링크 (지역 이름 = 서버 값) |
| 73 | 미사용 문구 `page.G0_2.supplyRef` "공급 기준치" | — | — | 빠짐(현재 코드에서 쓰지 않는 문구 — Coverage 보드 "그림으로 그리지 않은 것"에 명시) | — (쓰지 않는 문구 — 그리지 않음, 빠짐 유지) |
| 74 | API `GET /regions/{id}` (`useRegion`) | LivingAreas · 화면 전체(호출 주체) | — | 있음 | `LA` 세대수(Fact) 표시 · 법정동이 있으면 삭제 불가<br>`LA11` 머리: '생활권이 뭐예요?' 한 줄 답이 맨 위(지역을 받기 전부터) · 현재 위치 줄 · 생활권·법정동 개수 · #range 링크 |
| 75 | API `PUT /regions/{id}/living-areas` {living_areas[{id,name,legal_dong_codes}]} (`useUpdateLivingAreas`) | LivingAreas · 저장 줄 "생활권 저장"(호출 주체) | — | 있음 | `LA` 생활권 추가 → 법정동 선택 후 이동 → 이름 변경 → 저장(PUT) → 잡 진행 |
| 76 | API `GET /regions/resolve?q=` (`useResolveRegion`) | LivingAreas · "더할 곳 찾기"(호출 주체) | — | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행 |
| 77 | API `PATCH /regions/{id}` {selections, name?} (`useUpdateRegionSelections`) | LivingAreas · "범위 저장하고 새 수정본에서 다시 판정"(호출 주체) | — | 있음 | `RX` 후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행<br>`RX` 이름만 바꿔도 저장할 수 있고 본문에 name 이 실린다 |
| 78 | API `GET /jobs/{id}` 사슬 + `GET /regions/{id}/snapshots` (PublishJobProgress·useSnapshot) | LivingAreas · 펼친 모습 "생활권을 저장한 뒤" 진행 칸(호출 주체) | — | 있음 | `R3F2` F4 생활권 PUT 202 → 발행 대기 안내 + 잡 진행<br>`R3F2` F5 지역 선택 PATCH 202 → 발행 대기 안내 + region.expand 진행 |

요약: 전체 78 · 있음 67 · 문구로만 9 · 다른 보드 1 (Market) · 빠짐 1 (2026-10-16 고침 반영 — fixes/fixes-LivingAreas.md)

빠짐 목록:
- #73 `page.G0_2.supplyRef` "공급 기준치" — 코드에서 쓰지 않는 문구(의도적 생략, 고치지 않음)
- 고침 전 빠짐 7개 중 #24 → 있음(고침 LA-2), #27·#28·#50·#52·#71 → 문구로만(고침 LA-3 "구현 때 유지" 상자)

## 새로 더한 것 (기존에 없던 것)

| # | 새 기능 | 위치 (보드 · 섹션) | 비고 | 테스트 |
|---|---|---|---|---|
| N1 | "생활권은 출퇴근·학교·장보기처럼…" 생활권 뜻 설명 | 머리 | | `LA11` 머리: '생활권이 뭐예요?' 한 줄 답이 맨 위(지역을 받기 전부터) · 현재 위치 줄 · 생활권·법정동 개수 · #range 링크 |
| N2 | 요약 "생활권 11곳 · 법정동 278개" | 머리 | 서버 값 개수 | `LA11` 머리: '생활권이 뭐예요?' 한 줄 답이 맨 위(지역을 받기 전부터) · 현재 위치 줄 · 생활권·법정동 개수 · #range 링크 |
| N3 | 범위 확장으로 내려가는 링크 "지역 범위 넓히기 · 줄이기 ↓" | 머리 | 같은 화면 앵커(#range) | `LA11` 머리: '생활권이 뭐예요?' 한 줄 답이 맨 위(지역을 받기 전부터) · 현재 위치 줄 · 생활권·법정동 개수 · #range 링크 |
| N4 | 고른 동 수 "2개 동을 골랐어요" | 옮기기 도구줄 | | `LA11` 도구줄: 고른 동 수 · 고른 동이 없으면 "이리로 옮기기" 꺼짐 · 고른 동이 있는 카드는 강조 |
| N5 | 카드 동 목록 5개만 보이고 "나머지 n개 더 보기" | 생활권 카드 | 접기 | `LA11` 카드: 법정동은 처음 5개 + "나머지 n개 더 보기"(누르면 모두 · 접기) |
| N6 | 저장 줄 화면 아래 고정("스크롤해도 화면 아래에 붙어 있어요") + 안내 "저장하면 새 수정본에서 점수를 다시 매겨요" | 저장 줄 | | `LA11` 저장 → 저장 줄 아래 발행 진행(쓰기 토큰) |
| N7 | 범위 확장 `?` 설명 버튼 | "지역 범위를 넓히거나 줄일까요?" | | 안 그림 — 진입 청크 예산(450kB) 때문에 설명 문구를 뺐다. 범위 안내 문단은 그대로(`LA11` 지역 범위: 안내 · 마지막 하나는 뺄 수 없다는 title · 후보 없음 문구) |
| N8 | 세대수 출처 안내 줄 "세대수는 주민등록 세대(2026-09-01)로 만든 추정 값이에요…" + "상대 비교 · 투자 권유 아님" | 범위 확장 아래 | | `LA11` 머리: '생활권이 뭐예요?' 한 줄 답이 맨 위(지역을 받기 전부터) · 현재 위치 줄 · 생활권·법정동 개수 · #range 링크 (바닥 안내 — 날짜는 서버 라벨·출처 창이 보임) |

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
