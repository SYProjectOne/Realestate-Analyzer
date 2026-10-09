# ADR-04 수집

- 상태: 채택, OCR 부분은 DECISIONS D5 로 변경 (RA v1 §1)
- 결정: **httpx(정적) + Playwright chromium(팝업·동적) + pdfplumber(공고문, pypdf 폴백) + 공공데이터포털 Open API(실거래)**
- 버린 대안: Selenium, (원안) OCR

## 이유

- 일부 공식 홈페이지는 403, 동적 팝업은 렌더링 없이 읽히지 않았다.
- 스캔 PDF 는 원안에서 "확인 불가(스캔)" 라벨 + 사람 입력.

## 변경 (D5)

가장 진보된 무료 한글 OCR 후보(PaddleOCR 3.x, RapidOCR, Surya, EasyOCR, Tesseract)를 벤치마크해 기준
(가격표 숫자 문자 단위 100% 일치, CPU 페이지당 30초, 개인 무료, Windows pip)을 만족하면 채택 — 라벨 "추정(OCR)",
판정기 extract/audit 필수. 만족하는 것이 없으면 원안 유지. 결과는 `ADR-12-ocr.md`(WP1a).

## 결과

- `app/core/http.py`: 호스트별 속도 제한(`HTTP_RATE_PER_HOST`, 기본 1 req/s), 5xx·타임아웃·연결 오류만 지수 백오프
  재시도(`HTTP_MAX_RETRIES`), robots.txt(RFC 9309) 확인·캐시, 실패도 `FetchResult` 로 반환(예외 없음).
- 원문은 `core.snapshot.store_raw` → ADR-08 경로. 같은 sha256 이면 다시 쓰지 않는다(멱등).
- 실거래 키가 없으면 재가공 라벨로 동작(D1 #5), 뉴스 키가 없으면 news collector 비활성(D1 #6).

## 바꿀 신호

스캔 PDF 가 반 이상.
