"""지역 시장 (G6): 벤치마크(C3)·입주 물량(C4)·미분양(C5)·호재(C9)·규제 카드·생활권 시세."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import DB, get_snapshot, settings_of
from app.api.errors import not_found
from app.api.facts import LABEL_UNKNOWN, FactMaker, ProvIndex, fact, weakest
from app.api.routers.complexes import catalyst_view
from app.api.routers.snapshots import unsold_points
from app.api.views import area_names, judge_scope, judgment_days, load_bundles
from app.models import Benchmark, Catalyst, CatalystLink, Complex, Region, RtmsTrade, Supply

router = APIRouter(tags=["market"])


def _pct(a: int | None, b: int | None) -> float | None:
    if not a or b is None:
        return None
    return float(((Decimal(b) - Decimal(a)) / Decimal(a) * 100).quantize(Decimal("0.1"), ROUND_HALF_UP))


def _months_back(d: date, n: int) -> date:
    t = d.year * 12 + (d.month - 1) - n
    return date(t // 12, t % 12 + 1, min(d.day, 28))


@router.get("/snapshots/{sid}/market")
def get_market(session: DB, request: Request, sid: int, living_area: str | None = None) -> JSONResponse:
    snap = get_snapshot(session, sid)
    region = session.get(Region, snap.region_id)
    if region is None:
        raise not_found(f"region {snap.region_id}")
    names = area_names(region)
    want = {living_area} if living_area else None
    fm = FactMaker(settings_of(request), ProvIndex())
    checked = snap.asof_date
    asof = date.fromisoformat(snap.asof_date)

    benches = [
        b
        for b in session.scalars(
            select(Benchmark).where(Benchmark.region_id == region.id).order_by(Benchmark.id)
        )
        if want is None or b.living_area in want
    ]
    fm.prov.load(session, "benchmark", (b.id for b in benches))
    bench_views = []
    for b in benches:
        sale = fm.field("benchmark", b.id, "sale_price_84_won", b.sale_price_84_won, unit="won")
        med = fm.field("benchmark", b.id, "trade_median_won", b.trade_median_won, unit="won")
        gain = _pct(b.sale_price_84_won, b.trade_median_won)
        gain_f = fm.derived(gain, [sale, med], unit="pct") if gain is not None else None
        ann = None
        if gain is not None and b.sale_year and asof.year > b.sale_year:
            years = asof.year - b.sale_year
            r = (Decimal(1) + Decimal(str(gain)) / 100) ** (Decimal(1) / Decimal(years)) - 1
            ann = fm.derived(
                float((r * 100).quantize(Decimal("0.1"), ROUND_HALF_UP)),
                [sale, med],
                unit="pct",
                reason=f"산술({b.sale_year}~{asof.year} 연율)",
            )
        bench_views.append(
            {
                "id": b.id,
                "living_area": b.living_area,
                "name": b.name,
                "completed_year": b.completed_year,
                "sale_year": b.sale_year,
                "sale_period": b.sale_period,
                "sale_price_84_won": sale,
                "trade_low_won": fm.field("benchmark", b.id, "trade_low_won", b.trade_low_won, unit="won"),
                "trade_median_won": med,
                "trade_high_won": fm.field("benchmark", b.id, "trade_high_won", b.trade_high_won, unit="won"),
                "trade_window": b.trade_window,
                "n_trades": b.n_trades,
                "peak_won": fm.field("benchmark", b.id, "peak_won", b.peak_won, unit="won"),
                "peak_ym": fm.field("benchmark", b.id, "peak_ym", b.peak_ym, unit="ym"),
                "is_presale": bool(b.is_presale),
                "gain_low_pct": None,
                "gain_high_pct": gain_f,
                "annualized_pct": ann,
                "note": b.note,
            }
        )
    flags = []
    for la_id in sorted({b.living_area for b in benches if b.living_area} | (want or set(names))):
        own = [b for b in benches if b.living_area == la_id and not b.is_presale]
        flags.append(
            {
                "living_area": la_id,
                "sample_n": len(own),
                "no_recent_sale_case": not any((b.sale_year or 0) >= asof.year - 3 for b in own),
            }
        )

    supply_rows = [
        s
        for s in session.scalars(
            select(Supply).where(Supply.region_id == region.id).order_by(Supply.year, Supply.id)
        )
        if want is None or s.living_area in want
    ]
    fm.prov.load(session, "supply", (s.id for s in supply_rows))
    grouped: dict[tuple[str | None, int], list[Supply]] = defaultdict(list)
    for s in supply_rows:
        grouped[(s.living_area, s.year)].append(s)
    cx_names = {c.id: c.name for c in session.scalars(select(Complex).where(Complex.region_id == region.id))}
    supply_views = []
    for (area_id, year), group in sorted(grouped.items(), key=lambda kv: (kv[0][1], kv[0][0] or "")):
        facts = [fm.field("supply", s.id, "units", s.units, unit="units") for s in group]
        known = [f for f in facts if f["label"] != LABEL_UNKNOWN]
        if known:
            label = weakest(f["label"] for f in known)
            units = fact(
                sum(f["v"] for f in known),
                label,
                known[0]["prov"],
                max((f["checked_at"] or "" for f in known), default=None) or None,
                reason="추정 집계" if label == "추정" else None,
                unit="units",
            )
        else:
            units = facts[0]
        supply_views.append(
            {
                "living_area": area_id,
                "year": year,
                "units": units,
                "complexes": [cx_names[s.complex_id] for s in group if s.complex_id in cx_names] or None,
            }
        )

    complexes = [
        c
        for c in session.scalars(select(Complex).where(Complex.region_id == region.id).order_by(Complex.id))
        if want is None or c.living_area in want
    ]
    bundles = load_bundles(session, complexes, snap.id)
    fm.prov.load(session, "complex", (c.id for c in complexes))
    markers = []
    for c in complexes:
        if c.move_in_ym is None or judge_scope(bundles[c.id]) != "판정 대상":
            continue
        markers.append(
            {
                "complex_id": c.id,
                "name": c.name,
                "living_area": c.living_area,
                "move_in_ym": fm.field("complex", c.id, "move_in_ym", c.move_in_ym, unit="ym"),
            }
        )

    scopes: set[str] | None = None
    if want is not None:
        scopes = set()
        for a in region.living_areas or []:
            if a["id"] in want:
                scopes |= {str(code)[:5] for code in a.get("legal_dong_codes") or []}
    unsold = unsold_points(session, region.id, fm, scopes=scopes, per_scope=True)

    cats = list(
        session.scalars(select(Catalyst).where(Catalyst.region_id == region.id).order_by(Catalyst.id))
    )
    links: dict[int, list[int]] = defaultdict(list)
    for lk in session.scalars(
        select(CatalystLink).where(CatalystLink.catalyst_id.in_([c.id for c in cats] or [-1]))
    ):
        links[lk.catalyst_id].append(lk.complex_id)
    days = judgment_days(session, (c.judgment_seq for c in cats))
    cat_views = [
        catalyst_view(c, days.get(c.judgment_seq or -1) or checked, linked_ids=sorted(links.get(c.id, [])))
        for c in cats
        if want is None
        or not links.get(c.id)
        or any(cx_id in {x.id for x in complexes} for cx_id in links[c.id])
    ]

    reg_items = []
    for la_id, la_name in names.items():
        if want is not None and la_id not in want:
            continue
        for key, title, col in (
            ("regulated_area", "규제지역", "regulated"),
            ("price_cap", "분양가상한제", "price_cap"),
        ):
            src = next((c for c in complexes if c.living_area == la_id and getattr(c, col)), None)
            if src is None:
                continue
            reg_items.append(
                {
                    "key": key,
                    "title": title,
                    "scope": la_name,
                    "value": fm.field("complex", src.id, col, getattr(src, col), unit="text"),
                    "note": f"근거 단지: {src.name}",
                }
            )

    trades = [
        t
        for t in session.scalars(select(RtmsTrade).where(RtmsTrade.region_id == region.id))
        if not t.cancelled
        and not t.is_presale
        and Decimal(80) <= (t.area_m2 or 0) <= Decimal(85)
        and _months_back(asof, 6).isoformat() <= t.deal_date <= asof.isoformat()
    ]
    fm.prov.load(session, "rtms_trade", (t.id for t in trades))
    by_area: dict[str, list[RtmsTrade]] = defaultdict(list)
    for t in trades:
        la = _trade_area(t, region)
        if la and (want is None or la in want):
            by_area[la].append(t)
    prices = []
    for la_id, group_ts in sorted(by_area.items()):
        ts = sorted(group_ts, key=lambda t: t.price_won)
        tfacts = {t.id: fm.field("rtms_trade", t.id, "price_won", t.price_won, unit="won") for t in ts}
        if any(f["label"] == LABEL_UNKNOWN for f in tfacts.values()):
            continue
        med_t = ts[len(ts) // 2]
        label = weakest(f["label"] for f in tfacts.values())
        mid_val = int(median(t.price_won for t in ts))
        prices.append(
            {
                "living_area": la_id,
                "name": names.get(la_id, la_id),
                "median_won": fact(
                    mid_val, label, tfacts[med_t.id]["prov"], checked, reason=f"표본 {len(ts)}", unit="won"
                ),
                "low_won": fact(ts[0].price_won, label, tfacts[ts[0].id]["prov"], checked, unit="won"),
                "high_won": fact(ts[-1].price_won, label, tfacts[ts[-1].id]["prov"], checked, unit="won"),
                "n_trades": len(ts),
                "trade_window": f"{_months_back(asof, 6).isoformat()[:7]}~{snap.asof_date[:7]}",
                "basis": "전용 80~85㎡, 기준일 전 6개월, 분양권·해제 제외",
            }
        )

    return JSONResponse(
        {
            "snapshot_id": snap.id,
            "asof_date": snap.asof_date,
            "region_id": region.id,
            "living_areas": [{"id": k, "name": v} for k, v in names.items() if want is None or k in want],
            "benchmarks": bench_views,
            "benchmark_flags": flags,
            "supply": supply_views,
            "move_in_markers": markers,
            "unsold": unsold,
            "catalysts": cat_views,
            "regulation": {"items": reg_items},
            "living_area_prices": prices,
        }
    )


def _trade_area(t: RtmsTrade, region: Region) -> str | None:
    if t.legal_dong_code:
        for a in region.living_areas or []:
            if t.legal_dong_code in (a.get("legal_dong_codes") or []):
                return str(a["id"])
    return None
