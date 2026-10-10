"""R3d CORE2 — 정규화 쪽 4차 리뷰 재현 (`docs/design/wp/R3_REVIEW4.md`, DECISIONS D12-1, 계약 2026-10-09.9).

| 리뷰 | 테스트 |
| --- | --- |
| C-2 | compare 채택(adopted)이 사람 확인(source_rank 0)을 이기지 못한다 — resolver·정규화 저장 둘 다 |
| M-10 · D12-1 | 사람 확인 **이후에** 관측된 공식 1차 출처의 다른 값 → 그 값 채택 + critical change_event + '사람 확인 재검토' |
| M-8 | 잔여 공고 PDF 가 '최초 주택관리번호'로 원 단지를 가리켜도 이름·세대수·전매·거주·규제를 덮지 않는다(납부 조건만) |
| M-12 | 공고문 할인 줄: 타입 표기는 토큰 전체로, 계약금·발코니·옵션·선납 할인과 다른 타입이 같이 적힌 줄은 분양가 할인 아님 |
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate
from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.models import ChangeEvent, ChecklistItem, Complex, FieldProvenance, Region
from app.normalize.fields import COMPARE_ADOPTED, COMPARE_SIDE, with_tag
from app.normalize.resolver import resolve
from app.normalize.store import store_raw_document

from ._support import AddRaw


def _cand(**kw: Any) -> FieldCandidate:
    base: dict[str, Any] = {
        "entity": "complex", "entity_id": 7, "entity_key": None, "field": "resale_months", "value_text": "12개월",
        "value": 12, "source_rank": 1, "source_kind": "notice_pdf", "primary": True, "label": "확인됨",
        "excerpt": "전매제한 12개월", "raw_document_id": 11, "url": "https://www.applyhome.co.kr/a",
        "checked_at": "2026-09-01", "observed_on": "2026-09-01",
    }  # fmt: skip
    base.update(kw)
    return FieldCandidate(**base)


def _human(value: int, day: str = "2026-10-09") -> FieldCandidate:
    return _cand(value=value, value_text=str(value), source_rank=0, source_kind=None, label="확인됨",
                 reason="사람 확인(phone)", excerpt="전화 확인", raw_document_id=None, url=None,
                 checked_at=f"{day}T10:00:00+09:00", observed_on=day)  # fmt: skip


def test_c2_compare_adopted_does_not_beat_human_check() -> None:
    adopted = _cand(value=12, reason=with_tag(None, COMPARE_ADOPTED, "jl_3"))
    side = _cand(
        value=36,
        source_kind="applyhome_detail",
        raw_document_id=12,
        reason=with_tag(None, COMPARE_SIDE, "jl_3"),
    )
    r = resolve([adopted, side, _human(24)])
    assert [c.value for c in r.chosen] == [24], "compare 채택은 사람 확인(0순위)을 이기지 못한다(C-2·D12-1)"
    assert not r.needs_compare
    chosen_rows = [p for p in r.provenance if p.chosen]
    assert len(chosen_rows) == 1 and (chosen_rows[0].reason or "").startswith("사람 확인")


def test_d12_1_older_official_source_loses_to_human() -> None:
    r = resolve([_cand(value=12, observed_on="2026-10-08"), _human(24, "2026-10-09")])
    assert [c.value for c in r.chosen] == [24]


def test_d12_1_newer_official_source_with_other_value_wins() -> None:
    newer = _cand(value=36, raw_document_id=13, observed_on="2026-10-12", checked_at="2026-10-12")
    r = resolve([_cand(value=12), _human(24, "2026-10-09"), newer])
    assert [c.value for c in r.chosen] == [36], "사람 확인 이후 공식 1차 출처의 다른 값이 채택된다(D12-1)"
    assert "사람 확인 이후" in r.conflicts[0].rule
    # 같은 값이면 사람 확인 그대로(재검토 불필요), 공식이 아닌 출처(언론)는 이기지 못한다
    same = _cand(value=24, raw_document_id=13, observed_on="2026-10-12")
    assert [c.value for c in resolve([_human(24), same]).chosen] == [24]
    news = _cand(
        value=36,
        raw_document_id=14,
        source_rank=3,
        source_kind="news",
        primary=False,
        label="비공식",
        observed_on="2026-10-12",
    )
    assert [c.value for c in resolve([_human(24), news]).chosen] == [24]


class _One:
    def __init__(self, key: str, field: str, value: Any, observed_on: str) -> None:
        self.key, self.field, self.value, self.observed_on = key, field, value, observed_on

    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]:
        return [
            _cand(entity_id=None, entity_key=self.key, field=self.field, value=self.value, value_text=str(self.value),
                  raw_document_id=raw.id, url=raw.url, observed_on=self.observed_on, checked_at=self.observed_on,
                  excerpt=f"{self.field} {self.value}"),
        ]  # fmt: skip


def test_d12_1_store_new_official_notice_after_human_check(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    key = "2026000777"
    raw = add_raw("n1", source_kind="notice_pdf", url="https://www.applyhome.co.kr/n1", region_id=region.id)
    cx = Complex(region_id=region.id, applyhome_id=key, name="테스트 단지", former_names=[], apply_dates=[],
                 contract_dates=[], inclusion_class="미분류")  # fmt: skip
    db_session.add(cx)
    db_session.flush()
    store_raw_document(db_session, raw, parser=_One(key, "resale_months", 12, "2026-09-01"))
    # 사람 확인(0순위 후보) — API 와 같은 경로
    from app.normalize.store import resolve_field_group

    resolve_field_group(
        db_session, "complex", cx.id, "resale_months", [_human(24).model_copy(update={"entity_id": cx.id})]
    )
    db_session.refresh(cx)
    assert cx.resale_months == 24
    # 사람 확인보다 오래된 공고 재수집(같은 원문 재정규화) → 사람 확인 유지
    raw_old = add_raw(
        "n1-again", source_kind="notice_pdf", url="https://www.applyhome.co.kr/n1b", region_id=region.id
    )
    store_raw_document(db_session, raw_old, parser=_One(key, "resale_months", 12, "2026-10-01"))
    db_session.refresh(cx)
    assert cx.resale_months == 24, "사람 확인 이전에 관측된 공고는 사람 확인을 이기지 못한다"
    # 사람 확인 이후의 새 공식 공고(다른 값) → 채택 + critical 이벤트 + 재검토 체크리스트
    raw_new = add_raw(
        "n2", source_kind="notice_pdf", url="https://www.applyhome.co.kr/n2", region_id=region.id
    )
    res = store_raw_document(db_session, raw_new, parser=_One(key, "resale_months", 36, "2026-10-12"))
    db_session.refresh(cx)
    assert cx.resale_months == 36, "사람 확인 이후 새 공식 공고의 다른 값 채택(D12-1)"
    ev = [e for e in res.change_events if e.field == "resale_months"]
    assert ev and ev[0].severity == "critical" and ev[0].triggers_rejudge, "critical change_event"
    items = list(db_session.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == cx.id)))
    review = [i for i in items if i.title.startswith("사람 확인 재검토")]
    assert len(review) == 1 and review[0].status == "open" and review[0].kind == "사실 재확인", [
        i.title for i in items
    ]
    # 같은 원문 다시 정규화 → 이벤트·항목 중복 없음
    raw_new2 = add_raw(
        "n2-again", source_kind="notice_pdf", url="https://www.applyhome.co.kr/n2b", region_id=region.id
    )
    store_raw_document(db_session, raw_new2, parser=_One(key, "resale_months", 36, "2026-10-12"))
    assert len([i for i in db_session.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == cx.id))
                if i.title.startswith("사람 확인 재검토")]) == 1  # fmt: skip
    crit = list(db_session.scalars(select(ChangeEvent).where(ChangeEvent.complex_id == cx.id, ChangeEvent.field == "resale_months",
                                                            ChangeEvent.severity == "critical")))  # fmt: skip
    assert len(crit) == 1
    human_row = db_session.scalars(select(FieldProvenance).where(FieldProvenance.entity_id == cx.id,
                                                                 FieldProvenance.reason.like("사람 확인%"))).one()  # fmt: skip
    assert human_row.chosen is False, "사람 확인 행은 남되(병기) 채택되지 않는다"


class _Batch:
    """후보 묶음 그대로(공고문 파서가 내는 모양 — 단지 키 = 원 단지 번호, 납부 조건 키 = '<원 번호>:<이 공고 번호>')."""

    def __init__(self, rows: list[tuple[str, str, str, Any]], observed_on: str) -> None:
        self.rows, self.observed_on = rows, observed_on

    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]:
        return [
            _cand(entity=e, entity_id=None, entity_key=k, field=f, value=v, value_text=str(v), raw_document_id=raw.id,
                  url=raw.url, observed_on=self.observed_on, checked_at=self.observed_on, excerpt=f"{f} {v}")
            for e, k, f, v in self.rows
        ]  # fmt: skip


def test_m8_remainder_pdf_citing_original_number_does_not_overwrite_unit_fields(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    from app.models import ComplexType, PaymentTerms

    key = "2024000111"
    orig = [
        ("complex", key, "name", "검단 원 단지"), ("complex", key, "units_total", 3100),
        ("complex", key, "resale_months", 12), ("complex", key, "residency_months", 0),
        ("complex", key, "regulated", "비규제"), ("complex_type", f"{key}:84A", "units", 900),
        ("payment_terms", f"{key}:{key}", "effective_from", "2024-05-01"),
        ("payment_terms", f"{key}:{key}", "notice_kind", "본청약"),
    ]  # fmt: skip
    raw = add_raw(
        "orig", source_kind="notice_pdf", url="https://www.applyhome.co.kr/o.pdf", region_id=region.id
    )
    store_raw_document(db_session, raw, parser=_Batch(orig, "2024-05-01"))
    rem_no = "2026910999"
    rem = [
        ("complex", key, "name", "검단 원 단지(임의공급 4차)"), ("complex", key, "units_total", 1),
        ("complex", key, "resale_months", 0), ("complex", key, "residency_months", 36),
        ("complex", key, "regulated", "규제"), ("complex_type", f"{key}:84A", "units", 1),
        ("payment_terms", f"{key}:{rem_no}", "effective_from", "2026-09-10"),
        ("payment_terms", f"{key}:{rem_no}", "notice_kind", "임의"),
    ]  # fmt: skip
    raw2 = add_raw(
        "rem", source_kind="notice_pdf", url="https://www.applyhome.co.kr/r.pdf", region_id=region.id
    )
    res = store_raw_document(db_session, raw2, parser=_Batch(rem, "2026-09-10"))
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == key)).one()
    assert (cx.name, cx.units_total, cx.resale_months, cx.residency_months, cx.regulated) == (
        "검단 원 단지",
        3100,
        12,
        0,
        "비규제",
    ), "잔여 공고 PDF 의 단지 단위 값이 원 단지를 덮으면 안 된다(M-8·D11-4)"
    t = db_session.scalars(select(ComplexType).where(ComplexType.complex_id == cx.id)).one()
    assert t.units == 900
    kinds = sorted(
        p.notice_kind or ""
        for p in db_session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == cx.id))
    )
    assert kinds == ["본청약", "임의"], "공고별 기록(납부 조건)은 남는다"
    assert cx.id in res.complex_ids and {c.field for c in res.skipped if c.entity == "complex"} >= {
        "name",
        "units_total",
    }


def test_m12_discount_line_requires_whole_type_token_and_price_discount() -> None:
    from app.normalize.notice_parser import TypeSpec, _discount_line

    t84 = TypeSpec(short="84A", long="084.9582A", area_text="84.9582", units=10, span=(0, 1))
    ok = "84A 분양가 할인 10,000,000원\n"
    assert _discount_line(ok, t84) == (
        10_000_000,
        (len("84A 분양가 할인 "), len("84A 분양가 할인 10,000,000")),
    )
    for bad in (
        "184A 분양가 할인 10,000,000원",  # 다른 타입(부분 문자열)
        "84AB 분양가 할인 10,000,000원",
        "84A 계약금 할인 10,000,000원",  # 계약금 할인
        "84A 발코니 확장 할인 3,000,000원",  # 발코니 할인
        "84A 옵션 할인 2,000,000원",
        "59A·84A 분양가 할인 10,000,000원",  # 어느 타입 금액인지 모호
    ):
        assert _discount_line(bad + "\n", t84) is None, bad
    assert _discount_line("할인금액(84㎡): 12,500,000원\n", t84) is not None
