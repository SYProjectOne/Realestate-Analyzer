"""R4-FIX M6 (D18-7) — 주소 → 법정동: 신설 구(분구) 주소 표기와 참조 표의 구 표기 차이를 흡수한다.

R4: '왕길역 아테라'(단지 34·39·40·41·81, 민영) 주소 '인천광역시 서구 봉화로 60-11 (오류동, 왕길역 아테라)' — 참조 표에서
서구는 폐지(검단구·서해구로 분구), 같은 이름 '오류동' 이 계양구(활성)·검단구(활성)에 있다. 계양구 전체를 지역에 넣었으므로
둘 다 지역 안 → 모호 → 법정동 NULL → '범위 경계'(제외). 지역 안 민영 후보가 조용히 빠졌다.

참조 행은 R4 DB legal_dong 의 실제 행(코드·이름·활성)에서 필요한 것만 옮겼다.
"""

# ruff: noqa: E501  (한국어 docstring·참조 행)

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Complex, LegalDong, Region
from app.normalize.living_area import assign_complex_area

OLD_SEOGU = {  # 분구 전 서구(폐지)
    "2826011900": "오류동", "2826012000": "왕길동", "2826011600": "당하동", "2826011700": "원당동",
    "2826012100": "불로동", "2826011800": "마전동", "2826010100": "백석동", "2826010200": "시천동",
    "2826010300": "검암동", "2826010400": "경서동", "2826010500": "공촌동",
}  # fmt: skip
GEOMDAN = {  # 신설 검단구(활성)
    "2829010100": "백석동", "2829010300": "마전동", "2829010400": "당하동", "2829010500": "원당동",
    "2829010800": "오류동", "2829010900": "왕길동", "2829011000": "불로동",
}  # fmt: skip
SEOHAE = {"2827510100": "검암동", "2827510200": "경서동", "2827510300": "공촌동"}  # 신설 서해구(활성)
GYEYANG = {"2824511800": "오류동", "2824510300": "작전동", "2824510100": "효성동", "2824510200": "계산동"}  # fmt: skip


def _ld(code: str, gu: str, dong: str, *, active: bool) -> LegalDong:
    return LegalDong(
        code=code, sido_name="인천광역시", sigungu_name=gu, eupmyeondong_name=dong, ri_name=None,
        full_name=f"인천광역시 {gu} {dong}", sigungu_code=code[:5], active=active, source_date="2026-10-12",
    )  # fmt: skip


def _seed(s: Session) -> Region:
    for c, n in OLD_SEOGU.items():
        s.add(_ld(c, "서구", n, active=False))
    for c, n in GEOMDAN.items():
        s.add(_ld(c, "검단구", n, active=True))
    for c, n in SEOHAE.items():
        s.add(_ld(c, "서해구", n, active=True))
    for c, n in GYEYANG.items():
        s.add(_ld(c, "계양구", n, active=True))
    scope = sorted([*GEOMDAN, *GYEYANG])  # R4 지역: 검단구 동 선택 + 계양구 전체
    region = Region(
        name="t", query_text="t", selections=[], sido_codes=["28"], sigungu_codes=["28290", "28245"],
        legal_dong_codes=scope, living_areas=[{"id": "la_2", "name": "검단", "legal_dong_codes": sorted(GEOMDAN)},
                                              {"id": "la_3", "name": "계양", "legal_dong_codes": sorted(GYEYANG)}],
        age_premium_coef={}, applyhome_query={}, status="ready", created_at="2026-10-12T06:00:00+09:00",
    )  # fmt: skip
    s.add(region)
    s.flush()
    return region


def _cx(s: Session, region: Region, address: str) -> Complex:
    cx = Complex(region_id=region.id, name="x", address=address, former_names=[], apply_dates=[], contract_dates=[],
                 inclusion_class="미분류")  # fmt: skip
    s.add(cx)
    s.flush()
    return cx


def test_old_gu_address_maps_to_split_successor(db_session: Session) -> None:
    region = _seed(db_session)
    cx = _cx(db_session, region, "인천광역시 서구 봉화로 60-11 (오류동, 왕길역 아테라)")
    out = assign_complex_area(db_session, cx)
    assert (out.legal_dong_code, out.in_region, cx.living_area) == ("2829010800", True, "la_2")
    assert cx.inclusion_class == "미분류", "범위 경계가 아니다 — 분류는 판정기 몫"


def test_current_gu_address_still_exact(db_session: Session) -> None:
    region = _seed(db_session)
    a = _cx(db_session, region, "인천광역시 계양구 오류동 123")
    b = _cx(db_session, region, "인천광역시 검단구 왕길동 1")
    assert assign_complex_area(db_session, a).legal_dong_code == "2824511800"
    assert assign_complex_area(db_session, b).legal_dong_code == "2829010900"


def test_no_old_row_stays_ambiguous(db_session: Session) -> None:
    """구 이름이 없는 주소(오류동만)는 여전히 모호 — 추측하지 않는다."""
    region = _seed(db_session)
    cx = _cx(db_session, region, "인천광역시 오류동 왕길역 아테라")
    out = assign_complex_area(db_session, cx)
    assert out.legal_dong_code is None and cx.inclusion_class == "범위 경계"
