"""R4 재시험 N2(major, D21-2) — 수집 텍스트의 NUL·제어 문자는 저장 전에 공백으로 바꾼다(원문 파일은 그대로 보존).

R4: 잔여 공고문 2건(rd613 2025910104 더샵 송도센터니얼 무순위, rd616 2025930032 송도프라임뷰 불법행위재공급)의 pdfplumber
텍스트에 NUL(\\x00) 3,378·4,222개가 낱말 사이 구분자로 들어 있어 ① ``field_provenance.excerpt`` INSERT 가 Postgres 에서
``DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes`` — 그 공고문 값이 매 실행 저장되지 않았고, ② 인용 정규식
(``\\s``)이 '최초\\x00주택관리번호는\\x00…' 를 못 읽어 원 번호(2020000611·2019000711)를 잃고 자기 번호 단지 행이 생겼다.
(Postgres 저장 확인은 ``tests/contracts/test_core8_pg_nul.py``.)
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Complex, FieldProvenance, RawDocument, Region
from app.normalize._text import read_raw_text
from app.normalize.notice_parser import notice_numbers
from app.normalize.store import raw_dto, store_raw_document

from . import _r4b

N2 = "n2"
NUL_NOTICES = {613: ("2025910104", "2020000611"), 616: ("2025930032", "2019000711")}


def _dto(session: Session, raw_dir: Path, raw_id: int, region_id: int | None = None) -> object:
    _r4b.install(raw_dir)
    (dto,) = _r4b.insert(session, [_r4b.row(N2, raw_id)], region_id=region_id)
    return dto


def test_recorded_notice_really_has_nul(raw_dir: Path) -> None:
    """녹화 원문(추출 텍스트 파일)에는 NUL 이 그대로 있다 — 원문 파일은 고치지 않는다."""
    _r4b.install(raw_dir)
    for rid in NUL_NOTICES:
        data = (raw_dir / str(_r4b.row(N2, rid)["text_path"])).read_bytes()
        assert data.count(b"\x00") > 1000


def test_read_raw_text_replaces_control_chars_keeping_offsets(db_session: Session, raw_dir: Path) -> None:
    dto = _dto(db_session, raw_dir, 613)
    text = read_raw_text(dto, raw_dir=raw_dir)  # type: ignore[arg-type]
    assert text is not None
    assert "\x00" not in text, "파서·저장으로 가는 텍스트에 NUL 없음"
    original = (raw_dir / str(_r4b.row(N2, 613)["text_path"])).read_bytes().decode("utf-8")
    assert len(text) == len(original), "공백 1자로 바꿔 발췌 오프셋이 그대로"
    assert "\n" in text and "\f" in text or "\n" in text  # 줄바꿈·쪽 나눔은 남긴다


def test_cited_original_number_is_read_through_nul(db_session: Session, raw_dir: Path) -> None:
    for rid, (own, orig) in NUL_NOTICES.items():
        dto = _dto(db_session, raw_dir, rid)
        assert notice_numbers(dto, raw_dir=raw_dir) == (own, orig)  # type: ignore[arg-type]


def test_store_nul_notice_has_no_nul_in_db_and_attaches_to_original(
    db_session: Session, raw_dir: Path, region: Region
) -> None:
    for rid, (own, orig) in NUL_NOTICES.items():
        dto = _dto(db_session, raw_dir, rid, region.id)
        res = store_raw_document(db_session, dto, raw_dir=raw_dir)  # type: ignore[arg-type]
        assert res.provenance_ids, f"rd{rid}: 정규화 값이 저장된다"
        bad = db_session.scalars(
            select(FieldProvenance.id).where(
                FieldProvenance.raw_document_id == dto.id,  # type: ignore[attr-defined]
            )
        ).all()
        assert bad
        for fp in db_session.scalars(select(FieldProvenance).where(FieldProvenance.raw_document_id == dto.id)):  # type: ignore[attr-defined]
            for col in (fp.excerpt, fp.value_text, fp.reason, fp.value_norm):
                assert "\x00" not in (col or ""), (rid, fp.field)
        ids = set(db_session.scalars(select(Complex.applyhome_id)))
        assert own not in ids, f"잔여 공고 번호 {own} 로 단지 행을 만들지 않는다(원 번호 {orig} 인용)"
        assert orig in ids
    # 원문 행은 그대로(파일 경로·sha256)
    row = db_session.get(RawDocument, _r4b.insert(db_session, [_r4b.row(N2, 613)], region_id=region.id)[0].id)
    assert row is not None and raw_dto(row).text_path == _r4b.row(N2, 613)["text_path"]
