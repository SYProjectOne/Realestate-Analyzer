"""저장본 계산 한 번 안의 적재 메모(D14-5 성능 — 1000 단지 × 시나리오 5 발행 잡 15초).

``snapshot_view.compute`` 가 ``active()`` 로 켠 동안만 동작한다: 같은 계산 안에서 같은 인자로 다시 부르는 적재
(``views.load_bundles``·``views.provenance_for``·``views.judgment_days``)는 첫 결과를 다시 쓴다. 계산 세션은 읽기 전용이고
한 시점의 값만 보므로(``snapshot_view._read_session``) 같은 인자 = 같은 결과다. 켜지 않은 요청 경로(실시간 GET)는 그대로.

판단 없음 — 같은 읽기의 반복을 줄일 뿐이다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

__all__ = ["active", "cached", "store"]


_MEMO: ContextVar[dict[Hashable, Any] | None] = ContextVar("api_memo", default=None)


@contextmanager
def active() -> Iterator[dict[Hashable, Any]]:
    box: dict[Hashable, Any] = {}
    token = _MEMO.set(box)
    try:
        yield box
    finally:
        _MEMO.reset(token)


def store() -> dict[Hashable, Any] | None:
    """켜져 있으면 메모 dict, 아니면 None."""
    return _MEMO.get()


def cached[T](key: Hashable, make: Callable[[], T]) -> T:
    """켜져 있으면 ``key`` 의 첫 결과, 아니면 매번 ``make()``."""
    box = _MEMO.get()
    if box is None:
        return make()
    if key in box:
        got: T = box[key]
        return got
    val = make()
    box[key] = val
    return val
