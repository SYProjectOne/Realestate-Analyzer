"""R4 3차 재시험 N11(minor, D22-4) — 공식 홈페이지 동일성 판정이 review·unclear 면 사유는 '공식 홈페이지 동일성 미확인'.

R4 3차: 동일성 classify 가 same_complex·review(11) · unclear·review(9)인 20행도 '확인 불가(공식 홈페이지가 다른 단지)'로 보였다
(판정기 노트는 'same_complex·review'). D21-5 문언대로 접수 근거로 쓰지 않는 것은 맞지만 사유가 사실과 다르게 읽힌다.
D22-4: '다른 단지'는 판정기가 auto 로 아니라고(other_complex) 한 경우만이다. 판단은 판정기만(규칙 3) — 가짜 판정기 응답 모양만 바꾼다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.scheduler.context import SchedulerContext

from .conftest import SynthJev
from .test_core8_n6_site_identity import IdentityJev, _row, _run, other_site_ctx  # noqa: F401 (fixture)

SITE_OTHER = "공식 홈페이지가 다른 단지"
SITE_UNCONFIRMED = "공식 홈페이지 동일성 미확인"


@pytest.fixture
def jev() -> SynthJev:  # make_ctx 가 이 판정기를 쓴다
    return IdentityJev(identity="other_complex")


@pytest.mark.parametrize(
    ("identity", "decision", "reason"),
    [
        ("other_complex", "auto", SITE_OTHER),
        ("other_complex", "review", SITE_UNCONFIRMED),
        ("same_complex", "review", SITE_UNCONFIRMED),
        ("unclear", "auto", SITE_UNCONFIRMED),
        ("unclear", "review", SITE_UNCONFIRMED),
    ],
)
def test_identity_reason_follows_judge_answer(
    other_site_ctx: SchedulerContext,  # noqa: F811 (core8 fixture)
    factory: sessionmaker[Session],
    seeded: int,
    jev: SynthJev,
    identity: str,
    decision: str,
    reason: str,
) -> None:
    assert isinstance(jev, IdentityJev)
    jev.identity, jev.identity_decision = identity, decision
    sid = _run(other_site_ctx)
    row = _row(factory, sid)
    assert (row.status, row.reason) == ("확인 불가", reason), (identity, decision, row.reason, row.note)
    assert row.note and f"{identity}·{decision}" in row.note, (
        "판정 표식에 동일성 판정 결과(클래스·결정)를 남긴다"
    )
