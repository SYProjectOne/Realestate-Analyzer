"""R4 4차 재시험(r4d, 2026-10-13) 실데이터 녹화 재생 도구 — CORE10(D23) 테스트 공용.

녹화: ``fixtures/r4d_core10.zip`` (공개 분양 정보 — bootstrap 일일 단계 원문 중 단지 18개(N13 중복 경쟁률 단지 11 · N14 compare
채택 단지 · N9 추출 단지 · 원 공고 다시 받기 단지)의 청약홈 API·웹 상세, 원 공고 응답, 공고문 추출 텍스트·표, 공식 홈페이지 DOM
텍스트. PDF 바이너리·홈페이지 HTML 제외, 키·토큰 검사 통과). zip 안 ``docs.json`` = 재생 매니페스트(``tests/scheduler/_idem``)·
``raw/…`` = 원문(RAW_DIR 상대 경로). 행 순서 = 수집 순서(raw_document id).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
import re
import zipfile
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import RawDocument as RawDTO
from app.models import RawDocument
from app.normalize.store import raw_dto

ZIP = Path(__file__).resolve().parent / "fixtures" / "r4d_core10.zip"
_HNO = re.compile(r"(?:houseManageNo=|HOUSE_MANAGE_NO%3A%3AEQ%5D=)(\d{10})")


@cache
def manifest() -> dict[str, Any]:
    with zipfile.ZipFile(ZIP) as z:
        data: dict[str, Any] = json.loads(z.read("docs.json").decode("utf-8"))
    return data


def install(raw_dir: Path) -> None:
    """녹화 원문 파일(zip 의 ``raw/…``)을 RAW_DIR 로 푼다."""
    with zipfile.ZipFile(ZIP) as z:
        for info in z.infolist():
            if info.filename.startswith("raw/") and not info.is_dir():
                dst = raw_dir / info.filename.removeprefix("raw/")
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(z.read(info))


def house_no(url: str) -> str | None:
    m = _HNO.search(url)
    return m.group(1) if m else None


def all_rows() -> list[dict[str, Any]]:
    d = manifest()["docs"]
    rows = [*d["applyhome"], *d["notice_pdf"], *(r for v in d["originals"].values() for r in v)]
    return sorted(rows, key=lambda r: int(r["id"]))


def row(raw_id: int) -> dict[str, Any]:
    return next(r for r in all_rows() if r["id"] == raw_id)


def insert(session: Session, items: list[dict[str, Any]], *, region_id: int | None = 1) -> list[RawDTO]:
    """녹화 행 → raw_document(같은 sha256 이면 기존 행) → DTO."""
    out: list[RawDTO] = []
    for r in items:
        found = session.scalars(select(RawDocument).where(RawDocument.sha256 == r["sha256"])).first()
        if found is None:
            vals = {k: v for k, v in r.items() if k not in ("id", "house_no", "complex_id", "region_id")}
            found = RawDocument(**vals, region_id=region_id, complex_id=None)
            session.add(found)
            session.flush()
        out.append(raw_dto(found))
    return out
