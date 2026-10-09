"""월별 목록·공고·경쟁률 원문 보관 (WP2, RA §5 WP2 카드 · DECISIONS D1-14).

원문 파일은 이미 ``RAW_DIR/{source}/{yyyy-mm-dd}/{sha256}.{ext}``에 멱등 저장돼 있다(WP1). 여기서는
- 달마다 청약홈 목록·상세·경쟁률·공고문 원문의 색인(manifest.json)을 ``RAW_DIR/archive/{yyyy-mm}/``에 남기고,
- 디스크가 부족할 때를 위해 같은 달 원문을 결정적(zip 안 파일 순서·시각 고정) ``{yyyy-mm}.zip``으로 묶는다.
원문을 지우지 않는다(보존 무기한). 같은 입력이면 manifest·zip 바이트가 같다(재실행해도 바뀌지 않음).
``archived_notices``는 벤치마크 분양가를 '자체 아카이브 공고 우선'(RA §3)으로 찾을 때 쓴다.
"""

from __future__ import annotations

import json
import re
import zipfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.paths import resolve_raw_path
from app.core.settings import get_settings
from app.models import Complex, RawDocument

__all__ = [
    "ARCHIVE_SOURCES",
    "ArchiveEntry",
    "ArchiveManifest",
    "archive_kind",
    "archived_notices",
    "archived_notices_many",
    "build_month_manifest",
    "write_month_archive",
]

_HM_RE = re.compile(r"houseManageNo=(\d+)")
ARCHIVE_SOURCES = ("applyhome_list", "applyhome_detail", "notice_pdf")
_ZIP_TIME = (2000, 1, 1, 0, 0, 0)


def archive_kind(source_kind: str, url: str) -> str | None:
    """원문 → 보관 분류('목록'·'경쟁률'·'상세'·'공고'). 보관 대상이 아니면 None."""
    if source_kind == "applyhome_list":
        return "목록"
    if source_kind == "applyhome_detail":
        return "경쟁률" if "Competition" in url else "상세"
    if source_kind == "notice_pdf":
        return "공고"
    return None


@dataclass(frozen=True)
class ArchiveEntry:
    raw_document_id: int
    kind: str
    source_kind: str
    url: str
    fetched_at: str
    sha256: str
    path: str
    text_path: str | None
    complex_id: int | None


@dataclass
class ArchiveManifest:
    ym: str
    entries: list[ArchiveEntry] = field(default_factory=list)
    manifest_path: Path | None = None
    zip_path: Path | None = None
    missing_files: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.entries:
            out[e.kind] = out.get(e.kind, 0) + 1
        return out

    def to_json(self) -> str:
        doc = {"ym": self.ym, "counts": self.counts(), "entries": [asdict(e) for e in self.entries]}
        return json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def build_month_manifest(session: Session, ym: str, *, region_id: int | None = None) -> ArchiveManifest:
    """그 달(fetched_at의 YYYY-MM)에 받은 성공 원문(path 있음) 중 목록·상세·경쟁률·공고."""
    stmt = select(RawDocument).where(
        RawDocument.source_kind.in_(ARCHIVE_SOURCES),
        RawDocument.fetched_at.like(f"{ym}%"),
        RawDocument.path.is_not(None),
    )
    if region_id is not None:
        stmt = stmt.where(RawDocument.region_id == region_id)
    entries: list[ArchiveEntry] = []
    for r in session.scalars(stmt):
        kind = archive_kind(r.source_kind, r.url)
        if kind is None or r.path is None:
            continue
        if r.http_status not in (None, 200):
            continue
        entries.append(
            ArchiveEntry(
                raw_document_id=r.id,
                kind=kind,
                source_kind=r.source_kind,
                url=r.url,
                fetched_at=r.fetched_at,
                sha256=r.sha256,
                path=r.path,
                text_path=r.text_path,
                complex_id=r.complex_id,
            )
        )
    entries.sort(key=lambda e: (e.fetched_at, e.sha256))
    return ArchiveManifest(ym=ym, entries=entries)


def write_month_archive(
    session: Session,
    ym: str,
    *,
    raw_dir: Path | None = None,
    region_id: int | None = None,
    compress: bool = False,
) -> ArchiveManifest:
    """manifest.json을 쓰고(내용이 같으면 그대로), compress=True면 원문을 결정적 zip으로 묶는다."""
    base = raw_dir if raw_dir is not None else get_settings().raw_dir
    man = build_month_manifest(session, ym, region_id=region_id)
    out_dir = base / "archive" / ym
    out_dir.mkdir(parents=True, exist_ok=True)
    mpath = out_dir / "manifest.json"
    data = man.to_json()
    if not mpath.exists() or mpath.read_text(encoding="utf-8") != data:
        mpath.write_text(data, encoding="utf-8", newline="\n")
    man.manifest_path = mpath
    if compress:
        zpath = base / "archive" / f"{ym}.zip"
        tmp = zpath.with_suffix(".zip.part")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel in sorted({p for e in man.entries for p in (e.path, e.text_path) if p}):
                src = resolve_raw_path(rel, raw_dir=base)
                if not src.exists():
                    man.missing_files.append(rel)
                    continue
                info = zipfile.ZipInfo(rel, date_time=_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, src.read_bytes())
            info = zipfile.ZipInfo("manifest.json", date_time=_ZIP_TIME)
            zf.writestr(info, data.encode("utf-8"))
        if zpath.exists() and zpath.read_bytes() == tmp.read_bytes():
            tmp.unlink()
        else:
            tmp.replace(zpath)
        man.zip_path = zpath
    return man


def archived_notices(
    session: Session, applyhome_id: str, *, region_id: int | None = None
) -> list[RawDocument]:
    """그 단지(주택관리번호)의 보관 공고문 원문 — 오래된 것부터.

    무순위·임의공급 공고(다른 번호)는 complex_id로 찾는다. ``region_id`` 를 주면 그 지역의 단지 행만 본다
    (R3 W4: 다른 지역 단지의 원문이 섞이지 않게).
    """
    stmt_cx = select(Complex).where(Complex.applyhome_id == applyhome_id)
    if region_id is not None:
        stmt_cx = stmt_cx.where(Complex.region_id == region_id)
    cx = session.scalars(stmt_cx).first()
    stmt = select(RawDocument).where(RawDocument.source_kind == "notice_pdf", RawDocument.path.is_not(None))
    rows = [
        r
        for r in session.scalars(stmt)
        if (region_id is None or r.region_id in (None, region_id))
        and (f"houseManageNo={applyhome_id}" in r.url or (cx is not None and r.complex_id == cx.id))
    ]
    rows.sort(key=lambda r: (r.fetched_at, r.id))
    return rows


def archived_notices_many(
    session: Session, applyhome_ids: Iterable[str], *, region_id: int
) -> dict[str, list[RawDocument]]:
    """``archived_notices`` 를 여러 주택관리번호에 한 번에(쿼리 2개 — 단지 수와 무관, 벤치마크 N+1 방지).

    같은 규칙: URL 의 ``houseManageNo=`` 또는 그 지역 단지 행의 complex_id. 번호마다 오래된 것부터."""
    ids = sorted(set(applyhome_ids))
    out: dict[str, list[RawDocument]] = {hm: [] for hm in ids}
    if not ids:
        return out
    cx_hm: dict[int, str] = {}
    for cx in session.scalars(
        select(Complex)
        .where(Complex.applyhome_id.in_(ids), Complex.region_id == region_id)
        .order_by(Complex.id)
    ):
        cx_hm.setdefault(cx.id, str(cx.applyhome_id))
    by_cx: dict[int, str] = {}
    for cid, hm in cx_hm.items():
        if hm not in by_cx.values():
            by_cx[cid] = hm  # archived_notices 와 같이 번호마다 첫 단지 행
    stmt = select(RawDocument).where(RawDocument.source_kind == "notice_pdf", RawDocument.path.is_not(None))
    for r in session.scalars(stmt):
        if r.region_id not in (None, region_id):
            continue
        hits = {m for m in _HM_RE.findall(r.url or "") if m in out}
        if r.complex_id is not None and r.complex_id in by_cx:
            hits.add(by_cx[r.complex_id])
        for hm in hits:
            out[hm].append(r)
    for rows in out.values():
        rows.sort(key=lambda r: (r.fetched_at, r.id))
    return out
