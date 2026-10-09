"""단지 공식 홈페이지 수집기 (source_kind='official_site', RA §5 WP1 · T3).

단지 1개당 남는 raw_document
1. httpx(core.http) 응답: 성공이면 HTML(text_path = DOM 텍스트), 실패면 실패 행 — 403 은 http_status=403,
   DNS·TLS·timeout 은 http_status=None + error_text. 실패하면 렌더하지 않는다(접근 거부를 우회하지 않음).
2. 렌더(동적·팝업 표식이 있거나 render='always'): 전체 화면 PNG(text_path = 렌더 후 DOM 텍스트,
   image_hash = 팝업 해시). 렌더 실패는 실패 행(error_text='render: …').
메타(계약 2026-10-09.2 ``raw_document.meta``): 1번 HTML 행의 meta 컬럼에 둔다(별도 행 없음).
   키 = {kind, url, final_url, complex_id, html_sha256, render{reason, rendered, error, screenshot_sha256,
   popups[]}, image_hash, intake_candidates[{text, keywords, source}]}. 시각을 넣지 않는다.
   같은 HTML(같은 행)을 다시 수집하면 meta 는 최신 관찰(렌더 결과)로 바뀐다 — 렌더 이력은 스크린샷 행
   (image_hash)마다 남는다.
   상태 판단은 하지 않는다(WP2·판정기).
   2026-10-09.1 까지는 메타가 별도 JSON 행(content_type ``META_CONTENT_TYPE``)이었다 — ``read_site_meta`` 가
   두 모양을 다 읽는다(호환).

대상: ``targets`` 를 주면 그것만, 아니면 region 의 complex.official_site_url 전부.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.official_site.extract import html_to_text, intake_candidates, needs_render
from app.collectors.official_site.render import PlaywrightRenderer, Renderer, RenderResult, popup_hash
from app.collectors.reference.rawstore import Failure, RawStore, fetch_failure
from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.db import get_session
from app.core.http import HttpClient
from app.core.paths import resolve_raw_path
from app.models import Complex
from app.models import RawDocument as RawDocumentRow

__all__ = ["META_CONTENT_TYPE", "OfficialSiteCollector", "SiteOutcome", "SiteTarget", "read_site_meta"]

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
    ) -> None:
        self._http = http
        self._renderer = renderer
        self._render_mode: RenderMode = render
        self._targets = list(targets) if targets is not None else None
        self._session_factory = session_factory
        self._raw_dir = raw_dir
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
        return [d for o in self.outcomes for d in o.documents]

    def _renderer_or_default(self) -> Renderer:
        if self._renderer is None:
            self._renderer = PlaywrightRenderer()
        return self._renderer

    def _one(self, http: HttpClient, store: RawStore, region_id: int, target: SiteTarget) -> SiteOutcome:
        out = SiteOutcome(target)
        r = http.get(target.url)
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
                out.image_hash = popup_hash(rendered.popups)
                out.documents.append(
                    store.save_content(
                        source_kind="official_site",
                        url=target.url,
                        content=rendered.screenshot_png,
                        ext="png",
                        content_type="image/png",
                        http_status=rendered.status,
                        text=rendered.dom_text,
                        region_id=region_id,
                        complex_id=target.complex_id,
                        image_hash=out.image_hash,
                    )
                )
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
        out.meta = self._meta(target, r.final_url, html_doc, dom_text, reason, rendered, out.image_hash)
        out.documents[0] = self._attach_meta(store, html_doc, out.meta)
        return out

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
                    hashlib.sha256(rendered.screenshot_png).hexdigest()
                    if rendered is not None and rendered.ok
                    else None
                ),
                "popups": [p.as_meta() for p in rendered.popups] if rendered is not None else [],
            },
            "image_hash": image_hash,
            "intake_candidates": candidates,
        }
