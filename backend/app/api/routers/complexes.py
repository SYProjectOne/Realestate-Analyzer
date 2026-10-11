"""단지 상세(G3)·출처 패널·원문 파일."""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import snapshot_view as sv
from app.analysis.gap import unadjusted_from_flags
from app.api import views
from app.api.deps import DB, default_snapshot, get_complex, get_snapshot, resolve_scenario, settings_of
from app.api.errors import not_found
from app.api.facts import LABEL_UNKNOWN, FactMaker, day, fact, unknown
from app.api.routers.snapshots import SCENARIO_PATTERN
from app.api.views import (
    ScoreCtx,
    area_names,
    basis_type,
    competition_view,
    complex_header,
    current_payment,
    envelope_view,
    event_view,
    intake_view,
    judgment_days,
    ladder_view,
    payment_view,
    pick_intake,
    price_range,
    provenance_for,
    score_row,
    type_view,
)
from app.core.paths import resolve_raw_path
from app.core.raw_archive import archived_member, archived_stream  # noqa: F401  (재수출)
from app.core.settings import Settings, get_settings
from app.facts_view import region_catalysts
from app.models import (
    Catalyst,
    CatalystLink,
    ComparableSet,
    Competition,
    Complex,
    Decision,
    FieldProvenance,
    HumanCheck,
    JudgmentLog,
    RawDocument,
    Region,
    RemainingEvent,
    Scenario,
    ScoreComponent,
    ScoreRun,
    ScoreTotal,
    Snapshot,
)

router = APIRouter(tags=["complexes"])


# ====================================================================== 가격 갭·호재


def _coef_reason(c_per_year: Any) -> str:
    """대체 단지 보정 라벨 = 연간 계수 c(지역 설정, RA §6-2) — 총 보정률(c × 연수, coef_used)이 아니다(R3 W6).

    예 '대체·보정 c=0.015'. 총 보정률은 ``coef_used`` 필드로 따로 나간다."""
    return "대체·보정" if c_per_year is None else f"대체·보정 c={float(c_per_year):g}"


def comparables_by_complex(
    session: Session, snapshot_id: int, complex_ids: Sequence[int]
) -> dict[int, list[ComparableSet]]:
    """그 스냅샷 비교군 행(단지별, id 순) — 단지 여럿을 한 번에(materialize·비교 화면)."""
    out: dict[int, list[ComparableSet]] = defaultdict(list)
    ids = list(complex_ids)
    for i in range(0, len(ids), 500):
        for m in session.scalars(
            select(ComparableSet)
            .where(ComparableSet.snapshot_id == snapshot_id, ComparableSet.complex_id.in_(ids[i : i + 500]))
            .order_by(ComparableSet.id)
        ):
            out[m.complex_id].append(m)
    return out


def gap_view(
    session: Session,
    fm: FactMaker,
    ctx: ScoreCtx,
    cx: Complex,
    snapshot_id: int,
    price: dict[str, Any],
    *,
    members: Sequence[ComparableSet] | None = None,
) -> dict[str, Any]:
    gap_row = (ctx.components.get(cx.id) or {}).get("gap")
    label = gap_row.label if gap_row is not None and gap_row.label != LABEL_UNKNOWN else "추정"
    if members is None:
        members = comparables_by_complex(session, snapshot_id, [cx.id]).get(cx.id, [])
    checked = ctx.checked
    region = session.get(Region, cx.region_id)
    coef = dict((region.age_premium_coef if region is not None else None) or {})
    c_per_year = coef.get("c_per_year")
    comps: list[dict[str, Any]] = []
    for m in members:
        prov = f"cs_{m.id}"

        # 비교군 시세 = 실거래를 묶은 통계(재가공), 대체 단지면 추정 — gap 점수 라벨이 아니다(R3 minor 22)
        comp_label = "추정" if m.substitute else "재가공"
        comp_reason = "대체 단지" if m.substitute else (f"실거래 {m.n_trades}건 통계" if m.n_trades else None)

        def money(
            v: int | None, prov: str = prov, lb: str = comp_label, rs: str | None = comp_reason
        ) -> dict[str, Any]:
            return (
                fact(v, lb, prov, checked, reason=rs, unit="won")
                if v is not None
                else unknown("값 없음", checked, unit="won")
            )

        comps.append(
            {
                "name": m.member_apt_name,
                "completed_year": m.completed_year,
                "low": money(m.low_won),
                "median": money(m.median_won),
                "high": money(m.high_won),
                "adjusted_median": fact(
                    m.adjusted_median_won,
                    "추정",
                    prov,
                    checked,
                    reason=_coef_reason(c_per_year),
                    unit="won",
                )
                if m.adjusted_median_won is not None
                else None,
                "substitute": bool(m.substitute),
                "adjusted": bool(m.adjusted),
                "coef_used": float(m.coef_used) if m.coef_used is not None else None,
                "n_trades": m.n_trades,
                "outliers_excluded": int(m.outliers_excluded or 0),
                "trade_window": None,
            }
        )
    run_id = ctx.run.id if ctx.run is not None else None
    if gap_row is not None and run_id is not None and gap_row.raw_value is not None:
        gap_pct = fact(
            gap_row.raw_value, label, f"sc_{run_id}_{cx.id}_gap", checked, reason=gap_row.reason, unit="pct"
        )
    elif price["price_mid"]["label"] == LABEL_UNKNOWN:
        gap_pct = unknown("분양가 미공개", checked, unit="pct")
    else:
        gap_pct = unknown((gap_row.reason if gap_row else None) or "미판정", checked, unit="pct")
    gap_unadj = None
    raw_unadj = None
    if gap_row is not None:
        raw_unadj = gap_row.unadjusted_gap_pct
        if raw_unadj is None:  # 컬럼 이전(0004 전) 실행은 flags 태그(analysis.gap.unadjusted_tags)
            raw_unadj = unadjusted_from_flags(gap_row.flags)[0]
    if raw_unadj is not None and run_id is not None and gap_pct["label"] != LABEL_UNKNOWN:
        # 미보정 중앙값 기준 gap%(R3 W7) — 점수 실행이 score_component 에 저장한 값. 없으면 null(옛 실행)
        gap_unadj = fact(
            raw_unadj, label, f"sc_{run_id}_{cx.id}_gap", checked, reason="미보정 중앙값 기준", unit="pct"
        )
    if gap_row is not None and run_id is not None and gap_row.score_0_10 is not None:
        score = fact(
            gap_row.score_0_10,
            label,
            f"sc_{run_id}_{cx.id}_gap",
            checked,
            reason=gap_row.reason,
            unit="score",
        )
    else:
        score = unknown("미판정", checked, unit="score")
    empty = None
    if not comps:
        if price["price_mid"]["label"] == LABEL_UNKNOWN:
            empty = "비교군 없음(분양가 미공개 — 공고 후 재판정)"
        else:
            empty = f"비교군 없음({(gap_row.reason if gap_row else None) or '같은 생활권 비교 거래 없음'})"
    return {
        "price_low": price["price_low"],
        "price_high": price["price_high"],
        "price_mid": price["price_mid"],
        "comps": comps,
        "gap_pct": gap_pct,
        "gap_pct_unadjusted": gap_unadj,
        "score": score,
        "empty_reason": empty,
    }


def catalyst_view(
    c: Catalyst,
    checked: str | None,
    *,
    link: CatalystLink | None = None,
    linked_ids: Sequence[int] | None = None,
    fm: FactMaker | None = None,
) -> dict[str, Any]:
    """호재 1건. expected_ym 의 출처 = catalyst 의 field_provenance(호재 문구 원문) — classify 판정 seq 가
    아니다(R3 minor 22). ``fm`` 이 없으면(출처 색인 없이) 예정 시기는 '확인 불가(출처 미조회)'."""
    seq = c.judgment_seq
    if c.stage_prob is not None and seq is not None:
        prob = fact(c.stage_prob, "추정", f"jl_{seq}", checked, reason="판정기 classify", unit="prob")
    else:
        prob = unknown("미판정", checked, unit="prob")
    if c.expected_ym is None:
        expected = unknown("예정 시기 미기재", checked, unit="ym")
    elif fm is None:
        expected = unknown("출처 미조회", checked, unit="ym")
    else:
        expected = fm.field("catalyst", c.id, "expected_ym", c.expected_ym, unit="ym")
    out: dict[str, Any] = {
        "id": c.id,
        "name": c.name,
        "kind": c.kind,
        "stage": c.stage,
        "stage_prob": prob,
        "decision": c.decision,
        "expected_ym": expected,
        "location_confirmed": bool(c.location_confirmed),
        "linked": None,
        "distance_m": None,
        "weight": None,
        "linked_complex_ids": list(linked_ids) if linked_ids is not None else None,
        "lat": float(c.lat) if c.lat is not None else None,  # 계약 .8 — 사람 위치 확인(D11-5)
        "lon": float(c.lon) if c.lon is not None else None,
        "judgment_seq": seq,
        "source_url": c.source_url,
        "note": c.note,
    }
    if link is not None:
        out["linked"] = True
        out["distance_m"] = unknown(
            "거리 미측정" if link.distance_m is None else "거리 출처 없음", checked, unit="m"
        )
        out["weight"] = float(link.weight) if link.weight is not None else None
    return out


# ====================================================================== 단지 상세


def judgments_by_complex(
    session: Session, cxs: Sequence[Complex], snapshot_id: int, ladders: dict[int, Sequence[Any]]
) -> dict[int, list[JudgmentLog]]:
    """``complex_judgments`` 를 단지 여럿에 한 번에(같은 규칙 — materialize 의 단지 수천 개)."""
    ids = [c.id for c in cxs]
    seqs: dict[int, set[int]] = {
        c.id: {lad.judgment_seq for lad in ladders.get(c.id, ()) if lad.judgment_seq is not None} for c in cxs
    }
    for c in cxs:
        if c.inclusion_judgment_seq is not None:
            seqs[c.id].add(c.inclusion_judgment_seq)
    run_ids = list(session.scalars(select(ScoreRun.id).where(ScoreRun.snapshot_id == snapshot_id)))
    if run_ids:
        rerank = {
            s
            for s in session.scalars(select(ScoreRun.rerank_judgment_seq).where(ScoreRun.id.in_(run_ids)))
            if s is not None
        }
        for cid, s in session.execute(
            select(Decision.complex_id, Decision.judgment_seq).where(
                Decision.score_run_id.in_(run_ids), Decision.complex_id.is_not(None)
            )
        ):
            if cid in seqs and s is not None:
                seqs[cid].add(s)
        for cid in ids:
            seqs[cid] |= rerank
    all_seqs = sorted(set().union(*seqs.values())) if seqs else []
    by_seq: dict[int, JudgmentLog] = {}
    for i in range(0, len(all_seqs), 500):
        for j in session.scalars(select(JudgmentLog).where(JudgmentLog.seq.in_(all_seqs[i : i + 500]))):
            by_seq[j.seq] = j
    own: dict[int, list[JudgmentLog]] = defaultdict(list)
    for i in range(0, len(ids), 500):
        for j in session.scalars(
            select(JudgmentLog).where(
                JudgmentLog.complex_id.in_(ids[i : i + 500]),
                (JudgmentLog.snapshot_id == snapshot_id) | (JudgmentLog.snapshot_id.is_(None)),
            )
        ):
            if j.complex_id is not None:
                own[j.complex_id].append(j)
    out: dict[int, list[JudgmentLog]] = {}
    for cid in ids:
        rows = {j.seq: j for j in own.get(cid, [])}
        rows.update({s: by_seq[s] for s in seqs[cid] if s in by_seq})
        out[cid] = [rows[s] for s in sorted(rows)]
    return out


def complex_judgments(
    session: Session, cx: Complex, snapshot_id: int, ladders: Sequence[Any]
) -> list[JudgmentLog]:
    """이 단지·스냅샷의 판정 봉투.

    단지에 묶인 호출 + 이 스냅샷 파생 행(사다리·분류·decide·rerank)이 가리키는 호출."""
    seqs: set[int] = {lad.judgment_seq for lad in ladders if lad.judgment_seq is not None}
    if cx.inclusion_judgment_seq is not None:
        seqs.add(cx.inclusion_judgment_seq)
    run_ids = list(session.scalars(select(ScoreRun.id).where(ScoreRun.snapshot_id == snapshot_id)))
    if run_ids:
        seqs |= {
            s
            for s in session.scalars(
                select(Decision.judgment_seq).where(
                    Decision.score_run_id.in_(run_ids), Decision.complex_id == cx.id
                )
            )
            if s is not None
        }
        seqs |= {
            s
            for s in session.scalars(select(ScoreRun.rerank_judgment_seq).where(ScoreRun.id.in_(run_ids)))
            if s is not None
        }
    stmt = select(JudgmentLog).where(
        (JudgmentLog.seq.in_(sorted(seqs) or [-1]))
        | (
            (JudgmentLog.complex_id == cx.id)
            & ((JudgmentLog.snapshot_id == snapshot_id) | (JudgmentLog.snapshot_id.is_(None)))
        )
    )
    return list(session.scalars(stmt.order_by(JudgmentLog.seq)))


@router.get("/complexes/{id}")
def get_complex_detail(
    session: DB,
    request: Request,
    id: int,
    snapshot: int | None = None,
    scenario: Annotated[str, Query(pattern=SCENARIO_PATTERN)] = "base",
) -> JSONResponse:
    cx = get_complex(session, id)
    if snapshot is not None:
        snap = get_snapshot(session, snapshot)
        if snap.region_id != cx.region_id:  # R3 4차 minor: 다른 지역 스냅샷으로 단지를 읽지 않는다
            raise not_found(f"complex {id} in snapshot {snapshot}")
    else:
        found = default_snapshot(session, cx.region_id)
        if found is None:
            raise not_found(f"published snapshot for region {cx.region_id}")
        snap = found
    sc = resolve_scenario(session, scenario)
    # D13-1: 발행 리비전 = 저장본(그 리비전에 없던 단지는 404), 발행 전 = 실시간
    return JSONResponse(sv.details(session, snap, sc, cx, settings=settings_of(request)))


def detail_bodies(
    session: Session, settings: Settings, snap: Snapshot, sc: Scenario, complexes: Sequence[Complex]
) -> dict[int, dict[str, Any]]:
    """G3 단지 상세 응답(실시간 계산) — 단지 여럿을 한 번에(발행 때 지역 단지 전부를 저장, D13-1). 단지 1개 요청도
    같은 함수(같은 규칙·같은 바이트)."""
    if not complexes:
        return {}
    region = session.get(Region, snap.region_id)
    names = area_names(region)
    bundles = views.load_bundles(session, complexes, snap.id, scenario_id=sc.id)
    ids = [c.id for c in complexes]
    comps: dict[int, list[Competition]] = defaultdict(list)
    events: dict[int, list[RemainingEvent]] = defaultdict(list)
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        for c in session.scalars(
            select(Competition).where(Competition.complex_id.in_(chunk)).order_by(Competition.id)
        ):
            comps[c.complex_id].append(c)
        for ev in session.scalars(
            select(RemainingEvent).where(RemainingEvent.complex_id.in_(chunk)).order_by(RemainingEvent.id)
        ):
            events[ev.complex_id].append(ev)
    prov = provenance_for(session, bundles.values())
    prov.load(session, "competition", (c.id for cs in comps.values() for c in cs))
    prov.load(session, "remaining_event", (e.id for es in events.values() for e in es))
    fm = FactMaker(settings, prov)
    ctx = views.score_ctx(session, snap.id, sc, complex_ids=ids)
    # 그 리비전의 호재·단계·연결('호재 아님' 제외 — D11-2). 발행 리비전은 이 결과가 저장된다(D13-1)
    pairs = region_catalysts(session, snap.region_id)
    linked: dict[int, list[tuple[Any, Any]]] = defaultdict(list)
    for cat, cat_links in pairs:
        for lk in cat_links:
            linked[lk.complex_id].append((cat, lk))
    cat_days = judgment_days(session, (c.judgment_seq for c, _ in pairs))
    prov.load(session, "catalyst", (c.id for c, _ in pairs))  # 예정월 출처(사람 위치 확인 — D11-5)
    members = comparables_by_complex(session, snap.id, ids)
    judged = judgments_by_complex(session, [bundles[c.id].cx for c in complexes], snap.id,
                                  {c.id: bundles[c.id].ladders for c in complexes})  # fmt: skip
    out: dict[int, dict[str, Any]] = {}
    for cx0 in complexes:
        b = bundles[cx0.id]
        cx = b.cx
        days = judgment_days(
            session, [*(lad.judgment_seq for lad in b.ladders), cx.inclusion_judgment_seq, *ctx.jl_days]
        )
        days.update(ctx.jl_days)
        header = complex_header(fm, b, names)
        price = price_range(fm, b, header["notice_date"])
        basis = basis_type(b.types)
        pays = sorted(b.payments, key=lambda p: (p.effective_from, p.id))
        cur_pay = current_payment(b.payments)
        judgments = judged[cx.id]
        cats = {cat.id: cat for cat, _lk in linked.get(cx.id, [])}
        links = [lk for _cat, lk in linked.get(cx.id, [])]
        has_score = ctx.run is not None and cx.id in ctx.totals
        out[cx.id] = {
            "snapshot_id": snap.id,
            "asof_date": snap.asof_date,
            "scenario_id": sc.id,
            "header": header,
            "price": price,
            "intake_current": intake_view(cur) if (cur := pick_intake(b.intake)) is not None else None,
            "types": [type_view(fm, t, is_basis=basis is not None and t.id == basis.id) for t in b.types],
            "payment": [
                payment_view(
                    fm,
                    p,
                    first=pays[0],
                    is_current=cur_pay is not None and p.id == cur_pay.id,
                    basis_code=basis.type_code if basis else None,
                )
                for p in pays
            ],
            "competition": [competition_view(fm, c) for c in comps.get(cx.id, [])],
            "events": [event_view(fm, e) for e in events.get(cx.id, [])],
            "intake": [intake_view(i) for i in b.intake],
            "ladder": [
                ladder_view(lad, days.get(lad.judgment_seq) if lad.judgment_seq is not None else None)
                for lad in sorted(
                    b.ladders,
                    key=lambda x: (
                        ("move_in_plus_1y", "asof_plus_3y", "asof_plus_5y").index(x.horizon)
                        if x.horizon in ("move_in_plus_1y", "asof_plus_3y", "asof_plus_5y")
                        else 9
                    ),
                )
            ][:3],
            "gap": gap_view(session, fm, ctx, cx, snap.id, price, members=members.get(cx.id, [])),
            "catalysts": [
                catalyst_view(
                    cats[lk.catalyst_id],
                    cat_days.get(cats[lk.catalyst_id].judgment_seq or -1),
                    link=lk,
                    fm=fm,
                )
                for lk in links
                if lk.catalyst_id in cats
            ],
            "judgments": [envelope_view(j) for j in judgments],
            "score": score_row(ctx, b, names, jl_days=days) if has_score else None,
        }
    return out


# ====================================================================== 출처 패널


def _source_meta(session: Session, raw_id: int | None) -> tuple[str | None, int | None]:
    if raw_id is None:
        return None, None
    raw = session.get(RawDocument, raw_id)
    return (raw.source_kind, raw.http_status) if raw is not None else (None, None)


def _blank(prov_id: str, kind: str, label: str) -> dict[str, Any]:
    return {
        "id": prov_id,
        "kind": kind,
        "entity": None,
        "entity_id": None,
        "field": None,
        "value_text": None,
        "label": label,
        "reason": None,
        "url": None,
        "checked_at": None,
        "excerpt": None,
        "excerpt_start": None,
        "excerpt_end": None,
        "raw_document_id": None,
        "source_kind": None,
        "http_status": None,
        "source_rank": None,
        "chosen": None,
        "conflict_group": None,
        "conflicts": [],
        "formula_text": None,
        "judgment_seq": None,
        "compare_judgment_seq": None,
    }


def _conflict_item(o: FieldProvenance, okind: str | None) -> dict[str, Any]:
    return {
        "id": f"fp_{o.id}",
        "value_text": o.value_text,
        "label": o.label,
        "reason": o.reason,
        "url": o.url,
        "checked_at": o.checked_at,
        "source_kind": okind,
        "source_rank": o.source_rank,
        "chosen": bool(o.chosen),
        "excerpt": o.excerpt,
        "raw_document_id": o.raw_document_id,
    }


def _field_body(
    prov_id: str,
    fp: FieldProvenance,
    meta: tuple[str | None, int | None],
    conflicts: list[dict[str, Any]],
    demoted: bool,
) -> dict[str, Any]:
    kind, status = meta
    out = _blank(prov_id, "field", fp.label)
    out.update(
        entity=fp.entity,
        entity_id=fp.entity_id,
        field=fp.field,
        value_text=fp.value_text,
        reason=fp.reason,
        url=fp.url,
        checked_at=fp.checked_at,
        excerpt=fp.excerpt,
        excerpt_start=fp.excerpt_start,
        excerpt_end=fp.excerpt_end,
        raw_document_id=fp.raw_document_id,
        source_kind=kind,
        http_status=status,
        source_rank=fp.source_rank,
        chosen=bool(fp.chosen),
        conflict_group=fp.conflict_group,
        conflicts=conflicts,
        compare_judgment_seq=fp.compare_judgment_seq,
    )
    if demoted:
        # R3 4차 minor: 출처 서랍에도 강등(검증 모순)을 보인다 — 화면 Fact 와 같은 '확인 불가(검증 모순)'
        # (원문 발췌·값은 근거로 그대로 둔다). 오버레이는 읽기 전용(D11-3·D12-2)
        from app.facts_view import DEMOTION_LABEL, DEMOTION_REASON

        out.update(label=DEMOTION_LABEL, reason=f"{DEMOTION_REASON} — 모순 값(원문 그대로 표시)")
    return out


def _field_prov(session: Session, prov_id: str, fp_id: int) -> dict[str, Any]:
    fp = session.get(FieldProvenance, fp_id)
    if fp is None:
        raise not_found(f"provenance {prov_id}")
    if fp.conflict_group:
        others = select(FieldProvenance).where(
            FieldProvenance.conflict_group == fp.conflict_group, FieldProvenance.id != fp.id
        )
    else:
        others = select(FieldProvenance).where(
            FieldProvenance.entity == fp.entity,
            FieldProvenance.entity_id == fp.entity_id,
            FieldProvenance.field == fp.field,
            FieldProvenance.id != fp.id,
        )
    conflicts = [
        _conflict_item(o, _source_meta(session, o.raw_document_id)[0])
        for o in session.scalars(others.order_by(FieldProvenance.source_rank, FieldProvenance.id))
    ]
    demoted = False
    if fp.entity_id is not None and fp.chosen:
        from app.facts_view import load_overlay

        ov = load_overlay(session, entity=fp.entity, ids=[fp.entity_id])
        demoted = ov.is_demoted(fp.entity, fp.entity_id, fp.field)
    return _field_body(prov_id, fp, _source_meta(session, fp.raw_document_id), conflicts, demoted)


def _same_field(session: Session, r: FieldProvenance) -> list[FieldProvenance]:
    fp = FieldProvenance
    cond = fp.entity_id.is_(None) if r.entity_id is None else fp.entity_id == r.entity_id
    return list(session.scalars(select(fp).where(fp.entity == r.entity, cond, fp.field == r.field)))


def _field_provs(session: Session, fp_ids: set[int]) -> dict[str, dict[str, Any]]:
    """``_field_prov`` 를 출처 행 여럿에 한 번에(저장본 출처 서랍 — 1000 단지 ≈ 3만 6천 행, D14-1). 같은 규칙·같은 바이트
    (테스트가 한 행씩 계산과 비교한다). 서랍 안 충돌 출처(conflicts[].id)도 함께 만든다."""
    from app.facts_view import load_overlay

    fp = FieldProvenance
    rows: dict[int, FieldProvenance] = {}
    ids = sorted(fp_ids)
    for i in range(0, len(ids), 500):
        for r in views.light_rows(session, select(fp).where(fp.id.in_(ids[i : i + 500])), fp):
            rows[r.id] = r
    groups = sorted({str(r.conflict_group) for r in rows.values() if r.conflict_group})
    by_group: dict[str, list[FieldProvenance]] = defaultdict(list)
    for i in range(0, len(groups), 500):
        for r in views.light_rows(session, select(fp).where(fp.conflict_group.in_(groups[i : i + 500])), fp):
            by_group[str(r.conflict_group)].append(r)
    plain = [r for r in rows.values() if not r.conflict_group]
    by_triple: dict[tuple[str, int | None, str], list[FieldProvenance]] = defaultdict(list)
    ents: dict[str, set[int]] = defaultdict(set)
    for r in plain:
        if r.entity_id is not None:
            ents[r.entity].add(int(r.entity_id))
    triples = {(r.entity, r.entity_id, r.field) for r in plain}
    for ent, eids in ents.items():
        el = sorted(eids)
        for i in range(0, len(el), 500):
            for r in views.light_rows(
                session, select(fp).where(fp.entity == ent, fp.entity_id.in_(el[i : i + 500])), fp
            ):
                t = (r.entity, r.entity_id, r.field)
                if t in triples:
                    by_triple[t].append(r)
    for r in plain:
        if r.entity_id is None and (r.entity, None, r.field) not in by_triple:
            by_triple[(r.entity, None, r.field)] = _same_field(session, r)
    # 충돌 출처도 서랍으로(같은 묶음 — 이미 읽은 행). 그 행의 충돌 목록은 같은 묶음에서 자기를 뺀 것
    for lst in [*by_group.values(), *by_triple.values()]:
        for o in lst:
            rows.setdefault(o.id, o)
    raw_ids = sorted({r.raw_document_id for r in rows.values() if r.raw_document_id is not None})
    meta: dict[int, tuple[str | None, int | None]] = {}
    for i in range(0, len(raw_ids), 500):
        for rid, kind, status in session.execute(
            select(RawDocument.id, RawDocument.source_kind, RawDocument.http_status).where(
                RawDocument.id.in_(raw_ids[i : i + 500])
            )
        ):
            meta[int(rid)] = (kind, status)

    def m(rid: int | None) -> tuple[str | None, int | None]:
        return meta.get(rid, (None, None)) if rid is not None else (None, None)

    chosen_ents: dict[str, set[int]] = defaultdict(set)
    for r in rows.values():
        if r.entity_id is not None and r.chosen:
            chosen_ents[r.entity].add(int(r.entity_id))
    overlays = {ent: load_overlay(session, entity=ent, ids=sorted(eids)) for ent, eids in chosen_ents.items()}
    out: dict[str, dict[str, Any]] = {}
    for r in rows.values():
        if r.conflict_group:
            g = str(r.conflict_group)
            if g not in by_group:  # 충돌 출처로 따라온 행의 다른 묶음
                by_group[g] = list(session.scalars(select(fp).where(fp.conflict_group == g)))
            same = by_group[g]
        else:
            key = (r.entity, r.entity_id, r.field)
            if key not in by_triple:
                by_triple[key] = _same_field(session, r)
            same = by_triple[key]
        others = sorted((o for o in same if o.id != r.id), key=lambda o: (o.source_rank, o.id))
        conflicts = [_conflict_item(o, m(o.raw_document_id)[0]) for o in others]
        demoted = bool(
            r.entity_id is not None
            and r.chosen
            and overlays[r.entity].is_demoted(r.entity, r.entity_id, r.field)
        )
        pid = f"fp_{r.id}"
        out[pid] = _field_body(pid, r, m(r.raw_document_id), conflicts, demoted)
    return out


def _ints(rest: str, n: int) -> list[int] | None:
    parts = rest.split("_")
    if len(parts) < n or not all(p.isdigit() for p in parts[:n]):
        return None
    return [int(p) for p in parts[:n]]


def _score_total_formula(session: Session, run: ScoreRun, cid: int) -> str:
    comps = list(
        session.scalars(
            select(ScoreComponent)
            .where(ScoreComponent.score_run_id == run.id, ScoreComponent.complex_id == cid)
            .order_by(
                ScoreComponent.component, ScoreComponent.id
            )  # 식의 항 순서 고정(성분 이름순 — 색인 순서와 같다)
        )
    )
    terms = []
    for c in comps:
        w = (run.weights or {}).get(c.component)
        if w is None:
            continue
        s = "미판정" if c.score_0_10 is None else f"{float(c.score_0_10):g}"
        terms.append(f"{float(w):g}×{s}({c.component})")
    return "S = Σ w·s = " + " + ".join(terms) if terms else "S = Σ w·s"


def _score_run_prov(session: Session, prov_id: str, run_id: int) -> dict[str, Any]:
    """``st_<score_run_id>``: 점수 실행 전체 — 대시보드 KPI 집계(판정 대상 수 등)의 출처(R3 minor 22)."""
    run = session.get(ScoreRun, run_id)
    if run is None:
        raise not_found(f"provenance {prov_id}")
    scopes = Counter(
        s or "미기록"
        for s in session.scalars(select(ScoreTotal.judge_scope).where(ScoreTotal.score_run_id == run.id))
    )
    out = _blank(prov_id, "score_total", "추정")
    out.update(
        entity="score_run",
        entity_id=run.id,
        field="judge_scope",
        value_text=" · ".join(f"{k} {v}" for k, v in sorted(scopes.items())) or None,
        reason="집계",
        checked_at=day(run.created_at),
        formula_text=(
            "판정 대상 수 = 이 점수 실행의 score_total.judge_scope='판정 대상' 단지 수; "
            "접수 가능 수 = 같은 스냅샷 접수 표시값 '가능' 단지 수"
        ),
        judgment_seq=run.rerank_judgment_seq,
    )
    return out


@router.get("/provenance/{prov_id}")
def get_provenance(
    session: DB,
    prov_id: Annotated[str, Path(pattern=r"^(fp|sc|st|jl|hc|rd|cs)_[0-9A-Za-z_.:-]+$")],
    snapshot_id: int | None = None,
) -> JSONResponse:
    """출처 서랍(G3 ProvenanceTab). D14-1(계약 .11): 발행 리비전은 **저장본**(발행 순간의 출처 행·chosen·충돌·강등)에서
    읽는다 — ``snapshot_id`` 를 주면 그 리비전(발행 전이면 실시간, 그 발행 리비전에 없는 출처는 404), 주지 않으면 지역마다
    최신 발행 리비전 저장본에서 찾고 어디에도 없으면 실시간(발행 전 리비전에서만 보이는 출처)."""
    if snapshot_id is not None:
        snap = get_snapshot(session, snapshot_id)
        if sv.is_published(snap):
            got = sv.provenance(session, snap, prov_id)
            if got is None:
                raise sv.NotInRevision(f"발행 리비전 {snap.id} 저장본에 출처 {prov_id} 없음")
            return JSONResponse(got)
        return JSONResponse(provenance_body(session, prov_id))
    from app.api.views import latest_snapshot_id
    from app.models import Region

    pending: sv.MaterializePending | None = None
    for rid in list(session.scalars(select(Region.id).order_by(Region.id))):
        sid = latest_snapshot_id(session, int(rid))
        latest = session.get(Snapshot, sid) if sid is not None else None
        if latest is None or not sv.is_published(latest):
            continue
        try:
            found = sv.provenance(session, latest, prov_id)
        except (
            sv.MaterializePending
        ) as exc:  # 그 지역 최신 발행 리비전 저장본 미완 — 다른 지역에 없으면 503(R3 7차 m6)
            pending = exc
            continue
        if found is not None:
            return JSONResponse(found)
    if pending is not None:  # 실시간 200 으로 발행 순간이 아닌 값을 내보내지 않는다
        raise pending
    return JSONResponse(provenance_body(session, prov_id))


def provenance_bodies(session: Session, prov_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """출처 서랍 응답 여럿(저장본 — D14-1). 출처 행(fp)은 한 번에(충돌 출처 포함), 나머지는 한 건씩(없는 id 는 뺀다)."""
    from app.api.errors import ApiError

    want = sorted(set(prov_ids))
    fp_ids = {int(p[3:]) for p in want if p.startswith("fp_") and p[3:].isdigit()}
    out = _field_provs(session, fp_ids) if fp_ids else {}
    out.update(_score_provs(session, [p for p in want if p[:3] in ("sc_", "st_")]))
    out.update(_raw_provs(session, [p for p in want if p.startswith("rd_") and p[3:].isdigit()]))
    for pid in want:
        if pid in out or (pid.startswith("fp_") and pid[3:].isdigit()):
            continue
        try:
            out[pid] = provenance_body(session, pid)
        except ApiError:
            continue
    return out


def _score_provs(session: Session, prov_ids: list[str]) -> dict[str, dict[str, Any]]:
    """``sc_<실행>_<단지>_<성분>``·``st_<실행>_<단지>`` 서랍 여럿을 한 번에(점수 있는 1000 단지 × 시나리오 5 = 성분 3만 5천 —
    한 건씩이면 질의 7만). ``provenance_body`` 와 같은 값(테스트가 비교한다). 모양이 다르거나 행이 없는 id 는 뺀다(한 건씩
    경로가 404 로 같은 판단)."""
    sc_keys: dict[str, tuple[int, int, str]] = {}
    st_keys: dict[str, tuple[int, int]] = {}
    for pid in prov_ids:
        rest = pid[3:]
        if pid.startswith("sc_"):
            parts = rest.split("_", 2)
            if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                sc_keys[pid] = (int(parts[0]), int(parts[1]), parts[2])
        elif not rest.isdigit():
            ids = _ints(rest, 2)
            if ids is not None:
                st_keys[pid] = (ids[0], ids[1])
    if not sc_keys and not st_keys:
        return {}
    run_ids = sorted({k[0] for k in sc_keys.values()} | {k[0] for k in st_keys.values()})
    runs = {r.id: r for r in session.scalars(select(ScoreRun).where(ScoreRun.id.in_(run_ids)))}
    cx_ids = sorted({k[1] for k in sc_keys.values()} | {k[1] for k in st_keys.values()})
    comps: dict[tuple[int, int], list[Any]] = defaultdict(list)
    totals: dict[tuple[int, int], Any] = {}
    for rid in run_ids:
        for i in range(0, len(cx_ids), 500):
            chunk = cx_ids[i : i + 500]
            for c in views.light_rows(
                session,
                select(ScoreComponent)
                .where(ScoreComponent.score_run_id == rid, ScoreComponent.complex_id.in_(chunk))
                .order_by(ScoreComponent.id),
                ScoreComponent,
            ):
                comps[(rid, c.complex_id)].append(c)
            for t in views.light_rows(
                session,
                select(ScoreTotal)
                .where(ScoreTotal.score_run_id == rid, ScoreTotal.complex_id.in_(chunk))
                .order_by(ScoreTotal.id),
                ScoreTotal,
            ):
                totals.setdefault((rid, t.complex_id), t)
    out: dict[str, dict[str, Any]] = {}
    for pid, (rid, cid, comp) in sc_keys.items():
        run = runs.get(rid)
        row = next((c for c in comps.get((rid, cid), []) if c.component == comp), None)
        if row is None or run is None:
            continue
        body = _blank(pid, "score_component", row.label)
        body.update(
            entity="score_component",
            entity_id=row.id,
            field=row.component,
            reason=row.reason,
            value_text=None if row.score_0_10 is None else f"{float(row.score_0_10):g}",
            checked_at=day(run.created_at),
            formula_text=row.formula_text,
        )
        out[pid] = body
    for pid, (rid, cid) in st_keys.items():
        run = runs.get(rid)
        tot = totals.get((rid, cid))
        if run is None or tot is None:
            continue
        body = _blank(pid, "score_total", "추정")
        body.update(
            entity="score_total",
            entity_id=tot.id,
            field="total",
            value_text=None if tot.total is None else f"{float(tot.total):g}",
            reason=None if tot.total is not None else "미판정",
            checked_at=day(run.created_at),
            formula_text=_formula_of(
                run, sorted(comps.get((rid, cid), []), key=lambda c: (c.component, c.id))
            ),
            judgment_seq=run.rerank_judgment_seq,
        )
        out[pid] = body
    return out


def _raw_provs(session: Session, prov_ids: list[str]) -> dict[str, dict[str, Any]]:
    """``rd_<id>`` 서랍 여럿을 한 번에(D15-2 — 저장본이 접수 근거 원문 서랍을 모두 담는다). ``provenance_body`` 의 rd_ 와 같은 값."""
    ids = sorted({int(p[3:]) for p in prov_ids})
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(ids), 500):
        for raw in session.scalars(select(RawDocument).where(RawDocument.id.in_(ids[i : i + 500]))):
            out[f"rd_{raw.id}"] = _raw_body(f"rd_{raw.id}", raw)
    return out


def _raw_body(prov_id: str, raw: RawDocument) -> dict[str, Any]:
    ok = raw.path is not None and (raw.http_status is None or 200 <= raw.http_status < 300)
    out = _blank(prov_id, "raw_document", "확인됨" if ok else LABEL_UNKNOWN)
    out.update(
        entity="raw_document",
        entity_id=raw.id,
        url=raw.url,
        checked_at=raw.fetched_at,
        reason=None
        if ok
        else (str(raw.http_status) if raw.http_status else raw.error_text or "수집 실패"),
        raw_document_id=raw.id,
        source_kind=raw.source_kind,
        http_status=raw.http_status,
    )
    return out


def _formula_of(run: ScoreRun, comps: Sequence[Any]) -> str:
    """``_score_total_formula`` 와 같은 식(성분 행을 이미 읽은 경우)."""
    terms = []
    for c in comps:
        w = (run.weights or {}).get(c.component)
        if w is None:
            continue
        sv = "미판정" if c.score_0_10 is None else f"{float(c.score_0_10):g}"
        terms.append(f"{float(w):g}×{sv}({c.component})")
    return "S = Σ w·s = " + " + ".join(terms) if terms else "S = Σ w·s"


def provenance_body(session: Session, prov_id: str) -> dict[str, Any]:
    """출처 서랍 응답 1건(실시간). 없으면 404."""
    prefix, rest = prov_id[:2], prov_id[3:]
    if prefix == "fp":
        ids = _ints(rest, 1)
        if ids is None or len(rest.split("_")) != 1:
            raise not_found(f"provenance {prov_id}")
        return _field_prov(session, prov_id, ids[0])
    if prefix == "sc":
        parts = rest.split("_", 2)
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            raise not_found(f"provenance {prov_id}")
        row = session.scalars(
            select(ScoreComponent).where(
                ScoreComponent.score_run_id == int(parts[0]),
                ScoreComponent.complex_id == int(parts[1]),
                ScoreComponent.component == parts[2],
            )
        ).first()
        run = session.get(ScoreRun, int(parts[0]))
        if row is None or run is None:
            raise not_found(f"provenance {prov_id}")
        out = _blank(prov_id, "score_component", row.label)
        out.update(
            entity="score_component",
            entity_id=row.id,
            field=row.component,
            reason=row.reason,
            value_text=None if row.score_0_10 is None else f"{float(row.score_0_10):g}",
            checked_at=day(run.created_at),
            formula_text=row.formula_text,
        )
        return out
    if prefix == "st" and rest.isdigit():
        return _score_run_prov(session, prov_id, int(rest))
    if prefix == "st":
        ids = _ints(rest, 2)
        if ids is None:
            raise not_found(f"provenance {prov_id}")
        run = session.get(ScoreRun, ids[0])
        tot = session.scalars(
            select(ScoreTotal).where(ScoreTotal.score_run_id == ids[0], ScoreTotal.complex_id == ids[1])
        ).first()
        if run is None or tot is None:
            raise not_found(f"provenance {prov_id}")
        out = _blank(prov_id, "score_total", "추정")
        out.update(
            entity="score_total",
            entity_id=tot.id,
            field="total",
            value_text=None if tot.total is None else f"{float(tot.total):g}",
            reason=None if tot.total is not None else "미판정",
            checked_at=day(run.created_at),
            formula_text=_score_total_formula(session, run, ids[1]),
            judgment_seq=run.rerank_judgment_seq,
        )
        return out
    if prefix == "jl":
        ids = _ints(rest, 1)
        log = session.get(JudgmentLog, ids[0]) if ids else None
        if log is None:
            raise not_found(f"provenance {prov_id}")
        out = _blank(prov_id, "judgment", "추정")
        out.update(
            entity="judgment_log",
            entity_id=log.seq,
            field=log.tool,
            value_text=f"{log.tool} {log.status}"
            + (f" conf {float(log.confidence):g}" if log.confidence else ""),
            reason=f"판정기 {log.tool}",
            checked_at=day(log.created_at),
            excerpt=log.purpose,
            judgment_seq=log.seq,
        )
        return out
    if prefix == "hc":
        ids = _ints(rest, 1)
        hc = session.get(HumanCheck, ids[0]) if ids else None
        if hc is None:
            raise not_found(f"provenance {prov_id}")
        out = _blank(prov_id, "human_check", "확인됨")
        out.update(
            entity="human_check",
            entity_id=hc.id,
            field=hc.field,
            value_text=hc.value_text,
            reason=f"사람 확인({hc.kind})",
            checked_at=hc.checked_at,
            excerpt=hc.note,
        )
        return out
    if prefix == "rd":
        ids = _ints(rest, 1)
        raw = session.get(RawDocument, ids[0]) if ids else None
        if raw is None:
            raise not_found(f"provenance {prov_id}")
        return _raw_body(prov_id, raw)
    ids = _ints(rest, 1)
    cs = session.get(ComparableSet, ids[0]) if ids else None
    if cs is None:
        raise not_found(f"provenance {prov_id}")
    out = _blank(prov_id, "comparable_set", "추정")
    out.update(
        entity="comparable_set",
        entity_id=cs.id,
        field="median_won",
        value_text=f"{cs.member_apt_name} 중앙 {cs.median_won}" if cs.median_won else cs.member_apt_name,
        reason=cs.excluded_reason or ("대체·보정" if cs.substitute else None),
        excerpt=cs.note,
        checked_at=day(_snap_day(session, cs.snapshot_id)),
    )
    return out


def _snap_day(session: Session, sid: int) -> str | None:
    s = session.get(Snapshot, sid)
    return s.asof_date if s else None


# ====================================================================== 원문


_SERVE_TYPES = (("application/pdf", ".pdf"), ("image/png", ".png"), ("text/html", ".html"))


def _media_type(content_type: str | None, path: str) -> str:
    ct = (content_type or "").lower()
    for media, ext in _SERVE_TYPES:
        if (
            ct.startswith(media)
            or path.lower().endswith(ext)
            or (media == "text/html" and path.lower().endswith(".htm"))
        ):
            return media
    return "text/plain; charset=utf-8"


@router.get("/raw/{raw_document_id}")
def get_raw_document(
    session: DB,
    raw_document_id: int,
    as_: Annotated[str, Query(alias="as", pattern="^(file|text)$")] = "file",
) -> Any:
    raw = session.get(RawDocument, raw_document_id)
    if raw is None or raw.path is None:
        raise not_found(f"raw_document {raw_document_id}")
    rel = raw.text_path if as_ == "text" else raw.path
    if not rel:
        raise not_found(f"raw_document {raw_document_id} text")
    try:
        path = resolve_raw_path(rel)
    except ValueError as exc:
        raise not_found(f"raw_document {raw_document_id}") from exc
    if not path.is_file():
        stream = archived_stream(rel, get_settings().raw_dir)
        if stream is None:
            raise not_found(f"raw_document {raw_document_id} file")
        media = "text/plain; charset=utf-8" if as_ == "text" else _media_type(raw.content_type, rel)
        headers = {} if as_ == "text" else {"Content-Disposition": f'attachment; filename="{path.name}"'}
        return StreamingResponse(stream, media_type=media, headers=headers)
    if as_ == "text":
        return PlainTextResponse(path.read_text(encoding="utf-8", errors="replace"))
    return FileResponse(path, media_type=_media_type(raw.content_type, rel), filename=path.name)
