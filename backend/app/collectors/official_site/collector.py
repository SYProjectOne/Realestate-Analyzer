"""단지 공식 홈페이지 수집기 (source_kind='official_site', RA §5 WP1 · T3).

단지 1개당 남는 raw_document
1. httpx(core.http) 응답: 성공이면 HTML(text_path = DOM 텍스트), 실패면 실패 행 — 403 은 http_status=403,
   DNS·TLS·timeout 은 http_status=None + error_text. 실패하면 렌더하지 않는다(접근 거부를 우회하지 않음).
2. 렌더(동적·팝업 표식이 있거나 render='always'): 전체 화면 PNG(text_path = 렌더 후 DOM 텍스트,
   image_hash = 팝업 안정 해시 ``render.popup_hash``). 렌더 실패는 실패 행(error_text='render: …').
   **같은 화면이면 행을 늘리지 않는다(R3 M13)**: 같은 URL·단지의 직전 렌더 메타(HTML 행 meta.render:
   ``signature``·``popups[]``·``screenshot_sha256``)와 비교해 서명(시각을 가린 DOM 텍스트 + 팝업 서명)이 같고
   팝업 그림의 dHash 거리도 임계값 안이면 직전 스크린샷 행을 그대로 쓴다(image_hash 도 같다 → 가짜 팝업
   변경·재판정 없음). 서명은 같은데 그림이 임계값 넘게 바뀌었으면 image_hash 를 바꿔(팝업 해시 + dHash)
   새 행으로 남긴다.
메타(계약 2026-10-09.2 ``raw_document.meta``): 1번 HTML 행의 meta 컬럼에 둔다(별도 행 없음).
   키 = {kind, url, final_url, complex_id, html_sha256, render{reason, rendered, error, screenshot_sha256,
   signature, popups[{selector, sha256, width, height, images, text_sha256, dhash, signature}]}, image_hash,
   intake_candidates[{text, keywords, source}]}. 시각을 넣지 않는다.
   같은 HTML(같은 행)을 다시 수집하면 meta 는 최신 관찰(렌더 결과)로 바뀐다 — 렌더 이력은 스크린샷 행
   (image_hash)마다 남는다.
   상태 판단은 하지 않는다(WP2·판정기).
   2026-10-09.1 까지는 메타가 별도 JSON 행(content_type ``META_CONTENT_TYPE``)이었다 — ``read_site_meta`` 가
   두 모양을 다 읽는다(호환).

대상: ``targets`` 를 주면 그것만, 아니면 region 의 complex.official_site_url 전부.

R7-SITE(DECISIONS D26):
3. **팝업 그림 OCR(D26-1)**: 렌더한 팝업 요소 그림(PNG)을 공고문 OCR 엔진(D5 RapidOCR, ``notice_pdf.ocr``)으로 읽어 스크린샷
   행(PNG)의 meta 에 둔다 — ``{kind: 'official_site.popup_ocr', label: '추정(OCR)', engine, status, reason, items[{popup_sha256,
   signature, dhash, selector, image_path, text_path, text_sha256, chars, checked_at, seconds, status, error}]}``. 그림 원본·글자는
   원문 저장소(sha256 경로) 파일이다. **캐시**: 같은 화면이라 직전 스크린샷 행을 다시 쓰면 그 행의 OCR 을 그대로 쓰고(다시
   읽지 않는다 — 접수 classify 입력이 그대로라 분류 복사 D10-2), 새 스크린샷 행이면 같은 URL 의 이전 OCR 중 팝업 그림
   sha256 이 같거나(서명이 같고 dHash 거리 ``DHASH_THRESHOLD`` 이내) 한 것을 재사용한다. 페이지당 OCR 시간 예산
   ``OCR_BUDGET_S``(D5 — CPU 페이지당 30초)를 넘기면 남은 팝업은 ``skipped``. 엔진이 없으면 ``status='unavailable'`` + 사유.
   글자를 해석하지 않는다 — 접수 분류는 판정기(``scheduler.intake``).
4. **TLS 실패 사이트(D26-4)**: httpx 가 TLS·인증서 오류(robots.txt 포함)면 헤드리스 브라우저로 robots.txt 와 본문을 다시 받는다.
   인증서 검증은 켠 채다(``ignore_https_errors`` 쓰지 않음 — 브라우저 검증기의 체인 보완(중간 인증서 AIA)만 쓴다). robots 는
   브라우저로 받은 robots.txt 가 정한다(RFC 9309: 2xx 규칙·4xx 제한 없음·5xx·실패 전부 불허). 브라우저도 TLS 로 실패하면
   실패 행 'TLS' 그대로. 경로는 meta ``fetch{path: 'browser', reason: 'TLS', failed: 'robots.txt'|'page', robots{status,
   error}, result}`` 에 남는다(실패 행도 meta). 브라우저 요청 전에 ``core.http`` 의 호스트별 속도 제한 예약을 같이 쓴다.
   접근 거부(403 등)는 브라우저로 받아도 저장하지 않는다(D25-4).
"""

# ruff: noqa: E501  (한국어 docstring·주석)

from __future__ import annotations

import hashlib
import json
import time
import urllib.robotparser
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.official_site.extract import html_to_text, intake_candidates, needs_render
from app.collectors.official_site.render import (
    DHASH_THRESHOLD,
    BrowserFetch,
    PlaywrightRenderer,
    PopupShot,
    Renderer,
    RenderResult,
    hamming,
    is_tls_error,
    popup_hash,
    popup_signature,
    render_signature,
    visual_change,
)
from app.collectors.reference.rawstore import Failure, RawStore, fetch_failure, iso_kst
from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.db import get_session
from app.core.http import FetchResult, HttpClient
from app.core.paths import resolve_raw_path
from app.core.snapshot import store_raw
from app.core.time import now_kst, to_kst
from app.models import Complex
from app.models import RawDocument as RawDocumentRow

__all__ = [
    "META_CONTENT_TYPE",
    "OCR_BUDGET_S",
    "OCR_LABEL",
    "OCR_META_KIND",
    "OfficialSiteCollector",
    "PopupOcr",
    "SiteOutcome",
    "SiteTarget",
    "popup_ocr_texts",
    "read_site_meta",
    "robots_verdict",
]

# 2026-10-09.1 까지의 별도 메타 행 content_type(읽기 호환용 — 새로 만들지 않는다)
META_CONTENT_TYPE = "application/json; profile=official_site.meta"


def read_site_meta(raw: RawDocument, *, raw_dir: Path | None = None) -> dict[str, Any] | None:
    """official_site 메타 읽기.

    새 행은 ``raw.meta``, 옛 별도 메타 행(``META_CONTENT_TYPE``)은 그 JSON 파일.
    """
    if raw.meta is not None:
        return dict(raw.meta)
    if raw.content_type != META_CONTENT_TYPE or not raw.path:
        return None
    p = resolve_raw_path(raw.path, raw_dir=raw_dir)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


RenderMode = Literal["auto", "always", "never"]
SessionFactory = Callable[[], AbstractContextManager[Session]]
PopupOcr = Callable[[bytes], str]
"""팝업 그림 PNG 바이트 → 줄 단위 텍스트(``notice_pdf.ocr.ocr_png``)."""

OCR_LABEL: Final = "추정(OCR)"
"""팝업 그림 OCR 글자의 라벨(D5-4·D26-1)."""
OCR_META_KIND: Final = "official_site.popup_ocr"
OCR_BUDGET_S: Final = 30.0
"""페이지 하나의 팝업 OCR 시간 예산(D5 기준 'CPU 페이지당 30초 이내')."""
OCR_UNAVAILABLE: Final = "OCR 엔진 없음(선택 의존성 ocr: rapidocr·onnxruntime 미설치)"
_OCR_ENGINE: Final = "rapidocr PP-OCRv5 korean(D5·ADR-12)"


def popup_ocr_texts(raw: RawDocument, *, raw_dir: Path | None = None) -> list[str]:
    """스크린샷 행 meta 의 팝업 OCR 글자(성공 항목, 팝업 순서). 없거나 파일이 없으면 빈 목록. 해석하지 않는다."""
    meta = raw.meta if isinstance(raw.meta, dict) else None
    if meta is None or meta.get("kind") != OCR_META_KIND:
        return []
    out: list[str] = []
    for item in meta.get("items") or []:
        rel = item.get("text_path") if isinstance(item, dict) else None
        if not rel or item.get("status", "ok") != "ok":
            continue
        path = resolve_raw_path(str(rel), raw_dir=raw_dir)
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                out.append(text)
    return out


def robots_verdict(fetched: BrowserFetch, user_agent: str, url: str) -> Failure | None:
    """브라우저로 받은 robots.txt 로 ``url`` 을 받아도 되는가(RFC 9309 — ``core.http`` 와 같은 규칙). 허용이면 None, 아니면
    실패 사유: 2xx + Disallow → 'robots', 4xx → 제한 없음(None), 5xx → 'robots.txt <코드>', 응답 없음 → TLS·기타 원인."""
    status = fetched.status
    if fetched.error is None and status is not None and 200 <= status < 300:
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(fetched.text.splitlines())
        return None if parser.can_fetch(user_agent, url) else Failure(None, "robots")
    if fetched.error is None and status is not None and 400 <= status < 500:
        return None
    if fetched.error is None and status is not None:
        return Failure(status, f"robots.txt {status}")
    return Failure(None, "TLS" if is_tls_error(fetched.error) else "robots")


@dataclass(frozen=True, slots=True)
class SiteTarget:
    url: str
    complex_id: int | None = None


@dataclass(slots=True)
class SiteOutcome:
    """단지 1개 결과(수집기 호출자·테스트용 요약)."""

    target: SiteTarget
    documents: list[RawDocument] = field(default_factory=list)
    failure: Failure | None = None
    rendered: bool = False
    render_reason: str | None = None
    image_hash: str | None = None
    meta: dict[str, Any] | None = None
    fetch_path: str = "httpx"  # 'httpx' | 'browser'(TLS 실패 뒤 브라우저 경로, D26-4)


class OfficialSiteCollector:
    source_kind = "official_site"

    def __init__(
        self,
        *,
        http: HttpClient | None = None,
        renderer: Renderer | None = None,
        render: RenderMode = "auto",
        targets: Sequence[SiteTarget] | None = None,
        session_factory: SessionFactory = get_session,
        raw_dir: Path | None = None,
        ocr: PopupOcr | Literal["auto"] | None = "auto",
        ocr_budget_s: float = OCR_BUDGET_S,
        tls_browser: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """``ocr='auto'``: 선택 의존성 OCR 엔진이 있으면 팝업 그림을 읽는다(``notice_pdf.ocr.load_image_ocr``). None 이면 읽지
        않는다(meta 에 남기지 않음). ``tls_browser``: TLS 실패면 브라우저로 다시 받는다(D26-4, 렌더 'never' 면 하지 않음)."""
        self._http = http
        self._renderer = renderer
        self._render_mode: RenderMode = render
        self._targets = list(targets) if targets is not None else None
        self._session_factory = session_factory
        self._raw_dir = raw_dir
        self._ocr_setting = ocr
        self._ocr: PopupOcr | None = None
        self._ocr_loaded = False
        self._ocr_budget_s = ocr_budget_s
        self._tls_browser = tls_browser
        self._clock = clock
        self._robots_seen: dict[str, BrowserFetch] = {}
        self.outcomes: list[SiteOutcome] = []

    def _region_targets(self, session: Session, region: Region) -> list[SiteTarget]:
        rows = session.execute(
            select(Complex.id, Complex.official_site_url)
            .where(Complex.region_id == region.id, Complex.official_site_url.is_not(None))
            .order_by(Complex.id)
        )
        return [SiteTarget(url, cid) for cid, url in rows if url]

    def fetch(self, region: Region, snapshot: Snapshot, since: str | None) -> list[RawDocument]:
        self.outcomes = []
        self._robots_seen = {}
        http = self._http or HttpClient()
        try:
            with self._session_factory() as session:
                store = RawStore(session, raw_dir=self._raw_dir)
                targets = (
                    self._targets if self._targets is not None else self._region_targets(session, region)
                )
                for target in targets:
                    self.outcomes.append(self._one(http, store, region.id, target))
        finally:
            if self._http is None:
                http.close()
        # R4 M5(D18-6): 같은 URL 을 쓰는 단지가 여럿이면 원문 행은 하나(sha256)다 — 돌려주는 원문에는 대상 단지를 단다
        # (접수 행은 단지마다, ``scheduler.collect.intake_rows`` 가 complex_id 로 묶는다)
        return [
            d
            if d.complex_id == o.target.complex_id
            else d.model_copy(update={"complex_id": o.target.complex_id})
            for o in self.outcomes
            for d in o.documents
        ]

    def _renderer_or_default(self) -> Renderer:
        if self._renderer is None:
            self._renderer = PlaywrightRenderer()
        return self._renderer

    def _get_ocr(self) -> PopupOcr | None:
        if not self._ocr_loaded:
            if self._ocr_setting == "auto":
                from app.collectors.notice_pdf import ocr

                self._ocr = ocr.load_image_ocr()
            else:
                self._ocr = self._ocr_setting
            self._ocr_loaded = True
        return self._ocr

    def _one(self, http: HttpClient, store: RawStore, region_id: int, target: SiteTarget) -> SiteOutcome:
        out = SiteOutcome(target)
        r = http.get(target.url)
        if (
            not r.ok
            and fetch_failure(r).error_text == "TLS"
            and self._tls_browser
            and self._render_mode != "never"
        ):
            return self._via_browser(http, store, region_id, target, r, out)
        if not r.ok:
            out.failure = fetch_failure(r)
            out.documents.append(
                store.save_result(
                    r,
                    source_kind="official_site",
                    ext="html",
                    region_id=region_id,
                    complex_id=target.complex_id,
                    failure=out.failure,
                )
            )
            return out
        html = r.text()
        dom_text = html_to_text(html)
        html_doc = store.save_result(
            r,
            source_kind="official_site",
            ext="html",
            content_type=r.headers.get("content-type", "text/html"),
            text=dom_text,
            region_id=region_id,
            complex_id=target.complex_id,
        )
        out.documents.append(html_doc)
        want, reason = needs_render(html, dom_text)
        if self._render_mode == "always":
            want, reason = True, "always"
        elif self._render_mode == "never":
            want, reason = False, "never"
        out.render_reason = reason
        rendered: RenderResult | None = None
        if want:
            rendered = self._renderer_or_default().render(r.final_url or target.url)
            if rendered.ok:
                out.rendered = True
                doc, out.image_hash = self._screenshot(store, region_id, target, rendered)
                out.documents.append(self._popup_ocr(store, target, rendered, doc))
            else:
                out.documents.append(
                    store.save_failure(
                        source_kind="official_site",
                        url=target.url,
                        failure=Failure(None, "render"),
                        region_id=region_id,
                        complex_id=target.complex_id,
                        detail=(rendered.error or "").removeprefix("render: ")[:200] or None,
                    )
                )
        shot = out.documents[1] if rendered is not None and rendered.ok and len(out.documents) > 1 else None
        out.meta = self._meta(
            target, r.final_url, html_doc, dom_text, reason, rendered, out.image_hash,
            shot.sha256 if shot is not None else None,
        )  # fmt: skip
        out.documents[0] = self._attach_meta(store, html_doc, out.meta)
        return out

    # ------------------------------------------------------------------ D26-4 TLS → 브라우저

    def _via_browser(
        self,
        http: HttpClient,
        store: RawStore,
        region_id: int,
        target: SiteTarget,
        r: FetchResult,
        out: SiteOutcome,
    ) -> SiteOutcome:
        """httpx TLS 실패 → 브라우저(인증서 검증 켬)로 robots.txt(필요하면)·본문. 모듈 설명 4."""
        out.fetch_path = "browser"
        renderer = self._renderer_or_default()
        failed = "robots.txt" if r.blocked_by_robots else "page"
        info: dict[str, Any] = {"path": "browser", "reason": "TLS", "failed": failed}
        url = target.url
        failure: Failure | None = None
        detail: str | None = None
        if r.blocked_by_robots:
            parts = urlsplit(url)
            origin = f"{parts.scheme}://{parts.netloc}"
            robots = self._robots_seen.get(origin)
            fetcher = getattr(renderer, "fetch", None)
            if robots is None and callable(fetcher):
                _pace(http, url)
                robots = fetcher(f"{origin}/robots.txt")
                if isinstance(robots, BrowserFetch):
                    self._robots_seen[origin] = robots
            if not isinstance(robots, BrowserFetch):
                failure, detail = Failure(None, "TLS"), "브라우저로 robots.txt 를 받을 수 없음"
                info["robots"] = {"path": "browser", "status": None, "error": "fetch 없음"}
            else:
                info["robots"] = {"path": "browser", "status": robots.status, "error": _short(robots.error)}
                failure = robots_verdict(robots, getattr(http, "user_agent", ""), url)
        rendered: RenderResult | None = None
        if failure is None:
            _pace(http, url)
            rendered = renderer.render(url)
            info["page"] = {"path": "browser", "status": rendered.status, "error": _short(rendered.error)}
            if not rendered.ok:
                failure = Failure(None, "TLS" if is_tls_error(rendered.error) else "render")
                detail = _short(rendered.error)
            elif rendered.status is not None and rendered.status >= 400:
                failure = Failure(
                    rendered.status, None
                )  # 접근 거부·없음 — 받은 화면을 저장하지 않는다(D25-4)
        if failure is not None or rendered is None:
            out.failure = failure or Failure(None, "TLS")
            info["result"] = out.failure.reason
            doc = store.save_failure(
                source_kind="official_site",
                url=url,
                failure=out.failure,
                region_id=region_id,
                complex_id=target.complex_id,
                detail=detail if out.failure.error_text not in ("TLS", "robots") else None,
            )
            meta = {"kind": "official_site.fetch", "url": url, "complex_id": target.complex_id, "fetch": info}
            out.meta = meta
            out.documents.append(self._attach_meta(store, doc, meta))
            return out
        info["result"] = "ok"
        dom_text = html_to_text(rendered.html) if rendered.html else rendered.dom_text
        body = (rendered.html or rendered.dom_text).encode("utf-8")
        html_doc = store.save_content(
            source_kind="official_site",
            url=url,
            content=body,
            ext="html",
            content_type="text/html; charset=utf-8",
            http_status=rendered.status or 200,
            text=dom_text,
            region_id=region_id,
            complex_id=target.complex_id,
        )
        out.documents.append(html_doc)
        out.rendered = True
        out.render_reason = "TLS 브라우저 경로"
        shot, out.image_hash = self._screenshot(store, region_id, target, rendered)
        out.documents.append(self._popup_ocr(store, target, rendered, shot))
        out.meta = self._meta(
            target, rendered.final_url, html_doc, dom_text, out.render_reason, rendered, out.image_hash, shot.sha256
        )  # fmt: skip
        out.meta["fetch"] = info
        out.documents[0] = self._attach_meta(store, html_doc, out.meta)
        return out

    # ------------------------------------------------------------------ D26-1 팝업 그림 OCR

    def _popup_ocr(
        self, store: RawStore, target: SiteTarget, rendered: RenderResult, doc: RawDocument
    ) -> RawDocument:
        """스크린샷 행 meta 에 팝업 그림 OCR(모듈 설명 3). 그림 바이트가 있는 팝업이 없으면 그대로."""
        shots = [p for p in rendered.popups if p.png]
        if not shots or self._ocr_setting is None:
            return doc
        row = store.session.get(RawDocumentRow, doc.id)
        if row is None:  # pragma: no cover - 방금 만든/찾은 행
            return doc
        old = row.meta if isinstance(row.meta, dict) and row.meta.get("kind") == OCR_META_KIND else None
        if old is not None and old.get("status") == "ok":
            return doc  # 같은 화면(재사용 행) — 다시 읽지 않는다
        engine = self._get_ocr()
        if engine is None:
            meta: dict[str, Any] = {
                "kind": OCR_META_KIND, "label": OCR_LABEL, "engine": None, "status": "unavailable",
                "reason": OCR_UNAVAILABLE, "items": [],
            }  # fmt: skip
        else:
            meta = self._ocr_items(store, target, shots, engine)
        if row.meta != meta:
            row.meta = meta
            store.session.flush()
        return doc.model_copy(update={"meta": meta})

    def _ocr_items(
        self, store: RawStore, target: SiteTarget, shots: Sequence[PopupShot], engine: PopupOcr
    ) -> dict[str, Any]:
        cache = _ocr_cache(store.session, target.url)
        items: list[dict[str, Any]] = []
        started = self._clock()
        for p in shots:
            hit = _cached_item(cache, p)
            if hit is not None:
                items.append({**hit, "selector": p.selector})
                continue
            if self._clock() - started > self._ocr_budget_s:
                items.append(
                    {"popup_sha256": p.sha256, "selector": p.selector, "status": "skipped",
                     "error": f"페이지 OCR 시간 예산 {self._ocr_budget_s:g}초 초과(D5)"}
                )  # fmt: skip
                continue
            items.append(self._ocr_one(store, p, engine))
        ok = sum(1 for it in items if it.get("status") == "ok")
        status = "ok" if ok == len(items) else ("partial" if ok else "error")
        return {
            "kind": OCR_META_KIND,
            "label": OCR_LABEL,
            "engine": _OCR_ENGINE,
            "status": status,
            "reason": None if status == "ok" else "일부 팝업 OCR 실패·생략" if ok else "팝업 OCR 실패",
            "items": items,
        }

    def _ocr_one(self, store: RawStore, p: PopupShot, engine: PopupOcr) -> dict[str, Any]:
        base: dict[str, Any] = {
            "popup_sha256": p.sha256,
            "signature": popup_signature(p),
            "dhash": p.dhash,
            "selector": p.selector,
        }
        t0 = self._clock()
        try:
            text = engine(p.png).strip()
        except Exception as exc:  # 그림을 못 읽음·엔진 오류 — 실패도 데이터(규칙 7)
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            return {**base, "status": "error", "error": first[:200]}
        when = now_kst()
        day = to_kst(when).date()
        image = store_raw(p.png, source="official_site", day=day, ext="png", raw_dir=store.raw_dir)
        stored = store_raw(
            text.encode("utf-8"), source="official_site", day=day, ext="txt", raw_dir=store.raw_dir
        )
        return {
            **base,
            "status": "ok",
            "image_path": image.relpath,
            "text_path": stored.relpath,
            "text_sha256": stored.sha256,
            "chars": len(text),
            "checked_at": iso_kst(when),
            "seconds": round(self._clock() - t0, 2),
        }

    @staticmethod
    def _screenshot(
        store: RawStore, region_id: int, target: SiteTarget, rendered: RenderResult
    ) -> tuple[RawDocument, str | None]:
        """렌더 PNG 행과 image_hash(모듈 설명 2): 같은 화면이면 직전 스크린샷 행 재사용."""
        signature = render_signature(rendered.dom_text, rendered.popups)
        prev = _previous_render(store.session, target)
        same = prev is not None and prev.get("signature") == signature
        changed_pixels = same and visual_change(prev.get("popups") or [] if prev else [], rendered.popups)
        if prev is not None and same and not changed_pixels:
            row = store.session.scalars(
                select(RawDocumentRow).where(RawDocumentRow.sha256 == prev.get("screenshot_sha256"))
            ).first()
            if row is not None:
                return _dto(row), row.image_hash
        image_hash = popup_hash(rendered.popups)
        if changed_pixels:
            dh = ",".join(sorted(p.dhash or p.sha256 for p in rendered.popups))
            image_hash = hashlib.sha256(f"{image_hash or ''}|{dh}".encode()).hexdigest()
        doc = store.save_content(
            source_kind="official_site",
            url=target.url,
            content=rendered.screenshot_png,
            ext="png",
            content_type="image/png",
            http_status=rendered.status,
            text=rendered.dom_text,
            region_id=region_id,
            complex_id=target.complex_id,
            image_hash=image_hash,
        )
        return doc, doc.image_hash

    @staticmethod
    def _attach_meta(store: RawStore, doc: RawDocument, meta: dict[str, Any]) -> RawDocument:
        """HTML 행의 meta 컬럼에 쓴다(같은 행이면 최신 관찰로 갱신). commit 은 세션 컨텍스트가 한다."""
        row = store.session.get(RawDocumentRow, doc.id)
        if row is None:  # pragma: no cover - save_content 가 방금 만든/찾은 행
            return doc
        if row.meta != meta:
            row.meta = meta
            store.session.flush()
        return doc.model_copy(update={"meta": meta})

    @staticmethod
    def _meta(
        target: SiteTarget,
        final_url: str | None,
        html_doc: RawDocument,
        dom_text: str,
        reason: str,
        rendered: RenderResult | None,
        image_hash: str | None,
        screenshot_sha256: str | None = None,
    ) -> dict[str, Any]:
        candidates = intake_candidates(dom_text, source="html")
        if rendered is not None and rendered.ok:
            seen = {str(c["text"]) for c in candidates}
            candidates += [
                c
                for c in intake_candidates(rendered.dom_text, source="rendered")
                if str(c["text"]) not in seen
            ]
        return {
            "kind": "official_site.meta",
            "url": target.url,
            "final_url": final_url,
            "complex_id": target.complex_id,
            "html_sha256": html_doc.sha256,
            "render": {
                "reason": reason,
                "rendered": bool(rendered is not None and rendered.ok),
                "error": rendered.error if rendered is not None else None,
                "screenshot_sha256": (
                    (screenshot_sha256 or hashlib.sha256(rendered.screenshot_png).hexdigest())
                    if rendered is not None and rendered.ok
                    else None
                ),
                "signature": (
                    render_signature(rendered.dom_text, rendered.popups)
                    if rendered is not None and rendered.ok
                    else None
                ),
                "popups": [p.as_meta() for p in rendered.popups] if rendered is not None else [],
            },
            "image_hash": image_hash,
            "intake_candidates": candidates,
        }


def _dto(row: RawDocumentRow) -> RawDocument:
    return RawDocument.model_validate({name: getattr(row, name) for name in RawDocument.model_fields})


def _previous_render(session: Session, target: SiteTarget) -> dict[str, Any] | None:
    """같은 URL 의 가장 최근 성공 렌더 메타(HTML 행 meta.render). 없으면 None.

    R4 M5: 단지(complex_id)로 거르지 않는다 — 같은 URL 은 같은 화면이고, 원문 행은 sha256 로 하나라 그 행의 complex_id 는
    첫 단지뿐이다(다른 단지는 직전 렌더를 못 찾아 매번 새 스크린샷 → 같은 날 재수집에서 팝업 해시가 바뀌었다)."""
    stmt = (
        select(RawDocumentRow)
        .where(
            RawDocumentRow.source_kind == "official_site",
            RawDocumentRow.url == target.url,
            RawDocumentRow.meta.is_not(None),
        )
        .order_by(RawDocumentRow.id.desc())
        .limit(20)
    )
    for row in session.scalars(stmt):
        render = (row.meta or {}).get("render") if isinstance(row.meta, dict) else None
        if isinstance(render, dict) and render.get("rendered") and render.get("signature"):
            return render
    return None


def _short(error: str | None) -> str | None:
    if not error:
        return None
    first = error.strip().splitlines()[0] if error.strip() else error
    return first.removeprefix("render: ").removeprefix("browser: ")[:200]


def _pace(http: HttpClient, url: str) -> None:
    """브라우저 요청 전 ``core.http`` 의 호스트별 속도 제한 예약을 같이 쓴다(httpx 요청과 같은 호스트 키·간격 — 규칙 18).
    예약 함수가 없는 가짜 클라이언트면 아무것도 하지 않는다."""
    reserve = getattr(http, "_reserve", None)
    if not callable(reserve):
        return
    try:
        u = httpx.URL(url)
    except (httpx.InvalidURL, ValueError):
        return
    wait = float(reserve(f"{u.host}:{u.port}" if u.port else u.host))
    if wait > 0:
        sleep = getattr(http, "_sleep", time.sleep)
        sleep(wait)


def _ocr_cache(session: Session, url: str) -> list[dict[str, Any]]:
    """같은 URL 의 이전 스크린샷 행 meta 의 성공 OCR 항목(최근 행부터)."""
    stmt = (
        select(RawDocumentRow)
        .where(
            RawDocumentRow.source_kind == "official_site",
            RawDocumentRow.url == url,
            RawDocumentRow.content_type.like("image/%"),
            RawDocumentRow.meta.is_not(None),
        )
        .order_by(RawDocumentRow.id.desc())
        .limit(30)
    )
    out: list[dict[str, Any]] = []
    for row in session.scalars(stmt):
        meta = row.meta if isinstance(row.meta, dict) else {}
        if meta.get("kind") != OCR_META_KIND:
            continue
        out += [it for it in meta.get("items") or [] if isinstance(it, dict) and it.get("status") == "ok"]
    return out


def _cached_item(cache: Sequence[dict[str, Any]], p: PopupShot) -> dict[str, Any] | None:
    """같은 그림(sha256)이거나 같은 서명 + dHash 거리 임계값 이내인 이전 OCR 항목(R3 M13 과 같은 '같은 그림' 기준)."""
    for it in cache:
        if it.get("popup_sha256") == p.sha256:
            return it
    sig = popup_signature(p)
    for it in cache:
        old = it.get("dhash")
        near = isinstance(old, str) and p.dhash is not None and hamming(old, p.dhash) <= DHASH_THRESHOLD
        if it.get("signature") == sig and near:
            return it
    return None
