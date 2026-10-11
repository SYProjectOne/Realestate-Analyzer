"""R3e CORE3 — 5차 리뷰(`docs/design/wp/R3_REVIEW5.md`) 정규화·수집 쪽 Major (계약 2026-10-09.10).

| 리뷰 | 테스트 |
| --- | --- |
| M8 load_supply 가 빠진 단지 행을 남김 | ``test_m8_load_supply_deletes_rows_of_complexes_no_longer_in_input`` |
| M9 할인 판정 허용 목록 | ``test_m9_discount_allowlist`` (리뷰 재현 문구 전부) |
| M10 원 번호 인용 잔여 공고의 입주 지연 소실 | ``test_m10_cited_remainder_notice_move_in_delay_is_kept`` |
"""

# ruff: noqa: E501

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, Complex, Region

from ._support import AddRaw

# ====================================================================== M8


def test_m8_load_supply_deletes_rows_of_complexes_no_longer_in_input(db_session: Session) -> None:
    """입주월이 강등·삭제돼 입력에서 빠진 단지의 옛 추정 행·출처 행은 지운다(예전: upsert 만 → 옛 입주물량이 남음)."""
    from app.collectors.stats.supply import SupplyInput, estimate_supply, load_supply
    from app.models import FieldProvenance, Supply

    region = Region(name="r", query_text="q", selections=[], sido_codes=[], sigungu_codes=[], legal_dong_codes=[],
                    living_areas=[], age_premium_coef={}, applyhome_query={}, status="ready", created_at="2026-10-10")  # fmt: skip
    db_session.add(region)
    db_session.flush()
    cxs = []
    for i in range(2):
        cx = Complex(region_id=region.id, applyhome_id=f"20269990{i}", name=f"단지{i}", former_names=[], apply_dates=[],
                     contract_dates=[], inclusion_class="private_sale_apt")  # fmt: skip
        db_session.add(cx)
        db_session.flush()
        cxs.append(cx.id)
    first = load_supply(
        db_session, region.id,
        estimate_supply([SupplyInput(complex_id=c, living_area="la_1", move_in_ym="2027-03", units=1000) for c in cxs]),
    )  # fmt: skip
    assert first.inserted == 2
    gone = db_session.scalars(select(Supply).where(Supply.complex_id == cxs[0])).one()
    db_session.add(FieldProvenance(entity="supply", entity_id=gone.id, field="units", value_text="1000", label="추정",
                                   source_rank=1, chosen=True, checked_at="2026-10-10"))  # fmt: skip
    db_session.flush()
    # 2회차: 단지0 의 입주월이 강등(가려짐) → 입력에서 빠진다
    second = load_supply(
        db_session, region.id,
        estimate_supply([SupplyInput(complex_id=cxs[1], living_area="la_1", move_in_ym="2027-03", units=1000)]),
    )  # fmt: skip
    assert second.deleted == 1 and second.unchanged == 1
    rows = [
        (s.complex_id, s.units)
        for s in db_session.scalars(select(Supply).where(Supply.region_id == region.id))
    ]
    assert rows == [(cxs[1], 1000)]
    assert not list(db_session.scalars(select(FieldProvenance).where(FieldProvenance.entity == "supply",
                                                                     FieldProvenance.entity_id == gone.id)))  # fmt: skip


# ====================================================================== M9


def _t(short: str, long: str = "", area: str = "84.9") -> object:
    from app.normalize.notice_parser import TypeSpec

    return TypeSpec(short=short, long=long, area_text=area, units=10, span=(0, 1))


@pytest.mark.parametrize(
    ("desc", "spec", "line", "want"),
    [
        # (설명, 타입, 줄, 기대: None = 후보 아님 / (금액, 확인됨))
        ("whole token ok", ("84A", "084.9582A"), "84A 분양가 할인 10,000,000원", (10_000_000, True)),
        ("공급금액 할인 명시", ("84A", "084.9582A"), "84A 공급금액 할인 10,000,000원", (10_000_000, True)),
        # D15-1(D14-2 대체): 허용 꼴이 아닌 줄은 '추정'
        ("84A(30세대)", ("84A", "084.9582A"), "84A(30세대) 분양가 할인 10,000,000원", (10_000_000, False)),
        (
            "two types amount each, 84B",
            ("84B", "084.9100B"),
            "84A 분양가 할인 10,000,000원 / 84B 분양가 할인 15,000,000원",
            None,
        ),
        ("84A1 other type", ("84A", "084.9582A"), "84A1 분양가 할인 10,000,000원", None),
        ("159 vs 59", ("59", ""), "159 분양가 할인 10,000,000원", None),
        ("two types same line", ("84A", "084.9582A"), "84A, 84B 분양가 할인 10,000,000원", None),
        ("계약금 할인", ("84A", "084.9582A"), "84A 계약금 할인 10,000,000원", None),
        ("발코니 확장 할인", ("84A", "084.9582A"), "84A 발코니 확장 할인 3,000,000원", None),
        ("중도금 무이자", ("84A", "084.9582A"), "84A 중도금 무이자 10,000,000원", None),
        ("type 84 vs 84A line", ("84", ""), "84A 분양가 할인 10,000,000원", None),
        ("prev line type", ("84A", "084.9582A"), "84A\n분양가 할인 10,000,000원", None),
        # 허용 목록 밖 → 후보로만 '추정'(구매가에서 빼지 않는다)
        ("잔금 일시납", ("84A", "084.9582A"), "84A 잔금 일시납 할인 5,000,000원", (5_000_000, False)),
        ("완납 할인", ("84A", "084.9582A"), "84A 분양대금 완납 할인 5,000,000원", (5_000_000, False)),
        ("조기납부", ("84A", "084.9582A"), "84A 조기납부 할인 5,000,000원", (5_000_000, False)),
        ("저층 한정", ("84A", "084.9582A"), "84A 저층(1~3층) 분양가 할인 10,000,000원", (10_000_000, False)),
        (
            "동호 한정",
            ("84A", "084.9582A"),
            "84A 101동 1호 라인 분양가 할인 10,000,000원",
            (10_000_000, False),
        ),
        ("10층 이상", ("84A", "084.9582A"), "84A 10층 이상 분양가 할인 10,000,000원", (10_000_000, False)),
        ("빌트인 가전", ("84A", "084.9582A"), "84A 빌트인 냉장고 할인 1,200,000원", (1_200_000, False)),
        ("시스템에어컨", ("84A", "084.9582A"), "84A 시스템에어컨 할인 2,500,000원", (2_500_000, False)),
        ("중개수수료", ("84A", "084.9582A"), "84A 중개수수료 할인 1,000,000원", (1_000_000, False)),
        (
            "취득세",
            ("84A", "084.9582A"),
            "84A 취득세 할인 3,000,000원",
            None,
        ),  # D15-1: 할인 아닌 금액 → 사실 없음
        ("84㎡ 면적 표기", ("84A", "084.9582A"), "할인금액(84㎡): 12,500,000원", (12_500_000, False)),
        ("84A-1 표기", ("84A", "084.9582A"), "84A-1 분양가 할인 10,000,000원", (10_000_000, False)),
        (
            "공고 주택형만, 분양가 명시 없음",
            ("84A", "084.9582A"),
            "084.9582A 할인 9,000,000원",
            (9_000_000, False),
        ),
    ],
)
def test_m9_discount_allowlist(
    desc: str, spec: tuple[str, str], line: str, want: tuple[int, bool] | None
) -> None:
    from app.normalize.notice_parser import _discount_line

    got = _discount_line(line + "\n", _t(*spec))  # type: ignore[arg-type]
    assert (None if got is None else (got.won, got.confirmed)) == want, (desc, got)


def test_m9_unconfirmed_discount_candidate_is_estimate_label() -> None:
    """허용 목록 밖 할인 금액은 후보 라벨 '추정'(reason 에 사유) — D12-3 규칙상 구매가에서 빠지지 않는다."""
    from pathlib import Path

    from app.core.contracts_gen import RawDocument as RawDTO
    from app.normalize.notice_parser import parse_notice_text

    base = (Path(__file__).parent / "fixtures" / "notice" / "2025000222_switzen.txt").read_text(
        encoding="utf-8"
    )
    raw = RawDTO(id=1, source_kind="notice_pdf", url="https://static.applyhome.co.kr/x.pdf",
                 fetched_at="2026-10-09T00:00:00+09:00", http_status=200, sha256="0" * 64, region_id=1, path=None,
                 content_type=None, text_path=None, complex_id=None)  # fmt: skip
    for line, label, reason in (
        ("84A 빌트인 냉장고 할인 1,200,000원", "추정", "분양가 할인 명시 아님"),
        ("84A 분양가 할인 1,200,000원", "확인됨", None),
    ):
        disc = [
            c for c in parse_notice_text(base + "\n" + line + "\n", raw) if c.field == "discount_by_type.84A"
        ]
        assert len(disc) == 1, line
        assert disc[0].label == label and disc[0].value == 1_200_000, disc[0]
        assert (reason is None and disc[0].reason is None) or reason in (disc[0].reason or ""), disc[0]


# ====================================================================== M10


def test_m10_cited_remainder_notice_move_in_delay_is_kept(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    """원 번호를 인용한 잔여 공고: 이름·세대수는 버리되(D11-4) 입주 지연(2028-03 → 2028-09)은 원 단지 후보로 받는다."""
    from app.normalize.store import store_raw_document

    from .test_r3d_core2 import _Batch

    key = "2024000111"
    orig = [
        ("complex", key, "name", "검단 원 단지"), ("complex", key, "units_total", 3100),
        ("complex", key, "move_in_ym", "2028-03"),
        ("payment_terms", f"{key}:{key}", "effective_from", "2024-05-01"),
        ("payment_terms", f"{key}:{key}", "notice_kind", "본청약"),
    ]  # fmt: skip
    raw = add_raw(
        "orig", source_kind="notice_pdf", url="https://www.applyhome.co.kr/o.pdf", region_id=region.id
    )
    store_raw_document(db_session, raw, parser=_Batch(orig, "2024-05-01"))
    rem_no = "2026910999"
    rem = [
        ("complex", key, "name", "검단 원 단지(잔여세대)"), ("complex", key, "units_total", 3),
        ("complex", key, "move_in_ym", "2028-09"),
        ("payment_terms", f"{key}:{rem_no}", "effective_from", "2026-09-10"),
        ("payment_terms", f"{key}:{rem_no}", "notice_kind", "임의"),
    ]  # fmt: skip
    raw2 = add_raw(
        "rem", source_kind="notice_pdf", url="https://www.applyhome.co.kr/r.pdf", region_id=region.id
    )
    res = store_raw_document(db_session, raw2, parser=_Batch(rem, "2026-09-10"))
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == key)).one()
    assert (cx.name, cx.units_total, cx.move_in_ym) == ("검단 원 단지", 3100, "2028-09")
    assert sorted({c.field for c in res.skipped if c.entity == "complex"}) == ["name", "units_total"]
    evs = [
        (e.field, e.old_text, e.new_text)
        for e in db_session.scalars(select(ChangeEvent).where(ChangeEvent.complex_id == cx.id))
    ]
    assert any(f == "move_in_ym" for f, _o, _n in evs), evs
