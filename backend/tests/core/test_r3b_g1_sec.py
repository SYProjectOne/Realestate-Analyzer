"""R3b G1 — R3_REVIEW2 F1b 보안 잔여(core): SSRF(특수 대역·DNS rebinding·리다이렉트·prod 허용 거부) ·
redact 잔여(82-10-…·Bearer·redis://:pw@·URL 인코딩 비밀값)."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpcore
import httpx
import pytest
from pydantic import SecretStr

from app.core.http import (
    AsyncHttpClient,
    HttpClient,
    PinnedAsyncTransport,
    PinnedTransport,
    PrivateHostsInProdError,
    allow_private_hosts,
    ip_blocked,
)
from app.core.redact import find_sensitive, redact_text
from app.core.settings import Settings, set_settings

PUBLIC_IP = "93.184.216.34"

# ====================================================================== 1a 특수 대역


@pytest.mark.parametrize(
    "ip",
    [
        "100.64.0.1",  # CGNAT 100.64.0.0/10
        "100.127.255.254",
        "0.1.2.3",  # 0.0.0.0/8
        "192.0.0.8",  # IETF 192.0.0.0/24
        "198.18.0.1",  # 벤치마크 198.18.0.0/15
        "198.19.255.1",
        "240.0.0.1",  # 예약 240.0.0.0/4
        "255.255.255.255",
        "224.0.0.1",  # 멀티캐스트
        "192.0.2.1",  # 문서용(TEST-NET)
        "fc00::1",  # IPv6 ULA fc00::/7
        "fd12:3456::1",
        "fe80::1",  # 링크로컬
        "fe80::1%eth0",
        "fec0::1",  # 폐지된 site-local
        "::ffff:10.0.0.1",  # IPv4-mapped 사설
        "::ffff:100.64.0.1",  # IPv4-mapped CGNAT
        "64:ff9b::a00:1",  # NAT64 가 10.0.0.1 을 감쌈
        "64:ff9b::7f00:1",  # NAT64 → 127.0.0.1
        "64:ff9b::6440:1",  # NAT64 → 100.64.0.1
        "2002:a00:1::1",  # 6to4 → 10.0.0.1
        "::127.0.0.1",  # IPv4-compatible(폐지)
        "ff02::1",  # IPv6 멀티캐스트
    ],
)
def test_f1b_special_ranges_blocked(ip: str) -> None:
    assert ip_blocked(ip)


@pytest.mark.parametrize(
    "ip", [PUBLIC_IP, "8.8.8.8", "2606:4700:4700::1111", "64:ff9b::808:808", "::ffff:8.8.8.8"]
)
def test_f1b_public_addresses_pass(ip: str) -> None:
    assert not ip_blocked(ip)


@pytest.mark.parametrize("url", ["http://100.64.0.1/", "http://[fd00::1]/", "http://[64:ff9b::a00:1]/"])
def test_f1b_cgnat_and_v6_literals_blocked_without_request(url: str) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200)

    with HttpClient(
        respect_robots=False, max_retries=0, jitter=0.0, transport=httpx.MockTransport(handler)
    ) as c:
        r = c.get(url)
    assert seen == [] and r.error_kind == "blocked_host" and r.attempts == 0


def test_f1b_dns_to_cgnat_blocked() -> None:
    with HttpClient(
        respect_robots=False,
        max_retries=0,
        jitter=0.0,
        transport=httpx.MockTransport(lambda r: httpx.Response(200)),
        resolver=lambda h: ["100.100.1.1"],
    ) as c:
        assert c.get("http://carrier-nat.corp.kr/").error_kind == "blocked_host"


# ====================================================================== 1b DNS rebinding


class _FakeStream(httpcore.NetworkStream):
    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return b""

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        pass

    def close(self) -> None:
        pass


class _RecordingBackend(httpcore.NetworkBackend):
    """연결 대상 호스트를 기록한다. ``forward`` 가 있으면 그 로컬 포트로 실제 연결한다."""

    def __init__(self, forward: int | None = None) -> None:
        self.hosts: list[str] = []
        self._forward = forward

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        self.hosts.append(host)
        if self._forward is not None:
            return httpcore.SyncBackend().connect_tcp("127.0.0.1", self._forward, timeout=timeout)
        return _FakeStream()


class _Rebinder:
    """첫 질의는 공개 IP, 그다음부터는 내부 IP 를 주는 공격자 DNS."""

    def __init__(self, first: str = PUBLIC_IP, then: str = "127.0.0.1") -> None:
        self.calls: list[str] = []
        self._first, self._then = first, then

    def __call__(self, host: str) -> list[str]:
        self.calls.append(host)
        return [self._first] if len(self.calls) == 1 else [self._then]


class _Seen(BaseHTTPRequestHandler):
    seen: list[tuple[str, str | None]]

    def do_GET(self) -> None:
        type(self).seen.append((self.path, self.headers.get("Host")))
        if self.path.startswith("/redirect?to="):
            self.send_response(302)
            self.send_header("Location", self.path.split("=", 1)[1])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"internal"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def local_server() -> Iterator[tuple[int, list[tuple[str, str | None]]]]:
    seen: list[tuple[str, str | None]] = []
    handler = type("H", (_Seen,), {"seen": seen})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], seen
    finally:
        server.shutdown()
        server.server_close()


def test_f1b_dns_rebinding_connect_time_check_blocks(
    local_server: tuple[int, list[tuple[str, str | None]]],
) -> None:
    """검사 때는 공개 IP, 연결 때는 127.0.0.1 → 연결 시점 검사가 막는다(내부 서버는 요청을 못 받는다)."""
    port, seen = local_server
    dns = _Rebinder()
    with HttpClient(
        respect_robots=False, max_retries=2, jitter=0.0, resolver=dns, sleep=lambda _s: None
    ) as c:
        r = c.get(f"http://rebind.attacker-dns.kr:{port}/admin")
    assert len(dns.calls) >= 2  # 사전 검사 + 연결 시점
    assert seen == []
    assert r.error_kind == "blocked_host" and not r.ok and r.attempts == 1  # 재시도하지 않는다


def test_f1b_pinned_transport_connects_to_validated_ip_with_original_host(
    local_server: tuple[int, list[tuple[str, str | None]]],
) -> None:
    """연결은 검증한 IP 로(이름으로 다시 풀지 않는다), Host 헤더는 원래 이름 그대로."""
    port, seen = local_server
    backend = _RecordingBackend(forward=port)
    resolved: list[str] = []

    def resolver(host: str) -> list[str]:
        resolved.append(host)
        return [PUBLIC_IP]

    with httpx.Client(transport=PinnedTransport(resolver, inner=backend)) as client:
        resp = client.get(f"http://www.public-site.kr:{port}/page")
    assert resp.status_code == 200 and resp.content == b"internal"
    assert backend.hosts == [PUBLIC_IP] and resolved == ["www.public-site.kr"]
    assert seen == [("/page", f"www.public-site.kr:{port}")]


def test_f1b_pinned_transport_any_private_answer_blocks() -> None:
    backend = _RecordingBackend()
    transport = PinnedTransport(lambda h: [PUBLIC_IP, "10.0.0.7"], inner=backend)
    with httpx.Client(transport=transport) as client, pytest.raises(httpx.RequestError, match="blocked_host"):
        client.get("http://mixed.example.com/")
    assert backend.hosts == []


def test_f1b_pinned_transport_unresolvable_is_connect_error() -> None:
    backend = _RecordingBackend()
    with (
        httpx.Client(transport=PinnedTransport(lambda h: [], inner=backend)) as client,
        pytest.raises(httpx.ConnectError),
    ):
        client.get("http://nx.example.com/")
    assert backend.hosts == []


def test_f1b_pinned_transport_tries_validated_ips_in_order() -> None:
    class FailFirst(_RecordingBackend):
        def connect_tcp(self, host: str, port: int, *a: Any, **kw: Any) -> httpcore.NetworkStream:
            self.hosts.append(host)
            if len(self.hosts) == 1:
                raise httpcore.ConnectError("refused")
            raise httpcore.ConnectTimeout("stop here")

    backend = FailFirst()
    transport = PinnedTransport(lambda h: ["1.1.1.1", "8.8.8.8"], inner=backend)
    with httpx.Client(transport=transport) as client, pytest.raises(httpx.ConnectTimeout):
        client.get("http://two.example.com/")
    assert backend.hosts == ["1.1.1.1", "8.8.8.8"]


def test_f1b_async_rebinding_blocked(local_server: tuple[int, list[tuple[str, str | None]]]) -> None:
    port, seen = local_server
    dns = _Rebinder()

    async def run() -> str | None:
        async with AsyncHttpClient(respect_robots=False, max_retries=0, jitter=0.0, resolver=dns) as c:
            return (await c.get(f"http://rebind.attacker-dns.kr:{port}/")).error_kind

    assert asyncio.run(run()) == "blocked_host" and seen == []


def test_f1b_async_pinned_transport_connects_to_validated_ip() -> None:
    class Backend(httpcore.AsyncNetworkBackend):
        def __init__(self) -> None:
            self.hosts: list[str] = []

        async def connect_tcp(self, host: str, port: int, *a: Any, **kw: Any) -> httpcore.AsyncNetworkStream:
            self.hosts.append(host)
            raise httpcore.ConnectTimeout("stop")

    backend = Backend()

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=PinnedAsyncTransport(lambda h: [PUBLIC_IP], inner=backend)
        ) as c:
            with pytest.raises(httpx.ConnectTimeout):
                await c.get("https://www.public-site.kr/")

    asyncio.run(run())
    assert backend.hosts == [PUBLIC_IP]


def test_f1b_redirect_target_rechecked_at_connect_time(
    local_server: tuple[int, list[tuple[str, str | None]]],
) -> None:
    """리다이렉트 대상 이름이 훅 검사 땐 공개 IP, 연결 땐 내부 IP 로 풀려도 연결 시점 검사가 막는다."""
    port, seen = local_server
    hop = _Rebinder(first=PUBLIC_IP, then="10.0.0.5")

    def resolver(host: str) -> list[str]:
        return hop(host) if host == "hop.example.com" else [PUBLIC_IP]

    backend = _RecordingBackend(forward=port)  # 모든 검증 IP 연결을 로컬 서버로 보낸다(오프라인)
    with HttpClient(
        respect_robots=False,
        max_retries=0,
        jitter=0.0,
        resolver=resolver,
        transport=PinnedTransport(resolver, inner=backend),
    ) as c:
        r = c.get(f"http://start.example.com:{port}/redirect?to=http://hop.example.com:{port}/internal")
    assert [path for path, _ in seen] == [f"/redirect?to=http://hop.example.com:{port}/internal"]
    assert backend.hosts == [PUBLIC_IP]  # 리다이렉트 대상으로는 연결하지 않았다
    assert hop.calls == ["hop.example.com", "hop.example.com"]  # 훅 검사 + 연결 시점
    assert r.error_kind == "blocked_host" and not r.ok


# ====================================================================== 1d prod 에서 내부망 허용 거부


def _prod(**kw: Any) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="prod",
        api_token=SecretStr("tok-prod-123456"),
        judge_adapter="jev",
        database_url="postgresql+psycopg://sa:pw@db:5432/subscription",  # prod 는 SQLite 거부(D11-9)
        **kw,
    )


def test_f1b_prod_refuses_allow_private_from_settings() -> None:
    set_settings(_prod(http_allow_private_hosts=True))
    try:
        with pytest.raises(PrivateHostsInProdError, match="ENV=prod"):
            allow_private_hosts()
        with pytest.raises(PrivateHostsInProdError):
            HttpClient()
        with pytest.raises(PrivateHostsInProdError):
            AsyncHttpClient()
    finally:
        set_settings(None)


def test_f1b_prod_refuses_explicit_allow_private_but_allows_default() -> None:
    set_settings(_prod())
    try:
        with pytest.raises(PrivateHostsInProdError):
            HttpClient(allow_private=True)
        assert allow_private_hosts() is False
        with HttpClient() as c:
            assert c.allow_private is False
    finally:
        set_settings(None)


def test_f1b_dev_allows_allow_private() -> None:
    set_settings(Settings(_env_file=None, env="dev", http_allow_private_hosts=True))  # type: ignore[call-arg]
    try:
        assert allow_private_hosts() is True
        with HttpClient() as c:
            assert c.allow_private is True
    finally:
        set_settings(None)


# ====================================================================== 3 redact 잔여


@pytest.mark.parametrize(
    "text",
    [
        "연락처 82-10-1234-5678",
        "연락처 82 10 1234 5678",
        "연락처 82.10.1234.5678",
        "연락처 +82 10 1234 5678",
        "연락처 +82-10-1234-5678",
        "연락처 +82.10.1234.5678",
        "연락처 0082-10-1234-5678",
        "본사 82-2-123-4567",
    ],
)
def test_f1b_redact_international_phone_without_plus(text: str) -> None:
    out = redact_text(text)
    assert "[REDACTED:phone]" in out and "5678" not in out and "4567" not in out, out


@pytest.mark.parametrize(
    "text", ["공급 82세대 중 10호", "2026-10-12 82-10", "면적 82.10㎡", "분양가 82,100만원"]
)
def test_f1b_redact_international_phone_no_false_positive(text: str) -> None:
    assert redact_text(text) == text


@pytest.mark.parametrize(
    ("text", "token"),
    [
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig-_x", "eyJhbGciOiJIUzI1NiJ9"),
        ("headers={'authorization': 'bearer abc123DEF456ghi'}", "abc123DEF456ghi"),
        ("Authorization: Basic dXNlcjpwYXNzd29yZA==", "dXNlcjpwYXNzd29yZA"),
        ("Authorization: Token tk_live_998877", "tk_live_998877"),
    ],
)
def test_f1b_redact_bearer_and_authorization_values(text: str, token: str) -> None:
    out = redact_text(text)
    assert token not in out and "[REDACTED:secret]" in out, out


def test_f1b_redact_bearer_keeps_plain_prose() -> None:
    text = "the bearer of this notice"
    assert redact_text(text) == text


@pytest.mark.parametrize(
    ("text", "pw", "kept"),
    [
        ("redis://:s3cretPw@cache:6379/0", "s3cretPw", "@cache:6379/0"),
        ("rediss://:p%40ss!word@cache:6380", "p%40ss!word", "@cache:6380"),
        ("postgres://user:pg-pass-1@db:5432/x", "pg-pass-1", "postgres://user:"),
        ("amqp://guest:pa@ss@mq:5672/", "pa@ss", "@mq:5672/"),
    ],
)
def test_f1b_redact_url_userinfo_password(text: str, pw: str, kept: str) -> None:
    out = redact_text(f"connect failed: {text} (retry)")
    assert pw not in out and kept in out and "(retry)" in out, out


def test_f1b_redact_secret_url_encoded_forms() -> None:
    """serviceKey 원문 'AbC+dEf/123==' 이 요청 URL·오류 메시지에 인코딩돼 보여도 가린다."""
    key = "AbC+dEf/123=="
    for shown in [
        "AbC%2BdEf%2F123%3D%3D",  # quote(safe='') · httpx params
        "AbC%2BdEf/123%3D%3D",  # quote() 기본(safe='/')
        "AbC%2bdEf%2f123%3d%3d",  # 소문자 16진
        "AbC%252BdEf%252F123%253D%253D",  # 이중 인코딩
        "AbC dEf/123==",  # '+' 가 공백으로 풀린 경우(unquote_plus)
    ]:
        text = f"GET https://apis.data.go.kr/x/y?numOfRows=10&ServiceKey2={shown} → 500"
        out = redact_text(text, [key])
        assert shown not in out and "[REDACTED:secret]" in out, (shown, out)
        assert "numOfRows=10" in out


def test_f1b_redact_encoded_secret_given_encoded_finds_raw() -> None:
    encoded = "AbC%2BdEf%2F123%3D%3D"
    for shown in ["AbC+dEf/123==", "AbC%2bdEf%2f123%3d%3d"]:
        assert [f.kind for f in find_sensitive(f"key {shown} end", [encoded])] == ["secret"], shown


def test_f1b_redact_secret_regex_chars_safe() -> None:
    key = "a.b*c(d)e[f]+g?"
    assert redact_text(f"x {key} y", [key]) == "x [REDACTED:secret] y"
    assert redact_text("x aXbbc(d)e y", [key]) == "x aXbbc(d)e y"


def test_f1b_redact_many_calls_fast() -> None:
    import time

    secrets = ["AbC+dEf/123==", "myClientId123:mySecretValue456", "pw-Only-In-Url9"]
    text = "로그 한 줄 " * 20 + "AbC%2BdEf%2F123%3D%3D"
    started = time.perf_counter()
    for _ in range(2000):
        redact_text(text, secrets)
    assert time.perf_counter() - started < 3.0
