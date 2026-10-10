"""오류 → 계약 ``Error`` 본문 (contracts/schemas/error.json).

- ``ApiError(status, code, detail, field_errors)``: 라우터가 던지는 계약 오류.
- ``ContractViolation``: 출처(field_provenance) 없는 수치를 내보내려 함 — ENV=dev 에서만 던진다(T13, 500).
- ``install_handlers(app)``: HTTPException·요청 검증 오류·그 밖의 예외까지 모두
  ``{code, detail, field_errors?}`` 로.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

__all__ = [
    "ApiError",
    "ContractViolation",
    "bad_request",
    "conflict",
    "install_handlers",
    "not_found",
    "validation_error",
]

log = get_logger("app.api")

_STATUS_CODE = {
    400: "validation_error",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "not_found",
    409: "conflict",
    422: "validation_error",
    503: "judge_unavailable",
}


class ApiError(Exception):
    """계약 오류 응답. ``field_errors`` 는 [{loc: [...], msg}]."""

    def __init__(
        self,
        status: int,
        code: str,
        detail: str,
        *,
        field_errors: Sequence[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.field_errors = list(field_errors) if field_errors is not None else None
        self.headers = headers

    def body(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "detail": self.detail}
        if self.field_errors is not None:
            out["field_errors"] = self.field_errors
        return out


class ContractViolation(Exception):
    """출처 없는 수치(ENV=dev). 500 contract_violation."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def conflict(detail: str, *, code: str = "conflict") -> ApiError:
    return ApiError(409, code, detail)


def validation_error(detail: str, loc: Sequence[str | int] = ("body",), msg: str | None = None) -> ApiError:
    return ApiError(422, "validation_error", detail, field_errors=[{"loc": list(loc), "msg": msg or detail}])


def bad_request(detail: str) -> ApiError:
    return ApiError(422, "validation_error", detail)


def _json(status: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=body, headers=headers)


def _loc(loc: Sequence[Any]) -> list[str | int]:
    return [x if isinstance(x, int) else str(x) for x in loc]


def install_handlers(app: FastAPI) -> None:
    """앱 전체(라우터 밖 404 포함)의 오류 본문을 계약 Error 로 맞춘다."""

    async def api_error(_req: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ApiError)
        return _json(exc.status, exc.body(), exc.headers)

    async def contract_violation(_req: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ContractViolation)
        log.error("api.contract_violation", extra={"detail": exc.detail})
        return _json(500, {"code": "contract_violation", "detail": exc.detail})

    prefix = str(getattr(getattr(app.state, "settings", None), "api_prefix", "/api") or "").rstrip("/")

    def contract_path(req: Request) -> str:
        path = str(req.scope.get("path") or req.url.path)  # url.path 는 '#' 뒤를 잘라낸다
        return path[len(prefix) :] if prefix and path.startswith(prefix + "/") else path

    async def http_error(req: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        code = _STATUS_CODE.get(exc.status_code, "internal" if exc.status_code >= 500 else "validation_error")
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        headers = dict(getattr(exc, "headers", None) or {})
        if exc.status_code == 400:  # 본문 JSON 해석 실패 등 → 계약의 422 validation_error
            return _json(
                422,
                {
                    "code": "validation_error",
                    "detail": detail,
                    "field_errors": [{"loc": ["body"], "msg": detail}],
                },
            )
        if exc.status_code == 405:
            from app.api.contract import allowed_methods

            allowed = allowed_methods(contract_path(req))
            if allowed:
                headers["Allow"] = ", ".join(allowed)
        return _json(exc.status_code, {"code": code, "detail": detail}, headers or None)

    async def request_invalid(req: Request, exc: Exception) -> JSONResponse:
        """요청 검증 실패. 계약이 그 operation 에 422 를 문서화하지 않았고 404 는 있으면(경로·조회 파라미터가
        가리키는 대상이 없음) 404 not_found 로 답한다 — 문서화된 상태 코드만 낸다."""
        assert isinstance(exc, RequestValidationError)
        from app.api.contract import allowed_methods, documented_statuses

        allowed = allowed_methods(contract_path(req))
        if allowed and req.method.upper() not in allowed:
            # 같은 모양의 다른 경로('/regions/{id}' PATCH)에 잡힌 글자 그대로 경로('/regions/resolve') — 405
            return _json(
                405,
                {"code": _STATUS_CODE[405], "detail": "Method Not Allowed"},
                {"Allow": ", ".join(allowed)},
            )

        errors = [{"loc": _loc(e.get("loc", ())), "msg": str(e.get("msg", ""))} for e in exc.errors()]
        detail = (
            "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in errors)[:500]
            or "invalid request"
        )
        statuses = documented_statuses(req.method, contract_path(req))
        only_path = bool(errors) and all(e["loc"][:1] == ["path"] for e in errors)
        if "404" in statuses and (only_path or "422" not in statuses):
            return _json(404, {"code": "not_found", "detail": detail})
        return _json(422, {"code": "validation_error", "detail": detail, "field_errors": errors})

    async def overflow(req: Request, exc: Exception) -> JSONResponse:
        """DB 정수 범위(64비트)를 넘는 id·파라미터 = 그런 행 없음."""
        from app.api.contract import documented_statuses

        statuses = documented_statuses(req.method, contract_path(req))
        if "404" in statuses:
            return _json(404, {"code": "not_found", "detail": "id out of range"})
        return _json(
            422,
            {
                "code": "validation_error",
                "detail": "integer out of range",
                "field_errors": [{"loc": ["query"], "msg": "integer out of range"}],
            },
        )

    async def not_materialized(_req: Request, exc: Exception) -> JSONResponse:
        """발행 리비전 저장본(D13-1): 그 리비전에 없는 시나리오·생활권 = 404, 저장본 자체가 없음 = 500(실시간 폴백 없음)."""
        from app.snapshot_view import NotInRevision

        if isinstance(exc, NotInRevision):
            return _json(404, {"code": "not_found", "detail": str(exc)})
        log.error("api.snapshot_view_missing", extra={"detail": str(exc)})
        return _json(500, {"code": "internal", "detail": str(exc)})

    async def internal(_req: Request, exc: Exception) -> JSONResponse:
        log.exception("api.internal", extra={"error": type(exc).__name__})
        return _json(500, {"code": "internal", "detail": type(exc).__name__})

    app.add_exception_handler(ApiError, api_error)
    app.add_exception_handler(ContractViolation, contract_violation)
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(RequestValidationError, request_invalid)
    app.add_exception_handler(OverflowError, overflow)
    from app.snapshot_view import NotMaterialized

    app.add_exception_handler(NotMaterialized, not_materialized)
    app.add_exception_handler(Exception, internal)
