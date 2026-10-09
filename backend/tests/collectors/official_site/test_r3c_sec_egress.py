"""R3c SEC — 출구 프록시·브라우저 검사 보강(R3 3차 리뷰 minor 26~30).

- 26 범위 밖 포트(``:99999``·``:0``)는 예외 없이 403 + 기록
- 27 포트 허용 목록: 공개 웹(80·443)만. 그 밖(22·25·6379·8080 …)은 연결 전 차단·기록
- 28 프록시 인증: 렌더마다 무작위 토큰(Proxy-Authorization Basic). 토큰이 없거나 틀리면 407, 연결 없음
- 29 IPv4/IPv6: 답 전부를 v4 우선으로 정렬해 고정하고, 연결이 실패하면 다음 주소로 폴백
- 30 이름 풀기는 전역 락 밖(호스트별 1회) — 느린 DNS 하나가 다른 호스트 연결을 막지 않는다

프록시는 소켓으로 직접, 포트·인증·폴백은 실제 chromium + 로컬 서버로도 본다.
"""

# ruff: noqa: E501

from __future__ import annotations

import base64
import socket
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

import app.core.http as core_http
from app.collectors.official_site import render as render_mod
from app.collectors.official_site.egress import PUBLIC_WEB_PORTS, EgressProxy
from app.collectors.official_site.render import BrowserGuard, PlaywrightRenderer
from app.core.http import BlockedHostError

PUBLIC = "127.0.0.1"
DEAD = "127.0.0.3"  # 시험실 '공개' 주소지만 아무도 듣지 않는다(연결 거부 → 폴백)
_real_ip_blocked = core_http.ip_blocked


def _lab_ip_blocked(text: str) -> bool:
    return text not in (PUBLIC, DEAD) and _real_ip_blocked(text)


@pytest.fixture
def lab_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core_http, "ip_blocked", _lab_ip_blocked)
    monkeypatch.setattr(render_mod, "ip_blocked", _lab_ip_blocked)


class _Site:
    def __init__(self, host: str = PUBLIC, page: Callable[[], str] | None = None) -> None:
        self.seen: list[str] = []
        self.page = page
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                site.seen.append(self.path)
                is_page = self.path.startswith("/index") and site.page is not None
                body = site.page().encode() if is_page and site.page is not None else b"ok"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8" if is_page else "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer((host, 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def site() -> Iterator[_Site]:
    s = _Site()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def two_sites() -> Iterator[tuple[_Site, _Site]]:
    a, b = _Site(), _Site()
    try:
        yield a, b
    finally:
        a.close()
        b.close()


def _need_chromium() -> None:
    probe = PlaywrightRenderer(allow_private=True, settle_ms=0).render("about:blank")
    if probe.error and ("Executable doesn't exist" in probe.error or "playwright install" in probe.error):
        pytest.skip(f"Playwright chromium 미설치: {probe.error}")


def _to_public(host: str, port: int) -> list[str]:
    return [PUBLIC]


def _auth(proxy: EgressProxy) -> str:
    c = proxy.credentials
    return "Basic " + base64.b64encode(f"{c['username']}:{c['password']}".encode()).decode()


def _raw(proxy: EgressProxy, request: bytes) -> bytes:
    host, port = proxy.server.removeprefix("http://").split(":")
    with socket.create_connection((host, int(port)), timeout=10) as s:
        s.sendall(request)
        out = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            out += chunk
            if b"\r\n\r\n" in out and request.startswith(b"CONNECT"):
                break
    return out


# ====================================================================== 26·27 포트


def test_public_web_ports_are_80_and_443_only() -> None:
    assert frozenset({80, 443}) == PUBLIC_WEB_PORTS


@pytest.mark.parametrize("port", [22, 25, 6379, 8080, 8443, 3306])
def test_proxy_blocks_non_web_ports_before_connecting(port: int) -> None:
    calls: list[tuple[str, int]] = []

    def connect(host: str, p: int) -> list[str]:
        calls.append((host, p))
        return [PUBLIC]

    with EgressProxy(connect) as proxy:
        auth = _auth(proxy)
        tunnel = _raw(proxy, f"CONNECT named.lab:{port} HTTP/1.1\r\nProxy-Authorization: {auth}\r\n\r\n".encode())
        plain = _raw(
            proxy,
            f"GET http://named.lab:{port}/x HTTP/1.1\r\nHost: named.lab\r\nProxy-Authorization: {auth}\r\n\r\n".encode(),
        )
    assert tunnel.startswith(b"HTTP/1.1 403") and plain.startswith(b"HTTP/1.1 403")
    assert calls == []  # 이름 풀기·연결 전에 막았다
    assert len(proxy.blocked) == 2 and all(f"포트 {port}" in b for b in proxy.blocked), proxy.blocked


@pytest.mark.parametrize("target", ["named.lab:99999", "named.lab:0", "named.lab:-1", "named.lab:http"])
def test_proxy_out_of_range_port_is_403_not_exception(target: str) -> None:
    errors: list[BaseException] = []
    old = threading.excepthook
    threading.excepthook = lambda args: errors.append(args.exc_value or Exception())
    try:
        with EgressProxy(_to_public, allowed_ports=None) as proxy:
            auth = _auth(proxy)
            plain = _raw(
                proxy,
                f"GET http://{target}/x HTTP/1.1\r\nHost: named.lab\r\nProxy-Authorization: {auth}\r\n\r\n".encode(),
            )
            tunnel = _raw(proxy, f"CONNECT {target} HTTP/1.1\r\nProxy-Authorization: {auth}\r\n\r\n".encode())
    finally:
        threading.excepthook = old
    assert plain.startswith(b"HTTP/1.1 403"), plain[:60]
    assert tunnel.startswith(b"HTTP/1.1 403"), tunnel[:60]
    assert errors == [] and len(proxy.blocked) == 2


def test_proxy_allowed_ports_explicit(site: _Site) -> None:
    with EgressProxy(_to_public, allowed_ports=frozenset({site.port})) as proxy:
        out = _raw(
            proxy,
            f"GET http://named.lab:{site.port}/a HTTP/1.1\r\nHost: named.lab\r\nProxy-Authorization: {_auth(proxy)}\r\n\r\n".encode(),
        )
    assert b" 200 " in out.split(b"\r\n", 1)[0] and site.seen == ["/a"]


def test_guard_url_reason_blocks_non_web_port_and_bad_port() -> None:
    guard = BrowserGuard(allow_private=False, resolver=lambda h: ["93.184.216.34"])
    assert guard.url_reason("https://www.public-site.kr/") is None
    assert guard.url_reason("http://www.public-site.kr:80/") is None
    for bad in ("http://www.public-site.kr:8080/", "https://www.public-site.kr:6379/x", "http://www.public-site.kr:99999/"):
        reason = guard.url_reason(bad)
        assert reason is not None and reason.startswith("blocked_host"), bad
    assert "포트 8080" in (guard.url_reason("http://www.public-site.kr:8080/") or "")
    # 로컬 시험 서버(allow_private)는 포트 제한 없음 — prod 는 allow_private 자체가 거부된다
    assert BrowserGuard(allow_private=True, resolver=lambda h: []).url_reason("http://127.0.0.1:5173/") is None


def test_render_refuses_main_url_on_non_web_port_before_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    launched: list[str] = []

    def boom(*a: Any, **kw: Any) -> Any:
        launched.append("x")
        raise AssertionError("브라우저를 띄우면 안 된다")

    import playwright.sync_api

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", boom)
    result = PlaywrightRenderer(allow_private=False, resolver=lambda h: ["93.184.216.34"]).render(
        "http://www.public-site.kr:8080/"
    )
    assert (result.error or "").startswith("blocked_host") and "포트 8080" in (result.error or "")
    assert launched == []


def test_real_chromium_blocks_subresource_on_disallowed_port(lab_rules: None, two_sites: tuple[_Site, _Site]) -> None:
    _need_chromium()
    main, other = two_sites
    main.page = lambda: (
        "<!doctype html><html><body><h1>lab</h1>"
        f'<img src="http://cdn.r3c-lab.kr:{main.port}/ok.png">'
        f'<img src="http://cdn.r3c-lab.kr:{other.port}/port.png">'
        "</body></html>"
    )
    renderer = PlaywrightRenderer(
        allow_private=False,
        resolver=lambda h: [PUBLIC],
        settle_ms=200,
        timeout_ms=20_000,
        allowed_ports=frozenset({80, 443, main.port}),
    )
    holder: dict[str, BrowserGuard] = {}
    original = renderer.guard

    def keep() -> BrowserGuard:
        holder["g"] = original()
        return holder["g"]

    renderer.guard = keep  # type: ignore[method-assign]
    result = renderer.render(f"http://site.r3c-lab.kr:{main.port}/index.html")
    assert result.ok, result.error
    assert "/ok.png" in main.seen
    assert other.seen == []  # 허용하지 않는 포트는 요청 자체가 없다
    assert any(f"포트 {other.port}" in b for b in holder["g"].blocked), holder["g"].blocked


# ====================================================================== 28 인증


def test_proxy_requires_per_instance_token(site: _Site) -> None:
    with EgressProxy(_to_public, allowed_ports=None) as a, EgressProxy(_to_public, allowed_ports=None) as b:
        assert a.credentials["password"] != b.credentials["password"]
        assert len(a.credentials["password"]) >= 20
        req = f"GET http://named.lab:{site.port}/x HTTP/1.1\r\nHost: named.lab\r\n"
        none = _raw(a, (req + "\r\n").encode())
        wrong = _raw(a, (req + f"Proxy-Authorization: {_auth(b)}\r\n\r\n").encode())
        tunnel = _raw(a, f"CONNECT named.lab:{site.port} HTTP/1.1\r\n\r\n".encode())
        ok = _raw(a, (req + f"Proxy-Authorization: {_auth(a)}\r\n\r\n").encode())
    assert none.startswith(b"HTTP/1.1 407") and b"Proxy-Authenticate: Basic" in none
    assert wrong.startswith(b"HTTP/1.1 407") and tunnel.startswith(b"HTTP/1.1 407")
    assert b" 200 " in ok.split(b"\r\n", 1)[0]
    assert site.seen == ["/x"]  # 인증 없는 요청은 하나도 나가지 않았다
    assert a.unauthorized == 3
    # 토큰은 기록·진단 문자열에 남지 않는다
    assert all(a.credentials["password"] not in s for s in [*a.blocked, *a.allowed])


def test_proxy_auth_header_not_forwarded_upstream(site: _Site) -> None:
    headers: list[str] = []

    class Echo(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            headers.extend(f"{k}: {v}" for k, v in self.headers.items())
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer((PUBLIC, 0), Echo)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        with EgressProxy(_to_public, allowed_ports=None) as proxy:
            _raw(
                proxy,
                f"GET http://named.lab:{port}/h HTTP/1.1\r\nHost: named.lab\r\nProxy-Authorization: {_auth(proxy)}\r\n\r\n".encode(),
            )
    finally:
        server.shutdown()
        server.server_close()
    assert headers and not any(h.lower().startswith("proxy-authorization") for h in headers)


def test_renderer_launches_chromium_with_proxy_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class Stop(Exception):
        pass

    class Chromium:
        def launch(self, **kw: Any) -> Any:
            seen.update(kw)
            raise Stop

    class P:
        chromium = Chromium()

    renderer = PlaywrightRenderer(allow_private=False, resolver=lambda h: ["93.184.216.34"])
    guard = renderer.guard()
    assert guard.prepare("https://www.public-site.kr/") is None
    with pytest.raises(Stop):
        renderer._render_with(P(), "https://www.public-site.kr/", guard, "ua")
    proxy = seen["proxy"]
    assert proxy["server"].startswith("http://127.0.0.1:")
    assert proxy["username"] and len(proxy["password"]) >= 20


# ====================================================================== 29 IPv4/IPv6 순서·폴백


def test_guard_orders_v4_first_and_keeps_all_answers() -> None:
    v6, v4 = "2606:4700:4700::1111", "93.184.216.34"
    guard = BrowserGuard(allow_private=False, resolver=lambda h: sorted([v4, v6]))  # 문자열 정렬 = v6 먼저
    assert guard.connect_address("cdn.public-site.kr", 443) == [v4, v6]
    assert guard.prepare("https://www.public-site.kr/") is None
    assert guard.connect_address("www.public-site.kr", 443) == [v4, v6]
    assert f"MAP www.public-site.kr {v4}" in guard.launch_args()[0]


def test_proxy_falls_back_to_next_address(site: _Site) -> None:
    with EgressProxy(lambda h, p: [DEAD, PUBLIC], allowed_ports=None) as proxy:
        out = _raw(
            proxy,
            f"GET http://named.lab:{site.port}/fb HTTP/1.1\r\nHost: named.lab\r\nProxy-Authorization: {_auth(proxy)}\r\n\r\n".encode(),
        )
    assert b" 200 " in out.split(b"\r\n", 1)[0], out[:80]
    assert site.seen == ["/fb"]
    assert proxy.allowed[-1] == f"named.lab:{site.port} → {PUBLIC}"


def test_proxy_all_addresses_fail_is_502(site: _Site) -> None:
    with EgressProxy(lambda h, p: [DEAD], allowed_ports=None) as proxy:
        out = _raw(
            proxy,
            f"CONNECT named.lab:{site.port} HTTP/1.1\r\nProxy-Authorization: {_auth(proxy)}\r\n\r\n".encode(),
        )
    assert out.startswith(b"HTTP/1.1 502")


def test_real_chromium_falls_back_when_first_address_refuses(lab_rules: None, site: _Site) -> None:
    _need_chromium()
    site.page = lambda: "<!doctype html><html><body><h1>fallback</h1></body></html>"
    renderer = PlaywrightRenderer(
        allow_private=False,
        resolver=lambda h: [DEAD, PUBLIC],
        settle_ms=0,
        timeout_ms=20_000,
        allowed_ports=frozenset({site.port}),
    )
    result = renderer.render(f"http://site.r3c-lab.kr:{site.port}/index.html")
    assert result.ok, result.error
    assert "fallback" in result.dom_text and "/index.html" in site.seen


# ====================================================================== 30 락 밖 DNS


def test_guard_resolves_outside_global_lock() -> None:
    """느린 이름 하나를 푸는 동안 다른 호스트 연결 검사가 기다리지 않는다(같은 이름은 여전히 1회)."""
    gate = threading.Event()
    calls: list[str] = []

    def resolver(host: str) -> list[str]:
        calls.append(host)
        if host == "slow.public-site.kr":
            gate.wait(5)
        return ["93.184.216.34"]

    guard = BrowserGuard(allow_private=False, resolver=resolver)
    slow_results: list[list[str]] = []
    t1 = threading.Thread(target=lambda: slow_results.append(guard.connect_address("slow.public-site.kr", 443)))
    t2 = threading.Thread(target=lambda: slow_results.append(guard.connect_address("slow.public-site.kr", 443)))
    t1.start()
    time.sleep(0.1)
    t2.start()
    t0 = time.monotonic()
    fast = guard.connect_address("fast.public-site.kr", 443)
    elapsed = time.monotonic() - t0
    gate.set()
    t1.join(5)
    t2.join(5)
    assert fast == ["93.184.216.34"] and elapsed < 1.0, elapsed
    assert slow_results == [["93.184.216.34"], ["93.184.216.34"]]
    assert calls.count("slow.public-site.kr") == 1  # 같은 이름은 렌더당 한 번(rebinding 차단 유지)


def test_guard_caches_blocked_answer_per_render() -> None:
    answers = [["10.0.0.7"], ["93.184.216.34"]]
    calls: list[str] = []

    def resolver(host: str) -> list[str]:
        calls.append(host)
        return answers[min(len(calls) - 1, 1)]

    guard = BrowserGuard(allow_private=False, resolver=resolver)
    for _ in range(2):
        with pytest.raises(BlockedHostError):
            guard.connect_address("flip.public-site.kr", 443)
    assert calls == ["flip.public-site.kr"]
