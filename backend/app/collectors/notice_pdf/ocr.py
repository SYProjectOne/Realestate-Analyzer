"""스캔 공고문 OCR (DECISIONS D5) — 선택 의존성. 평가 결과는 docs/adr/ADR-12-ocr.md.

채택: **RapidOCR** (onnxruntime, 인식기 PP-OCRv5 korean mobile). 설치는 선택 의존성 그룹 ``ocr``
(제안: ``rapidocr>=3.10,<4``, ``onnxruntime>=1.18``). 설치돼 있지 않으면 ``load_ocr()`` 가 None 을 돌려주고
수집기는 OCR 없이 동작한다(스캔 PDF = '확인 불가(스캔)').

- 페이지를 200dpi 회색조로 렌더(pypdfium2 — pdfplumber 의존성)해 인식하고, 상자들을 세로 위치로 묶어
  한 줄씩(왼쪽→오른쪽, 공백 구분) 텍스트를 만든다 — 가격표 한 행이 한 줄이 되도록.
- OCR 로 얻은 값의 라벨은 '추정(OCR)'이고 판정기 extract/audit 를 거친다(D5-4, WP2·WP3).
- 모델 파일은 처음 쓸 때 rapidocr 가 내려받는다(이후 site-packages 캐시).
"""

from __future__ import annotations

import importlib
import io
from typing import Any

from app.collectors.notice_pdf.extract import OcrFn

__all__ = ["DPI", "lines_from_boxes", "load_ocr", "ocr_image"]

DPI = 200
_ENGINE: Any = None


def _engine() -> Any:
    global _ENGINE
    if _ENGINE is None:
        rapidocr = importlib.import_module("rapidocr")
        _ENGINE = rapidocr.RapidOCR(
            params={
                # rapidocr 3.10 기본 인식기(PP-OCRv6 small)는 한국어가 없다 → 인식기만 PP-OCRv5 korean mobile
                "Rec.lang_type": rapidocr.LangRec.KOREAN,
                "Rec.ocr_version": rapidocr.OCRVersion.PPOCRV5,
                "Rec.model_type": rapidocr.ModelType.MOBILE,
            }
        )
    return _ENGINE


def lines_from_boxes(items: list[tuple[list[list[float]], str]]) -> str:
    """(상자 4점, 텍스트) 목록 → 세로 위치가 겹치는 상자끼리 한 줄로(왼쪽부터), 줄은 위에서 아래로."""
    boxes = []
    for pts, text in items:
        ys = [p[1] for p in pts]
        xs = [p[0] for p in pts]
        boxes.append((min(ys), max(ys), min(xs), text))
    boxes.sort(key=lambda b: (b[0] + b[1]) / 2)
    lines: list[list[tuple[float, float, float, str]]] = []
    for box in boxes:
        center = (box[0] + box[1]) / 2
        if lines:
            last = lines[-1]
            top = sum(b[0] for b in last) / len(last)
            bottom = sum(b[1] for b in last) / len(last)
            if top <= center <= bottom:
                last.append(box)
                continue
        lines.append([box])
    return "\n".join(" ".join(b[3] for b in sorted(line, key=lambda b: b[2])) for line in lines)


def ocr_image(image: Any) -> str:
    """PIL 이미지 또는 경로 → 줄 단위 텍스트."""
    result = _engine()(image)
    boxes = result.boxes if result.boxes is not None else []
    texts = result.txts or ()
    return lines_from_boxes(
        [([list(map(float, p)) for p in box], str(t)) for box, t in zip(boxes, texts, strict=False)]
    )


def _ocr_pdf_pages(content: bytes, pages: list[int]) -> dict[int, str]:
    pdfium = importlib.import_module("pypdfium2")  # pdfplumber 의존성(타입 정보 없음)

    doc = pdfium.PdfDocument(io.BytesIO(content))
    out: dict[int, str] = {}
    try:
        for page in pages:
            if 0 <= page < len(doc):
                image = doc[page].render(scale=DPI / 72).to_pil().convert("RGB")
                out[page] = ocr_image(image)
    finally:
        doc.close()
    return out


def load_ocr() -> OcrFn | None:
    """채택한 OCR 엔진(rapidocr + onnxruntime)이 설치돼 있으면 OCR 함수, 아니면 None(= OCR 없음)."""
    try:
        importlib.import_module("rapidocr")
        importlib.import_module("onnxruntime")
    except ImportError:
        return None
    return _ocr_pdf_pages
