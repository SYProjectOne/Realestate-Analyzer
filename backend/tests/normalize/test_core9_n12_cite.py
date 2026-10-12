"""R4 3차 재시험 N12(minor, D22-4) — 원 공고 인용의 변형 문구 '최초 입주자모집공고일은 … 주택관리번호는 …'.

R4 3차: 월드메르디앙 송도(3차) 임의공급 공고문(2024940118)은 원 번호를 '이 아파트는 최초 입주자모집공고일은 2023.09.25(월요일)이며,
주택관리번호는 2023000463이므로 …'로 적는다. ``최초 주택관리번호는 …`` 만 읽던 정규식이 이를 인용으로 읽지 못해 잔여 공고 번호로
단지 행(70)이 생겼고 원 공고는 다시 받지 않았다. 같은 공고문의 '임의공급 3차 입주자모집공고일은 2024.11.04(월요일), 주택관리번호는
2024940118' 은 이 공고 자기 번호다(인용 아님).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Complex, Region
from app.normalize.notice_parser import notice_numbers
from app.normalize.store import store_raw_document

from . import _r4c

PDF = 654  # 2024940118 임의공급 공고문


def test_variant_original_citation_is_read(db_session: Session, raw_dir: Path) -> None:
    _r4c.install(raw_dir)
    (dto,) = _r4c.insert(db_session, [_r4c.row("n12", PDF)], region_id=None)
    assert "최초 입주자모집공고일은 2023.09.25(월요일)이며, 주택관리번호는 2023000463" in _r4c.text_of(
        "n12", PDF
    )
    assert notice_numbers(dto, raw_dir=raw_dir) == ("2024940118", "2023000463")


def test_own_number_sentence_is_not_a_citation() -> None:
    """'최초' 가 없는 자기 번호 문장·같은 번호 인용은 인용이 아니다(파싱 규칙 회귀 방지)."""
    from app.normalize.notice_parser import _ORIG_NO_RE, _no

    own = "■ 본 아파트의 임의공급 3차 입주자모집공고일은 2024.11.04(월요일), 주택관리번호는 2024940118입니다."
    assert _ORIG_NO_RE.search(own) is None
    m = _ORIG_NO_RE.search("■ 최초 주택관리번호는 2025-000302 입니다")
    assert m is not None and _no(m) == "2025000302"


def test_variant_citation_attaches_to_original_not_own_row(
    db_session: Session, raw_dir: Path, region: Region
) -> None:
    """공고문을 저장해도 잔여 공고 번호(2024940118)로 단지 행이 생기지 않는다 — 원 번호(2023000463) 단지 쪽."""
    _r4c.install(raw_dir)
    (dto,) = _r4c.insert(db_session, [_r4c.row("n12", PDF)], region_id=region.id)
    store_raw_document(db_session, dto, raw_dir=raw_dir)
    db_session.flush()
    keys = set(db_session.scalars(select(Complex.applyhome_id)))
    assert "2024940118" not in keys, f"잔여 공고 번호로 단지 행: {sorted(k for k in keys if k)}"
    assert "2023000463" in keys
