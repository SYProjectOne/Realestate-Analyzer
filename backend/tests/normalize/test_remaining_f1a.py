"""R3 M5: 청약홈 무순위·임의공급·잔여세대 공고(API·웹) → remaining_event (C8 타임라인의 원천).

kind·notice_no·notice_date·apply_dates·units_by_type·result_text. 공고는 자기 주택관리번호를 가지므로 원래 단지는
정규화한 단지명(괄호 회차 제거) + 법정동으로 찾는다(문자열 처리, 판단 아님). 못 찾거나 여럿이면 같은 이름·법정동의
잔여 공고 단지 중 가장 먼저 생긴 행에 묶는다.
"""

# ruff: noqa: E501  (한국어 docstring·발췌 문구)

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.applyhome import site
from app.models import ChangeEvent, FieldProvenance, Region, RemainingEvent
from app.normalize.remaining import sync_remaining_events

from ._assemble_support import FETCHED, add_complex, api_page, detail_url, model_rows, model_url
from ._support import AddRaw

SONGDO = "2818510600"
DETECTED = "2026-10-09T06:00:00+09:00"


def _remndr_row(
    hm: str, name: str, secd: str, notice: str, rcpt: tuple[str, str], units: int
) -> dict[str, object]:
    return {
        "HOUSE_MANAGE_NO": hm,
        "PBLANC_NO": hm,
        "HOUSE_NM": name,
        "HOUSE_SECD": secd,
        "HOUSE_SECD_NM": {"04": "무순위", "06": "재공급", "11": "임의공급"}[secd],
        "HSSPLY_ADRES": "인천광역시 연수구 송도동 308-1번지",
        "RCRIT_PBLANC_DE": notice,
        "SUBSCRPT_RCEPT_BGNDE": rcpt[0],
        "SUBSCRPT_RCEPT_ENDDE": rcpt[1],
        "PRZWNER_PRESNATN_DE": rcpt[1],
        "TOT_SUPLY_HSHLDCO": units,
        "SUBSCRPT_AREA_CODE_NM": "인천",
    }


COMP_HTML = """<html><body><table class="tbl_st tbl_center" id="compitTbl">
<thead><tr><th>주택형</th><th>공급세대수</th><th>접수건수</th><th>경쟁률</th><th>청약결과</th></tr></thead>
<tbody>
<tr><td>084.9766C</td><td>1</td><td>5</td><td>5.00</td><td>
      청약접수 종료
</td></tr>
</tbody></table></body></html>"""


def _api_notice(
    db_session: Session,
    add_raw: AddRaw,
    region: Region,
    hm: str,
    name: str,
    *,
    secd: str = "04",
    kind: str = "remndr",
    notice: str = "2026-09-10",
    rcpt: tuple[str, str] = ("2026-09-15", "2026-09-15"),
    comp: bool = True,
) -> int:
    """잔여 공고 1건: store 가 만든 자기 단지 행 + API 상세·주택형 원문 + 웹 경쟁률 원문."""
    self_cx = add_complex(
        db_session, region.id, hm, name, address="인천광역시 연수구 송도동 308-1번지", legal_dong_code=SONGDO
    )
    api_kind = "remndr" if kind == "remndr" else "opt"
    add_raw(
        api_page([_remndr_row(hm, name, secd, notice, rcpt, 1)]),
        source_kind="applyhome_detail",
        url=detail_url(hm, api_kind),
        region_id=region.id,
        complex_id=self_cx.id,
        ext="json",
        fetched_at=FETCHED,
    )
    add_raw(
        api_page(model_rows(hm, [("084.9766C", 78400, 1)])),
        source_kind="applyhome_detail",
        url=model_url(hm, api_kind),
        region_id=region.id,
        complex_id=self_cx.id,
        ext="json",
        fetched_at=FETCHED,
    )
    if comp:
        add_raw(
            COMP_HTML,
            source_kind="applyhome_detail",
            url=site.competition_url("remndr", hm, hm),
            region_id=region.id,
            complex_id=self_cx.id,
            ext="html",
            fetched_at=FETCHED,
        )
    return self_cx.id


def _events(db_session: Session) -> list[RemainingEvent]:
    return list(db_session.scalars(select(RemainingEvent).order_by(RemainingEvent.id)))


def test_api_remaining_notice_attaches_to_original_complex(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    original = add_complex(
        db_session,
        region.id,
        "2024000777",
        "더샵 송도마리나베이",
        address="인천광역시 연수구 송도동 308-1",
        legal_dong_code=SONGDO,
    )
    _api_notice(db_session, add_raw, region, "2026910242", "더샵 송도마리나베이(조합원 자격상실세대 3회차)")
    res = sync_remaining_events(db_session, region.id, snapshot_id=None, detected_at=DETECTED)

    [ev] = _events(db_session)
    assert ev.complex_id == original.id
    assert ev.kind == "무순위"
    assert ev.notice_no == "2026910242"
    assert ev.notice_date == "2026-09-10"
    assert ev.apply_dates == ["2026-09-15"]
    assert ev.units_by_type == {"84C": 1}
    assert ev.result_text is not None and "공급 1" in ev.result_text and "5.00" in ev.result_text
    assert ev.raw_document_id is not None
    assert res.inserted == 1 and res.unmatched == []


def test_opt_rounds_without_original_share_one_complex(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    first = _api_notice(
        db_session, add_raw, region, "2026940200", "리아츠 송도(22차)", secd="11", kind="opt", notice="2026-08-01",
        rcpt=("2026-08-05", "2026-08-06"),
    )  # fmt: skip
    _api_notice(
        db_session, add_raw, region, "2026940212", "리아츠 송도(23차)", secd="11", kind="opt", comp=False
    )
    res = sync_remaining_events(db_session, region.id, snapshot_id=None, detected_at=DETECTED)
    evs = _events(db_session)
    assert [(e.kind, e.notice_no, e.complex_id) for e in evs] == [
        ("임의", "2026940200", first),
        ("임의", "2026940212", first),
    ]
    assert evs[0].apply_dates == ["2026-08-05", "2026-08-06"]
    assert evs[1].result_text is None
    assert {u["notice_no"] for u in res.unmatched} == {"2026940200", "2026940212"}  # 원래 단지 못 찾음 기록


def test_resync_is_idempotent_and_new_event_is_critical(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    original = add_complex(
        db_session, region.id, "2024000777", "더샵 송도마리나베이", address="송도동", legal_dong_code=SONGDO
    )
    _api_notice(db_session, add_raw, region, "2026910242", "더샵 송도마리나베이(3회차)")
    first = sync_remaining_events(db_session, region.id, snapshot_id=None, detected_at=DETECTED)
    db_session.add_all(first.events)
    db_session.flush()
    second = sync_remaining_events(db_session, region.id, snapshot_id=None, detected_at=DETECTED)
    assert len(_events(db_session)) == 1
    assert (second.inserted, second.updated) == (0, 0) and second.events == []
    [ev] = first.events
    assert (ev.entity, ev.severity, ev.triggers_rejudge, ev.complex_id) == (
        "remaining_event",
        "critical",
        True,
        original.id,
    )
    assert db_session.scalar(select(func.count()).select_from(ChangeEvent)) == 1


def test_remaining_event_fields_have_provenance(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    _api_notice(db_session, add_raw, region, "2026910242", "더샵 송도마리나베이(3회차)")
    sync_remaining_events(db_session, region.id, snapshot_id=None, detected_at=DETECTED)
    [ev] = _events(db_session)
    fields = {
        fp.field: fp
        for fp in db_session.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "remaining_event",
                FieldProvenance.entity_id == ev.id,
                FieldProvenance.chosen.is_(True),
            )
        )
    }
    assert set(fields) == {"notice_date", "apply_dates", "units"}
    for fp in fields.values():
        assert fp.label == "확인됨" and fp.url and fp.checked_at and fp.raw_document_id


WEB_LIST = """<html><body><table><tbody>
<tr data-pbno="2026940300" data-hmno="2026940300" data-hsecd="11" data-honm="송도 웹 단지(2차)">
<td>인천</td><td>임의공급</td><td class="txt_l"><a href="#a"><b>송도 웹 단지(2차)</b></a></td>
<td>시행사</td><td>2026-10-01</td><td>2026-10-05 ~ 2026-10-06</td><td>2026-10-08</td><td></td></tr>
</tbody></table></body></html>"""

WEB_DETAIL = """<html><body><div id="printArea">
<table class="tbl_st"><caption class="blind">입주자모집공고 주요정보</caption>
<thead><tr><th scope="col" colspan="2">송도 웹 단지(2차)</th></tr></thead>
<tbody><tr><td>공급위치</td><td class="txt_l">인천광역시 연수구 송도동 77</td></tr>
<tr><td>공급규모</td><td class="txt_l">3세대</td></tr></tbody></table>
<table class="tbl_st"><caption class="blind">입주자모집공고 청약일정.</caption><tbody>
<tr><th scope="row">모집공고일</th><td class="txt_l">2026-10-01</td></tr>
<tr><th scope="row">청약접수</th><td class="txt_l" id="subscrptRceptPd">
   2026-10-05 ~ 2026-10-06
</td></tr>
<tr><th scope="row">당첨자 발표일</th><td class="txt_l">2026-10-08</td></tr>
</tbody></table>
<table class="tbl_st"><caption class="blind">주택형, 공급세대수, 비고</caption>
<thead><tr><th>주택형</th><th>공급세대수</th><th>비고</th></tr></thead><tbody>
<tr><td>084.9355A</td><td>
   2
</td><td rowspan="2">공급금액 : 사업주체 문의</td></tr>
<tr><td>059.9000B</td><td>1</td></tr>
</tbody></table></div></body></html>"""


def test_web_remaining_notice(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    hm = "2026940300"
    self_cx = add_complex(
        db_session,
        region.id,
        hm,
        "송도 웹 단지(2차)",
        address="인천광역시 연수구 송도동 77",
        legal_dong_code=SONGDO,
    )
    original = add_complex(db_session, region.id, "2025000123", "송도 웹 단지", legal_dong_code=SONGDO)
    form = site.list_form("인천", "202512", "202611", 1)
    add_raw(
        WEB_LIST,
        source_kind="applyhome_list",
        url=site.list_doc_url("remndr", form),
        region_id=region.id,
        ext="html",
    )
    add_raw(
        WEB_DETAIL,
        source_kind="applyhome_detail",
        url=site.detail_url("remndr", hm, hm),
        region_id=region.id,
        complex_id=self_cx.id,
        ext="html",
    )
    sync_remaining_events(db_session, region.id, snapshot_id=None, detected_at=DETECTED)
    [ev] = _events(db_session)
    assert (ev.complex_id, ev.kind, ev.notice_no, ev.notice_date) == (original.id, "임의", hm, "2026-10-01")
    assert ev.apply_dates == ["2026-10-05", "2026-10-06"]
    assert ev.units_by_type == {"84A": 2, "59B": 1}


def test_unknown_supply_kind_is_skipped_not_guessed(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    hm = "2026940300"
    self_cx = add_complex(db_session, region.id, hm, "송도 웹 단지(2차)", legal_dong_code=SONGDO)
    add_raw(
        WEB_DETAIL,
        source_kind="applyhome_detail",
        url=site.detail_url("remndr", hm, hm),
        region_id=region.id,
        complex_id=self_cx.id,
        ext="html",
    )
    res = sync_remaining_events(db_session, region.id, snapshot_id=None, detected_at=DETECTED)
    assert _events(db_session) == []
    assert res.unmatched == [
        {"notice_no": hm, "name": "송도 웹 단지(2차)", "reason": "확인 불가(공급 구분 없음)"}
    ]
