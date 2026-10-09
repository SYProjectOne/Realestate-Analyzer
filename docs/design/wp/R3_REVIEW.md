# R3 독립 리뷰 결과 (main 3920312) — critical 3 / major 16 / minor 39

경로 기준: `backend/app/`, `frontend/src/`. 재현 스크립트는 리뷰어 scratchpad에 있었음(필요하면 다시 작성).

## Critical
- **C1** `scheduler/inputs.py:395`(읽기만), `analysis/_ranking.py:19` — `benchmark` 행을 쓰는 코드가 devseed(`api/devseed.py:829`)뿐. 내장 시나리오 5개 모두 benchmark 가중치 > 0이고 `weighted_total`은 성분 하나라도 None이면 None → **실데이터로는 종합 점수·순위·TOP 5·unstable이 전부 비어 나온다**. 설계 누락(어느 카드에도 benchmark 생성 단계 없음).
- **C2** `scheduler/inputs.py:155-160`, `api/views.py:335-348`, `scheduler/pipeline.py:652` — 판정 범위를 규칙으로 정함. 제외 클래스 목록에 없으면 무조건 "판정 대상" → classify 미해결(미분류·manual_review)도 판정 대상. 접수 확인 불가도 "참고"로 빠지지 않고 noul·점수·TOP 5·judged_count에 들어감. meta §1-3-4 위반: 판정 대상 = 포함(classify 확정) ∧ 접수 가능|미정; 분양가 미공개 → "보류 — 공고 후 재판정"; 접수 확인 불가 → "참고 후보(순위만)", 사다리 미실행; classify review → 미해결(판정 대상 아님).
- **C3** `normalize/notice_parser.py:168`, `normalize/fields.py:109` — OCR로 읽은 공고문 숫자가 "확인됨"으로 저장. 파서가 `error_text=="scan"`만 거르고 `ocr`·`ocr_partial:*`은 일반 공고문 취급. D5-4 위반(라벨 "추정(OCR)" + extract/audit 필수). `grep -rn "추정(OCR)" app/normalize` → 0, 테스트 없음.

## Major
- **M1** `normalize/resolver.py:122-131`, `normalize/judged.py:454-462` — 같은 rank 1차끼리 상충 시 "최신" 임시 채택; compare contradicts여도 현재 채택값이 1차면 유지; compare review/degraded일 때도 최신값이 "확인됨"으로 점수에 들어감. 재현: 상세·목록 rank1 두 행 → `apply_compare(relation="contradicts")` → `changed=False`.
- **M2** `analysis/score.py:419`, `:437` — liquidity·move_in 라벨 "확인됨" 고정, 계약 .2의 `down_payment_label`·`resale_label`·`residency_label` 무시.
- **M3** (추정) `api/views.py:324-332`, `:514-526`, `reports/data.py:835-860` vs `scheduler/inputs.py:228-245` — 화면·CSV·보고서 "현재 구매가"는 `complex_type`, 점수·판정은 최신 `payment_terms.price_by_type`(§6-1). 임의공급 가격 변경 시 표시값≠판정값.
- **M4** `api/routers/snapshots.py:474-486`, `:546-557`, `market.py:120-131` — 출처 없음/값 없음 항목을 뺀 부분합을 전체 합계(미분양 KPI·입주물량·입주 피크)로 표시.
- **M5** `remaining_event` 생성 코드 없음(devseed만) → C8 타임라인 항상 "본청약만"(`routers/complexes.py:252`).
- **M6** `catalyst`·`catalyst_link` 생성 코드 없음; P4는 기존 행 재분류만(`pipeline.py:479`); D1-6 "호재 URL 사람 입력" 엔드포인트 없음 → G6 C9·G3 호재 탭 항상 빔.
- **M7** `checklist_item` 생성 로직 없음(중도금일·만료·공고 예상; devseed만), API는 PATCH만 → G7 Checklist·Calendar 빔.
- **M8** contradicted 주장 목록과 문장 수정 경로가 API·G7에 없음(RA §10 "스냅샷 published 안 됨" 대응 불가).
- **M9** `core/settings.py:63`, `api/deps.py:59-78` — 공유 토큰 30일 만료(RA §10 보안 5) 없음, `share_token_ttl_days` 미사용, 공유 링크 발급 경로 없음.
- **M10** `collectors/news/collector.py:179-182` — 뉴스 API 질의(`"<region.name> 분양"`)가 guard 미경유(RA §10 보안 1).
- **M11** (추정) `infra/.env.example:12`(ENV=dev), `docker-compose.yml:46-47`, `api/deps.py:66-67` — dev에서 토큰 비면 인증 꺼진 채 8000 포트가 모든 인터페이스에 열림.
- **M12** `judge/base.py:170-175`, `:293-303`, `scheduler/judge_version.py:42-47` — 첫 판정 호출이 error/blocked면 접미 없는 버전 기록 → 다음 실행에서 모델 확인 시 "버전 변경" 오탐 → critical 이벤트·웹훅·전 지역 재판정(실제 호출).
- **M13** (추정) `collectors/official_site/collector.py:173-190`, `render.py:110-160` — 팝업에 시각·애니메이션이 있으면 렌더마다 해시가 달라 raw_document 증가 + 가짜 팝업 변경 critical + 재판정 → T8·T17 깨짐. 테스트는 고정 PNG FakeRenderer라 못 잡음.
- **M14** (추정) `reports/data.py:862-883` — `_dates`가 `start`/`end` Fact 형태만 읽음. 실제 저장 `[{"kind","date"}]`·`interim_schedule.due_date` 문자열을 못 읽어 보고서 3개월 캘린더(s08)에서 청약·계약·중도금 날짜가 전부 빠짐.
- **M15** WP6 "Lighthouse 80 이상" 테스트·실행 기록 없음(`e2e/pages/lighthouse.mjs`는 수동).
- **M16** `normalize/fields.py:118-147`, `tests/normalize/test_store.py:146` — "모든 수치 필드 provenance 전수 검사"가 손으로 쓴 엔티티 4개만 봄; 모델 컬럼과 대조 안 함(`inclusion_prob`·시장 테이블 누락).

## Minor
1. T8 테스트가 팝업만 검사, 목록 diff(`scheduler/detect.py:85`) 미검증. (WP7)
2. `.github/workflows/ci.yml`에 Playwright e2e·차트 스크린샷(기준 이미지 win32 전용)·chromium 설치 없음; `tests/reports/test_pdf.py` skip 장치 없어 CI 실패 추정. (WP0)
3. WP2 "공고문 16개 가격 일치" expected가 13(+1)개, gochon13·marinabay 가격 단언 없음. (WP2)
4. "일일 수집 10분"을 청약홈 수집기만 FakeClock으로 잼. (WP1)
5. "openapi-typescript 생성 성공"·`schema.d.ts` 최신성 검사 테스트 없음. (WP0)
6. 픽스처 수정 시 CHANGELOG 사유 강제 장치 없음. (WP9)
7. D6 "부록 A 도구별 임계값" 테스트 없음(구현 `reports/data.py:1064-1091`). (WP8)
8. `tests/api/test_schemathesis.py:64` 경로 ID 무작위라 12개 작업 200 본문 미검증. (WP5)
9. `tests/api/test_perf_t16.py` 점수 행 없이·warmup 후 측정, CSV 미측정; size=1000이면 1.1~1.5초. (WP5)
10. `core/protocols.py:125` canonical JSON에 `allow_nan=False` 없음; Decimal TypeError; `1`과 `1.0` 다른 hash. (WP0, WP3)
11. `judge/base.py:242`, `:248` 캐시 조회 전에 adapter_version(서버 왕복) 확인 → 판정기 다운 시 캐시 재생 불가·blocked 대신 JudgeUnavailable; 모델 확정 전 경합 시 실제 호출 2회 가능. (WP3)
12. `core/redact.py:23-32`, `:54-60` guard 누락 형태: `+82` 전화번호, 공백 분리 주민번호, int 번호; 비밀값 목록에 NEWS 키 Secret 단독·디코딩된 DATA_GO 키·DATABASE_URL 누락. (WP0)
13. `scheduler/notify.py:76-79` guard 1건에 배치 알림 전체 소실; notify가 collect.daily에서만 불려 human check·생활권 편집·버전 변경 critical 알림 안 감. (WP7)
14. (추정) `scheduler/collect.py:266`, `:280`, `pipeline.py:753` 예외 문구가 마스킹 없이 `job_run.stats`에 → 읽기 전용 토큰으로 노출. (WP7)
15. `api/routers/ops.py:237-249`, `pages/ops/HumanCheckForm.tsx:42` `entered_by` 32자 자유 입력 — "역할 문자열만" 미강제. (WP5, WP6)
16. (추정) `components/ProvenancePanel.tsx:99`, `:173` 외 4곳 서버 URL을 scheme 검사 없이 href에. (WP6)
17. `core/http.py:192`, `:332-337` 사설 IP·localhost 미차단 + 리다이렉트 추종; `collectors/applyhome/parse.py:109` PDF 링크 검사가 부분 문자열. (WP0, WP1)
18. `api/routers/snapshots.py:332-400` CSV 수식 인젝션 처리 없음, prov 열 없음, rank 맨 숫자. (WP5)
19. `main.py:90` `/docs`·`/redoc`·`/openapi.json` 무인증. (WP5)
20. `api/routers/analysis.py:335-377`, `views.py:1104-1151` vs `scheduler/inputs.py:276-316` 미리보기 요건 사전 계산 입력이 파이프라인과 다름(has_priority_supply False→None, regulated 매핑, immediate_move_in 누락). (WP5, WP7)
21. `views.py:251-255` vs `inputs.py:127-133` 같은 날 날짜만/시각 포함 값 겹칠 때 접수 행 선택이 API·파이프라인 다름. (WP5)
22. 엉뚱한 출처 링크: KPI prov가 무관한 score_total(`snapshots.py:531-534`), catalyst `expected_ym`이 classify seq(`complexes.py:170`), 비교군 low/median/high가 gap 라벨(`complexes.py:68`, `:81-86`), market `checked_at`이 기준일(`market.py:236-240`). (WP5)
23. `ops.py:146-148` `cached_hits=0` 고정. (WP5)
24. `analysis/gap.py:173` 가격 출처 행 없으면 `price_label` 기본 "확인됨". (WP4, WP7)
25. `analysis/score.py:155-157` `delta_rerank`가 점수 차가 아니라 relevance 차(§6-5 해석, 추정); 화면·보고서 미표시. (WP4, WP6, WP8)
26. `reports/charts.py:122`, `:166`, `:62-77`, `C06/buildOption.ts:171-185` C1·C7 막대 라벨이 반올림 안 된 확률·라벨 없음; C6 "미판정" 막대가 최대 기여(w×10)로 스택 부풀림. (WP8, WP6)
27. `eslint-rules/no-raw-number-render.js` JSX children만 검사(props·i18n 파라미터·`formatNumber(confidence)`·`buildOption` 전체 누락); `showLabel={false}`로 price_low 라벨 숨김(`ComplexHeader.tsx:58`, `tabs.tsx:17`, `ComplexTable.tsx:161`). (WP6)
28. `charts/C07/buildOption.ts:35-39` 동률을 브라우저에서 재계산 + status review 포함. (WP6)
29. 계약이 맨 숫자 허용: confidence, weight, contribution, annualized, n_trades, coef_used, rank, supply_ref_pct 등(`views.py:728-909`, `complexes.py:91-109`). (WP0)
30. `api/devseed.py:193-197`, `:1237-1246` `--synth`·`--no-reset`에 ENV·DB 종류 확인 없음 → 운영 Postgres에 지어낸 출처 행. (WP5)
31. `core/settings.py:115-119` `ENV=prod` + `JUDGE_ADAPTER=mock` 허용. (WP0)
32. `scheduler/pipeline.py:569` `_prev_anchor`가 hash 미스면 실제 rerank 호출 후 결과 버림. (WP7)
33. `scheduler/runner.py` worker 사망 시 job이 영원히 running; collect 중복 제거가 queued와만 비교(`jobs.py:89-97`). (WP7)
34. `docs/runbook.md` §6·§8 백업(pg_dump·rsync) 자동화 없음, runbook은 tar; 월별 압축 시 `/raw/{id}` 못 읽음(추정). (WP0)
35. D2-6 "범위 경계" 목록이 G7에 없음(G2 필터로만). (WP6)
36. 소유 밖 변경 커밋: `a24c625`, `6e4b10e`, `0947379`, `ed67c4b` — 모두 CEO가 해당 라운드에 위임한 범위였음(기록 목적).
37. T16 "60fps"를 DOM 행 수<100으로, T18을 RawDocument ≥1로 대리 검증; 정규화 성공 미단언. (WP6, WP7)
38. `api/facts.py:103-104` 라벨 있고 prov None이면 모든 환경에서 예외 — `errors.py` "dev만" 설명과 다름. (WP5)
39. `reports/data.py:552-558` 보고서에서 출처 누락이 경고 로그·dev 예외 없이 "출처 누락" 표시만 — T13이 API에서만 강제. (WP8)

## 깨끗했던 항목
캐시 키 단일 정의 + DB 유일 제약; guard가 9개 도구 모두 hash·기록보다 먼저; 경로 조작 차단; 원문 HTML attachment+nosniff, 프론트 HTML 미리보기 없음; `dangerouslySetInnerHTML`·`innerHTML`·`srcdoc` 0; 보고서 Jinja2 autoescape, 부록 B http(s)만; 읽기 전용 토큰 쓰기 7종 403; 키워드 기반 판단 코드 없음; 지역명 하드코딩 0; 비밀값 커밋 0; 마이그레이션·생성물 diff 0; `/complexes` 1,000단지 1초 충족.
