"""R7-FIX2 — 같은 기준일 리비전(D11-1)에서 어제 수집 실패 행이 오늘 관측 옆에 남아 표시되는 결함.

운영(인천 지역 1): R7-FIX 배포 뒤 같은 기준일 2026-10-14 의 리비전 2·3(스냅샷 3·4, '같은 기준일 재수집' — 수동 collect.daily #8,
예약 06:00 collect.daily #7)에도 스냅샷 2(리비전 1, R7-FIX 배포 전 수집)가 물려받은 어제(2026-10-13) 실패 행이 그대로 있고
표시됐다 — 단지 7·8·22·37 은 headless_shot(오늘 원문 2299…, 판정기 분류) + official_popup '403'(어제 원문 1221…), 38·72·75·87 은
headless_shot(원문 2314) + official_popup 'TLS'(어제 원문 1258·1303). ``pick_intake`` 는 official_popup > headless_shot 이라 403·TLS.

원인: ``snapshots.get_or_create`` → ``new_revision`` 이 발행 리비전의 접수 행을 **빈 새 리비전에 전부** 복사한다(R7-FIX 의
"오늘 관측이 어제 실패를 대신" 규칙은 dst 에 오늘 행이 있을 때만 — 이 시점에는 없다). 그 뒤 ``collect.intake_rows`` 는 (단지,
경로)가 이미 있으면 오늘 행을 만들지 않고, ``copy_intake(prev, rev)`` 도 이미 다 있어 아무것도 안 한다 → 낡은 실패 행이 리비전마다
이어진다. 같은 날 리비전 1 이 실패·리비전 2 가 성공인 경우도 같다(리비전 1 의 실패 행이 리비전 2 에 남는다).

가짜 판정기는 응답 모양만 흉내 낸다(판단 아님).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.scope import pick_intake
from app.collectors.official_site import SiteTarget
from app.core.contracts_gen import RawDocument as RawDTO
from app.models import IntakeStatus, RawDocument, Snapshot
from app.scheduler.collect import collect, intake_rows
from app.scheduler.context import SchedulerContext
from app.scheduler.intake import UNCLASSIFIED
from app.scheduler.persist import copy_intake
from app.scheduler.pipeline import run_pipeline

from .conftest import SynthJev
from .test_r7_fix import SITE, _rows, _tls_ctx
from .test_r7_site import RecordingJev

A, B = 4, 5


@pytest.fixture
def jev() -> SynthJev:
    return RecordingJev()


def _publish(factory: sessionmaker[Session], sid: int) -> None:
    """발행 상태로(저장본 materialize 는 이 결함과 무관 — ``new_revision`` 은 status 만 본다)."""
    with factory() as s:
        snap = s.get(Snapshot, sid)
        assert snap is not None
        snap.status = "published"
        s.commit()


def _run(ctx: SchedulerContext, asof: str) -> int:
    res = collect(ctx, 1, ["official_site"], asof_date=asof)
    assert res.errors == {}, res.stats()
    run_pipeline(ctx, res.snapshot_id)
    return res.snapshot_id


def _view(
    factory: sessionmaker[Session], sid: int, cid: int
) -> list[tuple[str, str | None, int | None, int | None]]:
    return [(r.path, r.reason, r.raw_document_id, r.http_status) for r in _rows(factory, sid, cid)]


def _failure_raw_ids(factory: sessionmaker[Session], sid: int, cid: int) -> set[int]:
    return {
        r.raw_document_id
        for r in _rows(factory, sid, cid)
        if r.path in ("official_popup", "headless_shot")
        and r.raw_document_id is not None
        and r.http_status != 200
    }


def _inherit_like_before_r7_fix(
    factory: sessionmaker[Session], src: int, dst: int, cids: tuple[int, ...]
) -> None:
    """R7-FIX 배포 전 ``copy_intake`` 가 한 일 그대로: dst 에 (단지, 경로)가 없으면 src 행을 복사(인천 스냅샷 2 의 193~202 행)."""
    with factory() as s:
        have = {
            (r.complex_id, r.path)
            for r in s.scalars(select(IntakeStatus).where(IntakeStatus.snapshot_id == dst))
        }
        for r in s.scalars(
            select(IntakeStatus).where(IntakeStatus.snapshot_id == src, IntakeStatus.complex_id.in_(cids))
        ):
            if (r.complex_id, r.path) in have:
                continue
            s.add(
                IntakeStatus(
                    complex_id=r.complex_id, snapshot_id=dst, status=r.status, path=r.path, evidence_url=r.evidence_url,
                    screenshot_path=r.screenshot_path, raw_document_id=r.raw_document_id, http_status=r.http_status,
                    checked_at=r.checked_at, reason=r.reason, note=r.note, entered_by=r.entered_by,
                )
            )  # fmt: skip
        s.commit()


def test_live_pattern_same_asof_revisions_drop_inherited_failure_rows(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """운영 그대로: 1일차 실패(TLS) → 2일차 리비전 1 은 오늘 성공 + 어제 실패 행을 물려받음(R7-FIX 전 수집 — 스냅샷 2) → 발행 →
    같은 기준일 재수집 리비전 2·3(스냅샷 3·4). 리비전 2·3 의 표시 접수 행은 오늘 성공(headless_shot)이고 어제 실패 행이 없다.
    리비전 3(변경 없음)은 접수·동일성 classify 를 다시 부르지 않는다(D10-2)."""
    targets = [SiteTarget(SITE, A), SiteTarget(SITE, B)]
    with _tls_ctx(make_ctx, factory, targets, browser=False) as ctx:
        day1 = _run(ctx, "2026-10-13")
    _publish(factory, day1)
    stale = {cid: _failure_raw_ids(factory, day1, cid) for cid in (A, B)}
    assert all(stale.values())
    with _tls_ctx(make_ctx, factory, targets, browser=True) as ctx:
        rev1 = _run(ctx, "2026-10-14")
        _inherit_like_before_r7_fix(factory, day1, rev1, (A, B))  # 스냅샷 2 상태(193~202)
        _publish(factory, rev1)
        rev2 = _run(ctx, "2026-10-14")
        _publish(factory, rev2)
        calls = len(jev.calls)
        rev3 = _run(ctx, "2026-10-14")
    with factory() as s:
        revs = {sid: s.get(Snapshot, sid) for sid in (rev1, rev2, rev3)}
        assert [(x.revision, x.revision_reason) for x in revs.values() if x is not None] == [
            (1, None), (2, "같은 기준일 재수집"), (3, "같은 기준일 재수집"),
        ]  # fmt: skip
        shot = s.scalars(
            select(RawDocument).where(RawDocument.url == SITE, RawDocument.content_type == "image/png")
        ).one()
    for sid in (rev2, rev3):
        for cid in (A, B):
            view = _view(factory, sid, cid)
            assert not (_failure_raw_ids(factory, sid, cid) & stale[cid]), (sid, cid, view)
            shown = pick_intake(_rows(factory, sid, cid))
            assert shown is not None and (shown.path, shown.raw_document_id, shown.http_status) == (
                "headless_shot", shot.id, 200,
            ), (sid, cid, view)  # fmt: skip
            assert shown.reason != UNCLASSIFIED
    new = [c.removeprefix("jev_") for c in jev.calls[calls:]]
    assert "classify" not in new, new


def test_same_day_failed_revision_then_success_revision(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """지금 코드만으로도 생긴다: 같은 기준일 리비전 1 은 TLS 실패, 리비전 2 는 브라우저 성공 → 리비전 2 에 리비전 1 의 실패 행(이른
    수집의 원문)이 남아 표시되면 안 된다. 다음 리비전(변경 없음)도 같다."""
    targets = [SiteTarget(SITE, A), SiteTarget(SITE, B)]
    with _tls_ctx(make_ctx, factory, targets, browser=False) as ctx:
        rev1 = _run(ctx, "2026-10-14")
    _publish(factory, rev1)
    early = {cid: _failure_raw_ids(factory, rev1, cid) for cid in (A, B)}
    assert all(early.values())
    with _tls_ctx(make_ctx, factory, targets, browser=True) as ctx:
        rev2 = _run(ctx, "2026-10-14")
        _publish(factory, rev2)
        rev3 = _run(ctx, "2026-10-14")
    for sid in (rev2, rev3):
        for cid in (A, B):
            view = _view(factory, sid, cid)
            assert not _failure_raw_ids(factory, sid, cid), (sid, cid, view)
            shown = pick_intake(_rows(factory, sid, cid))
            assert shown is not None and (shown.path, shown.http_status) == ("headless_shot", 200), (
                sid,
                cid,
                view,
            )


def test_same_day_success_then_failure_revision_shows_failure(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """반대(회귀 방지): 리비전 1 성공, 리비전 2 는 실패 — 오늘(나중) 실패가 표시된다(이른 성공 행은 남지만 표시되지 않는다)."""
    targets = [SiteTarget(SITE, A), SiteTarget(SITE, B)]
    with _tls_ctx(make_ctx, factory, targets, browser=True) as ctx:
        rev1 = _run(ctx, "2026-10-14")
    _publish(factory, rev1)
    with _tls_ctx(make_ctx, factory, targets, browser=False) as ctx:
        rev2 = _run(ctx, "2026-10-14")
    for cid in (A, B):
        shown = pick_intake(_rows(factory, rev2, cid))
        assert shown is not None and (shown.path, shown.reason) == ("official_popup", "TLS"), _view(
            factory, rev2, cid
        )


def _raw(
    s: Session, key: str, status: int | None, *, image: bool = False, day: str = "2026-10-14"
) -> RawDocument:
    row = RawDocument(
        source_kind="official_site", url=f"https://cx.example.test/{key}", fetched_at=f"{day}T03:00:00+09:00",
        http_status=status, sha256=key * 64, path=f"raw/{key}" if status == 200 else None,
        content_type=("image/png" if image else "text/html") if status == 200 else None,
        error_text=None if status == 200 else (str(status) if status else "TLS"),
    )  # fmt: skip
    s.add(row)
    s.flush()
    return row


def _dto(r: RawDocument, cid: int) -> RawDTO:
    from app.normalize.store import raw_dto

    return raw_dto(r).model_copy(update={"complex_id": cid})


def test_intake_rows_today_observation_replaces_copied_failure_rows(
    factory: sessionmaker[Session], seeded: int
) -> None:
    """``intake_rows`` 단위(리비전 경로): 새 리비전에 복사된 행 중 오늘 관측이 있는 단지의 (1) **이른 수집 실패 행**(수집 경로·
    '확인 불가'·200 아님·원문 또는 응답 코드 — 오늘 받은 원문이 아님, 어느 경로든)과 (2) 오늘 행과 **같은 경로**의 이른 행은 지우고
    오늘 행을 만든다(새 기준일 스냅샷과 같은 결과). 사람 확인·비공식 참고·다른 경로의 성공 행·다른 경로의 원문 없는 적재 행·
    오늘 다시 받은 같은 원문(같은 날 재실행 — 멱등)·오늘 관측 없는 단지는 그대로."""
    with factory() as s:
        rev = Snapshot(region_id=1, asof_date="2026-10-14", status="building", degraded=False, created_at="2026-10-14T06:00:00+09:00", revision=2)  # fmt: skip
        s.add(rev)
        s.flush()
        old403 = _raw(s, "a", 403, day="2026-10-13")
        old_tls = _raw(s, "b", None, day="2026-10-13")
        shot = _raw(s, "c", 200, image=True)
        page = _raw(s, "d", 200)
        same_fail = _raw(s, "e", 403)
        ok_old = _raw(s, "f", 200, image=True, day="2026-10-13")

        def row(
            cid: int, path: str, raw: RawDocument | None, status: str = "확인 불가", reason: str | None = None
        ) -> IntakeStatus:
            return IntakeStatus(
                complex_id=cid, snapshot_id=rev.id, status=status, path=path,
                raw_document_id=raw.id if raw else None, http_status=raw.http_status if raw else None,
                checked_at=raw.fetched_at if raw else "2026-10-13", reason=reason,
            )  # fmt: skip

        s.add_all(
            [
                # 단지 7: 리비전 1 에서 복사된 어제 '403'(official_popup) + 오늘과 같은 원문의 성공 행(headless_shot)
                row(7, "official_popup", old403, reason="403"),
                row(7, "headless_shot", shot, reason="판정 미해결"),
                row(7, "human_check", None, status="가능"),
                row(7, "unofficial_ref", None, status="미정"),
                # 단지 8: 어제 'TLS'(http 없음) — 오늘 HTML 만 성공(같은 경로 official_popup)
                row(8, "official_popup", old_tls, reason="TLS"),
                row(
                    8, "headless_shot", ok_old, reason="판정 미해결"
                ),  # 이른 성공 행 — 그대로(경로 우선은 기존 규칙)
                # 단지 9: 오늘도 같은 실패 원문(같은 날 재실행) — 그대로
                row(9, "official_popup", same_fail, reason="403"),
                # 단지 10: 원문 없는 적재 행 — 오늘 같은 경로(official_popup) 관측이 대신한다(새 기준일과 같음)
                row(10, "official_popup", None, status="미정"),
                # 단지 12: 같은 경로(headless_shot)의 이른 성공 행 — 오늘 다른 원문이면 오늘 행
                row(12, "headless_shot", ok_old, reason="판정 미해결"),
                # 단지 13: 다른 경로의 원문 없는 적재 행(회귀 픽스처 모양) — 그대로
                row(13, "official_popup", None, status="미정"),
                # 단지 14: 원문 없이 응답 코드만 남은 적재 실패 행(픽스처 '403') — 수집 실패 행
                IntakeStatus(
                    complex_id=14,
                    snapshot_id=rev.id,
                    status="확인 불가",
                    path="official_popup",
                    http_status=403,
                    checked_at="2026-10-07",
                    reason="403",
                ),
                # 단지 11: 오늘 관측 없음 — 어제 실패 행 그대로
                row(11, "official_popup", old403, reason="403"),
            ]
        )
        s.flush()
        docs = [
            _dto(shot, 7),
            _dto(page, 8),
            _dto(same_fail, 9),
            _dto(page, 10),
            _dto(shot, 12),
            _dto(shot, 13),
            _dto(shot, 14),
        ]
        intake_rows(s, rev.id, docs)
        s.commit()
        got = {
            (r.complex_id, r.path, r.raw_document_id, r.reason)
            for r in s.scalars(select(IntakeStatus).where(IntakeStatus.snapshot_id == rev.id))
        }
        ids = {
            "old403": old403.id,
            "old_tls": old_tls.id,
            "shot": shot.id,
            "page": page.id,
            "same": same_fail.id,
            "ok_old": ok_old.id,
        }
    assert (7, "official_popup", ids["old403"], "403") not in got
    assert {
        (7, "headless_shot", ids["shot"], "판정 미해결"),
        (7, "human_check", None, None),
        (7, "unofficial_ref", None, None),
    } <= got
    assert (8, "official_popup", ids["old_tls"], "TLS") not in got
    assert (8, "official_popup", ids["page"], UNCLASSIFIED) in got, "오늘 HTML 성공 행이 새로 생긴다"
    assert (8, "headless_shot", ids["ok_old"], "판정 미해결") in got
    assert (9, "official_popup", ids["same"], "403") in got
    assert (10, "official_popup", None, None) not in got and (
        10,
        "official_popup",
        ids["page"],
        UNCLASSIFIED,
    ) in got
    assert [g for g in got if g[0] == 12] == [(12, "headless_shot", ids["shot"], UNCLASSIFIED)]
    assert (13, "official_popup", None, None) in got and (
        13,
        "headless_shot",
        ids["shot"],
        UNCLASSIFIED,
    ) in got
    assert [g for g in got if g[0] == 14] == [(14, "headless_shot", ids["shot"], UNCLASSIFIED)]
    assert (11, "official_popup", ids["old403"], "403") in got
    assert len([g for g in got if g[0] == 8 and g[1] == "official_popup"]) == 1


def test_copy_intake_into_revision_after_today_rows_skips_failures(
    factory: sessionmaker[Session], seeded: int
) -> None:
    """``intake_rows`` 가 리비전의 이른 실패 행을 지운 뒤 ``copy_intake(앞 리비전, 리비전)`` 이 그 행을 되살리지 않는다."""
    with factory() as s:
        r1 = Snapshot(region_id=1, asof_date="2026-10-14", status="published", degraded=False, created_at="2026-10-14T02:00:00+09:00", revision=1)  # fmt: skip
        r2 = Snapshot(region_id=1, asof_date="2026-10-14", status="building", degraded=False, created_at="2026-10-14T06:00:00+09:00", revision=2)  # fmt: skip
        s.add_all([r1, r2])
        s.flush()
        old403 = _raw(s, "7", 403, day="2026-10-13")
        shot = _raw(s, "8", 200, image=True)
        for sid in (r1.id, r2.id):  # r2 = new_revision 이 복사한 상태
            s.add_all(
                [
                    IntakeStatus(complex_id=7, snapshot_id=sid, status="확인 불가", path="official_popup", raw_document_id=old403.id, http_status=403, checked_at=old403.fetched_at, reason="403"),
                    IntakeStatus(complex_id=7, snapshot_id=sid, status="확인 불가", path="headless_shot", raw_document_id=shot.id, http_status=200, checked_at=shot.fetched_at, reason="판정 미해결"),
                ]
            )  # fmt: skip
        s.flush()
        intake_rows(s, r2.id, [_dto(shot, 7)])
        copy_intake(s, r1.id, r2.id)
        s.commit()
        got = [
            (r.path, r.reason)
            for r in s.scalars(
                select(IntakeStatus).where(IntakeStatus.snapshot_id == r2.id).order_by(IntakeStatus.id)
            )
        ]
    assert got == [("headless_shot", "판정 미해결")]


@dataclass
class _Row:
    id: int
    path: str
    checked_at: str | None
    status: str
    raw_document_id: int | None = None
    http_status: int | None = None


def test_pick_intake_failed_fetch_does_not_outrank_newer_success() -> None:
    """``pick_intake`` 방어: 수집 실패 행(수집 경로·원문 있음·200 아님)은 그보다 **나중**(KST 날짜, 같은 날이면 id) 수집 성공 행이
    있으면 경로 우선(official_popup > headless_shot)으로 이기지 못한다. 사람 확인은 늘 먼저, 원문 없는 행·성공 행끼리는 예전 규칙."""
    fail_old = _Row(10, "official_popup", "2026-10-13T19:26:03+09:00", "확인 불가", 1221, 403)
    ok_new = _Row(9, "headless_shot", "2026-10-14T02:39:25+09:00", "확인 불가", 2299, 200)
    assert pick_intake([ok_new, fail_old]) is ok_new  # 인천 스냅샷 2: 오늘 행 id 가 더 작아도 날짜가 나중
    tls_old = _Row(11, "official_popup", "2026-10-13T19:29:07+09:00", "확인 불가", 1258, None)
    assert pick_intake([tls_old, ok_new]) is ok_new
    # 같은 날: 나중에 기록된(id 큰) 성공이 이른 실패를 대신한다(같은 기준일 리비전)
    fail_am = _Row(20, "official_popup", "2026-10-14T06:00:00+09:00", "확인 불가", 3000, None)
    ok_pm = _Row(21, "headless_shot", "2026-10-14T06:00:00+09:00", "확인 불가", 3001, 200)
    assert pick_intake([fail_am, ok_pm]) is ok_pm
    # 나중 실패는 이른 성공을 이긴다(오늘 사이트가 막혔다 — 기존 동작)
    ok_old = _Row(30, "headless_shot", "2026-10-13T10:00:00+09:00", "가능", 4000, 200)
    fail_new = _Row(31, "official_popup", "2026-10-14T10:00:00+09:00", "확인 불가", 4001, 403)
    assert pick_intake([ok_old, fail_new]) is fail_new
    # 사람 확인은 늘 먼저
    hc = _Row(40, "human_check", "2026-10-01", "가능")
    assert pick_intake([fail_old, ok_new, hc]) is hc
    # 원문 없는 적재 행(회귀 픽스처)·성공 행끼리는 경로 우선 그대로(T8)
    popup_ok = _Row(50, "official_popup", "2026-10-13", "가능", 9062, 200)
    assert pick_intake([popup_ok, ok_new]) is popup_ok
    plain = _Row(51, "official_popup", "2026-10-13", "미정")
    assert pick_intake([plain, ok_new]) is plain
    # 실패 행뿐이면 그대로 표시(실패도 데이터)
    assert pick_intake([fail_old]) is fail_old
