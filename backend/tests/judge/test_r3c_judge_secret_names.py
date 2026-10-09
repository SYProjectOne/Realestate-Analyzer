"""CEO 요청(minor 32 후속): 판정기 자격 증명 env 이름 목록 = Settings ``JUDGE_SECRET_ENV_NAMES``.

이름이 자격 증명 모양(KEY·TOKEN …)이 아니어도 목록에 있으면 그 값을 가린다. 목록은 쉼표 구분 또는 JSON 배열.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.settings import DEFAULT_JUDGE_SECRET_ENV_NAMES, Settings, set_settings
from app.judge.jev_mcp import judge_secret_values

ODD = "plain-looking-value-123"


@pytest.fixture
def settings_with_odd_name() -> Iterator[Settings]:
    s = Settings(_env_file=None, judge_secret_env_names="JEV_ACCOUNT_REF, OPENROUTER_API_KEY")  # type: ignore[call-arg, arg-type]
    set_settings(s)
    yield s
    set_settings(None)


def test_listed_name_is_masked_even_without_credential_like_name(settings_with_odd_name: Settings) -> None:
    assert settings_with_odd_name.judge_secret_env_names == ["JEV_ACCOUNT_REF", "OPENROUTER_API_KEY"]
    env = {"JEV_ACCOUNT_REF": ODD, "JEV_MCP_MODEL": "jev-latest"}
    values = judge_secret_values(env)
    assert ODD in values  # 이름 패턴(KEY·TOKEN …)으로는 못 잡는 값
    assert "jev-latest" not in values


def test_default_names_and_json_list() -> None:
    assert Settings(_env_file=None).judge_secret_env_names == list(DEFAULT_JUDGE_SECRET_ENV_NAMES)  # type: ignore[call-arg]
    s = Settings(_env_file=None, judge_secret_env_names='["A_REF", "B_REF"]')  # type: ignore[call-arg, arg-type]
    assert s.judge_secret_env_values({"a_ref": "x", "B_REF": "", "C": "z"}) == ["x"]
