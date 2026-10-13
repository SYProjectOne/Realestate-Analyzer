"""데이터·운영 (G7): 소스 상태, 판정기 호출 집계, 체크리스트, 사람 확인(T3).

사람 확인(사실 필드)은 resolver 0순위 후보로 그 사실을 바꾸고 같은 사실의 강등(D11-3
'확인 불가(검증 모순)')을 복원 기록한다(``app.api.demotion.apply_human_check`` — 체크리스트 '사실 재확인'
done, change_event + rejudge 잡 제안). GET(체크리스트 목록)은 DB 를 쓰지 않는다(minor 13) — 강등
오버레이는 ``app.facts_view`` 로 읽는 순간 적용된다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.contract import check_body
from app.api.demotion import (
    CHECKED_AT_BEFORE_SOURCE,
    CHECKED_AT_FORMAT,
    DISCOUNT_NOT_BELOW_PRICE,
    HUMAN_FACT_FIELDS,
    ValueParseError,
    apply_human_check,
    checked_at_problem,
    discount_problem,
    human_target,
    later_official,
    parse_human_value,
)
from app.api.deps import DB, get_complex, in_db_range, settings_of
from app.api.errors import ApiError, not_found
from app.api.jobs import now_iso
from app.api.views import envelope_view, intake_view, pick_intake
from app.core.time import kst_date, now_kst
from app.models import (
    ChangeEvent,
    ChecklistItem,
    Complex,
    HumanCheck,
    IntakeStatus,
    JobRun,
    JudgmentLog,
    RawDocument,
    Region,
    Snapshot,
)
from app.models.enums import JUDGE_TOOL, SOURCE_KIND
from app.scheduler.rejudge import enqueue_rejudge
from app.scheduler.snapshots import latest_for_region, writable

router = APIRouter(tags=["ops"])

_DAILY = frozenset({"applyhome_list", "applyhome_detail", "notice_pdf", "official_site"})
_WEEKLY = frozenset({"rtms", "stats", "news"})
# 원문 처리 실패 표식 = ``app.scheduler.collect.PROCESS_FAILURE_PREFIXES``(R5-PIPE). 값만 옮겨 둔다 — collect 를 import 하면 API
# 프로세스에 판정기 어댑터 모듈(``judge.base``)이 올라온다(R5-OPS 경계 테스트). 같은 값인지는 테스트가 확인한다.
PROCESS_FAILURE_PREFIXES: tuple[str, ...] = ("store_failed:", "parse_failed:")


def _ok(d: RawDocument) -> bool:
    """원문이 있고 HTTP 성공이며 처리 실패 표식(R5-PIPE ``store_failed:``·``parse_failed:`` — 원문 저장·파싱 실패)이 없으면 성공.
    수집기 표식(OCR ``scan`` 등)은 원문이 있으면 성공이다."""
    if d.error_text is not None and d.error_text.startswith(PROCESS_FAILURE_PREFIXES):
        return False
    return d.path is not None and (d.http_status is None or 200 <= d.http_status < 300)


def _reason(d: RawDocument) -> str:
    if d.http_status is not None and not 200 <= d.http_status < 300:
        return str(d.http_status)
    return d.error_text or "원문 없음"


@router.get("/ops/sources")
def list_source_status(session: DB, request: Request, region_id: int | None = None) -> JSONResponse:
    settings = settings_of(request)
    if not in_db_range(region_id):
        return JSONResponse([])
    if region_id is None:
        rid = session.scalars(select(Region.id).order_by(Region.id).limit(1)).first()
    else:
        if session.get(Region, region_id) is None:
            return JSONResponse([])
        rid = region_id
    week_ago = (now_kst() - timedelta(days=7)).isoformat(timespec="seconds")
    names = {cid: name for cid, name in session.execute(select(Complex.id, Complex.name))}
    out = []
    for kind in SOURCE_KIND:
        stmt = select(RawDocument).where(RawDocument.source_kind == kind)
        if region_id is not None:
            stmt = stmt.where((RawDocument.region_id == region_id) | (RawDocument.region_id.is_(None)))
        docs = list(session.scalars(stmt.order_by(RawDocument.fetched_at.desc(), RawDocument.id.desc())))
        recent = [d for d in docs if d.fetched_at >= week_ago]
        ok_docs = [d for d in docs if _ok(d)]
        latest_by_url: dict[str, RawDocument] = {}
        for d in docs:
            latest_by_url.setdefault(d.url, d)
        failing = [
            {
                "url": d.url,
                "complex_id": d.complex_id,
                "complex_name": names.get(d.complex_id) if d.complex_id is not None else None,
                "http_status": d.http_status,
                "reason": _reason(d),
                "fetched_at": d.fetched_at,
                "raw_document_id": d.id,
            }
            for d in latest_by_url.values()
            if not _ok(d)
        ]
        enabled, why = True, None
        if kind == "news" and settings.news_api_key is None:
            enabled, why = False, "NEWS_API_KEY 없음"
        retry: dict[str, Any] | None = None
        if kind == "reference":
            retry = {"job_name": "reference.refresh", "payload": {}}
        elif rid is not None and kind in _DAILY:
            retry = {"job_name": "collect.daily", "payload": {"region_id": rid, "sources": [kind]}}
        elif rid is not None and kind in _WEEKLY:
            retry = {"job_name": "collect.weekly", "payload": {"region_id": rid, "sources": [kind]}}
        last = docs[0] if docs else None
        out.append(
            {
                "source_kind": kind,
                "enabled": enabled,
                "disabled_reason": why,
                "last_attempt_at": last.fetched_at if last else None,
                "last_success_at": ok_docs[0].fetched_at if ok_docs else None,
                "attempts_7d": len(recent),
                "successes_7d": sum(1 for d in recent if _ok(d)),
                "failures_7d": sum(1 for d in recent if not _ok(d)),
                "last_http_status": last.http_status if last else None,
                "last_error_text": last.error_text if last else None,
                "failing_targets": failing,
                "retry": retry,
            }
        )
    return JSONResponse(out)


def cache_hits(session: Any, since: str, tool: str | None = None) -> tuple[int, dict[str, int]]:
    """캐시 재생 수(R3 minor 23): 판정기를 다시 부르지 않은 호출은 judgment_log 에 행을 남기지 않으므로
    worker 잡 집계(``job_run.stats.cached`` — scheduler.pipeline.CountingCaller)를 더한다.
    도구별은 잡이 ``stats.cached_by_tool`` 을 남길 때만(없으면 도구별 0, 합계에는 들어간다).
    ``tool`` 을 주면 그 도구 수만(도구별 집계가 없는 잡은 셀 수 없어 0)."""
    total = 0
    by_tool: dict[str, int] = defaultdict(int)
    stmt = select(JobRun.stats).where(JobRun.started_at.is_not(None), JobRun.started_at >= since)
    for stats in session.scalars(stmt):
        if not isinstance(stats, dict):
            continue
        per_tool = stats.get("cached_by_tool")
        if isinstance(per_tool, dict):
            for name, n in per_tool.items():
                if isinstance(n, int) and n > 0:
                    by_tool[str(name)] += n
        n_all = stats.get("cached")
        if tool is None and isinstance(n_all, int) and n_all > 0:
            total += n_all
    if tool is not None:
        total = by_tool.get(tool, 0)
    return total, dict(by_tool)


def sent_calls(session: Any, since: str) -> tuple[int, dict[str, int], bool]:
    """판정기로 실제 보낸 ``tools/call`` 수(D18-2) — worker 잡 stats ``tools_calls``(전송 계층 계수)의 합.
    (합계, 도구별, 집계가 있는 잡이 하나라도 있었나). R4-FIX 이전 잡은 이 집계가 없다."""
    total = 0
    by_tool: dict[str, int] = defaultdict(int)
    seen = False
    stmt = select(JobRun.stats).where(JobRun.started_at.is_not(None), JobRun.started_at >= since)
    for stats in session.scalars(stmt):
        if not isinstance(stats, dict) or not isinstance(stats.get("tools_calls"), int):
            continue
        seen = True
        total += max(0, int(stats["tools_calls"]))
        per_tool = stats.get("tools_calls_by_tool")
        if isinstance(per_tool, dict):
            for name, n in per_tool.items():
                if isinstance(n, int) and n > 0:
                    by_tool[str(name)] += n
    return total, dict(by_tool), seen


@router.get("/ops/judgments")
def get_judgment_ops(
    session: DB,
    since: Annotated[str | None, Query(min_length=10, max_length=32)] = None,
    tool: Annotated[str | None, Query(pattern="^(" + "|".join(JUDGE_TOOL) + ")$")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> JSONResponse:
    now = now_kst()
    start = since or (now - timedelta(days=30)).date().isoformat()
    stmt = select(JudgmentLog).where(JudgmentLog.created_at >= start)
    if tool:
        stmt = stmt.where(JudgmentLog.tool == tool)
    rows = list(session.scalars(stmt.order_by(JudgmentLog.seq.desc())))
    by_tool: dict[str, list[JudgmentLog]] = defaultdict(list)
    daily: dict[str, list[JudgmentLog]] = defaultdict(list)
    for r in rows:
        by_tool[r.tool].append(r)
        daily[(r.created_at or "")[:10]].append(r)

    def avg(items: list[JudgmentLog]) -> float | None:
        vals = [r.duration_ms for r in items if r.duration_ms is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def count(items: list[JudgmentLog], status: str) -> int:
        return sum(1 for r in items if r.status == status)

    latest_snap = session.scalars(
        select(Snapshot).order_by(Snapshot.created_at.desc(), Snapshot.id.desc())
    ).first()
    cached_total, cached_by_tool = cache_hits(session, start, tool)
    # D18-2: 실제 호출 = 판정기로 보낸 tools/call 수(잡 stats 전송 계층 계수). guard 차단(blocked) 행은 보내지 않은 호출.
    # 계수가 없는 기간(R4-FIX 이전 잡·MockAdapter 재생)은 judgment_log 행 수가 하한이라 둘 중 큰 값을 쓴다.
    sent_total, sent_by_tool, _ = sent_calls(session, start)
    logged = sum(1 for r in rows if r.status != "blocked")
    if tool:
        sent_total = sent_by_tool.get(tool, 0)
    real_calls = max(logged, sent_total)
    stats = {
        "since": start,
        "until": now.date().isoformat(),
        "total_calls": real_calls + cached_total,
        "real_calls": real_calls,
        "cached_hits": cached_total,
        "failures": count(rows, "error"),
        "blocked": count(rows, "blocked"),
        "review": count(rows, "review"),
        "escaped": count(rows, "escaped"),
        "avg_duration_ms": avg(rows),
        "by_tool": [
            {
                "tool": t,
                "calls": max(sum(1 for r in items if r.status != "blocked"), sent_by_tool.get(t, 0)),
                "cached": cached_by_tool.get(t, 0),
                "failures": count(items, "error"),
                "review": count(items, "review"),
                "escaped": count(items, "escaped"),
                "blocked": count(items, "blocked"),
                "avg_duration_ms": avg(items),
            }
            for t, items in sorted(by_tool.items())
        ],
        "daily": [
            {"date": d, "calls": len(items), "failures": count(items, "error")}
            for d, items in sorted(daily.items())
            if len(d) == 10
        ],
        "adapter_version": (rows[0].adapter_version[:64] if rows else None),
        "degraded": bool(latest_snap.degraded) if latest_snap is not None else False,
    }
    first = (page - 1) * size
    return JSONResponse(
        {
            "stats": stats,
            "items": [envelope_view(r) for r in rows[first : first + size]],
            "total": len(rows),
            "page": page,
            "size": size,
        }
    )


def checklist_view(item: ChecklistItem, names: dict[int, str]) -> dict[str, Any]:
    return {
        "id": item.id,
        "complex_id": item.complex_id,
        "complex_name": names.get(item.complex_id) if item.complex_id is not None else None,
        "kind": item.kind,
        "title": item.title,
        "due_date": item.due_date,
        "status": item.status,
        "note": item.note,
        "closed_by": item.closed_by,
    }


def _complex_names(session: Any) -> dict[int, str]:
    return {cid: name for cid, name in session.execute(select(Complex.id, Complex.name))}


@router.get("/ops/checklist")
def list_checklist(
    session: DB,
    status: Annotated[str | None, Query(pattern="^(open|done|na)$")] = None,
    complex_id: int | None = None,
) -> JSONResponse:
    if not in_db_range(complex_id):
        return JSONResponse([])
    stmt = select(ChecklistItem)  # GET 은 DB 를 쓰지 않는다(minor 13 — 강등 복원 기록은 쓰기 경로)
    if status:
        stmt = stmt.where(ChecklistItem.status == status)
    if complex_id is not None:
        stmt = stmt.where(ChecklistItem.complex_id == complex_id)
    items = sorted(session.scalars(stmt), key=lambda i: (i.due_date is None, i.due_date or "", i.id))
    names = _complex_names(session)
    return JSONResponse([checklist_view(i, names) for i in items])


@router.patch("/ops/checklist/{id}")
def update_checklist_item(session: DB, id: int, body: Annotated[Any, Body()] = None) -> JSONResponse:
    item = session.get(ChecklistItem, id)
    if item is None:
        raise not_found(f"checklist_item {id}")
    check_body("updateChecklistItem", body)
    before = (item.status, item.note, item.due_date)
    for key in ("status", "note", "due_date"):
        if key in body:
            setattr(item, key, body[key])
    if "status" in body:  # 사람 처리(done·na) = closed_by human — 동기화가 다시 열지 않는다(M-9)
        item.closed_by = None if item.status == "open" else "human"
    if item.kind == "사실 재확인" and item.status != "open" and item.complex_id is not None:
        # R3 4차 minor(3차 minor 12 후속): 강등이 남았으면 '사실 재확인'은 그 자리에서 다시 열린다(다음 쓰기를 기다리지
        # 않는다 — 응답이 열린 상태를 보인다). 강등과 무관한 항목(사람 확인 재검토 등)은 그대로 닫힌다
        from app.api.demotion import sync_demotions

        session.flush()
        sync_demotions(session, {item.complex_id})
    session.flush()
    job_id: int | None = None
    if (item.status, item.note, item.due_date) != before:
        # D17-5(계약 .14): 체크리스트(상태·메모·기한)는 발행 리비전 보고서 본문(§8-4 체크리스트·캘린더)에 들어간다 — 바뀌면
        # 발행 잡(지역마다 — 단지 없는 '지역 공통' 항목은 모든 지역). 바뀐 것이 없으면 200 + job_id null
        from app.scheduler.snapshots import republish

        cx = session.get(Complex, item.complex_id) if item.complex_id is not None else None
        regions = (
            [cx.region_id] if cx is not None else list(session.scalars(select(Region.id).order_by(Region.id)))
        )
        for rid in regions:
            job = republish(session, rid, reason=f"체크리스트 변경: {item.title}"[:200], created_at=now_iso())
            if job is not None and job_id is None:
                job_id = int(job.id)
    session.commit()
    return JSONResponse(
        {**checklist_view(item, _complex_names(session)), "job_id": job_id},
        status_code=202 if job_id is not None else 200,
    )


def _value_errors(session: Any, body: Any) -> list[tuple[dict[str, Any], str]]:
    """R3i m2: 스키마 검사가 실패한 본문에서도 값 칸(형식·할인 상한)을 검사한다 — (field_error, code) 목록(문제 없거나 볼 수 없으면
    빈 목록). 단지·필드를 모르면 보지 않는다."""
    if not isinstance(body, dict):
        return []
    cid, field, text = body.get("complex_id"), body.get("field"), body.get("value_text")
    if (
        isinstance(cid, bool)
        or not isinstance(cid, int)
        or field not in HUMAN_FACT_FIELDS
        or not isinstance(text, str)
    ):
        return []
    if not in_db_range(cid) or session.get(Complex, cid) is None:
        return []
    eid = body.get("entity_id")
    try:
        target = human_target(
            session, cid, str(field), eid if isinstance(eid, int) and not isinstance(eid, bool) else None
        )
        value = parse_human_value(target, text) if target is not None else None
        problem = discount_problem(session, cid, value) if field == "discount" else None
        if problem is not None:
            raise ValueParseError(problem, code=DISCOUNT_NOT_BELOW_PRICE)
    except ValueParseError as exc:
        loc = ["body", "entity_id" if "entity_id" in str(exc) else "value_text"]
        return [({"loc": loc, "msg": str(exc)}, exc.code)]
    return []


def _checked_at_422(code: str, detail: str) -> ApiError:
    """계약 .12: 사람 확인 checked_at 422 — code = checked_at_format·checked_at_future·checked_at_before_source,
    field_errors[0].loc = ["body","checked_at"](.11 과 같음)."""
    return ApiError(422, code, detail, field_errors=[{"loc": ["body", "checked_at"], "msg": detail}])


@router.post("/ops/human-checks", status_code=201)
def create_human_check(session: DB, body: Annotated[Any, Body()] = None) -> JSONResponse:
    """사람 확인 입력(T3, D11-3). 사실 필드면 resolver 0순위 후보로 그 사실을 바꾸고(재정규화에도 유지) 같은 사실의 강등을
    복원 기록한다. 접수 상태면 그 기준일의 쓰기 가능 리비전(발행됐으면 새 리비전 — D11-1)에 human_check 접수 행을
    넣는다.
    값은 필드 형·범위(minor 11), note·value_text 는 길이(계약)·guard(전화·주민번호·이메일·비밀값 → 422)를 통과해야
    한다."""
    from app.judge.guard import check_payload

    # D14-6(N-M4, 계약 .11)·D15-7: checked_at = 시간대가 붙은 RFC3339, 2000년 이후, 지금보다 10분 넘게 미래면 422.
    # 계약 .12 F14·R3 8차 m11: checked_at **만** 틀렸으면 그 code(checked_at_*), 다른 칸도 틀렸으면 validation_error 에
    # 모든 칸(checked_at 포함)의 field_errors — 한 칸 오류가 다른 칸 오류를 가리지 않는다
    bad_time = checked_at_problem(body.get("checked_at")) if isinstance(body, dict) else None
    time_err = {"loc": ["body", "checked_at"], "msg": bad_time[1]} if bad_time is not None else None

    def _is_time(e: Mapping[str, Any]) -> bool:
        return list(e.get("loc") or [])[:2] == ["body", "checked_at"]

    try:
        check_body("createHumanCheck", body)
    except ApiError as exc:
        errs = list(exc.field_errors or [])
        if errs and all(_is_time(e) for e in errs):
            raise _checked_at_422(CHECKED_AT_FORMAT, exc.detail) from exc
        if time_err is not None and not any(_is_time(e) for e in errs):
            errs.append(time_err)
        # R3i m2: 스키마 오류가 있어도 값 칸(형식·할인 상한)도 검사해 모든 칸을 한 번에(F9 — 한 칸 오류가 다른 칸을 가리지 않는다)
        seen = {tuple(e.get("loc") or []) for e in errs}
        errs += [e for e, _code in _value_errors(session, body) if tuple(e["loc"]) not in seen]
        # R3i m10(F9): checked_at 오류가 늘 먼저(스키마 검사기 순서와 무관)
        errs.sort(key=lambda e: 0 if _is_time(e) else 1)
        raise ApiError(422, "validation_error", exc.detail, field_errors=errs) from exc
    cx = get_complex(session, body["complex_id"])
    others: list[dict[str, Any]] = []
    value_code: str | None = None
    guard = check_payload({"value_text": body["value_text"], "note": body.get("note") or ""})
    if not guard.ok:
        others.append({
            "loc": ["body", "note" if any("note" in f.path for f in guard.findings) else "value_text"],
            "msg": f"공개할 수 없는 정보가 있다({', '.join(guard.kinds())}) — 통화 내용은 요약만 적는다",
        })  # fmt: skip
    field = str(body["field"])
    target = None
    value: Any = None
    if field in HUMAN_FACT_FIELDS:
        try:
            target = human_target(session, cx.id, field, body.get("entity_id"))
            value = parse_human_value(target, str(body["value_text"])) if target is not None else None
            problem = discount_problem(session, cx.id, value) if field == "discount" else None
            if problem is not None:
                raise ValueParseError(problem, code=DISCOUNT_NOT_BELOW_PRICE)
        except ValueParseError as exc:
            target = None
            others.append(
                {"loc": ["body", "entity_id" if "entity_id" in str(exc) else "value_text"], "msg": str(exc)}
            )
            value_code = exc.code
    if others:
        errs = ([time_err] if time_err is not None else []) + others
        # 계약 .14(R3i m2): 할인 값 칸**만** 틀렸으면 그 code(discount_format·discount_not_below_price), 아니면 validation_error
        only_value = len(errs) == 1 and errs[0]["loc"] == ["body", "value_text"] and value_code is not None
        code = value_code if only_value and value_code is not None else "validation_error"
        raise ApiError(422, code, "; ".join(str(e["msg"]) for e in errs), field_errors=errs)
    if bad_time is not None:
        raise _checked_at_422(*bad_time)
    if target is not None:
        # D13-2·D14-6: 이미 수집된 공식 공고(KST 날짜로 확인일보다 뒤 관측)가 **다른 값**이면 입력 즉시 지는 사람
        # 확인(D12-1) — 조용히 받지 않는다. 같은 값의 나중 공고는 정상(m11)
        later = later_official(session, target, str(body["checked_at"]), value)
        if later is not None:
            day = kst_date(str(body["checked_at"]))
            raise _checked_at_422(
                CHECKED_AT_BEFORE_SOURCE,
                f"확인일 {day.isoformat() if day else str(body['checked_at'])[:10]}(KST) 은 이미 수집된 공식 공고"
                f"(관측 {later}, 다른 값)보다 이르다 — 그 공고 뒤에 다시 확인한 날짜를 적는다(사람 확인 이후 공고만 "
                "사람 확인을 이긴다, D12-1)",
            )
    hc = HumanCheck(
        complex_id=cx.id,
        field=field,
        value_text=body["value_text"],
        kind=body["kind"],
        checked_at=body["checked_at"],
        entered_by=body["entered_by"],
        note=body.get("note"),
        created_at=now_iso(),
        entity=target.entity if target is not None else None,
        entity_id=target.entity_id if target is not None else None,
    )
    session.add(hc)
    session.flush()
    created: dict[str, Any] | None = None
    change_id: int | None = None
    rejudge_job: JobRun | None = None
    # M-2: 재판정은 그 지역의 가장 새 (기준일, 리비전) — 더 새 기준일이 발행 전이면 거기(옛 기준일에 리비전을 만들지
    # 않는다). 발행됐으면 새 리비전(D11-1). change_event 도 그 리비전에 붙는다(발행 스냅샷은 불변)
    base = latest_for_region(session, cx.region_id)
    snap_w = (
        writable(session, base.id, reason=f"사람 확인: {cx.name} {field}"[:200], created_at=now_iso())
        if base is not None and (target is not None or field == "intake_status")
        else None  # '기타'(기록만)는 리비전·재판정 없음
    )
    if target is not None:
        restored = apply_human_check(session, hc, snapshot_id=snap_w.id if snap_w is not None else None)
        ce = ChangeEvent(
            snapshot_id=snap_w.id if snap_w is not None else None,
            entity=target.entity,
            entity_id=target.entity_id,
            field=target.field[:64],
            old_text="확인 불가(검증 모순)" if restored else None,
            new_text=f"{hc.value_text} (사람 확인)"[:200],
            detected_at=now_iso(),
            severity="critical",
            triggers_rejudge=True,
            complex_id=cx.id,
        )
        session.add(ce)
        session.flush()
        change_id = ce.id
        if snap_w is not None:  # D12-5: 재판정은 제안이 아니라 자동 등록
            rejudge_job = enqueue_rejudge(
                session,
                snap_w.id,
                [cx.id],
                (f"사람 확인 입력: {cx.name} {field}" + (" 복원" if restored else ""))[:200],
                change_event_ids=[ce.id],
            )
    if field == "intake_status" and snap_w is not None:
        snap = snap_w
        before = pick_intake(
            list(
                session.scalars(
                    select(IntakeStatus).where(
                        IntakeStatus.complex_id == cx.id, IntakeStatus.snapshot_id == snap.id
                    )
                )
            )
        )
        row = IntakeStatus(
            complex_id=cx.id,
            snapshot_id=snap.id,
            status=hc.value_text,
            path="human_check",
            checked_at=hc.checked_at,
            reason="사람 확인" if hc.value_text in ("확인 불가", "불가") else None,
            note=hc.note,
            entered_by=hc.entered_by,
        )
        session.add(row)
        session.flush()
        old = None
        if before is not None:
            old = before.status + (f"({before.reason})" if before.reason else "") + f" [{before.path}]"
        ce = ChangeEvent(
            snapshot_id=snap.id,
            entity="intake_status",
            entity_id=row.id,
            field="status",
            old_text=old,
            new_text=hc.value_text,
            detected_at=now_iso(),
            severity="critical",
            triggers_rejudge=True,
            complex_id=cx.id,
        )
        session.add(ce)
        session.flush()
        created = intake_view(row)
        change_id = ce.id
        rejudge_job = enqueue_rejudge(
            session,
            snap.id,
            [cx.id],
            f"사람 확인 입력: {cx.name} 접수 {hc.value_text}"[:200],
            change_event_ids=[ce.id],
        )
    session.commit()
    return JSONResponse(
        {
            "id": hc.id,
            "complex_id": hc.complex_id,
            "field": hc.field,
            "entity": hc.entity,
            "entity_id": hc.entity_id,
            "value_text": hc.value_text,
            "kind": hc.kind,
            "checked_at": hc.checked_at,
            "entered_by": hc.entered_by,
            "note": hc.note,
            "created_intake": created,
            "change_event_id": change_id,
            # 계약 .9(D12-5): 재판정은 자동 등록(rejudge_job_id). suggested_job 은 그 잡과 같은 payload(호환 — POST /jobs 로
            # 보내도 대기 중인 같은 잡을 돌려준다, 중복 등록 없음)
            "suggested_job": (
                {"job_name": "rejudge", "payload": dict(rejudge_job.payload or {})}
                if rejudge_job is not None
                else None
            ),
            "rejudge_job_id": rejudge_job.id if rejudge_job is not None else None,
            # 계약 .11(D14-5): 발행을 부르는 쓰기 응답의 공통 이름(= rejudge_job_id) — 자원을 만드는 POST 라 201 그대로
            "job_id": rejudge_job.id if rejudge_job is not None else None,
            # 계약 .14(D17-4): 할인 사람 확인이 들어간 기준 타입(화면 안내 — '기준 타입 84A 할인'). 할인이 아니면 null
            "basis_type_code": _basis_code(target),
        },
        status_code=201,
    )


def _basis_code(target: Any) -> str | None:
    """사람 확인 할인 대상 칸(``discount_by_type.<타입>``)의 타입 코드 — 할인이 아니면 None."""
    f = getattr(target, "field", None)
    return f.split(".", 1)[1] if isinstance(f, str) and f.startswith("discount_by_type.") else None
