"""수집용 HTTP 클라이언트 (RA §4-3 Collector 규칙, AGENTS 규칙 7·18).

- 호스트별 속도 제한(기본 ``HTTP_RATE_PER_HOST`` = 1 req/s; robots.txt 요청과 재시도도 포함)
- 지수 백오프 재시도: 5xx·타임아웃·연결 오류만. 4xx 는 재시도하지 않는다(429 포함).
- robots.txt 확인·캐시(RFC 9309): 2xx → 규칙 적용, 4xx → 제한 없음, 5xx·네트워크 실패 → 전부 불허.
  불허면 요청하지 않고 ``FetchResult(error="blocked_by_robots")`` 를 돌려준다.
- **예외를 삼키지도 던지지도 않는다**: 성공·실패 모두 ``FetchResult`` 로 반환한다.

동기 ``HttpClient`` 와 비동기 ``AsyncHttpClient`` 는 같은 규칙을 공유한다. 테스트는 ``sleep``·``clock`` 을
주입해 실제로 기다리지 않는다.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import threading
import time
import urllib.robotparser
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Literal, Self

import httpx

from app.core.settings import get_settings

ErrorKind = Literal["http_status", "timeout", "connect", "network", "robots", "invalid_url"]
BLOCKED_BY_ROBOTS = "blocked_by_robots"
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

    @property
    def ok(self) -> bool:
        return self.error is None and self.status is not None and 200 <= self.status < 400

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    def text(self, encoding: str | None = None) -> str:
        enc = encoding or _charset(self.headers.get("content-type", "")) or "utf-8"
        return self.content.decode(enc, errors="replace")


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

    def allows(self, user_agent: str, url: str) -> bool:
        if self.parser is None:
            return self.allow_all
        return self.parser.can_fetch(user_agent, url)


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
        clock: Callable[[], float],
    ) -> None:
        s = get_settings()
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
            return _RobotsEntry(parser, allow_all=True, expires_at=now + self.robots_ttl_s)
        if r.status is not None and 400 <= r.status < 500:
            return _RobotsEntry(None, allow_all=True, expires_at=now + self.robots_ttl_s)
        # 5xx·네트워크 실패 = unreachable → 전부 불허(짧게 캐시)
        ttl = min(self.robots_ttl_s, ROBOTS_UNREACHABLE_TTL_S)
        return _RobotsEntry(None, allow_all=False, expires_at=now + ttl)

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
    def _blocked(url: str, method: str) -> FetchResult:
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
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        transport: httpx.BaseTransport | None = None,
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
            clock=clock,
        )
        self._sleep = sleep
        self._robots_lock = threading.Lock()
        self._client = httpx.Client(
            timeout=self.timeout_s,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
            transport=transport,
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
        if self.respect_robots and not self._robots_allows(u):
            return self._blocked(url, method)
        return self._send(url, u, method, params=params, data=data, json=json, headers=headers)

    def _robots_allows(self, u: httpx.URL) -> bool:
        origin = self._origin(u)
        with self._robots_lock:
            entry = self._robots_cached(origin)
            if entry is None:
                robots_url = f"{origin}/robots.txt"
                r = self._send(robots_url, httpx.URL(robots_url), "GET")
                entry = self._robots_entry(r)
                self._robots[origin] = entry
        return entry.allows(self.user_agent, str(u))

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
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        transport: httpx.AsyncBaseTransport | None = None,
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
            clock=clock,
        )
        self._sleep = sleep
        self._robots_locks: dict[str, asyncio.Lock] = {}
        self._client = httpx.AsyncClient(
            timeout=self.timeout_s,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
            transport=transport,
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
        if self.respect_robots and not await self._robots_allows(u):
            return self._blocked(url, method)
        return await self._send(url, u, method, params=params, data=data, json=json, headers=headers)

    async def _robots_allows(self, u: httpx.URL) -> bool:
        origin = self._origin(u)
        lock = self._robots_locks.setdefault(origin, asyncio.Lock())
        async with lock:
            entry = self._robots_cached(origin)
            if entry is None:
                robots_url = f"{origin}/robots.txt"
                r = await self._send(robots_url, httpx.URL(robots_url), "GET")
                entry = self._robots_entry(r)
                self._robots[origin] = entry
        return entry.allows(self.user_agent, str(u))

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
