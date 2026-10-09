"""HTML → PDF: 같은 자립 HTML을 Playwright chromium ``page.pdf()``로 인쇄(DECISIONS D4, weasyprint 미사용).

인쇄 중 네트워크는 file: 외 전부 차단한다(외부 리소스 0 보장). 차트는 ``window.__reportReady`` 를 기다린다.
동기 API — worker 스레드에서 부른다(실행 중인 asyncio 루프 안에서는 부르지 않는다).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from playwright.sync_api import Route, sync_playwright

from app.reports.sections import DISCLAIMER

__all__ = ["html_to_pdf"]

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


def html_to_pdf(html_path: Path, pdf_path: Path, *, timeout_ms: int = READY_TIMEOUT_MS) -> Path:
    """``html_path`` 를 열어 차트가 그려지면 A4로 인쇄해 ``pdf_path`` 에 쓴다."""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.route("**/*", _only_local)
            page.goto(html_path.resolve().as_uri(), wait_until="load", timeout=timeout_ms)
            page.wait_for_function("window.__reportReady === true", timeout=timeout_ms)
            page.emulate_media(media="print")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                display_header_footer=True,
                header_template="<div></div>",
                footer_template=_FOOTER,
                margin={"top": "14mm", "bottom": "16mm", "left": "10mm", "right": "10mm"},
            )
        finally:
            browser.close()
    return pdf_path
