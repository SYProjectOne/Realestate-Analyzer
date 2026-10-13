"""R6-INTAKE — 접수 상태 입력(공식 홈페이지 동일성·접수 classify)과 분류 복사의 입력 비교.

운영자 첫 인천 실행(운영 DB 스냅샷 1): 접수 행 96 → 확인 불가 89. 원인(수집 실패 25 제외):
- 동일성(D21-5) same_complex·review 11: 판정기 입력에 홈페이지 주소·HTML 제목·설명·시공·시행·세대수가 없고 페이지 문구는 앞 1500자
  (메뉴·되풀이 배너)라 꼬리말의 현장 주소·시행사가 잘렸다.
- 접수 classify 확인 불가 36: 입력이 후보 줄 하나('마감재리스트' 9행 — 파서 거짓 후보, '분양중공사중'·'무순위 모집공고' 같은
  조각)이거나 메뉴 앞부분이었다. 단지 이름도 없었다(여러 단지를 나열한 브랜드 페이지에서 어느 단지 문구인지 모름).
- 입력을 고쳐도 같은 원문이면 이전 분류(review 포함)를 그대로 복사했다 — 입력 조립이 바뀌어도 다시 묻지 않았다(D22-2 위반 꼴).

판단은 판정기만(규칙 3). 이 테스트의 가짜 판정기는 판정기 응답 모양을 흉내 내고, 보낸 항목 텍스트를 기록한다.
고정 문구 = 인천 첫 실행 공개 분양 페이지(``fixtures/r6_intake_incheon_pages.json``, 전화번호 가림).
"""

# ruff: noqa: E501  (한국어 docstring·녹화 문구)

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.collectors.official_site import OfficialSiteCollector, PopupShot, RenderResult, SiteTarget
from app.core.http import HttpClient
from app.models import Complex, IntakeStatus, JudgmentLog
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext
from app.scheduler.pipeline import SITE_UNCONFIRMED, run_pipeline

from .conftest import REPO, SynthJev

PAGES = json.loads(
    (Path(__file__).parent / "fixtures" / "r6_intake_incheon_pages.json").read_text(encoding="utf-8")
)
WP1B_FIXTURES = REPO / "backend" / "tests" / "collectors" / "official_site" / "fixtures"
SITE = "https://site.example.test/"
ROBOTS = "https://site.example.test/robots.txt"
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes"
CX = 4


def page(name: str) -> dict[str, Any]:
    return next(c for c in PAGES["complexes"] if c["name"] == name)


class RecordingJev(SynthJev):
    """동일성 classify 에 정해진 답, 접수 classify 는 SynthJev(open). 보낸 항목 텍스트를 도구별로 기록."""

    def __init__(self) -> None:
        super().__init__()
        self.identity = "same_complex"
        self.identity_decision = "auto"
        self.site_items: list[dict[str, str]] = []
        self.intake_items: list[dict[str, str]] = []

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        ids = [c["id"] for c in a["classes"]]
        if "open" in ids:
            self.intake_items.extend(a["items"])
            return super()._classify(a)
        if "same_complex" not in ids:
            return super()._classify(a)
        self.site_items.extend(a["items"])
        return {
            "results": [
                {"id": it["id"], "classification": self.identity, "probabilities": {self.identity: 0.9},
                 "top_probability": 0.9, "confidence": 0.9, "decision": self.identity_decision}
                for it in a["items"]
            ]
        }  # fmt: skip


@pytest.fixture
def jev() -> SynthJev:
    return RecordingJev()


def _site_ctx(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], pg: dict[str, Any]
) -> Iterator[SchedulerContext]:
    """그 페이지(HTML 머리 + 렌더 DOM 문구)를 내는 공식 홈페이지 수집기 + 단지 CX 의 사실을 그 단지로 맞춘다."""
    with factory() as s:
        cx = s.get(Complex, CX)
        assert cx is not None
        cx.name, cx.address = pg["name"], pg["address"]
        cx.builder, cx.developer, cx.units_total = pg["builder"], pg["developer"], pg["units_total"]
        s.commit()
    http = HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0)
    rendered = str(pg["rendered_text"])

    class Renderer:
        def render(self, url: str) -> RenderResult:
            return RenderResult(
                url=url, final_url=url, status=200, screenshot_png=PNG, dom_text=rendered,
                popups=(PopupShot(selector="#layer_popup", sha256="c" * 64, width=300, height=200),),
            )  # fmt: skip

    def official(_ctx: SchedulerContext) -> OfficialSiteCollector:
        return OfficialSiteCollector(
            http=http, renderer=Renderer(), targets=[SiteTarget(SITE, CX)], session_factory=factory
        )

    html = f"<html><head>{pg['head_html']}</head><body><div id='app'></div><div class='popup'>팝업</div></body></html>"
    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(200, content=(WP1B_FIXTURES / "hndapt_robots.txt").read_bytes())
        router.get(SITE).respond(
            200, content=html.encode("utf-8"), headers={"content-type": "text/html; charset=utf-8"}
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


def _run(ctx: SchedulerContext, asof: str | None = None) -> int:
    res = collect(ctx, 1, ["official_site"], asof_date=asof)
    assert res.errors == {} and res.intake_rows == 1, res.stats()
    run_pipeline(ctx, res.snapshot_id)
    return res.snapshot_id


def _item(items: list[dict[str, str]], prefix: str) -> str:
    return next(it["text"] for it in items if it["id"] == f"{prefix}:c{CX}:headless_shot")


# ---------------------------------------------------------------- 동일성 근거


def test_identity_item_has_url_title_builder_and_footer(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """포레나더샵 인천시청역(인천 첫 실행 same_complex·review 0.50): 근거(주소·제목·시공·시행·꼬리말 현장 주소)가 항목에 있다."""
    assert isinstance(jev, RecordingJev)
    for ctx in _site_ctx(make_ctx, factory, page("포레나더샵 인천시청역")):
        _run(ctx)
    text = _item(jev.site_items, "site")
    for want in (
        "단지: 포레나더샵 인천시청역",
        "시공: (주)한화 건설부문, (주)포스코이앤씨",
        "시행: 상인천초교주변주택재개발정비사업조합",
        "홈페이지 주소: https://site.example.test/",
        "페이지 제목: 포레나더샵 인천시청역",
        "인천광역시 남동구 간석1동 311-1일원",  # 꼬리말(예전 앞 1500자 밖)
    ):
        assert want in text, want
    assert text.count("다채로운 생활 중심 인프라") == 1, "되풀이 배너 줄은 한 번만"


def test_identity_item_uses_title_when_body_lacks_name(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """중앙하이츠 갈산역 센트럴(review 0.76): 렌더 문구 184자에 단지 이름이 없고 HTML 제목·설명에만 있다."""
    assert isinstance(jev, RecordingJev)
    pg = page("중앙하이츠 갈산역 센트럴")
    assert pg["name"] not in pg["rendered_text"]
    for ctx in _site_ctx(make_ctx, factory, pg):
        _run(ctx)
    text = _item(jev.site_items, "site")
    assert "페이지 제목: 중앙하이츠 갈산역 센트럴 | 갈산역 0분의 가치" in text
    assert "페이지 설명: 중앙하이츠 갈산역 센트럴 - 갈산역" in text


# ---------------------------------------------------------------- 접수 classify 입력


def test_intake_item_is_page_text_not_finishing_material_line(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """숭의역 노르웨이숲 더 스카이: 예전 접수 입력 = '마감재리스트' 한 줄(→ unknown). 이제 단지 이름 + 페이지 문구(분양 일정 포함)."""
    assert isinstance(jev, RecordingJev)
    for ctx in _site_ctx(make_ctx, factory, page("숭의역 노르웨이숲 더 스카이")):
        sid = _run(ctx)
    text = _item(jev.intake_items, "intake")
    assert text != "마감재리스트"
    assert text.startswith("단지: 숭의역 노르웨이숲 더 스카이\n")
    assert "정당계약" in text and "분양일정" in text
    row = _row(factory, sid)
    assert row.note is None or "마감재" not in row.note, "거짓 후보는 문구 후보 note 에도 없다"


def test_intake_item_keeps_context_around_fragment(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """e편한세상 동인천 베이프런트: 예전 입력 '분양중공사중' 한 줄(→ open review 0.61). 이제 단지 이름 + 그 줄 앞뒤."""
    assert isinstance(jev, RecordingJev)
    for ctx in _site_ctx(make_ctx, factory, page("e편한세상 동인천 베이프런트")):
        _run(ctx)
    text = _item(jev.intake_items, "intake")
    assert text.startswith("단지: e편한세상 동인천 베이프런트\n")
    assert "분양중공사중\n신포역 초역세권과" in text


# ---------------------------------------------------------------- 분류 복사 = 같은 입력일 때만(D22-2)


def test_unconfirmed_identity_is_copied_only_while_input_is_same(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """동일성 review 행: 다음 날 같은 원문·같은 입력이면 복사(호출 0). 입력 조립이 바뀌었으면(예전 근거로 판정한 행 — 로그의
    항목 텍스트가 지금 입력과 다름) 다시 묻는다. R6-INTAKE 배포 직후 운영 DB 의 review 행이 이 경우다."""
    assert isinstance(jev, RecordingJev)
    jev.identity_decision = "review"
    for ctx in _site_ctx(make_ctx, factory, page("포레나더샵 인천시청역")):
        sid1 = _run(ctx, "2026-10-08")
        row1 = _row(factory, sid1)
        assert (row1.status, row1.reason) == ("확인 불가", SITE_UNCONFIRMED)
        n_site = len(jev.site_items)
        assert n_site == 1

        sid2 = _run(ctx, "2026-10-09")  # 같은 원문 → 복사, 판정기 호출 없음
        assert sid2 != sid1
        assert len(jev.site_items) == n_site, "같은 입력이면 다시 묻지 않는다(D22-2)"
        assert (_row(factory, sid2).status, _row(factory, sid2).reason) == ("확인 불가", SITE_UNCONFIRMED)

        # 원문은 그대로, 단지 사실(시행 — 새 출처)이 바뀌어 동일성 입력이 달라졌다. 예전에는 같은 원문 행이면 복사했다
        with factory() as s:
            cx = s.get(Complex, CX)
            assert cx is not None
            cx.developer = "상인천초교주변주택재개발정비사업조합(사업대행 한국토지신탁)"
            s.commit()
        jev.identity_decision = "auto"
        sid3 = _run(ctx, "2026-10-10")
        assert len(jev.site_items) == n_site + 1, "입력이 바뀌었으면 다시 묻는다"
        assert "사업대행 한국토지신탁" in jev.site_items[-1]["text"]
        assert _row(factory, sid3).status == "가능", "동일성 auto → 접수 classify(SynthJev open)"


def test_copy_compares_logged_input_text(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """R6-INTAKE 배포 직후: 운영 DB 의 동일성 review 행은 예전 조립(이름·위치 + 앞 1500자)으로 판정됐다. 그 판정 로그의 항목
    텍스트가 지금 조립과 다르면 복사하지 않고 미분류로 남긴다(판정기가 새 입력으로 다시 판정 — 새 input_hash)."""
    from app.scheduler.intake import UNCLASSIFIED, carry_classification

    assert isinstance(jev, RecordingJev)
    jev.identity_decision = "review"
    for ctx in _site_ctx(make_ctx, factory, page("포레나더샵 인천시청역")):
        _run(ctx, "2026-10-08")
        with factory() as s:
            log = s.scalars(
                select(JudgmentLog).where(JudgmentLog.purpose.startswith("classify:site_identity"))
            ).one()
            items = [dict(it) for it in log.input_json["items"]]
            items[0]["text"] = (
                "단지: 포레나더샵 인천시청역\n위치: 인천광역시 남동구 간석1동 311-1번지 일원\n페이지 문구:\n포레나\n사업안내"
            )
            log.input_json = {**log.input_json, "items": items}
            flag_modified(log, "input_json")
            s.commit()
        res = collect(ctx, 1, ["official_site"], asof_date="2026-10-09")  # 수집의 분류 복사(판정 전)
        with factory() as s:
            row = s.scalars(
                select(IntakeStatus).where(
                    IntakeStatus.snapshot_id == res.snapshot_id,
                    IntakeStatus.complex_id == CX,
                    IntakeStatus.path == "headless_shot",
                )
            ).one()
            assert row.reason == UNCLASSIFIED, "예전 입력으로 낸 분류는 복사하지 않는다"
            assert carry_classification(s, res.snapshot_id) == []
