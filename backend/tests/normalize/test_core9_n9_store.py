"""R4 3차 재시험 N9(critical, D22-1) — 저장 단위: 같은 공고문을 다시 정규화해도 판정기 추출 출처 행이 chosen 으로 남고, 값이
실제로 바뀌면(파서가 이제 다른 값을 읽음) 판정 행은 내려가고 change_event 가 남는다. 녹화: ``r4c_core9`` 그룹 ``n9`` 중
중흥S-클래스(2025000253) — R4 3차 계약금 비율 판정기 추출(jl_241·감사 jl_242) 단지. 실데이터 흐름 재생은
``tests/scheduler/test_core9_n9_reextract.py``."""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FieldProvenance, PaymentTerms, RawDocument
from app.normalize.fields import EXTRACT_REASON
from app.normalize.store import store_raw_document

from . import _r4c


def _store_with_judged(
    db_session: Session, raw_dir: Any, region_id: int
) -> tuple[RawDocument, FieldProvenance]:
    """중흥S-클래스(2025000253) 원문 저장 → 계약금 비율 판정기 추출 적용(가짜 판정 seq) → (공고문 행, 추출 출처 행)."""
    from app.normalize.extract_request import build_extract_requests
    from app.normalize.judged import AuditMark, ExtractedValue, apply_extracted

    _r4c.install(raw_dir)
    rows = [r for r in _r4c.rows("n9") if _r4c.house_no(str(r["url"])) == "2025000253"]
    dtos = _r4c.insert(db_session, rows, region_id=region_id)
    out = None
    for d in dtos:
        res = store_raw_document(db_session, d, raw_dir=raw_dir)
        if d.source_kind == "notice_pdf":
            out = res
    assert out is not None
    reqs = [
        r
        for r in build_extract_requests([c for c in out.candidates if c.needs_extract])
        if "down_payment_pct" in r.fields
    ]
    assert reqs, "계약금 비율은 파서가 못 읽는다(판정기 추출 대상)"
    apply_extracted(
        db_session, reqs[0], [ExtractedValue("down_payment_pct", "10%", "auto")], judgment_seq=241,
        audit={"down_payment_pct": AuditMark(False, 0.05)}, audit_seq=242,
    )  # fmt: skip
    db_session.flush()
    pdf = db_session.get(RawDocument, out.raw_document_id)
    assert pdf is not None
    fp = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.field == "down_payment_pct", FieldProvenance.reason.startswith(EXTRACT_REASON)
        )
    ).one()
    assert fp.chosen and fp.label == "확인됨"
    return pdf, fp


def test_restore_same_notice_keeps_judged_row_chosen(db_session: Session, raw_dir: Any, region: Any) -> None:
    from app.normalize.store import raw_dto

    pdf, fp = _store_with_judged(db_session, raw_dir, region.id)
    pt = db_session.get(PaymentTerms, fp.entity_id)
    assert pt is not None and pt.down_payment_pct is not None
    res = store_raw_document(db_session, raw_dto(pdf), raw_dir=raw_dir)  # 같은 원문 재정규화(같은 날 재수집)
    db_session.flush()
    db_session.refresh(fp)
    assert fp.chosen and fp.label == "확인됨", (fp.chosen, fp.label, fp.reason)
    db_session.refresh(pt)
    assert format(pt.down_payment_pct.normalize(), "f") == "10"
    assert [(e.entity, e.field) for e in res.change_events] == []


def test_parser_value_change_on_renormalize_emits_change_event(
    db_session: Session, raw_dir: Any, region: Any
) -> None:
    """같은 원문이라도 파서가 이제 다른 값을 읽으면(파서 개선 등) 판정 행은 내려가고 값 변경 change_event 가 남는다(D22-1)."""
    from app.normalize.notice_parser import NoticeParser
    from app.normalize.store import raw_dto

    pdf, fp = _store_with_judged(db_session, raw_dir, region.id)

    class Improved:
        def __init__(self) -> None:
            self.inner = NoticeParser(raw_dir=raw_dir)

        def parse(self, raw: Any) -> list[Any]:
            out = []
            for c in self.inner.parse(raw):
                if c.entity == "payment_terms" and c.field == "down_payment_pct" and c.needs_extract:
                    c = c.model_copy(
                        update={
                            "value": 20.0,
                            "value_text": "계약금 20%",
                            "label": "확인됨",
                            "needs_extract": False,
                            "reason": None,
                        }
                    )
                out.append(c)
            return out

    res = store_raw_document(db_session, raw_dto(pdf), raw_dir=raw_dir, parser=Improved())
    db_session.flush()
    pt = db_session.get(PaymentTerms, fp.entity_id)
    assert pt is not None and format(pt.down_payment_pct.normalize(), "f") == "20"
    db_session.refresh(fp)
    assert not fp.chosen
    assert [(e.field, e.old_text, e.new_text) for e in res.change_events if e.entity == "payment_terms"] == [
        ("down_payment_pct", "10", "20")
    ]
