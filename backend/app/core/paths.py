"""원문 저장 경로 (RA ADR-8): ``{RAW_DIR}/{source}/{yyyy-mm-dd}/{sha256}.{ext}``.

DB(``raw_document``)에는 RAW_DIR 기준 상대 경로(POSIX 문자열)를 저장하고, 읽을 때
``resolve_raw_path`` 로 절대 경로를 만든다 — 개발(./data/raw)과 컨테이너(/data/raw)가 같은 행을 쓴다.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath

from app.core.settings import get_settings

SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXT_RE = re.compile(r"^[a-z0-9]{1,10}$")


def _check(source: str, sha256: str, ext: str) -> str:
    if not SOURCE_RE.fullmatch(source) or ".." in source:
        raise ValueError(f"source 형식 오류: {source!r} (소문자·숫자·_.- 만)")
    if not SHA256_RE.fullmatch(sha256):
        raise ValueError(f"sha256 형식 오류: {sha256!r} (소문자 hex 64자)")
    norm = ext.lstrip(".").lower()
    if not EXT_RE.fullmatch(norm):
        raise ValueError(f"확장자 형식 오류: {ext!r}")
    return norm


def raw_relpath(source: str, day: date, sha256: str, ext: str) -> PurePosixPath:
    norm = _check(source, sha256, ext)
    return PurePosixPath(source, day.isoformat(), f"{sha256}.{norm}")


def raw_path(source: str, day: date, sha256: str, ext: str, *, raw_dir: Path | None = None) -> Path:
    base = raw_dir if raw_dir is not None else get_settings().raw_dir
    return base.joinpath(*raw_relpath(source, day, sha256, ext).parts)


def resolve_raw_path(relpath: str, *, raw_dir: Path | None = None) -> Path:
    """DB 의 상대 경로 → 절대 경로. 절대 경로·드라이브·``..`` 는 거부한다."""
    if PureWindowsPath(relpath).drive or PurePosixPath(relpath).is_absolute() or relpath.startswith("\\"):
        raise ValueError(f"절대 경로는 허용하지 않는다: {relpath!r}")
    parts = PurePosixPath(relpath.replace("\\", "/")).parts
    if not parts or any(p in {"..", "."} for p in parts):
        raise ValueError(f"경로 탈출 금지: {relpath!r}")
    base = raw_dir if raw_dir is not None else get_settings().raw_dir
    return base.joinpath(*parts)


def reference_dir() -> Path:
    return get_settings().reference_dir


def report_dir() -> Path:
    return get_settings().report_dir
