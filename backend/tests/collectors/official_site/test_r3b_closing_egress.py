"""R3b 마무리 — Playwright 내부망 잔여 구멍(``render.py`` + ``egress.py``).

로컬 HTTP 서버 둘: '공개'(127.0.0.1) · '내부'(127.0.0.2). 시험 동안 ``ip_blocked`` 를 "127.0.0.1 만 공개"로 바꿔
(그 밖의 루프백·사설 IP 는 그대로 내부망) 실제 chromium 이 다음을 **요청 전에** 못 하게 되는지 본다 —
내부 서버가 요청을 하나도 받지 않아야 한다.

- 하위 리소스의 302 리다이렉트 단계 → 내부 IP (Playwright route 는 리다이렉트 단계를 거치지 않는다)
- 본문 이동의 302 → 내부 IP (렌더 결과를 버린다)
- 본 호스트 외 이름이 DNS 로 내부 IP 로 풀림 · 검사 뒤 다른 IP 로 바뀌는 이름(rebinding)
- WebSocket(공개 호스트여도 연결하지 않는다)·JS fetch → 내부 IP

프록시 자체(브라우저 없이 소켓으로)도 시험한다.
"""

# ruff: noqa: E501

from __future__ import annotations

import base64
import socket
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

import app.core.http as core_http
from app.collectors.official_site import render as render_mod
from app.collectors.official_site.egress import EgressProxy
from app.collectors.official_site.render import BrowserGuard, PlaywrightRenderer
from app.core.http import BlockedHostError

PUBLIC = "127.0.0.1"
INTERNAL = "127.0.0.2"

_real_ip_blocked = core_http.ip_blocked


def _lab_ip_blocked(text: str) -> bool:
    """시험실 규칙: 127.0.0.1 = 공개 서버, 그 밖은 원래 규칙(127.0.0.2 는 루프백 → 내부망)."""
    return text != PUBLIC and _real_ip_blocked(text)


@pytest.fixture
def lab_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core_http, "ip_blocked", _lab_ip_blocked)
    monkeypatch.setattr(render_mod, "ip_blocked", _lab_ip_blocked)


class _Site:
    def __init__(self, host: str, page: Callable[[], str] | None = None) -> None:
        self.seen: list[str] = []
        self.page = page
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                site.seen.append(self.path)
                if self.path.startswith("/go-") and site.redirect is not None:
                    self.send_response(302)
                    self.send_header("Location", site.redirect(self.path))
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                is_page = self.path.startswith("/index") and site.page is not None
                body = site.page().encode() if is_page and site.page is not None else b"ok"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8" if is_page else "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.redirect: Callable[[str], str] | None = None
        self.server = ThreadingHTTPServer((host, 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def sites() -> Iterator[tuple[_Site, _Site]]:
    try:
        internal = _Site(INTERNAL)
    except OSError as exc:  # 127.0.0.2 를 못 여는 환경
        pytest.skip(f"{INTERNAL} 바인드 불가: {exc}")
    public = _Site(PUBLIC)
    try:
        yield public, internal
    finally:
        public.close()
        internal.close()


def _need_chromium() -> None:
    probe = PlaywrightRenderer(allow_private=True, settle_ms=0).render("about:blank")
    if probe.error and ("Executable doesn't exist" in probe.error or "playwright install" in probe.error):
        pytest.skip(f"Playwright chromium 미설치: {probe.error}")


def _resolver(table: dict[str, list[list[str]]]) -> Callable[[str], list[str]]:
    """이름 → 답 목록의 차례(마지막 답은 계속 반복). rebinding 흉내."""
    calls: dict[str, int] = {}

    def resolve(host: str) -> list[str]:
        answers = table.get(host)
        if not answers:
            return []
        i = calls.get(host, 0)
        calls[host] = i + 1
        return answers[min(i, len(answers) - 1)]

    return resolve


# ====================================================================== 실제 chromium


def test_real_chromium_blocks_redirect_hop_rebinding_and_websocket_before_request(
    lab_rules: None, sites: tuple[_Site, _Site]
) -> None:
    _need_chromium()
    public, internal = sites
    pp, ip = public.port, internal.port
    public.redirect = lambda path: f"http://{INTERNAL}:{ip}/secret{path}"
    public.page = lambda: (
        "<!doctype html><html><body><h1>lab</h1>"
        f'<img src="http://cdn.r3b-lab.kr:{pp}/cdn.png">'  # 공개 이름 → 공개 IP: 허용
        '<img src="/go-img">'  # 302 → 내부 IP (리다이렉트 단계)
        f'<img src="http://intra.r3b-lab.kr:{ip}/dns.png">'  # 이름이 내부 IP 로 풀림
        f'<img src="http://rebind.r3b-lab.kr:{ip}/rebind.png">'  # 처음엔 공개, 다음엔 내부
        "<script>"
        f'try {{ new WebSocket("ws://site.r3b-lab.kr:{pp}/ws"); }} catch (e) {{}}'
        f'try {{ fetch("http://{INTERNAL}:{ip}/js").catch(() => 0); }} catch (e) {{}}'
        "</script></body></html>"
    )
    resolver = _resolver(
        {
            "site.r3b-lab.kr": [[PUBLIC]],
            "cdn.r3b-lab.kr": [[PUBLIC]],
            "intra.r3b-lab.kr": [[INTERNAL]],
            "rebind.r3b-lab.kr": [[PUBLIC], [INTERNAL]],
        }
    )
    renderer = PlaywrightRenderer(
        allow_private=False, resolver=resolver, settle_ms=300, timeout_ms=20_000, allowed_ports={pp, ip}
    )  # 시험 서버 포트만 허용(R3c: 기본은 80·443)
    holder: dict[str, BrowserGuard] = {}
    original = renderer.guard

    def keep() -> BrowserGuard:
        holder["g"] = original()
        return holder["g"]

    renderer.guard = keep  # type: ignore[method-assign]
    result = renderer.render(f"http://site.r3b-lab.kr:{pp}/index.html")
    assert result.ok, result.error
    assert internal.seen == [], internal.seen  # 내부 서버는 아무 요청도 받지 않았다
    assert "/cdn.png" in public.seen and "/go-img" in public.seen
    assert "/ws" not in public.seen  # WebSocket 은 공개 호스트여도 연결하지 않는다
    guard = holder["g"]
    assert guard.websockets == [f"ws://site.r3b-lab.kr:{pp}/ws"]
    blocked = "\n".join(guard.blocked)
    assert f"{INTERNAL}:{ip}" in blocked  # 리다이렉트 단계·JS fetch(IP 문자열)
    assert "intra.r3b-lab.kr" in blocked and "WebSocket" in blocked


def test_real_chromium_main_redirect_to_internal_discarded(
    lab_rules: None, sites: tuple[_Site, _Site]
) -> None:
    _need_chromium()
    public, internal = sites
    public.redirect = lambda path: f"http://{INTERNAL}:{internal.port}/secret"
    resolver = _resolver({"site.r3b-lab.kr": [[PUBLIC]]})
    renderer = PlaywrightRenderer(
        allow_private=False,
        resolver=resolver,
        settle_ms=0,
        timeout_ms=20_000,
        allowed_ports={public.port, internal.port},
    )
    result = renderer.render(f"http://site.r3b-lab.kr:{public.port}/go-main")
    assert not result.ok and (result.error or "").startswith("blocked_host"), result
    assert internal.seen == []
    assert result.screenshot_png == b""


# ====================================================================== 프록시(브라우저 없이)


def _connect_rule(host: str, port: int) -> list[str]:
    if host in ("intra.lab", INTERNAL):
        raise BlockedHostError(f"blocked_host: 내부망 주소 {host}")
    return [PUBLIC]


def _raw(proxy: EgressProxy, request: bytes) -> bytes:
    """요청 머리 첫 줄 뒤에 이 프록시의 인증 헤더를 붙여 보낸다(R3c: 렌더마다 무작위 토큰)."""
    c = proxy.credentials
    auth = base64.b64encode(f"{c['username']}:{c['password']}".encode())
    first, _, tail = request.partition(b"\r\n")
    request = first + b"\r\nProxy-Authorization: Basic " + auth + b"\r\n" + tail
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


def test_proxy_connect_to_blocked_host_refused_before_connecting(sites: tuple[_Site, _Site]) -> None:
    _, internal = sites
    with EgressProxy(_connect_rule, allowed_ports=None) as proxy:
        out = _raw(proxy, f"CONNECT {INTERNAL}:{internal.port} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
    assert out.startswith(b"HTTP/1.1 403")
    assert internal.seen == [] and proxy.blocked and INTERNAL in proxy.blocked[0]


def test_proxy_absolute_get_rewritten_and_pinned(sites: tuple[_Site, _Site]) -> None:
    public, _ = sites
    with EgressProxy(_connect_rule, allowed_ports=None) as proxy:
        out = _raw(
            proxy,
            f"GET http://named.lab:{public.port}/a.png?x=1 HTTP/1.1\r\nHost: named.lab:{public.port}\r\n"
            "Proxy-Connection: keep-alive\r\n\r\n".encode(),
        )
    assert out.startswith(b"HTTP/1.0 200") or out.startswith(b"HTTP/1.1 200"), out[:80]
    assert public.seen == ["/a.png?x=1"]  # 원 주소 형태로, 검사한 IP(127.0.0.1)로 연결
    assert proxy.allowed == [f"named.lab:{public.port} → {PUBLIC}"]


def test_proxy_blocks_plain_websocket_upgrade_and_non_http(sites: tuple[_Site, _Site]) -> None:
    public, _ = sites
    with EgressProxy(_connect_rule, allowed_ports=None) as proxy:
        ws = _raw(
            proxy,
            f"GET http://named.lab:{public.port}/ws HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\n\r\n".encode(),
        )
        ftp = _raw(proxy, b"GET ftp://named.lab/x HTTP/1.1\r\nHost: x\r\n\r\n")
        dns = _raw(proxy, b"GET http://intra.lab/x HTTP/1.1\r\nHost: intra.lab\r\n\r\n")
    assert (
        ws.startswith(b"HTTP/1.1 403") and ftp.startswith(b"HTTP/1.1 403") and dns.startswith(b"HTTP/1.1 403")
    )
    assert public.seen == []
    assert len(proxy.blocked) == 3


def test_guard_connect_address_resolves_once_per_render(lab_rules: None) -> None:
    """본 호스트 외 이름도 렌더당 한 번 풀어 답 전부 검사 → 그 IP 고정(두 번째 연결은 다시 풀지 않는다)."""
    calls: list[str] = []

    def resolver(host: str) -> list[str]:
        calls.append(host)
        return [PUBLIC] if len(calls) == 1 else [INTERNAL]

    guard = BrowserGuard(allow_private=False, resolver=resolver)
    assert guard.connect_address("cdn.r3b-lab.kr", 443) == [PUBLIC]
    assert guard.connect_address("cdn.r3b-lab.kr", 443) == [PUBLIC]
    assert calls == ["cdn.r3b-lab.kr"]
    with pytest.raises(BlockedHostError):
        BrowserGuard(allow_private=False, resolver=lambda h: [PUBLIC, "10.0.0.7"]).connect_address(
            "mix.kr", 80
        )
    with pytest.raises(BlockedHostError):
        guard.connect_address("169.254.169.254", 80)


def test_guard_pins_idn_main_host_in_punycode_too() -> None:
    """국문 도메인 본 호스트: 브라우저는 punycode 로 프록시에 묻는다 → 같은 고정 IP(다시 풀지 않는다)."""
    calls: list[str] = []

    def resolver(host: str) -> list[str]:
        calls.append(host)
        return ["93.184.216.34"]

    guard = BrowserGuard(allow_private=False, resolver=resolver)
    assert guard.prepare("https://www.엘리프검단포레듀.com/") is None
    puny = "www.엘리프검단포레듀.com".encode("idna").decode("ascii")
    assert guard.connect_address(puny, 443) == ["93.184.216.34"]
    assert calls == ["www.엘리프검단포레듀.com"]
    assert f"MAP {puny} 93.184.216.34" in guard.launch_args()[0]
