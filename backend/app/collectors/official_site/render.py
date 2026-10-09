"""Playwright chromium 렌더: 전체 화면 스크린샷 PNG + 렌더 후 DOM 텍스트 + 팝업 요소 이미지 해시.

- 렌더는 ``core.http`` 로 같은 URL 을 먼저 받아 성공(robots 허용·2xx)한 뒤에만 한다(수집기가 보장).
- 팝업 = 보이는 ``popup·pop_·layer_pop·modal·lightbox·role=dialog`` 요소 중 가장 바깥 것(최대 10개).
  요소 스크린샷 PNG 의 sha256·perceptual hash(dHash 64비트)·정규화 텍스트를 남긴다.
- **안정 해시(R3 M13)**: 시계·애니메이션이 있는 팝업은 렌더마다 픽셀이 달라진다. 그래서
  1) 렌더를 멈춘다: ``reduced_motion=reduce`` + 애니메이션·전환 정지 CSS + ``getAnimations()`` 일시정지 +
     동영상 정지 + 스크린샷 ``animations='disabled'``·``caret='hide'``;
  2) ``popup_hash`` 는 픽셀이 아니라 **팝업 서명**(시각 표기를 가린 정규화 텍스트 + 이미지 주소 + 크기; 글자도
     이미지도 없으면 dHash)의 sha256 이다(팝업이 없으면 None). WP7 은 이 값으로 팝업 변경을 감지한다.
     이미지 주소는 ``normalize_image_url`` 로 캐시버스터(``?v=``·``?t=``·``?_=``·숫자만 쿼리 …)와 fragment 를
     떼고 남은 쿼리를 정렬한 뒤 넣는다(R3b F1b — 같은 팝업이 ``?v=123`` 때문에 다른 서명이 되지 않게).
     글자는 NFC·제로폭 문자 제거·공백 하나로(``text_sha256`` 도 같은 정규화 — D10-2 분류 복사 기준).
  3) 서명이 같아도 그림이 크게 바뀌었는지는 dHash 해밍 거리로 본다(``visual_change``, 임계값
     ``DHASH_THRESHOLD``) — 수집기가 직전 렌더와 비교해 넘으면 해시를 바꾸고, 안 넘으면 직전 스크린샷 행을
     재사용한다(같은 화면이면 raw_document 가 늘지 않는다).
- 실패는 예외 대신 ``RenderResult.error`` 로 돌려준다(실패도 데이터).
- **SSRF(R3b F1b)**: 브라우저도 ``core.http`` 와 같은 내부망 규칙을 따른다(``BrowserGuard``).
  1) ``page.goto`` 전에 URL 을 검사한다(http/https 만, localhost·내부망 IP·DNS 가 내부망으로 풀리는
     이름 차단).
  2) 본 호스트는 검사 때 푼 IP 로 고정한다(chromium ``--host-resolver-rules=MAP host ip``) — 브라우저가 다시
     풀 때 다른 IP 를 받는 DNS rebinding 을 막는다.
  3) 모든 하위 요청(이미지·스크립트·iframe·JS 이동)은 ``context.route`` 에서 같은 검사 → 내부망이면 abort.
     서비스 워커는 route 를 우회하므로 막는다(``service_workers='block'``).
  4) Playwright route 는 리다이렉트 단계를 거치지 않는다 → ``request`` 이벤트에서 리다이렉트로 온 요청이
     내부망이면(요청은 이미 나갔으므로) 렌더 결과를 버리고 ``blocked_host`` 오류로 돌려준다. 최종 URL 도
     검사한다.
  내부망 허용(``allow_private``, 테스트 로컬 서버)은 ``core.http.allow_private_hosts`` 를 따른다
  (prod 면 거부).
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import ipaddress
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpcore

from app.core.http import (
    BLOCKED_HOST,
    BlockedHostError,
    Resolver,
    allow_private_hosts,
    host_block_reason,
    pinned_addresses,
    system_resolve,
)

__all__ = [
    "DHASH_THRESHOLD",
    "FREEZE_CSS",
    "BrowserGuard",
    "PlaywrightRenderer",
    "PopupShot",
    "RenderResult",
    "Renderer",
    "dhash",
    "hamming",
    "normalize_image_url",
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
  document.querySelectorAll('video, audio').forEach((m) => {
    try { m.pause(); m.currentTime = 0; } catch (e) {}
  });
  return true;
}
"""
_TIME_RES = (
    re.compile(r"(?:(?:오전|오후|AM|PM|am|pm)\s*)?\d{1,2}\s*:\s*\d{2}(?:\s*:\s*\d{2})?(?:\.\d+)?"),
    re.compile(r"(?:(?:오전|오후)\s*)?\d{1,2}\s*시\s*\d{1,2}\s*분(?:\s*\d{1,2}\s*초)?"),
    re.compile(r"\d{1,2}\s*분\s*\d{1,2}\s*초"),
)
_WS = re.compile(r"\s+")
_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")


def normalize_popup_text(text: str) -> str:
    """팝업 글자 → 서명용: NFC, 제로폭 문자 제거, 시각 표기(12:03·12:03:45·오후 3시 5분 7초)를
    ``<시각>`` 으로, 공백(줄바꿈·nbsp 포함)을 하나로. 날짜·세대수·금액 같은 공고 내용은 그대로 둔다
    (그게 바뀌면 팝업 변경이다). 여러 번 적용해도 같다(멱등)."""
    out = _ZERO_WIDTH.sub("", unicodedata.normalize("NFC", text))
    for pattern in _TIME_RES:
        out = pattern.sub("<시각>", out)
    return _WS.sub(" ", out).strip()


_VOLATILE_PARAMS = frozenset(
    {
        "v", "ver", "version", "t", "ts", "_", "_t", "_ts", "_v", "cb", "cachebust", "cachebuster",
        "cache", "nocache", "nc", "rnd", "rand", "random", "time", "timestamp", "dt", "rev", "bust",
    }
)  # fmt: skip
"""이미지 주소의 캐시버스터 쿼리 이름(값이 바뀌어도 같은 그림)."""


def normalize_image_url(src: str) -> str:
    """팝업 서명용 이미지 주소: 스킴·호스트 소문자, fragment 제거, 캐시버스터 쿼리(``_VOLATILE_PARAMS`` 와
    값 없는 숫자만 쿼리 ``?20261009``) 제거, 남은 쿼리 정렬. data: 주소·파싱 못 하는 주소는 그대로."""
    s = src.strip()
    if s.lower().startswith("data:"):
        return s
    try:
        parts = urlsplit(s)
        pairs = parse_qsl(parts.query, keep_blank_values=True)
    except ValueError:
        return s
    kept = sorted(
        (k, v) for k, v in pairs if k.lower() not in _VOLATILE_PARAMS and not (v == "" and k.isdigit())
    )
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(kept), ""))


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
        text = normalize_popup_text(self.text)  # 이미 정규화된 글자면 그대로(멱등)
        return {
            "selector": self.selector,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "images": list(self.images),
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
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
    images = ",".join(sorted(normalize_image_url(s) for s in p.images))
    text = normalize_popup_text(p.text)
    # 글자도 이미지 주소도 없는 그림 팝업은 그림 자체(dHash, 없으면 바이트 해시)
    content = f"text:{text}|img:{images}" if text or images else f"pix:{p.dhash or p.sha256}"
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


_PASS_SCHEMES = frozenset({"about", "data", "blob"})  # 네트워크로 나가지 않는 주소


class BrowserGuard:
    """Playwright 렌더 1회의 요청 검사(모듈 설명 SSRF). ``core.http`` 의 내부망 규칙을 그대로 쓴다.

    - ``prepare(url)``: goto 전 검사 + 본 호스트 IP 고정(사유가 있으면 그 문자열, 없으면 None)
    - ``launch_args()``: chromium 인자(``--host-resolver-rules``)
    - ``on_route(route)``: ``context.route('**/*', …)`` 처리기 — 내부망이면 abort('blockedbyclient')
    - ``on_request(request)``: ``context.on('request', …)`` — 리다이렉트로 온 내부망 요청이면 ``violation``
    """

    def __init__(self, *, allow_private: bool, resolver: Resolver) -> None:
        self.allow_private = allow_private
        self._resolver = resolver
        self._cache: dict[str, str | None] = {}
        self.pins: dict[str, str] = {}
        self.blocked: list[str] = []  # abort 한 하위 요청(사유 + URL)
        self.violation: str | None = None  # 렌더 결과를 버려야 하는 사유(본문 이동·리다이렉트·최종 URL)

    def url_reason(self, url: str) -> str | None:
        """이 주소로 요청하면 안 되는 사유. http/https 만 허용(about·data·blob 은 네트워크 없음)."""
        try:
            parts = urlsplit(url)
            host = parts.hostname
        except ValueError:
            return f"{BLOCKED_HOST}: 잘못된 주소"
        scheme = parts.scheme.lower()
        if scheme in _PASS_SCHEMES:
            return None
        if scheme not in {"http", "https"}:
            return f"{BLOCKED_HOST}: 허용하지 않는 스킴 {scheme or '(없음)'}"
        if not host:
            return f"{BLOCKED_HOST}: 호스트 없음"
        if self.allow_private:
            return None
        if host not in self._cache:
            self._cache[host] = host_block_reason(host, self._resolver)
        return self._cache[host]

    def prepare(self, url: str) -> str | None:
        """goto 전 검사. 본 호스트가 이름이면 DNS 를 **한 번만** 풀어 그 답 전부를 검사하고, 통과하면 그 IP 로
        고정한다(검사한 답과 브라우저가 연결하는 IP 가 같다)."""
        try:
            parts = urlsplit(url)
            host = parts.hostname
        except ValueError:
            return f"{BLOCKED_HOST}: 잘못된 주소"
        is_name = bool(host) and not _is_ip(host or "") and parts.scheme.lower() in {"http", "https"}
        if self.allow_private or not is_name or host is None:
            return self.url_reason(url)
        local = host_block_reason(host, None)  # localhost 이름(DNS 없이)
        if local is not None:
            return local
        try:
            ips = pinned_addresses(host, self._resolver)
        except BlockedHostError as exc:
            self._cache[host] = str(exc)
            return str(exc)
        except httpcore.ConnectError:
            return None  # DNS 실패 — 브라우저도 실패해 render 오류로 남는다(고정할 IP 없음)
        self._cache[host] = None
        self.pins[host] = ips[0]
        return None

    def launch_args(self) -> list[str]:
        if not self.pins:
            return []
        rules = ", ".join(
            f"MAP {host} {f'[{ip}]' if ':' in ip else ip}" for host, ip in sorted(self.pins.items())
        )
        return [f"--host-resolver-rules={rules}"]

    def on_route(self, route: Any) -> None:
        request = route.request
        reason = self.url_reason(str(request.url))
        if reason is None:
            route.continue_()
            return
        self.blocked.append(f"{reason} ({request.url})")
        if _is_main_navigation(request):
            self.violation = self.violation or reason
        route.abort("blockedbyclient")

    def on_request(self, request: Any) -> None:
        if request.redirected_from is None:
            return
        reason = self.url_reason(str(request.url))
        if reason is not None:
            self.violation = self.violation or f"{reason} (리다이렉트 {request.url})"


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]").split("%", 1)[0])
    except ValueError:
        return False
    return True


def _is_main_navigation(request: Any) -> bool:
    try:
        if not request.is_navigation_request():
            return False
        frame = getattr(request, "frame", None)
        return frame is None or getattr(frame, "parent_frame", None) is None
    except Exception:  # 서비스 워커 요청 등 frame 이 없는 경우
        return False


class PlaywrightRenderer:
    """동기 Playwright chromium(headless). 이벤트 루프가 도는 스레드에서는 부르지 않는다(worker 스레드용).

    ``allow_private``·``resolver`` 는 ``core.http`` 와 같은 뜻(None 이면 설정; prod 에서 허용이면 생성 거부).
    """

    def __init__(
        self,
        *,
        timeout_ms: int = 30_000,
        settle_ms: int = 1_500,
        viewport: tuple[int, int] = (1280, 900),
        user_agent: str | None = None,
        full_page: bool = True,
        allow_private: bool | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.settle_ms = settle_ms
        self.viewport = viewport
        self.user_agent = user_agent
        self.full_page = full_page
        self.allow_private = allow_private_hosts(allow_private)
        self._resolver: Resolver = resolver if resolver is not None else system_resolve

    def guard(self) -> BrowserGuard:
        return BrowserGuard(allow_private=self.allow_private, resolver=self._resolver)

    def render(self, url: str) -> RenderResult:
        guard = self.guard()
        reason = guard.prepare(url)
        if reason is not None:  # 브라우저를 띄우지 않는다
            return RenderResult(url=url, error=reason)

        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        from app.core.settings import get_settings

        ua = self.user_agent or get_settings().http_user_agent
        try:
            with sync_playwright() as p:
                return self._render_with(p, url, guard, ua)
        except PlaywrightError as exc:
            if guard.violation is not None:
                return RenderResult(url=url, error=guard.violation)
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            return RenderResult(url=url, error=f"render: {first[:200]}")

    def _render_with(self, p: Any, url: str, guard: BrowserGuard, ua: str) -> RenderResult:
        """브라우저 1회: 검사 훅을 goto 보다 먼저 걸고, 위반이 있으면 결과를 버린다."""
        from playwright.sync_api import Error as PlaywrightError

        browser = p.chromium.launch(headless=True, args=guard.launch_args())
        try:
            context = browser.new_context(
                viewport={"width": self.viewport[0], "height": self.viewport[1]},
                user_agent=ua,
                locale="ko-KR",
                reduced_motion="reduce",
                service_workers="block",
            )
            context.route("**/*", guard.on_route)
            context.on("request", guard.on_request)
            page = context.new_page()
            try:
                response = page.goto(url, wait_until="load", timeout=self.timeout_ms)
            except PlaywrightError:
                if guard.violation is not None:
                    return RenderResult(url=url, error=guard.violation)
                raise
            if guard.violation is not None:
                return RenderResult(url=url, final_url=str(page.url), error=guard.violation)
            self._settle(page)
            result = self._capture(page, url, response)
            final = str(page.url)
            if guard.violation is None and (final_reason := guard.url_reason(final)) is not None:
                guard.violation = f"{final_reason} (최종 URL {final})"
            if guard.violation is not None:
                return RenderResult(url=url, final_url=final, error=guard.violation)
            return result
        finally:
            browser.close()

    def _settle(self, page: Any) -> None:
        from playwright.sync_api import Error as PlaywrightError

        # 계속 통신하는 페이지는 networkidle 이 오지 않는다 — load 까지로 충분
        with contextlib.suppress(PlaywrightError):
            page.wait_for_load_state("networkidle", timeout=min(5_000, self.timeout_ms))
        page.wait_for_timeout(self.settle_ms)
        # 애니메이션·전환·동영상을 멈춘다(안정 해시, R3 M13)
        with contextlib.suppress(PlaywrightError):
            page.add_style_tag(content=FREEZE_CSS)
            page.evaluate(_FREEZE_JS)

    def _capture(self, page: Any, url: str, response: Any) -> RenderResult:
        from playwright.sync_api import Error as PlaywrightError

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
