"""R3b G1 — N-C4 (D10-4): 같은 블록 병합(W12c)은 잔여 공고(무순위·임의공급·잔여세대)의 새 주택관리번호에만.

- 차수·단지·블록 번호는 이름 키에서 지우지 않는다('(1차)'·'(2차)'는 다른 단지).
- 주소가 '…일원'처럼 구역 표현이면 병합하지 않는다.
- 일반 APT 공고끼리는(이름·주소가 같아도) 병합하지 않는다.
리뷰 재현: '(1차)/(2차)' 괄호 제거로 이름 키가 같아지고 주소('…일원')도 같으면 2차가 1차 행을 덮어씀.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate
from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.models import Complex, Region
from app.normalize.store import block_name_key, store_raw_document

from ._support import AddRaw

APT_DETAIL = "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancDetail.do?houseManageNo={key}&pblancNo={key}&n={n}"
REMNDR_DETAIL = "https://www.applyhome.co.kr/ai/aia/selectAPTRemndrLttotPblancDetailView.do?houseManageNo={key}&pblancNo={key}&n={n}"
API_OPT = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getOPTLttotPblancDetail?cond%5BHOUSE_MANAGE_NO%3A%3AEQ%5D={key}&n={n}"


class _Fields:
    def __init__(self, key: str, values: dict[str, str]) -> None:
        self.key, self.values = key, values

    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]:
        return [
            FieldCandidate(
                entity="complex",
                entity_id=None,
                entity_key=self.key,
                field=f,
                value_text=v,
                value=v,
                source_rank=1,
                source_kind="applyhome_detail",
                primary=True,
                label="확인됨",
                excerpt=v,
                excerpt_start=0,
                excerpt_end=1,
                raw_document_id=raw.id,
                url=raw.url,
                checked_at="2026-10-09",
                observed_on="2026-09-01",
            )
            for f, v in self.values.items()
        ]


def _store(
    db_session: Session, add_raw: AddRaw, region: Region, url: str, key: str, n: int, **values: str
) -> Any:
    raw = add_raw(f"{key} {n} {values}", source_kind="applyhome_detail", url=url.format(key=key, n=n),
                  region_id=region.id)  # fmt: skip
    return store_raw_document(db_session, raw, parser=_Fields(key, values))


def _keys(db_session: Session) -> list[str]:
    return sorted(c.applyhome_id or "" for c in db_session.scalars(select(Complex)))


def test_nc4_round_number_paren_is_kept_in_name_key() -> None:
    assert block_name_key("힐스테이트 송도(1차)") != block_name_key("힐스테이트 송도(2차)")
    assert block_name_key("검단 AA13-1블록") != block_name_key("검단 AA13-2블록")
    assert block_name_key("푸르지오 1단지") != block_name_key("푸르지오 2단지")
    # 잔여 공고의 회차·공급 구분 괄호만 뗀다
    assert block_name_key("더샵 G5-11블록(조합원 자격상실세대 3회차)") == block_name_key("더샵 G5-11블록")
    assert block_name_key("더샵 G5-11블록(임의공급 4차)") == block_name_key("더샵 G5-11블록")


def test_nc4_review_repro_second_phase_remainder_does_not_overwrite_first(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    """리뷰 재현: 1차·2차가 같은 '…일원' 주소 — 2차(잔여 공고)가 1차 행을 덮어쓰면 안 된다."""
    addr = "인천광역시 서구 원당동 123 일원"
    _store(db_session, add_raw, region, APT_DETAIL, "2025000101", 1, name="검단 센트럴(1차)", address=addr)
    _store(db_session, add_raw, region, REMNDR_DETAIL, "2025910102", 2, name="검단 센트럴(2차)", address=addr)
    first = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2025000101")).one()
    assert first.name == "검단 센트럴(1차)" and first.former_names == []
    assert _keys(db_session) == ["2025000101", "2025910102"]


def test_nc4_zone_address_is_never_merged(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    """주소가 구역 표현('일원')이면 이름이 같아도 병합하지 않는다(잔여 공고여도)."""
    addr = "인천광역시 연수구 송도동 6-1 일원"
    _store(db_session, add_raw, region, APT_DETAIL, "2025000201", 1, name="송도 단지", address=addr)
    _store(
        db_session,
        add_raw,
        region,
        REMNDR_DETAIL,
        "2025910202",
        2,
        name="송도 단지(무순위 1회차)",
        address=addr,
    )
    assert _keys(db_session) == ["2025000201", "2025910202"]


def test_nc4_general_apt_notices_are_never_merged(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    """일반 APT 공고끼리는 이름·주소가 완전히 같아도 병합하지 않는다."""
    addr = "인천광역시 연수구 송도동 32-15"
    _store(db_session, add_raw, region, APT_DETAIL, "2025000301", 1, name="같은 단지", address=addr)
    _store(db_session, add_raw, region, APT_DETAIL, "2025000302", 2, name="같은 단지", address=addr)
    assert _keys(db_session) == ["2025000301", "2025000302"]


def test_nc4_remainder_notice_still_binds_to_same_block(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    """잔여 공고(웹 상세·API 임의공급)는 같은 블록 단지 1개에 묶는다 — 기존 W12c 동작 유지."""
    addr = "인천광역시 연수구 송도동 32-15 (G5-11BL)"
    _store(
        db_session,
        add_raw,
        region,
        APT_DETAIL,
        "2026000169",
        1,
        name="더샵 송도그란테르 G5-11블록",
        address=addr,
    )
    _store(db_session, add_raw, region, REMNDR_DETAIL, "2026910207", 2,
           name="더샵 송도그란테르 G5-11블록(조합원 자격상실세대 3회차)", address=addr + "번지")  # fmt: skip
    _store(db_session, add_raw, region, API_OPT, "2026910208", 3,
           name="더샵 송도그란테르 G5-11블록(임의공급 4차)", address=addr)  # fmt: skip
    assert _keys(db_session) == ["2026000169"]
