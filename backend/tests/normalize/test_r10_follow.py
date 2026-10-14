"""R10-FOLLOW(DECISIONS D29-2·D29-3, 계약 2026-10-09.21) — 정규화 쪽.

- D29-3 체크리스트 kind '청약 접수'·'당첨자 발표': ``complex.apply_dates``(R9-PARSE 모양 ``[{kind, start, end}]`` · 옛 모양
  ``[{kind, date}]``)·``winner_date`` 에서 만든다. 같은 순위·같은 기간의 거주지역 구분은 한 항목('1순위 청약 접수(해당지역·
  기타지역)'), 기한 = 접수 시작일, 끝나지 않은 접수(끝날짜 ≥ 기준일)만. 키 = 종류·순위(값이 바뀌어도 같은 항목 — R3b N-M5),
  같은 날 다시 맞추면 그대로(D23-1·D24-1).
- D29-2 같은 사업 임의공급 공고로 생긴 중복 단지 행(인천 도화 39/99 모양): 공고문이 원 공고 번호를 인용하면(D18-4 인용 — R9-PARSE
  가 고친 정규식) 그 공고의 자기 번호로 이미 있던 단지 행을 원 단지에 병합(``complex.merged_into_id``, 0018) — change_event 1건,
  다시 정규화하면 0. 인용이 없는 잔여 공고 행은 병합하지 않는다(추측 금지).
- 당첨가점 '-'(R10 과제 3): 청약홈 경쟁률 팝업의 당첨가점 칸이 '-' 이면 값 없는 '확인 불가' 후보(사유 '가점 당첨자 없음(청약홈
  '-')')를 낸다 — 팝업을 못 받은 '가점 미수집'과 구별된다. 숫자 칸·0 은 그대로.
"""

# ruff: noqa: E501  (한국어 docstring·발췌)

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, ChecklistItem, Competition, Complex, FieldProvenance, PaymentTerms, Region
from app.normalize.applyhome_parser import parse_applyhome_html
from app.normalize.checklist import item_key, sync_checklist
from app.normalize.store import store_raw_document

from ._support import COMP_URL, FIX, AddRaw, dto
from .test_r9_parse import _dohwa_docs

APPLYHOME = FIX / "applyhome"
ASOF = "2026-10-14"


def _cx(db_session: Session, region: Region, no: str | None, name: str, **kw: Any) -> Complex:
    vals: dict[str, Any] = {
        "region_id": region.id,
        "applyhome_id": no,
        "name": name,
        "former_names": [],
        "apply_dates": [],
        "contract_dates": [],
        "inclusion_class": "private_sale_apt",
        "inclusion_decision": "auto",
    }
    vals.update(kw)
    cx = Complex(**vals)
    db_session.add(cx)
    db_session.flush()
    return cx


def _items(db_session: Session, cid: int, *kinds: str) -> list[tuple[str, str, str | None, str]]:
    stmt = select(ChecklistItem).where(ChecklistItem.complex_id == cid).order_by(ChecklistItem.id)
    if kinds:
        stmt = stmt.where(ChecklistItem.kind.in_(kinds))
    return [(i.kind, i.title, i.due_date, i.status) for i in db_session.scalars(stmt)]


# ====================================================================== D29-3 체크리스트 '청약 접수'·'당첨자 발표'

# 운영 DB(인천, 2026-10-14 읽기 전용) 단지 1 '산곡역자이힐스테이트앤하늘채'의 실제 일정 모양
SANGOK = [
    {"kind": "특별공급", "start": "2026-10-19", "end": "2026-10-19"},
    {"kind": "1순위 해당지역", "start": "2026-10-20", "end": "2026-10-20"},
    {"kind": "1순위 기타지역", "start": "2026-10-20", "end": "2026-10-20"},
    {"kind": "2순위 해당지역", "start": "2026-10-21", "end": "2026-10-21"},
    {"kind": "2순위 기타지역", "start": "2026-10-21", "end": "2026-10-21"},
]
# 운영 DB 단지 2 모양 — 1순위 접수가 여러 날(시작 10-19, 끝 10-22)
WINDOW = [
    {"kind": "1순위 해당지역", "start": "2026-10-19", "end": "2026-10-22"},
    {"kind": "1순위 기타지역", "start": "2026-10-19", "end": "2026-10-22"},
    {"kind": "2순위 해당지역", "start": "2026-10-23", "end": "2026-10-27"},
    {"kind": "2순위 기타지역", "start": "2026-10-23", "end": "2026-10-27"},
]


def test_d29_3_apply_and_winner_items_from_complex_dates(db_session: Session, region: Region) -> None:
    cx = _cx(db_session, region, "2026000101", "산곡역 테스트", apply_dates=SANGOK, winner_date="2026-10-27")
    res = sync_checklist(db_session, region.id, asof_date=ASOF)
    got = _items(db_session, cx.id, "청약 접수", "당첨자 발표")
    assert got == [
        ("청약 접수", "특별공급 청약 접수", "2026-10-19", "open"),
        ("청약 접수", "1순위 청약 접수(해당지역·기타지역)", "2026-10-20", "open"),
        ("청약 접수", "2순위 청약 접수(해당지역·기타지역)", "2026-10-21", "open"),
        ("당첨자 발표", "당첨자 발표", "2026-10-27", "open"),
    ], got
    assert res.by_kind.get("청약 접수") == 3 and res.by_kind.get("당첨자 발표") == 1
    notes = {
        i.title: i.note
        for i in db_session.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == cx.id))
    }
    assert notes["1순위 청약 접수(해당지역·기타지역)"] == "자동: 청약홈 청약 일정 2026-10-20"
    assert notes["당첨자 발표"] == "자동: 청약홈 당첨자 발표일"


def test_d29_3_open_window_kept_until_end_past_ones_not_created(db_session: Session, region: Region) -> None:
    """기한 = 접수 시작일. 접수 중(시작 < 기준일 ≤ 끝)인 항목도 만든다(끝난 접수·지난 발표는 만들지 않는다 — 지난 일정)."""
    cx = _cx(db_session, region, "2026000102", "계양 테스트", apply_dates=WINDOW, winner_date="2026-11-05")
    old = _cx(
        db_session,
        region,
        "2026000103",
        "지난 단지",
        apply_dates=[{"kind": "1순위 해당지역", "start": "2026-09-29", "end": "2026-09-29"}],
        winner_date="2026-10-07",
    )
    sync_checklist(db_session, region.id, asof_date="2026-10-20")
    assert _items(db_session, cx.id, "청약 접수", "당첨자 발표") == [
        ("청약 접수", "1순위 청약 접수(해당지역·기타지역)", "2026-10-19", "open"),
        ("청약 접수", "2순위 청약 접수(해당지역·기타지역)", "2026-10-23", "open"),
        ("당첨자 발표", "당첨자 발표", "2026-11-05", "open"),
    ]
    note = db_session.scalars(
        select(ChecklistItem.note).where(
            ChecklistItem.complex_id == cx.id, ChecklistItem.title.startswith("1순위")
        )
    ).one()
    assert note == "자동: 청약홈 청약 일정 2026-10-19~2026-10-22"
    assert _items(db_session, old.id, "청약 접수", "당첨자 발표") == []


def test_d29_3_old_shape_and_remnant_window(db_session: Session, region: Region) -> None:
    """옛 모양(R9-PARSE 전 저장 — ``{kind, date}``)·잔여·임의 '청약접수' 한 칸."""
    a = _cx(
        db_session,
        region,
        "2026000104",
        "옛 모양",
        apply_dates=[{"kind": "특별공급", "date": "2026-10-20"}, {"kind": "1순위", "date": "2026-10-21"}],
    )
    b = _cx(
        db_session,
        region,
        "2026940105",
        "임의공급 단지",
        apply_dates=[{"kind": "청약접수", "start": "2026-10-16", "end": "2026-10-17"}],
    )
    sync_checklist(db_session, region.id, asof_date=ASOF)
    assert _items(db_session, a.id, "청약 접수") == [
        ("청약 접수", "특별공급 청약 접수", "2026-10-20", "open"),
        ("청약 접수", "1순위 청약 접수", "2026-10-21", "open"),
    ]
    assert _items(db_session, b.id, "청약 접수") == [("청약 접수", "청약 접수", "2026-10-16", "open")]


def test_d29_3_item_keys_are_stable() -> None:
    assert item_key("청약 접수", "1순위 청약 접수(해당지역·기타지역)") == "apply:1순위(해당지역·기타지역)"
    assert item_key("청약 접수", "특별공급 청약 접수") == "apply:특별공급"
    assert item_key("청약 접수", "청약 접수") == "apply:"
    assert item_key("당첨자 발표", "당첨자 발표") == "winner"
    # 사람이 붙인 같은 글자의 다른 종류 항목은 자동 키가 아니다
    assert item_key("법적 확인", "당첨자 발표").startswith("title:")


def test_d29_3_idempotent_and_date_change_updates_same_item(db_session: Session, region: Region) -> None:
    """D23-1·D24-1: 같은 날 다시 맞추면 그대로. 당첨자 발표일이 바뀌면 새 행이 아니라 같은 열린 항목의 기한을 고친다."""
    cx = _cx(db_session, region, "2026000106", "멱등 단지", apply_dates=SANGOK, winner_date="2026-10-27")
    sync_checklist(db_session, region.id, asof_date=ASOF)
    first = _items(db_session, cx.id)
    again = sync_checklist(db_session, region.id, asof_date=ASOF)
    assert (again.inserted, again.updated, again.closed, again.reopened) == (0, 0, 0, 0)
    assert _items(db_session, cx.id) == first
    cx.winner_date = "2026-10-28"
    db_session.flush()
    moved = sync_checklist(db_session, region.id, asof_date=ASOF)
    assert (moved.inserted, moved.updated) == (0, 1)
    assert [x for x in _items(db_session, cx.id, "당첨자 발표")] == [
        ("당첨자 발표", "당첨자 발표", "2026-10-28", "open")
    ]


def test_d29_3_excluded_or_merged_complex_gets_no_items(db_session: Session, region: Region) -> None:
    orig = _cx(db_session, region, "2026000107", "원 단지", apply_dates=SANGOK, winner_date="2026-10-27")
    _cx(
        db_session, region, "2026000108", "범위 밖", apply_dates=SANGOK, winner_date="2026-10-27",
        inclusion_class="범위 경계", inclusion_decision=None,
    )  # fmt: skip
    dup = _cx(db_session, region, "2026940109", "원 단지", apply_dates=SANGOK, winner_date="2026-10-27")
    sync_checklist(db_session, region.id, asof_date=ASOF)
    assert len(_items(db_session, dup.id, "청약 접수", "당첨자 발표")) == 4  # 병합 전 — 같은 일정(재현)
    dup.merged_into_id = orig.id
    db_session.flush()
    sync_checklist(db_session, region.id, asof_date=ASOF)
    opens = db_session.scalars(
        select(ChecklistItem.complex_id).where(
            ChecklistItem.status == "open", ChecklistItem.kind.in_(("청약 접수", "당첨자 발표"))
        )
    ).all()
    assert set(opens) == {orig.id}
    closed = db_session.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == dup.id)).all()
    assert closed and all(i.status == "na" and i.closed_by == "auto" for i in closed)


# ====================================================================== D29-2 같은 사업 중복 단지 행 병합

SCHED = [
    {"seq": n, "due_date": d, "pct": 10.0}
    for n, d in enumerate(
        ["2025-12-19", "2026-08-10", "2027-02-10", "2027-08-10", "2027-11-10", "2028-03-10"], start=1
    )
]


def _ops_dohwa(db_session: Session, region: Region) -> tuple[Complex, Complex]:
    """운영 DB 모양(인천 단지 39·99, 2026-10-14 읽기 전용 확인): 원 단지(2025000397, 본청약 납부 조건)와 인용을 못 읽던 때 임의공급
    번호로 생긴 행(2025940268 — 임의 납부 조건·경쟁률 행)."""
    orig = _cx(db_session, region, "2025000397", "두산위브 더센트럴 도화")
    stray = _cx(db_session, region, "2025940268", "두산위브 더센트럴 도화")
    db_session.add_all(
        [
            PaymentTerms(
                complex_id=orig.id, notice_no="2025000397", notice_kind="본청약",
                effective_from="2025-08-29", interim_schedule=SCHED, price_by_type={},
            ),
            PaymentTerms(
                complex_id=stray.id, notice_no="2025940268", notice_kind="임의",
                effective_from="2025-11-05", interim_schedule=SCHED, price_by_type={},
            ),
            Competition(
                complex_id=stray.id, kind="임의", round="임의 2025940268", type_code="옛행",
                supply=3, applied=10,
            ),
        ]
    )  # fmt: skip
    db_session.flush()
    return orig, stray


def _db_state(db_session: Session) -> list[Any]:
    cxs = [
        (c.id, c.applyhome_id, c.name, tuple(c.former_names or []), c.merged_into_id)
        for c in db_session.scalars(select(Complex).order_by(Complex.id))
    ]
    terms = [
        (t.id, t.complex_id, t.notice_no, json.dumps(t.interim_schedule, sort_keys=True))
        for t in db_session.scalars(select(PaymentTerms).order_by(PaymentTerms.id))
    ]
    comps = [
        (c.id, c.complex_id, c.round, c.type_code, c.applied)
        for c in db_session.scalars(select(Competition).order_by(Competition.id))
    ]
    fps = [
        (p.id, p.entity, p.entity_id, p.field, p.value_text, p.label, p.chosen)
        for p in db_session.scalars(select(FieldProvenance).order_by(FieldProvenance.id))
    ]
    return [*cxs, *terms, *comps, *fps]


def test_d29_2_cited_notice_merges_existing_duplicate_row(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region
) -> None:
    orig, stray = _ops_dohwa(db_session, region)
    links: dict[str, int] = {}
    events: list[ChangeEvent] = []
    docs = _dohwa_docs(add_raw, region)
    for d in docs:
        events.extend(store_raw_document(db_session, d, raw_dir=raw_dir, links=links).change_events)
    db_session.flush()
    db_session.refresh(stray)
    assert stray.merged_into_id == orig.id
    merges = [e for e in events if e.entity == "complex" and e.field == "merged_into"]
    assert len(merges) == 1, [(e.entity, e.field, e.new_text) for e in events]
    ev = merges[0]
    assert (ev.entity_id, ev.complex_id, ev.severity, ev.triggers_rejudge) == (
        stray.id,
        orig.id,
        "critical",
        True,
    )
    assert ev.old_text is None and ev.new_text is not None
    assert "2025940268" in ev.new_text and "2025000397" in ev.new_text
    # 원 단지 행의 단지 단위 값은 그대로(D11-4) — 같은 이름이라 별칭(옛 이름)도 늘지 않는다
    db_session.refresh(orig)
    assert orig.applyhome_id == "2025000397" and orig.former_names == []
    # 임의공급 API 원문(경쟁률·주택형)은 원 단지에(병합된 행에 새로 쓰지 않는다)
    new_comps = db_session.scalars(
        select(Competition.complex_id).where(Competition.type_code != "옛행")
    ).all()
    assert new_comps and set(new_comps) == {orig.id}

    # D23-1: 같은 원문 재정규화(연결 없이 원문마다 따로, 순서 거꾸로) — DB 그대로·change_event 0
    first = _db_state(db_session)
    again: list[ChangeEvent] = []
    for d in reversed(docs):
        again.extend(store_raw_document(db_session, d, raw_dir=raw_dir).change_events)
    db_session.flush()
    assert _db_state(db_session) == first
    assert again == [], [(e.entity, e.field, e.old_text, e.new_text) for e in again]


def test_d29_2_merged_row_redirects_later_documents(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region
) -> None:
    """병합 뒤에는 임의공급 번호의 청약홈 원문이 인용 공고문 없이 와도(다른 수집 실행) 원 단지에 쓰인다."""
    orig, stray = _ops_dohwa(db_session, region)
    docs = _dohwa_docs(add_raw, region)
    store_raw_document(db_session, docs[0], raw_dir=raw_dir, links={})
    db_session.flush()
    db_session.refresh(stray)
    assert stray.merged_into_id == orig.id
    before = db_session.scalars(select(Competition.id).where(Competition.complex_id == stray.id)).all()
    for d in docs[1:]:
        store_raw_document(db_session, d, raw_dir=raw_dir, links={})
    db_session.flush()
    after = db_session.scalars(select(Competition.id).where(Competition.complex_id == stray.id)).all()
    assert after == before  # 병합된 행에 새 행 없음
    assert db_session.scalars(select(Competition.id).where(Competition.complex_id == orig.id)).all()


def test_d29_2_uncited_remnant_row_is_not_merged(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region
) -> None:
    """D29-2 후단: 원 공고 번호가 공고문에 없으면(서해그랑블 5단지 1~4차 모양) 이름이 같아도 붙이지 않는다 — 공고문 없이
    청약홈 원문만 다시 정규화."""
    orig = _cx(db_session, region, "2025000397", "두산위브 더센트럴 도화")
    stray = _cx(db_session, region, "2025940268", "두산위브 더센트럴 도화")
    for d in _dohwa_docs(add_raw, region)[1:]:
        store_raw_document(db_session, d, raw_dir=raw_dir, links={})
    db_session.flush()
    db_session.refresh(stray)
    assert stray.merged_into_id is None
    assert not db_session.scalars(
        select(ChangeEvent).where(ChangeEvent.entity == "complex", ChangeEvent.field == "merged_into")
    ).all()
    assert orig.id != stray.id


def test_d29_2_first_load_merge_is_folded(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region
) -> None:
    """첫 적재(bootstrap) 안의 병합은 다른 값 기록처럼 이벤트 대신 요약 수(D18-7)."""
    orig, stray = _ops_dohwa(db_session, region)
    out = store_raw_document(db_session, _dohwa_docs(add_raw, region)[0], raw_dir=raw_dir, first_load=True)
    db_session.refresh(stray)
    assert stray.merged_into_id == orig.id
    assert out.change_events == [] and out.first_load_folded >= 1


# ====================================================================== 당첨가점 '-'

NO_WINNER = "가점 당첨자 없음(청약홈 '-')"


def _popup_dash() -> list[Any]:
    return parse_applyhome_html(
        (APPLYHOME / "competition_2025000271.html").read_text(encoding="utf-8"),
        dto(source_kind="applyhome_detail", url=COMP_URL.format(n="2025000271")),
    )


def test_dash_score_cells_are_unknown_candidates_with_reason() -> None:
    cands = _popup_dash()
    for area in ("해당지역", "기타지역"):
        key = f"2025000271:본청약:1순위 {area}:74A"
        got = {c.field: c for c in cands if c.entity_key == key and c.field.startswith("winning_score")}
        assert set(got) == {"winning_score_min", "winning_score_max", "winning_score_avg"}, (area, got)
        for c in got.values():
            assert (c.value, c.value_text, c.label, c.reason) == (None, "-", "확인 불가", NO_WINNER), c
            assert f"당첨가점 {area} 최저 - 최고 - 평균 -" in str(c.excerpt)
    # 2순위 행에는 가점 칸이 없다(가점 후보 없음)
    assert not [c for c in cands if ":2순위 " in str(c.entity_key) and c.field.startswith("winning_score")]


def test_dash_scores_stored_as_reasoned_unknown_and_idempotent(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region
) -> None:
    html = (APPLYHOME / "competition_2025000271.html").read_text(encoding="utf-8")
    url = COMP_URL.format(n="2025000271")
    popup = add_raw(html, source_kind="applyhome_detail", url=url, region_id=region.id, ext="html")
    store_raw_document(db_session, popup, raw_dir=raw_dir)
    db_session.flush()
    row = db_session.scalars(
        select(Competition).where(Competition.round == "1순위 해당지역", Competition.type_code == "74A")
    ).one()
    assert (row.winning_score_min, row.winning_score_max, row.winning_score_avg) == (None, None, None)
    fp = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == "competition",
            FieldProvenance.entity_id == row.id,
            FieldProvenance.field == "winning_score_min",
            FieldProvenance.chosen.is_(True),
        )
    ).one()
    assert (fp.label, fp.reason, fp.value_text, fp.raw_document_id) == ("확인 불가", NO_WINNER, "-", popup.id)
    assert fp.checked_at == "2026-10-09"
    again = store_raw_document(db_session, popup, raw_dir=raw_dir).change_events
    assert again == []
    # 나중 팝업이 숫자를 주면(재수집) 그 값이 채택된다 — 첫 값은 이벤트 없음(D29-1)
    first_block = html.index('class="cpResideSenm">해당지역</td>')
    head, tail = html[:first_block], html[first_block:]
    tail = tail.replace('<td rowspan="2">-</td>', '<td rowspan="2">51</td>', 1)
    later = add_raw(
        head + tail, source_kind="applyhome_detail", url=url, region_id=region.id, ext="html",
        fetched_at="2026-10-15T06:00:00+09:00",
    )  # fmt: skip
    events = store_raw_document(db_session, later, raw_dir=raw_dir).change_events
    db_session.refresh(row)
    assert row.winning_score_min is not None and int(row.winning_score_min) == 51
    assert not [e for e in events if e.field.startswith("winning_score")]
