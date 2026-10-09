"""스캔 공고문 OCR (DECISIONS D5) — 선택 의존성. 평가 결과는 docs/adr/ADR-12-ocr.md."""

from __future__ import annotations

from app.collectors.notice_pdf.extract import OcrFn

__all__ = ["load_ocr"]


def load_ocr() -> OcrFn | None:
    """채택한 OCR 엔진이 설치돼 있으면 OCR 함수, 아니면 None(= OCR 없음, '확인 불가(스캔)')."""
    return None
