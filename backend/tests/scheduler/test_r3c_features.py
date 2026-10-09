"""R3c CORE — 스케줄러 쪽 D11 결정 기능 (계약 2026-10-09.8).

| 결정·리뷰 | 테스트 |
| --- | --- |
| M-10 · D11-2 | '호재 아님' 판정은 catalyst·연결·출처를 지우지 않는다. 뉴스 후보는 stage '호재 아님', 사람이 넣은 호재는 단계 유지 + 판정 병기 |
| D11-7 | region.expand 잡: 새 기준일 스냅샷(바탕 = 이전 발행) → 전체 판정 → publish, 보고서 비교 기준 = 바탕(§12 지역 추가 장) |
| D11-8 | backup 잡: SQLite 백업 파일 + 원문 증분 복사(두 번째는 건너뜀), 매일 03:00 시간표 |
| minor 6 | 파이프라인 사실 라벨: 값이 있는데 출처 행이 없으면 '확인 불가'(null 이면 점수 라벨 합성이 '확인됨'으로 본다) |
| minor 3 | 접수 분류 복사는 같은 판정기 버전의 분류만, 버전이 바뀐 재판정은 옛 버전 분류를 미분류로 되돌린다 |
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Catalyst, CatalystLink, FieldProvenance, JobRun, RawDocument, Snapshot
from app.scheduler.context import SchedulerContext
from app.scheduler.handlers import HANDLERS
from app.scheduler.pipeline import run_pipeline

from .conftest import SynthJev


class NotCatalystJev(SynthJev):
    """호재 단계 classify 에서 '호재 아님'을 auto 로 내는 가짜 판정기(그 밖은 SynthJev 그대로)."""

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        ids = [c["id"] for c in a["classes"]]
        if "호재 아님" not in ids:
            return super()._classify(a)
        return {
            "results": [
                {"id": it["id"], "classification": "호재 아님", "probabilities": {"호재 아님": 0.97},
                 "top_probability": 0.97, "confidence": 0.95, "decision": "auto"}
                for it in a["items"]
            ]
        }  # fmt: skip


@pytest.fixture
def jev() -> SynthJev:
    return NotCatalystJev()


def test_m10_not_catalyst_keeps_rows_links_and_human_entries(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    with factory() as s:
        raw = RawDocument(
            source_kind="news", url="https://news.example.org/a/1", fetched_at="2026-10-07T06:00:00+09:00",
            http_status=200, sha256="ab" * 32, region_id=1,
        )  # fmt: skip
        s.add(raw)
        s.flush()
        news = Catalyst(region_id=1, name="○○ 다음 주 1순위 청약", kind="기타", stage="미확정",
                        raw_document_id=raw.id, source_url="https://news.example.org/a/1")  # fmt: skip
        human = Catalyst(region_id=1, name="사람이 넣은 역 신설", kind="교통", stage="계획",
                         source_url="https://www.example.go.kr/notice/1", location_confirmed=True)  # fmt: skip
        s.add_all([news, human])
        s.flush()
        s.add(CatalystLink(catalyst_id=human.id, complex_id=1, weight=1, label="추정", reason="사람 지정"))
        s.add(
            FieldProvenance(
                entity="catalyst", entity_id=news.id, field="name", value_text=news.name, raw_document_id=raw.id,
                url=raw.url, checked_at="2026-10-07", label="비공식", source_rank=2, chosen=True, excerpt=news.name,
            )
        )  # fmt: skip
        s.commit()
        news_id, human_id = news.id, human.id
    out = run_pipeline(make_ctx(), seeded)
    assert not out.degraded, out.error
    with factory() as s:
        n = s.get(Catalyst, news_id)
        h = s.get(Catalyst, human_id)
        assert n is not None and n.stage == "호재 아님" and n.decision == "auto", (
            "뉴스 후보는 지우지 않고 '호재 아님'(D11-2)"
        )
        assert s.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "catalyst", FieldProvenance.entity_id == news_id
            )
        ).first()
        assert h is not None and h.stage == "계획", "사람이 넣은 호재는 단계를 바꾸지 않는다"
        assert "판정기: 호재 아님" in (h.note or ""), "판정 결과는 병기"
        assert s.scalars(select(CatalystLink).where(CatalystLink.catalyst_id == human_id)).first() is not None
    kept = {d["catalyst_id"] for d in out.catalysts_discarded}
    assert {news_id, human_id} <= kept and all(d["kept"] for d in out.catalysts_discarded)


def test_d11_7_region_expand_job_runs_new_snapshot_and_report_compares_base(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, tmp_path: Path
) -> None:
    from app.scheduler import snapshots

    ctx = make_ctx()
    assert not run_pipeline(ctx, seeded).degraded
    with factory() as s:
        ok, _ = snapshots.publish(s, seeded, now="2026-10-07T08:00:00+09:00")
        s.commit()
        assert ok
        job = JobRun(
            job_name="region.expand", kind="manual", status="running", scheduled_at="2026-10-08T06:00:00+09:00",
            stats={}, payload={"region_id": 1, "added": [{"kind": "sigungu", "code": "41570", "full_name": "경기도 김포시"}],
                               "removed": [], "change_event_id": None},
        )  # fmt: skip
        s.add(job)
        s.commit()
        s.refresh(job)
    stats = HANDLERS["region.expand"](ctx, job)
    assert stats["published"] is True, stats
    with factory() as s:
        snap = s.get(Snapshot, stats["snapshot_id"])
        assert snap is not None and snap.asof_date == "2026-10-08" and snap.status == "published"
        assert snap.revision_of == seeded and (snap.revision_reason or "").startswith("지역 확장")
    from app.reports.export import default_compare

    with factory() as s:
        assert default_compare(s, stats["snapshot_id"]) == seeded, (
            "보고서 비교 기준 = 바탕(§12 지역 추가 장·리비전 diff)"
        )
        assert default_compare(s, seeded) is None


def test_d6_server_version_change_event_and_full_rejudge_in_new_revision(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """D6: 판정기 서버 버전이 바뀌면 change_event(judge·version·critical) + 전체 재판정 잡. 그 재판정은 발행 스냅샷이 아니라
    같은 기준일 새 리비전에 쓰인다(D11-1) — 리비전 diff 가 RA §10 '판정기 버전 변경 → 이전 run 과 delta 표'."""
    from app.models import ChangeEvent
    from app.scheduler import snapshots
    from app.scheduler.rejudge import handle_rejudge

    assert not run_pipeline(make_ctx(), seeded).degraded
    with factory() as s:
        assert snapshots.publish(s, seeded, now="2026-10-07T08:00:00+09:00")[0]
        s.commit()
    jev.version = "0.15.0"  # 서버 업데이트(npx …@latest) — 같은 입력도 input_hash 가 바뀐다
    jev.calls.clear()
    ctx = make_ctx()
    out = run_pipeline(ctx, seeded)
    assert not out.degraded and out.version_event_id is not None
    assert jev.calls, "새 버전은 캐시가 없다 — 판정기에 실제로 간다"
    with factory() as s:
        ev = s.get(ChangeEvent, out.version_event_id)
        assert ev is not None and (ev.entity, ev.field, ev.severity, ev.triggers_rejudge) == (
            "judge",
            "version",
            "critical",
            True,
        )
        assert "0.14.1" in (ev.old_text or "") and "0.15.0" in (ev.new_text or "")
        job = s.scalars(select(JobRun).where(JobRun.job_name == "rejudge").order_by(JobRun.id.desc())).first()
        assert job is not None and job.payload["complex_ids"] is None, "전체 재판정 1회"
        first_rev = s.get(Snapshot, out.snapshot_id)
        assert first_rev is not None and first_rev.revision_of == seeded, "발행 스냅샷 재판정은 새 리비전"
    stats = handle_rejudge(ctx, job)
    assert stats["snapshot_id"] == out.snapshot_id, "아직 발행 전인 리비전은 그 자리에서 이어서"


def test_d11_8_backup_job_copies_db_and_raw_incrementally(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    seeded: int,
    test_settings: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dest = tmp_path / "backup"
    monkeypatch.setenv("BACKUP_DIR", str(dest))
    raw = Path(test_settings.raw_dir)
    (raw / "news" / "2026-10-08").mkdir(parents=True, exist_ok=True)
    (raw / "news" / "2026-10-08" / "a.json").write_text("{}", encoding="utf-8")
    ctx = make_ctx()
    with factory() as s:
        job = JobRun(job_name="backup", kind="scheduled", status="running", scheduled_at="2026-10-08T03:00:00+09:00",
                     stats={}, payload={})  # fmt: skip
        s.add(job)
        s.commit()
        s.refresh(job)
    first = HANDLERS["backup"](ctx, job)
    assert (
        first["db"]["kind"] == "sqlite" and first["db"]["size_bytes"] > 0 and len(first["db"]["sha256"]) == 64
    )
    assert (dest / "2026-10-08" / "db.sqlite3").is_file()
    assert first["raw"]["copied"] >= 1 and (dest / "raw" / "news" / "2026-10-08" / "a.json").is_file()
    second = HANDLERS["backup"](ctx, job)
    assert second["raw"]["copied"] == 0 and second["raw"]["skipped"] == first["raw"]["files"], (
        "증분 — 같은 파일은 건너뛴다"
    )


def test_d11_8_backup_is_scheduled_daily_at_03(make_ctx: Callable[..., SchedulerContext]) -> None:
    from app.scheduler.jobs import CRON, JOB_NAMES, build_scheduler

    assert CRON["backup"] == {"hour": 3, "minute": 0}
    assert "backup" in JOB_NAMES and "region.expand" in JOB_NAMES
    sched = build_scheduler(make_ctx())
    assert sched.get_job("backup") is not None


def test_d11_8_backup_failure_is_a_failed_job_with_stats(
    make_ctx: Callable[..., SchedulerContext],
    test_settings: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.scheduler.backup import run_backup
    from app.scheduler.jobs import JobError

    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "b"))
    bad = test_settings.model_copy(update={"database_url": "mysql://x/y"})
    with pytest.raises(RuntimeError, match="DB 백업 실패") as err:
        from datetime import datetime

        run_backup(bad, now=datetime(2026, 10, 8, 3, 0))
    assert err.value.stats["db"]["error"]  # type: ignore[attr-defined]
    assert issubclass(JobError, RuntimeError)


def test_minor3_intake_carry_respects_adapter_version(factory: sessionmaker[Session], seeded: int) -> None:
    from app.models import IntakeStatus, JudgmentLog
    from app.scheduler.intake import (
        CLASSIFIED_MARK,
        UNCLASSIFIED,
        carry_classification,
        classified_version,
        reset_stale_classification,
    )

    with factory() as s:
        base = s.get(Snapshot, seeded)
        assert base is not None
        log = JudgmentLog(tool="classify", purpose="p4:intake", input_hash="sha256:" + "a" * 64, input_len=1,
                          input_json={}, output_json={}, status="ok", adapter_version="v1",
                          created_at="2026-10-07T06:00:00+09:00")  # fmt: skip
        s.add(log)
        later = Snapshot(region_id=base.region_id, asof_date="2026-10-08", status="building",
                         created_at="2026-10-08T06:00:00+09:00")  # fmt: skip
        s.add(later)
        s.flush()
        cid = 1
        prev = IntakeStatus(complex_id=cid, snapshot_id=seeded, status="가능", path="official_popup",
                            checked_at="2026-10-07T06:00:00+09:00", reason="접수 중",
                            note=f"{CLASSIFIED_MARK} jl_{log.seq}")  # fmt: skip
        row = IntakeStatus(complex_id=cid, snapshot_id=later.id, status="확인 불가", path="official_popup",
                           checked_at="2026-10-08T06:00:00+09:00", reason=UNCLASSIFIED)  # fmt: skip
        s.add_all([prev, row])
        s.flush()
        assert classified_version(s, prev) == "v1"
        # 판정기 v2 로 바뀐 뒤: v1 분류는 복사하지 않는다 → 미분류로 남아 판정기가 다시 분류
        assert carry_classification(s, later.id, adapter_version="v2") == []
        assert row.reason == UNCLASSIFIED
        # 같은 버전이면 복사(D10-2 — 판정 호출 없음)
        assert carry_classification(s, later.id, adapter_version="v1") == [row.id]
        assert (row.status, row.reason) == ("가능", "접수 중") and classified_version(s, row) == "v1"
        # 버전이 바뀐 전체 재판정: 복사된 v1 분류를 미분류로 되돌린다(표식도 지운다)
        assert reset_stale_classification(s, later.id, "v2") == [row.id]
        assert row.reason == UNCLASSIFIED and CLASSIFIED_MARK not in (row.note or "")
        assert reset_stale_classification(s, later.id, "v1") == []  # 이미 미분류
        s.rollback()


def test_minor6_value_without_provenance_is_unknown_label_not_confirmed(
    factory: sessionmaker[Session], seeded: int
) -> None:
    from sqlalchemy import delete

    from app.models import Complex, Region
    from app.scheduler.inputs import load_facts

    with factory() as s:
        cx = s.get(Complex, 7)
        assert cx is not None and cx.resale_months is not None
        s.execute(
            delete(FieldProvenance).where(
                FieldProvenance.entity == "complex", FieldProvenance.entity_id == 7,
                FieldProvenance.field == "resale_months",
            )
        )  # fmt: skip
        s.flush()
        snap, region = s.get(Snapshot, seeded), s.get(Region, 1)
        assert snap is not None and region is not None
        f7 = next(f for f in load_facts(s, snap, region) if f.complex_id == 7)
        assert f7.labels["resale"] == "확인 불가"
        assert f7.labels["residency"] is not None  # 출처 행이 있는 값은 그 라벨
        s.rollback()
