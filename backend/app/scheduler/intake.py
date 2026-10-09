"""접수 상태 행의 분류 문구·이전 분류 복사 (DECISIONS D10-2, R3 재리뷰 N-C2).

- ``intake_text``: 접수 상태 행의 원문(공식 홈페이지 HTML·렌더 DOM 텍스트) → classify 항목 텍스트. 접수 문구 후보 줄
  (normalize official_site 파서 — 분류하지 않음)이 있으면 그 줄들, 없으면 DOM 텍스트 앞부분. 파이프라인 접수 classify
  입력과 여기 해시 비교가 같은 함수를 쓴다.
- ``carry_classification``: '접수 문구 미분류' 행의 문구 해시(sha256)가 같은 (단지, 경로)의 **직전 분류 행**(판정기
  classify 로 정한 행)과 같으면 그 분류(status·reason·note)를 복사한다 — 판정 호출 없음. 수집(collect)과 파이프라인
  접수 classify 앞에서 부른다. 그래서 변경 없는 날(T8) publish 스냅샷의 접수 상태·판정 범위·순위가 전날과 같고,
  다음 변경일에 단지마다 D9-3 critical 이벤트가 쏟아지지 않는다.
- 판단하지 않는다: 문자열 해시 비교(산술)만. 문구가 바뀌었으면 미분류로 두어 판정기가 다시 분류한다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import hashlib
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IntakeStatus, RawDocument, Snapshot
from app.normalize._text import read_raw_text
from app.normalize.store import parser_for, raw_dto

__all__ = [
    "CLASSIFIED_MARK",
    "COPIED_MARK",
    "INTAKE_PATHS",
    "NO_TEXT",
    "UNCLASSIFIED",
    "carry_classification",
    "intake_text",
    "pending_complexes",
    "text_sha256",
]

UNCLASSIFIED: Final = "접수 문구 미분류"  # collect.intake_rows 가 남기는 사유(분류 대기)
INTAKE_PATHS: Final = ("official_popup", "headless_shot")
INTAKE_TEXT_MAX: Final = 2000
CLASSIFIED_MARK: Final = "판정기 classify"
"""파이프라인 접수 classify 가 note 에 남기는 표식(``판정기 classify jl_<seq>``) — 판정기로 정한 행."""
COPIED_MARK: Final = "문구 해시 동일 — 이전 분류 복사"
NO_TEXT: Final = "접수 문구 없음"
"""원문에 접수 문구가 없어 판정기 호출 없이 남긴 사유(파이프라인 접수 classify) — 문구가 그대로 없으면 그대로 복사."""


def intake_text(session: Session, row: IntakeStatus) -> str:
    """접수 상태 행의 원문 → classify 항목 텍스트(최대 2000자)."""
    doc = session.get(RawDocument, row.raw_document_id) if row.raw_document_id is not None else None
    if doc is None:
        return ""
    dto = raw_dto(doc)
    parser = parser_for("official_site")
    lines: list[str] = []
    if parser is not None:
        try:
            lines = [str(c.value_text) for c in parser.parse(dto) if c.value_text]
        except Exception:  # 원문 파일 없음 등 — 아래 DOM 텍스트로
            lines = []
    text = "\n".join(dict.fromkeys(lines))
    if not text:
        src = dto.model_copy(update={"path": None}) if row.path == "headless_shot" else dto
        text = (read_raw_text(src) or "").strip()
    return text[:INTAKE_TEXT_MAX]


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _classified(row: IntakeStatus) -> bool:
    """파이프라인이 처리한 행: 판정기 classify 결과이거나 '접수 문구 없음'(호출 없이 사유만)."""
    return row.reason != UNCLASSIFIED and (CLASSIFIED_MARK in (row.note or "") or row.reason == NO_TEXT)


def _previous_classified(session: Session, snap: Snapshot, row: IntakeStatus) -> IntakeStatus | None:
    """같은 지역·(단지, 경로)의 기준일 전(또는 같은 기준일의 앞선) 스냅샷에서 가장 최근의 판정기 분류 행."""
    stmt = (
        select(IntakeStatus)
        .join(Snapshot, Snapshot.id == IntakeStatus.snapshot_id)
        .where(
            Snapshot.region_id == snap.region_id,
            Snapshot.id != snap.id,
            Snapshot.asof_date <= snap.asof_date,
            IntakeStatus.complex_id == row.complex_id,
            IntakeStatus.path == row.path,
            IntakeStatus.reason.is_distinct_from(UNCLASSIFIED),
        )
        .order_by(Snapshot.asof_date.desc(), IntakeStatus.id.desc())
    )
    for cand in session.scalars(stmt.limit(20)):
        if _classified(cand):
            return cand
    return None


def carry_classification(session: Session, snapshot_id: int) -> list[int]:
    """이 스냅샷의 '접수 문구 미분류' 행 중 문구 해시가 직전 분류 행과 같은 것 → 분류 복사. 복사한 행 id."""
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        return []
    rows = list(
        session.scalars(
            select(IntakeStatus)
            .where(
                IntakeStatus.snapshot_id == snapshot_id,
                IntakeStatus.path.in_(INTAKE_PATHS),
                IntakeStatus.reason == UNCLASSIFIED,
            )
            .order_by(IntakeStatus.id)
        )
    )
    out: list[int] = []
    for row in rows:
        prev = _previous_classified(session, snap, row)
        if prev is None:
            if not intake_text(session, row).strip():
                # 원문에 접수 문구가 없다(팝업 그림만 등) — 분류할 것이 없으니 판정 호출 없이 사유만(파이프라인과 같은 규칙)
                row.reason = NO_TEXT
                out.append(row.id)
            continue
        if prev.raw_document_id != row.raw_document_id:  # 같은 원문 행(같은 sha256)이면 문구도 같다
            now_text = intake_text(session, row).strip()
            if text_sha256(now_text) != text_sha256(intake_text(session, prev).strip()):
                continue
        row.status = prev.status
        row.reason = prev.reason
        # 복사 표식은 매일 쌓이지 않게 마지막 것만 둔다
        base = " · ".join(p for p in (prev.note or "").split(" · ") if p and not p.startswith(COPIED_MARK))
        mark = f"{COPIED_MARK}(접수 행 {prev.id}, 스냅샷 {prev.snapshot_id})"
        row.note = f"{base} · {mark}" if base else mark
        out.append(row.id)
    if out:
        session.flush()
    return out


def pending_complexes(session: Session, snapshot_id: int) -> list[int]:
    """분류 복사 뒤에도 '접수 문구 미분류'로 남은 행의 단지(문구가 바뀌었거나 처음 본 문구) — 판정기 classify 가 필요하다.

    수집(collect)은 이 단지들을 재판정 대상에 넣는다: 미분류인 채 이전 판정을 복사해 publish 하면 접수 상태와 저장 범위가
    갈린다(N-C2 '변경 없는 날 P4 없이 publish')."""
    return sorted(
        set(
            session.scalars(
                select(IntakeStatus.complex_id).where(
                    IntakeStatus.snapshot_id == snapshot_id,
                    IntakeStatus.path.in_(INTAKE_PATHS),
                    IntakeStatus.reason == UNCLASSIFIED,
                )
            )
        )
    )
