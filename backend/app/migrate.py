"""DB 마이그레이션 진입점 — ``ENV_FILE`` 을 존중한다 (R4 M4, DECISIONS D18-7).

``uv run alembic upgrade head`` 는 환경변수 ``DATABASE_URL`` 만 읽는다(``contracts/migrations/env.py`` — 계약 디렉터리,
WP0). runbook 대로 ``ENV_FILE=../r4/.env`` 만 주면 조용히 ``backend/dev.db``(SQLite)를 마이그레이션했다(R4). 이 진입점은
앱 설정(``ENV_FILE`` → ``.env`` → 환경변수)의 ``DATABASE_URL`` 을 alembic 에 넘긴다::

    ENV_FILE=../r4/.env uv run python -m app.migrate            # = upgrade head
    uv run python -m app.migrate current

URL 은 출력하지 않는다(비밀번호가 들어 있을 수 있다 — 규칙 6·10). 방언 이름과 대상(파일 이름/호스트 없음)만 알린다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

__all__ = ["alembic_config", "main", "resolved_database_url"]

BACKEND = Path(__file__).resolve().parents[1]


def resolved_database_url() -> str:
    """앱 설정의 DB URL(``ENV_FILE`` 존중). 환경변수 ``DATABASE_URL`` 이 있으면 설정이 그것을 쓴다(pydantic 우선순위)."""
    from app.core.settings import load_settings

    return str(load_settings().database_url)


def alembic_config(url: str) -> object:
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND.parent / "contracts" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def main(argv: Sequence[str] | None = None) -> int:
    from alembic import command

    args = list(argv if argv is not None else sys.argv[1:]) or ["upgrade", "head"]
    url = resolved_database_url()
    os.environ["DATABASE_URL"] = (
        url  # env.py 는 DATABASE_URL 을 먼저 본다(계약 env.py 를 바꾸지 않고 같은 값을 넘긴다)
    )
    cfg = alembic_config(url)
    dialect = url.split(":", 1)[0]
    print(
        f"app.migrate: {' '.join(args)} ({dialect}, ENV_FILE={'있음' if os.environ.get('ENV_FILE') else '없음'})"
    )
    if args[0] == "upgrade":
        command.upgrade(cfg, args[1] if len(args) > 1 else "head")  # type: ignore[arg-type]
    elif args[0] == "downgrade":
        command.downgrade(cfg, args[1])  # type: ignore[arg-type]
    elif args[0] == "current":
        command.current(cfg)  # type: ignore[arg-type]
    else:
        raise SystemExit(f"지원하지 않는 명령: {args[0]} (upgrade [rev] | downgrade rev | current)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
