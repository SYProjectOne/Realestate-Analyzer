"""DB 행 → 계약 응답 모양(dict). 라우터는 이 함수들을 조합한다.

모든 수치는 ``facts.FactMaker`` 로만 Fact 가 된다
(출처 없는 수치는 dev 에서 예외, prod 에서 '확인 불가(출처 누락)').
목록 화면(G2)은 1,000단지에서도 1초 안에 돌도록 관련 행을 한 번에 읽고 페이지 안의 단지만 Fact 로 만든다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import functools
from collections import defaultdict, namedtuple
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, null, select
from sqlalchemy.orm import Session

from app.analysis import price_view as pv
from app.analysis import scope as scope_rules
from app.analysis.complex_input import build_complex_input, masked
from app.analysis.ladder import target_label
from app.api.facts import LABEL_UNKNOWN, FactMaker, ProvIndex, day, fact, num, round2, unknown
from app.core.contracts_gen import ComplexRow as ComplexRowDTO
from app.core.contracts_gen import ComplexScoreInput
from app.core.contracts_gen import ScoreRow as ScoreRowDTO
from app.models import (
    ChangeEvent,
    Competition,
    Complex,
    ComplexType,
    Decision,
    IntakeStatus,
    JudgmentLog,
    Ladder,
    LegalDong,
    PaymentTerms,
    Region,
    RemainingEvent,
    Scenario,
    ScoreComponent,
    ScoreRun,
    ScoreTotal,
    Snapshot,
)

__all__ = [
    "COMPONENT_ORDER",
    "HATCH_LABELS",
    "ComplexBundle",
    "ScoreCtx",
    "bundle_price",
    "complex_header",
    "complex_rows_data",
    "envelope_view",
    "intake_view",
    "judge_scope",
    "light_rows",
    "load_bundles",
    "pick_intake",
    "price_range",
    "region_view",
    "rejudge_needed",
    "scenario_view",
    "scope_result",
    "score_ctx",
    "score_price",
    "score_row",
    "shown_scope",
    "snapshot_view",
]

COMPONENT_ORDER = ("p10", "rerank", "gap", "benchmark", "supply", "liquidity", "move_in")
HATCH_LABELS = {
    "wait_new": "모집공고 대기",
    "ask_user": "사용자에게 질문",
    "investigate": "추가 조사",
    "none": "해당 없음",
}
_RAW_UNITS = {"p10": "prob", "rerank": "prob", "gap": "pct"}
# D10-1 '재판정 필요'(저장 범위 ≠ 현재 범위): 계약에 필드가 생기면(.6, G3) 응답에 싣고, 그 전에는 내부 플래그
# (``rejudge_needed``·``RowData.rejudge_needed``)만 — additionalProperties false 라 계약 밖 키를 내지 않는다.
_EMIT_REJUDGE_SCORE = "rejudge_needed" in ScoreRowDTO.model_fields
_EMIT_REJUDGE_ROW = "rejudge_needed" in ComplexRowDTO.model_fields


# ====================================================================== 지역·스냅샷·시나리오


def _legal_names(session: Session, codes: Iterable[str]) -> dict[str, LegalDong]:
    want = sorted(set(codes))
    out: dict[str, LegalDong] = {}
    for i in range(0, len(want), 500):
        for row in session.scalars(select(LegalDong).where(LegalDong.code.in_(want[i : i + 500]))):
            out[row.code] = row
    return out


def _dong_name(row: LegalDong | None, code: str) -> str:
    if row is None:
        return code
    parts = [p for p in (row.eupmyeondong_name, row.ri_name) if p]
    return " ".join(parts) or row.sigungu_name or row.full_name


def _households(stored: Any, aid: str, computed: Mapping[str, Any]) -> tuple[Any, Any]:
    """생활권 세대수 Fact. household_stat 집계가 있으면 그것, 없으면 저장된 Fact(없으면 null)."""
    hit = computed.get(aid)
    if hit and hit.get("households") and hit["households"].get("label") != LABEL_UNKNOWN:
        return hit["households"], hit.get("supply_ref_units")
    house = stored.get("households") if isinstance(stored, dict) else None
    ref = stored.get("supply_ref_units") if isinstance(stored, dict) else None
    if isinstance(house, dict) and house.get("label") == LABEL_UNKNOWN and not house.get("reason"):
        house = {**house, "reason": "값 없음"}
    return house, ref


def region_view(session: Session, region: Region, *, latest: Snapshot | None = None) -> dict[str, Any]:
    from app.normalize.living_area import region_household_facts

    areas = list(region.living_areas or [])
    names = _legal_names(session, (c for a in areas for c in a.get("legal_dong_codes") or []))
    try:
        computed = region_household_facts(session, region)
    except Exception:
        computed = {}
    living: list[dict[str, Any]] = []
    for a in areas:
        codes = [str(c) for c in a.get("legal_dong_codes") or []]
        house, ref = _households(a, str(a["id"]), computed)
        living.append(
            {
                "id": str(a["id"]),
                "name": str(a.get("name") or a["id"]),
                "legal_dong_codes": codes,
                "legal_dongs": [
                    {
                        "code": c,
                        "name": _dong_name(names.get(c), c),
                        "full_name": names[c].full_name if c in names else None,
                    }
                    for c in codes
                ],
                "households": house,
                "supply_ref_units": ref,
            }
        )
    coef = dict(region.age_premium_coef or {})
    coef.setdefault("c_per_year", 0.015)
    coef.setdefault("cap_years", 8)
    coef["label"] = "추정"
    return {
        "id": region.id,
        "name": region.name,
        "query_text": region.query_text,
        "selections": list(region.selections or []),
        "sido_codes": list(region.sido_codes or []),
        "sigungu_codes": list(region.sigungu_codes or []),
        "legal_dong_codes": list(region.legal_dong_codes or []),
        "living_areas": living,
        "age_premium_coef": {
            "c_per_year": float(coef["c_per_year"]),
            "cap_years": int(coef["cap_years"]),
            "label": "추정",
        },
        "supply_ref_pct": float(region.supply_ref_pct) if region.supply_ref_pct is not None else 0.08,
        "applyhome_query": dict(region.applyhome_query or {}),
        "status": region.status,
        "created_at": region.created_at,
        "latest_snapshot": snapshot_view(session, latest) if latest is not None else None,
    }


def area_names(region: Region | None) -> dict[str, str]:
    return {
        str(a["id"]): str(a.get("name") or a["id"]) for a in (region.living_areas if region else []) or []
    }


def snapshot_view(session: Session, snap: Snapshot) -> dict[str, Any]:
    # 남은 contradicted(분할 재검증 자식 없는 것)만 — publish·보고서와 같은 정의(계약 2026-10-09.4, R3 M8)
    from app.judge.claims import remaining_contradicted

    contradicted = len(remaining_contradicted(session, snap.id))
    ids: set[int] = set(
        session.scalars(select(IntakeStatus.complex_id).where(IntakeStatus.snapshot_id == snap.id).distinct())
    )
    ids |= set(session.scalars(select(Ladder.complex_id).where(Ladder.snapshot_id == snap.id).distinct()))
    ids |= {
        i
        for i in session.scalars(
            select(JudgmentLog.complex_id).where(JudgmentLog.snapshot_id == snap.id).distinct()
        )
        if i is not None
    }
    ids |= set(
        session.scalars(
            select(ScoreTotal.complex_id)
            .join(ScoreRun, ScoreRun.id == ScoreTotal.score_run_id)
            .where(ScoreRun.snapshot_id == snap.id)
            .distinct()
        )
    )
    return {
        "id": snap.id,
        "region_id": snap.region_id,
        "asof_date": snap.asof_date,
        "revision": int(snap.revision or 1),
        "revision_of": snap.revision_of,
        "revision_reason": snap.revision_reason,
        "status": snap.status,
        "degraded": bool(snap.degraded),
        "created_at": snap.created_at,
        "published_at": snap.published_at,
        "contradicted_claims": int(contradicted or 0),
        "complex_count": len(ids),
        **_backfill_meta(session, snap.id),
    }


def _backfill_meta(session: Session, snapshot_id: int) -> dict[str, Any]:
    """계약 .14(D17-2): 업그레이드 backfill 이 이 리비전에 **새로 계산해 채운** 저장본이 있으면 ``backfilled_at``(가장 늦은
    시각) — 화면 안내('업그레이드 때 다시 계산한 값 포함'). 없으면 키 자체를 넣지 않는다(발행 저장본 안의 이 객체 바이트가 그대로)."""

    from app.models import SnapshotViewUnit

    at = session.scalar(
        select(func.max(SnapshotViewUnit.backfilled_at)).where(SnapshotViewUnit.snapshot_id == snapshot_id)
    )
    return {"backfilled_at": str(at)} if at else {}


def scenario_view(sc: Scenario) -> dict[str, Any]:
    return {
        "id": sc.id,
        "code": sc.code,
        "name": sc.name,
        "is_builtin": bool(sc.is_builtin),
        "params": dict(sc.params or {}),
        "weights": {k: float(v) for k, v in (sc.weights or {}).items() if v is not None},
        "requirements": dict(sc.requirements or {}),
        "policy": dict(sc.policy or {}),
        "created_at": sc.created_at,
    }


# ====================================================================== 접수 상태


def intake_view(row: IntakeStatus) -> dict[str, Any]:
    reason = row.reason
    if row.status == "확인 불가" and not reason:
        reason = str(row.http_status) if row.http_status else "사유 미기재"
    return {
        "id": row.id,
        "complex_id": row.complex_id,
        "snapshot_id": row.snapshot_id,
        "status": row.status,
        "path": row.path,
        "evidence_url": row.evidence_url,
        "screenshot_path": row.screenshot_path,
        "raw_document_id": row.raw_document_id,
        "checked_at": row.checked_at,
        "http_status": row.http_status,
        "reason": reason,
        "note": row.note,
        "entered_by": row.entered_by,
    }


def pick_intake(rows: Sequence[IntakeStatus]) -> IntakeStatus | None:
    """표시 접수 행 = ``analysis.scope.pick_intake``(파이프라인·보고서와 같은 규칙, R3 minor 21)."""
    return scope_rules.pick_intake(rows)


# ====================================================================== 단지 묶음 (한 번에 읽기)


@dataclass
class ComplexBundle:
    cx: Complex
    types: list[ComplexType] = field(default_factory=list)
    payments: list[PaymentTerms] = field(default_factory=list)
    intake: list[IntakeStatus] = field(default_factory=list)
    ladders: list[Ladder] = field(default_factory=list)
    stored_scope: str | None = None  # score_total.judge_scope(이 스냅샷 마지막 점수 실행, 계약 2026-10-09.3)
    asof_date: str | None = None  # 스냅샷 기준일(요건 사전 계산의 즉시 입주 판단, R3 minor 20)
    scored_run: bool = False  # 이 스냅샷에 점수 실행이 있다(행이 없으면 그 실행에서 점수 대상 아님)
    changed_after_run: bool = False
    """점수 실행 뒤 재판정을 부르는 변경(change_event triggers_rejudge — 가격·입주월·강등·사람 확인 등)이 있었다(minor 5)."""
    latest: bool = True
    """이 스냅샷이 지역의 최신(기준일·리비전)인가 — 과거 스냅샷은 오늘 사실과 비교하지 않는다(minor 5)."""
    ocr_pending: dict[tuple[str, int], frozenset[str]] = field(default_factory=dict)
    """판정기 추출 전 OCR 값 필드((entity, id) → 필드들) — 점수 입력에서 null(R3 C3, 파이프라인과 같은 규칙)."""
    disc_labels: dict[tuple[str, int, str], str | None] = field(default_factory=dict)
    """공고 할인 출처 행 라벨((payment_terms, id, 'discount_by_type.<타입>') → chosen 라벨) — 확인됨일 때만 차감(D12-3)."""
    price_memo: tuple[tuple[int, int, int, int], Any] | None = field(default=None, repr=False, compare=False)
    """``bundle_price`` 계산 결과(같은 types·payments 목록이면 다시 계산하지 않는다 — 목록 화면 성능)."""


def _chunks(ids: Sequence[int], n: int = 500) -> Iterable[Sequence[int]]:
    for i in range(0, len(ids), n):
        yield ids[i : i + n]


def _region_scope(session: Session, snap: Snapshot | None, out: Mapping[int, ComplexBundle]) -> Any | None:
    """묶음이 그 스냅샷 지역의 단지 **전부**면 지역 단지 id 하위 질의, 아니면 None."""
    if snap is None or len(out) < 500:  # 작은 묶음은 IN 목록이 싸다
        return None
    if any(b.cx.region_id != snap.region_id for b in out.values()):
        return None
    total = session.scalar(
        select(func.count()).select_from(Complex).where(Complex.region_id == snap.region_id)
    )
    if total != len(out):
        return None
    return select(Complex.id).where(Complex.region_id == snap.region_id)


def latest_snapshot_id(session: Session, region_id: int) -> int | None:
    """지역의 최신 리비전 = 가장 새 발행 (기준일, 리비전)(D12-4). 발행이 없으면 가장 새 스냅샷.

    저장본 계산 중인 리비전(``snapshot_view.PUBLISHING`` — 메모리에서만 발행됨, D14-5)도 발행 리비전으로 센다."""
    from app.snapshot_view import PUBLISHING

    order = (Snapshot.asof_date.desc(), Snapshot.revision.desc(), Snapshot.id.desc())
    pub = PUBLISHING.get()
    for cond in (Snapshot.status == "published", None):
        stmt = select(Snapshot.id, Snapshot.asof_date, Snapshot.revision).where(
            Snapshot.region_id == region_id
        )
        if cond is not None:
            stmt = stmt.where(cond)
        got = session.execute(stmt.order_by(*order).limit(1)).first()
        if cond is not None and pub is not None and pub[1] == region_id:
            me = session.get(Snapshot, pub[0])
            if me is not None and (
                got is None
                or (me.asof_date, int(me.revision or 1), me.id) > (got[1], int(got[2] or 1), int(got[0]))
            ):
                return int(me.id)
        if got is not None:
            return int(got[0])
    return None


def _load_discount_labels(session: Session, out: Mapping[int, ComplexBundle]) -> None:
    """할인이 적힌 납부 조건 행만 그 할인 출처 행 라벨을 읽는다(할인 없는 지역은 질의 없음 — 목록 성능)."""
    from app.models import FieldProvenance

    owner: dict[int, ComplexBundle] = {
        p.id: b for b in out.values() for p in b.payments if getattr(p, "discount_by_type", None)
    }
    ids = sorted(owner)
    fp = FieldProvenance
    for chunk in _chunks(ids):
        for eid, name, label in session.execute(
            select(fp.entity_id, fp.field, fp.label).where(
                fp.entity == "payment_terms",
                fp.entity_id.in_(chunk),
                fp.field.like("discount_by_type.%"),
                fp.chosen.is_(True),
            )
        ):
            if eid in owner:
                owner[eid].disc_labels.setdefault(("payment_terms", int(eid), str(name)), label)


def load_bundles(
    session: Session,
    complexes: Sequence[Complex],
    snapshot_id: int,
    *,
    with_ladders: bool = True,
    scenario_id: int | None = None,
    complex_ocr: bool = True,
) -> dict[int, ComplexBundle]:
    """``_load_bundles`` + 저장본 계산 메모(``app.api.memo`` — 같은 계산 안의 같은 인자는 한 번만 읽는다, D14-5 성능)."""
    from app.api import memo

    if memo.store() is None:
        return _load_bundles(
            session, complexes, snapshot_id, with_ladders=with_ladders, scenario_id=scenario_id,
            complex_ocr=complex_ocr,
        )  # fmt: skip
    key = (
        "load_bundles", snapshot_id, tuple(c.id for c in complexes), type(complexes[0]).__name__ if complexes else "",
        with_ladders, scenario_id, complex_ocr,
    )  # fmt: skip
    got = memo.cached(
        key,
        lambda: _load_bundles(
            session, complexes, snapshot_id, with_ladders=with_ladders, scenario_id=scenario_id,
            complex_ocr=complex_ocr,
        ),
    )  # fmt: skip
    return dict(got)


def _load_bundles(
    session: Session,
    complexes: Sequence[Complex],
    snapshot_id: int,
    *,
    with_ladders: bool = True,
    scenario_id: int | None = None,
    complex_ocr: bool = True,
) -> dict[int, ComplexBundle]:
    """단지 묶음(사실 행·접수·사다리·저장 범위)을 한 번에 읽는다.

    저장 범위·사다리 숨김(M-1)은 **그 시나리오**(``scenario_id``)의 마지막 점수 실행 기준 — 시나리오 지정 rejudge 뒤 다른
    시나리오 화면이 그 rejudge 의 범위로 사다리를 숨기지 않게. ``scenario_id`` 가 없으면 스냅샷의 마지막 실행(시나리오 무관).

    ``complex_ocr=False``(목록·CSV): 단지 행의 판정기 추출 전 OCR 필드(``ocr_pending[("complex", id)]``)를 읽지 않는다 —
    그 값은 점수 입력 빌더(``score_input`` — 미리보기)만 쓰고, 목록의 범위·가격(``score_price``)은 타입·납부 조건 OCR 만
    본다(R3c 성능). 타입·납부 조건 OCR 은 그대로 읽는다."""
    snap = session.get(Snapshot, snapshot_id)
    asof = snap.asof_date if snap is not None else None
    out = {c.id: ComplexBundle(c, asof_date=asof) for c in complexes}
    # D13-1: 발행 리비전은 이 함수를 타지 않는다(저장본 ``app.snapshot_view``) — 여기는 발행 전 리비전·materialize 의
    # 지금 값 계산이다(옛 값별 동결 ``snapshot_state`` 는 저장본으로 대체·삭제)
    ids = list(out)
    region_ids = _region_scope(session, snap, out)

    def where_in(col: Any) -> list[Any]:
        """단지 id 조건: 지역 단지 전부면 하위 질의 하나(IN 목록 펼침 없음 — 목록 화면 성능), 아니면 500개씩."""
        if region_ids is not None:
            return [col.in_(region_ids)]
        return [col.in_(chunk) for chunk in _chunks(ids)]

    def fetch(stmt: Any, model: Any) -> Iterable[Any]:
        """지역 단지 전부(목록·CSV·대시보드 — 수천 행)면 같은 열 이름의 읽기 전용 행(``light_rows`` — ORM 객체·상태 추적
        없음, R3c 성능), 작은 묶음(상세 등)은 ORM 행 그대로. 묶음 행은 읽기만 한다(속성 접근 — Protocol 과 같은 모양)."""
        if region_ids is not None:
            return light_rows(session, stmt, model)
        return session.scalars(stmt)

    for cond in where_in(ComplexType.complex_id):
        for t in fetch(select(ComplexType).where(cond).order_by(ComplexType.id), ComplexType):
            if t.complex_id in out:
                out[t.complex_id].types.append(t)
    for cond in where_in(PaymentTerms.complex_id):
        for p in fetch(select(PaymentTerms).where(cond).order_by(PaymentTerms.id), PaymentTerms):
            if p.complex_id in out:
                out[p.complex_id].payments.append(p)
    _load_discount_labels(session, out)
    for cond in where_in(IntakeStatus.complex_id):
        for i in fetch(
            select(IntakeStatus)
            .where(cond, IntakeStatus.snapshot_id == snapshot_id)
            .order_by(IntakeStatus.id),
            IntakeStatus,
        ):
            if i.complex_id in out:
                out[i.complex_id].intake.append(i)
    if with_ladders:
        for cond in where_in(Ladder.complex_id):
            for lad in fetch(select(Ladder).where(cond, Ladder.snapshot_id == snapshot_id), Ladder):
                if lad.complex_id in out:
                    out[lad.complex_id].ladders.append(lad)
    run_stmt = select(ScoreRun.id).where(ScoreRun.snapshot_id == snapshot_id)
    if scenario_id is not None:
        run_stmt = run_stmt.where(ScoreRun.scenario_id == scenario_id)
    last_run = session.scalars(run_stmt.order_by(ScoreRun.id.desc()).limit(1)).first()
    if snap is not None:
        # '재판정 필요'(D10-1)는 지금 사실과 비교한다 — 발행 전(building·ready) 리비전은 늘 비교하고(M6: 실시간 리비전에서
        # 의미), 발행 리비전은 발행 순간(materialize)에 지역의 가장 새 발행 (기준일, 리비전)일 때만 비교해 그 값을 저장한다
        # (D13-1 — 이후에는 저장본만 읽는다). 과거 리비전은 그때의 기록이다
        if snap.status != "published":
            latest = True
        else:
            latest = latest_snapshot_id(session, snap.region_id) == snap.id
        for b in out.values():
            b.latest = latest
    if last_run is not None:
        for b in out.values():
            b.scored_run = True
        run_at = session.scalar(select(ScoreRun.created_at).where(ScoreRun.id == last_run))
        if run_at and snap is not None:
            # M6: 지역 단위 변경(생활권 편집·지역 확장/축소 — complex_id NULL, triggers_rejudge)은 지역 단지 전부에 걸린다
            region_changed = session.scalars(
                select(ChangeEvent.id)
                .where(
                    ChangeEvent.complex_id.is_(None),
                    ChangeEvent.entity == "region",
                    ChangeEvent.entity_id == snap.region_id,
                    ChangeEvent.triggers_rejudge.is_(True),
                    ChangeEvent.detected_at > run_at,
                )
                .limit(1)
            ).first()
            if region_changed is not None:
                for b in out.values():
                    b.changed_after_run = True
        if run_at:
            for cond in where_in(ChangeEvent.complex_id):
                for (cid,) in session.execute(
                    select(ChangeEvent.complex_id)
                    .where(
                        cond,
                        ChangeEvent.triggers_rejudge.is_(True),
                        ChangeEvent.detected_at > run_at,
                    )
                    .distinct()
                ):
                    if cid in out:
                        out[cid].changed_after_run = True
        for cond in where_in(ScoreTotal.complex_id):
            # 저장 범위 = 이 스냅샷 마지막 점수 실행의 score_total.judge_scope(D10-1 — 한 실행의 시나리오는 같은 범위)
            for cid, scope in session.execute(
                select(ScoreTotal.complex_id, ScoreTotal.judge_scope).where(
                    ScoreTotal.score_run_id == last_run,
                    cond,
                    ScoreTotal.judge_scope.is_not(None),
                )
            ):
                if cid in out:
                    out[cid].stored_scope = scope
    # D11-3 강등 오버레이: 강등 중인 사실 필드는 묶음 행에서 None 으로 보인다(점수 입력·범위·CSV·정렬 공통). Fact 의
    # '확인 불가(검증 모순)' 표시는 ``ProvIndex``(같은 오버레이)가 한다. 읽기 전용 감싸개 — DB 쓰기 없음
    from app.facts_view import load_overlay

    overlay = load_overlay(session, complex_ids=ids) if ids else None
    if overlay:
        # 강등 행이 있는 (entity, id)만 감싼다 — 나머지는 ``masked(row, ())`` 가 행 그대로라 같은 결과(R3c 성능)
        hit = {(e, i) for (e, i, _f) in overlay.active}
        for b in out.values():
            if ("complex", b.cx.id) in hit:
                b.cx = masked(b.cx, overlay.fields("complex", b.cx.id))
            if any(("complex_type", t.id) in hit for t in b.types):
                b.types = [masked(t, overlay.fields("complex_type", t.id)) for t in b.types]
            if any(("payment_terms", p.id) in hit for p in b.payments):
                b.payments = [masked(p, overlay.fields("payment_terms", p.id)) for p in b.payments]
    from app.scheduler.inputs import ocr_pending_fields

    targets: list[tuple[str, list[tuple[int, int]]]] = [
        *([("complex", [(b.cx.id, b.cx.id) for b in out.values()])] if complex_ocr else []),
        ("complex_type", [(t.complex_id, t.id) for b in out.values() for t in b.types]),
        ("payment_terms", [(p.complex_id, p.id) for b in out.values() for p in b.payments]),
    ]
    scopes: dict[str, Any] = {}
    if region_ids is not None:
        scopes = {
            "complex": region_ids,
            "complex_type": select(ComplexType.id).where(ComplexType.complex_id.in_(region_ids)),
            "payment_terms": select(PaymentTerms.id).where(PaymentTerms.complex_id.in_(region_ids)),
        }
    for entity, rows in targets:
        pending = ocr_pending_fields(session, entity, [eid for _, eid in rows], id_query=scopes.get(entity))
        for cid, eid in rows:
            if eid in pending:
                out[cid].ocr_pending[(entity, eid)] = pending[eid]
    if with_ladders:
        # D9-1·D10-1: 사다리는 '판정 대상'만 — 표시 범위(저장값 우선)가 '참고'·'보류'·'미해결'·'제외'인 단지는 같은
        # 스냅샷에 남은 사다리 행(이전 범위의 판정·이월·devseed)이 있어도 p10·C1·비교 화면에 쓰지 않는다.
        for b in out.values():
            if b.ladders and not scope_rules.runs_ladder(shown_scope(b)):
                b.ladders = []
    return out


def basis_type(types: Sequence[ComplexType]) -> ComplexType | None:
    """판정 기준 타입 = ``analysis.price_view.basis_type``."""
    return pv.basis_type(types)


def current_payment(payments: Sequence[PaymentTerms]) -> PaymentTerms | None:
    """현재 납부 조건 = ``analysis.price_view.current_terms``(파이프라인과 같은 순서)."""
    return pv.current_terms(payments)


def _disc_label(b: ComplexBundle) -> pv.DiscountLabel:
    """할인 출처 라벨(D12-3) — ``load_bundles`` 가 읽은 chosen 출처 행 라벨(``disc_labels``)."""
    return pv.labels_from(lambda e, i, f: b.disc_labels.get((e, i, f)))


def bundle_price(b: ComplexBundle) -> pv.PriceView:
    """§6-1 현재 구매가(최신 payment_terms.price_by_type 우선, 할인은 확인됨일 때만 — D12-3) — 파이프라인·보고서와 같은
    함수(R3 M3). 상세·목록 필터·정렬·비교·자금 요건 모두 이 값. 같은 묶음(같은 types·payments 목록)이면 한 번만 계산한다."""
    key = (id(b.types), len(b.types), id(b.payments), len(b.payments))
    if b.price_memo is not None and b.price_memo[0] == key:
        view: pv.PriceView = b.price_memo[1]
        return view
    view = pv.current_price(b.types, b.payments, discount_label=_disc_label(b))
    b.price_memo = (key, view)
    return view


def _masked_types(b: ComplexBundle) -> list[Any]:
    return [masked(t, b.ocr_pending.get(("complex_type", t.id), frozenset())) for t in b.types]


def _masked_payments(b: ComplexBundle) -> list[Any]:
    return [masked(p, b.ocr_pending.get(("payment_terms", p.id), frozenset())) for p in b.payments]


def score_price(b: ComplexBundle) -> pv.PriceView:
    """점수 입력 구매가 = ``bundle_price`` 에서 판정기 추출 전 OCR 값을 뺀 것(R3 C3 — 파이프라인 ``load_facts`` 와 같은
    규칙). 화면 표시 가격은 ``bundle_price``(OCR 값은 '추정(OCR)' 라벨로 보인다)."""
    if not b.ocr_pending:
        return bundle_price(b)
    return pv.current_price(_masked_types(b), _masked_payments(b), discount_label=_disc_label(b))


def scope_result(b: ComplexBundle) -> scope_rules.ScopeResult:
    """**현재 사실**로 계산한 판정 범위 = ``analysis.scope.judge_scope``(D9-1) — 파이프라인·보고서와 같은 함수.

    화면·KPI·TOP 5 에 보이는 범위는 저장값(``shown_scope``, D10-1)이다. 이 값은 미리보기(요건 사전 계산)와
    '재판정 필요' 비교(``rejudge_needed``)에만 쓴다."""
    return _scope_now(b, scope_rules.pick_intake(b.intake))


def _scope_now(b: ComplexBundle, cur: IntakeStatus | None) -> scope_rules.ScopeResult:
    """``scope_result`` 본체 — 표시 접수 행(``pick_intake``)을 이미 고른 호출자(목록 행)는 그 행을 넘긴다."""
    return scope_rules.judge_scope(
        inclusion_class=b.cx.inclusion_class,
        inclusion_decision=b.cx.inclusion_decision,
        has_price=score_price(b).known,
        intake_status=cur.status if cur is not None else None,
        original_notice_missing=scope_rules.original_missing(b.cx.applyhome_id, b.cx.notice_date),
    )


def _stored(b: ComplexBundle, ctx: ScoreCtx | None) -> str | None:
    """저장 판정 범위: 그 점수 실행(ctx)의 score_total.judge_scope, 없으면 스냅샷 마지막 실행의 값."""
    if ctx is not None and ctx.run is not None:
        t = ctx.totals.get(b.cx.id)
        if t is not None and t.judge_scope:
            return str(t.judge_scope)
    return b.stored_scope


def shown_scope(b: ComplexBundle, ctx: ScoreCtx | None = None) -> str:
    """화면 판정 범위(D10-1): 스냅샷 점수 실행의 **저장값**(score_total.judge_scope) — 순위·총점·성분과 같은 실행.

    저장값이 없을 때만(점수 실행 전 스냅샷, 계약 .3 이전 행) 현재 사실로 계산한 값을 낸다. 저장값과 현재값을 한 행에
    섞지 않는다 — 달라졌으면 ``rejudge_needed`` 가 True(재판정 필요 배지 + rejudge 제안).
    '미해결'은 계약 값 그대로(``analysis.scope.contract_scope``)."""
    stored = _stored(b, ctx)
    if stored:
        return stored
    return scope_rules.contract_scope(scope_result(b).scope)


def rejudge_needed(b: ComplexBundle, ctx: ScoreCtx | None = None) -> bool:
    """D10-1 '재판정 필요': 저장 판정 범위가 있고 현재 사실로 계산한 범위와 다르다(사람 확인·새 공고 등 이후 변경).

    점수 실행이 있는 스냅샷에서 그 단지 행이 없는데(그 실행에서 점수 밖) 지금은 점수 대상이면 역시 True.
    R3 3차 minor 5: 범위가 같아도 점수 실행 뒤 재판정을 부르는 변경(가격·입주월·강등·사람 확인 — change_event
    triggers_rejudge)이 있었으면 True. 지역 최신 스냅샷(기준일·리비전)이 아니면 오늘 사실과 비교하지 않는다(False) —
    과거 스냅샷은 그때의 기록이다."""
    return _row_scopes(b, ctx, scope_rules.pick_intake(b.intake))[1]


def _row_scopes(b: ComplexBundle, ctx: ScoreCtx | None, cur: IntakeStatus | None) -> tuple[str, bool]:
    """(``shown_scope``, ``rejudge_needed``) 를 한 번에 — 목록 행(1,000단지)이 접수 행 고르기·저장값 읽기·현재 범위
    계산을 단지마다 한 번만 하도록(R3c 성능). 규칙은 두 함수 설명 그대로."""
    stored = _stored(b, ctx)
    if stored and not b.latest:
        return stored, False
    current: str = scope_rules.contract_scope(_scope_now(b, cur).scope)
    shown = stored or current
    if not b.latest:
        return shown, False
    if stored and b.changed_after_run:
        return shown, True
    if stored:
        return shown, stored != current
    has_run = (ctx is not None and ctx.run is not None) or b.scored_run
    return shown, has_run and scope_rules.is_scored(current)


def judge_scope(b: ComplexBundle) -> str:
    """판정 범위(meta §1-3-4, D9-1·D10-1): 판정 대상 / 참고 / 보류 / 미해결 / 제외 — 화면 값 = ``shown_scope``
    (저장값 우선). 현재 사실로 계산한 값(미해결 포함·사유)은 ``scope_result``."""
    return shown_scope(b)


# ====================================================================== Fact 묶음


def _unit_text(v: Any) -> str | None:
    return "text" if isinstance(v, str) else None


def complex_header(fm: FactMaker, b: ComplexBundle, area_name: Mapping[str, str]) -> dict[str, Any]:
    cx = b.cx
    f = fm.field

    def cf(name: str, unit: str | None) -> dict[str, Any]:
        return f("complex", cx.id, name, getattr(cx, name), unit=unit)

    rr = cx.resale_release_on_registration
    rr_text = None if rr is None else ("등기 시 해제" if rr else "해당 없음")
    winner = cf("winner_date", "date")
    resale_months = cf("resale_months", "months")
    resale_end = _resale_end(fm, cx, winner, resale_months)
    return {
        "id": cx.id,
        "region_id": cx.region_id,
        "applyhome_id": cx.applyhome_id,
        "name": cx.name,
        "former_names": list(cx.former_names or []),
        "address": cx.address,
        "legal_dong_code": cx.legal_dong_code
        if cx.legal_dong_code and len(cx.legal_dong_code) == 10
        else None,
        "living_area": cx.living_area,
        "living_area_name": area_name.get(cx.living_area or "") if cx.living_area else None,
        "official_site_url": cx.official_site_url,
        "developer": cx.developer,
        "trustee": cx.trustee,
        "builder": cx.builder,
        "housing_type": cf("housing_type", "text"),
        "land_type": cf("land_type", "text"),
        "price_cap": cf("price_cap", "text"),
        "regulated": cf("regulated", "text"),
        "units_total": cf("units_total", "units"),
        "units_general": cf("units_general", "units"),
        "units_special": cf("units_special", "units"),
        "officetel_units": cf("officetel_units", "units"),
        "notice_date": cf("notice_date", "date"),
        "apply_dates": _schedule(fm, cx, "apply_dates"),
        "winner_date": winner,
        "contract_dates": _schedule(fm, cx, "contract_dates"),
        "move_in_ym": cf("move_in_ym", "ym"),
        "resale_months": resale_months,
        "resale_end": resale_end,
        "resale_release_on_registration": f(
            "complex", cx.id, "resale_release_on_registration", rr_text, unit="text"
        ),
        "residency_months": cf("residency_months", "months"),
        "rewin_restriction_years": cf("rewin_restriction_years", "years"),
        "inclusion_class": cx.inclusion_class or "미분류",
        "inclusion_decision": cx.inclusion_decision,
        "inclusion_prob": _judge_prob(cx.inclusion_prob, cx.inclusion_judgment_seq, "판정기 classify", None),
        "track": cx.track,
    }


def _judge_prob(value: Any, seq: int | None, reason: str, checked: str | None) -> dict[str, Any]:
    if value is None:
        return unknown("미판정", checked, unit="prob")
    if seq is None:
        return unknown("판정 기록 없음", checked, unit="prob")
    return fact(value, "추정", f"jl_{seq}", checked, reason=reason, unit="prob")


def _add_months(ymd: str, months: int) -> str | None:
    try:
        y, m, d = int(ymd[:4]), int(ymd[5:7]), int(ymd[8:10])
    except (ValueError, IndexError):
        return None
    total = y * 12 + (m - 1) + months
    ny, nm = divmod(total, 12)
    nm += 1
    mdays = [
        31,
        29 if (ny % 4 == 0 and (ny % 100 != 0 or ny % 400 == 0)) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    return f"{ny:04d}-{nm:02d}-{min(d, mdays[nm - 1]):02d}"


def _resale_end(
    fm: FactMaker,
    cx: Complex,
    winner: dict[str, Any],
    months: dict[str, Any],
    *,
    end: str | None = None,
) -> dict[str, Any]:
    """전매 종료일 Fact. ``end``: 이미 계산한 종료일(목록 ``RowData.resale_end`` — 같은 ``_add_months``)."""
    if cx.winner_date is None or cx.resale_months is None:
        return fm.derived(None, [winner, months], unit="date")
    if end is None:
        end = _add_months(cx.winner_date, int(cx.resale_months))
    return fm.derived(end, [months, winner], unit="date")


def _schedule(fm: FactMaker, cx: Complex, name: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in getattr(cx, name) or []:
        if not isinstance(it, dict):
            continue
        start = it.get("start") or it.get("date") or it.get("from")
        end = it.get("end") or it.get("to")
        if start is None:
            continue
        kind = str(it.get("kind") or ("계약" if name == "contract_dates" else "접수"))[:32]
        out.append(
            {
                "kind": kind,
                "start": fm.field("complex", cx.id, name, start, unit="date"),
                "end": fm.field("complex", cx.id, name, end, unit="date") if end else None,
            }
        )
    return out


def type_view(fm: FactMaker, t: ComplexType, *, is_basis: bool) -> dict[str, Any]:
    def tf(name: str, unit: str) -> dict[str, Any]:
        return fm.field("complex_type", t.id, name, getattr(t, name), unit=unit)

    return {
        "id": t.id,
        "complex_id": t.complex_id,
        "type_code": t.type_code,
        "notice_type_code": t.notice_type_code,
        "area_m2": tf("area_m2", "m2"),
        "units": tf("units", "units"),
        "max_price_won": tf("max_price_won", "won"),
        "floor_sample_price_won": tf("floor_sample_price_won", "won"),
        "floor_sample_text": t.floor_sample_text,
        "balcony_won": tf("balcony_won", "won"),
        "options_required_won": tf("options_required_won", "won"),
        "options_text": t.options_text,
        "is_basis": is_basis,
    }


def _man(won: int) -> str:
    return f"{Decimal(won) / Decimal(10000):,.0f}만"


def price_range(
    fm: FactMaker, b: ComplexBundle, notice: dict[str, Any] | None = None, *, full: bool = True
) -> dict[str, Any]:
    """§6-1 현재 구매가 범위 = ``bundle_price``(최신 공고 가격 우선, R3 M3). 출처는 쓴 필드 그대로.
    할인(D11-6, 계약 .8)은 그 출처 행 라벨이 '확인됨'일 때만 뺀다 — ``discount`` Fact 는 늘 보인다.

    ``full=False``(목록 행 — low·high·mid 만 쓴다): 구성 문구·최초 공고 대비 변동률·할인 Fact 를 만들지 않는다(None,
    R3c 성능). low·high·mid 는 같은 값·같은 Fact."""

    view = bundle_price(b)  # 할인 차감 규칙(확인됨만)도 같은 함수 — 목록 정렬·필터·비교와 같은 값(D12-3)
    t = (
        next((x for x in b.types if x.type_code == view.basis_type_code), None)
        if view.basis_type_code
        else None
    )
    if t is None or not view.known:
        reason = view.empty_reason or "분양가 미공개"
        if notice is not None and notice["label"] == LABEL_UNKNOWN and notice.get("reason"):
            reason = str(notice["reason"])
        cur = current_payment(b.payments)
        if t is not None and (
            fm.prov.demoted("complex_type", t.id, "max_price_won")
            or (
                cur is not None
                and fm.prov.demoted("payment_terms", cur.id, f"price_by_type.{t.type_code}.max_price_won")
            )
        ):
            reason = "검증 모순"  # 강등된 가격(D11-3·M-4) — 옛 공고 가격으로 돌아가지 않는다
        u = unknown(reason, None, unit="won")
        return {
            "basis_type_code": view.basis_type_code,
            "price_low": u,
            "price_high": dict(u),
            "price_mid": dict(u),
            "composition": None,
            "change_vs_first_pct": None,
            "discount": None,
            "discount_applied": False,
        }

    made: dict[tuple[str, int, str], dict[str, Any]] = {}

    def ref_fact(ref: pv.FieldRef) -> dict[str, Any]:
        # low·high 가 같은 원천(발코니·옵션·최고가)을 공유한다 — 원천 Fact 는 읽기만 하므로 한 번만 만든다(목록 성능)
        key = (ref.entity, ref.entity_id, ref.field)
        got = made.get(key)
        if got is None:
            got = made[key] = fm.field(ref.entity, ref.entity_id, ref.field, ref.value, unit="won")
        return got

    low_won, high_won = view.low_won, view.high_won
    low = fm.combine(low_won, [ref_fact(r) for r in view.low_refs], unit="won")
    high = fm.combine(high_won, [ref_fact(r) for r in view.high_refs], unit="won")
    mid_val = pv.mid_rounded(view)
    mid = fm.derived(mid_val, [low, high], unit="won")
    if not full:
        return {
            "basis_type_code": t.type_code,
            "price_low": low,
            "price_high": high,
            "price_mid": mid,
            "composition": None,
            "change_vs_first_pct": None,
            "discount": None,
            "discount_applied": False,
        }
    parts = ["공급가"]
    if t.balcony_won:
        parts.append(f"발코니 {_man(t.balcony_won)}")
    if t.options_required_won:
        parts.append(f"필수 옵션 {_man(t.options_required_won)}")
    composition = " + ".join(parts)
    discount = None
    if view.discount_ref is not None:
        ref = view.discount_ref
        discount = fm.field(ref.entity, ref.entity_id, ref.field, ref.value, unit="won")
        if view.discount_applied:
            composition += f" − 할인 {_man(int(ref.value))}"
    return {
        "basis_type_code": t.type_code,
        "price_low": low,
        "price_high": high,
        "price_mid": mid,
        "composition": composition,
        "change_vs_first_pct": _price_change(fm, b, t),
        "discount": discount,
        "discount_applied": bool(view.discount_applied),  # 계약 .10: 서버가 실제로 뺐는가(화면 문구 근거)
    }


def _price_change(fm: FactMaker, b: ComplexBundle, t: ComplexType) -> dict[str, Any] | None:
    pays = sorted(b.payments, key=lambda p: (p.effective_from, p.id))
    if len(pays) < 2:
        return None
    first, cur = pays[0], pays[-1]
    a = ((first.price_by_type or {}).get(t.type_code) or {}).get("max_price_won")
    z = ((cur.price_by_type or {}).get(t.type_code) or {}).get("max_price_won")
    if not a or z is None:
        return None
    src = fm.field("payment_terms", cur.id, f"price_by_type.{t.type_code}.max_price_won", z, unit="won")
    pct = float(((Decimal(z) - Decimal(a)) / Decimal(a) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP))
    return fm.derived(pct, [src], unit="pct")


def payment_view(
    fm: FactMaker, p: PaymentTerms, *, first: PaymentTerms | None, is_current: bool, basis_code: str | None
) -> dict[str, Any]:
    def pf(name: str, unit: str) -> dict[str, Any]:
        return fm.field("payment_terms", p.id, name, getattr(p, name), unit=unit)

    sched = []
    for i, s in enumerate(p.interim_schedule or [], start=1):
        if not isinstance(s, dict):
            continue
        sched.append(
            {
                "seq": int(s.get("seq") or i),
                "due_date": fm.field(
                    "payment_terms", p.id, "interim_schedule", s.get("due_date"), unit="date"
                ),
                "pct": fm.field("payment_terms", p.id, "interim_schedule", s.get("pct"), unit="pct"),
            }
        )
    pbt: dict[str, Any] = {}
    for code, item in (p.price_by_type or {}).items():
        if not isinstance(item, dict):
            continue
        key = f"price_by_type.{code}"
        units = item.get("units")
        pbt[str(code)] = {
            "notice_type_code": item.get("notice_type_code"),
            "units": fm.field("payment_terms", p.id, f"{key}.units", units, unit="units")
            if units is not None
            else None,
            "max_price_won": fm.field(
                "payment_terms", p.id, f"{key}.max_price_won", item.get("max_price_won"), unit="won"
            ),
            "floor_sample_price_won": fm.field(
                "payment_terms",
                p.id,
                f"{key}.floor_sample_price_won",
                item.get("floor_sample_price_won"),
                unit="won",
            ),
            "floor_sample_text": item.get("floor_sample_text"),
        }
    # 공고에 명시된 할인(타입별, 계약 .8 D11-6) — 출처 행 'discount_by_type.<type_code>' 라벨 그대로(표시용).
    # 구매가 차감은 ``price_range`` 가 그 라벨이 확인됨일 때만 한다(같은 출처 행). 없으면 {}.
    dbt: dict[str, Any] = {}
    disc_map = getattr(p, "discount_by_type", None)
    for code, won in (disc_map if isinstance(disc_map, dict) else {}).items():
        if won is None:
            continue
        dbt[str(code)] = fm.field("payment_terms", p.id, f"discount_by_type.{code}", won, unit="won")
    down = pf("down_payment_pct", "pct")
    change: dict[str, Any] | None = None
    if first is not None and first.id != p.id:
        delta = None
        if p.down_payment_pct is not None and first.down_payment_pct is not None:
            first_f = fm.field(
                "payment_terms", first.id, "down_payment_pct", first.down_payment_pct, unit="pct"
            )
            delta = fm.derived(num(p.down_payment_pct - first.down_payment_pct), [down, first_f], unit="pct")
        price_pct = None
        if basis_code:
            a = ((first.price_by_type or {}).get(basis_code) or {}).get("max_price_won")
            z = ((p.price_by_type or {}).get(basis_code) or {}).get("max_price_won")
            if a and z is not None:
                src = fm.field(
                    "payment_terms", p.id, f"price_by_type.{basis_code}.max_price_won", z, unit="won"
                )
                pct = float(
                    ((Decimal(z) - Decimal(a)) / Decimal(a) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
                )
                price_pct = fm.derived(pct, [src], unit="pct")
        change = {"down_payment_pct_delta": delta, "price_change_pct": price_pct}
    return {
        "id": p.id,
        "complex_id": p.complex_id,
        "notice_no": p.notice_no,
        "notice_kind": p.notice_kind,
        "effective_from": pf("effective_from", "date"),
        "down_payment_pct": down,
        "down_payment_first_won": pf("down_payment_first_won", "won"),
        "interim_pct": pf("interim_pct", "pct"),
        "interim_terms_text": p.interim_terms_text,
        "balance_pct": pf("balance_pct", "pct"),
        "interim_schedule": sched,
        "is_current": is_current,
        "price_by_type": pbt,
        "discount_by_type": dbt,
        "change_vs_first": change,
    }


def competition_view(fm: FactMaker, c: Competition) -> dict[str, Any]:
    return {
        "id": c.id,
        "complex_id": c.complex_id,
        "round": c.round,
        "kind": c.kind,
        "type_code": c.type_code,
        "supply": fm.field("competition", c.id, "supply", c.supply, unit="units"),
        "applied": fm.field("competition", c.id, "applied", c.applied, unit="count"),
        "ratio_or_shortfall_text": c.ratio_or_shortfall_text,
        "raw_document_id": c.raw_document_id,
    }


def event_view(fm: FactMaker, e: RemainingEvent) -> dict[str, Any]:
    by_type = {str(k): int(v) for k, v in (e.units_by_type or {}).items()}
    units = sum(by_type.values()) if by_type else None
    return {
        "id": e.id,
        "complex_id": e.complex_id,
        "kind": e.kind,
        "notice_no": e.notice_no,
        "notice_date": fm.field("remaining_event", e.id, "notice_date", e.notice_date, unit="date"),
        "apply_dates": [
            fm.field("remaining_event", e.id, "apply_dates", d, unit="date") for d in e.apply_dates or []
        ],
        "units": fm.field("remaining_event", e.id, "units", units, unit="units"),
        "units_by_type": by_type,
        "ratio_text": e.ratio_text,
        "result_text": e.result_text,
        "raw_document_id": e.raw_document_id,
    }


# ====================================================================== 판정 봉투·사다리


def envelope_result(row: JudgmentLog) -> dict[str, Any]:
    """정규화 결과 = judgment_log.result_json(계약 2026-10-09.3). NULL(옛 행)이면 원응답을 다시 정규화."""
    if row.status in {"blocked", "error"}:
        return {}
    out = row.output_json or {}
    stored = row.result_json
    if isinstance(stored, dict) and stored:
        return dict(stored)
    try:
        from app.judge.jev_mcp import normalize

        return dict(normalize(row.tool, out, row.input_json or {}, row.purpose).result)  # type: ignore[arg-type]
    except Exception:
        return {}


def envelope_view(row: JudgmentLog) -> dict[str, Any]:
    raw = dict(row.output_json or {})
    return {
        "tool": row.tool,
        "purpose": row.purpose[:128],
        "input_hash": row.input_hash,
        "input_len": row.input_len,
        "status": row.status,
        "confidence": float(row.confidence) if row.confidence is not None else None,
        "cached": False,
        "result": envelope_result(row),
        "raw": raw,
        "duration_ms": row.duration_ms,
        "judgment_seq": row.seq,
        "created_at": row.created_at,
        "adapter_version": row.adapter_version[:64] if row.adapter_version else None,
        "snapshot_id": row.snapshot_id,
        "complex_id": row.complex_id,
        "error_text": row.error_text,
        "model": row.model,
        "provider": row.provider,
    }


def _ladder_prob(row: Ladder, v: Any, checked: str | None) -> dict[str, Any]:
    """사다리 확률 1개(p5·p10·p20·p_flat) Fact — ``ladder_view`` 와 목록 p10(``p10_fact``)이 같이 쓴다."""
    if v is None:
        return unknown("값 없음" if row.status == "ok" else f"미해결({row.status})", checked, unit="prob")
    if row.status != "ok":
        return unknown(f"미해결({row.status})", checked, unit="prob")
    if row.judgment_seq is None:
        return unknown("판정 기록 없음", checked, unit="prob")
    return fact(v, "추정", f"jl_{row.judgment_seq}", checked, reason="판정기 noul", unit="prob")


def ladder_view(row: Ladder, checked: str | None) -> dict[str, Any]:
    seq = row.judgment_seq

    def pf(v: Any) -> dict[str, Any]:
        return _ladder_prob(row, v, checked)

    verdicts = row.verdicts or {}
    ann = row.annualized or {}
    months = row.months_from_asof if row.months_from_asof and row.months_from_asof >= 1 else 1
    return {
        "complex_id": row.complex_id,
        "snapshot_id": row.snapshot_id,
        "horizon": row.horizon,
        "target_ym": row.target_ym,
        "target_label": target_label(row.target_ym) if len(row.target_ym or "") == 7 else None,
        "months_from_asof": months,
        "p5": pf(row.p5),
        "p10": pf(row.p10),
        "p20": pf(row.p20),
        "p_flat": pf(row.p_flat),
        "verdicts": {
            k: (verdicts.get(k) if verdicts.get(k) in ("likely", "uncertain", "unlikely") else None)
            for k in ("p5", "p10", "p20", "p_flat")
        },
        "annualized": {k: (float(ann[k]) if ann.get(k) is not None else None) for k in ("p5", "p10", "p20")},
        "status": row.status,
        "judgment_seq": seq,
        "proposition_text": row.proposition_text,
    }


def judgment_days(session: Session, seqs: Iterable[int | None]) -> dict[int, str | None]:
    from app.api import memo

    want = sorted({s for s in seqs if s is not None})
    out: dict[int, str | None] = {}
    box = memo.store()
    seen: dict[int, str | None] | None = box.setdefault("judgment_days", {}) if box is not None else None
    if seen is not None:  # 저장본 계산 메모(단지 상세 수천 개가 같은 판정 기록을 다시 읽지 않게)
        out.update({s: seen[s] for s in want if s in seen and seen[s] != _NO_ROW})
        want = [s for s in want if s not in seen]
    for chunk in _chunks(want):
        for seq, created in session.execute(
            select(JudgmentLog.seq, JudgmentLog.created_at).where(JudgmentLog.seq.in_(chunk))
        ):
            out[seq] = day(created)
    if seen is not None:
        for s in want:
            seen[s] = out.get(s, _NO_ROW)
    return out


_NO_ROW = "<no-row>"


# ====================================================================== 점수


@dataclass
class ScoreCtx:
    """한 score_run 의 행들(없으면 run=None)."""

    run: ScoreRun | None
    scenario: Scenario
    components: dict[int, dict[str, ScoreComponent]] = field(default_factory=dict)
    totals: dict[int, ScoreTotal] = field(default_factory=dict)
    decisions: dict[int, Decision] = field(default_factory=dict)
    jl_days: dict[int, str | None] = field(default_factory=dict)

    @functools.cached_property
    def weights(self) -> dict[str, float]:
        """실행(없으면 시나리오) 가중치 — 한 번만 계산(단지 행마다 부른다, D14-5 성능)."""
        src = self.run.weights if self.run is not None else self.scenario.weights
        return {k: float(v) for k, v in (src or {}).items() if v is not None}

    @property
    def checked(self) -> str | None:
        return day(self.run.created_at) if self.run is not None else None


def latest_run(session: Session, snapshot_id: int, scenario_id: int) -> ScoreRun | None:
    return session.scalars(
        select(ScoreRun)
        .where(ScoreRun.snapshot_id == snapshot_id, ScoreRun.scenario_id == scenario_id)
        .order_by(ScoreRun.id.desc())
        .limit(1)
    ).first()


def light_rows(session: Session, stmt: Any, model: Any, skip: frozenset[str] = frozenset()) -> list[Any]:
    """``select(Model)`` 문장 → 같은 열 이름으로 읽는 읽기 전용 행(SQLAlchemy Row — 속성 접근). ORM 객체를 만들지
    않는다. ``skip`` 열은 읽지 않고 null 로 둔다.

    세션의 연결에서 Core 로 실행한다 — ORM 결과 처리(행마다 엔터티 적재 경로)를 건너뛴다(R3c 성능). 같은 SQL·같은 열
    타입 처리(JSON·Numeric)라 값은 ``session.execute`` 와 같다. 세션 autoflush 는 그대로 지킨다. 행은 모델별 namedtuple
    (같은 열 이름 속성) — SQLAlchemy Row 의 이름 접근(``__getattr__``)보다 속성 읽기가 훨씬 싸다(목록은 행마다 수십 번)."""
    keys = tuple(c.key for c in model.__table__.columns)
    cols = [null().label(k) if k in skip else c for k, c in zip(keys, model.__table__.columns, strict=True)]
    if session.autoflush:
        session.flush()
    make = _row_type(model.__name__, keys)._make
    return [make(r) for r in session.connection().execute(stmt.with_only_columns(*cols))]


@functools.cache
def _row_type(name: str, keys: tuple[str, ...]) -> Any:
    return namedtuple(f"{name}Row", keys)  # 열 이름이 런타임(모델)에 정해진다


LIST_COMPONENTS: tuple[str, ...] = ("gap",)
"""목록 행(``complex_rows_data``·``complex_row``)이 읽는 점수 성분 — gap%(값·라벨·사유·정렬). 나머지는 상세·점수 화면."""


def score_ctx(
    session: Session,
    snapshot_id: int,
    scenario: Scenario,
    *,
    complex_ids: Sequence[int] | None = None,
    with_flags: bool = True,
) -> ScoreCtx:
    """``_score_ctx`` + 저장본 계산 메모(같은 계산 안의 같은 인자는 한 번 — 대시보드·목록·상세·비교가 같은 실행을 읽는다,
    D14-5 성능). 문맥은 읽기만 한다."""
    from app.api import memo

    if memo.store() is None:
        return _score_ctx(session, snapshot_id, scenario, complex_ids=complex_ids, with_flags=with_flags)
    key = (
        "score_ctx", snapshot_id, scenario.id, None if complex_ids is None else tuple(complex_ids), with_flags,
    )  # fmt: skip
    return memo.cached(
        key,
        lambda: _score_ctx(session, snapshot_id, scenario, complex_ids=complex_ids, with_flags=with_flags),
    )


def _score_ctx(
    session: Session,
    snapshot_id: int,
    scenario: Scenario,
    *,
    complex_ids: Sequence[int] | None = None,
    with_flags: bool = True,
) -> ScoreCtx:
    """``with_flags=False`` = 목록 화면(G2·CSV) 모드: 성분 flags(JSON — 상세 화면 gap 보정 표식)를 읽지 않고, 성분은
    목록 행이 쓰는 것(``LIST_COMPONENTS`` — gap%·정렬)만 읽는다(R3c 성능: 1,000단지 × 성분 7개 → 1개)."""
    run = latest_run(session, snapshot_id, scenario.id)
    ctx = ScoreCtx(run=run, scenario=scenario)
    if run is None:
        return ctx
    comp_stmt = select(ScoreComponent).where(ScoreComponent.score_run_id == run.id)
    if not with_flags:
        comp_stmt = comp_stmt.where(ScoreComponent.component.in_(LIST_COMPONENTS))
    tot_stmt = select(ScoreTotal).where(ScoreTotal.score_run_id == run.id)
    dec_stmt = select(Decision).where(Decision.score_run_id == run.id, Decision.complex_id.is_not(None))
    if complex_ids is not None:
        ids = list(complex_ids)
        comp_stmt = comp_stmt.where(ScoreComponent.complex_id.in_(ids))
        tot_stmt = tot_stmt.where(ScoreTotal.complex_id.in_(ids))
        dec_stmt = dec_stmt.where(Decision.complex_id.in_(ids))
    # 점수 행은 읽기만 한다 — ORM 객체 대신 열 값 묶음(목록 화면 1,000단지 × 성분 7개, T16 성능)
    skip = frozenset() if with_flags else frozenset({"flags"})
    for c in light_rows(session, comp_stmt, ScoreComponent, skip):
        ctx.components.setdefault(c.complex_id, {})[c.component] = c
    for t in light_rows(session, tot_stmt, ScoreTotal):
        ctx.totals[t.complex_id] = t
    for d in session.scalars(dec_stmt):
        if d.complex_id is not None:
            ctx.decisions[d.complex_id] = d
    seqs: list[int | None] = [run.rerank_judgment_seq, *(d.judgment_seq for d in ctx.decisions.values())]
    ctx.jl_days = judgment_days(session, seqs)
    return ctx


def total_fact(ctx: ScoreCtx, cid: int) -> dict[str, Any]:
    t = ctx.totals.get(cid)
    if ctx.run is None or t is None or t.total is None:
        return unknown("미판정", ctx.checked, unit="score")
    return fact(round2(t.total), "추정", f"st_{ctx.run.id}_{cid}", ctx.checked, unit="score")


def _component_view(ctx: ScoreCtx, cid: int, key: str, ladder_p10: dict[str, Any] | None) -> dict[str, Any]:
    weight = ctx.weights.get(key, 0.0)
    row = (ctx.components.get(cid) or {}).get(key)
    if ctx.run is None or row is None:
        return {
            "score": unknown("미판정", ctx.checked, unit="score"),
            "raw": None,
            "formula_text": "미판정",
            "weight": weight,
            "contribution": None,
        }
    prov = f"sc_{ctx.run.id}_{cid}_{key}"
    if row.score_0_10 is None:
        score = unknown(row.reason or "미판정", ctx.checked, unit="score")
    else:
        score = fact(
            row.score_0_10,
            row.label if row.label != LABEL_UNKNOWN else "추정",
            prov,
            ctx.checked,
            reason=row.reason,
            unit="score",
        )
    raw: dict[str, Any] | None = None
    if row.raw_value is not None:
        if key == "p10" and ladder_p10 is not None and ladder_p10["label"] != LABEL_UNKNOWN:
            raw = ladder_p10
        elif key == "rerank" and ctx.run.rerank_judgment_seq is not None:
            raw = fact(
                row.raw_value,
                "추정",
                f"jl_{ctx.run.rerank_judgment_seq}",
                ctx.jl_days.get(ctx.run.rerank_judgment_seq),
                reason="판정기 rerank",
                unit="prob",
            )
        else:
            label = row.label if row.label != LABEL_UNKNOWN else "추정"
            raw = fact(row.raw_value, label, prov, ctx.checked, reason=row.reason, unit=_RAW_UNITS.get(key))
    contribution = None
    if row.score_0_10 is not None:
        contribution = float(
            (Decimal(str(weight)) * row.score_0_10).quantize(Decimal("0.0001"), ROUND_HALF_UP)
        )
    return {
        "score": score,
        "raw": raw,
        "formula_text": row.formula_text or "미판정",
        "weight": weight,
        "contribution": contribution,
    }


def _ladder_for(b: ComplexBundle, horizon: str) -> Ladder | None:
    return next((lad for lad in b.ladders if lad.horizon == horizon), None)


def p10_fact(b: ComplexBundle, horizon: str, jl_days: Mapping[int, str | None]) -> dict[str, Any]:
    lad = _ladder_for(b, horizon)
    if lad is None:
        return unknown("미판정", None, unit="prob")
    checked = jl_days.get(lad.judgment_seq) if lad.judgment_seq is not None else None
    return _ladder_prob(lad, lad.p10, checked)  # = ladder_view(lad, checked)["p10"] (사다리 전체 dict 없이)


def decision_badge(ctx: ScoreCtx, cid: int) -> dict[str, Any] | None:
    d = ctx.decisions.get(cid)
    if d is None:
        return None
    checked = ctx.jl_days.get(d.judgment_seq) if d.judgment_seq is not None else ctx.checked
    if d.prob is None or d.judgment_seq is None:
        prob = unknown("미판정", checked, unit="prob")
    else:
        prob = fact(d.prob, "추정", f"jl_{d.judgment_seq}", checked, reason="판정기 decide", unit="prob")
    return {
        "prob": prob,
        "chosen": bool(d.chosen),
        "tie": bool(d.tie),
        "mismatch": bool(d.mismatch),
        "confidence": float(d.confidence) if d.confidence is not None else None,
    }


def score_row(
    ctx: ScoreCtx,
    b: ComplexBundle,
    area_name: Mapping[str, str],
    *,
    jl_days: Mapping[int, str | None],
) -> dict[str, Any]:
    cid = b.cx.id
    horizon = str((ctx.scenario.policy or {}).get("p10_horizon") or "move_in_plus_1y")
    p10 = p10_fact(b, horizon, jl_days)
    keys = [k for k in COMPONENT_ORDER if k in ctx.weights]
    if "liquidity" not in keys and "move_in" not in keys:
        keys.append("liquidity")
    if "liquidity" in keys and "move_in" in keys:
        keys.remove("move_in")
    components = {k: _component_view(ctx, cid, k, p10) for k in keys}
    for k in ("p10", "rerank", "gap", "benchmark", "supply"):
        components.setdefault(k, _component_view(ScoreCtx(None, ctx.scenario), cid, k, None))
    t = ctx.totals.get(cid)
    rerank_row = (ctx.components.get(cid) or {}).get("rerank")
    delta: dict[str, Any] | None = None
    if ctx.run is not None and rerank_row is not None and rerank_row.delta is not None:
        delta = fact(
            rerank_row.delta,
            "추정",
            f"sc_{ctx.run.id}_{cid}_rerank",
            ctx.checked,
            reason="이전 run 대비",
            unit="score",  # rerank 점수(0~10) 차 — 계약 2026-10-09.4(F2 요청, minor 25)
        )
    cur = pick_intake(b.intake)
    return {
        "complex_id": cid,
        "name": b.cx.name,
        "living_area": b.cx.living_area,
        "living_area_name": area_name.get(b.cx.living_area or "") if b.cx.living_area else None,
        "score_run_id": ctx.run.id if ctx.run is not None else None,
        "total": total_fact(ctx, cid),
        "rank": t.rank if t is not None else None,
        "tie_group": t.tie_group if t is not None else None,
        "unstable": bool(t.unstable) if t is not None else False,
        "p10": p10,
        "components": components,
        "delta_rerank": delta,
        "intake": intake_view(cur) if cur is not None else None,
        "decision": decision_badge(ctx, cid),
        "judge_scope": shown_scope(b, ctx),
        **({"rejudge_needed": rejudge_needed(b, ctx)} if _EMIT_REJUDGE_SCORE else {}),
    }


def ladder_days(session: Session, bundles: Iterable[ComplexBundle]) -> dict[int, str | None]:
    return judgment_days(session, (lad.judgment_seq for b in bundles for lad in b.ladders))


# ====================================================================== 목록 행 (G2)


@dataclass
class RowData:
    """필터·정렬용 맨값(Fact 이전). Fact 는 페이지 안에서만 만든다."""

    b: ComplexBundle
    scope: str
    intake: IntakeStatus | None
    price_low: int | None
    price_high: int | None
    price_mid: Decimal | None
    total: Decimal | None
    rank: int | None
    resale_end: str | None
    gap_pct: Decimal | None
    p10: Decimal | None
    rejudge_needed: bool = False  # D10-1: 저장 범위 ≠ 현재 범위(계약 .6 전까지 내부 플래그)


def complex_rows_data(bundles: Mapping[int, ComplexBundle], ctx: ScoreCtx) -> list[RowData]:
    horizon = str((ctx.scenario.policy or {}).get("p10_horizon") or "move_in_plus_1y")
    out: list[RowData] = []
    for cid, b in bundles.items():
        view = bundle_price(b)
        low, high = view.low_won, view.high_won
        mid = (Decimal(low) + Decimal(high)) / 2 if low is not None and high is not None else None
        t = ctx.totals.get(cid)
        gap = (ctx.components.get(cid) or {}).get("gap")
        lad = _ladder_for(b, horizon)
        resale_end = None
        if b.cx.winner_date and b.cx.resale_months is not None:
            resale_end = _add_months(b.cx.winner_date, int(b.cx.resale_months))
        cur = pick_intake(b.intake)
        scope, rejudge = _row_scopes(b, ctx, cur)
        out.append(
            RowData(
                b=b,
                scope=scope,
                intake=cur,
                price_low=low,
                price_high=high,
                price_mid=mid,
                total=t.total if t is not None else None,
                rank=t.rank if t is not None else None,
                resale_end=resale_end,
                gap_pct=gap.raw_value if gap is not None else None,
                p10=lad.p10 if lad is not None and lad.status == "ok" else None,
                rejudge_needed=rejudge,
            )
        )
    return out


def complex_row(
    fm: FactMaker,
    ctx: ScoreCtx,
    rd: RowData,
    area_name: Mapping[str, str],
    *,
    jl_days: Mapping[int, str | None],
    last_change: dict[str, Any] | None,
) -> dict[str, Any]:
    b, cx = rd.b, rd.b.cx
    notice = fm.field("complex", cx.id, "notice_date", cx.notice_date, unit="date")
    price = price_range(fm, b, notice, full=False)
    winner = fm.field("complex", cx.id, "winner_date", cx.winner_date, unit="date")
    months = fm.field("complex", cx.id, "resale_months", cx.resale_months, unit="months")
    cur_pay = current_payment(b.payments)
    if cur_pay is not None:
        down = fm.field("payment_terms", cur_pay.id, "down_payment_pct", cur_pay.down_payment_pct, unit="pct")
    else:
        down = unknown("납부 조건 없음", None, unit="pct")
    gap_row = (ctx.components.get(cx.id) or {}).get("gap")
    if ctx.run is not None and gap_row is not None and gap_row.raw_value is not None:
        gap = fact(
            gap_row.raw_value,
            gap_row.label if gap_row.label != LABEL_UNKNOWN else "추정",
            f"sc_{ctx.run.id}_{cx.id}_gap",
            ctx.checked,
            reason=gap_row.reason,
            unit="pct",
        )
    else:
        why = (gap_row.reason if gap_row is not None else None) or (
            "미판정" if gap_row is None else "고정 입력"
        )
        gap = unknown(why, ctx.checked, unit="pct")
    t = ctx.totals.get(cx.id)
    return {
        "complex_id": cx.id,
        "name": cx.name,
        "living_area": cx.living_area,
        "living_area_name": area_name.get(cx.living_area or "") if cx.living_area else None,
        "track": cx.track,
        "judge_scope": rd.scope,
        "intake": intake_view(rd.intake) if rd.intake is not None else None,
        "price_low": price["price_low"],
        "price_high": price["price_high"],
        "price_mid": price["price_mid"],
        "resale_end": _resale_end(fm, cx, winner, months, end=rd.resale_end),
        "move_in_ym": fm.field("complex", cx.id, "move_in_ym", cx.move_in_ym, unit="ym"),
        "gap_pct": gap,
        "total": total_fact(ctx, cx.id),
        "rank": t.rank if t is not None else None,
        "tie_group": t.tie_group if t is not None else None,
        "unstable": bool(t.unstable) if t is not None else False,
        "p10": p10_fact(b, str((ctx.scenario.policy or {}).get("p10_horizon") or "move_in_plus_1y"), jl_days),
        "inclusion_class": cx.inclusion_class or "미분류",
        "inclusion_decision": cx.inclusion_decision,
        "inclusion_prob": _judge_prob(
            cx.inclusion_prob,
            cx.inclusion_judgment_seq,
            "판정기 classify",
            jl_days.get(cx.inclusion_judgment_seq or -1),
        ),
        "land_type": fm.field("complex", cx.id, "land_type", cx.land_type, unit="text"),
        "price_cap": fm.field("complex", cx.id, "price_cap", cx.price_cap, unit="text"),
        "regulated": fm.field("complex", cx.id, "regulated", cx.regulated, unit="text"),
        "residency_months": fm.field(
            "complex", cx.id, "residency_months", cx.residency_months, unit="months"
        ),
        "down_payment_pct": down,
        "units_total": fm.field("complex", cx.id, "units_total", cx.units_total, unit="units"),
        "last_change": last_change,
        **({"rejudge_needed": rd.rejudge_needed} if _EMIT_REJUDGE_ROW else {}),
    }


LIST_COMPLEX_FIELDS: frozenset[str] = frozenset(
    {
        "notice_date", "winner_date", "resale_months", "move_in_ym",
        "land_type", "price_cap", "regulated", "residency_months", "units_total",
    }
)  # fmt: skip
"""목록 행(``complex_row``)이 Fact 로 쓰는 단지 필드 — 목록 화면은 이 필드 출처만 읽는다(T16 성능)."""

LIST_TYPE_FIELDS: frozenset[str] = frozenset(
    {"max_price_won", "floor_sample_price_won", "balcony_won", "options_required_won"}
)
"""목록 행 가격 범위(``price_range`` ← ``analysis.price_view.current_price``)가 쓰는 판정 기준 타입 필드(R3c 성능)."""


_PAY_FIELDS_IN_MAX = 8


def _basis_of(b: ComplexBundle) -> ComplexType | None:
    """판정 기준 타입 = ``basis_type(b.types)`` — ``bundle_price`` 가 이미 고른 기준 타입 코드(같은 함수)로 찾는다(다시
    84㎡ 비교를 하지 않는다, 목록 성능). 코드가 같은 첫 타입 = ``analysis.price_view.basis_type`` 의 선택과 같다."""
    code = bundle_price(b).basis_type_code
    if code is None:
        return None
    return next((t for t in b.types if t.type_code == code), None)


def provenance_for(
    session: Session, bundles: Iterable[ComplexBundle], *, list_rows: bool = False
) -> ProvIndex:
    """단지 묶음의 사실 행 출처를 한 번에 읽는다.

    ``list_rows``: 목록 행(``complex_row``)에 필요한 것만 — 단지 필드 ``LIST_COMPLEX_FIELDS``, 타입은 판정 기준 타입의
    가격 필드(``LIST_TYPE_FIELDS``), 납부 조건은 현재 공고의 계약금 비율·기준 타입 가격·할인만(목록 행은
    ``price_range(full=False)`` — 변동률·구성 문구 없음, R3c 성능). 강등 오버레이는 필드 범위와 무관하게 읽은 행 id
    전체로 계산된다(``ProvIndex.load``). 빠진 출처를 쓰면 dev 는 예외(출처 누락)라 테스트가 잡는다."""
    items = list(bundles)
    from app.api import memo

    if memo.store() is not None:  # 저장본 계산 메모 — 시나리오만 다른 같은 단지 묶음은 같은 출처 행
        key = (
            "provenance_for", list_rows,
            tuple((b.cx.id, tuple(t.id for t in b.types), tuple(p.id for p in b.payments)) for b in items),
        )  # fmt: skip
        return memo.cached(key, lambda: _provenance_for(session, items, list_rows=list_rows))
    return _provenance_for(session, items, list_rows=list_rows)


def _provenance_for(session: Session, items: list[ComplexBundle], *, list_rows: bool) -> ProvIndex:
    idx = ProvIndex()
    if list_rows:
        idx.load(session, "complex", (b.cx.id for b in items), fields=LIST_COMPLEX_FIELDS)
        basis = {id(b): _basis_of(b) for b in items}
        idx.load(
            session,
            "complex_type",
            (t.id for t in basis.values() if t is not None),
            fields=LIST_TYPE_FIELDS,
        )
        pay_ids: set[int] = set()
        pay_fields: set[str] = {"down_payment_pct"}
        for b in items:
            cur = current_payment(b.payments)
            if cur is None:
                continue
            pay_ids.add(cur.id)
            t = basis[id(b)]
            if t is None:
                continue
            # 현재 공고에 기준 타입 칸이 있을 때만 그 가격·할인 출처를 쓴다(``analysis.price_view.current_price``)
            if isinstance(cur.price_by_type, Mapping) and t.type_code in cur.price_by_type:
                pay_fields.add(f"price_by_type.{t.type_code}.max_price_won")
                pay_fields.add(f"price_by_type.{t.type_code}.floor_sample_price_won")
            disc = getattr(cur, "discount_by_type", None)
            if isinstance(disc, Mapping) and t.type_code in disc:
                pay_fields.add(f"discount_by_type.{t.type_code}")
        # 필드 IN 은 (entity, entity_id, field) 색인을 필드 수만큼 찾는다 — 필드가 많으면(기준 타입 코드가 여럿) 그 공고
        # 출처 행 전부를 읽는 편이 싸다(결과는 같다: 필요한 필드는 다 들어 있다)
        fields = pay_fields if len(pay_fields) <= _PAY_FIELDS_IN_MAX else None
        idx.load(session, "payment_terms", pay_ids, fields=fields)
        return idx
    idx.load(session, "complex", (b.cx.id for b in items))
    idx.load(session, "complex_type", (t.id for b in items for t in b.types))
    idx.load(session, "payment_terms", (p.id for b in items for p in b.payments))
    return idx


# ====================================================================== 점수 입력(요건 사전 계산용)


def score_input(
    b: ComplexBundle, fm_labels: Mapping[str, str | None] | None = None, *, asof_date: str | None = None
) -> ComplexScoreInput:
    """DB 행 → ComplexScoreInput(요건 사전 계산·미리보기) — 파이프라인과 같은 빌더
    ``analysis.complex_input.build_complex_input``(R3 minor 20). 판정 값은 사다리 행 그대로(봉투 status 포함).

    범위는 **현재 사실**로 계산한 값(``scope_result`` — 미리보기는 지금 사실로 다시 판정할 때의 입력)이고 '미해결'은
    계약 값 그대로 실린다(계약 .4). 판정기 추출 전 OCR 값은 null(``score_price``·``ocr_pending``, R3 C3).
    ``asof_date`` 가 없으면 묶음의 스냅샷 기준일(``load_bundles`` 가 채움)로 즉시 입주를 판단한다.
    """
    labels = {k: v for k, v in (fm_labels or {}).items() if v in _LABEL_VALUES}
    pays = _masked_payments(b)
    return build_complex_input(
        masked(b.cx, b.ocr_pending.get(("complex", b.cx.id), frozenset())),
        scope=scope_result(b).scope,
        price=score_price(b),
        asof_date=asof_date or b.asof_date or "",
        terms=pv.current_terms(pays),
        payments=pays,
        intake=pick_intake(b.intake),
        labels=labels,  # type: ignore[arg-type]
        ladders=b.ladders,
    )


_LABEL_VALUES = frozenset({"확인됨", "추정", "비공식", "재가공", "확인 불가"})


def group_by(rows: Iterable[Any], key: str) -> dict[Any, list[Any]]:
    out: dict[Any, list[Any]] = defaultdict(list)
    for r in rows:
        out[getattr(r, key)].append(r)
    return out
