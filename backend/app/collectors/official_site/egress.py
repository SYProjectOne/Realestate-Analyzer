"""렌더 1회용 로컬 출구 프록시 — 브라우저의 **모든 연결을 연결 전에** 검사한다(R3b 마무리, SSRF 잔여 구멍).

Playwright ``route`` 는 (1) 리다이렉트 단계(302 → 내부망)를 거치지 않고, (2) WebSocket 을 거치지 않으며,
(3) 하위 리소스 호스트를 검사해도 브라우저가 연결할 때 DNS 를 **다시** 푼다(rebinding). 그래서 chromium 을
이 프록시(``--proxy-server``, Playwright 는 ``<-loopback>`` 으로 루프백도 프록시로 보낸다)로만 내보내고, 프록시가
요청마다 목적지를 검사한다:

- ``CONNECT host:port``(https·wss): ``connect(host, port)`` 가 돌려준 IP 로만 터널을 연다. 막히면 403.
- 절대 주소 요청(``GET http://host:port/path``): 같은 검사 후 그 IP 로 원 주소 형태(origin-form)로 보내고
  ``Connection: close`` 로 요청 1개 = 연결 1개(다른 호스트 요청이 같은 연결로 섞이지 않게).
  ``Upgrade``(평문 WebSocket) 요청은 언제나 403.
- 리다이렉트 단계·JS 이동·iframe·WebSocket 모두 새 프록시 요청이라 연결 **전에** 막힌다(route.fetch 로 대신
  받지 않는다 — 차단 우선).

``connect`` 는 ``render.BrowserGuard.connect_address`` (이름은 렌더당 한 번 풀어 답 전부 검사 → 그 IP 고정).
막힌 요청은 ``blocked`` 에 사유와 함께 남는다. 표준 라이브러리만 쓴다(스레드 + select).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import contextlib
import select
import socket
import threading
from collections.abc import Callable
from urllib.parse import urlsplit

__all__ = ["EgressProxy"]

_HEAD_LIMIT = 64 * 1024
_HOP_HEADERS = frozenset(
    {"proxy-connection", "proxy-authorization", "connection", "keep-alive", "te", "trailer", "upgrade"}
)

Connect = Callable[[str, int], str]
"""(호스트, 포트) → 연결할 IP. 막아야 하면 예외(사유 = str(예외))."""


class EgressProxy:
    """``with EgressProxy(connect) as proxy: launch(proxy={"server": proxy.server})``."""

    def __init__(self, connect: Connect, *, timeout_s: float = 30.0) -> None:
        self._connect = connect
        self._timeout = timeout_s
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._listener.settimeout(0.2)
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._socks: set[socket.socket] = set()
        self._threads: list[threading.Thread] = []
        self.blocked: list[str] = []
        self.allowed: list[str] = []  # 연결한 목적지 'host:port → ip'(진단·테스트)
        self._accept = threading.Thread(target=self._serve, name="egress-proxy", daemon=True)

    @property
    def server(self) -> str:
        host, port = self._listener.getsockname()[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> EgressProxy:
        self._accept.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._closed.set()
        with contextlib.suppress(OSError):
            self._listener.close()
        with self._lock:
            socks = list(self._socks)
        for s in socks:
            with contextlib.suppress(OSError):
                s.close()
        if self._accept.is_alive():
            self._accept.join(timeout=2)
        for t in list(self._threads):
            t.join(timeout=2)

    # ------------------------------------------------------------ 내부

    def _track(self, s: socket.socket) -> socket.socket:
        with self._lock:
            self._socks.add(s)
        return s

    def _serve(self) -> None:
        while not self._closed.is_set():
            try:
                client, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            t = threading.Thread(target=self._handle, args=(self._track(client),), daemon=True)
            self._threads.append(t)
            t.start()

    def _block(self, client: socket.socket, what: str, reason: str) -> None:
        with self._lock:
            self.blocked.append(f"{reason} ({what})")
        with contextlib.suppress(OSError):
            client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")

    def _open(self, client: socket.socket, host: str, port: int, what: str) -> socket.socket | None:
        try:
            ip = self._connect(host, port)
        except Exception as exc:  # 내부망·잘못된 주소·DNS 실패 — 연결하지 않는다
            self._block(client, what, str(exc) or type(exc).__name__)
            return None
        try:
            upstream = socket.create_connection((ip, port), timeout=self._timeout)
        except OSError as exc:
            with contextlib.suppress(OSError):
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            with self._lock:
                self.allowed.append(f"{host}:{port} → {ip} (연결 실패 {type(exc).__name__})")
            return None
        with self._lock:
            self.allowed.append(f"{host}:{port} → {ip}")
        return self._track(upstream)

    def _handle(self, client: socket.socket) -> None:
        upstream: socket.socket | None = None
        try:
            client.settimeout(self._timeout)
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = client.recv(65536)
                if not chunk:
                    return
                buf += chunk
                if len(buf) > _HEAD_LIMIT:
                    return
            head, rest = buf.split(b"\r\n\r\n", 1)
            lines = head.decode("latin-1").split("\r\n")
            parts = lines[0].split(" ")
            if len(parts) != 3:
                return
            method, target, version = parts
            if method.upper() == "CONNECT":
                host, port = _split_hostport(target, 443)
                if host is None:
                    self._block(client, target, "blocked_host: 잘못된 주소")
                    return
                upstream = self._open(client, host, port, f"CONNECT {target}")
                if upstream is None:
                    return
                client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                if rest:
                    upstream.sendall(rest)
            else:
                url = urlsplit(target)
                if url.scheme.lower() != "http" or not url.hostname:
                    self._block(client, target, f"blocked_host: 허용하지 않는 프록시 요청 {url.scheme or target}")
                    return
                headers = [h for h in lines[1:] if h]
                if any(h.split(":", 1)[0].strip().lower() == "upgrade" for h in headers):
                    self._block(client, target, "blocked_host: WebSocket 차단")
                    return
                port = url.port or 80
                upstream = self._open(client, url.hostname, port, f"{method} {target}")
                if upstream is None:
                    return
                path = (url.path or "/") + (f"?{url.query}" if url.query else "")
                kept = [h for h in headers if h.split(":", 1)[0].strip().lower() not in _HOP_HEADERS]
                out = "\r\n".join([f"{method} {path} {version}", *kept, "Connection: close", "", ""])
                upstream.sendall(out.encode("latin-1") + rest)
            _pipe(client, upstream, self._timeout, self._closed)
        except OSError:
            return
        finally:
            for s in (client, upstream):
                if s is not None:
                    with contextlib.suppress(OSError):
                        s.close()
                    with self._lock:
                        self._socks.discard(s)


def _split_hostport(target: str, default: int) -> tuple[str | None, int]:
    try:
        parts = urlsplit(f"//{target}")
        return parts.hostname, parts.port or default
    except ValueError:
        return None, default


def _pipe(a: socket.socket, b: socket.socket, idle_s: float, closed: threading.Event) -> None:
    """양방향 복사 — 한쪽이 닫히거나 ``idle_s`` 동안 아무것도 없으면 끝."""
    socks = [a, b]
    while not closed.is_set():
        ready, _, _ = select.select(socks, [], [], idle_s)
        if not ready:
            return
        for s in ready:
            data = s.recv(65536)
            if not data:
                return
            (b if s is a else a).sendall(data)
