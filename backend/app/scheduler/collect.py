"""수집 → 정규화 저장 → 변경 감지 (RA §4-4 collect.daily·collect.weekly, §10 스케줄, T8).

``collect(ctx, region_id, sources)``:
1. 기준일 스냅샷(building)을 만든다(하루 1개).
2. 단계 순서: 청약홈(목록·상세·경쟁률) → 공고문 PDF(청약홈을 돌면 같은 잡에서) → 공식 홈페이지 → 실거래 → 통계 → 뉴스.
   **저장 순서(D18-4)**: 잔여·임의공급 공고의 청약홈 원문은 공고문 PDF 단계까지 미뤄 [청약홈 일반 공고] → [원 번호를
   인용한 공고문·일반 공고문] → [잔여 공고 청약홈 원문] → [그 밖의 잔여 공고문] 순서로 저장한다(실행 하나가 같은 연결
   ``links`` 를 넘긴다) — 원 단지를 아는 원문이 먼저 와서 잔여 공고가 자기 단지 행을 만들지 않는다. 그다음 원 공고가 없는
   단지(주택관리번호는 있는데 공고일이 없음 — 인용으로 만든 원 단지)의 원 공고를 번호로 다시 받아 저장한다
   (``ApplyhomeCollector.fetch_originals``).
   수집기(WP1)는 원문을 raw_document 로 남기고(실패도 행), 정규화가 필요한 원문(청약홈·공고문·공식 홈페이지)은
   ``normalize.store.store_raw_document`` (WP2)로 사실 테이블·출처·change_event 를 만든다(원문마다 SAVEPOINT).
   실거래·미분양은 수집기가 직접 적재하고(load=True), 입주물량은 공고문 입주월 합산(추정 집계)을 적재한다.
3. 접수 상태 행(intake_status): 공식 홈페이지 원문 → 실패면 '확인 불가(<상태>)', 성공이면 문구 분류 전이라
   '확인 불가(접수 문구 미분류)' — 가능/불가 판단은 판정기·사람 몫(AGENTS 규칙 3). 이전 스냅샷의 (단지, 경로)
   행 중 오늘 없는 것은 복사(사람 확인 행 포함, 확인 시각 유지). 미분류 행의 문구 해시가 직전 판정기 분류 행과
   같으면 그 분류를 복사한다(``intake.carry_classification``, D10-2 — 판정 호출 없음).
4. 데이터 조립(assemble.py, R3 F1a): 이번에 돈 단계에 따라 잔여 공고 이력·체크리스트(청약홈·공고문),
   벤치마크(실거래 = collect.weekly: 청약홈 과거 공고 + rtms 과거 월 → benchmark), 호재 후보(뉴스).
   조립 예외는 ``errors['assemble.<단계>']``.
5. 변경 감지(detect.py): 팝업 해시·목록 diff + 정규화 이벤트(새 공고·가격·계약금·중도금일 = critical).

수집기 예외는 다른 단계를 막지 않고 ``errors`` 에 남긴다(잡은 끝에 failed). 수집기의 실패 응답(403 등)은
예외가 아니라 원문 행이다.
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.stats.supply import SupplyInput, estimate_supply, load_supply, write_supply_provenance
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.logging import get_logger
from app.models import ChangeEvent, Complex, IntakeStatus, Region, Snapshot
from app.normalize.living_area import correct_dong
from app.normalize.notice_parser import notice_numbers
from app.normalize.store import is_remainder_url, store_raw_document
from app.scheduler import assemble, detect, snapshots
from app.scheduler.intake import UNCLASSIFIED, carry_classification, intake_change_events, pending_complexes
from app.scheduler.persist import copy_intake

if TYPE_CHECKING:
    from app.scheduler.context import SchedulerContext

__all__ = ["STEP_ORDER", "CollectResult", "collect", "intake_rows"]

log = get_logger("app.scheduler.collect")

STEP_ORDER: Final = ("applyhome", "notice_pdf", "official_site", "rtms", "stats", "news")
_SOURCE_TO_STEP: Final = {
    "applyhome_list": "applyhome",
    "applyhome_detail": "applyhome",
    "notice_pdf": "notice_pdf",
    "official_site": "official_site",
    "rtms": "rtms",
    "stats": "stats",
    "news": "news",
}
STORE_KINDS: Final = frozenset({"applyhome_list", "applyhome_detail", "notice_pdf", "official_site"})


@dataclass
class CollectResult:
    region_id: int
    snapshot_id: int
    asof_date: str
    documents: dict[str, int] = field(default_factory=dict)
    stored: int = 0
    store_errors: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    loaded: dict[str, dict[str, Any]] = field(default_factory=dict)
    change_event_ids: list[int] = field(default_factory=list)
    rejudge_complex_ids: list[int] = field(default_factory=list)
    list_complex_ids: list[int] | None = None
    intake_rows: int = 0
    intake_copied: int = 0
    intake_carried: list[int] = field(default_factory=list)
    intake_pending: list[int] = field(default_factory=list)
    assembled: dict[str, Any] = field(default_factory=dict)
    official_docs: list[RawDTO] = field(default_factory=list, repr=False)
    first_load_folded: int = 0  # 첫 적재 요약(D18-7): 이벤트 대신 센 빈 값 → 값 변경 수

    def stats(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "region_id": self.region_id,
            "snapshot_id": self.snapshot_id,
            "asof_date": self.asof_date,
            "documents": self.documents,
            "stored": self.stored,
            "store_errors": self.store_errors[:50],
            "errors": self.errors,
            "skipped": self.skipped,
            "loaded": self.loaded,
            "change_events": len(self.change_event_ids),
            "first_load_folded": self.first_load_folded,
            "rejudge_complex_ids": self.rejudge_complex_ids,
            "intake_rows": self.intake_rows,
            "intake_copied": self.intake_copied,
            "intake_classification_carried": len(self.intake_carried),
            "intake_pending_classify": self.intake_pending,
            "assembled": self.assembled,
        }
        if self.list_complex_ids is not None:
            out["list_complex_ids"] = self.list_complex_ids
        return out


def _steps(sources: Sequence[str]) -> list[str]:
    wanted = {_SOURCE_TO_STEP[s] for s in sources if s in _SOURCE_TO_STEP}
    unknown = [s for s in sources if s not in _SOURCE_TO_STEP]
    if unknown:
        raise ValueError(f"알 수 없는 source: {unknown}")
    if "applyhome" in wanted:
        wanted.add("notice_pdf")  # 새·바뀐 공고의 공고문까지 같은 잡에서(collect_daily.json)
    return [s for s in STEP_ORDER if s in wanted]


def _first_load_text(session: Session, region_id: int, folded: int) -> str:
    n = session.scalar(select(func.count()).select_from(Complex).where(Complex.region_id == region_id)) or 0
    return f"첫 적재: 단지 {n}개, 값 {folded}건(첫 적재 중 기록·덮어쓰기 — 변경 이벤트 대신 요약)"


_FIRST_LOAD_N_RE = re.compile(r"값 (\d+)건")


def _first_load_event(
    session: Session, region_id: int, snapshot_id: int, folded: int, detected_at: str
) -> ChangeEvent:
    """지역 첫 적재 요약 한 줄(D18-7·R4 m3: 첫날 G1 '최근 변경'이 빈 값 → 값 critical 326건으로 가득했다. D21-7·R4 재시험
    m-b: 같은 적재 안의 값 → 다른 값 덮어쓰기 92건도 요약에 센다). 같은 적재(지역·스냅샷)에 이미 요약이 있으면(bootstrap 의
    일일·주간 수집·판정 단계) 그 줄의 수에 더한다 — 첫 적재 요약은 한 줄이다(D22-4)."""
    ev = _first_load_summary(session, region_id, snapshot_id)
    if ev is not None:
        m = _FIRST_LOAD_N_RE.search(ev.new_text or "")
        ev.new_text = _first_load_text(session, region_id, (int(m.group(1)) if m else 0) + folded)
        session.flush()
        return ev
    ev = ChangeEvent(
        snapshot_id=snapshot_id,
        entity="region",
        entity_id=region_id,
        field="first_load",
        old_text=None,
        new_text=_first_load_text(session, region_id, folded),
        detected_at=detected_at,
        severity="info",
        triggers_rejudge=False,
        complex_id=None,
    )
    session.add(ev)
    session.flush()
    return ev


def _first_load_summary(session: Session, region_id: int, snapshot_id: int) -> ChangeEvent | None:
    """이 적재(같은 지역·같은 스냅샷 — bootstrap 의 일일·주간 수집과 판정)의 요약 줄."""
    return session.scalars(
        select(ChangeEvent)
        .where(
            ChangeEvent.entity == "region",
            ChangeEvent.entity_id == region_id,
            ChangeEvent.field == "first_load",
            ChangeEvent.snapshot_id == snapshot_id,
        )
        .order_by(ChangeEvent.id.desc())
    ).first()


def fold_into_first_load(
    session: Session, region_id: int, snapshot_id: int, events: Sequence[ChangeEvent], detected_at: str
) -> int:
    """D22-4(R4 3차 m-b): 첫 적재(bootstrap) 안의 **판정 단계** 값 변경(판정기 추출 적용·compare 채택 — 빈 값 → 값, 값 → 값)도
    change_event 로 남기지 않고 첫 적재 요약 수에 더한다. 이미 쓴 이벤트 행은 지운다(첫날 G1 이 critical 로 차지 않게 —
    수집 단계 ``store_raw_document(first_load=True)`` 와 같은 규칙). 지운 수를 돌려준다. commit 은 호출자."""
    seen: set[int] = set()
    rows: list[ChangeEvent] = []
    for e in events:
        if e.id is None or e.id in seen:
            continue
        seen.add(e.id)
        rows.append(e)
    if not rows:
        return 0
    for e in rows:
        session.delete(e)
    session.flush()
    _first_load_event(session, region_id, snapshot_id, len(rows), detected_at)
    return len(rows)


def _url_house_no(url: str) -> str | None:
    m = re.search(r"(?:houseManageNo=|HOUSE_MANAGE_NO%3A%3AEQ%5D=)(\d{10})", url)
    return m.group(1) if m else None


def _fetch_originals(
    ctx: SchedulerContext, region: RegionDTO, snapshot: SnapshotDTO, res: CollectResult
) -> list[RawDTO]:
    """D18-4: 주택관리번호는 있는데 공고일이 없는 단지(잔여 공고문이 인용해 만든 원 단지) → 원 공고를 번호로 다시 받는다.
    stats ``loaded.originals`` = {wanted, documents}. 수집기에 그 메서드가 없으면(가짜·웹 전용) 건너뛴다."""
    with ctx.session_factory() as session:
        wanted = sorted(
            str(h)
            for h in session.scalars(
                select(Complex.applyhome_id).where(
                    Complex.region_id == region.id,
                    Complex.applyhome_id.is_not(None),
                    Complex.notice_date.is_(None),
                )
            )
        )
    res.loaded["originals"] = {"wanted": len(wanted), "documents": 0}
    factory = ctx.collectors.get("applyhome")
    if not wanted or factory is None:
        return []
    try:
        collector = factory(ctx)
        fetch = getattr(collector, "fetch_originals", None)
        if not callable(fetch):
            res.loaded["originals"]["skipped"] = "수집기에 원 공고 조회 없음"
            return []
        got = list(fetch(region, snapshot, wanted))
    except Exception as exc:  # 수집 오류는 다른 단계를 막지 않는다
        res.errors["applyhome_originals"] = assemble.safe_error(exc)
        log.exception("worker.collect.error", extra={"step": "applyhome_originals", "region_id": region.id})
        return []
    res.loaded["originals"]["documents"] = len(got)
    return got


def _load_stats(obj: Any) -> dict[str, int] | None:
    if obj is None:
        return None
    keys = ("inserted", "updated", "unchanged")
    return {k: int(getattr(obj, k, 0) or 0) for k in keys if hasattr(obj, k)}


def intake_rows(
    session: Session,
    snapshot_id: int,
    docs: Sequence[RawDTO],
    phrases: Mapping[int, Sequence[str]] | None = None,
) -> int:
    """공식 홈페이지 원문 → intake_status 행(단지·경로마다 1개, 이미 있으면 만들지 않음). 분류는 하지 않는다.

    ``phrases``: 단지별 접수 문구 후보(normalize official_site 파서의 intake_status 후보, 분류 전) → note 에 원문 그대로.
    """
    by_complex: dict[int, list[RawDTO]] = defaultdict(list)
    for d in docs:
        if d.source_kind == "official_site" and d.complex_id is not None:
            by_complex[d.complex_id].append(d)
    have = {
        (c, p)
        for c, p in session.execute(
            select(IntakeStatus.complex_id, IntakeStatus.path).where(IntakeStatus.snapshot_id == snapshot_id)
        )
    }
    n = 0
    for cid, ds in sorted(by_complex.items()):
        ok = [d for d in ds if d.http_status == 200 and not d.error_text and d.path]
        shot = next((d for d in ok if (d.content_type or "").startswith("image/")), None)
        if ok:
            main = shot or ok[0]
            path = "headless_shot" if shot is not None else "official_popup"
            reason, http = UNCLASSIFIED, main.http_status
        else:
            main = ds[0]
            path = "official_popup"
            http = main.http_status
            reason = (
                str(main.http_status) if main.http_status is not None else (main.error_text or "수집 실패")
            )
        if (cid, path) in have or session.get(Complex, cid) is None:
            continue
        session.add(
            IntakeStatus(
                complex_id=cid,
                snapshot_id=snapshot_id,
                status="확인 불가",
                path=path,
                evidence_url=main.url,
                screenshot_path=shot.path if shot is not None else None,
                raw_document_id=main.id,
                http_status=http,
                checked_at=main.fetched_at,
                reason=reason[:120],
                note=("문구 후보: " + " / ".join(dict.fromkeys((phrases or {}).get(cid, []))))[:500]
                if (phrases or {}).get(cid)
                else None,
                entered_by=None,
            )
        )
        n += 1
    session.flush()
    return n


def _last_list_ids(session: Session, region_id: int, before_snapshot: Snapshot) -> list[int] | None:
    """직전 collect.daily(다른 기준일)가 남긴 목록 단지 집합."""
    from app.models import JobRun

    for job in session.scalars(
        select(JobRun)
        .where(JobRun.job_name.in_(("collect.daily", "region.bootstrap")), JobRun.status == "done")
        .order_by(JobRun.id.desc())
    ):
        st = job.stats or {}
        if (job.payload or {}).get("region_id") != region_id:
            continue
        if st.get("asof_date") == before_snapshot.asof_date or "list_complex_ids" not in st:
            continue
        ids = st.get("list_complex_ids")
        return [int(i) for i in ids] if isinstance(ids, list) else None
    return None


def _supply(session: Session, region_id: int) -> dict[str, int]:
    """입주물량 추정 입력 — 강등 오버레이(D11-3·D12-2)를 적용한 입주월·세대수(R3 4차 minor: 원본 값으로 셌다)."""
    from app.analysis.complex_input import masked
    from app.facts_view import load_overlay

    rows = list(session.scalars(select(Complex).where(Complex.region_id == region_id).order_by(Complex.id)))
    ov = load_overlay(session, complex_ids=[c.id for c in rows])
    views = [masked(c, ov.fields("complex", c.id)) for c in rows]
    inputs = [
        SupplyInput(complex_id=c.id, living_area=c.living_area, move_in_ym=c.move_in_ym, units=c.units_total)
        for c in views
        if c.inclusion_class not in ("범위 경계",)
    ]
    stats = load_supply(session, region_id, estimate_supply(inputs))
    return {
        "inserted": stats.inserted,
        "updated": stats.updated + stats.deleted,  # 지운 행도 시장 자료 변경(change_event)
        "unchanged": stats.unchanged,
        "deleted": stats.deleted,
    }


def _market_event(
    session: Session, snapshot_id: int, entity: str, loaded: dict[str, int], detected_at: str
) -> ChangeEvent | None:
    ins, upd = loaded.get("inserted", 0), loaded.get("updated", 0)
    if ins + upd == 0:
        return None
    ev = ChangeEvent(
        snapshot_id=snapshot_id,
        entity=entity,
        entity_id=None,
        field="rows",
        old_text=None,
        new_text=f"추가 {ins}건, 갱신 {upd}건",
        detected_at=detected_at,
        severity="notice",
        triggers_rejudge=False,
        complex_id=None,
    )
    session.add(ev)
    session.flush()
    return ev


def collect(
    ctx: SchedulerContext,
    region_id: int,
    sources: Sequence[str],
    *,
    asof_date: str | None = None,
    since: str | None = None,
    detect_list: bool = True,
) -> CollectResult:
    steps = _steps(sources)
    asof = asof_date or ctx.today().isoformat()
    with ctx.session_factory() as session:
        region = session.get(Region, region_id)
        if region is None:
            raise LookupError(f"region {region_id} 없음")
        snap = snapshots.get_or_create(session, region_id, asof, created_at=ctx.iso_now())
        session.commit()
        region_dto = snapshots.region_dto(region)
        # D18-7·R4 m3: 지역 첫 적재(bootstrap 이 status 를 'bootstrapping' 으로 둔 동안) — 빈 값 → 값 변경은 이벤트 대신 요약
        first_load = region.status == "bootstrapping"
        snap_dto = snapshots.snapshot_dto(snap)
        res = CollectResult(region_id=region_id, snapshot_id=snap.id, asof_date=asof)
    detected_at = ctx.iso_now()
    events: list[ChangeEvent] = []
    list_ids: set[int] = set()
    phrases: dict[int, list[str]] = defaultdict(list)
    ran_applyhome = False
    ran: list[str] = []
    step_docs: dict[str, list[RawDTO]] = {}
    links: dict[str, int] = {}  # D18-4: 잔여 공고 번호 → 원 단지(이 실행의 모든 원문이 같이 쓴다)
    alt_addresses: dict[
        int, list[str]
    ] = {}  # D22-3: 원 단지 → 묶인 잔여 공고의 공급위치(실행 끝 법정동 보정)
    deferred: list[RawDTO] = []  # D18-4: 공고문 단계 뒤로 미룬 잔여 공고 청약홈 원문

    def store_docs(docs: Sequence[RawDTO]) -> None:
        with ctx.session_factory() as session:
            for doc in docs:
                if doc.source_kind not in STORE_KINDS:
                    continue
                try:
                    out = store_raw_document(
                        session, doc, snapshot_id=snap_dto.id, links=links, first_load=first_load
                    )
                except Exception as exc:  # 원문 1건 실패(SAVEPOINT 롤백) — 기록하고 다음 원문
                    res.store_errors.append(f"rd{doc.id}:{assemble.safe_error(exc)[:160]}")
                    continue
                res.stored += 1
                res.first_load_folded += out.first_load_folded
                for cid, addrs in out.alt_addresses.items():
                    have = alt_addresses.setdefault(cid, [])
                    have.extend(a for a in addrs if a not in have)
                events.extend(out.change_events)
                if doc.complex_id is not None:
                    phrases[doc.complex_id].extend(
                        str(c.value_text)
                        for c in out.candidates
                        if c.entity == "intake_status" and c.value_text
                    )
                if doc.source_kind == "applyhome_list":
                    list_ids.update(out.complex_ids)
            session.commit()

    def flush_deferred() -> None:
        """미룬 잔여 공고 원문 저장 + 원 공고 다시 받기(D18-4)."""
        nonlocal deferred
        if deferred:
            store_docs(deferred)
            deferred = []
        if ran_applyhome:
            got = _fetch_originals(ctx, region_dto, snap_dto, res)
            if got:
                step_docs.setdefault("applyhome", []).extend(got)
                store_docs(got)

    for step in steps:
        if (deferred or (ran_applyhome and "originals" not in res.loaded)) and STEP_ORDER.index(
            step
        ) > STEP_ORDER.index("notice_pdf"):
            flush_deferred()  # 공고문 단계가 없거나 실패했다 — 다음 단계(공식 홈페이지 등) 전에
        factory = ctx.collectors.get(step)
        if factory is None:
            res.skipped[step] = "수집기 없음"
            continue
        try:
            collector = factory(ctx)
            if getattr(collector, "enabled", True) is False:
                res.skipped[step] = str(getattr(collector, "disabled_reason", None) or "비활성")
                continue
            docs = collector.fetch(region_dto, snap_dto, since)
        except Exception as exc:  # 수집기 버그·환경 오류: 다른 단계는 계속, 잡은 failed
            res.errors[step] = assemble.safe_error(exc)
            log.exception("worker.collect.error", extra={"step": step, "region_id": region_id})
            continue
        res.documents[step] = len(docs)
        ran.append(step)
        step_docs[step] = list(docs)
        ran_applyhome = ran_applyhome or step == "applyhome"
        if step == "official_site":
            res.official_docs = list(docs)
        if step == "applyhome" and "notice_pdf" in steps:
            deferred = [d for d in docs if is_remainder_url(d.url)]
            store_docs([d for d in docs if not is_remainder_url(d.url)])
        elif step == "notice_pdf":
            remnant_nos = {_url_house_no(d.url) for d in deferred} - {None}
            pdf_first: list[RawDTO] = []
            pdf_last: list[RawDTO] = []
            for d in docs:
                own, cited = notice_numbers(d) if d.http_status == 200 else (_url_house_no(d.url) or "", None)
                (pdf_last if own in remnant_nos and cited is None else pdf_first).append(d)
            store_docs(pdf_first)
            flush_deferred()
            store_docs(pdf_last)
        else:
            store_docs(docs)
        with ctx.session_factory() as session:
            if step == "rtms":
                loaded = _load_stats(getattr(collector, "load_stats", None))
                if loaded is not None:
                    res.loaded["rtms"] = loaded
                    # D18-3: 법정동 매칭률(umdCd 없는 실제 응답 → 참조 표 매칭)
                    legal = getattr(getattr(collector, "load_stats", None), "legal_dong_stats", None)
                    if callable(legal):
                        res.loaded["rtms_legal_dong"] = legal()
                    ev = _market_event(session, snap_dto.id, "rtms_trade", loaded, detected_at)
                    if ev is not None:
                        events.append(ev)
            if step == "stats":
                last = getattr(collector, "last", None)
                loaded = _load_stats(getattr(last, "load", None))
                if loaded is not None:
                    res.loaded["unsold"] = loaded
                    ev = _market_event(session, snap_dto.id, "unsold", loaded, detected_at)
                    if ev is not None:
                        events.append(ev)
                res.loaded["supply"] = _supply(session, region_id)
                res.loaded["supply_provenance"] = write_supply_provenance(session, region_id).stats()
                ev = _market_event(session, snap_dto.id, "supply", res.loaded["supply"], detected_at)
                if ev is not None:
                    events.append(ev)
            session.commit()

    if deferred or (ran_applyhome and "originals" not in res.loaded):
        flush_deferred()
    asm = assemble.assemble(
        ctx, region_dto, snap_dto, steps=ran, docs=step_docs, detected_at=detected_at, links=links,
        first_load=first_load,
    )  # fmt: skip
    res.first_load_folded += int((asm.stats.get("remaining") or {}).get("first_load_folded") or 0)
    res.assembled = asm.stats
    res.errors.update(asm.errors)
    events.extend(asm.events)
    if alt_addresses:
        # D22-3(R4 3차 N10): 잔여 공고문이 원 단지보다 먼저 저장돼(원 공고 다시 받기 전 — 주소 없음) 쓰지 못한 공급위치로, 원 단지
        # 주소가 생긴 지금 법정동을 보정한다 — 저장 순서와 무관하게 첫 수집 안에서. 바뀌면 change_event(첫 적재면 요약 수)
        with ctx.session_factory() as session:
            for cid, addrs in sorted(alt_addresses.items()):
                cx = session.get(Complex, cid)
                if cx is None:
                    continue
                ev = correct_dong(session, cx, addrs, snapshot_id=snap_dto.id, detected_at=detected_at)
                if ev is None:
                    continue
                if first_load:
                    res.first_load_folded += 1
                else:
                    session.add(ev)
                    session.flush()
                    events.append(ev)
            session.commit()

    with ctx.session_factory() as session:
        snap_row = session.get(Snapshot, snap_dto.id)
        assert snap_row is not None
        if first_load and res.first_load_folded:
            events.append(
                _first_load_event(session, region_id, snap_dto.id, res.first_load_folded, detected_at)
            )
        res.intake_rows = intake_rows(session, snap_dto.id, res.official_docs, phrases)
        prev = snapshots.previous(session, snap_row)
        if prev is not None:
            res.intake_copied = copy_intake(session, prev.id, snap_dto.id)
        # D10-2: 문구 해시가 직전 분류 행과 같으면 분류 복사(판정 호출 없음) — 변경 없는 날 범위·순위 불변
        res.intake_carried = carry_classification(session, snap_dto.id)
        # D9-3: 분류 없이 표시 접수가 바뀐 단지(공식 홈페이지 403·수집 실패 → '확인 불가', 경로 바뀜 등)도 이벤트 +
        # 재판정(R3 3차 minor 4). 미분류 행이 남은 단지는 판정기 분류 뒤 파이프라인이 같은 함수로 본다
        waiting = set(pending_complexes(session, snap_dto.id))
        shown = set(
            session.scalars(select(IntakeStatus.complex_id).where(IntakeStatus.snapshot_id == snap_dto.id))
        )
        events.extend(
            intake_change_events(session, snap_row, prev, sorted(shown - waiting), detected_at=detected_at)
        )
        events.extend(
            detect.popup_changes(
                session, res.official_docs, asof_date=asof, snapshot_id=snap_dto.id, detected_at=detected_at
            )
        )
        if ran_applyhome:
            res.list_complex_ids = sorted(list_ids)
            if detect_list:
                events.extend(
                    detect.list_changes(
                        session,
                        today_ids=list_ids,
                        previous_ids=_last_list_ids(session, region_id, snap_row),
                        snapshot_id=snap_dto.id,
                        detected_at=detected_at,
                    )
                )
        session.commit()
        ids = {e.id for e in events if e.id is not None}
        res.change_event_ids = sorted(ids)
        rows = (
            list(session.scalars(select(ChangeEvent).where(ChangeEvent.id.in_(sorted(ids))))) if ids else []
        )
        # 분류 복사 뒤에도 미분류인 접수 행(문구 변경·처음 본 문구)의 단지는 재판정(P4 접수 classify) 대상 — 미분류인 채
        # 이전 판정 복사·publish 를 하지 않는다(N-C2)
        res.intake_pending = pending_complexes(session, snap_dto.id)
        res.rejudge_complex_ids = sorted(set(detect.rejudge_targets(rows)) | set(res.intake_pending))
    log.info(
        "worker.collect.done",
        extra={"region_id": region_id, "snapshot_id": res.snapshot_id, "events": len(res.change_event_ids)},
    )
    return res
