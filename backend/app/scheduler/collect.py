"""수집 → 정규화 저장 → 변경 감지 (RA §4-4 collect.daily·collect.weekly, §10 스케줄, T8).

``collect(ctx, region_id, sources)``:
1. 기준일 스냅샷(building)을 만든다(하루 1개).
2. 단계 순서: 청약홈(목록·상세·경쟁률) → 공고문 PDF(청약홈을 돌면 같은 잡에서) → 공식 홈페이지 → 실거래 → 통계 → 뉴스.
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

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.stats.supply import SupplyInput, estimate_supply, load_supply, write_supply_provenance
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.logging import get_logger
from app.models import ChangeEvent, Complex, IntakeStatus, Region, Snapshot
from app.normalize.store import store_raw_document
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
    loaded: dict[str, dict[str, int]] = field(default_factory=dict)
    change_event_ids: list[int] = field(default_factory=list)
    rejudge_complex_ids: list[int] = field(default_factory=list)
    list_complex_ids: list[int] | None = None
    intake_rows: int = 0
    intake_copied: int = 0
    intake_carried: list[int] = field(default_factory=list)
    intake_pending: list[int] = field(default_factory=list)
    assembled: dict[str, Any] = field(default_factory=dict)
    official_docs: list[RawDTO] = field(default_factory=list, repr=False)

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
        snap_dto = snapshots.snapshot_dto(snap)
        res = CollectResult(region_id=region_id, snapshot_id=snap.id, asof_date=asof)
    detected_at = ctx.iso_now()
    events: list[ChangeEvent] = []
    list_ids: set[int] = set()
    phrases: dict[int, list[str]] = defaultdict(list)
    ran_applyhome = False
    ran: list[str] = []
    step_docs: dict[str, list[RawDTO]] = {}

    for step in steps:
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
        with ctx.session_factory() as session:
            for doc in docs:
                if doc.source_kind not in STORE_KINDS:
                    continue
                try:
                    out = store_raw_document(session, doc, snapshot_id=snap_dto.id)
                except Exception as exc:  # 원문 1건 실패(SAVEPOINT 롤백) — 기록하고 다음 원문
                    res.store_errors.append(f"rd{doc.id}:{assemble.safe_error(exc)[:160]}")
                    continue
                res.stored += 1
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
            if step == "rtms":
                loaded = _load_stats(getattr(collector, "load_stats", None))
                if loaded is not None:
                    res.loaded["rtms"] = loaded
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

    asm = assemble.assemble(ctx, region_dto, snap_dto, steps=ran, docs=step_docs, detected_at=detected_at)
    res.assembled = asm.stats
    res.errors.update(asm.errors)
    events.extend(asm.events)

    with ctx.session_factory() as session:
        snap_row = session.get(Snapshot, snap_dto.id)
        assert snap_row is not None
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
