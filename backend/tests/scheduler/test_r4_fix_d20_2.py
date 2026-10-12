"""R4-FIX D20-2 — 트랙 (A) '12개월 안 공고 예정' 단지 후보(meta §1-3 #1). R4 녹화 뉴스 원문 재생.

녹화 ``fixtures/r4_news_2026-10-12.json`` = R4 2026-10-12 뉴스 검색 원문(공개 기사)에서 항목 4개: 0 오피스텔 입주 기사(후보 아님),
2·3·10 '검단 센트레빌 그랑포레'·'(계양신도시) 카이브 유보라' 공급 예정 기사. R4 에서는 둘 다 청약홈 미등록이라 수집되지 않았다(D18-8).

판정기는 결정적 가짜(``UpcomingJev`` — 판정 자체는 가짜가 정한다, 코드는 판정기 결과만 쓴다):
screen = '입주를 시작' 기사는 skip, extract = 문서의 따옴표 안 이름, classify = 첫 클래스(private_sale_apt) auto,
compare = same_fact auto.

| 테스트 | 확인 |
| --- | --- |
| ``test_news_creates_track_a_candidates`` | 후보 2개(그랑포레·카이브 유보라 — '카이브 유보라'는 판정기 compare 로 같은 단지, 옛 이름), 공고 전·track A·라벨 비공식·URL, 오피스텔 기사 제외, 다시 수집해도 행·판정 호출 0 |
| ``test_candidates_flow_to_scope_wait_new_and_report`` | 판정 범위 '보류'(분양가 미공개(공고 전)), _p4 가 다시 분류하지 않음, 상황 A decide 의 wait_new 근거·보고서 §8-2 근거 블록에 이름 |
| ``test_applyhome_notice_merges_into_candidate`` | 청약홈 공고(같은 이름 키 · 옛 이름 키)가 오면 같은 행에 주택관리번호(새 행 없음) + 새 공고 이벤트 |
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.contracts_gen import FieldCandidate
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.judge.jev_mcp import JevMcpAdapter
from app.models import ChangeEvent, Complex, FieldProvenance, JudgmentLog, Snapshot
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext

from .conftest import Clock, SynthJev
from .test_assemble_f1a import _save, _seed

NEWS = Path(__file__).resolve().parent / "fixtures" / "r4_news_2026-10-12.json"
QUOTED = re.compile(r"[‘'\"“]([^’'\"”]{2,40})[’'\"”]")


class UpcomingJev(SynthJev):
    def _screen(self, a: dict[str, Any]) -> dict[str, Any]:
        if "입주를 시작" in a["text"]:
            return {"probabilities": {"relevance": 0.05}, "recommendation": {"action": "skip"}}
        return super()._screen(a)

    def _extract(self, a: dict[str, Any]) -> dict[str, Any]:
        body = a["document"].split("발췌:", 1)[
            -1
        ]  # 본문 발췌의 따옴표 이름(제목 인용구는 단지 이름이 아니다 — 가짜 판정)
        found = list(dict.fromkeys(QUOTED.findall(body)))
        out = []
        for i, f in enumerate(a["fields"]):
            v = found[i] if i < len(found) else None
            out.append({"id": f["id"], "value": v, "status": "auto" if v else "not_found", "confidence": 0.9})
        return {"results": out}


@dataclass
class FakeNews:
    factory: sessionmaker[Session]

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        with self.factory() as s:
            doc = _save(s, NEWS.read_text(encoding="utf-8"), source_kind="news", region_id=region.id,
                        url="https://naverapihub.apigw.ntruss.com/search/v1/news?query=q")  # fmt: skip
            s.commit()
        return [doc]


def _ctx(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], jev: SynthJev
) -> SchedulerContext:
    return make_ctx(
        collectors={"news": lambda c: FakeNews(factory)},
        adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]),
    )


def _track_a(factory: sessionmaker[Session]) -> dict[str, Complex]:
    with factory() as s:
        return {c.name: c for c in s.scalars(select(Complex).where(Complex.track == "A"))}


def test_news_creates_track_a_candidates(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], clock: Clock
) -> None:
    _seed(factory)
    jev = UpcomingJev()
    res = collect(_ctx(make_ctx, factory, jev), 1, ["news"], asof_date="2026-10-12")
    rows = _track_a(factory)
    assert set(rows) == {"검단 센트레빌 그랑포레", "계양신도시 카이브 유보라"}, set(rows)
    kaive = rows["계양신도시 카이브 유보라"]
    assert "카이브 유보라" in (kaive.former_names or [])  # 판정기 compare 로 같은 단지(별칭)
    for cx in rows.values():
        assert cx.applyhome_id is None and cx.notice_date is None
        assert (cx.inclusion_class, cx.inclusion_decision) == ("private_sale_apt", "auto")
    with factory() as s:
        fps = list(
            s.scalars(
                select(FieldProvenance).where(
                    FieldProvenance.entity == "complex", FieldProvenance.field == "name"
                )
            )
        )
        assert {fp.label for fp in fps} == {"비공식"} and all(
            fp.url and fp.url.startswith("http") for fp in fps
        )
        assert all("롯데캐슬" not in c.name for c in s.scalars(select(Complex)))
        evs = list(
            s.scalars(
                select(ChangeEvent).where(ChangeEvent.entity == "complex", ChangeEvent.field == "track")
            )
        )
        assert len(evs) == 2 and all(e.id in res.change_event_ids for e in evs)
    st = res.stats()["assembled"]["upcoming"]
    assert (st["created"], st["rejected"]) == (2, 1)
    # 다시 수집: 새 행 0 · 판정기 호출 0(같은 입력 = 캐시)
    calls = len(jev.calls)
    again = collect(_ctx(make_ctx, factory, jev), 1, ["news"], asof_date="2026-10-12")
    assert len(_track_a(factory)) == 2 and len(jev.calls) == calls
    assert again.stats()["assembled"]["upcoming"]["created"] == 0


def test_candidates_flow_to_scope_wait_new_and_report(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, clock: Clock
) -> None:
    """회귀 픽스처 지역(단지 16)에서: 픽스처의 손으로 넣은 트랙 A 2단지(15·16)를 (B)·다른 이름으로 바꿔 두고 뉴스로만 후보를 만든다."""
    from app.analysis.scope import judge_scope
    from app.reports.data import wait_new_evidence as report_evidence
    from app.scheduler.pipeline import run_pipeline

    with factory() as s:
        for cx in s.scalars(select(Complex).where(Complex.track == "A")):
            cx.track, cx.name = "B", f"픽스처 단지 {cx.id}"
        s.commit()
    jev = UpcomingJev()
    ctx = _ctx(make_ctx, factory, jev)
    collect(ctx, 1, ["news"], asof_date="2026-10-07")
    before = {n: (c.inclusion_judgment_seq) for n, c in _track_a(factory).items()}
    assert len(before) == 2
    out = run_pipeline(ctx, seeded)
    assert not out.degraded, out.error
    after = _track_a(factory)
    assert {n: c.inclusion_judgment_seq for n, c in after.items()} == before, "_p4 가 다시 분류하지 않는다"
    for cx in after.values():
        sr = judge_scope(inclusion_class=cx.inclusion_class, inclusion_decision=cx.inclusion_decision,
                         has_price=False, intake_status=None)  # fmt: skip
        assert (sr.scope, sr.reason, sr.text) == ("보류", "분양가 미공개(공고 전)", "보류 — 공고 후 재판정")
    with factory() as s:
        decides = list(s.scalars(select(JudgmentLog).where(JudgmentLog.tool == "decide")))
        wait = [d for d in decides if "[wait_new]" in json.dumps(d.input_json, ensure_ascii=False)]
        assert wait, "상황 A(include_wait_new) decide 가 있어야 한다"
        text = report_evidence(wait[0].input_json) or ""
    assert "지역 (A) 트랙 공고 예정 2곳" in text
    assert "검단 센트레빌 그랑포레" in text and "계양신도시 카이브 유보라" in text


class _Fields:
    def __init__(self, key: str, values: dict[str, str]) -> None:
        self.key, self.values = key, values

    def parse(self, raw: RawDTO) -> list[FieldCandidate]:
        return [
            FieldCandidate(
                entity="complex", entity_id=None, entity_key=self.key, field=f, value_text=v, value=v, source_rank=1,
                source_kind="applyhome_detail", primary=True, label="확인됨", excerpt=v, excerpt_start=0, excerpt_end=1,
                raw_document_id=raw.id, url=raw.url, checked_at="2026-11-02", observed_on="2026-11-02",
            )
            for f, v in self.values.items()
        ]  # fmt: skip


def test_applyhome_notice_merges_into_candidate(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], clock: Clock
) -> None:
    from app.normalize.store import store_raw_document

    _seed(factory)
    collect(_ctx(make_ctx, factory, UpcomingJev()), 1, ["news"], asof_date="2026-10-12")
    ids = {n: c.id for n, c in _track_a(factory).items()}
    with factory() as s:
        snap = s.scalars(select(Snapshot)).first()
        assert snap is not None
        for key, name in (("2026000901", "검단 센트레빌 그랑포레"), ("2026000902", "카이브 유보라")):
            url = f"https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancDetail.do?houseManageNo={key}&pblancNo={key}"
            raw = _save(s, f"{key} {name}", source_kind="applyhome_detail", url=url, region_id=1, ext="html")
            out = store_raw_document(
                s, raw, snapshot_id=snap.id, parser=_Fields(key, {"name": name, "notice_date": "2026-11-02"})
            )
            assert any(e.entity == "notice" and e.field == "applyhome_id" for e in out.change_events)
        s.commit()
        got = {
            c.applyhome_id: c.id for c in s.scalars(select(Complex).where(Complex.applyhome_id.is_not(None)))
        }
        assert got == {
            "2026000901": ids["검단 센트레빌 그랑포레"],
            "2026000902": ids["계양신도시 카이브 유보라"],
        }
        assert s.scalar(select(func.count()).select_from(Complex)) == 2
