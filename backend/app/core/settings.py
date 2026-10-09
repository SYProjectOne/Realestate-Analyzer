"""환경 설정 (RA §10, DECISIONS D1·D6).

모든 값은 환경변수(또는 ``.env`` 파일)에서 온다. 비밀값은 ``SecretStr``.
``.env`` 경로는 기본 작업 디렉터리의 ``.env`` 이고, 환경변수 ``ENV_FILE`` 로 다른 파일을 가리킬 수 있다
(worktree 처럼 ``.env`` 가 없는 체크아웃에서 메인 체크아웃의 ``.env`` 를 읽을 때).
테스트는 ``set_settings()`` 로 덮어쓴다(``tests/conftest.py`` 의 ``test_settings`` fixture).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_JEV_MCP_CMD = "npx -y @jkudish/jev-mcp@latest"  # DECISIONS D6
DEFAULT_USER_AGENT = "subscription-analyzer/0.1 (public housing-subscription info collector)"
# 키 인증 공식 API — robots.txt 예외 (계약 2026-10-09.2): 공공데이터포털 Open API(apis.data.go.kr),
# 공공데이터포털 odcloud API(api.odcloud.kr — 청약홈 분양정보·경쟁률), 네이버 검색 API(developers 레거시
# openapi.naver.com / NAVER Cloud API HUB naverapihub.apigw.ntruss.com)
DEFAULT_ROBOTS_EXEMPT_HOSTS = (
    "apis.data.go.kr",
    "api.odcloud.kr",
    "openapi.naver.com",
    "naverapihub.apigw.ntruss.com",
)
DEFAULT_ENV_FILE = ".env"
NewsApiProvider = Literal["ncp", "naver_developers"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- 실행 환경
    env: Literal["dev", "prod"] = "dev"
    tz: str = "Asia/Seoul"
    log_level: str = "INFO"
    log_json: bool = True

    # --- 저장소
    database_url: str = "sqlite:///./dev.db"
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=0)
    raw_dir: Path = Path("./data/raw")
    reference_dir: Path = Path("./data/reference")
    report_dir: Path = Path("./data/reports")

    # --- API (ADR-9)
    api_prefix: str = "/api"
    api_token: SecretStr | None = None
    readonly_token: SecretStr | None = None
    share_token_ttl_days: int = Field(default=30, ge=1)

    # --- 판정기 (ADR-5, D6)
    judge_adapter: Literal["jev", "mock"] = "jev"
    jev_mcp_cmd: str = DEFAULT_JEV_MCP_CMD
    judge_call_timeout_s: float = Field(default=120.0, gt=0)  # 도구 호출 1건
    judge_start_timeout_s: float = Field(default=300.0, gt=0)  # 기동(initialize, 첫 npx 다운로드 포함)

    # --- 외부 키 (없으면 해당 기능 비활성: D1 #5·#6·#7)
    data_go_kr_key: SecretStr | None = None
    news_api_key: SecretStr | None = None
    # ncp = NAVER Cloud API HUB(헤더 X-NCP-APIGW-API-KEY-ID/-KEY), naver_developers = 레거시 개발자센터
    # (openapi.naver.com, X-Naver-Client-Id/-Secret). 키 형식은 둘 다 ``<ID>:<Secret>``.
    news_api_provider: NewsApiProvider = "ncp"
    webhook_url: SecretStr | None = None

    # --- 수집 HTTP (core.http)
    http_rate_per_host: float = Field(default=1.0, gt=0)  # 호스트당 초당 요청 수
    http_max_retries: int = Field(default=3, ge=0)  # 첫 시도 이후 재시도 횟수
    http_timeout_s: float = Field(default=30.0, gt=0)
    http_backoff_base_s: float = Field(default=1.0, ge=0)
    http_backoff_max_s: float = Field(default=60.0, ge=0)
    http_user_agent: str = DEFAULT_USER_AGENT
    # 키 인증 공식 API 호스트: 크롤링이 아니라 이용약관이 규율하므로 robots.txt 검사를 하지 않는다.
    # 환경변수는 쉼표 구분(``HTTP_ROBOTS_EXEMPT_HOSTS=apis.data.go.kr,openapi.naver.com``) 또는 JSON 배열.
    http_robots_exempt_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_ROBOTS_EXEMPT_HOSTS)
    )

    # --- worker
    worker_heartbeat_s: float = Field(default=60.0, gt=0)

    @field_validator("http_robots_exempt_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                return json.loads(text)
            return [h.strip() for h in text.split(",") if h.strip()]
        return value

    @field_validator("http_robots_exempt_hosts")
    @classmethod
    def _lower_hosts(cls, value: list[str]) -> list[str]:
        return [h.strip().lower() for h in value if h.strip()]

    @model_validator(mode="after")
    def _prod_guards(self) -> Self:
        if self.env == "prod" and (self.api_token is None or not self.api_token.get_secret_value()):
            raise ValueError("ENV=prod 에서는 API_TOKEN 이 필요하다")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def secret_values(self) -> list[str]:
        """설정에 들어 있는 비밀값 전부(빈 값 제외). 로그·외부 전송 마스킹에 쓴다."""
        out: list[str] = []
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, SecretStr):
                raw = value.get_secret_value()
                if raw:
                    out.append(raw)
        return out


def env_var_names() -> list[str]:
    """Settings 가 읽는 환경변수 이름(대문자) 목록."""
    return [name.upper() for name in Settings.model_fields]


def env_file_path() -> Path:
    """읽을 ``.env`` 경로: 환경변수 ``ENV_FILE`` 이 있으면 그것, 없으면 작업 디렉터리의 ``.env``."""
    return Path(os.environ.get("ENV_FILE") or DEFAULT_ENV_FILE)


def load_settings(env_file: Path | str | None = None) -> Settings:
    """``env_file``(없으면 ``env_file_path()``)을 읽은 새 Settings. 환경변수가 파일보다 우선한다."""
    path = Path(env_file) if env_file is not None else env_file_path()
    return Settings(_env_file=path)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def set_settings(settings: Settings | None) -> None:
    """테스트·CLI 용 덮어쓰기. ``None`` 이면 다음 ``get_settings()`` 가 환경에서 다시 읽는다."""
    global _settings
    _settings = settings
