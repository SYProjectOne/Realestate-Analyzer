"""R7-FIX — 인천 스냅샷 2(2026-10-14 collect.daily #3, R7-SITE 배포 뒤) 결함 재현.

TLS 브라우저 경로(D26-4)로 hillstate.co.kr 를 오늘 받았는데(원문 2313·2334 성공), 스냅샷 2 의 접수 표시 행은 어제 실패 원문
(1258·1303, 'TLS')을 가리켰다. 원인: ``collect`` 가 오늘 수집 행(``intake_rows`` — 성공 + 렌더 → 경로 ``headless_shot``)을 만든 뒤
``copy_intake`` 가 이전 스냅샷의 **다른 경로**(``official_popup``) 행 — 어제 실패 행 — 을 그대로 복사했고, 표시 행 규칙
(``pick_intake``: official_popup > headless_shot)이 그 낡은 실패 행을 골랐다. 같은 날 403 → 성공(단지 7·8·22·37)도 같은 결함.

둘째(같은 재생): 같은 스크린샷(바이트 동일 — 브랜드 공통 페이지)을 다른 URL 단지가 공유하면 원문 행은 sha256 로 하나라 그 행의
URL 은 먼저 받은 단지 것이다. 접수 행의 근거 주소·동일성 근거(HTML 제목)가 **다른 단지 URL** 의 페이지로 붙었다(단지 72·75·87 →
``/s/GI59``).

가짜 판정기는 응답 모양만 흉내 낸다(판단 아님).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.scope import pick_intake
from app.collectors.official_site import OfficialSiteCollector, RenderResult, SiteTarget
from app.collectors.official_site.render import BrowserFetch
from app.core.http import HttpClient
from app.models import IntakeStatus, RawDocument
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext
from app.scheduler.intake import UNCLASSIFIED, site_evidence
from app.scheduler.pipeline import run_pipeline

from .conftest import SynthJev
from .test_r7_site import RecordingJev

SITE = "https://brand.example.test/s/"
SITE_B = "https://brand.example.test/s/GI59"
ROBOTS = "https://brand.example.test/robots.txt"
A, B = 4, 5  # 픽스처 지역 단지 두 개(같은 공식 홈페이지 주소를 쓴다 — 인천 72·75·87)
SSL_ERR = "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1010)"
PAGE = "브랜드 공통 분양 안내\n분양안내\n잔여세대 선착순 동호지정 계약 진행중\n견본주택 오시는 길"


@pytest.fixture
def jev() -> SynthJev:
    return RecordingJev()


class BrowserRenderer:
    """TLS 브라우저 경로용 가짜 렌더러: robots.txt 허용, 본문 200 + 같은 스크린샷(브랜드 공통 화면)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch(self, url: str) -> BrowserFetch:
        self.calls.append(f"fetch {url}")
        return BrowserFetch(url=url, status=200, text="User-agent: *\nAllow: /\n")

    def render(self, url: str) -> RenderResult:
        self.calls.append(f"render {url}")
        title = "GI59 단지" if url == SITE_B else "브랜드 공통"
        return RenderResult(
            url=url, final_url=url, status=200, screenshot_png=b"\x89PNG-brand-common", dom_text=PAGE,
            html=f"<html><head><title>{title}</title></head><body><p>{PAGE}</p></body></html>",
        )  # fmt: skip


@contextmanager
def _tls_ctx(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    targets: list[SiteTarget],
    *,
    browser: bool,
) -> Iterator[SchedulerContext]:
    """httpx 는 robots.txt·본문 모두 TLS 실패. ``browser=False`` 면 R7-SITE 배포 전(실패 행 'TLS'), True 면 브라우저 경로."""
    http = HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0)

    def official(_ctx: SchedulerContext) -> OfficialSiteCollector:
        return OfficialSiteCollector(
            http=http, renderer=BrowserRenderer(), targets=targets, session_factory=factory, ocr=None,
            tls_browser=browser,
        )  # fmt: skip

    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).mock(side_effect=httpx.ConnectError(SSL_ERR))
        for t in {t.url for t in targets}:
            router.get(t).mock(side_effect=httpx.ConnectError(SSL_ERR))
        yield make_ctx(collectors={"official_site": official})
    http.close()


def _day(ctx: SchedulerContext, asof: str) -> int:
    res = collect(ctx, 1, ["official_site"], asof_date=asof)
    assert res.errors == {} and res.intake_rows == 2, res.stats()
    run_pipeline(ctx, res.snapshot_id)
    return res.snapshot_id


def _rows(factory: sessionmaker[Session], sid: int, cid: int) -> list[IntakeStatus]:
    with factory() as s:
        return list(
            s.scalars(
                select(IntakeStatus)
                .where(IntakeStatus.snapshot_id == sid, IntakeStatus.complex_id == cid)
                .order_by(IntakeStatus.id)
            )
        )


def test_shared_url_day1_tls_day2_browser_success_shows_today(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """두 단지가 같은 공식 홈페이지 주소. 1일차 TLS 실패(배포 전), 2일차 브라우저 경로 성공 → 2일차 두 단지의 표시 접수 행은
    2일차 성공 원문(스크린샷 행)이고 판정기로 분류된다. 어제 실패 행('TLS', 어제 원문)이 오늘 스냅샷에 남아 이기지 않는다."""
    targets = [SiteTarget(SITE, A), SiteTarget(SITE, B)]
    with _tls_ctx(make_ctx, factory, targets, browser=False) as ctx:
        day1 = _day(ctx, "2026-10-13")
    for cid in (A, B):
        shown = pick_intake(_rows(factory, day1, cid))
        assert shown is not None and (shown.path, shown.reason) == ("official_popup", "TLS")
    calls = len(jev.calls)
    with _tls_ctx(make_ctx, factory, targets, browser=True) as ctx:
        day2 = _day(ctx, "2026-10-14")
    assert len(jev.calls) > calls, "새로 받은 본문은 판정기로 간다"
    with factory() as s:
        shot = s.scalars(
            select(RawDocument).where(RawDocument.url == SITE, RawDocument.content_type == "image/png")
        ).one()
    for cid in (A, B):
        rows = _rows(factory, day2, cid)
        shown = pick_intake(rows)
        assert shown is not None
        assert (shown.path, shown.raw_document_id, shown.http_status) == ("headless_shot", shot.id, 200), [
            (r.path, r.reason, r.raw_document_id) for r in rows
        ]
        assert shown.reason not in ("TLS", UNCLASSIFIED) and "판정기 classify" in (shown.note or "")
        assert all(r.reason != "TLS" for r in rows), "어제 실패 행을 오늘 스냅샷에 복사하지 않는다"


def test_unchanged_next_day_after_recovery_copies_without_judge(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """회복 다음 날 같은 화면: 분류 복사(판정 호출 0, D10-2), 표시 행은 그대로 성공 행."""
    targets = [SiteTarget(SITE, A), SiteTarget(SITE, B)]
    with _tls_ctx(make_ctx, factory, targets, browser=False) as ctx:
        _day(ctx, "2026-10-13")
    with _tls_ctx(make_ctx, factory, targets, browser=True) as ctx:
        day2 = _day(ctx, "2026-10-14")
        calls = list(jev.calls)
        day3 = _day(ctx, "2026-10-15")
    assert "classify" not in [c.removeprefix("jev_") for c in jev.calls[len(calls) :]]
    for cid in (A, B):
        s2, s3 = pick_intake(_rows(factory, day2, cid)), pick_intake(_rows(factory, day3, cid))
        assert s2 is not None and s3 is not None
        assert (s3.path, s3.status, s3.reason, s3.raw_document_id) == (
            s2.path,
            s2.status,
            s2.reason,
            s2.raw_document_id,
        )
        assert "이전 분류 복사" in (s3.note or "")


def test_human_check_row_is_still_carried_over(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """오늘 수집 행이 있어도 사람 확인 행(human_check)은 다음 스냅샷으로 복사된다(수집 경로 행만 오늘 관측이 대신한다)."""
    targets = [SiteTarget(SITE, A), SiteTarget(SITE, B)]
    with _tls_ctx(make_ctx, factory, targets, browser=False) as ctx:
        day1 = _day(ctx, "2026-10-13")
    with factory() as s:
        s.add(
            IntakeStatus(
                complex_id=A, snapshot_id=day1, status="가능", path="human_check",
                checked_at="2026-10-13", reason=None, note="사람 확인", entered_by="tester",
            )
        )  # fmt: skip
        s.commit()
    with _tls_ctx(make_ctx, factory, targets, browser=True) as ctx:
        day2 = _day(ctx, "2026-10-14")
    shown = pick_intake(_rows(factory, day2, A))
    assert shown is not None and (shown.path, shown.status) == ("human_check", "가능")


def test_copy_intake_today_observation_replaces_yesterday_collected_rows(
    factory: sessionmaker[Session], seeded: int
) -> None:
    """``copy_intake`` 단위: 오늘 수집 관측 행(headless_shot + 원문)이 있는 단지는 어제 수집 관측 행(official_popup '403' + 원문 —
    인천 7·8·22·37)을 복사하지 않고 사람 확인·비공식 참고·원문 없는 적재 행은 복사한다. 오늘 수집 행이 없는 단지는 전부 복사."""
    from app.models import Snapshot
    from app.scheduler.persist import copy_intake

    def raw(s: Session, key: str, status: int | None) -> int:
        row = RawDocument(
            source_kind="official_site", url=f"https://cx.example.test/{key}", fetched_at="2026-10-07T03:00:00+09:00",
            http_status=status, sha256=key * 64, path=None, content_type=None, error_text=None if status == 200 else str(status),
        )  # fmt: skip
        s.add(row)
        s.flush()
        return row.id

    with factory() as s:
        yesterday = Snapshot(region_id=1, asof_date="2026-10-06", status="published", degraded=False, created_at="2026-10-06T06:00:00+09:00")  # fmt: skip
        dst = Snapshot(region_id=1, asof_date="2026-10-08", status="building", degraded=False, created_at="2026-10-08T06:00:00+09:00")  # fmt: skip
        s.add_all([yesterday, dst])
        s.flush()
        s.add_all(
            [
                IntakeStatus(complex_id=7, snapshot_id=yesterday.id, status="확인 불가", path="official_popup", checked_at="2026-10-06T03:00:00+09:00", reason="403", http_status=403, raw_document_id=raw(s, "a", 403)),
                IntakeStatus(complex_id=7, snapshot_id=yesterday.id, status="가능", path="human_check", checked_at="2026-10-06"),
                IntakeStatus(complex_id=7, snapshot_id=yesterday.id, status="미정", path="unofficial_ref", checked_at="2026-10-06"),
                IntakeStatus(complex_id=8, snapshot_id=yesterday.id, status="미정", path="official_popup", checked_at="2026-10-06"),  # 원문 없는 적재 행
                IntakeStatus(complex_id=9, snapshot_id=yesterday.id, status="확인 불가", path="official_popup", checked_at="2026-10-06T03:00:00+09:00", reason="TLS", raw_document_id=raw(s, "b", None)),
                IntakeStatus(complex_id=7, snapshot_id=dst.id, status="확인 불가", path="headless_shot", checked_at="2026-10-08T03:00:00+09:00", reason=UNCLASSIFIED, http_status=200, raw_document_id=raw(s, "c", 200)),
                IntakeStatus(complex_id=8, snapshot_id=dst.id, status="확인 불가", path="headless_shot", checked_at="2026-10-08T03:00:00+09:00", reason=UNCLASSIFIED, http_status=200, raw_document_id=raw(s, "d", 200)),
            ]
        )  # fmt: skip
        s.flush()
        copy_intake(s, yesterday.id, dst.id)
        s.commit()
        got = {
            (r.complex_id, r.path, r.reason)
            for r in s.scalars(select(IntakeStatus).where(IntakeStatus.snapshot_id == dst.id))
        }  # fmt: skip
    assert (7, "official_popup", "403") not in got, (
        "어제 '403' 행이 오늘 성공 행 옆에 복사되면 표시 행이 된다"
    )
    assert {(7, "human_check", None), (7, "unofficial_ref", None)} <= got
    assert (8, "official_popup", None) in got, "원문 없는 적재 행(수집 관측 아님)은 그대로"
    assert (9, "official_popup", "TLS") in got, "오늘 수집 행이 없는 단지는 그대로 복사"


def test_identical_screenshot_on_other_url_keeps_own_evidence(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """다른 주소 두 단지(브랜드 공통 화면 — 스크린샷 바이트 동일): 스크린샷 원문 행은 하나(sha256)라 그 URL 은 먼저 받은 단지 것.
    접수 행의 근거 주소·동일성 근거(HTML 제목)는 **자기 주소** 페이지여야 한다(인천 72·75·87 이 ``/s/GI59`` 근거를 받았다)."""
    targets = [SiteTarget(SITE_B, A), SiteTarget(SITE, B)]
    with _tls_ctx(make_ctx, factory, targets, browser=True) as ctx:
        day = _day(ctx, "2026-10-14")
    with factory() as s:
        for cid, url, title in ((A, SITE_B, "GI59 단지"), (B, SITE, "브랜드 공통")):
            [row] = [r for r in _rows(factory, day, cid) if r.path == "headless_shot"]
            assert row.evidence_url == url
            ev = site_evidence(s, s.get(IntakeStatus, row.id))  # type: ignore[arg-type]
            assert (ev.url, ev.title) == (url, title)
