"""0016 r4core10 — 계약 2026-10-09.18 (R4 4차 재시험 N13 · DECISIONS D23-2)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-13

계약 마이그레이션 — 계약 .18 소유자(R4-CORE10)가 추가한다. contracts/CHANGELOG.md 2026-10-09.18 항목.
**앱 코드를 import 하지 않는다**(D14-9). 스키마 변경 없음 — **데이터 마이그레이션**만.

| 변경 | 내용 | 결정 |
| --- | --- | --- |
| competition.type_code 의 뜻 | 그 시점의 단지 주택형과 대조한 코드 → **원 면적 코드**(파서가 원문 주택형에서 만든 코드 = 경쟁률 출처 행 ``entity_key`` 의 넷째 칸 '<주택관리번호>:<구분>:<회차>:<원 코드>'). 행 식별 = (단지, 구분, 회차, 원 코드). 표시 주택형은 읽기 시점(``app.normalize.competition``) | D23-2 |
| 중복 경쟁률 행 정리 | 같은 (단지, 구분, 회차, 원 코드) 행이 여럿이면(R4 4차 N13 — 같은 원문 재정규화가 대조 코드로 새 행을 만듦) 가장 앞 행(id 최소)만 남긴다. 값(공급·접수·비율)은 가장 늦게 쓴 행(id 최대) 값. 지우는 행의 출처 행은 남는 행에 같은 출처(원문·필드·값 표기·발췌 위치·라벨)가 있으면 지우고 없으면 남는 행으로 옮긴다(상충 묶음 이름도). 필드마다 chosen 은 가장 늦은 chosen 출처 행 하나. change_event·fact_demotion·human_check 의 (competition, 지운 id) 는 남는 id 로 | D23-2 |

출처 행이 없는(원 코드를 모르는) 경쟁률 행은 type_code 를 그대로 둔다. 발행 리비전 저장본(``snapshot_view``)은 건드리지 않는다
(D11-1 불변 — 이미 발행된 R4 4차 리비전 5·6 의 중복 행은 그 저장본에 남는다).

downgrade: 데이터는 되돌리지 않는다(지운 중복 행은 복원하지 않고 type_code 도 원 코드로 둔다 — 0015 앱은 원 코드 행을 그대로 읽는다).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMP = sa.table(
    "competition",
    sa.column("id", sa.Integer),
    sa.column("complex_id", sa.Integer),
    sa.column("kind", sa.String),
    sa.column("round", sa.String),
    sa.column("type_code", sa.String),
    sa.column("supply", sa.Integer),
    sa.column("applied", sa.Integer),
    sa.column("ratio_or_shortfall_text", sa.String),
)
_FP = sa.table(
    "field_provenance",
    sa.column("id", sa.Integer),
    sa.column("entity", sa.String),
    sa.column("entity_id", sa.Integer),
    sa.column("entity_key", sa.String),
    sa.column("field", sa.String),
    sa.column("value_text", sa.String),
    sa.column("raw_document_id", sa.Integer),
    sa.column("excerpt_start", sa.Integer),
    sa.column("label", sa.String),
    sa.column("chosen", sa.Boolean),
    sa.column("conflict_group", sa.String),
)
_REFS = ("change_event", "fact_demotion", "human_check")
"""(entity, entity_id) 로 경쟁률 행을 가리킬 수 있는 테이블."""


def _original_codes(bind: Any) -> dict[int, str]:
    """경쟁률 행 id → 원 면적 코드(그 행 원문 출처 행 중 가장 앞 행의 entity_key 넷째 칸)."""
    out: dict[int, str] = {}
    for eid, key in bind.execute(
        sa.select(_FP.c.entity_id, _FP.c.entity_key)
        .where(
            _FP.c.entity == "competition",
            _FP.c.raw_document_id.is_not(None),
            _FP.c.entity_key.is_not(None),
        )
        .order_by(_FP.c.id)
    ):
        parts = str(key).split(":")
        if eid is not None and len(parts) == 4 and parts[3] and eid not in out:
            out[int(eid)] = parts[3][:16]
    return out


def _source(r: Any) -> tuple[Any, ...]:
    return (r.field, r.raw_document_id, r.value_text or "", r.excerpt_start, r.label)


def _merge(bind: Any, keep: Any, dups: list[Any]) -> None:
    latest = dups[-1]
    vals = {
        "supply": latest.supply,
        "applied": latest.applied,
        "ratio_or_shortfall_text": latest.ratio_or_shortfall_text,
    }
    bind.execute(sa.update(_COMP).where(_COMP.c.id == keep.id).values(**vals))
    have = {
        _source(r)
        for r in bind.execute(sa.select(_FP).where(_FP.c.entity == "competition", _FP.c.entity_id == keep.id))
    }
    for d in dups:
        for r in list(
            bind.execute(
                sa.select(_FP)
                .where(_FP.c.entity == "competition", _FP.c.entity_id == d.id)
                .order_by(_FP.c.id)
            )
        ):
            if _source(r) in have:
                bind.execute(sa.delete(_FP).where(_FP.c.id == r.id))
                continue
            have.add(_source(r))
            group = r.conflict_group
            if group is not None and group.startswith(f"competition:{d.id}:"):
                group = f"competition:{keep.id}:{group.split(':', 2)[2]}"
            bind.execute(
                sa.update(_FP).where(_FP.c.id == r.id).values(entity_id=keep.id, conflict_group=group)
            )
        for table in _REFS:
            t = sa.table(table, sa.column("entity", sa.String), sa.column("entity_id", sa.Integer))
            bind.execute(
                sa.update(t)
                .where(t.c.entity == "competition", t.c.entity_id == d.id)
                .values(entity_id=keep.id)
            )
        bind.execute(sa.delete(_COMP).where(_COMP.c.id == d.id))
    # 필드마다 chosen 하나 — 가장 늦은 chosen 출처 행(가장 늦게 쓴 행의 채택)
    chosen: dict[str, list[int]] = defaultdict(list)
    for r in bind.execute(
        sa.select(_FP.c.id, _FP.c.field)
        .where(_FP.c.entity == "competition", _FP.c.entity_id == keep.id, _FP.c.chosen.is_(True))
        .order_by(_FP.c.id)
    ):
        chosen[r.field].append(r.id)
    for ids in chosen.values():
        if len(ids) > 1:
            bind.execute(sa.update(_FP).where(_FP.c.id.in_(ids[:-1])).values(chosen=False))


def upgrade() -> None:
    bind = op.get_bind()
    orig = _original_codes(bind)
    rows = list(bind.execute(sa.select(_COMP).order_by(_COMP.c.id)))
    groups: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    for r in rows:
        groups[(r.complex_id, r.kind, r.round, orig.get(r.id, r.type_code))].append(r)
    changed: list[tuple[int, str]] = []
    for (_cid, _kind, _round, code), members in groups.items():
        if len(members) > 1:
            _merge(bind, members[0], members[1:])
        if members[0].type_code != code:
            changed.append((members[0].id, code))
    # 원 코드로 — 두 단계(행끼리 잠시 겹치는 (단지·구분·회차·코드) 유일 제약을 피한다)
    for i, _code in changed:
        bind.execute(sa.update(_COMP).where(_COMP.c.id == i).values(type_code=f"~{i}"[:16]))
    for i, code in changed:
        bind.execute(sa.update(_COMP).where(_COMP.c.id == i).values(type_code=code))


def downgrade() -> None:
    """데이터는 되돌리지 않는다(모듈 설명)."""
