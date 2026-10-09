"""수집용 HTTP 클라이언트 (RA §4-3 Collector 규칙, AGENTS 규칙 7·18).

- 호스트별 속도 제한(기본 ``HTTP_RATE_PER_HOST`` = 1 req/s; robots.txt 요청과 재시도도 포함)
- 지수 백오프 재시도: 5xx·타임아웃·연결 오류만. 4xx 는 재시도하지 않는다(429 포함).
- robots.txt 확인·캐시(RFC 9309): 2xx → 규칙 적용, 4xx → 제한 없음, 5xx·네트워크 실패 → 전부 불허.
  불허면 요청하지 않고 ``FetchResult(error="blocked_by_robots")`` 를 돌려준다. 원인은 ``robots_status``
  (robots.txt 응답 코드)·``robots_error_kind``·``robots_error`` 에 남는다 — 규칙상 불허(2xx + Disallow)와
  robots.txt 자체의 실패(5xx·DNS·timeout)를 수집기가 다시 요청하지 않고 구분한다(``robots_reason``).
- 키 인증 공식 API 호스트(``HTTP_ROBOTS_EXEMPT_HOSTS``, 기본 apis.data.go.kr·openapi.naver.com)는
  robots.txt 를 보지 않는다 — 크롤링이 아니라 발급 키로 쓰는 API 이고 이용약관이 규율한다.
  속도 제한·재시도는 그대로.
- **예외를 삼키지도 던지지도 않는다**: 성공·실패 모두 ``FetchResult`` 로 반환한다.
- 내부망 차단(R3 minor 17, SSRF): localhost·사설·루프백·링크로컬·예약·멀티캐스트 주소(IP 문자열이거나 DNS 가
  그 주소로 풀리는 호스트)는 요청하지 않고 ``error_kind='blocked_host'`` 로 돌려준다. **리다이렉트 대상도 매번
  다시 검사한다**(httpx request 훅). 테스트의 로컬 서버는 ``allow_private=True``(또는 설정
  ``HTTP_ALLOW_PRIVATE_HOSTS`` — Settings 에 그 필드가 있으면) 로 허용한다. DNS 확인은 실제 네트워크(주입한
  transport 가 없을 때)에서만 한다 — 주입 transport 테스트는 오프라인으로 돈다.

동기 ``HttpClient`` 와 비동기 ``AsyncHttpClient`` 는 같은 규칙을 공유한다. 테스트는 ``sleep``·``clock`` 을
주입해 실제로 기다리지 않는다.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import random
import socket
import threading
import time
import urllib.robotparser
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Literal, Self

import httpx

from app.core.settings import get_settings

ErrorKind = Literal["http_status", "timeout", "connect", "network", "robots", "invalid_url", "blocked_host"]
BLOCKED_BY_ROBOTS = "blocked_by_robots"
BLOCKED_HOST = "blocked_host"
ROBOTS_TTL_S = 24 * 3600.0  # RFC 9309: 캐시는 24시간을 넘기지 않는다
ROBOTS_UNREACHABLE_TTL_S = 600.0

RequestBody = Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status: int | None  # HTTP 상태 코드; 응답이 없으면 None
    headers: dict[str, str]
    content: bytes
    error: str | None  # None = 성공(2xx·3xx)
    elapsed_ms: int
    attempts: int  # 실제로 보낸 요청 수(robots 차단·URL 오류는 0)
    method: str = "GET"
    error_kind: ErrorKind | None = None
    final_url: str | None = None  # 리다이렉트 후 URL
    blocked_by_robots: bool = False
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # robots 차단일 때 robots.txt 요청 결과(원인 보존). 차단이 아니면 모두 None.
    robots_status: int | None = None
    robots_error_kind: ErrorKind | None = None
    robots_error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status is not None and 200 <= self.status < 400

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    def text(self, encoding: str | None = None) -> str:
        enc = encoding or _charset(self.headers.get("content-type", "")) or "utf-8"
        return self.content.decode(enc, errors="replace")

    @property
    def robots_reason(self) -> str | None:
        """robots 차단 원인 한 단어: 'disallow'(robots.txt 2xx 의 규칙) / 'robots.txt <코드>'(5xx) /
        robots.txt 요청 실패 종류('timeout'·'connect'·'network' …). 차단이 아니면 None."""
        if not self.blocked_by_robots:
            return None
        if self.robots_status is not None:
            return "disallow" if 200 <= self.robots_status < 300 else f"robots.txt {self.robots_status}"
        return self.robots_error_kind or "network"


def _charset(content_type: str) -> str | None:
    for part in content_type.split(";"):
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            return value.strip("\"'")
    return None


@dataclass(slots=True)
class _RobotsEntry:
    parser: urllib.robotparser.RobotFileParser | None  # None = allow_all/disallow_all 로 결정
    allow_all: bool
    expires_at: float
    status: int | None = None  # robots.txt 응답 코드(없으면 None)
    error_kind: ErrorKind | None = None
    error: str | None = None

    def allows(self, user_agent: str, url: str) -> bool:
        if self.parser is None:
            return self.allow_all
        return self.parser.can_fetch(user_agent, url)


class BlockedHostError(httpx.RequestError):
    """내부망 주소로 가는 요청(리다이렉트 포함) — 보내지 않는다."""


Resolver = Callable[[str], list[str]]
"""호스트 이름 → IP 문자열 목록(DNS). 실패하면 빈 목록."""


def _system_resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return []
    return sorted({str(info[4][0]) for info in infos})


def _ip_blocked(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


@dataclass(slots=True)
class _Attempt:
    """한 번 보낸 결과(응답 또는 오류)."""

    response: httpx.Response | None = None
    error_kind: ErrorKind | None = None
    error: str | None = None


class _Core:
    """동기·비동기 공통: 설정, 속도 제한 예약, 재시도 판단, robots 해석."""

    def __init__(
        self,
        *,
        user_agent: str | None,
        rate_per_host: float | None,
        max_retries: int | None,
        timeout_s: float | None,
        backoff_base_s: float | None,
        backoff_max_s: float | None,
        jitter: float,
        respect_robots: bool,
        robots_ttl_s: float,
        robots_exempt_hosts: Iterable[str] | None,
        clock: Callable[[], float],
        allow_private: bool | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        s = get_settings()
        self.allow_private = (
            allow_private if allow_private is not None else bool(getattr(s, "http_allow_private_hosts", False))
        )
        self._resolver = resolver
        self._resolved: dict[str, bool] = {}
        self.user_agent = user_agent or s.http_user_agent
        self.rate_per_host = rate_per_host if rate_per_host is not None else s.http_rate_per_host
        if self.rate_per_host <= 0:
            raise ValueError("rate_per_host 는 0보다 커야 한다")
        self.max_retries = max_retries if max_retries is not None else s.http_max_retries
        self.timeout_s = timeout_s if timeout_s is not None else s.http_timeout_s
        self.backoff_base_s = backoff_base_s if backoff_base_s is not None else s.http_backoff_base_s
        self.backoff_max_s = backoff_max_s if backoff_max_s is not None else s.http_backoff_max_s
        self.jitter = jitter
        self.respect_robots = respect_robots
        self.robots_ttl_s = robots_ttl_s
        hosts = s.http_robots_exempt_hosts if robots_exempt_hosts is None else robots_exempt_hosts
        self.robots_exempt_hosts = frozenset(h.strip().lower() for h in hosts if h.strip())
        self._clock = clock
        self._next_slot: dict[str, float] = {}
        self._slot_lock = threading.Lock()
        self._robots: dict[str, _RobotsEntry] = {}

    # --- 속도 제한: 호스트별 다음 허용 시각을 예약하고 기다릴 시간을 돌려준다
    def _reserve(self, host: str) -> float:
        interval = 1.0 / self.rate_per_host
        with self._slot_lock:
            now = self._clock()
            slot = max(now, self._next_slot.get(host, now))
            self._next_slot[host] = slot + interval
            return slot - now

    def _backoff(self, attempt: int) -> float:
        delay: float = min(self.backoff_max_s, self.backoff_base_s * (2 ** (attempt - 1)))
        if self.jitter:
            delay *= 1 + self.jitter * random.random()
        return delay

    @staticmethod
    def _retryable(a: _Attempt) -> bool:
        if a.response is not None:
            return a.response.status_code >= 500
        return a.error_kind in {"timeout", "connect", "network"}

    @staticmethod
    def _classify(exc: httpx.HTTPError) -> _Attempt:
        if isinstance(exc, BlockedHostError):
            return _Attempt(error_kind="blocked_host", error=str(exc))
        if isinstance(exc, httpx.TimeoutException):
            return _Attempt(error_kind="timeout", error=f"timeout: {type(exc).__name__}: {exc}")
        if isinstance(exc, httpx.ConnectError):
            return _Attempt(error_kind="connect", error=f"connect: {exc}")
        if isinstance(exc, httpx.UnsupportedProtocol | httpx.InvalidURL):
            return _Attempt(error_kind="invalid_url", error=f"invalid_url: {exc}")
        return _Attempt(error_kind="network", error=f"network: {type(exc).__name__}: {exc}")

    @staticmethod
    def _parse(url: str) -> httpx.URL | None:
        try:
            u = httpx.URL(url)
        except (httpx.InvalidURL, TypeError, ValueError):
            return None
        if u.scheme not in {"http", "https"} or not u.host:
            return None
        return u

    @staticmethod
    def _host_key(u: httpx.URL) -> str:
        return f"{u.host}:{u.port}" if u.port else u.host

    @staticmethod
    def _origin(u: httpx.URL) -> str:
        port = f":{u.port}" if u.port else ""
        return f"{u.scheme}://{u.host}{port}"

    def blocked_reason(self, host: str) -> str | None:
        """내부망 호스트면 사유, 아니면 None(모듈 설명). ``allow_private`` 면 항상 None."""
        if self.allow_private:
            return None
        h = host.strip("[]").rstrip(".").lower()
        if not h:
            return None
        if h == "localhost" or h.endswith(".localhost"):
            return f"{BLOCKED_HOST}: localhost"
        if _ip_blocked(h):
            return f"{BLOCKED_HOST}: 내부망 주소 {h}"
        if self._resolver is None:
            return None
        if h not in self._resolved:
            self._resolved[h] = any(_ip_blocked(a) for a in self._resolver(h))
        return f"{BLOCKED_HOST}: {h} → 내부망 주소" if self._resolved[h] else None

    def _request_hook_check(self, request: httpx.Request) -> None:
        """모든 요청(리다이렉트 포함) 직전 검사."""
        reason = self.blocked_reason(request.url.host)
        if reason is not None:
            raise BlockedHostError(reason, request=request)

    def _blocked_host(self, url: str, method: str, reason: str) -> FetchResult:
        return FetchResult(
            url=url,
            status=None,
            headers={},
            content=b"",
            error=reason,
            elapsed_ms=0,
            attempts=0,
            method=method,
            error_kind="blocked_host",
        )

    def _checks_robots(self, u: httpx.URL) -> bool:
        """robots.txt 를 볼 요청인가(설정이 켜져 있고 키 인증 공식 API 호스트가 아님)."""
        return self.respect_robots and u.host.lower() not in self.robots_exempt_hosts

    def _robots_cached(self, origin: str) -> _RobotsEntry | None:
        entry = self._robots.get(origin)
        if entry is not None and entry.expires_at > self._clock():
            return entry
        return None

    def _robots_entry(self, r: FetchResult) -> _RobotsEntry:
        now = self._clock()
        if r.status is not None and 200 <= r.status < 300:
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(r.text().splitlines())
            return _RobotsEntry(parser, allow_all=True, expires_at=now + self.robots_ttl_s, status=r.status)
        if r.status is not None and 400 <= r.status < 500:
            return _RobotsEntry(None, allow_all=True, expires_at=now + self.robots_ttl_s, status=r.status)
        # 5xx·네트워크 실패 = unreachable → 전부 불허(짧게 캐시). 원인은 차단 결과에 그대로 싣는다.
        ttl = min(self.robots_ttl_s, ROBOTS_UNREACHABLE_TTL_S)
        return _RobotsEntry(
            None,
            allow_all=False,
            expires_at=now + ttl,
            status=r.status,
            error_kind=r.error_kind,
            error=r.error,
        )

    def _result(self, url: str, method: str, a: _Attempt, attempts: int, started: float) -> FetchResult:
        elapsed_ms = max(0, round((self._clock() - started) * 1000))
        if a.response is not None:
            resp = a.response
            status = resp.status_code
            error = None if status < 400 else f"HTTP {status}"
            return FetchResult(
                url=url,
                status=status,
                headers={k.lower(): v for k, v in resp.headers.items()},
                content=resp.content,
                error=error,
                elapsed_ms=elapsed_ms,
                attempts=attempts,
                method=method,
                error_kind=None if error is None else "http_status",
                final_url=str(resp.url),
            )
        return FetchResult(
            url=url,
            status=None,
            headers={},
            content=b"",
            error=a.error or "unknown error",
            elapsed_ms=elapsed_ms,
            attempts=attempts,
            method=method,
            error_kind=a.error_kind,
        )

    @staticmethod
    def _invalid(url: str, method: str) -> FetchResult:
        return FetchResult(
            url=url,
            status=None,
            headers={},
            content=b"",
            error=f"invalid_url: {url!r} (http/https 와 호스트가 필요)",
            elapsed_ms=0,
            attempts=0,
            method=method,
            error_kind="invalid_url",
        )

    @staticmethod
    def _blocked(url: str, method: str, entry: _RobotsEntry) -> FetchResult:
        return FetchResult(
            url=url,
            status=None,
            headers={},
            content=b"",
            error=BLOCKED_BY_ROBOTS,
            elapsed_ms=0,
            attempts=0,
            method=method,
            error_kind="robots",
            blocked_by_robots=True,
            robots_status=entry.status,
            robots_error_kind=entry.error_kind,
            robots_error=entry.error,
        )


class HttpClient(_Core):
    """동기 클라이언트. ``with HttpClient() as c: r = c.get(url)``."""

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        rate_per_host: float | None = None,
        max_retries: int | None = None,
        timeout_s: float | None = None,
        backoff_base_s: float | None = None,
        backoff_max_s: float | None = None,
        jitter: float = 0.1,
        respect_robots: bool = True,
        robots_ttl_s: float = ROBOTS_TTL_S,
        robots_exempt_hosts: Iterable[str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        transport: httpx.BaseTransport | None = None,
        allow_private: bool | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        super().__init__(
            user_agent=user_agent,
            rate_per_host=rate_per_host,
            max_retries=max_retries,
            timeout_s=timeout_s,
            backoff_base_s=backoff_base_s,
            backoff_max_s=backoff_max_s,
            jitter=jitter,
            respect_robots=respect_robots,
            robots_ttl_s=robots_ttl_s,
            robots_exempt_hosts=robots_exempt_hosts,
            clock=clock,
            allow_private=allow_private,
            resolver=resolver if resolver is not None else (_system_resolve if transport is None else None),
        )
        self._sleep = sleep
        self._robots_lock = threading.Lock()
        self._client = httpx.Client(
            timeout=self.timeout_s,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
            transport=transport,
            event_hooks={"request": [self._request_hook_check]},
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get(self, url: str, **kw: Any) -> FetchResult:
        return self.fetch(url, method="GET", **kw)

    def post(self, url: str, **kw: Any) -> FetchResult:
        return self.fetch(url, method="POST", **kw)

    def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        params: RequestBody = None,
        data: RequestBody = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> FetchResult:
        method = method.upper()
        u = self._parse(url)
        if u is None:
            return self._invalid(url, method)
        reason = self.blocked_reason(u.host)
        if reason is not None:
            return self._blocked_host(url, method, reason)
        if self._checks_robots(u):
            entry = self._robots_for(u)
            if not entry.allows(self.user_agent, str(u)):
                return self._blocked(url, method, entry)
        return self._send(url, u, method, params=params, data=data, json=json, headers=headers)

    def _robots_for(self, u: httpx.URL) -> _RobotsEntry:
        origin = self._origin(u)
        with self._robots_lock:
            entry = self._robots_cached(origin)
            if entry is None:
                robots_url = f"{origin}/robots.txt"
                r = self._send(robots_url, httpx.URL(robots_url), "GET")
                entry = self._robots_entry(r)
                self._robots[origin] = entry
        return entry

    def _send(
        self,
        url: str,
        u: httpx.URL,
        method: str,
        *,
        params: RequestBody = None,
        data: RequestBody = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> FetchResult:
        host = self._host_key(u)
        started = self._clock()
        attempts = 0
        while True:
            wait = self._reserve(host)
            if wait > 0:
                self._sleep(wait)
            attempts += 1
            try:
                resp = self._client.request(method, url, params=params, data=data, json=json, headers=headers)
                a = _Attempt(response=resp)
            except httpx.HTTPError as exc:
                a = self._classify(exc)
            if self._retryable(a) and attempts <= self.max_retries:
                if a.response is not None:
                    a.response.close()
                self._sleep(self._backoff(attempts))
                continue
            return self._result(url, method, a, attempts, started)


class AsyncHttpClient(_Core):
    """비동기 클라이언트. ``async with AsyncHttpClient() as c: r = await c.get(url)``."""

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        rate_per_host: float | None = None,
        max_retries: int | None = None,
        timeout_s: float | None = None,
        backoff_base_s: float | None = None,
        backoff_max_s: float | None = None,
        jitter: float = 0.1,
        respect_robots: bool = True,
        robots_ttl_s: float = ROBOTS_TTL_S,
        robots_exempt_hosts: Iterable[str] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        transport: httpx.AsyncBaseTransport | None = None,
        allow_private: bool | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        super().__init__(
            user_agent=user_agent,
            rate_per_host=rate_per_host,
            max_retries=max_retries,
            timeout_s=timeout_s,
            backoff_base_s=backoff_base_s,
            backoff_max_s=backoff_max_s,
            jitter=jitter,
            respect_robots=respect_robots,
            robots_ttl_s=robots_ttl_s,
            robots_exempt_hosts=robots_exempt_hosts,
            clock=clock,
            allow_private=allow_private,
            resolver=resolver if resolver is not None else (_system_resolve if transport is None else None),
        )
        self._sleep = sleep
        self._robots_locks: dict[str, asyncio.Lock] = {}

        async def hook(request: httpx.Request) -> None:
            self._request_hook_check(request)

        self._client = httpx.AsyncClient(
            timeout=self.timeout_s,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
            transport=transport,
            event_hooks={"request": [hook]},
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, url: str, **kw: Any) -> FetchResult:
        return await self.fetch(url, method="GET", **kw)

    async def post(self, url: str, **kw: Any) -> FetchResult:
        return await self.fetch(url, method="POST", **kw)

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        params: RequestBody = None,
        data: RequestBody = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> FetchResult:
        method = method.upper()
        u = self._parse(url)
        if u is None:
            return self._invalid(url, method)
        reason = self.blocked_reason(u.host)
        if reason is not None:
            return self._blocked_host(url, method, reason)
        if self._checks_robots(u):
            entry = await self._robots_for(u)
            if not entry.allows(self.user_agent, str(u)):
                return self._blocked(url, method, entry)
        return await self._send(url, u, method, params=params, data=data, json=json, headers=headers)

    async def _robots_for(self, u: httpx.URL) -> _RobotsEntry:
        origin = self._origin(u)
        lock = self._robots_locks.setdefault(origin, asyncio.Lock())
        async with lock:
            entry = self._robots_cached(origin)
            if entry is None:
                robots_url = f"{origin}/robots.txt"
                r = await self._send(robots_url, httpx.URL(robots_url), "GET")
                entry = self._robots_entry(r)
                self._robots[origin] = entry
        return entry

    async def _send(
        self,
        url: str,
        u: httpx.URL,
        method: str,
        *,
        params: RequestBody = None,
        data: RequestBody = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> FetchResult:
        host = self._host_key(u)
        started = self._clock()
        attempts = 0
        while True:
            wait = self._reserve(host)
            if wait > 0:
                await self._sleep(wait)
            attempts += 1
            try:
                resp = await self._client.request(
                    method, url, params=params, data=data, json=json, headers=headers
                )
                a = _Attempt(response=resp)
            except httpx.HTTPError as exc:
                a = self._classify(exc)
            if self._retryable(a) and attempts <= self.max_retries:
                if a.response is not None:
                    await a.response.aclose()
                await self._sleep(self._backoff(attempts))
                continue
            return self._result(url, method, a, attempts, started)
