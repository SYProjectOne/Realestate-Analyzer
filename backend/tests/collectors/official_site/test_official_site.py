"""official_site: 403(T3)·DNS·TLS 실패 행, 녹화 HTML + 렌더 결과 저장, 멱등, Playwright 팝업 렌더(로컬)."""

from __future__ import annotations

import functools
import json
import threading
from collections.abc import Callable, Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.official_site import (
    META_CONTENT_TYPE,
    OfficialSiteCollector,
    PlaywrightRenderer,
    PopupShot,
    RenderResult,
    SiteTarget,
    popup_hash,
    read_site_meta,
)
from app.collectors.reference.rawstore import RawStore
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.core.paths import resolve_raw_path
from app.models import RawDocument

SITE = "https://site.example.test/"
ROBOTS = "https://site.example.test/robots.txt"
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes"


class FakeRenderer:
    def __init__(self, result: RenderResult | None = None) -> None:
        self.calls: list[str] = []
        self.result = result

    def render(self, url: str) -> RenderResult:
        self.calls.append(url)
        if self.result is not None:
            return self.result
        return RenderResult(
            url=url,
            final_url=url,
            status=200,
            screenshot_png=PNG,
            dom_text="잔여 세대 선착순 동호지정 계약 중",
            popups=(PopupShot(selector="#layer_popup", sha256="a" * 64, width=300, height=200),),
        )


def _docs(engine: Engine) -> list[RawDocument]:
    with Session(engine) as s:
        return list(s.scalars(select(RawDocument).order_by(RawDocument.id)))


# --- 실패도 데이터 (T3)


def test_403_leaves_http_status_row_once_per_day(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    region, snapshot = region_ctx
    renderer = FakeRenderer()
    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(404)
        router.get(SITE).respond(403, text="Forbidden")
        collector = OfficialSiteCollector(http=http, renderer=renderer)
        docs = collector.fetch(region, snapshot, None)  # 대상 = region 의 complex.official_site_url
        OfficialSiteCollector(http=http, renderer=renderer).fetch(region, snapshot, None)
    assert renderer.calls == []  # 접근 거부는 렌더로 우회하지 않는다
    assert count(RawDocument) == 1
    (row,) = _docs(db_engine)
    assert (row.http_status, row.path, row.error_text, row.complex_id, row.region_id) == (
        403,
        None,
        None,
        4,
        1,
    )
    assert row.source_kind == "official_site" and row.url == SITE
    assert docs[0].sha256 == row.sha256
    assert collector.outcomes[0].failure is not None and collector.outcomes[0].failure.reason == "403"


@pytest.mark.parametrize(
    ("exc", "reason"),
    [
        (httpx.ConnectError("[Errno 11001] getaddrinfo failed"), "DNS"),
        (
            httpx.ConnectError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                "certificate has expired (_ssl.c:1010)"
            ),
            "TLS",
        ),
        (httpx.ReadTimeout("timed out"), "timeout"),
    ],
)
def test_network_failures_leave_error_text_rows(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient, exc: Exception, reason: str
) -> None:
    """DNS 실패·인증서 만료(실제 사례: 스위첸 홈페이지 2026-10-09)·타임아웃.

    → http_status=None + error_text.
    """
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).mock(side_effect=exc)
        router.get(SITE).mock(side_effect=exc)
        OfficialSiteCollector(http=http, renderer=FakeRenderer(), targets=[SiteTarget(SITE, 4)]).fetch(
            region, snapshot, None
        )
    (row,) = _docs(db_engine)
    assert (row.http_status, row.error_text, row.path) == (None, reason, None)


def test_robots_disallow_is_recorded_as_robots(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(200, text="User-agent: *\nDisallow: /\n")
        page = router.get(SITE).respond(200, text="<html></html>")
        OfficialSiteCollector(http=http, renderer=FakeRenderer()).fetch(region, snapshot, None)
        assert page.call_count == 0
    (row,) = _docs(db_engine)
    assert (row.http_status, row.error_text) == (None, "robots")


# --- 성공: 녹화 HTML(실제 단지 홈페이지) + 렌더 + 메타(raw_document.meta, 계약 2026-10-09.2)


def test_recorded_page_saves_html_screenshot_and_meta_idempotently(
    db_engine: Engine,
    raw_dir: Path,
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    region, snapshot = region_ctx
    html = (fixtures_dir / "hndapt_index.html").read_bytes()
    renderer = FakeRenderer()
    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(200, content=(fixtures_dir / "hndapt_robots.txt").read_bytes())
        router.get(SITE).respond(200, content=html, headers={"content-type": "text/html; charset=utf-8"})
        collector = OfficialSiteCollector(http=http, renderer=renderer)
        docs = collector.fetch(region, snapshot, None)
        out = collector.outcomes[0]
        assert out.render_reason == "팝업 표식" and out.rendered
        assert renderer.calls == [SITE]
        n = count(RawDocument)
        again = OfficialSiteCollector(http=http, renderer=FakeRenderer()).fetch(region, snapshot, None)
        assert count(RawDocument) == n == 2  # T17: html·png(메타는 html 행의 meta 컬럼), 두 번째 실행 증가 0

    html_doc, png_doc = docs
    assert [d.id for d in again] == [d.id for d in docs]
    assert (html_doc.content_type or "").startswith("text/html") and html_doc.text_path
    dom_text = resolve_raw_path(html_doc.text_path).read_text(encoding="utf-8")
    assert "송도 한내들 센트럴리버" in dom_text and "<script" not in dom_text
    assert png_doc.content_type == "image/png" and png_doc.image_hash == out.image_hash is not None
    assert resolve_raw_path(png_doc.path or "").read_bytes() == PNG
    # 메타는 별도 JSON 행이 아니라 html 행의 meta 컬럼
    assert not [d for d in _docs(db_engine) if d.content_type == META_CONTENT_TYPE]
    meta = html_doc.meta
    assert meta is not None and meta == out.meta
    (row,) = [d for d in _docs(db_engine) if d.id == html_doc.id]
    assert row.meta == meta
    assert meta["image_hash"] == out.image_hash and meta["render"]["rendered"] is True
    assert meta["render"]["screenshot_sha256"] == png_doc.sha256
    texts = [c["text"] for c in meta["intake_candidates"]]
    assert "계약안내문" in texts  # 녹화 HTML 의 메뉴(후보일 뿐, 판단은 WP2·판정기)
    assert "잔여 세대 선착순 동호지정 계약 중" in texts  # 렌더 후 텍스트
    assert {d.complex_id for d in docs} == {4}
    assert png_doc.meta is None
    assert read_site_meta(html_doc, raw_dir=raw_dir) == meta


def test_meta_follows_latest_render_on_same_html(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    """같은 HTML(같은 행)이라도 렌더 결과(팝업)가 바뀌면 meta 는 최신 관찰로 갱신된다. 새 스크린샷은 새 행."""
    region, snapshot = region_ctx
    body = (
        "<html><body><div class='popup'>잔여 세대 안내</div>"
        + "<p>단지 안내 문단</p>" * 40
        + "</body></html>"
    )
    other = RenderResult(
        url=SITE,
        final_url=SITE,
        status=200,
        screenshot_png=PNG + b"2",
        dom_text="분양 완료",
        popups=(PopupShot(selector="#pop2", sha256="b" * 64, width=100, height=100),),
    )
    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(404)
        router.get(SITE).respond(200, text=body, headers={"content-type": "text/html"})
        first = OfficialSiteCollector(http=http, renderer=FakeRenderer(), targets=[SiteTarget(SITE, 4)])
        d1 = first.fetch(region, snapshot, None)
        second = OfficialSiteCollector(http=http, renderer=FakeRenderer(other), targets=[SiteTarget(SITE, 4)])
        d2 = second.fetch(region, snapshot, None)
    assert d1[0].id == d2[0].id and d1[1].id != d2[1].id
    (html_row,) = [d for d in _docs(db_engine) if d.id == d1[0].id]
    assert html_row.meta is not None and html_row.meta["image_hash"] == second.outcomes[0].image_hash
    assert html_row.meta["image_hash"] != first.outcomes[0].image_hash
    assert len(_docs(db_engine)) == 3


def test_legacy_meta_row_is_still_readable(
    db_session: Session, raw_dir: Path, region_ctx: tuple[Region, Snapshot]
) -> None:
    """2026-10-09.1 까지의 별도 메타 JSON 행(content_type META_CONTENT_TYPE)도 같은 함수로 읽는다."""
    legacy = {"kind": "official_site.meta", "url": SITE, "image_hash": None, "intake_candidates": []}
    store = RawStore(db_session, raw_dir=raw_dir)
    doc = store.save_content(
        source_kind="official_site",
        url=SITE,
        content=json.dumps(legacy, ensure_ascii=False).encode("utf-8"),
        ext="json",
        content_type=META_CONTENT_TYPE,
        complex_id=4,
    )
    assert doc.meta is None
    assert read_site_meta(doc, raw_dir=raw_dir) == legacy
    html = store.save_content(
        source_kind="official_site", url=SITE, content=b"<html></html>", ext="html", content_type="text/html"
    )
    assert read_site_meta(html, raw_dir=raw_dir) is None
    assert read_site_meta(html.model_copy(update={"meta": {"k": 1}}), raw_dir=raw_dir) == {"k": 1}


def test_static_page_without_markers_skips_render(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    region, snapshot = region_ctx
    body = "<html><body>" + "<p>단지 안내 문단입니다. 견본주택 방문 예약 안내.</p>" * 20 + "</body></html>"
    renderer = FakeRenderer()
    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(404)
        router.get(SITE).respond(200, text=body, headers={"content-type": "text/html"})
        c = OfficialSiteCollector(http=http, renderer=renderer, targets=[SiteTarget(SITE, 4)])
        docs = c.fetch(region, snapshot, None)
    assert renderer.calls == [] and c.outcomes[0].render_reason == "정적"
    assert [d.content_type for d in docs] == ["text/html"]
    assert docs[0].meta is not None and docs[0].meta["render"]["rendered"] is False


def test_render_failure_is_a_row(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    region, snapshot = region_ctx
    renderer = FakeRenderer(RenderResult(url=SITE, error="render: Timeout 30000ms exceeded."))
    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(404)
        router.get(SITE).respond(200, text="<div id='app'></div>", headers={"content-type": "text/html"})
        c = OfficialSiteCollector(
            http=http, renderer=renderer, render="always", targets=[SiteTarget(SITE, 4)]
        )
        docs = c.fetch(region, snapshot, None)
    fail = docs[1]
    assert (fail.http_status, fail.path, fail.error_text) == (None, None, "render: Timeout 30000ms exceeded.")


# --- Playwright 실제 렌더 (로컬 HTML 페이지)

POPUP_PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>테스트 단지</title>
<style>
  body { font-family: sans-serif; }
  #layer_popup { position: fixed; top: 40px; left: 40px; width: 320px; height: 220px;
                 background: #c33; color: #fff; }
</style></head>
<body>
  <h1>테스트 단지</h1>
  <p>선착순 동호지정 계약 중</p>
  <div id="layer_popup" class="popup"><p>잔여 세대 선착순 분양 안내</p></div>
</body></html>"""


@pytest.fixture
def local_site(tmp_path: Path) -> Iterator[str]:
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text(POPUP_PAGE, encoding="utf-8")

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
    finally:
        server.shutdown()
        server.server_close()


def _renderer() -> PlaywrightRenderer:
    r = PlaywrightRenderer(settle_ms=100, timeout_ms=20_000, allow_private=True)  # 로컬 서버(127.0.0.1)
    probe = r.render("about:blank")
    if probe.error and ("Executable doesn't exist" in probe.error or "playwright install" in probe.error):
        pytest.skip(f"Playwright chromium 미설치: {probe.error}")
    return r


def test_playwright_renders_popup_png_and_hash(local_site: str) -> None:
    result = _renderer().render(local_site)
    assert result.ok, result.error
    assert result.screenshot_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert [p.selector for p in result.popups] == ["#layer_popup"]
    assert (result.popups[0].width, result.popups[0].height) == (320, 220)
    assert popup_hash(result.popups) is not None and len(popup_hash(result.popups) or "") == 64
    assert "잔여 세대 선착순 분양 안내" in result.dom_text


def test_collector_end_to_end_with_local_server(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], local_site: str
) -> None:
    region, snapshot = region_ctx
    renderer = _renderer()
    with HttpClient(rate_per_host=1000, max_retries=0, jitter=0, allow_private=True) as client:
        c = OfficialSiteCollector(http=client, renderer=renderer, targets=[SiteTarget(local_site, 4)])
        docs = c.fetch(region, snapshot, None)
    assert [d.content_type for d in docs][1:] == ["image/png"]
    assert docs[0].meta is not None and docs[0].meta["render"]["rendered"] is True
    png = docs[1]
    assert png.image_hash is not None and len(png.image_hash) == 64
    assert resolve_raw_path(png.path or "").read_bytes().startswith(b"\x89PNG")
    assert c.outcomes[0].rendered and c.outcomes[0].image_hash == png.image_hash


@pytest.mark.live
def test_live_official_site(db_engine: Engine, region_ctx: tuple[Region, Snapshot]) -> None:
    """실제 단지 홈페이지(녹화 원본과 같은 곳) + 실제 Playwright 렌더."""
    region, snapshot = region_ctx
    _renderer()  # chromium 없으면 건너뜀
    target = SiteTarget("https://sd.hndapt.co.kr/", 4)
    c = OfficialSiteCollector(targets=[target], renderer=PlaywrightRenderer())
    docs = c.fetch(region, snapshot, None)
    assert docs[0].http_status == 200
    assert c.outcomes[0].rendered, (c.outcomes[0].meta or {}).get("render")
