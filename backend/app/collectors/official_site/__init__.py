"""단지 공식 홈페이지 수집기: httpx → (동적·팝업이면) Playwright 렌더 → 스크린샷·DOM 텍스트·팝업 해시."""

from app.collectors.official_site.collector import (
    META_CONTENT_TYPE,
    OfficialSiteCollector,
    SiteOutcome,
    SiteTarget,
    read_site_meta,
)
from app.collectors.official_site.render import (
    DHASH_THRESHOLD,
    PlaywrightRenderer,
    PopupShot,
    Renderer,
    RenderResult,
    popup_hash,
    render_signature,
    visual_change,
)

__all__ = [
    "DHASH_THRESHOLD",
    "META_CONTENT_TYPE",
    "OfficialSiteCollector",
    "PlaywrightRenderer",
    "PopupShot",
    "RenderResult",
    "Renderer",
    "SiteOutcome",
    "SiteTarget",
    "popup_hash",
    "read_site_meta",
    "render_signature",
    "visual_change",
]
