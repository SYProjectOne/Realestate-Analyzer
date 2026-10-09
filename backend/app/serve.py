"""api 기동 진입점: ``python -m app.serve`` (R3 M11).

- 바인드 주소 = ``API_HOST``(기본 127.0.0.1), 포트 = ``API_PORT``(기본 8000).
- 토큰(API_TOKEN·READONLY_TOKEN)이 모두 비면 무인증 서버다 → ``API_HOST`` 를 무시하고 127.0.0.1 에만
  바인드하고 경고를 남긴다. 무인증 서버는 인증 의존성도 루프백 접속만 받는다(``api.deps.require_auth``)
  — 이중 방어.
- 컨테이너(infra/Dockerfile.api)는 ``API_HOST=0.0.0.0`` 을 주고, compose 는 API_TOKEN 이 비면 기동하지 않는다.
"""

from __future__ import annotations

import sys
from typing import Any

from app.core.logging import configure_logging, get_logger
from app.core.settings import Settings, get_settings

__all__ = ["LOOPBACK", "bind_host", "main", "uvicorn_kwargs"]

log = get_logger("app.serve")

LOOPBACK = "127.0.0.1"


def bind_host(settings: Settings) -> str:
    """토큰이 하나라도 있으면 ``API_HOST``, 모두 비면 127.0.0.1(+경고)."""
    if settings.auth_enabled:
        return settings.api_host
    if settings.api_host != LOOPBACK:
        log.warning(
            "API_TOKEN·READONLY_TOKEN 이 모두 비어 있어 API_HOST=%s 대신 127.0.0.1 에만 바인드한다",
            settings.api_host,
        )
    else:
        log.warning("API_TOKEN·READONLY_TOKEN 이 모두 비어 있다 — 인증 없이 127.0.0.1 에만 연다")
    return LOOPBACK


def uvicorn_kwargs(settings: Settings) -> dict[str, Any]:
    return {
        "app": "app.main:app",
        "host": bind_host(settings),
        "port": settings.api_port,
        "proxy_headers": True,
        # 프록시 헤더(X-Forwarded-For)는 같은 compose 네트워크의 web(nginx)만 보낸다.
        # 무인증이면 루프백 바인드라 외부에서 헤더를 꾸며 루프백인 척할 수 없다.
        "forwarded_allow_ips": "*",
        "log_config": None,
    }


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    settings = get_settings()
    configure_logging(settings)
    kwargs = uvicorn_kwargs(settings)
    log.info("api.serve", extra={"host": kwargs["host"], "port": kwargs["port"], "env": settings.env})
    uvicorn.run(**kwargs)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
