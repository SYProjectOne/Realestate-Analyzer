"""자유 지명 → 지역 후보 (DECISIONS D2-1·D2-3, contracts/schemas/region_candidate.json).

문자열 매칭이다(판단 아님 — 판정기 호출 없음). 이름에서 공백과 접미사(시·군·구·동·읍·면, 시도의 특별시·광역시·
특별자치시·특별자치도·도)를 떼고 비교한다: exact(같음) > prefix(이름이 질의로 시작) > partial(질의를 포함).
정렬은 match → kind(sido > sigungu > admin_dong > legal_dong) → full_name.

- sido·sigungu 후보의 legal_dong_codes = 하위 법정동(읍면동·리) 전부,
  admin_dong 후보 = admin_legal_map으로 펼친 법정동, legal_dong(읍면동) 후보 = 그 동과 하위 리.
  폐지 코드(active=false)는 넣지 않는다.
- 분구·개편으로 옛 코드와 새 코드가 함께 있으면 둘 다 후보로 나온다(D3).
- 여러 단어 질의('인천 연수구')는 마지막 단어가 후보 이름, 앞 단어는 상위 이름(시도·시군구)과 맞아야 한다.

순수 함수(``resolve_region``) + 참조 데이터 로더(CSV·DB) + DB 래퍼(``resolve_region_db``).
지역명은 코드에 없다 — 전부 참조 테이블(legal_dong·admin_dong·admin_legal_map)에서 온다.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import RegionCandidate
from app.models import AdminDong, AdminLegalMap, LegalDong

__all__ = [
    "AdminRow",
    "LegalRow",
    "ReferenceData",
    "expand_selections",
    "load_reference_csv",
    "load_reference_db",
    "normalize_name",
    "resolve_region",
    "resolve_region_db",
]

_SIDO_SUFFIXES = ("특별자치시", "특별자치도", "특별시", "광역시", "자치시", "도")
_SUFFIXES = ("시", "군", "구", "동", "읍", "면", "리")
_MATCH_ORDER = {"exact": 0, "prefix": 1, "partial": 2}
_KIND_ORDER = {"sido": 0, "sigungu": 1, "admin_dong": 2, "legal_dong": 3}


@dataclass(frozen=True)
class LegalRow:
    code: str
    sido_name: str
    sigungu_name: str | None
    eupmyeondong_name: str | None
    ri_name: str | None
    full_name: str
    sigungu_code: str
    active: bool = True


@dataclass(frozen=True)
class AdminRow:
    code: str
    full_name: str
    name: str
    sigungu_code: str
    active: bool = True


@dataclass
class ReferenceData:
    legal: list[LegalRow]
    admin: list[AdminRow] = field(default_factory=list)
    admin_legal: list[tuple[str, str]] = field(default_factory=list)  # (admin_code, legal_code)

    def legal_active(self) -> list[LegalRow]:
        return [r for r in self.legal if r.active]


def normalize_name(name: str, *, sido: bool = False) -> str:
    """공백 제거 + 접미사 하나 제거. 남는 글자가 2자 미만이면 떼지 않는다('송도'의 '도'를 지키기 위해)."""
    s = "".join(name.split())
    suffixes = (
        (*_SIDO_SUFFIXES, *_SUFFIXES)
        if sido
        else (*_SUFFIXES, "특별시", "광역시", "특별자치시", "특별자치도")
    )
    for suf in sorted(suffixes, key=len, reverse=True):
        if s.endswith(suf) and len(s) - len(suf) >= 2:
            return s[: -len(suf)]
    return s


def _match(q: str, name_norm: str) -> str | None:
    if not q or not name_norm:
        return None
    if q == name_norm:
        return "exact"
    if name_norm.startswith(q):
        return "prefix"
    if q in name_norm:
        return "partial"
    return None


def _ancestors_ok(prefix_tokens: list[str], names: Iterable[str]) -> bool:
    norms = [normalize_name(n, sido=True) for n in names if n] + [normalize_name(n) for n in names if n]
    for t in prefix_tokens:
        tn = normalize_name(t, sido=True)
        tn2 = normalize_name(t)
        if not any(n.startswith(tn) or n.startswith(tn2) for n in norms):
            return False
    return True


def _is_dong_level(r: LegalRow) -> bool:
    return bool(r.eupmyeondong_name)


def resolve_region(q: str, ref: ReferenceData, *, limit: int = 50) -> list[RegionCandidate]:
    """자유 지명 → RegionCandidate[] (순수 함수)."""
    tokens = q.split()
    if not tokens:
        return []
    target = tokens[-1]
    prefix_tokens = tokens[:-1]
    qn = normalize_name(target)
    qn_sido = normalize_name(target, sido=True)
    legal = [r for r in ref.legal_active() if _is_dong_level(r)]
    out: list[RegionCandidate] = []

    # 시도
    by_sido: dict[str, list[LegalRow]] = defaultdict(list)
    for r in legal:
        by_sido[r.code[:2]].append(r)
    for sido_code, rows in by_sido.items():
        name = rows[0].sido_name
        m = _match(qn_sido, normalize_name(name, sido=True))
        if m and not prefix_tokens:
            out.append(
                RegionCandidate(
                    kind="sido",
                    code=sido_code,
                    full_name=name,
                    legal_dong_codes=sorted(r.code for r in rows),
                    match=m,
                    sido_code=sido_code,
                )
            )

    # 시군구
    by_sgg: dict[str, list[LegalRow]] = defaultdict(list)
    for r in legal:
        if r.sigungu_name:
            by_sgg[r.sigungu_code].append(r)
    for sgg_code, rows in by_sgg.items():
        sgg_name = rows[0].sigungu_name or ""
        parts = [sgg_name, *sgg_name.split()[1:]] if " " in sgg_name else [sgg_name]
        best = _best(qn, parts)
        if best and _ancestors_ok(prefix_tokens, [rows[0].sido_name, *sgg_name.split()[:-1]]):
            out.append(
                RegionCandidate(
                    kind="sigungu",
                    code=sgg_code,
                    full_name=f"{rows[0].sido_name} {sgg_name}",
                    legal_dong_codes=sorted(r.code for r in rows),
                    match=best,
                    sigungu_code=sgg_code,
                    sido_code=sgg_code[:2],
                )
            )

    # 행정동
    legal_codes_active = {r.code for r in legal}
    admin_map: dict[str, list[str]] = defaultdict(list)
    for adm_code, lc in ref.admin_legal:
        if lc in legal_codes_active:
            admin_map[adm_code].append(lc)
    sgg_names = {code: rows[0] for code, rows in by_sgg.items()}
    for a in ref.admin:
        if not a.active:
            continue
        m = _match(qn, normalize_name(a.name))
        anc = sgg_names.get(a.sigungu_code)
        anc_names = [anc.sido_name, anc.sigungu_name or ""] if anc else [a.full_name]
        if m and _ancestors_ok(prefix_tokens, anc_names):
            out.append(
                RegionCandidate(
                    kind="admin_dong",
                    code=a.code,
                    full_name=a.full_name,
                    legal_dong_codes=sorted(set(admin_map.get(a.code, []))),
                    match=m,
                    sigungu_code=a.sigungu_code,
                    sido_code=a.sigungu_code[:2],
                )
            )

    # 법정동(읍면동·리)
    for r in legal:
        own = r.ri_name or r.eupmyeondong_name or ""
        m = _match(qn, normalize_name(own))
        if not m or not _ancestors_ok(
            prefix_tokens, [r.sido_name, r.sigungu_name or "", r.eupmyeondong_name or ""]
        ):
            continue
        codes = [r.code] if r.ri_name else sorted(x.code for x in legal if x.code[:8] == r.code[:8])
        out.append(
            RegionCandidate(
                kind="legal_dong",
                code=r.code,
                full_name=r.full_name,
                legal_dong_codes=codes,
                match=m,
                sigungu_code=r.sigungu_code,
                sido_code=r.code[:2],
            )
        )

    out.sort(key=lambda c: (_MATCH_ORDER[c.match], _KIND_ORDER[c.kind], c.full_name, c.code))
    return out[:limit]


def _best(qn: str, names: list[str]) -> str | None:
    found = [m for m in (_match(qn, normalize_name(n)) for n in names) if m]
    return min(found, key=lambda m: _MATCH_ORDER[m]) if found else None


def expand_selections(selections: list[RegionCandidate]) -> tuple[list[str], list[str], list[str]]:
    """고른 후보들 → (sido_codes, sigungu_codes, legal_dong_codes) — region 행의 D2-2 컬럼."""
    legal = sorted({c for s in selections for c in s.legal_dong_codes})
    sgg = sorted({c[:5] for c in legal})
    sido = sorted({c[:2] for c in legal})
    return sido, sgg, legal


def _bool(v: str) -> bool:
    return v.strip().lower() not in ("0", "false", "f", "n", "no", "폐지", "")


def load_reference_csv(directory: Path) -> ReferenceData:
    """legal_dong.csv · admin_dong.csv · admin_legal_map.csv (헤더 = 테이블 컬럼 이름, UTF-8)."""

    def rows(name: str) -> list[dict[str, str]]:
        p = directory / name
        if not p.exists():
            return []
        with p.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    legal = [
        LegalRow(
            code=r["code"],
            sido_name=r["sido_name"],
            sigungu_name=r.get("sigungu_name") or None,
            eupmyeondong_name=r.get("eupmyeondong_name") or None,
            ri_name=r.get("ri_name") or None,
            full_name=r["full_name"],
            sigungu_code=r.get("sigungu_code") or r["code"][:5],
            active=_bool(r.get("active", "1")),
        )
        for r in rows("legal_dong.csv")
    ]
    admin = [
        AdminRow(
            code=r["code"],
            full_name=r["full_name"],
            name=r["name"],
            sigungu_code=r.get("sigungu_code") or r["code"][:5],
            active=_bool(r.get("active", "1")),
        )
        for r in rows("admin_dong.csv")
    ]
    amap = [(r["admin_code"], r["legal_code"]) for r in rows("admin_legal_map.csv")]
    return ReferenceData(legal=legal, admin=admin, admin_legal=amap)


def load_reference_db(session: Session) -> ReferenceData:
    legal = [
        LegalRow(
            code=r.code,
            sido_name=r.sido_name,
            sigungu_name=r.sigungu_name,
            eupmyeondong_name=r.eupmyeondong_name,
            ri_name=r.ri_name,
            full_name=r.full_name,
            sigungu_code=r.sigungu_code,
            active=bool(r.active),
        )
        for r in session.scalars(select(LegalDong))
    ]
    admin = [
        AdminRow(
            code=r.code,
            full_name=r.full_name,
            name=r.name,
            sigungu_code=r.sigungu_code,
            active=bool(r.active),
        )
        for r in session.scalars(select(AdminDong))
    ]
    amap = [(m.admin_code, m.legal_code) for m in session.scalars(select(AdminLegalMap))]
    return ReferenceData(legal=legal, admin=admin, admin_legal=amap)


def resolve_region_db(session: Session, q: str, *, limit: int = 50) -> list[RegionCandidate]:
    """GET /regions/resolve 용 DB 래퍼(WP5가 부른다)."""
    return resolve_region(q, load_reference_db(session), limit=limit)
