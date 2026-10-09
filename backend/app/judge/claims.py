"""원자 주장 분할 (RA §4-3 ClaimSplitter, T6). 규칙 기반 문자열 처리 — LLM·판정기 호출 없음.

1 사실 = 1 주장. 순서:
1. 문장 분리: 마침표·물음표 뒤 공백, 줄바꿈, 세미콜론.
2. 접속 어미·접속사 분리: ``이고/이며``(서술격 조사 → 생략), ``있고→있다``, ``없고→없다``, ``하고→하다``,
   ``되고→된다``, ``였고→였다``, ``지만→다``, ``그리고/하지만/반면/또한``.
   앞 절이 ``<주어>의 …`` 로 시작하면 주어 없는 뒤 절에 그 주어를 붙인다(검증 가능한 주장으로).
3. 열거 주어 분배: ``A·B는 X`` → ``A는 X``, ``B는 X`` (괄호 안 ``·`` 는 건드리지 않는다).
4. 숫자가 2개 이상인 절은 ``, `` 로 나눈다(``7,490`` 처럼 공백 없는 쉼표는 숫자). 범위(``5.78~6.08억``)·날짜
   (``2028-09``)는 숫자 1개다. 나눌 자리가 없으면 그대로 둔다(비교식 ``a ≤ b`` 는 사실 1개).

``is_atomic(text)`` = 분할 결과가 1개. ``payloads.verify_payload`` 는 원자 주장만 받는다(복합 문장 → 예외).
"""

from __future__ import annotations

import re
from typing import Final

from app.core.contracts_gen import Claim

__all__ = ["CompoundClaimError", "RuleClaimSplitter", "is_atomic", "split_texts", "with_josa"]


class CompoundClaimError(ValueError):
    """복합 문장을 원자 주장 자리에 넣었다(verify 에 그대로 보내면 안 된다, T6)."""


_SENTENCE_RE: Final = re.compile(r"(?<=[.!?。])\s+|\n+|;\s*")
# (접속 어미, 앞 절 끝에 붙일 종결형). 긴 것부터.
_ENDINGS: Final[tuple[tuple[str, str], ...]] = (
    ("있으며", "있다"),
    ("없으며", "없다"),
    ("였으며", "였다"),
    ("이지만", ""),
    ("이고", ""),
    ("이며", ""),
    ("있고", "있다"),
    ("없고", "없다"),
    ("하고", "하다"),
    ("하며", "하다"),
    ("되고", "된다"),
    ("되며", "된다"),
    ("였고", "였다"),
    ("았고", "았다"),
    ("었고", "었다"),
    ("지만", "다"),
)
_CONJ_RE: Final = re.compile(
    r"(?<=\S)(?P<ending>" + "|".join(e for e, _ in _ENDINGS) + r")\s+"
    r"|\s+(?:그리고|하지만|반면|또한)\s+"
    r"|,\s*(?:그리고|또)\s+"
)
_ENDING_MAP: Final = dict(_ENDINGS)
_NUMBER_RE: Final = re.compile(
    r"(?<![A-Za-z가-힣\d.])[+-]?\d[\d,]*(?:\.\d+)?(?:\s*[~∼-]\s*[+-]?\d[\d,]*(?:\.\d+)?)?"
)
_SUBJECT_OF_RE: Final = re.compile(r"^((?:[^\s,]+\s){0,3}[^\s,]+의)\s")
_TOPIC_RE: Final = re.compile(r"^(?P<subj>[^,()\[\]]+?)(?P<josa>은|는|이|가)\s+(?P<rest>.+)$")
_JOSA_PAIRS: Final = {
    "은": ("은", "는"),
    "는": ("은", "는"),
    "이": ("이", "가"),
    "가": ("이", "가"),
    "을": ("을", "를"),
    "를": ("을", "를"),
}


def _has_batchim(ch: str) -> bool:
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 != 0
    if ch.isdigit():
        return ch in "013678"  # 영·일·삼·육·칠·팔
    if ch.isascii() and ch.isalpha():
        return ch.lower() in "lmnr"
    return False


def with_josa(word: str, josa: str) -> str:
    """받침에 맞는 조사: with_josa('84A', '을') → '84A를', with_josa('센트레빌', '는') → '센트레빌은'."""
    with_b, without_b = _JOSA_PAIRS[josa]
    return word + (with_b if word and _has_batchim(word[-1]) else without_b)


def _numbers(text: str) -> int:
    return len(_NUMBER_RE.findall(text))


def _split_conjunctions(sentence: str) -> list[str]:
    parts: list[str] = []
    pos = 0
    for m in _CONJ_RE.finditer(sentence):
        ending = m.group("ending")
        head = sentence[pos : m.start()] + (_ENDING_MAP[ending] if ending else "")
        parts.append(head.strip())
        pos = m.end()
    parts.append(sentence[pos:].strip())
    parts = [p for p in parts if p]
    if len(parts) > 1:
        subj = _SUBJECT_OF_RE.match(parts[0])
        if subj:
            subject = subj.group(1)
            parts = [parts[0]] + [p if _SUBJECT_OF_RE.match(p) else f"{subject} {p}" for p in parts[1:]]
    return parts


def _distribute_enumeration(clause: str) -> list[str]:
    m = _TOPIC_RE.match(clause)
    if not m or "·" not in m.group("subj") or "의 " in m.group("subj"):
        return [clause]
    items = [s.strip() for s in m.group("subj").split("·")]
    if len(items) < 2 or any(not s for s in items):
        return [clause]
    return [f"{with_josa(item, m.group('josa'))} {m.group('rest')}" for item in items]


def _split_numbers(clause: str) -> list[str]:
    if _numbers(clause) < 2:
        return [clause]
    pieces = [p.strip() for p in re.split(r",\s+|\s+/\s+", clause)]
    pieces = [p for p in pieces if p]
    return pieces if len(pieces) > 1 else [clause]


def split_texts(text: str) -> list[str]:
    """원문 → 원자 주장 문자열 목록(원문 순서)."""
    out: list[str] = []
    for sentence in _SENTENCE_RE.split(text or ""):
        sentence = sentence.strip()
        if not sentence:
            continue
        for clause in _split_conjunctions(sentence):
            for part in _distribute_enumeration(clause):
                out.extend(_split_numbers(part))
    return out


def is_atomic(text: str) -> bool:
    return len(split_texts(text)) == 1


class RuleClaimSplitter:
    """ClaimSplitter 구현(규칙 기반)."""

    def split(
        self,
        text: str,
        *,
        section: str = "",
        snapshot_id: int | None = None,
        complex_id: int | None = None,
    ) -> list[Claim]:
        return [
            Claim(
                snapshot_id=snapshot_id,
                section=section[:32],
                complex_id=complex_id,
                text=t,
                evidence_text=None,
                verify_status=None,
                judgment_seq=None,
                parent_claim_id=None,
                ordinal=i,
            )
            for i, t in enumerate(split_texts(text))
        ]
