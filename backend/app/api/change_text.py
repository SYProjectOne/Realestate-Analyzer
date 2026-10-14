"""변경 피드 한 줄 요약 (계약 2026-10-09.20, DECISIONS D28-5 Q5 — ``change_event.json`` ``field_label``·``summary``·``value_kind``).

G1 변경 피드에 ``official_popup_hash 4017…→59fd…`` 같은 64자리 해시가 그대로 보였다(00-baseline). 이 모듈은 저장된
change_event 행(엔티티·필드·이전·이후 문자열)을 사람이 읽는 한 줄로 바꾼다. **새 판단 없음** — 필드 이름 표 + 값 모양 검사
(해시·JSON) + 문장 틀뿐이다. 원값(old_text·new_text)은 응답에 그대로 남는다(D25-2: 변경 기록이지 Fact 가 아니다).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from typing import Final

__all__ = ["FIELD_LABELS", "change_summary", "field_label", "is_hash_field", "value_kind"]

FIELD_LABELS: Final[dict[str, str]] = {
    # 단지(complex)
    "official_popup_hash": "공식 홈페이지 팝업",
    "applyhome_list": "청약홈 공고 목록",
    "first_load": "첫 적재",
    "track": "공고 예정 후보",
    "applyhome_id": "주택관리번호",
    "legal_dong_code": "법정동",
    "name": "단지 이름",
    "former_names": "예전 이름",
    "address": "주소",
    "official_site_url": "공식 홈페이지 주소",
    "developer": "시행사",
    "trustee": "신탁사",
    "builder": "시공사",
    "housing_type": "주택 유형",
    "land_type": "택지 유형",
    "price_cap": "분양가상한제",
    "regulated": "규제지역",
    "units_total": "총 세대수",
    "units_general": "일반공급 세대수",
    "units_special": "특별공급 세대수",
    "officetel_units": "오피스텔 실수",
    "notice_date": "모집공고일",
    "apply_dates": "청약 접수 일정",
    "winner_date": "당첨자 발표일",
    "contract_dates": "계약 일정",
    "move_in_ym": "입주 예정월",
    "resale_months": "전매 제한 기간(개월)",
    "resale_release_on_registration": "등기 시 전매 해제",
    "residency_months": "거주의무 기간(개월)",
    "rewin_restriction_years": "재당첨 제한(년)",
    "inclusion_class": "포함 분류",
    "living_area": "생활권",
    # 주택형(complex_type)
    "type_code": "주택형",
    "area_m2": "전용면적",
    "units": "세대수",
    "max_price_won": "최고 공급가",
    "floor_sample_price_won": "대표 층 공급가",
    "balcony_won": "발코니 확장비",
    "options_required_won": "필수 옵션",
    # 납부 조건(payment_terms)
    "effective_from": "적용 시작일",
    "down_payment_pct": "계약금 비율(%)",
    "down_payment_first_won": "1차 계약금(정액)",
    "interim_pct": "중도금 비율(%)",
    "interim_terms_text": "중도금 조건",
    "balance_pct": "잔금 비율(%)",
    "interim_schedule": "중도금 납부 일정",
    "notice_kind": "공고 종류",
    # 경쟁률·잔여(competition·remaining_event)
    "supply": "공급 세대",
    "applied": "접수 건수",
    "ratio_or_shortfall_text": "경쟁률",
    "notice_no": "공고 번호",
    "units_by_type": "주택형별 세대수",
    "ratio_text": "경쟁률",
    "result_text": "결과",
    # 접수·지역·판정기·적재
    "status": "접수 상태",
    "selections": "지역 선택",
    "living_areas": "생활권 구성",
    "version": "판정기 버전",
    "rows": "자료 행",
    "expected_ym": "예정 시기",
    "stage": "호재 단계",
    "popup_image_hash": "공식 홈페이지 팝업 그림",
    "http_status": "공식 홈페이지 응답 코드",
    "new_notice": "새 공고",
    "price_change_pct": "최초 공고 대비 가격 변동(%)",
    "resale_end": "전매 종료일",
    "merged_into": "같은 사업 단지 병합",
}
"""필드 이름(change_event.field) → 화면 이름. 표에 없는 필드는 그대로(``field_label``)."""

_ENTITY_ROWS: Final[dict[str, str]] = {
    "benchmark": "벤치마크",
    "supply": "입주 물량",
    "unsold": "미분양",
    "rtms_trade": "실거래",
}
"""``rows`` 필드(적재 행 수 변화)의 엔티티별 이름."""

_PBT: Final = re.compile(r"^(price_by_type|discount_by_type)\.([^.]+)(?:\.(.+))?$")
_SCHED: Final = re.compile(r"^interim_schedule\[(\d+)\]\.(due_date|pct)$")
_ENTITY_FIELDS: Final[dict[tuple[str, str], str]] = {
    ("unsold", "total"): "미분양 세대",
    ("unsold", "post_completion"): "준공 후 미분양 세대",
    ("supply", "units"): "입주 물량 세대",
    ("intake_status", "status"): "접수 상태",
}
"""엔티티마다 뜻이 다른 필드 이름."""
_HASH: Final = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{32,}$")
_PLAIN_MAX: Final = 40


def field_label(entity: str, field: str) -> str:
    """필드 화면 이름. 공고별 타입 가격(``price_by_type.<타입>.<항목>``)·할인(``discount_by_type.<타입>``)은 '<타입> <항목 이름>'."""
    m = _PBT.match(field)
    if m is not None:
        kind, code, item = m.groups()
        if kind == "discount_by_type":
            return f"{code} 할인"
        return f"{code} {FIELD_LABELS.get(item or '', item or '가격')}"
    m2 = _SCHED.match(field)
    if m2 is not None:
        seq, item = m2.groups()
        return f"중도금 {seq}회차 " + ("납부일" if item == "due_date" else "비율(%)")
    if field == "rows" and entity in _ENTITY_ROWS:
        return f"{_ENTITY_ROWS[entity]} 자료"
    if (entity, field) in _ENTITY_FIELDS:
        return _ENTITY_FIELDS[(entity, field)]
    return FIELD_LABELS.get(field, field)[:80]


def is_hash_field(field: str) -> bool:
    """이름이 해시 필드('…_hash')인가 — 저장값이 줄인 해시('9be1…c04')여도 해시로 본다."""
    return field.endswith("_hash")


def value_kind(*values: str | None, field: str = "") -> str:
    """이전·이후 문자열 모양: 'hash'(해시 필드 이름 '…_hash' 또는 16진 32자 이상 — sha256 등) · 'json'(목록·객체) · 'plain'.
    둘 중 하나라도 해당하면 그 모양."""
    if is_hash_field(field):
        return "hash"
    kinds = set()
    for v in values:
        text = (v or "").strip()
        if not text:
            continue
        if _HASH.match(text):
            kinds.add("hash")
        elif text[:1] in ("[", "{"):
            kinds.add("json")
    if "hash" in kinds:
        return "hash"
    if "json" in kinds:
        return "json"
    return "plain"


def _particle(word: str) -> str:
    """'이'/'가' — 마지막 글자 받침 유무(한글이 아니면 '이(가)')."""
    if not word:
        return "이(가)"
    ch = word[-1]
    if not "가" <= ch <= "힣":
        return "이(가)"
    return "이" if (ord(ch) - 0xAC00) % 28 else "가"


def change_summary(entity: str, field: str, old_text: str | None, new_text: str | None) -> str:
    """한 줄 요약(최대 200자). 새 공고 = '새 공고: <내용>', 해시·JSON·긴 값 = '<이름>이(가) 바뀌었습니다', 짧은 값 = '<이름>: <이전> → <이후>'."""
    label = field_label(entity, field)
    kind = value_kind(old_text, new_text, field=field)
    if entity == "notice":
        return f"새 공고: {new_text}"[:200] if new_text else "새 공고"
    if field == "first_load" and old_text is None and new_text:
        return new_text[:200]
    if (
        entity == "complex" and field == "merged_into" and new_text
    ):  # D29-2: '<원 단지>에 병합 — 같은 사업(…)'
        return f"중복 단지 행 병합: {new_text}"[:200]
    long_value = any(len(v or "") > _PLAIN_MAX for v in (old_text, new_text))
    if kind != "plain" or long_value:
        return f"{label}{_particle(label)} 바뀌었습니다"[:200]
    return f"{label}: {old_text if old_text is not None else '없음'} → {new_text if new_text is not None else '없음'}"[
        :200
    ]
