"""공고문 PDF → 텍스트(+표) (RA ADR-4, DECISIONS D5).

1. pdfplumber 로 페이지별 텍스트와 표(``extract_tables``)를 뽑는다.
2. pdfplumber 가 실패하면(손상·암호 등) pypdf 텍스트로 폴백한다(표 없음).
3. 텍스트 레이어가 없는 페이지(공백 제외 글자 < ``MIN_PAGE_CHARS``)는 스캔으로 본다.
   전 페이지가 스캔이면 ``scanned=True`` → 수집기가 ``error_text='scan'`` = 화면 '확인 불가(스캔)'.
   일부만 스캔이면 ``scan_pages`` 에 0부터 센 페이지 번호를 남긴다.
4. OCR 엔진이 설치돼 있으면(선택 의존성, ``ocr.py``) 스캔 페이지만 OCR 해서 텍스트를 채우고
   ``ocr_pages`` 에 남긴다.
   OCR 로 얻은 값의 라벨은 '추정(OCR)'이고 판정기 extract/audit 를 거친다(D5-4) — 그 판단은 WP2·WP3 몫.

텍스트 파일 형식: 페이지마다 ``\\f`` (form feed) 로 구분한다(pdftotext 관례). 표 JSON 은
``[{"page": 0, "tables": [[["셀", ...], ...], ...]}, ...]`` — 표가 있는 페이지만.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = ["MIN_PAGE_CHARS", "OcrFn", "PdfExtraction", "extract_pdf", "is_pdf"]

MIN_PAGE_CHARS = 20
_WS = re.compile(r"\s+")

OcrFn = Callable[[bytes, list[int]], dict[int, str]]
"""(PDF 바이트, 0부터 센 페이지 번호들) → {페이지: OCR 텍스트}."""


@dataclass(slots=True)
class PdfExtraction:
    method: Literal["pdfplumber", "pypdf", "none"]
    pages: list[str] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    scan_pages: list[int] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    error: str | None = None  # 두 방법 모두 실패한 사유

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def scanned(self) -> bool:
        """텍스트 레이어가 한 페이지도 없다(OCR 전 기준)."""
        return self.page_count > 0 and len(self.scan_pages) == self.page_count

    @property
    def text(self) -> str:
        return "\f".join(self.pages)


def is_pdf(content: bytes) -> bool:
    return content[:1024].lstrip().startswith(b"%PDF")


def _chars(text: str) -> int:
    return len(_WS.sub("", text))


def _plumber(content: bytes) -> PdfExtraction:
    import pdfplumber

    out = PdfExtraction(method="pdfplumber")
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            out.pages.append(text)
            if _chars(text) >= MIN_PAGE_CHARS:
                tables = page.extract_tables()
                if tables:
                    out.tables.append(
                        {
                            "page": i,
                            "tables": [
                                [[c if c is not None else "" for c in row] for row in t] for t in tables
                            ],
                        }
                    )
            page.flush_cache()
    return out


def _pypdf(content: bytes) -> PdfExtraction:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    return PdfExtraction(method="pypdf", pages=[p.extract_text() or "" for p in reader.pages])


def extract_pdf(content: bytes, *, ocr: OcrFn | None = None) -> PdfExtraction:
    errors: list[str] = []
    result: PdfExtraction | None = None
    for fn in (_plumber, _pypdf):
        try:
            result = fn(content)
            break
        except Exception as exc:  # 손상 PDF 는 라이브러리마다 예외 종류가 다르다 — 사유로 남기고 다음 방법
            errors.append(f"{fn.__name__.strip('_')}: {type(exc).__name__}: {exc}"[:300])
    if result is None:
        return PdfExtraction(method="none", error="; ".join(errors) or "unknown")

    result.scan_pages = [i for i, t in enumerate(result.pages) if _chars(t) < MIN_PAGE_CHARS]
    if result.scan_pages and ocr is not None:
        try:
            texts = ocr(content, list(result.scan_pages))
        except Exception as exc:  # OCR 실패는 '확인 불가(스캔)'로 남는다
            result.error = f"ocr: {type(exc).__name__}: {exc}"[:300]
            texts = {}
        for page, text in sorted(texts.items()):
            if 0 <= page < result.page_count and _chars(text) >= MIN_PAGE_CHARS:
                result.pages[page] = text
                result.ocr_pages.append(page)
    return result
