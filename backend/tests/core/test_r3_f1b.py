"""R3 수정 F1b — core: minor 10(canonical JSON) · minor 12(redact 보강) ·
minor 17(http 내부망 차단·리다이렉트)."""

from __future__ import annotations

import asyncio
import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core.http import AsyncHttpClient, HttpClient
from app.core.protocols import canonical_hash_json, canonical_value, input_hash
from app.core.redact import find_sensitive, redact_obj, redact_text, sensitive_int_kind
from app.core.settings import Settings
from app.judge import cache
from app.judge.guard import check_payload, default_secrets

REPO = Path(__file__).resolve().parents[3]

# ====================================================================== minor 10 canonical JSON


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ({"n": 1}, {"n": 1.0}),
        ({"n": 1}, {"n": Decimal("1.00")}),
        ({"p": 0.5}, {"p": Decimal("0.5")}),
        ({"p": [0.25, 2]}, {"p": (Decimal("0.250"), 2.0)}),
        ({"z": 0}, {"z": -0.0}),
    ],
)
def test_minor10_same_value_same_hash(a: dict[str, Any], b: dict[str, Any]) -> None:
    assert input_hash("noul", "p", a, "v") == input_hash("noul", "p", b, "v")
    assert canonical_hash_json(a) == canonical_hash_json(b)


def test_minor10_bool_is_not_number_and_order_is_irrelevant() -> None:
    assert input_hash("screen", "p", {"x": True}, "v") != input_hash("screen", "p", {"x": 1}, "v")
    assert canonical_hash_json({"b": 1, "a": "가"}) == '{"a":"가","b":1}'  # ensure_ascii=False, 키 정렬


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, Decimal("NaN"), Decimal("Infinity")])
def test_minor10_nan_and_infinity_are_rejected(bad: Any) -> None:
    with pytest.raises(ValueError):
        input_hash("noul", "p", {"x": bad}, "v")
    with pytest.raises(ValueError):
        canonical_value([bad])


def test_minor10_decimal_payload_length_no_type_error() -> None:
    assert cache.payload_length({"p": Decimal("0.75")}) == len('{"p":0.75}')
    with pytest.raises(TypeError):
        canonical_value({"x": object()})


def test_minor10_recorded_fixture_hashes_unchanged() -> None:
    """정준화는 정수와 같은 실수만 바꾼다 → 녹화 132개의 input_hash 는 그대로(픽스처 재생성 불필요)."""
    fixture = REPO / "contracts" / "fixtures" / "incheon_gimpo_2026-10-08" / "judgments"
    version = json.loads((fixture / "_meta.json").read_text(encoding="utf-8"))["adapter_version"]
    index = json.loads((fixture / "_index.json").read_text(encoding="utf-8"))
    assert len(index) == 132
    for e in index:
        assert input_hash(e["tool"], e["purpose"], e["payload"], version) == e["input_hash"], e["file"]


# ====================================================================== minor 12 redact


@pytest.mark.parametrize(
    "text",
    ["문의 +82 10-1234-5678", "문의 +82-10-1234-5678", "문의 +821012345678", "본사 +82 2-123-4567",
     "문의 +82 (0)10 1234 5678"],
)  # fmt: skip
def test_minor12_international_phone(text: str) -> None:
    out = redact_text(text)
    assert "[REDACTED:phone]" in out and "1234" not in out


@pytest.mark.parametrize("text", ["주민번호 900101 1234567", "주민번호 900101 - 1234567", "900101–1234567"])
def test_minor12_rrn_with_space_or_dash_variants(text: str) -> None:
    assert [f.kind for f in find_sensitive(text)] == ["rrn"]


def test_minor12_integers() -> None:
    assert sensitive_int_kind(9001011234567) == "rrn"
    assert sensitive_int_kind(821012345678) == "phone"
    assert sensitive_int_kind(1012345678, "phone") == "phone"  # 앞자리 0 이 빠진 휴대전화
    assert sensitive_int_kind(1012345678, "price_won") is None  # 10억대 금액은 그대로
    assert sensitive_int_kind(770_000_000) is None and sensitive_int_kind(True) is None
    out = redact_obj({"contact": {"tel": 1012345678}, "rrn": 9001011234567, "price": 1012345678})
    assert out == {"contact": {"tel": "[REDACTED:phone]"}, "rrn": "[REDACTED:rrn]", "price": 1012345678}


def test_minor12_news_secret_part_alone_and_decoded_key() -> None:
    news = "myClientId123:mySecretValue456"
    assert (
        redact_text("X-NCP-APIGW-API-KEY: mySecretValue456", [news])
        == "X-NCP-APIGW-API-KEY: [REDACTED:secret]"
    )
    encoded = "AbC%2BdEf%2F123%3D%3D"  # 포털이 주는 인코딩 키를 그대로 .env 에 넣은 경우
    assert "AbC+dEf/123==" not in redact_text("serviceKey AbC+dEf/123== 사용", [encoded])


def test_minor12_database_url_password() -> None:
    text = "connect failed: postgresql+psycopg://app:s3cr3t-pw@db:5432/subs"
    out = redact_text(text)
    assert "s3cr3t-pw" not in out and "postgresql+psycopg://app:" in out and "@db:5432" in out


def test_minor12_guard_blocks_int_phone_and_database_password(tmp_path: Path) -> None:
    res = check_payload({"evidence": {"tel": 1012345678}, "units": 1573}, secrets=[])
    assert res.kinds() == ["phone"] and res.findings[0].path == "$.evidence.tel"
    assert check_payload({"price_won": 1012345678}, secrets=[]).ok
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url="postgresql+psycopg://app:pw-Only-In-Url9@db:5432/subs",
        raw_dir=tmp_path,
    )
    secrets = default_secrets(settings)
    assert "pw-Only-In-Url9" in secrets
    assert check_payload({"text": "비밀 pw-Only-In-Url9"}, secrets=secrets).kinds() == ["secret"]


# ====================================================================== minor 17 http


def _client(handler: Any, **kw: Any) -> HttpClient:
    opts: dict[str, Any] = {
        "respect_robots": False,
        "max_retries": 0,
        "jitter": 0.0,
        "rate_per_host": 1000.0,
        "transport": httpx.MockTransport(handler),
    }
    opts.update(kw)
    return HttpClient(**opts)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/admin",
        "http://localhost/x",
        "http://api.localhost/x",
        "http://10.0.0.5/",
        "http://192.168.0.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0/",
    ],
)
def test_minor17_private_and_localhost_are_blocked_without_request(url: str) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text="ok")

    with _client(handler) as c:
        r = c.get(url)
    assert seen == [] and not r.ok and r.error_kind == "blocked_host" and r.attempts == 0
    assert (r.error or "").startswith("blocked_host")


def test_minor17_redirect_target_is_rechecked() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "public.example.test":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/internal"})
        return httpx.Response(200, text="internal secret")

    with _client(handler) as c:
        r = c.get("https://public.example.test/start")
    assert seen == ["https://public.example.test/start"]  # 내부 주소로는 요청하지 않았다
    assert not r.ok and r.error_kind == "blocked_host" and r.content == b""


def test_minor17_dns_resolving_to_private_is_blocked_and_public_passes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    def resolver(host: str) -> list[str]:
        return {"intranet.corp-internal.kr": ["10.1.2.3"], "www.public-site.kr": ["93.184.216.34"]}.get(
            host, []
        )

    with _client(handler, resolver=resolver) as c:
        assert c.get("http://intranet.corp-internal.kr/").error_kind == "blocked_host"
        assert c.get("http://www.public-site.kr/").ok


def test_minor17_allow_private_for_tests() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    with _client(handler, allow_private=True) as c:
        assert c.get("http://127.0.0.1:8000/").ok


def test_minor17_async_client_blocks_too() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example.test":
            return httpx.Response(301, headers={"location": "http://192.168.1.1/"})
        return httpx.Response(200)

    async def run() -> tuple[str | None, str | None]:
        async with AsyncHttpClient(
            respect_robots=False, max_retries=0, jitter=0.0, rate_per_host=1000.0,
            transport=httpx.MockTransport(handler),
        ) as c:  # fmt: skip
            a = await c.get("http://localhost/")
            b = await c.get("https://public.example.test/")
            return a.error_kind, b.error_kind

    assert asyncio.run(run()) == ("blocked_host", "blocked_host")
