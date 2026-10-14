"""R10-FOLLOW(D29-2·D29-3) — 수집 잡(`collect.daily` 경로) 한 번으로 병합·체크리스트가 맞춰지는지, 같은 날 다시 돌리면 그대로인지.

운영 DB 모양(인천 2026-10-14 읽기 전용 확인): 원 단지 39(2025000397 — 본청약 납부 조건)와 임의공급 번호 행 99(2025940268 — 임의 납부
조건, 같은 중도금 일정). 수집기는 R9-PARSE 녹화 원문(``tests/normalize/fixtures/r9_parse`` — 임의공급 공고문 + 청약홈 임의공급 API
상세·주택형·경쟁률)을 돌려준다(네트워크 없음). 판정기 호출 없음(수집·조립 단계만).

| 테스트 | 확인 |
| --- | --- |
| ``test_daily_collect_merges_duplicate_and_syncs_checklist`` | 병합 표식 + change_event 1(critical, 원 단지 complex_id) · 판정 입력(``load_facts``)에서 빠짐 · 체크리스트: 원 단지에만 '청약 접수'·'당첨자 발표'·중도금, 병합된 행 항목은 auto 로 닫힘 · 같은 날 다시 수집 → change_event 0·단지·체크리스트 그대로(D23-1·D24-1) |
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors.applyhome import api as ah_api
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.snapshot import store_raw
from app.models import ChangeEvent, ChecklistItem, Complex, PaymentTerms, RawDocument, Region, Snapshot
from app.normalize.store import raw_dto
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext
from app.scheduler.inputs import load_facts

from .conftest import seed_region, seed_scenarios

R9 = Path(__file__).resolve().parents[1] / "normalize" / "fixtures" / "r9_parse"
NOTICE_URL = "https://static.applyhome.co.kr/ai/aia/getAtchmnfl.do?houseManageNo={n}&pblancNo={n}&atchmnflSeqNo=1&atchmnflSn=1"
ASOF = "2026-10-14"
APPLY = [
    {"kind": "특별공급", "start": "2026-10-19", "end": "2026-10-19"},
    {"kind": "1순위 해당지역", "start": "2026-10-20", "end": "2026-10-20"},
    {"kind": "1순위 기타지역", "start": "2026-10-20", "end": "2026-10-20"},
]
SCHED = [
    {"seq": n, "due_date": d, "pct": 10.0}
    for n, d in enumerate(["2026-12-19", "2027-08-10", "2028-02-10"], start=1)
]


def _save(s: Session, name: str, *, source_kind: str, url: str, ext: str) -> RawDTO:
    data = (R9 / name).read_bytes()
    stored = store_raw(data, source=source_kind, day=date(2026, 10, 14), ext=ext)
    row = s.scalars(select(RawDocument).where(RawDocument.sha256 == stored.sha256)).first()
    if row is None:
        row = RawDocument(
            source_kind=source_kind, url=url, fetched_at="2026-10-14T06:00:00+09:00", http_status=200,
            sha256=stored.sha256, path=stored.relpath, content_type="text/plain",
            text_path=stored.relpath if source_kind == "notice_pdf" else None, region_id=1,
        )  # fmt: skip
        s.add(row)
        s.flush()
    return raw_dto(row)


def _api_url(part: str) -> str:
    ep = ah_api.ENDPOINTS["opt"]
    path = {"detail": ep.detail, "model": ep.model, "competition": ep.competition}[part]
    return ah_api.doc_url(path, ah_api.item_params("2025940268", "2025940268"))


@dataclass
class Docs:
    factory: sessionmaker[Session]
    kind: str

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        with self.factory() as s:
            if self.kind == "notice_pdf":
                out = [
                    _save(
                        s, "notice_2025940268_dohwa_imui.txt", source_kind="notice_pdf",
                        url=NOTICE_URL.format(n="2025940268"), ext="txt",
                    )
                ]  # fmt: skip
            else:
                out = [
                    _save(s, name, source_kind="applyhome_detail", url=_api_url(part), ext="json")
                    for part, name in (
                        ("detail", "api_OPTDetail_2025940268.json"),
                        ("model", "api_OPTMdl_2025940268.json"),
                        ("competition", "api_OPTCmpet_2025940268.json"),
                    )
                ]
            s.commit()
        return out


def _seed(factory: sessionmaker[Session]) -> tuple[int, int]:
    with factory() as s:
        seed_scenarios(s)
        seed_region(s)
        ids = []
        for no, kind in (("2025000397", "본청약"), ("2025940268", "임의")):
            cx = Complex(
                region_id=1, applyhome_id=no, name="두산위브 더센트럴 도화", former_names=[], apply_dates=APPLY,
                contract_dates=[], winner_date="2026-10-27", inclusion_class="private_sale_apt",
                inclusion_decision="auto", notice_date="2025-08-29",
            )  # fmt: skip
            s.add(cx)
            s.flush()
            s.add(
                PaymentTerms(
                    complex_id=cx.id, notice_no=no, notice_kind=kind, effective_from="2025-08-29",
                    interim_schedule=SCHED, price_by_type={},
                )
            )  # fmt: skip
            ids.append(cx.id)
        s.commit()
        return ids[0], ids[1]


def _state(factory: sessionmaker[Session]) -> list[Any]:
    with factory() as s:
        cxs = [
            (c.id, c.applyhome_id, c.name, tuple(c.former_names or []), c.merged_into_id)
            for c in s.scalars(select(Complex).order_by(Complex.id))
        ]
        items = [
            (i.id, i.complex_id, i.kind, i.title, i.due_date, i.status, i.closed_by)
            for i in s.scalars(select(ChecklistItem).order_by(ChecklistItem.id))
        ]
        return [*cxs, *items]


def test_daily_collect_merges_duplicate_and_syncs_checklist(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Any
) -> None:
    orig, dup = _seed(factory)
    ctx = make_ctx(
        collectors={
            "applyhome": lambda c: Docs(factory, "applyhome"),
            "notice_pdf": lambda c: Docs(factory, "notice_pdf"),
        }
    )
    res = collect(ctx, 1, ["applyhome_list", "applyhome_detail"], asof_date=ASOF)
    assert not res.store_errors and not res.errors, (res.store_errors, res.errors)
    with factory() as s:
        assert s.get(Complex, dup).merged_into_id == orig  # type: ignore[union-attr]
        evs = list(
            s.scalars(
                select(ChangeEvent).where(ChangeEvent.entity == "complex", ChangeEvent.field == "merged_into")
            )
        )
        assert [(e.entity_id, e.complex_id, e.severity, e.triggers_rejudge) for e in evs] == [
            (dup, orig, "critical", True)
        ]
        assert evs[0].id in res.change_event_ids
        snap = s.scalars(select(Snapshot).where(Snapshot.region_id == 1)).one()
        region = s.get(Region, 1)
        assert region is not None
        assert [f.complex_id for f in load_facts(s, snap, region)] == [orig]  # 판정·점수 입력에서 빠진다
        opens = [
            (i.complex_id, i.kind, i.title, i.due_date)
            for i in s.scalars(
                select(ChecklistItem).where(ChecklistItem.status == "open").order_by(ChecklistItem.id)
            )
            if i.kind in ("청약 접수", "당첨자 발표", "중도금")
        ]
        assert {cid for cid, *_ in opens} == {orig}
        assert sorted((k, t, d) for _, k, t, d in opens if k != "중도금") == [
            ("당첨자 발표", "당첨자 발표", "2026-10-27"),
            ("청약 접수", "1순위 청약 접수(해당지역·기타지역)", "2026-10-20"),
            ("청약 접수", "특별공급 청약 접수", "2026-10-19"),
        ]
        dated = [(t, d) for _, _, t, d in opens]
        assert len(dated) == len(set(dated)), dated  # 같은 일정 두 번 없음
        assert not [
            i
            for i in s.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == dup))
            if i.status == "open"
        ]

    before = _state(factory)
    again = collect(ctx, 1, ["applyhome_list", "applyhome_detail"], asof_date=ASOF)
    assert again.change_event_ids == [], f"같은 날 다시 수집한 change_event {len(again.change_event_ids)}건"
    assert _state(factory) == before


def test_rejudge_after_merge_scores_without_the_merged_row(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    """병합 뒤 재판정(병합 change_event 가 부르는 rejudge)의 점수·사다리·주장에는 병합된 행이 없다 — 판정 대상이 아닌 단지의
    이전 행 복사도 ``load_facts`` 단지만이다."""
    from app.models import Claim, Ladder, ScoreTotal
    from app.scheduler.pipeline import run_pipeline

    first = run_pipeline(make_ctx(), seeded)
    with factory() as s:
        scored = sorted(
            {
                t.complex_id
                for t in s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id.in_(first.score_run_ids)))
            }
        )
        assert len(scored) >= 2
        orig, dup = scored[0], scored[1]
        cx = s.get(Complex, dup)
        assert cx is not None
        cx.merged_into_id = orig
        snap = s.get(Snapshot, seeded)
        assert snap is not None
        snap.status = "published"  # 운영 모양: 병합은 발행된 리비전 뒤 — 재판정은 새 리비전에(D11-1)
        s.commit()
    out = run_pipeline(make_ctx(), seeded, complex_ids=[orig], reason="R10 병합 뒤 재판정")
    assert out.snapshot_id != seeded
    with factory() as s:
        old = {
            t.complex_id
            for t in s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id.in_(first.score_run_ids)))
        }
        assert dup in old  # 발행 리비전의 행은 그대로
        assert list(s.scalars(select(Ladder).where(Ladder.snapshot_id == seeded, Ladder.complex_id == dup)))
        now = {
            t.complex_id
            for t in s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id.in_(out.score_run_ids)))
        }
        assert dup not in now and set(scored) - {dup} <= now
        lad = select(Ladder).where(Ladder.snapshot_id == out.snapshot_id, Ladder.complex_id == dup)
        assert not list(s.scalars(lad))
        claims = select(Claim).where(Claim.snapshot_id == out.snapshot_id, Claim.complex_id == dup)
        assert not list(s.scalars(claims))
