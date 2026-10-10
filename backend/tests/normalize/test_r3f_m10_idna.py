"""R3f CORE4 — 6차 리뷰 minor 10: 홈페이지 URL 내부망 검사의 UTS46 무시 문자 목록이 손 목록이라
U+2064·U+E0100~E01EF·U+1BCA0~1BCA3 이 지워지지 않고 검사를 지났다.

| 리뷰 | 테스트 |
| --- | --- |
| m10 리뷰 재현 3종 | ``test_m10_review_chars_are_ignored_before_internal_check`` |
| m10 UTS46 '아무것도 아님으로 매핑' 전체(``idna`` 표와 대조) | ``test_m10_matches_uts46_mapped_to_nothing_set`` |
| 공개 호스트는 정규형으로 | ``test_m10_public_host_canonical`` |
"""

# ruff: noqa: E501

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "ch",
    ["⁤", "\U000e0100", "\U000e01ef", "\U000e0150", "\U0001bca0", "\U0001bca3", "⁡", "឴", "⁪", "\U0001d173"],
)
def test_m10_review_chars_are_ignored_before_internal_check(ch: str) -> None:
    from app.normalize._text import normalize_site_url

    for url in (f"http://127.0.0.1{ch}/", f"http://loc{ch}alhost/", f"http://foo.local{ch}host/"):
        assert normalize_site_url(url) is None, ascii(url)


def test_m10_matches_uts46_mapped_to_nothing_set() -> None:
    """UTS46(IDNA 매핑 표)가 '아무것도 아님'으로 지우는 글자 전부를 ``canonical_host`` 가 지운다.

    표는 ``idna`` 패키지(httpx 의존성으로 이미 설치 — 새 의존성 아님)에서 읽는다. 없으면 건너뛴다."""
    idna = pytest.importorskip("idna")
    from app.normalize._text import canonical_host

    missed: list[str] = []
    for cp in range(0x110000):
        if 0xD800 <= cp <= 0xDFFF:
            continue
        s = "a" + chr(cp) + "b"
        try:
            mapped = idna.uts46_remap(s, std3_rules=False, transitional=False)
        except Exception:  # 허용되지 않는 글자(브라우저도 거부)
            continue
        if mapped == "ab" and canonical_host(s) != "ab":
            missed.append(f"U+{cp:04X}")
    assert missed == [], missed


def test_m10_public_host_canonical() -> None:
    from app.normalize._text import normalize_site_url

    assert normalize_site_url("http://exam⁤ple.com/") == "http://example.com/"
    assert normalize_site_url("http://exam\U000e0100ple.com/a") == "http://example.com/a"
