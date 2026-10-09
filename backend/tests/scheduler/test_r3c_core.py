"""R3c CORE — 3차 리뷰(`docs/design/wp/R3_REVIEW3.md`) 재현·통합 테스트 (계약 2026-10-09.8, DECISIONS D11).

실제 경로만 쓴다(spy 금지 — minor 21): 수집(``scheduler.collect``) → 정규화 저장(``normalize.store``) → 강등(``api.demotion``)
→ 사람 확인(``api.demotion.apply_human_check``) → 파이프라인(``scheduler.pipeline``)·API(TestClient)·보고서 데이터.

| 리뷰 | 시나리오 |
| --- | --- |
| C-3 | 수집 2회 → 강등 → 사람 확인 → 같은 원문 재수집 → 사람 확인 값 유지(재강등·조용한 되돌림 없음) |
| C-4 | 강등 → 같은 값 새 원문·값 없는 원문 → 강등 유지 / 다른 값 새 원문 → 해제(파이프라인 쓰기 경로가 복원 기록) |
| M-3 | 강등 기록 즉시(창 없음) 파이프라인 입력·API 상세·보고서에서 '확인 불가(검증 모순)' |
| C-1 | 주간 수집 2회(다른 날) → 그 스냅샷 벤치마크 표본 수 불변(이중 집계 없음), 과거 스냅샷 재채점에 미래 행 없음 |
| M-2·D11-1 | 발행 후 rejudge → 새 리비전, 옛 리비전 파생 행 불변, 새 리비전 완성 뒤 publish |
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors.applyhome import api as ah_api
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.snapshot import store_raw
from app.models import (
    Claim,
    Complex,
    FactDemotion,
    FieldProvenance,
    HumanCheck,
    Ladder,
    RawDocument,
    ScoreRun,
    ScoreTotal,
    Snapshot,
)
from app.normalize.store import raw_dto
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext
from app.scheduler.inputs import load_facts
from app.scheduler.pipeline import run_pipeline

HM = "2026990001"  # 테스트 공고(픽스처 단지와 겹치지 않는 주택관리번호)


def _detail_body(hm: str, *, move_in: str | None, name: str = "테스트 리비전 단지", stamp: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {
        "HOUSE_MANAGE_NO": hm, "PBLANC_NO": hm, "HOUSE_NM": name,
        "HSSPLY_ADRES": "인천광역시 연수구 송도동 1-1", "TOT_SUPLY_HSHLDCO": 300,
        "RCRIT_PBLANC_DE": "2026-09-01", "HOUSE_DTL_SECD_NM": "민영",
    }  # fmt: skip
    if move_in is not None:
        row["MVN_PREARNGE_YM"] = move_in
    body: dict[str, Any] = {"data": [row], "matchCount": 1, "page": 1, "perPage": 100}
    if stamp:
        body["_fetched"] = stamp  # 같은 값 재수집(응답 메타만 달라 sha 가 다른 원문)
    return body


def _save(factory: sessionmaker[Session], body: dict[str, Any], hm: str = HM) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    stored = store_raw(data, source="applyhome_detail", day=date(2026, 10, 8), ext="json")
    return {
        "source_kind": "applyhome_detail",
        "url": ah_api.doc_url(ah_api.ENDPOINTS["apt"].detail, ah_api.item_params(hm, hm)),
        "fetched_at": "2026-10-08T06:00:00+09:00",
        "http_status": 200,
        "sha256": stored.sha256,
        "path": stored.relpath,
        "content_type": "application/json",
        "region_id": 1,
    }


@dataclass
class Feed:
    """applyhome 단계 수집기: ``docs`` 의 원문 행을 넣고 돌려준다(같은 sha 면 기존 행 — 실제 수집기와 같은 멱등)."""

    factory: sessionmaker[Session]
    docs: list[dict[str, Any]] = field(default_factory=list)

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        out: list[RawDTO] = []
        with self.factory() as s:
            for r in self.docs:
                row = s.scalars(select(RawDocument).where(RawDocument.sha256 == r["sha256"])).first()
                if row is None:
                    row = RawDocument(**r)
                    s.add(row)
                    s.flush()
                out.append(raw_dto(row))
            s.commit()
        return out


def _ctx(make_ctx: Callable[..., SchedulerContext], feed: Feed) -> SchedulerContext:
    return make_ctx(collectors={"applyhome": lambda c: feed})


def _cx(s: Session) -> Complex:
    cx = s.scalars(select(Complex).where(Complex.applyhome_id == HM)).one()
    return cx


def _demote_move_in(factory: sessionmaker[Session], snapshot_id: int) -> int:
    """P9 사실 문장 주장(contradicted)을 만들고 PATCH 경로의 강등 함수로 강등한다. FactDemotion id."""
    from app.api.demotion import claim_target, demote

    with factory() as s:
        cx = _cx(s)
        claim = Claim(
            snapshot_id=snapshot_id, section=f"complex:{cx.id}", complex_id=cx.id,
            text=f"{cx.name} 입주 예정 시기는 {cx.move_in_ym}이다", evidence_text="",
            verify_status="contradicted", entity="complex", entity_id=cx.id, field="move_in_ym",
        )  # fmt: skip
        s.add(claim)
        s.flush()
        target = claim_target(s, claim)
        assert target is not None and target.complete
        d = demote(s, claim, target)
        assert d is not None
        s.commit()
        return d.id


def _human(factory: sessionmaker[Session], value: str) -> None:
    from app.api.demotion import apply_human_check, human_target

    with factory() as s:
        cx = _cx(s)
        t = human_target(s, cx.id, "move_in_ym")
        assert t is not None
        hc = HumanCheck(
            complex_id=cx.id, field="move_in_ym", value_text=value, kind="phone",
            checked_at="2026-10-08T10:00:00+09:00", entered_by="운영자", note="분양사무소 통화",
            created_at="2026-10-08T10:00:00+09:00", entity=t.entity, entity_id=t.entity_id,
        )  # fmt: skip
        s.add(hc)
        s.flush()
        apply_human_check(s, hc)
        s.commit()


def _fact_move_in(factory: sessionmaker[Session], snapshot_id: int) -> tuple[str | None, str | None]:
    """파이프라인 입력(``load_facts`` — 오버레이 적용)의 입주 예정 값·라벨."""
    with factory() as s:
        snap = s.get(Snapshot, snapshot_id)
        assert snap is not None
        from app.models import Region

        region = s.get(Region, snap.region_id)
        assert region is not None
        f = next(x for x in load_facts(s, snap, region) if x.row.applyhome_id == HM)
        return f.score_row.move_in_ym, f.labels.get("move_in")


def test_c3_human_check_survives_same_raw_recollection(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    """C-3: 수집 2회 → 강등 → 사람 확인 → 같은 원문 재수집 → 사람 확인 값이 그대로(라벨 확인됨·사람 확인), 강등 복원 유지."""
    feed = Feed(factory, [_save(factory, _detail_body(HM, move_in="202812"))])
    ctx = _ctx(make_ctx, feed)
    first = collect(ctx, 1, ["applyhome_list"], asof_date="2026-10-08")
    collect(ctx, 1, ["applyhome_list"], asof_date="2026-10-08")  # 같은 원문을 매일 다시 저장
    with factory() as s:
        assert _cx(s).move_in_ym == "2028-12"
    did = _demote_move_in(factory, first.snapshot_id)
    assert _fact_move_in(factory, first.snapshot_id) == (None, None), "강등 즉시 점수 입력에서 빠진다(M-3)"
    _human(factory, "2029-03")
    collect(ctx, 1, ["applyhome_list"], asof_date="2026-10-08")  # 같은 sha256 원문 재정규화
    with factory() as s:
        cx = _cx(s)
        assert cx.move_in_ym == "2029-03", "같은 원문 재정규화가 사람 확인 값을 되돌리면 안 된다(C-3)"
        chosen = s.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "complex", FieldProvenance.entity_id == cx.id,
                FieldProvenance.field == "move_in_ym", FieldProvenance.chosen.is_(True),
            )
        ).all()  # fmt: skip
        assert [(fp.label, fp.reason, fp.source_rank) for fp in chosen] == [("확인됨", "사람 확인(phone)", 0)]
        d = s.get(FactDemotion, did)
        assert d is not None and d.restored_by == "human_check"
    assert _fact_move_in(factory, first.snapshot_id) == ("2029-03", "확인됨")


def test_c4_same_value_or_valueless_source_keeps_demotion_other_value_releases(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    """C-4: 같은 페이지 재수집(sha 만 다름·값 동일)·값 없는 행은 강등을 풀지 않는다. 다른 값을 낸 새 출처만 푼다."""
    feed = Feed(factory, [_save(factory, _detail_body(HM, move_in="202812"))])
    ctx = _ctx(make_ctx, feed)
    res = collect(ctx, 1, ["applyhome_list"], asof_date="2026-10-08")
    did = _demote_move_in(factory, res.snapshot_id)
    # 같은 값, 다른 원문(sha 다름)
    feed.docs = [_save(factory, _detail_body(HM, move_in="202812", stamp="2026-10-08T07"))]
    collect(ctx, 1, ["applyhome_list"], asof_date="2026-10-08")
    assert _fact_move_in(factory, res.snapshot_id) == (None, None)
    # 값 없는 원문(파싱 실패 — 입주월 칸 없음)
    feed.docs = [_save(factory, _detail_body(HM, move_in=None, stamp="2026-10-08T08"))]
    collect(ctx, 1, ["applyhome_list"], asof_date="2026-10-08")
    assert _fact_move_in(factory, res.snapshot_id) == (None, None)
    with factory() as s:
        assert s.get(FactDemotion, did).restored_at is None  # type: ignore[union-attr]
    # 다른 값의 새 원문(최신 공고) → 해제
    feed.docs = [_save(factory, _detail_body(HM, move_in="202903", stamp="2026-10-08T09"))]
    collect(ctx, 1, ["applyhome_list"], asof_date="2026-10-08")
    assert _fact_move_in(factory, res.snapshot_id) == ("2029-03", "확인됨")
    with factory() as s:
        d = s.get(FactDemotion, did)
        assert d is not None and d.restored_by == "new_source", "수집(쓰기 경로)이 복원을 기록한다"


def test_c1_weekly_twice_keeps_benchmark_sample_count(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    """C-1: 주간 수집 2회(다른 날, 같은 사례) → 각 스냅샷 점수 입력의 벤치마크 = 그 스냅샷 조립분만(표본 수 불변).
    과거 스냅샷을 다시 채점해도 미래 스냅샷 조립분이 섞이지 않는다."""
    from sqlalchemy import delete

    from app.models import Benchmark, LegalDong, Region
    from app.scheduler.inputs import build_score_inputs
    from app.scheduler.payloads import EMPTY_ANCHOR

    from .test_r3b_g2_benchmark_flow import SONGDO, HistoryApplyhome, RecordedRtms

    with factory() as s:
        s.execute(delete(Benchmark))
        s.add(
            LegalDong(
                code=SONGDO, sido_name="인천광역시", sigungu_name="연수구", eupmyeondong_name="송도동", ri_name=None,
                full_name="인천광역시 연수구 송도동", sigungu_code="28185", active=True, source_date="2026-09-01",
            )
        )  # fmt: skip
        s.commit()
    ctx = make_ctx(
        collectors={"applyhome": lambda c: HistoryApplyhome(factory), "rtms": lambda c: RecordedRtms(factory)}
    )
    one = collect(ctx, 1, ["rtms"], asof_date="2026-10-07")
    two = collect(ctx, 1, ["rtms"], asof_date="2026-10-14")

    def inputs_for(sid: int) -> list[Any]:
        with factory() as s:
            snap = s.get(Snapshot, sid)
            region = s.get(Region, 1)
            assert snap is not None and region is not None
            facts = load_facts(s, snap, region)
            return list(build_score_inputs(s, snap, region, facts, EMPTY_ANCHOR).benchmarks)

    with factory() as s:
        per_snap = dict(
            s.execute(select(Benchmark.snapshot_id, func.count()).group_by(Benchmark.snapshot_id)).all()
        )
    assert per_snap.get(one.snapshot_id) and per_snap.get(two.snapshot_id), per_snap
    b1, b2 = inputs_for(one.snapshot_id), inputs_for(two.snapshot_id)
    assert len(b1) == per_snap[one.snapshot_id] and len(b2) == per_snap[two.snapshot_id], "이중 집계 없음"
    assert len(b1) == len(b2), "같은 사례 → 표본 수 불변"
    with factory() as s:
        future = {b.id for b in s.scalars(select(Benchmark).where(Benchmark.snapshot_id == two.snapshot_id))}
    assert not future & {b.id for b in b1}, "과거 스냅샷 재채점에 미래 행이 섞이지 않는다"


def test_d11_1_rejudge_after_publish_writes_new_revision(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    """M-2·D11-1: 발행 스냅샷 rejudge → 같은 기준일 새 리비전. 옛 리비전의 사다리·점수 행은 그대로, 새 리비전 완성 뒤 publish."""
    from app.scheduler import snapshots
    from app.scheduler.rejudge import enqueue_rejudge, handle_rejudge

    ctx = make_ctx()
    out = run_pipeline(ctx, seeded)
    assert not out.degraded, out.error
    with factory() as s:
        ok, n = snapshots.publish(s, seeded, now="2026-10-07T08:00:00+09:00")
        s.commit()
        assert ok, n
        before_ladders = sorted(
            (lad.id, lad.complex_id, lad.horizon, str(lad.p10)) for lad in s.scalars(select(Ladder).where(Ladder.snapshot_id == seeded))
        )
        before_runs = sorted(r.id for r in s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == seeded)))
        target = s.scalars(select(Complex.id).where(Complex.region_id == 1).order_by(Complex.id)).first()
        job = enqueue_rejudge(s, seeded, [target], "테스트 재판정")
        s.commit()
    stats = handle_rejudge(ctx, job)
    rev = int(stats["snapshot_id"])
    assert rev != seeded
    with factory() as s:
        old, new = s.get(Snapshot, seeded), s.get(Snapshot, rev)
        assert old is not None and new is not None
        assert old.status == "published" and (new.revision, new.revision_of, new.asof_date) == (2, seeded, old.asof_date)
        assert new.status == "ready"
        after_ladders = sorted(
            (lad.id, lad.complex_id, lad.horizon, str(lad.p10)) for lad in s.scalars(select(Ladder).where(Ladder.snapshot_id == seeded))
        )
        assert after_ladders == before_ladders, "발행 리비전의 사다리는 제자리에서 바뀌지 않는다(M-2)"
        assert sorted(r.id for r in s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == seeded))) == before_runs
        assert s.scalar(select(func.count()).select_from(ScoreRun).where(ScoreRun.snapshot_id == rev))
        assert s.scalar(select(func.count()).select_from(ScoreTotal).join(ScoreRun).where(ScoreRun.snapshot_id == rev))
        pub = s.scalars(select(Snapshot).where(Snapshot.id == rev)).one()
        ok, _ = snapshots.publish(s, pub.id, now="2026-10-07T09:00:00+09:00")
        s.commit()
        assert ok
        from app.api.deps import default_snapshot

        assert default_snapshot(s, 1).id == rev  # type: ignore[union-attr]
