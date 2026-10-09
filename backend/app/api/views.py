"""DB 행 → 계약 응답 모양(dict). 라우터는 이 함수들을 조합한다.

모든 수치는 ``facts.FactMaker`` 로만 Fact 가 된다
(출처 없는 수치는 dev 에서 예외, prod 에서 '확인 불가(출처 누락)').
목록 화면(G2)은 1,000단지에서도 1초 안에 돌도록 관련 행을 한 번에 읽고 페이지 안의 단지만 Fact 로 만든다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
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
        "status": snap.status,
        "degraded": bool(snap.degraded),
        "created_at": snap.created_at,
        "published_at": snap.published_at,
        "contradicted_claims": int(contradicted or 0),
        "complex_count": len(ids),
    }


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
    ocr_pending: dict[tuple[str, int], frozenset[str]] = field(default_factory=dict)
    """판정기 추출 전 OCR 값 필드((entity, id) → 필드들) — 점수 입력에서 null(R3 C3, 파이프라인과 같은 규칙)."""


def _chunks(ids: Sequence[int], n: int = 500) -> Iterable[Sequence[int]]:
    for i in range(0, len(ids), n):
        yield ids[i : i + n]


def load_bundles(
    session: Session, complexes: Sequence[Complex], snapshot_id: int, *, with_ladders: bool = True
) -> dict[int, ComplexBundle]:
    snap = session.get(Snapshot, snapshot_id)
    asof = snap.asof_date if snap is not None else None
    out = {c.id: ComplexBundle(c, asof_date=asof) for c in complexes}
    ids = list(out)
    for chunk in _chunks(ids):
        for t in session.scalars(
            select(ComplexType).where(ComplexType.complex_id.in_(chunk)).order_by(ComplexType.id)
        ):
            out[t.complex_id].types.append(t)
        for p in session.scalars(
            select(PaymentTerms).where(PaymentTerms.complex_id.in_(chunk)).order_by(PaymentTerms.id)
        ):
            out[p.complex_id].payments.append(p)
        for i in session.scalars(
            select(IntakeStatus)
            .where(IntakeStatus.complex_id.in_(chunk), IntakeStatus.snapshot_id == snapshot_id)
            .order_by(IntakeStatus.id)
        ):
            out[i.complex_id].intake.append(i)
        if with_ladders:
            for lad in session.scalars(
                select(Ladder).where(Ladder.complex_id.in_(chunk), Ladder.snapshot_id == snapshot_id)
            ):
                out[lad.complex_id].ladders.append(lad)
    last_run = session.scalars(
        select(ScoreRun.id).where(ScoreRun.snapshot_id == snapshot_id).order_by(ScoreRun.id.desc()).limit(1)
    ).first()
    if last_run is not None:
        for b in out.values():
            b.scored_run = True
        for chunk in _chunks(ids):
            # 저장 범위 = 이 스냅샷 마지막 점수 실행의 score_total.judge_scope(D10-1 — 한 실행의 시나리오는 같은 범위)
            for cid, scope in session.execute(
                select(ScoreTotal.complex_id, ScoreTotal.judge_scope).where(
                    ScoreTotal.score_run_id == last_run,
                    ScoreTotal.complex_id.in_(chunk),
                    ScoreTotal.judge_scope.is_not(None),
                )
            ):
                out[cid].stored_scope = scope
    from app.scheduler.inputs import ocr_pending_fields

    targets: list[tuple[str, list[tuple[int, int]]]] = [
        ("complex", [(b.cx.id, b.cx.id) for b in out.values()]),
        ("complex_type", [(t.complex_id, t.id) for b in out.values() for t in b.types]),
        ("payment_terms", [(p.complex_id, p.id) for b in out.values() for p in b.payments]),
    ]
    for entity, rows in targets:
        pending = ocr_pending_fields(session, entity, [eid for _, eid in rows])
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


def price_numbers(t: ComplexType | None) -> tuple[int | None, int | None]:
    """공고문 타입 행만으로 만든 (low, high) — **현재 구매가가 아니다**(최신 공고 가격 미반영).

    화면·CSV·미리보기의 현재 구매가는 ``bundle_price(b)``
    (= ``analysis.price_view.current_price``, R3 M3)를 쓴다.
    """
    if t is None:
        return None, None
    view = pv.current_price([t], [])
    return view.low_won, view.high_won


def bundle_price(b: ComplexBundle) -> pv.PriceView:
    """§6-1 현재 구매가(최신 payment_terms.price_by_type 우선) — 파이프라인·보고서와 같은 함수(R3 M3)."""
    return pv.current_price(b.types, b.payments)


def _masked_types(b: ComplexBundle) -> list[Any]:
    return [masked(t, b.ocr_pending.get(("complex_type", t.id), frozenset())) for t in b.types]


def _masked_payments(b: ComplexBundle) -> list[Any]:
    return [masked(p, b.ocr_pending.get(("payment_terms", p.id), frozenset())) for p in b.payments]


def score_price(b: ComplexBundle) -> pv.PriceView:
    """점수 입력 구매가 = ``bundle_price`` 에서 판정기 추출 전 OCR 값을 뺀 것(R3 C3 — 파이프라인 ``load_facts`` 와 같은
    규칙). 화면 표시 가격은 ``bundle_price``(OCR 값은 '추정(OCR)' 라벨로 보인다)."""
    if not b.ocr_pending:
        return bundle_price(b)
    return pv.current_price(_masked_types(b), _masked_payments(b))


def scope_result(b: ComplexBundle) -> scope_rules.ScopeResult:
    """**현재 사실**로 계산한 판정 범위 = ``analysis.scope.judge_scope``(D9-1) — 파이프라인·보고서와 같은 함수.

    화면·KPI·TOP 5 에 보이는 범위는 저장값(``shown_scope``, D10-1)이다. 이 값은 미리보기(요건 사전 계산)와
    '재판정 필요' 비교(``rejudge_needed``)에만 쓴다."""
    cur = scope_rules.pick_intake(b.intake)
    return scope_rules.judge_scope(
        inclusion_class=b.cx.inclusion_class,
        inclusion_decision=b.cx.inclusion_decision,
        has_price=score_price(b).known,
        intake_status=cur.status if cur is not None else None,
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

    점수 실행이 있는 스냅샷에서 그 단지 행이 없는데(그 실행에서 점수 밖) 지금은 점수 대상이면 역시 True."""
    current = scope_rules.contract_scope(scope_result(b).scope)
    stored = _stored(b, ctx)
    if stored:
        return stored != current
    has_run = (ctx is not None and ctx.run is not None) or b.scored_run
    return has_run and scope_rules.is_scored(current)


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


def _resale_end(fm: FactMaker, cx: Complex, winner: dict[str, Any], months: dict[str, Any]) -> dict[str, Any]:
    if cx.winner_date is None or cx.resale_months is None:
        return fm.derived(None, [winner, months], unit="date")
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


def price_range(fm: FactMaker, b: ComplexBundle, notice: dict[str, Any] | None = None) -> dict[str, Any]:
    """§6-1 현재 구매가 범위 = ``bundle_price``(최신 공고 가격 우선, R3 M3). 출처는 쓴 필드 그대로."""
    view = bundle_price(b)
    t = basis_type(b.types)
    if t is None or not view.known:
        reason = view.empty_reason or "분양가 미공개"
        if notice is not None and notice["label"] == LABEL_UNKNOWN and notice.get("reason"):
            reason = str(notice["reason"])
        u = unknown(reason, None, unit="won")
        return {
            "basis_type_code": view.basis_type_code,
            "price_low": u,
            "price_high": dict(u),
            "price_mid": dict(u),
            "composition": None,
            "change_vs_first_pct": None,
        }

    def ref_fact(ref: pv.FieldRef) -> dict[str, Any]:
        return fm.field(ref.entity, ref.entity_id, ref.field, ref.value, unit="won")

    low_won, high_won = view.low_won, view.high_won
    low = fm.combine(low_won, [ref_fact(r) for r in view.low_refs], unit="won")
    high = fm.combine(high_won, [ref_fact(r) for r in view.high_refs], unit="won")
    mid_val = pv.mid_rounded(view)
    mid = fm.derived(mid_val, [low, high], unit="won")
    parts = ["공급가"]
    if t.balcony_won:
        parts.append(f"발코니 {_man(t.balcony_won)}")
    if t.options_required_won:
        parts.append(f"필수 옵션 {_man(t.options_required_won)}")
    return {
        "basis_type_code": t.type_code,
        "price_low": low,
        "price_high": high,
        "price_mid": mid,
        "composition": " + ".join(parts),
        "change_vs_first_pct": _price_change(fm, b, t),
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
    }


def ladder_view(row: Ladder, checked: str | None) -> dict[str, Any]:
    ok = row.status == "ok"
    seq = row.judgment_seq

    def pf(v: Any) -> dict[str, Any]:
        if v is None:
            return unknown("값 없음" if ok else f"미해결({row.status})", checked, unit="prob")
        if not ok:
            return unknown(f"미해결({row.status})", checked, unit="prob")
        if seq is None:
            return unknown("판정 기록 없음", checked, unit="prob")
        return fact(v, "추정", f"jl_{seq}", checked, reason="판정기 noul", unit="prob")

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
    want = sorted({s for s in seqs if s is not None})
    out: dict[int, str | None] = {}
    for chunk in _chunks(want):
        for seq, created in session.execute(
            select(JudgmentLog.seq, JudgmentLog.created_at).where(JudgmentLog.seq.in_(chunk))
        ):
            out[seq] = day(created)
    return out


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

    @property
    def weights(self) -> dict[str, float]:
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


def score_ctx(
    session: Session, snapshot_id: int, scenario: Scenario, *, complex_ids: Sequence[int] | None = None
) -> ScoreCtx:
    run = latest_run(session, snapshot_id, scenario.id)
    ctx = ScoreCtx(run=run, scenario=scenario)
    if run is None:
        return ctx
    comp_stmt = select(ScoreComponent).where(ScoreComponent.score_run_id == run.id)
    tot_stmt = select(ScoreTotal).where(ScoreTotal.score_run_id == run.id)
    dec_stmt = select(Decision).where(Decision.score_run_id == run.id, Decision.complex_id.is_not(None))
    if complex_ids is not None:
        ids = list(complex_ids)
        comp_stmt = comp_stmt.where(ScoreComponent.complex_id.in_(ids))
        tot_stmt = tot_stmt.where(ScoreTotal.complex_id.in_(ids))
        dec_stmt = dec_stmt.where(Decision.complex_id.in_(ids))
    for c in session.scalars(comp_stmt):
        ctx.components.setdefault(c.complex_id, {})[c.component] = c
    for t in session.scalars(tot_stmt):
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
    p10: dict[str, Any] = ladder_view(lad, checked)["p10"]
    return p10


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
        out.append(
            RowData(
                b=b,
                scope=shown_scope(b, ctx),
                intake=pick_intake(b.intake),
                price_low=low,
                price_high=high,
                price_mid=mid,
                total=t.total if t is not None else None,
                rank=t.rank if t is not None else None,
                resale_end=resale_end,
                gap_pct=gap.raw_value if gap is not None else None,
                p10=lad.p10 if lad is not None and lad.status == "ok" else None,
                rejudge_needed=rejudge_needed(b, ctx),
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
    price = price_range(fm, b, notice)
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
        "resale_end": _resale_end(fm, cx, winner, months),
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


def provenance_for(session: Session, bundles: Iterable[ComplexBundle]) -> ProvIndex:
    """단지 묶음의 사실 행 출처를 한 번에 읽는다."""
    items = list(bundles)
    idx = ProvIndex()
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

    '미해결' 단지는 계약 .3 Literal 에 값이 없어 judge_scope='제외'로 실린다
    (``analysis.scope.contract_scope``).
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
