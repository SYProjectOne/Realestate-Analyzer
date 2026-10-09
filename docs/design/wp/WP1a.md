# WP1a 수집 어댑터 (청약홈·공고문 PDF·OCR) — 작업 지시

소유: `backend/app/collectors/applyhome/`, `backend/app/collectors/notice_pdf/`, `backend/tests/collectors/applyhome/`, `backend/tests/collectors/notice_pdf/`, `contracts/fixtures/ocr_samples/`(OCR 시료만), `docs/adr/ADR-12-ocr.md`. 공용 헬퍼는 각자 패키지 안에(WP1b와 충돌 방지 — `collectors/common/` 만들지 말 것).
참조: RA §3 `raw_document`·`competition`·`remaining_event` 행, §4-3 `Collector`, §5 WP1 카드, §9 T3·T17; DECISIONS D2-6(시도 단위 조회 + 시군구 이름 사전 필터), D5(OCR).

## 할 일
1. `applyhome/`: 청약홈(www.applyhome.co.kr) **APT 분양정보 목록**과 **무순위/잔여세대 목록** 두 개의 조회(실제 사이트를 열어 요청 형식 확인), 단지 **상세**·**경쟁률** 페이지, 모집공고문 PDF 링크 추출. `fetch(region, snapshot, since)`는 region의 `sido_codes`로 목록을 조회하고 공급위치 문자열에 region 시군구 이름이 포함된 행만 상세를 가져온다(정밀 법정동 배정은 WP2). 원문(HTML/JSON) 전부 `RawDocument`(source_kind = applyhome_list/applyhome_detail).
2. `notice_pdf/`: PDF 다운로드 → pdfplumber 텍스트(+표 추출 JSON) → 실패 시 pypdf 폴백. 텍스트 레이어 없음 → 스캔 감지 → "확인 불가(스캔)" 메타. `text_path`에 txt 저장.
3. 멱등: 같은 sha256이면 저장 안 함(`raw_document` 증가 0). 실패도 `RawDocument(http_status=…)`(403·타임아웃·DNS).
4. HTTP는 `app.core.http`만(속도 제한·robots·재시도).
5. **실제 사이트에서 녹화**: 인천(연수구·서구/검단구·계양구)·김포의 실제 목록·상세·경쟁률·공고문 PDF 몇 개를 받아 `backend/tests/collectors/<패키지>/fixtures/`에 저장, 테스트는 respx 오프라인 재생. 실제 접속 테스트는 `@pytest.mark.live`.
6. OCR(D5): 후보 PaddleOCR 3.x(PP-OCRv5 korean, PaddleOCR-VL), RapidOCR, Surya, EasyOCR, Tesseract. 실제 공고문 가격표 페이지 이미지 시료 3장 이상 + 정답 텍스트를 `contracts/fixtures/ocr_samples/`에. 각 후보를 **별도 임시 venv**(프로젝트 .venv 오염 금지)에서 설치·측정(숫자 문자 단위 정확도, 페이지당 시간, 라이선스, Windows pip 설치). 기준(가격표 숫자 100% 일치, CPU 30초/페이지 이내, 개인 무료, pip 설치) 통과 중 최고 1개 채택 → `notice_pdf/ocr.py`(선택 의존성; import 실패 시 OCR 없음으로 동작) + 보고에 "제안: optional-dependencies ocr = [...]". 미통과면 OCR 없음. 결과표 `docs/adr/ADR-12-ocr.md`.

## 완료 기준 (자동 테스트)
- [ ] collector마다 녹화 HTTP 픽스처(respx) 테스트
- [ ] 같은 입력 2회 → `raw_document` 증가 0 (임시 sqlite + `app.models`)
- [ ] 403 픽스처 → `http_status=403` 행, 예외 없음
- [ ] 목록 → 시군구 사전 필터 → 상세 수 검증
- [ ] 공고문 PDF → txt, 스캔 PDF 픽스처 → "확인 불가(스캔)"
- [ ] OCR 평가표(ADR-12); 채택 시 시료 3장 숫자 100% 테스트
- [ ] 지역 1개 일일 수집 녹화 재생 기준 10분 이내(시간 측정 테스트)
