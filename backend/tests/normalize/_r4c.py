"""R4 3차 재시험(r4c, 2026-10-12) 실데이터 녹화 재생 도구 — CORE9(D22) 테스트 공용.

녹화: ``fixtures/r4c_core9`` (공개 분양 정보 — 청약홈 API·웹 상세, 공고문 추출 텍스트·표. PDF 바이너리 제외, 키·토큰 검사 통과).
공고문 행의 ``path`` 는 텍스트 추출본(파이프라인 P1~P3 가 path 있는 원문만 읽는다). ``docs.json`` 의 그룹:

- ``n9``: 판정기 추출로 납부 조건(잔금·계약금 비율)을 채운 6단지(2026000065·2025000253·2026000367·2026000219·2025000499·
  2025000222) — 청약홈 API·웹 상세 4 + 공고문 1 씩(R4 3차 N9).
- ``n10``: 잔여 공고 청약홈 원문(2025930055·2025930047·2025910191) + 원 번호를 인용한 잔여 공고문 2건(603·608) — 원 단지
  주소(원 공고)에 동이 없다(R4 3차 N10).
- ``n10_orig``: 원 공고 다시 받기 응답(2021000189 'RC3BL' · 2021000830 '396-11번지(…A17BL)').
- ``n12``: 임의공급 2024940118 — 공고문이 원 번호를 '최초 입주자모집공고일은 … 주택관리번호는 2023000463'으로 적는다(N12).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
import shutil
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import RawDocument as RawDTO
from app.models import RawDocument
from app.normalize.store import raw_dto

FIX = Path(__file__).resolve().parent / "fixtures" / "r4c_core9"


@cache
def manifest() -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = json.loads((FIX / "docs.json").read_text(encoding="utf-8"))[
        "docs"
    ]
    return data


def rows(group: str, ids: list[int] | None = None) -> list[dict[str, Any]]:
    out = manifest()[group]
    return [r for r in out if ids is None or r["id"] in ids]


def row(group: str, raw_id: int) -> dict[str, Any]:
    return next(r for r in manifest()[group] if r["id"] == raw_id)


def install(raw_dir: Path) -> None:
    """녹화 원문 파일을 RAW_DIR 로 복사한다."""
    shutil.copytree(FIX / "raw", raw_dir, dirs_exist_ok=True)


def text_of(group: str, raw_id: int) -> str:
    r = row(group, raw_id)
    return (FIX / "raw" / str(r["text_path"] or r["path"])).read_text(encoding="utf-8")


def house_no(url: str) -> str | None:
    import re

    m = re.search(r"(?:houseManageNo=|HOUSE_MANAGE_NO%3A%3AEQ%5D=)(\d{10})", url)
    return m.group(1) if m else None


def insert(
    session: Session,
    items: list[dict[str, Any]],
    *,
    region_id: int | None = 1,
    overrides: dict[str, Any] | None = None,
) -> list[RawDTO]:
    """녹화 행 → raw_document(같은 sha256 이면 기존 행) → DTO."""
    out: list[RawDTO] = []
    for r in items:
        found = session.scalars(select(RawDocument).where(RawDocument.sha256 == r["sha256"])).first()
        if found is None:
            vals = {k: v for k, v in r.items() if k != "id"}
            vals.update(overrides or {})
            found = RawDocument(**vals, region_id=region_id, complex_id=None)
            session.add(found)
            session.flush()
        out.append(raw_dto(found))
    return out
