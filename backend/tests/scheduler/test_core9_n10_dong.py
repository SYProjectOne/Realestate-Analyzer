"""R4 3차 재시험 N10·N7(major, D22-3) — 법정동 보정(다른 출처 주소)은 첫 수집 안에서, 수집 순서와 무관하게, 이벤트와 함께.

R4 3차(2026-10-12): bootstrap 은 잔여 공고(청약홈 API·원 번호를 인용한 잔여 공고문)를 원 공고 다시 받기보다 먼저 저장했다. 그때는 원
단지(46 'RC3BL' · 47 '396-11번지(…A17BL)')에 주소가 없어 잔여 공고의 공급위치(당하동·송도동)를 쓰지 못했고, 원 단지가 생긴 뒤
붙은 잔여 이력(청약홈 API 공급위치)은 주소를 쓰지 않았다 → 1회차 법정동 NULL · '범위 경계' · 제외. 같은 날 재수집에서야 공고문이
다시 저장되며 법정동·생활권이 **조용히**(change_event 0) 채워져 다음 재판정이 판정기를 2회 더 불렀다.

D22-3: 보정은 첫 수집 안에서 끝나고(원 공고를 다시 받은 뒤 잔여 공고의 공급위치로), 순서와 무관하며, 값이 바뀌면 change_event
(첫 적재면 first_load 요약 수)를 남긴다. 녹화: ``r4c_core9`` 그룹 ``n10``·``n10_orig``(R4 3차 원문).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.models import ChangeEvent, Complex, LegalDong
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext

from ..normalize import _r4c
from .conftest import seed_region, seed_scenarios
from .test_r4_fix_d18_4 import Replay

ASOF = "2026-10-12"
ORIGINALS = {
    "2021000189": "2829010400",
    "2021000830": "2818510600",
}  # 당하동(검단구) · 송도동(연수구) — R4 3차 (b) 뒤 값


# 참조 표(행정표준코드) 중 이 녹화에 필요한 행 — 2026 분구: 서구 당하동(폐지) → 검단구 당하동(D18-7 M6)
LEGAL = [
    ("2826011700", "서구", "당하동", "28260", False),
    ("2829010400", "검단구", "당하동", "28290", True),
    ("2818510600", "연수구", "송도동", "28185", True),
]


def _setup(test_settings: Settings, factory: sessionmaker[Session], *, status: str) -> None:
    _r4c.install(test_settings.raw_dir)
    with factory() as s:
        seed_scenarios(s)
        seed_region(s, status=status)
        for code, gu, dong, sgg, active in LEGAL:
            s.add(
                LegalDong(
                    code=code, sido_name="인천광역시", sigungu_name=gu, eupmyeondong_name=dong, ri_name=None,
                    full_name=f"인천광역시 {gu} {dong}", sigungu_code=sgg, active=active, source_date="2026-09-01",
                )
            )  # fmt: skip
        s.commit()


def _originals() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in _r4c.rows("n10_orig"):
        hm = _r4c.house_no(str(r["url"]))
        assert hm is not None
        out.setdefault(hm, []).append(r)
    return out


def _ctx(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], *, originals_first: bool
) -> SchedulerContext:
    api = [r for r in _r4c.rows("n10") if r["source_kind"] != "notice_pdf"]
    pdfs = [r for r in _r4c.rows("n10") if r["source_kind"] == "notice_pdf"]
    orig = _originals()
    if originals_first:
        # 원 공고가 청약홈 단계에서 먼저 온다(잔여 공고문·잔여 공고 원문보다 앞) — 순서만 다르다
        ah = Replay(factory, [r for rows in orig.values() for r in rows] + api)
    else:
        ah = Replay(factory, api, originals=orig)  # R4 3차 bootstrap 순서: 원 공고는 다시 받기로 마지막에
    pdf = Replay(factory, pdfs)
    return make_ctx(collectors={"applyhome": lambda c: ah, "notice_pdf": lambda c: pdf})


def _dongs(factory: sessionmaker[Session]) -> dict[str, tuple[str | None, str | None, str | None]]:
    with factory() as s:
        return {
            str(c.applyhome_id): (c.legal_dong_code, c.living_area, c.inclusion_class)
            for c in s.scalars(select(Complex).where(Complex.applyhome_id.in_(sorted(ORIGINALS))))
        }


def _dong_events(factory: sessionmaker[Session]) -> list[ChangeEvent]:
    with factory() as s:
        return list(
            s.scalars(
                select(ChangeEvent).where(
                    ChangeEvent.entity == "complex", ChangeEvent.field == "legal_dong_code"
                )
            )
        )


def test_bootstrap_order_fills_legal_dong_in_first_collect(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    """R4 3차 bootstrap 순서(잔여 공고 → 원 공고 다시 받기) 그대로: 첫 수집이 끝났을 때 원 단지 법정동이 정해져 있다."""
    _setup(test_settings, factory, status="bootstrapping")
    res = collect(
        _ctx(make_ctx, factory, originals_first=False),
        1,
        ["applyhome_list", "applyhome_detail"],
        asof_date=ASOF,
    )
    assert not res.store_errors, res.store_errors
    got = _dongs(factory)
    assert set(got) == set(ORIGINALS), f"원 공고 다시 받기로 원 단지 행: {sorted(got)}"
    for hm, code in ORIGINALS.items():
        dong, area, cls = got[hm]
        assert dong == code, f"{hm}: 첫 수집 안에서 법정동(다른 출처 주소) — {dong}"
        assert area is not None and cls != "범위 경계", (hm, area, cls)
    # 첫 적재: 이벤트 대신 first_load 요약 수(D18-7)
    assert _dong_events(factory) == []
    with factory() as s:
        summary = s.scalars(select(ChangeEvent).where(ChangeEvent.field == "first_load")).all()
    assert len(summary) == 1


def test_order_does_not_matter(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    """원 공고가 먼저 와도(청약홈 단계) 같은 법정동 — 순서 무관(D22-3)."""
    _setup(test_settings, factory, status="bootstrapping")
    collect(
        _ctx(make_ctx, factory, originals_first=True),
        1,
        ["applyhome_list", "applyhome_detail"],
        asof_date=ASOF,
    )
    got = _dongs(factory)
    assert {hm: v[0] for hm, v in got.items()} == ORIGINALS


def test_correction_outside_first_load_leaves_change_event(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    """첫 적재가 아니면(운영 중 수집) 법정동 보정마다 change_event(complex·legal_dong_code) — 조용히 바뀌지 않는다(N10)."""
    _setup(test_settings, factory, status="ready")
    res = collect(
        _ctx(make_ctx, factory, originals_first=False),
        1,
        ["applyhome_list", "applyhome_detail"],
        asof_date=ASOF,
    )
    evs = {(e.complex_id, e.old_text, e.new_text) for e in _dong_events(factory)}
    with factory() as s:
        ids = {str(c.applyhome_id): c.id for c in s.scalars(select(Complex))}
    assert evs == {(ids[hm], None, code) for hm, code in ORIGINALS.items()}, evs
    assert {e.severity for e in _dong_events(factory)} == {"critical"}, "판정 범위가 바뀐다 → 재판정"
    assert set(res.rejudge_complex_ids) >= {ids[hm] for hm in ORIGINALS}
    # 같은 날 다시 수집하면 이미 정해진 법정동 — 새 이벤트 없음
    again = collect(
        _ctx(make_ctx, factory, originals_first=False),
        1,
        ["applyhome_list", "applyhome_detail"],
        asof_date=ASOF,
    )
    assert again.change_event_ids == [], again.change_event_ids
