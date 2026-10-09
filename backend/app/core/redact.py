"""비밀값·개인정보 탐지와 마스킹 (AGENTS 규칙 6·13, RA §10 보안 규칙).

- 로그(``core.logging``)는 ``redact_obj``/``redact_text`` 로 가린다.
- 판정기 guard(WP3 ``judge/guard.py``)·웹훅·뉴스 API 는 ``find_sensitive``/``contains_sensitive``
  로 거부 여부를 정할 수 있다(같은 패턴을 재사용).

패턴: 전화번호(휴대·지역·대표번호), 주민등록번호, 이메일, 설정의 비밀값(원문·URL 인코딩),
URL 쿼리의 키 파라미터(serviceKey·api_key·token 등), 비밀스러운 dict 키(token·password·authorization …).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote, quote_plus

Kind = Literal["phone", "rrn", "email", "secret", "query_key"]

MIN_SECRET_LEN = 4

PHONE_RE = re.compile(
    r"(?<![\d-])(?:"
    r"01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}"  # 휴대전화
    r"|0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4]|70|50\d?)[-.\s)]\s?\d{3,4}[-.\s]?\d{4}"  # 지역·인터넷 (구분자 필수)
    r"|0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4]|70)\d{7,8}"  # 지역번호 붙여 쓴 형태
    r"|1[5-9]\d{2}-\d{4}"  # 대표번호 15xx·16xx·18xx
    r")(?![\d-])"
)
RRN_RE = re.compile(r"(?<!\d)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])-?[1-8]\d{6}(?!\d)")
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
QUERY_KEY_RE = re.compile(
    r"(?i)([?&](?:servicekey|service_key|api_?key|apikey|access_token|token|secret|password|key)=)[^&\s#\"']+"
)
SENSITIVE_KEY_RE = re.compile(
    r"(?i)(token|secret|password|passwd|authorization|cookie|api_?key|service_?key|credential)"
)

_PATTERNS: tuple[tuple[Kind, re.Pattern[str]], ...] = (
    ("rrn", RRN_RE),
    ("phone", PHONE_RE),
    ("email", EMAIL_RE),
)


@dataclass(frozen=True, slots=True)
class Finding:
    kind: Kind
    start: int
    end: int


def _secret_variants(secrets: Iterable[str]) -> list[str]:
    variants: set[str] = set()
    for s in secrets:
        if not s or len(s) < MIN_SECRET_LEN:
            continue
        variants.update({s, quote(s, safe=""), quote_plus(s)})
    return sorted(variants, key=len, reverse=True)


def find_sensitive(text: str, secrets: Iterable[str] = ()) -> list[Finding]:
    """겹치지 않는 탐지 결과(앞에서부터). 비밀값 > 주민번호 > 전화 > 이메일 순으로 우선."""
    taken: list[Finding] = []

    def overlaps(a: int, b: int) -> bool:
        return any(a < f.end and f.start < b for f in taken)

    for variant in _secret_variants(secrets):
        start = 0
        while (idx := text.find(variant, start)) != -1:
            end = idx + len(variant)
            if not overlaps(idx, end):
                taken.append(Finding("secret", idx, end))
            start = end
    for m in QUERY_KEY_RE.finditer(text):
        a, b = m.start() + len(m.group(1)), m.end()
        if not overlaps(a, b):
            taken.append(Finding("query_key", a, b))
    for kind, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            if not overlaps(m.start(), m.end()):
                taken.append(Finding(kind, m.start(), m.end()))
    return sorted(taken, key=lambda f: f.start)


def contains_sensitive(text: str, secrets: Iterable[str] = ()) -> bool:
    return bool(find_sensitive(text, secrets))


def redact_text(text: str, secrets: Iterable[str] = ()) -> str:
    findings = find_sensitive(text, secrets)
    if not findings:
        return text
    out: list[str] = []
    pos = 0
    for f in findings:
        out.append(text[pos : f.start])
        label = "secret" if f.kind == "query_key" else f.kind
        out.append(f"[REDACTED:{label}]")
        pos = f.end
    out.append(text[pos:])
    return "".join(out)


def redact_obj(obj: Any, secrets: Iterable[str] = ()) -> Any:
    """dict·list·tuple 를 재귀로 가린다. 비밀스러운 키의 값은 통째로 ``[REDACTED:key]``.

    반환은 JSON 직렬화 가능한 형태(tuple→list, 그 밖의 객체→str).
    """
    secret_list = list(secrets)
    return _redact(obj, secret_list)


def _redact(obj: Any, secrets: list[str]) -> Any:
    if obj is None or isinstance(obj, bool | int | float):
        return obj
    if isinstance(obj, str):
        return redact_text(obj, secrets)
    if isinstance(obj, Mapping):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            key = str(k)
            if SENSITIVE_KEY_RE.search(key) and v is not None and not isinstance(v, bool | int | float):
                out[key] = "[REDACTED:key]"
            else:
                out[key] = _redact(v, secrets)
        return out
    if isinstance(obj, list | tuple | set | frozenset):
        return [_redact(v, secrets) for v in obj]
    return redact_text(str(obj), secrets)
