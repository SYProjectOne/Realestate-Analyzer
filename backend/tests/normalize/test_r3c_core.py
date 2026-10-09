"""R3c CORE — 정규화 쪽 3차 리뷰 재현 (`docs/design/wp/R3_REVIEW3.md`, DECISIONS D11-4).

- C-2: 잔여·임의·무순위 공고를 원 단지에 묶어도 그 공고의 단지 단위 필드(이름·당첨일·세대수)는 원 단지 값을 덮어쓰지 않는다
  (payment_terms·competition·remaining_event 에만). D11-4 이전에 쓰인 오염 출처 행도 재정규화 후보가 되지 않는다.
- M-7: 괄호 안 차수 + 잔여 표기('(2차 잔여세대)')에서 차수까지 지우지 않는다 → 1차에 병합되지 않는다.
- M-8: 잔여 이벤트 이름 끝 '(N차)'를 지우지 않는다 → 2차 잔여 이벤트가 1차에 붙지 않는다(원래 단지가 없으면 unmatched).
- minor 18: 구역 표현 '1056-1외'·'AA13블록외 2' 인식, 하이픈을 지워 'AA1-31' = 'AA13-1' 이 되던 키.
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate
from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.models import Complex, FieldProvenance, PaymentTerms, Region
from app.normalize._text import strip_supply_round
from app.normalize.remaining import remainder_name_key
from app.normalize.store import address_key, block_name_key, is_zone_address, store_raw_document

from ._support import AddRaw

APT_DETAIL = "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancDetail.do?houseManageNo={key}&pblancNo={key}&n={n}"
REMNDR_DETAIL = "https://www.applyhome.co.kr/ai/aia/selectAPTRemndrLttotPblancDetailView.do?houseManageNo={key}&pblancNo={key}&n={n}"


class _Notice:
    """공고 1건의 단지 단위 후보 + (잔여 공고면) 납부 조건 후보."""

    def __init__(self, key: str, values: dict[str, Any], *, terms_kind: str | None = None) -> None:
        self.key, self.values, self.terms_kind = key, values, terms_kind

    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]:
        def cand(entity: str, ekey: str, field: str, v: Any) -> FieldCandidate:
            return FieldCandidate(
                entity=entity, entity_id=None, entity_key=ekey, field=field, value_text=str(v), value=v,  # type: ignore[arg-type]
                source_rank=1, source_kind="applyhome_detail", primary=True, label="확인됨", excerpt=str(v),
                excerpt_start=0, excerpt_end=1, raw_document_id=raw.id, url=raw.url, checked_at="2026-10-09",
                observed_on="2026-09-01",
            )  # fmt: skip

        out = [cand("complex", self.key, f, v) for f, v in self.values.items()]
        if self.terms_kind:
            tk = f"{self.key}:{self.key}"
            out += [
                cand("payment_terms", tk, "effective_from", "2026-09-10"),
                cand("payment_terms", tk, "notice_kind", self.terms_kind),
            ]
        return out


def _store(
    db: Session,
    add_raw: AddRaw,
    region: Region,
    url: str,
    key: str,
    n: int,
    values: dict[str, Any],
    **kw: Any,
) -> Any:
    raw = add_raw(
        f"{key} {n} {values}",
        source_kind="applyhome_detail",
        url=url.format(key=key, n=n),
        region_id=region.id,
    )
    return store_raw_document(db, raw, parser=_Notice(key, values, **kw))


def test_c2_remainder_notice_does_not_overwrite_original_complex_unit_fields(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    addr = "인천광역시 연수구 송도동 32-15 (G5-11BL)"
    orig = {
        "name": "더샵 송도그란테르 G5-11블록",
        "address": addr,
        "winner_date": "2024-05-20",
        "units_general": 800,
    }
    _store(db_session, add_raw, region, APT_DETAIL, "2024000169", 1, orig)
    rem = {
        "name": "더샵 송도그란테르 G5-11블록(임의공급 4차)", "address": addr,
        "winner_date": "2026-09-20", "units_general": 3,
    }  # fmt: skip
    res = _store(db_session, add_raw, region, REMNDR_DETAIL, "2026910208", 2, rem, terms_kind="임의")
    rows = list(db_session.scalars(select(Complex).where(Complex.name.contains("G5-11"))))
    assert len(rows) == 1, "잔여 공고는 원 단지에 묶인다(D10-4)"
    cx = rows[0]
    assert (cx.name, cx.winner_date, cx.units_general) == (orig["name"], "2024-05-20", 800), (
        "잔여 공고의 단지 단위 값이 원 단지를 덮어쓰면 안 된다(C-2·D11-4)"
    )
    assert cx.former_names == []
    terms = list(db_session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == cx.id)))
    assert [t.notice_kind for t in terms] == ["임의"], "공고별 기록(payment_terms)에는 남는다"
    assert res.complex_ids == [cx.id], "재판정 대상에는 원 단지"
    assert {c.field for c in res.skipped if c.entity == "complex"} == set(rem)


def test_c2_polluted_rows_from_before_d11_4_are_not_candidates(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    """D11-4 이전에 잔여 공고가 원 단지에 쓴 단지 단위 출처 행(entity_key = 잔여 공고 번호)은 재정규화 후보가 아니다."""
    addr = "인천광역시 연수구 송도동 32-20"
    orig = {"name": "송도 단지 A", "address": addr, "winner_date": "2024-05-20"}
    _store(db_session, add_raw, region, APT_DETAIL, "2024000170", 1, orig)
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2024000170")).one()
    other = add_raw(
        "polluted",
        source_kind="applyhome_detail",
        url=REMNDR_DETAIL.format(key="2026910300", n=9),
        region_id=region.id,
    )
    for fp in db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity_id == cx.id, FieldProvenance.field == "winner_date"
        )
    ):
        fp.chosen = False
    db_session.add(
        FieldProvenance(
            entity="complex", entity_id=cx.id, entity_key="2026910300", field="winner_date", value_text="2026-09-20",
            value_norm="2026-09-20", raw_document_id=other.id, url=other.url, checked_at="2026-10-09", label="확인됨",
            source_rank=1, chosen=True, excerpt="2026-09-20", observed_on="2026-09-30",
        )
    )  # fmt: skip
    cx.winner_date = "2026-09-20"
    db_session.flush()
    _store(db_session, add_raw, region, APT_DETAIL, "2024000170", 2, orig)  # 원 공고 재정규화
    db_session.refresh(cx)
    assert cx.winner_date == "2024-05-20", "오염 행이 다시 이기면 안 된다"


def test_m7_phase_inside_supply_paren_is_kept() -> None:
    assert strip_supply_round("힐스테이트 송도(2차 잔여세대)") == "힐스테이트 송도(2차)"
    assert block_name_key("힐스테이트 송도(2차 잔여세대)") != block_name_key("힐스테이트 송도")
    assert block_name_key("힐스테이트 송도(2차 잔여세대)") == block_name_key("힐스테이트 송도(2차)")
    # 공급 구분 낱말 뒤 회차는 공급 회차 — 지운다
    assert block_name_key("더샵 G5-11블록(임의공급 4차)") == block_name_key("더샵 G5-11블록")
    assert block_name_key("더샵 G5-11블록(조합원 자격상실세대 3회차)") == block_name_key("더샵 G5-11블록")


def test_m7_second_phase_remainder_is_not_merged_into_first(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    addr = "인천광역시 연수구 송도동 77-1"
    _store(
        db_session, add_raw, region, APT_DETAIL, "2024000201", 1, {"name": "힐스테이트 송도", "address": addr}
    )
    _store(
        db_session,
        add_raw,
        region,
        REMNDR_DETAIL,
        "2026910202",
        2,
        {"name": "힐스테이트 송도(2차 잔여세대)", "address": addr},
    )
    keys = sorted(c.applyhome_id or "" for c in db_session.scalars(select(Complex)))
    assert keys == ["2024000201", "2026910202"], "2차 잔여 공고가 1차에 병합되면 안 된다(M-7)"


def test_m8_remainder_key_keeps_phase() -> None:
    assert remainder_name_key("리아츠 송도(2차)") != remainder_name_key("리아츠 송도")
    assert remainder_name_key("리아츠 송도 (3회차)") == remainder_name_key("리아츠 송도")


def test_minor18_zone_and_hyphen_keys() -> None:
    assert is_zone_address("인천광역시 서구 원당동 1056-1외")
    assert is_zone_address("검단신도시 AA13블록외 2")
    assert not is_zone_address("인천광역시 연수구 송도동 32-15")
    assert block_name_key("검단 AA1-31블록") != block_name_key("검단 AA13-1블록")
    assert address_key("송도동 32-15번지 (G5-11BL)") == address_key("송도동 32-15 (G5-11BL)")
