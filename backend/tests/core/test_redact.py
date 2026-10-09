from __future__ import annotations

import pytest

from app.core.redact import contains_sensitive, find_sensitive, redact_obj, redact_text

SECRET = "AbC+dEf/123=="  # 공공데이터포털 키처럼 + / = 가 섞인 값


@pytest.mark.parametrize(
    "text",
    [
        "연락처 010-1234-5678",
        "연락처 01012345678",
        "연락처 010 1234 5678",
        "사무실 02-123-4567",
        "사무실 031-1234-5678",
        "대표번호 1588-1234",
    ],
)
def test_phone_masked(text: str) -> None:
    out = redact_text(text)
    assert "[REDACTED:phone]" in out
    assert not any(ch.isdigit() for ch in out)
    assert [f.kind for f in find_sensitive(text)] == ["phone"]


@pytest.mark.parametrize("text", ["주민번호 900101-1234567", "rrn 9001012234567"])
def test_rrn_masked(text: str) -> None:
    out = redact_text(text)
    assert "[REDACTED:rrn]" in out
    assert "1234567" not in out and "2234567" not in out


def test_email_masked() -> None:
    out = redact_text("문의 someone.name+tag@example.co.kr 로")
    assert out == "문의 [REDACTED:email] 로"


def test_secret_values_masked_including_url_encoded() -> None:
    text = f"key={SECRET} enc=AbC%2BdEf%2F123%3D%3D"
    out = redact_text(text, secrets=[SECRET])
    assert SECRET not in out
    assert "AbC%2BdEf%2F123%3D%3D" not in out
    assert out.count("[REDACTED:secret]") == 2


def test_short_secrets_ignored() -> None:
    assert redact_text("a b c", secrets=["a", ""]) == "a b c"


def test_url_query_keys_masked() -> None:
    url = "https://apis.data.go.kr/x?serviceKey=SOMEKEY123&LAWD_CD=11110&api_key=zzz&token=t0k"
    out = redact_text(url)
    assert "SOMEKEY123" not in out
    assert "zzz" not in out
    assert "t0k" not in out
    assert "LAWD_CD=11110" in out


@pytest.mark.parametrize(
    "text",
    [
        "기준일 2026-10-09, D-3",
        "공급금액 573,000,000원 (5억 7,300만원)",
        "전용 84.97㎡ 1,573세대 2028-03 입주",
        "법정동코드 2818510600",
        "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancDetail.do?houseManageNo=2026000123",
    ],
)
def test_public_text_untouched(text: str) -> None:
    assert redact_text(text) == text
    assert not contains_sensitive(text)


def test_contains_sensitive_with_secret() -> None:
    assert contains_sensitive(f"x {SECRET} y", secrets=[SECRET])
    assert [f.kind for f in find_sensitive(f"x {SECRET} y", secrets=[SECRET])] == ["secret"]


def test_redact_obj_nested_and_sensitive_keys() -> None:
    obj = {
        "msg": "call 010-1111-2222",
        "nested": [{"Authorization": "Bearer abc"}, ("x@y.com", 3)],
        "api_token": "plain-value",
        "n": 5,
        "ok": True,
        "none": None,
    }
    out = redact_obj(obj)
    assert out["msg"] == "call [REDACTED:phone]"
    assert out["nested"][0]["Authorization"] == "[REDACTED:key]"
    assert out["nested"][1] == ["[REDACTED:email]", 3]
    assert out["api_token"] == "[REDACTED:key]"
    assert out["n"] == 5 and out["ok"] is True and out["none"] is None
