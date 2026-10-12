"""경쟁률 행의 식별과 표시 주택형 (D23-2, R4 4차 N13).

**식별(저장)**: 경쟁률 행은 원문이 준 값만으로 식별한다 — (단지, 공급 구분, 회차, **원 면적 코드**). 원 면적 코드 = 파서가 원문
주택형에서 만든 코드(청약홈 API ``HOUSE_TY`` '084.9939 ' → '84.9939', 문자 있는 주택형 '084.9582A' → '84A' 등 —
``normalize_type_code``)이고 ``competition.type_code`` 에 그대로 저장한다. 그 시점의 단지 주택형 행과 대조해 키를 바꾸지 않는다:
R4 4차에서는 bootstrap 이 타입 행이 없을 때 원 코드('84.9939')로, 같은 날 재정규화가 타입 행이 생긴 뒤 대조 코드('84'·'확인 불가
(타입 모호)')로 행을 찾아 **같은 경쟁률 행 70개를 새로 만들었다**(발행 리비전에 '확인됨' Fact 140개가 이벤트 없이 생김).

**표시(읽기 시점)**: 화면·보고서의 주택형은 ``display_type_codes`` 가 지금 단지 주택형 행과 대조해 정한다(문자열·소수 대조 —
판단 아님). 규칙은 옛 저장 단계 규칙과 같다:

- 면적 코드('.' 포함)가 아니면 원 코드 그대로.
- 단지 주택형과 **전용면적 소수 4자리**(주택형 원문 ``notice_type_code`` 의 면적, 원문이 없는 타입은 ``area_m2`` 소수 2자리)로
  맞춘다. 맞는 타입이 하나면 그 type_code, 없으면 원 코드, 여럿이면 ``TYPE_AMBIGUOUS``('확인 불가(타입 모호)').
- 같은 단지·구분·회차에서 표시 코드가 겹치면(모호한 면적이 둘 이상 · 다른 원 코드가 같은 타입에 맞음) 원 코드 순서로 첫 행만
  그 표시 코드를 쓰고 나머지는 원 코드 그대로(행이 합쳐 보이지 않게 — 결정적, 저장 순서와 무관).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from decimal import Decimal, InvalidOperation
from typing import Final, Protocol

__all__ = ["TYPE_AMBIGUOUS", "display_type_codes", "match_type_code"]

TYPE_AMBIGUOUS: Final = "확인 불가(타입 모호)"
"""면적 코드 경쟁률 행이 같은 면적의 단지 주택형 여럿에 맞을 때의 표시 주택형(매칭하지 않음)."""
_Q4: Final = Decimal("0.0001")
_Q2: Final = Decimal("0.01")
_NOTICE_AREA_RE: Final = re.compile(r"^0*(\d+\.\d+)")


class _TypeRow(Protocol):
    @property
    def type_code(self) -> str: ...
    @property
    def area_m2(self) -> object: ...
    @property
    def notice_type_code(self) -> str | None: ...


class _CompetitionRow(Protocol):
    @property
    def id(self) -> int: ...
    @property
    def kind(self) -> str: ...
    @property
    def round(self) -> str: ...
    @property
    def type_code(self) -> str: ...


def _notice_area(code: str | None) -> Decimal | None:
    """주택형 원문('084.9582A', '084.7529') → 전용면적 84.9582. 형식이 아니면 None."""
    m = _NOTICE_AREA_RE.match((code or "").strip())
    return Decimal(m.group(1)) if m else None


def match_type_code(code: str, types: Iterable[_TypeRow]) -> str:
    """원 면적 코드 하나 → 표시 주택형(맞는 타입 1개 = 그 코드, 없음 = 원 코드, 여럿 = ``TYPE_AMBIGUOUS``)."""
    if "." not in code:
        return code
    try:
        area = Decimal(code)
    except InvalidOperation:
        return code
    hits: list[str] = []
    for t in types:
        precise = _notice_area(t.notice_type_code)
        if precise is not None:
            same = precise.quantize(_Q4) == area.quantize(_Q4)
        elif t.area_m2 is not None:
            same = Decimal(str(t.area_m2)).quantize(_Q2) == area.quantize(_Q2)
        else:
            same = False
        if same:
            hits.append(t.type_code)
    if len(hits) == 1:
        return hits[0]
    return TYPE_AMBIGUOUS if hits else code


def display_type_codes(types: Sequence[_TypeRow], rows: Iterable[_CompetitionRow]) -> dict[int, str]:
    """한 단지의 경쟁률 행들 → {행 id: 표시 주택형}(모듈 설명). 같은 입력이면 저장 순서와 무관하게 같은 결과."""
    groups: dict[tuple[str, str], list[_CompetitionRow]] = defaultdict(list)
    for r in rows:
        groups[(r.kind, r.round)].append(r)
    out: dict[int, str] = {}
    for members in groups.values():
        taken: set[str] = set()
        originals = {m.type_code for m in members}
        for m in sorted(members, key=lambda x: (x.type_code, x.id)):
            shown = match_type_code(m.type_code, types)
            if shown != m.type_code and (shown in taken or shown in originals):
                # 이미 다른 행이 그 표시 코드(또는 원 코드)를 쓴다 — 합쳐 보이지 않게 원 코드
                shown = m.type_code
            taken.add(shown)
            out[m.id] = shown
    return out
