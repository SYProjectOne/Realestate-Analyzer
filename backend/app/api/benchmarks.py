"""벤치마크 행 선택·표본·없음 사유 (계약 2026-10-09.6 — R3 재리뷰 N-M3·N-M4, D9-2, G1 요청 benchmark.snapshot_id).

- ``benchmarks_for(session, snapshot)``: 그 스냅샷(리비전)이 인용하는 벤치마크 행 — **API·파이프라인 점수 입력·보고서가 모두
  이 함수**(C-1·M-6, 계약 .8). ``benchmark.snapshot_id`` = 조립한 스냅샷. 조립분은 그 스냅샷 것(snapshot_id = sid)이 있으면
  그것, 없으면 (기준일, id) 순서로 sid 앞선 가장 최근 조립분만 — 미래 스냅샷 조립분은 보이지 않는다(같은 기준일의 새
  리비전은 바탕 리비전의 조립분을 본다). snapshot_id NULL 행: 사람·devseed 입력(머리표 없음)은 늘 포함, 0006 이전 자동 행
  (머리표 '[bm:')은 조립분이 없는 스냅샷에만(조립분과 겹치면 이중 집계 — minor 25).
- ``is_substitute(b)``: 지역 전체 표본을 생활권 대체로 복사한 행(D9-2) = ``benchmark.substitute`` 컬럼(계약 2026-10-09.7,
  0007 — note 문자열로 판별하지 않는다).
- ``own_sample_n``: 생활권 **자기** 표본 수 = 대체 행·분양권 제외(N-M4: 대체까지 세면 '표본 3 미만' 배지가 빠졌다).
- ``benchmark_absence(session, region_id, rows)``: 점수에 쓸 행(분양권 제외)이 0이면 사유 ``{code, reason}``, 아니면 None.
  not_collected(지역 실거래 없음 = 수집 전) · presale_only(분양권 사례만) · no_sample(생활권·지역 전체 표본 0).
  보고서(G4)도 같은 함수를 쓰면 화면과 사유가 갈리지 않는다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Benchmark, RtmsTrade, Snapshot

__all__ = [
    "ABSENCE_REASONS",
    "benchmark_absence",
    "benchmarks_for",
    "is_substitute",
    "own_sample_n",
]


ABSENCE_REASONS: Final[dict[str, str]] = {
    "not_collected": "실거래 수집 전",
    "presale_only": "분양권 거래 사례만 있음(점수 제외)",
    "no_sample": "입주 후 실거래가 있는 과거 분양 사례 없음(생활권·지역 전체 표본 0)",
}


def is_substitute(b: Benchmark) -> bool:
    return bool(b.substitute)


def benchmarks_for(session: Session, snapshot: Snapshot) -> list[Benchmark]:
    """스냅샷이 인용하는 벤치마크 행(id 순) — 모듈 설명."""
    rows = list(
        session.scalars(
            select(Benchmark).where(Benchmark.region_id == snapshot.region_id).order_by(Benchmark.id)
        )
    )
    built = {b.snapshot_id for b in rows if b.snapshot_id is not None}
    pick: int | None = None
    if snapshot.id in built:
        pick = snapshot.id
    elif built:
        asof = {
            sid: day
            for sid, day in session.execute(
                select(Snapshot.id, Snapshot.asof_date).where(Snapshot.id.in_(sorted(built)))
            )
        }
        earlier = [sid for sid in built if (asof.get(sid) or "", sid) < (snapshot.asof_date, snapshot.id)]
        if earlier:
            pick = max(earlier, key=lambda sid: (asof.get(sid) or "", sid))
    out: list[Benchmark] = []
    for b in rows:
        if b.snapshot_id is not None:
            if b.snapshot_id == pick:
                out.append(b)
        elif not _auto(b) or pick is None:
            # 사람·시드 행(머리표 없음)은 늘, 스냅샷 없는 옛 자동 행(0006 이전)은 조립분이 없는 스냅샷에만 — 둘이 겹치면
            # 같은 사례가 두 번 집계된다(C-1·minor 25)
            out.append(b)
    return out


def _auto(b: Benchmark) -> bool:
    """정규화(``normalize.benchmark``)가 만든 행(note 머리표 '[bm:')."""
    return bool(b.note) and str(b.note).startswith("[bm:")


def own_sample_n(rows: Iterable[Benchmark], living_area: str) -> int:
    return sum(1 for b in rows if b.living_area == living_area and not b.is_presale and not is_substitute(b))


def benchmark_absence(session: Session, region_id: int, rows: Sequence[Benchmark]) -> dict[str, Any] | None:
    """점수에 쓸 벤치마크(분양권 제외)가 없으면 사유(계약 BenchmarkAbsence), 있으면 None."""
    if any(not b.is_presale for b in rows):
        return None
    if rows:
        code = "presale_only"
    else:
        trades = session.scalar(
            select(func.count()).select_from(RtmsTrade).where(RtmsTrade.region_id == region_id)
        )
        code = "no_sample" if trades else "not_collected"
    return {"code": code, "reason": ABSENCE_REASONS[code]}
