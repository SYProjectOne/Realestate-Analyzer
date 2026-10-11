"""R3h CORE6 — 8차 리뷰 minor 14·15(AGENTS 규칙 6·13): redact 우회(재현: scratchpad ``r8/c/redact_probe.py``).

| 리뷰 | 테스트 |
| --- | --- |
| m14 환경변수 꼴(``DATA_GO_KR_KEY=``·``SERVICE_KEY=``·``WEBHOOK_URL=``·``AWS_ACCESS_KEY_ID=``·``credentials=``) | ``test_m14_text_leaks_are_masked`` |
| m14 Cookie/Set-Cookie·단독 JWT·소문자 bearer·Slack webhook·``api%5Fkey=``·``serviceKey%3D``·``;serviceKey=``·``crtfc_key``·``password%3D``·점 키·전각 키 | ``test_m14_text_leaks_are_masked`` |
| m14 쌍 리스트·dict 키 ``key``·``auth``·``signature``·``crtfc_key``·``webhook_url`` | ``test_m14_obj_leaks_are_masked`` |
| m15 설정된 비밀값의 base64(접두 포함)·대문자·공백/줄바꿈/폭 없는 공백 낀 변형 | ``test_m15_configured_secret_variants`` |
| 과잉 가림 없음(평문·'the bearer of'·금액·주소) | ``test_no_over_redaction`` |
"""

# ruff: noqa: E501

from __future__ import annotations

import base64
import json

import pytest

from app.core.redact import redact_obj, redact_text

SECRET = "Zx9kQ2mN7pLw4Rt8"  # 가짜 키
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
HOOK = "XXXXXXXXXXXXXXXXXXXXXXXX"
MARKS = (SECRET, "eyJhbGciOiJIUzI1NiJ9", HOOK, "AKIAIOSFODNN7EXAMPLE", "abcdefghij")


@pytest.mark.parametrize(
    "text",
    [
        f"DATA_GO_KR_KEY={SECRET}",
        f"SERVICE_KEY={SECRET}",
        f"WEBHOOK_URL=https://hooks.slack.com/services/T000/B000/{HOOK}",
        "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
        f"credentials={SECRET}",
        f"Cookie: session={SECRET}",
        f"Set-Cookie: sid={SECRET}; Path=/",
        f"jwt={JWT}",
        f"token {JWT} expired",
        "Authorization header was: bearer abcdefghij",
        "sent bearer abcdefghijkl to upstream",
        f"posting to https://hooks.slack.com/services/T000/B000/{HOOK} failed",
        f"https://api.example.org/x?api%5Fkey={SECRET}",
        f"https://api.example.org/x?serviceKey%3D{SECRET}",
        f"https://api.example.org/x;serviceKey={SECRET}",
        f"https://opendart.fss.or.kr/api/list.json?crtfc_key={SECRET}",
        f"password%3D{SECRET}",
        f"jev.api.key={SECRET}",
        f"ｐａｓｓｗｏｒｄ={SECRET}",
        '{"\\u0070assword": "' + SECRET + '"}',
        '{"\\u0074oken":"' + SECRET + '"}',
    ],
)
def test_m14_text_leaks_are_masked(text: str) -> None:
    out = redact_text(text)
    assert not any(m in out for m in MARKS), out
    assert "[REDACTED" in out


@pytest.mark.parametrize(
    "obj",
    [
        [["password", SECRET]],
        [("Authorization", "Bearer abcdefghijkl")],
        {"crtfc_key": SECRET},
        {"key": SECRET},
        {"auth": SECRET},
        {"signature": SECRET},
        {"sig": SECRET},
        {"webhook_url": f"https://hooks.slack.com/services/T000/B000/{HOOK}"},
    ],
)
def test_m14_obj_leaks_are_masked(obj: object) -> None:
    out = json.dumps(redact_obj(obj), ensure_ascii=False)
    assert not any(m in out for m in (*MARKS, "abcdefghijkl")), out


@pytest.mark.parametrize(
    "text",
    [
        base64.b64encode(f"id:{SECRET}".encode()).decode(),
        base64.b64encode(SECRET.encode()).decode(),
        base64.b64encode(f"xy{SECRET}".encode()).decode(),
        base64.urlsafe_b64encode(f"user1:{SECRET}".encode()).decode(),
        SECRET.upper(),
        SECRET.lower(),
        SECRET[:5] + "​" + SECRET[5:],
        SECRET[:8] + "\n" + SECRET[8:],
        " ".join(SECRET),
    ],
)
def test_m15_configured_secret_variants(text: str) -> None:
    """설정된 비밀값(규칙 6·13): base64(앞에 다른 글자가 붙어도)·대소문자·공백류 낀 변형도 가린다."""
    out = redact_text(f"upstream said: {text} (end)", [SECRET])
    assert "[REDACTED" in out, out
    assert text not in out, out


@pytest.mark.parametrize(
    "text",
    [
        "the bearer of this note",
        "bearer bonds",
        "84A 분양가 할인 1,200,000원 — 공급금액 500,000,000원",
        "인천광역시 연수구 송도동 1-2, 2026-10-09T10:00:00+09:00",
        "key points: price, schedule",
        "monkey=3 turkey=4",
        "job stats: snapshot_id=12 kind=complex",
    ],
)
def test_no_over_redaction(text: str) -> None:
    assert redact_text(text, [SECRET]) == text
