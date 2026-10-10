"""R3f CORE4 — R3 6차 C2 · m1 / DECISIONS D14-1 (계약 2026-10-09.11): 발행 리비전의 출처 서랍·주장 목록 = 저장본.

리뷰 재현(scratchpad c/): 발행 뒤 새 공고·재수집·강등 → 상세 바이트는 같은데 서랍 ``fp_11 chosen True→False; fp_63 chosen
True→False, conflicts 0→2``, 입주물량 재수집이 출처 행을 지우면 서랍 404. claims 목록은 PATCH 뒤 50→51.
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.db import get_session
from app.models import FieldProvenance, Snapshot, SnapshotView, Supply

from ._support import READ, publish_revision
from .test_r3b_g3 import CX, SNAP
from .test_r3d_core2 import _demote_price, _revision_of, store_cx_field, store_notice


def _provs(body: Any, acc: set[str] | None = None) -> set[str]:
    acc = set() if acc is None else acc
    if isinstance(body, dict):
        p = body.get("prov")
        if isinstance(p, str):
            acc.add(p)
        for v in body.values():
            _provs(v, acc)
    elif isinstance(body, list):
        for v in body:
            _provs(v, acc)
    return acc


def _drawer_ids(client: TestClient, rev: int) -> list[str]:
    acc: set[str] = set()
    for u in (
        f"/api/complexes/{CX}?snapshot={rev}",
        f"/api/complexes/1?snapshot={rev}",
        f"/api/snapshots/{rev}/market",
    ):
        r = client.get(u, headers=READ)
        assert r.status_code == 200, r.text
        _provs(r.json(), acc)
    ids = sorted(p for p in acc if p.startswith("fp_"))
    assert len(ids) >= 10
    return ids


def _drawers(client: TestClient, rev: int, ids: list[str]) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for pid in ids:
        r = client.get(f"/api/provenance/{pid}?snapshot_id={rev}", headers=READ)
        assert r.status_code == 200, (pid, r.text[:200])
        out[pid] = r.content
    return out


def _supply_fp_ids() -> list[int]:
    with get_session() as s:
        sup = list(s.scalars(select(Supply.id).where(Supply.region_id == 1)))
        return list(
            s.scalars(
                select(FieldProvenance.id).where(
                    FieldProvenance.entity == "supply", FieldProvenance.entity_id.in_(sup)
                )
            )
        )


def test_c2_published_drawer_never_changes_after_notice_demotion_and_supply_recollect(
    client: TestClient,
) -> None:
    """발행 뒤 새 공고(가격·입주월)·강등(PATCH /claims)·입주물량 재수집(출처 행 삭제)에도 그 리비전 서랍 바이트가 같다."""
    rev = publish_revision(1, "C2 서랍 리비전")
    ids = _drawer_ids(client, rev)
    supply = [f"fp_{i}" for i in _supply_fp_ids()]
    ids = sorted(
        set(ids)
        | {
            p
            for p in supply
            if client.get(f"/api/provenance/{p}?snapshot_id={rev}", headers=READ).status_code == 200
        }
    )
    before = _drawers(client, rev, ids)

    from app.api.views import basis_type
    from app.models import ComplexType

    with get_session() as s:
        t = basis_type(list(s.scalars(select(ComplexType).where(ComplexType.complex_id == CX))))
        assert t is not None
        code = t.type_code
    store_notice(CX, "2026990401", {"effective_from": "2026-10-09", "notice_kind": "무순위",
                                    f"price_by_type.{code}.max_price_won": 777_000_000}, observed_on="2026-10-12")  # fmt: skip
    store_cx_field(CX, "move_in_ym", "2031-01", "notice_pdf", "2026-10-12", "c2-a")
    _demote_price(client, 658_140_000)
    from app.collectors.stats.supply import write_supply_provenance
    from app.scheduler.collect import _supply

    with get_session() as s:
        _supply(s, 1)
        write_supply_provenance(s, 1)
        # 리뷰 재현: 재수집이 그 단지 입주물량 출처 행을 지운다(collectors/stats/supply.py) — 서랍은 저장본이라 그대로
        s.execute(delete(FieldProvenance).where(FieldProvenance.entity == "supply"))
    after = _drawers(client, rev, ids)
    changed = [p for p in ids if after[p] != before[p]]
    assert not changed, f"발행 리비전 {rev} 출처 서랍이 바뀌었다(D14-1): {changed[:6]}"

    # 같은 출처를 지금 계산하면 실제로 달라졌다(이 시험이 의미 있음 — 저장본이 아니었다면 바뀌었다)
    from app.api.errors import ApiError
    from app.api.routers.complexes import provenance_body

    live_diff = 0
    with get_session() as s:
        for pid in ids:
            try:
                live = provenance_body(s, pid)
            except ApiError:
                live_diff += 1
                continue
            import json

            if json.loads(before[pid]) != live:
                live_diff += 1
    assert live_diff > 0


def test_c2_snapshot_param_building_is_live_and_default_is_latest_published(client: TestClient) -> None:
    rev = publish_revision(1, "C2 기본 리비전")
    ids = _drawer_ids(client, rev)
    pid = ids[0]
    stored = client.get(f"/api/provenance/{pid}?snapshot_id={rev}", headers=READ)
    default = client.get(f"/api/provenance/{pid}", headers=READ)  # 지정 없음 = 지역 최신 발행 리비전 저장본
    assert default.status_code == 200 and default.content == stored.content
    live_rev = _revision_of(rev, publish=False)
    with get_session() as s:
        fp = s.get(FieldProvenance, int(pid[3:]))
        assert fp is not None
        fp.reason = "발행 뒤 바뀐 사유"
    live = client.get(
        f"/api/provenance/{pid}?snapshot_id={live_rev}", headers=READ
    )  # 발행 전 리비전 = 실시간
    assert live.status_code == 200 and live.json()["reason"] == "발행 뒤 바뀐 사유"
    assert client.get(f"/api/provenance/{pid}?snapshot_id={rev}", headers=READ).content == stored.content
    assert client.get(f"/api/provenance/{pid}", headers=READ).content == stored.content


def test_c2_drawer_not_in_revision_404_and_pending_503(client: TestClient) -> None:
    rev = publish_revision(1, "C2 404")
    with get_session() as s:  # 발행 뒤 생긴 출처 행 — 그 리비전 화면에 없었다
        fp = FieldProvenance(entity="complex", entity_id=CX, field="name", value_text="x", value_norm="x",
                             label="추정", checked_at="2026-10-12", source_rank=9, chosen=False)  # fmt: skip
        s.add(fp)
        s.flush()
        new_id = fp.id
    r = client.get(f"/api/provenance/fp_{new_id}?snapshot_id={rev}", headers=READ)
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    with get_session() as s:  # 새 종류 저장본이 아직 없는(backfill 전) 발행 리비전 = 503 materialize_pending
        s.execute(
            delete(SnapshotView).where(SnapshotView.snapshot_id == rev, SnapshotView.kind == "provenance")
        )
    r = client.get(f"/api/provenance/fp_{new_id}?snapshot_id={rev}", headers=READ)
    assert r.status_code == 503 and r.json()["code"] == "materialize_pending"
    assert r.headers.get("retry-after")


def test_c2_batch_drawers_equal_single_drawers(client: TestClient) -> None:
    """저장본 출처 서랍(``provenance_bodies`` — 한 번에)은 한 건씩 계산(``provenance_body``)과 같은 값(강등 포함)."""
    from app.api.routers.complexes import provenance_bodies, provenance_body

    _demote_price(client, 658_140_000)
    with get_session() as s:
        ids = [
            f"fp_{i}" for i in s.scalars(select(FieldProvenance.id).order_by(FieldProvenance.id).limit(400))
        ]
        ids += [
            f"fp_{i}"
            for i in s.scalars(
                select(FieldProvenance.id).where(FieldProvenance.conflict_group.is_not(None)).limit(100)
            )
        ]
        many = provenance_bodies(s, ids)
        for pid in sorted(set(ids)):
            assert many[pid] == provenance_body(s, pid), pid
        for pid, body in many.items():  # 충돌 출처로 따라온 서랍도 같은 규칙
            if pid not in ids:
                assert body == provenance_body(s, pid), pid
        assert any(b["label"] == "확인 불가" and "검증 모순" in (b["reason"] or "") for b in many.values())


def test_m1_published_claims_list_is_stored(client: TestClient) -> None:
    """R3 6차 m1: 발행 리비전 주장 목록은 저장본 — PATCH /claims(강등) 뒤에도 같은 바이트. 발행 전 리비전은 지금 값."""
    rev = publish_revision(1, "m1 주장 리비전")
    before = client.get(f"/api/snapshots/{rev}/claims", headers=READ)
    assert before.status_code == 200
    _demote_price(client, 658_140_000)
    after = client.get(f"/api/snapshots/{rev}/claims", headers=READ)
    assert after.content == before.content
    verified = client.get(f"/api/snapshots/{rev}/claims?status=verified", headers=READ).json()
    assert all(c["verify_status"] == "verified" for c in verified)
    with get_session() as s:
        newest = s.scalars(select(Snapshot).order_by(Snapshot.id.desc())).first()
        assert newest is not None and newest.status != "published"
        live = newest.id
    assert client.get(f"/api/snapshots/{live}/claims", headers=READ).status_code == 200
    with get_session() as s:
        assert s.get(Snapshot, SNAP) is not None
