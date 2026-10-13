"""판정 파이프라인 단계 함수 (meta §2-1 P1~P9). 각 단계 = 입력 생성 → 어댑터 호출 → 행 데이터 변환.

전체 순서 실행(변경 단지만, degraded 처리, DB 적재)은 WP7(scheduler/rejudge.py)이 부른다. 여기서는
- 판단하지 않는다: status·확률·순위는 봉투에서 그대로 옮긴다. 산술(연율·tie 규칙·mismatch 대조)만 한다.
- ``JudgeUnavailable`` 은 삼키지 않고 위로 보낸다(WP7 degraded 전환, T18).
- 반환 모양은 계약 DTO(LadderRow, RerankAnchor, DecisionSet, Claim)라 WP4·WP5·WP7이 그대로 쓴다.
"""

# ruff: noqa: E501  (한국어 docstring·판정기 문구)

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from app.core.contracts_gen import (
    Claim,
    Decision,
    DecisionSet,
    Fact,
    JudgmentEnvelope,
    LadderAnnualized,
    LadderRow,
    LadderVerdicts,
    RequirementCheck,
    RequirementChecks,
    RequirementPre,
    RerankAnchor,
    RerankItem,
    RerankPrev,
)
from app.core.protocols import ClaimSplitter
from app.judge import payloads as P
from app.judge.base import JudgeCaller
from app.judge.claims import RuleClaimSplitter

__all__ = [
    "INTAKE_UNRESOLVED",
    "TIE_CONFIDENCE",
    "ClassifyOutcome",
    "CompareOutcome",
    "IntakeItem",
    "IntakeOutcome",
    "ScreenOutcome",
    "benchmark_screen_purpose",
    "catalyst_kind",
    "catalyst_stage",
    "has_contradiction",
    "is_not_catalyst",
    "p1_screen",
    "p1_screen_benchmark",
    "p1_screen_catalyst",
    "p1_screen_retry",
    "p1_screen_upcoming",
    "p2_extract",
    "p2_extract_upcoming",
    "p3_audit",
    "p4_classify_catalyst",
    "p4_classify_catalyst_kind",
    "p4_classify_inclusion",
    "p4_classify_inclusion_batch",
    "p4_classify_intake",
    "p4_classify_upcoming",
    "p5_compare",
    "p5_same_complex",
    "p6_ladder",
    "p7_rerank",
    "p8_decide",
    "p9_verify",
]

TIE_CONFIDENCE: Final = 0.6
"""decide confidence 가 이보다 낮으면 확률 상위 2개 후보를 tie=true·chosen=true (RA §6-4, T2)."""
_HATCH_LABELS: Final = {
    "ask_user": "사용자 확인",
    "investigate": "추가 조사",
    "none": "해당 없음",
    "wait_new": "모집공고 대기",
}
_EVIDENCE_TEXT_MAX: Final = 1000
INTAKE_UNRESOLVED: Final = "판정 미해결"
"""접수 상태 classify 가 review·manual_review(미해결)이면 '확인 불가(판정 미해결)' — '미정'이 아니다."""


def _day(env: JudgmentEnvelope) -> str:
    return env.created_at[:10]


def _prob_fact(env: JudgmentEnvelope, value: float | None, reason: str, *, usable: bool) -> Fact:
    """판정기 확률 → Fact(label 추정, prov jl_<seq>). 쓸 수 없으면 '확인 불가(미판정)'."""
    if usable and value is not None and env.judgment_seq is not None:
        return Fact(
            v=value,
            label="추정",
            reason=reason,
            prov=f"jl_{env.judgment_seq}",
            checked_at=_day(env),
            unit="prob",
        )
    why = "미판정" if env.judgment_seq is not None or not usable else "출처 누락"
    return Fact(v=None, label="확인 불가", reason=why, prov=None, checked_at=_day(env), unit="prob")


# ====================================================================== P1 ~ P5


@dataclass(frozen=True, slots=True)
class ScreenOutcome:
    envelope: JudgmentEnvelope
    verdict: str | None  # pass | skip | block | None(review)
    usable: bool  # pass 이고 status ok 일 때만 다음 단계 입력으로 쓴다


def p1_screen(
    adapter: JudgeCaller,
    text: str,
    *,
    task: str,
    purpose: str,
    snapshot_id: int | None = None,
    complex_id: int | None = None,
) -> ScreenOutcome:
    """P1 입력 검사. skip 이면 호출자가 purpose 를 바꿔 다른 입력으로 재스크린, block 은 사용 금지."""
    env = adapter.call(
        "screen", P.screen_payload(text, task=task), purpose, snapshot_id=snapshot_id, complex_id=complex_id
    )
    verdict = env.result.get("verdict") if env.result else None
    return ScreenOutcome(env, verdict, env.status == "ok" and verdict == "pass")


def p1_screen_retry(
    adapter: JudgeCaller,
    text: str,
    *,
    task: str,
    purpose: str,
    retry_text: str,
    retry_task: str,
    snapshot_id: int | None = None,
    complex_id: int | None = None,
) -> ScreenOutcome:
    """P1 + meta §2-1 재screen 규칙: skip(관련도 낮음)이면 purpose 를 단계에 맞게 바꿔(``<purpose>:retry``, 검사 목적
    ``retry_task``) **다른 입력**(``retry_text``)으로 한 번 더 screen 하고 그 결과를 쓴다. block·review 는 재screen 하지 않는다
    (block = 사용 금지). 판단은 두 번 다 판정기다 — 코드는 verdict 로 분기만 한다(규칙 3)."""
    first = p1_screen(
        adapter, text, task=task, purpose=purpose, snapshot_id=snapshot_id, complex_id=complex_id
    )
    if first.verdict != "skip":
        return first
    return p1_screen(
        adapter, retry_text, task=retry_task, purpose=f"{purpose}:retry"[:128],
        snapshot_id=snapshot_id, complex_id=complex_id,
    )  # fmt: skip


def p1_screen_benchmark(
    adapter: JudgeCaller, text: str, *, region_id: int, snapshot_id: int | None
) -> ScreenOutcome:
    """지역 벤치마크 텍스트 P1 screen(meta §2-1 P1 '벤치마크·호재 텍스트') — usable 일 때만 P6 noul 컨텍스트 ``benchmark``.
    skip 이면 다른 목적·다른 입력으로 재screen(``p1_screen_retry``)."""
    return p1_screen_retry(
        adapter, text, task=P.BENCHMARK_SCREEN_TASK, purpose=benchmark_screen_purpose(region_id),
        retry_text=P.benchmark_rescreen_text(text), retry_task=P.BENCHMARK_RESCREEN_TASK, snapshot_id=snapshot_id,
    )  # fmt: skip


def benchmark_screen_purpose(region_id: int) -> str:
    return f"screen:benchmark:region:{region_id}"


def p2_extract(
    adapter: JudgeCaller,
    document: str,
    fields: Sequence[P.ExtractField],
    *,
    purpose: str,
    snapshot_id: int | None = None,
    complex_id: int | None = None,
) -> JudgmentEnvelope:
    """P2 수치 추출. 필드별 decision=review 면 호출자가 공고문 원문값을 쓰고 'review' 표기."""
    payload = P.extract_payload(document, fields, purpose="청약 공고문 수치 추출")
    return adapter.call("extract", payload, purpose, snapshot_id=snapshot_id, complex_id=complex_id)


def p3_audit(
    adapter: JudgeCaller,
    source: str,
    records: Sequence[P.AuditRecord],
    *,
    purpose: str,
    snapshot_id: int | None = None,
    complex_id: int | None = None,
) -> JudgmentEnvelope:
    """P3 감사. verdict=flagged 항목은 원문 대조 후 수정."""
    return adapter.call(
        "audit", P.audit_payload(source, records), purpose, snapshot_id=snapshot_id, complex_id=complex_id
    )


@dataclass(frozen=True, slots=True)
class ClassifyOutcome:
    envelope: JudgmentEnvelope
    label: str | None
    prob: float | None
    decision: str | None  # auto | review | manual_review
    resolved: bool  # status ok(auto) 일 때만 True — review·manual_review 는 미해결, 상승 근거로 쓰지 않는다


def _classify_outcome(env: JudgmentEnvelope) -> ClassifyOutcome:
    r = env.result or {}
    return ClassifyOutcome(env, r.get("label") or None, r.get("prob"), r.get("decision"), env.status == "ok")


def p4_classify_inclusion(
    adapter: JudgeCaller, *, complex_id: int, text: str, snapshot_id: int | None = None
) -> ClassifyOutcome:
    """P4(a) 포함/제외 7클래스 → complex.inclusion_class / inclusion_decision / inclusion_prob."""
    payload = P.classify_inclusion_payload(item_id=f"complex:{complex_id}", text=text)
    env = adapter.call(
        "classify",
        payload,
        f"classify:inclusion:c{complex_id}",
        snapshot_id=snapshot_id,
        complex_id=complex_id,
    )
    return _classify_outcome(env)


def _batch_items(env: JudgmentEnvelope, ids: Sequence[str]) -> dict[str, ClassifyOutcome]:
    """배치 classify 봉투 → 항목별 결과. 항목 1개면 최상위가 그 항목(계약 ClassifyResult).

    항목은 decision=auto 이고 봉투가 판정기 응답(ok·review)일 때만 해결(resolved)이다.
    """
    r = env.result or {}
    usable = env.status in {"ok", "review"}
    if len(ids) == 1:
        rows = {ids[0]: r}
    else:
        rows = {str(it.get("id")): it for it in r.get("items") or [] if isinstance(it, dict)}
    out: dict[str, ClassifyOutcome] = {}
    for item_id in ids:
        it = rows.get(item_id) or {}
        decision = it.get("decision")
        out[item_id] = ClassifyOutcome(
            env, it.get("label") or None, it.get("prob"), decision, usable and decision == "auto"
        )
    return out


def p4_classify_inclusion_batch(
    adapter: JudgeCaller,
    items: Sequence[tuple[int, str]],
    *,
    snapshot_id: int | None = None,
    batch_no: int = 0,
) -> dict[int, ClassifyOutcome]:
    """P4(a) 배치: (complex_id, 텍스트) ≤64개 → 1회 호출(계약 2026-10-09.2 ClassifyResult.items[]).

    항목은 complex_id 순으로 정렬한다(같은 집합 = 같은 payload = 캐시).
    1개면 단건 호출과 같은 payload·purpose.
    """
    ordered = sorted(items, key=lambda x: x[0])
    if len(ordered) == 1:
        cid, text = ordered[0]
        return {cid: p4_classify_inclusion(adapter, complex_id=cid, text=text, snapshot_id=snapshot_id)}
    ids = [f"complex:{cid}" for cid, _ in ordered]
    payload = P.classify_inclusion_batch_payload([(f"complex:{cid}", t) for cid, t in ordered])
    env = adapter.call("classify", payload, f"classify:inclusion:batch{batch_no}", snapshot_id=snapshot_id)
    by_id = _batch_items(env, ids)
    return {cid: by_id[f"complex:{cid}"] for cid, _ in ordered}


@dataclass(frozen=True, slots=True)
class IntakeItem:
    """접수 상태 분류 항목: key = 'c<complex_id>:<path>', text = 공식 홈페이지 DOM 텍스트·팝업 문구."""

    complex_id: int
    path: str  # official_popup | headless_shot
    text: str

    @property
    def key(self) -> str:
        return f"intake:c{self.complex_id}:{self.path}"


@dataclass(frozen=True, slots=True)
class IntakeOutcome:
    item: IntakeItem
    outcome: ClassifyOutcome
    status: str  # 가능 | 미정 | 불가 | 확인 불가
    reason: str | None  # 확인 불가 사유(판정 미해결 · 문구로 판단 불가 · 입력 차단)

    @property
    def judgment_seq(self) -> int | None:
        return self.outcome.envelope.judgment_seq


def _intake_status(out: ClassifyOutcome) -> tuple[str, str | None]:
    if out.envelope.status == "blocked":
        return "확인 불가", "입력 차단(guard)"
    if not out.resolved or out.label not in P.INTAKE_STATUS_BY_CLASS:
        return "확인 불가", INTAKE_UNRESOLVED
    status = P.INTAKE_STATUS_BY_CLASS[out.label]
    return status, ("문구로 판단 불가" if status == "확인 불가" else None)


def p4_classify_intake(
    adapter: JudgeCaller,
    items: Sequence[IntakeItem],
    *,
    snapshot_id: int | None = None,
    batch_no: int = 0,
) -> dict[str, IntakeOutcome]:
    """접수 상태 classify(배치 ≤64, 1회) → key 별 상태.

    판단은 판정기만(auto). 미해결(review·manual_review)은 '확인 불가(판정 미해결)'.
    """
    if not items:
        return {}
    ordered = sorted(items, key=lambda i: (i.complex_id, i.path))
    ids = [i.key for i in ordered]
    payload = P.classify_intake_payload([(i.key, i.text) for i in ordered])
    cid = ordered[0].complex_id if len({i.complex_id for i in ordered}) == 1 else None
    env = adapter.call(
        "classify", payload, f"classify:intake:batch{batch_no}", snapshot_id=snapshot_id, complex_id=cid
    )
    by_id = _batch_items(env, ids)
    out: dict[str, IntakeOutcome] = {}
    for i in ordered:
        status, reason = _intake_status(by_id[i.key])
        out[i.key] = IntakeOutcome(i, by_id[i.key], status, reason)
    return out


SITE_ITEM_BUDGET: Final = P.ITEM_TEXT_MAX - 150
"""동일성 항목 텍스트 목표 길이 — payload 의 공개 텍스트 가림(전화 → '[REDACTED:phone]')이 길이를 조금 늘려도 2000자
자르기(``payloads._classify_items``)에 꼬리말이 잘리지 않게 여유를 둔다."""


@dataclass(frozen=True, slots=True)
class SiteItem:
    """D21-5 공식 홈페이지 동일성 항목: 단지 사실(이름·위치·시공·시행·세대수) + 그 페이지의 주소·제목·설명 + 페이지 문구.

    R6-INTAKE(인천 첫 실행 — 동일성 review 11건): 판정기가 페이지를 단지에 묶을 근거가 입력에 없었다. 홈페이지 주소(도메인이
    단지 이름인 경우가 많다)·HTML 제목·설명이 빠졌고, 페이지 문구는 앞 1500자(메뉴·회전 배너)만이라 시행·시공·현장 주소·총
    세대수가 있는 꼬리말이 잘렸다. 근거를 더해 보낼 뿐 같은 단지인지는 판정기가 정한다(규칙 3 — 이름 문자열을 세지 않는다).
    ``text`` 는 호출자가 줄 중복을 뺀 페이지 문구 — 넘치면 앞·뒤를 남긴다(``payloads.head_tail``)."""

    complex_id: int
    path: str
    name: str
    address: str | None
    text: str
    builder: str | None = None
    developer: str | None = None
    units_total: int | None = None
    url: str | None = None
    final_url: str | None = None
    title: str | None = None
    description: str | None = None

    @property
    def key(self) -> str:
        return f"site:c{self.complex_id}:{self.path}"

    @property
    def item_text(self) -> str:
        head = [
            f"단지: {self.name}",
            f"위치: {self.address}" if self.address else "",
            f"시공: {self.builder}" if self.builder else "",
            f"시행: {self.developer}" if self.developer else "",
            # 청약홈 공급 세대수는 일반분양분이라 페이지의 '총 n세대'(조합원·임대 포함)와 다를 수 있다 — 그 뜻을 함께 적는다
            # (재생: 라벨 없이 '공급 세대: 50세대'만 주자 '총 126세대' 페이지가 review 로 남았다)
            f"청약홈 공급 세대수: {self.units_total}세대(단지 총 세대수와 다를 수 있음)"
            if self.units_total
            else "",
            f"홈페이지 주소: {self.url}" if self.url else "",
            f"최종 주소(이동 후): {self.final_url}" if self.final_url and self.final_url != self.url else "",
            f"페이지 제목: {self.title}" if self.title else "",
            f"페이지 설명: {self.description}" if self.description else "",
        ]
        top = "\n".join(p for p in head if p)
        label = "\n페이지 문구:\n"
        return top + label + P.head_tail(self.text, SITE_ITEM_BUDGET - len(top) - len(label))


def p4_classify_site_identity(
    adapter: JudgeCaller,
    items: Sequence[SiteItem],
    *,
    snapshot_id: int | None = None,
    batch_no: int = 0,
) -> dict[str, ClassifyOutcome]:
    """D21-5(R4 재시험 N6): 공식 홈페이지 페이지 문구가 그 단지의 페이지인가(배치 ≤64, 1회). 접수 classify 앞에서 부른다.
    '그 단지'로 쓰는 것은 auto + ``SITE_SAME`` 뿐 — 그 밖(다른 단지·불명·review)은 호출자가 접수 근거에서 뺀다."""
    if not items:
        return {}
    ordered = sorted(items, key=lambda i: (i.complex_id, i.path))
    ids = [i.key for i in ordered]
    payload = P.classify_site_identity_payload([(i.key, i.item_text) for i in ordered])
    cid = ordered[0].complex_id if len({i.complex_id for i in ordered}) == 1 else None
    env = adapter.call(
        "classify",
        payload,
        f"classify:site_identity:batch{batch_no}",
        snapshot_id=snapshot_id,
        complex_id=cid,
    )
    return _batch_items(env, ids)


def is_same_site(out: ClassifyOutcome) -> bool:
    """동일성 classify 가 '그 단지의 페이지'(auto)인가."""
    return out.resolved and out.label == P.SITE_SAME


def is_other_site(out: ClassifyOutcome) -> bool:
    """동일성 classify 가 '다른 단지의 페이지'(auto)인가 — review·unclear 는 아니다(D22-4, R4 3차 N11)."""
    return out.resolved and out.label == P.SITE_OTHER_CLASS


def p1_screen_upcoming(
    adapter: JudgeCaller,
    *,
    news_key: str,
    title: str,
    excerpt: str | None,
    url: str | None,
    snapshot_id: int | None,
) -> ScreenOutcome:
    """D20-2 P1 공고 예정 신호 screen(뉴스 항목 → 공고 예정 단지 후보 전). usable 만 다음 단계."""
    parts = (f"제목: {title}", f"발췌: {excerpt}" if excerpt else "", f"링크: {url}" if url else "")
    text = "\n".join(p for p in parts if p)
    return p1_screen(adapter, text[:4000], task=P.UPCOMING_SCREEN_TASK,
                     purpose=f"screen:upcoming:{news_key}"[:128], snapshot_id=snapshot_id)  # fmt: skip


def p2_extract_upcoming(
    adapter: JudgeCaller, *, news_key: str, document: str, snapshot_id: int | None
) -> list[str]:
    """D20-2 P2 기사 → 공고 예정 단지 이름(판정기 auto 값만, 순서대로, 중복 없이). 봉투가 ok 가 아니면 []."""
    env = p2_extract(adapter, document, P.upcoming_extract_fields(),
                     purpose=f"extract:upcoming:{news_key}"[:128], snapshot_id=snapshot_id)  # fmt: skip
    if env.status != "ok":
        return []
    out: list[str] = []
    for f in (env.result or {}).get("fields") or []:
        v = f.get("value_text") if isinstance(f, dict) else None
        if f.get("decision") == "auto" and isinstance(v, str) and v.strip() and v.strip() not in out:
            out.append(v.strip())
    return out


def p4_classify_upcoming(
    adapter: JudgeCaller, *, news_key: str, items: Sequence[tuple[str, str]], snapshot_id: int | None
) -> dict[str, ClassifyOutcome]:
    """D20-2 공고 예정 단지 후보(id, 텍스트) → 지역·민간분양·공고 예정 여부(배치 1회). 해결 = auto 만."""
    ids = [i for i, _ in items]
    env = adapter.call("classify", P.classify_upcoming_payload(items),
                       f"classify:upcoming:{news_key}"[:128], snapshot_id=snapshot_id)  # fmt: skip
    return _batch_items(env, ids)


def p5_same_complex(
    adapter: JudgeCaller, passage_a: str, passage_b: str, *, pair_key: str, snapshot_id: int | None
) -> bool:
    """D20-2 두 기사 속 단지가 같은 단지인가(이름이 서로를 포함할 때만 묻는다 — 판단은 판정기). same_fact·auto 만 True."""
    out = p5_compare(adapter, passage_a, passage_b, aspects=["같은 아파트 단지(사업)를 가리키는가"],
                     purpose=f"compare:upcoming:{pair_key}"[:128], snapshot_id=snapshot_id)  # fmt: skip
    return out.resolved and out.relation == "same_fact"


def p1_screen_catalyst(
    adapter: JudgeCaller,
    *,
    catalyst_key: str,
    title: str,
    excerpt: str | None = None,
    url: str | None = None,
    snapshot_id: int | None = None,
) -> ScreenOutcome:
    """P1 호재 관련성 screen(뉴스 항목 → 호재 후보 전, D10-6). ``usable``(pass·ok)인 항목만 후보로 둔다 —
    skip(관련 없음)·block·review 는 후보가 아니다(호출자가 사유를 기록)."""
    payload = P.catalyst_screen_payload(title=title, excerpt=excerpt, url=url)
    env = adapter.call("screen", payload, f"screen:catalyst:{catalyst_key}"[:128], snapshot_id=snapshot_id)
    verdict = env.result.get("verdict") if env.result else None
    return ScreenOutcome(env, verdict, env.status == "ok" and verdict == "pass")


def p4_classify_catalyst(
    adapter: JudgeCaller,
    *,
    catalyst_key: str,
    text: str,
    complex_id: int | None = None,
    snapshot_id: int | None = None,
) -> ClassifyOutcome:
    """P4(b) 호재 단계 5클래스 + '호재 아님' → catalyst.stage·decision·judgment_seq.

    '호재 아님'(``is_not_catalyst``)이면 호출자가 후보를 폐기하고 기록한다(D10-6). 단계는 ``catalyst_stage``.
    """
    payload = P.classify_catalyst_payload(item_id=f"catalyst:{catalyst_key}", text=text)
    env = adapter.call(
        "classify",
        payload,
        f"classify:catalyst:{catalyst_key}"[:128],
        snapshot_id=snapshot_id,
        complex_id=complex_id,
    )
    return _classify_outcome(env)


def p4_classify_catalyst_kind(
    adapter: JudgeCaller,
    *,
    catalyst_key: str,
    text: str,
    complex_id: int | None = None,
    snapshot_id: int | None = None,
) -> ClassifyOutcome:
    """P4(b) 호재 종류 6클래스(D10-6) → catalyst.kind (``catalyst_kind``: 미해결이면 '기타')."""
    payload = P.classify_catalyst_kind_payload(item_id=f"catalyst:{catalyst_key}", text=text)
    env = adapter.call(
        "classify",
        payload,
        f"classify:catalyst_kind:{catalyst_key}"[:128],
        snapshot_id=snapshot_id,
        complex_id=complex_id,
    )
    return _classify_outcome(env)


def is_not_catalyst(out: ClassifyOutcome) -> bool:
    """판정기가 auto 로 '호재 아님'이라고 했는가(후보 폐기 조건). 미해결은 폐기하지 않는다(단계 '미확정')."""
    return out.resolved and out.label == P.NOT_CATALYST


def catalyst_stage(out: ClassifyOutcome) -> str | None:
    """호재 단계: auto 로 정해진 5단계면 그 값, 미해결이면 '미확정',
    '호재 아님'이면 None(단계 아님 — 폐기)."""
    if is_not_catalyst(out):
        return None
    return out.label if out.resolved and out.label in P.CATALYST_STAGE_CLASSES else "미확정"


_KIND_IDS: Final = frozenset(c["id"] for c in P.CATALYST_KIND_CLASSES)


def catalyst_kind(out: ClassifyOutcome) -> str:
    """호재 종류: auto 로 정해진 값, 미해결·모르는 값이면 '기타'(키워드로 대신 정하지 않는다)."""
    return out.label if out.resolved and out.label in _KIND_IDS and out.label else "기타"


@dataclass(frozen=True, slots=True)
class CompareOutcome:
    envelope: JudgmentEnvelope
    relation: str | None  # same_fact | contradicts | different_facts | review
    resolved: bool


def p5_compare(
    adapter: JudgeCaller,
    passage_a: str,
    passage_b: str,
    *,
    aspects: Sequence[str] | None = None,
    purpose: str,
    snapshot_id: int | None = None,
    complex_id: int | None = None,
) -> CompareOutcome:
    """P5 출처 충돌(needs_compare 그룹만). contradicts 면 호출자가 1차 자료 채택·2차 병기."""
    payload = P.compare_payload(passage_a, passage_b, aspects=aspects, purpose="같은 사실의 두 출처 대조")
    env = adapter.call("compare", payload, purpose, snapshot_id=snapshot_id, complex_id=complex_id)
    return CompareOutcome(env, (env.result or {}).get("overall"), env.status == "ok")


# ====================================================================== P6 사다리


def p6_ladder(
    adapter: JudgeCaller,
    card: P.EvidenceCard,
    *,
    asof_date: str,
    snapshot_id: int | None,
    horizons: Sequence[P.Horizon] = P.HORIZONS,
    benchmark_text: str | None = None,
    policy_text: str | None = None,
) -> list[LadderRow]:
    """P6 사다리: horizon 마다 noul 1회(명제 4개) → LadderRow.

    status 가 ok 가 아니면 확률은 '확인 불가(미판정)'.
    """
    card_text = P.evidence_card_text(card)
    rows: list[LadderRow] = []
    for spec in P.ladder_specs(card, asof_date=asof_date, horizons=horizons):
        payload = P.noul_payload(
            spec, card_text=card_text, benchmark_text=benchmark_text, policy_text=policy_text
        )
        env = adapter.call("noul", payload, spec.purpose, snapshot_id=snapshot_id, complex_id=card.complex_id)
        ok = env.status == "ok"
        props = {p.get("key"): p for p in (env.result or {}).get("propositions", [])} if ok else {}

        def fact(key: str, env: JudgmentEnvelope = env, props: dict[Any, Any] = props, ok: bool = ok) -> Fact:
            return _prob_fact(env, (props.get(key) or {}).get("prob"), "판정기 noul", usable=ok)

        def verdict(key: str, props: dict[Any, Any] = props) -> Any:
            return (props.get(key) or {}).get("verdict")

        ann = P.annualized(spec.months_from_asof)
        rows.append(
            LadderRow(
                complex_id=card.complex_id,
                snapshot_id=snapshot_id,
                horizon=spec.horizon,
                target_ym=spec.target_ym,
                target_label=spec.target_label,
                months_from_asof=spec.months_from_asof,
                p5=fact("p5"),
                p10=fact("p10"),
                p20=fact("p20"),
                p_flat=fact("p_flat"),
                verdicts=LadderVerdicts(
                    p5=verdict("p5"), p10=verdict("p10"), p20=verdict("p20"), p_flat=verdict("p_flat")
                ),
                annualized=LadderAnnualized(p5=ann["p5"], p10=ann["p10"], p20=ann["p20"]),
                status=env.status,
                judgment_seq=env.judgment_seq,
                proposition_text=dict(spec.propositions)["p10"],
            )
        )
    return rows


# ====================================================================== P7 rerank


def p7_rerank(
    adapter: JudgeCaller,
    cards: Sequence[P.EvidenceCard],
    *,
    region_id: int,
    snapshot_id: int | None,
    prev: RerankPrev | None = None,
) -> RerankAnchor:
    """P7 전체 후보 1회(§6-5 고정 앵커). 같은 집합이면 캐시, 바뀌면 전체 재호출(T7). prev 는 delta 용.

    후보가 JEV 상한(``RERANK_MAX`` 250)을 넘으면 나누지 않는다(나누면 한 호출 앵커가 깨진다) — 판정기를 부르지 않고 status
    ``error``·items 없음 앵커를 돌려준다(rerank 성분 '미판정', 실패를 숨기지 않음 — 호출자가 사유를 잡 stats 에 남긴다)."""
    if len({c.complex_id for c in cards}) > P.RERANK_MAX:
        return RerankAnchor(judgment_seq=None, status="error", items=[], prev=prev)
    env = adapter.call(
        "rerank", P.rerank_payload(cards), P.rerank_purpose(region_id=region_id), snapshot_id=snapshot_id
    )
    items = (
        [RerankItem.model_validate(i) for i in (env.result or {}).get("items", [])]
        if env.status == "ok"
        else []
    )
    return RerankAnchor(judgment_seq=env.judgment_seq, status=env.status, items=items, prev=prev)


# ====================================================================== P8 decide


def _req_check(pre: RequirementPre | None, judge: str | None) -> RequirementCheck:
    mismatch = pre is not None and (
        (pre.status == "충족" and judge == "contradicted")
        or (pre.status == "미충족" and judge == "supported")
    )
    return RequirementCheck(pre=pre, judge=judge, mismatch=mismatch)


def p8_decide(
    adapter: JudgeCaller,
    *,
    scenario_id: int,
    scenario_code: str | None,
    scenario_name: str,
    requirements: tuple[str, str, str],
    priorities: str,
    candidates: Sequence[P.DecideCandidate],
    snapshot_id: int | None,
    include_wait_new: bool = False,
    wait_new_evidence: str | None = None,
) -> DecisionSet:
    """P8 상황별 결정 → DecisionSet(후보 + 가상 후보 '모집공고 대기' + escape hatch 행).

    escaped 면 멈추고 question 을 그대로 보인다. 가상 후보(wait_new)는 단지 후보처럼 선택·동률·
    요건 판정(사전 계산 없음 — 판정기 판정만)을 싣고 complex_id 는 null 이다."""
    payload = P.decide_payload(
        scenario_name=scenario_name,
        requirements=requirements,
        candidates=candidates,
        priorities=priorities,
        include_wait_new=include_wait_new,
        wait_new_evidence=wait_new_evidence,
    )
    env = adapter.call(
        "decide", payload, P.decide_purpose(scenario_code or scenario_id), snapshot_id=snapshot_id
    )
    r = env.result or {}
    usable = env.status in {"ok", "escaped"}
    probs: dict[str, float] = r.get("probs") or {}
    checks: dict[str, dict[str, str]] = r.get("checks") or {}
    selected = r.get("selected") if usable else None
    conf = env.confidence

    option_ids = [f"complex:{c.card.complex_id}" for c in candidates] + (
        [P.WAIT_NEW_OPTION] if include_wait_new else []
    )
    tie_ids: set[str] = set()
    if env.status == "ok" and conf is not None and conf < TIE_CONFIDENCE:
        ranked = sorted(option_ids, key=lambda o: probs.get(o, 0.0), reverse=True)
        tie_ids = set(ranked[:2])

    items: list[Decision] = []
    for c in candidates:
        oid = f"complex:{c.card.complex_id}"
        judged = checks.get(oid, {}) if usable else {}
        reqs = RequirementChecks(
            access=_req_check(c.pre.access if c.pre else None, judged.get("access")),
            regulation=_req_check(c.pre.regulation if c.pre else None, judged.get("regulation")),
            funds=_req_check(c.pre.funds if c.pre else None, judged.get("funds")),
        )
        items.append(
            Decision(
                scenario_id=scenario_id,
                option_key="complex",
                complex_id=c.card.complex_id,
                label=c.card.name,
                prob=_prob_fact(env, probs.get(oid), "판정기 decide", usable=usable),
                chosen=env.status == "ok" and (oid == selected or oid in tie_ids),
                tie=oid in tie_ids,
                mismatch=reqs.access.mismatch or reqs.regulation.mismatch or reqs.funds.mismatch,
                confidence=conf,
                requirements=reqs,
                judgment_seq=env.judgment_seq,
            )
        )
    if include_wait_new:
        key = P.WAIT_NEW_OPTION
        judged = checks.get(key, {}) if usable else {}
        items.append(
            Decision(
                scenario_id=scenario_id,
                option_key=key,
                complex_id=None,
                label=_HATCH_LABELS[key],
                prob=_prob_fact(env, probs.get(key), "판정기 decide", usable=usable),
                chosen=env.status == "ok" and (key == selected or key in tie_ids),
                tie=key in tie_ids,
                mismatch=False,
                confidence=conf,
                requirements=RequirementChecks(
                    access=_req_check(None, judged.get("access")),
                    regulation=_req_check(None, judged.get("regulation")),
                    funds=_req_check(None, judged.get("funds")),
                ),
                judgment_seq=env.judgment_seq,
            )
        )
    for key in (h for h in ("ask_user", "investigate", "none") if h in probs):
        items.append(
            Decision(
                scenario_id=scenario_id,
                option_key=key,
                complex_id=None,
                label=_HATCH_LABELS[key],
                prob=_prob_fact(env, probs.get(key), "판정기 decide", usable=usable),
                chosen=usable and key == selected,
                tie=key in tie_ids,
                mismatch=False,
                confidence=conf,
                requirements=None,
                judgment_seq=env.judgment_seq,
            )
        )
    return DecisionSet(
        scenario_id=scenario_id,
        scenario_code=scenario_code,
        judgment_seq=env.judgment_seq,
        status=env.status,
        confidence=_prob_fact(env, conf, "판정기 decide confidence", usable=usable)
        if conf is not None
        else None,
        tie=bool(tie_ids),
        escaped=env.status == "escaped",
        question=r.get("question") if env.status == "escaped" else None,
        warnings=list(r.get("warnings") or []),
        cached=env.cached,
        items=items,
    )


# ====================================================================== P9 verify


def p9_verify(
    adapter: JudgeCaller,
    *,
    section: str,
    text: str,
    evidence: Sequence[tuple[str, str]],
    snapshot_id: int | None,
    complex_id: int | None = None,
    splitter: ClaimSplitter | None = None,
) -> list[Claim]:
    """P9: 원자 주장으로 나눈 뒤(T6) 16건씩 verify → claim 행(verify_status·judgment_seq).

    contradicted 는 호출자가 문장을 고쳐 다시 나눈 새 주장(parent_claim_id)으로 재검증한다
    (같은 입력 재호출 아님).
    """
    claims = (splitter or RuleClaimSplitter()).split(
        text, section=section, snapshot_id=snapshot_id, complex_id=complex_id
    )
    evidence_text = "; ".join(f"{eid}: {etext}" for eid, etext in evidence)[:_EVIDENCE_TEXT_MAX]
    out: list[Claim] = []
    for start in range(0, len(claims), P.VERIFY_MAX_CLAIMS):
        chunk = claims[start : start + P.VERIFY_MAX_CLAIMS]
        payload = P.verify_payload([c.text for c in chunk], evidence)
        env = adapter.call(
            "verify",
            payload,
            f"verify:section_{section}"[:128],
            snapshot_id=snapshot_id,
            complex_id=complex_id,
        )
        verdicts = {v.get("claim_id"): v.get("verdict") for v in (env.result or {}).get("claims", [])}
        for i, c in enumerate(chunk):
            status = verdicts.get(str(i)) if env.status in {"ok", "review"} else None
            out.append(
                c.model_copy(
                    update={
                        "verify_status": status or "review",
                        "judgment_seq": env.judgment_seq,
                        "evidence_text": public_evidence(evidence_text),
                    }
                )
            )
    return out


def public_evidence(text: str) -> str | None:
    return P.public_text(text) or None


def has_contradiction(claims: Sequence[Claim]) -> bool:
    """contradicted 가 하나라도 남으면 스냅샷 publish 불가."""
    return any(c.verify_status == "contradicted" for c in claims)
