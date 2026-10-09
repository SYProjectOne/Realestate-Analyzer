"""행안부 주민등록 인구 및 세대현황 (jumin.mois.go.kr, 키 불필요) → ``household_stat`` (DECISIONS D2-1).

원천: ``POST https://jumin.mois.go.kr/downloadCsv.do?searchYearMonth=month&xlsStats=3`` (전체 읍면동 현황,
월 1개).
cp949 CSV: ``"행정구역","YYYY년MM월_총인구수","YYYY년MM월_세대수", …`` / 행정구역 = ``"인천광역시 연수구
송도1동(2818582000)"``.
- 코드 끝 5자리가 00000 이고 시도가 아니면 시군구 행(scope_kind='sigungu', scope_code 5자리), 나머지는 행정동
  (scope_kind='admin_dong', 10자리). 시도 행은 버린다.
- 라벨 '추정', reason '주민등록 세대' 고정(D2-1).
- 해당 월이 아직 공표 전이면 머리글만 온다 → 한 달 전으로 다시(최대 ``max_back`` 개월).
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.reference.legal_dong import decode_korean
from app.collectors.reference.load import LoadStats
from app.collectors.reference.rawstore import RawStore, fetch_failure
from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.db import get_session
from app.core.http import HttpClient
from app.core.time import today_kst
from app.models import HouseholdStat

__all__ = [
    "HOUSEHOLD_LABEL",
    "HOUSEHOLD_REASON",
    "JUMIN_CSV_URL",
    "HouseholdCollector",
    "HouseholdRecord",
    "HouseholdResult",
    "jumin_form",
    "load_household_stats",
    "parse_household_csv",
]

JUMIN_CSV_URL = "https://jumin.mois.go.kr/downloadCsv.do"
JUMIN_CSV_PARAMS = {"searchYearMonth": "month", "xlsStats": "3"}
HOUSEHOLD_LABEL = "추정"
HOUSEHOLD_REASON = "주민등록 세대"
FALLBACK_NAME_RE = re.compile(r"^jumin_households_(\d{4})(\d{2})\.csv$")

_NAME_CODE_RE = re.compile(r"^(.*?)\s*\((\d{10})\)\s*$")
_YM_RE = re.compile(r"(\d{4})년(\d{2})월_세대수")


@dataclass(frozen=True, slots=True)
class HouseholdRecord:
    scope_kind: Literal["admin_dong", "sigungu"]
    scope_code: str
    ym: str
    households: int
    name: str


def jumin_form(ym: str) -> dict[str, str]:
    """전국(A)·전체 읍면동 월간 CSV 요청 본문."""
    y, m = ym.split("-")
    return {
        "sltOrgType": "1",
        "sltOrgLvl1": "A",
        "sltOrgLvl2": "",
        "gender": "gender",
        "genderPer": "genderPer",
        "generation": "generation",
        "sltUndefType": "",
        "searchYearStart": y,
        "searchMonthStart": m,
        "searchYearEnd": y,
        "searchMonthEnd": m,
        "sltOrderType": "1",
        "sltOrderValue": "ASC",
        "category": "month",
    }


def _int(text: str) -> int | None:
    digits = text.replace(",", "").strip()
    return int(digits) if digits.isdigit() else None


def parse_household_csv(content: bytes) -> tuple[str | None, list[HouseholdRecord]]:
    """CSV → (기준월 'YYYY-MM', 레코드). 머리글만 있으면 (None, [])."""
    reader = csv.reader(io.StringIO(decode_korean(content)))
    rows = list(reader)
    if not rows:
        return None, []
    header = rows[0]
    col = next((i for i, h in enumerate(header) if _YM_RE.search(h)), None)
    if col is None:
        return None, []
    m = _YM_RE.search(header[col])
    ym = f"{m.group(1)}-{m.group(2)}" if m else None
    if ym is None:
        return None, []
    out: list[HouseholdRecord] = []
    for row in rows[1:]:
        if len(row) <= col:
            continue
        nm = _NAME_CODE_RE.match(row[0].strip())
        households = _int(row[col])
        if not nm or households is None:
            continue
        name, code = " ".join(nm.group(1).split()), nm.group(2)
        if code[2:] == "00000000":
            continue  # 시도
        if code[5:] == "00000":
            out.append(HouseholdRecord("sigungu", code[:5], ym, households, name))
        else:
            out.append(HouseholdRecord("admin_dong", code, ym, households, name))
    return ym, out


def load_household_stats(
    session: Session, records: Iterable[HouseholdRecord], *, raw_document_id: int | None
) -> LoadStats:
    """(scope_kind, scope_code, ym) 기준 upsert. 같은 파일 재적재는 변화 0."""
    stats = LoadStats()
    recs = list(records)
    if not recs:
        return stats
    yms = {r.ym for r in recs}
    existing = {
        (h.scope_kind, h.scope_code, h.ym): h
        for h in session.scalars(select(HouseholdStat).where(HouseholdStat.ym.in_(yms)))
    }
    for r in recs:
        row = existing.get((r.scope_kind, r.scope_code, r.ym))
        if row is None:
            session.add(
                HouseholdStat(
                    scope_kind=r.scope_kind,
                    scope_code=r.scope_code,
                    ym=r.ym,
                    households=r.households,
                    raw_document_id=raw_document_id,
                    label=HOUSEHOLD_LABEL,
                    reason=HOUSEHOLD_REASON,
                )
            )
            stats.inserted += 1
        elif row.households != r.households:
            row.households = r.households
            row.raw_document_id = raw_document_id
            stats.updated += 1
        else:
            stats.unchanged += 1
    session.flush()
    return stats


def _prev_month(ym: str) -> str:
    y, m = (int(x) for x in ym.split("-"))
    y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return f"{y:04d}-{m:02d}"


@dataclass(slots=True)
class HouseholdResult:
    ym: str | None = None
    records: list[HouseholdRecord] = field(default_factory=list)
    documents: list[RawDocument] = field(default_factory=list)
    raw_document_id: int | None = None
    used_fallback: str | None = None  # 사본 파일 이름
    load: LoadStats | None = None


SessionFactory = Callable[[], AbstractContextManager[Session]]


class HouseholdCollector:
    """주민등록 세대 현황 수집기 (source_kind='stats'). 지역과 무관한 전국 파일 1개/월."""

    source_kind = "stats"

    def __init__(
        self,
        *,
        http: HttpClient | None = None,
        session_factory: SessionFactory = get_session,
        raw_dir: Path | None = None,
        fallback_dir: Path | None = None,
        max_back: int = 3,
        load: bool = True,
    ) -> None:
        self._http = http
        self._session_factory = session_factory
        self._raw_dir = raw_dir
        self._fallback_dir = fallback_dir
        self._max_back = max_back
        self._load = load
        self.last: HouseholdResult | None = None

    def fetch(self, region: Region, snapshot: Snapshot, since: str | None) -> list[RawDocument]:
        asof = date.fromisoformat(snapshot.asof_date)
        with self._session_factory() as session:
            result = self.collect(session, asof=asof)
        return result.documents

    def collect(self, session: Session, *, asof: date | None = None) -> HouseholdResult:
        """기준일 전월부터 거꾸로 받아 첫 공표 월을 적재한다. 전부 실패하면 사본(fallback_dir)."""
        store = RawStore(session, raw_dir=self._raw_dir)
        result = HouseholdResult()
        ym = _prev_month((asof or today_kst()).strftime("%Y-%m"))
        http = self._http or HttpClient()
        try:
            for _ in range(self._max_back):
                r = http.post(JUMIN_CSV_URL, params=JUMIN_CSV_PARAMS, data=jumin_form(ym))
                shown = f"{JUMIN_CSV_URL}?searchYearMonth=month&xlsStats=3#form-ym={ym}"  # POST 본문의 월
                if not r.ok:
                    result.documents.append(
                        store.save_result(
                            r, source_kind="stats", ext="csv", url=shown, failure=fetch_failure(r)
                        )
                    )
                    break
                doc = store.save_result(r, source_kind="stats", ext="csv", url=shown, content_type="text/csv")
                result.documents.append(doc)
                got_ym, records = parse_household_csv(r.content)
                if records:
                    result.ym, result.records, result.raw_document_id = got_ym, records, doc.id
                    break
                ym = _prev_month(ym)
        finally:
            if self._http is None:
                http.close()
        if not result.records and self._fallback_dir is not None:
            self._use_fallback(store, result)
        if self._load and result.records:
            result.load = load_household_stats(
                session, result.records, raw_document_id=result.raw_document_id
            )
        self.last = result
        return result

    def _use_fallback(self, store: RawStore, result: HouseholdResult) -> None:
        assert self._fallback_dir is not None
        files = sorted(
            p for p in self._fallback_dir.glob("jumin_households_*.csv") if FALLBACK_NAME_RE.match(p.name)
        )
        if not files:
            return
        path = files[-1]
        content = path.read_bytes()
        doc = store.save_content(
            source_kind="stats",
            url=f"fixture://reference/{path.name}",
            content=content,
            http_status=None,  # 사본 파일(HTTP 응답 아님) — url 이 fixture:// 이다
            ext="csv",
            content_type="text/csv",
        )
        result.documents.append(doc)
        result.ym, result.records = parse_household_csv(content)
        result.raw_document_id = doc.id
        result.used_fallback = path.name
