"""단지 상세(G3)·출처 패널·원문 파일."""

from __future__ import annotations

import re
import tarfile
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path as FsPath
from pathlib import PurePosixPath
from typing import IO, Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.gap import unadjusted_from_flags
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
    load_bundles,
    payment_view,
    pick_intake,
    price_range,
    provenance_for,
    score_ctx,
    score_row,
    type_view,
)
from app.core.paths import resolve_raw_path
from app.core.settings import get_settings
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


def gap_view(
    session: Session, fm: FactMaker, ctx: ScoreCtx, cx: Complex, snapshot_id: int, price: dict[str, Any]
) -> dict[str, Any]:
    gap_row = (ctx.components.get(cx.id) or {}).get("gap")
    label = gap_row.label if gap_row is not None and gap_row.label != LABEL_UNKNOWN else "추정"
    members = list(
        session.scalars(
            select(ComparableSet)
            .where(ComparableSet.snapshot_id == snapshot_id, ComparableSet.complex_id == cx.id)
            .order_by(ComparableSet.id)
        )
    )
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
    else:
        found = default_snapshot(session, cx.region_id)
        if found is None:
            raise not_found(f"published snapshot for region {cx.region_id}")
        snap = found
    sc = resolve_scenario(session, scenario)
    region = session.get(Region, cx.region_id)
    names = area_names(region)
    b = load_bundles(session, [cx], snap.id, scenario_id=sc.id)[cx.id]
    comps = list(
        session.scalars(select(Competition).where(Competition.complex_id == cx.id).order_by(Competition.id))
    )
    events = list(
        session.scalars(
            select(RemainingEvent).where(RemainingEvent.complex_id == cx.id).order_by(RemainingEvent.id)
        )
    )
    prov = provenance_for(session, [b])
    prov.load(session, "competition", (c.id for c in comps))
    prov.load(session, "remaining_event", (e.id for e in events))
    fm = FactMaker(settings_of(request), prov)
    ctx = score_ctx(session, snap.id, sc, complex_ids=[cx.id])
    days = judgment_days(
        session, [*(lad.judgment_seq for lad in b.ladders), cx.inclusion_judgment_seq, *ctx.jl_days]
    )
    days.update(ctx.jl_days)
    header = complex_header(fm, b, names)
    price = price_range(fm, b, header["notice_date"])
    basis = basis_type(b.types)
    pays = sorted(b.payments, key=lambda p: (p.effective_from, p.id))
    cur_pay = current_payment(b.payments)
    judgments = complex_judgments(session, cx, snap.id, b.ladders)
    links = list(session.scalars(select(CatalystLink).where(CatalystLink.complex_id == cx.id)))
    cats = {
        c.id: c
        for c in session.scalars(select(Catalyst).where(Catalyst.id.in_([lk.catalyst_id for lk in links])))
    }
    cat_days = judgment_days(session, (c.judgment_seq for c in cats.values()))
    has_score = ctx.run is not None and cx.id in ctx.totals
    body = {
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
        "competition": [competition_view(fm, c) for c in comps],
        "events": [event_view(fm, e) for e in events],
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
        "gap": gap_view(session, fm, ctx, cx, snap.id, price),
        "catalysts": [
            catalyst_view(
                cats[lk.catalyst_id], cat_days.get(cats[lk.catalyst_id].judgment_seq or -1), link=lk, fm=fm
            )
            for lk in links
            if lk.catalyst_id in cats
        ],
        "judgments": [envelope_view(j) for j in judgments],
        "score": score_row(ctx, b, names, jl_days=days) if has_score else None,
    }
    return JSONResponse(body)


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


def _field_prov(session: Session, prov_id: str, fp_id: int) -> dict[str, Any]:
    fp = session.get(FieldProvenance, fp_id)
    if fp is None:
        raise not_found(f"provenance {prov_id}")
    kind, status = _source_meta(session, fp.raw_document_id)
    out = _blank(prov_id, "field", fp.label)
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
    conflicts = []
    for o in session.scalars(others.order_by(FieldProvenance.source_rank, FieldProvenance.id)):
        okind, _ = _source_meta(session, o.raw_document_id)
        conflicts.append(
            {
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
        )
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
    return out


def _ints(rest: str, n: int) -> list[int] | None:
    parts = rest.split("_")
    if len(parts) < n or not all(p.isdigit() for p in parts[:n]):
        return None
    return [int(p) for p in parts[:n]]


def _score_total_formula(session: Session, run: ScoreRun, cid: int) -> str:
    comps = list(
        session.scalars(
            select(ScoreComponent).where(
                ScoreComponent.score_run_id == run.id, ScoreComponent.complex_id == cid
            )
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
) -> JSONResponse:
    prefix, rest = prov_id[:2], prov_id[3:]
    if prefix == "fp":
        ids = _ints(rest, 1)
        if ids is None or len(rest.split("_")) != 1:
            raise not_found(f"provenance {prov_id}")
        return JSONResponse(_field_prov(session, prov_id, ids[0]))
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
        return JSONResponse(out)
    if prefix == "st" and rest.isdigit():
        return JSONResponse(_score_run_prov(session, prov_id, int(rest)))
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
        return JSONResponse(out)
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
        return JSONResponse(out)
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
        return JSONResponse(out)
    if prefix == "rd":
        ids = _ints(rest, 1)
        raw = session.get(RawDocument, ids[0]) if ids else None
        if raw is None:
            raise not_found(f"provenance {prov_id}")
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
        return JSONResponse(out)
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
    return JSONResponse(out)


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


_MONTH_ARCHIVE = re.compile(r"^\d{4}-\d{2}\.tar\.gz$")


_CHUNK = 64 * 1024


def _open_member(archive: FsPath, member: str) -> tuple[tarfile.TarFile, IO[bytes]] | None:
    """압축을 스트림 모드("r|gz")로 열어 구성원을 찾는다 — 압축 전체를 풀거나 목록 전체를 먼저 읽지 않는다.

    찾으면 (열린 tar, 구성원 파일)을 돌려준다 — 닫는 것은 ``_chunks`` 가 다 흘린 뒤에."""
    tar = tarfile.open(archive, "r|gz")  # noqa: SIM115 — 응답 스트림이 끝날 때 _chunks 가 닫는다
    try:
        for info in tar:
            if info.name != member or not info.isfile():
                continue
            fh = tar.extractfile(info)
            if fh is not None:
                return tar, fh
    except BaseException:
        tar.close()
        raise
    tar.close()
    return None


def _chunks(tar: tarfile.TarFile, fh: IO[bytes]) -> Iterator[bytes]:
    try:
        while chunk := fh.read(_CHUNK):
            yield chunk
    finally:
        tar.close()


def archived_stream(rel: str, raw_dir: FsPath) -> Iterator[bytes] | None:
    """월별 압축(runbook §6 · ``infra/raw_archive.sh``) 안의 원문을 64KiB 조각으로 흘린다(재리뷰 F3).

    압축 = ``<RAW_DIR>/<source>/<yyyy-mm>.tar.gz``,
    구성원 이름 = RAW_DIR 기준 상대 경로(DB 의 ``path`` 그대로).
    같은 달 압축을 먼저, 없으면 그 소스의 다른 압축(*.tar.gz)을 본다. 없으면 None.
    요청마다 구성원 전체를 메모리에 올리지 않는다(전에는 ``getmember`` 로 목록 전체 + ``read()`` 전체)."""
    parts = PurePosixPath(rel.replace("\\", "/")).parts
    if len(parts) < 2:
        return None
    src_dir = raw_dir / parts[0]
    if not src_dir.is_dir():
        return None
    month = parts[1][:7] if len(parts) >= 3 else None
    archives = sorted(src_dir.glob("*.tar.gz"))
    archives.sort(key=lambda a: (a.name != f"{month}.tar.gz", not _MONTH_ARCHIVE.match(a.name), a.name))
    member = PurePosixPath(*parts).as_posix()
    for archive in archives:
        try:
            opened = _open_member(archive, member)
        except (OSError, tarfile.TarError, EOFError):
            continue
        if opened is not None:
            return _chunks(*opened)
    return None


def archived_member(rel: str, raw_dir: FsPath) -> bytes | None:
    """``archived_stream`` 을 모두 읽은 바이트(작은 원문·테스트용)."""
    stream = archived_stream(rel, raw_dir)
    return None if stream is None else b"".join(stream)


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
