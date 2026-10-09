"""R3 minor 17: 공고문 PDF 링크는 호스트를 정확히 비교한다(부분 문자열 비교 금지)."""

from __future__ import annotations

from app.collectors.applyhome.parse import notice_pdf_links

GOOD = "https://static.applyhome.co.kr/ai/aia/getAtchmnfl.do?houseManageNo=2025000271&atchmnflSeqNo=1"


def test_minor17_pdf_link_host_must_match_exactly() -> None:
    html = f"""
    <a href="{GOOD}">공고문</a>
    <a href="https://static.applyhome.co.kr.evil.example/ai/aia/getAtchmnfl.do?x=1">가짜1</a>
    <a href="https://evil.example/getAtchmnfl.do?next=static.applyhome.co.kr">가짜2</a>
    <a href="https://evil.example/static.applyhome.co.kr/getAtchmnfl.do">가짜3</a>
    <a href="javascript:alert('static.applyhome.co.kr/getAtchmnfl.do')">가짜4</a>
    <a href="ftp://static.applyhome.co.kr/getAtchmnfl.do">가짜5</a>
    <a href="{GOOD.replace("&", "&amp;")}">중복</a>
    """
    assert notice_pdf_links(html) == [GOOD]
