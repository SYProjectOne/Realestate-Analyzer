"""R5-OPS 3 (D25-1 major, D19-2): 백업 잡이 PATH 의 ``pg_dump`` 만 찾아 이 PC(PG17 이 PATH 에 없음)에서 매일 03:00 실패했다.

| 항목 | 테스트 |
| --- | --- |
| ``PG_DUMP_PATH``(실행 파일)를 쓰고 PATH 는 보지 않는다 | ``test_pg_dump_path_file_is_used_instead_of_path`` |
| ``PG_DUMP_PATH`` 가 bin 폴더면 그 안의 ``pg_dump(.exe)`` | ``test_pg_dump_path_directory`` |
| 설정한 경로에 없으면 실패 + 사유(PATH 로 조용히 넘어가지 않는다 — 다른 판 pg_dump 방지) | ``test_pg_dump_path_missing_fails_with_reason`` |
| 설정이 없고 PATH 에도 없으면 사유에 ``PG_DUMP_PATH`` 안내 | ``test_no_pg_dump_anywhere_mentions_setting`` |
| stats 에 쓴 pg_dump 경로·판(``--version``) — PG17 서버에 PG17 pg_dump 를 썼는지 G7 에서 확인 | ``test_pg_dump_path_file_is_used_instead_of_path`` |
| ``.env.example``·runbook §8 에 PG17 절차 | ``test_env_example_and_runbook_document_pg_dump_path`` |
"""

# ruff: noqa: E501  (한국어 assertion 메시지·표)

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from app.core.settings import Settings
from app.scheduler import backup as backup_mod
from app.scheduler.backup import run_backup

REPO = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 13, 3, 0)
PG_URL = "postgresql+psycopg://sa:s3cret%40pw@127.0.0.1:5434/subscription_analyzer"


def _fake_pg_dump(bin_dir: Path, seen: Path, *, name: str = "pg_dump") -> Path:
    """가짜 pg_dump — ``--version`` 은 판을 찍고, 덤프는 PGPASSWORD·argv[0] 을 적고 덤프 파일을 만든다."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "fake_pg_dump.py"
    script.write_text(
        "import os, sys, pathlib\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('pg_dump (PostgreSQL) 17.9'); sys.exit(0)\n"
        f"pathlib.Path({str(seen)!r}).write_text(os.environ.get('PGPASSWORD', ''), encoding='utf-8')\n"
        "out = sys.argv[sys.argv.index('-f') + 1]\n"
        "pathlib.Path(out).write_bytes(b'PGDMP')\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        exe = bin_dir / f"{name}.cmd"
        exe.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        exe = bin_dir / name
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        exe.chmod(0o755)
    return exe


def _pg(settings: Settings, tmp_path: Path, **update: Any) -> Settings:
    return settings.model_copy(update={"database_url": PG_URL, "backup_dir": tmp_path / "backup", **update})


def test_pg_dump_path_file_is_used_instead_of_path(
    test_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = tmp_path / "seen.txt"
    exe = _fake_pg_dump(tmp_path / "pg17" / "bin", seen)
    # PATH 에는 '틀린 판' pg_dump 가 있다 — 불리면 덤프 대신 표식을 남긴다
    wrong = tmp_path / "wrong.txt"
    _fake_pg_dump(tmp_path / "path_bin", wrong)
    monkeypatch.setenv("PATH", f"{tmp_path / 'path_bin'}{os.pathsep}{os.environ.get('PATH', '')}")
    stats = run_backup(_pg(test_settings, tmp_path, pg_dump_path=exe), now=NOW)
    assert stats["db"]["kind"] == "postgres" and stats["db"]["file"] == "db.dump"
    assert seen.read_text(encoding="utf-8") == "s3cret@pw"
    assert not wrong.exists(), "PG_DUMP_PATH 가 있는데 PATH 의 pg_dump 를 불렀다"
    assert stats["db"]["pg_dump"] == str(exe)
    assert stats["db"]["pg_dump_version"] == "pg_dump (PostgreSQL) 17.9"
    assert "s3cret" not in str(stats), "비밀번호는 stats 에 없다"


def test_pg_dump_path_directory(test_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``PG_DUMP_PATH=C:\\Program Files\\PostgreSQL\\17\\bin`` 처럼 폴더를 줘도 된다 — 그 안의 ``pg_dump.exe``/``pg_dump``."""
    bin_dir = tmp_path / "PostgreSQL" / "17" / "bin"
    bin_dir.mkdir(parents=True)
    exe = bin_dir / ("pg_dump.exe" if os.name == "nt" else "pg_dump")
    exe.write_bytes(b"")
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        if argv[1:] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, "pg_dump (PostgreSQL) 17.9\n", "")
        Path(argv[argv.index("-f") + 1]).write_bytes(b"PGDMP")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(backup_mod.subprocess, "run", fake_run)
    stats = run_backup(_pg(test_settings, tmp_path, pg_dump_path=bin_dir), now=NOW)
    assert calls and all(c[0] == str(exe) for c in calls)
    assert stats["db"]["pg_dump"] == str(exe)
    dump_argv = next(c for c in calls if "-f" in c)
    assert "s3cret" not in " ".join(dump_argv), "비밀번호는 argv 에 없다(PGPASSWORD 로만)"


def test_pg_dump_path_missing_fails_with_reason(
    test_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "wrong.txt"
    _fake_pg_dump(tmp_path / "path_bin", wrong)
    monkeypatch.setenv("PATH", f"{tmp_path / 'path_bin'}{os.pathsep}{os.environ.get('PATH', '')}")
    missing = tmp_path / "nope" / "pg_dump.exe"
    with pytest.raises(RuntimeError, match="PG_DUMP_PATH") as err:
        run_backup(_pg(test_settings, tmp_path, pg_dump_path=missing), now=NOW)
    stats = err.value.stats  # type: ignore[attr-defined]
    assert "PG_DUMP_PATH" in stats["db"]["error"]
    assert not wrong.exists(), "설정한 pg_dump 가 없을 때 PATH 의 다른 판으로 넘어갔다"


def test_no_pg_dump_anywhere_mentions_setting(
    test_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backup_mod.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError) as err:
        run_backup(_pg(test_settings, tmp_path), now=NOW)
    reason = err.value.stats["db"]["error"]  # type: ignore[attr-defined]
    assert "PATH" in reason and "PG_DUMP_PATH" in reason


def test_env_example_and_runbook_document_pg_dump_path() -> None:
    example = (REPO / "infra" / ".env.example").read_text(encoding="utf-8")
    assert any(line.startswith("PG_DUMP_PATH=") for line in example.splitlines())
    runbook = (REPO / "docs" / "runbook.md").read_text(encoding="utf-8")
    start = runbook.index("## 8. 백업")
    sec8 = runbook[start : runbook.index("\n## 9.", start)]
    for needle in ("PG_DUMP_PATH", "D19", r"PostgreSQL\17\bin", "pg_dump_version", "--version"):
        assert needle in sec8, f"runbook §8 에 {needle!r} 없음"
