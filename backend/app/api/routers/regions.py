"""지역 (DECISIONS D2-3): GET/POST /regions, /regions/resolve, /regions/{id}, PUT living-areas, snapshots."""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.contract import check_body
from app.api.deps import DB, default_snapshot, get_region
from app.api.errors import ApiError
from app.api.jobs import enqueue, now_iso
from app.api.views import region_view, snapshot_view
from app.models import AdminDong, AdminLegalMap, ChangeEvent, Complex, LegalDong, Region, Snapshot

router = APIRouter(tags=["regions"])


@router.get("/regions")
def list_regions(session: DB) -> JSONResponse:
    out = [
        region_view(session, r, latest=default_snapshot(session, r.id))
        for r in session.scalars(select(Region).order_by(Region.id))
    ]
    return JSONResponse(out)


_REFERENCE_CACHE: dict[str, tuple[tuple[Any, ...], Any]] = {}


def _reference(session: Session) -> Any:
    """참조 데이터(법정동·행정동·매핑) — 전국 5만 행을 요청마다 읽지 않도록 프로세스에 캐시한다.
    키 = DB + 행 수·최신 기준일(reference.refresh 가 바꾸면 다시 읽는다)."""
    from app.normalize.region_resolve import load_reference_db

    fingerprint = (
        session.scalar(select(func.count()).select_from(LegalDong)),
        session.scalar(select(func.max(LegalDong.source_date))),
        session.scalar(select(func.count()).select_from(AdminDong)),
        session.scalar(select(func.max(AdminDong.source_date))),
        session.scalar(select(func.count()).select_from(AdminLegalMap)),
    )
    url = str(session.get_bind().engine.url)
    hit = _REFERENCE_CACHE.get(url)
    if hit is not None and hit[0] == fingerprint:
        return hit[1]
    ref = load_reference_db(session)
    _REFERENCE_CACHE[url] = (fingerprint, ref)
    return ref


@router.get("/regions/resolve")
def resolve_region(session: DB, q: Annotated[str, Query(min_length=1, max_length=50)]) -> JSONResponse:
    from app.normalize.region_resolve import resolve_region as resolve_names

    if not q.strip():
        return JSONResponse([])
    cands = resolve_names(q, _reference(session), limit=50)
    return JSONResponse([c.model_dump(mode="json") for c in cands])


def _dong_rows(session: Session, prefix: str) -> list[LegalDong]:
    return list(
        session.scalars(
            select(LegalDong).where(
                LegalDong.code.like(f"{prefix}%"),
                LegalDong.active.is_(True),
                LegalDong.eupmyeondong_name.is_not(None),
            )
        )
    )


def _expand(session: Session, sel: dict[str, Any]) -> list[str]:
    """선택 1개 → 법정동(읍면동·리) 코드. 폐지 코드는 넣지 않는다(D2-3, region_resolve 와 같은 규칙)."""
    kind, code = sel["kind"], sel["code"]
    if kind == "sido" and len(code) == 2:
        return sorted(r.code for r in _dong_rows(session, code))
    if kind == "sigungu" and len(code) == 5:
        return sorted(r.code for r in _dong_rows(session, code))
    if kind == "legal_dong" and len(code) == 10:
        row = session.get(LegalDong, code)
        if row is None or not row.active or not row.eupmyeondong_name:
            return []
        if row.ri_name:
            return [row.code]
        return sorted(r.code for r in _dong_rows(session, code[:8]))
    if kind == "admin_dong" and len(code) == 10:
        legal = [
            m.legal_code
            for m in session.scalars(select(AdminLegalMap).where(AdminLegalMap.admin_code == code))
        ]
        active = {
            r.code
            for r in session.scalars(
                select(LegalDong).where(LegalDong.code.in_(legal), LegalDong.active.is_(True))
            )
        }
        return sorted(c for c in legal if c in active)
    return []


@router.post("/regions", status_code=201)
def create_region(session: DB, body: Annotated[Any, Body()] = None) -> JSONResponse:
    from app.normalize.living_area import default_living_areas
    from app.normalize.region_resolve import LegalRow

    check_body("createRegion", body)
    codes: list[str] = []
    errors: list[dict[str, Any]] = []
    for i, sel in enumerate(body["selections"]):
        got = _expand(session, sel)
        if not got:
            errors.append(
                {
                    "loc": ["body", "selections", i, "code"],
                    "msg": f"알 수 없는 {sel['kind']} 코드 {sel['code']}",
                }
            )
        codes.extend(c for c in got if c not in codes)
    if errors:
        raise ApiError(
            422, "validation_error", "선택한 후보를 참조 데이터에서 찾을 수 없다", field_errors=errors
        )
    legal = [
        LegalRow(
            code=r.code,
            sido_name=r.sido_name,
            sigungu_name=r.sigungu_name,
            eupmyeondong_name=r.eupmyeondong_name,
            ri_name=r.ri_name,
            full_name=r.full_name,
            sigungu_code=r.sigungu_code,
            active=bool(r.active),
        )
        for r in session.scalars(select(LegalDong).where(LegalDong.code.in_(codes)))
    ]
    region = Region(
        name=body["name"],
        query_text=body["query_text"],
        selections=[
            {"kind": s["kind"], "code": s["code"], "full_name": s["full_name"]} for s in body["selections"]
        ],
        sido_codes=sorted({c[:2] for c in codes}),
        sigungu_codes=sorted({c[:5] for c in codes}),
        legal_dong_codes=codes,
        living_areas=default_living_areas(codes, legal),
        age_premium_coef={"c_per_year": 0.015, "cap_years": 8, "label": "추정"},
        applyhome_query={},
        status="bootstrapping",
        created_at=now_iso(),
    )
    session.add(region)
    session.flush()
    job = enqueue(session, "region.bootstrap", {"region_id": region.id}, kind="manual")
    session.commit()
    return JSONResponse({"region": region_view(session, region), "job_id": job.id}, status_code=201)


@router.get("/regions/{id}")
def get_region_detail(session: DB, id: int) -> JSONResponse:
    region = get_region(session, id)
    return JSONResponse(region_view(session, region, latest=default_snapshot(session, region.id)))


def _sel_key(sel: dict[str, Any]) -> tuple[str, str]:
    return (str(sel["kind"]), str(sel["code"]))


def _expand_all(session: Session, selections: list[dict[str, Any]]) -> list[str]:
    """선택 목록 → 법정동 코드(중복 없이 순서 유지). 모르는 선택은 422."""
    codes: list[str] = []
    errors: list[dict[str, Any]] = []
    for i, sel in enumerate(selections):
        got = _expand(session, sel)
        if not got:
            errors.append(
                {
                    "loc": ["body", "selections", i, "code"],
                    "msg": f"알 수 없는 {sel['kind']} 코드 {sel['code']}",
                }
            )
        codes.extend(c for c in got if c not in codes)
    if errors:
        raise ApiError(
            422, "validation_error", "선택한 후보를 참조 데이터에서 찾을 수 없다", field_errors=errors
        )
    return codes


def _expanded_areas(session: Session, old: list[dict[str, Any]], codes: list[str]) -> list[dict[str, Any]]:
    """생활권 갱신(D11-7): 남은 법정동은 원래 생활권 그대로, 빠진 법정동은 제거(빈 생활권은 삭제), 새 법정동은 새 시군구마다 새
    생활권(기본값 규칙 — ``default_living_areas``, id 는 기존과 겹치지 않게 이어 붙인다)."""
    from app.normalize.living_area import default_living_areas
    from app.normalize.region_resolve import LegalRow

    keep = set(codes)
    out: list[dict[str, Any]] = []
    assigned: set[str] = set()
    for a in old:
        dongs = [c for c in a.get("legal_dong_codes") or [] if c in keep]
        assigned.update(dongs)
        if dongs:
            out.append({**a, "legal_dong_codes": dongs})
    fresh = [c for c in codes if c not in assigned]
    if fresh:
        legal = [
            LegalRow(
                code=r.code, sido_name=r.sido_name, sigungu_name=r.sigungu_name, eupmyeondong_name=r.eupmyeondong_name,
                ri_name=r.ri_name, full_name=r.full_name, sigungu_code=r.sigungu_code, active=bool(r.active),
            )
            for r in session.scalars(select(LegalDong).where(LegalDong.code.in_(fresh)))
        ]  # fmt: skip
        used = {str(a.get("id")) for a in out}
        n = 1 + max((int(i[3:]) for i in used if i.startswith("la_") and i[3:].isdigit()), default=0)
        for a in default_living_areas(fresh, legal):
            while f"la_{n}" in used:
                n += 1
            a["id"] = f"la_{n}"
            used.add(a["id"])
            out.append(a)
    return out


@router.patch("/regions/{id}")
def update_region(session: DB, id: int, body: Annotated[Any, Body()] = None) -> JSONResponse:
    """지역 선택 확장·축소(D11-7 = RA '지역 추가', 계약 .8): 코드·생활권을 다시 계산하고 change_event(critical) +
    region.expand 잡(추가 선택 수집 → 새 리비전에서 후보 전체 판정·rerank → publish)을 등록한다."""
    from app.api.errors import conflict
    from app.api.routers.snapshots import change_view

    region = get_region(session, id)
    check_body("updateRegion", body)
    new_sel = [
        {"kind": s["kind"], "code": s["code"], "full_name": s["full_name"]} for s in body["selections"]
    ]
    old_sel = list(region.selections or [])
    old_keys = {_sel_key(s) for s in old_sel}
    new_keys = {_sel_key(s) for s in new_sel}
    added = [s for s in new_sel if _sel_key(s) not in old_keys]
    removed = [s for s in old_sel if _sel_key(s) not in new_keys]
    name = body.get("name")
    if not added and not removed and (not name or name == region.name):
        raise conflict("선택이 바뀌지 않았다")
    codes = _expand_all(session, new_sel)
    old_count = len(old_sel)
    region.selections = new_sel
    region.legal_dong_codes = codes
    region.sigungu_codes = sorted({c[:5] for c in codes})
    region.sido_codes = sorted({c[:2] for c in codes})
    region.living_areas = _expanded_areas(session, list(region.living_areas or []), codes)
    if name:
        region.name = str(name)
    snap = default_snapshot(session, region.id)
    names = ", ".join(s["full_name"] for s in added) or "-"
    gone = ", ".join(s["full_name"] for s in removed) or "-"
    ce = ChangeEvent(
        snapshot_id=snap.id if snap else None,
        entity="region",
        entity_id=region.id,
        field="selections",
        old_text=f"선택 {old_count}개",
        new_text=f"선택 {len(new_sel)}개(추가: {names}; 제거: {gone})"[:500],
        detected_at=now_iso(),
        severity="critical",
        triggers_rejudge=True,
        complex_id=None,
    )
    session.add(ce)
    session.flush()
    job = enqueue(
        session,
        "region.expand",
        {"region_id": region.id, "added": added, "removed": removed, "change_event_id": ce.id},
        kind="manual",
    )
    session.commit()
    return JSONResponse(
        {
            "region": region_view(session, region, latest=default_snapshot(session, region.id)),
            "change_event": change_view(ce, {}),
            "job_id": job.id,
            "added": added,
            "removed": removed,
        }
    )


def _issue_errors(issues: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for issue in issues:
        loc: list[str | int] = ["body", "living_areas"]
        if issue.code:
            loc.append(issue.code)
        out.append({"loc": loc, "msg": issue.detail})
    return out


@router.put("/regions/{id}/living-areas")
def update_living_areas(session: DB, id: int, body: Annotated[Any, Body()] = None) -> JSONResponse:
    from app.normalize.living_area import LivingAreaError, apply_living_area_edit, living_area_of

    region = get_region(session, id)
    check_body("updateLivingAreas", body)
    old_areas = list(region.living_areas or [])
    try:
        new_areas = apply_living_area_edit(region.legal_dong_codes or [], old_areas, body["living_areas"])
    except LivingAreaError as exc:
        raise ApiError(
            422,
            "validation_error",
            "모든 법정동은 정확히 한 생활권에 속해야 한다: " + str(exc)[:400],
            field_errors=_issue_errors(exc.issues),
        ) from exc
    region.living_areas = new_areas
    for cx in session.scalars(select(Complex).where(Complex.region_id == region.id)):
        if cx.legal_dong_code:
            cx.living_area = living_area_of(cx.legal_dong_code, new_areas) or cx.living_area
    snap = (
        default_snapshot(session, region.id)
        or session.scalars(
            select(Snapshot)
            .where(Snapshot.region_id == region.id)
            .order_by(Snapshot.asof_date.desc())
            .limit(1)
        ).first()
    )

    def summary(areas: list[dict[str, Any]]) -> str:
        return json.dumps(
            [{"id": a["id"], "name": a["name"], "n": len(a.get("legal_dong_codes") or [])} for a in areas],
            ensure_ascii=False,
        )

    ce = ChangeEvent(
        snapshot_id=snap.id if snap else None,
        entity="region",
        entity_id=region.id,
        field="living_areas",
        old_text=summary(old_areas),
        new_text=summary(new_areas),
        detected_at=now_iso(),
        severity="critical",
        triggers_rejudge=True,
        complex_id=None,
    )
    session.add(ce)
    session.flush()
    if snap is not None:
        job = enqueue(
            session,
            "rejudge",
            {
                "snapshot_id": snap.id,
                "scenario_id": None,
                "complex_ids": None,
                "reason": f"생활권 편집: {region.name}"[:200],
                "change_event_ids": [ce.id],
            },
        )
    else:
        job = enqueue(session, "region.bootstrap", {"region_id": region.id})
    session.commit()
    from app.api.routers.snapshots import change_view

    return JSONResponse(
        {
            "region": region_view(session, region, latest=default_snapshot(session, region.id)),
            "change_event": change_view(ce, {}),
            "job_id": job.id,
        }
    )


@router.get("/regions/{id}/snapshots", tags=["snapshots"])
def list_snapshots(session: DB, id: int) -> JSONResponse:
    region = get_region(session, id)
    snaps = session.scalars(
        select(Snapshot)
        .where(Snapshot.region_id == region.id)
        .order_by(Snapshot.asof_date.desc(), Snapshot.id.desc())
    )
    return JSONResponse([snapshot_view(session, s) for s in snaps])
