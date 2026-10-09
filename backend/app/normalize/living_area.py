"""생활권 (DECISIONS D2-1·D2-2·D2-6, contracts/schemas/living_area.json).

- ``default_living_areas``: 기본 생활권 = 시군구 1개당 1개(이름은 시군구 이름, id는 'la_1'…).
- ``validate_living_areas`` / ``apply_living_area_edit``: 편집 검증 — region의 모든 법정동이
  정확히 한 생활권에 속해야 한다(중복·누락·지역 밖 코드·빈 생활권은 오류 → API 422).
  id는 생성 후 바뀌지 않는다.
- ``assign_legal_dong`` / ``assign_complex_area``: 단지 주소의 읍면동·리 이름 → 법정동 코드 → 생활권 id.
  지역 법정동에 매칭이 안 되면 단지를 버리지 않고 inclusion_class='범위 경계'(D2-6).
- ``aggregate_households``: 생활권 세대수 = 소속 법정동에 걸친 행정동 세대수 합.
  행정동 1:N 법정동은 균등 분할. 라벨 '추정', reason '주민등록 세대'(고정).
  공급 기준치 U_ref = 세대수 × supply_ref_pct(라벨 추정).

문자열 매칭과 산술뿐이다(판단 아님). 지역명은 참조 테이블에서만 온다.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AdminLegalMap, Complex, HouseholdStat, LegalDong, Region
from app.normalize.region_resolve import LegalRow, normalize_name

__all__ = [
    "HOUSEHOLD_LABEL",
    "HOUSEHOLD_REASON",
    "AssignResult",
    "HouseholdInput",
    "LivingAreaError",
    "LivingAreaIssue",
    "aggregate_households",
    "apply_living_area_edit",
    "assign_complex_area",
    "assign_legal_dong",
    "default_living_areas",
    "household_facts",
    "living_area_of",
    "region_household_facts",
    "validate_living_areas",
]

HOUSEHOLD_LABEL = "추정"
HOUSEHOLD_REASON = "주민등록 세대"
_ID_RE = re.compile(r"^la_[0-9A-Za-z_]+$")


# ---------------------------------------------------------------- 기본·편집·검증


def default_living_areas(legal_dong_codes: Sequence[str], legal: Iterable[LegalRow]) -> list[dict[str, Any]]:
    """시군구 1개당 생활권 1개. 순서 = 법정동 코드 순서에서 시군구가 처음 나온 순서."""
    by_code = {r.code: r for r in legal}
    groups: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for code in legal_dong_codes:
        sgg = code[:5]
        groups.setdefault(sgg, []).append(code)
        r = by_code.get(code)
        if sgg not in names and r is not None:
            names[sgg] = r.sigungu_name or r.sido_name
    return [
        {"id": f"la_{i}", "name": names.get(sgg, sgg), "legal_dong_codes": codes, "households": None}
        for i, (sgg, codes) in enumerate(groups.items(), start=1)
    ]


@dataclass(frozen=True)
class LivingAreaIssue:
    kind: str  # duplicate | missing | unknown | empty | name | duplicate_id | bad_id
    detail: str
    code: str | None = None
    areas: tuple[str, ...] = ()


class LivingAreaError(ValueError):
    """생활권 편집 검증 실패(API는 422 validation_error로 바꾼다)."""

    def __init__(self, issues: list[LivingAreaIssue]) -> None:
        self.issues = issues
        super().__init__("; ".join(i.detail for i in issues))


def validate_living_areas(
    region_codes: Sequence[str], areas: Sequence[Mapping[str, Any]]
) -> list[LivingAreaIssue]:
    """모든 법정동은 정확히 한 생활권에. 문제 목록(빈 목록 = 통과)."""
    issues: list[LivingAreaIssue] = []
    region_set = set(region_codes)
    owner: dict[str, list[str]] = defaultdict(list)
    seen_ids: set[str] = set()
    for a in areas:
        aid = str(a.get("id") or "")
        name = str(a.get("name") or "").strip()
        codes = list(a.get("legal_dong_codes") or [])
        if aid:
            if not _ID_RE.match(aid):
                issues.append(LivingAreaIssue("bad_id", f"생활권 id 형식 오류: {aid}", areas=(aid,)))
            if aid in seen_ids:
                issues.append(LivingAreaIssue("duplicate_id", f"생활권 id 중복: {aid}", areas=(aid,)))
            seen_ids.add(aid)
        if not name or len(name) > 64:
            issues.append(LivingAreaIssue("name", f"생활권 이름은 1~64자: {aid or name!r}", areas=(aid,)))
        if not codes:
            issues.append(LivingAreaIssue("empty", f"법정동이 없는 생활권: {name or aid}", areas=(aid,)))
        for c in codes:
            owner[c].append(aid or name)
    for c, owners in owner.items():
        if c not in region_set:
            issues.append(LivingAreaIssue("unknown", f"지역에 없는 법정동: {c}", code=c, areas=tuple(owners)))
        if len(owners) > 1:
            issues.append(
                LivingAreaIssue(
                    "duplicate", f"법정동 {c}가 생활권 {len(owners)}곳에 속함", code=c, areas=tuple(owners)
                )
            )
    for c in region_codes:
        if c not in owner:
            issues.append(LivingAreaIssue("missing", f"어느 생활권에도 없는 법정동: {c}", code=c))
    return issues


def apply_living_area_edit(
    region_codes: Sequence[str],
    existing: Sequence[Mapping[str, Any]],
    inputs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """PUT /regions/{id}/living-areas 본문(LivingAreaInput[]) → 새 living_areas. 검증 실패면 LivingAreaError.

    id가 있으면 그 생활권을 고치고, 없으면 새 id(la_<n>, 기존 최대 번호 + 1)를 준다. 입력에 없는 기존 생활권은
    삭제된다 — 그 법정동이 다른 생활권으로 옮겨지지 않았으면 '누락' 오류가 된다(비어 있을 때만 삭제 허용).
    구성이 그대로인 생활권은 세대수(households)를 유지하고, 바뀐 생활권은 null(재집계 대상)로 둔다.
    """
    old = {str(a["id"]): a for a in existing}
    known_ids = set(old)
    unknown_ids = [str(i["id"]) for i in inputs if i.get("id") and str(i["id"]) not in known_ids]
    nums = [int(m.group(1)) for a in existing if (m := re.match(r"^la_(\d+)$", str(a["id"])))]
    next_n = max(nums, default=0) + 1
    out: list[dict[str, Any]] = []
    for item in inputs:
        aid = str(item.get("id") or "")
        if not aid:
            aid = f"la_{next_n}"
            next_n += 1
        codes = list(item.get("legal_dong_codes") or [])
        prev = old.get(aid)
        keep = prev is not None and sorted(prev.get("legal_dong_codes") or []) == sorted(codes)
        out.append(
            {
                "id": aid,
                "name": str(item.get("name") or "").strip(),
                "legal_dong_codes": codes,
                "households": prev.get("households") if (keep and prev is not None) else None,
            }
        )
    issues = validate_living_areas(region_codes, out)
    issues += [LivingAreaIssue("unknown_id", f"없는 생활권 id: {i}", areas=(i,)) for i in unknown_ids]
    if issues:
        raise LivingAreaError(issues)
    return out


def living_area_of(code: str | None, areas: Sequence[Mapping[str, Any]]) -> str | None:
    if code is None:
        return None
    for a in areas:
        if code in (a.get("legal_dong_codes") or []):
            return str(a["id"])
    return None


# ---------------------------------------------------------------- 주소 → 법정동


_TOKEN_SPLIT = re.compile(r"[\s(),\[\]/·]+")


def _tokens(address: str) -> set[str]:
    return {t for t in _TOKEN_SPLIT.split(address) if t}


def assign_legal_dong(
    address: str, legal: Iterable[LegalRow], *, scope: set[str] | None = None
) -> str | None:
    """주소 문자열 → 법정동 코드(유일할 때만). 읍면동 이름이 주소 토큰과 같아야 하고, 리가 있으면 리까지
    맞춘다.
    시군구·시도 이름으로 좁히고, 그래도 여럿이면 scope(지역 법정동) 안의 것으로 좁힌다. 못 정하면 None."""
    toks = _tokens(address)
    toks_norm = {normalize_name(t, sido=True) for t in toks} | toks
    rows = [r for r in legal if r.active and r.eupmyeondong_name and r.eupmyeondong_name in toks]
    if not rows:
        return None
    ri_rows = [r for r in rows if r.ri_name and r.ri_name in toks]
    rows = ri_rows or [r for r in rows if not r.ri_name]

    def narrowed(cands: list[LegalRow], pred: Any) -> list[LegalRow]:
        sub = [r for r in cands if pred(r)]
        return sub or cands

    rows = narrowed(
        rows, lambda r: bool(r.sigungu_name) and all(p in toks for p in (r.sigungu_name or "").split())
    )
    rows = narrowed(
        rows, lambda r: r.sido_name in toks or normalize_name(r.sido_name, sido=True) in toks_norm
    )
    if scope:
        rows = narrowed(rows, lambda r: r.code in scope)
    codes = {r.code for r in rows}
    return codes.pop() if len(codes) == 1 else None


@dataclass(frozen=True)
class AssignResult:
    complex_id: int
    legal_dong_code: str | None
    living_area: str | None
    in_region: bool


def assign_complex_area(session: Session, cx: Complex) -> AssignResult:
    """단지 주소 → legal_dong_code·living_area. 지역 밖이거나 못 맞추면 inclusion_class '범위 경계'(미분류일
    때만)."""
    region = session.get(Region, cx.region_id)
    if region is None or not cx.address:
        return AssignResult(cx.id, cx.legal_dong_code, cx.living_area, False)
    scope = set(region.legal_dong_codes or [])
    names = sorted(_tokens(cx.address))
    rows = [
        _legal_row(r)
        for r in session.scalars(
            select(LegalDong).where(LegalDong.active.is_(True), LegalDong.eupmyeondong_name.in_(names))
        )
    ]
    code = assign_legal_dong(cx.address, rows, scope=scope)
    in_region = code is not None and code in scope
    cx.legal_dong_code = code
    cx.living_area = living_area_of(code, region.living_areas or []) if in_region else None
    if not in_region and cx.inclusion_class in (None, "미분류"):
        cx.inclusion_class = "범위 경계"
    return AssignResult(cx.id, code, cx.living_area, in_region)


def _legal_row(r: LegalDong) -> LegalRow:
    return LegalRow(
        code=r.code,
        sido_name=r.sido_name,
        sigungu_name=r.sigungu_name,
        eupmyeondong_name=r.eupmyeondong_name,
        ri_name=r.ri_name,
        full_name=r.full_name,
        sigungu_code=r.sigungu_code,
        active=bool(r.active),
    )


# ---------------------------------------------------------------- 세대수


@dataclass(frozen=True)
class HouseholdInput:
    admin_code: str
    households: int
    raw_document_id: int | None = None
    ym: str | None = None


@dataclass
class HouseholdAggregate:
    area_id: str
    households: int
    exact: Fraction
    admin_codes: list[str] = field(default_factory=list)
    split_admin_codes: list[str] = field(default_factory=list)  # 1:N 균등 분할된 행정동
    raw_document_ids: list[int] = field(default_factory=list)
    label: str = HOUSEHOLD_LABEL
    reason: str = HOUSEHOLD_REASON


def aggregate_households(
    areas: Sequence[Mapping[str, Any]],
    stats: Iterable[HouseholdInput],
    admin_legal: Iterable[tuple[str, str]],
) -> dict[str, HouseholdAggregate]:
    """생활권별 세대수. 행정동 세대수를 그 행정동에 매핑된 법정동 수로 균등 분할해 법정동에 나눈 뒤 합한다.
    반올림은 마지막에 한 번(사사오입). 매핑이 없는 행정동은 건너뛴다."""
    amap: dict[str, list[str]] = defaultdict(list)
    for adm, lc in admin_legal:
        if lc not in amap[adm]:
            amap[adm].append(lc)
    share: dict[str, Fraction] = defaultdict(Fraction)
    contrib: dict[str, set[str]] = defaultdict(set)
    raw_ids: dict[str, set[int]] = defaultdict(set)
    split: set[str] = set()
    for s in stats:
        legal_codes = amap.get(s.admin_code, [])
        if not legal_codes:
            continue
        if len(legal_codes) > 1:
            split.add(s.admin_code)
        part = Fraction(s.households, len(legal_codes))
        for lc in legal_codes:
            share[lc] += part
            contrib[lc].add(s.admin_code)
            if s.raw_document_id is not None:
                raw_ids[lc].add(s.raw_document_id)
    out: dict[str, HouseholdAggregate] = {}
    for a in areas:
        total = Fraction(0)
        admins: set[str] = set()
        rids: set[int] = set()
        for lc in a.get("legal_dong_codes") or []:
            total += share.get(lc, Fraction(0))
            admins |= contrib.get(lc, set())
            rids |= raw_ids.get(lc, set())
        rounded = int(
            (Decimal(total.numerator) / Decimal(total.denominator)).quantize(Decimal(1), ROUND_HALF_UP)
        )
        out[str(a["id"])] = HouseholdAggregate(
            area_id=str(a["id"]),
            households=rounded,
            exact=total,
            admin_codes=sorted(admins),
            split_admin_codes=sorted(admins & split),
            raw_document_ids=sorted(rids),
        )
    return out


def household_facts(
    aggregates: Mapping[str, HouseholdAggregate],
    *,
    checked_at: str | None,
    supply_ref_pct: Decimal | float | None = None,
) -> dict[str, dict[str, Any]]:
    """집계 → LivingArea.households / supply_ref_units Fact. prov = 세대 현황 원문(rd_<id>).
    원문 id가 없으면 '확인 불가(출처 누락)'로 낸다(빈 출처 금지)."""
    out: dict[str, dict[str, Any]] = {}
    for aid, agg in aggregates.items():
        if not agg.admin_codes:
            fact: dict[str, Any] = {
                "v": None,
                "label": "확인 불가",
                "reason": "세대 현황 없음",
                "prov": None,
                "checked_at": checked_at,
                "unit": "units",
            }
            out[aid] = {"households": fact, "supply_ref_units": None}
            continue
        prov = f"rd_{agg.raw_document_ids[0]}" if agg.raw_document_ids else None
        if prov is None:
            fact = {
                "v": None,
                "label": "확인 불가",
                "reason": "출처 누락",
                "prov": None,
                "checked_at": checked_at,
            }
            out[aid] = {"households": fact, "supply_ref_units": None}
            continue
        fact = {
            "v": agg.households,
            "label": HOUSEHOLD_LABEL,
            "reason": HOUSEHOLD_REASON,
            "prov": prov,
            "checked_at": checked_at,
            "unit": "units",
        }
        ref = None
        if supply_ref_pct is not None:
            units = (Decimal(agg.households) * Decimal(str(supply_ref_pct))).quantize(
                Decimal(1), ROUND_HALF_UP
            )
            ref = {
                "v": int(units),
                "label": "추정",
                "reason": f"세대수×{Decimal(str(supply_ref_pct)).normalize()}",
                "prov": prov,
                "checked_at": checked_at,
                "unit": "units",
            }
        out[aid] = {"households": fact, "supply_ref_units": ref}
    return out


def region_household_facts(
    session: Session, region: Region, *, checked_at: str | None = None
) -> dict[str, Any]:
    """DB 래퍼: household_stat(admin_dong, 최신 ym)·admin_legal_map → 생활권별 households Fact."""
    stats_rows = list(session.scalars(select(HouseholdStat).where(HouseholdStat.scope_kind == "admin_dong")))
    if not stats_rows:
        return household_facts(aggregate_households(region.living_areas or [], [], []), checked_at=checked_at)
    latest = max(r.ym for r in stats_rows)
    stats = [
        HouseholdInput(r.scope_code, r.households, r.raw_document_id, r.ym)
        for r in stats_rows
        if r.ym == latest
    ]
    amap = [(m.admin_code, m.legal_code) for m in session.scalars(select(AdminLegalMap))]
    aggs = aggregate_households(region.living_areas or [], stats, amap)
    return household_facts(
        aggs, checked_at=checked_at or f"{latest}-01", supply_ref_pct=region.supply_ref_pct
    )
