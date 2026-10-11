"""R3g CORE5 — R3 7차 minor 5: ``core.redact`` 누출 변형(리뷰어 스크립트 r7/b/fuzz_redact.py).

이중 인코딩 JSON·소문자/변형 PEM(대시 4개·공백 낀 대시·EC/OPENSSH/ENCRYPTED/PGP·CRLF·``\\n`` 이스케이프·END 불일치·
END 없음)·공백 낀 키 이름(``Secret Key:``·``API Key =``)·전각 콜론·여러 단어 값·키와 값 사이 줄바꿈·``private\\u005fkey``·
백틱·``privateKey``. 보통 글(한국어 공고 문장·'the bearer of …')은 그대로.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.redact import contains_sensitive, redact_obj, redact_text

B64 = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7"
TAIL = "QwErTy7890zxcv"
PEM = f"-----BEGIN PRIVATE KEY-----\n{B64}\n{TAIL}\n-----END PRIVATE KEY-----"
PEM_FRAGS = ("MIIEv", "QwErTy", "zxcv")

CASES: list[tuple[str, str, tuple[str, ...]]] = [
    ("json private_key", json.dumps({"type": "service_account", "private_key": PEM + "\n"}), PEM_FRAGS),
    ("json privateKey", json.dumps({"privateKey": "abc DEF ghi 123"}), ("abc DEF", "ghi 123")),
    ("single-quoted repr", repr({"private_key": "s3cr3t with space"}), ("s3cr3t", "with space")),
    ("escaped quotes", '{"password": "a\\"b c d"}', ("b c d", "a\\")),
    ("double-encoded json", json.dumps(json.dumps({"password": "s3cr3t pw xyz"})), ("s3cr3t", " pw", "xyz")),
    (
        "double-encoded pk",
        json.dumps(json.dumps({"private_key": "abcd efgh ijkl"})),
        ("abcd", "efgh", "ijkl"),
    ),
    ("triple-encoded", json.dumps(json.dumps(json.dumps({"api_key": "zq9 ww8 vv7"}))), ("zq9", "ww8", "vv7")),
    ("pretty multiline json", json.dumps({"private_key": "line1 line2"}, indent=2), ("line1", "line2")),
    ("key newline value", '{"private_key":\n   "tok tok tok"}', ("tok",)),
    ("EC PEM", PEM.replace("PRIVATE KEY", "EC PRIVATE KEY"), PEM_FRAGS),
    ("OPENSSH PEM", PEM.replace("PRIVATE KEY", "OPENSSH PRIVATE KEY"), PEM_FRAGS),
    ("ENCRYPTED PEM", PEM.replace("PRIVATE KEY", "ENCRYPTED PRIVATE KEY"), PEM_FRAGS),
    (
        "PGP",
        f"-----BEGIN PGP PRIVATE KEY BLOCK-----\nVersion: X\n\nlQOYBF{B64}\n-----END PGP PRIVATE KEY BLOCK-----",
        ("lQOY", "MIIEv"),
    ),
    ("lowercase pem", PEM.lower(), tuple(f.lower() for f in PEM_FRAGS)),
    (
        "spaced dashes",
        PEM.replace("-----BEGIN ", "----- BEGIN ").replace("KEY-----\n", "KEY -----\n", 1),
        PEM_FRAGS,
    ),
    ("4 dashes", PEM.replace("-----", "----"), PEM_FRAGS),
    ("CRLF pem", PEM.replace("\n", "\r\n"), PEM_FRAGS),
    ("escaped-newline pem", PEM.replace("\n", "\\n"), PEM_FRAGS),
    ("mismatched END", PEM.replace("END PRIVATE", "END RSA PRIVATE") + "\nafter text keep", PEM_FRAGS),
    ("truncated pem", "log: " + PEM.split("\n-----END")[0], PEM_FRAGS),
    (
        "truncated lowercase pem",
        "log: " + PEM.lower().split("\n-----end")[0],
        tuple(f.lower() for f in PEM_FRAGS),
    ),
    ("Secret Key spaced name", "Secret Key: AbCdEf123456", ("AbCdEf", "123456")),
    ("API Key spaced", "API Key = AbCdEf123456", ("AbCdEf",)),
    ("Private Key spaced", "Private Key: k9k9k9k9 m8m8", ("k9k9", "m8m8")),
    ("unquoted multiword", "password = s3cr3t pw", ("s3cr3t", " pw")),
    ("unquoted multiword then field", "password=s3cr3t pw user=kim", ("s3cr3t", " pw")),
    ("yaml block", "private_key: |\n  " + PEM.replace("\n", "\n  "), PEM_FRAGS),
    ("private_key_id", '"private_key_id": "0123456789abcdef0123"', ("0123456789abcdef",)),
    ("unicode-escaped key", '{"private\\u005fkey": "abcd efgh"}', ("abcd", "efgh")),
    ("backtick", "password=`abc def`", ("abc", "def")),
    ("fullwidth colon", "password：abcdefgh123", ("abcdefgh123",)),
    ("fullwidth colon spaced", "API Key ： zz11 yy22", ("zz11", "yy22")),
    ("crlf between key and value", 'password:\r\n  "pp1 qq2"', ("pp1", "qq2")),
]


@pytest.mark.parametrize(("name", "text", "frags"), CASES, ids=[c[0] for c in CASES])
def test_reviewer_variants_do_not_leak(name: str, text: str, frags: tuple[str, ...]) -> None:
    out = redact_text(text)
    assert "[REDACTED" in out, (name, out)
    for frag in frags:
        assert frag not in out, (name, frag, out)
    assert contains_sensitive(text), name


def test_mismatched_end_keeps_following_text() -> None:
    out = redact_text(PEM.replace("END PRIVATE", "END RSA PRIVATE") + "\nafter text keep")
    assert "after text keep" in out and "MIIEv" not in out


def test_public_certificate_is_kept() -> None:
    cert = f"-----BEGIN CERTIFICATE-----\n{B64}\n-----END CERTIFICATE-----"
    assert redact_text(cert) == cert


@pytest.mark.parametrize(
    "key",
    ["privateKey", "PrivateKey", "private_key", "Private Key", "private-key", "API Key", "private_key_id"],
)
def test_redact_obj_private_key_names(key: str) -> None:
    out = redact_obj({key: "x y z", "region": "인천"})
    assert out[key] == "[REDACTED:key]", out
    assert out["region"] == "인천"


@pytest.mark.parametrize(
    "text",
    [
        "분양가 할인 10,000,000원",
        "비밀번호 변경 안내",
        "the bearer of this letter",
        "Bearer bonds are old",
        "입주자모집공고 2026-10-09 공급금액 512,000,000원 (계약금 10%)",
        "청약 접수: 2026-10-20 ~ 2026-10-22, 당첨자 발표: 2026-10-29",
        "secretariat office notice",
        "tokenization of text",
        "BEGIN 공고문 END",
        "-----BEGIN CERTIFICATE-----",
        "key: value 형식의 일반 설정",
    ],
)
def test_ordinary_text_unchanged(text: str) -> None:
    assert redact_text(text) == text
    assert not contains_sensitive(text)


# ---------------------------------------------------------------- 성질 시험

_VALUE = st.text(
    alphabet="abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789 ", min_size=6, max_size=30
).filter(lambda v: v.strip() == v and "  " not in v and sum(c.isalnum() for c in v) >= 6)
_KEYS = st.sampled_from(
    ["password", "Password", "PASSWORD", "api_key", "API Key", "Secret Key", "secret_key", "private_key",
     "privateKey", "Private Key", "client_secret", "access-token", "x-api-key", "passwd", "auth token"]
)  # fmt: skip


def _templates(key: str, value: str) -> list[str]:
    return [
        json.dumps({key: value}),
        json.dumps(json.dumps({key: value})),
        json.dumps({"outer": json.dumps({key: value})}),
        json.dumps({key: value}, indent=2),
        f"{key}: {value}",
        f"{key} = {value}",
        f"{key}={value}",
        f"{key}：{value}",
        f"{key} ： {value}",
        f"[{key}] '{value}'".replace("] ", "]: "),
        f'{key}: "{value}"',
        f"{key}=`{value}`",
        f"log line {key}={value}\nnext line",
    ]


@settings(max_examples=300, deadline=None)
@given(_KEYS, _VALUE)
def test_secret_value_never_survives(key: str, value: str) -> None:
    for text in _templates(key, value):
        out = re.sub(r"\[REDACTED:\w+\]", "\x01", redact_text(text))  # 표식 글자('secret')는 누출이 아니다
        frame = text.replace(value, "\x00")  # 틀(키 이름·JSON 기호)에 우연히 있는 낱말은 누출이 아니다
        # R3h: 값이 키 이름 안에 있으면(키 'access-token' · 값 'access') 출력의 키 이름에 남은 글자는 누출이 아니다
        rest = out.replace(key, "\x02")
        for word in value.split(" "):
            if len(word) >= 4 and word not in frame:
                assert word not in rest, (text, out)
        assert value not in rest, (text, out)
