"""미분양 월별 (국토교통 통계누리 stat.molit.go.kr, 키 불필요) → ``unsold`` (RA §3, 월말 기준).

원천: 통계누리 '미분양주택현황보고' 통계표 JSON(화면이 쓰는 것과 같은 요청).
- 합계: ``GET /portal/stat/data.do?formId=2082&styleNum=128&apprYn=Y&startDate=YYYYMM&endDate=YYYYMM``
  ("시·군·구별 미분양현황") → 행 ``{"0": "2026-08", "1": "인천", "2": "연수구", "3": "505"}`` (2 = '계'는
  시도 합계)
- 준공 후: ``formId=5328&styleNum=1`` ("공사완료후 미분양현황") → 행 ``{"0","1"(시도),"2"(시군구|'합계'|'계'),
  "3"(부문),"4"(규모),"5"(호)}`` 중 부문·규모가 모두 '계'인 행.
이용 조건: 통계누리 저작권 정책상 통계정보는 자유 이용(상업적 이용 포함) — robots 는 Googlebot 일부 경로만
제한.

시군구 이름 → 코드는 ``legal_dong`` 표(참조 데이터)로 찾는다: (시도 약칭, 시군구 이름)이 맞는 시군구 행.
활성 코드
우선, 이름이 바뀐 옛 시군구(분구 전 이름 등)는 폐지 코드로 잡힌다. 지역은 region.sigungu_codes 로만 거른다.
라벨: 국토부 공식 통계 → source_label '확인됨'. 단지별 귀속은 하지 않는다(통계 단위 = 시군구).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.reference.load import LoadStats
from app.collectors.reference.rawstore import RawStore, fetch_failure
from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.db import get_session
from app.core.http import HttpClient
from app.models import LegalDong, Unsold

__all__ = [
    "MOLIT_DATA_URL",
    "SigunguResolver",
    "UnsoldCollector",
    "UnsoldRecord",
    "UnsoldStatRow",
    "load_unsold",
    "merge_unsold",
    "parse_unsold_post_completion",
    "parse_unsold_total",
    "sido_abbrev",
]

MOLIT_DATA_URL = "https://stat.molit.go.kr/portal/stat/data.do"
FORM_TOTAL = {"formId": "2082", "styleNum": "128"}
FORM_POST_COMPLETION = {"formId": "5328", "styleNum": "1"}
UNSOLD_LABEL = "확인됨"
SessionFactory = Callable[[], AbstractContextManager[Session]]
_TOTAL_WORDS = {"계", "합계", "소계", "전국"}


@dataclass(frozen=True, slots=True)
class UnsoldStatRow:
    ym: str  # YYYY-MM
    sido: str  # 약칭('인천')
    sigungu: str
    value: int


@dataclass(frozen=True, slots=True)
class UnsoldRecord:
    scope_code: str
    scope_name: str
    ym: str
    total: int | None
    post_completion: int | None


def _rows(content: bytes) -> list[dict[str, object]]:
    try:
        data = json.loads(content.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return []
    rows = data.get("data") if isinstance(data, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _num(v: object) -> int | None:
    s = str(v).replace(",", "").strip()
    return int(s) if s.isdigit() else None


def parse_unsold_total(content: bytes) -> list[UnsoldStatRow]:
    out: list[UnsoldStatRow] = []
    for r in _rows(content):
        sido, sgg, val = str(r.get("1", "")).strip(), str(r.get("2", "")).strip(), _num(r.get("3"))
        ym = str(r.get("0", "")).strip()
        if not sido or not sgg or val is None or sgg in _TOTAL_WORDS or sido in _TOTAL_WORDS or len(ym) != 7:
            continue
        out.append(UnsoldStatRow(ym, sido, sgg, val))
    return out


def parse_unsold_post_completion(content: bytes) -> list[UnsoldStatRow]:
    out: list[UnsoldStatRow] = []
    for r in _rows(content):
        if str(r.get("3", "")).strip() != "계" or str(r.get("4", "")).strip() != "계":
            continue
        sido, sgg, val = str(r.get("1", "")).strip(), str(r.get("2", "")).strip(), _num(r.get("5"))
        ym = str(r.get("0", "")).strip()
        if not sido or not sgg or val is None or sgg in _TOTAL_WORDS or sido in _TOTAL_WORDS or len(ym) != 7:
            continue
        out.append(UnsoldStatRow(ym, sido, sgg, val))
    return out


_SIDO_SUFFIXES = ("특별자치시", "특별자치도", "특별시", "광역시", "도")


def _sido_core(sido_name: str) -> str:
    core = sido_name
    for suf in _SIDO_SUFFIXES:
        if core.endswith(suf) and len(core) > len(suf):
            core = core[: -len(suf)]
            break
    return core.removesuffix("통합") or core


def sido_abbrev(sido_name: str) -> str:
    """'인천광역시'→'인천', '경기도'→'경기', '충청북도'→'충북', '전북특별자치도'→'전북'."""
    core = _sido_core(sido_name)
    if len(core) == 3 and core[2] in "남북":
        return core[0] + core[2]
    return core[:2]


def sido_aliases(sido_name: str) -> set[str]:
    """통계표가 쓸 수 있는 시도 약칭들('전남광주통합특별시' → {'전남', '전남광주'})."""
    core = _sido_core(sido_name)
    return {sido_abbrev(sido_name), core}


class SigunguResolver:
    """(시도 약칭, 시군구 이름) → 시군구 코드 5자리. legal_dong 시군구 행으로 만든 표."""

    def __init__(self, session: Session) -> None:
        self._index: dict[tuple[str, str], list[tuple[bool, str]]] = {}
        self._live_sido: set[str] = set()  # 현존 시도 코드 2자리(옛 코드 체계 23xxx 등과 가르기 위해)
        stmt = select(
            LegalDong.code,
            LegalDong.sido_name,
            LegalDong.sigungu_name,
            LegalDong.sigungu_code,
            LegalDong.active,
        ).where(LegalDong.code.like("__00000000") | LegalDong.code.like("_____00000"))
        for code, sido, sgg, sgg_code, active in session.execute(stmt):
            if code[2:] == "00000000":
                if active:
                    self._live_sido.add(code[:2])
                continue
            # 시군구가 없는 시(세종)는 통계표가 '세종시'로 쓴다 → 시도 약칭+'시' 로도 찾는다
            names = {"".join(str(sgg).split())} if sgg else {sido_abbrev(sido) + "시", sido}
            for alias in sido_aliases(sido):
                for name in names:
                    self._index.setdefault((alias, name), []).append((bool(active), sgg_code))

    def __len__(self) -> int:
        return len(self._index)

    def resolve(self, sido: str, sigungu: str) -> str | None:
        hits = self._index.get((sido.strip(), "".join(sigungu.split())))
        if not hits:
            return None
        # 현존 코드 > 현존 시도 체계의 폐지 코드(분구 전 이름 등) > 옛 시도 체계 코드, 같으면 큰 코드(최근)
        return sorted(hits, key=lambda h: (not h[0], h[1][:2] not in self._live_sido, -int(h[1])))[0][1]


def merge_unsold(
    resolver: SigunguResolver, total: Iterable[UnsoldStatRow], post: Iterable[UnsoldStatRow]
) -> tuple[list[UnsoldRecord], list[str]]:
    """합계·준공 후를 (시군구 코드, 월)로 합친다. 코드를 못 찾은 이름은 두 번째 값으로."""
    names: dict[tuple[str, str], str] = {}
    totals: dict[tuple[str, str], int] = {}
    posts: dict[tuple[str, str], int] = {}
    unresolved: set[str] = set()
    for target, rows in ((totals, total), (posts, post)):
        for r in rows:
            code = resolver.resolve(r.sido, r.sigungu)
            if code is None:
                unresolved.add(f"{r.sido} {r.sigungu}")
                continue
            names.setdefault((code, r.ym), f"{r.sido} {r.sigungu}")
            target[(code, r.ym)] = r.value
    out = [
        UnsoldRecord(
            scope_code=code,
            scope_name=name,
            ym=ym,
            total=totals.get((code, ym)),
            post_completion=posts.get((code, ym)),
        )
        for (code, ym), name in sorted(names.items())
    ]
    return out, sorted(unresolved)


def load_unsold(
    session: Session, region_id: int, records: Iterable[UnsoldRecord], *, raw_document_id: int | None
) -> LoadStats:
    """(region_id, scope_code, ym) 기준 upsert."""
    stats = LoadStats()
    recs = list(records)
    if not recs:
        return stats
    existing = {
        (u.scope_code, u.ym): u for u in session.scalars(select(Unsold).where(Unsold.region_id == region_id))
    }
    for r in recs:
        row = existing.get((r.scope_code, r.ym))
        if row is None:
            session.add(
                Unsold(
                    region_id=region_id,
                    scope_code=r.scope_code,
                    scope_name=r.scope_name,
                    ym=r.ym,
                    total=r.total,
                    post_completion=r.post_completion,
                    source_label=UNSOLD_LABEL,
                    raw_document_id=raw_document_id,
                )
            )
            stats.inserted += 1
        elif (row.total, row.post_completion) != (r.total, r.post_completion):
            row.total, row.post_completion, row.raw_document_id = r.total, r.post_completion, raw_document_id
            stats.updated += 1
        else:
            stats.unchanged += 1
    session.flush()
    return stats


def _shift(ym: str, months: int) -> str:
    y, m = (int(x) for x in ym.split("-"))
    total = y * 12 + (m - 1) + months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


@dataclass(slots=True)
class UnsoldResult:
    start: str = ""
    end: str = ""
    documents: list[RawDocument] = field(default_factory=list)
    records: list[UnsoldRecord] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    load: LoadStats | None = None


class UnsoldCollector:
    """미분양 수집기 (source_kind='stats'). 기간 = 기준월-1 에서 ``months`` 개월(또는 since 부터)."""

    source_kind = "stats"

    def __init__(
        self,
        *,
        http: HttpClient | None = None,
        months: int = 12,
        load: bool = True,
        session_factory: SessionFactory = get_session,
        raw_dir: Path | None = None,
    ) -> None:
        self._http = http
        self._months = max(1, months)
        self._load = load
        self._session_factory = session_factory
        self._raw_dir = raw_dir
        self.last: UnsoldResult | None = None

    def fetch(self, region: Region, snapshot: Snapshot, since: str | None) -> list[RawDocument]:
        end = _shift(snapshot.asof_date[:7], -1)  # 월말 기준 통계는 다음 달에 나온다
        start = _shift(end, -(self._months - 1))
        if since and since[:7] > start:
            start = min(since[:7], end)
        result = UnsoldResult(start=start, end=end)
        http = self._http or HttpClient()
        try:
            with self._session_factory() as session:
                store = RawStore(session, raw_dir=self._raw_dir)
                contents: dict[str, bytes] = {}
                total_doc: RawDocument | None = None
                for name, form in (("total", FORM_TOTAL), ("post", FORM_POST_COMPLETION)):
                    params = {
                        **form,
                        "apprYn": "Y",
                        "startDate": start.replace("-", ""),
                        "endDate": end.replace("-", ""),
                    }
                    r = http.get(MOLIT_DATA_URL, params=params)
                    shown = f"{MOLIT_DATA_URL}?" + "&".join(f"{k}={v}" for k, v in params.items())
                    if r.ok:
                        doc = store.save_result(
                            r,
                            source_kind="stats",
                            ext="json",
                            url=shown,
                            content_type="application/json",
                            region_id=region.id,
                        )
                        contents[name] = r.content
                    else:
                        doc = store.save_result(
                            r,
                            source_kind="stats",
                            ext="json",
                            url=shown,
                            region_id=region.id,
                            failure=fetch_failure(r),
                        )
                    result.documents.append(doc)
                    if name == "total":
                        total_doc = doc
                if "total" in contents or "post" in contents:
                    resolver = SigunguResolver(session)
                    records, unresolved = merge_unsold(
                        resolver,
                        parse_unsold_total(contents.get("total", b"")),
                        parse_unsold_post_completion(contents.get("post", b"")),
                    )
                    wanted = set(region.sigungu_codes)
                    result.records = [r for r in records if r.scope_code in wanted]
                    result.unresolved = unresolved
                    if self._load:
                        result.load = load_unsold(
                            session,
                            region.id,
                            result.records,
                            raw_document_id=total_doc.id
                            if total_doc is not None and total_doc.path
                            else None,
                        )
        finally:
            if self._http is None:
                http.close()
        self.last = result
        return result.documents
