"""분석: scenario, score_run, score_component, score_total, ladder, decision — RA §3, §6."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import (
    COMPONENT,
    HORIZON,
    JUDGMENT_STATUS,
    LABELS,
    OPTION_KEY,
    REQ_JUDGE,
    SCENARIO_CODE,
    in_check,
)

__all__ = ["Decision", "Ladder", "Scenario", "ScoreComponent", "ScoreRun", "ScoreTotal"]


class Scenario(Base):
    """상황 시나리오. 내장 5개(code base·A·B·C·D)는 0001이 시드한다.

    json 모양은 contracts/schemas/scenario.json.
    """

    __tablename__ = "scenario"
    __table_args__ = (CheckConstraint(in_check("code", SCENARIO_CODE), name="code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str | None] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    is_builtin: Mapped[bool] = mapped_column(Boolean, server_default=false())
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    weights: Mapped[dict[str, float]] = mapped_column(JSON)
    requirements: Mapped[dict[str, Any]] = mapped_column(JSON)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32))


class ScoreRun(Base):
    """점수 계산 1회. 한 run의 rerank 값은 rerank_judgment_seq 한 호출에서만(§6-5)."""

    __tablename__ = "score_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshot.id"), index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenario.id"))
    weights: Mapped[dict[str, float]] = mapped_column(JSON)
    rerank_judgment_seq: Mapped[int | None] = mapped_column(ForeignKey("judgment_log.seq"))
    prev_score_run_id: Mapped[int | None] = mapped_column(ForeignKey("score_run.id"))
    created_at: Mapped[str] = mapped_column(String(32))


class ScoreComponent(Base):
    """구성 점수 1개. formula_text가 툴팁에 그대로(빈 문자열 금지).

    Fact.prov = 'sc_<run>_<complex>_<component>'.
    """

    __tablename__ = "score_component"
    __table_args__ = (
        UniqueConstraint("score_run_id", "complex_id", "component"),
        CheckConstraint(in_check("component", COMPONENT), name="component"),
        CheckConstraint(in_check("label", LABELS), name="label"),
        CheckConstraint("formula_text <> ''", name="formula_text_not_empty"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    score_run_id: Mapped[int] = mapped_column(ForeignKey("score_run.id"))
    complex_id: Mapped[int] = mapped_column(ForeignKey("complex.id"))
    component: Mapped[str] = mapped_column(String(16))
    raw_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    score_0_10: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    formula_text: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str | None] = mapped_column(String(120))
    delta: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    flags: Mapped[list[str]] = mapped_column(JSON)


class ScoreTotal(Base):
    """종합 점수(반올림 전 원값). 동점은 같은 rank, tie_group 번호. unstable = 민감도에서 TOP 5 구성 변동."""

    __tablename__ = "score_total"
    __table_args__ = (UniqueConstraint("score_run_id", "complex_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    score_run_id: Mapped[int] = mapped_column(ForeignKey("score_run.id"))
    complex_id: Mapped[int] = mapped_column(ForeignKey("complex.id"))
    total: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    rank: Mapped[int | None] = mapped_column(Integer)
    tie_group: Mapped[int | None] = mapped_column(Integer)
    unstable: Mapped[bool] = mapped_column(Boolean, server_default=false())


class Ladder(Base):
    """사다리(noul 결과) horizon 3종. (snapshot_id, complex_id, horizon) 유일."""

    __tablename__ = "ladder"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "complex_id", "horizon"),
        CheckConstraint(in_check("horizon", HORIZON), name="horizon"),
        CheckConstraint(in_check("status", JUDGMENT_STATUS), name="status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshot.id"))
    complex_id: Mapped[int] = mapped_column(ForeignKey("complex.id"))
    horizon: Mapped[str] = mapped_column(String(16))
    target_ym: Mapped[str] = mapped_column(String(7))
    months_from_asof: Mapped[int | None] = mapped_column(Integer)
    p5: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    p10: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    p20: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    p_flat: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    verdicts: Mapped[dict[str, Any]] = mapped_column(JSON)
    annualized: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    judgment_seq: Mapped[int | None] = mapped_column(ForeignKey("judgment_log.seq"))
    proposition_text: Mapped[str | None] = mapped_column(Text)


class Decision(Base):
    """decide 후보 1행.

    req_*_pre = {status: 충족|미충족|미입력|확인 불가, evidence},
    req_*_judge = supported|contradicted|unknown.
    mismatch = 사전 계산과 판정기 불일치 → '증거와 상이' 배지.
    escape hatch 행은 complex_id NULL, option_key로 구분.
    """

    __tablename__ = "decision"
    __table_args__ = (
        UniqueConstraint("score_run_id", "scenario_id", "option_key", "complex_id"),
        CheckConstraint(in_check("option_key", OPTION_KEY), name="option_key"),
        CheckConstraint(in_check("req_access_judge", REQ_JUDGE), name="req_access_judge"),
        CheckConstraint(in_check("req_regulation_judge", REQ_JUDGE), name="req_regulation_judge"),
        CheckConstraint(in_check("req_funds_judge", REQ_JUDGE), name="req_funds_judge"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    score_run_id: Mapped[int] = mapped_column(ForeignKey("score_run.id"), index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenario.id"))
    complex_id: Mapped[int | None] = mapped_column(ForeignKey("complex.id"))
    option_key: Mapped[str] = mapped_column(String(16))
    prob: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    chosen: Mapped[bool] = mapped_column(Boolean, server_default=false())
    tie: Mapped[bool] = mapped_column(Boolean, server_default=false())
    req_access_pre: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    req_regulation_pre: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    req_funds_pre: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    req_access_judge: Mapped[str | None] = mapped_column(String(16))
    req_regulation_judge: Mapped[str | None] = mapped_column(String(16))
    req_funds_judge: Mapped[str | None] = mapped_column(String(16))
    mismatch: Mapped[bool] = mapped_column(Boolean, server_default=false())
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    warnings: Mapped[list[str]] = mapped_column(JSON)
    judgment_seq: Mapped[int | None] = mapped_column(ForeignKey("judgment_log.seq"))
