"""판정 파이프라인 P1~P9 + 점수 (meta §2-1, RA §5 WP7, §6). rejudge·region.bootstrap 의 본체.

순서(스냅샷 1개)
1. 사실 읽기(``inputs.load_facts``) → 재판정 대상 = complex_ids(없으면 지역 단지 전부)
2. P1 screen → P2 extract → P3 audit: 대상 단지 공고문에서 파서가 못 읽은 필드(normalize ``needs_extract``)만.
   결과는 ``normalize.judged.apply_extracted`` 로 사실 테이블·출처 행에 반영(auto+감사 통과 = 확인됨, 감사 전 = 추정,
   review·감사 flagged = 미반영)
3. 접수 상태 classify: 이 스냅샷의 '접수 문구 미분류' 행(공식 홈페이지 official_popup·headless_shot) 중 문구 해시가 직전
   분류 행과 같은 것은 분류 복사(``intake.carry_classification``, D10-2 — 호출 없음), 나머지를 원문 DOM 텍스트의
   접수 문구로 배치 classify(``judge.pipeline.p4_classify_intake``) → 가능/미정/불가/확인 불가. 미해결 = 확인 불가(판정 미해결).
   그다음 표시 접수 상태(``analysis.scope.pick_intake``)가 이전 스냅샷과 다르면 change_event(intake_status, critical,
   triggers_rejudge) + 그 단지를 이번 재판정 대상에 넣고 웹훅 알림(DECISIONS D9-3). 같은 변경 이벤트가 이미 있으면
   (사람 확인 입력 API·이전 실행) 다시 만들지 않는다.
4. P4 classify: 포함/제외 7클래스(지역 단지 전부·범위 경계 제외, 64개씩 배치 1회) · 호재: 후보(뉴스는 수집 때 P1 screen
   통과분만, ``assemble``) → 단계 classify('호재 아님'이면 후보 폐기·기록) → 종류(kind) classify(D10-6, ``_p4_catalysts``)
5. P5 compare: 대상 단지 출처 상충 중 같은 순위 1차·1차(needs_compare)만 → field_provenance.compare_judgment_seq.
   contradicts 면 ``normalize.judged.apply_compare``(1차 공고 자료 채택·병기)
6. P6 noul: 대상 단지 중 ``analysis.scope.runs_ladder``(판정 대상만 — 참고·보류·미해결·제외는 사다리 미실행, D9-1)의
   사다리 3시점 → ladder. 대상이 아닌 단지는 이전 스냅샷 사다리를 복사. 저장 판정 범위 = 같은 판정 범위(``stored_scope``)
7. P7 rerank: 후보군(판정 대상·참고·보류, ``analysis.scope.in_rerank``) 1회(§6-5 고정 앵커) — 같은 후보·같은 카드면 캐시.
   이전 run 앵커(delta_rerank)는 judgment_log 캐시 행에서만 읽는다(판정기 호출 없음, R3 minor 32)
8. 점수: 시나리오마다 ``analysis.score.run_detailed`` (ScoreInputs 는 DB 에서 조립, 2026-10-09.2 필드 채움).
   score_total.judge_scope = 이 실행의 판정 범위(계약 2026-10-09.3)
9. P8 decide: 시나리오마다 상위 후보 ≤6(policy.include_wait_new 면 ≤5 + 가상 후보 '모집공고 대기', 계약 .5) + 요건 사전 계산(``analysis.scenarios``) → decision.
   chosen·tie 는 ``analysis.score.decide_outcome`` 이 원본. 입력 조립은 ``payloads.decide_plan``(미리보기 빌더와 공용)
10. P9 verify: 대상 단지의 사실 문장을 원자 주장으로 나눠 검증 → claim. 대상이 아닌 단지는 이전 주장을 복사
11. score_run/component/total/decision/claim 저장 → snapshot.status='ready' (publish 는 snapshot.publish 잡)

판정 호출은 전부 ``ctx.adapter()``(= ``judge.get_adapter()``) + ``judge.pipeline`` 단계 함수로만 한다.
``JudgeUnavailable`` → 그때까지 쓴 판정 행은 두고 degraded(점수 미계산, T18).
판정기가 죽어 있어도 판정이 전부 캐시면 끝까지 돈다 — 버전 비교는 이번 실행에서 판정기에 **실제로 간** 호출의 봉투 버전만
쓰고(서버 재호출 없음), 실제 호출이 없으면 하지 않는다(R3 재리뷰 N-M8).
"""

# ruff: noqa: E501

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.scenarios import RequirementPrecalculator
from app.analysis.scope import runs_ladder
from app.core.contracts_gen import Claim as ClaimDTO
from app.core.contracts_gen import (
    JudgmentEnvelope,
    RerankAnchor,
    RerankItem,
    RerankPrev,
)
from app.core.contracts_gen import Scenario as ScenarioDTO
from app.core.logging import get_logger
from app.core.protocols import JudgePayload, JudgeTool, JudgeUnavailable
from app.core.redact import redact_text
from app.core.settings import get_settings
from app.judge import pipeline as jp
from app.judge.base import JudgeCaller
from app.judge.claims import with_josa
from app.judge.payloads import (
    CLASSIFY_BATCH_MAX,
    AuditRecord,
    ExtractField,
)
from app.models import (
    Catalyst,
    ChangeEvent,
    Complex,
    ComplexType,
    FieldProvenance,
    IntakeStatus,
    JudgmentLog,
    PaymentTerms,
    RawDocument,
    Region,
    Scenario,
    ScoreRun,
    Snapshot,
)
from app.models.enums import INCLUSION_CLASS
from app.normalize.extract_request import FIELD_DESCRIPTIONS, ExtractRequest, build_extract_requests
from app.normalize.judged import COMPARE_RESOLVED, AuditMark, ExtractedValue, apply_compare, apply_extracted
from app.normalize.store import parser_for, raw_dto
from app.scheduler import persist
from app.scheduler.degraded import clear_degraded, mark_degraded
from app.scheduler.inputs import ComplexFacts, evidence_card, load_facts
from app.scheduler.intake import (
    CLASSIFIED_MARK,
    INTAKE_PATHS,
    NO_TEXT,
    UNCLASSIFIED,
    carry_classification,
    intake_change_events,
    intake_text,
    reset_stale_classification,
)
from app.scheduler.judge_version import last_logged, record_version_change
from app.scheduler.payloads import (
    _anchor_from,
    decide_plan,
    rerank_pool,
    score_base,
    stored_scope,
    wait_new_evidence,
)
from app.scheduler.snapshots import contradicted_count, previous, snapshot_dto, writable

if TYPE_CHECKING:
    from app.scheduler.context import SchedulerContext

__all__ = ["CountingCaller", "PipelineResult", "load_scenarios", "run_pipeline"]

log = get_logger("app.scheduler.pipeline")

_SLUG: Final = re.compile(r"[^a-z0-9_-]")
# 판정기 extract 후보 패턴(JavaScript 정규식). 값을 고르는 것은 판정기다 — 여기서는 후보 위치만 넓게 준다.
_AMOUNT = r"[0-9][0-9,]*\s*(?:원|만\s*원|천\s*원)"
_PCT = r"[0-9]+(?:\.[0-9]+)?\s*%"
_DATE = r"20[0-9]{2}\s*[.\-년]\s*[0-9]{1,2}(?:\s*[.\-월]\s*[0-9]{1,2}\s*일?)?"
_MONTHS = r"[0-9]+\s*(?:개월|년)"
_FIELD_PATTERNS: Final = {
    "max_price_won": _AMOUNT,
    "floor_sample_price_won": _AMOUNT,
    "balcony_won": _AMOUNT,
    "options_required_won": _AMOUNT,
    "down_payment_pct": _PCT,
    "interim_pct": _PCT,
    "balance_pct": _PCT,
    "interim_schedule": _DATE,
    "effective_from": _DATE,
    "resale_months": _MONTHS,
    "residency_months": _MONTHS,
    "rewin_restriction_years": _MONTHS,
    "move_in_ym": _DATE,
    "units_total": r"[0-9][0-9,]*\s*세대",
}
_TEXT_SOURCES: Final = ("notice_pdf",)
_INTAKE_PATHS: Final = INTAKE_PATHS
EXTRACT_FIELDS_MAX: Final = 32
"""판정기 extract 한 호출의 필드 상한 — 넘으면 나눠 보낸다(잘라 버리지 않는다, R3 C3)."""


# ---------------------------------------------------------------- 호출 계수


class CountingCaller:
    """판정기 호출 계수(실제 호출 vs 캐시). 판정 자체는 그대로 넘긴다.

    ``before_call``: 호출 전에 파이프라인 세션을 commit 한다 — 어댑터는 호출마다 자기 세션으로 judgment_log 를
    쓰므로, 파이프라인 세션이 열린 트랜잭션(SQLite WAL 의 낡은 읽기 스냅샷)을 들고 있으면 쓰기가 막힌다.
    """

    def __init__(self, inner: JudgeCaller, before_call: Callable[[], None] | None = None) -> None:
        self.inner = inner
        self._before = before_call
        self.calls = 0  # cached=False 이고 blocked 가 아닌 호출(판정기로 간 호출)
        self.cached = 0
        self.blocked = 0
        self.by_tool: Counter[str] = Counter()
        self.cached_by_tool: Counter[str] = Counter()  # 도구별 캐시 재생(R3 m23 — /ops/judgments cached_hits)
        self.statuses: Counter[str] = Counter()
        self.seen_version: str | None = None  # 마지막 봉투의 adapter_version(캐시 재생 포함)
        self.live_version: str | None = None  # 판정기에 실제로 간 호출의 봉투 버전(버전 변경 감지용)

    @property
    def adapter_version(self) -> str:
        return self.inner.adapter_version

    def known_version(self) -> str | None:
        """서버에 묻지 않고 아는 버전: 이번 실행에서 본 봉투 버전, 없으면 어댑터에 물어 보되 판정기가 죽어 있으면 None
        (판정기 다운 + 전부 캐시에서 예외를 내지 않는다, N-M8)."""
        if self.seen_version:
            return self.seen_version
        try:
            return self.inner.adapter_version
        except JudgeUnavailable:
            return None

    def call(
        self,
        tool: JudgeTool,
        payload: JudgePayload,
        purpose: str,
        *,
        snapshot_id: int | None = None,
        complex_id: int | None = None,
    ) -> JudgmentEnvelope:
        if self._before is not None:
            self._before()
        env = self.inner.call(tool, payload, purpose, snapshot_id=snapshot_id, complex_id=complex_id)
        self.statuses[env.status] += 1
        if env.adapter_version:
            self.seen_version = env.adapter_version
        if env.cached:
            self.cached += 1
            self.cached_by_tool[tool] += 1
        elif env.status == "blocked":
            self.blocked += 1
        else:
            self.calls += 1
            self.by_tool[tool] += 1
            if env.adapter_version and env.status != "error":
                self.live_version = env.adapter_version
        return env


@dataclass
class PipelineResult:
    snapshot_id: int
    targets: list[int]
    degraded: bool = False
    error: str | None = None
    judge_calls: int = 0
    cached: int = 0
    blocked: int = 0
    by_tool: dict[str, int] = field(default_factory=dict)
    cached_by_tool: dict[str, int] = field(default_factory=dict)
    statuses: dict[str, int] = field(default_factory=dict)
    ladders: int = 0
    score_run_ids: list[int] = field(default_factory=list)
    decisions: int = 0
    claims: int = 0
    contradicted: int = 0
    extract_applied: int = 0
    extract_flagged: int = 0
    intake_classified: int = 0
    compare_adopted: int = 0
    intake_events: list[int] = field(default_factory=list)
    intake_carried: int = 0
    catalysts_discarded: list[dict[str, Any]] = field(default_factory=list)
    notified_event_ids: list[int] = field(default_factory=list)
    carried: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    version_event_id: int | None = None

    def absorb(self, c: CountingCaller) -> None:
        self.judge_calls, self.cached, self.blocked = c.calls, c.cached, c.blocked
        self.by_tool = dict(c.by_tool)
        self.cached_by_tool = dict(c.cached_by_tool)
        self.statuses = dict(c.statuses)

    def stats(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "targets": len(self.targets),
            "degraded": self.degraded,
            "judge_calls": self.judge_calls,
            "cached": self.cached,
            "blocked": self.blocked,
            "by_tool": self.by_tool,
            "cached_by_tool": self.cached_by_tool,
            "statuses": self.statuses,
            "ladders": self.ladders,
            "score_runs": len(self.score_run_ids),
            "decisions": self.decisions,
            "claims": self.claims,
            "contradicted": self.contradicted,
            "extract_applied": self.extract_applied,
            "extract_flagged": self.extract_flagged,
            "intake_classified": self.intake_classified,
            "compare_adopted": self.compare_adopted,
            "intake_events": self.intake_events,
            "intake_classification_carried": self.intake_carried,
            "catalysts_discarded": self.catalysts_discarded,
            "notified_event_ids": self.notified_event_ids,
            "carried": self.carried,
            "skipped": self.skipped,
            "version_event_id": self.version_event_id,
            **({"error": self.error} if self.error else {}),
        }


# ---------------------------------------------------------------- 시나리오


def load_scenarios(session: Session, scenario_id: int | None = None) -> list[ScenarioDTO]:
    stmt = select(Scenario).order_by(Scenario.id)
    if scenario_id is not None:
        stmt = stmt.where(Scenario.id == scenario_id)
    return [
        ScenarioDTO.model_validate(
            {
                "id": s.id,
                "code": s.code,
                "name": s.name,
                "is_builtin": bool(s.is_builtin),
                "params": s.params,
                "weights": s.weights,
                "requirements": s.requirements,
                "policy": s.policy,
                "created_at": s.created_at,
            }
        )
        for s in session.scalars(stmt)
    ]


# ---------------------------------------------------------------- P1~P3


def _slug(name: str) -> str:
    s = _SLUG.sub("_", name.lower())
    return s if s[:1].isalpha() else f"f_{s}"


def _p1_p3(
    session: Session,
    caller: CountingCaller,
    snap: Snapshot,
    targets: Sequence[int],
    res: PipelineResult,
    seq: persist.SeqResolver,
) -> None:
    """대상 단지 공고문에서 파서가 못 읽은 필드만 screen → extract → audit → 반영(normalize.judged).

    extract decision=auto 필드만 audit 에 보내고, audit 결과(통과·flagged)와 함께 ``apply_extracted`` 로 넘긴다.
    판정기를 부르는 것은 여기(judge.pipeline 단계 함수), 사실·출처 행 쓰기는 normalize(WP2)다.
    """
    if not targets:
        return
    docs = session.scalars(
        select(RawDocument)
        .where(
            RawDocument.complex_id.in_(list(targets)),
            RawDocument.source_kind.in_(_TEXT_SOURCES),
            RawDocument.path.is_not(None),
        )
        .order_by(RawDocument.id)
    )
    n_req = 0
    for doc in docs:
        parser = parser_for(doc.source_kind)
        if parser is None:
            continue
        try:
            cands = parser.parse(raw_dto(doc))
        except Exception as exc:  # 원문 파일 없음 등 — 파싱 실패도 기록
            res.skipped[f"parse:rd{doc.id}"] = type(exc).__name__
            continue
        for i, whole in enumerate(build_extract_requests([c for c in cands if c.needs_extract])):
            if not whole.text.strip() or not whole.fields:
                continue
            # 필드가 32개를 넘으면 나눠 보낸다(잘라 버리면 넘친 OCR 값이 판정 없이 남는다, R3 C3). 첫 조각은 예전 tag 그대로
            for k in range(0, len(whole.fields), EXTRACT_FIELDS_MAX):
                req = whole if len(whole.fields) <= EXTRACT_FIELDS_MAX else _part(whole, k)
                tag = f"rd{doc.id}:{i}" + (f":{k // EXTRACT_FIELDS_MAX}" if k else "")
                n_req += 1
                _extract_one(session, caller, snap, doc.complex_id, req, tag, res, seq)
    if n_req:
        res.carried["extract_requests"] = n_req


def _part(req: ExtractRequest, start: int) -> ExtractRequest:
    """ExtractRequest 의 필드 조각(같은 원문·같은 후보)."""
    return replace(req, fields=list(req.fields[start : start + EXTRACT_FIELDS_MAX]))


def _extract_one(
    session: Session,
    caller: CountingCaller,
    snap: Snapshot,
    cid: int | None,
    req: ExtractRequest,
    tag: str,
    res: PipelineResult,
    seq: persist.SeqResolver,
) -> None:
    """요청 1개(필드 ≤32): screen → extract → audit → 반영. screen 거부·extract 실패면 반영 없음 — OCR 값은 chosen 출처가
    OCR 판독으로 남아 점수 입력에서 null(``inputs.ocr_pending_fields``, R3 C3)."""
    screen = jp.p1_screen(
        caller, req.text, task="청약 공고문 수치 추출 전 입력 검사", purpose=f"screen:extract:{tag}",
        snapshot_id=snap.id, complex_id=cid,
    )  # fmt: skip
    if not screen.usable:
        res.skipped[f"screen:{tag}"] = (
            f"screen {screen.verdict or screen.envelope.status} — OCR 값 점수 입력 제외"
        )
        return
    fields = [
        ExtractField(
            id=_slug(f),
            pattern=_FIELD_PATTERNS.get(f, r"[0-9][0-9,.]*"),
            description=FIELD_DESCRIPTIONS.get(f, f),
        )
        for f in req.fields[:EXTRACT_FIELDS_MAX]
    ]
    env = jp.p2_extract(
        caller, req.text, fields, purpose=f"extract:{tag}", snapshot_id=snap.id, complex_id=cid
    )
    by_slug = {_slug(f): f for f in req.fields}
    values = [
        ExtractedValue(by_slug[str(f.get("name"))], f.get("value_text"), f.get("decision"))
        for f in (env.result or {}).get("fields", [])
        if str(f.get("name")) in by_slug
    ]
    got = [
        f
        for f in (env.result or {}).get("fields", [])
        if f.get("decision") == "auto" and f.get("value_text") and str(f.get("name")) in by_slug
    ]
    if env.status != "ok" or not got:
        if env.status == "ok" and values:  # review 필드만 — 반영 없이 기록(skipped)
            apply_extracted(session, req, values, judgment_seq=seq(env.judgment_seq), snapshot_id=snap.id)
        return
    desc = {_slug(f): FIELD_DESCRIPTIONS.get(f, f) for f in req.fields}
    records = [
        AuditRecord(
            id=str(f["name"]),
            request=desc.get(str(f["name"]), str(f["name"])),
            value=str(f["value_text"]),
        )
        for f in got[:EXTRACT_FIELDS_MAX]
    ]
    audit_env = jp.p3_audit(
        caller, req.text, records, purpose=f"audit:{tag}", snapshot_id=snap.id, complex_id=cid
    )
    marks: dict[str, AuditMark] | None = None
    if audit_env.status == "ok":  # review(미해결 감사)는 감사 없음으로 본다 → 추정
        marks = {
            by_slug[str(it.get("field"))]: AuditMark(bool(it.get("flagged")), it.get("p_wrong"))
            for it in (audit_env.result or {}).get("items", [])
            if str(it.get("field")) in by_slug
        }
    applied = apply_extracted(
        session,
        req,
        values,
        judgment_seq=seq(env.judgment_seq),
        audit=marks,
        audit_seq=seq(audit_env.judgment_seq),
        snapshot_id=snap.id,
    )
    res.extract_applied += len(applied.applied)
    res.extract_flagged += len(applied.flagged)
    session.commit()


# ---------------------------------------------------------------- P4


def _inclusion_text(f: ComplexFacts) -> str:
    cx = f.fact_row
    parts = [
        f"단지명: {cx.name}",
        f"사업주체(시행): {cx.developer}" if cx.developer else "",
        f"신탁: {cx.trustee}" if cx.trustee else "",
        f"시공: {cx.builder}" if cx.builder else "",
        f"주택 구분: {cx.housing_type}" if cx.housing_type else "",
        f"공급위치: {cx.address}" if cx.address else "",
        f"공급 세대: {cx.units_total}세대" if cx.units_total else "",
        f"오피스텔: {cx.officetel_units}실" if cx.officetel_units else "",
    ]
    return "\n".join(p for p in parts if p)


def _intake_text(session: Session, row: IntakeStatus) -> str:
    """접수 상태 행 → classify 항목 텍스트(``intake.intake_text`` — 분류 복사의 문구 해시와 같은 함수)."""
    return intake_text(session, row)


def _p4_intake(
    session: Session, caller: CountingCaller, snap: Snapshot, seq: persist.SeqResolver, res: PipelineResult
) -> None:
    """'접수 문구 미분류' 행 → (문구 해시가 직전 분류와 같으면 복사, D10-2) → 판정기 classify(배치) → 가능/미정/불가/확인 불가.
    문구가 없으면 판정기 호출 없이 사유만."""
    version = caller.known_version()
    if version is not None:  # 판정기 버전이 바뀌었으면 옛 버전 분류는 다시(R3 3차 minor 3)
        reset_stale_classification(session, snap.id, version)
    res.intake_carried += len(carry_classification(session, snap.id, adapter_version=version))
    rows = list(
        session.scalars(
            select(IntakeStatus)
            .where(
                IntakeStatus.snapshot_id == snap.id,
                IntakeStatus.path.in_(_INTAKE_PATHS),
                IntakeStatus.reason == UNCLASSIFIED,
            )
            .order_by(IntakeStatus.complex_id, IntakeStatus.path, IntakeStatus.id)
        )
    )
    items: dict[str, tuple[IntakeStatus, jp.IntakeItem]] = {}
    for r in rows:
        text = _intake_text(session, r)
        if not text.strip():
            r.reason = NO_TEXT
            continue
        item = jp.IntakeItem(r.complex_id, r.path, text)
        items.setdefault(item.key, (r, item))
    ordered = [v for _, v in sorted(items.items())]
    for b in range(0, len(ordered), CLASSIFY_BATCH_MAX):
        chunk = ordered[b : b + CLASSIFY_BATCH_MAX]
        out = jp.p4_classify_intake(
            caller, [i for _, i in chunk], snapshot_id=snap.id, batch_no=b // CLASSIFY_BATCH_MAX
        )
        for row, item in chunk:
            o = out[item.key]
            row.status = o.status
            row.reason = o.reason
            s = seq(o.judgment_seq)
            mark = f"{CLASSIFIED_MARK} jl_{s}" if s is not None else CLASSIFIED_MARK
            row.note = f"{row.note} · {mark}" if row.note else mark
            res.intake_classified += 1
    session.flush()


def _p4(
    session: Session,
    caller: CountingCaller,
    snap: Snapshot,
    region: Region,
    facts: Sequence[ComplexFacts],
    targets: set[int],
    seq: persist.SeqResolver,
) -> None:
    """포함/제외: 지역 단지 전부(범위 경계 제외)를 64개씩 배치 1회 — 같은 집합·같은 텍스트면 캐시(T17).

    대상 단지만이 아니라 전부를 보내는 것은 배치 payload 가 집합으로 정해지기 때문이다(부분 재판정이 다른 payload 를
    만들면 같은 사실에 판정기를 다시 부른다). 결과는 배치 안의 모든 단지에 쓴다(같은 판정).
    """
    del targets
    pool = [(f.complex_id, f) for f in facts if f.row.inclusion_class != "범위 경계"]
    for b in range(0, len(pool), CLASSIFY_BATCH_MAX):
        chunk = pool[b : b + CLASSIFY_BATCH_MAX]
        outs = jp.p4_classify_inclusion_batch(
            caller,
            [(cid, _inclusion_text(f)) for cid, f in chunk],
            snapshot_id=snap.id,
            batch_no=b // CLASSIFY_BATCH_MAX,
        )
        for cid, f in chunk:
            out = outs[cid]
            cx = f.row
            if out.resolved and out.label in INCLUSION_CLASS:
                cx.inclusion_class = out.label
                cx.inclusion_decision = "auto"
            else:
                # 미해결(review·manual_review)은 분류를 바꾸지 않는다 — 표시만, 판단은 사람·재판정
                cx.inclusion_decision = (
                    out.decision if out.decision in ("review", "manual_review") else "review"
                )
            cx.inclusion_prob = persist.to_dec(out.prob) if out.prob is not None else None
            cx.inclusion_judgment_seq = seq(out.envelope.judgment_seq)
    session.flush()


# ---------------------------------------------------------------- P4 호재 (D10-6)


def _is_news(cat: Catalyst) -> bool:
    """뉴스 수집 후보(``normalize.catalyst.catalysts_from_news`` — raw_document_id = 뉴스 원문). 사람 URL 입력·시드 호재는 아님."""
    return cat.raw_document_id is not None


def _catalyst_text(cat: Catalyst) -> str:
    """호재 판정 입력(단계·종류 classify 공용) = 이름·발췌·출처. 종류(kind)는 넣지 않는다 — 종류 classify 결과가 다음
    실행의 입력을 바꿔 같은 호재를 매번 다시 판정하지 않게(같은 사실 = 같은 payload = 캐시)."""
    return "\n".join(p for p in (f"호재: {cat.name}", cat.note or "", cat.source_url or "") if p)


def _catalyst_key(cat: Catalyst) -> str:
    """판정 purpose 키. 뉴스 후보는 행 id 가 아니라 출처 URL·제목 해시(``assemble.news_key`` — 수집 screen 과 같은 키):
    폐기 후 다음 수집에 다시 들어온 같은 기사는 새 id 여도 같은 purpose 라 캐시(호출 0). 나머지는 예전처럼 행 id."""
    if not _is_news(cat):
        return str(cat.id)
    from app.scheduler.assemble import news_key

    return news_key(cat.source_url, cat.name)


NOT_CATALYST: Final = "호재 아님"
"""catalyst.stage '호재 아님'(계약 .8, D11-2) — 판정기가 호재가 아니라고 본 뉴스 후보. 지우지 않고 제외로 남긴다."""


def _not_catalyst(
    session: Session,
    cat: Catalyst,
    out: jp.ClassifyOutcome,
    why: str,
    res: PipelineResult,
    seq_id: int | None,
) -> None:
    """'호재 아님'(D11-2·M-10): 행·출처·연결을 지우지 않는다(발행 스냅샷이 인용한 호재가 사라지지 않게). 뉴스 후보는
    stage '호재 아님'(제외), 사람이 넣은 호재(뉴스 원문 없음)는 단계를 그대로 두고 판정 결과만 병기(decision·judgment_seq·
    note). 기록 = 행 자체 + 잡 stats ``catalysts_discarded``(이름 유지 — 대시보드 호환)."""
    res.catalysts_discarded.append(
        {
            "catalyst_id": cat.id,
            "name": cat.name[:80],
            "source_url": cat.source_url,
            "reason": why,
            "judgment_seq": seq_id,
            "kept": True,
        }
    )
    cat.decision = out.decision
    cat.stage_prob = persist.to_dec(out.prob) if out.prob is not None else None
    cat.judgment_seq = seq_id
    if _is_news(cat):
        cat.stage = NOT_CATALYST
        return
    mark = f"판정기: 호재 아님(jl_{seq_id})" if seq_id is not None else "판정기: 호재 아님"
    if mark not in (cat.note or ""):
        cat.note = f"{cat.note} · {mark}" if cat.note else mark


def _p4_catalysts(
    session: Session,
    caller: CountingCaller,
    snap: Snapshot,
    region: Region,
    seq: persist.SeqResolver,
    res: PipelineResult,
) -> None:
    """D10-6: 호재 후보(뉴스는 수집 때 P1 screen 통과분만 — ``assemble``) → 단계 classify(5단계 + '호재 아님') →
    '호재 아님'(``judge.pipeline.catalyst_stage`` = None)이면 후보 폐기·기록, 아니면 단계·종류 classify(``catalyst_kind``).

    판단은 판정기만 — 봉투 결과를 행에 옮긴다(미해결이면 단계 '미확정'·종류 '기타'). '호재 아님'은 지우지 않는다(D11-2):
    뉴스 후보는 stage '호재 아님'(제외), 사람이 넣은 호재는 단계 유지 + 판정 결과 병기(``_not_catalyst``).
    """
    for cat in list(
        session.scalars(select(Catalyst).where(Catalyst.region_id == region.id).order_by(Catalyst.id))
    ):
        key = _catalyst_key(cat)
        text = _catalyst_text(cat)
        out = jp.p4_classify_catalyst(caller, catalyst_key=key, text=text, snapshot_id=snap.id)
        s = seq(out.envelope.judgment_seq)
        stage = jp.catalyst_stage(out)
        if stage is None:  # '호재 아님'(auto)
            _not_catalyst(session, cat, out, "호재 아님(판정기 classify)", res, s)
            continue
        cat.stage = stage
        cat.decision = out.decision
        cat.stage_prob = persist.to_dec(out.prob) if out.prob is not None else None
        cat.judgment_seq = s
        kout = jp.p4_classify_catalyst_kind(caller, catalyst_key=key, text=text, snapshot_id=snap.id)
        cat.kind = jp.catalyst_kind(kout)
    session.flush()


# ---------------------------------------------------------------- P5


def _p5(
    session: Session,
    caller: CountingCaller,
    snap: Snapshot,
    targets: set[int],
    seq: persist.SeqResolver,
    res: PipelineResult | None = None,
) -> int:
    """같은 순위 1차·1차 상충만 compare(RA §3 표). 결과 seq 를 출처 행에 남기고, contradicts 면
    ``normalize.judged.apply_compare``(1차 공고 자료 채택·병기)."""
    if not targets:
        return 0
    ids = list(targets)
    keys: set[tuple[str, int]] = {("complex", i) for i in ids}
    keys |= {
        ("complex_type", t)
        for (t,) in session.execute(select(ComplexType.id).where(ComplexType.complex_id.in_(ids)))
    }
    keys |= {
        ("payment_terms", t)
        for (t,) in session.execute(select(PaymentTerms.id).where(PaymentTerms.complex_id.in_(ids)))
    }
    groups: dict[str, list[FieldProvenance]] = {}
    for fp in session.scalars(
        select(FieldProvenance)
        .where(FieldProvenance.conflict_group.is_not(None))
        .order_by(FieldProvenance.id)
    ):
        if fp.entity_id is not None and (fp.entity, fp.entity_id) in keys and fp.conflict_group:
            groups.setdefault(fp.conflict_group, []).append(fp)
    n = 0
    for group, rows in sorted(groups.items()):
        chosen = next((r for r in rows if r.chosen), None)
        if chosen is None or chosen.source_rank >= 3 or not chosen.excerpt:
            continue
        rivals = [
            r for r in rows
            if r is not chosen and r.source_rank == chosen.source_rank and r.value_text != chosen.value_text
            and r.excerpt and r.compare_judgment_seq is None
        ]  # fmt: skip
        for r in rivals:
            cid = chosen.entity_id if chosen.entity == "complex" else None
            out = jp.p5_compare(
                caller,
                chosen.excerpt,
                r.excerpt or "",
                purpose=f"compare:{group}"[:128],
                snapshot_id=snap.id,
                complex_id=cid,
            )
            s = seq(out.envelope.judgment_seq)
            chosen.compare_judgment_seq = chosen.compare_judgment_seq or s
            r.compare_judgment_seq = s
            n += 1
            # contradicts·same_fact·different_facts 모두 apply_compare 가 채택·병기 표식을 남긴다(R3 M1 —
            # 채택 보류는 compare 결과로만 푼다; review·escaped 는 보류 유지)
            if out.resolved and out.relation in COMPARE_RESOLVED:
                adopted = apply_compare(
                    session, group, relation=out.relation, judgment_seq=s, snapshot_id=snap.id
                )
                if res is not None and adopted.changed:
                    res.compare_adopted += 1
                break  # 채택이 바뀌었을 수 있다 — 같은 그룹의 나머지는 다음 재판정에서
    session.flush()
    return n


# ---------------------------------------------------------------- P7


def _prev_anchor(session: Session, caller: CountingCaller, run_seq: int | None) -> RerankPrev | None:
    """이전 run 의 rerank 결과(같은 판정기 버전일 때만). judgment_log 캐시 행을 **읽기만** 한다 — 판정기에 다시
    보내지 않는다(이전에는 hash 미스면 실제 rerank 호출 후 결과를 버렸다, R3 minor 32)."""
    if run_seq is None:
        return None
    row = session.get(JudgmentLog, run_seq)
    if row is None or row.status != "ok" or row.tool != "rerank":
        return None
    if row.adapter_version != caller.known_version():  # 서버에 다시 묻지 않는다(판정기 다운 + 캐시, N-M8)
        return None
    items: list[RerankItem] = list(_anchor_from(row).items)
    if not items:
        return None
    return RerankPrev(judgment_seq=row.seq, items=items)


def _last_rerank_seq(session: Session, snapshot_ids: Sequence[int]) -> int | None:
    for sid in snapshot_ids:
        seq = session.scalars(
            select(ScoreRun.rerank_judgment_seq)
            .where(ScoreRun.snapshot_id == sid, ScoreRun.rerank_judgment_seq.is_not(None))
            .order_by(ScoreRun.id.desc())
        ).first()
        if seq is not None:
            return seq
    return None


# ---------------------------------------------------------------- D9-3 접수 상태 변경


def _intake_changes(
    ctx: SchedulerContext,
    session: Session,
    snap: Snapshot,
    prev: Snapshot | None,
    complex_ids: Sequence[int],
) -> list[ChangeEvent]:
    """표시 접수 상태 변경 → change_event(intake_status, critical) — ``intake.intake_change_events``(수집과 같은 함수)."""
    return intake_change_events(session, snap, prev, complex_ids, detected_at=ctx.iso_now())


def _notify(ctx: SchedulerContext, session: Session, events: Sequence[ChangeEvent]) -> list[int]:
    """critical 이벤트 웹훅(건별 guard, 이미 보낸 이벤트는 다시 보내지 않음 — notify.Notifier). 보낸 이벤트 id."""
    if not events:
        return []
    ids = sorted({e.complex_id for e in events if e.complex_id is not None})
    names = {c.id: c.name for c in session.scalars(select(Complex).where(Complex.id.in_(ids)))} if ids else {}
    return list(ctx.notifier.notify(events, names).event_ids)


# ---------------------------------------------------------------- P9


def _claim_targets(f: ComplexFacts) -> dict[str, tuple[str, int, str]]:
    """P9 사실 문장의 필드(논리) → 주장이 생성된 DB 사실(entity, entity_id, 출처 필드 경로) — 계약 claim.entity·entity_id·field.

    가격은 점수·화면이 실제로 쓰는 필드(현재 구매가 max_ref — 최신 공고 ``payment_terms.price_by_type.<타입>.max_price_won``,
    없으면 ``complex_type.max_price_won``)다(M-4: 강등도 그 필드에 걸린다)."""
    out: dict[str, tuple[str, int, str]] = {}
    cx = f.row
    ref = f.price.max_ref if f.price is not None else None
    if ref is not None:
        out["max_price_won"] = (ref.entity, ref.entity_id, ref.field)
    for name in ("move_in_ym", "resale_months", "residency_months"):
        out[name] = ("complex", cx.id, name)
    if f.terms is not None:
        out["down_payment_pct"] = ("payment_terms", f.terms.id, "down_payment_pct")
    return out


def _with_targets(claims: Sequence[ClaimDTO], f: ComplexFacts) -> list[ClaimDTO]:
    """원자 주장마다 그 문장이 가리키는 사실 필드가 하나면 대상(entity·entity_id·field)을 단다(D10-3 — 강등·같은 대상 검사).
    필드 용어 판별은 API 와 같은 함수(``api.demotion.fields_in``)."""
    from app.api.demotion import fields_in

    targets = _claim_targets(f)
    out: list[ClaimDTO] = []
    for c in claims:
        found = fields_in(c.text or "") & set(targets)
        if len(found) == 1:
            entity, eid, path = targets[next(iter(found))]
            c = c.model_copy(update={"entity": entity, "entity_id": eid, "field": path})
        out.append(c)
    return out


def _claim_text(f: ComplexFacts) -> str:
    """P9 사실 문장 — 강등 중인 사실(D11-3)은 문장에 넣지 않는다(``fact_row``·가격 view 가 이미 값을 뺐다)."""
    cx = f.fact_row
    name = cx.name
    lines: list[str] = []
    evid = {eid for eid, _ in f.evidence}
    ref = f.price.max_ref if f.price is not None else None
    price = ref.value if ref is not None else None
    if isinstance(price, int | float) and price and evid:
        lines.append(f"{name} 기준 타입 최고 공급금액은 {int(price):,}원이다")
    if cx.move_in_ym:
        lines.append(f"{name} 입주 예정 시기는 {cx.move_in_ym}이다")
    if cx.resale_months is not None:
        lines.append(f"{name} 전매제한 기간은 {cx.resale_months}개월이다")
    if cx.residency_months is not None:
        lines.append(f"{name} 거주의무 기간은 {cx.residency_months}개월이다")
    if f.terms is not None and f.terms.down_payment_pct is not None:
        pct = format(f.terms.down_payment_pct.normalize(), "f")
        lines.append(f"{with_josa(name, '은')} 계약금 비율 {pct}%를 적용한다")
    return "\n".join(lines)


# ---------------------------------------------------------------- 본체


def _sync_demotions(session: Session, complex_ids: Sequence[int] | None) -> None:
    from app.api.demotion import sync_demotions

    if sync_demotions(session, set(complex_ids) if complex_ids is not None else None):
        session.commit()


def run_pipeline(
    ctx: SchedulerContext,
    snapshot_id: int,
    *,
    complex_ids: Sequence[int] | None = None,
    scenario_id: int | None = None,
    reason: str = "",
) -> PipelineResult:
    with ctx.session_factory() as session:
        # D11-1·M-2: 발행 스냅샷은 불변 — 그 기준일의 가장 큰 리비전이 발행됐으면 새 리비전(building)에 판정하고, 발행 전
        # 리비전이면 그 자리에서. 판정 중에는 building(파생 행이 반쯤 바뀐 상태로 publish 되지 않게), 끝나면 ready
        snap = writable(session, snapshot_id, reason=reason or "재판정", created_at=ctx.iso_now())
        if snap.status != "building":
            snap.status = "building"
        session.commit()
        snapshot_id = snap.id
        region = session.get(Region, snap.region_id)
        if region is None:
            raise LookupError(f"region {snap.region_id} 없음")
        prev = previous(session, snap, published_only=True) or previous(session, snap)
        earlier = [prev.id] if prev is not None else []
        # 강등 정리(D10-3, G3 ``api.demotion``): 새 원문이 출처를 다시 골랐으면 복원, 같은 원문 재정규화면 강등 유지 —
        # 강등된 사실은 값이 비어 점수·요건 입력에서 빠진다
        _sync_demotions(session, complex_ids)
        facts = load_facts(session, snap, region)
        all_ids = [f.complex_id for f in facts]
        targets = all_ids if complex_ids is None else sorted(set(complex_ids) & set(all_ids))
        res = PipelineResult(snapshot_id, targets)
        _, before_version = last_logged(session)
        caller: CountingCaller | None = None
        try:
            caller = CountingCaller(ctx.adapter(), before_call=session.commit)
            seq = persist.SeqResolver(session)
            tset = set(targets)
            # P1~P5 (+ 접수 상태 classify)
            _p1_p3(session, caller, snap, targets, res, seq)
            _p4_intake(session, caller, snap, seq, res)
            changed = _intake_changes(ctx, session, snap, prev, all_ids)
            if changed:
                res.intake_events = [e.id for e in changed]
                tset |= {e.complex_id for e in changed if e.complex_id is not None}
                res.targets = sorted(tset)
                session.commit()
                res.notified_event_ids += _notify(ctx, session, changed)
            _p4(session, caller, snap, region, facts, tset, seq)
            _p4_catalysts(session, caller, snap, region, seq, res)
            res.carried["compare"] = _p5(session, caller, snap, tset, seq, res)
            session.commit()
            facts = load_facts(session, snap, region)  # 포함 분류가 바뀌었을 수 있다
            scope = {f.complex_id: f.scope for f in facts}

            # P6 사다리
            rows = []
            for f in facts:
                if f.complex_id in tset and runs_ladder(f.scope):
                    rows.extend(
                        jp.p6_ladder(caller, evidence_card(f), asof_date=snap.asof_date, snapshot_id=snap.id)
                    )
            res.ladders = persist.save_ladders(session, snap.id, rows, seq)
            if prev is not None:
                res.carried["ladder"] = persist.copy_ladders(
                    session, prev.id, snap.id, [i for i in all_ids if i not in tset]
                )
            session.commit()
            shown = stored_scope(session, snap.id, facts)  # 저장 판정 범위 = D9-1 판정 범위 그대로

            # P7 rerank — 후보군 전체 1회
            empty = RerankAnchor(judgment_seq=None, status="review", items=[])
            base, cards = score_base(session, snap, region, facts)
            pool = rerank_pool(facts, cards, scope)
            anchor = empty
            if pool:
                prev_seq = _last_rerank_seq(session, [snap.id, *earlier])
                prev_anchor = _prev_anchor(session, caller, prev_seq)
                anchor = jp.p7_rerank(
                    caller, pool, region_id=region.id, snapshot_id=snap.id, prev=prev_anchor
                )
            inputs = base.model_copy(update={"rerank": anchor})

            # 점수 + P8 decide (시나리오마다)
            snap_dto = snapshot_dto(snap)
            precalc = RequirementPrecalculator()
            scenarios = load_scenarios(session, scenario_id)
            if not scenarios:
                res.skipped["score"] = "시나리오 행 없음(scenario 시드 필요)"
            saved_gaps = False
            upcoming = wait_new_evidence(facts, snap.asof_date)  # 가상 후보 '모집공고 대기' 근거(계약 .5)
            for sc in scenarios:
                plan = decide_plan(
                    snap_dto, sc, inputs, cards, scope, precalc=precalc, wait_new_text=upcoming,
                )  # fmt: skip
                detail = plan.detail
                run = persist.save_score_run(
                    session,
                    detail,
                    created_at=ctx.iso_now(),
                    seq=seq,
                    previous_snapshot_ids=earlier,
                    scopes=shown,
                )
                res.score_run_ids.append(run.id)
                if not saved_gaps:
                    persist.save_comparables(session, snap.id, detail.gaps)
                    saved_gaps = True
                if not plan.runnable:
                    n_cand = plan.n_options
                    res.skipped[f"decide:{sc.code or sc.id}"] = f"후보 {n_cand}개(2개 이상 필요)"
                    continue
                dset = jp.p8_decide(
                    caller,
                    scenario_id=sc.id,
                    scenario_code=sc.code,
                    scenario_name=sc.name,
                    requirements=plan.requirements,
                    priorities=plan.priorities,
                    candidates=plan.candidates,
                    snapshot_id=snap.id,
                    include_wait_new=plan.include_wait_new,
                    wait_new_evidence=plan.wait_new_evidence,
                )
                res.decisions += len(persist.save_decisions(session, run, dset, seq))
            if scenario_id is not None and prev is not None:
                # 시나리오 지정 재판정: 다른 시나리오의 저장 결과도 이 리비전에 있어야 한다(새 리비전이면 비어 있다 — D11-1)
                runs, _ = persist.copy_runs(session, prev.id, snap.id, created_at=ctx.iso_now())
                if runs:
                    res.carried["score_run"] = runs
            session.commit()

            # P9 verify — 대상 단지의 사실 문장
            claims = []
            for f in facts:
                if f.complex_id not in tset or not runs_ladder(f.scope) or not f.evidence:
                    continue
                text = _claim_text(f)
                if not text:
                    continue
                try:
                    verified = jp.p9_verify(
                        caller,
                        section=f"complex:{f.complex_id}",
                        text=text,
                        evidence=f.evidence,
                        snapshot_id=snap.id,
                        complex_id=f.complex_id,
                    )
                    claims.extend(_with_targets(verified, f))
                except ValueError as exc:  # 복합 문장·근거 없음 — verify 하지 않고 기록
                    res.skipped[f"verify:{f.complex_id}"] = type(exc).__name__
            res.claims = len(persist.save_claims(session, claims, seq))
            if prev is not None:
                res.carried["claim"] = persist.copy_claims(
                    session, prev.id, snap.id, [i for i in all_ids if i not in tset]
                )
            res.contradicted = contradicted_count(session, snap.id)
            if snap.status == "building":
                snap.status = "ready"
            clear_degraded(session, snap.id)
            session.commit()
        except JudgeUnavailable as exc:
            session.rollback()
            mark_degraded(session, snapshot_id)
            session.commit()
            ctx.reset_adapter()
            res.degraded = True
            res.error = "judge_unavailable: " + redact_text(str(exc), get_settings().secret_values())[:200]
            log.warning("worker.pipeline.degraded", extra={"snapshot_id": snapshot_id})
        if caller is not None:
            res.absorb(caller)
            # 버전 변경 감지는 판정기에 실제로 간 호출의 봉투 버전만(N-M8: 다운 + 전부 캐시면 서버 재호출·예외 없음)
            if not res.degraded and caller.live_version:
                ev = record_version_change(
                    ctx, session, before_version, caller.live_version, snapshot_id=snapshot_id
                )
                if ev is not None:
                    res.version_event_id = ev.id
                    session.commit()
        log.info(
            "worker.pipeline.done",
            extra={
                "snapshot_id": snapshot_id,
                "targets": len(targets),
                "judge_calls": res.judge_calls,
                "cached": res.cached,
                "degraded": res.degraded,
                "reason": reason[:60],
            },
        )
        return res
