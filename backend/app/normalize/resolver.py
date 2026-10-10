"""상충 해결 (WP2, RA §3 표 · §4-3 ``Resolver``).

(entity, entity_id|entity_key, field)마다 후보 하나를 chosen으로 정하고,
모든 후보를 field_provenance 행으로 돌려준다.

정하는 순서(우선순위 규칙이지 판단이 아니다)
1. 값이 있는 후보가 값 없는 후보('확인 불가', needs_extract)보다 앞선다.
2. source_rank 오름차순(§3 표: app.normalize.fields.source_rank).
3. 1차(primary) 자료가 2차보다 앞선다.
4. 같은 출처 종류끼리는 최신이 앞선다(observed_on = 원문 시점·공고일 → checked_at → raw_document_id
   내림차순) — '공고문 최신' 규칙. observed_on 이 없는 후보(옛 출처)는 가장 오래된 것으로 본다.

상충(conflict_group): 값이 다른 후보가 둘 이상이면 '<entity>:<id 또는 key>:<field>'로 묶는다.
needs_compare: chosen과 값이 다르면서 같은 source_rank인 1차 후보가 **다른 출처 종류**일 때만 true
(같은 rank의 1차·1차 상충 — 우선순위로 가를 수 없음). 같은 출처 종류는 최신 규칙으로 가르고, rank가 다르면
rank 1 채택(T5: 청약홈 상세 1,573 vs 공고문 1,769 → compare 없음), 둘 다 2차면 병기하고 판정 미사용.
판정기는 부르지 않는다 — needs_compare 그룹의 compare는 WP3가 부른다.

같은 rank 1차·1차 상충 = **채택 보류**(R3 M1, RA §3 "우선순위 없음 → compare"):
- 우선순위로 고른 대표 후보(최신)를 출처 행 chosen=true 로 두되(P5 가 compare 할 상대를 찾는 기준),
  ``ResolvedFields.chosen`` 에는 값 없는 '확인 불가' 후보(reason ``CONFLICT_HOLD``)를 낸다 → 사실 테이블 값을
  비운다(점수 미사용). 대표 출처 행 reason 앞에도 ``CONFLICT_HOLD`` 를 붙인다(화면 '확인 불가(출처 상충 …)').
- compare 결과로만 채택한다: ``normalize.judged.apply_compare`` 가 출처 행 reason 에 ``COMPARE_ADOPTED``·
  ``COMPARE_SIDE`` 표식을 남기고, 여기서는 그 표식이 있는 후보를 채택한다. 표식 없는 새 1차 상대가 생기면
  다시 보류한다(새 상충 = compare 필요).

사람 확인(source_rank 0 — ``api.demotion.apply_human_check``, D11-3·**D12-1**):
- 그 시점까지 관측된 출처를 모두 이긴다 — compare 채택(``COMPARE_ADOPTED``)도 이기지 못한다(R3 4차 C-2).
- 사람 확인 **이후에** 관측된(observed_on > 사람 확인일) 공식 1차 출처(공고문·청약홈,
  ``OFFICIAL_SOURCES``)가 **다른 값**을 내면 그 값이 채택된다(그 뒤 출처끼리는 위 규칙 그대로).
  저장(``normalize.store``)이 critical change_event 와 체크리스트 '사람 확인 재검토'를 남긴다(M-10).

OCR 판독 후보(label '추정' + reason 'OCR', R3 C3)는 같은 원문의 판정기 추출 행(reason '판정기 추출 …'·
'판정기 감사 flagged …')이 생기면 값 없는 후보로 본다 — 판정기 결과(채택·감사 flagged·review)가
OCR 값을 대신한다.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Hashable, Iterable
from decimal import Decimal, InvalidOperation

from app.core.contracts_gen import ConflictGroup, FieldCandidate, ProvenanceRow, ResolvedFields
from app.normalize.fields import (
    AUDIT_FLAG_REASON,
    COMPARE_ADOPTED,
    COMPARE_SIDE,
    CONFLICT_HOLD,
    EXTRACT_REASON,
    has_tag,
    is_ocr,
    norm_value,
    rule_text,
    strip_tags,
    with_tag,
)

__all__ = [
    "OFFICIAL_SOURCES",
    "PriorityResolver",
    "group_key",
    "is_human_candidate",
    "resolve",
    "same_value",
    "to_provenance_row",
]

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


def _is_primary(c: FieldCandidate) -> bool:
    return c.primary is None or c.primary


def _priority(c: FieldCandidate) -> tuple[int, int, int]:
    return (0 if _has_value(c) else 1, c.source_rank, 0 if _is_primary(c) else 1)


OFFICIAL_SOURCES = frozenset({"notice_pdf", "applyhome_detail", "applyhome_list"})
"""D12-1 '공식 1차 출처'(공고문·청약홈) — 사람 확인 이후 이 출처가 다른 값을 내면 그 값이 채택된다."""


def is_human_candidate(c: FieldCandidate) -> bool:
    """사람 확인 후보(source_rank 0, D11-3)."""
    return c.source_rank == 0


def _is_official(c: FieldCandidate) -> bool:
    return _is_primary(c) and c.source_kind in OFFICIAL_SOURCES and c.source_rank > 0


def _observed_after(c: FieldCandidate, human: FieldCandidate) -> bool:
    """c 가 사람 확인 **이후에** 관측됐는가(observed_on > 사람 확인일, 같은 날은 이후가 아니다)."""
    return bool(c.observed_on) and (c.observed_on or "") > (human.observed_on or human.checked_at or "")[:10]


def _is_judged(c: FieldCandidate) -> bool:
    return (strip_tags(c.reason) or "").startswith((EXTRACT_REASON, AUDIT_FLAG_REASON))


def _demote_superseded_ocr(cands: list[tuple[int, FieldCandidate]]) -> list[tuple[int, FieldCandidate]]:
    """같은 원문에 판정기 추출 행이 있으면 그 원문의 OCR 판독 후보는 값 없는 후보로(채택 안 됨)."""
    judged_raw = {c.raw_document_id for _, c in cands if _is_judged(c)}
    if not judged_raw:
        return cands
    out: list[tuple[int, FieldCandidate]] = []
    for i, c in cands:
        if c.raw_document_id in judged_raw and is_ocr(c.label, c.reason) and not _is_judged(c):
            c = c.model_copy(update={"value": None, "label": "확인 불가"})
        out.append((i, c))
    return out


def _ordered(cands: list[tuple[int, FieldCandidate]]) -> list[tuple[int, FieldCandidate]]:
    # 1) 최신순(observed_on → checked_at → raw_document_id 내림차순, 같으면 입력 순서)
    # 2) 우선순위로 안정 정렬
    by_recent = sorted(
        cands,
        key=lambda oc: (
            oc[1].observed_on or "",
            oc[1].checked_at or "",
            oc[1].raw_document_id or 0,
            -oc[0],
        ),
        reverse=True,
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
        value_norm=norm_value(c.value),
        observed_on=c.observed_on,
    )


def _resolve_group(
    gk: GroupKey, items: list[tuple[int, FieldCandidate]]
) -> tuple[FieldCandidate, list[ProvenanceRow], ConflictGroup | None]:
    view = _demote_superseded_ocr(items)
    original = {id(v): c for (_, v), (_, c) in zip(view, items, strict=True)}
    ordered = _ordered(view)
    lead = ordered[0][1]
    valued = [c for _, c in ordered if _has_value(c)]
    distinct: list[FieldCandidate] = []
    for c in valued:
        if not any(same_value(c, d) for d in distinct):
            distinct.append(c)
    entity, ident, field = gk
    conflict: ConflictGroup | None = None
    group_id: str | None = None
    held = False
    human = lead if is_human_candidate(lead) and _has_value(lead) else None
    superseded = False
    pool = valued
    if human is not None:
        # D12-1: 사람 확인은 그 시점까지 관측된 출처를 이긴다(compare 채택 포함 — C-2).
        # 사람 확인 **이후에** 관측된 공식 1차 출처가 다른 값을 내면 그 값을 채택한다
        # (그 뒤의 출처끼리만 우선순위·상충 규칙)
        after = [c for c in valued if c is not human and _observed_after(c, human)]
        newer = [c for c in after if _is_official(c) and not same_value(c, human)]
        if newer:
            superseded = True
            lead = newer[0]
            pool = after
    if len(distinct) > 1:
        group_id = f"{entity}:{ident.split(':', 1)[1]}:{field}"
        adopted = (
            [c for c in pool if has_tag(c.reason, COMPARE_ADOPTED)] if human is None or superseded else []
        )
        if adopted:
            lead = adopted[0]
        rivals = (
            [c for c in pool if not same_value(c, lead) and c.source_rank == lead.source_rank]
            if human is None or superseded
            else []
        )
        compare_rivals = [r for r in rivals if _is_primary(r) and r.source_kind != lead.source_kind]
        pending = [
            r
            for r in compare_rivals
            if not adopted or not (has_tag(r.reason, COMPARE_SIDE) or has_tag(r.reason, COMPARE_ADOPTED))
        ]
        held = _is_primary(lead) and bool(pending)
        all_secondary = all(not _is_primary(c) for c in valued)
        rule = rule_text(entity, field)
        if superseded:
            rule = f"{rule} / 사람 확인 이후 공식 1차 출처가 다른 값 → 새 값 채택(사람 확인 재검토, D12-1)"
        elif human is not None:
            rule = f"{rule} / 사람 확인(0순위) 채택 — 그 이전 출처·compare 채택보다 우선(D12-1)"
        if held:
            rule = f"{rule} / 같은 rank 1차·1차 상충 → 채택 보류(점수 미사용), compare 결과로만 채택"
        elif adopted:
            rule = f"{rule} / 같은 rank 1차·1차 상충 → compare 결과 채택·병기"
        elif all_secondary:
            rule = f"{rule} / 둘 다 2차 → 병기, 판정 미사용"
        elif rivals:
            rule = f"{rule} / 같은 출처 종류 → 최신 채택"
        cands = [lead, *(c for c in valued if c is not lead)]
        conflict = ConflictGroup(
            conflict_group=group_id,
            entity=entity,
            entity_id=lead.entity_id,
            entity_key=lead.entity_key,
            field=field,
            candidates=[original[id(c)] for c in cands],
            chosen_index=0,
            needs_compare=held,
            rule=rule,
        )
    rows: list[ProvenanceRow] = []
    for (_, v), (_, c) in zip(view, items, strict=True):
        reason = strip_tags(c.reason) if has_tag(c.reason, CONFLICT_HOLD) else c.reason
        if held and v is lead:
            reason = with_tag(c.reason, CONFLICT_HOLD)
        row = to_provenance_row(c, chosen=(v is lead), conflict_group=group_id)
        rows.append(row if row.reason == reason else row.model_copy(update={"reason": reason}))
    chosen = original[id(lead)]
    if held:
        chosen = chosen.model_copy(
            update={"value": None, "label": "확인 불가", "reason": CONFLICT_HOLD, "needs_extract": False}
        )
    elif lead is not chosen:  # 판정기 결과로 값을 잃은 OCR 후보가 대표 → 값 없음
        chosen = lead
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
