"""상충 해결 (WP2, RA §3 표 · §4-3 ``Resolver``).

(entity, entity_id|entity_key, field)마다 후보 하나를 chosen으로 정하고,
모든 후보를 field_provenance 행으로 돌려준다.

정하는 순서(우선순위 규칙이지 판단이 아니다)
1. 값이 있는 후보가 값 없는 후보('확인 불가', needs_extract)보다 앞선다.
2. source_rank 오름차순(§3 표: app.normalize.fields.source_rank).
3. 1차(primary) 자료가 2차보다 앞선다.
4. 같은 출처 종류끼리는 최신이 앞선다(checked_at → raw_document_id 내림차순) — '공고문 최신' 규칙.

상충(conflict_group): 값이 다른 후보가 둘 이상이면 '<entity>:<id 또는 key>:<field>'로 묶는다.
needs_compare: chosen과 값이 다르면서 같은 source_rank인 1차 후보가 **다른 출처 종류**일 때만 true
(같은 rank의 1차·1차 상충 — 우선순위로 가를 수 없음). 같은 출처 종류는 최신 규칙으로 가르고, rank가 다르면
rank 1 채택(T5: 청약홈 상세 1,573 vs 공고문 1,769 → compare 없음), 둘 다 2차면 병기하고 판정 미사용.
판정기는 부르지 않는다 — needs_compare 그룹의 compare는 WP3가 부른다.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Hashable, Iterable
from decimal import Decimal, InvalidOperation

from app.core.contracts_gen import ConflictGroup, FieldCandidate, ProvenanceRow, ResolvedFields
from app.normalize.fields import rule_text

__all__ = ["PriorityResolver", "group_key", "resolve", "same_value", "to_provenance_row"]

GroupKey = tuple[str, str, str]


def group_key(c: FieldCandidate) -> GroupKey:
    """(entity, 'id:<n>' 또는 'key:<k>', field). entity_id가 있으면 id가 이긴다."""
    ident = f"id:{c.entity_id}" if c.entity_id is not None else f"key:{c.entity_key or ''}"
    return (c.entity, ident, c.field)


def _norm(v: float | str | bool | None) -> Hashable:
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        try:
            return Decimal(str(v)).normalize()
        except InvalidOperation:  # pragma: no cover - nan/inf
            return str(v)
    s = " ".join(str(v).split())
    try:
        return Decimal(s.replace(",", "")).normalize()
    except InvalidOperation:
        return s


def same_value(a: FieldCandidate, b: FieldCandidate) -> bool:
    return _norm(a.value) == _norm(b.value)


def _has_value(c: FieldCandidate) -> bool:
    return c.value is not None and c.label != "확인 불가"


def _priority(c: FieldCandidate) -> tuple[int, int, int]:
    return (0 if _has_value(c) else 1, c.source_rank, 0 if (c.primary is None or c.primary) else 1)


def _ordered(cands: list[tuple[int, FieldCandidate]]) -> list[tuple[int, FieldCandidate]]:
    # 1) 최신순(checked_at → raw_document_id 내림차순, 같으면 입력 순서) → 2) 우선순위로 안정 정렬
    by_recent = sorted(
        cands, key=lambda oc: (oc[1].checked_at or "", oc[1].raw_document_id or 0, -oc[0]), reverse=True
    )
    return sorted(by_recent, key=lambda oc: _priority(oc[1]))


def to_provenance_row(c: FieldCandidate, *, chosen: bool, conflict_group: str | None) -> ProvenanceRow:
    return ProvenanceRow(
        id=None,
        entity=c.entity,
        entity_id=c.entity_id,
        entity_key=c.entity_key,
        field=c.field,
        value_text=c.value_text,
        raw_document_id=c.raw_document_id,
        url=c.url,
        checked_at=c.checked_at,
        label=c.label,
        reason=c.reason,
        source_rank=c.source_rank,
        chosen=chosen,
        conflict_group=conflict_group,
        excerpt=c.excerpt,
        excerpt_start=c.excerpt_start,
        excerpt_end=c.excerpt_end,
    )


def _resolve_group(
    gk: GroupKey, items: list[tuple[int, FieldCandidate]]
) -> tuple[FieldCandidate, list[ProvenanceRow], ConflictGroup | None]:
    ordered = _ordered(items)
    chosen = ordered[0][1]
    valued = [c for _, c in ordered if _has_value(c)]
    distinct: list[FieldCandidate] = []
    for c in valued:
        if not any(same_value(c, d) for d in distinct):
            distinct.append(c)
    entity, ident, field = gk
    conflict: ConflictGroup | None = None
    group_id: str | None = None
    if len(distinct) > 1:
        group_id = f"{entity}:{ident.split(':', 1)[1]}:{field}"
        rivals = [c for c in valued if not same_value(c, chosen) and c.source_rank == chosen.source_rank]
        chosen_primary = chosen.primary is None or chosen.primary
        needs_compare = bool(
            chosen_primary
            and any((r.primary is None or r.primary) and r.source_kind != chosen.source_kind for r in rivals)
        )
        all_secondary = all(not (c.primary is None or c.primary) for c in valued)
        rule = rule_text(entity, field)
        if needs_compare:
            rule = f"{rule} / 같은 rank 1차·1차 상충 → compare 필요(임시 채택: 최신)"
        elif all_secondary:
            rule = f"{rule} / 둘 다 2차 → 병기, 판정 미사용"
        elif rivals:
            rule = f"{rule} / 같은 출처 종류 → 최신 채택"
        cands = [c for _, c in ordered if _has_value(c)]
        conflict = ConflictGroup(
            conflict_group=group_id,
            entity=entity,
            entity_id=chosen.entity_id,
            entity_key=chosen.entity_key,
            field=field,
            candidates=cands,
            chosen_index=0,
            needs_compare=needs_compare,
            rule=rule,
        )
    rows = [to_provenance_row(c, chosen=(c is chosen), conflict_group=group_id) for _, c in items]
    return chosen, rows, conflict


def resolve(candidates: Iterable[FieldCandidate]) -> ResolvedFields:
    groups: OrderedDict[GroupKey, list[tuple[int, FieldCandidate]]] = OrderedDict()
    for i, c in enumerate(candidates):
        groups.setdefault(group_key(c), []).append((i, c))
    chosen: list[FieldCandidate] = []
    prov: list[ProvenanceRow] = []
    conflicts: list[ConflictGroup] = []
    for gk, items in groups.items():
        ch, rows, conflict = _resolve_group(gk, items)
        chosen.append(ch)
        prov.extend(rows)
        if conflict is not None:
            conflicts.append(conflict)
    return ResolvedFields(
        chosen=chosen,
        provenance=prov,
        conflicts=conflicts,
        needs_compare=any(c.needs_compare for c in conflicts),
    )


class PriorityResolver:
    """``Resolver`` 구현 (RA §3 우선순위)."""

    def resolve(self, candidates: list[FieldCandidate]) -> ResolvedFields:
        return resolve(candidates)
