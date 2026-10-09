"""P5(R3 M1, F1b 요청 — F3 위임): compare 가 same_fact·different_facts 여도 apply_compare 를 부른다.

채택 보류(같은 rank 1차·1차 상충)는 compare 결과로만 풀린다 — contradicts 만 반영하던 P5 는 same_fact 그룹을
영원히 보류 상태로 남겼다. review(미해결)는 그대로 보류.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Complex, FieldProvenance, Snapshot
from app.scheduler import persist, pipeline


def _group(s: Session, cid: int) -> str:
    group = f"complex:{cid}:units_total"
    for value, chosen in (("1573", True), ("1769", False)):
        s.add(
            FieldProvenance(
                entity="complex", entity_id=cid, field="units_total", value_text=value, label="확인됨",
                source_rank=1, chosen=chosen, conflict_group=group, excerpt=f"총 {value}세대",
                checked_at="2026-10-08",
            )
        )  # fmt: skip
    s.flush()
    return group


@pytest.mark.parametrize(("relation", "applied"), [("same_fact", True), ("different_facts", True),
                                                   ("contradicts", True), (None, False)])  # fmt: skip
def test_p5_applies_compare_for_every_resolved_relation(
    factory: sessionmaker[Session],
    seeded: int,
    monkeypatch: pytest.MonkeyPatch,
    relation: str | None,
    applied: bool,
) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_compare(_caller: Any, _a: str, _b: str, **_kw: Any) -> Any:
        return SimpleNamespace(
            resolved=relation is not None, relation=relation, envelope=SimpleNamespace(judgment_seq=None)
        )

    def spy(_session: Any, group: str, *, relation: str | None, **_kw: Any) -> Any:
        calls.append((group, relation))
        return SimpleNamespace(changed=False)

    monkeypatch.setattr(pipeline.jp, "p5_compare", fake_compare)
    monkeypatch.setattr(pipeline, "apply_compare", spy)
    with factory() as s:
        snap = s.get(Snapshot, seeded)
        cx = s.scalars(select(Complex).order_by(Complex.id)).first()
        assert snap is not None and cx is not None
        group = _group(s, cx.id)
        n = pipeline._p5(s, None, snap, {cx.id}, persist.SeqResolver(s))  # type: ignore[arg-type]
        assert n >= 1
        assert calls == ([(group, relation)] if applied else [])
        s.rollback()
