# 설계 결정 v1.1 — RA_v1 대비 변경분 (2026-10-09, CEO 오케스트레이터)

원본 설계도는 `docs/source/RA_v1.md`(이하 RA)이다. 이 문서는 §11 미결 사항에 대한 사람(라홈)의 답과, 그 답 때문에 바뀐 계약·WP 카드만 적는다. RA와 이 문서가 충돌하면 **이 문서가 이긴다**. RA가 말하지 않는 화면·운영 규칙은 `docs/source/meta_prompt.md` §2-6~§2-9를 따른다.

계약 버전: `2026-10-09.15`

## D1. §11 미결 사항 답

| # | 항목 | 결정 | 출처 |
| --- | --- | --- | --- |
| 1 | 생활권 정의 | **지역은 사용자가 입력한다**(D2). 생활권 기본값 = 시군구 1개당 생활권 1개, 사용자가 화면에서 법정동을 옮겨 나누거나 묶는다 | 사람 답 |
| 2 | 연식 보정 c와 상한 | 0.015/년, 상한 8년, 라벨 추정 | 사람 답 |
| 3 | 공급 기준치 U_ref | 생활권 세대수의 8%, 라벨 추정 | 사람 답 |
| 4 | 상황 가중치 | RA §6-4 표 그대로 (A·D는 liquidity → move_in) | 사람 답 |
| 5 | 실거래 API 키 | 사람이 발급받아 `.env`의 `DATA_GO_KR_KEY`에 직접 넣는다(2026-10-09 결정). rt.molit.go.kr 웹 자동수집은 이용안내가 금지하므로 구현하지 않는다. 키가 없는 동안 rtms는 비활성이고 가격 갭·벤치마크는 "확인 불가(실거래 키 없음)" → RA §6-4대로 종합 점수 미계산 | 사람 답 |
| 5a | 공식 API 확장 | 사람이 2026-10-09 추가 발급: 같은 `DATA_GO_KR_KEY`로 청약홈 분양정보·청약 신청/당첨자 API, NAVER Cloud API HUB 검색 키(`NEWS_API_PROVIDER=ncp`). 청약홈은 **공식 API 1순위, 웹 수집은 폴백**(RA ADR-4 확장). 입주물량 추정 집계 원천에 API 입주예정월 추가. 뉴스 collector 활성 | 사람 답 |
| 5b | 골든 파일 v2 | 세대수 가정값만 행안부 주민등록 세대수 실측으로 교체한 뒤 회귀 기준으로 고정(2026-10-09 결정) | 사람 답 |
| 6 | 뉴스 API | 2026-10-09 NAVER Cloud API HUB 검색 키 발급(5a) → news collector 활성(`naverapihub.apigw.ntruss.com/search/v1/news`). 키가 없으면 비활성, 호재는 사람이 URL 입력 가능 | 사람 답 |
| 6a | 청약홈 경쟁률 API | 사람이 2026-10-09 data.go.kr 15098905 활용신청 승인 — APT·무순위·임의공급 경쟁률 3종 200 확인. 경쟁률은 공식 API 1순위, 웹 수집은 폴백. 합성 픽스처는 실녹화로 교체(WP9-후속) | 사람 답 |
| 7 | 웹훅 | 없음. `notify.py`는 구현·테스트하고 `WEBHOOK_URL`이 비면 보내지 않는다 | 사람 답 |
| 8 | 보고서 형식 | **HTML + PDF** 두 가지(D4). md·docx 없음 | 사람 답 |
| 9 | 실행 수단·병렬 | Claude Code 서브에이전트, worktree 격리, R1 병렬 8명 | 사람 답 |
| 10 | DB | 개발 SQLite, compose는 Postgres 16. Docker Desktop은 사람이 설치 중 — 설치 전에는 compose 검증 보류 | 사람 답 |
| 11 | OCR | **가장 진보된 무료 한글 OCR을 찾아 벤치마크 후 채택, 기준 미달이면 OCR 없음**(D5) | 사람 답 |
| 12 | 판정기 임계값 | **설치된 JEV 기본값을 따르고 업데이트 시 자동 반영**(D6) | 사람 답 |
| 13 | 사용자 수 | 1명 (ADR-9 유지) | 사람 답 |
| 14 | 보존 기간 | 무기한, 삭제 없음; 디스크 부족 시 월별 압축 | 사람 답 |

## D2. 지역은 사용자가 자유 지명으로 입력한다 (계약 확장)

프로그램은 인천·김포 전용이 아니다. 사용자가 "송도", "검단", "김포시", "인천 연수구"처럼 **자유 지명**을 입력하면 후보(시도·시군구·행정동·법정동)를 보여 주고, 사용자가 고른 묶음이 하나의 `region`이 된다. 인천·김포는 회귀 픽스처(RA §9)로만 남는다. 코드에 지역명을 하드코딩하지 않는다.

### D2-1 참조 데이터 (새 테이블)

| 테이블 | 핵심 컬럼 | 원천 | 규칙 |
| --- | --- | --- | --- |
| `legal_dong` | code(10자리, PK), sido_name, sigungu_name, eupmyeondong_name, ri_name, full_name, sigungu_code(5자리), active(bool), source_date | 행정표준코드관리시스템 "법정동코드 전체자료"(키 불필요 파일) | 폐지 코드는 active=false로 유지 |
| `admin_dong` | code(10자리, PK), full_name, name, sigungu_code, active, source_date | 행안부 행정동 코드(jscode) | — |
| `admin_legal_map` | admin_code, legal_code | 행안부 "행정기관 및 관할구역(법정동) 변경내역" | (admin_code, legal_code) 유일 |
| `household_stat` | id, scope_kind(admin_dong/sigungu), scope_code, ym, households, raw_document_id, label | 행안부 주민등록 인구 및 세대현황(키 불필요) | 라벨 "추정(주민등록 세대)" 고정; 생활권 세대수 = 소속 법정동에 걸친 행정동 세대수 합(1:N 매핑은 균등 분할, 라벨 추정) |

참조 파일은 `collectors/reference/`(WP1)가 내려받아 `raw_document`로 저장하고 파싱해 위 테이블에 적재한다. 다운로드가 실패해도 동작하도록 최신 파일 사본을 `contracts/fixtures/reference/`에 둔다(공공누리 제1유형).

### D2-2 `region` 컬럼 변경

`region`에 추가: `query_text`(사용자가 입력한 원문), `selections`(json: 고른 후보 `[{kind, code, full_name}]`), `sigungu_codes`(json, 실거래 조회용 5자리), `sido_codes`(json, 청약홈 조회용), `legal_dong_codes`(json, 전체 법정동), `supply_ref_pct`(기본 0.08), `status`(resolving/bootstrapping/ready/failed), `created_at`.
`living_areas` json 형식: `[{"id": "la_1", "name": "연수구", "legal_dong_codes": ["2818510600", ...], "households": Fact|null}]`. 단지의 `complex.living_area`는 단지 주소의 법정동 코드로 자동 배정한다.

### D2-3 새 REST 엔드포인트 (openapi.yaml에 추가)

| 메서드 | 경로 | 용도 | 응답 |
| --- | --- | --- | --- |
| GET | `/regions/resolve?q=` | 자유 지명 → 후보 목록. 이름 부분 일치(공백·"시/군/구/동" 접미사 무시), 정확 일치 우선. 판정기 호출 없음(문자열 매칭은 판단이 아님) | `RegionCandidate[]` = `{kind: sido\|sigungu\|admin_dong\|legal_dong, code, full_name, legal_dong_codes[], match: exact\|prefix\|partial}` |
| POST | `/regions` | `{name, query_text, selections[]}` → region 생성 + `region.bootstrap` 잡 등록 | `Region` (201) + `job_id` |
| PUT | `/regions/{id}/living-areas` | 생활권 편집 `{living_areas:[{name, legal_dong_codes[]}]}`; 모든 법정동은 정확히 한 생활권에 속해야 함(검증 실패 422) | `Region` + change_event(critical) + rejudge 잡 |
| GET | `/regions/{id}` | 지역 상세(선택·생활권·세대수·상태) | `Region` |

### D2-4 새 잡

| job_name | payload | 누가 넣나 | 하는 일 |
| --- | --- | --- | --- |
| `reference.refresh` | `{}` | 최초 기동 시 1회 + 매월 1일 05:00 | 법정동·행정동·매핑 파일 갱신 |
| `region.bootstrap` | `{region_id}` | POST /regions | collect.daily + collect.weekly 즉시 실행 → 스냅샷 생성 → 판정 파이프라인 P1~P9 → 점수 → publish |

### D2-5 화면 추가 (WP6)

| # | 라우트 | 요소 |
| --- | --- | --- |
| G0 지역 입력 | `/regions/new` | 검색창(자유 지명, 디바운스 자동완성 → `/regions/resolve`), 후보 다중 선택 칩, 이름 입력, "분석 시작" → `JobProgress`. 지역이 하나도 없으면 `/`가 여기로 보낸다 |
| G0-2 생활권 편집 | `/regions/:id/living-areas` | 생활권 카드 목록 + 법정동 목록(드래그 또는 선택 후 이동), 생활권 추가·이름 변경·삭제(빈 경우만), 세대수 표시(Fact), 저장 → PUT |

헤더의 `RegionPicker`에 "지역 추가" 항목을 둔다.

### D2-6 청약홈 조회

청약홈 목록은 `region.sido_codes`로 조회하고, 결과 단지 주소를 `legal_dong` 이름으로 매칭해 `region.legal_dong_codes`에 속한 것만 남긴다. 매칭 실패 단지는 버리지 않고 `checklist_item(kind=법적 확인)`이 아니라 G7 "범위 경계" 목록(`complex.inclusion_class = 범위 경계`)으로 남긴다.

## D3. 회귀 데이터

인천·김포 보고서는 `docs/source/incheon_gimpo_report.md`(Claude Docs 원문 변환본)다. 픽스처 지역 정의 = 인천 연수구(송도동)·서구/검단구(검단)·계양구 + 김포시. 보고서는 2026-07 검단구 분구 이후 "검단구"를 쓴다 — 법정동 코드 표가 아직 서구 코드면 둘 다 후보로 나와야 한다. (2026-10-09 확인: 공식 법정동코드 전체자료는 분구를 반영해 서구 28260을 폐지하고 검단구 28290을 둔다 — 계약 2026-10-09.2부터 예시·픽스처는 검단구 현행 코드.)

## D4. 보고서 = HTML + PDF (WP8 카드 변경)

- 산출물: `reports/templates/*.html.j2`(섹션 §1~§11 + 지역 추가 장 + 부록 A 판정 로그 · B 참고자료), `render.py`(Jinja2 → 단일 자립 HTML: CSS·ECharts 번들 인라인, 차트 option은 WP4 결과에서 생성), `pdf.py`(같은 HTML을 Playwright chromium `page.pdf()`로 인쇄 — weasyprint 미사용), `diff.py`.
- md 32KB 분할 규칙은 **삭제**. 대신 HTML은 섹션마다 앵커가 있고 단독으로 열린다.
- 완료 기준(T15 대체): 픽스처 스냅샷 2개로 html·pdf 생성; HTML이 외부 네트워크 없이 열림(외부 URL 리소스 0); PDF 페이지 수 > 0 이고 텍스트 추출로 섹션 제목 11개 확인; 참고자료 URL 전수 형식 유효; §8 숫자 20개 = `score_total`; diff 표 생성; contradicted claim이 있으면 생성 거부.
- `report` 잡 payload: `{snapshot_id, format: html|pdf, compare_snapshot_id?}`. `POST /reports`의 format enum도 `html|pdf`.
- CLI: `python -m app.reports.cli --snapshot <id> --format pdf` (프론트 없이 보고서; meta §2-8).

## D5. OCR (WP1 notice_pdf 담당)

후보: PaddleOCR 3.x(PP-OCRv5 korean / PaddleOCR-VL), RapidOCR(ONNX), Surya, EasyOCR, Tesseract(kor). 평가 절차:
1. 실제 스캔 공고문 또는 공고문 PDF 페이지를 이미지로 만든 시료 3장 이상(가격표 포함)을 `contracts/fixtures/ocr_samples/`에 둔다(정답 텍스트 동봉).
2. 기준: 가격표 숫자(공급금액·층·타입) **문자 단위 100% 일치**, CPU에서 페이지당 30초 이내, 라이선스가 개인 사용 무료, Windows pip 설치 가능.
3. 기준을 만족하는 것 중 정확도 최고를 채택하고 `pyproject` 선택 의존성 그룹 `ocr`로 제안(WP0 승인). 하나도 만족 못 하면 OCR 없음 — RA 기본값("확인 불가(스캔)" + 사람 입력).
4. 채택 시 OCR로 얻은 값의 라벨은 "추정(OCR)"이고, 판정기 extract/audit을 반드시 거친다.
5. 평가 결과는 `docs/adr/ADR-12-ocr.md`에 표로 남긴다.

## D6. 판정기 연결 (WP3 카드 변경)

- 실행 명령 기본값: `JEV_MCP_CMD="npx -y @jkudish/jev-mcp@latest"` (설치된 Claude 설정은 0.13.0 고정; 프로그램은 최신 추종).
- 어댑터는 **임계값을 넘기지 않는다** — JEV 기본값을 그대로 쓴다. RA WP3 카드의 숫자 목록은 "현재 기본값 참고"일 뿐 설정에 하드코딩하지 않는다.
- MCP `initialize` 응답의 `serverInfo.version`을 읽어 `adapter_version = "<어댑터 코드 버전>+jev-mcp@<서버 버전>"`으로 만든다. 서버 버전이 바뀌면 input_hash가 모두 바뀌어 전체 재판정 1회(RA §10 runbook "판정기 버전 변경"). 이때 `change_event(entity=judge, field=version, severity=critical)`을 남긴다.
- **보강(2026-10-09, 계약 2026-10-09.2)**: adapter_version에 JEV 응답의 `model`(예 `jev-1.13.0`)도 포함한다 — `"<코드>+jev-mcp@<서버 버전>+<model>"`. 모델이 바뀌어도(`jev-latest`가 새 모델을 가리키는 등, 서버 버전은 그대로일 수 있음) 재판정한다. 모델은 응답에만 보이므로 어댑터는 시작 시 judgment_log에서 같은 코드·서버 버전의 마지막 모델을 읽고(없으면 접미 없이), 응답의 model이 다르면 그 호출부터 새 버전의 input_hash로 기록한다. 모델 변경도 `change_event(entity=judge, field=version, severity=critical)` 대상이다(WP7).
- 도구가 응답에 담아 주는 임계값·결정(auto/review 등)을 `judgment_log.output_json`에 그대로 저장하고, 보고서 부록 A에 사용된 임계값을 도구별로 적는다(meta §2-1 "보고서에 적는다").
- JEV 도구 이름: `jev_screen, jev_extract, jev_audit, jev_classify, jev_compare, jev_noul, jev_rerank, jev_decide, jev_verify` (설치본에는 find·gate·review도 있으나 미사용).

## D7. 메타 프롬프트에서 가져오는 화면 공통 규칙 (WP6)

빈 값은 "확인 불가(사유)", 날짜는 기준일 대비 D±, 라이트/다크 두 테마, 모바일(≤768px)은 G1·G2·G3 읽기 전용, 모든 판정 화면 하단에 "투자 권유 아님 · 상대 비교" 고정 문구, 라벨은 색이 아니라 텍스트 배지, 차트 데이터는 표로 열어볼 수 있음.

## D8. 실행 방식

- CEO = 메인 세션. WP마다 서브에이전트 1명(worktree 격리, 브랜치 `wp/<n>-<slug>`). 원격 저장소가 없으므로 PR 대신 로컬 브랜치 → CEO 검증 → main 머지.
- R0은 WP0을 세 갈래로 나눈다: WP0-A 계약(contracts·models·protocols), WP0-B 뼈대(core·infra·CI·도구 설정), WP0-C 프론트 스캐폴드(A 머지 후).
- R1 8명: WP1a(applyhome·notice_pdf·OCR), WP1b(official_site·rtms·stats·news·reference), WP2, WP3, WP4, WP6a(pages), WP6b(charts·components), WP9-픽스처.
- `expected_scores_v2.json` 골든 파일은 R1 끝에 사람이 확인한다(RA §9).
- R4 실제 JEV 실행은 R3 통과 후 사람 확인을 받고 돌린다.

## D9. R3 리뷰 후속 결정 (2026-10-09, CEO)

원문: `docs/design/wp/R3_FIX.md` "CEO 결정" 절.
- D9-1 판정 범위는 meta §1-3-4를 공용 함수 `analysis/scope.py` 하나로 계산(제외·보류·미해결·참고·판정 대상). classify 미해결은 판정 대상이 아니다. 접수 확인 불가·불가는 "참고 후보(순위만)" — 사다리 미실행.
- D9-2 벤치마크는 청약홈 과거 공고 분양가 + 입주 후 실거래(rtms)로 자동 생성. 단지 매칭은 정규화 이름+법정동(모호하면 매칭 안 함). sale_period = 분양 연도 ≥ 기준연도−3 → 고가 분양기. 생활권 표본 0 → 지역 전체 대체(추정), 그래도 0 → 종합 미계산 + 사유 표시.
- D9-3 접수 상태 변경은 critical change_event.

## D10. R3 재리뷰 후속 결정 (2026-10-09, CEO) — 원문 `docs/design/wp/R3_REVIEW2.md`, 배정 `R3B_FIX.md`
- D10-1 스냅샷 화면·KPI·TOP 5는 그 스냅샷 score_run의 **저장값**(judge_scope·rank·total·성분)을 그대로 보인다(ADR-8 불변). 현재 사실로 계산한 범위가 저장값과 다르면 "재판정 필요" 배지 + rejudge 잡 제안만 한다. 저장값과 현재값을 한 행에 섞지 않는다.
- D10-2 접수 상태 분류는 공식 홈페이지 문구 해시(`popups[].text_sha256`/DOM 텍스트 해시)가 이전 분류 행과 같으면 그 분류를 복사한다(판정 호출 없음). 변경 없는 날 published 스냅샷의 범위·순위는 전날과 같다.
- D10-3 contradicted 주장 수정(PATCH /claims)은 같은 대상(section·complex·field)만 허용한다. 주장이 DB 사실에서 생성된 경우 그 사실 필드는 "확인 불가(검증 모순)"로 강등되어 점수 입력에서 빠지고 체크리스트 "사실 재확인" 항목이 생긴다. 사람 확인(human_check) 또는 새 원문이 오면 복원한다.
- D10-4 같은 블록 병합(W12c)은 무순위·임의공급·잔여세대 공고로 들어온 새 주택관리번호에만 적용한다. 차수·단지·블록 번호는 이름 키에서 지우지 않는다. 주소가 "…일원"처럼 구역 표현이면 병합하지 않는다. 일반 APT 공고끼리는 병합하지 않는다.
- D10-5 벤치마크 단지 매칭은 정규화 이름 **완전 일치**(차수·단지·블록 유지) + 법정동 일치만. 포함(contains)·준공연도 근사 매칭 금지.
- D10-6 뉴스 → P1 screen(호재 관련성) 통과분만 catalyst 후보가 된다. P4 호재 분류 클래스에 "호재 아님"을 두고, 종류(kind)도 classify로 정한다.
- D10-7 공유(읽기 전용 공유 링크) 토큰은 화면 조회 GET만: `/ops/*`·`/jobs*` 제외. 읽기 전용 API 토큰(READONLY_TOKEN)은 모든 GET.
- D10-8 T16 화면 기준: 가상 스크롤 p50 프레임 간격 ≤ 17ms(60fps) + p95 ≤ 34ms. RA "60fps"를 p50으로 해석해 기록.

## D11. R3 3차 리뷰 후속 결정 (2026-10-10, CEO) — 원문 `docs/design/wp/R3_REVIEW3.md`, 배정 `R3C_FIX.md`
- D11-1 **발행 스냅샷은 불변**. 발행 후 재판정(사람 확인·생활권 편집·판정기 버전 변경·시나리오 실행)은 같은 기준일의 **새 스냅샷 리비전**(`snapshot.revision`, 유일 (region_id, asof_date, revision))에 쓴다. 화면 기본 = 최신 published 리비전. 리비전 간 diff가 RA §10 "판정기 버전 변경 → 이전 run과 delta 표"와 "지역 추가 장"을 겸한다. 파생 행은 리비전이 완성된 뒤 한 번에 published.
- D11-2 '호재 아님' 판정은 catalyst를 지우지 않고 `stage='호재 아님'`(제외)로 남긴다. 사람이 넣은 호재는 판정과 무관하게 보존(판정 결과는 병기).
- D11-3 **강등(검증 모순)은 읽기 시점 오버레이**: 사실 값을 읽는 단일 함수(`app/facts_view.py`)가 API·파이프라인·보고서·CSV 모두에서 강등을 적용한다(창(window) 없음). 강등은 (entity, entity_id, field, 모순 값의 value_norm)로 기록되고, chosen 값이 그 모순 값과 같은 동안 유지된다. 해제: (a) 사람 확인 — `human_check`는 resolver 우선순위 **0순위 후보**로 들어가 재정규화에도 유지되고, (b) 새 출처가 **다른 값**을 낼 때만. 같은 값 재수집·값 없는 행은 해제하지 않는다. 가격 강등은 점수·화면이 실제로 쓰는 필드(`payment_terms.price_by_type` 현재 공고)에 걸고, P9 주장도 그 필드를 대상으로 만든다.
- D11-4 잔여·임의·무순위 공고를 원 단지에 묶을 때 그 공고의 단지 단위 필드(이름·당첨일·세대수·일정 등)는 원 단지 값을 덮어쓰지 않는다 — `remaining_event`·`payment_terms`·`competition`에만 기록. 차수 표기는 어떤 괄호 안에 있어도 이름 키에서 지우지 않는다.
- D11-5 `catalyst_link`는 사람이 위치를 확인할 때 만든다(`PATCH /catalysts/{id}`: location_confirmed, lat/lon 또는 영향 생활권·단지). 단지 좌표가 없으면 distance_m=null, weight=1(같은 생활권), 라벨 추정. location_confirmed=false면 링크 없음(RA).
- D11-6 할인: 공고문·청약홈에 명시된 할인만 `payment_terms.discount_won`(타입별)으로 저장, 라벨 확인됨일 때만 §6-1 차감.
- D11-7 지역 선택 확장(`PATCH /regions/{id}` selections 추가·제거) = RA "지역 추가": 새 리비전에서 후보 전체 rerank 1회 + 보고서 §12 "지역 추가" 장(이전 리비전과 비교).
- D11-8 백업: worker가 매일 03:00 `backup` 잡(Postgres면 pg_dump, rawdata는 증분 복사)을 실행하고 결과를 job_run에 남긴다. SQLite 개발 모드에서는 파일 복사.
- D11-9 prod에서 SQLite DATABASE_URL 거부. 차트 스크린샷 linux 기준 이미지는 Docker/WSL 설치 후 생성(현재 둘 다 없음 — 사람 할 일과 함께 기록).
- D11-10 (2026-10-10) RA "지역 추가 → 통합 순위 재산출"은 D2 구조에서 지역 확장(`PATCH /regions/{id}` → `region.expand` → 새 리비전에서 확장된 지역의 후보 전체 rerank·점수)으로 충족한다. 지역(region)끼리는 독립 분석이며 지역 간 합산 순위는 만들지 않는다(여러 시군구를 보려면 한 지역에 함께 선택).
- D11-11 호재 좌표·예상 시기(`lat`·`lon`·`expected_ym`)는 사람 입력(`PATCH /catalysts`)으로만 채운다 — 뉴스 자동 추출은 추정이 섞여 쓰지 않는다.

## D12. R3 4차 리뷰 후속 결정 (2026-10-10, CEO) — 원문 `R3_REVIEW4.md`
- D12-1 사람 확인은 그 시점까지 관측된 출처보다 우선한다. 사람 확인 **이후에 관측된**(observed_on > checked_at) 공식 1차 출처(공고문·청약홈)가 **다른 값**을 내면 그 새 값이 채택되고, critical change_event + 체크리스트 "사람 확인 재검토"가 생긴다. compare 채택은 사람 확인을 이기지 못한다.
- D12-2 강등은 행 id가 아니라 **(단지, 의미 필드, 모순 값)**에 걸린다: 같은 단지의 같은 의미 필드(예: 기준 타입 공급금액·계약금%)에 같은 모순 값이 다른 공고 행으로 들어와도 강등이 유지된다.
- D12-3 할인 차감 규칙(확인됨만)은 가격을 쓰는 **모든 경로**(상세·목록 필터·정렬·비교·자금 요건·보고서·점수)에서 같은 공용 함수(`price_view.current_price`)로만 계산한다.
- D12-4 발행 리비전에서 보이는 사실 중 판정 범위·생활권·호재 단계/연결처럼 리비전마다 달라질 수 있는 값은 **리비전 시점 값을 저장**(스냅샷 범위 테이블)해 옛 리비전이 나중에 바뀌지 않게 한다. "최신 리비전"은 published만.
- D12-5 사람 확인·생활권 편집·지역 확장 뒤 재판정은 **자동 등록**(제안만이 아님); carry_forward는 그 기준일 이후 사실 변경이 있으면 복사하지 않고 재판정한다.
- D12-6 백업은 worker 이미지에 postgres 클라이언트(pg_dump)를 포함하고 백업 위치는 별도 볼륨(`backups`).

## D13. R3 5차 리뷰 후속 결정 (2026-10-10, CEO) — 원문 `R3_REVIEW5.md`
- D13-1 **발행 리비전 = 저장된 읽기 모델(materialized)**. 리비전을 published로 바꾸는 트랜잭션에서 그 리비전의 화면 응답 전부(대시보드·단지 목록·단지 상세·비교 입력·시장·변경 목록·민감도·CSV 행)와 보고서 입력 데이터를 시나리오별로 JSON으로 저장(`snapshot_view` 테이블: snapshot_id, kind, key, scenario, body, sha256)한다. 발행된 리비전의 GET은 **항상 저장본**을 돌려준다(현재 사실·오버레이 재계산 없음). building/ready 리비전만 실시간 계산. 보고서도 저장본으로 렌더. 0009 이전 발행분은 마이그레이션에서 한 번 materialize. 이로써 값별 동결(`snapshot_state`)은 저장본 생성 시점 계산으로 대체된다.
- D13-2 **사람 확인은 (단지, 의미 필드) 단위**(강등과 같은 키, D12-2). 사람 확인 이전 관측(observed_on ≤ checked_at) 출처는 행과 무관하게 모두 사람 확인 값에 진다. 이후 관측된 공식 1차 출처가 다른 값이면 채택 + critical + "사람 확인 재검토"(D12-1)를 행과 무관하게 적용. 이미 수집된 공고보다 이른 checked_at 사람 확인은 422로 거절(조용한 패배 금지).
- D13-3 잡 큐 갱신은 원자적: queued 잡 payload 병합은 `UPDATE … WHERE status='queued'`로 하고, 실패하면 새 잡을 만든다.
- D13-4 변경 없는 주간 수집은 새 리비전을 만들지 않는다(직전 발행 리비전 유지). 이월은 이전 리비전 이후 모든 change_event(자기 리비전 것 포함, 지역 단위 포함)와 실패한 rejudge를 검사해 하나라도 있으면 이월하지 않고 재판정한다.
- D13-5 모든 change_event는 쓰기 가능한 리비전(`writable()`)에만 붙는다 — 예외 없음(재강등·지역 확장 포함). 테스트로 전 경로 고정.

## D14. R3 6차 리뷰 후속 결정 (2026-10-10, CEO) — 원문 `R3_REVIEW6.md`, 배정 `R3F_FIX.md`
- D14-1 D13-1 "화면 응답 전부"에 **출처 서랍과 주장 목록을 포함**한다. 발행 리비전의 `GET /provenance/{id}`·claims 목록은 저장본에서 읽는다. 출처 조회는 스냅샷을 지정받고(계약 .11 `snapshot_id`), 지정이 없으면 그 단지 지역의 최신 published 리비전이다. building/ready 리비전만 실시간이다.
- D14-2 할인 '확인됨'은 **줄 전체**(금액 앞뒤·괄호·각주)에 조건이 없을 때만이다. 조건 예: 층·동·호·라인·특정 타입 외, "~시", 한정, 최대, 조건, 선착순, 특별공급, 잔금·완납, 기간·까지, ※·단. "할인 없음/미적용"이 붙은 줄은 할인 사실을 만들지 않는다. 취득세·중도금 이자·발코니·옵션 지원은 할인이 아니다. 그 밖은 '추정'(표시만, 차감 없음)이다.
- D14-3 사용자 시나리오 보고서: 대상 리비전에 그 시나리오 저장본이 없으면 POST 단계에서 422(`scenario_not_in_revision`)로 거절한다. 비교 기준 리비전에 그 시나리오가 없으면 delta 표는 "비교 기준에 이 시나리오 없음"으로 생략하고 보고서는 성공한다. §12 건수 비교는 시나리오와 무관하게 낸다. 시나리오 식별은 id로 한다(code는 NULL일 수 있음).
- D14-4 저장본 행은 `contract_version`과 `sha256`을 갖고 **읽을 때 검증**한다. 불일치면 500 `stored_view_mismatch`로 거절하고 로그를 남긴다(조용히 내보내지 않음). 저장 kind의 모양을 바꾸는 계약 변경은 저장본 변환 마이그레이션을 함께 낸다.
- D14-5 저장본 생성(materialize)은 **worker 잡**(`snapshot.publish`)에서만 한다. API 요청 안에서 발행하지 않는다. 발행이 필요한 쓰기 API는 잡을 등록하고 202와 job_id를 돌려준다. 행은 나눠 쓰고, published 전환은 짧은 한 트랜잭션으로 한다. 끝날 때까지 이전 published가 기본이다. 기준: 1000단지 × 시나리오 5에서 잡 30초(한 프로세스) 이하, 그동안 API 쓰기 잠금 1초 이하. (사람 확인 POST는 행 생성이므로 201 + job_id)
- D14-6 사람 확인 `checked_at`은 시간대가 붙은 RFC3339여야 한다(계약 .11 `format: date-time`). 지금보다 10분 넘게 미래면 422다. 날짜 비교는 한 공용 함수로 KST 날짜 기준이다. 나중 공고 값이 사람 확인 값과 **같으면** 정상 수용이다(422·재검토 없음). 같은 의미 키를 다시 사람 확인하면 열린 '사람 확인 재검토'를 닫는다. 이른 확인일 422(D13-2)는 이미 수집된 출처 값이 **다를 때만**이다.
- D14-7 이월·재판정 판단은 **단지 단위**다. 단지별 마지막 성공 판정 이후 그 단지(또는 지역 단위) change_event가 있거나, 그 단지를 포함한 rejudge가 실패했으면 이월하지 않고 재판정한다.
- D14-8 출처 누락(T13): 실시간 경로(building/ready)는 dev 500, prod '확인 불가(출처 누락)' + 경고로 RA를 유지한다. 발행 저장본은 모든 환경에서 라벨로 저장하고 materialize 잡 통계에 누락 건수를 남긴다(발행 뒤 500 불가).
- D14-9 마이그레이션은 앱 코드를 import하지 않는다. 0010은 테이블만 만든다. 기존 발행분 저장본 채우기는 멱등 단계로 옮긴다: worker 시작 + `python -m app.snapshot_view backfill`. 저장본이 아직 없는 published GET은 503 `materialize_pending`이다. devseed reset은 SQLite 파일 삭제 또는 반사(reflect) 기반 전체 삭제 후 alembic을 head로 다시 찍는다.

## D15. R3 7차 리뷰 후속 결정 (2026-10-11, CEO) — 원문 `R3_REVIEW7.md`, 배정 `R3G_FIX.md`
- D15-1 할인 '확인됨'은 **허용 목록**만이다(D14-2 대체). 한 줄 전체가 `{타입} {분양가|공급금액} 할인 {금액}원` 꼴이고 꼬리글·괄호·범위·"예정"이 없으며, 다음 줄이 괄호·※·*·"단"·조건 낱말로 시작하지 않을 때만 '확인됨'이다. 금액 0원·할인 아닌 금액(경품·지원 등)은 할인 사실이 아니다. 그 밖은 전부 '추정'(표시만)이다. 파싱 규칙이며 판단 대체가 아니다.
- D15-2 출처 저장본은 저장된 **모든 본문**(모든 시나리오·모든 kind·patch 행 `{"$v":…}` 포함)의 prov id와 접수 근거 `rd_`를 모은다. FE는 `rd_` 예외 없이 언제나 snapshot_id를 넘긴다. 불변 테스트도 모든 시나리오 응답에서 id를 모은다.
- D15-3 저장본 완결성은 (리비전, 시나리오, kind) 단위 **완료 표식**으로 판단한다. 표식은 그 단위의 마지막 쓰기와 같은 트랜잭션에 쓴다. 표식 없는 단위는 미완(503 + `pending_count`에 셈)이고 backfill이 그 단위를 다시 만든다. backfill은 리비전마다 따로 실패한다. 저장본 호환은 계약 문자열이 아니라 **저장 모양 버전**(정수, 모양이 바뀔 때만 올림)으로 비교한다.
- D15-4 이월 판단의 "판정됨"은 **복사 원본(prev) 리비전에 들어 있는 점수 실행**만 센다. 다른(미발행) 리비전의 rejudge 성공은 세지 않는다. 시나리오를 지정한 rejudge는 그 시나리오만 판정된 것으로 센다.
- D15-5 사용자 시나리오 보고서 §12의 순위표·TOP 5는 **같은 시나리오끼리만** 비교한다. 비교 기준에 그 시나리오가 없으면 12-1은 사유와 함께 생략한다(D14-3과 같은 규칙).
- D15-6 발행은 리비전마다 하나만 돈다(single-flight: DB 잠금 또는 유일 키). 정리 DELETE는 상태 조건을 붙인다. 발행 계산 중에 들어온 변경은 **후속 발행 잡**으로 이어 붙인다. 발행을 일으키는 쓰기 응답은 늘 job_id를 준다. 모든 발행 경로(expand·daily 이월·주간 마감·bootstrap)는 실패하면 재시도 잡을 남긴다.
- D15-7 시각 파싱은 `core.time` 하나로 한다. `T`·`Z`는 대소문자를 가리지 않는다. 연도는 2000년부터 지금 + 10분까지 허용하고, 범위 밖·overflow는 422다. 화면·보고서의 날짜 표시는 모두 KST다.
- D15-8 FE: 503 `materialize_pending` 동안 **다른 리비전·시나리오의 이전 값을 보이지 않는다**(placeholder는 같은 리비전·시나리오 키일 때만). G5 '이후' 열과 열린 서랍은 그 Fact가 나온 리비전의 snapshot_id로 조회한다. 진행 안내는 후속 `snapshot.publish` 잡이 끝날 때 닫는다. `publish_blocked`와 30분 상한 도달은 안내한다.

## D16. R3 8차 리뷰 후속 결정 (2026-10-11, CEO) — 원문 `R3_REVIEW8.md`, 배정 `R3H_FIX.md`
- D16-1 **자동 파싱으로 얻은 할인은 언제나 '추정'이다**(D14-2·D15-1 대체). 공고문 파서는 할인 후보를 찾아 표시하지만 '확인됨'을 만들지 않는다. 할인이 구매가에서 빠지는 것(D11-6·D12-3)은 **사람 확인으로 '확인됨'이 된 할인**(D13-2 의미 단위, 필드 `discount`)이나 공식 구조화 출처(청약홈 API 등 할인 필드가 있을 때)뿐이다. 이유: 조건 문구는 앞뒤 줄·떨어진 각주·표 머리에 흩어져 있어 줄 단위 규칙으로 '조건 없음'을 증명할 수 없다(7·8차 누출). 녹화 공고 59건에 할인 줄이 0건이라 실데이터 영향은 없다. 화면은 '추정' 할인 옆에 "공고문에서 찾은 할인(조건 확인 필요) — 사람 확인 시 구매가에 반영" 안내와 G7 사람 확인 링크를 둔다.
- D16-2 0012 이전에 만든 저장본 단위는 마이그레이션에서 **전부 미완(pending)으로 표시**한다(행 수 추정 금지). backfill은 빠진 키만 채우고 이미 있는 행의 바이트는 그대로 두며, provenance 단위는 D15-2 범위로 빠진 id를 채운다. 행이 있는데 표식이 없는 단위도 미완이다. runbook에 업그레이드 뒤 backfill 절차를 적는다.
- D16-3 발행 임대가 바쁘면(busy) 후속 잡은 실패가 아니라 **지연 재큐잉**(짧은 backoff, 상한 있음)한다. 그 자리 발행(daily·expand 등)도 잡 id를 holder로 쓴다. 포함되어 닫힌 후속 잡에는 포함한 발행 잡의 `publish_job_id`를 기록한다. 정리 DELETE는 임대 보유자 조건을 붙인다.
- D16-4 발행 리비전 응답에 보이는 값을 바꾸는 쓰기(호재 예정월·좌표·연결 등 모든 PATCH)는 늘 발행 잡을 남기고 job_id를 돌려준다. 바뀐 것이 없으면 job_id null과 200이다.
- D16-5 사용자 입력 시각(checked_at 등)은 API가 원문을 그대로 돌려주되 화면·보고서의 날짜 표시는 모두 KST로 변환한다(D15-7 확인).

## D17. R3 9차 리뷰 후속 결정 (2026-10-12, CEO) — 원문 `R3_REVIEW9.md`, 배정 `R3I_FIX.md`. **R3 게이트(critical 0) 통과.**
- D17-1 backfill은 발행과 **같은 임대**를 잡는다. 저장본 단위 재작성은 "새 행 쓰기 → 옛 행 교체 → 표식"을 한 트랜잭션(또는 옛 행을 지우지 않고 빠진 키만 추가)으로 하여, 중단·겹침 어느 시점에서도 이미 저장된 본문(서랍 포함)이 지워지거나 현재 사실로 다시 계산되지 않는다.
- D17-2 backfill이 **새로 계산해 채운** 키는 저장 단위에 `backfilled_at`을 남기고, 그 리비전 응답 메타에 "업그레이드 때 다시 계산한 값 포함" 표지를 둔다(FE 안내). 목록 본문도 키와 같은 범위 제한(리비전 단지 목록)을 따른다. CHANGELOG S4·runbook을 구현과 일치시킨다.
- D17-3 이월 발행(`snapshot.publish` carry 포함) 실패는 재시도 잡을 남기고(D15-6), `building`→`ready` 전환은 재실행해도 끝까지 가는 멱등 단계다. building에 멈춘 리비전으로 미뤄진(`deferred_to`) 쓰기는 그 리비전이 실패로 끝나면 새 발행 잡으로 다시 등록된다.
- D17-4 사람 확인은 **의미 단위로 유지**된다: 새 공고에 그 의미 필드 값이 **없으면** 사람 확인 값을 그대로 적용한다(값 없음 ≠ 다른 값). 새 공고가 **다른 값**을 내면 D12-1(채택 + critical + 재검토). 할인 사람 확인은 기준 타입 기준이며 폼과 안내에 기준 타입을 표시한다.
- D17-5 D16-4 범위: 발행 저장 본문(report 포함)에 들어가는 값을 바꾸는 쓰기(체크리스트·지역 이름 포함)는 발행 잡을 남긴다.
- D17-6 SQLite 개발 모드의 D14-5 측정 테스트는 전체 스위트와 같은 프로세스 부하에서도 기준(30s·1s)을 지켜야 한다. 묶음 사이 잠금을 API가 끼어들 수 있게 양보한다.

## D18. R4 실데이터 시험 후속 결정 (2026-10-12, CEO) — 원문 `R4_RESULT.md`, 배정 `R4_FIX.md`. **R4 게이트 미통과** → 수정 후 재실행.
- D18-1 (C1, D6 보강 수정) 캐시 키의 adapter_version = `<코드>+jev-mcp@<서버 버전>+<고정 모델>`. 고정 모델은 **모델을 실제로 부른 응답**(provider ≠ none)이 알려 준 모델이며, provider none(로컬 처리) 응답의 `model`은 무시한다. 고정 모델이 바뀌면 그 **실행 중에는 키를 바꾸지 않고**, change_event(judge·version·critical)를 남겨 다음 실행부터 새 키로 전체 재판정한다(실행 중 replay 금지). 응답마다 실제 `model`·`provider`는 judgment_log 행에 따로 기록한다.
- D18-2 (C1) **실제 호출 수는 MCP `tools/call` 단위로 어댑터 전송 계층에서 센다**. 잡 stats `judge_calls`·G7 `real_calls`·runbook 집계는 이 수를 쓰고, 캐시 적중은 `tools/call`이 0이어야 한다. 수집 단계 판정(호재 screen 등)도 잡 집계에 포함(m2).
- D18-3 (C2) 실거래 API 응답에 `umdCd`가 없으면 `sggCd + umdNm`을 참조 표(legal_dong)로 매칭해 법정동 코드를 만든다. 매칭 실패·모호는 NULL + 사유로 남기고 비율을 수집 stats에 기록한다. 녹화 픽스처에 실제 응답 모양(umdCd 없음)을 추가한다.
- D18-4 (C3·M1·M3) **잔여·임의·무순위·재공급 공고는 원 단지(사업)의 사건**이다. 별도 단지 행을 만들지 않고 최초 주택관리번호(또는 D10-4 블록 병합)로 원 단지에 `remaining_event`로 붙는다. 공고 제목·본문 줄은 단지 이름 후보가 되지 않는다(D11-4). 원 단지 행이 그 공고로만 생겼으면 원 공고를 주택관리번호로 공식 API에서 다시 가져와 채우고, 그래도 없으면 범위 사유는 '원 공고 미수집'이다('분양가 미공개'가 아님). 원 단지의 접수 상태는 열린 잔여 사건으로 갱신된다.
- D18-5 (호출 수) RA §9의 132는 기준값이며 "넘으면 이유 기록"을 따른다. 공고문 조각 단위 screen·extract는 유지하되 같은 조각(같은 정규화 본문)은 한 번만 판정한다. R4 재실행 게이트: 2회차 `tools/call` 0(엄격), 1회차는 도구별 수와 132 대비 이유 기록.
- D18-6 (M5) bootstrap은 지역의 모든 수집 단계(잔여 공고 상세·공식 홈페이지·접수 상태 포함)를 끝낸 뒤 판정한다. 같은 날 변화 없는 `collect.daily`는 새 판정 0이어야 한다(T8 실데이터).
- D18-7 (M2·M4·M6·m1·m3·m4) 미분양 사실은 출처 행을 갖는다. alembic은 `ENV_FILE`을 존중한다. 주소 → 법정동 매칭은 신설 구(예 검단구) 주소 표기와 참조 표의 구 표기 차이를 흡수한다. 지역 첫 적재(bootstrap)의 null→값 변경은 change_event 대신 '첫 적재' 한 줄로 요약한다. 보고서 ECharts 경로는 runbook에 명시한다.
- D18-8 (수집 범위) 회귀 픽스처에 있으나 실제 수집에 빠진 단지(오퍼스 한강 스위첸, 해링턴플레이스 풍무 1BL, 계양 카이브 유보라, 검단 센트레빌 그랑포레)의 누락 원인을 찾아 고친다(공고일 범위·지역 선택·API 페이지 등). 고칠 수 없는 원인이면 사유를 기록한다.
- D18-9 (m5) 사람이 2026-10-12 data.go.kr '국토교통부_아파트 분양권전매 실거래가 자료' 활용신청 완료(같은 `DATA_GO_KR_KEY`). R4 재시험에서 `RTMSDataSvcSilvTrade` 200·`is_presale` 적재를 확인한다(승인 반영까지 시간이 걸릴 수 있음 — 403이면 실패 행으로 남고 재시험 기록에 적는다).

## D19. 로컬 운영 DB (2026-10-12, 사람 답 + CEO)
- D19-1 Docker는 설치하지 않는다(사람 답). 운영·R4는 이 PC에 이미 설치된 PostgreSQL을 쓴다. PG16(5432)은 다른 앱이 쓰고 관리자 비밀번호를 알 수 없어 건드리지 않고, **PostgreSQL 17.9(포트 5434, 다른 앱 DB 없음)**에 전용 역할 `sa`와 DB `subscription_analyzer`(운영)·`subscription_analyzer_r4`(R4 재시험)를 만들었다. 접속 주소는 루트 `.env`의 `DATABASE_URL`·`R4_DATABASE_URL`(비밀번호는 무작위 생성, 커밋·출력 금지). 운영 DB는 alembic head(0013)까지 올렸다.
- D19-2 compose 기동·Docker 이미지 빌드·리눅스 차트 기준 이미지는 '미검증'으로 남긴다(사람이 Docker 설치를 원할 때 진행). 로컬 백업은 PG17 `pg_dump`(`C:\Program Files\PostgreSQL\17\bin`)를 쓴다 — compose의 `postgresql-client-16`은 16 서버 전용이다.

## D20. R4-FIX 후속 결정 (2026-10-12, CEO)
- D20-1 계약 .15는 R4-FIX가 낸다(이번 라운드 계약 소유 위임): `contracts/migrations/env.py`는 `DATABASE_URL`이 없으면 앱 설정(`ENV_FILE`)의 URL을 쓴다; 청약홈 기본 조회 창을 **지난 24개월 + 향후 12개월**로(meta §1-4 "지난 24~36개월 + 향후 12개월"); `POST /regions`에 선택 필드 `applyhome_query`(from_ym·to_ym); `judgment_log`에 `model`·`provider` 열; 픽스처 재녹화 사유를 CHANGELOG에.
- D20-2 **트랙 (A)의 "12개월 내 공고 예정" 단지**(meta §1-3 #1)를 수집한다: 뉴스·공식 홈페이지 신호를 판정기 screen(공고 예정 신호)·classify(지역·민간분양 여부)로 걸러 단지 후보를 만들고, 라벨 '비공식'/'추정', 범위 사유 "보류 — 공고 후 재판정"(meta §1-3 #4), 청약홈 공고가 나오면 같은 단지로 합친다(이름 키·주소). 공고 예정 목록은 P8 `wait_new` 근거와 보고서 §8-2에 쓰인다. 이미 일부 구현돼 있으면 빠진 연결만 채운다. 판단은 판정기만(규칙 3).
- D20-3 R4 DB에 이미 생긴 잔여 공고 단지 행 병합 마이그레이션은 만들지 않는다 — 운영 DB(D19)는 비어 있고 R4 재시험은 새 DB로 한다.
- D19-3 (2026-10-12) 사람이 판정기 키를 루트 `.env`에 넣었다. JEV 0.14.1이 읽는 이름은 `TYPESAFE_API_KEY`·`OPENROUTER_API_KEY`·`JEV_API_KEY`(+`JEV_API_BASE_URL`)·Cloudflare·AI Gateway이고, 넣은 값은 사용자 환경변수 `TYPESAFE_API_KEY`와 같아 `.env`의 이름을 `JEV_SECRET_KEY` → `TYPESAFE_API_KEY`로 바꿨다. 지금 어댑터(`judge/jev_mcp.subprocess_env`)는 **프로세스 환경변수만** 자식에게 넘기므로 `.env` 값은 판정기에 가지 않는다 — 다음 백엔드 라운드에서 `.env`(설정)의 판정기 자격 증명 이름(`JUDGE_SECRET_ENV_NAMES`)도 자식 env로 넘기게 고친다(프로그램이 사용자 환경변수에 기대지 않게).
