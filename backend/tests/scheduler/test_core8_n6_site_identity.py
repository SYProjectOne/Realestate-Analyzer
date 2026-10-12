"""R4 재시험 N6(major, D21-5) — 공식 홈페이지 문구를 접수 판정 입력으로 쓰기 전에 그 페이지가 **그 단지의 페이지인지** 판정기에 묻는다.

R4: 2021 공고 단지 '검단신도시 AB3-2블록 예미지 퍼스트포레'(55)의 청약홈 등록 홈페이지 ``yemizi-firstforet.com`` 이 지금은 대구
'더샵 동성로 센트리엘' 분양 페이지다(본문에 예미지·퍼스트포레 0회, 동성로 9회). 확인 없이 그 문구('일부세대 선착순 분양중')를
접수 classify 에 넣어 '가능' → 판정 대상(noul 3 · decide 후보 · rerank 2위).

D21-5: 판정기 classify(공식 홈페이지 동일성 — 단지 이름·위치 + 페이지 문구)가 auto 'same_complex' 일 때만 접수 classify 로
간다. 아니거나 review 면 접수 근거로 쓰지 않고 '확인 불가(공식 홈페이지가 다른 단지)'. 판단은 판정기만(규칙 3) — 이 테스트의
가짜 판정기가 '다른 단지'라고 답하는 것은 판정기 응답 모양을 흉내 낼 뿐이다.
"""

# ruff: noqa: E501  (한국어 docstring·녹화 문구)

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors.official_site import OfficialSiteCollector, PopupShot, RenderResult, SiteTarget
from app.core.http import HttpClient
from app.models import Complex, IntakeStatus, JudgmentLog
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext
from app.scheduler.pipeline import run_pipeline

from .conftest import REPO, SynthJev

WP1B_FIXTURES = REPO / "backend" / "tests" / "collectors" / "official_site" / "fixtures"
SITE = "https://site.example.test/"
ROBOTS = "https://site.example.test/robots.txt"
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes"
CX = 4
# R4 재시험 원문(raw_document 842, 공개 분양 페이지) 렌더 DOM 텍스트 앞부분 — 다른 단지(대구) 분양 페이지
OTHER_SITE_TEXT = "\n".join(
    [
        "더샵 동성로 센트리엘", "방문예약", "사업안내", "프리미엄", "단지안내",
        "더샵 동성로 센트리엘 모델하우스", "따라올 수 없는, 초중심의 미래가치를 더 높게 누리다", "일부세대 선착순 분양중",
        "놀라운 비전으로 대구의 초중심", "그곳에 포스코더샵이 찾아옵니다", "잔여세대 계약중",
    ]
)  # fmt: skip
SITE_OTHER = "공식 홈페이지가 다른 단지"


class IdentityJev(SynthJev):
    """공식 홈페이지 동일성 classify 에 정해진 답(다른 단지·review)을 주는 가짜 판정기. 나머지는 SynthJev."""

    def __init__(self, *, identity: str, decision: str = "auto") -> None:
        super().__init__()
        self.identity = identity
        self.identity_decision = decision
        self.identity_calls: list[dict[str, Any]] = []

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        ids = [c["id"] for c in a["classes"]]
        if "same_complex" not in ids:
            return super()._classify(a)
        self.identity_calls.append(a)
        return {
            "results": [
                {"id": it["id"], "classification": self.identity, "probabilities": {self.identity: 0.9},
                 "top_probability": 0.9, "confidence": 0.9, "decision": self.identity_decision}
                for it in a["items"]
            ]
        }  # fmt: skip


class OtherSiteRenderer:
    def render(self, url: str) -> RenderResult:
        return RenderResult(
            url=url, final_url=url, status=200, screenshot_png=PNG, dom_text=OTHER_SITE_TEXT,
            popups=(PopupShot(selector="#layer_popup", sha256="b" * 64, width=300, height=200),),
        )  # fmt: skip


@pytest.fixture
def jev() -> SynthJev:  # conftest 의 jev 를 덮는다(make_ctx 가 이 판정기를 쓴다)
    return IdentityJev(identity="other_complex")


@pytest.fixture
def other_site_ctx(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session]
) -> Iterator[SchedulerContext]:
    http = HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0)

    def official(_ctx: SchedulerContext) -> OfficialSiteCollector:
        return OfficialSiteCollector(
            http=http, renderer=OtherSiteRenderer(), targets=[SiteTarget(SITE, CX)], session_factory=factory
        )

    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(200, content=(WP1B_FIXTURES / "hndapt_robots.txt").read_bytes())
        router.get(SITE).respond(
            200,
            content=OTHER_SITE_TEXT.encode("utf-8"),
            headers={"content-type": "text/plain; charset=utf-8"},
        )
        yield make_ctx(collectors={"official_site": official})
    http.close()


def _row(factory: sessionmaker[Session], sid: int) -> IntakeStatus:
    with factory() as s:
        return s.scalars(
            select(IntakeStatus).where(
                IntakeStatus.snapshot_id == sid,
                IntakeStatus.complex_id == CX,
                IntakeStatus.path == "headless_shot",
            )
        ).one()


def _run(ctx: SchedulerContext) -> int:
    res = collect(ctx, 1, ["official_site"])
    assert res.errors == {} and res.intake_rows == 1, res.stats()
    run_pipeline(ctx, res.snapshot_id)
    return res.snapshot_id


def test_other_complex_site_is_not_intake_evidence(
    other_site_ctx: SchedulerContext, factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    assert isinstance(jev, IdentityJev)
    sid = _run(other_site_ctx)
    row = _row(factory, sid)
    assert (row.status, row.reason) == ("확인 불가", SITE_OTHER), (row.status, row.reason)
    with factory() as s:
        name = s.get(Complex, CX).name  # type: ignore[union-attr]
        logs = list(
            s.scalars(select(JudgmentLog).where(JudgmentLog.purpose.startswith("classify:site_identity")))
        )
        assert logs and logs[0].status == "ok"
        text = logs[0].input_json["items"][0]["text"]
        assert name in text and "동성로" in text, "판정기 입력 = 단지 이름·위치 + 페이지 문구"
        assert row.note and f"jl_{logs[0].seq}" in row.note
        intake_calls = list(
            s.scalars(select(JudgmentLog).where(JudgmentLog.purpose.startswith("classify:intake")))
        )
        assert intake_calls == [], "다른 단지 페이지 문구는 접수 classify 입력이 아니다"


def test_review_identity_is_also_not_evidence(
    other_site_ctx: SchedulerContext, factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    assert isinstance(jev, IdentityJev)
    jev.identity, jev.identity_decision = "same_complex", "review"
    sid = _run(other_site_ctx)
    # D22-4(R4 3차 N11): 접수 근거로 쓰지 않는 것은 같고, 사유는 '다른 단지'가 아니라 '동일성 미확인'
    assert (_row(factory, sid).status, _row(factory, sid).reason) == (
        "확인 불가",
        "공식 홈페이지 동일성 미확인",
    )


def test_same_complex_site_goes_to_intake_classify(
    other_site_ctx: SchedulerContext, factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    assert isinstance(jev, IdentityJev)
    jev.identity = "same_complex"
    sid = _run(other_site_ctx)
    row = _row(factory, sid)
    assert row.status == "가능", (row.status, row.reason)  # 동일성 auto 통과 → 접수 classify(SynthJev 'open')
    assert len(jev.identity_calls) == 1
