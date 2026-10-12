"""R4 재시험 N1(critical, D21-1) — 공고문 공급금액 표의 단위 표기를 읽어 원으로 환산한다.

R4: 검단호수공원역 중흥S-클래스(2025000253) 공고문 '■ 공급금액 및 납부일정 (단위: 세대, 천원)' 표를 원으로 읽어 84A 최고가
617,000원(실제 6.17억)이 '확인됨'으로 저장되고, 공고문 순위(rank 1)가 청약홈 API '61,700만원'(rank 2)을 compare 없이 이겼다.

D21-1: ① 표 머리·근처의 단위 표기('(단위: 천원)'·'만원'·'원')를 읽어 원으로 환산하고 단위 근거를 출처 발췌에 남긴다.
② 단위가 없으면 원으로 보되(사유 '단위 표기 없음'), 같은 단지·타입의 다른 1차 출처와 10배 이상 다르면 순위로 채택하지 않고
compare(판정기)로 보낸다 — 공고문 타입 행(complex_type)과 그 공고의 타입 가격(payment_terms.price_by_type) 모두.
compare 가 same_fact 면 단위가 분명한 출처(청약홈 '만원')를 채택하고, 그 밖이면 보류(확인 불가)로 둔다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate
from app.models import Complex, ComplexType, FieldProvenance, PaymentTerms, Region
from app.normalize.notice_parser import NoticeParser
from app.normalize.resolver import resolve
from app.normalize.store import store_raw_document

from . import _r4b

N1 = "n1"
NOTICE_ID = 579
API_IDS = [75, 76]  # 청약홈 API 상세·주택형(LTTOT_TOP_AMOUNT 만원)
EXPECTED_MAX = {"84A": 617_000_000, "84B": 599_000_000, "112A": 714_000_000, "114A": 734_000_000}
EXPECTED_FLOOR = {"84A": 576_000_000, "84B": 557_000_000, "112A": 643_000_000, "114A": 664_000_000}


def _parse(raw_dir: Path, group: str, raw_id: int) -> list[FieldCandidate]:
    _r4b.install(raw_dir)
    from app.core.contracts_gen import RawDocument as RawDTO

    r = dict(_r4b.row(group, raw_id))
    dto = RawDTO.model_validate({**r, "region_id": 1, "complex_id": None})
    return NoticeParser(raw_dir=raw_dir).parse(dto)


def _by(cands: list[FieldCandidate], entity: str, field_name: str) -> dict[str, FieldCandidate]:
    return {
        str(c.entity_key).split(":")[-1]: c
        for c in cands
        if c.entity == entity and c.field == field_name and c.value is not None
    }


def test_thousand_won_table_is_converted_to_won(raw_dir: Path) -> None:
    cands = _parse(raw_dir, N1, NOTICE_ID)
    tops = {k: c.value for k, c in _by(cands, "complex_type", "max_price_won").items()}
    assert tops == EXPECTED_MAX, "공급금액 표 '(단위: 세대, 천원)' → 원(×1,000)"
    floors = {k: c.value for k, c in _by(cands, "complex_type", "floor_sample_price_won").items()}
    assert floors == EXPECTED_FLOOR
    pbt = {
        c.field: c.value
        for c in cands
        if c.entity == "payment_terms" and c.field.startswith("price_by_type.") and c.field.endswith(".max_price_won")
    }
    assert pbt["price_by_type.84A.max_price_won"] == 617_000_000


def test_unit_evidence_is_in_the_excerpt(raw_dir: Path) -> None:
    cands = _parse(raw_dir, N1, NOTICE_ID)
    c = _by(cands, "complex_type", "max_price_won")["84A"]
    assert "천원" in (c.excerpt or ""), f"가격 사실의 출처 발췌에 단위 근거가 있어야 한다: {c.excerpt!r}"
    assert "617,000" in (c.excerpt or "")


def test_won_tables_are_unchanged() -> None:
    """원 단위 표(회귀 픽스처 공고문)는 값·발췌·사유가 그대로다."""
    from app.normalize.notice_parser import parse_notice_text

    from ._support import NOTICE_BASE, dto, notice_file

    text = notice_file("2025000302").read_text(encoding="utf-8")
    raw = dto(source_kind="notice_pdf", url=f"{NOTICE_BASE}houseManageNo=2025000302&pblancNo=2025000302")
    cands = parse_notice_text(text, raw)
    tops = _by(cands, "complex_type", "max_price_won")
    assert tops and all(v.value is not None and int(v.value) > 100_000_000 for v in tops.values())
    assert all(not (v.reason or "") for v in tops.values()), "원 단위 표의 가격 사유는 비어 있다(발췌·사유 그대로)"


def _unitless_text(raw_dir: Path) -> tuple[str, str]:
    """N1 공고문에서 금액 단위만 지운 변형(단위 표기 없는 표) → (sha256, text_path)."""
    text = _r4b.text_of(N1, NOTICE_ID).replace("(단위: 세대, 천원)", "(단위: 세대)")
    data = text.encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    rel = f"notice_pdf/2026-10-12/{sha}.txt"
    p = raw_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return sha, rel


def test_unitless_table_reads_won_with_reason(raw_dir: Path) -> None:
    from app.core.contracts_gen import RawDocument as RawDTO

    _r4b.install(raw_dir)
    sha, rel = _unitless_text(raw_dir)
    r = {**_r4b.row(N1, NOTICE_ID), "sha256": sha, "text_path": rel, "table_path": None}
    cands = NoticeParser(raw_dir=raw_dir).parse(RawDTO.model_validate({**r, "region_id": 1, "complex_id": None}))
    c = _by(cands, "complex_type", "max_price_won")["84A"]
    assert c.value == 617_000
    assert "단위 표기 없음" in (c.reason or ""), c.reason


def _cand(kind: str, rank: int, value: int, reason: str | None = None) -> FieldCandidate:
    return FieldCandidate.model_validate(
        {
            "entity": "complex_type", "entity_id": 7, "entity_key": "2025000253:84A", "field": "max_price_won",
            "value_text": f"{value:,}", "value": value, "source_rank": rank, "source_kind": kind, "primary": True,
            "label": "확인됨", "reason": reason, "excerpt": f"84A {value:,}", "raw_document_id": rank,
            "url": "https://example.invalid/", "checked_at": "2026-10-12", "observed_on": "2025-07-04",
            "needs_extract": False,
        }
    )  # fmt: skip


def test_resolver_holds_tenfold_apart_primary_sources_for_compare() -> None:
    """단위 없는 공고문(rank 1) 617,000 vs 청약홈(rank 2) 617,000,000 — 순위로 채택하지 않고 compare 대기(보류)."""
    notice = _cand("notice_pdf", 1, 617_000, "단위 표기 없음 — 원으로 봄")
    api = _cand("applyhome_detail", 2, 617_000_000)
    res = resolve([notice, api])
    assert res.needs_compare, "10배 이상 다른 1차 출처 → compare"
    assert res.chosen[0].value is None and res.chosen[0].label == "확인 불가"
    # 같은 크기(단위 환산이 맞음)면 그대로 순위 규칙(rank 1 공고문 채택, compare 없음)
    ok = resolve([_cand("notice_pdf", 1, 617_000_000), _cand("applyhome_detail", 2, 617_100_000)])
    assert not ok.needs_compare and ok.chosen[0].value == 617_000_000


# ---------------------------------------------------------------- 저장·compare 흐름 (실데이터 재생)


def _store(session: Session, raw_dir: Path, *, unitless: bool) -> int:
    _r4b.install(raw_dir)
    for dto in _r4b.insert(session, _r4b.rows(N1, API_IDS), region_id=session.scalars(select(Region.id)).one()):
        store_raw_document(session, dto, raw_dir=raw_dir)
    notice = dict(_r4b.row(N1, NOTICE_ID))
    if unitless:
        sha, rel = _unitless_text(raw_dir)
        notice.update(sha256=sha, text_path=rel, table_path=None)
    (dto,) = _r4b.insert(session, [notice], region_id=session.scalars(select(Region.id)).one())
    store_raw_document(session, dto, raw_dir=raw_dir)
    session.flush()
    cx = session.scalars(select(Complex).where(Complex.applyhome_id == "2025000253")).one()
    return cx.id


def _type(session: Session, cid: int, code: str) -> ComplexType:
    return session.scalars(
        select(ComplexType).where(ComplexType.complex_id == cid, ComplexType.type_code == code)
    ).one()


def _pbt(session: Session, cid: int) -> dict[str, Any]:
    pt = session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == cid)).one()
    return dict(pt.price_by_type or {})


def test_store_thousand_won_notice_agrees_with_api(db_session: Session, raw_dir: Path, region: Region) -> None:
    cid = _store(db_session, raw_dir, unitless=False)
    t = _type(db_session, cid, "84A")
    assert t.max_price_won == 617_000_000
    assert _pbt(db_session, cid)["84A"]["max_price_won"] == 617_000_000
    groups = db_session.scalars(
        select(FieldProvenance.conflict_group).where(
            FieldProvenance.entity == "complex_type", FieldProvenance.entity_id == t.id,
            FieldProvenance.field == "max_price_won",
        )
    ).all()  # fmt: skip
    assert set(groups) == {None}, "단위 환산이 맞으면 상충이 없다"


def test_store_unitless_notice_is_held_then_compare_same_fact_adopts_api(
    db_session: Session, raw_dir: Path, region: Region
) -> None:
    from app.normalize.judged import apply_compare

    cid = _store(db_session, raw_dir, unitless=True)
    t = _type(db_session, cid, "84A")
    assert t.max_price_won is None, "10배 이상 다른 1차 출처 — 순위(공고문 rank 1)로 채택하지 않는다"
    assert _pbt(db_session, cid)["84A"].get("max_price_won") is None, "그 공고의 타입 가격도 보류(현재 구매가에 쓰이지 않음)"
    group = f"complex_type:{t.id}:max_price_won"
    res = apply_compare(db_session, group, relation="same_fact", judgment_seq=None)
    assert res.changed
    db_session.flush()
    assert _type(db_session, cid, "84A").max_price_won == 617_000_000, "same_fact → 단위가 분명한 청약홈 값"


@pytest.mark.parametrize("relation", ["contradicts", "different_facts"])
def test_store_unitless_notice_stays_held_unless_same_fact(
    db_session: Session, raw_dir: Path, region: Region, relation: str
) -> None:
    from app.normalize.judged import apply_compare

    cid = _store(db_session, raw_dir, unitless=True)
    t = _type(db_session, cid, "84A")
    apply_compare(db_session, f"complex_type:{t.id}:max_price_won", relation=relation, judgment_seq=None)
    db_session.flush()
    assert _type(db_session, cid, "84A").max_price_won is None, "단위 상충은 same_fact 가 아니면 보류(공고문 617,000 채택 금지)"


def test_p5_compares_tenfold_apart_rivals_across_ranks(
    db_session: Session, raw_dir: Path, region: Region, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models import Snapshot
    from app.scheduler import persist, pipeline

    cid = _store(db_session, raw_dir, unitless=True)
    snap = Snapshot(region_id=region.id, asof_date="2026-10-12", status="building", created_at="2026-10-12T06:00:00+09:00")
    db_session.add(snap)
    db_session.flush()
    seen: list[str] = []

    def fake_compare(_caller: Any, a: str, b: str, **kw: Any) -> Any:
        seen.append(str(kw.get("purpose")))
        return SimpleNamespace(resolved=True, relation="same_fact", envelope=SimpleNamespace(judgment_seq=None))

    monkeypatch.setattr(pipeline.jp, "p5_compare", fake_compare)
    pipeline._p5(db_session, None, snap, {cid}, persist.SeqResolver(db_session))  # type: ignore[arg-type]
    t = _type(db_session, cid, "84A")
    assert f"compare:complex_type:{t.id}:max_price_won" in seen, "rank 가 달라도 10배 이상 다르면 compare"
    assert _type(db_session, cid, "84A").max_price_won == 617_000_000

