"""계약 원본(contracts/openapi.bundled.yaml)으로 요청 본문을 검증한다.

pydantic 생성물(``app.core.contracts_gen``)은 느슨하게 형변환하고(문자열 '1' → 1) if/then 조건을 모른다.
API 는 계약을 '그대로' 구현해야 하므로 본문은 JSON Schema 2020-12(형식 검사 포함)로 먼저 검증하고,
통과한 값만 pydantic 모델로 읽는다. 실패는 422 validation_error + field_errors.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from app.api.errors import ApiError

__all__ = [
    "CONTRACTS_DIR",
    "OPENAPI_BUNDLED",
    "allowed_methods",
    "bundled",
    "check_body",
    "check_schema",
    "documented_statuses",
    "query_names",
]

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts"
OPENAPI_BUNDLED = CONTRACTS_DIR / "openapi.bundled.yaml"
_URN = "urn:subscription-analyzer:openapi"


@functools.cache
def bundled() -> dict[str, Any]:
    loader: Any = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with OPENAPI_BUNDLED.open(encoding="utf-8") as f:
        doc: dict[str, Any] = yaml.load(f, Loader=loader)
    return doc


@functools.cache
def _registry() -> Registry[Any]:
    resource: Resource[Any] = Resource.from_contents(bundled(), default_specification=DRAFT202012)
    registry: Registry[Any] = Registry().with_resource(_URN, resource)
    return registry


@functools.cache
def _validator(pointer: str) -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"{_URN}#{pointer}"}, registry=_registry(), format_checker=FormatChecker()
    )


@functools.cache
def _request_pointer(operation_id: str) -> str:
    for path, item in bundled()["paths"].items():
        for method, op in item.items():
            if isinstance(op, dict) and op.get("operationId") == operation_id:
                esc = path.replace("~", "~0").replace("/", "~1")
                return f"/paths/{esc}/{method}/requestBody/content/application~1json/schema"
    raise KeyError(operation_id)


def _errors(validator: Draft202012Validator, value: Any, root: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for err in sorted(validator.iter_errors(value), key=lambda e: [str(p) for p in e.absolute_path]):
        loc: list[str | int] = [root, *[p if isinstance(p, int) else str(p) for p in err.absolute_path]]
        out.append({"loc": loc, "msg": err.message[:300]})
        if len(out) >= 20:
            break
    return out


def _raise(errors: list[dict[str, Any]]) -> None:
    if errors:
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in errors)[:500]
        raise ApiError(422, "validation_error", detail, field_errors=errors)


def non_finite(value: Any, loc: tuple[str | int, ...] = ("body",)) -> list[dict[str, Any]]:
    """본문 안의 NaN·Infinity(JSON 표준 밖 — 파이썬 json 은 받는다, ``1e400`` 도 inf) 위치. R3 5차 M7: 커밋 뒤 500·이후 GET
    500 이 나던 것을 모든 쓰기 엔드포인트 공통으로 422 로."""
    import math

    if isinstance(value, float) and not math.isfinite(value):
        return [{"loc": list(loc), "msg": "유한한 숫자가 아니다(NaN·Infinity 거부)"}]
    out: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for k, v in value.items():
            out.extend(non_finite(v, (*loc, str(k))))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.extend(non_finite(v, (*loc, i)))
    return out


def check_body(operation_id: str, body: Any) -> None:
    """operation 의 requestBody 스키마로 검증. 실패면 422. NaN·Infinity 는 스키마와 무관하게 422(M7 — 공용)."""
    bad = non_finite(body)
    if bad:
        from app.api.errors import ApiError

        raise ApiError(
            422, "validation_error", "숫자는 유한해야 한다(NaN·Infinity 거부)", field_errors=bad[:20]
        )
    _raise(_errors(_validator(_request_pointer(operation_id)), body, "body"))


def check_schema(component: str, value: Any, *, root: str = "body") -> None:
    """components.schemas.<component> 로 검증(잡 payload 등). 실패면 422."""
    _raise(_errors(_validator(f"/components/schemas/{component}"), value, root))


_METHODS = ("get", "put", "post", "delete", "patch", "head", "options")


@functools.cache
def _templates() -> tuple[tuple[re.Pattern[str], str, dict[str, frozenset[str]]], ...]:
    out = []
    for path, item in bundled()["paths"].items():
        rx = re.compile("^" + re.sub(r"\\{[^/]+?\\}", "[^/]+", re.escape(path)) + "$")
        ops = {
            m.upper(): frozenset(str(k) for k in (op.get("responses") or {}))
            for m, op in item.items()
            if m in _METHODS
        }
        out.append((rx, path, ops))
    # 글자 그대로인 경로가 먼저: '/regions/resolve' 가 '/regions/{id}' 로 잡히지 않게(PATCH → 405, 422 아님)
    out.sort(key=lambda t: t[1].count("{"))
    return tuple(out)


def _match(path: str) -> tuple[str, dict[str, frozenset[str]]] | None:
    for rx, template, ops in _templates():
        if rx.match(path):
            return template, ops
    return None


def allowed_methods(path: str) -> list[str]:
    """계약 경로(접두 없이)의 문서화된 메서드(405 Allow 헤더)."""
    hit = _match(path)
    return sorted(hit[1]) if hit else []


def documented_statuses(method: str, path: str) -> frozenset[str]:
    """계약 경로·메서드의 문서화된 응답 상태 코드. 없으면 빈 집합."""
    hit = _match(path)
    return hit[1].get(method.upper(), frozenset()) if hit else frozenset()


def _param(p: dict[str, Any]) -> dict[str, Any]:
    ref = p.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/parameters/"):
        resolved: dict[str, Any] = bundled()["components"]["parameters"][ref.rsplit("/", 1)[-1]]
        return resolved
    return p


@functools.cache
def _query_names() -> dict[tuple[str, str], tuple[frozenset[str], frozenset[str]]]:
    """(METHOD, 경로 템플릿) → (일반 조회 파라미터 이름, deepObject 이름)."""
    out: dict[tuple[str, str], tuple[frozenset[str], frozenset[str]]] = {}
    for path, item in bundled()["paths"].items():
        common = [_param(p) for p in item.get("parameters") or []]
        for method, op in item.items():
            if method not in _METHODS:
                continue
            params = common + [_param(p) for p in op.get("parameters") or []]
            plain = frozenset(
                p["name"] for p in params if p.get("in") == "query" and p.get("style") != "deepObject"
            )
            deep = frozenset(
                p["name"] for p in params if p.get("in") == "query" and p.get("style") == "deepObject"
            )
            out[(method.upper(), path)] = (plain, deep)
    return out


def query_names(method: str, path: str) -> tuple[frozenset[str], frozenset[str]] | None:
    """요청 경로(접두 없이)의 계약 조회 파라미터 이름. 계약에 없는 경로면 None."""
    hit = _match(path)
    if hit is None:
        return None
    return _query_names().get((method.upper(), hit[0]))
