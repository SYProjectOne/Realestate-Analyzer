"""판정기 어댑터 (WP3). 판정기를 직접 부르는 코드는 이 패키지 밖에 없다(AGENTS 규칙 4).

진입점
- ``get_adapter(settings, fixture_dir=None)`` — ``settings.judge_adapter``:
  ``jev`` → JevMcpAdapter, ``mock`` → MockAdapter.
- ``pipeline`` — P1~P9 단계 함수(WP7 이 순서대로 부른다).
- ``claims.RuleClaimSplitter`` — ClaimSplitter 구현.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.settings import Settings
    from app.judge.jev_mcp import JevMcpAdapter
    from app.judge.mock import MockAdapter

__all__ = ["get_adapter"]


def get_adapter(
    settings: Settings | None = None, *, fixture_dir: Path | None = None
) -> JevMcpAdapter | MockAdapter:
    """설정대로 어댑터를 만든다. mock 은 녹화 디렉터리(``contracts/fixtures/<fixture>``)가 필요하다."""
    from app.core.settings import get_settings

    s = settings or get_settings()
    if s.judge_adapter == "mock":
        if fixture_dir is None:
            raise ValueError("JUDGE_ADAPTER=mock 에는 fixture_dir(contracts/fixtures/<fixture>)가 필요하다")
        from app.core.db import get_sessionmaker
        from app.judge.mock import MockAdapter

        # 재생 봉투를 judgment_log 에 남겨 판정 확률의 출처(jl_<seq>)가 실제 어댑터와 같게(R3 마무리)
        # 세션은 호출 때마다 지금 엔진에서(엔진이 닫혔다 다시 만들어져도 닫힌 엔진에 연결을 남기지 않게)
        return MockAdapter(fixture_dir, session_factory=lambda: get_sessionmaker(s)())
    from app.judge.jev_mcp import JevMcpAdapter

    return JevMcpAdapter(s.jev_mcp_cmd)
