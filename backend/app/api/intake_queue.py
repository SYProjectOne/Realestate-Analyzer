"""G7 접수 확인 대기열 (계약 2026-10-09.19, DECISIONS D26-2) — ``GET /ops/intake-queue``.

한 스냅샷에서 단지마다 표시 접수 행(``analysis.scope.pick_intake`` — human_check > official_popup > headless_shot)이
'확인 불가'·'미정'인 단지를 사유별로 묶는다. **저장된 행만 읽는다** — 판정기 호출·DB 쓰기 없음(AGENTS 규칙 4).

묶음은 저장된 사유 문자열·http_status 로 정한다(데이터 기준 — ``queue_key``). 수집·판정 쪽이 사유를 새로 만들어도
(R7-SITE: '판정 대상 아님(…)'·TLS 브라우저 재시도·OCR 등) 이 모듈을 고치지 않는다: 머리말이 맞으면 그 분류, 아니면
other('기타')에 그 사유 이름의 묶음이 생긴다. 사유 머리말 비교·낱말 자르기는 문자열 규칙이지 판단이 아니다(규칙 3).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.scope import pick_intake
from app.models import Complex, HumanCheck, IntakeStatus, RawDocument, Snapshot

__all__ = ["CATEGORY_ORDER", "QUEUE_STATUSES", "build_queue", "empty_queue", "queue_key"]

QUEUE_STATUSES: Final = ("확인 불가", "미정")
CATEGORY_ORDER: Final = (
    "collect_failed",
    "identity",
    "no_phrase",
    "unresolved",
    "not_judged",
    "other",
    "undecided",
)

# 수집 실패 낱말(raw_document.error_text 값 목록 — 계약 .2 · core.http ErrorKind). 대소문자 무시, 표시는 원래 표기
_FETCH_WORDS: Final = frozenset(
    {
        "dns",
        "timeout",
        "connect",
        "tls",
        "network",
        "robots",
        "robots.txt",
        "invalid_url",
        "render",
        "blocked_host",
        "blocked_by_robots",
    }
)
_FETCH_PREFIXES_KO: Final = ("접속 실패", "수집 실패", "타임아웃", "원문 없음")
# 판정 쪽 사유 머리말 → 분류(묶음 이름 = 저장 사유 그대로)
_JUDGE_PREFIXES: Final[tuple[tuple[str, str], ...]] = (
    ("공식 홈페이지 동일성 미확인", "identity"),
    ("공식 홈페이지가 다른 단지", "identity"),
    ("문구로 판단 불가", "no_phrase"),
    ("접수 문구 없음", "no_phrase"),
    ("판정 미해결", "unresolved"),
    ("접수 문구 미분류", "unresolved"),
    ("판정 대상 아님", "not_judged"),
)
_HEAD_WORD = re.compile(r"^[A-Za-z_][A-Za-z_.]*")
_JL = re.compile(r"\bjl_(\d+)\b")
_REASON_MAX: Final = 120


def shown_reason(status: str, reason: str | None, http_status: int | None) -> str | None:
    """접수 행 표시 사유 — ``views.intake_view`` 와 같은 규칙('확인 불가'인데 사유가 비면 http_status 또는 '사유 미기재')."""
    if status == "확인 불가" and not reason:
        return str(http_status) if http_status else "사유 미기재"
    return reason


def queue_key(status: str, reason: str | None, http_status: int | None) -> tuple[str, str]:
    """(category, 묶음 이름). 계약 ``intake_queue.json`` 설명의 (1)~(5) 규칙."""
    text = (shown_reason(status, reason, http_status) or "").strip()
    if status == "미정":
        return "undecided", (text or "미정")[:_REASON_MAX]
    if http_status is not None and not 200 <= http_status < 300:
        return "collect_failed", (text if text.isdigit() else str(http_status))[:_REASON_MAX]
    if text.isdigit():
        return "collect_failed", text
    head = _HEAD_WORD.match(text)
    if head is not None and head.group(0).lower() in _FETCH_WORDS:
        return "collect_failed", head.group(0)
    for prefix in _FETCH_PREFIXES_KO:
        if text.startswith(prefix):
            return "collect_failed", prefix
    for prefix, category in _JUDGE_PREFIXES:
        if text.startswith(prefix):
            return category, text[:_REASON_MAX]
    return "other", (text or "사유 미기재")[:_REASON_MAX]


def empty_queue(region_id: int | None) -> dict[str, Any]:
    return {
        "region_id": region_id,
        "snapshot_id": None,
        "asof_date": None,
        "revision": None,
        "snapshot_status": None,
        "total": 0,
        "groups": [],
    }


def _judgment_ref(note: str | None) -> str | None:
    found = _JL.findall(note or "")
    return f"jl_{found[-1]}" if found else None


def _screenshots(session: Session, rows: Sequence[IntakeStatus]) -> dict[int, int]:
    """접수 행 id → 스크린샷 원문 id. 접수 행 원문이 그 경로면 그 행, 아니면 같은 경로의 원문(같은 단지 우선, id 큰 것).
    맞는 원문이 없으면 없음(지어내지 않는다)."""
    wanted = {r.screenshot_path for r in rows if r.screenshot_path}
    if not wanted:
        return {}
    docs = list(
        session.execute(
            select(RawDocument.id, RawDocument.path, RawDocument.complex_id).where(
                RawDocument.path.in_(wanted)
            )
        )
    )
    out: dict[int, int] = {}
    for r in rows:
        if not r.screenshot_path:
            continue
        same = [d for d in docs if d.path == r.screenshot_path]
        own = next((d for d in same if d.id == r.raw_document_id), None)
        if own is None and same:
            own = max(same, key=lambda d: (d.complex_id == r.complex_id, d.id))
        if own is not None:
            out[r.id] = int(own.id)
    return out


def _pending_checks(
    session: Session, snap: Snapshot, complex_ids: Iterable[int], rows: Sequence[IntakeStatus]
) -> dict[int, dict[str, Any]]:
    """단지 → 이 스냅샷을 만든 뒤 들어왔고 아직 이 스냅샷에 없는 접수 사람 확인(마지막 입력).

    반영 = 같은 단지·같은 확인 시각·같은 값의 human_check 접수 행이 이 스냅샷에 있다."""
    ids = sorted(set(complex_ids))
    if not ids or not snap.created_at:
        return {}
    reflected = {(r.complex_id, r.checked_at, r.status) for r in rows if r.path == "human_check"}
    out: dict[int, dict[str, Any]] = {}
    for hc in session.scalars(
        select(HumanCheck)
        .where(
            HumanCheck.field == "intake_status",
            HumanCheck.complex_id.in_(ids),
            HumanCheck.created_at.is_not(None),
            HumanCheck.created_at > snap.created_at,
        )
        .order_by(HumanCheck.id)
    ):
        if (hc.complex_id, hc.checked_at, hc.value_text) in reflected:
            out.pop(hc.complex_id, None)
            continue
        out[hc.complex_id] = {
            "id": hc.id,
            "value_text": hc.value_text,
            "checked_at": hc.checked_at,
            "created_at": hc.created_at,
        }
    return out


def build_queue(session: Session, snap: Snapshot) -> dict[str, Any]:
    """스냅샷 하나의 대기열(계약 ``IntakeQueue``)."""
    rows = list(
        session.scalars(
            select(IntakeStatus).where(IntakeStatus.snapshot_id == snap.id).order_by(IntakeStatus.id)
        )
    )
    by_complex: dict[int, list[IntakeStatus]] = defaultdict(list)
    for r in rows:
        by_complex[r.complex_id].append(r)
    shown: list[IntakeStatus] = []
    for cid in sorted(by_complex):
        picked = pick_intake(by_complex[cid])
        if picked is not None and picked.status in QUEUE_STATUSES:
            shown.append(picked)
    names = {
        int(cid): str(name)
        for cid, name in session.execute(
            select(Complex.id, Complex.name).where(Complex.id.in_([r.complex_id for r in shown]))
        )
    }
    shots = _screenshots(session, shown)
    pending = _pending_checks(session, snap, (r.complex_id for r in shown), rows)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in shown:
        groups[queue_key(r.status, r.reason, r.http_status)].append(
            {
                "intake_id": r.id,
                "complex_id": r.complex_id,
                "complex_name": names.get(r.complex_id, ""),
                "status": r.status,
                "reason": shown_reason(r.status, r.reason, r.http_status),
                "path": r.path,
                "evidence_url": r.evidence_url,
                "raw_document_id": r.raw_document_id,
                "screenshot_path": r.screenshot_path,
                "screenshot_raw_document_id": shots.get(r.id),
                "checked_at": r.checked_at,
                "http_status": r.http_status,
                "note": r.note,
                "judgment_ref": _judgment_ref(r.note),
                "human_check_pending": pending.get(r.complex_id),
            }
        )
    ordered = sorted(groups.items(), key=lambda kv: (CATEGORY_ORDER.index(kv[0][0]), -len(kv[1]), kv[0][1]))
    out: list[dict[str, Any]] = [
        {
            "category": cat,
            "reason": reason,
            "count": len(items),
            "items": sorted(items, key=lambda it: (str(it["complex_name"]), int(it["intake_id"]))),
        }
        for (cat, reason), items in ordered
    ]
    return {
        "region_id": snap.region_id,
        "snapshot_id": snap.id,
        "asof_date": snap.asof_date,
        "revision": snap.revision,
        "snapshot_status": snap.status,
        "total": sum(len(items) for _key, items in ordered),
        "groups": out,
    }
