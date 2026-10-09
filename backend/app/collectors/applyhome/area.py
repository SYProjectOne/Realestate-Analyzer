"""지역(region 행) → 청약홈 조회 조건과 시군구 사전 필터 (DECISIONS D2-6).

- 청약홈 목록은 시도 단위로만 거를 수 있고 값은 시도 *약칭*('경기', '충북')이다. 약칭은 시도 이름에서
  행정구역 접미사를 떼어 만든다(코드에 지역명 표 없음): 이름은 ``legal_dong.sido_name`` → 없으면
  ``region.selections[].full_name`` 첫 토큰에서 온다.
  ``region.applyhome_query['areas']`` ({시도코드: 약칭})가 있으면 그대로 쓴다.
- 사전 필터: 상세의 공급위치를 토큰으로 나눠 region 의 시군구 이름(연속 토큰) 또는 읍면동 이름이 있으면 통과.
  공급위치에 행정구역(시·군·구) 토큰이 하나도 없으면('○○ 도시개발구역 내 공동1BL') 버리지 않고 통과시킨다.
  이름은 ``legal_dong`` 표(시군구 코드·법정동 코드) → 없으면 selections 에서 온다. 시도 전체를 고른 경우는
  그 시도의 모든 행이 통과한다. 이 필터는 '상세를 더 받을지'만 정한다 — 정밀 법정동 배정·범위 경계는 WP2.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import Region
from app.models import LegalDong

__all__ = [
    "AreaFilter",
    "RegionAreas",
    "address_tokens",
    "build_region_areas",
    "has_admin_token",
    "sido_short_name",
]

_SIDO_SUFFIXES = ("특별자치시", "특별자치도", "특별시", "광역시", "자치시", "자치도", "도")
_TOKEN_SPLIT = re.compile(r"[\s(),\[\]{}·/]+")
# 행정구역 토큰(시도·시군구). '검단신도시' 같은 지구 이름은 행정구역이 아니다.
_ADMIN_TOKEN = re.compile(r"^[가-힣]{1,8}(특별시|광역시|특별자치시|특별자치도|도|시|군|구)$")


def has_admin_token(tokens: Iterable[str]) -> bool:
    return any(_ADMIN_TOKEN.match(t) and not t.endswith("신도시") for t in tokens)


def sido_short_name(full: str) -> str:
    """'인천광역시'→'인천', '경기도'→'경기', '충청북도'→'충북', '전북특별자치도'→'전북'."""
    name = full.replace(" ", "")
    for suffix in _SIDO_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break
    if len(name) == 3 and name[-1] in "남북":  # 충청북·경상남·전라북 → 충북·경남·전북
        return name[0] + name[2]
    return name


def address_tokens(address: str) -> list[str]:
    return [t for t in _TOKEN_SPLIT.split(address) if t]


def _contains_seq(tokens: list[str], seq: tuple[str, ...]) -> bool:
    n = len(seq)
    return n > 0 and any(tuple(tokens[i : i + n]) == seq for i in range(len(tokens) - n + 1))


@dataclass(slots=True)
class AreaFilter:
    """시도 1개 안의 사전 필터."""

    sido_code: str
    area: str  # 청약홈 suplyAreaCode 값(시도 약칭)
    whole: bool = False  # 시도 전체 선택
    sigungu: set[tuple[str, ...]] = field(default_factory=set)  # ('수원시', '장안구') 같은 연속 토큰
    dongs: set[str] = field(default_factory=set)

    def matches(self, address: str | None) -> bool:
        if self.whole:
            return True
        if not address:
            return False
        tokens = address_tokens(address)
        if not has_admin_token(tokens):
            # '용현ㆍ학익 1블록 도시개발구역 내 …'처럼 시군구가 없는 공급위치 — 버리지 않는다
            # (범위 경계 판단은 WP2, D2-6)
            return True
        token_set = set(tokens)
        for seq in self.sigungu:
            # '수원시 장안구'는 연속 토큰으로, 또는 마지막 토큰('장안구')만으로도 통과(사전 필터는 너그럽게)
            if _contains_seq(tokens, seq) or seq[-1] in token_set:
                return True
        return bool(self.dongs & token_set)


@dataclass(slots=True)
class RegionAreas:
    filters: dict[str, AreaFilter]  # sido_code → filter

    def by_area(self, area: str) -> AreaFilter | None:
        return next((f for f in self.filters.values() if f.area == area), None)


def _split_selection(kind: str, code: str, full_name: str) -> tuple[str, tuple[str, ...], str | None]:
    """selection → (시도 이름, 시군구 토큰, 읍면동 이름)."""
    tokens = full_name.split()
    if not tokens:
        return "", (), None
    sido, rest = tokens[0], tokens[1:]
    if kind == "sido":
        return sido, (), None
    if kind == "sigungu":
        return sido, tuple(rest), None
    # legal_dong / admin_dong: 마지막 토큰이 읍면동(법정동 코드 끝 2자리 ≠ 00 이면 리까지 있으므로 하나 더 앞)
    has_ri = kind == "legal_dong" and len(code) == 10 and code[8:] != "00" and len(rest) >= 2
    if has_ri:
        return sido, tuple(rest[:-2]), rest[-2]
    if rest:
        return sido, tuple(rest[:-1]), rest[-1]
    return sido, (), None


def build_region_areas(region: Region, session: Session | None) -> RegionAreas:
    sido_codes = [c for c in region.sido_codes if c]
    sido_names: dict[str, str] = {}
    filters: dict[str, AreaFilter] = {}

    # 1) legal_dong 표 (WP1b reference 가 적재)
    ld_rows: list[LegalDong] = []
    if session is not None:
        codes = list(region.legal_dong_codes)
        if codes:
            ld_rows.extend(session.scalars(select(LegalDong).where(LegalDong.code.in_(codes))))
        if region.sigungu_codes:
            ld_rows.extend(
                session.scalars(
                    select(LegalDong).where(
                        LegalDong.sigungu_code.in_(list(region.sigungu_codes)),
                        LegalDong.sigungu_name.is_not(None),
                    )
                )
            )
        if sido_codes:
            for row in session.scalars(
                select(LegalDong).where(LegalDong.code.in_([c + "00000000" for c in sido_codes]))
            ):
                sido_names.setdefault(row.code[:2], row.sido_name)

    region_dongs = set(region.legal_dong_codes)
    region_sgg = set(region.sigungu_codes)
    sgg_by_sido: dict[str, set[tuple[str, ...]]] = {}
    dong_by_sido: dict[str, set[str]] = {}
    for row in ld_rows:
        sc = row.code[:2]
        sido_names.setdefault(sc, row.sido_name)
        if row.sigungu_name and row.sigungu_code in region_sgg:
            sgg_by_sido.setdefault(sc, set()).add(tuple(row.sigungu_name.split()))
        if row.eupmyeondong_name and row.code in region_dongs:
            dong_by_sido.setdefault(sc, set()).add(row.eupmyeondong_name.strip())

    # 2) selections (참조 표가 비어 있어도 동작)
    whole: set[str] = set()
    for sel in region.selections:
        sido_name, sgg, dong = _split_selection(sel.kind, sel.code, sel.full_name)
        sc = sel.code[:2]
        if sido_name:
            sido_names.setdefault(sc, sido_name)
        if sel.kind == "sido":
            whole.add(sc)
        if sgg:
            sgg_by_sido.setdefault(sc, set()).add(sgg)
        if dong:
            dong_by_sido.setdefault(sc, set()).add(dong)

    overrides = _area_overrides(region.applyhome_query)
    for sc in sido_codes or sorted(sido_names):
        area = overrides.get(sc) or (sido_short_name(sido_names[sc]) if sc in sido_names else "")
        if not area:
            continue
        filters[sc] = AreaFilter(
            sido_code=sc,
            area=area,
            whole=sc in whole,
            sigungu=sgg_by_sido.get(sc, set()),
            dongs=dong_by_sido.get(sc, set()),
        )
    return RegionAreas(filters)


def _area_overrides(query: dict[str, object]) -> dict[str, str]:
    raw = query.get("areas")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if isinstance(v, str) and v}
