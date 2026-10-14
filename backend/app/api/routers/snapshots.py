"""스냅샷 화면: 대시보드(G1), 단지 표(G2)·CSV, 변경 피드(G1·G8)."""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Final

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import snapshot_view as sv
from app.analysis._ranking import display_order_key, tie_order_key
from app.api import change_text, views
from app.api.benchmarks import benchmark_absence, benchmarks_for
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
    light_rows,
    provenance_for,
    scope_result,
    score_row,
)
from app.core.settings import Settings
from app.core.time import kst_day, now_kst
from app.models import ChangeEvent, Complex, RawDocument, Region, Scenario, Snapshot, Supply, Unsold

router = APIRouter(tags=["snapshots"])

SCENARIO_PATTERN = r"^(base|A|B|C|D|[0-9]+)$"
SORT_PATTERN = r"^-?(total|rank|name|price_mid|price_low|move_in_ym|resale_end|gap_pct|p10|living_area|last_change|intake)$"
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
        # 계약 .20(D28-5 Q5): 사람이 읽는 필드 이름·한 줄 요약·값 모양(해시는 화면에서 접는다) — 원값은 old/new 그대로
        "field_label": change_text.field_label(ev.entity, ev.field),
        "summary": change_text.change_summary(ev.entity, ev.field, ev.old_text, ev.new_text),
        "value_kind": change_text.value_kind(ev.old_text, ev.new_text, field=ev.field),
    }


def _names(session: Session, ids: Sequence[int | None]) -> dict[int, str]:
    want = sorted({i for i in ids if i is not None})
    if not want:
        return {}
    return {
        cid: name
        for cid, name in session.execute(select(Complex.id, Complex.name).where(Complex.id.in_(want)))
    }


def changes_ledger(session: Session, snap: Snapshot) -> dict[str, Any]:
    """변경 피드 원장: 그 지역 관련 change_event 전부(지역 스냅샷에 붙은 것 · 지역 단지 · 지역 단위), 최신 순.

    발행 리비전은 이 원장을 저장한다(D13-1 — ``snapshot_view`` kind=changes). 질의(기본·since·비교·심각도)는
    ``query_changes`` 가 원장에 적용한다 — 실시간·저장본이 같은 함수다. ``_asof`` = 이벤트가 붙은 지역 스냅샷의 기준일."""
    region_snaps = {
        s.id: s for s in session.scalars(select(Snapshot).where(Snapshot.region_id == snap.region_id))
    }
    cids = list(session.scalars(select(Complex.id).where(Complex.region_id == snap.region_id)))
    stmt = (
        select(ChangeEvent)
        .where(
            (ChangeEvent.snapshot_id.in_(list(region_snaps) or [-1]))
            | (ChangeEvent.complex_id.in_(cids or [-1]))
            | ((ChangeEvent.entity == "region") & (ChangeEvent.entity_id == snap.region_id))
        )
        .order_by(ChangeEvent.detected_at.desc(), ChangeEvent.id.desc())
    )
    events = list(session.scalars(stmt))
    names = _names(session, [e.complex_id for e in events])
    out = []
    for e in events:
        row = change_view(e, names)
        sn = region_snaps.get(e.snapshot_id) if e.snapshot_id is not None else None
        row["_asof"] = sn.asof_date if sn is not None else None
        out.append(row)
    return {"events": out}


def query_changes(
    ledger: Mapping[str, Any],
    snap: Snapshot,
    *,
    since: str | None = None,
    compare: Snapshot | None = None,
    severity: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """원장 → 응답 행. 기본 = 이 스냅샷에 붙은 것, ``compare`` = 비교 기준일 초과 ~ 이 기준일 이하 지역 스냅샷에 붙은 것,
    ``since`` = 그 시각 이후 지역 관련 전부. 최신 순(detected_at, id 내림차순)."""
    evs: list[dict[str, Any]] = list(ledger.get("events") or [])
    if compare is not None:
        evs = [
            e for e in evs if e.get("_asof") is not None and compare.asof_date < e["_asof"] <= snap.asof_date
        ]
    elif since is not None:
        evs = [e for e in evs if (e.get("detected_at") or "") >= since]
    else:
        evs = [e for e in evs if e.get("snapshot_id") == snap.id]
    if severity:
        evs = [e for e in evs if e.get("severity") == severity]
    if limit:
        evs = evs[:limit]
    return [{k: v for k, v in e.items() if not k.startswith("_")} for e in evs]


def changes_for(
    session: Session,
    snap: Snapshot,
    *,
    since: str | None = None,
    compare: Snapshot | None = None,
    severity: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """그 스냅샷의 변경 피드 — 발행 리비전은 저장 원장, 발행 전은 지금 원장(``sv.read``)."""
    ledger = sv.read(session, snap, "changes")
    return query_changes(ledger, snap, since=since, compare=compare, severity=severity, limit=limit)


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


def _dec_s(v: Decimal | None) -> str | None:
    return None if v is None else str(v)


def _dec(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def row_keys(rd: RowData, last: Mapping[int, ChangeEvent]) -> dict[str, Any]:
    """목록 행의 필터·정렬 키(Fact 이전 맨값). 저장본(D13-1)은 이 키와 응답 행을 함께 저장하고, 실시간·저장본 모두
    ``match_keys``·``sort_keyed`` 로 질의한다(같은 규칙). 숫자(Decimal)는 문자열로 — 정렬·비교 때 Decimal 로 되돌린다."""
    cx = rd.b.cx
    ev = last.get(cx.id)
    return {
        "cid": cx.id,
        "name": cx.name,
        "living_area": cx.living_area,
        "intake_status": rd.intake.status if rd.intake else None,
        "land_type": cx.land_type,
        "inclusion_class": cx.inclusion_class,
        "judge_scope": rd.scope,
        "resale_end": rd.resale_end,
        "price_mid": _dec_s(rd.price_mid),
        "price_low": rd.price_low,
        "move_in_ym": cx.move_in_ym,
        "q": " ".join([cx.name, *(cx.former_names or []), cx.address or ""]),
        "total": _dec_s(rd.total),
        "rank": rd.rank,
        "gap_pct": _dec_s(rd.gap_pct),
        "p10": _dec_s(rd.p10),
        "last_change": ev.detected_at if ev is not None else None,
        "intake_deadline": intake_deadline(cx.apply_dates, rd.b.asof_date),  # 계약 .20 Q9 정렬 키
    }


INTAKE_ORDER: Final = {"가능": 0, "미정": 1, "확인 불가": 2, None: 2, "불가": 3}
"""계약 .20(D28-5 Q9) 정렬 키 ``intake``: 가능 → 미정 → 확인 불가(접수 행 없음 포함) → 불가."""


def intake_deadline(apply_dates: Any, asof: str | None) -> str | None:
    """접수 마감 임박 키: 단지 공고 접수 일정(``complex.apply_dates`` — 저장값) 항목마다 끝날짜(없으면 시작) 중 기준일 이후 가장
    이른 날짜. 일정이 없거나 모두 지났으면 None. 날짜 비교뿐(판단 아님)."""
    days: list[str] = []
    for it in apply_dates or []:
        if not isinstance(it, Mapping):
            continue
        d = it.get("end") or it.get("to") or it.get("start") or it.get("date") or it.get("from")
        text = str(d)[:10] if d else ""
        if len(text) == 10 and text[4] == "-" and (asof is None or text >= asof):
            days.append(text)
    return min(days) if days else None


def match_keys(k: Mapping[str, Any], f: Mapping[str, Any]) -> bool:
    if "living_area" in f and (k["living_area"] or "") not in f["living_area"]:
        return False
    if "intake_status" in f and (k["intake_status"] or "") not in f["intake_status"]:
        return False
    if "land_type" in f and (k["land_type"] or "") not in f["land_type"]:
        return False
    if "inclusion_class" in f and (k["inclusion_class"] or "") not in f["inclusion_class"]:
        return False
    if "judge_scope" in f and k["judge_scope"] not in f["judge_scope"]:
        return False
    if "resale_end_before" in f and (k["resale_end"] is None or k["resale_end"] > f["resale_end_before"]):
        return False
    mid = _dec(k["price_mid"])
    if "price_min" in f and (mid is None or mid < f["price_min"]):
        return False
    if "price_max" in f and (mid is None or mid > f["price_max"]):
        return False
    if "move_in_year" in f and not (k["move_in_ym"] or "").startswith(str(f["move_in_year"])):
        return False
    return not (f.get("q") and f["q"] not in k["q"])


_SORT_GETTERS: dict[str, Callable[[Mapping[str, Any]], Any]] = {
    "total": lambda k: _dec(k["total"]),
    "rank": lambda k: k["rank"],
    "name": lambda k: k["name"],
    "price_mid": lambda k: _dec(k["price_mid"]),
    "price_low": lambda k: k["price_low"],
    "move_in_ym": lambda k: k["move_in_ym"],
    "resale_end": lambda k: k["resale_end"],
    "gap_pct": lambda k: _dec(k["gap_pct"]),
    "p10": lambda k: _dec(k["p10"]),
    "living_area": lambda k: k["living_area"],
    "last_change": lambda k: k["last_change"],
    "intake": lambda k: INTAKE_ORDER.get(k.get("intake_status"), 2),
}


def sort_keyed[T](rows: list[tuple[dict[str, Any], T]], sort: str) -> list[tuple[dict[str, Any], T]]:
    """정렬: 값이 있는 행(같은 값은 complex_id 오름차순 — 안정 정렬) 다음 값 없는 행(complex_id 순).

    ``rank``·``-rank``: 같은 순위(공동 순위) 안은 종합 점수 높은 순 → complex_id(``_ranking.tie_order_key`` — 대시보드 TOP 5·
    민감도·보고서와 같은 순서, R7-FIX2). 방향은 순위에만 걸린다.

    ``intake``·``-intake``(계약 .20 Q9): 접수 상태 순(``INTAKE_ORDER``) — 같은 상태 안은 마감 임박(``intake_deadline``, 없으면
    뒤) → complex_id. 방향은 상태 순서에만 걸린다."""
    desc = sort.startswith("-")
    name = sort.lstrip("-")
    get = _SORT_GETTERS[name]
    present = [r for r in rows if get(r[0]) is not None]
    missing = [r for r in rows if get(r[0]) is None]
    if name == "rank":
        present.sort(key=lambda r: tie_order_key(r[0]["total"], r[0]["cid"]))
    elif name == "intake":
        # 같은 상태 안 = 마감 임박(없으면 뒤) → complex_id — 방향은 상태 순서에만(계약 .20 Q9). 옛 저장본 키에는 마감이 없다(None)
        present.sort(
            key=lambda r: (
                r[0].get("intake_deadline") is None,
                r[0].get("intake_deadline") or "",
                r[0]["cid"],
            )
        )
    else:
        present.sort(key=lambda r: r[0]["cid"])
    present.sort(key=lambda r: get(r[0]), reverse=desc)
    missing.sort(key=lambda r: r[0]["cid"])
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


class LiveRows:
    """발행 전 리비전의 목록 행(실시간). 필터·정렬은 키로, Fact 는 요청한 행(페이지)만 만든다(목록 성능)."""

    def __init__(self, session: Session, settings: Settings, snap: Snapshot, sc: Scenario) -> None:
        region = session.get(Region, snap.region_id)
        # 목록 행은 단지 열을 읽기만 한다 — ORM 객체 대신 같은 열 이름의 읽기 전용 행(R3c 성능).
        # 단지 OCR 표식은 점수 입력(미리보기)만 쓰므로 읽지 않는다(``load_bundles(complex_ocr=False)``)
        # D29-2: 병합된 중복 단지 행(complex.merged_into_id)은 목록에서 뺀다 — 발행 리비전은 저장본 그대로(D11-1)
        complexes = light_rows(
            session,
            select(Complex).where(Complex.region_id == snap.region_id, Complex.merged_into_id.is_(None)),
            Complex,
        )
        bundles = views.load_bundles(session, complexes, snap.id, scenario_id=sc.id, complex_ocr=False)
        self.session, self.settings = session, settings
        self.ctx = views.score_ctx(session, snap.id, sc, with_flags=False)
        self.rows = complex_rows_data(bundles, self.ctx)
        self.last = last_changes(session, [r.b.cx.id for r in self.rows])
        self.names = area_names(region)
        self.keyed = [(row_keys(r, self.last), r) for r in self.rows]

    def items(self, rows: Sequence[RowData]) -> list[dict[str, Any]]:
        return build_rows(self.session, self.settings, self.ctx, rows, self.names, self.last)


def complexes_body(session: Session, settings: Settings, snap: Snapshot, sc: Scenario) -> dict[str, Any]:
    """저장본(D13-1 kind=complexes): 그 시나리오의 단지 행 전부 + 필터·정렬 키(질의는 읽을 때)."""
    live = LiveRows(session, settings, snap, sc)
    items = live.items(live.rows)
    return {
        "scenario_id": sc.id,
        "rows": [{"k": k, "item": it} for (k, _r), it in zip(live.keyed, items, strict=True)],
    }


def _source(session: Session, settings: Settings, snap: Snapshot, sc: Scenario) -> Any:
    """발행 리비전 = 저장 행(dict), 그 밖 = ``LiveRows``(``sv.read`` 가 고른다)."""
    return sv.read(
        session, snap, "complexes", scenario=sc, live=lambda: LiveRows(session, settings, snap, sc)
    )


def query_rows(
    src: Any, filters: Mapping[str, Any], sort: str, start: int = 0, size: int | None = None
) -> tuple[int, list[dict[str, Any]]]:
    """목록 질의(필터 → 정렬 → 페이지) → (전체 수, 응답 행). 저장본·실시간이 같은 키 규칙."""
    if isinstance(src, LiveRows):
        live_rows = sort_keyed([kr for kr in src.keyed if match_keys(kr[0], filters)], sort)
        page = live_rows[start : start + size] if size is not None else live_rows[start:]
        return len(live_rows), src.items([r for _k, r in page])
    stored_rows = [(r["k"], r["item"]) for r in src["rows"] if match_keys(r["k"], filters)]
    stored_rows = sort_keyed(stored_rows, sort)
    picked = stored_rows[start : start + size] if size is not None else stored_rows[start:]
    return len(stored_rows), [it for _k, it in picked]


def build_rows(
    session: Session,
    settings: Settings,
    ctx: ScoreCtx,
    rows: Sequence[RowData],
    names: Mapping[str, str],
    last: Mapping[int, ChangeEvent],
) -> list[dict[str, Any]]:
    bundles: list[ComplexBundle] = [r.b for r in rows]
    fm = FactMaker(settings, provenance_for(session, bundles, list_rows=True))
    days = ladder_days(session, bundles)
    days.update(ctx.jl_days)
    from app.api.views import judgment_days

    days.update(judgment_days(session, (b.cx.inclusion_judgment_seq for b in bundles)))
    # 계약 .20 Q4: 경쟁률 요약 — 페이지 단지의 경쟁률 행·칸 출처만 한 번에 읽는다
    comps = views.competition_rows_for(session, [b.cx.id for b in bundles])
    views.load_competition_prov(session, fm, comps)
    return [
        complex_row(
            fm,
            ctx,
            r,
            names,
            jl_days=days,
            last_change=_last_change_view(last.get(r.b.cx.id)),
            comps=comps.get(r.b.cx.id, ()),
        )
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
    filters = parse_filters(request)
    sc = resolve_scenario(session, scenario)
    src = _source(session, settings_of(request), snap, sc)
    total, items = query_rows(src, filters, sort, (page - 1) * size, size)
    return JSONResponse(
        {
            "items": items,
            "total": total,
            "snapshot_id": snap.id,
            "asof_date": snap.asof_date,
            "page": page,
            "size": size,
            "sort": sort,
            "scenario_id": sc.id,
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


# 스프레드시트가 수식으로 해석하는 첫 글자(CSV 수식 인젝션, OWASP) — 문자열 셀은 앞에 작은따옴표를 붙인다.
# 숫자 값(int·float)은 그대로 둔다(음수 gap_pct 등). R3 minor 18.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _csv_text(v: Any) -> str:
    if v is None:
        return ""
    text = str(v)
    return "'" + text if text.startswith(_FORMULA_START) else text


def _csv_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return _csv_text(v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, int | float):
        return str(v)
    return _csv_text(v)


@router.get("/snapshots/{sid}/complexes.csv")
def export_complexes_csv(
    session: DB,
    request: Request,
    sid: int,
    scenario: ScenarioQ = "base",
    sort: SortQ = "-total",
) -> Response:
    snap = get_snapshot(session, sid)
    filters = parse_filters(request)
    sc = resolve_scenario(session, scenario)
    _total, items = query_rows(_source(session, settings_of(request), snap, sc), filters, sort)
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
        head += [col, f"{col}_label", f"{col}_checked_at", f"{col}_prov"]
    # rank 는 total(Fact)에서 파생한 서수 — 라벨·출처는 total 의 것(R3 minor 18)
    # rejudge_needed(D10-1): 저장 범위 ≠ 현재 사실 범위면 1 — CSV 에도 '재판정 필요'가 보이게(R3 3차 minor 2)
    head += ["rank", "rank_label", "rank_prov", "inclusion_class", "rejudge_needed"]
    w.writerow(head)
    for it in items:
        intake = it["intake"] or {}
        row = [
            it["complex_id"],
            _csv_text(it["name"]),
            _csv_text(it["living_area"]),
            _csv_text(it["living_area_name"]),
            _csv_text(it["judge_scope"]),
            _csv_text(intake.get("status")),
            _csv_text(intake.get("reason")),
            kst_day(intake.get("checked_at")),  # KST 날짜(D14-6)
        ]
        for col in _CSV_FACTS:
            f = it[col]
            label = f["label"] if f["label"] != LABEL_UNKNOWN else f"확인 불가({f.get('reason') or ''})"
            row += [_csv_value(f["v"]), _csv_text(label), f.get("checked_at") or "", f.get("prov") or ""]
        total = it["total"]
        ranked = it["rank"] is not None
        row += [
            it["rank"] if ranked else "",
            _csv_text(total["label"]) if ranked else "",
            (total.get("prov") or "") if ranked else "",
            _csv_text(it["inclusion_class"]),
            1 if it.get("rejudge_needed") else 0,
        ]
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


def partial_missing(facts: Sequence[dict[str, Any]], unit: str) -> dict[str, Any] | None:
    """합계 규칙(R3 M4): 원천이 하나라도 확인 불가면 합계도 '확인 불가(일부 누락 n건)'.

    부분합을 합계로 내지 않는다.

    전부 확인 불가면 첫 원천의 사유를 그대로. 모두 있으면 None(호출자가 합한다)."""
    missing = [f for f in facts if f["label"] == LABEL_UNKNOWN]
    if not missing:
        return None
    if len(missing) == len(facts):
        return facts[0]
    checked = max((f["checked_at"] for f in facts if f.get("checked_at")), default=None)
    return unknown(f"일부 누락 {len(missing)}건", checked, unit=unit)


def _sum_fact(fm: FactMaker, rows: Sequence[Unsold], name: str) -> dict[str, Any]:
    facts = [fm.field("unsold", u.id, name, getattr(u, name), unit="units") for u in rows]
    partial = partial_missing(facts, "units")
    if partial is not None:
        return partial
    known = facts
    total = sum(f["v"] for f in known)
    # 계약 .20(D28-5 Q5): 짧은 사유 — 단위별 값은 KPI ``breakdown``·G6 시장 단위별 점(예전 '<이름> <값>·… 합' 나열은 라벨 칸을 넘쳤다)
    scopes = len({u.scope_code or u.scope_name or str(u.id) for u in rows})
    reason = f"지역 합계(시군구 {scopes}곳)" if len(known) > 1 else known[0].get("reason")
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


def _kpi_count(ctx: ScoreCtx, value: int, first_cid: int | None, *, reason: str = "집계") -> dict[str, Any]:
    """KPI 집계 수. 출처 = 이 점수 실행 전체 ``st_<score_run_id>``.

    단지 하나의 score_total 이 아니다(R3 minor 22)."""
    if ctx.run is None or first_cid is None:
        return unknown("미판정", None, unit="count")
    return fact(value, "추정", f"st_{ctx.run.id}", ctx.checked, reason=reason, unit="count")


def _move_in_peak(session: Session, region_id: int, fm: FactMaker) -> dict[str, Any]:
    rows = list(session.scalars(select(Supply).where(Supply.region_id == region_id)))
    if not rows:
        u = unknown("입주 물량 없음", None)
        return {"year": {**u, "unit": "year"}, "units": {**u, "unit": "units"}}
    fm.prov.load(session, "supply", (s.id for s in rows))
    all_facts = {s.id: fm.field("supply", s.id, "units", s.units, unit="units") for s in rows}
    # 피크 연도는 연도별 합의 최댓값 — 어느 행이든 빠지면 합·피크가 부분값이다(R3 M4)
    partial = partial_missing(list(all_facts.values()), "units")
    if partial is not None:
        return {"year": {**partial, "unit": "year"}, "units": partial}
    by_year: dict[int, list[Supply]] = {}
    for s in rows:
        by_year.setdefault(s.year, []).append(s)
    year, group = max(by_year.items(), key=lambda kv: (sum(s.units or 0 for s in kv[1]), -kv[0]))
    known = [all_facts[s.id] for s in group]
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
    return JSONResponse(sv.read(session, snap, "dashboard", settings=settings_of(request), scenario=sc))


def dashboard_body(session: Session, settings: Settings, snap: Snapshot, sc: Scenario) -> dict[str, Any]:
    """G1 대시보드 응답(실시간 계산 — 발행 리비전은 이 결과를 저장한다, D13-1)."""
    region = session.get(Region, snap.region_id)
    if region is None:
        raise not_found(f"region {snap.region_id}")
    names = area_names(region)
    complexes = list(
        session.scalars(
            select(Complex).where(
                Complex.region_id == snap.region_id, Complex.merged_into_id.is_(None)
            )  # D29-2
        )
    )
    bundles = views.load_bundles(session, complexes, snap.id, scenario_id=sc.id)
    ctx = views.score_ctx(session, snap.id, sc)
    rows = complex_rows_data(bundles, ctx)
    fm = FactMaker(settings, ProvIndex())
    top_ids = sorted(
        (cid for cid, t in ctx.totals.items() if t.rank is not None and t.rank <= 5 and cid in bundles),
        key=lambda cid: display_order_key(ctx.totals[cid].rank, ctx.totals[cid].total, cid),  # R7-FIX2
    )
    days = ladder_days(session, [bundles[c] for c in top_ids])
    days.update(ctx.jl_days)
    # 계약 .20(D28-5 Q7·Q4): TOP 카드의 사실(가격·전매·입주·갭·경쟁률) — 목록 행과 같은 함수·같은 리비전 값(D10-1)
    top_fm = FactMaker(settings, provenance_for(session, [bundles[c] for c in top_ids], list_rows=True))
    top_comps = views.competition_rows_for(session, top_ids)
    views.load_competition_prov(session, top_fm, top_comps)
    top5 = [
        score_row(
            ctx,
            bundles[cid],
            names,
            jl_days=days,
            facts=views.score_row_facts(top_fm, ctx, bundles[cid], top_comps.get(cid, ())),
        )
        for cid in top_ids
    ]
    # D10-1·출처 식(st_<run>): 판정 대상 수 = 이 점수 실행의 score_total.judge_scope='판정 대상'
    # 단지 수(저장값) — TOP 5·순위와 같은 실행이라 KPI 와 TOP 5 가 갈리지 않는다(현재 사실로 다시 세지 않는다)
    if any(t.judge_scope for t in ctx.totals.values()):
        judged = [cid for cid, t in ctx.totals.items() if t.judge_scope == "판정 대상" and cid in bundles]
    else:  # 계약 .3 이전 실행(저장 범위 없음) — 표시 범위로
        judged = [r.b.cx.id for r in rows if r.scope == "판정 대상"]
    # 재판정 필요(계약 .6, D10-1): TOP 5 행 또는 KPI(판정 대상 수 — 저장·현재 범위 중 하나가
    # '판정 대상')에 걸린 단지가 하나라도 있으면 true
    top_set = set(top_ids)
    rejudge = any(
        r.rejudge_needed
        and (r.b.cx.id in top_set or r.scope == "판정 대상" or scope_result(r.b).scope == "판정 대상")
        for r in rows
    )
    first = top_ids[0] if top_ids else (min(ctx.totals) if ctx.totals else None)
    unsold_all = unsold_points(session, region.id, fm)
    latest_unsold = next((p for p in reversed(unsold_all) if p["total"]["label"] != LABEL_UNKNOWN), None)
    unsold_kpi = (
        {
            "ym": latest_unsold["ym"],
            "total": latest_unsold["total"],
            "post_completion": latest_unsold["post_completion"],
            # 계약 .20(D28-5 Q5): 합계의 단위(시군구)별 내역 — 원천 행 Fact 그대로
            "breakdown": [
                p
                for p in unsold_points(session, region.id, fm, per_scope=True)
                if p["ym"] == latest_unsold["ym"]
            ],
        }
        if latest_unsold
        else {
            "ym": None,
            "total": unknown("미분양 자료 없음"),
            "post_completion": unknown("미분양 자료 없음"),
            "breakdown": [],
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
        # 벤치마크 없음 사유(계약 2026-10-09.6, N-M3 — G3; 점수 부분 아님)
        "benchmark_absence": benchmark_absence(session, region.id, benchmarks_for(session, snap)),
        "score_run_id": ctx.run.id if ctx.run is not None else None,
        "weights": ctx.weights,
        "kpis": {
            "judged_count": _kpi_count(ctx, len(judged), first),
            # 접수 가능 수 = 이 스냅샷(리비전)의 표시 접수 행. 발행 리비전은 불변이라 점수 실행이 본
            # 접수 행과 같다(D11-1 — 사람 확인 접수는 새 리비전에 들어간다). 발행 전이면 실행 뒤 바뀐
            # 행일 수 있다(R3 3차 minor 1).
            "intake_open_count": _kpi_count(
                ctx,
                sum(1 for r in rows if r.intake and r.intake.status == "가능"),
                first,
                reason="집계(이 스냅샷 접수 행)"
                if snap.status == "published"
                else "집계(발행 전 — 점수 실행 뒤 접수 행이 바뀌었을 수 있음)",
            ),
            "unsold": unsold_kpi,
            "move_in_peak": _move_in_peak(session, region.id, fm),
            "data_freshness": freshness(session, region.id),
        },
        "top5": top5,
        "changes": query_changes(changes_ledger(session, snap), snap, limit=20),
        "unsold_series": unsold_all,
        "rejudge_needed": rejudge,
    }
    return body
