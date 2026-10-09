"""D4 완료 기준(PDF): 같은 HTML을 Playwright chromium page.pdf()로 — 페이지 > 0, 텍스트 추출로 섹션 제목 11개."""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy.orm import Session, sessionmaker

from app.reports.export import generate
from app.reports.sections import SECTION_TITLES


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


def test_pdf_for_both_snapshots_has_pages_and_eleven_section_titles(
    factory: sessionmaker[Session], out_dir: Path
) -> None:
    for sid, compare in ((12, 11), (11, None)):
        with factory() as s:
            rep = generate(s, sid, "pdf", compare_snapshot_id=compare, out_dir=out_dir)
        assert rep.path.suffix == ".pdf" and rep.path.read_bytes()[:5] == b"%PDF-"
        reader = PdfReader(str(rep.path))
        assert len(reader.pages) > 0
        text = _norm("".join(page.extract_text() or "" for page in reader.pages))
        missing = [t for t in SECTION_TITLES if _norm(t) not in text]
        assert not missing, missing
        if compare is not None:
            assert "diff" in rep.path.name or "_vs_" in rep.path.name
