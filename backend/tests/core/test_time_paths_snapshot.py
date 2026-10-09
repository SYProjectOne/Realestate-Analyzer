from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path, PurePosixPath

import pytest

from app.core.paths import raw_path, raw_relpath, resolve_raw_path
from app.core.snapshot import (
    base_date,
    canonical_json,
    sha256_bytes,
    sha256_file,
    sha256_text,
    store_raw,
)
from app.core.time import KST, add_days, d_day, format_d_day, now_kst, to_kst, today_kst

SHA = "0123456789abcdef" * 4


# ---------------------------------------------------------------- time


def test_today_kst_crosses_midnight() -> None:
    # UTC 16:00 = KST 다음날 01:00
    assert today_kst(datetime(2026, 10, 8, 16, 0, tzinfo=UTC)) == date(2026, 10, 9)
    assert today_kst(datetime(2026, 10, 8, 14, 59, tzinfo=UTC)) == date(2026, 10, 8)


def test_to_kst_and_now() -> None:
    k = to_kst(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    assert k.utcoffset() == timedelta(hours=9)
    assert k.hour == 9
    assert now_kst().utcoffset() == timedelta(hours=9)
    with pytest.raises(ValueError):
        to_kst(datetime(2026, 1, 1))  # naive 금지


def test_kst_is_asia_seoul() -> None:
    assert datetime(2026, 7, 1, tzinfo=KST).utcoffset() == timedelta(hours=9)


def test_d_day() -> None:
    base = date(2026, 10, 9)
    assert d_day(date(2026, 10, 12), base) == 3
    assert d_day(date(2026, 10, 9), base) == 0
    assert d_day(date(2026, 10, 7), base) == -2
    assert format_d_day(date(2026, 10, 12), base) == "D-3"
    assert format_d_day(date(2026, 10, 9), base) == "D-day"
    assert format_d_day(date(2026, 10, 7), base) == "D+2"
    assert add_days(base, -10) == date(2026, 9, 29)


def test_base_date_matches_today_kst() -> None:
    now = datetime(2026, 10, 8, 23, 30, tzinfo=UTC)
    assert base_date(now) == date(2026, 10, 9)


# ---------------------------------------------------------------- paths (ADR-8)


def test_raw_path_layout(tmp_path: Path) -> None:
    p = raw_path("applyhome_list", date(2026, 10, 9), SHA, ".HTML", raw_dir=tmp_path)
    assert p == tmp_path / "applyhome_list" / "2026-10-09" / f"{SHA}.html"
    assert raw_relpath("notice_pdf", date(2026, 10, 9), SHA, "pdf") == PurePosixPath(
        f"notice_pdf/2026-10-09/{SHA}.pdf"
    )


def test_raw_path_uses_settings_raw_dir(test_settings: object, raw_dir: Path) -> None:
    p = raw_path("official_site", date(2026, 1, 2), SHA, "png")
    assert p.parent.parent.parent == raw_dir


@pytest.mark.parametrize(
    ("source", "sha", "ext"),
    [
        ("../etc", SHA, "html"),
        ("Apply Home", SHA, "html"),
        ("", SHA, "html"),
        ("applyhome", "XYZ", "html"),
        ("applyhome", SHA.upper(), "html"),
        ("applyhome", SHA, "ht/ml"),
        ("applyhome", SHA, ""),
    ],
)
def test_raw_path_validation(tmp_path: Path, source: str, sha: str, ext: str) -> None:
    with pytest.raises(ValueError):
        raw_path(source, date(2026, 10, 9), sha, ext, raw_dir=tmp_path)


def test_resolve_raw_path_blocks_traversal(tmp_path: Path) -> None:
    ok = resolve_raw_path(f"applyhome/2026-10-09/{SHA}.html", raw_dir=tmp_path)
    assert ok == tmp_path / "applyhome" / "2026-10-09" / f"{SHA}.html"
    for bad in ["../secret.txt", "/etc/passwd", "a/../../x", "C:/Windows/x"]:
        with pytest.raises(ValueError):
            resolve_raw_path(bad, raw_dir=tmp_path)


# ---------------------------------------------------------------- snapshot


def test_sha256_helpers(tmp_path: Path) -> None:
    expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert sha256_bytes(b"hello") == expected
    assert sha256_text("hello") == expected
    f = tmp_path / "f.bin"
    f.write_bytes(b"hello")
    assert sha256_file(f) == expected


def test_canonical_json_stable_and_korean() -> None:
    a = canonical_json({"b": 1, "a": "송도", "c": [1, 2]})
    b = canonical_json({"c": [1, 2], "a": "송도", "b": 1})
    assert a == b == '{"a":"송도","b":1,"c":[1,2]}'


def test_store_raw_idempotent(raw_dir: Path) -> None:
    day = date(2026, 10, 9)
    first = store_raw(b"<html>1</html>", source="applyhome_list", day=day, ext="html")
    assert first.created is True
    assert first.sha256 == sha256_bytes(b"<html>1</html>")
    assert first.size == len(b"<html>1</html>")
    assert first.path.read_bytes() == b"<html>1</html>"
    assert first.path == raw_dir / "applyhome_list" / "2026-10-09" / f"{first.sha256}.html"
    assert first.relpath == f"applyhome_list/2026-10-09/{first.sha256}.html"

    second = store_raw(b"<html>1</html>", source="applyhome_list", day=day, ext="html")
    assert second.created is False
    assert second.path == first.path
    assert len(list(first.path.parent.iterdir())) == 1  # 임시 파일 남지 않음


def test_store_raw_explicit_dir(tmp_path: Path) -> None:
    r = store_raw(b"x", source="stats", day=date(2026, 1, 1), ext="csv", raw_dir=tmp_path)
    assert r.path.is_relative_to(tmp_path)
