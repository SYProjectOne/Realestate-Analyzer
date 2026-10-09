from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.core.settings import Settings, env_var_names, get_settings, set_settings

# RA §10 환경변수 + 지시서 추가분
REQUIRED_ENV = {
    "DATABASE_URL",
    "RAW_DIR",
    "API_TOKEN",
    "READONLY_TOKEN",
    "JEV_MCP_CMD",
    "DATA_GO_KR_KEY",
    "NEWS_API_KEY",
    "WEBHOOK_URL",
    "JUDGE_ADAPTER",
    "ENV",
    "REFERENCE_DIR",
    "TZ",
    "HTTP_RATE_PER_HOST",
    "HTTP_MAX_RETRIES",
}


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in env_var_names():
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def make(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def test_all_ra_env_vars_are_fields() -> None:
    assert set(env_var_names()) >= REQUIRED_ENV


def test_defaults(clean_env: pytest.MonkeyPatch) -> None:
    s = make()
    assert s.env == "dev"
    assert s.tz == "Asia/Seoul"
    assert s.http_rate_per_host == 1.0
    assert s.http_max_retries >= 1
    assert s.jev_mcp_cmd == "npx -y @jkudish/jev-mcp@latest"  # DECISIONS D6
    assert s.database_url.startswith("sqlite:///")
    assert isinstance(s.raw_dir, Path)
    assert isinstance(s.reference_dir, Path)
    assert s.api_token is None
    assert s.webhook_url is None


def test_judge_timeouts_and_robots_exempt_defaults(clean_env: pytest.MonkeyPatch) -> None:
    s = make()
    assert s.judge_call_timeout_s == 120
    assert s.judge_start_timeout_s == 300
    assert s.http_robots_exempt_hosts == ["apis.data.go.kr", "openapi.naver.com"]


@pytest.mark.parametrize(
    "raw",
    ["apis.data.go.kr, OpenAPI.naver.com", '["apis.data.go.kr", "openapi.naver.com"]'],
)
def test_robots_exempt_hosts_from_env(clean_env: pytest.MonkeyPatch, raw: str) -> None:
    clean_env.setenv("HTTP_ROBOTS_EXEMPT_HOSTS", raw)
    clean_env.setenv("JUDGE_CALL_TIMEOUT_S", "30")
    s = make()
    assert s.http_robots_exempt_hosts == ["apis.data.go.kr", "openapi.naver.com"]
    assert s.judge_call_timeout_s == 30


def test_robots_exempt_hosts_empty(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("HTTP_ROBOTS_EXEMPT_HOSTS", "")
    assert make().http_robots_exempt_hosts == []


def test_report_echarts_js_setting(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """WP8 ECharts 번들 경로는 Settings(REPORT_ECHARTS_JS, 계약 2026-10-09.3). 빈 값 = None."""
    assert make().report_echarts_js is None
    clean_env.setenv("REPORT_ECHARTS_JS", "")
    assert make().report_echarts_js is None
    bundle = tmp_path / "echarts.min.js"
    clean_env.setenv("REPORT_ECHARTS_JS", str(bundle))
    assert make().report_echarts_js == bundle
    assert "REPORT_ECHARTS_JS" in env_var_names()


def test_env_override_and_secret_types(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("API_TOKEN", "tok-AAAA1111BBBB2222")
    clean_env.setenv("DATA_GO_KR_KEY", "key+with/slash==")
    clean_env.setenv("HTTP_RATE_PER_HOST", "0.5")
    clean_env.setenv("JUDGE_ADAPTER", "mock")
    clean_env.setenv("RAW_DIR", "/data/raw")
    s = make()
    assert isinstance(s.api_token, SecretStr)
    assert s.api_token.get_secret_value() == "tok-AAAA1111BBBB2222"
    assert "tok-AAAA1111BBBB2222" not in repr(s)
    assert "tok-AAAA1111BBBB2222" not in str(s.model_dump())
    assert s.http_rate_per_host == 0.5
    assert s.judge_adapter == "mock"
    assert s.raw_dir == Path("/data/raw")


def test_secret_values_lists_every_secret(clean_env: pytest.MonkeyPatch) -> None:
    s = make(
        api_token="t1-xxxxxxxx",
        readonly_token="t2-yyyyyyyy",
        data_go_kr_key="k3-zzzzzzzz",
        news_api_key="k4-wwwwwwww",
        webhook_url="https://hooks.example.test/abc",
    )
    assert set(s.secret_values()) == {
        "t1-xxxxxxxx",
        "t2-yyyyyyyy",
        "k3-zzzzzzzz",
        "k4-wwwwwwww",
        "https://hooks.example.test/abc",
    }


def test_invalid_env_rejected(clean_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        make(env="staging")
    with pytest.raises(ValidationError):
        make(judge_adapter="openai")
    with pytest.raises(ValidationError):
        make(http_rate_per_host=0)


def test_prod_requires_api_token(clean_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        make(env="prod")
    s = make(env="prod", api_token="x" * 32)
    assert s.env == "prod"


def test_is_sqlite(clean_env: pytest.MonkeyPatch) -> None:
    assert make(database_url="sqlite:///./x.db").is_sqlite
    assert not make(database_url="postgresql+psycopg://u:p@db:5432/x").is_sqlite


def test_get_settings_override(test_settings: Settings) -> None:
    assert get_settings() is test_settings
    other = make(env="dev", database_url="sqlite:///./other.db")
    set_settings(other)
    assert get_settings() is other
