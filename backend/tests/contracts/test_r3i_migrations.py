"""R3i CORE7 — 9차 리뷰(``R3_REVIEW9.md``) major 1·2 · m1 · m5 / **D17-1·D17-2** (계약 .14, 마이그레이션 ``0014``).

devseed(단지 16·시나리오 5·발행 11·12)를 SQLite·임베디드 Postgres 16 에 옮겨 '업그레이드 직후'(0013: 모든 표식 미완 + .11 범위
좁은 서랍 + 기본 시나리오 단지 상세 일부 없음) 상태를 만들고, **발행 뒤 사실 변경**(계약금 10 → 20 — 리뷰 재현 ``r9/b/mutate.py``)을
넣은 뒤 backfill 을 돌린다.

| 리뷰 | 단계 |
| --- | --- |
| major 1 중단: 서랍 DELETE 커밋 뒤 쓰기 전에 죽으면 다음 backfill 이 지금 사실('20')로 서랍을 다시 만든다 | (1) 세 지점(새 행 쓰기 중·새 행 뒤 서랍 전·서랍 쓰기 중)에 예외 → 매번 원래 행·서랍 바이트 그대로, 복구 뒤 서랍 = 발행 순간 값 |
| major 1 동시: backfill 2개 — A IntegrityError, B 가 빈 서랍으로 재생성 | (2) A 가 쓰는 중 B → B 는 그 리비전 busy(건너뜀), A 완료, 서랍 = 발행 순간 값 |
| major 1 발행 겹침 | (3) backfill 이 임대를 든 동안 같은 리비전 ``publish_revision`` → busy(아무것도 안 씀) |
| major 2 / D17-2 ``backfilled_at``·응답 메타 | (4) 새로 계산해 채운 단위만 ``backfilled_at``, 표식만 다시 쓴 단위는 NULL, ``GET /regions/{id}/snapshots`` 의 그 리비전 ``backfilled_at`` |
| major 2 / D17-2 목록 본문 범위 | (5) 발행 뒤 단지 추가 + 시나리오 2 단지 목록·비교 단위 다시 계산 → 새 단지 없음(키와 같은 범위) |
| m5 보고서 저장본 옛 ``sc_<행>``·``st_<행>`` | (6) 0013 DB 의 보고서 본문을 옛 id 로 → head(0014 변환) → 원래 바이트, 서랍 미완 → backfill → 모든 점수 prov 서랍 |
| m1 0013 이 compare 채택 표식을 지움 | (7) 0012 DB 의 파서 할인 '확인됨' + compare 채택 사유 → 0013 → 표식 유지 + '추정' |
| 왕복 | autogenerate diff 0, head → base → head |
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import re
import threading
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.orm import Session

from app.models import Base

from ._support import alembic_config
from .test_r3f_migrations import _copy_rows, _wipe, seeded_sqlite  # noqa: F401  (픽스처 재사용)
from .test_r3h_migrations import _drawers, _narrow_drawers, _rd_ids, _rows, _settings, _units

SNAP = 12


@contextmanager
def _db(url: str, seed_db: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[sa.Engine, Any, Any]]:
    from app.core.db import reset_engine
    from app.core.settings import set_settings

    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    settings = _settings(url, seed_db)
    set_settings(settings)
    try:
        _copy_rows(f"sqlite:///{seed_db.as_posix()}", engine)
        yield engine, settings, cfg
    finally:
        set_settings(None)
        reset_engine()
        command.upgrade(cfg, "head")
        _wipe(engine)
        command.downgrade(cfg, "base")
        engine.dispose()


def _down_payment_fp(engine: sa.Engine) -> tuple[str, int, int]:
    """발행 리비전 서랍에 있는 계약금 출처(fp_<id>) 하나 — (출처 id, 납부 조건 id, 단지 id)."""
    drawers = _drawers(engine, SNAP)
    with engine.connect() as c:
        for fid, pt in c.execute(
            sa.text(
                "SELECT id, entity_id FROM field_provenance WHERE entity = 'payment_terms' AND field = 'down_payment_pct' "
                "AND chosen = :t ORDER BY id"
            ),
            {"t": True},
        ):
            if f"fp_{fid}" in drawers:
                cx = c.execute(sa.text("SELECT complex_id FROM payment_terms WHERE id = :p"), {"p": pt}).scalar()
                return f"fp_{fid}", int(pt), int(cx)
    raise AssertionError("계약금 출처 서랍 없음")


def _mutate_after_publish(engine: sa.Engine, fp: str, pt: int) -> None:
    """발행 뒤 사실 변경(리뷰 재현 r9/b/mutate.py): 계약금 → 20, 그 출처 행 값도 '20'."""
    with engine.begin() as c:
        c.execute(sa.text("UPDATE payment_terms SET down_payment_pct = 20 WHERE id = :p"), {"p": pt})
        c.execute(
            sa.text("UPDATE field_provenance SET value_text = '20', value_norm = '20' WHERE id = :i"),
            {"i": int(fp[3:])},
        )


def _upgrade_state(engine: sa.Engine, keep_cx: int) -> list[str]:
    """업그레이드 직후(0013) 모양: 모든 표식 미완 + 좁은 서랍(rd_ 없음) + 기본 시나리오 단지 상세 일부 삭제(``keep_cx`` 는 남긴다).
    지운 단지 상세 키."""
    rows = _rows(engine, SNAP)
    base_sc = min((sc for (_k, _key, sc) in rows if sc), key=int)
    gone = sorted((key for (k, key, sc) in rows if k == "complex" and sc == base_sc and key != str(keep_cx)), key=int)[:3]
    assert _narrow_drawers(engine, SNAP) > 0
    with engine.begin() as c:
        for key in gone:
            c.execute(
                sa.text("DELETE FROM snapshot_view WHERE snapshot_id = :s AND kind = 'complex' AND scenario = :b AND key = :k"),
                {"s": SNAP, "b": base_sc, "k": key},
            )
        c.execute(sa.text("UPDATE snapshot_view_unit SET done = :f"), {"f": False})
    return gone


def _drawer_value(engine: sa.Engine, pid: str) -> Any:
    got = _drawers(engine, SNAP).get(pid)
    return got.get("value_text") if isinstance(got, dict) else got


def _assert_kept(engine: sa.Engine, before: dict[tuple[str, str, str], bytes], drawers: dict[str, Any], what: str) -> None:
    after = _rows(engine, SNAP)
    lost = [k for k in before if k[0] != "provenance" and after.get(k) != before[k]]
    assert not lost, f"{what}: 이미 있던 저장 행이 지워지거나 바뀌었다 {lost[:5]}"
    now = _drawers(engine, SNAP)
    changed = [p for p, v in drawers.items() if now.get(p) != v]
    assert not changed, f"{what}: 발행 순간 서랍이 지워지거나 지금 사실로 바뀌었다 {changed[:5]} (서랍 {len(now)}/{len(drawers)})"


def check_r3i_backfill(url: str, seed_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.snapshot_view as sv

    with _db(url, seed_db, monkeypatch) as (engine, settings, _cfg):
        fp, pt, cx = _down_payment_fp(engine)
        drawer0 = _drawer_value(engine, fp)
        assert drawer0 is not None and str(drawer0) != "20"
        rd0 = _rd_ids(engine, SNAP)
        _mutate_after_publish(engine, fp, pt)
        gone = _upgrade_state(engine, cx)
        before = _rows(engine, SNAP)
        drawers_before = _drawers(engine, SNAP)
        assert drawers_before.get(fp) is not None

        # (1) 중단 — 세 지점
        real_write = sv.write_rows
        real_dicts = sv._row_dicts

        def crash_main(bind: Any, sid: int, rows: Any, **kw: Any) -> Any:
            if sid == SNAP and rows and rows[0].kind != "provenance":
                raise RuntimeError("worker killed while writing backfilled rows")
            return real_write(bind, sid, rows, **kw)

        def crash_after_main(bind: Any, sid: int, rows: Any, **kw: Any) -> Any:
            out = real_write(bind, sid, rows, **kw)
            if sid == SNAP and rows and rows[0].kind != "provenance":
                raise RuntimeError("worker killed after backfilled rows, before drawers")
            return out

        def crash_drawers(sid: int, rows: Any) -> Any:
            if sid == SNAP and rows and all(r.kind == "provenance" for r in rows):
                raise RuntimeError("worker killed while writing drawers")
            return real_dicts(sid, rows)

        points: list[tuple[str, Callable[[], None]]] = [
            ("새 행 쓰기 중", lambda: monkeypatch.setattr(sv, "write_rows", crash_main)),
            ("새 행 뒤·서랍 전", lambda: monkeypatch.setattr(sv, "write_rows", crash_after_main)),
            ("서랍 쓰기 중", lambda: monkeypatch.setattr(sv, "_row_dicts", crash_drawers)),
        ]
        for name, arm in points:
            arm()
            try:
                res = sv.backfill(engine, settings=settings)
            finally:
                monkeypatch.setattr(sv, "write_rows", real_write)
                monkeypatch.setattr(sv, "_row_dicts", real_dicts)
            assert [f["snapshot_id"] for f in res["failed"]] == [SNAP], (name, res)
            _assert_kept(engine, before, drawers_before, name)
            with engine.connect() as c:
                lease = c.execute(sa.text("SELECT publish_lease FROM snapshot WHERE id = :s"), {"s": SNAP}).scalar()
            assert lease is None, f"{name}: 실패한 backfill 이 임대를 남겼다 {lease}"

        res = sv.backfill(engine, settings=settings)
        assert not res["failed"] and SNAP in res["snapshots"], res
        _assert_kept(engine, before, drawers_before, "복구")
        assert _drawer_value(engine, fp) == drawer0, "복구 뒤 서랍 = 발행 순간 값(지금 사실 '20' 아님)"
        assert rd0 <= set(_drawers(engine, SNAP)), "좁은 서랍의 rd_ 는 채워졌다"
        assert all(d for d, _r in _units(engine).values())
        keys = {key for (k, key, _sc) in _rows(engine, SNAP) if k == "complex"}
        assert set(gone) <= keys

        # (4) D17-2: 새로 계산해 채운 단위만 backfilled_at
        with engine.connect() as c:
            marks = {
                (str(k), str(sc)): b
                for k, sc, b in c.execute(
                    sa.text("SELECT kind, scenario, backfilled_at FROM snapshot_view_unit WHERE snapshot_id = :s"),
                    {"s": SNAP},
                )
            }
        base_sc = min((sc for (_k, sc) in marks if sc), key=int)
        assert marks[("complex", base_sc)], "지운 단지 상세를 다시 계산한 단위 = backfilled_at"
        assert marks[("provenance", "")], "rd_ 서랍을 새로 계산해 넣은 단위 = backfilled_at"
        assert marks[("dashboard", base_sc)] is None, "표식만 다시 쓴 단위(행 그대로)는 backfilled_at 없음"
        with Session(bind=engine) as s:
            from app.api.views import snapshot_view
            from app.models import Snapshot

            meta = snapshot_view(s, s.get(Snapshot, SNAP))  # type: ignore[arg-type]
            assert meta.get("backfilled_at"), meta
            other = snapshot_view(s, s.get(Snapshot, 11))  # type: ignore[arg-type]
            assert other.get("backfilled_at") is None, "새로 계산한 값이 없는 리비전은 표지 없음"

        # (2) 동시 backfill 2개 — A 가 쓰는 동안 B
        _narrow_drawers(engine, SNAP)
        victim = gone[0]
        with engine.begin() as c:
            c.execute(
                sa.text("DELETE FROM snapshot_view WHERE snapshot_id = :s AND kind = 'complex' AND scenario = :b AND key = :k"),
                {"s": SNAP, "b": base_sc, "k": victim},
            )
            c.execute(sa.text("UPDATE snapshot_view_unit SET done = :f WHERE snapshot_id = :s"), {"f": False, "s": SNAP})
        before2 = _rows(engine, SNAP)
        drawers2 = _drawers(engine, SNAP)
        a_in, b_done = threading.Event(), threading.Event()

        def hooked(bind: Any, sid: int, rows: Any, **kw: Any) -> Any:
            if threading.current_thread().name == "A" and sid == SNAP and not a_in.is_set():
                a_in.set()
                b_done.wait(120)
            return real_write(bind, sid, rows, **kw)

        monkeypatch.setattr(sv, "write_rows", hooked)
        out: dict[str, Any] = {}
        ta = threading.Thread(target=lambda: out.__setitem__("A", sv.backfill(engine, settings=settings)), name="A")
        ta.start()
        try:
            assert a_in.wait(120), "A 가 쓰기에 들어가지 않았다"
            out["B"] = sv.backfill(engine, settings=settings)
            # (3) 발행 겹침: backfill(A)이 임대를 든 동안 같은 리비전 발행은 busy — 아무것도 쓰지 않는다
            out["P"] = sv.publish_revision(engine, SNAP, now="2026-10-12T00:00:00+09:00", holder="job:999999")
        finally:
            b_done.set()
            ta.join(180)
            monkeypatch.setattr(sv, "write_rows", real_write)
        assert not out["A"]["failed"] and SNAP in out["A"]["snapshots"], out["A"]
        assert not out["B"]["failed"], out["B"]
        assert SNAP in out["B"].get("busy", []) and SNAP not in out["B"]["snapshots"], out["B"]
        assert out["P"].busy and not out["P"].published, out["P"]
        _assert_kept(engine, before2, drawers2, "동시")
        assert _drawer_value(engine, fp) == drawer0

        # (5) D17-2 목록 본문 범위: 발행 뒤 단지 추가 + 시나리오 2 단지 목록·비교 다시 계산 → 새 단지 없음
        scs = sorted({sc for (_k, sc) in marks if sc}, key=int)
        sc2 = scs[1]
        with engine.begin() as c:
            from app.models import Complex

            table = Complex.__table__
            row = dict(c.execute(sa.select(table).where(table.c.id == cx)).mappings().one())
            row.pop("id")
            row["name"] = "R3i 발행 뒤 단지"
            row["applyhome_id"] = "2099000001"
            c.execute(table.insert(), [row])
            new_id = int(c.execute(sa.text("SELECT MAX(id) FROM complex")).scalar() or 0)
            for kind in ("complexes", "compare"):
                c.execute(
                    sa.text("DELETE FROM snapshot_view WHERE snapshot_id = :s AND kind = :k AND scenario = :sc"),
                    {"s": SNAP, "k": kind, "sc": sc2},
                )
                c.execute(
                    sa.text("UPDATE snapshot_view_unit SET done = :f WHERE snapshot_id = :s AND kind = :k AND scenario = :sc"),
                    {"f": False, "s": SNAP, "k": kind, "sc": sc2},
                )
        res = sv.backfill(engine, settings=settings)
        assert not res["failed"], res
        with Session(bind=engine) as s:
            lst = sv.stored(s, SNAP, "complexes", scenario=sc2)
            base_lst = sv.stored(s, SNAP, "complexes", scenario=base_sc)
            cmp = sv.stored(s, SNAP, "compare", scenario=sc2)
        ids = [r["item"]["complex_id"] for r in lst["rows"]]
        assert new_id not in ids, "발행 뒤 단지가 옛 리비전 목록 본문에 들어갔다(키와 같은 범위 — D17-2)"
        assert sorted(ids) == sorted(r["item"]["complex_id"] for r in base_lst["rows"])
        assert str(new_id) not in (cmp.get("items") or {}), "비교 입력에도 발행 뒤 단지 없음"
        assert set(cmp["items"]) == {str(i) for i in ids}


def test_sqlite_r3i_backfill(seeded_sqlite: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    check_r3i_backfill(f"sqlite:///{(tmp_path / 'r3i.db').as_posix()}", seeded_sqlite, monkeypatch)


@pytest.mark.postgres
def test_postgres_r3i_backfill(seeded_sqlite: Path, postgres_url: str) -> None:  # noqa: F811
    mp = pytest.MonkeyPatch()
    try:
        check_r3i_backfill(postgres_url, seeded_sqlite, mp)
    finally:
        mp.undo()


# ====================================================================== m5 — 보고서 저장본 옛 점수 id 변환(0014)

_NEW_RE = re.compile(rb'"prov":(\{"\$v":)?"(sc|st)_(\d+)_(\d+)(?:_([A-Za-z0-9]+))?"')
_OLD_RE = re.compile(rb'"prov":(?:\{"\$v":)?"(?:sc|st)_\d+"')


def _to_old_ids(engine: sa.Engine) -> int:
    """.13 이전 보고서 저장본 흉내: 점수 prov 를 행 id(``sc_<성분 행>``·``st_<합계 행>``)로 되돌린다(본문·sha256 다시). 바꾼 행 수."""
    with engine.connect() as c:
        comp = {
            (int(r), int(cx), str(k)): int(i)
            for i, r, cx, k in c.execute(sa.text("SELECT id, score_run_id, complex_id, component FROM score_component"))
        }
        tot = {(int(r), int(cx)): int(i) for i, r, cx in c.execute(sa.text("SELECT id, score_run_id, complex_id FROM score_total"))}
        rows = c.execute(
            sa.text("SELECT id, body FROM snapshot_view WHERE kind IN ('report', 'report_diff')")
        ).all()

    def old(m: re.Match[bytes]) -> bytes:
        v, kind, run, cx, comp_name = m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), m.group(5)
        rid = comp.get((run, cx, comp_name.decode())) if kind == b"sc" and comp_name else tot.get((run, cx))
        if rid is None or (kind == b"sc") != bool(comp_name):
            return m.group(0)
        inner = b'"' + kind + b"_" + str(rid).encode() + b'"'
        return b'"prov":' + (b'{"$v":' + inner if v else inner)

    n = 0
    with engine.begin() as c:
        for rid, body in rows:
            raw = zlib.decompress(bytes(body))
            assert not _OLD_RE.search(raw), "head 보고서 저장본에 옛 모양 id 가 있으면 안 된다"
            new = _NEW_RE.sub(old, raw)
            if new != raw:
                n += 1
                c.execute(
                    sa.text("UPDATE snapshot_view SET body = :b, sha256 = :h WHERE id = :i"),
                    {"b": zlib.compress(new, 1), "h": hashlib.sha256(new).hexdigest(), "i": rid},
                )
    return n


def check_m5_report_ids(url: str, seed_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.snapshot_view as sv
    from app.models import Snapshot

    with _db(url, seed_db, monkeypatch) as (engine, settings, cfg):
        rows0 = _rows(engine, SNAP)
        command.downgrade(cfg, "0013")
        assert _to_old_ids(engine) > 0
        assert _rows(engine, SNAP) != rows0
        command.upgrade(cfg, "head")
        rows1 = _rows(engine, SNAP)

        def plain(rows: dict[tuple[str, str, str], bytes]) -> dict[tuple[str, str, str], bytes]:
            return {k: zlib.decompress(v) for k, v in rows.items() if k[0] in ("report", "report_diff")}

        assert plain(rows1) == plain(rows0), "0014 변환 = 옛 행 id → API 서랍 id(sc_<실행>_<단지>_<성분>·st_<실행>_<단지>), 원래 JSON 바이트"
        with engine.connect() as c:
            sha_ok = all(
                hashlib.sha256(zlib.decompress(bytes(b))).hexdigest() == h
                for b, h in c.execute(sa.text("SELECT body, sha256 FROM snapshot_view WHERE kind = 'report'"))
            )
        assert sha_ok
        assert not _units(engine, SNAP)[(SNAP, "provenance", "")][0], "변환한 리비전의 서랍 단위는 미완(새 id 서랍 채우기)"
        res = sv.backfill(engine, settings=settings)
        assert not res["failed"], res
        with Session(bind=engine) as s:
            snap = s.get(Snapshot, SNAP)
            assert snap is not None
            ids: set[str] = set()
            for (k, _key, _sc), body in _rows(engine, SNAP).items():
                if k == "report":
                    ids |= {m.decode() for m in re.findall(rb'"prov":(?:\{"\$v":)?"((?:sc|st)_[0-9A-Za-z_]+)"', zlib.decompress(body))}
            assert ids
            missing = [p for p in sorted(ids) if sv.provenance(s, snap, p) is None]
            assert not missing, missing[:10]


def test_sqlite_m5_report_score_ids(seeded_sqlite: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    check_m5_report_ids(f"sqlite:///{(tmp_path / 'r3i_m5.db').as_posix()}", seeded_sqlite, monkeypatch)


@pytest.mark.postgres
def test_postgres_m5_report_score_ids(seeded_sqlite: Path, postgres_url: str) -> None:  # noqa: F811
    mp = pytest.MonkeyPatch()
    try:
        check_m5_report_ids(postgres_url, seeded_sqlite, mp)
    finally:
        mp.undo()


# ====================================================================== m1 — 0013 이 compare 채택 표식을 지우지 않는다


def check_m1_0013_keeps_compare_mark(url: str, seed_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _db(url, seed_db, monkeypatch) as (engine, _settings_obj, cfg):
        command.downgrade(cfg, "0012")
        with engine.begin() as c:
            raw_id = c.execute(sa.text("SELECT MIN(id) FROM raw_document WHERE source_kind = 'notice_pdf'")).scalar()
            pt = c.execute(sa.text("SELECT MIN(id) FROM payment_terms")).scalar()
            c.execute(
                sa.text(
                    "INSERT INTO field_provenance (entity, entity_id, field, value_text, value_norm, raw_document_id, url, "
                    "checked_at, label, reason, source_rank, chosen) VALUES ('payment_terms', :pt, 'discount_by_type.84A', "
                    "'1,200,000', '1200000', :raw, 'https://x', '2026-10-08', '확인됨', :reason, 1, :chosen)"
                ),
                {"pt": pt, "raw": raw_id, "reason": "판정기 compare 채택(jl_7)", "chosen": True},
            )
        command.upgrade(cfg, "0013")
        with engine.connect() as c:
            label, reason = c.execute(
                sa.text("SELECT label, reason FROM field_provenance WHERE field = 'discount_by_type.84A' ORDER BY id DESC")
            ).first()  # type: ignore[misc]
        assert label == "추정"
        assert "판정기 compare 채택" in reason and "조건 확인 필요" in reason, reason
        # 라벨을 내린 채택 할인 → backfill 이 critical·재판정 change_event 를 한 번(멱등) + 재판정 잡
        import app.snapshot_view as sv

        command.upgrade(cfg, "head")
        res = sv.backfill(engine, settings=_settings_obj)
        assert res["discounts_relabelled"] == 1 and not res["failed"], res
        with engine.connect() as c:
            evs = c.execute(
                sa.text(
                    "SELECT severity, triggers_rejudge, snapshot_id FROM change_event WHERE field = 'discount_by_type.84A' "
                    "AND new_text LIKE '%0013 전환%'"
                )
            ).all()
            jobs = c.execute(sa.text("SELECT payload FROM job_run WHERE job_name = 'rejudge' AND status = 'queued'")).all()
        assert len(evs) == 1 and evs[0][0] == "critical" and evs[0][1] and evs[0][2] is not None, evs
        assert jobs, "재판정 잡"
        assert sv.backfill(engine, settings=_settings_obj)["discounts_relabelled"] == 0


def test_sqlite_m1_0013_keeps_compare_mark(seeded_sqlite: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    check_m1_0013_keeps_compare_mark(f"sqlite:///{(tmp_path / 'r3i_m1.db').as_posix()}", seeded_sqlite, monkeypatch)


@pytest.mark.postgres
def test_postgres_m1_0013_keeps_compare_mark(seeded_sqlite: Path, postgres_url: str) -> None:  # noqa: F811
    mp = pytest.MonkeyPatch()
    try:
        check_m1_0013_keeps_compare_mark(postgres_url, seeded_sqlite, mp)
    finally:
        mp.undo()


# ====================================================================== 0014 왕복


def check_0014_roundtrip(url: str, seed_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _db(url, seed_db, monkeypatch) as (engine, _s, cfg):
        command.downgrade(cfg, "0013")
        with engine.connect() as c:
            cols = {col["name"] for col in sa.inspect(c).get_columns("snapshot_view_unit")}
        assert "backfilled_at" not in cols
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            cols = {col["name"] for col in sa.inspect(c).get_columns("snapshot_view_unit")}
            assert "backfilled_at" in cols
            ctx = MigrationContext.configure(c, opts={"compare_type": True})
            assert compare_metadata(ctx, Base.metadata) == []


def test_sqlite_0014_roundtrip(seeded_sqlite: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    check_0014_roundtrip(f"sqlite:///{(tmp_path / 'r3i_rt.db').as_posix()}", seeded_sqlite, monkeypatch)


@pytest.mark.postgres
def test_postgres_0014_roundtrip(seeded_sqlite: Path, postgres_url: str) -> None:  # noqa: F811
    mp = pytest.MonkeyPatch()
    try:
        check_0014_roundtrip(postgres_url, seeded_sqlite, mp)
    finally:
        mp.undo()
