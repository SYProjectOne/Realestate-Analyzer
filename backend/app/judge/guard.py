"""판정기 payload 검문 (AGENTS 규칙 6, RA §10, T14).

payload 의 모든 문자열(키 포함)을 ``app.core.redact.find_sensitive`` 로 훑는다:
전화번호·주민등록번호·이메일·설정 비밀값(+판정기 자격 증명 환경변수 값)·URL 키 파라미터.
하나라도 있으면 거부 — 어댑터는 판정기에 보내지 않고 status='blocked' 행을 남긴다.
blocked 행·봉투·로그에는 원문이 아니라 걸린 위치(JSON 경로)와 종류만 남긴다.

공개 공고문에 흔한 대표번호 등은 ``payloads.public_text`` 가 payload 를 만들 때 미리 가린다.
guard 는 마지막 방어선이다.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from app.core.redact import find_sensitive, sensitive_int_kind
from app.core.settings import Settings, get_settings

__all__ = [
    "CREDENTIAL_ENV_PREFIXES",
    "GuardFinding",
    "GuardResult",
    "blocked_input_json",
    "check_payload",
    "default_secrets",
]

CREDENTIAL_ENV_PREFIXES: tuple[str, ...] = (
    "TYPESAFE_",
    "OPENROUTER_",
    "AI_GATEWAY_",
    "CLOUDFLARE_",
    "JEV_API_KEY",
    "JEV_CLOUDFLARE_",
)
"""판정기 자체 자격 증명(자식 프로세스에 넘기는 것). 그 값이 payload 에 섞이면 거부한다."""
_CREDENTIAL_HINTS = ("KEY", "TOKEN", "SECRET")
_SAFE_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,40}")


@dataclass(frozen=True, slots=True)
class GuardFinding:
    kind: str  # phone | rrn | email | secret | query_key
    path: str  # JSON 경로, 예: $.candidates[0].text  (키에서 걸리면 끝에 '<key>')


@dataclass(frozen=True, slots=True)
class GuardResult:
    findings: list[GuardFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def kinds(self) -> list[str]:
        return sorted({f.kind for f in self.findings})

    def summary(self) -> list[dict[str, str]]:
        return [{"kind": f.kind, "path": f.path} for f in self.findings]


def default_secrets(settings: Settings | None = None) -> list[str]:
    """설정 비밀값 전부 + DATABASE_URL 의 비밀번호 + 판정기 자격 증명 환경변수 값."""
    s = settings or get_settings()
    out = list(s.secret_values())
    try:
        db_password = urlsplit(s.database_url).password
    except ValueError:
        db_password = None
    if db_password:
        out.append(db_password)
    for name, value in os.environ.items():
        upper = name.upper()
        if value and upper.startswith(CREDENTIAL_ENV_PREFIXES) and any(h in upper for h in _CREDENTIAL_HINTS):
            out.append(value)
    return out


def check_payload(payload: Any, *, secrets: Sequence[str] | None = None) -> GuardResult:
    secret_list = list(secrets) if secrets is not None else default_secrets()
    findings: list[GuardFinding] = []
    for path, text in _walk(payload, "$"):
        for f in find_sensitive(text, secret_list):
            findings.append(GuardFinding(kind=f.kind, path=path))
    for path, key, number in _walk_ints(payload, "$", None):
        kind = sensitive_int_kind(number, key)
        if kind is not None:
            findings.append(GuardFinding(kind=kind, path=path))
    return GuardResult(findings)


def _walk_ints(obj: Any, path: str, key: str | None) -> Iterable[tuple[str, str | None, int]]:
    """정수 값(bool 제외)과 그 dict 키 — 정수로 들어온 주민번호·전화번호 검사용."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, int):
        yield path, key, obj
    elif isinstance(obj, dict):
        for i, (k, v) in enumerate(obj.items()):
            name = str(k)
            seg = f".{name}" if _SAFE_KEY.fullmatch(name) else f".<key{i}>"
            yield from _walk_ints(v, f"{path}{seg}", name)
    elif isinstance(obj, list | tuple):
        for i, v in enumerate(obj):
            yield from _walk_ints(v, f"{path}[{i}]", key)


def blocked_input_json(result: GuardResult) -> dict[str, Any]:
    """blocked 행의 input_json — 원문 대신 걸린 위치·종류만."""
    return {"blocked": True, "findings": result.summary()}


def _walk(obj: Any, path: str) -> Iterable[tuple[str, str]]:
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for i, (k, v) in enumerate(obj.items()):
            key = str(k)
            # 경로에는 안전한 키 이름만 쓴다(키 자체가 민감값일 수 있다)
            seg = f".{key}" if _SAFE_KEY.fullmatch(key) else f".<key{i}>"
            yield f"{path}{seg}<key>", key
            yield from _walk(v, f"{path}{seg}")
    elif isinstance(obj, list | tuple):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")
    elif obj is not None and not isinstance(obj, bool | int | float):
        yield path, str(obj)
