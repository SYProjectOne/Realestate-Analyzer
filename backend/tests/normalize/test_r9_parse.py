"""R9-PARSE(D28-5, ui-benchmark 20-gap §2-2 Q2·Q3·Q4) — 실제 녹화 원문 발췌로 고정한다.

픽스처 ``fixtures/r9_parse/``(README 참고): 운영 수집(2026-10-13·14)의 공개 분양 정보 원문 발췌 —
- 시티오씨엘 8단지 본청약 공고문(2025000560)·무순위 공고문(2025910275): 납부 표 머리가 '계약금1차 계약금2차 (35%)'·'1회 … 6회'·
  '10% … 10%' 로 갈라진 표(Q2: 중도금 '2회차 35%' 한 줄·잔금 '해석 실패'·필수 옵션 칸 고지문).
- 두산위브 더센트럴 도화 임의공급 공고문(2025940268): 원 공고 인용 '최초 입주자모집공고일 주택관리번호 2025-000397'(조사 없음)
  — 못 읽어 같은 사업의 단지 행이 둘(39·99) 생기고 G7 캘린더에 중도금 일정이 두 번 나왔다.
- 청약홈 공식 API 상세·경쟁률(2025000560)·임의공급 상세·주택형·경쟁률(2025940268), 웹 경쟁률 팝업(2025000560, 당첨가점).
"""

# ruff: noqa: E501  (한국어 docstring·발췌)

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.applyhome import api as ah_api
from app.core.contracts_gen import FieldCandidate
from app.models import ChecklistItem, Competition, Complex, FieldProvenance, PaymentTerms, Region
from app.normalize.applyhome_api_parser import parse_applyhome_api_json
from app.normalize.applyhome_parser import parse_applyhome_html
from app.normalize.checklist import absorbed_remnant_rows, sync_checklist
from app.normalize.notice_parser import (
    _INSTALL_RE,
    BALANCE_DERIVED_REASON,
    notice_numbers,
    parse_notice_text,
)
from app.normalize.store import store_raw_document

from ._support import COMP_URL, FIX, NOTICE_BASE, AddRaw, dto

R9 = FIX / "r9_parse"
APPLYHOME_API = FIX / "applyhome_api"


def _notice_url(no: str) -> str:
    return f"{NOTICE_BASE}houseManageNo={no}&pblancNo={no}&atchmnflSeqNo=1&atchmnflSn=1"


def _api_url(kind: ah_api.ApiKind, part: str, no: str) -> str:
    ep = ah_api.ENDPOINTS[kind]
    path = {"detail": ep.detail, "model": ep.model, "competition": ep.competition}[part]
    return ah_api.doc_url(path, ah_api.item_params(no, no))


def _text(name: str) -> str:
    return (R9 / name).read_text(encoding="utf-8")


def _notice(name: str, no: str) -> list[FieldCandidate]:
    return parse_notice_text(_text(name), dto(source_kind="notice_pdf", url=_notice_url(no)))


def _vals(cands: list[FieldCandidate], entity: str, key: str) -> dict[str, FieldCandidate]:
    return {c.field: c for c in cands if c.entity == entity and c.entity_key == key}


# ---------------------------------------------------------------- Q2 납부 표


EXPECTED_SCHEDULE = [
    {"seq": 1, "due_date": "2026-05-07", "pct": 10.0},
    {"seq": 2, "due_date": "2026-12-07", "pct": 10.0},
    {"seq": 3, "due_date": "2027-07-07", "pct": 10.0},
    {"seq": 4, "due_date": "2028-03-07", "pct": 10.0},
    {"seq": 5, "due_date": "2028-08-07", "pct": 10.0},
    {"seq": 6, "due_date": "2028-12-07", "pct": 10.0},
]


def test_q2_interim_schedule_has_six_installments() -> None:
    """중도금 1~6회(각 10%)·날짜 6개 — 예전에는 '계약금2차 (35%)'를 중도금 '2회 35%'로 읽어 한 줄(2028-12-07)만 냈다."""
    for name, no, key in (
        ("notice_2025000560_cityociel8.txt", "2025000560", "2025000560:2025000560"),
        ("notice_2025910275_cityociel8_muso.txt", "2025910275", "2025000560:2025910275"),
    ):
        p = _vals(_notice(name, no), "payment_terms", key)
        sched = p["interim_schedule"]
        assert sched.label == "확인됨" and not sched.needs_extract, name
        assert json.loads(str(sched.value)) == EXPECTED_SCHEDULE, name
        assert (p["down_payment_pct"].value, p["interim_pct"].value) == (5.0, 60.0)
        assert p["down_payment_first_won"].value == 10_000_000


def test_q2_down_payment_second_column_is_not_an_installment() -> None:
    """'계약금1차 계약금2차 (35%)'의 '2차 (35%)'는 중도금 회차가 아니다(계약금 분납 열 머리 + 잔금 비율)."""
    assert _INSTALL_RE.search("계약금1차 계약금2차 (35%)") is None
    assert _INSTALL_RE.search("계약금1차 계약금 2차 (35%)") is None
    m = _INSTALL_RE.search("1차(10%) 2차(10%)")
    assert m is not None and (m.group(1), m.group(2)) == ("1", "10")


def test_q2_balance_pct_is_derived_and_labelled_estimate() -> None:
    """잔금 비율: 표 머리에서 '잔금'과 '(35%)'가 다른 줄 — 100 − 계약금 − 중도금 = 35, 라벨 '추정'(산술) — '해석 실패'가 아니다."""
    p = _vals(
        _notice("notice_2025000560_cityociel8.txt", "2025000560"), "payment_terms", "2025000560:2025000560"
    )
    bal = p["balance_pct"]
    # needs_extract 그대로: 판정기 extract 요청은 예전('확인 불가' 후보)과 같은 발췌(표 머리) — 같은 요청·같은 캐시 키
    assert (bal.value, bal.label, bal.reason, bal.needs_extract) == (
        35.0,
        "추정",
        BALANCE_DERIVED_REASON,
        True,
    )
    assert bal.excerpt and "계약금(5%)" in bal.excerpt and "(35%)" in bal.excerpt  # 근거 발췌 = 납부 표 머리


def test_q2_derived_balance_keeps_extract_request_and_yields_to_judge(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region
) -> None:
    """산술 잔금은 판정기 추출이 나오면 물러난다(OCR 판독과 같은 규칙): extract 요청은 예전과 같은 필드·발췌로 남고, 판정기가
    auto 로 읽은 값(감사 통과)이 '확인됨'으로 채택된다. review 면 산술 '추정' 값이 그대로 남는다."""
    from app.normalize.extract_request import build_extract_requests
    from app.normalize.judged import AuditMark, ExtractedValue, apply_extracted

    d = add_raw(
        _text("notice_2025000560_cityociel8.txt"),
        source_kind="notice_pdf",
        url=_notice_url("2025000560"),
        region_id=region.id,
    )
    cands = store_raw_document(db_session, d, raw_dir=raw_dir).candidates
    db_session.flush()
    reqs = [r for r in build_extract_requests(cands) if r.entity == "payment_terms"]
    assert [r.fields for r in reqs] == [["balance_pct"]] and "(35%)" in reqs[0].text
    pt = db_session.scalars(select(PaymentTerms)).one()
    assert pt.balance_pct == Decimal("35")

    review = apply_extracted(
        db_session, reqs[0], [ExtractedValue("balance_pct", "35%", "review")], judgment_seq=1
    )
    assert not review.applied and pt.balance_pct == Decimal("35")
    out = apply_extracted(
        db_session,
        reqs[0],
        [ExtractedValue("balance_pct", "35%", "auto")],
        judgment_seq=2,
        audit={"balance_pct": AuditMark(flagged=False, p_wrong=0.05)},
        audit_seq=3,
    )
    assert set(out.applied) == {"balance_pct"}
    chosen = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.field == "balance_pct", FieldProvenance.chosen.is_(True)
        )
    ).one()
    assert chosen.label == "확인됨" and chosen.reason and chosen.reason.startswith("판정기 추출")
    # 같은 원문 재정규화 — 판정기 추출 행이 그대로 채택(D22-1), 이벤트 0
    again = store_raw_document(db_session, d, raw_dir=raw_dir).change_events
    db_session.flush()
    assert again == []
    kept = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.field == "balance_pct", FieldProvenance.chosen.is_(True)
        )
    ).one()
    assert kept.id == chosen.id and kept.label == "확인됨"


def test_q2_balance_pct_read_directly_stays_confirmed() -> None:
    """'잔금(35%)'이 바로 붙은 표는 그대로 '확인됨'(산술 대체 아님) — 도화 임의공급 공고문."""
    p = _vals(
        _notice("notice_2025940268_dohwa_imui.txt", "2025940268"), "payment_terms", "2025000397:2025940268"
    )
    assert (p["balance_pct"].value, p["balance_pct"].label, p["balance_pct"].reason) == (35.0, "확인됨", None)


def test_q2_options_text_is_not_the_boilerplate() -> None:
    """필수 옵션: '추가 선택품목 비용 미포함' 고지문은 0원의 근거(발췌)로만 남고 옵션 설명(options_text)이 아니다."""
    cands = _notice("notice_2025000560_cityociel8.txt", "2025000560")
    types = sorted({str(c.entity_key) for c in cands if c.entity == "complex_type"})
    assert types == [f"2025000560:{t}" for t in ("101", "110", "136P", "59", "75", "84A", "84B", "84C")]
    for key in types:
        t = _vals(cands, "complex_type", key)
        assert t["options_required_won"].value == 0 and t["options_required_won"].label == "확인됨"
        assert "선택품목" in str(t["options_required_won"].excerpt)  # 근거 발췌는 그대로
        assert t["options_text"].value is None, key


def test_q2_renormalize_clears_stored_boilerplate_and_fills_schedule(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region, monkeypatch: Any
) -> None:
    """운영 DB 모양: 옛 파서로 저장된 단지(options_text = 고지문, 중도금 1행, 잔금 없음) → 같은 원문을 고친 파서로 다시 정규화하면
    options_text 는 비고(옛 출처 행이 값을 되살리지 않는다), 중도금 6회·잔금 '추정' 35 가 저장된다. 다시 한 번 돌리면 그대로(D23-1)."""
    from app.normalize import notice_parser as np_mod

    d = add_raw(
        _text("notice_2025000560_cityociel8.txt"),
        source_kind="notice_pdf",
        url=_notice_url("2025000560"),
        region_id=region.id,
    )
    real = np_mod.parse_notice_text

    def old_parser(text: str, raw: Any) -> list[FieldCandidate]:  # 옛 저장 상태를 만든다(옛 파서가 낸 값)
        out = []
        for c in real(text, raw):
            if c.field == "options_text":
                c = c.model_copy(
                    update={"value": "상기 공급금액에는 … 미포함된 가격이며", "value_text": "고지문"}
                )
            if c.field == "interim_schedule":
                c = c.model_copy(update={"value": '[{"due_date":"2028-12-07","pct":35.0,"seq":2}]'})
            if c.field == "balance_pct":
                c = c.model_copy(
                    update={
                        "value": None,
                        "label": "확인 불가",
                        "reason": "잔금 비율 표기 해석 실패",
                        "needs_extract": True,
                    }
                )
            out.append(c)
        return out

    monkeypatch.setattr(np_mod, "parse_notice_text", old_parser)
    store_raw_document(db_session, d, raw_dir=raw_dir)
    db_session.flush()
    monkeypatch.setattr(np_mod, "parse_notice_text", real)
    store_raw_document(db_session, d, raw_dir=raw_dir)
    db_session.flush()
    from app.models import ComplexType

    texts = {t.type_code: t.options_text for t in db_session.scalars(select(ComplexType))}
    assert texts and set(texts.values()) == {None}, texts
    pt = db_session.scalars(select(PaymentTerms)).one()
    assert pt.interim_schedule == EXPECTED_SCHEDULE and pt.balance_pct == Decimal("35")
    bal = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.field == "balance_pct", FieldProvenance.chosen.is_(True)
        )
    ).one()
    assert (bal.label, bal.reason) == ("추정", BALANCE_DERIVED_REASON)
    again = store_raw_document(db_session, d, raw_dir=raw_dir).change_events
    assert again == []


def test_q2_floor_sample_is_lowest_priced_row_by_definition() -> None:
    """'대표 층' = 공고 표에서 공급금액이 가장 낮은 층 행(RA §6-1 구매가 범위의 아래 끝, 계약 complex_type.floor_sample_*) —
    파싱 결함이 아니라 정의다(84C 는 1층 579,000,000). 1층 행이 없는 타입은 그 타입의 최저가 층(75 → 2층, 136P → 45-46층)."""
    cands = _notice("notice_2025000560_cityociel8.txt", "2025000560")
    got = {
        str(c.entity_key).split(":")[1]: c.value
        for c in cands
        if c.entity == "complex_type" and c.field == "floor_sample_text"
    }
    assert got == {
        "59": "1층",
        "75": "2층",
        "84A": "1층",
        "84B": "1층",
        "84C": "1층",
        "101": "1층",
        "110": "1층",
        "136P": "45-46층",
    }
    price = {
        str(c.entity_key).split(":")[1]: c.value
        for c in cands
        if c.entity == "complex_type" and c.field == "floor_sample_price_won"
    }
    assert price["84C"] == 579_000_000


# ---------------------------------------------------------------- G7 캘린더 중복(원 공고 인용 변형)


def test_dohwa_citation_without_particle_is_read() -> None:
    raw = dto(source_kind="notice_pdf", url=_notice_url("2025940268"))
    text = _text("notice_2025940268_dohwa_imui.txt")
    assert "최초 입주자모집공고일 주택관리번호 2025-000397" in text
    p = parse_notice_text(text, raw)
    keys = {str(c.entity_key) for c in p if c.entity == "payment_terms"}
    assert keys == {"2025000397:2025940268"}


def test_dohwa_notice_numbers(raw_dir: Path, add_raw: AddRaw) -> None:
    d = add_raw(
        _text("notice_2025940268_dohwa_imui.txt"), source_kind="notice_pdf", url=_notice_url("2025940268")
    )
    assert notice_numbers(d, raw_dir=raw_dir) == ("2025940268", "2025000397")


def _dohwa_docs(add_raw: AddRaw, region: Region) -> list[Any]:
    """도화: 임의공급 공고문 → 임의공급 API 상세·주택형·경쟁률(수집 단계 순서 — 인용 공고문이 먼저, D18-4)."""
    out = [
        add_raw(
            _text("notice_2025940268_dohwa_imui.txt"),
            source_kind="notice_pdf",
            url=_notice_url("2025940268"),
            region_id=region.id,
        )
    ]
    for part, name in (
        ("detail", "api_OPTDetail_2025940268.json"),
        ("model", "api_OPTMdl_2025940268.json"),
        ("competition", "api_OPTCmpet_2025940268.json"),
    ):
        out.append(
            add_raw(
                _text(name),
                source_kind="applyhome_detail",
                url=_api_url("opt", part, "2025940268"),
                region_id=region.id,
                ext="json",
            )
        )
    return out


def test_dohwa_fresh_store_makes_no_second_complex_row(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region
) -> None:
    """새로 적재: 임의공급 번호(2025940268)로 단지 행이 생기지 않고 원 단지(2025000397) 하나에 납부 조건이 붙는다."""
    links: dict[str, int] = {}
    for d in _dohwa_docs(add_raw, region):
        store_raw_document(db_session, d, raw_dir=raw_dir, links=links)
    db_session.flush()
    keys = sorted(k for k in db_session.scalars(select(Complex.applyhome_id)) if k)
    assert keys == ["2025000397"], keys
    terms = db_session.scalars(select(PaymentTerms)).all()
    assert [(t.notice_no, t.notice_kind) for t in terms] == [("2025940268", "임의")]


def test_dohwa_existing_stray_row_is_absorbed_and_calendar_not_duplicated(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region
) -> None:
    """운영 DB 모양: 예전 적재가 남긴 원 단지 행(2025000397, 본청약 납부 조건)과 임의공급 번호 행(2025940268, 같은 중도금
    일정)이 둘 다 있다. 고친 파서로 같은 원문을 다시 정규화하면 ① 공고문 납부 조건이 원 단지에 붙고 ② 임의공급 API 원문도 원 단지에
    쓰이며 ③ 체크리스트(G7 캘린더)에는 같은 일정이 한 번만 열린다(두 번째 행의 열린 자동 항목은 auto 로 닫힘)."""
    sched = [
        {"seq": n, "due_date": d, "pct": 10.0}
        for n, d in enumerate(
            ["2025-12-19", "2026-08-10", "2027-02-10", "2027-08-10", "2027-11-10", "2028-03-10"], start=1
        )
    ]
    orig = Complex(
        region_id=region.id,
        applyhome_id="2025000397",
        name="두산위브 더센트럴 도화",
        former_names=[],
        apply_dates=[],
        contract_dates=[],
        inclusion_class="private_sale_apt",
        inclusion_decision="auto",
    )
    stray = Complex(
        region_id=region.id,
        applyhome_id="2025940268",
        name="두산위브 더센트럴 도화",
        former_names=[],
        apply_dates=[],
        contract_dates=[],
        inclusion_class="private_sale_apt",
        inclusion_decision="auto",
    )
    db_session.add_all([orig, stray])
    db_session.flush()
    db_session.add_all(
        [
            PaymentTerms(
                complex_id=orig.id,
                notice_no="2025000397",
                notice_kind="본청약",
                effective_from="2025-08-29",
                interim_schedule=sched,
                price_by_type={},
            ),
            PaymentTerms(
                complex_id=stray.id,
                notice_no="2025940268",
                notice_kind="임의",
                effective_from="2025-11-05",
                interim_schedule=sched,
                price_by_type={},
            ),
        ]
    )
    db_session.flush()
    sync_checklist(db_session, region.id, asof_date="2026-10-14")
    before = [
        (i.complex_id, i.title, i.due_date)
        for i in db_session.scalars(
            select(ChecklistItem).where(ChecklistItem.status == "open", ChecklistItem.kind == "중도금")
        )
    ]
    assert sorted(t for _, t, _ in before).count("중도금 3회차 납부일") == 2  # 재현: 같은 일정 두 번

    links: dict[str, int] = {}
    for d in _dohwa_docs(add_raw, region):
        store_raw_document(db_session, d, raw_dir=raw_dir, links=links)
    db_session.flush()
    assert {
        t.notice_no
        for t in db_session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == orig.id))
    } == {"2025000397", "2025940268"}
    comp_owners = {c.complex_id for c in db_session.scalars(select(Competition))}
    assert comp_owners == {orig.id}  # 임의공급 경쟁률도 원 단지에
    assert absorbed_remnant_rows(db_session, region.id) == {stray.id}

    sync_checklist(db_session, region.id, asof_date="2026-10-14")
    opens = [
        (i.complex_id, i.title, i.due_date)
        for i in db_session.scalars(select(ChecklistItem).where(ChecklistItem.status == "open"))
    ]
    dated = [(t, d) for _, t, d in opens if d is not None]
    assert len(dated) == len(set(dated)), f"같은 일정이 두 번: {sorted(dated)}"
    assert {cid for cid, _, _ in opens} == {orig.id}
    closed = db_session.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == stray.id)).all()
    assert closed and all(i.status == "na" and i.closed_by == "auto" for i in closed)


# ---------------------------------------------------------------- Q3 청약 일정


def test_q3_api_apply_dates_by_rank_and_area_with_start_end() -> None:
    cands = parse_applyhome_api_json(
        _text("api_APTDetail_2025000560.json"),
        dto(source_kind="applyhome_detail", url=_api_url("apt", "detail", "2025000560")),
    )
    c = _vals(cands, "complex", "2025000560")
    assert json.loads(str(c["apply_dates"].value)) == [
        {"kind": "특별공급", "start": "2025-12-01", "end": "2025-12-01"},
        {"kind": "1순위 해당지역", "start": "2025-12-02", "end": "2025-12-02"},
        {"kind": "1순위 기타지역", "start": "2025-12-02", "end": "2025-12-02"},
        {"kind": "2순위 해당지역", "start": "2025-12-03", "end": "2025-12-03"},
        {"kind": "2순위 기타지역", "start": "2025-12-03", "end": "2025-12-03"},
    ]
    assert (c["winner_date"].value, json.loads(str(c["contract_dates"].value))) == (
        "2025-12-09",
        [{"from": "2025-12-21", "to": "2025-12-24"}],
    )
    assert c["apply_dates"].label == "확인됨" and "SPSPLY_RCEPT_BGNDE" in str(c["apply_dates"].excerpt)


def test_q3_remnant_apply_window_has_start_and_end() -> None:
    cands = parse_applyhome_api_json(
        (APPLYHOME_API / "getOPTLttotPblancDetail_2026940173.json").read_text(encoding="utf-8"),
        dto(source_kind="applyhome_detail", url=_api_url("opt", "detail", "2026940173")),
    )
    c = _vals(cands, "complex", "2026940173")
    assert json.loads(str(c["apply_dates"].value)) == [
        {"kind": "청약접수", "start": "2026-08-19", "end": "2026-08-24"}
    ]


def test_q3_web_detail_and_api_give_the_same_apply_dates() -> None:
    """같은 출처 종류(applyhome_detail)의 두 원문이 다른 값을 내면 상충 묶음이 생긴다 — 웹 상세와 API 가 같은 JSON 이어야 한다."""
    manifest = {
        m["file"]: m["url"] for m in json.loads((APPLYHOME_API / "manifest.json").read_text(encoding="utf-8"))
    }
    for api_name, web_name in (
        ("getAPTLttotPblancDetail_2026000367.json", "web_detail_2026000367.html"),
        ("getRemndrLttotPblancDetail_2026910242.json", "web_detail_2026910242.html"),
        ("getOPTLttotPblancDetail_2026940173.json", "web_detail_2026940173.html"),
    ):
        a = [
            c.value
            for c in parse_applyhome_api_json(
                (APPLYHOME_API / api_name).read_text(encoding="utf-8"),
                dto(source_kind="applyhome_detail", url=manifest[api_name]),
            )
            if c.field == "apply_dates"
        ]
        w = [
            c.value
            for c in parse_applyhome_html(
                (APPLYHOME_API / web_name).read_text(encoding="utf-8"),
                dto(source_kind="applyhome_detail", url=manifest[web_name]),
            )
            if c.field == "apply_dates"
        ]
        assert a and a == w, (api_name, a, w)


# ---------------------------------------------------------------- Q4 당첨가점


def _popup() -> list[FieldCandidate]:
    return parse_applyhome_html(
        _text("web_competition_2025000560.html"),
        dto(source_kind="applyhome_detail", url=COMP_URL.format(n="2025000560")),
    )


def test_q4_popup_winning_scores_per_type_and_area() -> None:
    cands = _popup()
    s59 = _vals(cands, "competition", "2025000560:본청약:1순위 해당지역:59.9801")
    assert (
        s59["winning_score_min"].value,
        s59["winning_score_max"].value,
        s59["winning_score_avg"].value,
    ) == (
        42.0,
        63.0,
        48.5,
    )
    assert s59["winning_score_avg"].label == "확인됨" and "당첨가점 해당지역" in str(
        s59["winning_score_avg"].excerpt
    )
    s75 = _vals(cands, "competition", "2025000560:본청약:1순위 해당지역:75.9096")
    assert (
        s75["winning_score_min"].value,
        s75["winning_score_max"].value,
        s75["winning_score_avg"].value,
    ) == (
        30.0,
        55.0,
        37.54,
    )
    other = _vals(cands, "competition", "2025000560:본청약:1순위 기타지역:59.9801")
    assert (other["winning_score_min"].value, other["winning_score_max"].value) == (
        0.0,
        0.0,
    )  # 원문 그대로(가점 당첨자 없음 표기)
    # 미달 주택형('-')은 가점 후보가 없다(값 없음)
    a84 = _vals(cands, "competition", "2025000560:본청약:1순위 해당지역:84A")
    assert not {"winning_score_min", "winning_score_max", "winning_score_avg"} & set(a84)
    assert a84["ratio_or_shortfall_text"].value == "(△307)"


def test_q4_popup_and_api_agree_on_ratios() -> None:
    """팝업(가점 포함)과 공식 API 경쟁률이 같은 행·같은 값(공급·접수·경쟁률) — 상충 없음."""
    api = {
        (c.entity_key, c.field): c.value
        for c in parse_applyhome_api_json(
            _text("api_APTCmpet_2025000560.json"),
            dto(source_kind="applyhome_detail", url=_api_url("apt", "competition", "2025000560")),
        )
        if c.entity == "competition"
    }
    web = {
        (c.entity_key, c.field): c.value
        for c in _popup()
        if c.entity == "competition" and not c.field.startswith("winning_score")
    }
    assert api and api == web


def test_q4_scores_stored_with_provenance_and_idempotent(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region
) -> None:
    docs = [
        add_raw(
            _text("api_APTDetail_2025000560.json"),
            source_kind="applyhome_detail",
            url=_api_url("apt", "detail", "2025000560"),
            region_id=region.id,
            ext="json",
        ),
        add_raw(
            _text("api_APTCmpet_2025000560.json"),
            source_kind="applyhome_detail",
            url=_api_url("apt", "competition", "2025000560"),
            region_id=region.id,
            ext="json",
        ),
        add_raw(
            _text("web_competition_2025000560.html"),
            source_kind="applyhome_detail",
            url=COMP_URL.format(n="2025000560"),
            region_id=region.id,
            ext="html",
        ),
    ]
    for d in docs:
        store_raw_document(db_session, d, raw_dir=raw_dir)
    db_session.flush()
    row = db_session.scalars(
        select(Competition).where(Competition.round == "1순위 해당지역", Competition.type_code == "59.9801")
    ).one()
    assert (row.winning_score_min, row.winning_score_max, row.winning_score_avg) == (
        Decimal("42"),
        Decimal("63"),
        Decimal("48.5"),
    )
    prov = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == "competition",
            FieldProvenance.entity_id == row.id,
            FieldProvenance.field == "winning_score_avg",
        )
    ).all()
    assert [(p.label, p.chosen, p.raw_document_id) for p in prov] == [("확인됨", True, docs[2].id)]
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2025000560")).one()
    assert cx.apply_dates[0] == {"kind": "특별공급", "start": "2025-12-01", "end": "2025-12-01"}

    def snap() -> list[tuple[Any, ...]]:
        comps = [
            (
                c.id,
                c.round,
                c.type_code,
                c.supply,
                c.applied,
                c.ratio_or_shortfall_text,
                c.winning_score_min,
                c.winning_score_max,
                c.winning_score_avg,
            )
            for c in db_session.scalars(select(Competition).order_by(Competition.id))
        ]
        fps = [
            (p.id, p.entity, p.entity_id, p.field, p.value_text, p.label, p.chosen, p.reason)
            for p in db_session.scalars(select(FieldProvenance).order_by(FieldProvenance.id))
        ]
        return [*comps, *fps, (tuple(json.dumps(x, sort_keys=True) for x in cx.apply_dates),)]

    first = snap()
    events = []
    for d in reversed(docs):  # D23-1: 같은 원문 재정규화(순서를 바꿔도) — DB 그대로·변경 이벤트 0
        events.extend(store_raw_document(db_session, d, raw_dir=raw_dir).change_events)
    db_session.flush()
    assert snap() == first and events == []


def test_q4_first_scores_are_quiet_later_change_is_info_event(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region
) -> None:
    """운영 DB 모양: 경쟁률 행은 API 로 이미 있고 가점은 없다. 팝업으로 가점이 처음 들어오면 이벤트를 남기지 않고(지난 결과의 첫
    수집 — 배포 뒤 첫 수집이 행마다 이벤트를 쏟지 않게), 그 뒤 값이 바뀌면 info 이벤트 1건."""
    for name, part in (
        ("api_APTDetail_2025000560.json", "detail"),
        ("api_APTCmpet_2025000560.json", "competition"),
    ):
        d = add_raw(
            _text(name),
            source_kind="applyhome_detail",
            url=_api_url("apt", part, "2025000560"),
            region_id=region.id,
            ext="json",
        )
        store_raw_document(db_session, d, raw_dir=raw_dir)
    db_session.flush()
    html = _text("web_competition_2025000560.html")
    url = COMP_URL.format(n="2025000560")
    popup = add_raw(html, source_kind="applyhome_detail", url=url, region_id=region.id, ext="html")
    events = store_raw_document(db_session, popup, raw_dir=raw_dir).change_events
    assert not [e for e in events if e.field.startswith("winning_score")]
    changed = html.replace('<td rowspan="2">48.5</td>', '<td rowspan="2">49.5</td>', 1)
    assert changed != html
    later = add_raw(
        changed,
        source_kind="applyhome_detail",
        url=url,
        region_id=region.id,
        ext="html",
        fetched_at="2026-10-15T06:00:00+09:00",
    )
    events = store_raw_document(db_session, later, raw_dir=raw_dir).change_events
    got = [
        (e.field, e.old_text, e.new_text, e.severity) for e in events if e.field.startswith("winning_score")
    ]
    assert got == [("winning_score_avg", "48.5", "49.5", "info")]


def test_q3_apply_dates_shape_feeds_api_intake_deadline() -> None:
    """저장 모양 ``[{kind, start, end}]`` 를 계약 .20 소비자가 그대로 읽는다: 접수 마감 임박 키(``sort=intake``)는 항목의 **끝**날짜
    (잔여·임의 '청약접수' 기간이면 마감일 — 예전 모양에서는 시작일뿐이었다)."""
    from app.api.routers.snapshots import intake_deadline

    apt = parse_applyhome_api_json(
        _text("api_APTDetail_2025000560.json"),
        dto(source_kind="applyhome_detail", url=_api_url("apt", "detail", "2025000560")),
    )
    items = json.loads(str(_vals(apt, "complex", "2025000560")["apply_dates"].value))
    assert intake_deadline(items, "2025-11-30") == "2025-12-01"
    assert intake_deadline(items, "2025-12-03") == "2025-12-03"
    assert intake_deadline(items, "2025-12-04") is None
    opt = parse_applyhome_api_json(
        (APPLYHOME_API / "getOPTLttotPblancDetail_2026940173.json").read_text(encoding="utf-8"),
        dto(source_kind="applyhome_detail", url=_api_url("opt", "detail", "2026940173")),
    )
    window = json.loads(str(_vals(opt, "complex", "2026940173")["apply_dates"].value))
    assert intake_deadline(window, "2026-08-20") == "2026-08-24"
