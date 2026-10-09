# ADR-12 OCR (스캔 공고문)

- 상태: 채택 제안(WP1a, 2026-10-09) — 선택 의존성 그룹 `ocr` 은 WP0 승인 대기
- 결정: **RapidOCR 3.10 (onnxruntime) + PP-OCRv5 korean mobile 인식기** 를 선택 의존성으로 채택
- 버린 대안: PaddleOCR 3.x(CPU 시간 초과), EasyOCR(숫자 100% 미달), Tesseract(숫자 미달·pip 설치 불가),
  Surya(정확도·시간 미달, 최신판은 pip 외 llama-server 필요), PaddleOCR-VL(미측정 — 아래)
- 근거 규칙: DECISIONS D5, ADR-04 변경

## 기준 (D5)

1. 가격표 숫자(공급금액·층·타입) **문자 단위 100% 일치** — 시료 전 페이지
2. CPU 에서 **페이지당 30초 이내**
3. 개인 사용 무료 라이선스
4. Windows 에서 **pip 만으로** 설치

## 시료 (`contracts/fixtures/ocr_samples/`)

실제 청약홈 모집공고문(2026-10-09 녹화)의 공급금액 표 페이지를 200dpi 회색조 PNG 로 렌더한 4장.
정답 = 같은 페이지의 PDF 텍스트 레이어(`sample_NN.txt`). 채점 대상 숫자 토큰은 `manifest.json` 의 `numbers`
(정규식: 금액 `1,234,567` · 주택형 `084.9766C` · 층 `32층`/`16~20층` · 소수/연월 `2026.12`).

| 시료 | 원본 | 쪽 | 숫자 토큰 |
| --- | --- | --- | --- |
| sample_01 | 2026940062 왕길역 아테라(3차) 임의공급 | 3 | 60 |
| sample_02 | 2026910242 더샵 송도마리나베이 무순위 | 4 | 24 |
| sample_03 | 2026000169 더샵 송도그란테르 G5-11 | 7 | 440 |
| sample_04 | 2026000195 더샵 검단레이크파크 AB23 | 8 | 468 |

## 측정 (2026-10-09)

환경: AMD Ryzen 5 5600(6코어/12스레드), RAM 32GB, Windows 11, Python 3.12, GPU 미사용.
후보마다 별도 임시 venv(`C:/tmp/ocrbench/<engine>`, 프로젝트 .venv 무관). 도구: `backend/tests/collectors/notice_pdf/ocr_bench.py`.
**주의**: 같은 PC 에서 다른 에이전트 7명이 테스트를 돌리는 중에 쟀다 — 절대 시간은 흔들릴 수 있고, 순위는 같다.
페이지 시간 = 모델 적재·워밍업 1회 뒤 한 페이지 인식 시간.

| 엔진 (버전) | 숫자 토큰 일치 | 숫자 문자 정확도 | 페이지당 시간 평균 / 최대 | 라이선스 | Windows pip | 기준 |
| --- | --- | --- | --- | --- | --- | --- |
| **RapidOCR 3.10.0** + onnxruntime 1.30, 인식 PP-OCRv5 korean mobile | **992/992 (100%)** | **100%** | **10.1s / 18.6s** | Apache-2.0(코드·모델) | 가능 | **통과** |
| PaddleOCR 3.7.0 + paddlepaddle 3.3.1, PP-OCRv5 mobile 검출 + korean mobile 인식 | 992/992 (100%) | 100% | 88.0s / 149.3s | Apache-2.0 | 가능(단 oneDNN 끔 필요) | 시간 미달 |
| EasyOCR 1.7.2 + torch 2.14 CPU (ko+en) | 964/992 (97.2%) | 98.5% | 27.8s / 41.2s | Apache-2.0 | 가능 | 정확도·시간 미달 |
| Tesseract 5.4.0 (kor+eng tessdata_best, psm 6) + pytesseract | 504/992 (50.8%) | 54.8% | 9.6s / 15.9s | Apache-2.0 | **불가**(별도 설치 프로그램) | 정확도·설치 미달 |
| Surya 0.17.1 + torch 2.14 CPU (transformers 4.56) | 519/524 (3쪽까지, 99.0%) | 99.6% | 165s / 288s (4쪽째 중단) | 코드 GPL-3.0, 모델 OpenRAIL-M 변형(개인·소규모 무료) | 0.17 은 가능 / 최신 0.22 는 불가 | 정확도·시간 미달 |
| PaddleOCR-VL | 미측정 | — | — | Apache-2.0 | — | 아래 |

세부(쪽별 일치/시간):

- RapidOCR: 60/60 3.7s · 24/24 3.2s · 440/440 15.1s · 468/468 18.6s
- PaddleOCR 3.x: 60/60 48.6s · 24/24 31.7s · 440/440 122.5s · 468/468 149.3s. 기본 검출(PP-OCRv5 server)은 한 시간
  가까이 끝나지 않아 중단했고 mobile 검출로 다시 쟀다. oneDNN 을 켜면 `NotImplementedError(ConvertPirAttribute2RuntimeAttribute)`.
- EasyOCR: 60/60 · 24/24 · 417/440 · 463/468 — 조밀한 표에서 콤마·자릿수 누락
- Tesseract: 50/60 · 9/24 · 386/440 · 59/468 — 표 칸 경계에서 숫자가 붙거나 끊김
- Surya: 58/60 107s · 24/24 100s · 437/440 288s — 4쪽째(468 토큰)는 시간 기준을 이미 크게 넘어 중단.
  최신 surya-ocr 0.22(surya-ocr-2 VLM)는 `llama-server` 실행 파일을 따로 설치해야 해 pip 기준 미달이라
  pip 만으로 되는 마지막 계열 0.17.1 로 쟀다(transformers ≥4.57 과 충돌 → 4.56 고정).
- PaddleOCR-VL: 0.9B VLM 이라 CPU 에서 페이지당 30초 안에 들 수 없다고 보고 설치·측정하지 않았다
  (같은 Paddle 런타임의 PP-OCRv5 mobile 파이프라인이 이미 31~149초/쪽). GPU 가 생기면 다시 잴 후보.

## 결정

기준 4개를 모두 만족한 것은 **RapidOCR** 하나 → 채택. 구현 `backend/app/collectors/notice_pdf/ocr.py`:

- `load_ocr()` — `rapidocr`·`onnxruntime` 이 import 되면 OCR 함수, 아니면 `None`(= OCR 없음, 기존 동작).
- 스캔 페이지(텍스트 레이어 < 20자)만 200dpi 로 렌더(pypdfium2, pdfplumber 의존성) → 인식 → 상자를 세로 위치로
  묶어 한 줄(왼→오)씩 텍스트. 인식기만 PP-OCRv5 korean mobile(rapidocr 3.10 기본 PP-OCRv6 small 은 한국어 없음).
- raw_document.error_text: 전 페이지 OCR = `ocr`, 일부 = `ocr_partial:<쪽>`; OCR 이 없거나 실패하면 `scan`
  (= 화면 '확인 불가(스캔)'). OCR 값의 라벨은 **'추정(OCR)'** 이고 판정기 extract/audit 를 반드시 거친다(D5-4, WP2·WP3).
- 모델 파일(검출 ~5MB, 인식 13MB)은 처음 쓸 때 rapidocr 가 내려받아 site-packages 에 캐시한다.

**제안(WP0)**: `backend/pyproject.toml`

```toml
[project.optional-dependencies]
ocr = ["rapidocr>=3.10,<4", "onnxruntime>=1.18"]
```

자동 테스트: `backend/tests/collectors/notice_pdf/test_ocr.py` — 시료 4장 숫자 100%, 스캔 PDF 픽스처 OCR.
엔진이 없는 환경에서는 그 두 테스트가 skip 되고, 엔진 없을 때 '확인 불가(스캔)' 동작은 항상 검사한다.
프로젝트 .venv 를 바꾸지 않고 돌리기: `uv run --with "rapidocr==3.10.0" --with onnxruntime pytest tests/collectors/notice_pdf/test_ocr.py`.

## 한계·바꿀 신호

- 시료는 텍스트 레이어가 있는 PDF 를 렌더한 깨끗한 이미지다. 실제 스캔(기울기·번짐·도장)에서는 더 낮을 수 있다 —
  그래서 OCR 값은 '추정(OCR)' + 판정기 audit 이다. 실제 스캔 공고가 나오면 시료에 추가하고 다시 잰다.
- 100dpi JPEG 로 만든 거친 스캔 픽스처(`scan_2026940062_p1p3.pdf`)에서도 가격표 숫자 60/60 이었다(테스트가 100% 를 요구).
- rapidocr 의 기본 모델 버전이 바뀌면(3.10 → PP-OCRv6) 한국어 인식기 지정이 깨질 수 있다 — 버전 상한 `<4`.
