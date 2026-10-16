# 대응표 — 시나리오 G5 (`/scenario`, `frontend/src/pages/scenario` index.tsx·schema.ts + C07·C10) → Scenario.dc.html

입력: `frontend/src/pages/scenario/index.tsx`, `schema.ts`, `pages/_shared/index.tsx`, `charts/C07·C10`, `components/JobProgress.tsx·FactCell·Term`, `app/toast.tsx`, `i18n/ko.json` · 보드: `boards/Scenario.dc.html` ("펼친 모습 · 다른 상태" A~H 포함)

| # | 기존 기능 (현재 소스 위치 · ko 키/문구) | 새 목업 위치 (보드 · 섹션 제목) | 바뀐 이름 | 상태 | 테스트 |
|---|---|---|---|---|---|
| 1 | [틀] 화면 제목 h1 (`pages/scenario/index.tsx` PageShell · `page.G5.title` "시나리오(내 조건)") | Scenario · h1 "내 조건으로 다시 보기" + 소개 문단 | 시나리오(내 조건) → 내 조건으로 다시 보기 | 있음 | scenario.test › 머리: h1 · 소개 · 4단계 진행 표시 · routes.test › G5 |
| 2 | [상태] 시나리오 목록 불러오는 중 (`pages/scenario/index.tsx` ScenarioPage · `app.loading`) | Scenario · E "조건 목록을 불러오는 중" role=status | — | 있음 | scenario.test › 조건 목록을 불러오는 중 → 뼈대 |
| 3 | [상태] 판정기 질문 남김 배너 role=alert + 질문 텍스트 (`pages/scenario/index.tsx` ScenarioBody · `page.G5.escaped` "판정기가 질문을 남겼습니다") | Scenario · A "맨 위에 뜨는 띠" "판정기가 질문을 남겼어요 / [판정기 질문 문장]" | — | 있음 | scenario.test › escaped 봉투 → 맨 위 띠 + 질문 텍스트 |
| 4 | [틀] 현재 시나리오 = URL ?scenario= → 없으면 base → 첫째 (`pages/scenario/index.tsx` ScenarioPage current) | Scenario · 1 카드 "지금 보는 조건" 표시 | — | 있음 | scenario.test › 출발 조건: 기본 제공 카드 5개 · 지금 보는 조건 = ?scenario= → 없으면 기본 |
| 5 | [출발 조건] 출발 시나리오 select, 바꾸면 전역 ?scenario= 변경 (`pages/scenario/index.tsx` BaseScenarioPicker · `page.G5.base` "출발 시나리오") | Scenario · 1 "어떤 상황에서 시작할까요?" select "출발 조건 (저장한 조건 포함)" + 카드 라디오 5개 | 출발 시나리오 → 출발 조건 | 있음 | scenario.test › 출발 조건 select … 바꾸면 ?scenario= · 출발 조건 카드(누르면 ?scenario=) |
| 6 | [출발 조건] select 옵션 = 시나리오 이름(내장 + 사용자) | Scenario · 옵션 기본·A~D·[내가 저장한 조건 이름] | — | 있음 | scenario.test › 출발 조건 select: 옵션 = 시나리오 이름 전부 |
| 7 | [출발 조건] 내장 시나리오 안내 (`page.G5.readOnlyBuiltin` "내장 시나리오는 이름을 바꿔 새로 저장합니다") | Scenario · 1 아래 "기본 제공 조건은 바꿀 수 없어요. … 새 이름으로 저장하면 '내가 저장한 조건'으로 남아요." | 내장 → 기본 제공 | 있음 | scenario.test › 출발 조건(readOnlyBuiltin 안내) |
| 8 | [폼] 폼 제목·이름 (form aria-label · `page.G5.form` "내 조건") | Scenario · 2 h2 "내 조건을 적어 주세요" · form aria-label "내 조건" (novalidate) | — | 있음 | scenario.test › 폼 … · acceptance › G5 조건 폼 |
| 9 | [폼] 이름 칸 (`page.G5.field.name` "시나리오 이름") | Scenario · 2 "이 조건의 이름 *" | 시나리오 이름 → 이 조건의 이름 | 있음 | scenario.test › 폼(이 조건의 이름) |
| 10 | [폼] 이름 필수 오류 (`pages/scenario/schema.ts` · `page.G5.error.required` "필수 항목입니다") | Scenario · 2 이름 칸 아래 "이름을 적어 주세요 (꼭 필요한 칸이에요)" | 필수 항목입니다 → 이름을 적어 주세요 | 있음 | scenario.test › zod 검증(이름 필수) · 잘못된 입력은 필드 오류 |
| 11 | [폼] 내장 시나리오면 이름 비워 두고 새로 저장 (`pages/scenario/index.tsx` fromScenario) | Scenario · 2 "기본 제공 조건 'A 가점 높음(실거주)'는 새 이름으로 저장돼요." | — | 있음 | scenario.test › 폼(기본 제공이면 이름 비움 + 새 이름 안내) |
| 12 | [폼] 거주지 (`page.G5.field.residence`) | Scenario · 2 "사는 곳 (거주지)" | — | 있음 | scenario.test › 폼(칸 이름 = 쉬운 말 (공식 이름)) |
| 13 | [폼] 무주택 체크 (`page.G5.field.homeless`) | Scenario · 2 "집이 없어요 (무주택)" | — | 있음 | scenario.test › 폼(집이 없어요 체크) |
| 14 | [폼] 세대원 수 (`page.G5.field.household_size`) | Scenario · 2 "함께 사는 가족 수 (세대원 수) 명" | — | 있음 | scenario.test › 폼(칸 이름·단위) |
| 15 | [폼] 세대원 수 정수·1~20 오류 (`pages/scenario/schema.ts` optionalNumber int · `page.G5.error.number`) | Scenario · B "숫자(정수)를 적어 주세요" + 범위 줄 "가족 수 1~20명" | 숫자를 입력하세요 → 숫자(정수)를 적어 주세요 | 있음 | scenario.test › zod 칸별 범위(가족 수 정수) |
| 16 | [폼] 청약통장 체크 (`page.G5.field.has_account`) | Scenario · 2 "청약통장이 있어요" | — | 있음 | scenario.test › 폼(칸 이름) |
| 17 | [폼] 청약 가점 (`page.G5.field.score`) | Scenario · 2 "청약 가점 [?] 점 / 84점" | — | 있음 | scenario.test › 폼(청약 가점 용어 '?' · 단위 점 / 84점) |
| 18 | [폼] 가점 0~84 오류 (`page.G5.error.max` "{max} 이하여야 합니다") | Scenario · B "84 이하여야 해요" | — | 있음 | scenario.test › zod 검증(가점 범위) · 잘못된 입력은 필드 오류 |
| 19 | [폼] 자기자본(억) (`page.G5.field.equity_won`) | Scenario · 2 "지금 가진 내 돈 (자기자본) 억원" | — | 있음 | scenario.test › 폼(지금 가진 내 돈 = 3, 단위 억원) |
| 20 | [폼] 자기자본 0~1000 오류 (`page.G5.error.min` "{min} 이상이어야 합니다") | Scenario · B "0 이상이어야 해요" | — | 있음 | scenario.test › zod 칸별 범위(내 돈 0 이상) |
| 21 | [폼] 총 대출한도(억) (`page.G5.field.loan_limit_won`) | Scenario · 2 "받을 수 있는 대출 모두 (총 대출한도) 억원" | — | 있음 | scenario.test › 폼(단위 억원) |
| 22 | [폼] 대출한도 0~1000 오류 | Scenario · B 오류 칸 "받을 수 있는 대출 모두 1200 → 1000 이하여야 해요" | — | 있음(고침 SC-9) | scenario.test › zod 칸별 범위(대출 1,000 이하) |
| 23 | [폼] 목적 select 4개 (`page.G5.field.purpose` · `page.G5.purpose.*` 선택 안 함·실거주·시세차익·병행) | Scenario · 2 "왜 사려고 하나요 (목적)" 선택 안 함 · 직접 살 집 (실거주) · 되팔아 차익 (시세차익) · 둘 다 (병행) | 옵션에 쉬운 말 덧붙임 | 있음 | scenario.test › 폼(목적 옵션 4개) |
| 24 | [폼] 보유 기간(년) (`page.G5.field.holding_years`) | Scenario · 2 "얼마나 가지고 있을 건가요 (보유 기간) 년" | — | 있음 | scenario.test › 폼(칸 이름) |
| 25 | [폼] 보유 기간 정수 0~50 오류 | Scenario · B 오류 칸 "얼마나 가지고 있을 건가요 60 → 50 이하여야 해요" | — | 있음(고침 SC-9) | scenario.test › zod 칸별 범위(보유 50 이하) |
| 26 | [폼] 희망 평형(㎡) (`page.G5.field.preferred_area_m2`) | Scenario · 2 "원하는 집 크기 (희망 평형) ㎡" | — | 있음 | scenario.test › 폼(칸 이름·단위) |
| 27 | [폼] 희망 평형 10~300 오류 | Scenario · B 오류 칸 "원하는 집 크기 5 → 10 이상이어야 해요" | — | 있음(고침 SC-9) | scenario.test › zod 칸별 범위(크기 10 이상) |
| 28 | [폼] 입주 희망 시기 YYYY-MM (`page.G5.field.move_in_by`) | Scenario · 2 "들어가 살고 싶은 때 (입주 희망 시기)" 자리표시 "예: 2029-06 (연-월)" | — | 있음 | scenario.test › 폼(칸 이름·자리표시) |
| 29 | [폼] 입주 시기 형식 오류 (`page.G5.error.ym` "YYYY-MM 형식으로 입력하세요") | Scenario · B "2029-06처럼 연-월로 적어 주세요" | — | 있음 | scenario.test › zod 검증(입주 시기 형식) |
| 30 | [폼] 숫자 칸 inputMode=decimal | Scenario · 숫자 칸 inputmode="decimal" 6개 | — | 있음 | scenario.test › 폼(inputMode=decimal 6개) |
| 31 | [폼] 오류 칸 aria-invalid · aria-describedby 연결 | Scenario · B 오류 칸 aria-invalid, 이름 칸 aria-describedby | — | 있음 | scenario.test › 잘못된 입력(aria-invalid·describedby) |
| 32 | [폼] 잘못된 입력이면 POST 하지 않고 칸별 오류 (`pages/scenario/schema.ts` toScenarioCreate) | Scenario · B "입력이 맞지 않을 때 (저장을 누른 뒤)" | — | 있음 | scenario.test › 잘못된 입력은 … POST 하지 않는다 |
| 33 | [비중] 가중치 묶음 fieldset·legend (`pages/scenario/index.tsx` WeightPreview · `page.G5.weights` "가중치 미리보기") | Scenario · 2 "어떤 기준을 얼마나 중요하게 볼까요? (비중 미리보기)" | 가중치 미리보기 → 비중 미리보기 | 있음 | scenario.test › 비중(fieldset 이름 = 비중 미리보기) · e2e pages › G5 시나리오 |
| 34 | [비중] 안내 (`page.G5.weightsHint` "하나를 움직이면 나머지가 비례해서 맞춰져 합이 항상 1입니다") | Scenario · 2 "… 하나를 움직이면 나머지가 원래 비율대로 맞춰져서 합이 늘 100%예요." | 합 1 → 합 100% | 있음 | scenario.test › 비중(안내 문장) |
| 35 | [비중] 슬라이더 +10% 상승 가능성 (range 0~1 step 0.01 · `chart.C06.component.p10`) | Scenario · 2 "입주 뒤 값이 오를 가능성" + 설명 "목표 시점(입주 + 1년, 이 조건 설정)… 당첨 확률 아님 · 보장 아님" | — | 있음(고침 SC-1) | scenario.test › 비중(슬라이더 이름 · 오를 가능성 목표 시점 + 당첨 확률 아님 · 보장 아님) |
| 36 | [비중] 슬라이더 판정기 순위 (`chart.C06.component.rerank`) | Scenario · 2 "비슷한 단지들 사이 순위" | — | 있음 | scenario.test › 비중(슬라이더 6개 이름) |
| 37 | [비중] 슬라이더 가격 갭 (`chart.C06.component.gap`) | Scenario · 2 "주변 시세와 가격 차이" | — | 있음 | scenario.test › 비중(슬라이더 6개 이름) |
| 38 | [비중] 슬라이더 벤치마크 (`chart.C06.component.benchmark`) | Scenario · 2 "근처 새 아파트가 입주 뒤 오른 정도" | — | 있음 | scenario.test › 비중(슬라이더 6개 이름) |
| 39 | [비중] 슬라이더 공급 (`chart.C06.component.supply`) | Scenario · 2 "같은 시기 입주 물량" | — | 있음 | scenario.test › 비중(슬라이더 6개 이름) |
| 40 | [비중] 6번째 슬라이더 유동성 또는 입주 시기 (시나리오 weights 키 · `chart.C06.component.liquidity`/`move_in`) | Scenario · 2 "입주 시기" (A 조건 기준, '이 조건의 6번째 기준') | — | 있음 | scenario.test › 비중(6번째 = 입주 시기, A 조건) |
| 41 | [비중] 슬라이더 값 표시 0.35 + aria-valuetext (MetaValue) | Scenario · 2 "35% (0.35)", aria-valuetext=% | 0.35 → 35% (0.35) | 있음 | scenario.test › 비중(값 "35% (0.35)" · aria-valuetext) |
| 42 | [비중] 한 칸 바꾸면 나머지 비례 재분배 (`pages/scenario/schema.ts` rebalance) | Scenario · 목업 스크립트가 같은 rebalance로 움직임 | — | 있음 | scenario.test › 가중치 합 1 제약 · 슬라이더를 움직여도 합은 1.00 |
| 43 | [비중] 합 표시, 1이 아니면 빨강 (`page.G5.weightsSum` "합 {sum}") | Scenario · 2 "합계 100% (1.00)" · B "합계 95% (0.95)" | 합 → 합계 | 있음 | scenario.test › 비중(합계 100% (1.00)) |
| 44 | [비중] 합 오류 role=alert (`page.G5.error.weightsSum` "가중치 합이 1이어야 합니다(지금 {sum})") | Scenario · B "비중 합이 100%여야 해요 (지금 95%)" | — | 있음 | scenario.test › zod 가중치 합 ≠ 1 이면 거부(지금 합 %) |
| 45 | [저장] 저장 버튼 submit (`page.G5.save` "저장") | Scenario · 2 [이 조건 저장] | 저장 → 이 조건 저장 | 있음 | scenario.test › 슬라이더를 움직여도 합은 1.00, 저장 → POST /scenarios |
| 46 | [저장] 저장 성공 토스트 + 저장한 시나리오로 전환 (`app/toast.tsx` · `page.G5.saved` "시나리오를 저장했습니다") | Scenario · C "조건을 저장했어요 [닫기]" + 버튼 옆 "저장하면 이 조건이 '지금 보는 조건'이 돼요" | — | 있음 | scenario.test › … 저장 → 토스트 + 저장한 조건으로 전환 |
| 47 | [저장] 저장 실패 role=alert (`page.common.loadError` "불러오지 못했습니다: {detail}") | Scenario · C "저장하지 못했어요: [오류 내용]" | 불러오지 못했습니다 → 저장하지 못했어요 | 있음 | scenario.test › 저장 실패 → role=alert |
| 48 | [저장] 읽기 전용이면 꺼짐 + title (`api/auth` useCanWrite · `auth.readOnlyHint`) | Scenario · D [이 조건 저장] title "읽기 전용 열쇠로는 저장·실행할 수 없어요" | 토큰 → 열쇠 | 있음 | scenario.test › 읽기 전용 열쇠 → 저장·다시 판정 버튼 꺼짐 + 안내 title |
| 49 | [저장] 저장 요청 중 꺼짐 (create.isPending) | Scenario · 바닥 "구현할 때 지금 동작 그대로 유지" 상자 | — | 문구로만(고침 SC-10) | scenario.test › 저장 요청을 보내는 동안 [이 조건 저장] 꺼짐(#49) |
| 50 | [재판정] 구역 제목 (`pages/scenario/index.tsx` RunPanel · `page.G5.run` "재판정 실행") | Scenario · 3 h2 "이 조건으로 다시 판정할까요?" + 설명 | 재판정 실행 → 다시 판정 | 있음 | scenario.test › 재판정 실행(구역 = 질문형 h2 · 안내) |
| 51 | [재판정] 실행 버튼 → POST /jobs {job_name: rejudge} (`page.G5.run` · `page.G5.runReason`) | Scenario · 3 [다시 판정하기] | 재판정 실행 → 다시 판정하기 | 있음 | scenario.test › 재판정 실행 → POST /jobs(rejudge) · r3d › G5 재판정 |
| 52 | [재판정] 버튼 꺼짐: 읽기 전용 + title | Scenario · D [다시 판정하기] title | — | 있음 | scenario.test › 읽기 전용 열쇠 |
| 53 | [재판정] 버튼 꺼짐: 시나리오·기준일 없음·요청 중 | Scenario · 바닥 "구현할 때 지금 동작 그대로 유지" 상자 | — | 문구로만(고침 SC-10) | scenario.test › 기준일이 없으면 [다시 판정하기] 꺼짐(#53) |
| 54 | [재판정] 캐시 히트·새 호출 수 (`page.G5.cache` "캐시 히트 {hits} · 새 호출 {misses}") | Scenario · 3 "저장된 답 다시 씀 21건 · 새로 물어볼 것 0건" 두 칸 | 캐시 히트 → 저장된 답 다시 씀 · 새 호출 → 새로 물어볼 것 | 있음 | scenario.test › 재판정 실행(캐시 두 칸: 저장된 답 다시 씀 · 새로 물어볼 것 1건) |
| 55 | [재판정] 실행 중 안내 (`page.G5.running` "재판정 중 — 2초마다 상태를 확인합니다") | Scenario · F "다시 판정하는 중이에요 — 2초마다 상태를 확인해요." | — | 있음 | scenario.test › 재판정 실행(다시 판정하는 중) |
| 56 | [작업 진행] 제목·잡 이름·상태 (`components/JobProgress.tsx` JobProgressView · `job.title` · `job.status.*` 대기·실행 중·완료·실패) | Scenario · F "작업 진행 다시 판정 실행 중" + "상태 이름: 대기 · 실행 중 · 완료 · 실패" | — | 있음 | scenario.test › 재판정 실행(JobProgress 2초 폴링) · shell-components.test › 작업 이름·단계는 쉬운 말 |
| 57 | [작업 진행] 진행 수 done/total + progress 막대(모르면 미정 막대) (`job.progress`) | Scenario · F "[완료 수]/[전체 수]" + "진행 수를 모르면 막대가 좌우로 움직여요" | — | 있음 | r3f › JobProgressView: 받아 둔 잡이 있으면 … · shell-components.test(진행 막대) |
| 58 | [작업 진행] 단계 (`job.step` "단계 {step}") | Scenario · F "단계 [단계 이름]" | — | 있음 | shell-components.test › 작업 이름·단계는 쉬운 말(모르는 값은 원문) |
| 59 | [작업 진행] 잡 오류 (`job.error` "오류: {detail}") | Scenario · F "오류: [오류 내용]" | — | 있음 | shell-components.test › 작업 없음 · 오류 문구 |
| 60 | [작업 진행] 상태 다시 확인 중 (`job.retrying`) | Scenario · F "상태를 받지 못해 다시 확인하는 중: [내용]" | — | 있음 | r3f › JobProgressView: 받아 둔 잡이 있으면 일시 오류 동안 마지막 상태 + 다시 확인 중 줄 |
| 61 | [작업 진행] 재큐잉·불완전 수집 안내 (`components/JobProgress.tsx` JobRequeueNote · degradedFailureText · `job.requeued*` · `job.degradedFailed`) | Shell · 6 "작업 진행 · 알림" (Scenario F에 '공통 부품 보드와 같아요') | — | 다른 보드(Shell) | r4fe12 › JobProgressView(G0 bootstrap): '불완전한 수집 — 다시 수집' + '적재 중' |
| 62 | [재판정] 완료 뒤 결과 리비전 표시 (`page.G5.afterRevision` "이후 값: {snapshot}") | Scenario · 3 "바뀐 값이 저장된 곳: 기준일 2026-10-14 ([n]번째 수정본)" | 이후 값 → 바뀐 값이 저장된 곳 · 리비전 → 수정본 | 있음 | r3d › G5 재판정 → 이후 값이 어느 리비전인지(snapshotText) |
| 63 | [재판정] 리비전 목록 갱신 중 (`page.G5.afterPending` "새 리비전(목록 갱신 중)") | Scenario · G "새 수정본(목록 새로 고치는 중)" | — | 있음 | r3d › G5 재판정(이후 리비전 표기) · r3f › 새 리비전 대시보드 500 |
| 64 | [재판정] 이 리비전으로 화면 보기 버튼(다른 리비전일 때만) (`page.G5.openRevision`) | Scenario · 3 [이 수정본으로 화면 보기] | 리비전 → 수정본 | 있음 | r3d › G5 재판정(이 수정본으로 화면 보기 → 헤더 기준일) |
| 65 | [재판정] 실행 뒤 값 받는 중 (`page.G5.afterLoading`) | Scenario · G "실행 뒤 값을 받는 중…" | — | 있음 | r3f › 새 리비전 대시보드 500 → 받는 중 문구 대신 오류, 다시 시도하면 표 |
| 66 | [재판정] 실행 뒤 값 오류 + 다시 시도 (`page.G5.afterError` · `app.retry`) | Scenario · G "실행 뒤 값을 받지 못했어요: [오류 내용] [다시 시도]" | — | 있음 | r3f › 새 리비전 대시보드 500 → 오류 + 다시 시도 |
| 67 | [재판정] 실행 뒤 특수 오류 문구 (`lib/errorText.ts` specialErrorText · `page.common.materializePendingStill` · `page.common.storedViewMismatch`) | Shell · 7 "이 기준일 결과를 만드는 중이에요 … 보던 기준일과 저장된 화면이 다를 때도 안내가 떠요" | — | 다른 보드(Shell) | r3f2 › stored_view_mismatch(500) → 서버 오류 문구 · r3f2 › F15 503 준비 중 → 자동 재시도 |
| 68 | [이전 대비] 표 제목 (`pages/scenario/index.tsx` DiffTable · `page.G5.diff` "이전 결과 대비") | Scenario · 3 h3 "이전 결과와 비교하면 순위가 바뀌었나요?" + 설명 | — | 있음 | scenario.test › 재판정 실행 → 이전 대비 표(h3) |
| 69 | [이전 대비] 변동 없음 (`page.G5.noDiff` "순위 변동 없음") | Scenario · G "순위 변동 없음 (이전 결과 표 위에 떠요)" | — | 있음 | r3d › G5 재판정(순위 변동 없음 문구 조건) |
| 70 | [이전 대비] 열 단지 (`page.G5.diffCol.name`) | Scenario · 3 "단지" | — | 있음 | scenario.test › 재판정 실행 → 이전 대비 표 · r3c › G5 이전 대비 표 |
| 71 | [이전 대비] 열 이전 순위 (`page.G5.diffCol.rankBefore`) | Scenario · 3 "이전 순위" (+동률) | — | 있음 | r3c › G5 이전 대비 표 · e2e api writes7-r3d |
| 72 | [이전 대비] 열 새 순위 (`page.G5.diffCol.rankAfter`) | Scenario · 3 "새 순위" | — | 있음 | r3c › G5 이전 대비 표 · e2e api writes7-r3d |
| 73 | [이전 대비] 열 이전 종합 (`page.G5.diffCol.totalBefore`) | Scenario · 3 "이전 종합 점수" | 이전 종합 → 이전 종합 점수 | 있음 | r3c › G5 이전 대비 표 |
| 74 | [이전 대비] 열 새 종합 (`page.G5.diffCol.totalAfter`) | Scenario · 3 "새 종합 점수" | 새 종합 → 새 종합 점수 | 있음 | r3c › G5 이전 대비 표 |
| 75 | [이전 대비] 열 판정기 순위 변화 (`page.G5.diffCol.deltaRerank`) | Scenario · 3 "판정기 줄 세우기 변화 (새 실행, 이전 실행 대비)" | 판정기 순위 변화 → 판정기 줄 세우기 변화 | 있음 | r3c › G5 이전 대비 표: 새 run 의 delta_rerank 열 |
| 76 | [이전 대비] 순위 없을 때 "없음" (`page.common.none`) | Scenario · 3 이전 대비 표 예시 줄 "이전 순위·새 순위: 없음" | — | 있음(고침 SC-2) | r3c › G5 이전 대비 표(순위 없음 → 없음) |
| 77 | [이전 대비] 순위 변화 없음 사유 (`page.common.deltaRerankNone`) | Scenario · G "판정기 줄 세우기 변화가 없을 때: 확인 불가(이전 실행 없음)" | — | 있음 | r3c › G5 이전 대비 표(확인 불가(이전 실행 없음)) |
| 78 | [이전 대비] 이전·새 숫자의 출처 = 그 값이 나온 리비전 (FactCell provSnapshotId) | Scenario · 바닥 "구현할 때 지금 동작 그대로 유지" 상자 | — | 문구로만(고침 SC-10) | r3d › G5 재판정(이전·새 숫자 출처 = 그 리비전, provSnapshotId) |
| 79 | [요건 사전 계산] 구역 제목 (`pages/scenario/index.tsx` RequirementPreview · `page.G5.requirements` "요건 사전 계산(판정기 호출 없음)") | Scenario · 4 h2 "내 조건이면 단지마다 요건을 채우나요?" + "(요건 사전 계산)" | — | 있음 | scenario.test › 요건 사전 계산(구역 = 질문형 h2) |
| 80 | [요건 사전 계산] 불러오는 중 (`app.loading`) | Scenario · H 꼬리 "불러오는 중…" | — | 있음 | shell-components.test › Skeleton: 뼈대 줄 + "불러오는 중…" |
| 81 | [요건 사전 계산] 오류 (queryErrorText) | Scenario · H 꼬리 "요건 표를 못 불러왔을 때: 불러오지 못했어요: [오류 내용]" | — | 있음 | scenario.test › 요건 표를 못 불러오면 오류 문구 |
| 82 | [요건 사전 계산] 열 단지 (`page.G5.req.complex`) | Scenario · 4 "단지 (79곳 중 8곳)" | — | 있음 | scenario.test › 요건 사전 계산(단지 열 + n곳 중 n곳) |
| 83 | [요건 사전 계산] 열 접근 (`page.G5.req.access`) | Scenario · 4 "지금 신청할 수 있나 (접근)" | — | 있음 | scenario.test › 요건 사전 계산(쉬운 열 이름 + (접근)) |
| 84 | [요건 사전 계산] 열 규제 (`page.G5.req.regulation`) | Scenario · 4 "규제와 부딪히지 않나 (규제)" | — | 있음 | scenario.test › 요건 사전 계산(열 이름) |
| 85 | [요건 사전 계산] 열 자금 (`page.G5.req.funds`) | Scenario · 4 "내 돈으로 되나 (자금)" | — | 있음 | scenario.test › 요건 사전 계산(열 이름) |
| 86 | [요건 사전 계산] 열 머리 아래 요건 문장 (requirements[c].text) | Scenario · 4 열 머리 "가점제 1순위 공급(…)으로 접근 가능" 등 | — | 있음 | scenario.test › 요건 사전 계산(열 머리 아래 요건 문장 = 서버 문장) |
| 87 | [요건 사전 계산] 칸 상태 배지 (`page.G5.reqStatus.*` 충족·미충족·미입력·확인 불가) | Scenario · 4 칸 배지 + H 꼬리 "요건 칸 상태는 4가지예요" | — | 있음 | scenario.test › 요건 사전 계산(상태 배지 15) |
| 88 | [요건 사전 계산] 칸 근거 문장 (evidence) | Scenario · 4 배지 아래 근거(서버 문장 그대로 — 고친 문구 예시 위 안내) | — | 있음(고침 SC-3) | scenario.test › 요건 사전 계산(근거 = 서버 문장 그대로) |
| 89 | [요건 사전 계산] 제외 배지 + 회색 행 (`page.G5.req.excluded` "제외") | Scenario · H "요건 표에서 빠진 단지" 회색 행 + "제외" | — | 있음 | scenario.test › 요건 표: 처음 8곳 → [나머지 n곳 더 보기] · 제외 단지 회색 + 제외 배지 |
| 90 | [요건 사전 계산] 표 아래 캐시 수 (`page.G5.cache`) | Scenario · 4 꼬리 "저장된 답 21건 다시 씀 · 새로 물어본 것 0건 (판정기 호출 없음)" | 캐시 히트 → 저장된 답 다시 씀 | 있음 | scenario.test › 요건 사전 계산(캐시 줄 18) |
| 91 | [C07 판정기 확률] 차트 제목 (`charts/C07` · `chart.C07.title` "판정기 확률") | Scenario · "판정기 결과 · A 가점 높음(실거주)" h2 "이 조건이면 판정기는 어디를 고르나요?" / h3 "판정기가 고를 확률" | 판정기 확률 → 판정기가 고를 확률 | 있음 | charts.r11 › 차트 이름(aria-label) = 제목 · e2e charts-gallery › C07 normal |
| 92 | [C07 판정기 확률] 부제 신뢰도 (`chart.C07.confidence`) | Scenario · "믿음 정도 0.89 [?]" | 신뢰도 → 믿음 정도 | 있음 | charts.contract › C07 T2 상황 B: confidence 0.48 < 0.6 → 동률 |
| 93 | [C07 판정기 확률] 라벨 배지 | Scenario · "판정기 추정" | — | 있음 | e2e charts-gallery › C07 normal(라벨 배지) |
| 94 | [C07 판정기 확률] 동률 배지 (`badge.tie`) | Scenario · H 꼬리 "판정기 차트 배지: 동률 …" | — | 있음 | ChartGallery.test › 특수 상태 배지(동률) · charts.contract › C07 minor 28 … |
| 95 | [C07 판정기 확률] 증거와 상이 배지 (`badge.mismatch`) | Scenario · H 꼬리 "근거와 달라요" | 증거와 상이 → 근거와 달라요 | 있음 | charts.contract › C07 decide prob per 후보 + escape 선택지(hasMismatch) |
| 96 | [C07 판정기 확률] 캐시 배지 (`badge.cached`) | Scenario · H 꼬리 "이전 결과 재사용" | 캐시 → 이전 결과 재사용 | 있음 | e2e charts-gallery › C07 normal(캐시 배지) |
| 97 | [C07 판정기 확률] 질문 남김 배지 (`chart.C07.escape`) | Scenario · H 꼬리 "질문 남김" | — | 있음 | e2e charts-gallery › C07 escaped |
| 98 | [C07 판정기 확률] 질문 남김이면 막대 대신 "질문 남김: {질문}" (`charts/C07` emptyReason) | Compare · F "질문을 남기면 막대 대신 '질문 남김: [판정기 질문 문장]'" | — | 다른 보드(Compare) | charts.contract › C07 escaped → 막대 대신 질문 텍스트 · e2e charts-gallery › C07 escaped |
| 99 | [C07 판정기 확률] 판정 미해결 배지 (`chart.C07.unresolved`) | Scenario · H 꼬리 "판정 미해결" | — | 있음 | charts.r11 › C07 미해결 |
| 100 | [C07 판정기 확률] 미해결이면 막대 회색 + "미해결" | Compare · F 설명 "미해결이면 막대가 회색이 되고 …" | — | 다른 보드(Compare) | charts.r11 › C07 미해결 · charts.contract › C07 minor 28: 봉투 review·blocked·error·escaped |
| 101 | [C07 판정기 확률] 가로 막대(선택 강조, 보류 선택지 회색) | Scenario · 판정기가 고를 확률 막대 | — | 있음 | charts.r11 › C07 보류 선택지 · charts.r11 › C07 범례 · charts.contract › C07 계약 .5 가상 후보 |
| 102 | [C07 판정기 확률] 막대 라벨 확률 · 선택 · 가상 후보 · 보류 | Scenario · "{%} 판정기 선택 · 가상 후보 · 판정기 보류 선택지" | 선택 → 판정기 선택 | 있음 | charts.contract › C07 minor 28: ok 봉투의 항목 동률·선택은 서버 값 그대로 · charts.r11 › C07 보류 선택지 · charts.contract › C07 계약 .5 가상 후보 |
| 103 | [C07 판정기 확률] 범주 축 후보 이름 | Scenario · 막대 왼쪽 후보 이름 | — | 있음 | charts.contract › C07 decide prob per 후보 + escape 선택지 |
| 104 | [C07 판정기 확률] 확률 축 0~1 눈금 | Scenario · 판정기 결과 막대 아래 확률 축 0% 25% 50% 75% 100% | — | 있음(고침 SC-4) | charts.r11 › C07 눈금 |
| 105 | [C07 판정기 확률] 툴팁 | Scenario · 판정기 결과 툴팁 예시 2개(이름 / 확률 / 표시) | — | 있음(고침 SC-5) | charts.contract › C07 툴팁의 서버 문자열은 HTML 이스케이프 |
| 106 | [C07 판정기 확률] 빈 상태 (`chart.C07.empty` "판정 없음") | Scenario · H 꼬리 "판정 없음 (차트가 빌 때)" | — | 있음 | ChartGallery.test › 빈 상태 카드는 차트 대신 빈 상태 문구 · charts.contract › C07 escaped → … / 판정 없음 |
| 107 | [C07 판정기 확률] 표로 보기 버튼 (`table.show`) | Scenario · 꼬리말 [표로 보기] | — | 있음 | charts.r11 › ChartFrame 표로 보기 |
| 108 | [C07 판정기 확률] 표 열 이름 (`chart.col.name`) | Compare · L "이름" | — | 다른 보드(Compare) | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C07 계약 .5 가상 후보(toTable) |
| 109 | [C07 판정기 확률] 표 열 확률 (`chart.col.prob`) | Compare · L "확률" | — | 다른 보드(Compare) | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C07 계약 .5 가상 후보(toTable) |
| 110 | [C07 판정기 확률] 표 열 표시 (`chart.col.flags`) | Compare · L "표시" | — | 다른 보드(Compare) | buildOption.test › toTable(빈 데이터) 열 정의 · charts.contract › C07 계약 .5 가상 후보(toTable) |
| 111 | [C10 민감도] 차트 제목 (`charts/C10` · `chart.C10.title` "가중치 민감도") | Scenario · "가중치 민감도 · A 가점 높음(실거주)" h2 "어떤 기준의 비중을 10%p 늘리거나 줄이면 순위가 바뀌나요?" | — | 있음 | charts.r11 › 차트 이름(aria-label) = 제목 · e2e charts-gallery › C10 normal |
| 112 | [C10 민감도] 용어 ⓘ 비중 (Term `weight`) | Scenario · 가중치 민감도 "용어: '비중' [?]" | — | 있음(고침 SC-7) | rawKeys › C10 패널: 한 문장 설명 · 비중/민감도 ⓘ … |
| 113 | [C10 민감도] 용어 ⓘ 민감도 (Term `sensitivity`) | Scenario · 같은 줄 "'민감도' [?]" | — | 있음(고침 SC-7) | rawKeys › C10 패널: 한 문장 설명 · 비중/민감도 ⓘ … |
| 114 | [C10 민감도] 순위 불안정 배지 (`badge.unstable`) | Scenario · 가중치 민감도 결과 상자 [순위가 흔들려요] (단지 이름 나열은 뺌) | 순위 불안정 → 순위가 흔들려요(+단지 이름) | 있음(고침 SC-6) | ChartGallery.test › 특수 상태 배지(순위 불안정) |
| 115 | [C10 민감도] 변동 없는 성분 배지 (`chart.C10.stable`) | Scenario · 같은 상자 [비중을 바꿔도 순위가 그대로인 기준 있음] | 있음 → 기준 이름까지 | 있음(고침 SC-6) | rawKeys › C10 패널(stable-badge) |
| 116 | [C10 민감도] 설명 문단 (`chart.C10.explain`) | Scenario · 구역 설명 + '한 줄 답' | — | 있음 | rawKeys › C10 패널(설명) |
| 117 | [C10 민감도] HTML 표 행 = 변형 12개 (`chart.C10.variantLabel`) | Scenario · 행 6개(기준) × 열 "줄이면 → 1~5위" / "늘리면 → 1~5위" | 12행 → 6행 × 2열 | 있음 | charts.r11 › C10 재설계 표 |
| 118 | [C10 민감도] 표 열 비중 바꾼 항목 (`chart.col.variant`) | Scenario · "기준 (지금 비중) · 무엇을 보나요" | — | 있음 | charts.r11 › C10 패널 |
| 119 | [C10 민감도] 표 열 1~5위(TOP 5) + 실제 순위 괄호 | Scenario · 칸 안 "1위 … 5위" + "(공동)" | 괄호 실제 순위 → (공동) | 있음 | charts.r11 › C10 패널 · charts.r11 › C10 재설계 표 |
| 120 | [C10 민감도] 표 열 순위 변동 (`chart.C10.changedCol` · `changedNo` · `changedWith`) | Scenario · 칸 아래 "순위 변동: 있음 — 새로 들어옴 … · 빠짐 …" / "순위 변동: 없음" | — | 있음 | rawKeys › C10 패널(순위 변동 없음/있음) · charts.r11 › C10 패널 · charts.r11 › C10 결과 개수 |
| 121 | [C10 민감도] 진입·이탈 단지 + 굵게 (`chart.C10.entered` · `chart.C10.exited`) | Scenario · 칸 안 "· 새로 들어옴" 표시 + 변동 문장 | 진입 → 새로 들어옴 · 이탈 → 빠짐 | 있음 | charts.r11 › C10 진입 굵게 |
| 122 | [C10 민감도] 변동 없는 행 회색 (text-grayed) | Scenario · "회색 칸 = 상위 5곳 변동 없음" (변동 칸은 주황 바탕) | — | 있음 | charts.r11 › C10 패널(변동 없는 칸 회색 data-stable) |
| 123 | [C10 민감도] 순위 선 차트 | Scenario · h3 "기준별로 비중을 바꾸면 각 단지는 몇 위가 되나요?" | — | 있음 | charts.contract › C10 작은 선: 기준 TOP 5 단지별 순위, y축 뒤집힘 |
| 124 | [C10 민감도] 선 차트 x축 변형 짧은 이름 (`chart.C10.variantShort`) | Scenario · "6가지 기준 × (줄이면 / 늘리면)" | — | 있음 | charts.r11 › C10 x축 · rawKeys › C10 민감도: x축·표 행 이름은 쉬운 말 |
| 125 | [C10 민감도] 선 차트 y축 순위(위가 1위, 최대 순위까지) | Scenario · "1위 … 6위" + "6위로 내려가면 상위 5곳에서 빠진 거예요" | — | 있음 | charts.contract › C10 작은 선(y축 뒤집힘) · charts.r11 › C10 상위 5곳 밖 띠 |
| 126 | [C10 민감도] 선 차트 범례 기준 TOP 5 단지 | Scenario · 범례 5단지 | — | 있음 | charts.r11 › C10 범례 |
| 127 | [C10 민감도] 선 차트 툴팁 | Scenario · 순위 선 차트 툴팁 예시(비중 바꾼 항목 / 단지별 순위, 없으면 확인 불가) | — | 있음(고침 SC-8) | charts.r11 › C10 툴팁 |
| 128 | [C10 민감도] 빈 상태 (`chart.C10.empty` "민감도 없음") | Scenario · H 꼬리 "민감도 없음" | — | 있음 | ChartGallery.test › 빈 상태 카드는 차트 대신 빈 상태 문구 · charts.contract › C10 변동 없는 가중치 행 = stable(민감도 없음) |
| 129 | [C10 민감도] 표로 보기 버튼 | Scenario · 꼬리말 [표로 보기] | — | 있음 | charts.r11 › ChartFrame 표로 보기 |
| 130 | [C10 민감도] 표 열 비중 바꾼 항목 | Compare · L 꼬리말(문구로만) | — | 다른 보드(Compare) | charts.contract › C10 표 = 12 변형 × TOP 5(이름), 변동 표시 |
| 131 | [C10 민감도] 표 열 순위 변동 | Compare · L 꼬리말(문구로만) | — | 다른 보드(Compare) | charts.contract › C10 표 = 12 변형 × TOP 5(이름), 변동 표시 |
| 132 | [C10 민감도] 표 열 TOP 5 (`chart.col.top5`) | Compare · L 꼬리말(문구로만) | — | 다른 보드(Compare) | charts.contract › C10 표 = 12 변형 × TOP 5(이름), 변동 표시 |
| 133 | [C10 민감도] 표 열 표시(진입·이탈) | Compare · L 꼬리말(문구로만) | — | 다른 보드(Compare) | charts.contract › C10 표 = 12 변형 × TOP 5(이름), 변동 표시 |
| 134 | [공통] 숫자 누르면 출처 서랍 (FactCell → GET /provenance/{id}) | Shell · 3 (Scenario는 바닥 문구 "숫자를 누르면 출처가 열려요") | — | 다른 보드(Shell) | provenancePreserved(FactCell 공용) · FactCell.test |
| 135 | [키보드] 폼 Enter 제출(form onSubmit) · 슬라이더 화살표 키(range) | Scenario · form + input type=range (기본 키보드 동작) | — | 있음 | scenario.test › 잘못된 입력(폼 제출) · 슬라이더(range 기본 키보드) |
| 136 | [API] GET /scenarios (`api/hooks.ts` useScenarios) | Scenario · 1 출발 조건 목록 | — | 있음 | scenario.test › 출발 조건 select(GET /scenarios) |
| 137 | [API] POST /scenarios (useCreateScenario) | Scenario · 2 [이 조건 저장] | — | 있음 | scenario.test › 슬라이더 … 저장 → POST /scenarios |
| 138 | [API] GET /scenarios/{id}/preview?snapshot_id= (useScenarioPreview) | Scenario · 4 요건 표 · 3 캐시 수 | — | 있음 | scenario.test › 요건 사전 계산 · e2e api screens › G5 미리보기 |
| 139 | [API] GET /snapshots/{sid}/dashboard?scenario= — 이전 TOP 5·이름 (useDashboard) | Scenario · 3 이전 결과 표 '이전' 열 | — | 있음 | scenario.test › 재판정 실행(이전 = 대시보드 TOP 5) |
| 140 | [API] GET /snapshots/{sid}/compare?ids=TOP5&scenario= — C07 판정 (useCompare) | Scenario · 판정기 결과 | — | 있음 | scenario.test › 판정기 결과·민감도(C07) · escaped 봉투 |
| 141 | [API] GET /snapshots/{sid}/sensitivity?scenario= (useSensitivity) | Scenario · 가중치 민감도 | — | 있음 | scenario.test › 판정기 결과·민감도(C10) |
| 142 | [API] POST /jobs {rejudge} (useCreateJob) | Scenario · 3 [다시 판정하기] | — | 있음 | scenario.test › 재판정 실행 → POST /jobs(rejudge) |
| 143 | [API] GET /jobs/{id} 2초 폴링 (useJob · JobProgress) | Scenario · F 작업 진행 | — | 있음 | scenario.test › 재판정 실행(2초 폴링 2회 이상) |
| 144 | [API] GET /snapshots/{afterId}/dashboard — 잡이 쓴 새 리비전 + 무효화 | Scenario · 3 이전 결과 표 '새' 열 | — | 있음 | r3d › G5 재판정(GET /snapshots/13/dashboard?scenario=B) |
| 145 | [API] GET /regions/{id}/snapshots — 결과 리비전 이름 (useSnapshot) | Scenario · 3 "기준일 2026-10-14 ([n]번째 수정본)" | — | 있음 | r3d › G5 재판정(리비전 이름 snapshotText) |

## 요약

전체 145 · 있음 130 · 문구로만 3 · 다른 보드 12 · 빠짐 0 (2026-10-16 목업 고침 반영 — `../fixes/fixes-Scenario.md`)

### 빠짐 목록

- 없음 — 모두 고침(보드에 그리거나 "구현할 때 지금 동작 그대로 유지" 상자에 적음)

## 새로 더한 것 (기존 화면에 없던 것)

| # | 목업에 새로 생긴 것 | 목업 위치 (섹션) | 비고 |
|---|---|---|---|
| N1 | 4단계 진행 표시(출발 조건 고르기 → 내 조건 적기 → 다시 판정하기 → 요건·판정·순위 확인) | 머리 | — |
| N2 | 소개 문단(같은 질문은 저장한 답을 다시 써서 빨라요) | 머리 | — |
| N3 | 출발 조건 카드 라디오(코드·이름·누구에게 맞는지·주요 값, '지금 보는 조건' 표시) | 1 | 기존은 select만 |
| N4 | 폼 묶음 제목 '나와 우리 집 · 돈 · 계획' | 2 | — |
| N5 | 칸 단위 표시(명 · 점 / 84점 · 억원 · 년 · ㎡ · 약 34평형)와 자리표시 예시 | 2 | — |
| N6 | 청약 가점 [?] 용어 버튼 | 2 | — |
| N7 | "비워 둔 칸은 '미입력'으로 두고 계산해요" 안내 | 2 | — |
| N8 | 비중 슬라이더마다 '무엇을 보나요' 설명 한 줄 | 2 | — |
| N9 | 칸별 허용 범위 요약 줄 | B | — |
| N10 | 토스트 [닫기] 버튼 | C | 공통 토스트(Shell · 6)와 같음 |
| N11 | 다시 판정 설명 "새 수정본에 저장되고, 지금 보는 수정본은 그대로예요" | 3 | — |
| N12 | 완료 상태 줄 "다시 판정 끝났어요" | 3 | — |
| N13 | 이전 결과 표 '이전' 순위에 동률 배지 | 3 | — |
| N14 | 요건 요약 칩(세 요건 모두 충족 3곳 · 하나라도 미충족 40곳 · 확인 불가 섞임 36곳) | 4 | — |
| N15 | 요건 표 "79곳 중 8곳" + [나머지 71곳 더 보기] 버튼 | 4 | 기존은 전체 행 |
| N16 | 요건 표 단지 이름 = 상세 링크 | 4 | — |
| N17 | 믿음 정도 [?] 설명 버튼 | 판정기 결과 | — |
| N18 | 민감도 '한 줄 답' 요약과 "지금 순서: …" 줄 | 가중치 민감도 | 한 줄 답 문장 → 서버 값 개수 줄 "순위 변동: 있음 4 · 없음 8"(고침 SC-6) |
| N19 | 민감도 선 차트의 '주황 띠 = 상위 5곳 밖' | 가중치 민감도 | — |
| N20 | 화면 바닥 고지 + 라벨 범례 | 바닥 | — |

## 참고

- 목업의 6번째 비중은 'A 가점 높음(실거주)' 기준 '입주 시기'(move_in). 현재 코드는 시나리오 weights 키를 그대로 그려 base 는 '유동성'이다 — 키는 서버 값을 따른다.
- C07·C10 '표로 보기' 펼친 표는 Scenario 보드에 없고 Compare 보드 L에만 있다(C10 은 거기서도 문구로만).
- 작업 진행의 재큐잉·발행 안내는 Shell(공통 부품) 보드 6.
