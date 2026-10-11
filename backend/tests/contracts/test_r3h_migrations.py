"""R3h CORE6 — 8차 리뷰 N-M1·N-M2·m3 / **D16-2**: 0012 이전 저장본 단위는 전부 미완(행 수 추정 금지), backfill 은 빠진 키만,
표식 없는 행 단위도 미완. 계약 .13 마이그레이션 ``0013``(.12 DB: 표식 재검증 + 파서 '확인됨' 할인 → '추정', D16-1).

devseed(인천·김포 — 단지 16·시나리오 5·발행 11·12)를 SQLite·임베디드 Postgres 16 에 옮겨:

| 리뷰 | 단계 |
| --- | --- |
| N-M1 .11 DB 출처 서랍이 .11 범위(``rd_`` 없음) — 색인 묶음 수만 맞으면 done 이던 것 | (1) 0011 에서 서랍의 ``rd_`` 를 빼고(묶음 수 그대로) → head: 모든 단위 미완 → backfill → ``rd_`` 서랍 전부 있음, 원래 서랍 본문 그대로 |
| N-M2 기본 시나리오 단위가 일부만(16 중 8) + 다른 시나리오 0 → '시나리오 사이 최대 행 수' 추정이 done | (1) 같은 DB: 기본 시나리오 단지 상세 절반·다른 시나리오 전부·보고서 삭제 → head → backfill → 키 전부, 남은 행 바이트 그대로 |
| m3 행 있고 표식 없는 단위 → 영구 404 | (2) 표식 삭제 → 503(미완)·pending_count 1 → backfill 이 표식만(바이트 그대로) |
| D16-2 .12 DB(0012 가 추정으로 done 표식) | (3) 0012 에서 좁은 서랍 + done 표식 → head(0013) → 미완 → backfill → ``rd_`` 서랍 |
| D16-1 .12 DB 의 파서 '확인됨' 할인 | (3) 0013 이 '추정'으로(사람 확인 행은 그대로) |
| backfill 이 발행 뒤 생긴 키를 옛 리비전에 넣지 않는다(불변) | (4) 발행 뒤 단지 추가 + 단지 상세 단위 미완 → backfill 은 지운 키만 되살린다 |
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import zlib
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.orm import Session

from app.models import Base

from ._support import alembic_config
from .test_r3f_migrations import _copy_rows, _wipe, seeded_sqlite  # noqa: F401  (픽스처 재사용)

SNAP = 12


def _units(engine: sa.Engine, sid: int | None = None) -> dict[tuple[int, str, str], tuple[bool, int]]:
    with engine.connect() as c:
        return {
            (int(s), str(k), str(sc)): (bool(d), int(r))
            for s, k, sc, d, r in c.execute(
                sa.text("SELECT snapshot_id, kind, scenario, done, rows FROM snapshot_view_unit")
            )
            if sid is None or int(s) == sid
        }


def _rows(engine: sa.Engine, sid: int) -> dict[tuple[str, str, str], bytes]:
    with engine.connect() as c:
        return {
            (str(k), str(key), str(sc)): bytes(b)
            for k, key, sc, b in c.execute(
                sa.text("SELECT kind, key, scenario, body FROM snapshot_view WHERE snapshot_id = :s"),
                {"s": sid},
            )
        }


def _drawers(engine: sa.Engine, sid: int) -> dict[str, object]:
    out: dict[str, object] = {}
    for (k, key, _sc), body in _rows(engine, sid).items():
        if k == "provenance" and key != "idx":
            out.update(json.loads(zlib.decompress(body).decode("utf-8")))
    return out


def _narrow_drawers(engine: sa.Engine, sid: int) -> int:
    """.11 범위 서랍 흉내: 묶음 행 수·색인은 그대로 두고 묶음 본문에서 ``rd_`` 서랍을 뺀다(본문·sha256 다시). 뺀 수."""
    removed = 0
    with engine.begin() as c:
        for key, body in c.execute(
            sa.text(
                "SELECT key, body FROM snapshot_view WHERE snapshot_id = :s AND kind = 'provenance' AND key != 'idx'"
            ),
            {"s": sid},
        ).all():
            got = json.loads(zlib.decompress(bytes(body)).decode("utf-8"))
            keep = {k: v for k, v in got.items() if not k.startswith("rd_")}
            removed += len(got) - len(keep)
            raw = json.dumps(keep, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            c.execute(
                sa.text(
                    "UPDATE snapshot_view SET body = :b, sha256 = :h WHERE snapshot_id = :s AND kind = 'provenance' AND key = :k"
                ),
                {"b": zlib.compress(raw, 1), "h": hashlib.sha256(raw).hexdigest(), "s": sid, "k": key},
            )
    return removed


def _rd_ids(engine: sa.Engine, sid: int) -> set[str]:
    """그 리비전 저장 본문(서랍 제외)이 가리키는 접수 근거 ``rd_`` 전부(화면이 서랍으로 연다)."""
    import re

    out: set[str] = set()
    for (k, _key, _sc), body in _rows(engine, sid).items():
        if k != "provenance":
            out |= {
                f"rd_{m.decode()}"
                for m in re.findall(rb'"raw_document_id":(?:\{"\$v":)?(\d+)', zlib.decompress(body))
            }
    return out


def _settings(url: str, seed_db: Path):  # type: ignore[no-untyped-def]
    from app.core.settings import Settings

    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="dev",
        database_url=url,
        raw_dir=seed_db.parent / "raw",
        reference_dir=seed_db.parent / "reference",
        report_dir=seed_db.parent / "reports",
        judge_adapter="mock",
        log_json=False,
    )


def check_r3h_migrations(url: str, seed_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.db import reset_engine
    from app.core.settings import set_settings
    from app.models import Complex, Snapshot
    from app.snapshot_view import MaterializePending, backfill, pending_count, provenance, read

    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    settings = _settings(url, seed_db)
    set_settings(settings)
    try:
        _copy_rows(f"sqlite:///{seed_db.as_posix()}", engine)
        rows0 = _rows(engine, SNAP)
        drawers0 = _drawers(engine, SNAP)
        rd0 = _rd_ids(engine, SNAP)
        assert rd0 and rd0 <= set(drawers0), "head(.12) 서랍은 rd_ 를 담는다"

        # (1) .11 DB: 좁은 서랍(N-M1) + 기본 시나리오 단지 상세 절반·다른 시나리오 전부·보고서 없음(N-M2)
        command.downgrade(cfg, "0011")
        assert _narrow_drawers(engine, SNAP) > 0
        scs = sorted({sc for (_k, _key, sc) in rows0 if sc}, key=int)
        base_cx = sorted((key for (k, key, sc) in rows0 if k == "complex" and sc == scs[0]), key=int)
        gone_cx = base_cx[len(base_cx) // 2 :]
        with engine.begin() as c:
            c.execute(
                sa.text(
                    "DELETE FROM snapshot_view WHERE snapshot_id = :s AND scenario != '' AND scenario != :b"
                ),
                {"s": SNAP, "b": scs[0]},
            )
            c.execute(
                sa.text(
                    "DELETE FROM snapshot_view WHERE snapshot_id = :s AND kind IN ('report', 'report_diff')"
                ),
                {"s": SNAP},
            )
            for key in gone_cx:
                c.execute(
                    sa.text(
                        "DELETE FROM snapshot_view WHERE snapshot_id = :s AND kind = 'complex' AND scenario = :b AND key = :k"
                    ),
                    {"s": SNAP, "b": scs[0], "k": key},
                )
        kept = _rows(engine, SNAP)
        command.upgrade(cfg, "head")
        units = _units(engine, SNAP)
        assert units and not any(d for d, _r in units.values()), (
            "D16-2: 0012 이전 단위는 전부 미완(행 수 추정 없음)"
        )
        with Session(bind=engine) as s:
            assert pending_count(s) == 2  # 발행 11·12 둘 다
        reset_engine()
        res = backfill(engine, settings=settings)
        assert sorted(res["snapshots"]) == [11, SNAP] and not res["failed"], res
        after = _rows(engine, SNAP)
        assert set(after) == set(rows0), sorted(set(rows0) ^ set(after))[:10]
        assert all(after[k] == kept[k] for k in kept if k[0] != "provenance"), (
            "이미 있던 행은 발행 순간 바이트 그대로"
        )
        drawers1 = _drawers(engine, SNAP)
        assert rd0 <= set(drawers1), sorted(rd0 - set(drawers1))[:10]  # N-M1: rd_ 서랍이 채워졌다
        assert all(drawers1[k] == v for k, v in drawers0.items() if not k.startswith("rd_")), (
            "원래 서랍 본문 그대로"
        )
        assert all(d for d, _r in _units(engine).values())
        with Session(bind=engine) as s:
            assert pending_count(s) == 0
            snap = s.get(Snapshot, SNAP)
            assert snap is not None
            for pid in sorted(rd0)[:20]:
                assert provenance(s, snap, pid) is not None, pid
        assert backfill(engine, settings=settings)["snapshots"] == []

        # (2) m3: 행 있고 표식 없는 단위 → 미완(503) — 404 아님. backfill 은 표식만(바이트 그대로)
        before = _rows(engine, SNAP)
        with engine.begin() as c:
            c.execute(
                sa.text(
                    "DELETE FROM snapshot_view_unit WHERE snapshot_id = :s AND kind = 'dashboard' AND scenario = :sc"
                ),
                {"s": SNAP, "sc": scs[2]},
            )
        with Session(bind=engine) as s:
            from app.models import Scenario

            snap = s.get(Snapshot, SNAP)
            sc = s.get(Scenario, int(scs[2]))
            assert snap is not None and sc is not None
            with pytest.raises(MaterializePending):
                read(s, snap, "dashboard", scenario=sc)
            assert pending_count(s) == 1
        res = backfill(engine, settings=settings)
        assert res["snapshots"] == [SNAP] and res["rows"] == 0, res
        assert {k: v for k, v in _rows(engine, SNAP).items() if k[0] != "provenance"} == {
            k: v for k, v in before.items() if k[0] != "provenance"
        }
        assert _units(engine, SNAP)[(SNAP, "dashboard", scs[2])][0] is True

        # (3) .12 DB(0012 가 추정으로 done 을 찍은 좁은 서랍) + 파서 '확인됨' 할인 → head(0013)
        command.downgrade(cfg, "0012")
        _narrow_drawers(engine, SNAP)
        with engine.begin() as c:
            c.execute(sa.text("UPDATE snapshot_view_unit SET done = true"))
            raw_id = c.execute(
                sa.text("SELECT MIN(id) FROM raw_document WHERE source_kind = 'notice_pdf'")
            ).scalar()
            pt = c.execute(sa.text("SELECT MIN(id) FROM payment_terms")).scalar()
            ins = (
                "INSERT INTO field_provenance (entity, entity_id, field, value_text, value_norm, raw_document_id, url, "
                "checked_at, label, reason, source_rank, chosen) VALUES ('payment_terms', :pt, 'discount_by_type.84A', "
                "'1,200,000', '1200000', :raw, 'https://x', '2026-10-08', '확인됨', :reason, :rank, :chosen)"
            )
            c.execute(sa.text(ins), {"pt": pt, "raw": raw_id, "reason": None, "rank": 1, "chosen": False})
            c.execute(
                sa.text(ins), {"pt": pt, "raw": None, "reason": "사람 확인(phone)", "rank": 0, "chosen": True}
            )
        with Session(bind=engine) as s:
            assert pending_count(s) == 0, "0012 표식은 done(추정) — 좁은 서랍이 숨는다"
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            got = c.execute(
                sa.text(
                    "SELECT label, reason, raw_document_id FROM field_provenance WHERE field = 'discount_by_type.84A' ORDER BY id"
                )
            ).all()
        parser = [r for r in got if r[2] is not None]
        human = [r for r in got if r[2] is None]
        assert parser and all(r[0] == "추정" and "조건 확인 필요" in (r[1] or "") for r in parser), parser
        assert human and all(r[0] == "확인됨" and r[1] == "사람 확인(phone)" for r in human), human
        assert not any(d for d, _r in _units(engine).values()), "0013: 표식 재검증(전부 미완)"
        reset_engine()
        res = backfill(engine, settings=settings)
        assert not res["failed"], res
        assert rd0 <= set(_drawers(engine, SNAP))
        assert all(d for d, _r in _units(engine).values())

        # (4) 불변: 발행 뒤 생긴 단지는 옛 리비전 단지 상세 키가 되지 않는다(backfill 은 지운 키만)
        victim = base_cx[0]
        with engine.begin() as c:
            c.execute(
                sa.text(
                    "DELETE FROM snapshot_view WHERE snapshot_id = :s AND kind = 'complex' AND scenario = :b AND key = :k"
                ),
                {"s": SNAP, "b": scs[0], "k": victim},
            )
            c.execute(
                sa.text(
                    "UPDATE snapshot_view_unit SET done = false WHERE snapshot_id = :s AND kind = 'complex' AND scenario = :b"
                ),
                {"s": SNAP, "b": scs[0]},
            )
        with Session(bind=engine) as s, s.begin():
            cx = Complex(
                region_id=1, name="R3h 발행 뒤 단지", former_names=[], apply_dates=[], contract_dates=[]
            )
            s.add(cx)
            s.flush()
            new_id = str(cx.id)
        reset_engine()
        res = backfill(engine, settings=settings)
        assert not res["failed"], res
        keys = {key for (k, key, sc) in _rows(engine, SNAP) if k == "complex" and sc == scs[0]}
        assert victim in keys and new_id not in keys, (victim, new_id)
        assert keys == set(base_cx)

        # autogenerate diff 0
        with engine.connect() as c:
            ctx = MigrationContext.configure(c, opts={"compare_type": True})
            assert compare_metadata(ctx, Base.metadata) == []
    finally:
        set_settings(None)
        reset_engine()
        command.upgrade(cfg, "head")
        _wipe(engine)
        command.downgrade(cfg, "base")
        engine.dispose()


def test_sqlite_r3h_migrations_and_backfill(
    seeded_sqlite: Path,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_r3h_migrations(f"sqlite:///{(tmp_path / 'r3h.db').as_posix()}", seeded_sqlite, monkeypatch)


@pytest.mark.postgres
def test_postgres_r3h_migrations_and_backfill(seeded_sqlite: Path, postgres_url: str) -> None:  # noqa: F811
    mp = pytest.MonkeyPatch()
    try:
        check_r3h_migrations(postgres_url, seeded_sqlite, mp)
    finally:
        mp.undo()
