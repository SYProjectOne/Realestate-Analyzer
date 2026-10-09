"""R3 M13: 팝업 변경 감지 해시 안정화 — 시각·애니메이션은 무시, 글자·그림 변경은 잡는다.

- 단위: 시각 표기 정규화, 서명 기반 popup_hash, dHash 거리.
- 수집기: 같은 화면(서명 같고 dHash 임계값 안)이면 직전 스크린샷 행 재사용(raw_document 증가 0, image_hash 동일),
  글자가 바뀌거나 그림이 크게 바뀌면 새 해시·새 행.
- 실제 Playwright: 시계(초 단위 갱신)·CSS 애니메이션이 있는 로컬 페이지 3회 렌더 → 같은 해시.
"""

from __future__ import annotations

import functools
import io
import threading
from collections.abc import Callable, Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import respx
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.official_site import (
    DHASH_THRESHOLD,
    OfficialSiteCollector,
    PlaywrightRenderer,
    PopupShot,
    RenderResult,
    SiteTarget,
    popup_hash,
    render_signature,
    visual_change,
)
from app.collectors.official_site.render import dhash, hamming, normalize_popup_text
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.models import RawDocument

SITE = "https://site.example.test/"
ROBOTS = "https://site.example.test/robots.txt"


def _png(*, clock: str = "12", banner: bool = False, inverse: bool = False) -> bytes:
    """팝업 그림: 빨간 바탕 + 줄무늬(내용) + 작은 시계 칸(clock 이 바뀌면 몇 픽셀만 달라진다)."""
    img = Image.new("RGB", (320, 220), (40, 40, 200) if inverse else (200, 40, 40))
    d = ImageDraw.Draw(img)
    for x in range(0, 320, 40):
        d.rectangle([x, 60, x + 18, 200], fill=(250, 250, 250) if not inverse else (10, 10, 10))
    d.text((280, 5), clock, fill=(255, 255, 0))
    if banner:
        d.rectangle([0, 0, 320, 50], fill=(0, 0, 0))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _shot(text: str, png: bytes) -> PopupShot:
    import hashlib

    return PopupShot(selector="#layer_popup", sha256=hashlib.sha256(png).hexdigest(), width=320, height=220,
                     text=normalize_popup_text(text), dhash=dhash(png))  # fmt: skip


# ====================================================================== 단위


def test_m13_time_is_masked_but_notice_content_kept() -> None:
    a = normalize_popup_text("현재 시각 14:03:22  잔여 3세대\n10월 15일 계약")
    b = normalize_popup_text("현재 시각 14:03:27 잔여 3세대 10월 15일 계약")
    assert a == b == "현재 시각 <시각> 잔여 3세대 10월 15일 계약"
    assert normalize_popup_text("오후 3시 5분 7초 기준") == normalize_popup_text("오후 3시 6분 1초 기준")
    assert normalize_popup_text("잔여 3세대") != normalize_popup_text("잔여 2세대")


def test_m13_popup_hash_ignores_pixels_when_text_or_images_identify_the_popup() -> None:
    p1 = _shot("분양 안내 12:00:01", _png(clock="01"))
    p2 = _shot("분양 안내 12:00:09", _png(clock="09"))
    assert p1.sha256 != p2.sha256  # 픽셀은 다르다
    assert popup_hash([p1]) == popup_hash([p2])
    assert popup_hash([_shot("분양 마감", _png())]) != popup_hash([p1])
    assert popup_hash([]) is None


def test_m13_dhash_distance_threshold() -> None:
    base, clock, other = dhash(_png(clock="01")), dhash(_png(clock="59")), dhash(_png(inverse=True))
    assert base and clock and other
    assert hamming(base, clock) <= DHASH_THRESHOLD < hamming(base, other)
    assert dhash(b"not a png") is None
    prev = [_shot("팝업", _png(clock="01")).as_meta()]
    assert not visual_change(prev, [_shot("팝업", _png(clock="59"))])
    assert visual_change(prev, [_shot("팝업", _png(inverse=True))])


# ====================================================================== 수집기(가짜 렌더러)


class SeqRenderer:
    def __init__(self, results: list[RenderResult]) -> None:
        self.results = list(results)

    def render(self, url: str) -> RenderResult:
        return self.results.pop(0)


def _result(text: str, png: bytes, *, page_png: bytes | None = None) -> RenderResult:
    return RenderResult(url=SITE, final_url=SITE, status=200, screenshot_png=page_png or png,
                        dom_text=f"단지 안내 {text}", popups=(_shot(text, png),))  # fmt: skip


def test_m13_collector_reuses_screenshot_row_for_same_screen_and_detects_real_changes(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    region, snapshot = region_ctx
    body = "<html><body><div class='popup'>잔여 세대 안내</div>" + "<p>단지 안내</p>" * 40 + "</body></html>"
    renders = [
        _result("잔여 세대 안내 14:00:01", _png(clock="01")),
        _result("잔여 세대 안내 14:00:31", _png(clock="31")),  # 시계만 바뀜
        _result("잔여 세대 안내 14:01:02", _png(clock="02")),  # 시계만 바뀜
        _result("잔여 세대 마감", _png(clock="02")),  # 글자 변경 → 새 해시
        _result("잔여 세대 마감", _png(clock="02", inverse=True)),  # 그림만 크게 변경 → 새 해시
    ]
    seq = SeqRenderer(renders)
    hashes: list[str | None] = []
    png_counts: list[int] = []
    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(404)
        router.get(SITE).respond(200, text=body, headers={"content-type": "text/html"})
        for _ in renders:
            c = OfficialSiteCollector(http=http, renderer=seq, render="always", targets=[SiteTarget(SITE, 4)])
            docs = c.fetch(region, snapshot, None)
            assert [d.content_type for d in docs][1:] == ["image/png"]
            hashes.append(c.outcomes[0].image_hash)
            with Session(db_engine) as s:
                png_counts.append(len(list(s.scalars(select(RawDocument).where(RawDocument.content_type == "image/png")))))
    assert hashes[0] == hashes[1] == hashes[2]  # 가짜 팝업 변경 없음
    assert png_counts[:3] == [1, 1, 1]  # 같은 화면 → 스크린샷 행 재사용(raw_document 증가 0)
    assert hashes[3] != hashes[2] and png_counts[3] == 2  # 글자 변경
    assert hashes[4] != hashes[3] and png_counts[4] == 3  # 그림 변경(서명 같음, dHash 임계값 초과)
    assert count(RawDocument) == 4  # html 1 + png 3


# ====================================================================== 실제 Playwright


CLOCK_PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>시계 단지</title>
<style>
  body { font-family: sans-serif; }
  #layer_popup { position: fixed; top: 40px; left: 40px; width: 340px; height: 240px;
                 background: #c33; color: #fff; }
  .spin { width: 40px; height: 40px; background: #ff0; animation: spin 0.4s linear infinite; }
  .blink { animation: blink 0.3s step-end infinite; }
  @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
  @keyframes blink { 50% { opacity: 0.2; } }
</style></head>
<body>
  <h1>시계 단지</h1>
  <div id="layer_popup" class="popup">
    <p>잔여 세대 선착순 분양 안내</p>
    <p class="blink">현재 시각 <span id="clock">00:00:00</span></p>
    <div class="spin"></div>
  </div>
  <script>
    function tick() {
      const d = new Date();
      const pad = (n) => String(n).padStart(2, "0");
      const ms = String(d.getMilliseconds()).padStart(3, "0");
      document.getElementById("clock").textContent =
        pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds()) + "." + ms;
    }
    tick(); setInterval(tick, 37);
  </script>
</body></html>"""


@pytest.fixture
def clock_site(tmp_path: Path) -> Iterator[str]:
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text(CLOCK_PAGE, encoding="utf-8")

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


def test_m13_real_playwright_three_renders_of_clock_and_animation_page_same_hash(clock_site: str) -> None:
    renderer = PlaywrightRenderer(settle_ms=150, timeout_ms=20_000)
    probe = renderer.render("about:blank")
    if probe.error and ("Executable doesn't exist" in probe.error or "playwright install" in probe.error):
        pytest.skip(f"Playwright chromium 미설치: {probe.error}")
    results = [renderer.render(clock_site) for _ in range(3)]
    assert all(r.ok for r in results), [r.error for r in results]
    assert all(len(r.popups) == 1 and "<시각>" in r.popups[0].text for r in results)
    hashes = {popup_hash(r.popups) for r in results}
    signatures = {render_signature(r.dom_text, r.popups) for r in results}
    assert len(hashes) == 1 and None not in hashes
    assert len(signatures) == 1
    # 그림도 임계값 안(애니메이션 정지 + 시계 숫자 몇 개)
    first = [p.as_meta() for p in results[0].popups]
    assert not any(visual_change(first, r.popups) for r in results[1:])
