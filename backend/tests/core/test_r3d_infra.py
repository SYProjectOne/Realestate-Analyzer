"""R3d CORE2 — 4차 리뷰 운영 minor: infra README, runbook 의 D11·D12 규칙(문서가 실제 설정과 맞는지)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
INFRA = ROOT / "infra"


def test_infra_readme_lists_every_file_and_backup_volume() -> None:
    readme = (INFRA / "README.md").read_text(encoding="utf-8")
    for f in sorted(p.name for p in INFRA.iterdir() if p.is_file() and p.name != "README.md"):
        assert f"`{f}`" in readme, f"infra/README.md 에 {f} 설명이 없다"
    compose = yaml.safe_load((INFRA / "docker-compose.yml").read_text(encoding="utf-8"))
    assert compose["services"]["worker"]["environment"]["BACKUP_DIR"] in readme
    assert "PG_MAJOR" in readme and "postgres:16" in readme


def test_runbook_covers_d11_d12_rules() -> None:
    runbook = (ROOT / "docs" / "runbook.md").read_text(encoding="utf-8")
    for needle in (
        "발행 스냅샷은 불변",  # D11-1
        "`backup`",  # D11-8 스케줄
        "`region.expand`",  # D11-7
        "사람 확인 재검토",  # D12-1
        "(단지, 의미 필드, 모순 값)",  # D12-2
        "`analysis.price_view.current_price`",  # D12-3
        "snapshot_state",  # D12-4
        "자동 등록",  # D12-5
        "backups",  # D12-6
        "prod + SQLite 거부",  # D11-9
        "npm ci",  # 회귀 실행 순서(t13)
    ):
        assert needle in runbook, f"runbook 에 '{needle}' 이 없다"
