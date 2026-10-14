"""'확인 불가'·접수 사유 문자열 → 사유 코드 (계약 2026-10-09.20, DECISIONS D28-5 Q5 — ``fact.json`` ``ReasonCode``).

사유 문자열은 수집·정규화·판정·점수 단계가 저마다 만든다(``'403'``·``'발코니 표 해석 실패'``·``'판정 미해결'``·``'미판정'`` …).
화면이 쉬운 말로 바꾸려면 문자열 비교 대신 안정된 코드가 필요하다. 이 모듈은 **저장된 사유 문자열의 머리말·낱말**로 코드를
정한다(``app.api.intake_queue.queue_key`` 와 같은 데이터 기준 — 새 사유가 생겨도 코드·계약을 바꾸지 않고 ``other``). 문자열
규칙이지 판단이 아니다(AGENTS 규칙 3). 원래 사유 문자열은 응답에 그대로 남는다.

규칙 순서는 계약 설명(``fact.json`` ``$defs.ReasonCode``)과 같다 — 첫 규칙이 이긴다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from typing import Final

__all__ = ["REASON_CODES", "reason_code"]

REASON_CODES: Final = (
    "fetch_failed",
    "not_collected",
    "not_published",
    "parse_failed",
    "source_missing",
    "demoted",
    "conflict_hold",
    "partial_missing",
    "identity_unconfirmed",
    "other_complex_site",
    "no_phrase",
    "phrase_inconclusive",
    "not_target",
    "input_blocked",
    "unresolved",
    "unjudged",
    "not_entered",
    "no_sample",
    "human_check",
    "no_winner",
    "no_value",
    "other",
)
"""계약 enum 순서 그대로(테스트가 계약과 맞춘다)."""

# 수집 실패 낱말(raw_document.error_text 값 목록 — core.http ErrorKind · intake_queue 와 같은 낱말 + 청약홈 빈 데이터셋 D23-4)
_FETCH_WORDS: Final = frozenset(
    {
        "dns",
        "timeout",
        "connect",
        "tls",
        "network",
        "robots",
        "robots.txt",
        "invalid_url",
        "render",
        "blocked_host",
        "blocked_by_robots",
        "empty_dataset",
        "browser",
    }
)
_HEAD_WORD: Final = re.compile(r"^[A-Za-z_][A-Za-z_.]*")
_FETCH_PREFIXES: Final = ("접속 실패", "수집 실패", "타임아웃")

# (코드, 머리말 목록, 포함 낱말 목록) — 순서대로 첫 일치
_RULES: Final[tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]] = (
    (
        "not_collected",
        (),
        ("원문 없음", "미수집", "수집 기록 없음", "자료 없음", "물량 없음", "수집기 없음", "출처 미조회"),
    ),
    ("not_published", ("공고 전", "발표 전"), ("분양가 미공개", "공고 전")),
    ("parse_failed", (), ("해석 실패", "표 없음", "배정 실패", "변환 실패", "스캔", "OCR 실패")),
    ("source_missing", (), ("출처 누락",)),
    ("demoted", (), ("검증 모순",)),
    ("conflict_hold", (), ("출처 상충", "compare 대기", "상충", "모호")),
    ("partial_missing", (), ("일부 누락",)),
    ("identity_unconfirmed", ("공식 홈페이지 동일성 미확인",), ()),
    ("other_complex_site", ("공식 홈페이지가 다른 단지",), ()),
    ("no_phrase", ("접수 문구 없음",), ()),
    ("phrase_inconclusive", ("문구로 판단 불가",), ()),
    ("not_target", ("판정 대상 아님",), ()),
    ("input_blocked", ("입력 차단",), ()),
    ("unresolved", (), ("판정 미해결", "미해결", "미분류")),
    ("unjudged", (), ("미판정", "판정 기록 없음", "미계산", "고정 입력")),
    ("not_entered", (), ("미입력",)),
    ("no_sample", (), ("표본 0", "비교군 없음", "실거래 없음", "사례 없음")),
    ("human_check", ("사람 확인",), ()),
    ("no_winner", ("가점 당첨자 없음",), ()),  # 계약 .21(R10): 경쟁률 팝업 당첨가점 '-' — 가점 미수집과 구별
    ("no_value", (), ("값 없음", "미기재", "표기 없음", "결측")),
)


def reason_code(reason: str | None, http_status: int | None = None) -> str | None:
    """사유 문자열(·접수 행 HTTP 상태) → 사유 코드. 사유가 비고 HTTP 상태도 정상이면 None(코드 없음).

    접수 행: HTTP 상태가 2xx 가 아니면 사유와 무관하게 ``fetch_failed``(``intake_queue.queue_key`` 와 같다)."""
    if http_status is not None and not 200 <= http_status < 300:
        return "fetch_failed"
    text = (reason or "").strip()
    if not text:
        return None
    if text.isdigit():
        return "fetch_failed"
    head = _HEAD_WORD.match(text)
    if head is not None and head.group(0).lower() in _FETCH_WORDS:
        return "fetch_failed"
    if text.startswith(_FETCH_PREFIXES):
        return "fetch_failed"
    for code, prefixes, words in _RULES:
        if prefixes and text.startswith(prefixes):
            return code
        if any(w in text for w in words):
            return code
    if text.endswith("없음"):
        return "no_value"
    return "other"
