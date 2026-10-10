"""R3d CORE2 — 4차 리뷰 보안 minor: redact 가 snake_case 비밀 키·짧은 Bearer 토큰을 가린다."""

from __future__ import annotations

import pytest

from app.core.redact import contains_sensitive, redact_text


@pytest.mark.parametrize(
    "text",
    [
        "client_secret=abcdEFGH1234",
        "access_token: zz9abcdef",
        'refresh_token="qwe123rty"',
        "X_API_KEY=k3y-v4lue",
        "Bearer ab12",
        "Bearer 7a-9",
    ],
)
def test_snake_case_keys_and_short_bearer_are_redacted(text: str) -> None:
    out = redact_text(text)
    assert "[REDACTED" in out, out
    assert contains_sensitive(text)


@pytest.mark.parametrize(
    "text", ["the bearer of news", "Bearer abc", "분양가 할인 10,000,000원", "token 없음"]
)
def test_plain_words_stay(text: str) -> None:
    assert redact_text(text) == text
