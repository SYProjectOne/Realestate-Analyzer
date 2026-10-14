"""비교(G4)·민감도(C10)·시나리오(G5) — 판정기 호출 없음."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import snapshot_view as sv
from app.api import views
from app.api.contract import check_body
from app.api.deps import DB, get_snapshot, resolve_scenario, settings_of
from app.api.errors import not_found, validation_error
from app.api.facts import LABEL_UNKNOWN, FactMaker, fact, unknown, weakest
from app.api.jobs import now_iso
from app.api.routers.complexes import gap_view
from app.api.routers.snapshots import SCENARIO_PATTERN
from app.api.views import (
    COMPONENT_ORDER,
    HATCH_LABELS,
    area_names,
    bundle_price,
    current_payment,
    ladder_days,
    ladder_view,
    price_range,
    provenance_for,
    scenario_view,
    score_input,
    score_row,
)
from app.core.contracts_gen import Scenario as ScenarioDTO
from app.core.settings import Settings
from app.models import Complex, Decision, JudgmentLog, Region, Scenario, ScoreRun, Snapshot

router = APIRouter(tags=["analysis"])

ScenarioQ = Annotated[str, Query(pattern=SCENARIO_PATTERN)]


def scenario_dto(sc: Scenario) -> ScenarioDTO:
    return ScenarioDTO.model_validate(scenario_view(sc))


# ====================================================================== 비교 (G4)


def _parse_ids(raw: str) -> list[int]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not all(p.lstrip("-").isdigit() for p in parts):
        raise validation_error("ids 는 정수 목록(쉼표 구분)", ("query", "ids"))
    ids = [int(p) for p in parts]
    if not 2 <= len(ids) <= 6:
        raise validation_error("비교는 2~6개 단지", ("query", "ids"))
    return ids


def decision_set(
    session: Session, run: ScoreRun, sc: Scenario, names: dict[int, str]
) -> dict[str, Any] | None:
    rows = list(
        session.scalars(select(Decision).where(Decision.score_run_id == run.id).order_by(Decision.id))
    )
    if not rows:
        return None
    seq = next((r.judgment_seq for r in rows if r.judgment_seq is not None), None)
    log = session.get(JudgmentLog, seq) if seq is not None else None
    checked = (log.created_at or "")[:10] if log is not None else None
    status = log.status if log is not None else "ok"
    result: dict[str, Any] = {}
    if log is not None:
        from app.api.views import envelope_result

        result = envelope_result(log)
    conf = next((r.confidence for r in rows if r.confidence is not None), None)
    items = []
    for r in rows:
        prob = (
            fact(r.prob, "추정", f"jl_{r.judgment_seq}", checked, reason="판정기 decide", unit="prob")
            if r.prob is not None and r.judgment_seq is not None
            else unknown("미판정", checked, unit="prob")
        )
        reqs = None
        # 가상 후보 '모집공고 대기'(계약 .5)도 요건 판정(판정기 판정만, 사전 계산 없음)을 보인다
        if r.option_key in ("complex", "wait_new"):
            reqs = {}
            for key, pre, judge in (
                ("access", r.req_access_pre, r.req_access_judge),
                ("regulation", r.req_regulation_pre, r.req_regulation_judge),
                ("funds", r.req_funds_pre, r.req_funds_judge),
            ):
                pre_ok = pre if isinstance(pre, dict) and pre.get("status") and pre.get("evidence") else None
                mismatch = pre_ok is not None and (
                    (pre_ok["status"] == "충족" and judge == "contradicted")
                    or (pre_ok["status"] == "미충족" and judge == "supported")
                )
                reqs[key] = {"pre": pre_ok, "judge": judge, "mismatch": mismatch}
        label = (
            names.get(r.complex_id, f"단지 {r.complex_id}")
            if r.complex_id
            else HATCH_LABELS.get(r.option_key, r.option_key)
        )
        items.append(
            {
                "id": r.id,
                "score_run_id": r.score_run_id,
                "scenario_id": r.scenario_id,
                "option_key": r.option_key,
                "complex_id": r.complex_id,
                "label": label,
                "prob": prob,
                "chosen": bool(r.chosen),
                "tie": bool(r.tie),
                "mismatch": bool(r.mismatch),
                "confidence": float(r.confidence) if r.confidence is not None else None,
                "requirements": reqs,
                "judgment_seq": r.judgment_seq,
            }
        )
    return {
        "scenario_id": sc.id,
        "scenario_code": sc.code,
        "score_run_id": run.id,
        "judgment_seq": seq,
        "status": status,
        "confidence": fact(conf, "추정", f"jl_{seq}", checked, reason="판정기 decide confidence", unit="prob")
        if conf is not None and seq is not None
        else None,
        "tie": any(r.tie for r in rows),
        "escaped": status == "escaped",
        "question": result.get("question") if status == "escaped" else None,
        "warnings": [str(w) for w in (rows[0].warnings or [])],
        "cached": False,
        "items": items,
    }


def _won(v: Decimal) -> int:
    return int(v.quantize(Decimal(1), rounding=ROUND_HALF_UP))


@router.get("/snapshots/{sid}/compare")
def get_compare(
    session: DB, request: Request, sid: int, ids: Annotated[str, Query()], scenario: ScenarioQ = "base"
) -> JSONResponse:
    snap = get_snapshot(session, sid)
    id_list = _parse_ids(ids)
    sc = resolve_scenario(session, scenario)
    complexes = {c.id: c for c in session.scalars(select(Complex).where(Complex.id.in_(id_list)))}
    missing = [i for i in id_list if i not in complexes or complexes[i].region_id != snap.region_id]
    if missing:
        raise not_found(f"complex {missing[0]} in snapshot {sid}")
    # D13-1: 발행 리비전 = 저장된 비교 입력(그 리비전 단지 전부), 발행 전 = 요청 단지만 실시간
    parts = sv.compare_parts(
        session, snap, sc, [complexes[i] for i in dict.fromkeys(id_list)], settings=settings_of(request)
    )
    items = parts["items"]
    gone = [i for i in id_list if str(i) not in items]
    if gone:
        raise not_found(f"complex {gone[0]} in snapshot {sid}")
    return JSONResponse(
        {
            "snapshot_id": snap.id,
            "asof_date": snap.asof_date,
            "scenario_id": sc.id,
            "ids": id_list,
            "rows": [items[str(i)]["row"] for i in id_list],
            "components": parts["components"],
            "ladders": {str(i): items[str(i)]["ladders"] for i in id_list},
            "gaps": {str(i): items[str(i)]["gap"] for i in id_list},
            "terms": [items[str(i)]["term"] for i in id_list],
            "decisions": parts["decisions"],
        }
    )


def compare_body(
    session: Session, settings: Settings, snap: Snapshot, sc: Scenario, complexes: Sequence[Complex]
) -> dict[str, Any]:
    """G4 비교 입력(실시간 계산): 단지별 {점수 행, 사다리, 가격 갭, 자금 조건} + 시나리오 가중치·결정 묶음.
    발행 리비전은 지역 단지 전부로 저장한다(D13-1). 응답 조립(요청 순서·중복)은 ``get_compare``."""
    region = session.get(Region, snap.region_id)
    names = area_names(region)
    bundles = views.load_bundles(session, list(complexes), snap.id, scenario_id=sc.id)
    ctx = views.score_ctx(session, snap.id, sc, complex_ids=[c.id for c in complexes])
    fm = FactMaker(settings, provenance_for(session, bundles.values()))
    days = ladder_days(session, bundles.values())
    days.update(ctx.jl_days)
    loan = (sc.params or {}).get("loan_limit_won")
    from app.api.routers.complexes import comparables_by_complex
    from app.api.views import _resale_end, notice_fact

    members = comparables_by_complex(session, snap.id, [c.id for c in complexes])
    comps = views.competition_rows_for(
        session, [c.id for c in complexes]
    )  # 계약 .20 Q4 — 점수 행 경쟁률 요약
    views.load_competition_prov(session, fm, comps)
    items: dict[str, Any] = {}
    for c in complexes:
        i = c.id
        b = bundles[i]
        notice = notice_fact(fm, b.cx)
        price = price_range(fm, b, notice)
        gap = gap_view(session, fm, ctx, b.cx, snap.id, price, members=members.get(i, []))
        pay = current_payment(b.payments)
        down = views.down_payment_pct_fact(fm, b)
        view = bundle_price(b)  # §6-1 현재 구매가(최신 공고 가격 우선, R3 M3)
        low, high = view.low_won, view.high_won
        mid = (Decimal(low) + Decimal(high)) / 2 if low is not None and high is not None else None
        # 계약금 원 금액 = P_mid × D — 목록·상세와 같은 함수(views.down_payment_won_fact → price.share_won)
        down_won = views.down_payment_won_fact(fm, b, price["price_mid"], down)
        if mid is not None and pay is not None and pay.down_payment_pct is not None:
            dp = mid * pay.down_payment_pct / 100
            if loan is None:
                equity = unknown("미입력", None, unit="won")
            else:
                need = max(dp, mid - Decimal(int(loan)))
                equity = fm.derived(
                    _won(need),
                    [price["price_mid"], down],
                    unit="won",
                    reason=f"산술(대출한도 {int(loan) // 10_000:,}만)",
                )
        else:
            src = [price["price_mid"], down]
            equity = (
                fm.derived(None, src, unit="won") if loan is not None else unknown("미입력", None, unit="won")
            )
        winner = fm.field("complex", i, "winner_date", b.cx.winner_date, unit="date")
        months = fm.field("complex", i, "resale_months", b.cx.resale_months, unit="months")
        items[str(i)] = {
            "row": score_row(
                ctx, b, names, jl_days=days, facts=views.score_row_facts(fm, ctx, b, comps.get(i, ()))
            ),  # 계약 .20 Q7·Q4
            "ladders": [ladder_view(lad, days.get(lad.judgment_seq or -1)) for lad in b.ladders],
            "gap": gap,
            "term": {
                "complex_id": i,
                "name": b.cx.name,
                "resale_end": _resale_end(fm, b.cx, winner, months),
                "residency_months": fm.field(
                    "complex", i, "residency_months", b.cx.residency_months, unit="months"
                ),
                "down_payment_pct": down,
                "down_payment_won": down_won,
                "required_equity_won": equity,
                "interim_terms_text": pay.interim_terms_text if pay is not None else None,
            },
        }
    cx_names = {
        c.id: c.name for c in session.scalars(select(Complex).where(Complex.region_id == snap.region_id))
    }
    decisions: dict[str, Any] = {}
    runs = session.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == snap.id).order_by(ScoreRun.id))
    latest_by_scenario: dict[int, ScoreRun] = {r.scenario_id: r for r in runs}
    for scen_id, run in latest_by_scenario.items():
        scen = session.get(Scenario, scen_id)
        if scen is None:
            continue
        ds = decision_set(session, run, scen, cx_names)
        if ds is not None:
            decisions[scen.code or str(scen.id)] = ds
    keys = [k for k in COMPONENT_ORDER if k in ctx.weights]
    return {"items": items, "components": {"weights": ctx.weights, "keys": keys}, "decisions": decisions}


# ====================================================================== 민감도 (C10)


@router.get("/snapshots/{sid}/sensitivity")
def get_sensitivity(session: DB, sid: int, scenario: ScenarioQ = "base") -> JSONResponse:
    snap = get_snapshot(session, sid)
    sc = resolve_scenario(session, scenario)
    return JSONResponse(sv.read(session, snap, "sensitivity", scenario=sc))


def sensitivity_body(session: Session, snap: Snapshot, sc: Scenario) -> dict[str, Any]:
    """C10 민감도 응답(실시간 계산 — 발행 리비전은 저장한다, D13-1)."""
    from app.analysis.sensitivity import compute_sensitivity
    from app.core.contracts_gen import Weights

    ctx = views.score_ctx(session, snap.id, sc)
    scores: dict[int, dict[Any, Decimal | None]] = {}
    for cid, t in ctx.totals.items():
        if t.rank is None and t.total is not None:
            continue  # 시나리오 정책으로 후보에서 빠진 단지(D)
        scores[cid] = {k: c.score_0_10 for k, c in (ctx.components.get(cid) or {}).items()}
    weights = Weights.model_validate(ctx.weights)
    sens = compute_sensitivity(
        scores, weights, snapshot_id=snap.id, scenario_id=sc.id, score_run_id=ctx.run.id if ctx.run else None
    )
    body: dict[str, Any] = sens.model_dump(mode="json")
    body["base_weights"] = {k: v for k, v in body["base_weights"].items() if v is not None}
    for cell in body.get("cells") or []:
        cell["weights"] = {k: v for k, v in cell["weights"].items() if v is not None}
    ids = set(body.get("base_top5") or [])
    for cell in body.get("cells") or []:
        ids |= {r["complex_id"] for r in cell.get("ranks") or []}
    names = {c.id: c.name for c in session.scalars(select(Complex).where(Complex.id.in_(sorted(ids))))}
    for cell in body.get("cells") or []:
        for r in cell.get("ranks") or []:
            r["name"] = names.get(r["complex_id"])
    body["complex_names"] = {str(k): v for k, v in sorted(names.items())}
    body["score_run_id"] = ctx.run.id if ctx.run is not None else None
    return body


# ====================================================================== 시나리오 (G5)


@router.get("/scenarios")
def list_scenarios(session: DB) -> JSONResponse:
    rows = session.scalars(select(Scenario).order_by(Scenario.is_builtin.desc(), Scenario.id))
    return JSONResponse([scenario_view(s) for s in rows])


@router.post("/scenarios", status_code=201)
def create_scenario(session: DB, body: Annotated[Any, Body()] = None) -> JSONResponse:
    check_body("createScenario", body)
    weights = {k: v for k, v in body["weights"].items() if v is not None}
    total = sum((Decimal(str(v)) for v in weights.values()), Decimal(0))
    if abs(total - 1) > Decimal("1e-9"):
        raise validation_error(f"가중치 합이 1이 아니다({total})", ("body", "weights"))
    if ("liquidity" in weights) == ("move_in" in weights):
        raise validation_error("liquidity 와 move_in 중 정확히 하나", ("body", "weights"))
    base = resolve_scenario(session, "base")
    sc = Scenario(
        code=None,
        name=body["name"],
        is_builtin=False,
        params=body["params"],
        weights=weights,
        requirements=body.get("requirements") or dict(base.requirements or {}),
        policy=body.get("policy") or dict(base.policy or {}),
        created_at=now_iso(),
    )
    session.add(sc)
    session.flush()
    session.commit()
    return JSONResponse(scenario_view(sc), status_code=201)


def cache_estimate(session: Session, snap: Snapshot, sc: Scenario) -> tuple[int, int, dict[str, int]]:
    """'재판정 실행' 시 판정기 호출 예상(계약 2026-10-09.3 WP5-5). 판정기를 부르지 않는다.

    WP7 빌더(``scheduler.payloads.scenario_payloads``)가 만든 payload 마다 같은 input_hash 의 최종
    judgment_log 행이 있으면 히트.
    """
    from app.scheduler.payloads import cache_status, scenario_payloads

    plan = scenario_payloads(session, snap.id, scenario_dto(sc))
    st = cache_status(session, plan)
    return st.hits, st.misses, st.calls_by_tool


@router.get("/scenarios/{id}/preview")
def preview_scenario(
    session: DB, request: Request, id: int, snapshot: Annotated[int, Query()]
) -> JSONResponse:
    from app.analysis.scenarios import precalc_rows

    sc = session.get(Scenario, id)
    if sc is None:
        raise not_found(f"scenario {id}")
    snap = get_snapshot(session, snapshot)
    # D29-2: 병합된 중복 단지 행은 뺀다(새 리비전 후보가 아니다)
    complexes = list(
        session.scalars(
            select(Complex).where(Complex.region_id == snap.region_id, Complex.merged_into_id.is_(None))
        )
    )
    bundles = views.load_bundles(session, complexes, snap.id, scenario_id=sc.id)
    fm = FactMaker(settings_of(request), provenance_for(session, bundles.values()))
    inputs = []
    for b in bundles.values():
        labels = {
            "resale": _label(fm.field("complex", b.cx.id, "resale_months", b.cx.resale_months)),
            "residency": _label(fm.field("complex", b.cx.id, "residency_months", b.cx.residency_months)),
            "move_in": _label(fm.field("complex", b.cx.id, "move_in_ym", b.cx.move_in_ym)),
            "winner": _label(fm.field("complex", b.cx.id, "winner_date", b.cx.winner_date)),  # 계약 .7
        }
        pay = current_payment(b.payments)
        if pay is not None:
            labels["down_payment"] = _label(
                fm.field("payment_terms", pay.id, "down_payment_pct", pay.down_payment_pct)
            )
        # 가격 라벨 = 구매가 범위(low·high) 구성 필드 중 가장 약한 것 — 파이프라인과 같다(minor 6)
        pr = price_range(fm, b)
        if pr["price_low"]["v"] is not None and pr["price_high"]["v"] is not None:
            labels["price"] = weakest([pr["price_low"]["label"], pr["price_high"]["label"]])
        cx_in = score_input(b, labels, asof_date=snap.asof_date)
        if cx_in.judge_scope in ("제외", "미해결"):
            continue
        inputs.append(cx_in)
    dto = scenario_dto(sc)
    rows = precalc_rows(inputs, dto, asof_date=snap.asof_date)
    hits, misses, by_tool = cache_estimate(session, snap, sc)
    return JSONResponse(
        {
            "scenario_id": sc.id,
            "snapshot_id": snap.id,
            "weights": scenario_view(sc)["weights"],
            "requirements": dict(sc.requirements or {}),
            "requirements_pre": [r.model_dump(mode="json") for r in rows],
            "cache_hits": hits,
            "cache_misses": misses,
            "calls_by_tool": by_tool,
        }
    )


def _label(f: dict[str, Any]) -> str | None:
    lb = f.get("label")
    return (
        str(lb)
        if lb and lb != LABEL_UNKNOWN
        else (
            "확인 불가"
            if lb == LABEL_UNKNOWN and f.get("v") is None and f.get("reason") not in (None, "값 없음")
            else None
        )
    )
