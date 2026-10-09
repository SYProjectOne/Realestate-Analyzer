# 설계 결정 v1.1 — RA_v1 대비 변경분 (2026-10-09, CEO 오케스트레이터)

원본 설계도는 `docs/source/RA_v1.md`(이하 RA)이다. 이 문서는 §11 미결 사항에 대한 사람(라홈)의 답과, 그 답 때문에 바뀐 계약·WP 카드만 적는다. RA와 이 문서가 충돌하면 **이 문서가 이긴다**. RA가 말하지 않는 화면·운영 규칙은 `docs/source/meta_prompt.md` §2-6~§2-9를 따른다.

계약 버전: `2026-10-09.8`

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
