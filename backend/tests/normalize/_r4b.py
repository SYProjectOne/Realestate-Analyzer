"""R4 재시험(r4b, 2026-10-12) 실데이터 녹화 재생 도구 — CORE8(D21) 테스트 공용.

녹화: ``fixtures/r4b_core8`` (공개 분양 정보 — 청약홈 API·웹 상세, 공고문 추출 텍스트·표. PDF 바이너리 제외, 키·토큰 검사 통과).
``docs.json`` 의 그룹:

- ``elif``: 엘리프 검단 포레듀(AA32블록) 원 공고 2025000302 + 무순위 2025910193 + 임의공급 2025940252 — 잔여 공고문이 원 번호를
  '2025-000302'(하이픈)로 적는다(R4 N3·N4).
- ``n1``: 검단호수공원역 중흥S-클래스(2025000253) — 공고문 공급금액 표 '(단위: 세대, 천원)'(R4 N1).
- ``n2``: NUL 문자가 든 잔여 공고문 2건(2025910104·2025930032) + 그 청약홈 잔여 공고(R4 N2).
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

FIX = Path(__file__).resolve().parent / "fixtures" / "r4b_core8"


@cache
def manifest() -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = json.loads((FIX / "docs.json").read_text(encoding="utf-8"))["docs"]
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


def insert(
    session: Session, items: list[dict[str, Any]], *, region_id: int | None = 1, overrides: dict[str, Any] | None = None
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
