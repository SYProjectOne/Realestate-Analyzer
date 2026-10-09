"""R3b G3 — 설정·기동·인프라·운영(재리뷰 F3 minor, m34).

- 프록시 헤더 허용 목록: FORWARDED_ALLOW_IPS(기본 127.0.0.1), prod 에서 '*' 거부, compose 는 내부망 대역만.
- m34: worker 이미지에 raw_archive.sh(실행 권한), runbook 경로, 스크립트가 상대 RAW_DIR 로도 동작.
"""

# ruff: noqa: E501  (한국어 assertion 메시지)
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.core.settings import Settings, env_var_names

ROOT = Path(__file__).resolve().parents[3]
INFRA = ROOT / "infra"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in env_var_names():
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def make(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def test_proxy_headers_trusted_only_from_allow_list(clean_env: pytest.MonkeyPatch) -> None:
    from app.serve import uvicorn_kwargs

    assert make().forwarded_allow_ips == "127.0.0.1", "기본 = 루프백만"
    kw = uvicorn_kwargs(make(env="dev", api_token="w" * 32, forwarded_allow_ips="172.30.0.0/24"))
    assert kw["proxy_headers"] is True and kw["forwarded_allow_ips"] == "172.30.0.0/24"
    assert uvicorn_kwargs(make())["forwarded_allow_ips"] != "*"
    with pytest.raises(ValidationError, match="FORWARDED_ALLOW_IPS"):
        make(env="prod", api_token="t" * 32, forwarded_allow_ips="*")
    assert make(env="dev", forwarded_allow_ips="*").forwarded_allow_ips == "*", "dev 는 허용(로컬 실험)"


def test_proxy_allow_list_is_honoured_by_uvicorn() -> None:
    """uvicorn 의 허용 목록이 CIDR 을 받는다(compose 내부망 대역) — 밖의 주소는 믿지 않는다."""
    from uvicorn.middleware.proxy_headers import _TrustedHosts

    hosts = _TrustedHosts("172.30.0.0/24")
    assert "172.30.0.7" in hosts and "10.0.0.1" not in hosts and "127.0.0.1" not in hosts


def test_compose_passes_internal_subnet_as_proxy_allow_list() -> None:
    compose = yaml.safe_load((INFRA / "docker-compose.yml").read_text(encoding="utf-8"))
    env = compose["x-backend-env"]
    assert env["FORWARDED_ALLOW_IPS"] == "${INTERNAL_SUBNET:-172.30.0.0/24}"
    subnet = compose["networks"]["default"]["ipam"]["config"][0]["subnet"]
    assert subnet == env["FORWARDED_ALLOW_IPS"], "허용 대역 = web 이 있는 내부망"
    example = (INFRA / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^FORWARDED_ALLOW_IPS=127\.0\.0\.1$", example, re.M)
    assert "FORWARDED_ALLOW_IPS" in env_var_names()


def test_m34_worker_image_has_archive_script_and_runbook_paths() -> None:
    docker = (INFRA / "Dockerfile.worker").read_text(encoding="utf-8")
    assert "COPY infra/raw_archive.sh /app/infra/raw_archive.sh" in docker
    assert "chmod 755 /app/infra/raw_archive.sh" in docker
    runbook = (ROOT / "docs" / "runbook.md").read_text(encoding="utf-8")
    assert "exec worker /app/infra/raw_archive.sh /data/raw" in runbook
    # compose 명령은 모두 -f infra/docker-compose.yml (저장소 루트에서 그대로 실행)
    for m in re.finditer(r"docker compose(?! -f infra/docker-compose\.yml)([^`\n]*)", runbook):
        pytest.fail(f"runbook: -f 없는 compose 명령: {m.group(0)}")
    proc = subprocess.run(
        ["git", "ls-files", "-s", "infra/raw_archive.sh", "infra/backup.sh"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if proc.returncode == 0 and proc.stdout:
        assert all(line.startswith("100755") for line in proc.stdout.splitlines()), proc.stdout


@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("tar") is None, reason="bash·tar 없음")
def test_m34_archive_script_accepts_relative_raw_dir(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    day = raw / "applyhome_list" / "2020-01-15"
    day.mkdir(parents=True)
    (day / "abc.json").write_text("{}", encoding="utf-8")
    bash = shutil.which("bash")
    assert bash is not None
    script = (INFRA / "raw_archive.sh").as_posix()
    proc = subprocess.run(
        [bash, script, "raw", "applyhome_list", "2020-01"],
        cwd=tmp_path, capture_output=True, text=True, check=False, env={**os.environ, "LC_ALL": "C"},
    )  # fmt: skip
    assert proc.returncode == 0, proc.stdout + proc.stderr
    archive = raw / "applyhome_list" / "2020-01.tar.gz"
    assert archive.is_file() and not day.exists()
    with tarfile.open(archive) as tar:
        assert "applyhome_list/2020-01-15/abc.json" in tar.getnames()
    assert date.today().year >= 2020
