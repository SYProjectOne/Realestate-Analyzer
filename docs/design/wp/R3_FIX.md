# R3 수정 라운드 — 리뷰(`R3_REVIEW.md`) 항목 배정 (계약 2026-10-09.3 → .4)

규칙: `R1_COMMON.md` 그대로. 각 에이전트는 **아래 "파일 소유"에 적힌 파일만** 수정한다(같은 라운드 5명 병렬 — 겹치면 머지 충돌). 다른 소유 파일이 필요하면 보고의 "요청". 모든 항목은 **실패하는 테스트 먼저**. 수정한 리뷰 항목 ID별로 테스트 이름을 보고에 표로.

## CEO 결정 (D9, DECISIONS에 반영됨)
- **D9-1 판정 범위(C2)** — meta §1-3-4 그대로, 공용 함수 하나(`app/analysis/scope.py: judge_scope(...)`)로만 계산하고 API·파이프라인·보고서가 모두 이것을 부른다:
  - 제외: inclusion classify(auto)가 제외 클래스(공공·임대·비아파트·범위 밖) 또는 `범위 경계`
  - 보류: 포함 확정이나 분양가 미공개(공고 전) → "보류 — 공고 후 재판정"
  - 미해결: inclusion classify가 review/escaped/미분류 → "미해결(분류 판정 미해결)" — 판정 대상 아님, 사다리·점수 없음
  - 참고: 포함 확정 + 가격 있음 + 접수 상태 `확인 불가` 또는 `불가` → "참고 후보(순위만)", 사다리 미실행, rerank 후보에는 포함
  - 판정 대상: 포함 확정 + 가격 있음 + 접수 `가능` 또는 `미정`
  - `score_total.judge_scope` 값 집합에 "미해결" 추가(계약 .4).
- **D9-2 벤치마크 생성(C1)** — 벤치마크 = 같은 생활권에서 입주 완료(입주월 ≤ 기준일)된 아파트로 (a) 84㎡에 가장 가까운 타입의 분양가(청약홈 공식 API 과거 공고 = 확인됨, 언론 역산 = 추정)와 (b) 입주월 이후 실거래(rtms, 해제 제외, 80~85㎡)를 모두 가진 단지. 단지 매칭 = 정규화한 단지명 + 법정동(문자열 정규화는 판단이 아님; 모호하면 매칭하지 않고 "확인 불가(매칭 모호)" 기록). `sale_period` = 분양 연도 ≥ 기준연도−3 → "고가 분양기", 그 이전 → "저가 분양기"(라벨 추정, 식 기록). 분양권 거래(입주 전)는 `is_presale=true`. 생활권 표본이 0이면 지역 전체 생활권으로 대체(라벨 "추정(대체: 지역 전체)"), 그래도 0이면 benchmark 성분 null → RA대로 종합 미계산(이 경우 G1·보고서에 "벤치마크 없음" 사유 표시).
- **D9-3** 접수 상태 변경 → `change_event(intake_status, critical)`.

=====F1a=====
# F1a 데이터 조립 (C1·M5·M6·M7)
파일 소유: `backend/app/normalize/benchmark.py`(신규), `normalize/remaining.py`(신규), `normalize/checklist.py`(신규), `normalize/catalyst.py`(신규), `backend/app/collectors/applyhome/`(과거 공고 조회 창 확장만), `backend/app/collectors/rtms/`(조회 창: 벤치마크용 과거 월), `backend/app/scheduler/collect.py`, `backend/app/scheduler/assemble.py`(신규), 해당 테스트 디렉터리.
1. C1: D9-2 벤치마크 생성 — 수집(청약홈 API 과거 공고 N년, 기본 10년; rtms 입주 후 월) → `normalize/benchmark.py` 조립 → `benchmark` 행 + provenance. `scheduler/assemble.py`가 collect.weekly 후 호출. 인천·김포 녹화/실 API로 생활권별 표본 수 보고.
2. M5: `remaining_event` 생성 — 청약홈 무순위·임의공급·잔여세대 공고(API·웹) → kind·notice_no·notice_date·apply_dates·units_by_type·result_text.
3. M6: 호재 생성 — news collector 결과 → `catalyst` 후보 행(stage 미정, `location_confirmed=false`, link 없음); 분류(kind·stage)는 P4 classify가 한다(판정은 judge만). 사람 URL 입력은 F3가 엔드포인트를 만든다 — F1a는 `normalize/catalyst.py`에 "URL+제목+발췌 → catalyst 후보 행" 공개 함수 제공.
4. M7: `checklist_item` 생성 — 사실 테이블에서 결정론적으로: 중도금일(interim_schedule), 전매 종료·거주의무 만료, 계약일, 공고 예상(청약홈 공고 예정), 추정 라벨 항목(토허·대지지분·비과세 거주요건)은 "법적 확인" 항목으로. 멱등(같은 항목 중복 생성 없음).
완료: 각 항목 테스트 + 전체 pytest·ruff·mypy.

=====F1b=====
# F1b 판정·정규화·보안 정합 (C3·M1·M10·M12·M13·M16 + minor 3·10·11·12·17)
파일 소유: `backend/app/normalize/{notice_parser,fields,resolver,judged,store,provenance}.py`, `backend/app/judge/`, `backend/app/core/{protocols,redact,http}.py`, `backend/app/collectors/{official_site,news}/`, `backend/app/collectors/applyhome/parse.py`, `backend/app/scheduler/judge_version.py`, 해당 테스트.
- C3: OCR 원문(`error_text` ocr·ocr_partial:*)은 라벨 "추정(OCR)" + 모든 수치 필드 `needs_extract`(판정기 extract/audit 경유) — 테스트 필수.
- M1: 같은 rank 1차 상충은 채택 보류(`needs_compare=True`, 표시 라벨 "확인 불가(출처 상충)" 또는 병기, 점수 미사용) → compare 결과로만 채택; contradicts면 RA §3 규칙(공고문 채택·병기); review/degraded면 미채택 유지.
- M10: news 질의 guard 경유(`judge/guard.py` 공용 필터) — 거부 시 요청 안 함 + 실패 행.
- M12 + minor 11: adapter_version 확정 로직 — error/blocked 행은 버전 근거로 쓰지 않음; 캐시 조회를 서버 왕복보다 먼저(판정기 다운 시 캐시 재생 가능); 모델 확정 전 동시 호출 1회 보장.
- M13: 팝업 변경 감지 해시를 안정화(시각·애니메이션 무시: 렌더 대기·애니메이션 정지 CSS·perceptual hash + 임계값, 또는 DOM 텍스트 정규화 해시 병행) + 실제 Playwright로 시각 표시가 있는 로컬 페이지 3회 렌더 → 같은 해시 테스트.
- M16: provenance 전수 검사를 모델 컬럼 메타데이터 기반으로(수치 컬럼 자동 수집).
- minor 3: 공고문 16개 가격 단언(gochon13·marinabay 포함; 표를 못 읽으면 needs_extract 단언). minor 10: canonical JSON `allow_nan=False`, Decimal 처리, 1 vs 1.0 정규화(문서화 + 테스트; 기존 픽스처 hash가 바뀌면 `contracts/fixtures/tools/build_incheon_gimpo.py` 재생성은 F3에 요청). minor 12: redact 패턴 보강(+82, 공백 분리 주민번호, int, NEWS Secret 단독, 디코딩 키, DATABASE_URL). minor 17: http 사설 IP·localhost 차단(설정으로 테스트 허용), 리다이렉트 대상 재검사, PDF 링크 호스트 정확 비교.

=====F2=====
# F2 점수·파이프라인 정합 (C2·M2·M3 + minor 1·13·14·20·21·24·25·32·33·37(T18))
파일 소유: `backend/app/analysis/`(신규 `scope.py`, `price_view.py` 포함), `backend/app/scheduler/{inputs,pipeline,runner,jobs,notify,rejudge,detect}.py`, `backend/app/api/views.py`(judge_scope·현재 구매가·요건 입력·접수 행 선택 부분만 — 공용 함수 호출로 교체), 해당 테스트.
- C2: D9-1 `analysis/scope.py` 공용 함수 + 파이프라인(사다리 미실행·rerank 포함 규칙)·API·보고서(F4가 호출하도록 시그니처 README) 적용. 테스트: 미분류/manual_review/확인 불가/불가/보류 각각.
- M2: liquidity·move_in 라벨을 입력 라벨에서 합성(가장 약한 라벨).
- M3: "현재 구매가" 공용 함수(`analysis/price_view.py`: §6-1 최신 payment_terms.price_by_type 우선, 없으면 complex_type) — 파이프라인·API가 사용; 보고서는 F4가 사용.
- D9-3: 접수 상태 변경 → change_event critical.
- minor 1(목록 diff T8 테스트), 13(notify: 건별 guard, 모든 critical 이벤트 경로에서 알림), 14(job_run.stats 예외 문구 redact), 20·21(미리보기 요건 입력·접수 행 선택을 파이프라인과 같은 공용 함수로), 24(가격 출처 없으면 라벨 "확인 불가(출처 누락)"), 25(delta_rerank = 점수 차로; §6-5), 32(`_prev_anchor` 실제 호출 금지 — 캐시만), 33(runner: 하트비트·stale running 회수, 중복 제거 running 포함), 37 일부(T18 정규화 성공 단언).

=====F3=====
# F3 API·프론트·계약 .4·운영 (M4·M8·M9·M11·M15 + M6 엔드포인트 + minor 2·5·6·8·9·15·16·18·19·22·23·26(C6)·27·28·29·30·31·34·35·37(T16)·38)
파일 소유: `contracts/`(openapi·schemas·migrations `0004_r3.py`·CHANGELOG·fixtures 재생성 도구 실행), `backend/app/models/`, `backend/app/core/{settings,db}.py`, `backend/app/main.py`, `backend/app/api/`(단 `views.py`의 F2 담당 부분 제외 — 다른 함수만), `frontend/`, `infra/`, `.github/`, `docs/runbook.md`, 해당 테스트. **계약 .4 소유자** — 다른 에이전트의 계약 요청을 받아 반영(F2: judge_scope "미해결" 값).
- 계약 .4: judge_scope "미해결"; `GET /snapshots/{sid}/claims?status=contradicted` + `PATCH /claims/{id}`(문장 수정 → 원자 분할 재검증 잡 등록); `POST /catalysts`(사람 URL 입력 → F1a `normalize/catalyst.py` 호출 → 분류 잡); 공유 링크 `POST /share-links`(읽기 전용, 만료 30일; `share_token_ttl_days` 사용) + 검증; minor 29 맨 숫자 → Fact 또는 명시적 "비수치 메타" 표기(계약에 근거 문구); minor 22 출처 링크 교정.
- M4 부분합 → 합계는 전부 있을 때만, 아니면 "확인 불가(일부 누락 n건)". M8 G7 contradicted 목록·수정 UI. M9 위. M11 dev라도 토큰이 비면 127.0.0.1에만 바인드 + 경고(compose는 토큰 필수), `.env.example` 기본 ENV=prod 검토. M15 Lighthouse 자동 테스트(80 이상, `npm run lighthouse` + CI 잡).
- minor 2(CI: chromium 설치·e2e·PDF 테스트), 5(schema.d.ts 최신성 테스트), 6(픽스처 변경 시 CHANGELOG 사유 강제 테스트), 8(schemathesis 유효 ID), 9(perf: 점수 행 포함·cold·CSV), 15(entered_by 역할 enum), 16(href scheme 화이트리스트), 18(CSV 수식 인젝션·prov 열), 19(/docs 인증), 23(cached_hits 실제 집계), 26 C6(미판정 막대 = 0 길이 + 빗금 표시만), 27(eslint 규칙 확장: props·i18n 파라미터·format 함수 인자; showLabel=false 제거), 28(C7: 서버 tie 값만 사용, review 제외), 30(devseed: prod·Postgres에서 거부), 31(prod+mock 거부), 34(백업 스크립트·월별 압축 후 `/raw` 읽기), 35(G7 범위 경계 목록), 37 T16(실제 rAF 프레임 간격 측정), 38(facts 예외 dev만).
- F1b가 canonical JSON을 바꾸면 픽스처 hash 재생성(`build_incheon_gimpo.py`)은 F3가 마지막에 main 머지 후 실행.

=====F4=====
# F4 보고서 정합 (M14 + minor 7·26(C1·C7)·39 + C2·M3 적용)
파일 소유: `backend/app/reports/`, `backend/tests/reports/`.
- M14 `_dates`가 실제 저장 형태(`[{"kind","date"}]`, `interim_schedule.due_date`) 처리 + 3개월 캘린더 테스트.
- minor 7 부록 A 도구별 임계값 테스트. minor 26 C1·C7 라벨 반올림·라벨 표기. minor 39 출처 누락 시 dev 예외·prod 경고 로그(API와 같은 규칙).
- C2·M3: F2의 `analysis/scope.py`·`analysis/price_view.py`가 머지되면 그것을 쓰도록 — 이번 라운드에는 F2와 동시 진행이므로 **인터페이스(함수 이름·시그니처)를 R3_FIX에 적힌 대로 가정**하고 import를 지연(없으면 기존 동작)시키는 대신, F2 머지 후 CEO가 재지시할 수 있게 보고에 적는다. `tests/reports/_seed.py` → `app.api.devseed` 재사용으로 교체.
