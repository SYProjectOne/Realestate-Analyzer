"""R6-DONG — 운영 첫 실데이터(인천, 스냅샷 1, 단지 101) 에서 18 단지의 법정동이 틀리거나 비었다.

참조 표(``fixtures/r6_dong/*.csv``)는 운영 DB 의 실제 행(법정동코드 전체자료·jscode, 공공누리 1유형)에서 인천 전체(폐지 포함)·
전국 시도/시군구 행·같은 이름 읍면동 행·인천 행정동/매핑만 옮겼다. 주소 문자열은 운영 DB 의 실제 단지 주소(공개 분양 정보)다.

| 원인 | 실제 주소(단지 id) | 테스트 |
| --- | --- | --- |
| 분구·통합 전 구 이름 + 여러 동 나열 | 중구 운서동, 운남동…(25) · 서구 가정동, 청라동(18) | ``test_old_gu_dong_list`` |
| 통합 구(제물포구 = 옛 중구 일부 + 옛 동구) | 중구 신포동 · 동구 송림동(합성 주소, 실제 참조 행) | ``test_old_gu_merged_successor`` |
| 행정동 이름(번지 주소) | 남동구 간석1동(24) · 부평구 산곡1동(46) · 미추홀구 학익2동(82) | ``test_admin_dong_lot_address`` |
| 여러 시도에 걸친 주소 → 지역 밖 동 | 계양구 귤현동 … 경기도 부천시 대장동 …(2·4·17) | ``test_multi_region_prefers_first_in_region`` |
| 동 없는 주소 + 시군구 + 지구 이름에 동 | 서해구 인천검암역세권(5) | ``test_district_name_with_sigungu`` |
| 동·구 모두 없음 / 옛 중구(두 구로 갈림) + 도로명 | 21·65·84·95 | ``test_no_dong_stays_boundary`` |
| 회귀: 서구 오류동 → 검단구(계양구 오류동이 지역 안에 있어도) | 왕길역 아테라 | ``test_split_successor_with_real_reference`` |
"""

# ruff: noqa: E501  (한국어 docstring·실제 주소)

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models import AdminDong, AdminLegalMap, Complex, LegalDong, Region
from app.normalize.living_area import assign_complex_area, default_living_areas, living_area_of
from app.normalize.region_resolve import ReferenceData, load_reference_csv

R6 = Path(__file__).parent / "fixtures" / "r6_dong"


def load_r6_reference(s: Session) -> ReferenceData:
    ref = load_reference_csv(R6)
    for r in ref.legal:
        s.add(
            LegalDong(
                code=r.code, sido_name=r.sido_name, sigungu_name=r.sigungu_name, eupmyeondong_name=r.eupmyeondong_name,
                ri_name=r.ri_name, full_name=r.full_name, sigungu_code=r.sigungu_code, active=r.active,
                source_date="2026-10-13",
            )
        )  # fmt: skip
    for a in ref.admin:
        s.add(
            AdminDong(code=a.code, full_name=a.full_name, name=a.name, sigungu_code=a.sigungu_code, active=a.active,
                      source_date="2026-10-12")
        )  # fmt: skip
    for adm, lc in ref.admin_legal:
        s.add(AdminLegalMap(admin_code=adm, legal_code=lc))
    s.flush()
    return ref


def incheon_region(s: Session, ref: ReferenceData) -> Region:
    """운영 지역 1('인천' 시도 선택)과 같은 구성: 인천 활성 법정동 전부, 시군구마다 생활권 1개."""
    codes = sorted(r.code for r in ref.legal if r.active and r.code.startswith("28") and r.eupmyeondong_name)
    region = Region(
        name="인천", query_text="인천", selections=[], sido_codes=["28"], sigungu_codes=sorted({c[:5] for c in codes}),
        legal_dong_codes=codes, living_areas=default_living_areas(codes, ref.legal), age_premium_coef={},
        applyhome_query={}, status="ready", created_at="2026-10-13T06:00:00+09:00",
    )  # fmt: skip
    s.add(region)
    s.flush()
    return region


@pytest.fixture
def incheon(db_session: Session) -> Region:
    return incheon_region(db_session, load_r6_reference(db_session))


def _cx(
    s: Session, region: Region, address: str, *, code: str | None = None, cls: str = "범위 경계"
) -> Complex:
    cx = Complex(region_id=region.id, name="x", address=address, former_names=[], apply_dates=[], contract_dates=[],
                 inclusion_class=cls, legal_dong_code=code)  # fmt: skip
    s.add(cx)
    s.flush()
    return cx


def _check(s: Session, region: Region, address: str, want: str, *, code: str | None = None) -> None:
    cx = _cx(s, region, address, code=code)
    out = assign_complex_area(s, cx)
    assert out.legal_dong_code == want, (address, out.legal_dong_code)
    assert cx.legal_dong_code == want and out.in_region
    assert cx.living_area == living_area_of(want, region.living_areas or []) and cx.living_area is not None
    assert cx.inclusion_class == "미분류", "지역 법정동에 맞으면 범위 경계에서 풀려 다음 P4 classify 가 분류"


def test_old_gu_dong_list(db_session: Session, incheon: Region) -> None:
    """옛 구 이름 + 동 나열: 첫 동을 새 구(참조 표의 폐지 행·이름 겹침으로 찾은 후계 구)에서."""
    _check(
        db_session,
        incheon,
        "인천광역시 중구 운서동, 운남동, 운북동, 중산동 일원 영종하늘도시 내 A24블록",
        "2815510300",
    )
    _check(
        db_session,
        incheon,
        "인천광역시 서구 가정동, 청라동 일원 인천가정2 공공주택지구내 B2블록",
        "2827510600",
    )


def test_old_gu_merged_successor(db_session: Session, incheon: Region) -> None:
    """제물포구는 옛 중구 일부 + 옛 동구 전부 — 어느 쪽 옛 이름이든 제물포구로(R4 M6 규칙은 한 옛 구만 봤다)."""
    sinpo = (
        db_session.query(LegalDong)
        .filter_by(sigungu_code="28125", eupmyeondong_name="신포동", active=True)
        .one()
    )
    songnim = (
        db_session.query(LegalDong)
        .filter_by(sigungu_code="28125", eupmyeondong_name="송림동", active=True)
        .one()
    )
    _check(db_session, incheon, "인천광역시 중구 신포동 1-1", sinpo.code)
    _check(db_session, incheon, "인천광역시 동구 송림동 100", songnim.code)


def test_admin_dong_lot_address(db_session: Session, incheon: Region) -> None:
    """행정동 이름(간석1동) → 행정동·법정동 매핑(admin_legal_map) → 법정동."""
    _check(db_session, incheon, "인천광역시 남동구 간석1동 311-1번지 일원", "2820010200")
    _check(db_session, incheon, "인천광역시 부평구 산곡1동 87-903번지 일원", "2823710300")
    _check(db_session, incheon, "인천광역시 미추홀구 학익2동 290-1", "2817710300")


def test_admin_dong_many_legal_stays_ambiguous(db_session: Session, incheon: Region) -> None:
    """행정동이 법정동 여럿(영종동 → 중산동·운남동·운북동)이고 번지·같은 이름 법정동이 없으면 고르지 않는다(모호)."""
    cx = _cx(db_session, incheon, "인천광역시 영종구 영종동 일원", code=None, cls="미분류")
    out = assign_complex_area(db_session, cx)
    assert out.legal_dong_code is None and cx.inclusion_class == "범위 경계"


def test_multi_region_prefers_first_in_region(db_session: Session, incheon: Region) -> None:
    """여러 시도에 걸친 주소: 지역 안 첫 동(계양구 귤현동). 지역 밖 동(부천 대장동 4119610600)은 지역 안 동이 있으면 고르지 않는다."""
    for addr in (
        "인천광역시 계양구 귤현동, 동양동, 박촌동, 병방동, 상야동, 경기도 부천시 대장동, 서울특별시 강서구 오곡동 일원 인천계양 테크노밸리 공공주택지구 내 A17블록",
        "인천광역시 계양구 귤현동, 동양동, 박촌동, 병방동, 상야동 및 경기도 부천시 대장동, 서울특별시 강서구 오곡동 일원 인천계양 테크노밸리 공공주택지구 내 A6블록",
    ):
        _check(db_session, incheon, addr, "2824511100", code="4119610600")


def test_out_of_region_address_still_boundary(db_session: Session, incheon: Region) -> None:
    """회귀: 지역 밖 동만 있는 주소는 그 법정동 + '범위 경계'(D2-6)."""
    cx = _cx(db_session, incheon, "경기도 부천시 대장동 1", cls="미분류")
    out = assign_complex_area(db_session, cx)
    assert (out.legal_dong_code, out.in_region, cx.inclusion_class) == ("4119610600", False, "범위 경계")


def test_district_name_with_sigungu(db_session: Session, incheon: Region) -> None:
    """동 토큰이 없어도 시군구 + 지구 이름 안의 그 구 법정동 이름(검암)이 하나뿐이면 그 법정동."""
    _check(db_session, incheon, "인천광역시 서해구 인천검암역세권 공공주택지구 내 B-1BL", "2827510100")


@pytest.mark.parametrize(
    "address",
    [
        "인천광역시 중구 자연대로 667(오션포레베네스트하우스)",  # 옛 중구는 제물포구·영종구로 갈림, 도로명뿐
        "인천광역시 중구 영종국제도시 A26BL",
        "인천광역시 인천경제자유구역 영종지구 영종국제도시 내 A-42BL",  # 시군구 없음
        "용현ㆍ학익 1블록 도시개발구역 내 공동1-1BL",  # 시도·시군구 없음
    ],
    ids=["old_gu_road", "old_gu_no_dong", "no_sigungu", "no_sido"],
)
def test_no_dong_stays_boundary(db_session: Session, incheon: Region, address: str) -> None:
    """동도 복구할 시군구+동 이름도 없으면 추측하지 않는다(D2-6·D21-6 '범위 경계')."""
    cx = _cx(db_session, incheon, address, cls="미분류")
    out = assign_complex_area(db_session, cx)
    assert out.legal_dong_code is None and cx.legal_dong_code is None and cx.inclusion_class == "범위 경계"


def test_split_successor_with_real_reference(db_session: Session, incheon: Region) -> None:
    """회귀(R4 M6): 서구 오류동 → 검단구 오류동. 실제 참조 표에서 계양구 오류동도 지역 안이지만 서구의 후계 구가 아니다."""
    _check(db_session, incheon, "인천광역시 서구 봉화로 60-11 (오류동, 왕길역 아테라)", "2829010800")
    _check(db_session, incheon, "인천광역시 계양구 오류동 123", "2824511800")


def test_rederive_corrects_stored_rows_with_event_and_is_idempotent(
    db_session: Session, incheon: Region
) -> None:
    """이미 저장된 단지(옛 규칙의 틀린 법정동·NULL)를 지금 규칙으로 다시 맞춘다: 바뀐 단지마다 change_event(complex·
    legal_dong_code, critical), 다시 돌리면 변경·이벤트 0(D23-1 멱등성)."""
    from app.normalize.living_area import rederive_region_dongs

    wrong = _cx(
        db_session,
        incheon,
        "인천광역시 계양구 귤현동, 동양동, 박촌동, 병방동, 상야동, 경기도 부천시 대장동, 서울특별시 강서구 오곡동 일원 인천계양 테크노밸리 공공주택지구 내 A9블록",
        code="4119610600",
    )
    empty = _cx(db_session, incheon, "인천광역시 남동구 간석1동 311-1번지 일원")
    keep = _cx(db_session, incheon, "인천광역시 중구 자연대로 667(오션포레베네스트하우스)")
    ok = _cx(db_session, incheon, "인천광역시 계양구 오류동 123", code="2824511800", cls="private_sale_apt")
    ok.living_area = living_area_of("2824511800", incheon.living_areas or [])
    no_addr = Complex(region_id=incheon.id, name="공고 예정", address=None, former_names=[], apply_dates=[],
                      contract_dates=[], inclusion_class="미분류")  # fmt: skip
    db_session.add(no_addr)
    db_session.flush()

    evs = rederive_region_dongs(
        db_session, incheon.id, snapshot_id=None, detected_at="2026-10-13T09:00:00+09:00"
    )
    got = {(e.complex_id, e.entity, e.field, e.old_text, e.new_text, e.severity) for e in evs}
    assert got == {
        (wrong.id, "complex", "legal_dong_code", "4119610600", "2824511100", "critical"),
        (empty.id, "complex", "legal_dong_code", None, "2820010200", "critical"),
    }, got
    assert (wrong.inclusion_class, empty.inclusion_class) == ("미분류", "미분류")
    assert wrong.living_area is not None and empty.living_area is not None
    assert (keep.legal_dong_code, keep.inclusion_class) == (None, "범위 경계")
    assert (ok.legal_dong_code, ok.inclusion_class) == ("2824511800", "private_sale_apt"), (
        "맞는 단지는 그대로"
    )
    assert (no_addr.legal_dong_code, no_addr.inclusion_class) == (None, "미분류"), (
        "주소 없는 단지(공고 예정)는 그대로"
    )

    def state() -> list[tuple[object, ...]]:
        return [
            (c.id, c.legal_dong_code, c.living_area, c.inclusion_class)
            for c in db_session.query(Complex).order_by(Complex.id)
        ]

    before = state()
    assert (
        rederive_region_dongs(
            db_session, incheon.id, snapshot_id=None, detected_at="2026-10-14T09:00:00+09:00"
        )
        == []
    )
    assert state() == before
