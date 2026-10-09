"""스냅샷 화면: 대시보드(G1), 단지 표(G2)·CSV, 변경 피드(G1·G8)."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DB, get_snapshot, resolve_scenario, settings_of
from app.api.errors import ApiError, not_found
from app.api.facts import LABEL_UNKNOWN, FactMaker, ProvIndex, fact, unknown, weakest
from app.api.views import (
    ComplexBundle,
    RowData,
    ScoreCtx,
    area_names,
    complex_row,
    complex_rows_data,
    ladder_days,
    load_bundles,
    provenance_for,
    score_ctx,
    score_row,
)
from app.core.time import now_kst
from app.models import ChangeEvent, Complex, RawDocument, Region, Snapshot, Supply, Unsold

router = APIRouter(tags=["snapshots"])

SCENARIO_PATTERN = r"^(base|A|B|C|D|[0-9]+)$"
SORT_PATTERN = (
    r"^-?(total|rank|name|price_mid|price_low|move_in_ym|resale_end|gap_pct|p10|living_area|last_change)$"
)
ScenarioQ = Annotated[str, Query(pattern=SCENARIO_PATTERN)]
SortQ = Annotated[str, Query(pattern=SORT_PATTERN)]

_TABS = {
    "complex_type": "price",
    "payment_terms": "payment",
    "competition": "events",
    "remaining_event": "events",
    "catalyst": "catalysts",
    "judge": "judgments",
    "notice": "events",
}


# ====================================================================== 변경 피드


def change_view(ev: ChangeEvent, names: Mapping[int, str]) -> dict[str, Any]:
    return {
        "id": ev.id,
        "snapshot_id": ev.snapshot_id,
        "entity": ev.entity,
        "entity_id": ev.entity_id,
        "field": ev.field[:64],
        "old_text": ev.old_text,
        "new_text": ev.new_text,
        "detected_at": ev.detected_at,
        "severity": ev.severity,
        "triggers_rejudge": bool(ev.triggers_rejudge),
        "complex_id": ev.complex_id,
        "complex_name": names.get(ev.complex_id) if ev.complex_id is not None else None,
        "tab": _TABS.get(ev.entity),
    }


def _names(session: Session, ids: Sequence[int | None]) -> dict[int, str]:
    want = sorted({i for i in ids if i is not None})
    if not want:
        return {}
    return {
        cid: name
        for cid, name in session.execute(select(Complex.id, Complex.name).where(Complex.id.in_(want)))
    }


def changes_for(
    session: Session,
    snap: Snapshot,
    *,
    since: str | None = None,
    compare: Snapshot | None = None,
    severity: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    region_snaps = {
        s.id: s for s in session.scalars(select(Snapshot).where(Snapshot.region_id == snap.region_id))
    }
    stmt = select(ChangeEvent)
    if compare is not None:
        ids = [sid for sid, s in region_snaps.items() if compare.asof_date < s.asof_date <= snap.asof_date]
        stmt = stmt.where(ChangeEvent.snapshot_id.in_(ids or [-1]))
    elif since is not None:
        cids = list(session.scalars(select(Complex.id).where(Complex.region_id == snap.region_id)))
        stmt = stmt.where(
            ChangeEvent.detected_at >= since,
            (ChangeEvent.snapshot_id.in_(list(region_snaps)))
            | (ChangeEvent.complex_id.in_(cids or [-1]))
            | ((ChangeEvent.entity == "region") & (ChangeEvent.entity_id == snap.region_id)),
        )
    else:
        stmt = stmt.where(ChangeEvent.snapshot_id == snap.id)
    if severity:
        stmt = stmt.where(ChangeEvent.severity == severity)
    stmt = stmt.order_by(ChangeEvent.detected_at.desc(), ChangeEvent.id.desc())
    if limit:
        stmt = stmt.limit(limit)
    events = list(session.scalars(stmt))
    names = _names(session, [e.complex_id for e in events])
    return [change_view(e, names) for e in events]


@router.get("/snapshots/{sid}/changes")
def list_changes(
    session: DB,
    sid: int,
    since: Annotated[str | None, Query(min_length=10, max_length=32)] = None,
    compare_snapshot: int | None = None,
    severity: Annotated[str | None, Query(pattern="^(info|notice|critical)$")] = None,
) -> JSONResponse:
    snap = get_snapshot(session, sid)
    compare = get_snapshot(session, compare_snapshot) if compare_snapshot is not None else None
    return JSONResponse(changes_for(session, snap, since=since, compare=compare, severity=severity))


# ====================================================================== 단지 표 (G2)


_FILTER_KEYS = {
    "living_area",
    "intake_status",
    "land_type",
    "inclusion_class",
    "judge_scope",
    "resale_end_before",
    "price_min",
    "price_max",
    "move_in_year",
    "q",
}


def parse_filters(request: Request) -> dict[str, Any]:
    """deepObject ``filter[key]=value`` (openapi ComplexFilter, additionalProperties false)."""
    out: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    for key, value in request.query_params.multi_items():
        if key == "filter":
            errors.append({"loc": ["query", "filter"], "msg": "filter[...] 형식만 허용"})
            continue
        if not key.startswith("filter["):
            continue
        name = key[7:-1] if key.endswith("]") else ""
        if name not in _FILTER_KEYS:
            errors.append({"loc": ["query", key], "msg": "알 수 없는 필터"})
            continue
        try:
            if name in ("price_min", "price_max"):
                v = int(value)
                if v < 0:
                    raise ValueError
                out[name] = v
            elif name == "move_in_year":
                v = int(value)
                if not 2000 <= v <= 2100:
                    raise ValueError
                out[name] = v
            elif name == "resale_end_before":
                out[name] = date.fromisoformat(value).isoformat()
            elif name == "q":
                if len(value) > 50:
                    raise ValueError
                out[name] = value.strip()
            else:
                out[name] = {v.strip() for v in value.split(",") if v.strip()}
        except ValueError:
            errors.append({"loc": ["query", key], "msg": "값 형식 오류"})
    if errors:
        raise ApiError(422, "validation_error", "filter 검증 실패", field_errors=errors)
    return out


def _match(rd: RowData, f: Mapping[str, Any]) -> bool:
    cx = rd.b.cx
    if "living_area" in f and (cx.living_area or "") not in f["living_area"]:
        return False
    if "intake_status" in f and (rd.intake.status if rd.intake else "") not in f["intake_status"]:
        return False
    if "land_type" in f and (cx.land_type or "") not in f["land_type"]:
        return False
    if "inclusion_class" in f and (cx.inclusion_class or "") not in f["inclusion_class"]:
        return False
    if "judge_scope" in f and rd.scope not in f["judge_scope"]:
        return False
    if "resale_end_before" in f and (rd.resale_end is None or rd.resale_end > f["resale_end_before"]):
        return False
    if "price_min" in f and (rd.price_mid is None or rd.price_mid < f["price_min"]):
        return False
    if "price_max" in f and (rd.price_mid is None or rd.price_mid > f["price_max"]):
        return False
    if "move_in_year" in f and not (cx.move_in_ym or "").startswith(str(f["move_in_year"])):
        return False
    if f.get("q"):
        hay = " ".join([cx.name, *(cx.former_names or []), cx.address or ""])
        if f["q"] not in hay:
            return False
    return True


def _sort_key(name: str, last: Mapping[int, str]) -> Callable[[RowData], Any]:
    getters: dict[str, Callable[[RowData], Any]] = {
        "total": lambda r: r.total,
        "rank": lambda r: r.rank,
        "name": lambda r: r.b.cx.name,
        "price_mid": lambda r: r.price_mid,
        "price_low": lambda r: r.price_low,
        "move_in_ym": lambda r: r.b.cx.move_in_ym,
        "resale_end": lambda r: r.resale_end,
        "gap_pct": lambda r: r.gap_pct,
        "p10": lambda r: r.p10,
        "living_area": lambda r: r.b.cx.living_area,
        "last_change": lambda r: last.get(r.b.cx.id),
    }
    return getters[name]


def sort_rows(rows: list[RowData], sort: str, last: Mapping[int, str]) -> list[RowData]:
    desc = sort.startswith("-")
    get = _sort_key(sort.lstrip("-"), last)
    present = [r for r in rows if get(r) is not None]
    missing = [r for r in rows if get(r) is None]
    present.sort(key=lambda r: r.b.cx.id)
    present.sort(key=get, reverse=desc)  # 안정 정렬: 같은 값은 complex_id 오름차순
    missing.sort(key=lambda r: r.b.cx.id)
    return present + missing


def last_changes(session: Session, complex_ids: Sequence[int]) -> dict[int, ChangeEvent]:
    out: dict[int, ChangeEvent] = {}
    ids = list(complex_ids)
    for i in range(0, len(ids), 500):
        stmt = (
            select(ChangeEvent)
            .where(ChangeEvent.complex_id.in_(ids[i : i + 500]))
            .order_by(ChangeEvent.detected_at, ChangeEvent.id)
        )
        for ev in session.scalars(stmt):
            if ev.complex_id is not None:
                out[ev.complex_id] = ev
    return out


def _last_change_view(ev: ChangeEvent | None) -> dict[str, Any] | None:
    if ev is None:
        return None
    return {"at": ev.detected_at, "field": ev.field, "severity": ev.severity, "change_event_id": ev.id}


def list_rows(
    session: Session, snap: Snapshot, scenario_value: str, request: Request, sort: str
) -> tuple[ScoreCtx, list[RowData], dict[str, str], dict[int, ChangeEvent]]:
    filters = parse_filters(request)
    scenario = resolve_scenario(session, scenario_value)
    region = session.get(Region, snap.region_id)
    complexes = list(session.scalars(select(Complex).where(Complex.region_id == snap.region_id)))
    bundles = load_bundles(session, complexes, snap.id)
    ctx = score_ctx(session, snap.id, scenario)
    rows = [r for r in complex_rows_data(bundles, ctx) if _match(r, filters)]
    last = last_changes(session, [r.b.cx.id for r in rows])
    rows = sort_rows(rows, sort, {k: v.detected_at for k, v in last.items()})
    return ctx, rows, area_names(region), last


def build_rows(
    session: Session,
    request: Request,
    ctx: ScoreCtx,
    rows: Sequence[RowData],
    names: Mapping[str, str],
    last: Mapping[int, ChangeEvent],
) -> list[dict[str, Any]]:
    bundles: list[ComplexBundle] = [r.b for r in rows]
    fm = FactMaker(settings_of(request), provenance_for(session, bundles))
    days = ladder_days(session, bundles)
    days.update(ctx.jl_days)
    from app.api.views import judgment_days

    days.update(judgment_days(session, (b.cx.inclusion_judgment_seq for b in bundles)))
    return [
        complex_row(fm, ctx, r, names, jl_days=days, last_change=_last_change_view(last.get(r.b.cx.id)))
        for r in rows
    ]


@router.get("/snapshots/{sid}/complexes")
def list_complexes(
    session: DB,
    request: Request,
    sid: int,
    scenario: ScenarioQ = "base",
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=1000)] = 50,
    sort: SortQ = "-total",
) -> JSONResponse:
    snap = get_snapshot(session, sid)
    ctx, rows, names, last = list_rows(session, snap, scenario, request, sort)
    start = (page - 1) * size
    items = build_rows(session, request, ctx, rows[start : start + size], names, last)
    return JSONResponse(
        {
            "items": items,
            "total": len(rows),
            "snapshot_id": snap.id,
            "asof_date": snap.asof_date,
            "page": page,
            "size": size,
            "sort": sort,
            "scenario_id": ctx.scenario.id,
        }
    )


_CSV_FACTS = (
    "price_low",
    "price_high",
    "price_mid",
    "resale_end",
    "move_in_ym",
    "gap_pct",
    "total",
    "p10",
    "units_total",
    "down_payment_pct",
    "residency_months",
)


def _csv_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


@router.get("/snapshots/{sid}/complexes.csv")
def export_complexes_csv(
    session: DB,
    request: Request,
    sid: int,
    scenario: ScenarioQ = "base",
    sort: SortQ = "-total",
) -> Response:
    snap = get_snapshot(session, sid)
    ctx, rows, names, last = list_rows(session, snap, scenario, request, sort)
    items = build_rows(session, request, ctx, rows, names, last)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    head = [
        "complex_id",
        "name",
        "living_area",
        "living_area_name",
        "judge_scope",
        "intake_status",
        "intake_reason",
        "intake_checked_at",
    ]
    for col in _CSV_FACTS:
        head += [col, f"{col}_label", f"{col}_checked_at"]
    head += ["rank", "inclusion_class"]
    w.writerow(head)
    for it in items:
        intake = it["intake"] or {}
        row = [
            it["complex_id"],
            it["name"],
            it["living_area"] or "",
            it["living_area_name"] or "",
            it["judge_scope"],
            intake.get("status", ""),
            intake.get("reason") or "",
            (intake.get("checked_at") or "")[:10],
        ]
        for col in _CSV_FACTS:
            f = it[col]
            label = f["label"] if f["label"] != LABEL_UNKNOWN else f"확인 불가({f.get('reason') or ''})"
            row += [_csv_value(f["v"]), label, f.get("checked_at") or ""]
        row += [it["rank"] or "", it["inclusion_class"]]
        w.writerow(row)
    body = ("﻿" + buf.getvalue()).encode("utf-8")
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="complexes_{snap.asof_date}.csv"'},
    )


# ====================================================================== 대시보드 (G1)


def _ym_back(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) - n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def unsold_points(
    session: Session,
    region_id: int,
    fm: FactMaker,
    *,
    scopes: set[str] | None = None,
    months: int = 24,
    per_scope: bool = False,
) -> list[dict[str, Any]]:
    rows = [
        u
        for u in session.scalars(select(Unsold).where(Unsold.region_id == region_id).order_by(Unsold.ym))
        if scopes is None or (u.scope_code or "") in scopes
    ]
    if not rows:
        return []
    fm.prov.load(session, "unsold", (u.id for u in rows))
    if per_scope:
        return [
            {
                "ym": u.ym,
                "scope_code": u.scope_code,
                "scope_name": u.scope_name,
                "total": fm.field("unsold", u.id, "total", u.total, unit="units"),
                "post_completion": fm.field(
                    "unsold", u.id, "post_completion", u.post_completion, unit="units"
                ),
            }
            for u in rows
        ]
    latest = max(u.ym for u in rows)
    by_ym: dict[str, list[Unsold]] = {}
    for u in rows:
        by_ym.setdefault(u.ym, []).append(u)
    out: list[dict[str, Any]] = []
    for i in range(months - 1, -1, -1):
        ym = _ym_back(latest, i)
        group = by_ym.get(ym)
        if not group:
            out.append(
                {
                    "ym": ym,
                    "total": unknown("결측", None, unit="units"),
                    "post_completion": unknown("결측", None, unit="units"),
                }
            )
            continue
        out.append(
            {
                "ym": ym,
                "total": _sum_fact(fm, group, "total"),
                "post_completion": _sum_fact(fm, group, "post_completion"),
            }
        )
    return out


def _sum_fact(fm: FactMaker, rows: Sequence[Unsold], name: str) -> dict[str, Any]:
    facts = [fm.field("unsold", u.id, name, getattr(u, name), unit="units") for u in rows]
    known = [f for f in facts if f["label"] != LABEL_UNKNOWN]
    if not known:
        return facts[0]
    total = sum(f["v"] for f in known)
    parts = "·".join(
        f"{u.scope_name or u.scope_code} {getattr(u, name)}" for u in rows if getattr(u, name) is not None
    )
    reason = f"{parts} 합"[:120] if len(known) > 1 else known[0].get("reason")
    label = weakest(f["label"] for f in known)
    checked = max((f["checked_at"] for f in known if f.get("checked_at")), default=None)
    return fact(total, label, known[0]["prov"], checked, reason=reason, unit="units")


_DAILY = ("applyhome_list", "official_site")
_WEEKLY = ("rtms", "stats")


def freshness(session: Session, region_id: int) -> dict[str, Any]:
    now = now_kst()
    stale = failing = 0
    oldest: RawDocument | None = None
    for kind in (*_DAILY, *_WEEKLY):
        docs = list(
            session.scalars(
                select(RawDocument)
                .where(RawDocument.source_kind == kind, RawDocument.region_id == region_id)
                .order_by(RawDocument.fetched_at.desc())
                .limit(200)
            )
        )
        if not docs:
            continue
        ok = [d for d in docs if d.path and (d.http_status is None or 200 <= d.http_status < 300)]
        if docs[0] not in ok:
            failing += 1
        if ok:
            last = ok[0]
            limit_h = 26 if kind in _DAILY else 24 * 8
            try:
                from datetime import datetime

                age = now - datetime.fromisoformat(last.fetched_at)
                if age.total_seconds() > limit_h * 3600:
                    stale += 1
            except ValueError:
                stale += 1
            if oldest is None or last.fetched_at < oldest.fetched_at:
                oldest = last
    if oldest is None:
        last_fact = unknown("수집 기록 없음", None, unit="text")
    else:
        last_fact = fact(oldest.fetched_at, "확인됨", f"rd_{oldest.id}", oldest.fetched_at, unit="text")
    return {"last_success_at": last_fact, "stale_sources": stale, "failing_sources": failing}


def _kpi_count(ctx: ScoreCtx, value: int, first_cid: int | None) -> dict[str, Any]:
    if ctx.run is None or first_cid is None:
        return unknown("미판정", None, unit="count")
    return fact(value, "추정", f"st_{ctx.run.id}_{first_cid}", ctx.checked, reason="집계", unit="count")


def _move_in_peak(session: Session, region_id: int, fm: FactMaker) -> dict[str, Any]:
    rows = list(session.scalars(select(Supply).where(Supply.region_id == region_id)))
    if not rows:
        u = unknown("입주 물량 없음", None)
        return {"year": {**u, "unit": "year"}, "units": {**u, "unit": "units"}}
    fm.prov.load(session, "supply", (s.id for s in rows))
    by_year: dict[int, list[Supply]] = {}
    for s in rows:
        by_year.setdefault(s.year, []).append(s)
    year, group = max(by_year.items(), key=lambda kv: (sum(s.units for s in kv[1]), -kv[0]))
    facts = [fm.field("supply", s.id, "units", s.units, unit="units") for s in group]
    known = [f for f in facts if f["label"] != LABEL_UNKNOWN]
    if not known:
        return {"year": unknown("출처 누락", None, unit="year"), "units": facts[0]}
    label = weakest(f["label"] for f in known)
    checked = max((f["checked_at"] for f in known if f.get("checked_at")), default=None)
    units = fact(
        sum(f["v"] for f in known), label, known[0]["prov"], checked, reason="추정 집계", unit="units"
    )
    yr = fact(year, label, known[0]["prov"], checked, reason="추정 집계", unit="year")
    return {"year": yr, "units": units}


@router.get("/snapshots/{sid}/dashboard")
def get_dashboard(session: DB, request: Request, sid: int, scenario: ScenarioQ = "base") -> JSONResponse:
    snap = get_snapshot(session, sid)
    sc = resolve_scenario(session, scenario)
    region = session.get(Region, snap.region_id)
    if region is None:
        raise not_found(f"region {snap.region_id}")
    names = area_names(region)
    complexes = list(session.scalars(select(Complex).where(Complex.region_id == snap.region_id)))
    bundles = load_bundles(session, complexes, snap.id)
    ctx = score_ctx(session, snap.id, sc)
    rows = complex_rows_data(bundles, ctx)
    fm = FactMaker(settings_of(request), ProvIndex())
    top_ids = sorted(
        (cid for cid, t in ctx.totals.items() if t.rank is not None and t.rank <= 5 and cid in bundles),
        key=lambda cid: (ctx.totals[cid].rank or 0, cid),
    )
    days = ladder_days(session, [bundles[c] for c in top_ids])
    days.update(ctx.jl_days)
    top5 = [score_row(ctx, bundles[cid], names, jl_days=days) for cid in top_ids]
    judged = [r for r in rows if r.scope == "판정 대상"]
    first = top_ids[0] if top_ids else (min(ctx.totals) if ctx.totals else None)
    unsold_all = unsold_points(session, region.id, fm)
    latest_unsold = next((p for p in reversed(unsold_all) if p["total"]["label"] != LABEL_UNKNOWN), None)
    unsold_kpi = (
        {
            "ym": latest_unsold["ym"],
            "total": latest_unsold["total"],
            "post_completion": latest_unsold["post_completion"],
        }
        if latest_unsold
        else {
            "ym": None,
            "total": unknown("미분양 자료 없음"),
            "post_completion": unknown("미분양 자료 없음"),
        }
    )
    body = {
        "region_id": region.id,
        "snapshot_id": snap.id,
        "asof_date": snap.asof_date,
        "scenario_id": sc.id,
        "scenario_code": sc.code,
        "scenario_name": sc.name,
        "degraded": bool(snap.degraded),
        "score_run_id": ctx.run.id if ctx.run is not None else None,
        "weights": ctx.weights,
        "kpis": {
            "judged_count": _kpi_count(ctx, len(judged), first),
            "intake_open_count": _kpi_count(
                ctx, sum(1 for r in rows if r.intake and r.intake.status == "가능"), first
            ),
            "unsold": unsold_kpi,
            "move_in_peak": _move_in_peak(session, region.id, fm),
            "data_freshness": freshness(session, region.id),
        },
        "top5": top5,
        "changes": changes_for(session, snap, limit=20),
        "unsold_series": unsold_all,
    }
    return JSONResponse(body)
