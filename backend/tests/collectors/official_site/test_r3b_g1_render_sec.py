"""R3b G1 — R3_REVIEW2 F1b (official_site 렌더):

- 팝업 서명: 이미지 주소의 캐시버스터(``?v=``·``?t=``·숫자만 쿼리)·fragment 는 서명에 넣지 않는다.
  경로·의미 있는 쿼리가 다르면 다른 서명. 글자 해시(``text_sha256``)는 공백·제로폭 문자·유니코드
  정규화에 흔들리지 않는다(D10-2).
- Playwright SSRF: ``page.goto`` 전에 같은 URL 검사(스킴·내부망·DNS), 본 호스트는 검사한 IP 로 고정
  (``--host-resolver-rules``), 모든 하위 요청은 ``context.route`` 로 검사해 내부망이면 abort,
  리다이렉트 경유·최종 URL 이 내부망이면 렌더 결과를 버린다. prod 에서 allow_private 거부.
  대부분 브라우저 없이 가짜 Playwright 객체로 시험하고, chromium 이 있으면 실제 고정·abort 도 본다.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from pydantic import SecretStr

from app.collectors.official_site.render import (
    BrowserGuard,
    PlaywrightRenderer,
    PopupShot,
    RenderResult,
    normalize_image_url,
    normalize_popup_text,
    popup_hash,
    popup_signature,
)
from app.core.http import PrivateHostsInProdError
from app.core.settings import Settings, set_settings

PUBLIC_IP = "93.184.216.34"


def _shot(images: tuple[str, ...] = (), text: str = "잔여 세대 안내") -> PopupShot:
    return PopupShot(selector="#pop", sha256="a" * 64, width=300, height=200, images=images, text=text)


# ====================================================================== 팝업 서명 쿼리 정규화


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("https://site.kr/img/pop.jpg?v=1", "https://site.kr/img/pop.jpg?v=2"),
        ("https://site.kr/img/pop.jpg?t=1696845123", "https://site.kr/img/pop.jpg?t=1696845999"),
        ("https://site.kr/img/pop.jpg?20261009", "https://site.kr/img/pop.jpg?20261010"),
        ("https://site.kr/img/pop.jpg?_=1&ver=3", "https://site.kr/img/pop.jpg"),
        ("https://site.kr/img/pop.jpg#top", "https://site.kr/img/pop.jpg"),
        ("https://SITE.kr/img/pop.jpg", "https://site.kr/img/pop.jpg"),
        ("https://site.kr/view.php?id=7&v=1", "https://site.kr/view.php?v=9&id=7"),
    ],
)
def test_f1b_popup_signature_ignores_cache_buster(a: str, b: str) -> None:
    assert normalize_image_url(a) == normalize_image_url(b)
    assert popup_signature(_shot((a,))) == popup_signature(_shot((b,)))
    assert popup_hash([_shot((a,))]) == popup_hash([_shot((b,))])


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("https://site.kr/img/pop1.jpg?v=1", "https://site.kr/img/pop2.jpg?v=1"),  # 다른 경로
        ("https://site.kr/view.php?id=7", "https://site.kr/view.php?id=8"),  # 의미 있는 쿼리
        ("https://site.kr/img/pop.jpg", "https://cdn.site.kr/img/pop.jpg"),  # 다른 호스트
    ],
)
def test_f1b_popup_signature_detects_real_image_change(a: str, b: str) -> None:
    assert popup_signature(_shot((a,))) != popup_signature(_shot((b,)))


def test_f1b_popup_meta_keeps_raw_image_urls_and_contract_fields() -> None:
    meta = _shot(("https://site.kr/p.jpg?v=5",)).as_meta()
    assert meta["images"] == ["https://site.kr/p.jpg?v=5"]  # 계약 필드 값은 관찰 그대로
    assert set(meta) == {
        "selector",
        "sha256",
        "width",
        "height",
        "images",
        "text_sha256",
        "dhash",
        "signature",
    }


@pytest.mark.parametrize(
    "variant",
    [
        "잔여  세대\n안내",
        " 잔여 세대 안내 ",
        "잔여\u00a0세대\t안내",
        "잔여\u200b 세대 안내\ufeff",
        "잔여 세대 안내",  # 이미 정규화된 글자
    ],
)
def test_f1b_popup_text_hash_stable_over_whitespace(variant: str) -> None:
    """D10-2: 접수 상태 분류 복사는 text_sha256 이 같을 때만 — 공백·제로폭 문자 차이로 해시가
    바뀌면 안 된다."""
    base = _shot(text="잔여 세대 안내")
    other = _shot(text=variant)
    assert other.as_meta()["text_sha256"] == base.as_meta()["text_sha256"]
    assert popup_signature(other) == popup_signature(base)
    assert base.as_meta()["text_sha256"] == hashlib.sha256("잔여 세대 안내".encode()).hexdigest()


def test_f1b_popup_text_nfc_normalized() -> None:
    nfd = "\u1100\u1161\u11a8 안내"  # '각' 의 자모 분해형(NFD)
    assert normalize_popup_text(nfd) == normalize_popup_text("각 안내")
    assert normalize_popup_text("잔여 3세대") != normalize_popup_text("잔여 2세대")


# ====================================================================== Playwright SSRF — goto 전 검사


@pytest.fixture
def no_browser(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """브라우저를 띄우려 하면 기록하고 실패시킨다(검사가 먼저 막아야 한다)."""
    launched: list[str] = []

    def boom(*a: Any, **kw: Any) -> Any:
        launched.append("sync_playwright")
        raise AssertionError("브라우저를 띄우면 안 된다")

    import playwright.sync_api

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", boom)
    return launched


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/",
        "http://localhost/",
        "http://100.64.0.1/",
        "http://[fd00::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "chrome://settings",
        "javascript:alert(1)",
    ],
)
def test_f1b_render_checks_url_before_goto(url: str, no_browser: list[str]) -> None:
    result = PlaywrightRenderer(allow_private=False).render(url)
    assert result.error is not None and result.error.startswith("blocked_host"), result.error
    assert not result.ok and no_browser == []


def test_f1b_render_dns_to_private_blocked_before_goto(no_browser: list[str]) -> None:
    renderer = PlaywrightRenderer(allow_private=False, resolver=lambda h: ["10.1.2.3"])
    result = renderer.render("https://intranet.corp-internal.kr/")
    assert (result.error or "").startswith("blocked_host") and no_browser == []


def test_f1b_render_prod_refuses_allow_private() -> None:
    set_settings(
        Settings(_env_file=None, env="prod", api_token=SecretStr("tok-123456"), http_allow_private_hosts=True)  # type: ignore[call-arg]
    )
    try:
        with pytest.raises(PrivateHostsInProdError):
            PlaywrightRenderer()
        with pytest.raises(PrivateHostsInProdError):
            PlaywrightRenderer(allow_private=True)
    finally:
        set_settings(None)


# ====================================================================== 가짜 Playwright


class FakeRequest:
    def __init__(
        self, url: str, *, navigation: bool = False, redirected_from: FakeRequest | None = None
    ) -> None:
        self.url = url
        self.redirected_from = redirected_from
        self._navigation = navigation

    def is_navigation_request(self) -> bool:
        return self._navigation


class FakeRoute:
    def __init__(self, request: FakeRequest) -> None:
        self.request = request
        self.outcome: str | None = None

    def abort(self, error_code: str | None = None) -> None:
        self.outcome = f"abort:{error_code}"

    def continue_(self) -> None:
        self.outcome = "continue"


class FakeResponse:
    status = 200


class NavError(Exception):
    pass


class FakePage:
    def __init__(self, ctx: FakeContext) -> None:
        self._ctx = ctx
        self.url = "about:blank"

    def goto(self, url: str, **kw: Any) -> FakeResponse:
        self._ctx.log.append(f"goto {url}")
        for req in self._ctx.script(url):
            for listener in self._ctx.listeners:
                listener(req)
            if req.redirected_from is None:  # Playwright: 리다이렉트 단계는 route 를 거치지 않는다
                route = FakeRoute(req)
                assert self._ctx.handler is not None, "goto 전에 route 를 걸어야 한다"
                self._ctx.handler(route)
                self._ctx.routes.append(route)
                if req.is_navigation_request() and route.outcome != "continue":
                    from playwright.sync_api import Error as PlaywrightError

                    raise PlaywrightError(f"net::ERR_BLOCKED_BY_CLIENT at {req.url}")
            if req.is_navigation_request():
                self.url = req.url
        return FakeResponse()


class FakeContext:
    def __init__(self, script: Callable[[str], list[FakeRequest]], log: list[str]) -> None:
        self.script = script
        self.log = log
        self.handler: Callable[[Any], None] | None = None
        self.listeners: list[Callable[[Any], None]] = []
        self.routes: list[FakeRoute] = []
        self.kwargs: dict[str, Any] = {}

    def route(self, pattern: str, handler: Callable[[Any], None]) -> None:
        self.log.append(f"route {pattern}")
        self.handler = handler

    def route_web_socket(self, pattern: str, handler: Callable[[Any], None]) -> None:
        self.log.append(f"route_web_socket {pattern}")

    def on(self, event: str, cb: Callable[[Any], None]) -> None:
        if event == "request":
            self.listeners.append(cb)

    def new_page(self) -> FakePage:
        return FakePage(self)


class FakeBrowser:
    def __init__(self, ctx: FakeContext) -> None:
        self.ctx = ctx
        self.closed = False

    def new_context(self, **kw: Any) -> FakeContext:
        self.ctx.kwargs = kw
        return self.ctx

    def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser
        self.launch_kwargs: dict[str, Any] = {}

    def launch(self, **kw: Any) -> FakeBrowser:
        self.launch_kwargs = kw
        return self.browser


class FakePlaywright:
    def __init__(self, script: Callable[[str], list[FakeRequest]]) -> None:
        self.log: list[str] = []
        self.context = FakeContext(script, self.log)
        self.browser = FakeBrowser(self.context)
        self.chromium = FakeChromium(self.browser)


def _resolver(table: dict[str, list[str]]) -> Callable[[str], list[str]]:
    return lambda host: table.get(host, [PUBLIC_IP])


def _run(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    script: Callable[[str], list[FakeRequest]],
    resolver: Callable[[str], list[str]],
) -> tuple[RenderResult, FakePlaywright]:
    renderer = PlaywrightRenderer(allow_private=False, resolver=resolver, settle_ms=0)
    fake = FakePlaywright(script)
    monkeypatch.setattr(PlaywrightRenderer, "_settle", lambda self, page: None)
    monkeypatch.setattr(
        PlaywrightRenderer,
        "_capture",
        lambda self, page, u, response: RenderResult(
            url=u, final_url=page.url, status=200, screenshot_png=b"png"
        ),
    )
    guard = renderer.guard()
    reason = guard.prepare(url)
    assert reason is None, reason
    return renderer._render_with(fake, url, guard, "test-ua"), fake


def test_f1b_render_route_installed_before_goto_and_private_subrequests_aborted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://www.public-site.kr/"

    def script(u: str) -> list[FakeRequest]:
        return [
            FakeRequest(u, navigation=True),
            FakeRequest("https://cdn.public-site.kr/pop.jpg"),
            FakeRequest("http://10.0.0.5/admin"),
            FakeRequest("http://intranet.corp-internal.kr/x.png"),
            FakeRequest("http://[::1]:9200/_cat"),
            FakeRequest("data:image/png;base64,AAAA"),
        ]

    result, fake = _run(monkeypatch, url, script, _resolver({"intranet.corp-internal.kr": ["192.168.0.9"]}))
    assert result.ok and result.error is None
    assert fake.log[:3] == ["route **/*", "route_web_socket **/*", f"goto {url}"]  # 검사 훅이 이동보다 먼저
    assert str(fake.chromium.launch_kwargs["proxy"]["server"]).startswith("http://127.0.0.1:")  # 출구 프록시
    outcomes = {r.request.url: r.outcome for r in fake.context.routes}
    assert outcomes[url] == "continue"
    assert outcomes["https://cdn.public-site.kr/pop.jpg"] == "continue"
    assert outcomes["data:image/png;base64,AAAA"] == "continue"
    for bad in ("http://10.0.0.5/admin", "http://intranet.corp-internal.kr/x.png", "http://[::1]:9200/_cat"):
        assert outcomes[bad] == "abort:blockedbyclient", bad
    assert fake.context.kwargs.get("service_workers") == "block"  # 서비스 워커는 route 를 우회한다
    assert fake.browser.closed


def test_f1b_render_pins_main_host_to_validated_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """본 호스트는 검사한 IP 로 고정한다 — 브라우저가 다시 풀 때 다른 IP(rebinding)를 받지 않게."""
    calls: list[str] = []

    def resolver(host: str) -> list[str]:
        calls.append(host)
        return [PUBLIC_IP] if len(calls) == 1 else ["127.0.0.1"]

    url = "https://www.public-site.kr/index.html"
    result, fake = _run(monkeypatch, url, lambda u: [FakeRequest(u, navigation=True)], resolver)
    args = fake.chromium.launch_kwargs.get("args") or []
    rules = f"MAP www.public-site.kr {PUBLIC_IP}, MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"
    assert f"--host-resolver-rules={rules}" in args
    assert result.ok


def test_f1b_render_pin_ipv6_bracketed() -> None:
    guard = PlaywrightRenderer(allow_private=False, resolver=lambda h: ["2606:4700:4700::1111"]).guard()
    assert guard.prepare("https://v6.public-site.kr/") is None
    assert guard.launch_args()[0] == (
        "--host-resolver-rules=MAP v6.public-site.kr [2606:4700:4700::1111], "
        "MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"
    )


def test_f1b_render_redirect_hop_to_private_discards_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """리다이렉트 단계는 route 를 거치지 않는다 → request 이벤트로 잡아 렌더 결과를 버린다."""
    url = "https://www.public-site.kr/"

    def script(u: str) -> list[FakeRequest]:
        first = FakeRequest(u, navigation=True)
        return [first, FakeRequest("http://192.168.0.1/router", navigation=True, redirected_from=first)]

    result, _ = _run(monkeypatch, url, script, _resolver({}))
    assert not result.ok and (result.error or "").startswith("blocked_host"), result
    assert "리다이렉트" in (result.error or "") and result.screenshot_png == b""


def test_f1b_render_main_navigation_blocked_by_route_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """본문 이동(예: JS location 변경)이 내부망이면 route 가 막고, 결과는 blocked_host 오류."""
    url = "https://www.public-site.kr/"

    def script(u: str) -> list[FakeRequest]:
        return [FakeRequest("http://169.254.169.254/latest/meta-data/", navigation=True)]

    result, _ = _run(monkeypatch, url, script, _resolver({}))
    assert not result.ok and (result.error or "").startswith("blocked_host"), result


def test_f1b_browser_guard_allow_private_passes_everything() -> None:
    guard = PlaywrightRenderer(allow_private=True).guard()
    assert guard.prepare("http://127.0.0.1:8000/") is None
    assert guard.url_reason("http://10.0.0.1/") is None
    assert not any(a.startswith("--host-resolver-rules") for a in guard.launch_args())
    assert guard.url_reason("file:///etc/passwd") is not None  # 스킴 제한은 그대로


def test_f1b_browser_guard_records_blocked_subrequests() -> None:
    guard = BrowserGuard(allow_private=False, resolver=lambda h: [PUBLIC_IP])
    route = FakeRoute(FakeRequest("http://10.9.9.9/x.png"))
    guard.on_route(route)
    assert route.outcome == "abort:blockedbyclient" and guard.violation is None
    assert guard.blocked == ["blocked_host: 내부망 주소 10.9.9.9 (http://10.9.9.9/x.png)"]


# ====================================================================== 실제 chromium(설치돼 있으면)

_PAGE = (
    "<!doctype html><html><body><h1>pinned</h1>"
    '<img src="/ok.png" width="10" height="10"><img src="/blocked.png" width="10" height="10">'
    "</body></html>"
)


@pytest.fixture
def recording_site() -> Iterator[tuple[int, list[tuple[str, str | None]]]]:
    seen: list[tuple[str, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append((self.path, self.headers.get("Host")))
            is_page = self.path.startswith("/index")
            body = _PAGE.encode() if is_page else b""
            self.send_response(200 if is_page else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], seen
    finally:
        server.shutdown()
        server.server_close()


class _PathGuard(BrowserGuard):
    """실제 chromium 시험용: 내부망 판정 대신 '/blocked' 경로를 막는다(로컬 서버밖에 없으므로)."""

    def url_reason(self, url: str) -> str | None:
        return "blocked_host: test" if "/blocked" in url else super().url_reason(url)


def test_f1b_real_chromium_pins_host_and_aborts_blocked_subrequest(
    recording_site: tuple[int, list[tuple[str, str | None]]],
) -> None:
    """실제 chromium: --host-resolver-rules 로 이름을 고정 IP 로 연결하고(Host 헤더는 이름 그대로), route 가
    하위 요청을 abort 한다(서버가 그 요청을 받지 않는다)."""
    probe = PlaywrightRenderer(allow_private=True, settle_ms=0).render("about:blank")
    if probe.error and ("Executable doesn't exist" in probe.error or "playwright install" in probe.error):
        pytest.skip(f"Playwright chromium 미설치: {probe.error}")
    from playwright.sync_api import sync_playwright

    port, seen = recording_site
    renderer = PlaywrightRenderer(allow_private=True, settle_ms=50, timeout_ms=20_000)
    guard = _PathGuard(allow_private=True, resolver=lambda h: [])
    guard.pins["pinned.example.com"] = "127.0.0.1"
    url = f"http://pinned.example.com:{port}/index.html"
    with sync_playwright() as p:
        result = renderer._render_with(p, url, guard, "test-ua")
    assert result.ok, result.error
    paths = [path for path, _ in seen]
    assert "/index.html" in paths and "/ok.png" in paths and "/blocked.png" not in paths
    assert ("/index.html", f"pinned.example.com:{port}") in seen
    assert any("/blocked.png" in b for b in guard.blocked)
