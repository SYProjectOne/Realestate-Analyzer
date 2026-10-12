"""R4 재시험 N7(minor, D21-6) — 동 이름 없는 주소는 같은 단지의 다른 출처 주소로 법정동을 찾고, 없으면 사유를 남긴다.

R4: '인천광역시 서구 검단신도시 RC3BL'(46 검단역 금강펜테리움 더 시글로), '인천광역시 연수구 396-11번지(송도랜드마크시티 6,8공구
A17BL)'(47 송도자이 더 스타)처럼 동 이름이 없는 원 단지 주소(2021 공고 — 원 공고 다시 받기 청약홈 API)는 법정동 NULL → '범위
경계' → 제외. 같은 사업의 잔여 공고문(원 번호 인용)은 '■ 공급위치 : 인천광역시 서구 당하동 1235(…)'·'… 연수구 송도동 396-11
(A17블록)' 로 동을 적는다 — 그 주소는 원 단지 값을 덮지 않으므로(D11-4) 건너뛰어졌다.

D21-6: 단지 주소에 동이 없으면 같은 단지의 다른 출처 주소(청약홈 API·공고문·공식 홈페이지 — 여기서는 원 번호를 인용한 잔여
공고문)로 법정동을 찾는다(단지 주소는 그대로). 그래도 없으면 범위 사유 '범위 경계(주소에 동 없음)'.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.scope import judge_scope
from app.models import Complex, Region
from app.normalize.store import store_raw_document

from . import _r4b

N7 = "n7"
CASES = {
    # 원 공고(청약홈 API, 주소에 동 없음) → 원 번호 인용 잔여 공고문(공급위치에 동)
    "2021000189": (719, 603, "인천광역시 서구 검단신도시 RC3BL", "2826011700"),  # 서구 당하동(테스트 참조표)
    "2021000830": (
        728,
        608,
        "인천광역시 연수구 396-11번지(송도랜드마크시티 6,8공구 A17BL)",
        "2818510600",
    ),  # 연수구 송도동
}


def _store(session: Session, raw_dir: Path, region: Region, raw_id: int) -> None:
    (dto,) = _r4b.insert(session, [_r4b.row(N7, raw_id)], region_id=region.id)
    res = store_raw_document(session, dto, raw_dir=raw_dir)
    assert res is not None
    session.flush()


def test_original_address_without_dong_is_boundary_with_reason(
    db_session: Session, raw_dir: Path, region: Region
) -> None:
    _r4b.install(raw_dir)
    for hm, (api_id, _pdf, address, _code) in CASES.items():
        _store(db_session, raw_dir, region, api_id)
        cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == hm)).one()
        assert cx.address == address and cx.legal_dong_code is None and cx.inclusion_class == "범위 경계"
        sr = judge_scope(
            inclusion_class=cx.inclusion_class, inclusion_decision=cx.inclusion_decision, has_price=True,
            intake_status=None, address=cx.address, legal_dong_code=cx.legal_dong_code,
        )  # fmt: skip
        assert (sr.scope, sr.reason) == ("제외", "범위 경계(주소에 동 없음)"), sr


def test_other_source_address_of_same_complex_gives_legal_dong(
    db_session: Session, raw_dir: Path, region: Region
) -> None:
    _r4b.install(raw_dir)
    for hm, (api_id, pdf_id, address, code) in CASES.items():
        _store(db_session, raw_dir, region, api_id)
        _store(db_session, raw_dir, region, pdf_id)  # 원 번호를 인용한 잔여 공고문(공급위치에 동)
        cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == hm)).one()
        assert cx.address == address, "단지 주소는 원 공고 값 그대로(D11-4)"
        assert cx.legal_dong_code == code, (hm, cx.legal_dong_code)
        assert cx.living_area is not None and cx.inclusion_class != "범위 경계"
        # 원 공고를 다시 저장해도(같은 날 재수집) 찾은 법정동이 지워지지 않는다
        _store(db_session, raw_dir, region, api_id)
        db_session.refresh(cx)
        assert cx.legal_dong_code == code


def test_scope_reason_unchanged_for_addresses_with_dong() -> None:
    sr = judge_scope(
        inclusion_class="범위 경계", inclusion_decision="auto", has_price=True, intake_status=None
    )
    assert sr.reason == "범위 경계(주소가 지역 법정동에 매칭 안 됨)"
    sr2 = judge_scope(
        inclusion_class="범위 경계", inclusion_decision="auto", has_price=True, intake_status=None,
        address="인천광역시 서구 당하동 1235", legal_dong_code=None,
    )  # fmt: skip
    assert sr2.reason == "범위 경계(주소가 지역 법정동에 매칭 안 됨)"
