"""백업 잡 (DECISIONS D11-8, 계약 2026-10-09.8 ``backup`` — RA §10 '백업은 pg_dump 일 1회 + rawdata 증분').

worker 시간표가 매일 03:00 ``backup`` 잡을 넣고(``scheduler.jobs.CRON``) runner 가 이 함수를 돌린다. 결과는 job_run.stats.

- DB: Postgres 면 ``pg_dump -Fc``(사용자 지정 형식 — pg_restore 로 골라 복구) → ``<BACKUP_DIR>/<날짜>/db.dump``.
  SQLite(개발 모드)면 sqlite3 온라인 백업 API 로 ``db.sqlite3`` 파일 복사(쓰기 중이어도 일관된 사본).
  pg_dump 가 없거나 실패하면 잡은 failed(stats 에 사유) — 조용히 넘어가지 않는다(규칙 7).
- 원문: ``RAW_DIR`` → ``<BACKUP_DIR>/raw/`` 증분 복사(크기·수정 시각이 다른 파일만, 지우지 않는다 — 보존 무기한).
- 보존: payload ``keep_days`` 가 있으면 그보다 오래된 날짜 폴더만 지운다(원문 사본은 지우지 않는다). 기본은 지우지 않는다.

``BACKUP_DIR`` 은 환경변수(없으면 RAW_DIR 의 상위 폴더 아래 ``backup``). DB URL 의 비밀번호는 로그·stats 에 남기지 않는다
(pg_dump 에는 PGPASSWORD 환경변수로 넘긴다).
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import unquote, urlsplit, urlunsplit

from app.core.settings import Settings

__all__ = ["KEEP_DAYS_MAX", "backup_dir", "run_backup"]

KEEP_DAYS_MAX = 3650
"""보존 일수 상한(계약 .9 ``job_payloads/backup.json`` maximum) — 넘으면 잡 실패(조용히 자르지 않는다)."""


def backup_dir(settings: Settings) -> Path:
    """백업 위치: 설정 ``BACKUP_DIR``(환경변수·``.env`` — Settings), 비면 RAW_DIR 상위 폴더 아래 ``backup/``."""
    configured = getattr(settings, "backup_dir", None)
    if configured is not None and str(configured).strip() not in ("", "."):
        return Path(configured)
    env = os.environ.get("BACKUP_DIR")  # Settings 를 거치지 않은 호출(테스트 SimpleNamespace 등) 호환
    if env:
        return Path(env)
    return Path(settings.raw_dir).resolve().parent / "backup"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sqlite_path(url: str) -> Path | None:
    if not url.startswith("sqlite"):
        return None
    tail = url.split(":///", 1)[1] if ":///" in url else ""
    return Path(tail) if tail and tail != ":memory:" else None


def _dump_sqlite(src: Path, out: Path) -> dict[str, Any]:
    dst = out / "db.sqlite3"
    with sqlite3.connect(str(src)) as s_conn, sqlite3.connect(str(dst)) as d_conn:
        s_conn.backup(d_conn)
    return {"kind": "sqlite", "file": dst.name, "size_bytes": dst.stat().st_size, "sha256": _sha256(dst)}


def _dump_postgres(url: str, out: Path) -> dict[str, Any]:
    exe = shutil.which("pg_dump")
    if exe is None:
        raise RuntimeError("pg_dump 없음(PATH) — Postgres 백업 불가")
    parts = urlsplit(url.replace("postgresql+psycopg://", "postgresql://"))
    # URL 의 비밀번호는 퍼센트 인코딩(예 '%40' = '@') — PGPASSWORD 에는 원래 문자로(R3 4차 minor)
    password = unquote(parts.password or "")
    netloc = parts.hostname or ""
    if parts.username:
        netloc = f"{parts.username}@{netloc}"
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    safe = urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))
    dst = out / "db.dump"
    env = {**os.environ, "PGPASSWORD": password} if password else dict(os.environ)
    proc = subprocess.run(
        [exe, "-Fc", "--dbname", safe, "-f", str(dst)], capture_output=True, text=True, env=env, timeout=3600
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump 실패(exit {proc.returncode}): {proc.stderr.strip()[:200]}")
    return {"kind": "postgres", "file": dst.name, "size_bytes": dst.stat().st_size, "sha256": _sha256(dst)}


def _copy_raw(src: Path, mirror: Path) -> dict[str, int]:
    """증분 복사: 크기·수정 시각이 같은 파일은 건너뛴다. 사본에만 있는 파일은 지우지 않는다(보존 무기한)."""
    copied = skipped = 0
    if not src.is_dir():
        return {"copied": 0, "skipped": 0, "files": 0}
    for path in src.rglob("*"):
        if not path.is_file() or path.name.startswith(".tmp-"):
            continue
        rel = path.relative_to(src)
        dst = mirror / rel
        st = path.stat()
        if dst.is_file():
            dt = dst.stat()
            if dt.st_size == st.st_size and int(dt.st_mtime) == int(st.st_mtime):
                skipped += 1
                continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
        copied += 1
    return {"copied": copied, "skipped": skipped, "files": copied + skipped}


def _prune(root: Path, today: date, keep_days: int) -> list[str]:
    removed: list[str] = []
    limit = today - timedelta(days=keep_days)
    for child in sorted(root.iterdir()) if root.is_dir() else []:
        try:
            day = date.fromisoformat(child.name)
        except ValueError:
            continue  # raw/ 등 날짜 폴더가 아닌 것
        if child.is_dir() and day < limit:
            shutil.rmtree(child)
            removed.append(child.name)
    return removed


def run_backup(settings: Settings, *, now: datetime, keep_days: int | None = None) -> dict[str, Any]:
    """백업 1회(모듈 설명). stats(dict)를 돌려준다. DB 백업이 실패하면 ``RuntimeError``(stats 는 예외의 ``stats``)."""
    root = backup_dir(settings)
    day = now.date()
    stats: dict[str, Any] = {"backup_dir": str(root), "day": day.isoformat()}
    if keep_days is not None and not 1 <= keep_days <= KEEP_DAYS_MAX:
        _fail(stats, f"keep_days 는 1~{KEEP_DAYS_MAX}: {keep_days}")
    out = root / day.isoformat()
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # R3 4차 minor: 폴더를 못 만들어도 stats(사유)를 남긴다
        _fail(stats, f"백업 폴더를 만들 수 없다: {exc}", exc)
    url = settings.database_url
    try:
        sqlite_file = _sqlite_path(url)
        if sqlite_file is not None:
            stats["db"] = _dump_sqlite(sqlite_file, out)
        elif url.startswith(("postgresql", "postgres")):
            stats["db"] = _dump_postgres(url, out)
        else:
            raise RuntimeError("알 수 없는 DATABASE_URL 형식 — 백업 불가")
    except Exception as exc:
        stats["db"] = {"error": str(exc)[:300]}
        err = RuntimeError(f"DB 백업 실패: {str(exc)[:200]}")
        err.stats = stats  # type: ignore[attr-defined]
        raise err from exc
    try:
        stats["raw"] = _copy_raw(Path(settings.raw_dir), root / "raw")
        if keep_days:
            stats["pruned"] = _prune(root, day, keep_days)
    except OSError as exc:  # 디스크 가득·권한 등 — DB 백업 결과와 함께 failed(stats 유지)
        stats["raw_error"] = str(exc)[:300]
        _fail(stats, f"원문 복사·정리 실패: {exc}", exc)
    return stats


def _fail(stats: dict[str, Any], message: str, cause: BaseException | None = None) -> NoReturn:
    """``RuntimeError``(+ ``.stats``) — 처리 함수(``handle_backup``)가 stats 와 함께 failed 로 남긴다."""
    err = RuntimeError(message[:300])
    err.stats = stats  # type: ignore[attr-defined]
    if cause is not None:
        raise err from cause
    raise err
