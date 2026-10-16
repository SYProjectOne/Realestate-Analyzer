# 대응표 — G7 데이터·운영 (`/ops`) → Ops.dc.html

소스: `frontend/src/pages/ops/index.tsx`, `Checklist.tsx`(ChecklistPanel·ChecklistTable·Calendar), `IntakeQueuePanel.tsx`, `HumanCheckForm.tsx`, `humanCheckRules.ts`, `SourceStatusTable.tsx`, `RejudgeQueue.tsx`, `JudgmentStatsPanel.tsx`(+ `pages/complex/JudgmentsTab.tsx` JudgmentTable), `ClaimsPanel.tsx`, `BoundaryList.tsx`, `SharePanel.tsx`, 공통 `components/JobProgress.tsx`·`IntakeBadge.tsx`·`RawDocumentPreview.tsx`·`ExternalLink.tsx`·`CachedBadge.tsx`, `pages/_shared`(QueryState·Section·ScopeReason·schedule), `app/toast.tsx`, 문자열 `i18n/ko.json`(`page.G7.*`, `page.common.*`, `intake.*`, `job.*`, `page.G3.judgment.*`, `app.*`, `auth.readOnlyHint`).
보드: `boards/Ops.dc.html`(섹션: 머리 "오늘 확인할 것부터 볼까요?" · "오늘 확인할 것" 타일 · 메뉴 9칸 · ① "언제, 무엇을 확인해야 하나요?" · ② "접수 상태를 사람이 확인해야 하는 단지" · ③ "분양사무소에 확인한 내용을 남길까요?" · ④ "자료를 잘 모으고 있나요?" · ⑤ "자동 작업이 잘 돌고 있나요?" · ⑥ "최근 30일, 판정기를 얼마나 불렀나요?" · ⑦ "검증에서 어긋난 문장이 남아 있나요?" · ⑧ "지역 경계에 걸친 단지가 있나요?" · ⑨ "보기만 할 수 있는 링크를 만들까요?" · "펼친 모습 · 다른 상태").
전역 판정기 장애 띠(AppLayout)와 머리줄은 Shell 보드에서 다룬다.

## 화면 틀·공통 상태

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 1 | 화면 제목 h1 (`index.tsx` · `page.G7.title` "데이터·운영") | Ops · 머리 h1 "오늘 확인할 것부터 볼까요?" + "운영자용 화면 · 인천 · …" (메뉴 이름 "데이터·운영" 유지) | 데이터·운영 → 오늘 확인할 것부터 볼까요? | 있음 | ops/r11ops.test › 머리: 질문형 h1 + 운영자용 머리말(지역·기준일) + 안내 · routes.test › G7 /ops → 제목을 렌더한다 |
| 2 | 패널 9종을 한 화면에 세로로 나열(사람 확인 폼 맨 위) | Ops · 메뉴 9칸 + ①~⑨ 섹션("한 번에 한 묶음씩 보여요") | 순서 바뀜(사람 확인 → ③) | 있음 | ops/r11ops.test › 묶음 메뉴 9칸(쓰기 토큰) — 묶음마다 질문형 h2 · "이게 뭐예요?" · 머리말 번호 |
| 3 | 공통 로딩 (`QueryState` · `app.loading`) | Ops · 펼친 모습 "모든 묶음 공통 상태" "불러오는 중…" | — | 있음 | components/shell-components.test › 불러오는 중 = 뼈대 + "불러오는 중…" |
| 4 | 공통 조회 오류 (`page.common.loadError`) | Ops · 펼친 모습 "불러오지 못했어요: [설명]" | — | 있음 | components/shell-components.test › 일반 오류 = "불러오지 못했어요: 내용" + 잠시 뒤 + 다시 시도(N10) |
| 5 | 준비 중 503 + 다시 시도 (`page.common.materializePending`, `app.retry`) | Ops · 펼친 모습 "이 발행본의 화면 자료를 준비하는 중이에요…" + [다시 시도] | — | 있음 | r3f2.test › G1 대시보드: 503 동안 "준비 중", Retry-After 뒤 다시 불러 화면이 뜬다(공용 QueryState) |
| 6 | 스냅샷 없음 (`app.noSnapshot` — 주장·경계·대기열 패널) | Ops · 펼친 모습 "기준일이 없을 때: 아직 기준일이 없어요. 지역 분석이 끝나면 나타나요." | — | 있음 | ops/intakeQueue.test › 스냅샷 없음 · 빈 대기열 안내 |
| 7 | 읽기 전용 토큰: 쓰기 버튼·칸 꺼짐 + title (`auth.readOnlyHint`) | Ops · 펼친 모습 "읽기 전용 열쇠예요 — 저장·실행 버튼이 꺼져 있어요(버튼에 마우스를 올리면 …)" | 토큰 → 열쇠 | 있음 | share/share.test › 읽기 전용(공유) 토큰이면 패널이 없고 … · ops/humanCheck8.test › 읽기 전용(쓰기 불가)이면 복원 링크가 없다 |
| 8 | 지역 로딩 동안 소스 표 자리 미리 잡기 (`SOURCES_MIN_HEIGHT` min-h-96, CLS 방지) | — | — | 문구로만(고침 OP-13 — "구현 때 유지" 상자) | ops/r11ops.test › 지역 로딩 동안에도 수집 상태 자리를 미리 잡는다(min-h-96, CLS) |

## ① 일정·체크리스트 (ChecklistPanel · Calendar)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 9 | 체크리스트 Section·표 aria-label (`page.G7.checklist` "체크리스트") | Ops · ① "언제, 무엇을 확인해야 하나요?" 표 caption "체크리스트" | — | 있음 | ops/ops.test › 소스 상태 · 큐 · 체크리스트 · 캘린더 · 판정기 통계(30일) |
| 10 | 표 열: 종류 배지 (`page.G7.check.kind` · `page.G7.checkKind.*`) | Ops · ① 표 "종류" ("전매 가능 시작 추정", "청약 접수", "중도금 납부" …) | 법적 확인 → 직접 확인할 것, 중도금 → 중도금 납부, 만료(전매) → 전매 가능 시작 | 있음 | ops/ops.test › "사실 재확인" 항목이 표·캘린더에 종류 배지와 함께 보인다 |
| 11 | 표 열: 항목 = 제목 (`page.G7.check.title` "항목", 행 머리) | Ops · ① 표 "할 일" | 항목 → 할 일 | 있음 | ops/ops.test › 소스 상태 · 큐 · 체크리스트 …(체크리스트 표) · r3i2.test › 화면: 202 → 발행 진행(publish-job), 200 → "발행 작업 없음" 안내 |
| 12 | 표 열: 단지 (`page.G7.check.complex`) | Ops · ① 표 "단지" | — | 있음 | ops/ops.test › 소스 상태 · 큐 · 체크리스트 …(체크리스트 표) · r3i2.test › 화면: 202 → 발행 진행(publish-job), 200 → "발행 작업 없음" 안내 |
| 13 | 표 열: 기한 (`page.G7.check.due`, formatDate D±) / 없으면 (`page.G7.check.noDue` "기한 없음") | Ops · ① 표 "기한" ("10.19 D-4", "어제 지남", "오늘", "기한 없음") | — | 있음 | ops/ops.test › 소스 상태 · 큐 · 체크리스트 …(체크리스트 표) · r3i2.test › 화면: 202 → 발행 진행(publish-job), 200 → "발행 작업 없음" 안내 |
| 14 | 표 열: 상태 select 열림·완료·해당 없음 (`page.G7.check.status`, `page.G7.checkStatus.*`, aria-label "상태 · {제목}") | Ops · ① 표 "상태" select + 라벨 "상태 · {단지} {할 일}" | — | 있음 | r3i2.test › 화면: 202 → 발행 진행(publish-job), 200 → "발행 작업 없음" 안내(상태 select) |
| 15 | 상태 select 꺼짐: 읽기 전용·저장 중 (+ title) | Ops · 펼친 모습 "읽기 전용 열쇠예요 — 저장·실행 버튼이 꺼져 있어요" | — | 문구로만(고침 OP-13 — "구현 때 유지" 상자에도 적음) | r3i2.test › 목: 상태가 바뀌면 202 …(readOnly·pending disabled — 코드, 같은 useCanWrite 규칙은 claims/share 읽기 전용 테스트) |
| 16 | 표 열: 메모 (`page.G7.check.note`) | Ops · ① 표 "메모" ("자동 · 청약홈 청약 일정") | — | 있음 | ops/ops.test › "사실 재확인" 항목이 표·캘린더에 …(메모 칸) |
| 17 | 닫힌 항목 흐리게 (`status !== 'open'` → text-grayed) | — | — | 있음(고침 OP-2 — 닫힌 줄(해당 없음·완료) 흐리게 + "사람이 닫음" 줄 추가) | ops/r11ops.test › 닫힌 체크리스트 줄·꺼진 자료 줄은 흐리게(data 표시 + 회색) |
| 18 | 닫은 주체 배지 자동 (`page.G7.check.closedBy.auto` "자동 닫힘") + 뜻 (`closedByHint.auto`, title·sr-only) | Ops · ① 표 마지막 줄 "자동으로 닫힘 근거가 사라지거나 단지가 빠져 자동으로 닫았어요…" + 펼친 모습 "① 체크리스트 닫힘 표시" | 뜻을 보이는 글로 | 있음 | r3d.test › 닫힌 항목에 자동 닫힘·사람이 닫음 배지, 열린 항목엔 없다 · ops/r11ops.test › 닫힌 체크리스트 줄·꺼진 자료 줄은 흐리게 |
| 19 | 닫은 주체 배지 사람 (`closedBy.human` "사람이 닫음") + 뜻 (`closedByHint.human`) | Ops · 펼친 모습 "사람이 닫음 사람이 닫은 항목은 자동으로 다시 열지 않아요(…예외)" | — | 있음(고침 OP-2 — ① 표 마지막 줄에도 "사람이 닫음" 배지) | r3d.test › 닫힌 항목에 자동 닫힘·사람이 닫음 배지, 열린 항목엔 없다 · ops/r11ops.test › 닫힌 체크리스트 줄·꺼진 자료 줄은 흐리게 |
| 20 | 항목 없음 (`page.G7.check.none` "항목 없음") | Ops · 펼친 모습 "항목이 하나도 없으면: 항목 없음" | — | 있음 | components/shell-components.test › QueryState 빈 데이터 = 호출 측 문구 상자 |
| 21 | 상태 바꾸면 발행 잡 안내 (`page.G7.check.jobHint`) + PublishJobProgress | Ops · ① "상태를 바꾸면 이렇게 알려 줘요 예시" "체크리스트가 보고서(체크리스트·달력)에 들어가서, 보고서 반영 작업을 등록했어요." + role=progressbar | 발행 작업 → 보고서 반영 작업 | 있음 | r3i2.test › 화면: 202 → 발행 진행(publish-job), 200 → "발행 작업 없음" 안내 |
| 22 | 바뀐 것 없음 (`page.G7.check.unchanged`) | Ops · ① "또는: 저장했어요 — 바뀐 것이 없거나 반영할 수정본이 없어 반영 작업은 없어요." | — | 있음 | r3i2.test › 화면: 202 → 발행 진행(publish-job), 200 → "발행 작업 없음" 안내 |
| 23 | 캘린더 Section·목록 aria-label (`page.G7.calendar` "캘린더") | Ops · ① 달력 "2026년 10월 · 10건" + "10월 일정 날짜순" | 캘린더 → 달력 | 있음 | ops/r11ops.test › 달력은 체크리스트 묶음 안(달력 이름 목록 유지) · ops/ops.test › 소스 상태 · 큐 · 체크리스트 · 캘린더 … |
| 24 | 기한 있는 항목만, 날짜순, 월별 묶음 (`Calendar`) | Ops · ① "기한이 있는 항목만 달력에 나와요" + 달력 월 이동 + 날짜순 목록 | 월별 목록 → 월 달력 + 그 달 목록 | 있음 | ops/ops.test › 전매제한 종료 '만료' → '전매 가능 시작' + 계산 기준 줄, 다른 '만료'는 '기한 만료', 범례 |
| 25 | 캘린더 줄: 날짜 (formatDate) | Ops · ① 날짜순 목록 날짜 "10.14" | — | 있음 | ops/ops.test › 전매제한 종료 '만료' → '전매 가능 시작' + 계산 기준 줄, 다른 '만료'는 '기한 만료', 범례 |
| 26 | 캘린더 줄: 종류 배지 쉬운 말 (`scheduleKindText` · `page.common.scheduleKind.*`, 전매 종료 → `resaleOpen` "전매 가능 시작") | Ops · ① 날짜순 목록 종류 배지 ("전매 가능 시작"·"청약 접수"·"중도금 납부"·"계약"·"당첨자 발표") | — | 있음 | ops/ops.test › 전매제한 종료 '만료' → '전매 가능 시작' + 계산 기준 줄, 다른 '만료'는 '기한 만료', 범례 |
| 27 | 캘린더 줄: 단지 · 제목 (전매 종료면 "전매 가능 시작") | Ops · ① 날짜순 목록 이름 + 내용 | — | 있음 | ops/ops.test › 전매제한 종료 '만료' → '전매 가능 시작' + 계산 기준 줄, 다른 '만료'는 '기한 만료', 범례 |
| 28 | 캘린더 줄: 메모 (`item.note`) | Ops · ① 날짜순 목록 내용 "… · 공고문 납부 조건 10.0%" | — | 있음 | ops/ops.test › 전매제한 종료 '만료' → '전매 가능 시작' + 계산 기준 줄, 다른 '만료'는 '기한 만료', 범례 |
| 29 | 캘린더 줄: 계산 근거 둘째 줄 (`page.common.scheduleBasis` "계산 기준: {basis}") | Ops · ① "되팔 수 있게 되는 날 · 계산 기준: 당첨자 발표일 + 12개월" | — | 있음 | ops/ops.test › 전매제한 종료 '만료' → '전매 가능 시작' + 계산 기준 줄, 다른 '만료'는 '기한 만료', 범례 |
| 30 | 캘린더 줄 title = 서버 제목 전문 | Ops · ① "줄에 마우스를 올리면 원래 제목이 보여요" | — | 있음 | ops/ops.test › 전매제한 종료 '만료' → '전매 가능 시작' + 계산 기준 줄, 다른 '만료'는 '기한 만료', 범례 |
| 31 | 캘린더 종류 뜻 접이식 (`page.G7.calendarLegend.title` "종류 뜻", 데이터에 나온 종류만·처음 나온 순서) | Ops · ① details "종류 뜻 보기" + 펼친 모습 "① 달력 '종류 뜻' 펼친 모습" 9종 | 종류 뜻 → 종류 뜻 보기 | 있음 | ops/ops.test › 전매제한 종료 '만료' → … 범례 · wiring21.test › G7 캘린더·범례·체크리스트 종류 칸에 두 종류 |
| 32 | 종류 뜻 문구 (`page.G7.calendarLegend.kind.*`, `resaleOpen`) | Ops · 펼친 모습 "① 달력 '종류 뜻'" (전매 가능 시작·중도금 납부·계약·기한 만료·공고 예상·확인할 것·값 다시 확인·청약 접수·당첨자 발표) | 사실 재확인 → 값 다시 확인 | 있음 | ops/ops.test › 전매제한 종료 '만료' → … 범례 · wiring21.test › G7 캘린더·범례·체크리스트 종류 칸에 두 종류 |
| 33 | 기한 있는 항목 없음 (`page.G7.check.noDue` "기한 없음" — 달력 자리) | Ops · 펼친 모습 "기한 있는 항목이 없으면 달력 자리에: 기한 없음" | — | 있음 | ops/ops.test › 전매제한 종료 '만료' → …(기한 없으면 check.noDue — 코드) |
| 34 | API `GET /ops/checklist` (`useChecklist`) | Ops · ①(호출 주체) | — | 있음 | ops/ops.test › 소스 상태 · 큐 · 체크리스트 · 캘린더 · 판정기 통계(30일) |
| 35 | API `PATCH /ops/checklist/{id}` {status} (`usePatchChecklistItem`) | Ops · ① 상태 select(호출 주체) | — | 있음 | r3i2.test › 목: 상태가 바뀌면 202 + job_id(snapshot.publish 상태 있는 잡), 같은 값이면 200 + null |

## ② 접수 확인 대기열 (IntakeQueuePanel)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 36 | Section 제목 (`page.G7.iq.title` "접수 확인 대기열") | Ops · ② "접수 상태를 사람이 확인해야 하는 단지" (메뉴 "접수 확인 대기열") | — | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로 … · ops/r11ops.test › 묶음 메뉴 9칸 …(질문형 h2) |
| 37 | 구역 앵커 `#intake-queue` (다른 화면에서 `/ops#intake-queue`) | Ops · ② 섹션 id=s2 + 타일 링크 | 앵커 id 값은 보드에서 s2 — 구현 때 `intake-queue` 유지 | 있음(고침 OP-1 — 섹션 id를 intake-queue 로 바꾸고 "주소 앵커 유지" 표시) | ops/r11ops.test › 묶음 9개 · 앵커 #intake-queue · #human-check 는 기존 값 · ops/r11ops.test › 오늘 확인할 것 타일 4장 …(href #intake-queue) |
| 38 | 전체 건수 배지 (`page.G7.iq.total` "{n}건", 0이면 숨김) | Ops · ② "89건" | — | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로, 판정 대상 아님·미정은 접어 둔다 |
| 39 | 안내 (`page.G7.iq.intro`) | Ops · ② "이게 뭐예요?" 문단 | — | 있음 | ops/r11ops.test › 묶음 메뉴 9칸 … "이게 뭐예요?" |
| 40 | 지역·스냅샷 없음 (`app.noSnapshot`) | Ops · 펼친 모습 "기준일이 없을 때" | — | 있음 | ops/intakeQueue.test › 스냅샷 없음 · 빈 대기열 안내 · ops/intakeQueue.test › 스냅샷은 있는데 확인할 행이 없으면 없음 안내 |
| 41 | 발행 스냅샷 없음 (`page.G7.iq.noSnapshot` "발행된 스냅샷이 없습니다 — 지역 적재가 끝나면 대기열이 생깁니다") | Ops · 펼친 모습 "② … 발행된 기준일이 없으면: 아직 발행된 기준일이 없어요 — …" | — | 있음 | ops/intakeQueue.test › 스냅샷 없음 · 빈 대기열 안내 · ops/intakeQueue.test › 스냅샷은 있는데 확인할 행이 없으면 없음 안내 |
| 42 | 대기열 비었음 (`page.G7.iq.none` "확인할 접수 행이 없습니다") | Ops · 펼친 모습 "대기열이 비면: 확인할 접수 줄이 없어요" | — | 있음 | ops/intakeQueue.test › 스냅샷 없음 · 빈 대기열 안내 · ops/intakeQueue.test › 스냅샷은 있는데 확인할 행이 없으면 없음 안내 |
| 43 | 기준 줄 (`page.G7.iq.basis` "기준: {date} 스냅샷 · 리비전 {revision}") | Ops · ② "기준: 2026-10-15 기준일 (1번째 수정본) · 운영 기록" | 리비전 n → n번째 수정본 | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로, 판정 대상 아님·미정은 접어 둔다 |
| 44 | 분류별 접이식 + 분류 건수(서버 순서 그대로) | Ops · ② details 6개 + "건수" | — | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로, 판정 대상 아님·미정은 접어 둔다 |
| 45 | 처음 접어 두는 분류: 판정 대상 아님·접수 미정 (`COLLAPSED`) | Ops · ② "(판정 대상 아님) … 처음엔 접어 둬요" · "(접수 미정) … 처음엔 접어 둬요" | — | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로, 판정 대상 아님·미정은 접어 둔다 |
| 46 | 분류 수집 실패 (`page.G7.iq.category.collect_failed` + `categoryHint.collect_failed`) | Ops · ② "페이지를 못 받았어요 (수집 실패)" + 안내 문단 | 분류 이름 앞에 쉬운 말 | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로, 판정 대상 아님·미정은 접어 둔다 |
| 47 | 분류 공식 홈페이지 동일성 (`category.identity` + hint) | Ops · ② "이 단지 홈페이지가 맞는지 모르겠어요 (공식 홈페이지 확인)" + 안내 | 동일성 → 공식 홈페이지 확인 | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로, 판정 대상 아님·미정은 접어 둔다 |
| 48 | 분류 문구로 판단 불가 (`category.no_phrase` + hint "…스크린샷을 보고 입력하세요") | Ops · ② "페이지는 맞는데 접수 문구가 없어요 (문구로 판단 불가)" (접힌 상태 — 안내 문단은 그리지 않음) | — | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로, 판정 대상 아님·미정은 접어 둔다 |
| 49 | 분류 판정 미해결 (`category.unresolved` + hint) | Ops · ② "판정기가 정하지 못했어요 (판정 미해결)" + 요약 "화면 캡처·근거 페이지를 보고 입력하세요" | — | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로, 판정 대상 아님·미정은 접어 둔다 |
| 50 | 분류 판정 대상 아님 (`category.not_judged` + hint) | Ops · ② "점수 대상이 아니에요 (판정 대상 아님)" + "필요할 때만 확인" | — | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로, 판정 대상 아님·미정은 접어 둔다 |
| 51 | 분류 접수 미정 (`category.undecided` + hint) | Ops · ② "일정이 아직 안 정해졌어요 (접수 미정)" + "일정이 정해졌는지 확인" | — | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로, 판정 대상 아님·미정은 접어 둔다 |
| 52 | 분류 기타 (`category.other` + hint) | Ops · ② "정해진 묶음에 없는 새 이유는 '기타' 묶음으로 따로 모여요(지금 0건)" | — | 문구로만 | ops/intakeQueue.test › 모르는 사유(서버 other)도 그 사유 이름으로 보인다 — 화면은 사유를 해석하지 않는다 |
| 53 | 사유 묶음 제목 + 건수 (`page.G7.iq.groupCount` "{n}건", 사유 = 서버 문자열) | Ops · ② "연결 안 됨 (connect) · 8건" | — | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로, 판정 대상 아님·미정은 접어 둔다 |
| 54 | 항목 표 열: 단지 = G3 링크 (`page.G7.iq.col.complex`) | Ops · ② 표 "단지" 링크 | — | 있음 | ops/intakeQueue.test › 항목: G3 링크·접수 배지·HTTP·근거 페이지·스크린샷·판정 로그·반영 대기 |
| 55 | 사람 확인 입력됨 대기 배지 (`page.G7.iq.pending` "사람 확인 입력됨({value}, {date}) — 재판정·발행 대기") | Ops · 펼친 모습 "② 사람 확인을 넣고 기다리는 단지" | 재판정 → 다시 판정 | 있음 | ops/intakeQueue.test › 항목: G3 링크·접수 배지·HTTP·근거 페이지·스크린샷·판정 로그·반영 대기 |
| 56 | 항목 표 열: 접수 상태 IntakeBadge (`page.G7.iq.col.status`, 상태·사유·날짜·경로) | Ops · ② 표 "지금 접수 상태" "확인 불가(연결 안 됨, 10.15) 경로: 공식 팝업" | 접수 상태 → 지금 접수 상태 | 있음 | ops/intakeQueue.test › 항목: G3 링크·접수 배지·HTTP·근거 페이지·스크린샷·판정 로그·반영 대기 |
| 57 | 판정 로그 표식 (`page.G7.iq.judgment` "판정 로그 {ref}") | Ops · ② 표 "판정 기록 1328번 보기" 링크 | 판정 로그 → 판정 기록 n번 보기(링크로) | 있음 | ops/intakeQueue.test › 항목: G3 링크·접수 배지·HTTP·근거 페이지·스크린샷·판정 로그·반영 대기 |
| 58 | 항목 표 열: HTTP (`page.G7.iq.col.http`, 없으면 빈 칸) | Ops · ② 표 "응답 코드" ("200 열림", "응답 없음") | HTTP → 응답 코드, 빈 칸 → "응답 없음" | 있음 | ops/intakeQueue.test › 항목: G3 링크·접수 배지·HTTP·근거 페이지·스크린샷·판정 로그·반영 대기 |
| 59 | 항목 표 열: 확인 시각 (`page.G7.iq.col.checkedAt`) | Ops · ② 표 "확인한 때" | — | 있음 | ops/intakeQueue.test › 항목: G3 링크·접수 배지·HTTP·근거 페이지·스크린샷·판정 로그·반영 대기 |
| 60 | 항목 표 열: 근거 = 근거 페이지 외부 링크 (`page.G7.iq.col.evidence`, `page.G7.iq.evidence` "근거 페이지") | Ops · ② 표 "근거" "근거 페이지 ↗" + 도메인 | — | 있음 | ops/intakeQueue.test › 항목: G3 링크·접수 배지·HTTP·근거 페이지·스크린샷·판정 로그·반영 대기 |
| 61 | 근거 주소 없음 (`page.G7.iq.noEvidence` "근거 주소 없음") | — | — | 있음(고침 OP-6 — 펼친 모습 "② 근거 주소가 없는 줄") | ops/intakeQueue.test › 항목: …(evidence_url null → iq.noEvidence — 코드) · ops/intakeQueue.test › 모르는 사유(서버 other) … |
| 62 | 스크린샷 미리보기 (`page.G7.iq.screenshot` "스크린샷" + `RawDocumentPreview`) | Ops · ② 표 "화면 캡처 미리보기" 버튼 + 펼친 모습 "② 화면 캡처 미리보기 펼친 모습" | 스크린샷 → 화면 캡처 | 있음 | ops/intakeQueue.test › 항목: G3 링크·접수 배지·HTTP·근거 페이지·스크린샷·판정 로그·반영 대기 |
| 63 | 미리보기 상태: 열기·닫기·원문 저장·불러오는 중·실패·미리보기 안 되는 형식·내려받는 중·내려받기 실패 (`RawDocumentPreview`) | Ops · 펼친 모습 "[미리보기 닫기] [원문 파일 저장]" + "불러오는 동안 … 저장 실패: …" | — | 있음 | components/RawDocumentPreview.test › 열기 전에는 받지 않고 … · 저장 → fetch(Bearer) … · 실패하면 오류 문구 |
| 64 | 항목 표 열: 사람 확인 링크 (`page.G7.iq.col.action`, `page.G7.iq.act` "사람 확인 입력", title `page.G7.iq.actHint`) → 폼을 그 단지·접수 상태로 채움(hc_complex·hc_field) | Ops · ② 표 "사람 확인 입력" 링크 title "③ 사람 확인 입력 칸을 이 단지·접수 상태로 채워요" | — | 있음 | ops/intakeQueue.test › '사람 확인 입력' → 폼을 그 단지·접수 상태로 채움 → 저장하면 대기열에 반영 대기 |
| 65 | 링크 누르면 폼으로 스크롤 (`scrollIntoView`) | Ops · ③ "② 대기열에서 '…'로 채웠어요" (스크롤 동작은 적지 않음) | — | 문구로만(고침 OP-13 — "구현 때 유지" 상자에도 적음) | ops/intakeQueue.test › '사람 확인 입력' → 폼을 … 채움(scrollIntoView rAF) · ops/r11ops.test › 다른 화면에서 #human-check 로 들어오면 … 스크롤 |
| 66 | API `GET /ops/intake-queue?region_id=&snapshot_id=` (`useIntakeQueue`) | Ops · ②(호출 주체) | — | 있음 | ops/intakeQueue.test › 분류·사유별 건수 — 서버 순서 그대로 …(GET /ops/intake-queue) |
| 67 | API `GET /raw/{id}` (스크린샷 미리보기·저장) | Ops · ② 화면 캡처 미리보기(호출 주체) | — | 있음 | components/RawDocumentPreview.test › 저장 → fetch(Bearer) → 응답 파일 이름으로 저장 |

## ③ 사람 확인 입력 (HumanCheckForm · humanCheckRules)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 68 | Section·폼 aria-label (`page.G7.human` "사람 확인 입력") + 앵커 `#human-check` | Ops · ③ "분양사무소에 확인한 내용을 남길까요?" (메뉴 "사람 확인 입력", id=s3) | 앵커 id 값은 보드에서 s3 — 구현 때 `human-check` 유지 | 있음(고침 OP-1 — 섹션 id를 human-check 로 바꾸고 "주소 앵커 유지" 표시) | ops/r11ops.test › 묶음 9개 · 앵커 … #human-check 는 기존 값 · acceptance.test › G7 /ops: 소스 상태 표 + 사람 확인 입력 폼 |
| 69 | 안내 (`page.G7.humanIntro` "분양사무소 전화·방문 결과를 '사람 확인'으로 기록합니다") | Ops · ③ "이게 뭐예요? 전화·방문·이메일로 직접 확인한 값을 …" | 문구 늘림 | 있음 | ops/r11ops.test › 묶음 메뉴 9칸 … "이게 뭐예요?" |
| 70 | 단지 select (`page.G7.hc.complex` "단지", 빈 값 `page.common.none` "없음") | Ops · ③ "단지" select (빈 값 "고르세요") | 없음 → 고르세요 | 있음 | ops/ops.test › 필수값 없이 저장하면 막는다 |
| 71 | 필드 select 8종 (`page.G7.hc.field` "필드", `page.G7.hcField.*`) | Ops · ③ "무엇을 확인했나요?" 8개 옵션 | 필드 → 무엇을 확인했나요?, 전매 제한(개월) → 되팔기 제한 기간 (전매, 개월), 거주의무(개월) → 꼭 살아야 하는 기간 (거주의무, 개월) | 있음 | ops/humanCheck8.test › 필드 선택지 = 접수 상태 + 강등 가능한 사실 5개 + 기타 |
| 72 | 값: 접수 상태면 select 4종 (`page.G7.hc.value` "값", `intake.status.*`) | Ops · ③ "확인한 값" select "고르세요 · 접수 가능 · 접수 미정 · 접수 확인 불가 · 접수 불가" | 값 → 확인한 값 | 있음 | ops/ops.test › 사람 확인 저장 → 접수 배지 즉시 갱신 + 자동 등록 재판정(rejudge_job_id) 진행 |
| 73 | 값: 숫자 필드면 text 입력(inputMode decimal/numeric), 입주 예정이면 month 입력, maxLength 200 | Ops · ③ "숫자 항목을 고르면 입력 칸과 규칙 안내로 바뀌어요" + 규칙 표 "입주 예정 … 달력 칸" + 오류 예시 칸 | — | 있음 | ops/humanCheck8.test › 값 형·범위: 정수 필드 6.02 거부(절삭 금지), 개월 0~240, 입주 YYYY-MM, 계약금 0~100 |
| 74 | 필드별 값 안내 (`page.G7.hcHint.*` 최고 공급금액·입주 예정·전매·거주의무·계약금) | Ops · ③ "값을 이렇게 넣어 주세요" 표 | — | 있음 | ops/humanCheck8.test › 서버 허용 범위(계약 .8) …(hcHint) |
| 75 | 할인 안내 + 기준 타입 (`page.G7.hcHint.discount` / `discountBasis` "기준 타입 {type} 할인(원)…", 단지 상세의 `basis_type_code`) | Ops · ③ 규칙 표 "할인 기준 타입 [타입] 할인(원) — …" | — | 있음 | r3h2.test › 폼: 할인 칸 선택 → 값(쉼표·원) 그대로 POST field=discount … · r3i2.test(discountBasis 접근 설명) |
| 76 | 기타 = 기록만, 200자 | Ops · ③ 규칙 표 "기타 기록만 남아요, 200자까지" | — | 있음 | ops/humanCheck8.test › 메모·값 길이 상한(500·200)은 입력 칸이 막는다 |
| 77 | 숫자를 고쳐 쓰지 않음(엄격 형식, `parseStrictNumber`) | Ops · ③ "숫자는 고쳐 쓰지 않아요: 쉼표는 세 자리마다, 숫자 사이에 띄어쓰기 없이…" | — | 있음 | r3i2.test › 다른 숫자 필드(F4): 쉼표 세 자리마다·숫자 사이 공백 없음·단위 앞 공백 한 칸·음수 거절 |
| 78 | 단위 접미어 허용(개월·년 ×12·원·%) (`HUMAN_NUMBER_UNITS`) | Ops · ③ 규칙 표 "'개월'·'년'을 붙여도 돼요('3년' = 36개월)" · "'%' 붙여도 돼요" · "끝 '원'은 붙여서" | — | 있음 | r3i2.test › 다른 숫자 필드(F4): 쉼표 세 자리마다·숫자 사이 공백 없음·단위 앞 공백 한 칸·음수 거절 |
| 79 | 확인 방법 select 전화·방문·이메일 (`page.G7.hc.kind` "종류", `page.G7.hcKind.*`) | Ops · ③ fieldset "어떻게 확인했나요?" 라디오 3개 | select → 라디오, 종류 → 어떻게 확인했나요? | 있음 | ops/ops.test › 사람 확인 저장 → …(kind=phone 기본) |
| 80 | 확인 시각 datetime-local, 기본 = 지금 (`page.G7.hc.checkedAt` "확인 시각") | Ops · ③ "확인한 때" datetime-local | 확인 시각 → 확인한 때 | 있음 | r3f2.test › F6·F7 사람 확인: RFC3339(시간대) 로 보내고 201 + job_id 잡을 발행 대기 안내와 함께 감시 |
| 81 | 시간대 안내 (`page.G7.hc.checkedAtTz` "이 브라우저 시간대({tz})로 보냅니다") | Ops · ③ "이 브라우저 시간대(+09:00)로 보내요" | — | 있음 | r3f2.test › F6·F7 사람 확인: RFC3339(시간대) 로 보내고 201 + job_id 잡을 발행 대기 안내와 함께 감시 |
| 82 | 입력자 역할 select 운영자·검토자 (`page.G7.hc.enteredBy` "입력자", `page.G7.hcRole.*`) | Ops · ③ "입력한 사람 (역할)" + "이름 대신 역할만 남겨요" | — | 있음 | ops/ops.test › minor 15: 입력자는 역할 select(운영자·검토자)뿐 — 자유 입력 칸 없음 |
| 83 | 메모 textarea maxLength 500 + 안내 (`page.G7.hc.note`, `page.G7.hc.noteHint`) | Ops · ③ "메모" + "통화·방문 내용 요약만 적어요. 전화번호·주민번호·이메일·비밀값은 서버가 거부해요." | — | 있음 | ops/humanCheck8.test › 메모·값 길이 상한(500·200)은 입력 칸이 막는다 |
| 84 | 강등 사실 행 지정 표시 (`page.G7.hc.entityPinned` "강등된 사실 행(주장의 대상)을 지정했습니다") | Ops · ③ "⑦에서 '사람 확인으로 되돌리기'로 왔을 때: 검증에서 어긋난 값(주장의 대상)을 정해 두었어요." | — | 있음 | ops/humanCheck8.test › 복원 링크 → 폼 미리 채움 → 저장(entity_id) → 주장 목록 다시 읽어 "복원됨(사람 확인)" |
| 85 | 저장 버튼 (`page.G7.hc.submit` "사람 확인 저장"), 읽기 전용·저장 중 꺼짐 | Ops · ③ "사람 확인 저장" + "저장하면 다시 판정 작업이 자동으로 등록돼요." | — | 있음 | ops/ops.test › 사람 확인 저장 → … · ops/ops.test › 필수값 없이 저장하면 막는다 |
| 86 | 필수 오류 (`page.G7.hc.required` "단지·필드·값·입력자(역할)는 필수입니다") | Ops · ③ "틀렸을 때 예시" "단지·항목·값·입력자(역할)는 꼭 넣어야 해요." | 필드 → 항목 | 있음 | ops/ops.test › 필수값 없이 저장하면 막는다 |
| 87 | 모든 칸을 한 번에 검사·칸 아래 경고 role=alert + aria-invalid (8차 m17) | Ops · ③ "틀린 칸을 한꺼번에 모두 보여 줘요. 서버가 돌려준 칸별 오류도 같은 자리에 나와요." + 칸 아래 경고 예시 | — | 있음 | r3h.test › 서버 422 여러 칸: 확인 시각·값·메모 칸 오류와 detail 을 모두 보인다 |
| 88 | 정수 오류 (`page.G7.hc.badInt` "정수만 입력하세요(소수 불가)") | Ops · ③ 예시 "6.02" → "정수만 넣어 주세요(소수는 안 돼요)" | — | 있음 | ops/humanCheck8.test › 정수 필드에 소수 → 오류, POST 하지 않는다 |
| 89 | 입주 예정 형식 (`page.G7.hc.badYm`) | Ops · ③ "그 밖의 오류 안내 문구 목록" "입주 예정은 연-월(YYYY-MM)로 넣어 주세요" | — | 있음 | ops/humanCheck8.test › 값 형·범위 … · ops/humanCheck8.test › 서버 허용 범위(계약 .8): 공급금액 …, 입주 2000~2100년, 계약금 소수 둘째 자리 |
| 90 | 입주 예정 범위 (`page.G7.hc.badYmRange`) | Ops · ③ 오류 목록 "입주 예정은 2000-01 ~ 2100-12 사이여야 해요" | — | 있음 | ops/humanCheck8.test › 값 형·범위 … · ops/humanCheck8.test › 서버 허용 범위(계약 .8): 공급금액 …, 입주 2000~2100년, 계약금 소수 둘째 자리 |
| 91 | 숫자 형식 (`page.G7.hc.badFormat` "…단위는 {units}…", 단위 없으면 `page.G7.hc.noUnit` "없음") | Ops · ③ 오류 목록 "숫자 모양이 맞지 않아요 — …, 단위는 [단위](…)" | — | 있음 | r3i2.test › 다른 숫자 필드(F4): 쉼표 세 자리마다·숫자 사이 공백 없음·단위 앞 공백 한 칸·음수 거절 |
| 92 | 할인 형식 (`page.G7.hc.badDiscountFormat`) | Ops · ③ 오류 목록 "할인 모양이 맞지 않아요 — …" | — | 있음 | r3i2.test › 다른 숫자 필드(F4): 쉼표 세 자리마다·숫자 사이 공백 없음·단위 앞 공백 한 칸·음수 거절 |
| 93 | 서버 할인 형식·범위 (`page.G7.hc.discountFormat`) | Ops · ③ 오류 목록 "할인 모양·범위가 맞지 않아요 — [서버 설명]" | — | 있음 | r3h2.test › 폼: 할인 칸 선택 → … 201 + job_id 감시(서버 422 discount 문구) |
| 94 | 서버 할인 ≥ 차감 바탕 (`page.G7.hc.discountNotBelowPrice`) | Ops · ③ 오류 목록 "할인이 기준 타입 가격(…) 이상이라 구매가에서 뺄 수 없어요 — [서버 설명]" | — | 있음 | r3h2.test › 폼: 할인 칸 선택 → … 201 + job_id 감시(서버 422 discount 문구) |
| 95 | 소수 자릿수 (`page.G7.hc.decimals`) | Ops · ③ 오류 목록 "소수점 아래 [n]자리까지만 넣어 주세요" | — | 있음 | ops/humanCheck8.test › 값 형·범위 … · ops/humanCheck8.test › 서버 허용 범위(계약 .8): 공급금액 …, 입주 2000~2100년, 계약금 소수 둘째 자리 |
| 96 | 최솟값·최댓값·음수 (`page.G7.hc.min`, `page.G7.hc.max`, 단위 포맷 '1,000만') | Ops · ③ 오류 목록 "[최솟값] 이상이어야 해요 · [최댓값] 이하여야 해요" | — | 있음 | ops/humanCheck8.test › 값 형·범위 … · ops/humanCheck8.test › 서버 허용 범위(계약 .8): 공급금액 …, 입주 2000~2100년, 계약금 소수 둘째 자리 |
| 97 | 값 길이 (`page.G7.hc.tooLong` "값은 {max}자 이하로…") | Ops · ③ 오류 목록 "값은 200자 이하로 넣어 주세요" | — | 있음 | ops/humanCheck8.test › 메모·값 길이 상한(500·200)은 입력 칸이 막는다 |
| 98 | 메모 길이 (`page.G7.hc.noteTooLong`) | Ops · ③ 예시 "메모는 500자 이하로 넣어 주세요" | — | 있음 | r3h.test › 서버 422 여러 칸: 확인 시각·값·메모 칸 오류와 detail 을 모두 보인다 |
| 99 | 확인 시각 비었음·형식 (`page.G7.hc.checkedAtRequired`) | Ops · ③ 오류 목록 "확인 시각(날짜와 시각)을 넣어 주세요" | — | 있음 | r3f2.test › checkedAtProblem: 비었으면 입력 안내, 형식이 맞으면 통과 · r3h.test › checkedAtProblem: 브라우저 시계와 무관 |
| 100 | 확인 시각 2000-01-01 이전 (`page.G7.hc.checkedAtTooOld`) | Ops · ③ 오류 목록 "확인 시각은 2000-01-01(한국 시간) 이후여야 해요" | — | 있음 | r3f2.test › checkedAtProblem: 비었으면 입력 안내, 형식이 맞으면 통과 · r3h.test › checkedAtProblem: 브라우저 시계와 무관 |
| 101 | 서버 422 미래 (`checked_at_future` · `page.G7.hc.checkedAtFuture`) | Ops · ③ 예시 "확인 시각이 지금보다 10분 넘게 미래예요 — … ([서버 설명])" | — | 있음 | r3g2.test › checked_at_future(문구와 무관) → 미래 안내 |
| 102 | 서버 422 공고보다 이름 (`checked_at_before_source` · `page.G7.hc.checkedAtTooEarly`) | Ops · ③ 오류 목록 "확인 시각이 이미 모은 공식 공고(다른 값)보다 일러요 — …" | — | 있음 | r3g2.test › checked_at_before_source → 이른 확인일 안내 |
| 103 | 서버 422 형식 (`checked_at_format` · `page.G7.hc.checkedAtFormat`) | Ops · ③ 오류 목록 "확인 시각 모양·범위가 맞지 않아요(…) — [서버 설명]" | — | 있음 | r3h.test › 서버 422 여러 칸 … |
| 104 | 서버 422 그 밖 (`page.G7.hc.checkedAtServer`) | Ops · ③ 오류 목록 "확인 시각을 서버가 받지 않았어요 — [서버 설명]" | — | 있음 | r3h.test › 서버 422 여러 칸 … |
| 105 | 일반 서버 오류 줄 (`page.G7.hc.serverError` "저장하지 못했습니다: {detail}", 칸에 못 붙인 오류 포함) | Ops · ③ 예시 "저장하지 못했어요: [서버 설명]" | — | 있음 | r3h.test › 서버 422 여러 칸: 확인 시각·값·메모 칸 오류와 detail 을 모두 보인다 |
| 106 | 저장 토스트 접수 상태 (`page.G7.hc.saved`) + 자동 재판정 (`page.G7.hc.rejudgeAuto` "재판정 잡 {id}을(를) 자동 등록했습니다…") | Ops · ③ "저장한 뒤 예시" role=status "저장했어요 — … · 다시 판정 작업 #[번호]을 자동 등록했어요" | 재판정 잡 → 다시 판정 작업 | 있음 | ops/ops.test › 사람 확인 저장 → 접수 배지 즉시 갱신 + 자동 등록 재판정(rejudge_job_id) 진행 |
| 107 | 저장 토스트 사실 필드 (`page.G7.hc.savedFact`) | Ops · ③ "숫자 항목 저장 알림: 저장했어요 — 같은 값의 검증 모순 표시를 사람 확인 값으로 되돌렸어요" | — | 있음 | ops/humanCheck8.test › 사실 필드 저장 → POST field=move_in_ym, 결과 문구(접수 배지 아님) |
| 108 | 방금 저장한 접수 상태 (`page.G7.hc.latest` + IntakeBadge) | Ops · ③ "방금 저장한 접수 상태 접수 가능 · 사람 확인" | — | 있음 | ops/ops.test › 사람 확인 저장 → 접수 배지 즉시 갱신 … |
| 109 | 사실 저장 결과 (`page.G7.hc.factSaved` "{field} = {value} (사람 확인 — 출처 우선순위 0)") | Ops · ③ "숫자 항목 저장: 되팔기 제한 기간 = [값] 사람 확인 가장 먼저 쓰는 출처" | 출처 우선순위 0 → 가장 먼저 쓰는 출처 | 있음 | ops/humanCheck8.test › 사실 필드 저장 → POST field=move_in_ym, 결과 문구(접수 배지 아님) |
| 110 | 대상 행 (`page.G7.hc.target` "대상 행: {entity} {id}", `page.G7.hcEntity.*`) | Ops · ③ "· 대상: 납부 조건 [번호]" | — | 있음 | ops/humanCheck8.test › 응답 entity·entity_id → "대상 행: 납부 조건 #31" |
| 111 | 할인 반영 기준 타입 (`page.G7.hc.discountBasisSaved` "기준 타입 {type} 할인으로 반영") | Ops · ③ "할인 저장: 기준 타입 [타입] 할인으로 반영했어요" | — | 있음 | r3h2.test › 폼: 할인 칸 선택 → … POST field=discount(기준 타입 반영) |
| 112 | 저장 뒤 진행 PublishJobProgress (rejudge → 발행) | Ops · ③ "작업 진행 · 다시 판정 · 실행 중" role=progressbar + "작업이 끝나 새 수정본이 발행될 때까지 화면은 지금 발행본을 보여요." | — | 있음 | r3f2.test › F6·F7 사람 확인: … 201 + job_id 잡을 발행 대기 안내와 함께 감시 |
| 113 | 재판정 없음 (`page.G7.hc.noRejudge` "재판정 없음(기타 항목)") | Ops · ③ "'기타'를 저장하면: 다시 판정 없음(기타 항목)" | — | 있음 | r3d.test › 사람 확인 field=기타 → rejudge_job_id null → 잡 진행 없이 "재판정 없음", POST /jobs 없음 |
| 114 | URL 미리 채우기 `hc_complex`·`hc_field`·`hc_entity` (대기열·주장·G3 할인 링크) | Ops · ③ "② 대기열에서 '검단 스타힐스 가현숲 · 접수 상태'로 채웠어요." | — | 있음 | ops/intakeQueue.test › '사람 확인 입력' → 폼을 그 단지·접수 상태로 채움 … · r3h2.test › '추정' 할인 … /ops 사람 확인 링크 |
| 115 | 같은 화면에서 URL이 바뀌면 폼을 다시 채움(값·오류 지움) | — | — | 문구로만(고침 OP-13 — "구현 때 유지" 상자) | ops/humanCheck8.test › 복원 링크 → 폼 미리 채움(같은 화면 URL 변경 → 다시 채움) |
| 116 | 다른 화면에서 `#human-check` 로 들어오면 폼으로 한 번 스크롤 | — | — | 문구로만(고침 OP-13 — "구현 때 유지" 상자) | ops/r11ops.test › 다른 화면에서 #human-check 로 들어오면 사람 확인 폼으로 한 번 스크롤 |
| 117 | 단지를 바꾸면 사실 행 지정 지움 / 필드를 바꾸면 값·오류 지움 | — | — | 문구로만(고침 OP-13 — "구현 때 유지" 상자) | ops/humanCheck8.test › 복원 링크 → 폼 미리 채움 …(단지·항목 바꾸면 지움 — 코드 clearLocal/setEntityId) |
| 118 | API `GET /snapshots/{sid}/complexes?size=1000&sort=name` (단지 선택지) | Ops · ③ "단지" select(호출 주체) | — | 있음 | ops/ops.test › 사람 확인 저장 → …(단지 선택지 GET complexes) |
| 119 | API `GET /complexes/{id}` (할인 기준 타입, field=discount일 때만) | Ops · ③ 규칙 표 "기준 타입 [타입]"(호출 주체) | — | 있음 | r3h2.test › 폼: 할인 칸 선택 → …(GET /complexes/{id} 기준 타입) |
| 120 | API `POST /ops/human-checks` {complex_id, field, entity_id?, value_text, kind, checked_at(RFC3339+시간대), entered_by, note} | Ops · ③ "사람 확인 저장"(호출 주체) | — | 있음 | r3f2.test › F6·F7 사람 확인: RFC3339(시간대) 로 보내고 … |

## ④ 수집 상태 (SourceStatusTable)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 121 | Section·표 aria-label (`page.G7.sources` "소스 상태") | Ops · ④ "자료를 잘 모으고 있나요?" (메뉴 "수집 상태") 표 caption "최근 7일 · 시각은 한국 시간 · 운영 기록 그대로" | 소스 상태 → 수집 상태 | 있음 | ops/ops.test › 소스 상태 · 큐 …(table name page.G7.sources) · ops/r11ops.test › 묶음 메뉴 9칸 … |
| 122 | 소스 없음 (`page.common.none`) | — | — | 있음(고침 OP-5 — 펼친 모습 "④ 수집 상태 다른 경우" 목록이 비면 "없음") | components/shell-components.test › QueryState 빈 데이터 = 호출 측 문구 상자 |
| 123 | 표 열: 소스 (`page.G7.src.kind`, 행 머리 `page.G7.sourceKind.*` 8종) | Ops · ④ 표 "자료" 8줄 (청약홈 목록 … 참조 코드 (지역·동 이름표)) | 소스 → 자료, 청약홈 상세 → 청약홈 단지 상세, 공고문 PDF → 입주자 모집 공고문 (PDF) 등 | 있음 | r4fe12.test › 4xx 실패 대상은 '확인 불가(403, 날짜)'(계약 source_status 표시 규칙 — 상태 코드를 두 번 쓰지 않는다) |
| 124 | 실패 대상 접이식 + 개수 (`page.G7.src.failing` "실패 대상 · n") | Ops · ④ "단지 공식 홈페이지" 아래 details "열리지 않는 곳 16곳" | 실패 대상 → 열리지 않는 곳 | 있음 | r4fe12.test › 4xx 실패 대상은 '확인 불가(403, 날짜)'(계약 source_status 표시 규칙 — 상태 코드를 두 번 쓰지 않는다) |
| 125 | 실패 대상 줄: 단지 · "확인 불가(코드/사유, 날짜)" · 외부 링크 (`formatUnknownTarget`, title=사유) | Ops · ④ "e편한세상 부평 그랑힐스(보류지) · 확인 불가(404, 10.15 06:12) · hanwoorired.co.kr ↗" | — | 있음 | r4fe12.test › 4xx 실패 대상은 '확인 불가(403, 날짜)'(계약 source_status 표시 규칙 — 상태 코드를 두 번 쓰지 않는다) |
| 126 | 2xx 실패는 코드 대신 사유 — 빈 데이터셋 (`page.G7.src.reason.emptyDataset` "빈 데이터셋 — 청약홈 적재 중") | Ops · 펼친 모습 "④ 수집 상태 다른 경우" "확인 불가(빈 자료 — 청약홈이 아직 올리는 중, [날짜])" + ④ "실패 이유가 응답 코드가 아닌 경우(예: 빈 자료)는 이유를 글로 보여 줘요" | 빈 데이터셋 → 빈 자료 | 있음 | r4fe12.test › 실패 대상: '확인 불가(빈 데이터셋 — 청약홈 적재 중, 2026-10-13)' — 200·영문 코드 없이 · r4fe12.test › 4xx 실패 대상은 … |
| 127 | 표 열: 사용 (`page.G7.src.enabled`, `page.common.yes` "예") | Ops · ④ 표 "켜짐" "예" | 사용 → 켜짐 | 있음 | ops/r11ops.test › 닫힌 체크리스트 줄·꺼진 자료 줄은 흐리게(data 표시 + 회색) |
| 128 | 꺼진 소스 배지 (`page.G7.src.disabled` "꺼짐({reason})") | Ops · 펼친 모습 "[자료 이름] 꺼짐([사유])" | — | 있음 | ops/r11ops.test › 닫힌 체크리스트 줄·꺼진 자료 줄은 흐리게(data 표시 + 회색) |
| 129 | 꺼진 소스 줄 흐리게 | — | — | 있음(고침 OP-3 — 같은 칸 첫 줄, 꺼진 자료 줄 흐리게) | ops/r11ops.test › 닫힌 체크리스트 줄·꺼진 자료 줄은 흐리게(data 표시 + 회색) |
| 130 | 표 열: 최종 수집 (`page.G7.src.lastSuccess`) / 없음 → EmptyState inline | Ops · ④ 표 "마지막 성공" + 펼친 모습 "마지막 성공 확인 불가 (한 번도 성공 못 함)" | 최종 수집 → 마지막 성공 | 있음 | ops/ops.test › 소스 상태 · 큐 · … · r4fe12.test › 4xx 실패 대상은 … |
| 131 | 표 열: 최종 시도 (`page.G7.src.lastAttempt`) | Ops · ④ 표 "마지막 시도" | — | 있음 | ops/ops.test › 소스 상태 · 큐 · … · r4fe12.test › 4xx 실패 대상은 … |
| 132 | 최종 시도 없음 → EmptyState inline | — | — | 있음(고침 OP-4 — 같은 칸 둘째 줄, 마지막 시도 "확인 불가") | ops/ops.test › 소스 상태 · 큐 · … · r4fe12.test › 4xx 실패 대상은 … |
| 133 | 표 열: 성공(7일) (`page.G7.src.success`) | Ops · ④ 표 "성공" | 성공(7일) → 성공 (7일은 캡션으로) | 있음 | ops/ops.test › 소스 상태 · 큐 · … · r4fe12.test › 4xx 실패 대상은 … |
| 134 | 표 열: 실패(7일) (`page.G7.src.failure`), 실패 있으면 굵은 경고색 | Ops · ④ 표 "실패" (55 굵은 주황) | — | 있음 | ops/ops.test › 소스 상태 · 큐 · … · r4fe12.test › 4xx 실패 대상은 … |
| 135 | 표 열: HTTP (`page.G7.src.http`, 없으면 빈 칸) | Ops · ④ 표 "응답 코드" + `?` 설명 | HTTP → 응답 코드 | 있음 | ops/ops.test › 소스 상태 · 큐 · … · r4fe12.test › 4xx 실패 대상은 … |
| 136 | 표 열: 마지막 오류 (`page.G7.src.error`, title = 원문) | Ops · ④ 표 "마지막 오류" ("—") | — | 있음 | ops/ops.test › 소스 상태 · 큐 · … · r4fe12.test › 4xx 실패 대상은 … |
| 137 | 표 열: 재시도 버튼 (`page.G7.src.retry` "재시도", `row.retry` 있을 때만) | Ops · ④ 표 "다시 모으기" 버튼 | 재시도 → 다시 모으기 | 있음 | ops/ops.test › 소스 재시도 버튼 → POST /jobs(retry 잡) |
| 138 | 재시도 꺼짐: 읽기 전용·등록 중 (+ title) | Ops · 펼친 모습 "읽기 전용 열쇠예요 — 저장·실행 버튼이 꺼져 있어요" | — | 문구로만(고침 OP-13 — "구현 때 유지" 상자에도 적음) | ops/ops.test › 소스 재시도 버튼 …(readOnly·pending disabled — 코드) |
| 139 | 재시도 토스트 (`page.G7.src.retried` "재시도 잡을 등록했습니다") | Ops · ④ "'다시 모으기'를 누르면 "다시 모으기 작업을 등록했어요" 알림이 뜨고…" | — | 문구로만 | ops/ops.test › 소스 재시도 버튼 → POST /jobs(retry 잡) |
| 140 | API `GET /ops/sources?region_id=` (`useOpsSources`) | Ops · ④(호출 주체) | — | 있음 | ops/ops.test › 소스 상태 · 큐 · 체크리스트 · 캘린더 · 판정기 통계(30일) |
| 141 | API `POST /jobs` {job_name, payload} (재시도, `useCreateJob`) | Ops · ④ "다시 모으기"(호출 주체) | — | 있음 | ops/ops.test › 소스 재시도 버튼 → POST /jobs(retry 잡) |

## ⑤ 작업 대기열 (RejudgeQueue)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 142 | Section·표 aria-label (`page.G7.queue` "재조사·재판정 큐") | Ops · ⑤ "자동 작업이 잘 돌고 있나요?" (메뉴 "작업 대기열") 표 caption "작업 대기열" | 재조사·재판정 큐 → 작업 대기열 | 있음 | ops/ops.test › 소스 상태 · 큐 …(table name page.G7.queue) |
| 143 | 잡 없음 (`page.G7.job.none` "잡 없음") | Ops · 펼친 모습 "작업이 없으면: 작업 없음" | — | 있음 | ops/ops.test › 소스 상태 · 큐 …(table name page.G7.queue) |
| 144 | 표 열: 잡 = job_name + id (`page.G7.job.name`) | Ops · ⑤ 표 "작업" "새 수정본 발행 #29 · snapshot.publish" | 잡 → 작업, 쉬운 이름 앞에 | 있음 | ops/r11ops.test › 작업 대기열: 쉬운 작업 이름(jobNameText, D30-8) + 원래 이름 |
| 145 | 표 열: 상태 배지 (`page.G7.job.status`, `job.status.*`) | Ops · ⑤ 표 "상태" "완료" + 펼친 모습 "대기 · 실행 중 · 실패" | — | 있음 | r4fe12.test › G7 잡 목록: 재큐잉 잡은 대기 + 재수집 안내(다음 시도 시각), failed 는 코드 접두 없는 사유 |
| 146 | 상태 아래 재큐잉 안내 — 빈 데이터셋 (`job.requeuedDegraded` + `requeuedAt` + `requeuedDegradedBootstrap`/`requeuedDegradedDaily`) | Ops · 펼친 모습 "⑤ 작업 대기열 다른 상태" "대기 수집 자료가 불완전해([사유]) … — 지역 첫 적재 중이라 발행본은 아직 없어요 / 이전 발행본이 그대로 기본 화면이에요." | — | 있음 | r4fe12.test › G7 잡 목록: 재큐잉 잡은 대기 + 재수집 안내(다음 시도 시각), failed 는 코드 접두 없는 사유 |
| 147 | 재큐잉 시각 없음 (`job.requeuedSoon` "곧 다시 시도") | — | — | 있음(고침 OP-12 — 펼친 모습 "⑤ 작업 대기열 다른 상태" "곧 다시 시도") | r4fe12.test › G7 잡 목록: 재큐잉 잡은 대기 + 재수집 안내(다음 시도 시각), failed 는 코드 접두 없는 사유 |
| 148 | 재큐잉 안내 — 발행 busy (`job.requeued`) / 발행 예외 (`job.requeuedError`) | Ops · 펼친 모습 "대기 같은 수정본의 다른 발행이 끝나길 기다리는 중(다시 대기 [n]회) — 실패가 아니에요 · 발행 중 오류가 나 다시 시도하는 중([n]/[n]회)" | — | 있음 | r4fe12.test › G7 잡 목록: 재큐잉 잡은 대기 + 재수집 안내(다음 시도 시각), failed 는 코드 접두 없는 사유 |
| 149 | 표 열: 예약 (`page.G7.job.scheduled`) | Ops · ⑤ 표 "예약" | — | 있음 | ops/ops.test › 소스 상태 · 큐 …(GET /jobs?size=50) · r4fe12.test › G7 잡 목록 … |
| 150 | 표 열: 시작 (`page.G7.job.started`) | Ops · ⑤ 표 "시작" | — | 있음 | ops/ops.test › 소스 상태 · 큐 …(GET /jobs?size=50) · r4fe12.test › G7 잡 목록 … |
| 151 | 표 열: 종료 (`page.G7.job.finished`) | Ops · ⑤ 표 "끝" | 종료 → 끝 | 있음 | ops/ops.test › 소스 상태 · 큐 …(GET /jobs?size=50) · r4fe12.test › G7 잡 목록 … |
| 152 | 표 열: 진행 (`page.G7.job.progress`, `page.G7.job.progressValue` "{done}/{total}" + 단계) | Ops · ⑤ 표 "진행" + 펼친 모습 "실행 중 [n]/[n] · 단계 [단계 이름]" | — | 있음 | ops/ops.test › 소스 상태 · 큐 …(GET /jobs?size=50) · r4fe12.test › G7 잡 목록 … |
| 153 | 표 열: 오류 (`page.G7.job.error`, error_text 또는 빈 데이터셋 상한 실패 `job.degradedFailed`) | Ops · ⑤ 표 "오류" + 펼친 모습 "실패 수집 자료가 [n]회 다시 모아도 불완전해 멈췄어요 — 발행하지 않았어요: [사유]" | — | 있음 | r4fe12.test › G7 잡 목록: … failed 는 코드 접두 없는 사유 |
| 154 | 최근 50건 조회 (`size: 50`) | Ops · ⑤ "최근 29건" + "21건 더 보기" | — | 있음 | ops/ops.test › 소스 상태 · 큐 …(GET /jobs?size=50) · r4fe12.test › G7 잡 목록 … |
| 155 | API `GET /jobs?size=50` (`useJobs`) | Ops · ⑤(호출 주체) | — | 있음 | ops/ops.test › 소스 상태 · 큐 …(GET /jobs?size=50) · r4fe12.test › G7 잡 목록 … |

## ⑥ 판정기 호출 통계 (JudgmentStatsPanel · JudgmentTable)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 156 | Section 제목 (`page.G7.stats` "판정기 호출(30일)") | Ops · ⑥ "최근 30일, 판정기를 얼마나 불렀나요?" (메뉴 "판정기 호출 통계") | — | 있음 | ops/ops.test › since30: 기준일 30일 전 · ops/ops.test › 소스 상태 · … 판정기 통계(30일) |
| 157 | 30일 범위 = 기준일 − 30일 (`since30`) | Ops · ⑥ "2026-09-15 ~ 2026-10-15" | — | 있음 | ops/ops.test › since30: 기준일 30일 전 · ops/ops.test › 소스 상태 · … 판정기 통계(30일) |
| 158 | 판정기 장애 줄 role=alert (`stats.degraded` · `app.degraded` "판정기 장애 — 미판정 모드…") | Ops · 펼친 모습 "⑥ 판정기 장애 때 판정기 장애 — 판정 쉬는 모드: 새 판정 없이 저장된 결과·이전 결과만 보여요." | 미판정 모드 → 판정 쉬는 모드 | 있음(고침 OP-14 — "미판정 모드: 판정기를 쓸 수 없어 새 판정을 하지 않아요"로 뜻 되돌림) | ops/ops.test › 판정기 degraded → 전역 배너 |
| 159 | 타일: 호출 (`page.G7.stat.total`) | Ops · ⑥ 타일 "전체 호출" | 호출 → 전체 호출 | 있음 | ops/ops.test › 소스 상태 · … 판정기 통계(30일)(타일 list name page.G7.stats) |
| 160 | 타일: 실제 호출 (`page.G7.stat.real`) | Ops · ⑥ 타일 "실제로 보낸 호출" | — | 있음 | ops/ops.test › 소스 상태 · … 판정기 통계(30일)(타일 list name page.G7.stats) |
| 161 | 타일: 캐시 (`page.G7.stat.cached`) | Ops · ⑥ 타일 "저장된 결과 다시 씀 (캐시)" | 캐시 → 저장된 결과 다시 씀 | 있음 | ops/ops.test › 소스 상태 · … 판정기 통계(30일)(타일 list name page.G7.stats) |
| 162 | 타일: 실패 (`page.G7.stat.failures`) | Ops · ⑥ 타일 "실패" | — | 있음 | ops/ops.test › 소스 상태 · … 판정기 통계(30일)(타일 list name page.G7.stats) |
| 163 | 타일: 검토 (`page.G7.stat.review`) | Ops · ⑥ 타일 "사람 검토 필요" | 검토 → 사람 검토 필요 | 있음 | ops/ops.test › 소스 상태 · … 판정기 통계(30일)(타일 list name page.G7.stats) |
| 164 | 타일: 질문 (`page.G7.stat.escaped`) | Ops · ⑥ 타일 "질문으로 넘김" | — | 있음 | ops/ops.test › 소스 상태 · … 판정기 통계(30일)(타일 list name page.G7.stats) |
| 165 | 타일: 평균 소요 (`page.G7.stat.avg`, `page.G3.judgment.ms`) / 없으면 `empty.unknown` | Ops · ⑥ 타일 "평균 걸린 시간 152.8 ms (1,000ms = 1초)" + 펼친 모습 "평균 걸린 시간 기록이 없으면 타일에 확인 불가" | 평균 소요 → 평균 걸린 시간 | 있음 | ops/ops.test › 소스 상태 · … 판정기 통계(30일)(타일 list name page.G7.stats) |
| 166 | 실제 호출 설명 (`page.G7.stat.realHint`) | Ops · ⑥ "실제로 보낸 호출 = 판정기로 실제 보낸 호출 수(…). 전체 호출 = …" | — | 있음 | r4fe9.test › 통계 타일 아래 안내: 실제 호출의 뜻과 호출 = 실제 + 캐시 |
| 167 | 도구별 호출 제목·목록 (`page.G7.stat.byTool` "도구별 호출") | Ops · ⑥ "판단 종류별 호출" | 도구별 → 판단 종류별 | 있음 | ops/ops.test › 소스 상태 · … (list name page.G7.stat.byTool) |
| 168 | 도구별 막대(최댓값 기준 폭) + 문구 (`page.G7.stat.bar` "{tool}: {calls}회(실패 {failures})") | Ops · ⑥ 막대 9줄 "외부 글 안전 검사 screen … 실제 406 · 다시 씀 666 · 실패 0 · 검토 0 · 막힘 2" | 도구 코드 → 쉬운 이름 + 코드 | 있음 | ops/ops.test › 소스 상태 · … (list name page.G7.stat.byTool) |
| 169 | 어댑터 버전 배지 (`page.G7.stat.adapter` "어댑터 {version}") | Ops · ⑥ 출처 줄 "판정기 연결 버전 0.2.0 (jev-mcp 0.14.3 · jev 1.13.0)" | 어댑터 → 판정기 연결 버전 | 있음 | ops/ops.test › 소스 상태 · … (list name page.G7.stat.byTool) |
| 170 | 최근 판정 표 (`JudgmentTable`, caption = 제목, 20건) | Ops · ⑥ "최근 판정 기록" 표 + "최근 20건 중 8건" | — | 있음 | r4fe9.test › G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시 |
| 171 | 판정 표 열: 번호 (`page.G3.judgment.seq`) | Ops · ⑥ 표 "번호" | — | 있음 | r4fe9.test › G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시 |
| 172 | 판정 표 열: 도구 (`page.G3.judgment.tool`) | Ops · ⑥ 표 "판단 종류" | 도구 → 판단 종류 | 있음 | r4fe9.test › G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시 |
| 173 | 판정 표 열: 목적 (`page.G3.judgment.purpose`) | Ops · ⑥ 표 "무엇을 판단했나" (쉬운 말 + 원 코드 "decide:scenario_D") | 목적 → 무엇을 판단했나 | 있음 | r4fe9.test › G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시 |
| 174 | 판정 표 열: 상태 배지 (`page.G3.judgment.status`, `page.common.status.*`) | Ops · ⑥ 표 "결과" "정상/검토" | 상태 → 결과 | 있음 | r4fe9.test › G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시 |
| 175 | 미해결 줄 흐리게 + '미해결' 배지 (`page.common.unresolved`) | Ops · ⑥ "결과를 못 정한 줄(검토·질문 남김·차단·오류)은 흐리게 '미해결' 배지와 함께 보여요" + 펼친 모습 "검토 미해결" | — | 있음 | r4fe9.test › G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시 |
| 176 | 캐시 배지 (`CachedBadge` · `badge.cached` "캐시") | Ops · ⑥ "저장된 결과를 다시 쓴 줄에는 '저장된 결과' 배지" + 펼친 모습 "저장된 결과" | 캐시 → 저장된 결과 | 있음 | r4fe9.test › G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시 |
| 177 | 오류 글 (`env.error_text`) | Ops · ⑥ "오류가 있으면 결과 아래에 오류 글이 붙어요" | — | 문구로만 | r4fe9.test › G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시 |
| 178 | 판정 표 열: 모델 (`page.G3.judgment.model`) + 공급자 `({provider})` | Ops · ⑥ 표 "모델" "jev-1.13.0 (typesafe)" | — | 있음 | r4fe9.test › JudgmentTable: '모델' 열 — provider 'none' 은 '로컬' 배지 … |
| 179 | 모델 로컬 배지 (`page.G3.judgment.local` "로컬", title `localHint`) / 기록 없음 (`modelNone`) | Ops · ⑥ "판정기가 부르지 않은 처리는 모델 칸에 '로컬(비용 없음)', 모델 기록이 없으면 '기록 없음'" + 펼친 모습 "모델: 로컬 (비용 없음) · 기록 없음" | — | 있음 | r4fe9.test › JudgmentTable: '모델' 열 — provider 'none' 은 '로컬' 배지 … |
| 180 | 판정 표 열: 신뢰도 (`page.G3.judgment.confidence`) / 없으면 "확인 불가" | Ops · ⑥ 표 "확신 정도" + `?` ("0.56", "확인 불가") | 신뢰도 → 확신 정도 | 있음 | r4fe9.test › G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시 |
| 181 | 판정 표 열: 소요 (`page.G3.judgment.duration`, "{ms}ms") | Ops · ⑥ 표 "걸린 시간" "202ms" | 소요 → 걸린 시간 | 있음 | r4fe9.test › G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시 |
| 182 | 소요 없음 → "확인 불가" | — | — | 있음(고침 OP-7 — 펼친 모습 "⑥ 판정기 장애 때" 걸린 시간 "확인 불가" 줄) | r4fe9.test › G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시 |
| 183 | 판정 표 열: 시각 (`page.G3.judgment.createdAt`) | Ops · ⑥ 표 "시각" | — | 있음 | r4fe9.test › G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시 |
| 184 | API `GET /ops/judgments?since=&size=20` (`useOpsJudgments`) | Ops · ⑥(호출 주체) | — | 있음 | ops/ops.test › 소스 상태 · … (GET /ops/judgments since) |

## ⑦ 모순 주장 (ClaimsPanel)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 185 | Section·목록 aria-label (`page.G7.claims.title` "모순(contradicted) 주장") | Ops · ⑦ "검증에서 어긋난 문장이 남아 있나요?" (메뉴 "모순 주장") | — | 있음 | ops/r11ops.test › 모순 주장: 상태 필터 없이 받은 목록의 상태별 줄 수 + 모순 줄만 목록에 |
| 186 | 안내 (`page.G7.claims.intro`) | Ops · ⑦ "이게 뭐예요?" 문단 | contradicted·claim.reverify 등 영어 뺌 | 있음 | ops/r11ops.test › 모순 주장: 상태 필터 없이 받은 목록의 상태별 줄 수 + 모순 줄만 목록에 |
| 187 | 주장 없음 (`page.G7.claims.none` "남은 contradicted 주장이 없습니다") | Ops · ⑦ "남은 모순 주장이 없어요" | — | 있음(고침 OP-9 — 요약에서 API에 없는 맞음·검토 수를 빼고 "API 필요" 표시) | ops/r11ops.test › 모순 주장이 없으면 "남은 모순 주장이 없어요" + 상태별 줄 수는 그대로 · ops/claims.test › contradicted 가 없으면 빈 안내 |
| 188 | 줄: 단지 링크(G3) / 단지 없으면 이름·section | Ops · ⑦ 예시 "[단지 이름]" 링크 | — | 있음 | ops/claims.test › GET /snapshots/{sid}/claims(상태 필터 없음 — 계약 .22 A5) → 모순 줄의 문장·단지·근거·상태·남음 배지 |
| 189 | 줄: 검증 상태 배지 (`page.G7.claims.status.*`) | Ops · ⑦ 예시 "모순 (검증 결과 어긋남)" | — | 있음 | ops/claims.test › GET /snapshots/{sid}/claims(상태 필터 없음 — 계약 .22 A5) → 모순 줄의 문장·단지·근거·상태·남음 배지 |
| 190 | 줄: 남음 배지 (`page.G7.claims.remaining` "남음(publish 막힘)") | Ops · ⑦ 예시 "남아 있음 · 발행 막힘" | — | 있음 | ops/claims.test › GET /snapshots/{sid}/claims(상태 필터 없음 — 계약 .22 A5) → 모순 줄의 문장·단지·근거·상태·남음 배지 |
| 191 | 줄: 재검증 대기 배지 (`page.G7.claims.pending` "재검증 대기 중 {job}") | Ops · ⑦ 예시 "다시 검증 기다리는 중 #[작업 번호]" | — | 있음 | ops/claims.test › pending_job_id 가 있거나 child_count>0 이면 수정 칸·버튼이 꺼진다 |
| 192 | 줄: 분할 배지 (`page.G7.claims.split` "분할 재검증됨(자식 {n}건)") | Ops · ⑦ 예시 "나눠서 다시 검증함 (작은 문장 [n]건)" | 자식 → 작은 문장 | 있음 | ops/claims.test › pending_job_id 가 있거나 child_count>0 이면 수정 칸·버튼이 꺼진다 |
| 193 | 줄: 대상 필드 (`page.G7.claims.field` "대상 필드: {name}") | Ops · ⑦ 예시 "대상 값: [항목 이름]" | 대상 필드 → 대상 값 | 있음 | ops/claims.test › 대상 필드 이름과 "고치면 사실이 강등된다" 안내(사실 주장만) · ops/claims.test › 강등됨 → "확인 불가(검증 모순)" 배지 |
| 194 | 강등 배지 (`label.withReason` "{label}({reason})" → '확인 불가(검증 모순)') | Ops · ⑦ 예시 "확인 불가(검증 모순)" | — | 있음 | ops/claims.test › 대상 필드 이름과 "고치면 사실이 강등된다" 안내(사실 주장만) · ops/claims.test › 강등됨 → "확인 불가(검증 모순)" 배지 |
| 195 | 복원 배지 사람 확인 (`page.G7.claims.restored` + `restoredBy.human_check`) | Ops · ⑦ 예시 "되돌림(사람 확인)" | 복원됨 → 되돌림 | 있음 | ops/claims.test › 복원됨(restored_by=%s) → "%s"(되돌림 문구) |
| 196 | 복원 배지 새 원문 (`restoredBy.new_source` "새 원문") | — | — | 있음(고침 OP-8 — "되돌림(새 원문)" 배지) | ops/claims.test › 복원됨(restored_by=%s) → "%s"(되돌림 문구) |
| 197 | 복원 배지 주체 모름 (`page.G7.claims.restoredPlain` "복원됨") | — | — | 있음(고침 OP-8 — 괄호 없는 "되돌림" 배지) | ops/claims.test › 복원됨(restored_by=%s) → "%s"(되돌림 문구) |
| 198 | 사람 확인으로 복원 링크 (`page.G7.claims.restoreByHuman`, 쓰기 토큰 + 강등 + 사람 확인 필드로 옮길 수 있을 때, ③ 폼 미리 채움·스크롤) | Ops · ⑦ 예시 "사람 확인으로 되돌리기 →" + ③ "⑦에서 '사람 확인으로 되돌리기'로 왔을 때…" | 복원 → 되돌리기 | 있음 | ops/humanCheck8.test › 복원 링크 → 폼 미리 채움 → 저장(entity_id) … |
| 199 | 판정 출처 버튼 (`page.G7.claims.prov` "판정 출처" → 출처 창) | Ops · ⑦ 예시 "판정 출처 보기" | — | 있음 | ops/claims.test › 출처 버튼(prov jl_) → 공통 출처 패널이 열린다 |
| 200 | 주장 문장 인용 | Ops · ⑦ 예시 "[주장 문장 — 예: …]" | — | 있음 | ops/claims.test › GET /snapshots/{sid}/claims(…) → 모순 줄의 문장·단지·근거·상태·남음 배지 |
| 201 | 근거 (`page.G7.claims.evidence` "근거") | Ops · ⑦ 예시 "근거 [공고문에서 뽑은 원문 조각]" | — | 있음 | ops/claims.test › GET /snapshots/{sid}/claims(…) → 모순 줄의 문장·단지·근거·상태·남음 배지 |
| 202 | 고친 문장 라벨·textarea (`page.G7.claims.revise` "고친 문장") | Ops · ⑦ 예시 "고친 문장" textarea | — | 있음 | ops/claims.test › 문장 수정 → PATCH /claims/{id} {text} → claim.reverify 잡 진행 표시 · ops/claims.test › 같은 문장이거나 비어 있으면 보내지 않는다 |
| 203 | DB 사실 주장 안내 (`page.G7.claims.demoteHint`) | Ops · ⑦ 예시 "저장된 값에서 나온 문장이에요. 고쳐서 다시 검증을 맡기면…" | — | 있음 | ops/claims.test › 대상 필드 이름과 "고치면 사실이 강등된다" 안내(사실 주장만) |
| 204 | 고쳐서 재검증 버튼 (`page.G7.claims.submit`) — 꺼짐: 읽기 전용·재검증 대기·분할됨·저장 중·빈 문장·안 바뀜 (+ title) | Ops · ⑦ 예시 꺼진 "고쳐서 다시 검증" + "문장을 바꿔야 버튼이 켜져요 · 다시 검증 중이거나 이미 나눠졌거나 읽기 전용이면 꺼져요" | 재검증 → 다시 검증 | 있음 | ops/claims.test › 문장 수정 → PATCH /claims/{id} {text} → claim.reverify 잡 진행 표시 · ops/claims.test › 같은 문장이거나 비어 있으면 보내지 않는다 |
| 205 | 수정 오류 (`page.G7.claims.error` "수정하지 못했습니다: {detail}") | Ops · ⑦ 예시 "고치지 못했어요: [서버 설명]" | — | 있음 | ops/claims.test › 409 conflict → 서버 detail 을 보인다 |
| 206 | 재검증 진행 JobProgress (claim.reverify) | Ops · ⑦ 예시 "작업 진행 · 다시 검증 · 실행 중" role=progressbar | — | 있음 | ops/claims.test › 문장 수정 → PATCH /claims/{id} {text} → claim.reverify 잡 진행 표시 |
| 207 | 끝나면 사실 화면 다시 읽기 (`invalidateFactViews`) | Ops · ⑦ "끝나면 내려간 값·되돌린 값을 다시 읽어 와요." | — | 문구로만 | r3d.test › 잡 상세가 running → done 이면 지역·리비전·사실 화면 무효화 · ClaimsPanel onDone=invalidateFactViews(코드) |
| 208 | API `GET /snapshots/{sid}/claims?status=contradicted` (`useClaims`) | Ops · ⑦(호출 주체) | — | 있음 | ops/claims.test › GET /snapshots/{sid}/claims(상태 필터 없음 — 계약 .22 A5) … |
| 209 | API `PATCH /claims/{id}` {text} (`useReviseClaim`) | Ops · ⑦ "고쳐서 다시 검증"(호출 주체) | — | 있음 | ops/claims.test › 문장 수정 → PATCH /claims/{id} {text} … |

## ⑧ 범위 경계 단지 (BoundaryList)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 210 | Section·목록 aria-label (`page.G7.boundary.title` "범위 경계 단지") | Ops · ⑧ "지역 경계에 걸친 단지가 있나요?" (메뉴 "범위 경계 단지") | — | 있음 | ops/boundary.test › GET complexes?filter[inclusion_class]=범위 경계 → 이름 + 단지 화면 링크 |
| 211 | 안내 (`page.G7.boundary.intro`) | Ops · ⑧ "이게 뭐예요?" 문단 | D2-6 표기 뺌 | 있음 | ops/boundary.test › GET complexes?filter[inclusion_class]=범위 경계 → 이름 + 단지 화면 링크 |
| 212 | 스냅샷 없음 (`app.noSnapshot`) | Ops · 펼친 모습 "기준일이 없을 때" | — | 있음 | ops/boundary.test › (snapshotId null → app.noSnapshot — 코드) · layout/shell.test › 발행 기준일이 없으면 "아직 기준일이 없어요" |
| 213 | 경계 단지 없음 (`page.G7.boundary.none` "범위 경계 단지가 없습니다") | Ops · 펼친 모습 "⑧ … 없으면: 범위 경계 단지가 없어요" | — | 있음 | ops/boundary.test › 범위 경계 단지가 없으면 빈 안내 |
| 214 | 단지 이름 링크 → 단지 화면(현재 검색 조건 유지) | Ops · ⑧ 칩 링크 + "누르면 단지 화면으로 가요" | — | 있음 | ops/boundary.test › GET complexes?filter[inclusion_class]=범위 경계 → 이름 + 단지 화면 링크 |
| 215 | 생활권 이름 (`living_area_name`, 있을 때만) | Ops · ⑧ "생활권 이름이 있으면 단지 이름 옆에 붙어요(지금 4곳 모두 없음)" | — | 문구로만 | r4fe11.test › G7 범위 경계 목록: 단지마다 서버 사유(주소에 동 없음 / 매칭 안 됨), 키 없으면 이름만 |
| 216 | 판정 범위 사유 (`ScopeReason` · 서버 `judge_scope_reason`, compact) | Ops · ⑧ "판정 범위 이유: 범위 경계(주소에 동 없음)" | — | 있음 | r4fe11.test › G7 범위 경계 목록: 단지마다 서버 사유(주소에 동 없음 / 매칭 안 됨), 키 없으면 이름만 |
| 217 | 재판정 필요면 '지금 값 기준' 안내 (`page.common.scopeReasonCurrent`, compact는 title) | Ops · 펼친 모습 "⑧ 범위 경계 다른 상태" "판정 범위 이유: [이유] — 지금 값 기준, 다시 판정 뒤 범위의 이유 다시 판정 필요" | — | 있음 | r4fe11.test › G7 범위 경계 목록: 단지마다 서버 사유(주소에 동 없음 / 매칭 안 됨), 키 없으면 이름만 |
| 218 | API `GET /snapshots/{sid}/complexes?size=200&sort=name&filter inclusion_class=범위 경계` | Ops · ⑧(호출 주체) | — | 있음 | ops/boundary.test › GET complexes?filter[inclusion_class]=범위 경계 → 이름 + 단지 화면 링크 |

## ⑨ 공유 링크 (SharePanel)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 219 | 쓰기 토큰일 때만 보임(읽기·공유 토큰이면 패널 없음, GET도 안 부름) | Ops · ⑨ "쓰기 권한이 있을 때만 이 묶음이 보여요." + 펼친 모습 "공유 링크 묶음은 보이지 않아요." | — | 있음 | share/share.test › 읽기 전용(공유) 토큰이면 패널이 없고 GET /share-links 도 부르지 않는다 · ops/r11ops.test › 읽기 전용 토큰이면 공유 링크 메뉴·묶음이 없다(8칸) |
| 220 | Section 제목 (`page.G7.share.title` "읽기 전용 공유 링크") | Ops · ⑨ "보기만 할 수 있는 링크를 만들까요?" (메뉴 "공유 링크") | — | 있음 | share/share.test › 목록: 상태(활성·만료·회수)와 만료일 |
| 221 | 안내 (`page.G7.share.intro`) | Ops · ⑨ "이게 뭐예요?" 문단 | — | 있음 | share/share.test › 목록: 상태(활성·만료·회수)와 만료일 |
| 222 | 메모 입력칸 (`page.G7.share.label` "메모(누구에게·용도, 사람 이름 금지)", placeholder `labelHint` "예: 검토 요청") | Ops · ⑨ "메모 (누구에게·무슨 용도 — 사람 이름은 빼요)" placeholder "예: 검토 요청" | — | 있음 | share/share.test › label 은 64자까지 · share/share.test › label 이 비면 본문 label 없이(null) 보낸다 |
| 223 | 메모 최대 64자 (`SHARE_LABEL_MAX`) | — | — | 문구로만(고침 OP-13 — "구현 때 유지" 상자) · 입력칸 maxlength=64 | share/share.test › label 은 64자까지 · share/share.test › label 이 비면 본문 label 없이(null) 보낸다 |
| 224 | 발급 버튼 (`page.G7.share.create` "공유 링크 발급") | Ops · ⑨ "공유 링크 만들기" | 발급 → 만들기 | 있음 | share/share.test › 발급 → POST /share-links {label} → 링크(<origin>/share#토큰)를 한 번만 보이고 복사 |
| 225 | 발급 중 버튼 꺼짐 | — | — | 문구로만(고침 OP-13 — "구현 때 유지" 상자) | share/share.test › 발급 → POST /share-links {label} → 링크(<origin>/share#토큰)를 한 번만 보이고 복사 |
| 226 | 발급 오류 (`page.common.loadError`) | Ops · ⑨ "불러오지 못했어요: [서버 설명] (만들기·회수 실패 때)" | — | 있음 | share/share.test › 발급 → POST /share-links {label} → 링크(<origin>/share#토큰)를 한 번만 보이고 복사 |
| 227 | 새 링크 상자 제목 (`page.G7.share.createdTitle` "새 공유 링크") | Ops · ⑨ "만든 직후 예시" 라벨 "새 공유 링크" | — | 있음 | share/share.test › 발급 → POST /share-links {label} → 링크(<origin>/share#토큰)를 한 번만 보이고 복사 |
| 228 | 링크 주소 읽기 전용 칸 (`/share#<토큰>`, 토큰은 해시에만) | Ops · ⑨ 입력칸 "[이 서버 주소]/share#[한 번만 보이는 열쇠]" | — | 있음 | share/share.test › 발급 → POST /share-links {label} → 링크(<origin>/share#토큰)를 한 번만 보이고 복사 |
| 229 | 칸에 들어가면 전체 선택 (`onFocus select`) | — | — | 문구로만(고침 OP-13 — "구현 때 유지" 상자) | share/share.test › 발급 → POST /share-links {label} → 링크(<origin>/share#토큰)를 한 번만 보이고 복사 |
| 230 | 복사 버튼 (`page.G7.share.copy`) | Ops · ⑨ "복사" | — | 있음 | share/share.test › 발급 → POST /share-links {label} → 링크(<origin>/share#토큰)를 한 번만 보이고 복사 |
| 231 | 복사 성공 (`page.G7.share.copied`) / 실패 (`page.G7.share.copyFailed`) | Ops · ⑨ "복사했어요 · 실패하면: 복사하지 못했어요 — 주소를 직접 골라 복사하세요" | — | 있음 | share/share.test › 발급 → POST /share-links {label} → 링크(<origin>/share#토큰)를 한 번만 보이고 복사 |
| 232 | 닫기 버튼 (`page.G7.share.done`) | Ops · ⑨ "닫기" | — | 있음 | share/share.test › 발급 → POST /share-links {label} → 링크(<origin>/share#토큰)를 한 번만 보이고 복사 |
| 233 | 한 번만 보임 안내 (`page.G7.share.once`) | Ops · ⑨ "이 링크는 지금 한 번만 보여요. 닫기 전에 복사해서 전달하세요." | — | 있음 | share/share.test › 발급 → POST /share-links {label} → 링크(<origin>/share#토큰)를 한 번만 보이고 복사 |
| 234 | 만료일 (`page.G7.share.expires` "만료: {date}") | Ops · ⑨ "만료: [날짜]" | — | 있음 | share/share.test › 발급 → POST /share-links {label} → 링크(<origin>/share#토큰)를 한 번만 보이고 복사 |
| 235 | 목록 표 aria-label (`page.G7.share.list` "공유 링크 목록") | Ops · ⑨ "링크가 생긴 뒤 목록 예시" caption "공유 링크 목록" | — | 있음 | share/share.test › 목록: 상태(활성·만료·회수)와 만료일 |
| 236 | 목록 없음 (`page.G7.share.none` "발급한 공유 링크가 없습니다") | Ops · ⑨ "아직 만든 공유 링크가 없어요" | — | 있음 | share/share.test › 목록: 상태(활성·만료·회수)와 만료일 |
| 237 | 표 열: 메모 (`page.G7.share.col.label`) / 없으면 `page.common.none` "없음" | Ops · ⑨ 표 "메모" ("[메모]", "없음") | — | 있음 | share/share.test › 목록: 상태(활성·만료·회수)와 만료일 |
| 238 | 표 열: 상태 배지 사용 중·만료·회수됨 (`page.G7.share.col.status`, `page.G7.share.status.*`) | Ops · ⑨ 표 "상태" 3가지 | — | 있음 | share/share.test › 목록: 상태(활성·만료·회수)와 만료일 |
| 239 | 표 열: 발급일 (`page.G7.share.col.created`) | Ops · ⑨ 표 "만든 날" | 발급일 → 만든 날 | 있음 | share/share.test › 목록: 상태(활성·만료·회수)와 만료일 |
| 240 | 표 열: 만료일 / 회수됨이면 (`page.G7.share.revokedAt` "회수: {date}") | Ops · ⑨ 표 "만료일" + "회수: [날짜]" | — | 있음 | share/share.test › 목록: 상태(활성·만료·회수)와 만료일 |
| 241 | 표 열: 회수 버튼 (`page.G7.share.revoke`, 사용 중만, 열 머리 sr-only) | Ops · ⑨ 표 "회수" 열 + 버튼 | 열 머리가 보이게 | 있음 | share/share.test › 회수 → DELETE /share-links/{id} |
| 242 | 회수 중 버튼 꺼짐 | — | — | 문구로만(고침 OP-13 — "구현 때 유지" 상자) | share/share.test › 회수 → DELETE /share-links/{id} |
| 243 | 회수 오류 (`page.common.loadError`) | Ops · ⑨ "불러오지 못했어요: [서버 설명] (만들기·회수 실패 때)" | — | 있음 | share/share.test › 회수 → DELETE /share-links/{id} |
| 244 | API `GET /share-links` · `POST /share-links` {label} · `DELETE /share-links/{id}` | Ops · ⑨ 목록·"공유 링크 만들기"·"회수"(호출 주체) | — | 있음 | share/share.test › 발급 → POST … · share/share.test › 회수 → DELETE … · share/share.test › 목록 … |

## 작업 진행 칸 (①③⑦ — PublishJobProgress · JobProgress 공통)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 245 | 발행 대기 안내 (`job.publishPending`) | Ops · ③ "작업이 끝나 새 수정본이 발행될 때까지 화면은 지금 발행본을 보여요." | — | 있음 | r3g2.test › 화면: rejudge done → publish_job_id 잡을 이어 감시 → 그 잡 done 이면 "발행됨" |
| 246 | 진행 상태·수·단계·막대 (`job.status.*`, `job.progress`, `job.step`) | Ops · ①③⑦ role=progressbar + "실행 중" | — | 있음 | components.contract.test › JobProgressView: 계약 progress(done/total·step)를 보여 준다 |
| 247 | 진행 수 없을 때 미정 막대 | — | — | 있음(고침 OP-11 — 펼친 모습 "①③⑦ 작업 진행 칸" 줄무늬 미정 막대) | components/shell-components.test › 진행 수가 없으면 끝을 모르는 줄무늬 막대(role=progressbar, 값 없음) |
| 248 | 발행 완료 (`job.publishDone`) | Ops · 펼친 모습 "①③⑦ 작업 진행 칸의 다른 문구" "새 수정본이 발행됐어요 — 화면 기본이 새 수정본으로 바뀌어요" | — | 있음 | r3g2.test › 화면: rejudge done → publish_job_id 잡을 이어 감시 → 그 잡 done 이면 "발행됨" |
| 249 | 미룸 (`job.publishDeferred`) | Ops · 같은 목록 "이 변경은 지금 판정 중인 새 수정본에 들어가…" | — | 있음 | r3g2.test › 화면: 후속 발행 잡이 미뤄지면(deferred_to) 그 리비전 발행까지 기다린다는 안내 |
| 250 | 재등록 (`job.publishRedeferred`) | Ops · 같은 목록 "미뤄 둔 수정본의 발행이 끝내 실패해…" | — | 있음 | r3i2.test › 화면: rejudge → 발행 잡 미룸(deferred) → 나중에 redeferred_job_id → … 재등록 안내 |
| 251 | 발행 막힘 — 사유 (`job.publishBlocked`) · 남은 모순 수 (`publishBlockedContradicted`) · 사유 모름 (`publishBlockedUnknown`) | Ops · 같은 목록 "발행이 막혔어요(남은 모순 주장 등) — ⑦에서 주장을 고치면 다시 발행돼요: [설명] · 남은 모순 주장 [n]건 · 이유 확인 불가" | — | 있음 | r3h.test › 화면: "남은 모순 주장 1,234건" … · r3h.test › 화면: 서버 사유(failed publish_blocked: …)는 코드 접두를 떼고 보인다 |
| 252 | 발행 실패 (`job.publishFailed`) | Ops · 같은 목록 "발행 작업이 실패했어요 — 화면은 지금 발행본을 계속 보여요: [설명]" | — | 있음 | r3h2.test › publishPhase: queued 재큐잉 = waiting · 40회 넘어 failed = 발행 실패 |
| 253 | 사슬 상한 (`job.publishChainCapped`) | Ops · 같은 목록 "발행 작업을 [n]단계까지 따라갔지만…" | — | 있음 | r3h.test › 사슬은 PUBLISH_CHAIN_MAX단계에서 멈추고 그렇다고 알린다(조용히 기다리지 않는다) |
| 254 | 30분 상한 (`job.publishExpired`) | Ops · 같은 목록 "30분 동안 발행 완료를 확인하지 못해 멈췄어요…" | — | 있음 | r3g.test › snapshotsWatchExpired: 잡을 모르는(forbidden·truncated·failed) 채 생성 30분이 지나면 true |
| 255 | 조회 일시 오류 (`job.retrying`) · 오류 (`job.error`) · 잡 없음 (`job.none`) | Ops · 같은 목록 "상태를 받지 못해 다시 확인하는 중: [설명] · 오류: [설명] · 진행 중인 작업 없음" | — | 있음 | r3f.test › JobProgressView: 받아 둔 잡이 있으면 일시 오류 동안 … · components/shell-components.test › 작업 없음 · 오류 문구 |
| 256 | 빈 데이터셋 상한 실패 (`job.degradedFailed`) | Ops · ⑤ 펼친 모습 "실패 … 발행하지 않았어요: [사유]" | — | 있음 | r4fe12.test › JobProgressView: 6회 넘어 failed(degraded_source) — 코드 접두 없이 멈춘 이유 |
| 257 | 사슬 후속 잡 줄 (rejudge → publish) | Ops · ③ "작업 진행 · 다시 판정 · 실행 중"(첫 잡만 그림) + "발행 작업을 [n]단계까지 따라갔지만…" | — | 문구로만 | r3g2.test › 화면: rejudge done → publish_job_id 잡을 이어 감시 …(사슬 후속 잡) |
| 258 | API `GET /jobs/{id}` 사슬 폴링 + `GET /regions/{id}/snapshots` | Ops · ①③⑦ 작업 진행 칸(호출 주체) | — | 있음 | r3g2.test › 화면: rejudge done → publish_job_id 잡을 이어 감시 …(잡 목록 조회 없음) |

요약: 전체 258 · 있음 241 · 문구로만 17 · 다른 보드 0 · 빠짐 0 (2026-10-16 고침 반영 — fixes/fixes-Ops.md)

빠짐 목록: 없음 (2026-10-16 고침 반영)
- 고침 전 빠짐 18개: #17 → 있음(OP-2), #61 → 있음(OP-6), #122·#129·#132 → 있음(OP-5·OP-3·OP-4), #147 → 있음(OP-12), #182 → 있음(OP-7), #196·#197 → 있음(OP-8), #247 → 있음(OP-11)
- #8·#115·#116·#117·#223·#225·#229·#242 → 문구로만(OP-13 "구현 때 유지" 상자)

## 새로 더한 것 (기존에 없던 것)

| # | 새 기능 | 위치 (보드 · 섹션) | 비고 | 테스트 |
|---|---|---|---|---|
| N1 | 머리 상태 줄 "판정기 연결 정상 · 마지막 발행 2026-10-15 06:14 · 운영 기록 09:04 조회" | 머리 | 어떤 API 값인지 구현 때 정해야 함 |
| N2 | "오늘 확인할 것" 타일 4장(사람 확인 필요 단지 · 수집 실패 자료 · 모순 주장 · 2주 안 기한) + 각 섹션 바로가기 | "오늘 확인할 것" | 고침 OP-10: "급한 것·나중에" 같은 판단 이름을 빼고 대기열 분류 이름·건수 그대로, 모순 주장 타일은 목록 줄 수만(OP-9). 2주 안 기한은 줄 개수 세기(D25-3) |
| N3 | 섹션 메뉴 9칸 + 건수 배지, "한 번에 한 묶음씩 보여요", 휴대폰에서는 위로 쌓이고 옆으로 밀기 | 메뉴 | 탭형 내비 |
| N4 | 섹션마다 "이게 뭐예요?" 설명 + 응답 코드·확신 정도 `?` 버튼 | ①~⑨ | |
| N5 | 체크리스트 필터 "종류" · "상태"(건수 포함), 요약 "전체 329건 · 열림 316 · 해당 없음 13", "기한 가까운 순" 정렬, D-day("D-4·오늘·어제 지남"), "320건 더 보기" | ① | 지금은 필터·정렬·더 보기 없음 |
| N6 | 월 달력 격자(날짜 칸 점 표시, 오늘 테두리) + 이전·다음 달 버튼 "‹ 9월" "11월 7건 ›" + 색 범례 | ① | 지금은 월별 목록만 |
| N7 | 대기열 분류 요약 줄 "연결 안 됨 8 · 보안 연결 오류 4 · 페이지 없음 2", 묶음 "펼치기" 버튼, "이 묶음 n건 더 보기" | ② | |
| N8 | 확인 방법을 라디오로 · 메모 글자 수 "0/500" · 숫자 규칙 표 "값을 이렇게 넣어 주세요" | ③ | |
| N9 | 실패 소스 수 요약 "실패가 있는 곳 1 / 8", 실패 대상 "10곳 더 보기" | ④ | |
| N10 | 작업 쉬운 이름("새 수정본 발행"·"다시 판정"·"매일 수집"·"백업"), 요약 "최근 29건 · 모두 완료", 종류별 개수 줄, "21건 더 보기" | ⑤ | |
| N11 | 판단 종류별 막대를 "실제로 보냄 / 저장된 결과 다시 씀" 두 색으로 나눔 + "표로 보기" + 안전 검사 막힘 횟수 | ⑥ | |
| N12 | 판정 표 "무엇을 판단했나" 쉬운 말 설명 | ⑥ | |
| N13 | 모순 주장 요약 "모순 주장 0건 (목록 줄 수)" + "맞음 [n] · 사람 검토 [n] — API 필요" 메모 | ⑦ | 고침 OP-9: 지금 API(`status=contradicted`)에 없는 맞음 19·검토 5와 판단 문장 "막히지 않아요"를 뺌 |
| N14 | 경계 단지 요약 "기준일 2026-10-15 · 4곳" | ⑧ | |
| N15 | "휴대폰에서는 읽기 전용이에요(입력 칸·버튼이 꺼져요)" | 펼친 모습 · 공통 상태 | 새 동작 |
| N16 | 진행 칸 목록의 "다시 확인" 버튼(발행 대기 30분 멈춤) | 펼친 모습 · ①③⑦ 문구 | 지금은 머리줄 Header(`job.watchExpired`·`job.watchRecheck`)에만 있음 |
| N17 | 맨 아래 원칙 안내 "판단은 판정기만 하고, 이 화면은 기록·확인·재시도만 해요" + 라벨 범례(확인됨·추정·사람 확인) | 맨 아래 | |

## 구현 메모 — R11-MARKETOPS (2026-10-16, 브랜치 wp/r11-marketops)

`테스트` 열 = `frontend/src/pages/` 기준 파일(확장자 `.tsx` 생략) › 테스트 이름(앞부분). `components/`·`layout/` 는 `frontend/src/` 기준. "(… — 코드)"는 그 줄만 흉내 내는 테스트가 없어 같은 코드 경로를 지나는 테스트와 코드 위치를 함께 적은 것이다.

새로 더한 것(N) 구현 여부:
- 구현: N2('오늘 확인할 것' 타일 4장 — 대기열 `total`·분류별 줄 수, 실패 자료 줄 수, 모순 줄 수, 2주 안 열린 기한 줄 수 · 기한 지난 열린 줄 수) · N3(묶음 메뉴 — 데스크톱 왼쪽 따라오는 세로 메뉴, 좁은 화면 위 한 줄 옆으로 밀기, 건수 배지는 줄 수·서버 total) · N4("이게 뭐예요?" 한 줄 — 9묶음 모두) · N13(모순 주장 = 상태 필터 없이 받은 목록의 모순 줄 수 + 상태별 줄 수, 계약 .22 A5) · N14(경계 단지 n곳) · N10 일부(작업 쉬운 이름 `jobNameText`·단계 `jobStepText`, 최근 n건).
- 화면 동작: 묶음은 모두 아래로 펼쳐 보인다(목업 "한 번에 한 묶음씩"은 하지 않음 — #intake-queue → #human-check 미리 채움 흐름과 기존 테스트가 두 묶음을 함께 본다). 메뉴·타일은 `?쿼리#묶음` 링크 + 그 카드로 스크롤.
- 하지 않음: N1(머리 상태 줄 — 어떤 API 값인지 미정) · N5(체크리스트 필터·정렬·더 보기) · N6(월 달력 격자) · N7(대기열 요약 줄·더 보기) · N8(확인 방법 라디오·글자 수) · N9(실패 요약 n/8은 알약으로만, 더 보기 없음) · N11(두 색 막대·표로 보기) · N12(판정 목적 쉬운 말 — G3 JudgmentTable 소유) · N16 · N17(원칙 안내 — 진입 청크 예산).
