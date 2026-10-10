"""R3f CORE4 — 6차 리뷰 minor 17: ``living_area.assign_complex_area`` 가 모호한 법정동(같은 이름 읍면동)에서 단지의
기존 ``legal_dong_code`` 까지 None 으로 지웠다.

| 리뷰 | 테스트 |
| --- | --- |
| m17 모호 법정동이 기존 법정동 코드를 지우지 않음('범위 경계'는 유지) | ``test_m17_ambiguous_dong_keeps_previous_code`` |
| 회귀: 기존 코드 없으면 None, 분명한 주소는 새 코드 | ``test_m17_unambiguous_address_still_reassigns`` |
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Complex, LegalDong


def _two_same_name_dongs(db_session: Session, region: Any) -> tuple[LegalDong, LegalDong]:
    a = LegalDong(code="2818599901", sido_name="인천광역시", sigungu_name="연수구", eupmyeondong_name="겹친동",
                  ri_name=None, full_name="인천광역시 연수구 겹친동", sigungu_code="28185", active=True, source_date="2026-10-01")  # fmt: skip
    b = LegalDong(code="2824599901", sido_name="인천광역시", sigungu_name="계양구", eupmyeondong_name="겹친동",
                  ri_name=None, full_name="인천광역시 계양구 겹친동", sigungu_code="28245", active=True, source_date="2026-10-01")  # fmt: skip
    db_session.add_all([a, b])
    region.legal_dong_codes = [*(region.legal_dong_codes or []), a.code, b.code]
    db_session.flush()
    return a, b


def test_m17_ambiguous_dong_keeps_previous_code(db_session: Session, region: Any) -> None:
    from app.normalize.living_area import assign_complex_area

    a, _b = _two_same_name_dongs(db_session, region)
    cx = Complex(region_id=region.id, applyhome_id="2026777002", name="겹친동 단지", former_names=[], apply_dates=[],
                 contract_dates=[], inclusion_class="private_sale_apt", address="인천광역시 겹친동 1-1",
                 legal_dong_code=a.code)  # fmt: skip
    db_session.add(cx)
    db_session.flush()
    res = assign_complex_area(db_session, cx)
    assert cx.legal_dong_code == a.code, "모호하다고 이미 아는 법정동을 지우지 않는다"
    assert not res.in_region and cx.inclusion_class == "범위 경계"


def test_m17_unambiguous_address_still_reassigns(db_session: Session, region: Any) -> None:
    from app.normalize.living_area import assign_complex_area

    a, b = _two_same_name_dongs(db_session, region)
    none_cx = Complex(region_id=region.id, applyhome_id="2026777003", name="새 단지", former_names=[], apply_dates=[],
                      contract_dates=[], inclusion_class="미분류", address="인천광역시 겹친동 2-2")  # fmt: skip
    clear_cx = Complex(region_id=region.id, applyhome_id="2026777004", name="분명 단지", former_names=[], apply_dates=[],
                       contract_dates=[], inclusion_class="미분류", address="인천광역시 계양구 겹친동 3-3",
                       legal_dong_code=a.code)  # fmt: skip
    db_session.add_all([none_cx, clear_cx])
    db_session.flush()
    assert (
        assign_complex_area(db_session, none_cx).legal_dong_code is None and none_cx.legal_dong_code is None
    )
    res = assign_complex_area(db_session, clear_cx)
    assert res.legal_dong_code == b.code and clear_cx.legal_dong_code == b.code and res.in_region
