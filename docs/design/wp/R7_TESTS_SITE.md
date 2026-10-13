# R7-SITE — 팝업 그림 OCR·판정 대상 아닌 단지 제외·TLS 사이트 브라우저 경로 (D26-1·D26-3·D26-4, 2026-10-13)

브랜치 `wp/r7-site`(main `36894df` — `Merge wp/r6-intake` 포함). 계약 `.18` 그대로(계약·마이그레이션·새 라이브러리 없음 — OCR 은
D5 선택 의존성 `ocr` 의 RapidOCR, 브라우저는 기존 Playwright). 판정 규칙(클래스·임계값·review 처리·D21-5/D22-4 사유)은 바꾸지
않았다 — 판정기에 들어가는 **입력**(팝업 그림 글자), **누구를 보내는가**(판정 대상 아닌 단지 제외), **원문을 받는 경로**(TLS)만.

## 1. 원인 (R6_TESTS_INTAKE §1 의 남은 몫)

| 구분 | 인천 스냅샷 1 | 원인 |
| --- | ---: | --- |
| 문구로 판단 불가 | 29(R6 재생 33) | 접수 안내가 **팝업 그림** 안 — DOM 텍스트에 없다. 렌더 메타에 팝업이 잡힌 행 다수(1280×900 오버레이·이미지 1~10장) |
| 수집 실패 TLS | 9 | robots.txt 요청부터 TLS 실패 → RFC 9309 '전부 불허' → 본문 요청 안 함. hillstate.co.kr 5행(서버 서명 방식을 OpenSSL 이 거부)·중간 인증서 누락 1·자체 서명 1·만료 1·호스트 불일치 1 |
| 범위 경계·공공분양 단지의 접수 행 | 15 | 점수 대상이 아닌데 동일성·접수 classify 로 판정기를 부르고 '확인 불가(…)'로 사람 확인 대상처럼 보였다(LH 청약 포털 5 등). 포함/제외 classify 가 접수 classify **뒤**에 돌아 첫 실행에는 공공분양을 알 수 없었다 |

## 2. 고친 것

| 파일 | 내용 |
| --- | --- |
| `collectors/official_site/render.py` | `PopupShot.png`(요소 스크린샷 바이트 — 메타·서명·비교 밖), `RenderResult.html`(`page.content()`), `BrowserFetch`·`PlaywrightRenderer.fetch(url)`(robots.txt 를 브라우저로 — 렌더와 같은 내부망·포트·출구 프록시 검사), 새 페이지 문맥은 `ignore_https_errors=False` 를 명시(검증 끄지 않음), `is_tls_error` |
| `collectors/official_site/collector.py` | **D26-1** 팝업 그림 OCR → 스크린샷 행 meta `{kind:'official_site.popup_ocr', label:'추정(OCR)', engine, status, reason, items[{popup_sha256, signature, dhash, selector, image_path, text_path, text_sha256, chars, checked_at, seconds, status, error}]}`(그림 원본·글자는 원문 저장소 sha256 경로). 캐시: 같은 화면(스크린샷 행 재사용)이면 다시 읽지 않음, 새 스크린샷 행이면 같은 URL 이전 OCR 중 그림 sha256 같은 것(또는 서명 같고 dHash 거리 ≤ 10) 재사용. 페이지 예산 30초(D5), 엔진 없음 → `status='unavailable'` + 사유, 엔진 오류 → 항목 `error`(실패도 데이터). **D26-4** httpx 가 TLS 로 실패하면 `_via_browser`: (robots.txt 가 TLS 였으면) 브라우저로 robots.txt → `robots_verdict`(RFC 9309: 2xx 규칙·4xx 제한 없음·5xx·실패 전부 불허) → 허용이면 브라우저 렌더(본문 HTML 행 + 스크린샷 행). 브라우저도 TLS 면 실패 행 'TLS' 그대로, 403 등은 저장 안 함(D25-4). 경로는 meta `fetch{path:'browser', reason:'TLS', failed, robots{status,error}, page{status,error}, result}`(실패 행도). 브라우저 요청 전 `core.http` 호스트별 속도 제한 예약(`_pace`) — 같은 원점 robots.txt 는 실행당 한 번 |
| `collectors/notice_pdf/ocr.py` | `ocr_png`(그림 바이트 → 줄 텍스트), `load_image_ocr()`(엔진 없으면 None) — 기존 엔진·줄 묶기 재사용 |
| `scheduler/intake.py` | **D26-1** `ocr_text`·`intake_body`: 페이지(DOM)에 접수 문구 후보가 **없을 때만** `[팝업 그림 글자 — 추정(OCR)]` 아래 OCR 글자(OCR 후보 문맥, 없으면 페이지 문구 + OCR 글자, OCR 부분 ≤ 800자). 페이지에 후보가 있으면 R6 입력 그대로(§4 재생 근거). **D26-3** `not_target_reason`·`mark_not_target`(분류 복사 앞에서): 범위 경계 또는 포함/제외 auto 제외 클래스 단지의 미분류·수집 실패 접수 행 → '확인 불가' + 사유 `판정 대상 아님(범위 경계｜공공분양｜공공임대｜민간임대｜비아파트｜범위 밖)`. 다시 대상이 되면 수집 때 사유(미분류·실패 원인)로 되돌린다 |
| `scheduler/pipeline.py` | 포함/제외 classify(`_p4`)를 접수 classify(`_p4_intake`) **앞으로** — 첫 실행에도 공공분양이 접수 판정에서 빠진다(`_p4` 는 대상 집합을 쓰지 않아 순서 무관). 접수 분류 표식에 OCR 근거면 `판정기 classify jl_<seq>(근거에 팝업 그림 글자 추정(OCR))` |

판단 경계(규칙 3): 프로그램은 OCR 글자를 해석하지 않는다(접수 분류는 판정기). '판정 대상 아님'은 complex 행의 값(판정기 포함/제외
classify 결과·D2-6 주소 매칭)을 옮긴 것이고 `analysis.scope.judge_scope` 의 '제외' 조건과 같다(미해결은 빼지 않는다). robots 해석은
`core.http` 와 같은 RFC 9309 규칙이다.

### 결정성·캐시(D10-2·D22-2)

- OCR 글자는 그림 해시로 캐시한다 — 같은 화면이면 스크린샷 행 meta 를 그대로 쓰므로 접수 항목 텍스트가 같다 → 분류 복사(호출 0).
- 페이지에 후보가 있거나 팝업 OCR 이 없는 행의 접수 항목은 R6 와 **바이트까지 같다**(input_hash 그대로). OCR 이 붙는 행만 배포 뒤
  첫 수집에서 입력이 바뀌어 `_same_input` 이 복사를 막고 판정기로 간다(1회).
- 녹화(`contracts/fixtures`)·회귀 골든: 동일성·접수 classify 녹화가 없고, 픽스처 지역 단지는 렌더 팝업 그림이 없어(가짜 렌더러)
  바뀐 것 없음.

## 3. 테스트 (먼저 쓰고 main `36894df` 코드에서 실패 확인)

`backend/tests/scheduler/test_r7_site.py`, `backend/tests/collectors/official_site/test_r7_site_collector.py`.
수정 전 실행: main 을 임시 worktree 로 꺼내 새 테스트 파일만 복사해 돌렸다. 새 API(`ocr=`·`PopupShot.png`)를 쓰지 않게 고친
사본으로 동작만 비교한 결과도 적는다.

| 테스트 | 결함 | 수정 전(main) |
| --- | --- | --- |
| `scheduler…::test_intake_item_carries_popup_ocr_text_with_label` | 접수 항목에 팝업 그림 글자 없음(문구로 판단 불가) | **실패** — 항목 = 단지 이름 + 메뉴 문구, OCR 블록 없음 |
| `…::test_unchanged_popup_is_not_reocred_and_not_rejudged_next_day` | 같은 그림 재OCR·재판정 | **실패**(OCR 0회 — 기능 없음) |
| `…::test_page_intake_phrases_keep_r6_input_without_ocr` | DOM 후보가 있으면 R6 입력 유지 | 통과 대상(회귀 방지; main 은 `ocr=` 인자 없음으로 수집 오류) |
| `…::test_boundary_complex_skips_identity_and_intake_classify` | 범위 경계 단지 동일성·접수 classify | **실패** — 동일성 항목 `site:c4:headless_shot` 이 판정기로 감 |
| `…::test_public_sale_complex_skips_classify_from_first_run` | 첫 실행 공공분양(포함/제외가 접수 뒤) | **실패** — 동일성 항목이 판정기로 감 |
| `…::test_private_complex_still_classified` | 민간 단지는 그대로 | 통과(회귀 방지) |
| `…::test_not_target_row_returns_to_unclassified_when_complex_becomes_target`·`…::test_failed_fetch_row_of_not_target_complex_says_not_target` | 대상 복귀·수집 실패 행 | 수집 오류(`mark_not_target` 없음) |
| `collectors…::test_popup_ocr_saved_on_screenshot_row_with_label_and_provenance`·`test_same_popup_image_is_not_read_again`·`test_changed_popup_image_is_read_again`·`test_without_engine_reason_is_recorded`·`test_ocr_time_budget_skips_remaining_popups`·`test_engine_error_is_data`·`test_load_image_ocr_is_none_without_engine`·`test_real_engine_reads_popup_image_text` | 팝업 그림 OCR 없음 | 수집 오류(`OCR_META_KIND`·`popup_ocr_texts` 없음) |
| `…::test_tls_failure_retries_robots_and_page_with_browser`·`test_tls_browser_robots_disallow_is_obeyed`·`test_tls_browser_robots_outcomes[×3]`·`test_tls_browser_page_denied_is_not_saved`·`test_tls_page_with_robots_ok_renders_directly`·`test_tls_render_never_keeps_failure`·`test_tls_browser_robots_fetched_once_per_origin`·`test_browser_requests_use_core_http_rate_limit`·`test_robots_verdict_follows_rfc9309[×6]`·`test_tls_error_markers` | TLS 면 본문을 받지 않음 | 수집 오류(`robots_verdict`·`BrowserFetch` 없음). main 동작 = 실패 행 'TLS', 렌더 호출 0(기존 `test_official_site.py::test_network_failures_leave_error_text_rows[TLS]` 가 고정) |
| `…::test_browser_fetch_keeps_certificate_validation_on` | 브라우저 문맥 검증 끄지 않음(`ignore_https_errors=False`) | 수집 오류 |
| `…::test_real_chromium_rejects_self_signed_certificate` | 실제 chromium 자체 서명 → TLS 실패(우회 없음) | 수집 오류 |

고정 그림: `tests/collectors/official_site/fixtures/r7_popup_soldout.png` — 인천 첫 실행 호반써밋Ⅲ 공개 분양 페이지 팝업의 오른쪽
1/3('100% 분양완료' 는 그림 안에만 있다). 가짜 판정기·가짜 OCR 은 응답 모양만 흉내 낸다(판단 아님).

## 4. 실제 재생 (운영 DB 읽기 전용 + 버리는 SQLite, 실제 판정기 tools/call 3)

방법: 운영 DB 를 `load_settings(<루트 .env>)` + `SET TRANSACTION READ ONLY` 로 읽어(SELECT 만) 지역·단지 101·스냅샷 1 접수 행 96·
공식 홈페이지 원문 행 129(+파일 214)를 버리는 SQLite(`c:/tmp/r7r`)로 옮겼다. 영향 행만 오늘(2026-10-13) **실제로 다시 수집**했다 —
TLS 9행 + 렌더 메타에 팝업이 있던 행 29 = 38 대상(공개 페이지, `core.http` 속도 제한·robots 준수). 나머지는 운영 원문 그대로.
새 코드의 `_p4_intake`(분류 복사·판정 대상 아님·동일성·접수 classify)를 실제 JEV(루트 `.env` 자격 증명 — 출력 없음)와 버리는 캐시로
돌렸다. 운영 DB·운영 캐시·운영 원문 디렉터리에는 아무것도 쓰지 않았다. 판정기 payload 원문은 출력·저장하지 않았다(규칙 13).

호출: 동일성 1배치(64항목) + 접수 1배치(46항목) = 2, DOM 후보 규칙 수정 뒤 접수 1배치 다시 = 1(동일성은 캐시) → **3**.
같은 스냅샷 다시 판정 0, 다음 날 스냅샷(같은 원문) 0(65행 분류 복사), 6개 단지 다시 수집 → 스크린샷 행 5개 재사용·새 행 1개도
OCR 엔진 호출 0(그림 해시 캐시).

### 접수 행 96(인천 스냅샷 1) 사유별

| 사유 | 1회차(운영) | R6 재생(main) | **R7 재생** |
| --- | ---: | ---: | ---: |
| 가능 | 4 | 4 | 4 |
| 미정 | 2 | 4 | 3 |
| 불가 | 1 | 1 | **4** |
| 문구로 판단 불가 | 29 | 33 | **26** |
| 판정 미해결 | 7 | 8 | 9 |
| 공식 홈페이지 동일성 미확인 | 19 | 12 | 10 |
| 공식 홈페이지가 다른 단지 | 8 | 8 | 8 |
| 판정 대상 아님(범위 경계) | — | — | **13** |
| 판정 대상 아님(공공분양) | — | — | **2** |
| TLS | 9 | 9 | **1** |
| robots | 0 | 0 | 1 |
| connect | 10 | 10 | 8 |
| 403 / 404 | 4 / 2 | 4 / 2 | 4 / 2 |
| 접수 문구 없음 | 1 | 1 | 1 |
| **확인 불가 합계** | 89 | 87 | 85 |
| 그중 사람 확인 대상(판정 대상 아님 제외) | 89 | 87 | **70** |

- 민간분양(판정 대상 후보) 단지의 접수 확정(가능·미정·불가): 1회차 6 → R6 7 → **R7 11**. 새로 정해진 것 — 디에트르 라 메르Ⅰ
  '가능'(팝업 그림 '선착순 계약' — open auto 0.90), 호반써밋Ⅲ '불가'(그림 '100% 분양완료' — closed auto 1.00), 두산위브 더센트럴
  도화 2행 '불가'(그림 '분양완료'). 범위 경계라 빠진 R6 의 '가능' 1(오션포레베네스트)·'미정' 1(검암역 푸르지오 프라베뉴)은 점수 대상이
  아니다.
- OCR 이 접수 항목에 들어간 행 19 — 확정 7, 판정 미해결 5(그림이 일정·옵션 안내라 review), 문구로 판단 불가 7.
- DOM 후보 규칙의 근거(같은 재생): DOM 후보 문맥에 OCR 글자를 덧붙이자 시티오씨엘 8단지('선착순 계약 안내문')가 open auto →
  review 0.63 으로 흐려졌다. 페이지에 후보가 있으면 OCR 을 붙이지 않게 바꾼 뒤 다시 auto '가능'.
- TLS 9 → 브라우저: hillstate.co.kr 5행은 브라우저로 robots.txt(200, 허용)·본문(200)을 받았다 — 웰카운티(공공분양)는 판정 대상 아님,
  나머지 4행은 브랜드 공통 페이지(`/s/`·`/s/GI59`)라 동일성 unclear(review) → '동일성 미확인'. 인하대역 푸르지오(중간 인증서 누락)는
  브라우저가 체인을 보완해 robots.txt 를 받았고 **Disallow** 라 본문을 받지 않음 → 'robots'. 만료(해링턴 스퀘어 — 범위 경계)·자체 서명
  (포레나 인천학익 — 범위 경계)·호스트 불일치(강화서희스타힐스 — `ERR_CERT_COMMON_NAME_INVALID`)는 브라우저도 실패 — 검증을 끄지
  않으므로 TLS 그대로(앞 둘은 '판정 대상 아님(범위 경계)', 원인은 원문 행·meta 에 남는다).
- OCR 성능(D5 기준 페이지당 30초): 팝업 그림 32장, 장당 0.23~2.55초, 페이지당 최대 2.8초(CPU, onnxruntime).

## 5. 운영 반영

- 배포 뒤 첫 `collect.daily`: 렌더한 팝업 그림을 OCR(인천 ≈ 32장, 1분 안), TLS 사이트는 브라우저 경로. 접수 항목이 바뀌는 행
  (DOM 후보 없고 OCR 글자 있음 — 인천 19)과 TLS 에서 새로 받은 행만 분류 복사가 막혀 판정기로 간다 → 동일성 1배치 + 접수 1배치
  ≈ `tools/call` 2(R6-INTAKE 와 같이 배포되면 R6 §5 의 전체 재판정 ≈ 3 에 포함). 같은 날 다시 돌리면 0. runbook §10-19.
- 판정 대상 아닌 단지의 접수 행은 '판정 대상 아님(<구분>)' — 사람 확인 대기열(D26-2, R7-QUEUE)에서 빼도 된다.
- R6-DONG(main `80fca23`, 이 브랜치에 병합)은 인천 범위 경계 단지 다수(LH 계양·가정·영종, 프라베뉴, 포레나더샵 인천시청역, 해링턴 스퀘어
  산곡역 등)의 법정동을 찾아 '미분류'로 되돌린다. 그러면 포함/제외 classify(접수보다 먼저 돈다)가 공공분양으로 정한 단지는
  '판정 대상 아님(공공분양)', 민간분양이면 일반 접수 판정으로 간다 — §4 의 '범위 경계 13'은 운영 DB 스냅샷 1 의 분류 기준이며,
  R6-DONG 뒤 분류는 판정기 호출이 필요해 이번 재생에 넣지 않았다.
- rapidocr 가 없는 설치(선택 의존성)는 스크린샷 행 meta `status='unavailable'` 사유만 남고 지금과 같다(OCR 블록 없음).

## 6. 제안 · 요청 (이번에 하지 않은 것)

1. **WP0 — `core.http` 공개 예약 함수**: 브라우저 요청이 같은 호스트 간격을 쓰도록 `HttpClient._reserve`(비공개)를 부른다
   (`collector._pace`, 없으면 아무것도 안 함). `HttpClient.reserve(host) -> float` 같은 공개 함수를 두면 비공개 의존이 없어진다.
2. hillstate.co.kr 4단지(숭의역·불로 포레스트·레이크 송도 4차·자이 계양)는 청약홈 등록 주소가 브랜드 공통 페이지라 동일성 review —
   단지 페이지 주소를 사람 확인(G7)으로 바꾸는 운영 절차가 필요(코드 아님).
3. DOM 에 후보가 없고 그림만 있는 행 중 '판정 미해결' 5(일정·옵션 안내 그림)는 R6 제안 2(접수 classify 기준일)와 같은 문제 —
   기준일 결정이 나면 같이 풀린다.
4. 동일성 항목에도 OCR 글자(단지 이름이 그림에만 있는 페이지)를 넣을 수 있다 — 이번 범위(D26-1 = 접수 classify) 밖이라 하지 않음.

계약 변경 요청: 없음(`raw_document.meta` 는 수집기가 키를 정하는 자유 객체 — 계약 2026-10-09.2).
