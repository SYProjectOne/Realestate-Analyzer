# 대응표 — 보고서 G8 (`/reports`, `frontend/src/pages/reports`) + 공유 링크 받기 (`/share#토큰`, `frontend/src/pages/share`) → Reports.dc.html

입력: `frontend/src/pages/reports/index.tsx`, `frontend/src/pages/share/index.tsx`, `pages/_shared/index.tsx`, `components/SnapshotPicker.tsx·JobProgress.tsx`, `api/download.ts`, `api/auth.ts`, `i18n/ko.json` · 보드: `boards/Reports.dc.html`

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 1 | [틀] 화면 제목 h1 (`pages/reports/index.tsx` PageShell · `page.G8.title` "보고서") | Reports · h1 "보고서를 만들어 볼까요?" + 소개 문단 | 보고서 → 보고서를 만들어 볼까요? | 있음 | `RP11` 머리: 지역 · 발행된 기준일 수 · 만든 보고서 수(목록 세기) + 질문형 h1 + 소개<br>`RT` 라우트 10개 — G8 /reports → 제목을 렌더한다<br>`E2P` G8 보고서: 생성 버튼 · 목록 · 다운로드 |
| 2 | [틀] 지역을 바꾸면 고른 값·생성 오류·잡 진행 모두 초기화 (`pages/reports/index.tsx` ReportsPage key) | Reports · 바닥 "구현할 때 지금 동작 그대로 유지" 상자 | — | 문구로만(고침 RP-7) | `R3G` 409 오류가 난 뒤 지역을 바꾸면 오류 문구가 사라진다<br>`R3G` 잡을 등록한 뒤 지역을 바꾸면 그 잡 진행을 내린다<br>`R3F` 지역을 바꾸면 이전 지역에서 고른 기준·비교 리비전을 POST 하지 않는다 |
| 3 | [보고서 만들기] 구역 제목 (`pages/reports/index.tsx` · `page.G8.generate` "보고서 생성") | Reports · "보고서 만들기" h2 "네 가지만 고르면 돼요" + '이게 뭐예요?' | 보고서 생성 → 보고서 만들기 | 있음 | `RP11` 만들기 4단계: 질문형 라벨 · 설명(?) · 선택 요약 · 만들 수 있어요(남은 모순 주장 0건) · 진행 자리표시<br>`RP` 생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress |
| 4 | [보고서 만들기] 기준 리비전 select — 발행 리비전만 (`components/SnapshotPicker.tsx` SnapshotPicker · `page.G8.snapshot` "기준일(리비전)") | Reports · 1 "어느 기준일 자료로 만들까요?" select | 기준일(리비전) → 기준일(수정본) | 있음 | `R3D` 비교 선택에 리비전 표기, 생성 중 리비전은 빠진다; 생성 중 기준이면 생성 막음<br>`TD` 읽기 전용 토큰 → 저장(role=read) · 안내 배너 · 쓰기 버튼 비활성<br>`RP11` 만들기 4단계: 질문형 라벨 · 설명(?) · 선택 요약 · 만들 수 있어요(남은 모순 주장 0건) · 진행 자리표시 |
| 5 | [보고서 만들기] 옵션 이름 n번째 리비전 + title 리비전 사유 (`components/SnapshotPicker.tsx` snapshotText·snapshotTitle · `picker.revision` · `picker.revisionReason`) | Reports · 1 옵션 "2026.10.14 · 7번째 수정본" title "7번째 수정본: 같은 날 다시 모음" | 리비전 → 수정본 | 있음 | `R3D` 비교 선택에 리비전 표기, 생성 중 리비전은 빠진다; 생성 중 기준이면 생성 막음<br>`E2W7` M-16 G8: 기준·비교 선택이 리비전을 구별 → 새 리비전 기준·이전 리비전 비교 보고서 → 목록 행 리비전 표기 |
| 6 | [보고서 만들기] 옵션 꼬리 일부 수집 실패·만드는 중 (`picker.snapshotDegraded` · `picker.snapshotBuilding`) | Reports · 1 설명 "일부 수집이 실패한 기준일은 '일부 수집 실패', 만드는 중이면 '만드는 중'이 이름 옆에 붙어요" | — | 문구로만 | `R3D` 비교 선택에 리비전 표기, 생성 중 리비전은 빠진다; 생성 중 기준이면 생성 막음 |
| 7 | [보고서 만들기] 비교 select + "비교 안 함" (`page.G8.compareSnapshot` "이전 기준일과 비교(선택)" · `page.G8.noCompare`) | Reports · 2 "이전 기준일과 비교할까요? (골라도 되고 안 골라도 돼요)" + "비교 안 함" | — | 있음 | `RP` 생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress<br>`R3E` 비교 선택은 발행 리비전만(ready·building 제외) |
| 8 | [보고서 만들기] 비교 후보 = 대상보다 앞선 같은 지역 발행 리비전만 + title (`pages/reports/index.tsx` compareCandidates·isOlderRevision · `page.G8.compareOlderOnly`) | Reports · 2 옵션이 앞선 것만 + "고른 기준일보다 앞선 발행본만 나와요" | — | 있음 | `R3F2` isOlderRevision·compareCandidates: (기준일, 리비전, id) 순 — 자기 자신·더 새 리비전 제외<br>`R3E` 비교 선택은 발행 리비전만(ready·building 제외)<br>`R3F2` ?scenario=<발행 뒤 만든 시나리오> + 대상 12 → 생성 막고 안내, "리비전 13 으로" → 대상 바꿔 scenario_id 와 POST |
| 9 | [보고서 만들기] 기준을 비교 리비전으로 바꾸면 비교 해제 (`pages/reports/index.tsx` pickBase) | Reports · 바닥 "구현할 때 지금 동작 그대로 유지" 상자 | — | 문구로만(고침 RP-7) | `R3F` 비교로 고른 리비전을 기준으로 바꾸면 비교는 없음으로 — 같은 id 를 비교로 보내지 않는다 |
| 10 | [보고서 만들기] 시나리오 select + 기본 (`page.G8.scenario` "보고서 시나리오" · `page.G8.scenarioDefault` "기본(서버 기본 시나리오)") | Reports · 3 "어떤 상황으로 볼까요? (시나리오)" 옵션 "기본 상황 (서버 기본값)" · A~D | 보고서 시나리오 → 어떤 상황으로 볼까요? | 있음 | `R3F2` 내장 시나리오는 대상 리비전 검사 없이 scenario_id 로 보낸다<br>`R3F2` ?scenario=<발행 뒤 만든 시나리오> + 대상 12 → 생성 막고 안내, "리비전 13 으로" → 대상 바꿔 scenario_id 와 POST |
| 11 | [보고서 만들기] 고르지 않으면 전역 ?scenario= 따름 (`pages/reports/index.tsx` globalScenario) | Reports · 바닥 "구현할 때 지금 동작 그대로 유지" 상자 | — | 문구로만(고침 RP-7) | `R3F2` 내장 시나리오는 대상 리비전 검사 없이 scenario_id 로 보낸다 |
| 12 | [보고서 만들기] 형식 묶음 fieldset·legend (`page.G8.format` "형식") | Reports · 4 "어떤 파일로 받을까요?" | 형식 → 어떤 파일로 받을까요? | 있음 | `RP11` 만들기 4단계: 질문형 라벨 · 설명(?) · 선택 요약 · 만들 수 있어요(남은 모순 주장 0건) · 진행 자리표시 |
| 13 | [보고서 만들기] 형식 라디오 HTML (`page.G8.formats.html`) | Reports · 4 "HTML 브라우저에서 바로 열어요" | — | 있음 | `RP11` 만들기 4단계: 질문형 라벨 · 설명(?) · 선택 요약 · 만들 수 있어요(남은 모순 주장 0건) · 진행 자리표시<br>`E2A` G8 보고서: 생성(POST) → 워커 1회 → 목록 완료 → Bearer 다운로드 |
| 14 | [보고서 만들기] 형식 라디오 PDF (`page.G8.formats.pdf`) | Reports · 4 "PDF 인쇄·보관할 때" | — | 있음 | `RP` 생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress<br>`FL1` G8 보고서 PDF: 생성 → worker → 목록 완료 → 다운로드(%PDF, 페이지 > 0) |
| 15 | [보고서 만들기] 생성 버튼 → POST /reports {snapshot_id, format, compare_snapshot_id, scenario_id} (`page.G8.generate`) | Reports · [보고서 만들기] | 보고서 생성 → 보고서 만들기 | 있음 | `RP` 생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress<br>`ACC` G8 /reports: 생성 버튼·보고서 목록<br>`E2A` G8 보고서: 생성(POST) → 워커 1회 → 목록 완료 → Bearer 다운로드<br>`FL1` G8 보고서 PDF: 생성 → worker → 목록 완료 → 다운로드(%PDF, 페이지 > 0) |
| 16 | [보고서 만들기] 읽기 전용이면 버튼 꺼짐 + title (`auth.readOnlyHint`) | Reports · 만들 수 없을 때 "'보고서 만들기' 버튼이 꺼진 모습" — 꺼진 버튼 + 올리면 "읽기 전용 열쇠로는 저장·실행할 수 없어요" | 토큰 → 열쇠 | 있음(고침 RP-2) | `RP` 읽기 전용 토큰이면 생성 버튼 비활성 + 안내, 다운로드는 된다<br>`TD` 읽기 전용 토큰 → 저장(role=read) · 안내 배너 · 쓰기 버튼 비활성 |
| 17 | [보고서 만들기] 기준 없음·요청 중이면 버튼 꺼짐 (create.isPending) | Reports · 같은 블록 꺼지는 조건 목록(기준일 안 고름 · 막힘 · 요청 보내는 중) | — | 있음(고침 RP-2) | `R3D` 비교 선택에 리비전 표기, 생성 중 리비전은 빠진다; 생성 중 기준이면 생성 막음<br>`RP` 읽기 전용 토큰이면 생성 버튼 비활성 + 안내, 다운로드는 된다 |
| 18 | [막힘] 생성 중 리비전 (`pages/reports/index.tsx` blockReason · `page.G8.building`) | Reports · "버튼이 꺼지는 경우 막힘 4가지" 1 "만드는 중인 수정본은 보고서를 만들 수 없어요." | — | 있음 | `R3D` 비교 선택에 리비전 표기, 생성 중 리비전은 빠진다; 생성 중 기준이면 생성 막음 |
| 19 | [막힘] 발행 전 리비전 (`page.G8.unpublished`) | Reports · 막힘 2 "아직 발행되지 않은 수정본은 …" | — | 있음 | `R3E` ready(발행 전) 기준이면 생성 버튼 비활성 + 안내, 요청을 보내지 않는다 |
| 20 | [막힘] 모순 주장 남음 (`page.G8.blocked` "모순(contradicted) 주장 {n}건이 남아 생성할 수 없습니다") | Reports · 막힘 3 "모순 주장 [n]건이 남아 만들 수 없어요." | — | 있음 | `RP` contradicted claim이 있으면 생성 버튼 비활성 + 사유<br>`RP11` 모순 주장이 남으면: 막힌 이유(role=alert, 버튼이 가리킴) + 데이터·운영 화면으로 고치러 가는 링크, "만들 수 있어요" 없음 |
| 21 | [막힘] 시나리오가 리비전 발행 뒤에 만들어짐 (`pages/reports/index.tsx` scenarioMadeAfterPublish · `page.G8.scenarioNotInRevision`) | Reports · 막힘 4 "'[상황 이름]' 상황은 이 수정본이 발행된 뒤에 만들어져서 …" | — | 있음 | `R3F2` ?scenario=<발행 뒤 만든 시나리오> + 대상 12 → 생성 막고 안내, "리비전 13 으로" → 대상 바꿔 scenario_id 와 POST |
| 22 | [막힘] 결과가 있는 리비전으로 바꾸는 버튼 (`pages/reports/index.tsx` revisionWithScenario · `page.G8.scenarioPickRevision` "대상 리비전을 {snapshot}(으)로") | Reports · 막힘 4 [대상 수정본을 [2026.10.15]로 바꾸기] | 리비전 → 수정본 | 있음 | `R3F2` ?scenario=<발행 뒤 만든 시나리오> + 대상 12 → 생성 막고 안내, "리비전 13 으로" → 대상 바꿔 scenario_id 와 POST<br>`R3G` G8: 서버가 422 scenario_not_in_revision 인데 화면이 맞다고 본 리비전이 가장 새 것이면 — 같은 리비전을 추천(숨김)하지 않고 다른 리비전 또는 시나리오 실행 안내 |
| 23 | [막힘] 결과 리비전이 없으면 시나리오 실행 링크 (`page.common.scenarioMissingRun`) | Reports · 막힘 4 [결과가 있는 수정본이 없으면: 시나리오 실행 화면으로] | — | 있음 | `R3G` G8: 서버가 422 scenario_not_in_revision 인데 화면이 맞다고 본 리비전이 가장 새 것이면 — 같은 리비전을 추천(숨김)하지 않고 다른 리비전 또는 시나리오 실행 안내 |
| 24 | [오류] 409 만들 수 없음 (`pages/reports/index.tsx` createErrorText · `page.G8.conflict`) | Reports · "누른 뒤 오류가 나는 경우 오류 4가지" 1 "보고서를 만들 수 없어요: [서버 설명]" | — | 있음 | `R3E` POST /reports 409 conflict(발행 전 등) → 안내 문구(조용히 묻히지 않는다)<br>`R3D` POST /reports 409 → 리비전 목록·보고서 목록을 다시 받는다<br>`RP11` 409 publish_blocked 도 고칠 곳 링크를 붙이고, 만들기를 누르면 진행 자리표시가 작업 진행으로 바뀐다 |
| 25 | [오류] 422 scenario_not_in_revision + 거절 리비전 뺀 바꾸기 버튼 (`page.G8.scenarioNotInRevisionServer`) | Reports · 오류 2 "이 수정본에는 고른 상황 결과가 없어요 — … ([서버 설명])" + [대상 수정본을 [기준일]로 바꾸기] | — | 있음 | `R3F2` 서버 422 scenario_not_in_revision → 안내 + 대상 다시 고르기 버튼<br>`R3F2` createErrorText: 422 scenario_not_in_revision·503 materialize_pending 안내<br>`R3G` G8: 서버가 422 scenario_not_in_revision 인데 화면이 맞다고 본 리비전이 가장 새 것이면 — 같은 리비전을 추천(숨김)하지 않고 다른 리비전 또는 시나리오 실행 안내 |
| 26 | [오류] 503 보고서 자료 준비 중 (`page.G8.pending`) | Reports · 오류 3 "이 수정본의 보고서 자료를 아직 준비하는 중이에요 — …" | — | 있음 | `R3H2` 생성 버튼 → 503 → 준비 중 안내<br>`R3I2` 비교 리비전을 고르지 않고 생성 → 503 → 준비 중 안내<br>`R3F2` createErrorText: 422 scenario_not_in_revision·503 materialize_pending 안내 |
| 27 | [오류] 그 밖의 생성 요청 실패 (`page.G8.createError`) | Reports · 오류 4 "보고서 만들기 요청이 실패했어요: [설명]" | — | 있음 | `R3F2` createErrorText: 422 scenario_not_in_revision·503 materialize_pending 안내 |
| 28 | [막힘·오류] 안내는 버튼 아래 role=alert, 버튼 aria-describedby (id g8-blocked) | Reports · 막힘·오류 줄 role=alert + "안내는 '보고서 만들기' 버튼 바로 아래에 떠요" | — | 있음 | `RP11` 모순 주장이 남으면: 막힌 이유(role=alert, 버튼이 가리킴) + 데이터·운영 화면으로 고치러 가는 링크, "만들 수 있어요" 없음 |
| 29 | [막힘·오류] 기준·시나리오를 다시 고르면 오류 지움 (create.reset) | Reports · 바닥 "구현할 때 지금 동작 그대로 유지" 상자 | — | 문구로만(고침 RP-7) | `R3F2` ?scenario=<발행 뒤 만든 시나리오> + 대상 12 → 생성 막고 안내, "리비전 13 으로" → 대상 바꿔 scenario_id 와 POST (대상 바꾸면 안내가 사라짐) |
| 30 | [작업 진행] 생성 뒤 JobProgress — 제목·잡 이름·상태·진행 수·단계·막대 (`components/JobProgress.tsx` · `job.title` · `job.status.*` · `job.progress` · `job.step`) | Reports · "누른 뒤 이 자리에 진행 상황이 보여요" 예시 "작업 진행 보고서 만들기 (report) 실행 중 [n]/[n] · 단계" + progressbar | — | 있음 | `RP` 생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress<br>`CT` JobProgressView: 상태 텍스트<br>`CC` JobProgressView: 계약 progress(done/total·step)를 보여 준다<br>`E2A` G8 보고서: 생성(POST) → 워커 1회 → 목록 완료 → Bearer 다운로드 |
| 31 | [작업 진행] 상태 다시 확인 중 (`job.retrying`) | Reports · 진행 예시 아래 상태 줄 "상태를 받지 못해 다시 확인하는 중: [설명]" | — | 있음(고침 RP-1) | `R3F` JobProgressView: 받아 둔 잡이 있으면 일시 오류 동안 마지막 상태 + 다시 확인 중 줄 |
| 32 | [작업 진행] 잡 오류 (`job.error`) | Reports · 같은 자리 "오류: [설명]" | — | 있음(고침 RP-1) | `CT` JobProgressView: 상태 텍스트<br>`FE12` JobProgressView: 6회 넘어 failed(degraded_source) — 코드 접두 없이 멈춘 이유 |
| 33 | [작업 진행] 재큐잉·불완전 수집 안내 (`components/JobProgress.tsx` JobRequeueNote) | Shell · 6 "작업 진행 · 알림" | — | 다른 보드(Shell) | coverage-Shell.md 6 작업 진행 행의 테스트<br>`FE12` JobProgressView: 발행 busy 재큐잉 문구는 그대로(회귀) |
| 34 | [작업 진행] 끝나면 보고서 목록 다시 받기 (invalidate ['reports']) | Reports · 바닥 "구현할 때 지금 동작 그대로 유지" 상자 | — | 문구로만(고침 RP-7) | `R3D` report 잡 완료는 보고서 목록만<br>`E2A` G8 보고서: 생성(POST) → 워커 1회 → 목록 완료 → Bearer 다운로드<br>`FL1` G8 보고서 PDF: 생성 → worker → 목록 완료 → 다운로드(%PDF, 페이지 > 0) |
| 35 | [보고서 목록] 구역 제목 (`pages/reports/index.tsx` ReportList · `page.G8.list` "보고서 목록") | Reports · "만든 보고서" h2 "지금까지 만든 보고서" + '이게 뭐예요?' | 보고서 목록 → 지금까지 만든 보고서 | 있음 | `RP` 보고서가 없으면 무엇이 들어가는지·어떻게 만드는지·진행이 어디 보이는지 안내<br>`RP11` 만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼<br>`ACC` G8 /reports: 생성 버튼·보고서 목록 |
| 36 | [보고서 목록] 빈 상태 제목 + 무엇이 들어가나·어떻게 만드나·진행은 어디 (`page.G8.emptyTitle` · `emptyBody` · `emptyHow` · `emptyProgress`) | Reports · "아직 만든 보고서가 없어요" + 세 문장 | 보고서 생성 → 보고서 만들기 | 있음 | `RP` 보고서가 없으면 무엇이 들어가는지·어떻게 만드는지·진행이 어디 보이는지 안내 |
| 37 | [보고서 목록] 불러오는 중 (QueryState · `app.loading`) | Reports · "이 화면의 공통 상태 예시" "목록·비교 표를 불러오는 중: 불러오는 중…" | — | 있음 | `SC` Skeleton: 뼈대 줄(장식) + "불러오는 중…"(role=status, N9) |
| 38 | [보고서 목록] 오류 (QueryError) | Reports · 공통 상태 "불러오지 못했어요: [설명] [다시 시도]" | 일반 오류에 [다시 시도] 버튼이 붙음 | 있음 | coverage-Shell.md §7 QueryState 오류 카드 행의 테스트 |
| 39 | [보고서 목록] 준비 중 (`page.common.materializePending`) | Reports · 공통 상태 "이 발행본의 화면 자료를 준비하는 중이에요 …" | — | 있음 | `R3F2` (F15 503 materialize_pending → 준비 중 → 자동 재시도) |
| 40 | [보고서 목록] 열 생성 (`page.G8.col.created` · formatDate) | Reports · 목록 예시 "만든 때" | 생성 → 만든 때 | 있음 | `RP11` 만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼 |
| 41 | [보고서 목록] 열 기준 (`page.G8.col.snapshot`) | Reports · 목록 예시 "기준일" | 기준 → 기준일 | 있음 | `RP11` 만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼<br>`E2W7` M-16 G8: 기준·비교 선택이 리비전을 구별 → 새 리비전 기준·이전 리비전 비교 보고서 → 목록 행 리비전 표기 |
| 42 | [보고서 목록] 열 비교 (`page.G8.col.compare`) | Reports · 목록 예시 "비교한 기준일" | 비교 → 비교한 기준일 | 있음 | `RP11` 만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼<br>`E2W7` M-16 G8: 기준·비교 선택이 리비전을 구별 → 새 리비전 기준·이전 리비전 비교 보고서 → 목록 행 리비전 표기 |
| 43 | [보고서 목록] 열 형식 (`page.G8.col.format`) | Reports · 목록 예시 "형식" | — | 있음 | `RP11` 만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼 |
| 44 | [보고서 목록] 열 상태 (`page.G8.col.status`) | Reports · 목록 예시 "상태" | — | 있음 | `RP11` 만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼 |
| 45 | [보고서 목록] 열 크기 (`page.G8.col.size` · `page.G8.sizeKb` "{kb}KB") | Reports · 목록 예시 "크기" "[n]KB" | — | 있음 | `RP11` 만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼 |
| 46 | [보고서 목록] 열 파일 (`page.G8.col.file`) | Reports · 목록 예시 "파일" | — | 있음 | `RP11` 만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼<br>`RP` 보고서 목록: 완료된 것만 다운로드 버튼 → GET /reports/{id}(Bearer) → 파일 이름으로 저장 |
| 47 | [보고서 목록] 기준·비교 칸 리비전 이름, 목록에 없으면 "스냅샷 #{id}" (`page.G8.snapshotId`) | Reports · 목록 예시 "2026.10.14 · 7번째 수정본" · "기준일 #[번호]" | 스냅샷 #id → 기준일 #번호 | 있음 | `E2W7` M-16 G8: 기준·비교 선택이 리비전을 구별 → 새 리비전 기준·이전 리비전 비교 보고서 → 목록 행 리비전 표기<br>`RP11` 만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼 |
| 48 | [보고서 목록] 상태 배지 4종 (`job.status.*` 대기·실행 중·완료·실패) | Reports · 목록 예시 완료·실행 중·실패 + "상태는 대기 · 실행 중 · 완료 · 실패 네 가지예요" | — | 있음 | `RP11` 만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼 |
| 49 | [보고서 목록] 막힌 이유 blocked_reason | Reports · 목록 예시 "실패 [막힌 이유]" | — | 있음 | `RP11` 만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼 (blocked_reason 줄) |
| 50 | [다운로드] 완료된 것만 파일 이름 버튼 → GET /reports/{id}(Bearer) 저장 (`api/download.ts` useDownload · reportRequest) | Reports · 목록 예시 [[파일 이름].html] (뒤에 붙던 '받기'는 뺌 — 파일 이름 그대로) | — | 있음(고침 RP-3) | `RP` 보고서 목록: 완료된 것만 다운로드 버튼 → GET /reports/{id}(Bearer) → 파일 이름으로 저장<br>`DL` 저장한 토큰을 Authorization 으로 싣고, Content-Disposition 이름으로 저장한다<br>`E2P` G8 보고서: 생성 버튼 · 목록 · 다운로드<br>`FL1` G8 보고서 PDF: 생성 → worker → 목록 완료 → 다운로드(%PDF, 페이지 > 0) |
| 51 | [다운로드] 파일 이름 없으면 "다운로드" (`page.common.download`) | Reports · 목록 예시 줄 [다운로드] "파일 이름이 없을 때" | — | 있음(고침 RP-3) | `RP11` 다운로드: 파일 이름이 없으면 "다운로드" · 받는 동안 "내려받는 중…"(꺼짐) · 실패는 버튼 아래 role=alert · 409 면 목록 다시 받기(#51~#54)<br>`DL` 이름이 없으면 fallbackName(보고서 목록의 filename) |
| 52 | [다운로드] 받는 중 버튼 꺼짐 (`download.pending` "내려받는 중…") | Reports · 목록 예시 줄 꺼진 [내려받는 중…] | — | 있음(고침 RP-3) | `RP11` 다운로드: 파일 이름이 없으면 "다운로드" · 받는 동안 "내려받는 중…"(꺼짐) · 실패는 버튼 아래 role=alert · 409 면 목록 다시 받기(#51~#54) |
| 53 | [다운로드] 받기 실패 role=alert (`download.error` "내려받지 못했습니다: {detail}") | Reports · 목록 예시 줄 role=alert "내려받지 못했어요: [설명]" | — | 있음(고침 RP-3) | `RP11` 다운로드: 파일 이름이 없으면 "다운로드" · 받는 동안 "내려받는 중…"(꺼짐) · 실패는 버튼 아래 role=alert · 409 면 목록 다시 받기(#51~#54) |
| 54 | [다운로드] 409(아직 미완료)면 목록 다시 받기 (`pages/reports/index.tsx` ReportRow conflict) | Reports · 바닥 "구현할 때 지금 동작 그대로 유지" 상자 | — | 문구로만(고침 RP-7) | `RP11` 다운로드: 파일 이름이 없으면 "다운로드" · 받는 동안 "내려받는 중…"(꺼짐) · 실패는 버튼 아래 role=alert · 409 면 목록 다시 받기(#51~#54) |
| 55 | [다운로드] 읽기 전용이어도 다운로드는 됨 | Reports · 바닥 "구현할 때 지금 동작 그대로 유지" 상자 | — | 문구로만(고침 RP-7) | `RP` 읽기 전용 토큰이면 생성 버튼 비활성 + 안내, 다운로드는 된다 |
| 56 | [바뀐 항목] 구역 제목 (`pages/reports/index.tsx` SnapshotDiff · `page.G8.diff` "이전 기준일 대비 바뀐 항목") | Reports · "이전 기준일 대비 바뀐 항목" h2 "이전 기준일보다 무엇이 바뀌었나요?" | — | 있음 | `RP` 보고서가 없으면 무엇이 들어가는지·어떻게 만드는지·진행이 어디 보이는지 안내<br>`RP11` 바뀐 항목: 비교 쌍 알약 · 요약 칸 4개(행 세기) · 단지 이름 = 상세 링크 · 해시 값은 접어 두고 풀이 |
| 57 | [바뀐 항목] 비교 안 골랐을 때 안내 (`page.G8.diffHint`) | Reports · "비교를 안 골랐거나 바뀐 게 없으면" "비교할 기준일을 고르면 바뀐 항목을 보여 줘요" | — | 있음 | `RP` 보고서가 없으면 무엇이 들어가는지·어떻게 만드는지·진행이 어디 보이는지 안내 |
| 58 | [바뀐 항목] 바뀐 것 없음 (`page.G8.noDiff` "바뀐 항목 없음") | Reports · 같은 곳 "바뀐 항목 없음" | — | 있음 | `R3D`/`RP` QueryState empty → '바뀐 항목 없음' (`RP` 생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress) |
| 59 | [바뀐 항목] 불러오는 중·오류 (QueryState) | Reports · 공통 상태 "목록·비교 표를 불러오는 중" · "불러오지 못했어요" | — | 있음 | `RP11` 바뀐 항목: 비교 쌍 알약 · 요약 칸 4개(행 세기) · 단지 이름 = 상세 링크 · 해시 값은 접어 두고 풀이 |
| 60 | [바뀐 항목] 열 단지 (`page.G8.diffCol.complex`) | Reports · 표 "단지" (상세 링크) | — | 있음 | `RP11` 바뀐 항목: 비교 쌍 알약 · 요약 칸 4개(행 세기) · 단지 이름 = 상세 링크 · 해시 값은 접어 두고 풀이 |
| 61 | [바뀐 항목] 열 대상 (`page.G8.diffCol.entity` · changeEntityText) | Reports · 표 "무엇" + "'무엇'에는 단지·주택형·납부 조건·… 중 하나가 와요" | 대상 → 무엇 | 있음 | `RP` 생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress<br>`RP11` 바뀐 항목: 비교 쌍 알약 · 요약 칸 4개(행 세기) · 단지 이름 = 상세 링크 · 해시 값은 접어 두고 풀이 |
| 62 | [바뀐 항목] 열 필드 — 사람이 읽는 이름 field_label, title = 원래 field (`page.G8.diffCol.field` · changeFieldText) | Reports · 표 "항목" "공식 홈페이지 팝업" title=official_popup_hash + "마우스를 올리면 원래 이름이 보여요" | 필드 → 항목 | 있음 | `RP` 생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress |
| 63 | [바뀐 항목] 열 변경 "이전 → 이후" (`page.G8.diffCol.change` · `page.common.arrow`) | Reports · 표 "바뀐 내용 (이전 → 지금)" + 예시 "[이전 값] → [새 값]" | 변경 → 바뀐 내용 | 있음 | `RP` 생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress |
| 64 | [바뀐 항목] 해시·JSON 값은 요약 + 접기 details/summary | Reports · 표 "공식 홈페이지 팝업이 바뀌었어요" + details "내부 지문(해시) … 90b9b798… → ed830f2b…" | — | 있음 | `RP11` 바뀐 항목: 비교 쌍 알약 · 요약 칸 4개(행 세기) · 단지 이름 = 상세 링크 · 해시 값은 접어 두고 풀이 |
| 65 | [바뀐 항목] 첫 적재(first_load)는 화살표 없이 한 문장 (`pages/_shared/index.tsx` changeValueText · `page.common.changeField.first_load`) | Reports · 바뀐 항목 예시 "[지역 이름] · 지역 · 첫 적재 · 첫 적재: 단지 [n]개, 값 [n]건(…)" 화살표 없음 | — | 있음(고침 RP-5) | `RP11` 첫 적재(first_load) 줄은 화살표 없이 서버 문장 한 줄(RP-5) |
| 66 | [바뀐 항목] 열 중요도 배지 (`page.G8.diffCol.severity` · `page.common.severity.*` 정보·알림·중요) | Reports · 표 "중요도" "중요" + "중요도는 정보 · 알림 · 중요" | — | 있음 | `RP11` 바뀐 항목: 비교 쌍 알약 · 요약 칸 4개(행 세기) · 단지 이름 = 상세 링크 · 해시 값은 접어 두고 풀이 |
| 67 | [바뀐 항목] 열 감지 (`page.G8.diffCol.detected` · formatDate) | Reports · 표 "알아챈 때" "10.14 22:42" | 감지 → 알아챈 때 | 있음 | `RP11` 바뀐 항목: 비교 쌍 알약 · 요약 칸 4개(행 세기) · 단지 이름 = 상세 링크 · 해시 값은 접어 두고 풀이 |
| 68 | [API] GET /regions/{id}/snapshots — 기준·비교 후보 (`hooks/useSnapshot`) | Reports · 1·2 select | — | 있음 | `R3D` 비교 선택에 리비전 표기, 생성 중 리비전은 빠진다; 생성 중 기준이면 생성 막음<br>`R3E` 비교 선택은 발행 리비전만(ready·building 제외) |
| 69 | [API] GET /scenarios (useScenarios) | Reports · 3 select | — | 있음 | `R3F2` 내장 시나리오는 대상 리비전 검사 없이 scenario_id 로 보낸다 |
| 70 | [API] POST /reports (useCreateReport) | Reports · [보고서 만들기] | — | 있음 | `RP` 생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress<br>`FL1` G8 보고서 PDF: 생성 → worker → 목록 완료 → 다운로드(%PDF, 페이지 > 0) |
| 71 | [API] GET /jobs/{id} 폴링 (JobProgress) | Reports · 진행 예시 | — | 있음 | `RP` 생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress<br>`R3F` GET /jobs/{id} 503 한 번 → 다시 조회해 running → done 까지 따라간다 |
| 72 | [API] GET /reports (useReports) | Reports · 만든 보고서 | — | 있음 | `RP` 보고서가 없으면 무엇이 들어가는지·어떻게 만드는지·진행이 어디 보이는지 안내<br>`RP11` 만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼 |
| 73 | [API] GET /reports/{id} 파일(Bearer) (useDownload) | Reports · [파일 받기] | — | 있음 | `RP` 보고서 목록: 완료된 것만 다운로드 버튼 → GET /reports/{id}(Bearer) → 파일 이름으로 저장<br>`DL` 저장한 토큰을 Authorization 으로 싣고, Content-Disposition 이름으로 저장한다 |
| 74 | [API] GET /snapshots/{sid}/changes?compare_snapshot= (비교 고를 때만) (useChanges) | Reports · 바뀐 항목 | — | 있음 | `RP` 생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress |
| 75 | [공유 링크 받기] 화면 제목 (`pages/share/index.tsx` SharePage · `page.share.title` "공유 링크") | Reports · "다른 화면 · 공유 링크 받는 곳" h3 "공유 링크" | — | 있음 | `SHR11` 주소가 잘렸을 때: 앱 이름 · 제목 · 경고 한 줄 · 홈으로 버튼 |
| 76 | [공유 링크 받기] #<토큰> 읽기, 비었거나 인코딩 깨지면 토큰 없음 (`pages/share/index.tsx` shareTokenFromHash) | Reports · "다른 화면 · 공유 링크 받는 곳" 2 "주소가 잘렸을 때" | — | 있음 | `SHR` shareTokenFromHash: 잘못된 퍼센트 인코딩(URIError)은 throw 하지 않고 null<br>`SHR` 잘못된 인코딩의 /share#… → 토큰 없음 안내, 저장하지 않는다<br>`SHR` 토큰 없이 /share → 오류 안내, 저장하지 않는다 |
| 77 | [공유 링크 받기] 적용 중 role=status (`page.share.applying`) | Reports · "다른 화면 · 공유 링크 받는 곳" 1 "보기 전용 공유 링크를 적용하는 중이에요…" | 읽기 전용 → 보기 전용 | 있음 | `SHR` #<토큰> → 읽기 전용 토큰으로 저장 · 주소의 # 제거 · / 로 이동 |
| 78 | [공유 링크 받기] 쓰기 토큰 없으면 묻지 않고 읽기 전용으로 저장(localStorage) 후 홈 (setAuth 'read') | Reports · 공유 링크 받는 곳 "동작 메모" 상자 | — | 문구로만(고침 RP-6) | `SHR` #<토큰> → 읽기 전용 토큰으로 저장 · 주소의 # 제거 · / 로 이동<br>`SHR` 저장된 토큰이 읽기 전용이면 확인 없이 바로 적용(지금처럼 localStorage) |
| 79 | [공유 링크 받기] 주소창에서 # 지우기(history.replaceState) 후 / 로 이동 (`pages/share/index.tsx` stripHash) | Reports · 공유 링크 받는 곳 "동작 메모" 상자 | — | 문구로만(고침 RP-6) | `SHR` #<토큰> → 읽기 전용 토큰으로 저장 · 주소의 # 제거 · / 로 이동<br>`E2P` G7 공유 링크 발급 → /share#토큰 으로 들어오면 읽기 전용 |
| 80 | [공유 링크 받기] 토큰 없음 role=alert (`page.share.missing`) | Reports · "다른 화면 · 공유 링크 받는 곳" 2 "공유 링크에 열쇠가 없어요. 받은 주소 전체(# 뒤까지)를 그대로 여세요." | 토큰 → 열쇠 | 있음 | `SHR` 토큰 없이 /share → 오류 안내, 저장하지 않는다<br>`SHR11` 주소가 잘렸을 때: 앱 이름 · 제목 · 경고 한 줄 · 홈으로 버튼 |
| 81 | [공유 링크 받기] 홈으로 링크 (`page.share.home`) | Reports · "다른 화면 · 공유 링크 받는 곳" 2 [홈으로] | — | 있음 | `SHR11` 주소가 잘렸을 때: 앱 이름 · 제목 · 경고 한 줄 · 홈으로 버튼 |
| 82 | [공유 링크 받기] 쓰기 토큰 덮어쓰기 확인 다이얼로그 role=alertdialog aria-modal (`page.share.confirmTitle` · `page.share.confirmBody`) | Reports · "다른 화면 · 공유 링크 받는 곳" 3 role=alertdialog "이 브라우저에 쓰기 열쇠가 저장돼 있어요" + 설명 | — | 있음 | `SHR` 저장된 쓰기 토큰이 있으면 덮어쓰지 않고 확인 다이얼로그(기본 = 이 탭에서만) |
| 83 | [공유 링크 받기] 버튼 이 탭에서만 — sessionStorage (`page.share.tabOnly`) | Reports · "다른 화면 · 공유 링크 받는 곳" 3 [이 탭에서만 보기 전용으로 보기] | — | 있음 | `SHR` "이 탭에서만 읽기 전용으로 보기" → sessionStorage 에만, 저장된 쓰기 토큰은 그대로 |
| 84 | [공유 링크 받기] 버튼 저장된 토큰 바꾸기 — localStorage (`page.share.replace`) | Reports · "다른 화면 · 공유 링크 받는 곳" 3 [저장된 열쇠를 공유 열쇠로 바꾸기] | 토큰 → 열쇠 | 있음 | `SHR` "저장된 토큰을 공유 토큰으로 바꾸기" → localStorage 를 읽기 전용 공유 토큰으로 |
| 85 | [공유 링크 받기] 버튼 취소 → 적용 없이 홈 (`page.share.cancel`) | Reports · "다른 화면 · 공유 링크 받는 곳" 3 [취소] | — | 있음 | `SHR` "취소" → 아무것도 적용하지 않고 홈으로 |
| 86 | [키보드] 다이얼로그 기본 포커스 = 이 탭에서만 | Reports · 공유 링크 받는 곳 "동작 메모" 상자 | — | 문구로만(고침 RP-6) | `SHR` 저장된 쓰기 토큰이 있으면 덮어쓰지 않고 확인 다이얼로그(기본 = 이 탭에서만) |
| 87 | [키보드] 다이얼로그 Esc = 취소 | Reports · 공유 링크 받는 곳 "동작 메모" 상자 | — | 문구로만(고침 RP-6) | `SHR11` 확인 창이 떠 있는 동안 서버 자료를 부르지 않고(#90), Esc = 취소 — 아무것도 바꾸지 않고 홈으로(#87) |
| 88 | [공유 링크 받기] 권한 모르는 저장 토큰·빌드 환경 토큰도 확인 대상 (`api/auth` hasStoredWriteToken) | Reports · 공유 링크 받는 곳 "동작 메모" 상자 | — | 문구로만(고침 RP-6) | `SHR` 권한을 모르는 저장 토큰(role 없음)도 확인한다<br>`AU` hasStoredWriteToken: 저장 토큰이 write·권한 모름이면 true, read·없음이면 false |
| 89 | [공유 링크 받기] 처음 열 때 한 번만 판단(적용 뒤 다이얼로그 다시 안 뜸) | Reports · 공유 링크 받는 곳 "동작 메모" 상자 | — | 문구로만(고침 RP-6) | `SHR` "이 탭에서만 읽기 전용으로 보기" → sessionStorage 에만, 저장된 쓰기 토큰은 그대로 (적용 뒤 홈으로 — 다시 묻지 않음) |
| 90 | [API] 공유 링크 받기는 토큰을 정하기 전 API를 부르지 않음(AppLayout 밖 라우트 — 401 토큰 창 안 뜸) | Reports · 공유 링크 받는 곳 "동작 메모" 상자 | — | 문구로만(고침 RP-6) | `SHR11` 확인 창이 떠 있는 동안 서버 자료를 부르지 않고(#90), Esc = 취소 — 아무것도 바꾸지 않고 홈으로(#87) |

## 요약

전체 90 · 있음 74 · 문구로만 15 · 다른 보드 1 · 빠짐 0 (2026-10-16 목업 고침 반영 — `../fixes/fixes-Reports.md`)

### 빠짐 목록

- 없음 — 모두 고침(보드에 그리거나 "구현할 때 지금 동작 그대로 유지" 상자에 적음)

## 새로 더한 것 (기존 화면에 없던 것)

| # | 목업에 새로 생긴 것 | 목업 위치 (섹션) | 비고 | 테스트 |
|---|---|---|---|---|
| N1 | 머리 요약 "인천 · 발행된 기준일 9개 · 만든 보고서 0개" | 머리 | — | `RP11` 머리: 지역 · 발행된 기준일 수 · 만든 보고서 수(목록 세기) + 질문형 h1 + 소개 |
| N2 | 소개 문단(단지 표와 판정 근거를 파일 하나로 …) | 머리 | — | `RP11` 머리: 지역 · 발행된 기준일 수 · 만든 보고서 수(목록 세기) + 질문형 h1 + 소개 |
| N3 | 구역마다 '이게 뭐예요?' 설명 상자 | 보고서 만들기 · 만들 수 없을 때 · 만든 보고서 · 바뀐 항목 · 공유 | — | `RP11` 만들기 4단계: 질문형 라벨 · 설명(?) · 선택 요약 · 만들 수 있어요(남은 모순 주장 0건) · 진행 자리표시 |
| N4 | 단계 번호 1~4 | 보고서 만들기 | — | `RP11` 만들기 4단계: 질문형 라벨 · 설명(?) · 선택 요약 · 만들 수 있어요(남은 모순 주장 0건) · 진행 자리표시 |
| N5 | 기준일·수정본 [?], 상황 [?] 설명 버튼 | 보고서 만들기 1·3 | — | `RP11` 만들기 4단계: 질문형 라벨 · 설명(?) · 선택 요약 · 만들 수 있어요(남은 모순 주장 0건) · 진행 자리표시 |
| N6 | 형식 옵션 설명(브라우저에서 바로 열어요 / 인쇄·보관할 때) | 보고서 만들기 4 | — | `RP11` 만들기 4단계: 질문형 라벨 · 설명(?) · 선택 요약 · 만들 수 있어요(남은 모순 주장 0건) · 진행 자리표시 |
| N7 | 버튼 옆 선택 요약 "2026.10.14 · 7번째 수정본 · 6번째 수정본과 비교 · 기본 상황 · HTML" | 보고서 만들기 | — | `RP11` 만들기 4단계: 질문형 라벨 · 설명(?) · 선택 요약 · 만들 수 있어요(남은 모순 주장 0건) · 진행 자리표시 |
| N8 | 만들 수 있음 상태 "만들 수 있어요 · 남은 모순 주장 0건" | 보고서 만들기 | — | `RP11` 만들기 4단계: 질문형 라벨 · 설명(?) · 선택 요약 · 만들 수 있어요(남은 모순 주장 0건) · 진행 자리표시 |
| N9 | 진행 칸 자리 미리 보이기(예시 · 자리표시) | 보고서 만들기 | — | `RP11` 만들기 4단계: 질문형 라벨 · 설명(?) · 선택 요약 · 만들 수 있어요(남은 모순 주장 0건) · 진행 자리표시 |
| N10 | 모순 주장 막힘에 [데이터·운영 ⑦ 모순 주장에서 고치기 →] 링크 | 만들 수 없을 때 · 막힘 3 | — | `RP11` 모순 주장이 남으면: 막힌 이유(role=alert, 버튼이 가리킴) + 데이터·운영 화면으로 고치러 가는 링크, "만들 수 있어요" 없음 |
| N11 | 바뀐 항목 머리 "2026.10.14 · 7번째 ← 6번째 수정본" | 바뀐 항목 | — | `RP11` 바뀐 항목: 비교 쌍 알약 · 요약 칸 4개(행 세기) · 단지 이름 = 상세 링크 · 해시 값은 접어 두고 풀이 |
| N12 | 바뀐 항목 요약 칸 4개(바뀐 항목 n건·단지 n곳 / 중요 n건·알림·정보 / 무엇이 바뀌었나 / 알아챈 때) | 바뀐 항목 | "같은 날 다시 모을 때"(화면 추측) → "5건 모두 이 시각에 감지"(개수) (고침 RP-4) | `RP11` 바뀐 항목: 비교 쌍 알약 · 요약 칸 4개(행 세기) · 단지 이름 = 상세 링크 · 해시 값은 접어 두고 풀이 |
| N13 | 바뀐 항목 단지 이름 = 상세 링크 | 바뀐 항목 | — | `RP11` 바뀐 항목: 비교 쌍 알약 · 요약 칸 4개(행 세기) · 단지 이름 = 상세 링크 · 해시 값은 접어 두고 풀이 |
| N14 | 해시 값 풀이 "글자 그대로가 아니라 내용이 바뀌었는지 알아보는 표시예요" · "자료: 수집 변경 기록" | 바뀐 항목 | — | `RP11` 바뀐 항목: 비교 쌍 알약 · 요약 칸 4개(행 세기) · 단지 이름 = 상세 링크 · 해시 값은 접어 두고 풀이 |
| N15 | 공유 링크 받는 곳 설명(토큰은 # 뒤에만 있어 서버 기록에 남지 않음) | 공유 링크 받는 곳 | — | `SHR11` 쓰기 열쇠가 있을 때: 확인 창 아래 첫 선택·Esc 안내 |
| N16 | 화면 바닥 고지 + 라벨 범례(보고서 안 숫자에도 같은 표시) | 바닥 | — | `RP11` 바닥: 보고서는 자격을 판정하지 않는다는 고지 + 라벨 범례 |

## 참고

- 공유 링크 받기(`/share#토큰`)는 별도 보드가 없고 Reports 보드의 "다른 화면 · 공유 링크 받는 곳" 섹션에 있다.
- `pages/share/share.test.tsx` 가 함께 검사하는 G7 공유 링크 패널(발급·목록·회수, POST/GET/DELETE /share-links)은 `pages/ops` 소속이라 이 표에 넣지 않았다 → Ops 보드(⑨). 읽기 전용 배너·다른 탭 고정 배너([새 열쇠 사용])는 레이아웃 소속 → Shell 보드 2.
- Reports 목록·막힘·오류는 '예시 · 자리표시'로 그려져 있다(지금 데이터엔 보고서 0개·막힘 없음).

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
