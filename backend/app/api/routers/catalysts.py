"""호재 URL 사람 입력 (DECISIONS D1-6, 계약 2026-10-09.4 — R3 M6).

``POST /catalysts``: 공개 기사·공고 URL + 제목(+발췌) → 호재 후보 행 → 분류 잡.

- 후보 행은 F1a 의 ``app.normalize.catalyst`` 공개 함수가 만든다(정규화 소유 — api 는 행 모양을 정하지
  않는다). 가져오기는 지연한다(``candidate_factory``): 모듈·함수가 없으면 ``CandidateUnavailable``
  → 500 internal(사유).
  기대 시그니처::

      catalyst_candidate(session, region_id, *, url: str, title: str, excerpt: str | None = None)
          -> CatalystCandidate(catalyst, created)   # flush 만, 같은 URL 이면 그 행(created=False)
      CatalystInputError(ValueError)              # URL·제목이 후보 조건에 안 맞음 → 422

- 분류(kind·stage)는 판정기 classify 가 한다(규칙 3): 지역 최신 스냅샷에 rejudge(complex_ids=[] → P4 호재
  classify·점수 재계산)를 등록한다 — 같은 스냅샷에 대기 중인 rejudge 가 있으면 그 잡에 합친다
  (``scheduler.rejudge.enqueue_rejudge``). 스냅샷이 없으면 job=null(다음 파이프라인 P4 가 분류).
- URL 정규화(``normalize_url``, 재리뷰 F3): scheme·host 소문자, 기본 포트·fragment·추적 쿼리
  (utm_*·fbclid·gclid 등) 제거, 남은 쿼리 정렬, 끝 '/' 제거. 같은 지역에 정규화 URL 이 같은 호재가 이미
  있으면 그 행을 돌려주고(후보 함수를 다시 부르지 않는다) rejudge 를 다시 등록하지 않는다(job=null).
  후보 함수가 기존 행을 돌려줘도(created=False) 다시 등록하지 않는다.
- 제목·발췌는 guard(전화번호·주민번호·이메일·비밀값)를 통과해야 한다 — 판정기 payload 로 가는 문장이다(422).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import importlib
import math
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.contract import check_body, has_visible
from app.api.deps import DB, default_snapshot, get_region, settings_of
from app.api.errors import ApiError, not_found, validation_error
from app.api.facts import FactMaker, ProvIndex
from app.api.jobs import job_view, now_iso
from app.api.routers.complexes import catalyst_view
from app.models import Catalyst, CatalystLink, Snapshot

__all__ = [
    "CANDIDATE_FUNCTION",
    "CANDIDATE_MODULE",
    "CandidateUnavailable",
    "candidate_factory",
    "normalize_url",
    "router",
]

router = APIRouter(tags=["market"])

CANDIDATE_MODULE = "app.normalize.catalyst"
CANDIDATE_FUNCTION = "catalyst_candidate"


class CandidateUnavailable(RuntimeError):
    """F1a 의 후보 함수가 아직 없다(라운드 병렬 진행 — 머지 전)."""


def candidate_factory() -> Callable[..., Any]:
    """``app.normalize.catalyst.catalyst_candidate`` 를 지연 import 한다(테스트는 대역으로 바꾼다)."""
    try:
        module = importlib.import_module(CANDIDATE_MODULE)
    except ModuleNotFoundError as exc:
        raise CandidateUnavailable(f"{CANDIDATE_MODULE} 모듈 없음(호재 후보 함수 미머지)") from exc
    fn = getattr(module, CANDIDATE_FUNCTION, None)
    if not callable(fn):
        raise CandidateUnavailable(f"{CANDIDATE_MODULE}.{CANDIDATE_FUNCTION} 없음")
    return fn  # type: ignore[no-any-return]


_TRACKING = ("utm_", "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref_src")
_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(url: str) -> str:
    """같은 기사·공고를 같은 문자열로(문자열 정규화 — 판단 아님)."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host if port is None or _DEFAULT_PORTS.get(scheme) == port else f"{host}:{port}"
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(_TRACKING)
    )
    path = parts.path.rstrip("/") if parts.path not in ("", "/") else ""
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


def _existing(session: Session, region_id: int, url: str) -> Catalyst | None:
    want = normalize_url(url)
    for row in session.scalars(
        select(Catalyst)
        .where(Catalyst.region_id == region_id, Catalyst.source_url.is_not(None))
        .order_by(Catalyst.id)
    ):
        if row.source_url and normalize_url(row.source_url) == want:
            return row
    return None


def _snapshot_for(session: Session, region_id: int) -> Snapshot | None:
    snap = default_snapshot(session, region_id)
    if snap is not None:
        return snap
    return session.scalars(
        select(Snapshot)
        .where(Snapshot.region_id == region_id)
        .order_by(Snapshot.asof_date.desc(), Snapshot.id.desc())
        .limit(1)
    ).first()


@router.post("/catalysts", status_code=201)
def create_catalyst(session: DB, request: Request, body: Annotated[Any, Body()] = None) -> JSONResponse:
    check_body("createCatalyst", body)
    region = get_region(session, int(body["region_id"]))
    url = normalize_url(str(body["url"]))
    title = str(body["title"]).strip()
    excerpt = (str(body.get("excerpt") or "").strip()) or None
    if not has_visible(title):  # 계약 .19: 스키마 pattern 과 같은 규칙
        raise validation_error("title 이 비었다", ("body", "title"))
    from app.judge.guard import check_payload

    guard = check_payload({"title": title, "excerpt": excerpt or "", "url": url})
    if not guard.ok:
        raise validation_error(
            f"공개할 수 없는 정보가 있다({', '.join(guard.kinds())}) — 판정기로 보내지 않는다",
            ("body",),
        )
    have = _existing(session, region.id, url)
    if have is not None:  # 같은 기사·공고 — 후보 함수·rejudge 를 다시 부르지 않는다
        snap = _snapshot_for(session, region.id)
        checked = (snap.asof_date if snap is not None else now_iso())[:10]
        fm = FactMaker(settings_of(request), ProvIndex().load(session, "catalyst", [have.id]))
        return JSONResponse(
            {"catalyst": catalyst_view(have, checked, fm=fm), "job": None, "job_id": None}, status_code=201
        )
    try:
        make = candidate_factory()
    except CandidateUnavailable as exc:
        raise ApiError(500, "internal", str(exc)) from exc
    try:
        made = make(session, region.id, url=url, title=title, excerpt=excerpt)
    except ValueError as exc:  # normalize.catalyst.CatalystInputError(ValueError) — 후보 조건 위반
        raise validation_error(f"호재 후보로 받을 수 없다: {exc}", ("body",)) from exc
    row = getattr(made, "catalyst", made)
    if not isinstance(row, Catalyst):
        raise ApiError(500, "internal", f"{CANDIDATE_MODULE}.{CANDIDATE_FUNCTION}: 행 없음")
    session.flush()
    snap = _snapshot_for(session, region.id)
    job_out: dict[str, Any] | None = None
    if snap is not None and getattr(made, "created", True) is not False:
        from app.scheduler.rejudge import enqueue_rejudge

        job = enqueue_rejudge(session, snap.id, [], f"호재 URL 입력: {title}"[:200])
        job_out = job_view(job)
    session.commit()
    checked = (snap.asof_date if snap is not None else now_iso())[:10]
    fm = FactMaker(settings_of(request), ProvIndex().load(session, "catalyst", [row.id]))
    view = catalyst_view(row, checked, fm=fm)
    return JSONResponse(
        {"catalyst": view, "job": job_out, "job_id": job_out["id"] if job_out is not None else None},
        status_code=201,
    )  # 계약 .12(D15-6·m16): 발행을 일으키는 쓰기 응답은 job_id


# ====================================================================== D11-5 위치 확인 → catalyst_link (계약 .8)

LINK_WEIGHT = Decimal("1")
"""단지 좌표가 없어 거리를 잴 수 없을 때의 연결 가중치(같은 생활권·사람 지정 = 1, D11-5)."""
COORD_STEP = Decimal("0.000001")
"""호재 좌표 저장 자리(catalyst.lat·lon = Numeric(9, 6)) — R3i m8."""


def _link_view(link: CatalystLink) -> dict[str, Any]:
    return {
        "complex_id": link.complex_id,
        "distance_m": link.distance_m,
        "weight": float(link.weight) if link.weight is not None else None,
        "label": link.label or "추정",
        "reason": link.reason,
    }


@router.patch("/catalysts/{id}", status_code=202)
def update_catalyst(
    session: DB, request: Request, id: int, body: Annotated[Any, Body()] = None
) -> JSONResponse:
    """사람이 호재 위치를 확인하고 영향 범위(단지·생활권)를 지정한다(D11-5). location_confirmed=true 면 catalyst_link 를
    만든다 — 단지 좌표가 없으므로 distance_m NULL, weight 1, 라벨 추정. false 면 연결을 모두 지운다(RA: 위치 미확정 =
    연결 없음). expected_ym 은 사람 확인 출처 행(reason '사람 확인(위치 확인)')으로 남긴다. 연결이 바뀌면 지역 최신
    스냅샷에 rejudge(점수 재계산 — 대상 단지 0개)를 등록한다."""
    from app.models import Complex

    check_body("updateCatalyst", body)
    cat = session.get(Catalyst, id)
    if cat is None:
        raise not_found(f"catalyst {id}")
    region = get_region(session, cat.region_id)
    confirmed = bool(body["location_confirmed"])
    for key, bound in (
        ("lat", 90),
        ("lon", 180),
    ):  # R3 4차 M-13: NaN·무한대·범위 밖 좌표는 쓰기 전에 422(커밋 뒤 500 금지)
        v = body.get(key)
        if v is not None and (
            isinstance(v, bool)
            or not isinstance(v, int | float)
            or not math.isfinite(v)
            or not -bound <= v <= bound
        ):
            raise validation_error(f"{key} 는 유한한 숫자(−{bound}~{bound})여야 한다: {v!r}", ("body", key))
    if (
        confirmed and cat.stage == "호재 아님"
    ):  # minor: 판정기가 호재가 아니라고 본 후보는 단지에 연결하지 않는다
        raise validation_error(
            "'호재 아님' 판정 후보는 위치 확인·연결을 할 수 없다", ("body", "location_confirmed")
        )
    area_ids = [str(a) for a in body.get("living_area_ids") or []]
    known_areas = {str(a.get("id")) for a in region.living_areas or []}
    bad = [a for a in area_ids if a not in known_areas]
    if bad:
        raise validation_error(f"이 지역에 없는 생활권: {', '.join(bad)}", ("body", "living_area_ids"))
    want: dict[int, str] = {}
    for cid in body.get("complex_ids") or []:
        cx = session.get(Complex, int(cid))
        if cx is None or cx.region_id != region.id:
            raise validation_error(f"이 지역의 단지가 아니다: {cid}", ("body", "complex_ids"))
        want[cx.id] = "사람 지정(단지 좌표 없음)"
    if area_ids:
        for cx in session.scalars(
            select(Complex).where(
                Complex.region_id == region.id,
                Complex.living_area.in_(area_ids),
                Complex.merged_into_id.is_(None),  # D29-2: 병합된 중복 행에는 잇지 않는다
            )
        ):
            want.setdefault(cx.id, f"같은 생활권({cx.living_area}, 단지 좌표 없음)")
    if confirmed and not want:
        raise validation_error(
            "위치를 확인했으면 영향 단지(complex_ids) 또는 생활권(living_area_ids)을 하나 이상 지정한다",
            ("body",),
        )

    # D16-4(R3 8차 N-M4): 발행 리비전 응답에 보이는 값(위치 확인·좌표·예정월·연결)이 하나라도 바뀌면 발행 잡, 아니면 200
    def _num(v: Any) -> Decimal | None:
        # R3i m8: 저장 열(Numeric(9, 6))과 같은 자리로 맞춰 비교·저장 — 소수 7자리 이상을 보내면 저장값(6자리)과 늘 달라 같은 본문
        # 재전송도 '바뀜'(새 발행 잡)이었다
        return Decimal(str(v)).quantize(COORD_STEP, rounding=ROUND_HALF_UP) if v is not None else None

    before_state = (bool(cat.location_confirmed), _num(cat.lat), _num(cat.lon), cat.expected_ym)
    cat.location_confirmed = confirmed
    if "lat" in body:
        cat.lat = _num(body["lat"])
    if "lon" in body:
        cat.lon = _num(body["lon"])
    if body.get("expected_ym"):
        if str(body["expected_ym"]) != cat.expected_ym:  # 같은 예정월이면 출처 행을 다시 만들지 않는다
            _human_expected_ym(session, cat, str(body["expected_ym"]))
    elif "expected_ym" in body and body["expected_ym"] is None and cat.expected_ym is not None:
        _human_expected_ym(session, cat, None)  # minor: null 로 지운다(사람이 확인한 예정월 취소)
    after_state = (bool(cat.location_confirmed), _num(cat.lat), _num(cat.lon), cat.expected_ym)
    links = {
        lk.complex_id: lk
        for lk in session.scalars(select(CatalystLink).where(CatalystLink.catalyst_id == cat.id))
    }
    before = set(links)
    target = set(want) if confirmed else set()
    for cid in before - target:
        session.delete(links.pop(cid))
    link_changed = False
    for cid in sorted(target):
        lk = links.get(cid)
        if lk is None:
            lk = CatalystLink(catalyst_id=cat.id, complex_id=cid)
            session.add(lk)
            links[cid] = lk
        new = (None, LINK_WEIGHT, "추정", want[cid][:120])
        if (lk.distance_m, lk.weight, lk.label, lk.reason) != new:
            link_changed = True
            lk.distance_m, lk.weight, lk.label, lk.reason = new
    session.flush()
    job_out: dict[str, Any] | None = None
    snap = _snapshot_for(session, region.id)
    changed = before != target or link_changed or before_state != after_state
    if changed:
        # 연결·위치·예정월은 점수·판정에 쓰지 않는다 — rejudge 대신 새 리비전 + snapshot.publish 잡(파생 행 복사 → 발행).
        # 발행은 worker 가 한다(D14-5 — 요청 안에서 저장본을 만들지 않는다, 계약 .11 202 + job_id). D16-4: 예정월·좌표만
        # 바뀌어도 발행 리비전 상세·시장 보드의 값이 바뀌므로 늘 발행 잡
        from app.scheduler.snapshots import republish

        job = republish(session, region.id, reason=f"호재 위치 확인: {cat.name}"[:200], created_at=now_iso())
        job_out = job_view(job) if job is not None else None
    session.commit()
    checked = (snap.asof_date if snap is not None else now_iso())[:10]
    fm = FactMaker(settings_of(request), ProvIndex().load(session, "catalyst", [cat.id]))
    view = catalyst_view(cat, checked, fm=fm, linked_ids=sorted(target))
    return JSONResponse(
        {
            "catalyst": view,
            "links": [_link_view(links[c]) for c in sorted(target)],
            "job": job_out,
            "job_id": job_out["id"] if job_out is not None else None,
        },
        # D16-4: 바뀐 것이 없으면 200 + job_id null. R3i m14: 바뀌었어도 발행할 리비전이 없으면(스냅샷 없는 지역) 잡이 없다 — 200
        status_code=202 if changed and job_out is not None else 200,
    )


def _human_expected_ym(session: Session, cat: Catalyst, ym: str | None) -> None:
    """사람이 확인한 예정월 → catalyst.expected_ym + 출처 행(사람 확인 — chosen, 이전 chosen 은 내린다). None 이면 지운다."""
    from app.models import FieldProvenance

    for fp in session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == "catalyst",
            FieldProvenance.entity_id == cat.id,
            FieldProvenance.field == "expected_ym",
            FieldProvenance.chosen.is_(True),
        )
    ):
        fp.chosen = False
    if ym is None:
        cat.expected_ym = None
        return
    session.add(
        FieldProvenance(
            entity="catalyst", entity_id=cat.id, field="expected_ym", value_text=ym, value_norm=ym,
            raw_document_id=None, url=cat.source_url, checked_at=now_iso(), label="확인됨",
            reason="사람 확인(위치 확인)", source_rank=0, chosen=True, excerpt=f"사람 확인: 예정 {ym}",
        )
    )  # fmt: skip
    cat.expected_ym = ym
