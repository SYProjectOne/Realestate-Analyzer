"""월별 압축 원문 읽기 (runbook §6 · ``infra/raw_archive.sh``) — API(GET /raw/{id})와 정규화(공고문 재파싱)가 같이 쓴다.

R3 4차 minor: 정규화의 '자체 아카이브 공고문 우선' 분양가(``normalize.benchmark._archive_price``)가 압축된 원문을 못 읽고
조용히 청약홈 API 값으로 폴백했다 — 원문 읽기(``normalize._text.read_raw_text``)도 원본 파일이 없으면 이 압축에서 읽는다.
"""

# ruff: noqa: E501

from __future__ import annotations

import functools
import re
import tarfile
from collections.abc import Iterator
from pathlib import Path as FsPath
from pathlib import PurePosixPath
from typing import IO

__all__ = ["archived_member", "archived_stream"]

_MONTH_ARCHIVE = re.compile(r"^\d{4}-\d{2}\.tar\.gz$")


_CHUNK = 64 * 1024


def _open_member(archive: FsPath, member: str) -> tuple[tarfile.TarFile, IO[bytes]] | None:
    """압축을 스트림 모드("r|gz")로 열어 구성원을 찾는다 — 압축 전체를 풀거나 목록 전체를 먼저 읽지 않는다.

    찾으면 (열린 tar, 구성원 파일)을 돌려준다 — 닫는 것은 ``_chunks`` 가 다 흘린 뒤에."""
    tar = tarfile.open(archive, "r|gz")  # noqa: SIM115 — 응답 스트림이 끝날 때 _chunks 가 닫는다
    try:
        for info in tar:
            if info.name != member or not info.isfile():
                continue
            fh = tar.extractfile(info)
            if fh is not None:
                return tar, fh
    except BaseException:
        tar.close()
        raise
    tar.close()
    return None


@functools.lru_cache(maxsize=64)
def _members(archive: str, mtime_ns: int, size: int) -> frozenset[str]:
    """압축 구성원 이름 목록 — (경로, 수정 시각, 크기)마다 한 번만 훑는다(R3 3차 minor 17: 원본이 없을 때
    요청마다 압축 전체를 훑던 CPU 부담 — 공유 토큰으로 반복 요청 가능). 압축이 바뀌면 다시 훑는다."""
    del mtime_ns, size  # 캐시 키
    names: set[str] = set()
    with tarfile.open(archive, "r|gz") as tar:
        for info in tar:
            if info.isfile():
                names.add(info.name)
    return frozenset(names)


def _has_member(archive: FsPath, member: str) -> bool:
    st = archive.stat()
    return member in _members(str(archive), st.st_mtime_ns, st.st_size)


def _chunks(tar: tarfile.TarFile, fh: IO[bytes]) -> Iterator[bytes]:
    try:
        while chunk := fh.read(_CHUNK):
            yield chunk
    finally:
        tar.close()


def archived_stream(rel: str, raw_dir: FsPath) -> Iterator[bytes] | None:
    """월별 압축(runbook §6 · ``infra/raw_archive.sh``) 안의 원문을 64KiB 조각으로 흘린다(재리뷰 F3).

    압축 = ``<RAW_DIR>/<source>/<yyyy-mm>.tar.gz``,
    구성원 이름 = RAW_DIR 기준 상대 경로(DB 의 ``path`` 그대로).
    같은 달 압축을 먼저, 없으면 그 소스의 다른 압축(*.tar.gz)을 본다. 없으면 None.
    요청마다 구성원 전체를 메모리에 올리지 않는다(전에는 ``getmember`` 로 목록 전체 + ``read()`` 전체)."""
    parts = PurePosixPath(rel.replace("\\", "/")).parts
    if len(parts) < 2:
        return None
    src_dir = raw_dir / parts[0]
    if not src_dir.is_dir():
        return None
    month = parts[1][:7] if len(parts) >= 3 else None
    archives = sorted(src_dir.glob("*.tar.gz"))
    archives.sort(key=lambda a: (a.name != f"{month}.tar.gz", not _MONTH_ARCHIVE.match(a.name), a.name))
    member = PurePosixPath(*parts).as_posix()
    for archive in archives:
        try:
            if not _has_member(archive, member):
                continue  # 목록(캐시)에 없으면 압축을 풀지 않는다
            opened = _open_member(archive, member)
        except (OSError, tarfile.TarError, EOFError):
            continue
        if opened is not None:
            return _chunks(*opened)
    return None


def archived_member(rel: str, raw_dir: FsPath) -> bytes | None:
    """``archived_stream`` 을 모두 읽은 바이트(작은 원문·테스트용)."""
    stream = archived_stream(rel, raw_dir)
    return None if stream is None else b"".join(stream)
