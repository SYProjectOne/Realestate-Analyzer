"""R3d CORE2 — 스케줄러 쪽 4차 리뷰 재현 (`docs/design/wp/R3_REVIEW4.md`, 계약 2026-10-09.9, DECISIONS D12).

실제 파이프라인(``run_pipeline``)·잡 처리 함수(``HANDLERS``)·가짜 판정기 전송(``SynthJev`` — guard·캐시·judgment_log 실경로)만 쓴다.

| 리뷰 | 테스트 |
| --- | --- |
| M-4 | 지역 선택에서 뺀 단지 → '범위 경계'(판정 범위 제외) — 사다리(noul) 호출 없음, §12 '제외'에 잡힌다 |
| M-5 | 오늘 리비전 1 이 미발행(building)일 때 지역 확장 → 비교 기준(직전 발행) → §12 장 |
| M-6 | 판정기 버전 변경이 미발행 리비전 1 에서 감지 → 비교 기준(직전 발행) → delta 표 |
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Complex, JobRun, Ladder, Region, ScoreRun, ScoreTotal, Snapshot
from app.scheduler import snapshots
from app.scheduler.context import SchedulerContext
from app.scheduler.handlers import HANDLERS
from app.scheduler.pipeline import run_pipeline

from .conftest import SynthJev


def _publish(factory: sessionmaker[Session], sid: int) -> None:
    with factory() as s:
        ok, n = snapshots.publish(s, sid, now="2026-10-07T08:00:00+09:00")
        s.commit()
        assert ok, n


def _expand_job(factory: sessionmaker[Session], **payload: object) -> JobRun:
    with factory() as s:
        job = JobRun(job_name="region.expand", kind="manual", status="running", scheduled_at="2026-10-08T06:00:00+09:00",
                     stats={}, payload={"region_id": 1, "added": [], "removed": [], "change_event_id": None, **payload})  # fmt: skip
        s.add(job)
        s.commit()
        s.refresh(job)
        return job


def test_m4_complex_removed_from_region_selection_is_excluded_not_judged(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    ctx = make_ctx()
    assert not run_pipeline(ctx, seeded).degraded
    _publish(factory, seeded)
    with factory() as s:
        judged = s.scalars(
            select(ScoreTotal.complex_id)
            .join(ScoreRun, ScoreRun.id == ScoreTotal.score_run_id)
            .where(ScoreRun.snapshot_id == seeded, ScoreTotal.judge_scope == "판정 대상")
        ).first()
        assert judged is not None
        cx = s.get(Complex, judged)
        assert cx is not None and cx.legal_dong_code and cx.inclusion_class != "범위 경계"
        region = s.get(Region, cx.region_id)
        assert region is not None
        gone = cx.legal_dong_code
        # 지역 선택에서 그 단지의 법정동을 뺀다(PATCH /regions 가 하는 재계산과 같은 결과)
        region.legal_dong_codes = [c for c in region.legal_dong_codes or [] if c != gone]
        areas = [
            {**a, "legal_dong_codes": [c for c in a.get("legal_dong_codes") or [] if c != gone]}
            for a in region.living_areas or []
        ]
        region.living_areas = [a for a in areas if a["legal_dong_codes"]]  # 빈 생활권은 지운다(PATCH 규칙)
        name = cx.name
        s.commit()
    jev.calls.clear()
    job = _expand_job(factory, removed=[{"kind": "legal_dong", "code": gone, "full_name": "뺀 법정동"}])
    stats = HANDLERS["region.expand"](ctx, job)
    assert stats["published"] is True, stats
    with factory() as s:
        cx = s.get(Complex, judged)
        assert cx is not None and cx.inclusion_class == "범위 경계", (
            "지역 밖이 된 단지는 분류와 무관하게 범위 경계"
        )
        scope = s.scalars(
            select(ScoreTotal.judge_scope)
            .join(ScoreRun, ScoreRun.id == ScoreTotal.score_run_id)
            .where(ScoreRun.snapshot_id == stats["snapshot_id"], ScoreTotal.complex_id == judged)
        ).first()
        assert scope in (None, "제외"), scope
        assert not list(
            s.scalars(
                select(Ladder).where(Ladder.snapshot_id == stats["snapshot_id"], Ladder.complex_id == judged)
            )
        ), "제외 단지는 사다리 행이 없다"
    from app.models import JudgmentLog

    with factory() as s:
        noul = list(s.scalars(select(JudgmentLog).where(JudgmentLog.snapshot_id == stats["snapshot_id"],
                                                        JudgmentLog.complex_id == judged, JudgmentLog.tool == "noul")))  # fmt: skip
        assert not noul, "뺀 단지로 사다리(noul)를 부르면 안 된다(M-4)"
    from app.reports.data import _candidates

    with (
        factory() as s
    ):  # §12 후보군(보고서 _extra 가 쓰는 함수 — 이 픽스처는 보고서 전체 적재에 필요한 출처 행이 없다)
        runs = {sid: s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == sid).order_by(ScoreRun.id.desc())).first()
                for sid in (seeded, stats["snapshot_id"])}  # fmt: skip
        everyone = set(s.scalars(select(Complex.id)))
        prev_c = _candidates(s, runs[seeded], everyone)
        cur_c = _candidates(s, runs[stats["snapshot_id"]], everyone)
        assert judged in prev_c - cur_c, f"§12 '제외'에 잡힌다({name})"


def test_m5_region_expand_on_unpublished_revision_1_still_has_section_12(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    ctx = make_ctx()
    assert not run_pipeline(ctx, seeded).degraded
    _publish(factory, seeded)
    with factory() as s:  # 오늘 수집이 이미 리비전 1(building)을 만들었다
        today = snapshots.get_or_create(s, 1, ctx.today().isoformat(), created_at=ctx.iso_now())
        s.commit()
        tid = today.id
        assert today.revision == 1 and today.status == "building" and today.revision_of is None
    job = _expand_job(factory, added=[{"kind": "sigungu", "code": "41570", "full_name": "경기도 김포시"}])
    stats = HANDLERS["region.expand"](ctx, job)
    assert stats["snapshot_id"] == tid
    from app.reports.export import default_compare

    with factory() as s:
        snap = s.get(Snapshot, tid)
        assert snap is not None and snap.revision_of == seeded, "직전 발행 스냅샷이 비교 기준(M-5)"
        assert default_compare(s, tid) == seeded


def test_m6_judge_version_change_on_unpublished_revision_1_gets_compare_base(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    from app.reports.export import default_compare
    from app.scheduler.judge_version import record_version_change

    ctx = make_ctx()
    assert not run_pipeline(ctx, seeded).degraded
    _publish(factory, seeded)
    with factory() as s:
        today = snapshots.get_or_create(s, 1, ctx.today().isoformat(), created_at=ctx.iso_now())
        s.commit()
        tid = today.id
        ev = record_version_change(ctx, s, "wp3+jev-mcp@0.14.1+m1", "wp3+jev-mcp@0.15.0+m1", snapshot_id=tid)
        s.commit()
        assert ev is not None
        snap = s.get(Snapshot, tid)
        assert snap is not None and snap.revision_of == seeded, (
            "미발행 리비전 1 에도 비교 기준(delta 표, M-6)"
        )
        assert default_compare(s, tid) == seeded
        job = s.scalars(select(JobRun).where(JobRun.job_name == "rejudge").order_by(JobRun.id.desc())).first()
        assert job is not None and job.payload["snapshot_id"] == tid and job.payload["complex_ids"] is None


# ====================================================================== 백업 minor (D11-8·D12-6)


def _fake_pg_dump(bin_dir: Path, seen: Path) -> None:
    """PATH 의 가짜 pg_dump — 받은 PGPASSWORD 를 파일에 적고 덤프 파일을 만든다(실제 하위 프로세스 경로)."""
    import os
    import sys

    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "fake_pg_dump.py"
    script.write_text(
        "import os, sys, pathlib\n"
        f"pathlib.Path({str(seen)!r}).write_text(os.environ.get('PGPASSWORD', ''), encoding='utf-8')\n"
        "out = sys.argv[sys.argv.index('-f') + 1]\n"
        "pathlib.Path(out).write_bytes(b'PGDMP')\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        (bin_dir / "pg_dump.cmd").write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        exe = bin_dir / "pg_dump"
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        exe.chmod(0o755)


def test_minor_backup_password_percent_decoded_keep_days_bound_and_oserror_stats(
    test_settings: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    from datetime import datetime

    from app.scheduler.backup import run_backup

    seen = tmp_path / "seen.txt"
    _fake_pg_dump(tmp_path / "bin", seen)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "b"))
    pg = test_settings.model_copy(
        update={"database_url": "postgresql+psycopg://sa:p%40ss%3Aw%2Frd@db:5432/x"}
    )
    stats = run_backup(pg, now=datetime(2026, 10, 8, 3, 0))
    assert stats["db"]["kind"] == "postgres"
    assert seen.read_text(encoding="utf-8") == "p@ss:w/rd", "퍼센트 인코딩을 풀어 PGPASSWORD 로"
    assert "p%40ss" not in str(stats) and "p@ss" not in str(stats), "비밀번호는 stats 에 없다"
    with pytest.raises(RuntimeError, match="keep_days") as err:
        run_backup(test_settings, now=datetime(2026, 10, 8, 3, 0), keep_days=100_000)
    assert err.value.stats["day"] == "2026-10-08"  # type: ignore[attr-defined]
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("BACKUP_DIR", str(blocker))
    with pytest.raises(RuntimeError, match="백업 폴더") as err2:
        run_backup(test_settings, now=datetime(2026, 10, 8, 3, 0))
    assert err2.value.stats["backup_dir"] == str(blocker), "OSError 도 stats 와 함께 실패"  # type: ignore[attr-defined]
