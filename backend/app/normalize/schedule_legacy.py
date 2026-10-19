"""옛 파서 모양 접수 일정 다시 읽기 (D33-1).

R9-PARSE 전 파서는 ``complex.apply_dates`` 를 ``[{kind, date}]``(시작일만)로 저장했다. 지금 파서는 ``[{kind, start, end}]``
(기간)다. 지난 공고는 청약홈 원문을 다시 받지 않아(같은 URL 성공 원문 재사용) 지금 파서로 다시 읽힐 기회가 없었다.
일일 수집이 이 함수를 불러, 옛 모양이 남은 단지의 **채택된 출처 원문**을 지금 파서로 읽고 그 단지의 접수 일정 값과 채택
출처 행 하나만 고친다(원문 전체를 다시 저장하지 않는다 — 다른 출처 행·옛 파싱 표식은 건드리지 않는다). 값 모양만 바뀌므로
change_event·재판정을 만들지 않고 수만 센다.
한 번 바뀌면 그 단지는 다음 날부터 대상이 아니다. 문자열·저장 처리만 한다(판단 아님).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Complex, FieldProvenance, RawDocument

__all__ = ["LegacyReparse", "is_legacy_schedule", "legacy_apply_raw_ids", "reparse_legacy_apply_dates"]


def is_legacy_schedule(items: object) -> bool:
    """옛 모양 항목(``date`` 만 있고 ``start`` 없음)이 하나라도 있다."""
    return isinstance(items, list) and any(
        isinstance(it, dict) and "date" in it and "start" not in it for it in items
    )


def legacy_apply_raw_ids(session: Session, region_id: int) -> list[int]:
    """지역 안 옛 모양 접수 일정 단지의 채택(chosen) 출처 원문 id."""
    ids: set[int] = set()
    for cx in session.scalars(select(Complex).where(Complex.region_id == region_id).order_by(Complex.id)):
        if not is_legacy_schedule(cx.apply_dates):
            continue
        ids.update(
            rid
            for rid in session.scalars(
                select(FieldProvenance.raw_document_id).where(
                    FieldProvenance.entity == "complex",
                    FieldProvenance.entity_id == cx.id,
                    FieldProvenance.field == "apply_dates",
                    FieldProvenance.chosen.is_(True),
                    FieldProvenance.raw_document_id.is_not(None),
                )
            )
            if rid is not None
        )
    return sorted(ids)


@dataclass
class LegacyReparse:
    complexes: int = 0  # 새 모양으로 바꾼 단지 수
    skipped: int = 0  # 원문을 지금 파서로 읽어도 새 모양 값이 없는 단지
    errors: list[str] = field(default_factory=list)

    def stats(self) -> dict[str, object]:
        return {
            "complexes": self.complexes,
            "skipped": self.skipped,
            **({"errors": self.errors} if self.errors else {}),
        }


def reparse_legacy_apply_dates(session: Session, region_id: int) -> LegacyReparse:
    """옛 모양 단지마다 채택된 출처 원문을 지금 파서로 읽어 **그 단지의 apply_dates 후보 하나만** 반영한다 — 단지 값과 그
    채택 출처 행(value_text·value_norm·발췌)만 바꾸고, 원문 전체를 다시 저장하지 않는다(다른 출처 행·표식은 그대로).
    값 모양만 바뀌므로 change_event 를 만들지 않는다. commit 은 호출자."""
    from app.normalize.fields import norm_value
    from app.normalize.store import parser_for, raw_dto

    out = LegacyReparse()
    for cx in session.scalars(select(Complex).where(Complex.region_id == region_id).order_by(Complex.id)):
        if not is_legacy_schedule(cx.apply_dates):
            continue
        fp = session.scalars(
            select(FieldProvenance)
            .where(
                FieldProvenance.entity == "complex",
                FieldProvenance.entity_id == cx.id,
                FieldProvenance.field == "apply_dates",
                FieldProvenance.chosen.is_(True),
                FieldProvenance.raw_document_id.is_not(None),
            )
            .order_by(FieldProvenance.id.desc())
        ).first()
        row = session.get(RawDocument, fp.raw_document_id) if fp is not None and fp.raw_document_id else None
        parser = parser_for(row.source_kind) if row is not None else None
        if fp is None or row is None or row.path is None or row.http_status != 200 or parser is None:
            out.skipped += 1
            continue
        try:
            cands = parser.parse(raw_dto(row))
        except Exception as exc:  # 원문 1건 실패 — 기록하고 다음 단지(규칙 7: 삼키지 않고 남긴다)
            out.errors.append(f"rd{row.id}:{type(exc).__name__}")
            continue
        cand = next(
            (
                c
                for c in cands
                if c.entity == "complex"
                and c.field == "apply_dates"
                and c.value is not None
                and (c.entity_id == cx.id or (c.entity_key is not None and c.entity_key == cx.applyhome_id))
            ),
            None,
        )
        value = json.loads(cand.value) if cand is not None and isinstance(cand.value, str) else None
        if cand is None or not value or is_legacy_schedule(value):
            out.skipped += 1
            continue
        cx.apply_dates = value
        fp.value_text = cand.value_text
        fp.value_norm = norm_value(cand.value)
        fp.excerpt = cand.excerpt
        fp.excerpt_start, fp.excerpt_end = cand.excerpt_start, cand.excerpt_end
        out.complexes += 1
    session.flush()
    return out
