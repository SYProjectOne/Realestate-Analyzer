"""core.http — 재시도·백오프·속도 제한·robots·실패 결과 반환 (respx, 오프라인)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from app.core.http import AsyncHttpClient, FetchResult, HttpClient

UA = "test-agent/1.0 (+offline tests)"
ALLOW_ALL = "User-agent: *\nDisallow:\n"


class FakeClock:
    """sleep 이 시계를 앞으로 민다. 실제로 기다리지 않는다."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 6))
        self.now += seconds

    async def asleep(self, seconds: float) -> None:
        self.sleep(seconds)


def client(clock: FakeClock, **kw: Any) -> HttpClient:
    opts: dict[str, Any] = {
        "user_agent": UA,
        "rate_per_host": 1.0,
        "max_retries": 3,
        "backoff_base_s": 1.0,
        "backoff_max_s": 30.0,
        "jitter": 0.0,
        "timeout_s": 5.0,
        "sleep": clock.sleep,
        "clock": clock.monotonic,
    }
    opts.update(kw)
    return HttpClient(**opts)


def aclient(clock: FakeClock, **kw: Any) -> AsyncHttpClient:
    opts: dict[str, Any] = {
        "user_agent": UA,
        "rate_per_host": 1.0,
        "max_retries": 3,
        "backoff_base_s": 1.0,
        "backoff_max_s": 30.0,
        "jitter": 0.0,
        "timeout_s": 5.0,
        "sleep": clock.asleep,
        "clock": clock.monotonic,
    }
    opts.update(kw)
    return AsyncHttpClient(**opts)


# ---------------------------------------------------------------- 성공·결과 형태


@respx.mock
def test_success_returns_result_object() -> None:
    respx.get("https://a.test/robots.txt").respond(200, text=ALLOW_ALL)
    route = respx.get("https://a.test/page").respond(200, content=b"<html>ok</html>", headers={"X-A": "1"})
    clock = FakeClock()
    with client(clock) as c:
        r = c.get("https://a.test/page")
    assert isinstance(r, FetchResult)
    assert r.url == "https://a.test/page"
    assert r.status == 200
    assert r.content == b"<html>ok</html>"
    assert r.headers["x-a"] == "1"
    assert r.error is None
    assert r.error_kind is None
    assert r.ok
    assert r.attempts == 1
    assert r.elapsed_ms >= 0
    assert r.blocked_by_robots is False
    assert r.fetched_at.tzinfo is not None
    assert len(r.sha256) == 64
    assert route.calls.last.request.headers["user-agent"] == UA


@respx.mock
def test_post_form_passes_through() -> None:
    respx.get("https://a.test/robots.txt").respond(200, text=ALLOW_ALL)
    route = respx.post("https://a.test/list").respond(200, json={"rows": []})
    clock = FakeClock()
    with client(clock) as c:
        r = c.post("https://a.test/list", data={"sido": "11"})
    assert r.status == 200
    assert r.method == "POST"
    assert route.calls.last.request.content == b"sido=11"


# ---------------------------------------------------------------- 재시도·백오프


@respx.mock
def test_retries_5xx_with_exponential_backoff() -> None:
    respx.get("https://a.test/x").mock(
        side_effect=[httpx.Response(503), httpx.Response(502), httpx.Response(200, text="ok")]
    )
    clock = FakeClock()
    with client(clock, respect_robots=False) as c:
        r = c.get("https://a.test/x")
    assert r.status == 200
    assert r.ok
    assert r.attempts == 3
    assert clock.sleeps == [1.0, 2.0]


@respx.mock
def test_5xx_exhausted_returns_failure_not_exception() -> None:
    route = respx.get("https://a.test/x").respond(503)
    clock = FakeClock()
    with client(clock, respect_robots=False, max_retries=2) as c:
        r = c.get("https://a.test/x")
    assert route.call_count == 3
    assert r.attempts == 3
    assert r.status == 503
    assert not r.ok
    assert r.error_kind == "http_status"
    assert r.error is not None and "503" in r.error
    assert clock.sleeps == [1.0, 2.0]


@respx.mock
def test_backoff_capped() -> None:
    respx.get("https://a.test/x").respond(500)
    clock = FakeClock()
    with client(clock, respect_robots=False, max_retries=4, backoff_max_s=3.0) as c:
        c.get("https://a.test/x")
    assert clock.sleeps == [1.0, 2.0, 3.0, 3.0]


@pytest.mark.parametrize("code", [400, 403, 404, 410, 429])
@respx.mock
def test_4xx_not_retried(code: int) -> None:
    route = respx.get("https://a.test/x").respond(code)
    clock = FakeClock()
    with client(clock, respect_robots=False) as c:
        r = c.get("https://a.test/x")
    assert route.call_count == 1
    assert r.attempts == 1
    assert r.status == code
    assert r.error_kind == "http_status"
    assert not r.ok
    assert clock.sleeps == []


@respx.mock
def test_timeout_retried_then_returned_as_data() -> None:
    route = respx.get("https://a.test/slow").mock(side_effect=httpx.ReadTimeout("slow"))
    clock = FakeClock()
    with client(clock, respect_robots=False) as c:
        r = c.get("https://a.test/slow")
    assert route.call_count == 4  # 1 + max_retries
    assert r.attempts == 4
    assert r.status is None
    assert r.content == b""
    assert r.error_kind == "timeout"
    assert r.error is not None
    assert not r.ok


@respx.mock
def test_connect_error_retried_then_success() -> None:
    respx.get("https://a.test/x").mock(
        side_effect=[httpx.ConnectError("refused"), httpx.Response(200, text="ok")]
    )
    clock = FakeClock()
    with client(clock, respect_robots=False) as c:
        r = c.get("https://a.test/x")
    assert r.ok
    assert r.attempts == 2


@respx.mock
def test_connect_error_exhausted_kind() -> None:
    respx.get("https://dns-fail.test/x").mock(side_effect=httpx.ConnectError("Name or service not known"))
    clock = FakeClock()
    with client(clock, respect_robots=False, max_retries=1) as c:
        r = c.get("https://dns-fail.test/x")
    assert r.error_kind == "connect"
    assert r.status is None
    assert r.attempts == 2


def test_invalid_url_is_result() -> None:
    clock = FakeClock()
    with client(clock) as c:
        r = c.get("not a url")
        r2 = c.get("ftp://a.test/file")
    assert r.error_kind == "invalid_url"
    assert r.attempts == 0
    assert r2.error_kind == "invalid_url"


# ---------------------------------------------------------------- 속도 제한


@respx.mock
def test_rate_limit_per_host() -> None:
    respx.get(url__regex=r"https://a\.test/.*").respond(200)
    respx.get(url__regex=r"https://b\.test/.*").respond(200)
    clock = FakeClock()
    with client(clock, respect_robots=False, rate_per_host=1.0) as c:
        c.get("https://a.test/1")
        c.get("https://b.test/1")  # 다른 호스트: 기다리지 않음
        assert clock.sleeps == []
        c.get("https://a.test/2")  # 같은 호스트: 1초 간격
        assert clock.sleeps == [1.0]
        c.get("https://a.test/3")
        assert clock.sleeps == [1.0, 1.0]


@respx.mock
def test_rate_limit_fractional_rate() -> None:
    respx.get(url__regex=r"https://a\.test/.*").respond(200)
    clock = FakeClock()
    with client(clock, respect_robots=False, rate_per_host=0.5) as c:
        c.get("https://a.test/1")
        c.get("https://a.test/2")
    assert clock.sleeps == [2.0]


@respx.mock
def test_rate_limit_counts_elapsed_time() -> None:
    respx.get(url__regex=r"https://a\.test/.*").respond(200)
    clock = FakeClock()
    with client(clock, respect_robots=False, rate_per_host=1.0) as c:
        c.get("https://a.test/1")
        clock.now += 0.4
        c.get("https://a.test/2")
    assert clock.sleeps == [0.6]


# ---------------------------------------------------------------- robots.txt


@respx.mock
def test_robots_disallow_blocks_without_request() -> None:
    respx.get("https://a.test/robots.txt").respond(200, text="User-agent: *\nDisallow: /private\n")
    private = respx.get("https://a.test/private/doc").respond(200)
    public = respx.get("https://a.test/public").respond(200)
    clock = FakeClock()
    with client(clock) as c:
        blocked = c.get("https://a.test/private/doc")
        allowed = c.get("https://a.test/public")
    assert private.call_count == 0
    assert blocked.blocked_by_robots is True
    assert blocked.error == "blocked_by_robots"
    assert blocked.error_kind == "robots"
    assert blocked.status is None
    assert blocked.attempts == 0
    assert not blocked.ok
    assert public.call_count == 1
    assert allowed.ok


@respx.mock
def test_robots_specific_user_agent() -> None:
    respx.get("https://a.test/robots.txt").respond(
        200, text="User-agent: test-agent\nDisallow: /\n\nUser-agent: *\nDisallow:\n"
    )
    page = respx.get("https://a.test/x").respond(200)
    clock = FakeClock()
    with client(clock) as c:
        r = c.get("https://a.test/x")
    assert r.blocked_by_robots
    assert page.call_count == 0


@respx.mock
def test_robots_cached_per_origin() -> None:
    robots = respx.get("https://a.test/robots.txt").respond(200, text=ALLOW_ALL)
    respx.get(url__regex=r"https://a\.test/p\d").respond(200)
    clock = FakeClock()
    with client(clock) as c:
        c.get("https://a.test/p1")
        c.get("https://a.test/p2")
        c.get("https://a.test/p3")
    assert robots.call_count == 1


@respx.mock
def test_robots_cache_expires() -> None:
    robots = respx.get("https://a.test/robots.txt").respond(200, text=ALLOW_ALL)
    respx.get("https://a.test/p").respond(200)
    clock = FakeClock()
    with client(clock, robots_ttl_s=60.0) as c:
        c.get("https://a.test/p")
        clock.now += 61
        c.get("https://a.test/p")
    assert robots.call_count == 2


@respx.mock
def test_robots_request_is_rate_limited_too() -> None:
    respx.get("https://a.test/robots.txt").respond(200, text=ALLOW_ALL)
    respx.get("https://a.test/p").respond(200)
    clock = FakeClock()
    with client(clock) as c:
        c.get("https://a.test/p")
    assert clock.sleeps == [1.0]  # robots.txt 다음 페이지 요청까지 1초


@pytest.mark.parametrize("code", [401, 403, 404])
@respx.mock
def test_robots_4xx_means_allow(code: int) -> None:
    # RFC 9309 §2.3.1.3: robots.txt 가 unavailable(4xx)면 제한 없음
    respx.get("https://a.test/robots.txt").respond(code)
    page = respx.get("https://a.test/p").respond(200)
    clock = FakeClock()
    with client(clock) as c:
        r = c.get("https://a.test/p")
    assert r.ok
    assert page.call_count == 1


@respx.mock
def test_robots_5xx_means_disallow() -> None:
    # RFC 9309 §2.3.1.4: unreachable(5xx·네트워크)이면 전부 불허로 본다
    respx.get("https://a.test/robots.txt").respond(500)
    page = respx.get("https://a.test/p").respond(200)
    clock = FakeClock()
    with client(clock, max_retries=1) as c:
        r = c.get("https://a.test/p")
    assert r.blocked_by_robots
    assert page.call_count == 0


# ---------------------------------------------------------------- 비동기


@respx.mock
async def test_async_success_and_robots() -> None:
    respx.get("https://a.test/robots.txt").respond(200, text="User-agent: *\nDisallow: /no\n")
    respx.get("https://a.test/yes").respond(200, text="ok")
    no = respx.get("https://a.test/no").respond(200)
    clock = FakeClock()
    async with aclient(clock) as c:
        ok = await c.get("https://a.test/yes")
        blocked = await c.get("https://a.test/no")
    assert ok.ok and ok.attempts == 1
    assert blocked.blocked_by_robots
    assert no.call_count == 0


@respx.mock
async def test_async_retry_backoff_and_failure_result() -> None:
    respx.get("https://a.test/x").mock(side_effect=[httpx.Response(500), httpx.Response(200)])
    respx.get("https://a.test/t").mock(side_effect=httpx.ConnectTimeout("t"))
    respx.get("https://a.test/f").respond(404)
    clock = FakeClock()
    async with aclient(clock, respect_robots=False, max_retries=2) as c:
        r = await c.get("https://a.test/x")
        assert r.ok and r.attempts == 2
        t = await c.get("https://a.test/t")
        assert t.error_kind == "timeout" and t.attempts == 3 and t.status is None
        f = await c.get("https://a.test/f")
        assert f.status == 404 and f.attempts == 1


@respx.mock
async def test_async_rate_limit() -> None:
    respx.get(url__regex=r"https://a\.test/.*").respond(200)
    clock = FakeClock()
    async with aclient(clock, respect_robots=False) as c:
        await c.get("https://a.test/1")
        await c.get("https://a.test/2")
    assert clock.sleeps == [1.0]


def test_defaults_from_settings(test_settings: Any) -> None:
    c = HttpClient()
    try:
        assert c.rate_per_host == test_settings.http_rate_per_host
        assert c.max_retries == test_settings.http_max_retries
        assert c.user_agent == test_settings.http_user_agent
        assert c.respect_robots is True
    finally:
        c.close()
