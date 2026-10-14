"""생활권 (DECISIONS D2-1·D2-2·D2-6, contracts/schemas/living_area.json).

- ``default_living_areas``: 기본 생활권 = 시군구 1개당 1개(이름은 시군구 이름, id는 'la_1'…).
- ``validate_living_areas`` / ``apply_living_area_edit``: 편집 검증 — region의 모든 법정동이
  정확히 한 생활권에 속해야 한다(중복·누락·지역 밖 코드·빈 생활권은 오류 → API 422).
  id는 생성 후 바뀌지 않는다.
- ``assign_complex_area``: 단지 주소 → 법정동 코드(``normalize.dong_match``, R6-DONG) → 생활권 id.
  지역 법정동에 매칭이 안 되면 단지를 버리지 않고 inclusion_class='범위 경계'(D2-6). ``rederive_region_dongs`` 는 이미
  저장된 지역 단지를 지금 규칙으로 다시 맞춘다(바뀌면 change_event). ``assign_legal_dong``(행 목록을 받는 순수 함수)은
  벤치마크 경로(``normalize.benchmark``)가 쓴다.
- ``aggregate_households``: 생활권 세대수 = 소속 법정동에 걸친 행정동 세대수 합.
  행정동 1:N 법정동은 균등 분할. 라벨 '추정', reason '주민등록 세대'(고정).
  공급 기준치 U_ref = 세대수 × supply_ref_pct(라벨 추정).

문자열 매칭과 산술뿐이다(판단 아님). 지역명은 참조 테이블에서만 온다.
"""

# ruff: noqa: E501  (한국어 docstring)

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

from app.models import AdminLegalMap, ChangeEvent, Complex, FieldProvenance, HouseholdStat, Region
from app.normalize.dong_match import DongRef, match_address
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
    "correct_dong",
    "default_living_areas",
    "household_facts",
    "living_area_of",
    "rederive_region_dongs",
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


def assign_complex_area(
    session: Session, cx: Complex, *, alt_addresses: Sequence[str] = (), ref: DongRef | None = None
) -> AssignResult:
    """단지 주소 → legal_dong_code·living_area. 못 맞추면 inclusion_class '범위 경계'(미분류일 때만).

    주소 → 법정동 규칙은 ``normalize.dong_match.match_address``(R6-DONG): 구간별 시도·시군구, 옛 구의 후계 구(분구·통합),
    행정동 이름, 여러 동 나열이면 지역 안 첫 동, 동 없는 주소의 지구 이름(시군구가 있을 때만).

    법정동이 정해졌는데 지역 법정동 밖이면(지역 선택에서 그 법정동·시군구를 뺐다 — R3 4차 M-4) 분류와 무관하게
    '범위 경계'(판정 범위 '제외') — 이전 분류('포함')로 계속 판정 대상이 되지 않는다. 다시 지역에 들어오면
    ``scheduler.handlers.handle_region_expand`` 가 '미분류'로 되돌려 다음 P4 classify 가 다시 분류한다.

    ``alt_addresses``(D21-6, R4 재시험 N7): 단지 주소에 동 이름이 없을 때(참조 표에 맞는 읍면동 토큰 없음 — 'RC3BL'·
    '396-11번지(…A17BL)') 같은 단지의 다른 출처 주소(원 번호를 인용한 잔여 공고문·청약홈 잔여 공고의 공급위치)로 법정동을
    찾는다. 단지 주소(``cx.address``)는 바꾸지 않는다(D11-4). 찾은 법정동은 이후 다시 배정해도 유지된다(아래 '이미 아는
    법정동' 규칙). 지구 이름으로 찾은 법정동(rule 'district')은 다른 출처 주소·이미 아는 법정동보다 약하다.

    ``ref``: 지역 단지 전체를 다시 맞출 때 참조 표 조회 캐시를 같이 쓴다."""
    region = session.get(Region, cx.region_id)
    if region is None:
        return AssignResult(cx.id, cx.legal_dong_code, cx.living_area, False)
    ref = ref or DongRef(session)
    scope = set(region.legal_dong_codes or [])
    if not cx.address:  # 주소 없이 법정동만 아는 단지(시드·옛 행): 그 법정동이 지역 밖이 됐으면 범위 경계
        inside = cx.legal_dong_code is not None and cx.legal_dong_code in scope
        if cx.legal_dong_code is not None and not inside:
            cx.living_area = None
            cx.inclusion_class = "범위 경계"
        elif inside:
            cx.living_area = living_area_of(cx.legal_dong_code, region.living_areas or []) or cx.living_area
        return AssignResult(cx.id, cx.legal_dong_code, cx.living_area, inside)
    m = match_address(cx.address, ref, scope=scope)
    if cx.legal_dong_code is None and m.code is None and not m.candidates:
        # 같은 단지의 다른 출처 주소: 호출자가 준 것(원 단지에 묶인 잔여 공고의 공급위치) + 그 단지 주소의 다른 출처 행 값
        others = [
            v
            for v in session.scalars(
                select(FieldProvenance.value_text).where(
                    FieldProvenance.entity == "complex",
                    FieldProvenance.entity_id == cx.id,
                    FieldProvenance.field == "address",
                    FieldProvenance.value_text.is_not(None),
                )
            )
            if v and v != cx.address
        ]
        for alt in dict.fromkeys([*alt_addresses, *others]):
            alt_code = match_address(alt, ref, scope=scope).code
            if alt_code is not None:
                cx.legal_dong_code = alt_code
                break
    code = m.code if m.rule != "district" else None
    if code is None and cx.legal_dong_code is not None and not m.candidates:
        # 주소에 읍면동 이름이 없다(매칭 불가) — 이미 아는 법정동(다른 출처 주소로 찾음)으로 지역 안팎만 다시 본다
        code = cx.legal_dong_code
    if code is None and m.rule == "district":
        code = m.code
    in_region = code is not None and code in scope
    # 법정동을 못 정했는데 같은 이름 읍면동 후보가 있었다(여러 시군구 — 모호): 분류와 무관하게 '범위 경계'(판정 범위 제외,
    # 법정동 확인 불가) — R3 5차 minor: 이전 분류('포함')로 판정 대상에 남았다
    ambiguous = code is None and m.candidates
    # R3 6차 minor 17: 모호하면 이미 아는 법정동 코드를 None 으로 지우지 않는다(분류만 '범위 경계')
    if not ambiguous:
        cx.legal_dong_code = code
    cx.living_area = living_area_of(code, region.living_areas or []) if in_region else None
    if not in_region and (code is not None or ambiguous or cx.inclusion_class in (None, "미분류")):
        cx.inclusion_class = "범위 경계"
    elif in_region and cx.inclusion_class == "범위 경계":
        # '범위 경계'는 판정기 분류가 아니라 주소 매칭 결과다(D2-6) — 이제 지역 법정동에 맞으면(다른 출처 주소로 법정동을 찾음,
        # D21-6) 미분류로 되돌려 다음 P4 classify 가 포함/제외를 정한다(지역 확장과 같은 규칙)
        cx.inclusion_class = "미분류"
    return AssignResult(cx.id, code, cx.living_area, in_region)


def rederive_region_dongs(
    session: Session, region_id: int, *, snapshot_id: int | None, detected_at: str
) -> list[ChangeEvent]:
    """R6-DONG: 이미 저장된 지역 단지(주소 있는 것)의 법정동·생활권·범위 경계를 지금 규칙으로 다시 맞춘다.

    저장 경로는 주소가 바뀔 때만 다시 배정하므로(``store.write_chosen`` touched), 규칙이 고쳐져도 옛 규칙으로 틀린 법정동(여러
    시도 주소 → 지역 밖 동, 옛 구·행정동 이름 → NULL)이 남는다. 수집 끝(``scheduler.collect``)에 부른다. 법정동이 바뀐 단지마다
    change_event(complex·legal_dong_code, critical — 판정 범위가 바뀐다)를 돌려준다(세션에 넣지 않는다 — 호출자가 첫 적재면
    요약 수로 접고 아니면 넣는다). 바뀐 것이 없으면 아무것도 쓰지 않는다 — 같은 입력이면 다시 불러도 결과가 같다(D23-1)."""
    from app.normalize.changes import make_event

    ref = DongRef(session)
    out: list[ChangeEvent] = []
    rows = session.scalars(
        select(Complex)
        .where(Complex.region_id == region_id, Complex.address.is_not(None), Complex.merged_into_id.is_(None))
        .order_by(Complex.id)
    )
    for cx in list(rows):
        if not cx.address:
            continue
        before = (cx.legal_dong_code, cx.living_area, cx.inclusion_class)
        with session.no_autoflush:
            assign_complex_area(session, cx, ref=ref)
        if cx.legal_dong_code == before[0]:
            # 법정동이 그대로면 아무것도 바꾸지 않는다(생활권·분류는 그 단지를 마지막으로 배정·편집한 경로의 몫)
            cx.living_area, cx.inclusion_class = before[1], before[2]
            continue
        out.append(
            make_event(
                entity="complex",
                entity_id=cx.id,
                field="legal_dong_code",
                old=before[0],
                new=cx.legal_dong_code,
                snapshot_id=snapshot_id,
                complex_id=cx.id,
                detected_at=detected_at,
                severity="critical",
            )
        )
    session.flush()
    return out


def correct_dong(
    session: Session,
    cx: Complex,
    alt_addresses: Sequence[str],
    *,
    snapshot_id: int | None,
    detected_at: str,
) -> ChangeEvent | None:
    """D22-3(R4 3차 N10·N7): 단지 주소에 동이 없어 법정동을 못 정한 단지를 같은 단지의 다른 출처 주소(원 단지에 묶인 잔여
    공고의 공급위치 — 공고문·청약홈 잔여 공고)로 보정한다(``assign_complex_area(alt_addresses=…)``). 보정해 법정동이 바뀌면
    change_event(complex·legal_dong_code, critical — 판정 범위가 바뀐다)를 돌려준다(세션에 넣지 않는다 — 호출자가 첫 적재면
    요약 수로 접고 아니면 넣는다). 주소가 아직 없거나(원 공고 전) 이미 법정동이 있으면 아무것도 하지 않는다."""
    if cx.legal_dong_code is not None or not cx.address or not alt_addresses:
        return None
    before = cx.legal_dong_code
    assign_complex_area(session, cx, alt_addresses=alt_addresses)
    if cx.legal_dong_code == before:
        return None
    from app.normalize.changes import make_event

    return make_event(
        entity="complex",
        entity_id=cx.id,
        field="legal_dong_code",
        old=before,
        new=cx.legal_dong_code,
        snapshot_id=snapshot_id,
        complex_id=cx.id,
        detected_at=detected_at,
        severity="critical",
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
