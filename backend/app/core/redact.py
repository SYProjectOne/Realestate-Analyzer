"""비밀값·개인정보 탐지와 마스킹 (AGENTS 규칙 6·13, RA §10 보안 규칙).

- 로그(``core.logging``)는 ``redact_obj``/``redact_text`` 로 가린다.
- 판정기 guard(WP3 ``judge/guard.py``)·웹훅·뉴스 API 는 ``find_sensitive``/``contains_sensitive``
  로 거부 여부를 정할 수 있다(같은 패턴을 재사용).

패턴: 전화번호(휴대·지역·대표번호, 국제 표기 +82·0082·구분자 있는 82-10-…), 주민등록번호(하이픈·공백
구분·붙여 씀), 이메일, 설정의 비밀값(원문·URL 디코딩, ``ID:Secret`` 형식이면 각 부분도 — 각각 글자 단위로
퍼센트 인코딩(부분·소문자·이중)·'+'↔공백 모양까지), URL 쿼리의 키 파라미터(serviceKey·api_key·token 등),
URL 안의 접속 비밀번호(``scheme://user:password@host``·사용자 없는 ``redis://:pw@host``),
Authorization 헤더 값·``Bearer <토큰>``, 비밀스러운 dict 키(token·password·authorization …).
정수 값(``redact_obj``·guard): 13자리 주민번호 모양, +82 국제 전화(82…), 그리고 키 이름이 전화를 뜻하면
(phone·tel·mobile·전화·연락처) 앞자리 0 이 빠진 전화번호(1012345678)도 잡는다(R3 minor 12).

R3c SEC(3차 리뷰 minor 22·31):
- 이름으로 비밀임을 아는 헤더·키(``X-NCP-APIGW-API-KEY``·``x-api-key``·``X-Naver-Client-Secret``·
  ``X-Auth-Token`` …) 뒤의 값, 숫자 없는 ``Bearer`` 토큰(16자 이상, 대소문자 섞임, 또는 ``-._~+/`` 가 든
  8자 이상 — 'the bearer of …' 같은 글은 그대로). dict 키도 하이픈 표기(``api-key``·``client-secret``)를
  비밀 키로 본다.
- 전화·주민번호 변형: 전각 숫자·전각 하이픈, en/em dash 등 대시류, 공백 낀 하이픈(``010 - 1234``), ``8210-…``·
  ``(82)10-…``·``(+82) 10-…``. 글자 단위 1:1 치환(``_FOLD``)한 사본에서 찾으므로 위치는 원문 그대로다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal
from urllib.parse import quote, quote_plus, unquote, unquote_plus

Kind = Literal["phone", "rrn", "email", "secret", "query_key"]

MIN_SECRET_LEN = 4
MIN_SECRET_PART_LEN = 8  # 'ID:Secret' 의 부분 — 짧은 조각은 흔한 낱말과 겹칠 수 있다

_KR_CODE = r"(?:1[016789]|2|3[1-3]|4[1-4]|5[1-5]|6[1-4]|70)"
_SEP = r"(?:\s?[-.]\s?|\s)"  # 구분자 1개: 하이픈·점(앞뒤 공백 하나씩 허용) 또는 공백
PHONE_RE = re.compile(
    r"(?<![\d-])(?:"
    r"(?:\+|00\d{0,3})82"
    + _SEP
    + r"?(?:\(0\)\s?)?"
    + _KR_CODE  # 국제 +82 · 0082 · 00782 …
    + r"(?:"
    + _SEP
    + r"|\)\s?)?\d{3,4}"
    + _SEP
    + r"?\d{4}"
    r"|\(\+?82\)\s?(?:\(0\)\s?)?"
    + _KR_CODE  # (82)10-… · (+82) 10-…
    + _SEP
    + r"?\d{3,4}"
    + _SEP
    + r"?\d{4}"
    r"|82"
    + _SEP
    + r"?(?:\(0\)\s?)?"
    + _KR_CODE  # '+' 없는 82-10-1234-5678 · 8210-1234-5678 (뒤 구분자 필수)
    + _SEP
    + r"\d{3,4}"
    + _SEP
    + r"\d{4}"
    r"|01[016789]" + _SEP + r"?\d{3,4}" + _SEP + r"?\d{4}"  # 휴대전화
    r"|0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4]|70|50\d?)(?:"
    + _SEP
    + r"|\)\s?)\d{3,4}"
    + _SEP
    + r"?\d{4}"  # 지역·인터넷 (구분자 필수)
    r"|0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4]|70)\d{7,8}"  # 지역번호 붙여 쓴 형태
    r"|1[5-9]\d{2}\s?-\s?\d{4}"  # 대표번호 15xx·16xx·18xx
    r")(?![\d-])"
)
RRN_RE = re.compile(r"(?<!\d)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?:\s?[-–]\s?|\s)?[1-8]\d{6}(?!\d)")
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"
_FOLD = str.maketrans(
    {
        **{chr(0xFF10 + i): str(i) for i in range(10)},  # 전각 숫자
        **dict.fromkeys(_DASHES, "-"),  # 대시류(하이픈·en/em dash·마이너스·전각 하이픈)
        "\uff08": "(",
        "\uff09": ")",
        "\uff0b": "+",
        "\uff0e": ".",
        "\u3000": " ",
        "\u00a0": " ",
    }
)
"""개인정보 패턴을 찾기 전 글자 단위 1:1 치환(길이·위치가 바뀌지 않는다)."""
DSN_PASSWORD_RE = re.compile(r"(?i)\b[a-z][a-z0-9+.\-]*://[^/\s:@]*:([^\s/?#]+)@")
"""URL 안의 접속 비밀번호(DATABASE_URL 'postgresql+psycopg://user:pw@host/db', 사용자 없는
'redis://:pw@host:6379/0', '@' 가 든 비밀번호는 authority 의 마지막 '@' 까지) — 비밀번호만 가린다."""
_TOKEN = r"[A-Za-z0-9\-._~+/]+=*"
_TOKEN_CH = r"[A-Za-z0-9\-._~+/]"
AUTH_HEADER_RE = re.compile(
    r"(?i:authorization)[\"']?\s*[:=]\s*[\"']?\s*(?:(?i:bearer|basic|token|digest)\s+)?(" + _TOKEN + ")"
    r"|\b(?i:bearer)\s+("
    r"(?=" + _TOKEN_CH + r"*\d)" + _TOKEN_CH + r"{8,}=*"  # 숫자 포함 8자 이상
    r"|(?=[A-Za-z]*[a-z][A-Za-z]*[A-Z])[A-Za-z]{8,}(?!"
    + _TOKEN_CH
    + r")"  # 소문자 뒤 대문자(첫 글자만 대문자인 낱말 제외) 8자 이상
    r"|(?=[A-Za-z0-9]*[\-._~+/])" + _TOKEN_CH + r"{8,}=*"  # 토큰 기호가 든 8자 이상
    r"|" + _TOKEN_CH + r"{16,}=*"  # 16자 이상
    r")"
    r"|\b(?i:bearer)\s+((?=" + _TOKEN_CH + r"*[\d\-._~+/])" + _TOKEN_CH + r"{4,7}=*)(?!" + _TOKEN_CH + r")"
    # R3 4차 minor: 'Bearer' 뒤 숫자·토큰 기호가 든 4~7자 짧은 토큰도 — R3 5차 minor: 대소문자 무관('bearer abc123')
    # (소문자 낱말 'bearer of' 는 그대로)
)
"""Authorization 헤더 값(``Authorization: Bearer …``·``Basic …``·``Token …``)과 홀로 나온 ``Bearer <토큰>``
(토큰 모양만 — 'the bearer of …'·'bearer bonds' 같은 글은 그대로)."""
_SECRET_NAME = (
    r"(?:x-)?[a-z0-9_-]*?"
    r"(?:api[-_]?key(?:[-_]id)?|apikey|client[-_]?secret|client[-_]?id|access[-_]?token|auth[-_]?token|"
    r"refresh[-_]?token|secret[-_]?access[-_]?key|private[-_]?key|secret[-_]?key|secret|token|password|passwd|pwd)"
)
HEADER_KEY_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])(" + _SECRET_NAME + r")[\"']?\s*[:=]\s*[\"']?\s*(" + _TOKEN + ")"
)
"""이름으로 비밀임을 아는 헤더·키 뒤의 값(``X-NCP-APIGW-API-KEY: …``·``x-api-key=…``·``"X-Api-Key": "…"``,
snake_case ``client_secret=…``·``access_token: …`` — R3 4차 minor; ``aws_secret_access_key=…``·``private_key=…``·
``pwd=…`` — R3 5차 minor)."""
QUOTED_KEY_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])(" + _SECRET_NAME + r")[\"']?\s*[:=]\s*"
    r"(?:\"((?:[^\"\\\n]|\\.)*)\"?|'((?:[^'\\\n]|\\.)*)'?)"
)
"""R3 6차 minor 9: 따옴표로 감싼 비밀 키 값은 **따옴표 안 전체**(공백·JSON 이스케이프 ``\\n``·``\\"`` 포함 — JSON
``"private_key": "-----BEGIN …\\n…"``·``password = 's3cr3t pw'``). 닫는 따옴표가 없으면(잘린 로그) 그 줄 끝까지."""
PEM_PRIVATE_RE = re.compile(
    r"-----BEGIN ([A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*)-----(.*?)(?:-----END \1-----|\Z)", re.DOTALL
)
"""R3 6차 minor 9: PEM 개인키 블록(``-----BEGIN [RSA|EC|OPENSSH|ENCRYPTED ]PRIVATE KEY-----`` … ``-----END …-----``)의
여러 줄 본문 전체. END 줄이 없으면(잘린 로그) 글 끝까지. 공개 인증서(``CERTIFICATE``)는 그대로."""
_PHONE_KEY_RE = re.compile(r"(?i)(phone|tel|mobile|fax|전화|연락처|휴대)")
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
QUERY_KEY_RE = re.compile(
    r"(?i)([?&](?:servicekey|service_key|api_?key|apikey|access_token|token|secret|password|key)=)[^&\s#\"']+"
)
SENSITIVE_KEY_RE = re.compile(
    r"(?i)(token|secret|password|passwd|authorization|cookie|api[-_]?key|service[-_]?key|credential|client[-_]?id"
    r"|private[-_]?key)"  # R3 6차 minor 9: dict 키 'private_key'·'privateKey'
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


_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def _char_pattern(ch: str) -> str:
    """비밀값 글자 1개가 URL 에 보일 수 있는 모양: 원문 · %XX(대소문자 16진) · 이중 인코딩 %25XX ·
    (공백이면 '+', '+' 면 unquote_plus 로 풀린 공백)."""
    if ch in _UNRESERVED:
        return re.escape(ch)
    enc = "".join(
        "%(?:25)?" + "".join(f"[{d}{d.lower()}]" if d.isalpha() else d for d in f"{b:02X}")
        for b in ch.encode("utf-8")
    )
    alts = [re.escape(ch), enc]
    if ch == " ":
        alts.append(r"\+")
    elif ch == "+":
        alts.append(" ")
    return "(?:" + "|".join(alts) + ")"


def _secret_forms(secrets: Iterable[str]) -> list[str]:
    """비밀값 표기 원형: 원문·URL 디코딩(인코딩된 키를 받은 경우의 원래 키), 그리고 'ID:Secret' 형식이면
    각 부분(뉴스 API 키는 두 헤더로 나뉘어 따로 보인다). 인코딩 모양은 ``_char_pattern`` 이 맡는다."""
    forms: set[str] = set()
    for s in secrets:
        if not s or len(s) < MIN_SECRET_LEN:
            continue
        group = {s, unquote(s), unquote_plus(s)}
        if ":" in s:
            group.update(part for part in s.split(":") if len(part) >= MIN_SECRET_PART_LEN)
        forms.update(f for f in group if len(f) >= MIN_SECRET_LEN)
    return sorted(forms, key=lambda f: (-len(f), f))


@lru_cache(maxsize=64)
def _secret_patterns(secrets: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    """비밀값마다 정규식 1개: 글자별로 원문·퍼센트 인코딩(부분 인코딩·소문자·이중 인코딩 포함)을 모두 받는다.
    quote·quote_plus·httpx params 인코딩, '/' 만 남긴 quote() 기본 모양을 따로 나열하지 않아도 잡힌다."""
    return tuple(re.compile("".join(_char_pattern(ch) for ch in form)) for form in _secret_forms(secrets))


def _secret_variants(secrets: Iterable[str]) -> list[str]:
    """(호환) 대표 표기 변형 목록: 원형마다 원문·quote(safe='')·quote_plus."""
    variants: set[str] = set()
    for form in _secret_forms(secrets):
        variants.update({form, quote(form, safe=""), quote_plus(form)})
    return sorted(variants, key=len, reverse=True)


def sensitive_int_kind(value: int, key: str | None = None) -> Kind | None:
    """정수로 들어온 개인정보(주민번호·전화번호). 금액 같은 보통 정수와 겹치지 않게 좁게 본다(모듈 설명)."""
    if isinstance(value, bool) or value <= 0:
        return None
    digits = str(value)
    if len(digits) == 13 and RRN_RE.fullmatch(digits):
        return "rrn"
    if len(digits) in (11, 12) and digits.startswith("82") and PHONE_RE.fullmatch("+" + digits):
        return "phone"
    if key is not None and _PHONE_KEY_RE.search(key) and PHONE_RE.fullmatch("0" + digits):
        return "phone"
    return None


def find_sensitive(text: str, secrets: Iterable[str] = ()) -> list[Finding]:
    """겹치지 않는 탐지 결과(앞에서부터). 비밀값 > 주민번호 > 전화 > 이메일 순으로 우선."""
    taken: list[Finding] = []

    def overlaps(a: int, b: int) -> bool:
        return any(a < f.end and f.start < b for f in taken)

    # 긴 비밀 구간(PEM 본문·따옴표 값 전체)을 먼저 — 그 안의 짧은 탐지가 먼저 잡혀 구간 전체가 겹침으로 버려지지 않게(m9)
    for m in PEM_PRIVATE_RE.finditer(text):
        a, b = m.start(2), m.end(2)
        if b > a and not overlaps(a, b):
            taken.append(Finding("secret", a, b))
    for m in QUOTED_KEY_RE.finditer(text):
        g = 2 if m.group(2) is not None else 3
        a, b = m.start(g), m.end(g)
        if b > a and not overlaps(a, b):
            taken.append(Finding("secret", a, b))
    for pattern in _secret_patterns(tuple(secrets)):
        for m in pattern.finditer(text):
            if not overlaps(m.start(), m.end()):
                taken.append(Finding("secret", m.start(), m.end()))
    for m in AUTH_HEADER_RE.finditer(text):
        group = next(g for g in (1, 2, 3) if m.group(g) is not None)
        a, b = m.start(group), m.end(group)
        if not overlaps(a, b):
            taken.append(Finding("secret", a, b))
    for m in HEADER_KEY_RE.finditer(text):
        a, b = m.start(2), m.end(2)
        if not overlaps(a, b):
            taken.append(Finding("secret", a, b))
    for m in QUERY_KEY_RE.finditer(text):
        a, b = m.start() + len(m.group(1)), m.end()
        if not overlaps(a, b):
            taken.append(Finding("query_key", a, b))
    for m in DSN_PASSWORD_RE.finditer(text):
        a, b = m.start(1), m.end(1)
        if not overlaps(a, b):
            taken.append(Finding("secret", a, b))
    folded = text.translate(_FOLD)  # 1:1 치환 — 위치는 원문과 같다
    for kind, pattern in _PATTERNS:
        for m in pattern.finditer(folded):
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


def _redact(obj: Any, secrets: list[str], key: str | None = None) -> Any:
    if obj is None or isinstance(obj, bool | float):
        return obj
    if isinstance(obj, int):
        kind = sensitive_int_kind(obj, key)
        return f"[REDACTED:{kind}]" if kind is not None else obj
    if isinstance(obj, str):
        return redact_text(obj, secrets)
    if isinstance(obj, Mapping):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            name = str(k)
            if SENSITIVE_KEY_RE.search(name) and v is not None and not isinstance(v, bool | int | float):
                out[name] = "[REDACTED:key]"
            else:
                out[name] = _redact(v, secrets, name)
        return out
    if isinstance(obj, list | tuple | set | frozenset):
        return [_redact(v, secrets, key) for v in obj]
    return redact_text(str(obj), secrets)
