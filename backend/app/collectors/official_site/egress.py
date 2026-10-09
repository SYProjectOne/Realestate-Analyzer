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

``connect`` 는 ``render.BrowserGuard.connect_address`` (이름은 렌더당 한 번 풀어 답 전부 검사 → 그 IP 목록 고정).
막힌 요청은 ``blocked`` 에 사유와 함께 남는다. 표준 라이브러리만 쓴다(스레드 + select).

R3c SEC(3차 리뷰 minor 26~29):

- **포트**: 공개 웹(``PUBLIC_WEB_PORTS`` = 80·443)만. 그 밖의 포트(22·25·6379·8080 …)와 범위 밖·숫자 아닌
  포트는 이름을 풀기 **전에** 403 + ``blocked`` 기록(``blocked_host: 포트 …``). ``allowed_ports=None`` 은
  제한 없음(로컬 시험 서버 — ``allow_private`` 렌더만. prod 는 ``allow_private`` 자체가 거부된다).
- **인증**: 프록시마다 무작위 토큰(``secrets.token_urlsafe``). ``Proxy-Authorization: Basic`` 이 없거나 틀리면
  407(``Proxy-Authenticate``)이고 아무 데도 연결하지 않는다 — 같은 머신의 다른 프로세스가 렌더 동안 이
  프록시로 나가지 못한다. chromium 은 ``launch(proxy={..., username, password})`` 로 받는다(첫 요청은 인증 없이
  보내고 407 뒤에 붙인다 — ``unauthorized`` 로 센다). 토큰은 기록·진단 문자열에 남기지 않고 위로 전달하지
  않는다(hop-by-hop 헤더로 지운다).
- **주소 폴백**: ``connect`` 는 검사한 IP **목록**(v4 우선)을 돌려준다. 앞 주소 연결이 실패하면 다음 주소로
  (IPv6 경로가 없는 머신에서 v6 를 먼저 골라 502 나던 문제). 전부 실패하면 502.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import base64
import binascii
import contextlib
import hmac
import secrets
import select
import socket
import threading
from collections.abc import Callable, Collection, Sequence
from urllib.parse import urlsplit

__all__ = ["PUBLIC_WEB_PORTS", "EgressProxy"]

PUBLIC_WEB_PORTS: frozenset[int] = frozenset({80, 443})
"""렌더가 나갈 수 있는 목적지 포트(공개 웹 http·https 만)."""

_HEAD_LIMIT = 64 * 1024
_HOP_HEADERS = frozenset(
    {"proxy-connection", "proxy-authorization", "connection", "keep-alive", "te", "trailer", "upgrade"}
)
_407 = (
    b"HTTP/1.1 407 Proxy Authentication Required\r\n"
    b'Proxy-Authenticate: Basic realm="egress"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
)
_502 = b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"

Connect = Callable[[str, int], Sequence[str]]
"""(호스트, 포트) → 연결할 IP 목록(앞에서부터 시도). 막아야 하면 예외(사유 = str(예외))."""


def port_block_reason(port: int | None, allowed: Collection[int] | None = PUBLIC_WEB_PORTS) -> str | None:
    """목적지 포트를 막는 사유(``blocked_host: …``) 또는 None. ``port`` None = 범위 밖·숫자 아님."""
    if port is None or not 0 < port < 65536:
        return "blocked_host: 잘못된 포트"
    if allowed is not None and port not in allowed:
        ports = "·".join(str(p) for p in sorted(allowed))
        return f"blocked_host: 포트 {port} 차단(공개 웹 {ports} 만)"
    return None


def netloc_port(netloc: str, default: int) -> int | None:
    """netloc 의 포트(없으면 ``default``). 범위 밖·숫자 아님이면 None — 예외를 내지 않는다(minor 26)."""
    hostport = netloc.rpartition("@")[2]
    if hostport.startswith("["):
        rest = hostport.partition("]")[2]
        text: str | None = rest[1:] if rest.startswith(":") else None
    else:
        text = hostport.rpartition(":")[2] if ":" in hostport else None
    if not text:
        return default
    if not (text.isascii() and text.isdigit()):
        return None
    value = int(text)
    return value if 0 < value < 65536 else None


class EgressProxy:
    """``with EgressProxy(connect) as p: launch(proxy={"server": p.server, **p.credentials})``."""

    def __init__(
        self,
        connect: Connect,
        *,
        timeout_s: float = 30.0,
        allowed_ports: Collection[int] | None = PUBLIC_WEB_PORTS,
    ) -> None:
        self._connect = connect
        self._timeout = timeout_s
        self._allowed_ports = frozenset(allowed_ports) if allowed_ports is not None else None
        self._username = "egress"
        self._password = secrets.token_urlsafe(24)
        self._expected_auth = base64.b64encode(f"{self._username}:{self._password}".encode())
        self.unauthorized = 0  # 인증 없는·틀린 요청 수
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

    @property
    def credentials(self) -> dict[str, str]:
        """chromium ``launch(proxy=…)`` 에 넣을 사용자·토큰(이 프록시 1개 = 렌더 1회 전용)."""
        return {"username": self._username, "password": self._password}

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

    def _authorized(self, headers: Sequence[str]) -> bool:
        for h in headers:
            name, _, value = h.partition(":")
            if name.strip().lower() != "proxy-authorization":
                continue
            scheme, _, token = value.strip().partition(" ")
            if scheme.lower() != "basic":
                return False
            try:  # 정준 base64 로 다시 써서 비교(공백·패딩 차이 무시), 비교는 상수 시간
                given = base64.b64encode(base64.b64decode(token.strip(), validate=True))
            except (binascii.Error, ValueError):
                return False
            return hmac.compare_digest(given, self._expected_auth)
        return False

    def _open(self, client: socket.socket, host: str, port: int | None, what: str) -> socket.socket | None:
        reason = port_block_reason(port, self._allowed_ports)
        if reason is not None or port is None:  # 이름을 풀기 전에 막는다
            self._block(client, what, reason or "blocked_host: 잘못된 포트")
            return None
        try:
            ips = list(self._connect(host, port))
        except Exception as exc:  # 내부망·잘못된 주소·DNS 실패 — 연결하지 않는다
            self._block(client, what, str(exc) or type(exc).__name__)
            return None
        failures: list[str] = []
        for ip in ips:  # 검사한 주소만, 앞에서부터(v4 우선). 연결 실패면 다음 주소
            try:
                upstream = socket.create_connection((ip, port), timeout=self._timeout)
            except OSError as exc:
                failures.append(f"{ip} (연결 실패 {type(exc).__name__})")
                continue
            with self._lock:
                self.allowed.extend(f"{host}:{port} → {f}" for f in failures)
                self.allowed.append(f"{host}:{port} → {ip}")
            return self._track(upstream)
        with contextlib.suppress(OSError):
            client.sendall(_502)
        with self._lock:
            self.allowed.extend(f"{host}:{port} → {f}" for f in failures or ["(주소 없음)"])
        return None

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
            headers = [h for h in lines[1:] if h]
            if not self._authorized(headers):
                with self._lock:
                    self.unauthorized += 1
                with contextlib.suppress(OSError):
                    client.sendall(_407)
                return
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
                try:
                    url = urlsplit(target)
                    hostname = url.hostname
                except ValueError:
                    self._block(client, target, "blocked_host: 잘못된 주소")
                    return
                if url.scheme.lower() != "http" or not hostname:
                    self._block(
                        client, target, f"blocked_host: 허용하지 않는 프록시 요청 {url.scheme or target}"
                    )
                    return
                if any(h.split(":", 1)[0].strip().lower() == "upgrade" for h in headers):
                    self._block(client, target, "blocked_host: WebSocket 차단")
                    return
                port = netloc_port(url.netloc, 80)
                upstream = self._open(client, hostname, port, f"{method} {target}")
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


def _split_hostport(target: str, default: int) -> tuple[str | None, int | None]:
    try:
        host = urlsplit(f"//{target}").hostname
    except ValueError:
        return None, None
    return host, netloc_port(target, default)


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
