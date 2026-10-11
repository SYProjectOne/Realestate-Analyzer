"""R3i CORE7 — 9차 리뷰 m17(redact 잔여 — 재현 scratchpad ``r9/r/probe_redact.py``), 규칙 6·13.

| 리뷰 | 테스트 |
| --- | --- |
| camelCase 키(``accessKey=``·``secretKey:``)·``pass:`` | ``test_m17_key_names`` |
| 키 없는 토큰(``sk-ant-…``·``ghp_…``·``github_pat_…``·``xoxb-…``·``AKIA…``·``glpat-…``) | ``test_m17_keyless_tokens`` |
| dict 비밀 키의 정수·실수 값 | ``test_m17_sensitive_key_numeric_values`` |
| 'bearer' 뒤 산문 과잉 가림('the bearer certificates') — 토큰은 그대로 가린다 | ``test_m17_bearer_prose_not_masked``·``test_m17_bearer_tokens_still_masked`` |
"""

from __future__ import annotations

import pytest

from app.core.redact import redact_obj, redact_text


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("accessKey=AKIAABCDEFGHIJKL", "AKIAABCDEFGHIJKL"),
        ("secretKey: AAAABBBBCCCC", "AAAABBBBCCCC"),
        ('{"accessKey": "Zx9QwErTy"}', "Zx9QwErTy"),
        ("pass: hunter22", "hunter22"),
        ("pass=hunter22", "hunter22"),
        ("apiKeyId=abcd1234efgh", "abcd1234efgh"),
        ("clientSecret=s3cr3tvalue", "s3cr3tvalue"),
    ],
)
def test_m17_key_names(text: str, secret: str) -> None:
    out = redact_text(text)
    assert secret not in out and "[REDACTED" in out, out


@pytest.mark.parametrize(
    "text",
    ["monkey: banana", "turkey=roast", "bypass: road", "passenger: 3", "compass=north", "keyword=판정"],
)
def test_m17_key_names_not_overmatched(text: str) -> None:
    assert redact_text(text) == text


@pytest.mark.parametrize(
    "token",
    [
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
        "sk-proj-AbCdEfGhIjKlMnOpQrStUvWx",
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "gho_abcdefghijklmnopqrstuvwxyz0123456789",
        "github_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz",
        "xoxb-1234567890-abcdefghijkl",
        "AKIAABCDEFGHIJKLMNOP",
        "glpat-abcdefghijk12345678",
        "AIzaSyA1234567890abcdefghijklmnopqrstu",
    ],
)
def test_m17_keyless_tokens(token: str) -> None:
    out = redact_text(f"error: upstream said {token} was rejected")
    assert token not in out and "[REDACTED:secret]" in out, out


@pytest.mark.parametrize(
    ("obj", "kept"),
    [
        ({"password": 12345678}, None),
        ({"token": 98765432}, None),
        ({"api_key": 1.5}, None),
        ({"secret": True}, True),  # 참·거짓은 비밀이 아니다(표시)
        ({"max_tokens": 1000}, 1000),  # 개수 키는 그대로
        ({"token_count": 12}, 12),
    ],
)
def test_m17_sensitive_key_numeric_values(obj: dict[str, object], kept: object) -> None:
    out = redact_obj(obj)
    (key, value), = out.items()
    if kept is None:
        assert value == "[REDACTED:key]", out
    else:
        assert value == kept, out


@pytest.mark.parametrize(
    "text",
    ["the bearer certificates were issued", "a bearer instrument is", "this bearer documentation", "The Bearer bonds"],
)
def test_m17_bearer_prose_not_masked(text: str) -> None:
    assert redact_text(text) == text


@pytest.mark.parametrize(
    "text",
    ["auth bearer abcdefghijklmn", "Authorization: Bearer abcdefgh123", "bearer Zx9QwErTyU1234", "curl -H 'bearer abcdefghij'"],
)
def test_m17_bearer_tokens_still_masked(text: str) -> None:
    out = redact_text(text)
    assert "[REDACTED:secret]" in out, out
