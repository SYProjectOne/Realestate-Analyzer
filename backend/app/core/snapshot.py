"""스냅샷 유틸: sha256, 정규 JSON, 기준일, 원문 저장(멱등).

스냅샷 행·ID 형식은 계약(``contracts/``, ``app.models``)이 정한다. 여기는 계산 도구만 둔다.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.core.paths import raw_path, raw_relpath
from app.core.time import add_days, d_day, format_d_day, today_kst

__all__ = [
    "StoredRaw",
    "add_days",
    "base_date",
    "canonical_json",
    "d_day",
    "format_d_day",
    "sha256_bytes",
    "sha256_file",
    "sha256_text",
    "store_raw",
]

_CHUNK = 1 << 20


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    """키 정렬·공백 없음·UTF-8 그대로. 같은 값 = 같은 문자열(해시 키용)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def base_date(now: datetime | None = None) -> date:
    """기준일(Asia/Seoul)."""
    return today_kst(now)


@dataclass(frozen=True, slots=True)
class StoredRaw:
    path: Path
    relpath: str  # RAW_DIR 기준 POSIX 경로 (DB 저장용)
    sha256: str
    size: int
    created: bool  # False = 같은 내용이 이미 있었다(멱등)


def store_raw(
    content: bytes,
    *,
    source: str,
    day: date,
    ext: str,
    raw_dir: Path | None = None,
) -> StoredRaw:
    """원문을 sha256 경로에 저장한다. 이미 있으면 쓰지 않는다. 쓰기는 임시 파일 → rename(원자적)."""
    digest = sha256_bytes(content)
    rel = raw_relpath(source, day, digest, ext)
    path = raw_path(source, day, digest, ext, raw_dir=raw_dir)
    if path.exists():
        return StoredRaw(path, rel.as_posix(), digest, len(content), created=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return StoredRaw(path, rel.as_posix(), digest, len(content), created=True)
