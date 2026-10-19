"""판정기 입력(payload) 생성 (meta §2-1 P1~P9, §2-2 명제 템플릿, RA §6-3·§6-5·§6-7).

payload 는 JEV 도구 인자 그대로다(JEV 입력은 strict — 모르는 키는 거부된다). 그래서
- 임계 인자(auto_accept·minimum_margin·block_at·review_at·wrong_at·subject_at)를 절대 넣지 않는다(D6).
- 우리 쪽 메타(시점·단지 id)는 payload 가 아니라 purpose 키(``noul:ladder:<horizon>:<target_ym>:c<id>``)와
  후보 id(``complex:<id>`` / decide 는 slug ``complex_<id>``)에 담는다 → 정규화가 결정적이다.
- 모든 자유 텍스트는 ``public_text`` 로 연락처·비밀값을 미리 가린다(guard 는 마지막 방어선).
- 같은 집합이면 같은 payload 가 되도록 후보는 complex_id 순으로 정렬한다(캐시 적중, T7).

길이 한도(JEV 0.14.1): 증거 카드 ≤2,000자(우리 규칙), noul 명제 ≤2,000자·64개,
rerank 후보 ≤2,000자·250개·합 100,000자,
decide 후보 2~6·evidence ≤12,000·priorities ≤2,000·requirements ≤3(각 ≤500), verify 주장 ≤16(우리 규칙),
extract document ≤50,000·fields ≤32, audit records ≤32, classify item ≤2,000·items ≤64(배치).
"""

# ruff: noqa: E501  (한국어 docstring·판정기 문구)

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Final, Literal

from app.core.contracts_gen import RequirementPre, RequirementPreSet
from app.core.protocols import JudgePayload
from app.core.redact import redact_text
from app.judge.claims import CompoundClaimError, is_atomic, with_josa
from app.judge.guard import default_secrets

__all__ = [
    "BENCHMARK_PRICE_FIELDS",
    "BENCHMARK_PRICE_PURPOSE",
    "BENCHMARK_RESCREEN_TASK",
    "BENCHMARK_SCREEN_TASK",
    "CATALYST_CLASSES",
    "CATALYST_KIND_CLASSES",
    "CATALYST_SCREEN_TASK",
    "CATALYST_STAGE_CLASSES",
    "CLASSIFY_BATCH_MAX",
    "EVIDENCE_CARD_MAX",
    "EVIDENCE_CARD_ORDER",
    "EXTRACT_RESCREEN_TASK",
    "EXTRACT_SCREEN_TASK",
    "HEAD_TAIL_GAP",
    "HORIZONS",
    "INCLUSION_CLASSES",
    "INTAKE_CLASSES",
    "INTAKE_STATUS_BY_CLASS",
    "ITEM_TEXT_MAX",
    "NOT_CATALYST",
    "RERANK_MAX",
    "RERANK_QUERY",
    "SITE_IDENTITY_CLASSES",
    "SITE_OTHER_CLASS",
    "SITE_SAME",
    "UPCOMING_CLASSES",
    "UPCOMING_INCLUDED",
    "UPCOMING_NAME_FIELDS",
    "UPCOMING_SCREEN_TASK",
    "VERIFY_MAX_CLAIMS",
    "WAIT_NEW_DESCRIPTION",
    "WAIT_NEW_OPTION",
    "AuditRecord",
    "DecideCandidate",
    "EvidenceCard",
    "ExtractField",
    "Horizon",
    "LadderSpec",
    "annualized",
    "audit_payload",
    "benchmark_price_extract_fields",
    "benchmark_rescreen_text",
    "catalyst_screen_payload",
    "classify_catalyst_kind_payload",
    "classify_catalyst_payload",
    "classify_inclusion_batch_payload",
    "classify_inclusion_payload",
    "classify_intake_payload",
    "classify_site_identity_payload",
    "classify_upcoming_payload",
    "compare_payload",
    "decide_option_id",
    "decide_payload",
    "decide_purpose",
    "evidence_card_text",
    "extract_payload",
    "extract_rescreen_text",
    "head_tail",
    "ladder_specs",
    "noul_payload",
    "public_text",
    "rerank_needs_rerun",
    "rerank_payload",
    "rerank_purpose",
    "screen_payload",
    "target_for",
    "upcoming_extract_fields",
    "verify_payload",
]

Horizon = Literal["move_in_plus_1y", "asof_plus_3y", "asof_plus_5y"]
HORIZONS: Final[tuple[Horizon, ...]] = ("move_in_plus_1y", "asof_plus_3y", "asof_plus_5y")
EVIDENCE_CARD_MAX: Final = 2000
_LINE_MAX: Final = 400
EVIDENCE_CARD_ORDER: Final = (
    "단지",
    "생활권",
    "기준 타입",
    "현재 구매가",
    "입주",
    "전매",
    "거주의무",
    "계약금",
    "중도금",
    "접수",
    "비교군 실거래",
    "가격 갭",
    "벤치마크",
    "공급",
    "호재",
    "비고",
)
_CARD_REQUIRED: Final = 4  # 단지·생활권·기준 타입·현재 구매가 는 길이 초과 시에도 남긴다
VERIFY_MAX_CLAIMS: Final = 16
DECIDE_MAX: Final = 6
RERANK_QUERY: Final = (
    "현재 구매가로 분양받았을 때 입주 후 실거래가 상승 여력이 큰 민간분양 아파트 단지 "
    "(가격 갭·벤치마크·공급·유동성 근거 기준)"
)
_RERANK_TOTAL_MAX: Final = 100_000
RERANK_MAX: Final = 250
"""JEV rerank 후보 상한. 넘으면 나누지 않는다(§6-5 고정 앵커 = 한 호출) — ``judge.pipeline.p7_rerank`` 가 실패 앵커(error)로 남긴다."""
_DECIDE_EVIDENCE_MAX: Final = 12_000
_SLUG_RE: Final = re.compile(r"^[a-z][a-z0-9_-]*$")
_GAINS: Final = {"p5": 0.05, "p10": 0.10, "p20": 0.20}

_INCLUSION: Final = (
    ("private_sale_apt", "민간 사업주체(시행사·조합 등 민간 명의)가 분양하는 공동주택 아파트. 포함 대상. "
     "신탁사가 수탁자여도 실제 사업주체가 민간이면 여기. 예: 민영주택 일반분양 아파트"),
    ("public_sale", "LH·SH·지방공사 등 공공 사업주체가 분양하는 아파트(공공분양·국민주택). "
     "사업주체 명의가 공공기관이면 private_sale_apt 보다 우선"),
    ("public_rental", "공공 사업주체의 임대주택(국민임대·행복주택·공공지원 등). 분양 아님"),
    ("private_rental", "민간 사업주체의 임대주택(민간임대·장기일반민간임대). 분양 아님"),
    ("non_apartment", "아파트가 아닌 상품(오피스텔·도시형생활주택·생활숙박시설·상가). "
     "주상복합의 오피스텔 분양분만 다룬 공고도 여기"),
    ("out_of_scope", "청약·분양 공고가 아니거나 대상 지역·기간 밖의 자료"),
    ("manual_review", "사업주체 명의나 상품 유형을 자료만으로 정할 수 없을 때(사람 확인 필요)"),
)  # fmt: skip
NOT_CATALYST: Final = "호재 아님"
"""P4(b) 호재 분류의 '호재 아님' 클래스(D10-6) — 이 결과면 후보를 폐기하고 기록한다(G2 파이프라인)."""
_CATALYST: Final = (
    ("확정", "고시·승인·착공 등 공식 절차로 확정된 호재(관보·지자체 고시·국토부 발표 근거)"),
    ("계획", "공식 계획(기본계획·종합계획)에 반영됐으나 승인·착공 전인 호재"),
    ("추진", "예비타당성·용역·협의 등 추진 단계로 공식 계획 반영 전인 호재"),
    ("언론", "언론·홍보 자료에만 나오고 공식 근거가 없는 호재"),
    ("미확정", "근거가 불분명하거나 상충해 단계를 정할 수 없는 호재"),
    (NOT_CATALYST, "교통·개발·학교·상업·생활인프라 호재가 아닌 자료. 아파트 분양 광고·청약 일정·"
     "모델하우스·분양가·경쟁률·시세·대출·세금 기사, 단지 홍보문은 여기(호재 단계보다 우선). "
     "예: '○○ 다음 주 1순위 청약'"),
)  # fmt: skip
_CATALYST_KIND: Final = (
    ("교통", "철도·지하철·GTX·도로·IC·버스 노선 등 교통망 신설·연장·개선"),
    ("개발", "도시개발·택지·재개발·산업단지·업무지구·대규모 복합개발 사업"),
    ("학교", "초·중·고 신설·이전·학군 관련 사업"),
    ("상업", "대형 상업시설·쇼핑몰·백화점·상권 개발"),
    ("생활인프라", "공원·병원·도서관·체육·문화시설 등 생활 편의시설"),
    ("기타", "위 다섯 가지에 들지 않거나 종류를 자료만으로 정할 수 없을 때"),
)  # fmt: skip
CATALYST_SCREEN_TASK: Final = (
    "부동산 호재(교통·개발·학교·상업·생활인프라 사업) 관련성 검사 — "
    "이 기사가 지역의 호재 사업 자체를 다루는가. "
    "아파트 분양 광고·청약 일정·분양가·경쟁률·시세 기사는 호재가 아니다"
)
"""P1 screen 의 purpose(뉴스 → 호재 후보 전, D10-6). 관련 없으면 JEV 가 skip 을 준다."""
_INTAKE: Final = (
    ("open", "지금 청약·계약 접수를 받고 있다(선착순·동호지정 계약 중, 잔여 세대 분양 중, "
     "무순위·임의공급 접수 중 등). 문구가 현재 진행 중인 접수를 말해야 한다"),
    ("pending", "접수 일정이 공지됐거나 예정이지만 아직 시작 전이다"
     "(오픈 예정, 공고 예정, 견본주택 오픈 예정 등)"),
    ("closed", "접수가 끝났다(분양 완료, 완판, 계약 마감, 접수 종료)"),
    ("unknown", "문구만으로 지금 접수 가능 여부를 정할 수 없다"
     "(메뉴 이름·일반 안내·광고 문구뿐이거나 서로 맞지 않음)"),
)  # fmt: skip
UPCOMING_SCREEN_TASK: Final = (
    "공고 예정 아파트 단지 신호 검사(트랙 A, meta §1-3 #1) — 이 기사 발췌가 특정 아파트 단지(이름이 있는 단지)의 "
    "앞으로 12개월 안 분양(입주자모집공고·공급) 예정을 알리는가. 이미 분양·청약·입주를 마친 단지, 오피스텔·상가만 다룬 "
    "기사, 시장 일반론·인구 이동 통계만 있는 기사는 해당 없음"
)
"""D20-2 P1 screen 의 purpose(뉴스 → 공고 예정 단지 후보 전). 관련 없으면 JEV 가 skip 을 준다."""
UPCOMING_NAME_FIELDS: Final = ("complex_1", "complex_2", "complex_3")
"""D20-2 P2 extract: 기사 하나가 알린 공고 예정 단지 이름(최대 3개)."""
UPCOMING_INCLUDED: Final = "private_sale_apt"
"""D20-2 공고 예정 classify 에서 단지 후보가 되는 클래스(포함/제외 클래스와 같은 id — 단지 inclusion_class 로 그대로 쓴다)."""
_UPCOMING: Final = (
    (UPCOMING_INCLUDED, "분석 지역 안에서 민간 사업주체가 앞으로 12개월 안에 분양(입주자모집공고)할 아파트 단지"
     "(주상복합의 아파트 포함). 포함 대상"),
    ("public_sale", "LH·SH·지방공사 등 공공 사업주체의 공공분양 아파트"),
    ("rental", "공공·민간 임대주택(분양 아님)"),
    ("non_apartment", "오피스텔·도시형생활주택·생활숙박시설·상가 등 아파트가 아닌 상품"),
    ("already_supplied", "이미 분양·청약·입주를 마쳤거나 12개월 안 공고 예정이 아닌 단지"),
    ("out_of_region", "분석 지역 밖의 단지"),
    ("unclear", "단지·지역·사업주체를 자료만으로 정할 수 없을 때"),
)  # fmt: skip
UPCOMING_CLASSES: Final = tuple({"id": i, "description": d} for i, d in _UPCOMING)
"""D20-2 공고 예정 단지 classify 7클래스(지역·민간분양·공고 예정 여부)."""
SITE_SAME: Final = "same_complex"
"""D21-5 공식 홈페이지 동일성 classify 에서 '그 단지의 페이지'인 클래스 — auto 일 때만 접수 classify 입력으로 쓴다."""
SITE_OTHER_CLASS: Final = "other_complex"
"""D22-4(R4 3차 N11) 동일성 classify 에서 '다른 단지의 페이지'인 클래스 — auto 일 때만 사유 '공식 홈페이지가 다른 단지'."""
_SITE_IDENTITY: Final = (
    (SITE_SAME, "페이지 문구가 위에 적힌 그 단지(이름·위치가 같은 분양 사업)의 공식 분양·홍보 페이지다"),
    (SITE_OTHER_CLASS, "다른 단지·다른 지역·다른 사업의 분양 페이지다(도메인을 다른 사업이 쓰고 있음 등)"),
    ("unclear", "페이지 문구만으로 그 단지의 페이지인지 정할 수 없다(메뉴·광고 문구뿐 등)"),
)  # fmt: skip
SITE_IDENTITY_CLASSES: Final = tuple({"id": i, "description": d} for i, d in _SITE_IDENTITY)
"""D21-5(R4 재시험 N6) 공식 홈페이지 동일성 3클래스 — 청약홈에 등록된 홈페이지 주소가 지금 다른 단지 페이지일 수 있다."""
CLASSIFY_BATCH_MAX: Final = 64
"""JEV classify items 상한(배치 1회)."""
INTAKE_CLASSES: Final = tuple({"id": i, "description": d} for i, d in _INTAKE)
"""접수 상태 4클래스(공식 홈페이지 DOM 텍스트·팝업 문구 → 가능/미정/불가/확인 불가)."""
INTAKE_STATUS_BY_CLASS: Final = {"open": "가능", "pending": "미정", "closed": "불가", "unknown": "확인 불가"}
"""classify 클래스 id → intake_status.status. 미해결(review)은 매핑하지 않는다(→ '확인 불가(판정 미해결)')."""
INCLUSION_CLASSES: Final = tuple({"id": i, "description": d} for i, d in _INCLUSION)
"""P4(a) 포함/제외 7클래스(사업주체 명의 기준, contracts ClassifyResult 설명과 같은 id)."""
CATALYST_CLASSES: Final = tuple({"id": i, "description": d} for i, d in _CATALYST)
"""P4(b) 호재 단계 5클래스 + '호재 아님'(D10-6)."""
CATALYST_STAGE_CLASSES: Final = tuple(i for i, _ in _CATALYST if i != NOT_CATALYST)
"""호재 단계 5종(catalyst.stage 값) — '호재 아님'은 단계가 아니다."""
CATALYST_KIND_CLASSES: Final = tuple({"id": i, "description": d} for i, d in _CATALYST_KIND)
"""P4(b) 호재 종류 6클래스(catalyst.kind 값 = 계약 CATALYST_KIND, D10-6)."""


def public_text(text: str | None) -> str:
    """판정기로 나가는 자유 텍스트: 전화·주민번호·이메일·비밀값을 가리고 앞뒤 공백 정리."""
    return redact_text(text or "", default_secrets()).strip()


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


ITEM_TEXT_MAX: Final = 2000
"""classify 항목 텍스트 상한(``_classify_items`` 의 자르기와 같다)."""
HEAD_TAIL_GAP: Final = "\n…\n"


def head_tail(text: str, limit: int, *, tail_share: float = 0.4) -> str:
    """``limit`` 자 안에 맞춘 페이지 문구: 넘치면 앞부분 + ``HEAD_TAIL_GAP`` + 뒷부분(뒤 ``tail_share`` 비율).

    R6-INTAKE: 공식 홈페이지 문구는 앞이 메뉴·회전 배너이고 시행·시공·현장 주소·총 세대수는 맨 아래 꼬리말에 있다. 앞에서
    1500자만 자르면 그 단지인지 가릴 근거(꼬리말)가 빠져 동일성 classify 가 review 로 남았다(인천 첫 실행 — 포레나더샵
    인천시청역 등). 자르기 규칙(산술)일 뿐 문구를 고르지 않는다. 같은 입력이면 같은 출력(결정적)."""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    room = limit - len(HEAD_TAIL_GAP)
    if room <= 0:
        return text[:limit]
    tail = int(room * tail_share)
    head = room - tail
    return text[:head].rstrip() + HEAD_TAIL_GAP + text[len(text) - tail :].lstrip()


# ====================================================================== 증거 카드


@dataclass(frozen=True, slots=True)
class EvidenceCard:
    """단지 증거 카드 입력(표시 문자열). 수치는 호출자(WP7)가 Fact 표시 규칙으로 만든 문자열을 넣는다."""

    complex_id: int
    name: str
    basis_type: str | None = None  # 판정 기준 타입(84㎡에 가장 가까운 것), 예 '84A'
    price_range: str | None = None  # 예 '5.78~6.08억'
    price_composition: str | None = None  # 예 '공급가+발코니'
    move_in_ym: str | None = None  # 'YYYY-MM'
    immediate_move_in: bool = False
    living_area: str | None = None
    resale: str | None = None
    residency: str | None = None
    down_payment: str | None = None
    interim: str | None = None
    intake: str | None = None
    comparables: str | None = None
    gap: str | None = None
    benchmark: str | None = None
    supply: str | None = None
    catalysts: Sequence[str] = field(default_factory=tuple)
    notes: str | None = None


def _card_lines(c: EvidenceCard) -> list[tuple[str, str | None]]:
    price = c.price_range
    if price and c.price_composition:
        price = f"{price} ({c.price_composition})"
    move_in = "즉시 입주" if c.immediate_move_in else c.move_in_ym
    return [
        ("단지", c.name),
        ("생활권", c.living_area),
        ("기준 타입", f"전용 {c.basis_type}" if c.basis_type else None),
        ("현재 구매가", price),
        ("입주", move_in),
        ("전매", c.resale),
        ("거주의무", c.residency),
        ("계약금", c.down_payment),
        ("중도금", c.interim),
        ("접수", c.intake),
        ("비교군 실거래", c.comparables),
        ("가격 갭", c.gap),
        ("벤치마크", c.benchmark),
        ("공급", c.supply),
        ("호재", "; ".join(x for x in c.catalysts if x) or None),
        ("비고", c.notes),
    ]


def evidence_card_text(card: EvidenceCard, *, limit: int = EVIDENCE_CARD_MAX) -> str:
    """항목 순서 고정(EVIDENCE_CARD_ORDER) ``항목: 값`` 줄들.

    길이 초과 시 줄을 자르고, 그래도 넘치면 뒤 항목부터 뺀다(앞 4항목은 남긴다).
    """
    lines = [f"{k}: {_cut(public_text(v), _LINE_MAX)}" for k, v in _card_lines(card) if v and public_text(v)]
    while len("\n".join(lines)) > limit and len(lines) > _CARD_REQUIRED:
        lines.pop()
    return _cut("\n".join(lines), limit)


# ====================================================================== 사다리 (P6)


@dataclass(frozen=True, slots=True)
class LadderSpec:
    complex_id: int
    horizon: Horizon
    target_ym: str
    target_label: str
    months_from_asof: int
    propositions: tuple[tuple[str, str], ...]  # (p5|p10|p20|p_flat, 명제)
    purpose: str


def _ym(d: date) -> tuple[int, int]:
    return d.year, d.month


def _add_months(year: int, month: int, n: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + n
    return total // 12, total % 12 + 1


def _parse_ym(ym: str) -> tuple[int, int]:
    y, m = ym.split("-")[:2]
    return int(y), int(m)


def target_for(
    horizon: Horizon, *, asof_date: str, move_in_ym: str | None, immediate: bool = False
) -> tuple[str, int, bool] | None:
    """(target_ym, months_from_asof, 즉시입주로 처리했는가). 입주월을 모르면 move_in_plus_1y 는 None.

    move_in_plus_1y = 입주월 + 12개월(입주월이 기준월 이전이거나 즉시 입주면 기준일 + 12개월),
    asof_plus_3y = 기준일 + 36개월, asof_plus_5y = 기준일 + 60개월 — 뒤 둘은 단지와 무관하다(T10).
    """
    from app.analysis.ladder import ladder_target  # 한 구현(R3 3차 RA 부분: 사다리 목표 계산 중복 제거)

    t = ladder_target(horizon, asof_date, move_in_ym=move_in_ym, immediate=immediate)
    if t is None:
        return None
    ay, am = _ym(date.fromisoformat(asof_date))
    imm = horizon == "move_in_plus_1y" and (immediate or not move_in_ym or _parse_ym(move_in_ym) <= (ay, am))
    return t.target_ym, t.months_from_asof, imm


def _half_label(target_ym: str) -> str:
    y, m = _parse_ym(target_ym)
    return f"{y} {'상반기' if m <= 6 else '하반기'}"


def ladder_specs(
    card: EvidenceCard, *, asof_date: str, horizons: Iterable[Horizon] = HORIZONS
) -> list[LadderSpec]:
    """meta §2-2 명제 템플릿 × horizon. horizon 1개당 noul 1회, 명제 4개(+5/+10/+20/보합·하락)."""
    specs: list[LadderSpec] = []
    for horizon in horizons:
        t = target_for(
            horizon, asof_date=asof_date, move_in_ym=card.move_in_ym, immediate=card.immediate_move_in
        )
        if t is None:
            continue
        target_ym, months, immediate = t
        label = _half_label(target_ym)
        if horizon == "move_in_plus_1y":
            when = "기준일+1년 시점" if immediate else f"입주({card.move_in_ym}) 후 1년 시점"
        else:
            when = f"기준일+{3 if horizon == 'asof_plus_3y' else 5}년 시점"
        price = card.price_range or "확인 불가"
        if card.price_composition:
            price = f"{price}, {card.price_composition}"
        unit = with_josa(f"전용 {card.basis_type}", "을") if card.basis_type else "기준 타입을"
        base = (
            f"{public_text(card.name)} {unit} {asof_date} 현재 구매가({public_text(price)})로 매수할 경우, "
            f"{when}인 {label} 실거래가가 현재 구매가 대비 "
        )
        props = (
            ("p5", base + "+5% 이상이다"),
            ("p10", base + "+10% 이상이다"),
            ("p20", base + "+20% 이상이다"),
            ("p_flat", base + "이하(보합·하락)이다"),
        )
        purpose = f"noul:ladder:{horizon}:{target_ym}:c{card.complex_id}"
        specs.append(LadderSpec(card.complex_id, horizon, target_ym, label, months, props, purpose))
    return specs


def noul_payload(
    spec: LadderSpec, *, card_text: str, benchmark_text: str | None = None, policy_text: str | None = None
) -> JudgePayload:
    """명제 4개 + 컨텍스트(증거 카드 · 지역 벤치마크 · 제도). 임계값 없음."""
    context = [
        {"id": cid, "text": public_text(text)}
        for cid, text in (("card", card_text), ("benchmark", benchmark_text), ("policy", policy_text))
        if text and public_text(text)
    ]
    payload: JudgePayload = {"propositions": [_cut(t, 2000) for _, t in spec.propositions]}
    if context:
        payload["context"] = context
    return payload


def annualized(months_from_asof: int) -> dict[str, float | None]:
    """임계 상승률 g 의 연율 r = (1+g)^(12/m) − 1 (RA §6-3), 소수 4자리(``analysis.ladder.annualize``)."""
    if months_from_asof < 1:
        return {k: None for k in _GAINS}
    from app.analysis.ladder import annualize

    return {k: float(annualize(Decimal(str(g)), months_from_asof)) for k, g in _GAINS.items()}


# ====================================================================== rerank (P7)


def rerank_purpose(*, region_id: int) -> str:
    return f"rerank:region:{region_id}"


def rerank_needs_rerun(prev_ids: Iterable[int], current_ids: Iterable[int]) -> bool:
    """후보 집합이 바뀌면 전체(과거 후보 포함)를 1회 재호출한다(§6-5 고정 앵커, T7)."""
    return set(prev_ids) != set(current_ids)


def rerank_payload(cards: Sequence[EvidenceCard], *, query: str = RERANK_QUERY) -> JudgePayload:
    """모든 후보를 한 번에(complex_id 순, 중복 제거). 후보 텍스트는 증거 카드, 합 100,000자 안으로 줄인다."""
    unique = {c.complex_id: c for c in cards}
    if not unique:
        raise ValueError("rerank 후보가 없다")
    if len(unique) > RERANK_MAX:
        raise ValueError(f"rerank 후보는 {RERANK_MAX}개까지")
    per = min(EVIDENCE_CARD_MAX, _RERANK_TOTAL_MAX // len(unique) - 50)
    candidates = [
        {"id": f"complex:{cid}", "text": evidence_card_text(unique[cid], limit=per)} for cid in sorted(unique)
    ]
    return {"query": _cut(query, 2000), "candidates": candidates}


# ====================================================================== decide (P8)


@dataclass(frozen=True, slots=True)
class DecideCandidate:
    card: EvidenceCard
    pre: RequirementPreSet | None = None  # RequirementPrecalc.evaluate 결과(WP4) → 증거에 그대로 삽입


WAIT_NEW_OPTION: Final = "wait_new"
WAIT_NEW_DESCRIPTION: Final = (
    "모집공고 대기 — 12개월 내 공고 예정 단지를 기다림(지금 후보 대신 가점제 1순위 청약)"
)
"""P8 가상 후보(보고서 §8-2·§12-5-2 '모집공고 대기'). decision 행은 option_key 'wait_new'·complex_id null."""


def decide_option_id(complex_id: int) -> str:
    return f"complex_{complex_id}"


def decide_purpose(scenario: str | int) -> str:
    return f"decide:scenario_{scenario}"


def _pre_line(label: str, pre: RequirementPre | None) -> str:
    if pre is None:
        return f"{label}=확인 불가(사전 계산 없음)"
    return f"{label}={pre.status} — {public_text(pre.evidence)}"


def decide_payload(
    *,
    scenario_name: str,
    requirements: tuple[str, str, str],
    candidates: Sequence[DecideCandidate],
    priorities: str,
    include_wait_new: bool = False,
    extra_evidence: str | None = None,
    wait_new_evidence: str | None = None,
) -> JudgePayload:
    """후보 ≤6(단지 + 가상 후보 '모집공고 대기') + 증거(카드 + 요건 사전 계산 문자열)
    + 우선순위 + 요건 3개. 임계값 없음.

    요건 순서는 (접근 가능성, 규제 제약, 자금) 고정 — 정규화가 순서로 access/regulation/funds 를 매긴다.
    ``include_wait_new``: 가상 후보 ``wait_new``(12개월 내 공고 예정 단지를 기다림,
    보고서 §8-2·§12-5-2) — 근거 ``wait_new_evidence``(지역 (A) 트랙 공고 예정 목록 요약)는
    단지 블록 뒤 ``[wait_new]`` 블록으로 들어간다.
    """
    n_options = len(candidates) + (1 if include_wait_new else 0)
    if not 2 <= n_options <= DECIDE_MAX:
        raise ValueError(f"decide 후보는 2~{DECIDE_MAX}개 (지금 {n_options})")
    if len({c.card.complex_id for c in candidates}) != len(candidates):
        raise ValueError("decide 후보 complex_id 중복")
    if len(requirements) != 3:
        raise ValueError("요건은 (접근 가능성, 규제 제약, 자금) 3개")
    ordered = sorted(candidates, key=lambda c: c.card.complex_id)
    header = public_text(extra_evidence) if extra_evidence else ""
    wait_block = ""
    if include_wait_new:
        wait_body = public_text(wait_new_evidence) if wait_new_evidence else "공고 예정 목록 없음"
        wait_block = f"[{WAIT_NEW_OPTION}] {WAIT_NEW_DESCRIPTION}\n{_cut(wait_body, EVIDENCE_CARD_MAX)}"
    budget = (_DECIDE_EVIDENCE_MAX - len(header) - len(wait_block) - 200) // max(1, len(ordered))
    blocks: list[str] = []
    for c in ordered:
        pre = c.pre
        pre_text = "요건 사전 계산: " + "; ".join(
            [
                _pre_line("접근 가능성", pre.access if pre else None),
                _pre_line("규제 제약", pre.regulation if pre else None),
                _pre_line("자금", pre.funds if pre else None),
            ]
        )
        head = f"[{decide_option_id(c.card.complex_id)}] {public_text(c.card.name)}"
        card_budget = max(200, budget - len(head) - len(pre_text) - 4)
        blocks.append(
            f"{head}\n{evidence_card_text(c.card, limit=min(EVIDENCE_CARD_MAX, card_budget))}\n{pre_text}"
        )
    if wait_block:
        blocks.append(wait_block)
    evidence = "\n\n".join([header, *blocks] if header else blocks)
    options: list[dict[str, str]] = []
    for c in ordered:
        desc = f"{public_text(c.card.name)}"
        if c.card.basis_type:
            desc += f" — 전용 {c.card.basis_type}"
        if c.card.price_range:
            desc += f", 현재 구매가 {public_text(c.card.price_range)}"
        options.append({"id": decide_option_id(c.card.complex_id), "description": _cut(desc, 2000)})
    if include_wait_new:
        options.append({"id": WAIT_NEW_OPTION, "description": WAIT_NEW_DESCRIPTION})
    decision = (
        f"상황 '{public_text(scenario_name)}'에서 후보 단지 중 어느 것을 우선 검토할 것인가 "
        "(투자 권유가 아닌 상대 비교, 증거의 수치와 요건 사전 계산만 근거로)"
    )
    return {
        "decision": _cut(decision, 1500),
        "evidence": _cut(evidence, _DECIDE_EVIDENCE_MAX),
        "priorities": _cut(public_text(priorities), 2000),
        "candidates": options,
        "requirements": [_cut(public_text(r), 500) for r in requirements],
    }


# ====================================================================== verify (P9)


def verify_payload(claims: Sequence[str], evidence: Sequence[tuple[str, str]]) -> JudgePayload:
    """원자 주장 ≤16 + 근거 항목. 복합 문장이 섞이면 ``CompoundClaimError`` (T6)."""
    if not claims:
        raise ValueError("verify 주장이 없다")
    if len(claims) > VERIFY_MAX_CLAIMS:
        raise ValueError(f"verify 주장은 {VERIFY_MAX_CLAIMS}건까지 (지금 {len(claims)})")
    for c in claims:
        if not is_atomic(c):
            raise CompoundClaimError("복합 문장은 ClaimSplitter 로 나눈 뒤 verify 에 보낸다")
    items = [{"id": eid, "text": public_text(text)} for eid, text in evidence if public_text(text)]
    if not items:
        raise ValueError("verify 근거가 없다")
    return {"claims": [_cut(public_text(c), 2000) for c in claims], "evidence": items}


# ====================================================================== P1~P5


def screen_payload(text: str, *, task: str) -> JudgePayload:
    body = public_text(text)
    if not body:
        raise ValueError("screen 텍스트가 비었다")
    return {"text": body, "purpose": public_text(task)}


BENCHMARK_SCREEN_TASK: Final = "지역 아파트 벤치마크(같은 생활권 분양가 → 입주 후 실거래) 요약 — 상승 확률 판정(noul) 컨텍스트로 쓰기 전 입력 검사"
"""P1 screen(meta §2-1 '벤치마크·호재 텍스트')의 purpose — P6 noul 컨텍스트 ``benchmark`` 로 넣기 전."""
BENCHMARK_RESCREEN_TASK: Final = (
    "부동산 시세 자료 — 아파트 단지별 분양가와 입주 후 실거래가 비교 표가 수치 근거로 쓸 만한 입력인가"
)
"""P1 재screen(skip 이면 purpose 를 단계에 맞게 바꿔 다른 입력으로, meta §2-1 P1)."""


def benchmark_rescreen_text(text: str) -> str:
    """벤치마크 재screen 입력(다른 입력): 머리 설명 + 사례 줄만(머리 요약 줄 제외)."""
    rows = [line for line in text.splitlines()[1:] if line.strip()]
    return "아파트 단지별 분양가와 입주 후 실거래가 비교(분양권 제외):\n" + "\n".join(rows or [text])


EXTRACT_SCREEN_TASK: Final = "청약 공고문 수치 추출 전 입력 검사"
EXTRACT_RESCREEN_TASK: Final = (
    "청약 입주자모집공고 본문·표에서 아래 '추출 대상' 항목의 값을 찾기 전 입력 검사"
)


def extract_rescreen_text(text: str, field_descriptions: Sequence[str]) -> str:
    """공고문 조각 재screen 입력(다른 입력): 추출 대상 항목 머리 + 같은 조각."""
    head = ", ".join(dict.fromkeys(d for d in field_descriptions if d))
    return f"추출 대상: {head}\n{text}" if head else f"추출 대상: 청약 공고 수치\n{text}"


@dataclass(frozen=True, slots=True)
class ExtractField:
    id: str  # slug ^[a-z][a-z0-9_-]*$
    pattern: str  # JavaScript 정규식(구분자 없이)
    description: str
    flags: str | None = None


def extract_payload(
    document: str, fields: Sequence[ExtractField], *, purpose: str | None = None
) -> JudgePayload:
    if not 1 <= len(fields) <= 32:
        raise ValueError("extract 필드는 1~32개")
    out_fields: list[dict[str, Any]] = []
    for f in fields:
        if not _SLUG_RE.match(f.id) or len(f.id) > 64:
            raise ValueError(f"extract 필드 id 형식: {f.id!r}")
        item: dict[str, Any] = {
            "id": f.id,
            "pattern": f.pattern[:500],
            "description": _cut(f.description, 2000),
        }
        if f.flags:
            item["flags"] = f.flags[:8]
        out_fields.append(item)
    payload: JudgePayload = {"document": _cut(public_text(document), 50_000), "fields": out_fields}
    if purpose:
        payload["purpose"] = purpose
    return payload


@dataclass(frozen=True, slots=True)
class AuditRecord:
    id: str
    request: str
    value: str


def audit_payload(source: str, records: Sequence[AuditRecord]) -> JudgePayload:
    if not 1 <= len(records) <= 32:
        raise ValueError("audit 레코드는 1~32개")
    for r in records:
        if not _SLUG_RE.match(r.id):
            raise ValueError(f"audit 레코드 id 형식: {r.id!r}")
    return {
        "source": _cut(public_text(source), 50_000),
        "records": [
            {"id": r.id, "request": _cut(r.request, 500), "value": _cut(public_text(r.value), 2000)}
            for r in records
        ],
    }


def _classify_items(items: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
    if not 1 <= len(items) <= CLASSIFY_BATCH_MAX:
        raise ValueError(f"classify 항목은 1~{CLASSIFY_BATCH_MAX}개 (지금 {len(items)})")
    ids = [i for i, _ in items]
    if len(set(ids)) != len(ids):
        raise ValueError("classify 항목 id 중복")
    return [{"id": i, "text": _cut(public_text(t), ITEM_TEXT_MAX)} for i, t in items]


def classify_inclusion_payload(*, item_id: str, text: str) -> JudgePayload:
    """P4(a) 포함/제외 — 사업주체 명의 기준 7클래스(단지 1개)."""
    return classify_inclusion_batch_payload([(item_id, text)])


def classify_inclusion_batch_payload(items: Sequence[tuple[str, str]]) -> JudgePayload:
    """P4(a) 배치: 단지 N개(≤64)를 1회에. 항목 순서는 호출자가 정한다(같은 집합이면 같은 순서 — 캐시 적중)."""
    return {
        "items": _classify_items(items),
        "classes": [dict(c) for c in INCLUSION_CLASSES],
        "purpose": "청약 공고 단지의 포함/제외 분류(사업주체 명의·상품 유형 기준)",
    }


def classify_intake_payload(items: Sequence[tuple[str, str]]) -> JudgePayload:
    """접수 상태 분류(배치 ≤64): 항목 = (id, 공식 홈페이지 DOM 텍스트·팝업 문구). 4클래스, 임계값 없음.

    가능/미정/불가는 판정기 auto 일 때만 쓴다(AGENTS 규칙 3) — 프로그램은 문구를 해석하지 않는다.
    """
    return {
        "items": _classify_items(items),
        "classes": [dict(c) for c in INTAKE_CLASSES],
        "purpose": "분양 단지 공식 홈페이지·팝업 문구로 본 현재 청약·계약 접수 상태 분류",
    }


def classify_site_identity_payload(items: Sequence[tuple[str, str]]) -> JudgePayload:
    """D21-5 공식 홈페이지 동일성(배치 ≤64): 항목 = (id, '단지: 이름 / 위치: 주소 / 페이지 문구: …'). 3클래스, 임계값 없음.
    프로그램은 이름 문자열이 페이지에 있는지 세지 않는다(같은 단지인지 판단은 판정기만 — 규칙 3)."""
    return {
        "items": _classify_items(items),
        "classes": [dict(c) for c in SITE_IDENTITY_CLASSES],
        "purpose": "청약홈에 등록된 공식 홈페이지 주소의 지금 페이지가 그 분양 단지의 페이지인지 분류",
    }


def classify_catalyst_payload(*, item_id: str, text: str) -> JudgePayload:
    """P4(b) 호재 단계 5클래스 + '호재 아님'(D10-6: 분양 기사는 호재 아님)."""
    return {
        "items": [{"id": item_id, "text": _cut(public_text(text), 2000)}],
        "classes": [dict(c) for c in CATALYST_CLASSES],
        "purpose": "부동산 호재(교통·개발·생활인프라)의 진행 단계 분류 — 호재가 아니면 '호재 아님'",
    }


def classify_catalyst_kind_payload(*, item_id: str, text: str) -> JudgePayload:
    """P4(b) 호재 종류 6클래스(교통·개발·학교·상업·생활인프라·기타, D10-6) — 종류를 키워드로 정하지 않는다."""
    return {
        "items": [{"id": item_id, "text": _cut(public_text(text), 2000)}],
        "classes": [dict(c) for c in CATALYST_KIND_CLASSES],
        "purpose": "부동산 호재 사업의 종류 분류",
    }


def upcoming_extract_fields() -> list[ExtractField]:
    """D20-2 P2 extract 필드: 기사가 알린 공고 예정 단지 이름 1~3(따옴표 안 이름이 후보 위치 — 값을 고르는 것은 판정기)."""
    quoted = "[‘'\"“][^’'\"”]{2,40}[’'\"”]"
    return [
        ExtractField(
            id=f,
            pattern=quoted,
            description=f"기사가 앞으로 분양(공급) 예정이라고 알린 {n}번째 아파트 단지 이름. 없으면 찾지 못함",
        )
        for n, f in enumerate(UPCOMING_NAME_FIELDS, start=1)
    ]


BENCHMARK_PRICE_FIELDS: Final = ("price_84", "price_per_3_3", "public_sale")
"""D31-3 P2 extract: 2020년 이전 분양 단지의 언론 기사 분양가(전용 84㎡ 값 · 3.3㎡당 평균 · 공공분양 표현)."""
BENCHMARK_PRICE_PURPOSE: Final = "아파트 단지 분양가 기사 발췌에서 그 단지의 최초 분양가 추출"


def benchmark_price_extract_fields(name: str) -> list[ExtractField]:
    """D31-3 P2 extract 필드(단지 이름을 설명에 넣는다 — 다른 단지 값과 가르는 것은 판정기). 정규식은 후보 위치만 준다."""
    who = f"'{name}' 단지"
    return [
        ExtractField(
            id="price_84",
            pattern=r"\d+\s?억(?:\s?\d+\s?천)?(?:\s?\d[\d,]*)?\s?만?\s?원",
            description=(
                f"{who}의 전용 84㎡ 주택형 최초 분양가(분양 때 공급가격). 범위로 나오면 가장 높은 값. 다른 단지의 가격, "
                "분양권 시세·프리미엄, 입주 뒤 실거래가·호가는 아님. 없으면 찾지 못함"
            ),
        ),
        ExtractField(
            id="price_per_3_3",
            pattern=r"\d[\d,]{2,5}\s?만\s?원",
            description=(
                f"{who}의 3.3㎡(평)당 평균 분양가(최초 분양). 다른 단지의 값, 주변 시세, 입주 뒤 실거래 평당가는 아님. "
                "없으면 찾지 못함"
            ),
        ),
        ExtractField(
            id="public_sale",
            pattern="공공분양",
            description=(
                f"{who}가 공공분양(LH·지방공사 등 공공 사업주체가 공급하는 분양) 단지라고 밝힌 표현. 민간분양이거나 다른 "
                "단지 이야기면 찾지 못함"
            ),
        ),
    ]


def classify_upcoming_payload(items: Sequence[tuple[str, str]]) -> JudgePayload:
    """D20-2 공고 예정 단지 후보 classify(배치 ≤64): 항목 = (id, 지역 + 단지 이름 + 기사 제목·발췌)."""
    return {
        "items": _classify_items(items),
        "classes": [dict(c) for c in UPCOMING_CLASSES],
        "purpose": "기사에 나온 공고 예정 아파트 단지가 분석 지역 안 민간분양(12개월 안 공고 예정)인지 분류",
    }


def catalyst_screen_payload(
    *, title: str, excerpt: str | None = None, url: str | None = None
) -> JudgePayload:
    """P1 screen(뉴스 → 호재 후보 전, D10-6): 제목·발췌·링크 + 호재 관련성 목적.
    통과(pass)분만 후보가 된다."""
    parts = (f"제목: {title}", f"발췌: {excerpt}" if excerpt else "", f"링크: {url}" if url else "")
    text = "\n".join(p for p in parts if p)
    return screen_payload(_cut(text, 4000), task=CATALYST_SCREEN_TASK)


def compare_payload(
    passage_a: str, passage_b: str, *, aspects: Sequence[str] | None = None, purpose: str | None = None
) -> JudgePayload:
    """P5 출처 충돌 — 같은 사실의 두 출처 문장."""
    payload: JudgePayload = {
        "passage_a": _cut(public_text(passage_a), 20_000),
        "passage_b": _cut(public_text(passage_b), 20_000),
    }
    if aspects:
        payload["aspects"] = [_cut(a, 200) for a in aspects[:10]]
    if purpose:
        payload["purpose"] = purpose
    return payload
