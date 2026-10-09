"""Playwright chromium 렌더: 전체 화면 스크린샷 PNG + 렌더 후 DOM 텍스트 + 팝업 요소 이미지 해시.

- 렌더는 ``core.http`` 로 같은 URL 을 먼저 받아 성공(robots 허용·2xx)한 뒤에만 한다(수집기가 보장).
- 팝업 = 보이는 ``popup·pop_·layer_pop·modal·lightbox·role=dialog`` 요소 중 가장 바깥 것(최대 10개).
  요소 스크린샷 PNG 의 sha256·perceptual hash(dHash 64비트)·정규화 텍스트를 남긴다.
- **안정 해시(R3 M13)**: 시계·애니메이션이 있는 팝업은 렌더마다 픽셀이 달라진다. 그래서
  1) 렌더를 멈춘다: ``reduced_motion=reduce`` + 애니메이션·전환 정지 CSS + ``getAnimations()`` 일시정지 +
     동영상 정지 + 스크린샷 ``animations='disabled'``·``caret='hide'``;
  2) ``popup_hash`` 는 픽셀이 아니라 **팝업 서명**(시각 표기를 가린 정규화 텍스트 + 이미지 주소 + 크기; 글자도
     이미지도 없으면 dHash)의 sha256 이다(팝업이 없으면 None). WP7 은 이 값으로 팝업 변경을 감지한다.
  3) 서명이 같아도 그림이 크게 바뀌었는지는 dHash 해밍 거리로 본다(``visual_change``, 임계값
     ``DHASH_THRESHOLD``) — 수집기가 직전 렌더와 비교해 넘으면 해시를 바꾸고, 안 넘으면 직전 스크린샷 행을
     재사용한다(같은 화면이면 raw_document 가 늘지 않는다).
- 실패는 예외 대신 ``RenderResult.error`` 로 돌려준다(실패도 데이터).
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

__all__ = [
    "DHASH_THRESHOLD",
    "FREEZE_CSS",
    "PlaywrightRenderer",
    "PopupShot",
    "RenderResult",
    "Renderer",
    "dhash",
    "hamming",
    "normalize_popup_text",
    "popup_hash",
    "popup_signature",
    "render_signature",
    "visual_change",
]

DHASH_THRESHOLD = 10
"""dHash(64비트) 해밍 거리 임계값: 이보다 크면 그림이 바뀐 것으로 본다(시계 숫자 몇 개는 이 안쪽)."""

FREEZE_CSS = """
*, *::before, *::after {
  animation: none !important; animation-play-state: paused !important;
  transition: none !important; caret-color: transparent !important; scroll-behavior: auto !important;
}
"""
_FREEZE_JS = """
() => {
  try { document.getAnimations().forEach((a) => { try { a.pause(); a.currentTime = 0; } catch (e) {} }); }
  catch (e) {}
  document.querySelectorAll('video, audio').forEach((m) => { try { m.pause(); m.currentTime = 0; } catch (e) {} });
  return true;
}
"""
_TIME_RES = (
    re.compile(r"(?:(?:오전|오후|AM|PM|am|pm)\s*)?\d{1,2}\s*:\s*\d{2}(?:\s*:\s*\d{2})?(?:\.\d+)?"),
    re.compile(r"(?:(?:오전|오후)\s*)?\d{1,2}\s*시\s*\d{1,2}\s*분(?:\s*\d{1,2}\s*초)?"),
    re.compile(r"\d{1,2}\s*분\s*\d{1,2}\s*초"),
)
_WS = re.compile(r"\s+")


def normalize_popup_text(text: str) -> str:
    """팝업 글자 → 서명용: 시각 표기(12:03·12:03:45·오후 3시 5분 7초)를 ``<시각>`` 으로, 공백을 하나로.
    날짜·세대수·금액 같은 공고 내용은 그대로 둔다(그게 바뀌면 팝업 변경이다)."""
    out = text
    for pattern in _TIME_RES:
        out = pattern.sub("<시각>", out)
    return _WS.sub(" ", out).strip()


def dhash(png: bytes, size: int = 8) -> str | None:
    """PNG → difference hash(64비트, 16진 16자). 이미지를 못 읽으면 None."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(png)) as im:
            gray = im.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
            px = list(gray.tobytes())
    except Exception:  # 손상·가짜 PNG(테스트) — 해시 없음
        return None
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:0{size * size // 4}x}"


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()

_POPUP_JS = """
() => {
  const sel = [
    '[id*="popup" i]', '[class*="popup" i]', '[id*="pop_" i]', '[class*="pop_" i]',
    '[class*="layer_pop" i]', '[class*="layerpop" i]', '[class*="modal" i]', '[class*="lightbox" i]',
    '[role="dialog"]'
  ].join(',');
  const els = Array.from(document.querySelectorAll(sel));
  const visible = els.filter((e) => {
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return r.width >= 80 && r.height >= 80 && s.visibility !== 'hidden' && s.display !== 'none'
      && parseFloat(s.opacity || '1') > 0.05;
  });
  const outer = visible.filter((e) => !visible.some((o) => o !== e && o.contains(e)));
  return outer.slice(0, 10).map((e, i) => {
    e.setAttribute('data-wp1b-popup', String(i));
    const r = e.getBoundingClientRect();
    const imgs = Array.from(e.querySelectorAll('img')).map((im) => im.currentSrc || im.src).filter(Boolean);
    return {
      index: i, tag: e.tagName.toLowerCase(), id: e.id || null,
      cls: (typeof e.className === 'string' && e.className) ? e.className : null,
      width: Math.round(r.width), height: Math.round(r.height), images: imgs.slice(0, 10),
      text: (e.innerText || '').slice(0, 4000),
    };
  });
}
"""


@dataclass(frozen=True, slots=True)
class PopupShot:
    selector: str
    sha256: str
    width: int
    height: int
    images: tuple[str, ...] = ()
    text: str = ""  # normalize_popup_text 를 거친 팝업 글자
    dhash: str | None = None  # 요소 스크린샷의 perceptual hash

    def as_meta(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "images": list(self.images),
            "text_sha256": hashlib.sha256(self.text.encode("utf-8")).hexdigest() if self.text else None,
            "dhash": self.dhash,
            "signature": popup_signature(self),
        }


@dataclass(frozen=True, slots=True)
class RenderResult:
    url: str
    final_url: str | None = None
    status: int | None = None
    screenshot_png: bytes = b""
    dom_text: str = ""
    popups: tuple[PopupShot, ...] = field(default_factory=tuple)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.screenshot_png)


def popup_signature(p: PopupShot) -> str:
    """팝업 1개의 안정 서명(모듈 설명 2). 글자·이미지가 있으면 픽셀을 보지 않는다."""
    images = ",".join(sorted(p.images))
    if p.text or images:
        content = f"text:{p.text}|img:{images}"
    else:  # 글자도 이미지 주소도 없는 그림 팝업 — 그림 자체(dHash, 없으면 바이트 해시)
        content = f"pix:{p.dhash or p.sha256}"
    return hashlib.sha256(f"{content}|{p.width}x{p.height}".encode()).hexdigest()


def popup_hash(popups: Sequence[PopupShot]) -> str | None:
    """정렬한 팝업 서명들의 sha256(팝업이 없으면 None). 시계·애니메이션 픽셀 차이에 흔들리지 않는다."""
    if not popups:
        return None
    joined = "\n".join(sorted(popup_signature(p) for p in popups))
    return hashlib.sha256(joined.encode("ascii")).hexdigest()


def render_signature(dom_text: str, popups: Sequence[PopupShot]) -> str:
    """렌더 1회의 안정 서명 = 시각을 가린 DOM 텍스트 + popup_hash. 같으면 같은 화면으로 본다."""
    return hashlib.sha256(
        f"{normalize_popup_text(dom_text)}\n{popup_hash(popups) or ''}".encode()
    ).hexdigest()


def visual_change(
    previous: Iterable[Mapping[str, Any]], popups: Sequence[PopupShot], *, threshold: int = DHASH_THRESHOLD
) -> bool:
    """직전 렌더의 팝업 meta(``as_meta``) 대비 같은 서명 팝업의 dHash 거리가 임계값을 넘는가."""
    old = {str(m.get("signature")): m.get("dhash") for m in previous if m.get("signature")}
    for p in popups:
        before = old.get(popup_signature(p))
        if isinstance(before, str) and p.dhash is not None and hamming(before, p.dhash) > threshold:
            return True
    return False


class Renderer(Protocol):
    def render(self, url: str) -> RenderResult: ...


class PlaywrightRenderer:
    """동기 Playwright chromium(headless). 이벤트 루프가 도는 스레드에서는 부르지 않는다(worker 스레드용)."""

    def __init__(
        self,
        *,
        timeout_ms: int = 30_000,
        settle_ms: int = 1_500,
        viewport: tuple[int, int] = (1280, 900),
        user_agent: str | None = None,
        full_page: bool = True,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.settle_ms = settle_ms
        self.viewport = viewport
        self.user_agent = user_agent
        self.full_page = full_page

    def render(self, url: str) -> RenderResult:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        from app.core.settings import get_settings

        ua = self.user_agent or get_settings().http_user_agent
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        viewport={"width": self.viewport[0], "height": self.viewport[1]},
                        user_agent=ua,
                        locale="ko-KR",
                        reduced_motion="reduce",
                    )
                    page = context.new_page()
                    response = page.goto(url, wait_until="load", timeout=self.timeout_ms)
                    # 계속 통신하는 페이지는 networkidle 이 오지 않는다 — load 까지로 충분
                    with contextlib.suppress(PlaywrightError):
                        page.wait_for_load_state("networkidle", timeout=min(5_000, self.timeout_ms))
                    page.wait_for_timeout(self.settle_ms)
                    # 애니메이션·전환·동영상을 멈춘다(안정 해시, R3 M13)
                    with contextlib.suppress(PlaywrightError):
                        page.add_style_tag(content=FREEZE_CSS)
                        page.evaluate(_FREEZE_JS)
                    png = page.screenshot(full_page=self.full_page, animations="disabled", caret="hide")
                    text = page.inner_text("body") if page.locator("body").count() else ""
                    infos: list[dict[str, Any]] = page.evaluate(_POPUP_JS)
                    shots: list[PopupShot] = []
                    for info in infos:
                        selector = f'[data-wp1b-popup="{info["index"]}"]'
                        try:
                            shot = page.locator(selector).first.screenshot(
                                timeout=5_000, animations="disabled", caret="hide"
                            )
                        except PlaywrightError:
                            continue
                        name = "#" + info["id"] if info.get("id") else (info.get("cls") or info["tag"])
                        shots.append(
                            PopupShot(
                                selector=str(name)[:120],
                                sha256=hashlib.sha256(shot).hexdigest(),
                                width=int(info["width"]),
                                height=int(info["height"]),
                                images=tuple(str(s) for s in info.get("images", [])),
                                text=normalize_popup_text(str(info.get("text") or "")),
                                dhash=dhash(shot),
                            )
                        )
                    lines = (" ".join(line.split()) for line in text.splitlines())
                    return RenderResult(
                        url=url,
                        final_url=page.url,
                        status=response.status if response is not None else None,
                        screenshot_png=png,
                        dom_text="\n".join(line for line in lines if line),
                        popups=tuple(shots),
                    )
                finally:
                    browser.close()
        except PlaywrightError as exc:
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            return RenderResult(url=url, error=f"render: {first[:200]}")
