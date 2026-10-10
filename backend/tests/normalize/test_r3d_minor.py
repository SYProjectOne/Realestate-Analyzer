"""R3d CORE2 — 정규화 쪽 4차 리뷰 minor(`R3_REVIEW4.md` 이름 키·병합·체크리스트·호재·할인).

| minor | 테스트 |
| --- | --- |
| 이름 키 | '(1블록 잔여세대)'·'(3BL 무순위)'·'(Ⅱ 잔여세대)'·'(잔여세대 2차)' 의 단지 표기 보존, '1056-1외, 1056-2' 구역, AA1-31≠AA13-1 |
| M-8(3차) | 2차 잔여 공고가 1차 단지에 붙지 않고 unmatched 로 기록 |
| 병합 | 같은 블록에 묶인 잔여 공고는 원 단지 타입 행을 새로 만들지 않는다 |
| 할인 | 0·음수·공급가 이상 할인은 확인됨이어도 빼지 않는다 |
| 아카이브 | 월별 압축된 공고문도 읽는다(아카이브 우선 분양가가 조용히 폴백하지 않게) |
"""

# ruff: noqa: E501

from __future__ import annotations

import io
import tarfile
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate
from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.models import Complex, ComplexType, Region
from app.normalize._text import strip_supply_round
from app.normalize.benchmark import normalize_apt_name
from app.normalize.store import is_zone_address, store_raw_document

from ._assemble_support import add_complex
from ._support import AddRaw


def test_name_keys_keep_block_and_phase_tokens() -> None:
    assert strip_supply_round("검단 푸르지오(1블록 잔여세대)") == "검단 푸르지오(1블록)"
    assert strip_supply_round("송도 더샵(3BL 무순위)") == "송도 더샵(3BL)"
    assert strip_supply_round("한강 센트럴(Ⅱ 잔여세대)") == "한강 센트럴(Ⅱ)"
    assert strip_supply_round("힐스테이트(잔여세대 2차)") == "힐스테이트(2차)"
    assert strip_supply_round("더샵(임의공급 4차)") == "더샵", "공급 회차는 지운다"
    assert strip_supply_round("A(조합원 자격상실세대 3회차)") == "A"
    assert is_zone_address("인천광역시 서구 원당동 1056-1외, 1056-2")
    assert not is_zone_address("인천광역시 연수구 송도동 32-15")
    assert normalize_apt_name("검단 AA1-31블록") != normalize_apt_name("검단 AA13-1블록")
    assert normalize_apt_name("힐스테이트 레이크 송도(2차)") == normalize_apt_name("힐스테이트레이크송도2차")


def test_m8_second_phase_remainder_is_unmatched_not_attached_to_first(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    from app.normalize.remaining import sync_remaining_events

    from .test_remaining_f1a import SONGDO, _api_notice

    add_complex(db_session, region.id, "2024000700", "리아츠 송도", address="인천광역시 연수구 송도동 308-1",
                legal_dong_code=SONGDO)  # fmt: skip
    _api_notice(db_session, add_raw, region, "2026910900", "리아츠 송도(2차 잔여세대)")
    res = sync_remaining_events(
        db_session, region.id, snapshot_id=None, detected_at="2026-10-09T06:00:00+09:00"
    )
    assert any(u["notice_no"] == "2026910900" for u in res.unmatched), res.unmatched
    first = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2024000700")).one()
    from app.models import RemainingEvent

    assert not list(
        db_session.scalars(select(RemainingEvent).where(RemainingEvent.complex_id == first.id))
    ), "2차 잔여 이벤트가 1차 단지에 붙으면 안 된다"


class _Rows:
    def __init__(self, rows: list[tuple[str, str, str, Any]]) -> None:
        self.rows = rows

    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]:
        return [
            FieldCandidate(
                entity=e,
                entity_id=None,
                entity_key=k,
                field=f,
                value=v,
                value_text=str(v),
                source_rank=1,  # type: ignore[arg-type]
                source_kind="applyhome_detail",
                primary=True,
                label="확인됨",
                excerpt=f"{f} {v}",
                raw_document_id=raw.id,
                url=raw.url,
                checked_at="2026-10-09",
                observed_on="2026-09-10",
            )
            for e, k, f, v in self.rows
        ]


def test_merged_remainder_does_not_precreate_type_rows(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    addr = "인천광역시 연수구 송도동 32-15 (G5-11BL)"
    key = "2024000169"
    raw = add_raw("o", source_kind="applyhome_detail",
                  url=f"https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancDetail.do?houseManageNo={key}&pblancNo={key}",
                  region_id=region.id)  # fmt: skip
    store_raw_document(db_session, raw, parser=_Rows([
        ("complex", key, "name", "더샵 송도 G5-11블록"), ("complex", key, "address", addr),
        ("complex_type", f"{key}:84A", "units", 100),
    ]))  # fmt: skip
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == key)).one()
    rem = "2026910208"
    raw2 = add_raw("r", source_kind="applyhome_detail",
                   url=f"https://www.applyhome.co.kr/ai/aia/selectAPTRemndrLttotPblancDetailView.do?houseManageNo={rem}&pblancNo={rem}",
                   region_id=region.id)  # fmt: skip
    store_raw_document(db_session, raw2, parser=_Rows([
        ("complex", rem, "name", "더샵 송도 G5-11블록(임의공급 4차)"), ("complex", rem, "address", addr),
        ("complex_type", f"{rem}:59B", "units", 1),
        ("payment_terms", f"{rem}:{rem}", "effective_from", "2026-09-10"),
        ("payment_terms", f"{rem}:{rem}", "notice_kind", "임의"),
    ]))  # fmt: skip
    codes = sorted(
        t.type_code for t in db_session.scalars(select(ComplexType).where(ComplexType.complex_id == cx.id))
    )
    assert codes == ["84A"], f"묶인 잔여 공고의 타입 행(59B)을 원 단지에 만들면 안 된다: {codes}"


def test_discount_bounds_not_subtracted_even_if_confirmed() -> None:
    from app.analysis.price_view import current_price

    class T:
        id, type_code, area_m2 = 1, "84A", 84.9
        max_price_won, floor_sample_price_won, balcony_won, options_required_won = (
            600_000_000,
            None,
            None,
            None,
        )

    class P:
        def __init__(self, disc: int) -> None:
            self.id, self.effective_from, self.notice_no, self.price_by_type = 7, "2026-09-01", "n", {}
            self.discount_by_type = {"84A": disc}

    for disc in (-5_000_000, 600_000_000, 700_000_000):
        view = current_price([T()], [P(disc)], discount_label=lambda r: "확인됨")  # type: ignore[list-item]
        assert not view.discount_applied and view.high_won == 600_000_000, disc
    ok = current_price([T()], [P(10_000_000)], discount_label=lambda r: "확인됨")  # type: ignore[list-item]
    assert ok.discount_applied and ok.high_won == 590_000_000


def test_read_raw_text_falls_back_to_month_archive(tmp_path: Path) -> None:
    from app.normalize._text import read_raw_text

    rel = "notice_pdf/2026-08-14/abc.txt"
    src = tmp_path / "notice_pdf"
    src.mkdir()
    data = "공급금액 표 84A 605,000,000".encode()
    with tarfile.open(src / "2026-08.tar.gz", "w:gz") as tar:
        info = tarfile.TarInfo(rel)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    raw = RawDocumentDTO(id=1, source_kind="notice_pdf", url="https://www.applyhome.co.kr/x.pdf",
                         fetched_at="2026-08-15T06:00:00+09:00", http_status=200, sha256="a" * 64, path=rel,
                         content_type="text/plain", text_path=rel, complex_id=None, region_id=None,
                         error_text=None, image_hash=None)  # fmt: skip
    assert read_raw_text(raw, raw_dir=tmp_path) == "공급금액 표 84A 605,000,000", (
        "원본이 없으면 월별 압축에서 읽는다"
    )


def test_minor23_one_field_with_long_excerpts_keeps_every_excerpt() -> None:
    from app.normalize.extract_request import MAX_TEXT, build_extract_requests

    def cand(i: int) -> FieldCandidate:
        return FieldCandidate(
            entity="payment_terms", entity_id=None, entity_key="k:1", field="interim_schedule", value=None,
            value_text=None, source_rank=1, source_kind="notice_pdf", primary=True, label="확인 불가",
            excerpt=f"[발췌{i}]" + "가" * 900, raw_document_id=5, url="https://www.applyhome.co.kr/x", checked_at="2026-10-09",
            needs_extract=True,
        )  # fmt: skip

    [req] = build_extract_requests([cand(i) for i in range(4)])
    assert len(req.text) <= MAX_TEXT
    assert all(f"[발췌{i}]" in req.text for i in range(4)), (
        "한 필드 발췌 합이 길어도 뒤 발췌가 잘려 나가지 않는다"
    )
