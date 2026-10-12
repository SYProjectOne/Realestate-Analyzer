"""R4-FIX M5 (D18-6) — 같은 공식 홈페이지 URL 을 쓰는 단지 여럿.

R4: 원문 저장은 sha256 로 중복을 없애 첫 단지의 complex_id 를 돌려줬고(접수 행이 첫 단지에만), 직전 렌더 메타는 원문 행의
complex_id(첫 단지)로만 찾아 다른 단지는 매번 새 스크린샷 → 같은 날 다시 수집에서 접수 행·팝업 해시가 바뀌었다(M5).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from itertools import count

import respx
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.official_site import OfficialSiteCollector, PopupShot, RenderResult, SiteTarget
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.models import Complex, RawDocument

SITE = "https://site.example.test/"
ROBOTS = "https://site.example.test/robots.txt"
BODY = "<html><body><div id='layer_popup'>잔여 세대 선착순 계약</div><script>x</script></body></html>"


class DynamicRenderer:
    """같은 화면(문구·팝업)인데 스크린샷 바이트는 매번 다르다(시계·배너 회전 — 실사이트 모양)."""

    def __init__(self) -> None:
        self.n = count()
        self.calls: list[str] = []

    def render(self, url: str) -> RenderResult:
        self.calls.append(url)
        return RenderResult(
            url=url, final_url=url, status=200, screenshot_png=b"\x89PNG\r\n\x1a\n" + str(next(self.n)).encode(),
            dom_text="잔여 세대 선착순 동호지정 계약 중",
            popups=(PopupShot(selector="#layer_popup", sha256="a" * 64, width=300, height=200),),
        )  # fmt: skip


def _png_count(engine: Engine) -> int:
    with Session(engine) as s:
        return int(
            s.scalar(
                select(func.count()).select_from(RawDocument).where(RawDocument.content_type == "image/png")
            )
            or 0
        )


def test_shared_url_documents_belong_to_each_target_and_reuse_screenshot(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    region, snapshot = region_ctx
    with Session(db_engine) as s:
        s.add(Complex(id=5, region_id=1, name="같은 사업 다른 블록", former_names=[], apply_dates=[], contract_dates=[],
                      official_site_url=SITE))  # fmt: skip
        s.commit()
    targets = [SiteTarget(SITE, 4), SiteTarget(SITE, 5)]
    renderer = DynamicRenderer()
    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(404)
        router.get(SITE).respond(200, text=BODY, headers={"content-type": "text/html"})
        first = OfficialSiteCollector(http=http, renderer=renderer, render="always", targets=targets).fetch(
            region, snapshot, None
        )
        pngs = _png_count(db_engine)
        second = OfficialSiteCollector(http=http, renderer=renderer, render="always", targets=targets).fetch(
            region, snapshot, None
        )
    assert {d.complex_id for d in first} == {4, 5}, "공유 원문도 대상 단지마다 돌려준다(접수 행이 단지마다)"
    assert {d.complex_id for d in second} == {4, 5}
    assert _png_count(db_engine) == pngs, "같은 화면이면 같은 URL 의 직전 스크린샷을 재사용(단지와 무관)"
    by_target = {(d.complex_id, d.content_type): d.sha256 for d in second}
    assert by_target[(4, "image/png")] == by_target[(5, "image/png")]
