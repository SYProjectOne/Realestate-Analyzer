"""R3f CORE4 — 6차 리뷰 minor 9: ``redact.py`` 가 PEM 본문·JSON ``"private_key"`` 값의 **첫 토큰만** 가렸다.

| 리뷰 | 테스트 |
| --- | --- |
| m9 PEM 여러 줄 본문 | ``test_m9_pem_private_key_body_is_fully_redacted`` |
| m9 JSON ``"private_key": "…"`` 값 전체(이스케이프 줄바꿈·공백 포함) | ``test_m9_json_quoted_secret_value_is_fully_redacted`` |
| m9 dict 키 ``private_key`` | ``test_m9_redact_obj_private_key_dict`` |
| 회귀: 공개 인증서·일반 글은 그대로 | ``test_m9_public_text_unchanged`` |
"""

# ruff: noqa: E501

from __future__ import annotations

import json

import pytest

BODY = ["MIIEvQIBADANBgkqhkiG9w0BAQEFAASC", "AbcdEf+/0123456789xyzXYZ==", "TAILpart9876"]


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
@pytest.mark.parametrize("kind", ["PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY", "OPENSSH PRIVATE KEY"])
def test_m9_pem_private_key_body_is_fully_redacted(kind: str, nl: str) -> None:
    from app.core.redact import contains_sensitive, redact_text

    pem = nl.join([f"-----BEGIN {kind}-----", *BODY, f"-----END {kind}-----"])
    text = f"key loaded: {pem}{nl}next line ok"
    out = redact_text(text)
    assert not any(b in out for b in BODY), out
    assert "[REDACTED:secret]" in out and out.endswith("next line ok"), out
    assert contains_sensitive(pem)


def test_m9_pem_truncated_without_end_line() -> None:
    """로그가 잘려 END 줄이 없어도 본문을 가린다."""
    from app.core.redact import redact_text

    out = redact_text("-----BEGIN PRIVATE KEY-----\n" + "\n".join(BODY))
    assert not any(b in out for b in BODY), out


def test_m9_json_quoted_secret_value_is_fully_redacted() -> None:
    from app.core.redact import redact_text

    pem = "\n".join(["-----BEGIN PRIVATE KEY-----", *BODY, "-----END PRIVATE KEY-----", ""])
    doc = json.dumps({"type": "service_account", "private_key": pem, "client_email": "x"})
    out = redact_text(doc)
    assert not any(b in out for b in BODY), out
    assert '"type": "service_account"' in out, out
    for text, secret_parts in [
        ('{"private_key": "abc def ghi", "x": 1}', ["abc", "def", "ghi"]),
        ("{'private_key': 'abc def ghi'}", ["abc", "def", "ghi"]),
        ("password = 's3cr3t pw'", ["s3cr3t", " pw"]),
        ('"client_secret": "with \\"escaped\\" quote tail9"', ["with", "escaped", "tail9"]),
        ('"private_key": "unterminated value tail8', ["unterminated", "tail8"]),
    ]:
        red = redact_text(text)
        assert not any(p in red for p in secret_parts), (text, red)
    assert redact_text('{"private_key": "abc def", "x": 1}').endswith('"x": 1}')


def test_m9_redact_obj_private_key_dict() -> None:
    from app.core.redact import redact_obj

    out = redact_obj({"private_key": "abc def ghi", "nested": {"privateKey": "zz yy"}, "n": 3})
    assert out == {"private_key": "[REDACTED:key]", "nested": {"privateKey": "[REDACTED:key]"}, "n": 3}


def test_m9_public_text_unchanged() -> None:
    from app.core.redact import redact_text

    for t in (
        "-----BEGIN CERTIFICATE-----\nMIIBszCCAVmgAwIBAgIU\n-----END CERTIFICATE-----",
        "token_type=bearer",
        '{"name": "단지 이름 그대로", "price": 100}',
        "the bearer of news",
    ):
        assert redact_text(t) == t
