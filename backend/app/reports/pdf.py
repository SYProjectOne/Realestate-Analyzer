"""HTML → PDF: 같은 자립 HTML을 Playwright chromium ``page.pdf()``로 인쇄(DECISIONS D4, weasyprint 미사용).

인쇄 중 네트워크는 file: 외 전부 차단한다(외부 리소스 0 보장). 차트는 ``window.__reportReady`` 를 기다린다.
동기 API — worker 스레드에서 부른다(실행 중인 asyncio 루프 안에서는 부르지 않는다).

쪽수(R9-REPORT, 첫 장 메타 상자 '본문 n쪽 · 부록 m쪽'): 한 번 인쇄해 쪽마다 첫 글이 어느 장 제목인지 보고(장은 새 쪽에서
시작한다 — report.css ``break-before: page``) 본문·부록 쪽을 센 뒤, ``data-pages`` 칸을 채우고 다시 인쇄한다. 같은 브라우저
페이지에서 하므로 차트를 다시 그리지 않는다. 쪽수가 바뀌면(채운 숫자로 줄이 밀림) 한 번 더 센다(최대 3회).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Final

from playwright.sync_api import Page, Route, sync_playwright
from pypdf import PdfReader

from app.reports.sections import APPENDIX_TITLES, BODY_TITLES, DISCLAIMER

__all__ = ["count_pages", "html_to_pdf"]

READY_TIMEOUT_MS: Final = 60_000
_FOOTER: Final = (
    '<div style="font-size:7px;width:100%;text-align:center;color:#4b5563;">'
    f'{DISCLAIMER} — <span class="pageNumber"></span> / <span class="totalPages"></span></div>'
)


def _only_local(route: Route) -> None:
    url = route.request.url
    if url.startswith(("file:", "data:", "about:")):
        route.continue_()
    else:
        route.abort()


def _pdf(page: Page) -> bytes:
    return page.pdf(
        format="A4",
        print_background=True,
        display_header_footer=True,
        header_template="<div></div>",
        footer_template=_FOOTER,
        margin={"top": "14mm", "bottom": "16mm", "left": "10mm", "right": "10mm"},
    )


_FILL_JS: Final = """(c) => {
  for (const el of document.querySelectorAll('[data-pages]')) el.textContent = String(c[el.dataset.pages]);
  for (const el of document.querySelectorAll('[data-pages-note]')) el.remove();
}"""
MAX_PASSES: Final = 3


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


_FOOTER_RE: Final = re.compile(re.escape(_norm(DISCLAIMER)) + r"—\d+/\d+")
_MARKS: Final = tuple((_norm(t), "body") for t in BODY_TITLES) + tuple(
    (_norm(t), "appendix") for t in APPENDIX_TITLES
)


def count_pages(pdf: bytes) -> dict[str, int]:
    """본문·부록·전체 쪽수. 쪽의 첫 글이 장 제목이면 그 장의 묶음으로 바뀐다(첫 장·목차 = 본문)."""
    reader = PdfReader(io.BytesIO(pdf))
    out = {"body": 0, "appendix": 0, "total": len(reader.pages)}
    group = "body"
    for page in reader.pages:
        text = _FOOTER_RE.sub("", _norm(page.extract_text() or ""))
        for title, g in _MARKS:
            if text.startswith(title):
                group = g
                break
        out[group] += 1
    return out


def _print_with_page_counts(page: Page, pdf_path: Path) -> dict[str, int]:
    counts = count_pages(_pdf(page))
    data = b""
    for _ in range(MAX_PASSES):
        page.evaluate(_FILL_JS, counts)
        data = _pdf(page)
        again = count_pages(data)
        if again == counts:
            break
        counts = again
    pdf_path.write_bytes(data)
    return counts


def html_to_pdf(html_path: Path, pdf_path: Path, *, timeout_ms: int = READY_TIMEOUT_MS) -> Path:
    """``html_path`` 를 열어 차트가 그려지면 A4로 인쇄해 ``pdf_path`` 에 쓴다(첫 장 쪽수 칸을 채운 판)."""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.route("**/*", _only_local)
            page.goto(html_path.resolve().as_uri(), wait_until="load", timeout=timeout_ms)
            page.wait_for_function("window.__reportReady === true", timeout=timeout_ms)
            page.emulate_media(media="print")
            _print_with_page_counts(page, pdf_path)
        finally:
            browser.close()
    return pdf_path
