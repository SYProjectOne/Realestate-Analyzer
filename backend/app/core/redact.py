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
    + _TOKEN_CH
    + r"{8,}=*"  # R3 8차 minor 14: 'bearer' 뒤 8자 이상 토큰은 모양과 무관하게(소문자뿐인 'bearer abcdefghij' 도)
    r")"
    r"|\b(?i:bearer)\s+((?=" + _TOKEN_CH + r"*[\d\-._~+/])" + _TOKEN_CH + r"{4,7}=*)(?!" + _TOKEN_CH + r")"
    # R3 4차 minor: 'Bearer' 뒤 숫자·토큰 기호가 든 4~7자 짧은 토큰도 — R3 5차 minor: 대소문자 무관('bearer abc123')
    # (소문자 낱말 'bearer of' 는 그대로)
)
"""Authorization 헤더 값(``Authorization: Bearer …``·``Basic …``·``Token …``)과 홀로 나온 ``Bearer <토큰>``
(토큰 모양만 — 'the bearer of …'·'bearer bonds' 같은 글은 그대로)."""
_NS = r"(?:[-_ .]|%5[fF]|\\u005[fF]|\\u002[dD])?"
"""키 이름 낱말 사이 구분: 하이픈·밑줄·공백(``Secret Key``·``API Key``, R3 7차 minor 5)·JSON 유니코드 이스케이프
(``private\\u005fkey``)."""
_SECRET_NAME = (
    r"(?:x-)?[a-z0-9_-]*?"
    r"(?:api{s}key(?:{s}id)?|apikey|client{s}secret|client{s}id|access{s}token|auth{s}token|"
    r"refresh{s}token|secret{s}access{s}key|private{s}key(?:{s}id)?|secret{s}key|secret|token|passphrase|password|passwd|pwd"
    # R3 8차 minor 14: 환경변수·설정 키 꼴('DATA_GO_KR_KEY'·'SERVICE_KEY'·'AWS_ACCESS_KEY_ID'·'crtfc_key' — 앞 낱말 + 구분 + key),
    # 'credentials'·'webhook_url'·'signature'. 'monkey'·'turkey' 처럼 구분 없는 낱말은 아니다
    r"|[a-z0-9]+(?:[-_.]|%5[fF])key(?:{s}id)?|credentials?|webhook{s}url|signature"
    # R3i m17: camelCase 키('accessKey'·'sessionKey' — 소문자 뒤 대문자 K, 'monkey' 는 아니다)·홀로 쓴 'pass'('bypass'·'compass' 는 아니다)
    r"|(?-i:[a-z0-9]Key)(?:{s}id)?|(?<![a-z0-9])pass)"
).replace("{s}", _NS)
_KEY_SEP = r"(?:\\*[\"'`]|\])?\s*(?:[:=\uff1a\uff1d]|%3[dD])\s*"
"""키 이름 뒤 구분: (이스케이프된) 닫는 따옴표 또는 ``]``(``user[password]=…``), 공백·줄바꿈, ``:``·``=``·전각 ``：``·``＝``(R3 7차 minor 5)."""
_UNQUOTED_WORD = r"[^\s,;&\"'`<>{}\[\]\\]+"
HEADER_KEY_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])("
    + _SECRET_NAME
    + ")"
    + _KEY_SEP
    + r"(?!\\*[\"'`])("
    + _UNQUOTED_WORD
    + r"(?:[ \t]+(?![\w.-]+\s*[:=\uff1a\uff1d])"
    + _UNQUOTED_WORD
    + r")*)"
)
"""이름으로 비밀임을 아는 헤더·키 뒤의 따옴표 없는 값(``X-NCP-APIGW-API-KEY: …``·``x-api-key=…``,
snake_case ``client_secret=…``·``access_token: …`` — R3 4차 minor; ``aws_secret_access_key=…``·``private_key=…``·
``pwd=…`` — R3 5차 minor). R3 7차 minor 5: 공백으로 이어진 **여러 낱말**(``password = s3cr3t pw``)을 같은 줄에서
다음 ``이름=``/``이름:`` 앞까지, 공백 낀 키 이름(``Secret Key: …``)·전각 콜론."""
QUOTED_KEY_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])("
    + _SECRET_NAME
    + ")"
    + _KEY_SEP
    + r"(?P<esc>\\*)(?P<q>[\"'`])(?P<v>(?:\\.|[^\\\n])*?)(?=(?P=esc)(?P=q)|\r?\n|\Z)"
)
"""R3 6차 minor 9: 따옴표로 감싼 비밀 키 값은 **따옴표 안 전체**(공백·JSON 이스케이프 ``\\n``·``\\"`` 포함 — JSON
``"private_key": "-----BEGIN …\\n…"``·``password = 's3cr3t pw'``). 닫는 따옴표가 없으면(잘린 로그) 그 줄 끝까지.
R3 7차 minor 5: 이중·삼중 인코딩 JSON(``\\"password\\": \\"…\\"`` — 여는 따옴표 앞 역슬래시 수와 같은 닫는 따옴표까지),
백틱, 키와 값 사이 줄바꿈."""
_DASH = r"-{2,}[ \t]*"
PEM_PRIVATE_RE = re.compile(
    r"(?i)" + _DASH + r"BEGIN[ \t]+([A-Z0-9 ]*PRIVATE[ \t]+KEY[A-Z0-9 ]*?)[ \t]*-{2,}"
    r"(.*?)(?:" + _DASH + r"END\b[A-Z0-9 \t]*-{2,}|\Z)",
    re.DOTALL,
)
"""R3 6차 minor 9: PEM 개인키 블록(``-----BEGIN [RSA|EC|OPENSSH|ENCRYPTED|PGP ]PRIVATE KEY[ BLOCK]-----`` … ``-----END …-----``)의
여러 줄 본문 전체. END 줄이 없으면(잘린 로그) 글 끝까지. 공개 인증서(``CERTIFICATE``)는 그대로.
R3 7차 minor 5: 대소문자 무관, 대시 2개 이상·대시 안쪽 공백(``----- BEGIN … KEY -----``), END 이름이 달라도(불일치) 첫 END 줄에서 끝."""
_PHONE_KEY_RE = re.compile(r"(?i)(phone|tel|mobile|fax|전화|연락처|휴대)")
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_U = r"(?:_|%5f)"
QUERY_KEY_RE = re.compile(
    r"(?i)([?&;](?:[a-z0-9]*(?:_|%5f|-))?"
    r"(?:service"
    + _U
    + r"?key|api"
    + _U
    + r"?key|apikey|access"
    + _U
    + r"token|token|secret|password|signature|sig"
    r"|auth|key)(?:=|%3d))[^&;\s#\"']+"
)
"""URL 쿼리의 키 파라미터 값. R3 8차 minor 14: ``;`` 구분, 이름·'=' 의 퍼센트 인코딩(``api%5Fkey=``·``serviceKey%3D``),
앞 낱말 + 구분 + key(``crtfc_key``·``x_api_key``), ``signature``·``sig``·``auth``."""
SENSITIVE_KEY_RE = re.compile(
    r"(?i)(token|secret|password|passwd|passphrase|authorization|cookie|api[-_ ]?key|service[-_ ]?key|credential"
    r"|client[-_ ]?id|private[-_ ]?key"  # R3 6차 minor 9: dict 키 'private_key'·'privateKey' — 7차 minor 5: 'Private Key'·'API Key'
    r"|webhook|signature|^sig$|(?:^|[-_.])(?:key|auth)$|^auth[-_]|dsn"  # R3 8차 minor 14: 'key'·'crtfc_key'·'auth'·'signature'·'webhook_url'
    r"|(?-i:[a-z0-9]Key(?:Id)?)$|^pass$)"  # R3i m17: camelCase 'accessKey'·'sessionKeyId', 'pass'
)
COUNT_KEY_RE = re.compile(r"(?i)(?:count|len|length|size|tokens|total|bytes|seconds|_n|_s|_ms)$")
"""R3i m17: 비밀 키 이름이라도 개수·길이·시간을 뜻하는 키('max_tokens'·'token_count')의 숫자 값은 그대로 둔다."""
TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:sk-ant-[A-Za-z0-9_-]{10,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}|xox[abposr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|glpat-[A-Za-z0-9_-]{16,}"
    r"|AIza[0-9A-Za-z_-]{30,})"
)
"""R3i m17: 키 이름 없이 홀로 나온 공급자 토큰(접두어로 알 수 있는 것 — Anthropic·OpenAI ``sk-``, GitHub ``ghp_``·``github_pat_``,
Slack ``xox?-``, AWS 접근 키 ``AKIA…``, GitLab ``glpat-``, Google ``AIza…``)."""
_PROSE_BEFORE_BEARER = frozenset(
    {
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "its",
        "his",
        "her",
        "their",
        "our",
        "your",
        "my",
        "any",
        "each",
        "every",
        "no",
    }
)
"""R3i m17: 'the bearer certificates' 같은 산문 — 'bearer' 앞이 한정사이고 뒤가 소문자 낱말뿐이면 토큰이 아니다."""
COOKIE_RE = re.compile(r"(?im)(?<![A-Za-z0-9_-])(?:set-)?cookie[\"']?\s*[:=]\s*([^\r\n]+)")
"""R3 8차 minor 14: ``Cookie:``·``Set-Cookie:`` 헤더 값 전체(쿠키 이름·값·속성 — 세션 값이 섞인다)."""
JWT_RE = re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{8,}")
"""R3 8차 minor 14: 키 이름 없이 홀로 나온 JWT(``eyJ…``.``…``.``…``)."""
WEBHOOK_RE = re.compile(
    r"(?i)https?://(?:hooks\.slack\.com/(?:services|workflows|triggers)|(?:discord|discordapp)\.com/api/webhooks)"
    r"/([^\s\"'<>]+)"
)
"""R3 8차 minor 14: 웹훅 URL(Slack·Discord) — 경로가 곧 비밀이다(키 이름 없이 홀로 나와도)."""

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
    out: list[re.Pattern[str]] = []
    for form in _secret_forms(secrets):
        if len(form) < MIN_SECRET_PART_LEN:
            out.append(re.compile("".join(_char_pattern(ch) for ch in form)))
            continue
        # R3 8차 minor 15: 8자 이상 비밀값은 대소문자 무관 + 글자 사이 공백류(공백·줄바꿈·폭 없는 공백)도 같은 값으로 본다
        out.append(re.compile(_GAP.join(_char_pattern(ch) for ch in form), re.IGNORECASE))
        cores = _b64_cores(form)
        if cores:
            out.append(re.compile("|".join(re.escape(c) for c in sorted(cores, key=lambda c: (-len(c), c)))))
    return tuple(out)


_GAP = r"[\s​‌‍⁠﻿]*"


def _b64_cores(form: str) -> set[str]:
    """R3 8차 minor 15: 비밀값이 base64(표준·URL-safe) 안에 들어 있을 때(``Basic base64(id:secret)`` 등) 앞에 붙은 글자 수와
    무관하게 늘 보이는 가운데 조각 — 앞 바이트 수 mod 3 마다 하나. 8자 미만 조각은 버린다(흔한 글자열과 겹침)."""
    import base64

    raw = form.encode("utf-8")
    out: set[str] = set()
    for lead in range(3):
        enc = base64.b64encode(b"\0" * lead + raw).decode("ascii")
        start = -(-8 * lead // 6)
        end = (8 * (lead + len(raw))) // 6
        core = enc[start:end]
        if len(core) >= MIN_SECRET_PART_LEN:
            out |= {core, core.replace("+", "-").replace("/", "_")}
    return out


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


_KEY_FOLD_HINT = re.compile(r"[！-～　]|\\u00[2-7][0-9a-fA-F]")
_JSON_ESC = re.compile(r"\\u00([2-7][0-9a-fA-F])")


def _fold_keys(text: str) -> tuple[str, list[int]]:
    """키 이름 기반 패턴용 사본: 전각 ASCII → ASCII, JSON 유니코드 이스케이프(인쇄 가능한 ASCII ``\\u0020``~``\\u007e``) →
    그 글자. 반환 (사본, 위치 표) — 위치 표[i] = 사본 i 번째 글자의 원문 시작 위치(끝 = len(text)). 접을 것이 없으면 원문."""
    if not _KEY_FOLD_HINT.search(text):
        return text, list(range(len(text) + 1))
    out: list[str] = []
    pos: list[int] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and (m := _JSON_ESC.match(text, i)) is not None and 0x20 <= int(m.group(1), 16) <= 0x7E:
            out.append(chr(int(m.group(1), 16)))
            pos.append(i)
            i = m.end()
            continue
        o = ord(ch)
        out.append(chr(o - 0xFEE0) if 0xFF01 <= o <= 0xFF5E else (" " if ch == "　" else ch))
        pos.append(i)
        i += 1
    pos.append(n)
    return "".join(out), pos


def find_sensitive(text: str, secrets: Iterable[str] = ()) -> list[Finding]:
    """겹치지 않는 탐지 결과(앞에서부터). 비밀값 > 주민번호 > 전화 > 이메일 순으로 우선."""
    taken: list[Finding] = []

    def overlaps(a: int, b: int) -> bool:
        return any(a < f.end and f.start < b for f in taken)

    # R3 8차 minor 14: 키 이름 기반 패턴은 '키 접힘' 사본에서 찾는다 — 전각 ASCII(``ｐａｓｓｗｏｒｄ=``)·JSON 유니코드
    # 이스케이프(``"\\u0070assword"``)를 ASCII 로 편 사본과 원문 위치 표(``pos``)로 원문 구간을 가린다
    keyed, pos = _fold_keys(text)

    def add(kind: Kind, a: int, b: int) -> None:
        a, b = pos[a], pos[b]
        if b > a and not overlaps(a, b):
            taken.append(Finding(kind, a, b))

    # 긴 비밀 구간(PEM 본문·따옴표 값 전체)을 먼저 — 그 안의 짧은 탐지가 먼저 잡혀 구간 전체가 겹침으로 버려지지 않게(m9)
    for m in PEM_PRIVATE_RE.finditer(keyed):
        add("secret", m.start(2), m.end(2))
    for m in QUOTED_KEY_RE.finditer(keyed):
        add("secret", m.start("v"), m.end("v"))
    for pattern in _secret_patterns(tuple(secrets)):
        for m in pattern.finditer(text):
            if not overlaps(m.start(), m.end()):
                taken.append(Finding("secret", m.start(), m.end()))
    for m in COOKIE_RE.finditer(keyed):
        add("secret", m.start(1), m.end(1))
    for m in WEBHOOK_RE.finditer(keyed):
        add("secret", m.start(1), m.end(1))
    for m in JWT_RE.finditer(keyed):
        add("secret", m.start(), m.end())
    for m in TOKEN_RE.finditer(keyed):
        add("secret", m.start(), m.end())
    for m in AUTH_HEADER_RE.finditer(keyed):
        group = next(g for g in (1, 2, 3) if m.group(g) is not None)
        if group == 2 and m.group(2).isalpha() and m.group(2).islower():
            before = keyed[: m.start()].split()
            if before and before[-1].lower().strip("\"'(") in _PROSE_BEFORE_BEARER:
                continue  # R3i m17: 'the bearer certificates' — 산문(토큰 아님)
        add("secret", m.start(group), m.end(group))
    for m in HEADER_KEY_RE.finditer(keyed):
        add("secret", m.start(2), m.end(2))
    for m in QUERY_KEY_RE.finditer(keyed):
        add("query_key", m.start() + len(m.group(1)), m.end())
    for m in DSN_PASSWORD_RE.finditer(keyed):
        add("secret", m.start(1), m.end(1))
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
            numeric = isinstance(v, int | float) and not isinstance(v, bool)
            if (
                SENSITIVE_KEY_RE.search(name)
                and v is not None
                and not isinstance(v, bool)
                # R3i m17: 비밀 키의 정수·실수 값도 가린다(숫자 PIN·토큰) — 개수·길이 키('max_tokens')는 그대로
                and not (numeric and COUNT_KEY_RE.search(name))
            ):
                out[name] = "[REDACTED:key]"
            else:
                out[name] = _redact(v, secrets, name)
        return out
    # R3 8차 minor 14: (이름, 값) 쌍 리스트 — 헤더 튜플 목록·form 쌍([("Authorization", "Bearer …")], [["password", …]])
    if (
        isinstance(obj, list | tuple)
        and len(obj) == 2
        and isinstance(obj[0], str)
        and isinstance(obj[1], str)
        and SENSITIVE_KEY_RE.search(obj[0])
    ):
        return [obj[0], "[REDACTED:key]"]
    if isinstance(obj, list | tuple | set | frozenset):
        return [_redact(v, secrets, key) for v in obj]
    return redact_text(str(obj), secrets)
