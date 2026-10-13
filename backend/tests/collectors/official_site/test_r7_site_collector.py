"""R7-SITE 수집기 — 팝업 그림 OCR(D26-1)·TLS 실패 사이트의 브라우저 경로(D26-4).

- D26-1: 렌더한 팝업 요소 그림(PNG)을 D5 OCR 엔진으로 읽어 스크린샷 행 meta 에 둔다(라벨 '추정(OCR)', 그림 sha256·경로·확인 시각).
  같은 그림이면 다시 읽지 않는다(그림 해시 캐시) — 접수 classify 입력이 그대로(D10-2). 엔진이 없으면 사유를 남긴다. 시간 예산(D5).
- D26-4: 인천 첫 실행 TLS 9행 — robots.txt 요청부터 TLS 실패라 RFC 9309 '전부 불허'로 본문을 받지 않았다(hillstate.co.kr 서명 방식,
  중간 인증서 누락 등). httpx 가 TLS 로 실패하면 브라우저(인증서 검증 켬)로 robots.txt·본문을 다시 받고, robots 는 그대로 지킨다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import datetime as dt
import hashlib
import ssl
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.official_site import (
    OfficialSiteCollector,
    PlaywrightRenderer,
    PopupShot,
    RenderResult,
    SiteTarget,
)
from app.collectors.official_site.collector import OCR_META_KIND, popup_ocr_texts, robots_verdict
from app.collectors.official_site.render import BrowserFetch, is_tls_error
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.core.paths import resolve_raw_path
from app.models import RawDocument

SITE = "https://site.example.test/"
ROBOTS = "https://site.example.test/robots.txt"
SSL_ERR = "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1010)"
HTML = "<html><head><title>테스트 단지</title></head><body><div class='popup'><img src='/pop.jpg'></div>본문</body></html>"


def _popup(
    png: bytes, *, image: str = "https://site.example.test/pop1.jpg", sha: str | None = None
) -> PopupShot:
    return PopupShot(
        selector="#popup-wrap", sha256=sha or hashlib.sha256(png).hexdigest(), width=800, height=600,
        images=(image,), png=png, dhash="0f0f0f0f0f0f0f0f",
    )  # fmt: skip


class Renderer:
    """가짜 렌더러(+ 브라우저 fetch). 응답을 바꿔 가며 쓴다."""

    def __init__(
        self, *, dom_text: str = "본문", popups: tuple[PopupShot, ...] = (), shot: bytes = b"\x89PNG-1"
    ) -> None:
        self.dom_text, self.popups, self.shot = dom_text, popups, shot
        self.status: int | None = 200
        self.error: str | None = None
        self.robots = BrowserFetch(url=ROBOTS, status=200, text="User-agent: *\nAllow: /\n", final_url=ROBOTS)
        self.calls: list[str] = []

    def render(self, url: str) -> RenderResult:
        self.calls.append(f"render {url}")
        return RenderResult(
            url=url, final_url=url, status=self.status, screenshot_png=self.shot, dom_text=self.dom_text,
            popups=self.popups, error=self.error, html=HTML,
        )  # fmt: skip

    def fetch(self, url: str) -> BrowserFetch:
        self.calls.append(f"fetch {url}")
        return self.robots


class FakeOcr:
    def __init__(self, text: str = "잔여세대 선착순 동호지정") -> None:
        self.text = text
        self.calls: list[bytes] = []

    def __call__(self, png: bytes) -> str:
        self.calls.append(png)
        return self.text


def _rows(engine: Engine) -> list[RawDocument]:
    with Session(engine) as s:
        return list(s.scalars(select(RawDocument).order_by(RawDocument.id)))


def _fetch(collector: OfficialSiteCollector, region_ctx: tuple[Region, Snapshot]) -> None:
    region, snapshot = region_ctx
    collector.fetch(region, snapshot, None)


def _ok_site(router: respx.MockRouter) -> None:
    router.get(ROBOTS).respond(404)
    router.get(SITE).respond(200, content=HTML.encode(), headers={"content-type": "text/html; charset=utf-8"})


def _png_row(engine: Engine) -> RawDocument:
    rows = [r for r in _rows(engine) if (r.content_type or "").startswith("image/")]
    return rows[-1]


# ====================================================================== D26-1 팝업 그림 OCR


def test_popup_ocr_saved_on_screenshot_row_with_label_and_provenance(
    db_engine: Engine, raw_dir: Path, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    png = b"popup-image-A"
    ocr = FakeOcr()
    with respx.mock(assert_all_called=False) as router:
        _ok_site(router)
        _fetch(
            OfficialSiteCollector(
                http=http, renderer=Renderer(popups=(_popup(png),)), targets=[SiteTarget(SITE, 4)], ocr=ocr
            ),
            region_ctx,
        )
    row = _png_row(db_engine)
    meta = row.meta
    assert isinstance(meta, dict)
    assert (meta["kind"], meta["label"], meta["status"]) == (OCR_META_KIND, "추정(OCR)", "ok")
    (item,) = meta["items"]
    assert item["popup_sha256"] == hashlib.sha256(png).hexdigest()
    assert item["checked_at"] and item["chars"] == len(ocr.text)
    assert resolve_raw_path(item["image_path"], raw_dir=raw_dir).read_bytes() == png, (
        "OCR 한 그림 원본을 남긴다(출처)"
    )
    assert resolve_raw_path(item["text_path"], raw_dir=raw_dir).read_text(encoding="utf-8") == ocr.text
    from app.normalize.store import raw_dto

    assert popup_ocr_texts(raw_dto(row), raw_dir=raw_dir) == [ocr.text]
    assert ocr.calls == [png]


def test_same_popup_image_is_not_read_again(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    """같은 화면(스크린샷 행 재사용)이면 OCR 하지 않고, 화면은 바뀌었지만(새 스크린샷 행) 팝업 그림이 같으면 이전 OCR 을 쓴다."""
    png = b"popup-image-A"
    ocr = FakeOcr()
    renderer = Renderer(popups=(_popup(png),))
    with respx.mock(assert_all_called=False) as router:
        _ok_site(router)
        for _ in range(2):
            _fetch(
                OfficialSiteCollector(http=http, renderer=renderer, targets=[SiteTarget(SITE, 4)], ocr=ocr),
                region_ctx,
            )
        assert len(ocr.calls) == 1
        first = _png_row(db_engine)
        renderer.dom_text, renderer.shot = "본문 바뀜", b"\x89PNG-2"  # 새 스크린샷 행
        _fetch(
            OfficialSiteCollector(http=http, renderer=renderer, targets=[SiteTarget(SITE, 4)], ocr=ocr),
            region_ctx,
        )
    second = _png_row(db_engine)
    assert second.id != first.id
    assert len(ocr.calls) == 1, "그림 sha256 이 같으면 이전 OCR 결과"
    assert isinstance(second.meta, dict) and isinstance(first.meta, dict)
    assert second.meta["items"][0]["text_path"] == first.meta["items"][0]["text_path"]


def test_changed_popup_image_is_read_again(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    ocr = FakeOcr()
    renderer = Renderer(popups=(_popup(b"popup-A"),))
    with respx.mock(assert_all_called=False) as router:
        _ok_site(router)
        _fetch(
            OfficialSiteCollector(http=http, renderer=renderer, targets=[SiteTarget(SITE, 4)], ocr=ocr),
            region_ctx,
        )
        renderer.popups = (_popup(b"popup-B", image="https://site.example.test/pop2.jpg"),)
        renderer.shot = b"\x89PNG-2"
        _fetch(
            OfficialSiteCollector(http=http, renderer=renderer, targets=[SiteTarget(SITE, 4)], ocr=ocr),
            region_ctx,
        )
    assert ocr.calls == [b"popup-A", b"popup-B"]


def test_without_engine_reason_is_recorded(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """rapidocr 가 없으면(선택 의존성) 실패 없이 사유만 남긴다."""
    from app.collectors.notice_pdf import ocr as ocr_mod

    monkeypatch.setattr(ocr_mod, "load_image_ocr", lambda: None)
    with respx.mock(assert_all_called=False) as router:
        _ok_site(router)
        _fetch(
            OfficialSiteCollector(
                http=http, renderer=Renderer(popups=(_popup(b"p"),)), targets=[SiteTarget(SITE, 4)]
            ),
            region_ctx,
        )
    meta = _png_row(db_engine).meta
    assert isinstance(meta, dict)
    assert meta["status"] == "unavailable" and "rapidocr" in meta["reason"] and meta["items"] == []


def test_ocr_time_budget_skips_remaining_popups(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    """D5: 페이지당 30초. 예산을 넘기면 남은 팝업은 읽지 않고 'skipped'(다음 수집에 이어 읽는다)."""
    now = [0.0]

    class SlowOcr(FakeOcr):
        def __call__(self, png: bytes) -> str:
            now[0] += 20.0
            return super().__call__(png)

    ocr = SlowOcr()
    pops = tuple(_popup(f"p{i}".encode(), image=f"https://site.example.test/{i}.jpg") for i in range(3))
    with respx.mock(assert_all_called=False) as router:
        _ok_site(router)
        _fetch(
            OfficialSiteCollector(
                http=http,
                renderer=Renderer(popups=pops),
                targets=[SiteTarget(SITE, 4)],
                ocr=ocr,
                clock=lambda: now[0],
            ),
            region_ctx,
        )
    meta = _png_row(db_engine).meta
    assert isinstance(meta, dict)
    assert [it["status"] for it in meta["items"]] == ["ok", "ok", "skipped"]
    assert meta["status"] == "partial" and len(ocr.calls) == 2


def test_engine_error_is_data(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    def broken(png: bytes) -> str:
        raise OSError("cannot identify image file")

    with respx.mock(assert_all_called=False) as router:
        _ok_site(router)
        _fetch(
            OfficialSiteCollector(
                http=http,
                renderer=Renderer(popups=(_popup(b"x"),)),
                targets=[SiteTarget(SITE, 4)],
                ocr=broken,
            ),
            region_ctx,
        )
    meta = _png_row(db_engine).meta
    assert isinstance(meta, dict)
    assert meta["status"] == "error" and "cannot identify" in meta["items"][0]["error"]


def test_load_image_ocr_is_none_without_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """엔진(rapidocr·onnxruntime)이 없으면 그림 OCR 함수도 없다(공고문 OCR ``load_ocr`` 와 같은 판단)."""
    from app.collectors.notice_pdf import ocr as ocr_mod

    monkeypatch.setattr(ocr_mod, "load_ocr", lambda: None)
    assert ocr_mod.load_image_ocr() is None
    monkeypatch.setattr(ocr_mod, "load_ocr", lambda: object())
    assert ocr_mod.load_image_ocr() is ocr_mod.ocr_png


# ====================================================================== D26-4 TLS → 브라우저


def _tls(router: respx.MockRouter, *, robots_ok: bool = False) -> None:
    if robots_ok:
        router.get(ROBOTS).respond(404)
    else:
        router.get(ROBOTS).mock(side_effect=httpx.ConnectError(SSL_ERR))
    router.get(SITE).mock(side_effect=httpx.ConnectError(SSL_ERR))


def test_tls_failure_retries_robots_and_page_with_browser(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    renderer = Renderer(popups=(_popup(b"pop"),))
    with respx.mock(assert_all_called=False) as router:
        _tls(router)
        c = OfficialSiteCollector(http=http, renderer=renderer, targets=[SiteTarget(SITE, 4)], ocr=FakeOcr())
        _fetch(c, region_ctx)
    assert renderer.calls == [f"fetch {ROBOTS}", f"render {SITE}"]
    html_row, png_row = _rows(db_engine)
    assert (html_row.http_status, html_row.error_text) == (200, None)
    assert html_row.content_type == "text/html; charset=utf-8" and png_row.content_type == "image/png"
    meta = html_row.meta
    assert isinstance(meta, dict)
    assert meta["fetch"]["path"] == "browser" and meta["fetch"]["reason"] == "TLS"
    assert meta["fetch"]["failed"] == "robots.txt" and meta["fetch"]["robots"]["status"] == 200
    assert meta["fetch"]["result"] == "ok"
    assert meta["render"]["screenshot_sha256"] == png_row.sha256
    assert c.outcomes[0].fetch_path == "browser" and c.outcomes[0].failure is None


def test_tls_browser_robots_disallow_is_obeyed(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    """브라우저로 받은 robots.txt 가 막으면 본문을 받지 않는다(규칙 18 — RFC 9309)."""
    renderer = Renderer()
    renderer.robots = BrowserFetch(url=ROBOTS, status=200, text="User-agent: *\nDisallow: /\n")
    with respx.mock(assert_all_called=False) as router:
        _tls(router)
        _fetch(OfficialSiteCollector(http=http, renderer=renderer, targets=[SiteTarget(SITE, 4)]), region_ctx)
    assert renderer.calls == [f"fetch {ROBOTS}"]
    (row,) = _rows(db_engine)
    assert (row.http_status, row.error_text, row.path) == (None, "robots", None)
    assert isinstance(row.meta, dict) and row.meta["fetch"]["robots"]["status"] == 200


@pytest.mark.parametrize(
    ("robots", "rendered", "error_text", "http_status"),
    [
        (
            BrowserFetch(
                url=ROBOTS,
                error="browser: page.goto: net::ERR_CERT_DATE_INVALID at https://site.example.test/robots.txt",
            ),
            False,
            "TLS",
            None,
        ),
        (BrowserFetch(url=ROBOTS, status=503, text="busy"), False, "robots.txt 503", 503),
        (BrowserFetch(url=ROBOTS, status=404, text="nope"), True, None, 200),
    ],
    ids=["browser-tls-too", "robots-5xx-unreachable", "robots-404-allow-all"],
)
def test_tls_browser_robots_outcomes(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    http: HttpClient,
    robots: BrowserFetch,
    rendered: bool,
    error_text: str | None,
    http_status: int | None,
) -> None:
    """브라우저도 TLS 로 실패하면 'TLS' 그대로(확인 불가(TLS)), 5xx 는 전부 불허, 4xx 는 제한 없음(RFC 9309)."""
    renderer = Renderer()
    renderer.robots = robots
    with respx.mock(assert_all_called=False) as router:
        _tls(router)
        _fetch(
            OfficialSiteCollector(http=http, renderer=renderer, targets=[SiteTarget(SITE, 4)], ocr=None),
            region_ctx,
        )
    assert (f"render {SITE}" in renderer.calls) is rendered
    first = _rows(db_engine)[0]
    assert (first.error_text, first.http_status) == (error_text, http_status)
    if not rendered:
        assert isinstance(first.meta, dict) and first.meta["fetch"]["result"] == (
            error_text if error_text != "robots.txt 503" else "503"
        )


def test_tls_browser_page_denied_is_not_saved(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    """브라우저로 받은 본문이 403 이면 화면을 저장하지 않는다(D25-4 — 접근 거부를 우회하지 않음)."""
    renderer = Renderer()
    renderer.status = 403
    with respx.mock(assert_all_called=False) as router:
        _tls(router)
        _fetch(OfficialSiteCollector(http=http, renderer=renderer, targets=[SiteTarget(SITE, 4)]), region_ctx)
    (row,) = _rows(db_engine)
    assert (row.http_status, row.path) == (403, None)


def test_tls_page_with_robots_ok_renders_directly(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    """robots.txt 는 httpx 로 받았고(허용) 본문만 TLS 실패 → 브라우저 robots 를 다시 받지 않고 본문만."""
    renderer = Renderer()
    with respx.mock(assert_all_called=False) as router:
        _tls(router, robots_ok=True)
        _fetch(
            OfficialSiteCollector(http=http, renderer=renderer, targets=[SiteTarget(SITE, 4)], ocr=None),
            region_ctx,
        )
    assert renderer.calls == [f"render {SITE}"]
    meta = _rows(db_engine)[0].meta
    assert isinstance(meta, dict) and meta["fetch"]["failed"] == "page"


def test_tls_render_never_keeps_failure(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    renderer = Renderer()
    with respx.mock(assert_all_called=False) as router:
        _tls(router)
        _fetch(
            OfficialSiteCollector(
                http=http, renderer=renderer, render="never", targets=[SiteTarget(SITE, 4)]
            ),
            region_ctx,
        )
    assert renderer.calls == []
    (row,) = _rows(db_engine)
    assert row.error_text == "TLS"


def test_tls_browser_robots_fetched_once_per_origin(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    """같은 호스트를 쓰는 단지 여럿(hillstate.co.kr 4단지)이면 브라우저 robots.txt 는 한 번."""
    renderer = Renderer()
    with respx.mock(assert_all_called=False) as router:
        _tls(router)
        targets = [SiteTarget(SITE, 4), SiteTarget(SITE, 4)]
        _fetch(OfficialSiteCollector(http=http, renderer=renderer, targets=targets, ocr=None), region_ctx)
    assert renderer.calls.count(f"fetch {ROBOTS}") == 1


def test_browser_requests_use_core_http_rate_limit(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot]
) -> None:
    """브라우저 요청도 core.http 의 호스트별 간격(1 req/s)을 같이 쓴다(규칙 18)."""
    sleeps: list[float] = []
    client = HttpClient(sleep=sleeps.append, clock=lambda: 0.0, max_retries=0, jitter=0, rate_per_host=1.0)
    renderer = Renderer()
    try:
        with respx.mock(assert_all_called=False) as router:
            _tls(router)
            _fetch(
                OfficialSiteCollector(
                    http=client, renderer=renderer, targets=[SiteTarget(SITE, 4)], ocr=None
                ),
                region_ctx,
            )
    finally:
        client.close()
    assert renderer.calls == [f"fetch {ROBOTS}", f"render {SITE}"]
    assert sleeps[-2:] == [1.0, 2.0], sleeps  # httpx robots.txt(0초) 뒤 브라우저 robots(1초)·본문(2초)


@pytest.mark.parametrize(
    ("fetched", "allowed", "error"),
    [
        (BrowserFetch(url=ROBOTS, status=200, text="User-agent: *\nDisallow: /private\n"), True, None),
        (BrowserFetch(url=ROBOTS, status=200, text="User-agent: *\nDisallow: /\n"), False, "robots"),
        (BrowserFetch(url=ROBOTS, status=403), True, None),
        (BrowserFetch(url=ROBOTS, status=500), False, "robots.txt 500"),
        (BrowserFetch(url=ROBOTS, error="browser: net::ERR_CERT_AUTHORITY_INVALID"), False, "TLS"),
        (BrowserFetch(url=ROBOTS, error="browser: net::ERR_CONNECTION_RESET"), False, "robots"),
    ],
)
def test_robots_verdict_follows_rfc9309(fetched: BrowserFetch, allowed: bool, error: str | None) -> None:
    failure = robots_verdict(fetched, "subscription-analyzer", SITE)
    assert (failure is None) is allowed
    assert (failure.reason if failure else None) == (error if error != "robots.txt 500" else "500")


def test_tls_error_markers() -> None:
    assert is_tls_error("render: page.goto: net::ERR_CERT_COMMON_NAME_INVALID at https://x/")
    assert is_tls_error("browser: net::ERR_SSL_PROTOCOL_ERROR")
    assert is_tls_error(SSL_ERR)
    assert not is_tls_error("render: page.goto: net::ERR_NAME_NOT_RESOLVED")


# ---------------------------------------------------------------------- 브라우저 인증서 검증은 켠 채


class _Resp:
    status = 200

    def text(self) -> str:
        return "User-agent: *\nAllow: /\n"


class _Page:
    url = ROBOTS

    def goto(self, url: str, **kw: Any) -> _Resp:
        self.url = url
        return _Resp()


class _Ctx:
    def route(self, *a: Any) -> None: ...
    def route_web_socket(self, *a: Any) -> None: ...
    def on(self, *a: Any) -> None: ...
    def new_page(self) -> _Page:
        return _Page()


class _Browser:
    def __init__(self) -> None:
        self.context_kwargs: dict[str, Any] = {}

    def new_context(self, **kw: Any) -> _Ctx:
        self.context_kwargs = kw
        return _Ctx()

    def close(self) -> None: ...


class _Chromium:
    def __init__(self, browser: _Browser) -> None:
        self.browser = browser

    def launch(self, **kw: Any) -> _Browser:
        return self.browser


class _Playwright:
    def __init__(self) -> None:
        self.browser = _Browser()
        self.chromium = _Chromium(self.browser)


def test_browser_fetch_keeps_certificate_validation_on() -> None:
    renderer = PlaywrightRenderer(allow_private=False, resolver=lambda h: ["93.184.216.34"])
    guard = renderer.guard()
    assert guard.prepare(ROBOTS) is None
    fake = _Playwright()
    got = renderer._fetch_with(fake, ROBOTS, guard, "ua")
    assert got.ok and got.status == 200 and "Allow" in got.text
    assert fake.browser.context_kwargs["ignore_https_errors"] is False  # 검증을 끄지 않는다(D26-4)


# ---------------------------------------------------------------------- 실제 chromium: 자체 서명 인증서는 실패(검증 켬)


@pytest.fixture
def self_signed_site(tmp_path: Path) -> Iterator[str]:
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=2))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
    )  # fmt: skip
    certfile, keyfile = tmp_path / "c.pem", tmp_path / "k.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = b"User-agent: *\nAllow: /\n"
            self.send_response(200)
            self.send_header("content-type", "text/plain")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a: Any) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile, keyfile)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield f"https://127.0.0.1:{server.server_address[1]}/robots.txt"
    finally:
        server.shutdown()
        server.server_close()


def test_real_chromium_rejects_self_signed_certificate(self_signed_site: str) -> None:
    """실제 chromium 도 검증을 켠 채라 자체 서명 인증서는 실패한다 → 'TLS'(우회하지 않는다)."""
    probe = PlaywrightRenderer(allow_private=True, settle_ms=0).render("about:blank")
    if probe.error and "Executable doesn't exist" in probe.error:
        pytest.skip("chromium 미설치")
    got = PlaywrightRenderer(allow_private=True, settle_ms=0, timeout_ms=15_000).fetch(self_signed_site)
    assert not got.ok and is_tls_error(got.error), got
