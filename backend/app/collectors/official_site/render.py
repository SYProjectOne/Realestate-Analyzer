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
- **SSRF(R3b F1b → R3b 마무리)**: 브라우저도 ``core.http`` 와 같은 내부망 규칙을 따른다(``BrowserGuard``).
  1) ``page.goto`` 전에 URL 을 검사한다(http/https 만, localhost·내부망 IP·DNS 가 내부망으로 풀리는
     이름 차단). 막히면 브라우저를 띄우지 않는다.
  2) **연결 전 검사 = 출구 프록시**(``egress.EgressProxy``): chromium 의 모든 연결(하위 리소스·iframe·JS 이동·
     **리다이렉트 단계**·WebSocket)은 렌더 1회용 로컬 프록시로만 나간다(Playwright 는 ``<-loopback>`` 으로 루프백도
     프록시로 보낸다). 프록시는 요청마다 ``connect_address`` 로 목적지를 검사하고 **검사한 IP 로만** 연결한다 —
     본 호스트 외 이름도 렌더당 한 번 풀어 답 전부를 검사하고 그 IP 로 고정(DNS rebinding 차단). 리다이렉트 단계는
     Playwright ``route`` 를 거치지 않지만(1.63 실측) 새 프록시 요청이므로 나가기 전에 막힌다(``route.fetch`` 로
     대신 받지 않는다 — 차단 우선).
  3) 이름 해석 차단: ``--host-resolver-rules`` = 본 호스트 고정 IP + ``MAP * ~NOTFOUND``(프록시 127.0.0.1 만 EXCLUDE) — 프록시를 우회하는
     경로가 생겨도 브라우저가 직접 이름을 풀지 못한다. QUIC 끔, WebRTC 는 프록시 밖 UDP 금지.
  4) 모든 하위 요청은 ``context.route`` 에서도 먼저 같은 검사 → 내부망이면 abort(프록시까지 가지 않는다).
     서비스 워커는 route 를 우회하므로 막는다(``service_workers='block'``).
  5) WebSocket: ``context.route_web_socket``(Playwright ≥ 1.48 — pyproject 하한)으로 모든 WebSocket 을 서버에
     연결하지 않는다(모의 소켓, 기록만 — 처리기에서 ``close()`` 를 부르면 동기 API 가 멈춘다, 1.63 실측). 프록시도
     평문 ``Upgrade`` 요청을 막는다(이중).
  6) 본문 이동이 리다이렉트로 내부망을 가리키면(프록시가 막았어도) 렌더 결과를 버리고 ``blocked_host`` 오류로
     돌려준다(``request`` 이벤트 — 하위 리소스 리다이렉트는 기록만). 최종 URL 도 검사한다.
  내부망 허용(``allow_private``, 테스트 로컬 서버)은 ``core.http.allow_private_hosts`` 를 따른다
  (prod 면 거부). 허용이어도 프록시·WebSocket 차단은 그대로다.
  7) (R3c SEC) 목적지 포트는 공개 웹(80·443, ``egress.PUBLIC_WEB_PORTS``)만 — goto 전·route·프록시 모두 같은
     규칙(``allowed_ports``; ``allow_private`` 로컬 시험은 기본 제한 없음). 프록시는 렌더마다 무작위 토큰으로
     인증한다. 이름의 답은 **전부** 검사해 v4 우선으로 고정하고 프록시가 앞 주소 연결 실패 시 다음 주소로
     폴백한다. 이름 풀기는 전역 락 밖(호스트별 락 — 같은 이름은 렌더당 한 번, 다른 이름은 서로 기다리지 않는다).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import contextlib
import hashlib
import io
import ipaddress
import re
import threading
import unicodedata
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpcore

from app.collectors.official_site.egress import PUBLIC_WEB_PORTS, EgressProxy, netloc_port, port_block_reason
from app.core.http import (
    BLOCKED_HOST,
    BlockedHostError,
    Resolver,
    allow_private_hosts,
    host_block_reason,
    ip_blocked,
    pinned_addresses,
    system_resolve,
)

__all__ = [
    "DHASH_THRESHOLD",
    "FREEZE_CSS",
    "BrowserFetch",
    "BrowserFetcher",
    "BrowserGuard",
    "PlaywrightRenderer",
    "PopupShot",
    "RenderResult",
    "Renderer",
    "dhash",
    "hamming",
    "is_tls_error",
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
    # R7-SITE(D26-1): 요소 스크린샷 PNG 바이트 — 팝업 그림 OCR 입력. 메타·서명·비교에 넣지 않는다(sha256·dhash 가 그 값)
    png: bytes = field(default=b"", repr=False, compare=False)

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
    html: str = ""  # 렌더 후 문서 HTML(``page.content()``) — TLS 브라우저 경로(D26-4)의 HTML 원문 행

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.screenshot_png)


@dataclass(frozen=True, slots=True)
class BrowserFetch:
    """브라우저로 받은 문서 1개(robots.txt — D26-4). 실패는 ``error``(예외 대신 데이터)."""

    url: str
    status: int | None = None
    text: str = ""
    final_url: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status is not None


_TLS_ERROR_MARKERS: Final = ("err_cert", "err_ssl", "ssl", "certificate", "tls")


def is_tls_error(message: str | None) -> bool:
    """오류 문구가 TLS·인증서 오류인가(httpx ``[SSL: …]``·chromium ``net::ERR_CERT_…``·``ERR_SSL_…``). 문자열 검사."""
    low = (message or "").lower()
    return any(m in low for m in _TLS_ERROR_MARKERS)


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


class BrowserFetcher(Protocol):
    """브라우저로 문서 하나를 받는다(robots.txt — D26-4). 인증서 검증은 켠 채(브라우저 기본 검증기 — 중간 인증서 AIA 보완)."""

    def fetch(self, url: str) -> BrowserFetch: ...


_PASS_SCHEMES = frozenset({"about", "data", "blob"})  # 네트워크로 나가지 않는 주소


class BrowserGuard:
    """Playwright 렌더 1회의 요청 검사(모듈 설명 SSRF). ``core.http`` 의 내부망 규칙을 그대로 쓴다.

    - ``prepare(url)``: goto 전 검사 + 본 호스트 IP 고정(사유가 있으면 그 문자열, 없으면 None)
    - ``launch_args()``: chromium 인자(``--host-resolver-rules``)
    - ``on_route(route)``: ``context.route('**/*', …)`` 처리기 — 내부망이면 abort('blockedbyclient')
    - ``on_request(request)``: ``context.on('request', …)`` — 리다이렉트로 온 내부망 요청이면 ``violation``

    ``allowed_ports``: 목적지 포트 허용 목록. None 이면 기본 — 공개 웹(80·443), ``allow_private``(로컬 시험
    서버, prod 거부)면 제한 없음.
    """

    def __init__(
        self, *, allow_private: bool, resolver: Resolver, allowed_ports: Collection[int] | None = None
    ) -> None:
        self.allow_private = allow_private
        self._resolver = resolver
        if allowed_ports is not None:
            self.allowed_ports: frozenset[int] | None = frozenset(allowed_ports)
        else:
            self.allowed_ports = None if allow_private else PUBLIC_WEB_PORTS
        self._cache: dict[str, str | None] = {}
        self.pins: dict[str, str] = {}  # 이름 → 첫 IP(--host-resolver-rules MAP)
        self.addresses: dict[str, list[str]] = {}  # 이름 → 검사한 IP 전부(v4 우선, 프록시 폴백 순서)
        self._failures: dict[str, Exception] = {}  # 이름 → 연결 시점 검사 실패(렌더당 한 번)
        self._host_locks: dict[str, threading.Lock] = {}
        self.blocked: list[str] = []  # abort 한 하위 요청(사유 + URL)
        self.websockets: list[str] = []  # 연결하지 않은 WebSocket 주소
        self.violation: str | None = None  # 렌더 결과를 버려야 하는 사유(본문 이동·리다이렉트·최종 URL)
        self._connect_lock = threading.Lock()

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
        port_reason = port_block_reason(
            netloc_port(parts.netloc, 443 if scheme == "https" else 80), self.allowed_ports
        )
        if port_reason is not None:
            return port_reason
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
        scheme = parts.scheme.lower()
        port_reason = port_block_reason(
            netloc_port(parts.netloc, 443 if scheme == "https" else 80), self.allowed_ports
        )
        if port_reason is not None:  # 이름을 풀기 전에
            return port_reason
        local = host_block_reason(host, None)  # localhost 이름(DNS 없이)
        if local is not None:
            return local
        try:
            ips = _v4_first(pinned_addresses(host, self._resolver))
        except BlockedHostError as exc:
            self._cache[host] = str(exc)
            return str(exc)
        except httpcore.ConnectError:
            return None  # DNS 실패 — 브라우저도 실패해 render 오류로 남는다(고정할 IP 없음)
        self._cache[host] = None
        ascii_host = _ascii_host(host)  # 국문 도메인: 브라우저는 punycode 로 묻는다(프록시 CONNECT·MAP 규칙)
        for name in {host, ascii_host}:
            self.pins[name] = ips[0]
            self.addresses[name.lower()] = ips
        return None

    def connect_address(self, host: str, port: int) -> list[str]:
        """출구 프록시의 연결 직전 검사: 연결할 IP 목록(앞에서부터 시도, v4 우선). 막아야 하면
        ``BlockedHostError``, DNS 실패는 ``ConnectError``.

        본 호스트는 ``prepare`` 때 고정한 IP 들. 그 밖의 이름은 렌더당 **한 번** 풀어 답 전부를 검사하고 그 목록으로
        고정한다(같은 렌더 안에서 다시 풀지 않는다 — rebinding 차단. 실패도 렌더 동안 기억). 이름 풀기는 전역 락
        밖에서 호스트별 락으로 한다(느린 DNS 하나가 다른 호스트 연결을 막지 않는다). IP 문자열은 그 IP 를 검사한다.
        ``allow_private`` 면 고정 IP 또는 이름 그대로(시스템 DNS)."""
        h = host.strip("[]").rstrip(".")
        key = h.lower()
        with self._connect_lock:
            found = self._pinned(h)
            if found is not None:
                return found
            if self.allow_private:
                return [h]
            if _is_ip(h):
                if ip_blocked(h):
                    raise BlockedHostError(f"{BLOCKED_HOST}: 내부망 주소 {h}")
                return [h]
            host_lock = self._host_locks.setdefault(key, threading.Lock())
        with host_lock:
            with self._connect_lock:
                found = self._pinned(h)
                if found is not None:
                    return found
                failed = self._failures.get(key)
            if failed is not None:
                raise type(failed)(str(failed))
            try:
                ips = _v4_first(pinned_addresses(h, self._resolver))  # 전역 락 밖 DNS(이 호스트만 기다린다)
            except (BlockedHostError, httpcore.ConnectError) as exc:
                with self._connect_lock:
                    self._failures[key] = exc
                raise
            with self._connect_lock:
                self.addresses[key] = ips
                self.pins[key] = ips[0]
            return list(ips)

    def _pinned(self, h: str) -> list[str] | None:
        """고정된 주소 목록(``_connect_lock`` 안에서 부른다)."""
        found = self.addresses.get(h) or self.addresses.get(h.lower())
        if found:
            return list(found)
        pinned = self.pins.get(h) or self.pins.get(h.lower())
        return [pinned] if pinned is not None else None

    def launch_args(self) -> list[str]:
        """chromium 인자: 이름 해석 차단(고정 + ``MAP * ~NOTFOUND``)·QUIC 끔·WebRTC 프록시 밖 UDP 금지.

        ``allow_private`` 이고 고정이 없으면 이름 해석 규칙을 두지 않는다(로컬 시험 서버)."""
        args = ["--disable-quic", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"]
        rules = [f"MAP {host} {f'[{ip}]' if ':' in ip else ip}" for host, ip in sorted(self.pins.items())]
        if not self.allow_private:
            # 출구 프록시(127.0.0.1)만 예외 — MAP 규칙은 IP 문자열에도 걸린다(실측: 프록시 연결 실패)
            rules += ["MAP * ~NOTFOUND", "EXCLUDE 127.0.0.1"]
        if rules:
            args.insert(0, f"--host-resolver-rules={', '.join(rules)}")
        return args

    def on_websocket(self, ws: Any) -> None:
        """``context.route_web_socket`` 처리기: 서버에 연결하지 않는다(모의 소켓 — 네트워크 없음), 기록만."""
        self.websockets.append(str(ws.url))
        self.blocked.append(f"{BLOCKED_HOST}: WebSocket 차단 ({ws.url})")

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
        if reason is None:
            return
        # 연결은 출구 프록시가 이미 막았다(요청 전). 본문 이동이면 결과를 버리고, 하위 리소스면 기록만 한다.
        if _is_main_navigation(request):
            self.violation = self.violation or f"{reason} (리다이렉트 {request.url})"
        else:
            self.blocked.append(f"{reason} (리다이렉트 {request.url})")


def _v4_first(ips: Sequence[str]) -> list[str]:
    """IPv4 를 앞에(각 계열 안의 순서는 유지), 중복 제거. 시스템 DNS 는 문자열 정렬이라 v6 가 앞에 올 수 있다 —
    v6 경로가 없는 머신에서 첫 주소만 쓰면 502(minor 29). 프록시는 이 순서로 시도하고 실패하면 다음 주소로."""
    seen = list(dict.fromkeys(ips))
    return [ip for ip in seen if ":" not in ip] + [ip for ip in seen if ":" in ip]


def _ascii_host(host: str) -> str:
    try:
        return host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return host


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
        allowed_ports: Collection[int] | None = None,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.settle_ms = settle_ms
        self.viewport = viewport
        self.user_agent = user_agent
        self.full_page = full_page
        self.allow_private = allow_private_hosts(allow_private)
        self._resolver: Resolver = resolver if resolver is not None else system_resolve
        self.allowed_ports = frozenset(allowed_ports) if allowed_ports is not None else None

    def guard(self) -> BrowserGuard:
        return BrowserGuard(
            allow_private=self.allow_private, resolver=self._resolver, allowed_ports=self.allowed_ports
        )

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

    def fetch(self, url: str) -> BrowserFetch:
        """문서 하나(robots.txt)를 브라우저로 받는다 — D26-4 TLS 경로. 렌더와 같은 검사(내부망·포트·출구 프록시)를 거치고
        인증서 검증은 켠 채다. 상태 코드와 본문 글자를 돌려준다(robots 해석은 호출자 — RFC 9309)."""
        guard = self.guard()
        reason = guard.prepare(url)
        if reason is not None:
            return BrowserFetch(url=url, error=reason)

        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        from app.core.settings import get_settings

        ua = self.user_agent or get_settings().http_user_agent
        try:
            with sync_playwright() as p:
                return self._fetch_with(p, url, guard, ua)
        except PlaywrightError as exc:
            if guard.violation is not None:
                return BrowserFetch(url=url, error=guard.violation)
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            return BrowserFetch(url=url, error=f"browser: {first[:200]}")

    def _fetch_with(self, p: Any, url: str, guard: BrowserGuard, ua: str) -> BrowserFetch:
        with EgressProxy(
            guard.connect_address, timeout_s=self.timeout_ms / 1000, allowed_ports=guard.allowed_ports
        ) as proxy:
            try:
                browser = self._launch(p, guard, proxy)
                try:
                    page = self._page(browser, guard, ua)
                    response = page.goto(url, wait_until="load", timeout=self.timeout_ms)
                    final = str(page.url)
                    if guard.violation is None and (final_reason := guard.url_reason(final)) is not None:
                        guard.violation = f"{final_reason} (최종 URL {final})"
                    if guard.violation is not None:
                        return BrowserFetch(url=url, final_url=final, error=guard.violation)
                    if response is None:
                        return BrowserFetch(url=url, final_url=final, error="browser: 응답 없음")
                    return BrowserFetch(
                        url=url, status=int(response.status), text=str(response.text()), final_url=final
                    )
                finally:
                    browser.close()
            finally:
                guard.blocked.extend(proxy.blocked)

    def _render_with(self, p: Any, url: str, guard: BrowserGuard, ua: str) -> RenderResult:
        """브라우저 1회(출구 프록시 안): 검사 훅을 goto 보다 먼저 걸고, 위반이 있으면 결과를 버린다."""
        with EgressProxy(
            guard.connect_address, timeout_s=self.timeout_ms / 1000, allowed_ports=guard.allowed_ports
        ) as proxy:
            try:
                return self._browse(p, url, guard, ua, proxy)
            finally:
                guard.blocked.extend(proxy.blocked)

    def _launch(self, p: Any, guard: BrowserGuard, proxy: EgressProxy) -> Any:
        return p.chromium.launch(
            headless=True,
            args=guard.launch_args(),
            proxy={"server": proxy.server, "bypass": "<-loopback>", **proxy.credentials},  # 렌더 1회용 토큰
        )

    def _page(self, browser: Any, guard: BrowserGuard, ua: str) -> Any:
        """검사 훅을 건 새 페이지. **인증서 검증은 끄지 않는다**(``ignore_https_errors=False`` — D26-4: 브라우저는 자기
        검증기로 체인을 보완할 뿐, 오류를 무시하지 않는다)."""
        context = browser.new_context(
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
            user_agent=ua,
            locale="ko-KR",
            reduced_motion="reduce",
            service_workers="block",
            ignore_https_errors=False,
        )
        context.route("**/*", guard.on_route)
        context.route_web_socket("**/*", guard.on_websocket)
        context.on("request", guard.on_request)
        return context.new_page()

    def _browse(self, p: Any, url: str, guard: BrowserGuard, ua: str, proxy: EgressProxy) -> RenderResult:
        from playwright.sync_api import Error as PlaywrightError

        browser = self._launch(p, guard, proxy)
        try:
            page = self._page(browser, guard, ua)
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
        html = ""
        with contextlib.suppress(PlaywrightError):
            html = str(page.content())  # 팝업 표식(data-wp1b-popup)을 달기 전
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
                    png=shot,
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
            html=html,
        )
