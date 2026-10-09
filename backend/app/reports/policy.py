"""보고서의 판정 범위·현재 구매가 계산 지점 — 각각 함수 하나(R3 수정 F4, D9-1·M3).

F2 가 같은 라운드에 공용 함수 ``app.analysis.scope.judge_scope``·``app.analysis.price_view`` 를 만든다.
그것이 main 에 머지되면 아래 두 함수의 **본문 한 줄**을 공용 함수 호출로 바꾼다(호출부 ``data.py`` 는 그대로).
그때까지는 같은 규칙(meta §1-3-4 = D9-1, §6-1)을 여기서 계산한다
— 규칙은 판단이 아니다(판정기 결과·사실만 읽음).

- ``judge_scope(...)`` → ``"제외" | "보류" | "미해결" | "참고" | "판정 대상"`` (계약 .4 값 집합)
- ``current_price_source(basis, payments)`` → 현재 구매가 원천(최신 공고 ``payment_terms.price_by_type`` 우선,
  없으면 ``complex_type``)과 그 출처 행 키
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from app.models import ComplexType, PaymentTerms

__all__ = [
    "EXCLUDED_CLASSES",
    "JUDGE_SCOPE_TEXT",
    "JudgeScope",
    "PriceSource",
    "current_price_source",
    "current_terms",
    "judge_scope",
]

JudgeScope = Literal["제외", "보류", "미해결", "참고", "판정 대상"]

# meta §1-3-4 · D9-1 표시 문구
JUDGE_SCOPE_TEXT: Final[dict[str, str]] = {
    "판정 대상": "판정 대상",
    "보류": "보류 — 공고 후 재판정",
    "미해결": "미해결(분류 판정 미해결)",
    "참고": "참고 후보(순위만)",
    "제외": "제외",
}
EXCLUDED_CLASSES: Final = frozenset(
    {"public_sale", "public_rental", "private_rental", "non_apartment", "out_of_scope"}
)
INCLUDED_CLASS: Final = "private_sale_apt"
BOUNDARY: Final = "범위 경계"


def judge_scope(
    *,
    inclusion_class: str,
    inclusion_decision: str | None,
    has_price: bool,
    intake_status: str | None,
) -> JudgeScope:
    """판정 범위(D9-1). F2 머지 후 본문 = ``return analysis.scope.judge_scope(...)``.

    - 제외: classify(auto)가 제외 클래스, 또는 '범위 경계'(주소 매칭 실패 — classify 결과가 아님)
    - 미해결: classify 가 auto 가 아님(review·manual_review·미분류) — 판정 대상 아님, 사다리·점수 없음
    - 보류: 포함 확정이나 분양가 미공개(공고 전)
    - 참고: 포함 확정 + 가격 + 표시 접수 상태 '확인 불가'·'불가'·기록 없음 — 순위만, 사다리 미실행
    - 판정 대상: 포함 확정 + 가격 + 접수 '가능'·'미정'
    """
    if inclusion_class == BOUNDARY:
        return "제외"
    if inclusion_decision != "auto":
        return "미해결"
    if inclusion_class in EXCLUDED_CLASSES:
        return "제외"
    if inclusion_class != INCLUDED_CLASS:  # 'manual_review'·'미분류' 가 auto 로 온 경우
        return "미해결"
    if not has_price:
        return "보류"
    if intake_status in ("가능", "미정"):
        return "판정 대상"
    return "참고"


def current_terms(payments: Sequence[PaymentTerms]) -> PaymentTerms | None:
    """현재 공고 조건 = effective_from 최신(같으면 id 큰 것) — API ``views.current_payment`` 와 같은 순서."""
    return max(payments, key=lambda p: (p.effective_from or "", p.id)) if payments else None


@dataclass(frozen=True, slots=True)
class PriceSource:
    """§6-1 현재 구매가 원천: 공급금액(최고가·대표층) + 그 출처 행 키 (entity, entity_id, field)."""

    max_won: int | None
    floor_won: int | None
    max_key: tuple[str, int, str]
    floor_key: tuple[str, int, str]
    notice_no: str | None  # price_by_type 를 쓴 공고 번호(None = complex_type 값)


def current_price_source(basis: ComplexType | None, payments: Sequence[PaymentTerms]) -> PriceSource | None:
    """현재 구매가 원천(§6-1). F2 머지 후 본문 = ``analysis.price_view`` 호출 한 줄.

    최신 공고(``current_terms``)의 ``price_by_type[판정 타입]`` 에 최고가가 있으면 그 값(임의공급 가격 변경),
    없으면 ``complex_type`` 값. 발코니·필수 옵션은 늘 ``complex_type``(호출부가 더한다).
    """
    if basis is None:
        return None
    cur = current_terms(payments)
    by_type = (cur.price_by_type or {}) if cur is not None else {}
    item = by_type.get(basis.type_code) if isinstance(by_type, dict) else None
    if cur is not None and isinstance(item, dict) and item.get("max_price_won") is not None:
        key = f"price_by_type.{basis.type_code}"
        floor = item.get("floor_sample_price_won")
        return PriceSource(
            max_won=int(item["max_price_won"]),
            floor_won=int(floor) if floor is not None else None,
            max_key=("payment_terms", cur.id, f"{key}.max_price_won"),
            floor_key=("payment_terms", cur.id, f"{key}.floor_sample_price_won"),
            notice_no=cur.notice_no,
        )
    return PriceSource(
        max_won=basis.max_price_won,
        floor_won=basis.floor_sample_price_won,
        max_key=("complex_type", basis.id, "max_price_won"),
        floor_key=("complex_type", basis.id, "floor_sample_price_won"),
        notice_no=None,
    )
