"""재정규화 멱등성 속성 테스트(D23-1, R4-CORE10) 공용 — 녹화 원문 재생 수집기 · DB 스냅샷 · 차이.

재생 세트(``ReplaySet``)는 매니페스트 하나다(``docs.json`` · 녹화 zip · CORE8/CORE9 그룹 녹화 · R4 1차 녹화를 같은 모양으로)::

    {"asof": "2026-10-13", "region": {...}, "legal_dong": [...],
     "docs": {"applyhome": [...], "originals": {"<주택관리번호>": [...]}, "notice_pdf": [...], "official_site": [...],
              "news": [...]},
     "raw_root": "<선택 — 없으면 매니페스트 옆 raw/>"}

``news``(R4-CORE11, D24-1)는 주간 단계 뉴스 원문이다 — 첫 수집 전체(일일·주간·판정) 속성 테스트가 쓴다. 매니페스트에 없으면
``with_default_news`` 가 저장소 녹화(``fixtures/r4_news_2026-10-12.json`` — R4 1차 뉴스 검색 원문 4항목)를 붙인다.

행은 ``raw_document`` 열(id 는 녹화 당시 값 — 넣을 때 버린다). 공식 홈페이지 행은 ``house_no``(그 단지 주택관리번호)로 재생 DB
의 단지에 단다(녹화 당시 단지 id 는 재생 DB 와 다르다). 원문 파일은 ``raw_root`` 아래 상대 경로다.

DB 스냅샷(``db_state``)은 실행·리비전마다 새로 생기는 운영 기록(``RUN_TABLES``)을 뺀 **모든 테이블의 모든 행·모든 열**이다
(새 테이블은 자동으로 비교 대상 — 빼려면 사유와 함께 ``RUN_TABLES`` 에 적는다). 리비전마다 복사되는 접수 상태 행은 리비전
id·행 id 를 뺀 내용으로 비교한다(``intake_view``).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
import random
import shutil
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.models import Base, Complex, IntakeStatus, LegalDong, RawDocument, Region
from app.normalize.store import raw_dto

from .conftest import seed_region, seed_scenarios

RUN_TABLES: dict[str, str] = {
    "snapshot": "리비전 기록 — 같은 날 재수집은 새 리비전을 만든다(D11-1)",
    "snapshot_view": "발행 저장본 — 리비전마다",
    "snapshot_view_unit": "발행 저장본 단위 — 리비전마다",
    "job_run": "잡 실행 기록",
    "judgment_log": "판정기 호출 기록 — 새 행 수는 tools/call 로 따로 단언",
    "change_event": "변경 이벤트 — 사실 이벤트 0 을 따로 단언",
    "score_run": "점수 실행 — 리비전마다(이월 복사)",
    "score_component": "점수 성분 — 리비전마다",
    "score_total": "점수 합계 — 리비전마다",
    "ladder": "noul 사다리 — 리비전마다",
    "decision": "decide 결과 — 리비전마다",
    "claim": "verify 주장 — 리비전마다",
    "comparable_set": "비교군 — 리비전마다",
    "intake_status": "접수 상태 — 리비전마다 복사(내용은 intake_view 로 비교)",
    "benchmark": "벤치마크 — 리비전마다(snapshot_id)",
}
"""DB 스냅샷에서 빼는 실행·리비전 기록(사유). 여기 없는 테이블은 전부 바이트 단위 비교 대상이다."""


@dataclass
class ReplaySet:
    """재생 세트 하나 — 매니페스트(dict) + 원문 뿌리. ``region`` 이 없으면 회귀 픽스처 지역(``conftest.seed_region``)."""

    name: str
    manifest: dict[str, Any]
    raw_root: Path
    extra_files: list[tuple[Path, str]] = field(default_factory=list)
    """원문 뿌리 밖 파일 → RAW_DIR 상대 경로(r4_remnant 의 원 공고 응답)."""
    in_place: bool = False
    """True 면 RAW_DIR 을 ``raw_root`` 로 바꿔 읽는다(로컬 전체 재생 — 수십 MB 를 복사하지 않는다)."""

    @property
    def docs(self) -> dict[str, Any]:
        out: dict[str, Any] = self.manifest["docs"]
        return out

    @property
    def asof(self) -> str:
        return str(self.manifest["asof"])

    def install(self, raw_dir: Path) -> None:
        """원문 파일을 RAW_DIR 로 복사한다(PDF 바이너리는 녹화에 없다 — 파서는 text_path·table_path 를 읽는다)."""
        for row in self._all_rows():
            for k in ("path", "text_path", "table_path"):
                rel = row.get(k)
                if not rel:
                    continue
                src = self.raw_root / rel
                if src.exists():
                    dst = raw_dir / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
        for src, rel in self.extra_files:
            dst = raw_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)

    def _all_rows(self) -> Iterable[dict[str, Any]]:
        d = self.docs
        yield from d.get("applyhome", [])
        yield from d.get("notice_pdf", [])
        yield from d.get("official_site", [])
        yield from d.get("news", [])
        for rows in (d.get("originals") or {}).values():
            yield from rows

    def seed(self, factory: sessionmaker[Session]) -> None:
        """시나리오 · 지역(status bootstrapping) · 법정동 참조 행."""
        r = self.manifest.get("region")
        with factory() as s:
            seed_scenarios(s)
            if r is None:
                seed_region(s, status="bootstrapping")
            else:
                s.add(
                    Region(
                        id=1,
                        name=r["name"],
                        query_text=r["query_text"],
                        selections=r["selections"],
                        sido_codes=r["sido_codes"],
                        sigungu_codes=r["sigungu_codes"],
                        legal_dong_codes=r["legal_dong_codes"],
                        living_areas=r["living_areas"],
                        age_premium_coef=r["age_premium_coef"],
                        supply_ref_pct=Decimal(str(r["supply_ref_pct"])),
                        applyhome_query={},
                        status="bootstrapping",
                        created_at=r["created_at"],
                    )
                )
            for ld in self.manifest.get("legal_dong", []):
                s.add(LegalDong(**ld))
            s.commit()


NEWS_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "r4_news_2026-10-12.json"
NEWS_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news?query=q"


def with_default_news(rs: ReplaySet) -> ReplaySet:
    """매니페스트에 주간 단계 뉴스 원문이 없으면 저장소 녹화 뉴스 1건을 붙인다(R4-CORE11). 원문 뿌리를 그 자리에서 읽는 세트
    (``in_place`` — 로컬 전체 재생)는 바깥 폴더에 파일을 쓰지 않도록 붙이지 않는다(매니페스트 ``news`` 를 쓴다)."""
    import hashlib

    if rs.docs.get("news") or rs.in_place:
        return rs
    data = NEWS_FIXTURE.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    rel = f"news/{rs.asof}/{sha}.json"
    row = {
        "source_kind": "news", "url": NEWS_URL, "fetched_at": f"{rs.asof}T05:30:00+09:00", "http_status": 200,
        "sha256": sha, "path": rel, "content_type": "application/json", "text_path": None, "table_path": None,
        "error_text": None, "image_hash": None, "meta": None,
    }  # fmt: skip
    docs = {**rs.docs, "news": [row]}
    return ReplaySet(
        rs.name,
        {**rs.manifest, "docs": docs},
        rs.raw_root,
        [*rs.extra_files, (NEWS_FIXTURE, rel)],
        rs.in_place,
    )


def load_manifest(name: str, path: Path, *, in_place: bool = False) -> ReplaySet:
    """``docs.json`` 경로 → 세트(``raw_root`` 가 매니페스트에 있으면 그곳, 없으면 옆 ``raw/``)."""
    m: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    root = Path(m["raw_root"]) if m.get("raw_root") else path.parent / "raw"
    return ReplaySet(name, m, root, in_place=in_place)


def load_zip(name: str, archive: Path, workdir: Path) -> ReplaySet:
    """녹화 zip(``docs.json`` + ``raw/…``)을 풀어 세트로."""
    with zipfile.ZipFile(archive) as z:
        z.extractall(workdir)
    return load_manifest(name, workdir / "docs.json")


def _by_house(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(_house_no(str(r["url"])) or "?", []).append(r)
    return out


def grouped_set(
    name: str, fix: Path, groups: list[str], *, originals: tuple[str, ...] = (), asof: str
) -> ReplaySet:
    """CORE8·CORE9 녹화(``docs.json`` 의 그룹별 행, 회귀 픽스처 지역) → 세트. ``originals`` 그룹은 원 공고 다시 받기 응답."""
    m = json.loads((fix / "docs.json").read_text(encoding="utf-8"))["docs"]
    rows = [r for g in groups for r in m[g]]
    orig = [r for g in originals for r in m[g]]
    manifest = {
        "asof": asof,
        "region": None,
        "docs": {
            "applyhome": [r for r in rows if r["source_kind"] != "notice_pdf"],
            "notice_pdf": [r for r in rows if r["source_kind"] == "notice_pdf"],
            "originals": _by_house(orig),
        },
    }
    return ReplaySet(name, manifest, fix / "raw")


def remnant_set(fix: Path) -> ReplaySet:
    """R4 1차 녹화(``r4_remnant`` — 원 공고 응답은 과거 공고 목록 행으로 만든 것, ``test_r4_fix_d18_4``)."""
    from .test_r4_fix_d18_4 import _originals

    m = json.loads((fix / "docs.json").read_text(encoding="utf-8"))
    extra = [
        (fix / o["detail"], f"applyhome_detail/2026-10-12/orig_{hm}.json") for hm, o in m["originals"].items()
    ]
    manifest = {
        "asof": "2026-10-12",
        "region": None,
        "docs": {
            "applyhome": m["docs"]["applyhome"],
            "notice_pdf": m["docs"]["notice_pdf"],
            "originals": _originals(m),
        },
    }
    return ReplaySet("r4", manifest, fix / "raw", extra_files=extra)


def _insert(factory: sessionmaker[Session], rows: list[dict[str, Any]]) -> list[RawDTO]:
    """녹화 행 → raw_document(같은 sha256 이면 기존 행을 그대로 — 실제 수집기 ``RawStore`` 와 같은 멱등) → DTO.

    새 행의 ``complex_id`` 는 실제 수집기처럼 **받는 시점**의 그 주택관리번호 단지(청약홈 상세·원 공고·공고문 = URL 의 번호,
    공식 홈페이지 = 녹화 행의 ``house_no``)다. 이미 있는 행은 바꾸지 않는다(실제 수집기도 같은 원문을 다시 받으면 기존 행을
    돌려준다 — ``latest_ok``·``by_sha``)."""
    out: list[RawDTO] = []
    with factory() as s:
        for r in rows:
            found = s.scalars(select(RawDocument).where(RawDocument.sha256 == r["sha256"])).first()
            if found is None:
                vals = {k: v for k, v in r.items() if k not in ("id", "house_no", "complex_id", "region_id")}
                hn = r.get("house_no") or _house_no(str(r["url"]))
                cid = s.scalar(select(Complex.id).where(Complex.applyhome_id == hn)) if hn else None
                found = RawDocument(**vals, region_id=1, complex_id=cid)
                s.add(found)
                s.flush()
            out.append(raw_dto(found))
        s.commit()
    return out


def _house_no(url: str) -> str | None:
    import re

    m = re.search(r"(?:houseManageNo=|HOUSE_MANAGE_NO%3A%3AEQ%5D=)(\d{10})", url)
    return m.group(1) if m else None


@dataclass
class Replay:
    """녹화 원문을 돌려주는 수집기(네트워크 없음). ``rng`` 가 있으면 돌려주는 순서를 섞는다(속성 테스트 — 순서 무관)."""

    factory: sessionmaker[Session]
    rows: list[dict[str, Any]]
    originals: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    rng: random.Random | None = None
    original_calls: list[list[str]] = field(default_factory=list)

    def _order(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = list(rows)
        if self.rng is not None:
            self.rng.shuffle(rows)
        return rows

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        return _insert(self.factory, self._order(self.rows))

    def fetch_originals(
        self, region: RegionDTO, snapshot: SnapshotDTO, house_manage_nos: list[str]
    ) -> list[RawDTO]:
        self.original_calls.append(list(house_manage_nos))
        rows = [r for hm in house_manage_nos for r in self.originals.get(hm, [])]
        return _insert(self.factory, self._order(rows))


class NoticeReplay(Replay):
    """공고문(새 행이면 받는 시점의 그 공고 단지에 단다 — ``_insert``)."""


class SiteReplay(Replay):
    """공식 홈페이지: 녹화 행의 ``house_no`` 단지가 재생 DB 에 있을 때만 그 원문이 온다(실제 수집기는 DB 단지의 공식 홈페이지만
    돈다 — 녹화 당시 단지 id 는 재생 DB 와 다르다)."""

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        with self.factory() as s:
            have = {
                str(a)
                for a in s.scalars(select(Complex.applyhome_id).where(Complex.applyhome_id.is_not(None)))
            }
        return _insert(
            self.factory, self._order([r for r in self.rows if str(r.get("house_no") or "") in have])
        )


@dataclass
class Collectors:
    applyhome: Replay
    notice_pdf: NoticeReplay
    official_site: SiteReplay
    news: Replay | None = None
    """주간 단계 뉴스(R4-CORE11) — 있으면 ``as_ctx`` 가 ``news`` 수집기로 넘긴다(없으면 주간 단계는 원문 없음)."""

    def shuffle(self, seed: int | None) -> None:
        for c in (self.applyhome, self.notice_pdf, self.official_site, self.news):
            if c is not None:
                c.rng = random.Random(seed) if seed is not None else None

    def as_ctx(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "applyhome": lambda c: self.applyhome,
            "notice_pdf": lambda c: self.notice_pdf,
            "official_site": lambda c: self.official_site,
        }
        if self.news is not None:
            out["news"] = lambda c: self.news
        return out


def collectors(rs: ReplaySet, factory: sessionmaker[Session], *, weekly: bool = False) -> Collectors:
    """재생 수집기. ``weekly`` 면 주간 단계 뉴스 원문(``docs.news``)도 재생한다(R4-CORE11)."""
    d = rs.docs
    return Collectors(
        applyhome=Replay(factory, list(d.get("applyhome", [])), dict(d.get("originals") or {})),
        notice_pdf=NoticeReplay(factory, list(d.get("notice_pdf", []))),
        official_site=SiteReplay(factory, list(d.get("official_site", []))),
        news=Replay(factory, list(d.get("news", []))) if weekly else None,
    )


# ---------------------------------------------------------------- DB 스냅샷


def _cell(v: Any) -> Any:
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex()
    return v


def db_state(factory: sessionmaker[Session]) -> dict[str, list[tuple[Any, ...]]]:
    """``RUN_TABLES`` 밖 모든 테이블 → 행(모든 열, 기본키 순). 값은 DB 가 돌려준 그대로(바이트 단위 비교)."""
    out: dict[str, list[tuple[Any, ...]]] = {}
    with factory() as s:
        for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
            if table.name in RUN_TABLES:
                continue
            cols = [c.name for c in table.columns]
            pk = [c.name for c in table.primary_key.columns] or cols[:1]
            rows = s.execute(
                text(f"SELECT {', '.join(cols)} FROM {table.name} ORDER BY {', '.join(pk)}")
            ).all()
            out[table.name] = [tuple(_cell(v) for v in r) for r in rows]
        out["intake_status(view)"] = intake_view(s)
    return out


def _note(note: str | None) -> str | None:
    """분류 복사 표식('… 이전 분류 복사(접수 행 n, 스냅샷 m)' — 그 리비전이 어느 행에서 복사했는지, D10-2)은 리비전마다 다른
    행을 가리키는 설계라 뺀다(나머지 문구는 그대로 비교)."""
    from app.scheduler.intake import COPIED_MARK

    if not note:
        return note
    return " · ".join(p for p in note.split(" · ") if not p.startswith(COPIED_MARK)) or None


def intake_view(s: Session) -> list[tuple[Any, ...]]:
    """최신 리비전의 접수 상태 행 — 리비전 id·행 id·분류 복사 표식을 뺀 내용(리비전마다 복사되므로)."""
    sid = s.scalar(select(IntakeStatus.snapshot_id).order_by(IntakeStatus.snapshot_id.desc()).limit(1))
    rows = s.scalars(select(IntakeStatus).where(IntakeStatus.snapshot_id == sid)) if sid is not None else []
    cols = ("complex_id", "path", "status", "evidence_url", "screenshot_path", "raw_document_id", "http_status",
            "checked_at", "reason", "note", "entered_by")  # fmt: skip
    return sorted(tuple(_note(r.note) if c == "note" else getattr(r, c) for c in cols) for r in rows)


def state_diff(
    before: dict[str, list[tuple[Any, ...]]], after: dict[str, list[tuple[Any, ...]]], *, limit: int = 12
) -> list[str]:
    """테이블별 차이(사라진 행 · 생긴 행 · 바뀐 행 — 기본키 첫 열 기준). 빈 목록 = 같다."""
    out: list[str] = []
    for name in sorted(set(before) | set(after)):
        a, b = before.get(name, []), after.get(name, [])
        if a == b:
            continue
        ka = {r[0]: r for r in a}
        kb = {r[0]: r for r in b}
        gone = [k for k in ka if k not in kb]
        new = [k for k in kb if k not in ka]
        changed = [k for k in ka if k in kb and ka[k] != kb[k]]
        out.append(f"{name}: 사라짐 {len(gone)} · 생김 {len(new)} · 바뀜 {len(changed)}")
        for k in new[:limit]:
            out.append(f"  + {kb[k]}")
        for k in gone[:limit]:
            out.append(f"  - {ka[k]}")
        for k in changed[:limit]:
            diffs = [(i, x, y) for i, (x, y) in enumerate(zip(ka[k], kb[k], strict=True)) if x != y]
            out.append(f"  ~ {k}: {diffs}")
    return out


def changed_cells(
    before: dict[str, list[tuple[Any, ...]]], after: dict[str, list[tuple[Any, ...]]]
) -> dict[str, int]:
    """테이블 → 차이 행 수(요약)."""
    out: dict[str, int] = {}
    for name in set(before) | set(after):
        a = {r[0]: r for r in before.get(name, [])}
        b = {r[0]: r for r in after.get(name, [])}
        n = sum(1 for k in set(a) | set(b) if a.get(k) != b.get(k))
        if n:
            out[name] = n
    return out


# ---------------------------------------------------------------- 파서 변경 배포(R10-FIX — D23-1 확장)

SUPERSEDED_HEAD = "옛 파싱"
"""``normalize.fields.SUPERSEDED_REASON`` 의 머리(수정 전 트리에서도 import 오류 없이 돌도록 글자로)."""


def old_apply_items(found: dict[str, tuple[str, str]]) -> list[dict[str, str]]:
    """R9-PARSE 전 청약 일정 모양: 순위(구분 첫 낱말)마다 시작일 하나 ``{kind, date}`` — 거주지역 구분·마감일 없음."""
    from app.normalize.applyhome_api_parser import APPLY_KINDS

    order = {k: i for i, k in enumerate(APPLY_KINDS)}
    firsts: dict[str, str] = {}
    for k in sorted(found, key=lambda k: (order.get(k, len(order)), k)):
        rank = k.split()[0]
        if rank not in firsts or found[k][0] < firsts[rank]:
            firsts[rank] = found[k][0]
    return [{"kind": r, "date": d} for r, d in firsts.items()]


def old_apply_text(items: list[dict[str, str]]) -> str:
    return "; ".join(f"{a['kind']} {a.get('date') or a.get('start')}" for a in items)


def use_old_apply_parser(mp: Any) -> None:
    """청약홈 API·웹 상세 두 파서를 R9-PARSE 전 모양으로(``pytest.MonkeyPatch`` 문맥 안에서)."""
    from app.normalize import applyhome_api_parser, applyhome_parser

    for mod in (applyhome_api_parser, applyhome_parser):
        mp.setattr(mod, "apply_items", old_apply_items)
        mp.setattr(mod, "apply_text", old_apply_text)


def untag_superseded(factory: sessionmaker[Session]) -> int:
    """수정 전 배포가 남긴 DB 모양: 옛 파싱 행에 표식이 없다(수정 전 트리에서는 표식 행이 없어 아무것도 하지 않는다)."""
    from app.models import FieldProvenance

    n = 0
    with factory() as s:
        for fp in s.scalars(
            select(FieldProvenance).where(FieldProvenance.reason.like(f"{SUPERSEDED_HEAD}%"))
        ):
            _, sep, rest = (fp.reason or "").partition("; ")
            fp.reason = rest if sep and rest else None
            n += 1
        s.commit()
    return n
