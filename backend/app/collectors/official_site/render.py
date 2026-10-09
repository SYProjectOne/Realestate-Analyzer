"""Playwright chromium 렌더: 전체 화면 스크린샷 PNG + 렌더 후 DOM 텍스트 + 팝업 요소 이미지 해시.

- 렌더는 ``core.http`` 로 같은 URL 을 먼저 받아 성공(robots 허용·2xx)한 뒤에만 한다(수집기가 보장).
- 팝업 = 보이는 ``popup·pop_·layer_pop·modal·lightbox·role=dialog`` 요소 중 가장 바깥 것(최대 10개).
  요소 스크린샷 PNG 의 sha256 을 남기고, ``popup_hash`` = 정렬한 해시들을 이은 문자열의 sha256
  (팝업이 없으면 None). WP7 이 이 값으로 팝업 변경을 감지한다.
- 실패는 예외 대신 ``RenderResult.error`` 로 돌려준다(실패도 데이터).
"""

from __future__ import annotations

import contextlib
import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

__all__ = ["PlaywrightRenderer", "PopupShot", "RenderResult", "Renderer", "popup_hash"]

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

    def as_meta(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "images": list(self.images),
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


def popup_hash(popups: tuple[PopupShot, ...] | list[PopupShot]) -> str | None:
    if not popups:
        return None
    joined = "\n".join(sorted(p.sha256 for p in popups))
    return hashlib.sha256(joined.encode("ascii")).hexdigest()


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
                    )
                    page = context.new_page()
                    response = page.goto(url, wait_until="load", timeout=self.timeout_ms)
                    # 계속 통신하는 페이지는 networkidle 이 오지 않는다 — load 까지로 충분
                    with contextlib.suppress(PlaywrightError):
                        page.wait_for_load_state("networkidle", timeout=min(5_000, self.timeout_ms))
                    page.wait_for_timeout(self.settle_ms)
                    png = page.screenshot(full_page=self.full_page)
                    text = page.inner_text("body") if page.locator("body").count() else ""
                    infos: list[dict[str, Any]] = page.evaluate(_POPUP_JS)
                    shots: list[PopupShot] = []
                    for info in infos:
                        selector = f'[data-wp1b-popup="{info["index"]}"]'
                        try:
                            shot = page.locator(selector).first.screenshot(timeout=5_000)
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
