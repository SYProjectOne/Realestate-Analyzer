"""R3c SEC — redact 패턴 보강(R3 3차 리뷰 minor 22·31).

- 22 숫자 없는 Bearer 토큰, 헤더 이름으로 알 수 있는 키(X-NCP-APIGW-API-KEY, x-api-key, X-Naver-Client-Secret …)
- 31 전화·주민번호 변형: ``8210-``·``(82)10-``·en/em dash·전각 숫자·공백 낀 하이픈
"""

# ruff: noqa: E501

from __future__ import annotations

import pytest

from app.core.redact import contains_sensitive, find_sensitive, redact_obj, redact_text

# ---------------------------------------------------------------- 22 Bearer·헤더 이름


@pytest.mark.parametrize(
    "text, secret",
    [
        ("Bearer abcdefghijklmnopqrstuv", "abcdefghijklmnopqrstuv"),
        ("bearer AbCdEfGhIjKl", "AbCdEfGhIjKl"),
        ("headers: bearer abc-def_ghi.jkl", "abc-def_ghi.jkl"),
        ("X-NCP-APIGW-API-KEY: plainsecretvalue", "plainsecretvalue"),
        ("X-NCP-APIGW-API-KEY-ID=someidvalue", "someidvalue"),
        ("x-api-key: lowercasekeyvalue", "lowercasekeyvalue"),
        ("'X-Naver-Client-Secret': 'naversecretzz'", "naversecretzz"),
        ('{"X-Api-Key": "jsonkeyvalue"}', "jsonkeyvalue"),
        ("api-key = spacedvalue", "spacedvalue"),
        ("X-Auth-Token: tokenvalueabc", "tokenvalueabc"),
    ],
)
def test_minor22_header_and_bearer_tokens_masked(text: str, secret: str) -> None:
    out = redact_text(text)
    assert secret not in out, out
    assert "[REDACTED:secret]" in out
    assert contains_sensitive(text)


@pytest.mark.parametrize(
    "text",
    [
        "the bearer of this letter",
        "bearer bonds are rare",
        "Bearer Instruments Act",
        "the bearer certificates",
        "무기명(bearer) 채권",
        "Content-Type: text/html",
        "X-Frame-Options: DENY",
    ],
)
def test_minor22_prose_and_plain_headers_untouched(text: str) -> None:
    assert redact_text(text) == text


def test_minor22_dict_keys_with_hyphen_masked() -> None:
    out = redact_obj(
        {"X-NCP-APIGW-API-KEY": "v1", "x-api-key": "v2", "X-Naver-Client-Secret": "v3", "Accept": "a"}
    )
    assert out == {
        "X-NCP-APIGW-API-KEY": "[REDACTED:key]",
        "x-api-key": "[REDACTED:key]",
        "X-Naver-Client-Secret": "[REDACTED:key]",
        "Accept": "a",
    }


# ---------------------------------------------------------------- 31 전화·주민번호 변형


@pytest.mark.parametrize(
    "text",
    [
        "연락처 8210-1234-5678",
        "연락처 (82)10-1234-5678",
        "연락처 (+82) 10-1234-5678",
        "연락처 010–1234–5678",  # en dash
        "연락처 010—1234—5678",  # em dash
        "연락처 ０１０－１２３４－５６７８",  # 전각
        "연락처 ０１０１２３４５６７８",
        "연락처 010 - 1234 - 5678",
        "연락처 010 -1234- 5678",
        "사무실 02 - 123 - 4567",
        "대표 1588–1234",
        "연락처 +82 10 – 1234 – 5678",
    ],
)
def test_minor31_phone_variants_masked(text: str) -> None:
    out = redact_text(text)
    assert "[REDACTED:phone]" in out, out
    assert not any(ch.isdigit() for ch in out), out
    assert [f.kind for f in find_sensitive(text)] == ["phone"]


@pytest.mark.parametrize(
    "text",
    [
        "주민 900101–1234567",
        "주민 900101—1234567",
        "주민 ９００１０１－１２３４５６７",
        "주민 900101 - 1234567",
        "주민 ９００１０１１２３４５６７",
    ],
)
def test_minor31_rrn_variants_masked(text: str) -> None:
    out = redact_text(text)
    assert "[REDACTED:rrn]" in out, out
    assert not any(ch.isdigit() for ch in out), out


def test_minor31_positions_kept_with_fullwidth() -> None:
    text = "앞 ０１０－１２３４－５６７８ 뒤"
    assert redact_text(text) == "앞 [REDACTED:phone] 뒤"


@pytest.mark.parametrize(
    "text",
    [
        "기준일 2026–10–09, D-3",
        "공급금액 573,000,000원 (5억 7,300만원)",
        "전용 84.97㎡ 1,573세대 2028-03 입주",
        "법정동코드 2818510600",
        "기간 2026-10-01 – 2026-10-09",
        "블록 AA13-1 외 2필지",
        "세대수 ８４세대",
    ],
)
def test_minor31_public_text_untouched(text: str) -> None:
    assert redact_text(text) == text
