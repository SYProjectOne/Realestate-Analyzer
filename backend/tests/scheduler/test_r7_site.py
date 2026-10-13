"""R7-SITE — 인천 첫 실운영 후속(DECISIONS D26-1·D26-3): 팝업 그림 OCR 을 접수 classify 입력에, 판정 대상이 아닌 단지는 접수 판정에서 뺀다.

- D26-1: 인천 첫 실행 '문구로 판단 불가' 29행의 주원인 — 접수 안내가 팝업 **그림** 안에 있어 DOM 문구가 없다(R6_TESTS_INTAKE §1).
  수집기가 팝업 요소 그림을 OCR(D5 RapidOCR 재사용)해 스크린샷 행 meta 에 남기고(라벨 '추정(OCR)'), 접수 항목이 그 글자를 싣는다.
  분류는 판정기만(규칙 3). 같은 그림이면 다시 읽지 않고 입력도 그대로 → 변경 없는 날 판정 호출 0(D10-2·D22-2).
- D26-3: 범위 경계·민간분양 아닌 단지(LH 청약 포털 5행 등)는 공식 홈페이지 동일성·접수 classify 대상에서 뺀다. 행은 남고 사유는
  '판정 대상 아님(<구분>)'. 첫 실행에도 빠지도록 포함/제외 classify 가 접수 classify 보다 먼저 돈다.

이 테스트의 가짜 판정기·가짜 OCR 은 응답 모양만 흉내 낸다(판단 아님).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors.official_site import OfficialSiteCollector, PopupShot, RenderResult, SiteTarget
from app.core.http import HttpClient
from app.models import Complex, IntakeStatus
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext
from app.scheduler.pipeline import run_pipeline

from .conftest import REPO, SynthJev

WP1B_FIXTURES = REPO / "backend" / "tests" / "collectors" / "official_site" / "fixtures"
SITE = "https://site.example.test/"
ROBOTS = "https://site.example.test/robots.txt"
CX = 4
PAGE_TEXT = (
    "검단 테스트 단지\n사업개요\n입지환경\n오시는 길\n사이버 견본주택"  # 접수 문구 없음(안내가 팝업 그림 안)
)
OCR_TEXT = "검단 테스트 단지\n잔여세대 선착순 동호지정 계약 진행중\n견본주택 방문 상담 가능"


class RecordingJev(SynthJev):
    """동일성 classify 는 auto same_complex, 접수 classify 는 SynthJev(open). 포함/제외는 ``inclusion`` 이 정한다.
    보낸 항목을 도구별로 기록."""

    def __init__(self) -> None:
        super().__init__()
        self.inclusion: dict[str, str] = {}
        self.site_items: list[dict[str, str]] = []
        self.intake_items: list[dict[str, str]] = []

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        ids = [c["id"] for c in a["classes"]]
        if "open" in ids:
            self.intake_items.extend(a["items"])
            return super()._classify(a)
        if "same_complex" in ids:
            self.site_items.extend(a["items"])
            return {
                "results": [
                    {"id": it["id"], "classification": "same_complex", "probabilities": {"same_complex": 0.95},
                     "top_probability": 0.95, "confidence": 0.95, "decision": "auto"}
                    for it in a["items"]
                ]
            }  # fmt: skip
        out = super()._classify(a)
        if "public_sale" in ids:
            for r in out["results"]:
                label = self.inclusion.get(r["id"])
                if label is not None:
                    r.update(classification=label, probabilities={label: 0.96})
        return out


@pytest.fixture
def jev() -> SynthJev:
    return RecordingJev()


class FakeOcr:
    def __init__(self, text: str = OCR_TEXT) -> None:
        self.text = text
        self.calls: list[bytes] = []

    def __call__(self, png: bytes) -> str:
        self.calls.append(png)
        return self.text


def _site_ctx(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    ocr: FakeOcr,
    *,
    popup_png: bytes = b"popup-image-1",
) -> Iterator[SchedulerContext]:
    http = HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0)

    class Renderer:
        def render(self, url: str) -> RenderResult:
            return RenderResult(
                url=url, final_url=url, status=200, screenshot_png=b"\x89PNG-full-1", dom_text=PAGE_TEXT,
                popups=(PopupShot(selector="#popup-wrap", sha256="d" * 64, width=800, height=600,
                                  images=("https://site.example.test/img/pop1.jpg",), png=popup_png),),
            )  # fmt: skip

    def official(_ctx: SchedulerContext) -> OfficialSiteCollector:
        return OfficialSiteCollector(
            http=http, renderer=Renderer(), targets=[SiteTarget(SITE, CX)], session_factory=factory, ocr=ocr
        )

    html = "<html><head><title>검단 테스트 단지</title></head><body><div id='app'></div><div class='popup'></div></body></html>"
    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(200, content=(WP1B_FIXTURES / "hndapt_robots.txt").read_bytes())
        router.get(SITE).respond(
            200, content=html.encode("utf-8"), headers={"content-type": "text/html; charset=utf-8"}
        )
        yield make_ctx(collectors={"official_site": official})
    http.close()


def _run(ctx: SchedulerContext, asof: str | None = None) -> int:
    res = collect(ctx, 1, ["official_site"], asof_date=asof)
    assert res.errors == {} and res.intake_rows == 1, res.stats()
    run_pipeline(ctx, res.snapshot_id)
    return res.snapshot_id


def _row(factory: sessionmaker[Session], sid: int) -> IntakeStatus:
    with factory() as s:
        return s.scalars(
            select(IntakeStatus).where(
                IntakeStatus.snapshot_id == sid,
                IntakeStatus.complex_id == CX,
                IntakeStatus.path == "headless_shot",
            )
        ).one()


def _mine(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return [it for it in items if it["id"].endswith(f":c{CX}:headless_shot")]


# ---------------------------------------------------------------- D26-1 팝업 그림 OCR → 접수 classify 입력


def test_intake_item_carries_popup_ocr_text_with_label(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """DOM 에 접수 문구가 없고 팝업 그림에만 있다(인천 첫 실행 '문구로 판단 불가' 주원인). 접수 항목에 OCR 글자가 '추정(OCR)' 머리와
    함께 들어가고, 분류는 판정기 결과(가짜 open)다. 행 note 에 근거가 OCR 이었다는 표식."""
    assert isinstance(jev, RecordingJev)
    ocr = FakeOcr()
    for ctx in _site_ctx(make_ctx, factory, ocr):
        sid = _run(ctx)
    (item,) = _mine(jev.intake_items)
    assert "[팝업 그림 글자 — 추정(OCR)]" in item["text"]
    assert "잔여세대 선착순 동호지정 계약 진행중" in item["text"]
    assert item["text"].startswith("단지: ")
    row = _row(factory, sid)
    assert (row.status, row.reason) != ("확인 불가", "접수 문구 없음")
    assert row.status == "가능", "판정기(가짜 open auto) 결과"
    assert "추정(OCR)" in (row.note or "")
    assert ocr.calls == [b"popup-image-1"]


def test_unchanged_popup_is_not_reocred_and_not_rejudged_next_day(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """다음 날 같은 화면·같은 팝업 그림: OCR 다시 안 함, 접수 입력 그대로 → 분류 복사(판정 호출 0, D10-2·D22-2)."""
    assert isinstance(jev, RecordingJev)
    ocr = FakeOcr()
    for ctx in _site_ctx(make_ctx, factory, ocr):
        sid1 = _run(ctx, "2026-10-08")
        n_site, n_intake, n_calls = len(jev.site_items), len(jev.intake_items), len(jev.calls)
        sid2 = _run(ctx, "2026-10-09")
    assert sid2 != sid1
    assert len(ocr.calls) == 1, "같은 그림은 다시 읽지 않는다(그림 해시 캐시)"
    assert (len(jev.site_items), len(jev.intake_items)) == (n_site, n_intake), (
        "같은 입력이면 다시 묻지 않는다"
    )
    assert "classify" not in [c.removeprefix("jev_") for c in jev.calls[n_calls:]]
    assert (_row(factory, sid2).status, _row(factory, sid2).reason) == (
        _row(factory, sid1).status,
        _row(factory, sid1).reason,
    )


# ---------------------------------------------------------------- D26-3 판정 대상 아닌 단지


def test_boundary_complex_skips_identity_and_intake_classify(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """범위 경계 단지(주소 매칭 — 점수 대상 아님): 동일성·접수 classify 에 보내지 않고 사유 '판정 대상 아님(범위 경계)'. 행은 남는다."""
    assert isinstance(jev, RecordingJev)
    with factory() as s:
        cx = s.get(Complex, CX)
        assert cx is not None
        cx.inclusion_class = "범위 경계"
        s.commit()
    for ctx in _site_ctx(make_ctx, factory, FakeOcr()):
        sid = _run(ctx)
    assert _mine(jev.site_items) == [] and _mine(jev.intake_items) == []
    row = _row(factory, sid)
    assert (row.status, row.reason) == ("확인 불가", "판정 대상 아님(범위 경계)")
    assert row.raw_document_id is not None and row.evidence_url == SITE, (
        "원문·근거는 그대로(목록·상세에 보인다)"
    )


def test_public_sale_complex_skips_classify_from_first_run(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """공공분양(포함/제외 classify auto public_sale): 첫 실행(분류 전 단지)에도 접수 판정에서 빠진다 — 포함/제외가 먼저 돈다."""
    assert isinstance(jev, RecordingJev)
    jev.inclusion[f"complex:{CX}"] = "public_sale"
    for ctx in _site_ctx(make_ctx, factory, FakeOcr()):
        sid = _run(ctx)
    with factory() as s:
        cx = s.get(Complex, CX)
        assert cx is not None and (cx.inclusion_class, cx.inclusion_decision) == ("public_sale", "auto")
    assert _mine(jev.site_items) == [] and _mine(jev.intake_items) == []
    assert (_row(factory, sid).status, _row(factory, sid).reason) == ("확인 불가", "판정 대상 아님(공공분양)")


def test_private_complex_still_classified(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """민간분양(또는 미해결) 단지는 그대로 동일성·접수 classify 를 거친다(회귀 방지)."""
    assert isinstance(jev, RecordingJev)
    for ctx in _site_ctx(make_ctx, factory, FakeOcr()):
        _run(ctx)
    assert len(_mine(jev.site_items)) == 1 and len(_mine(jev.intake_items)) == 1


def test_not_target_row_returns_to_unclassified_when_complex_becomes_target(
    factory: sessionmaker[Session], seeded: int
) -> None:
    """같은 스냅샷에서 범위 경계가 풀리면(법정동 보정) '판정 대상 아님' 행은 미분류로 돌아가 판정기로 간다."""
    from app.scheduler.intake import UNCLASSIFIED, mark_not_target

    with factory() as s:
        cx = s.get(Complex, CX)
        assert cx is not None
        cx.inclusion_class = "범위 경계"
        row = IntakeStatus(
            complex_id=CX, snapshot_id=seeded, status="확인 불가", path="headless_shot", evidence_url=SITE,
            checked_at="2026-10-07T06:00:00+09:00", reason=UNCLASSIFIED,
        )  # fmt: skip
        s.add(row)
        s.flush()
        assert mark_not_target(s, seeded) == [row.id]
        assert row.reason == "판정 대상 아님(범위 경계)"
        cx.inclusion_class = "미분류"
        assert mark_not_target(s, seeded) == [row.id]
        assert (row.status, row.reason) == ("확인 불가", UNCLASSIFIED)
        assert mark_not_target(s, seeded) == []
