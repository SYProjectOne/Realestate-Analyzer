"""판정 녹화의 input_hash 계산 (WP9). 규칙은 app.core.protocols.input_hash 한 곳 — 여기서는 import만 한다.

사용 (backend/ 에서):
    uv run python ../contracts/fixtures/tools/hash.py --tool screen --purpose screen:notice:2 \
        --adapter-version mock-fixture-2026-10-08 payload.json
    → sha256:<64 hex>   (녹화 파일 이름 = judgments/<tool>/<hex>.json)

--adapter-version을 생략하면 contracts/fixtures/<fixture>/judgments/_meta.json 의 값을 쓴다(--fixture).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.protocols import JUDGE_TOOLS, JudgeTool, input_hash  # noqa: E402

DEFAULT_FIXTURE = "incheon_gimpo_2026-10-08"

__all__ = ["fixture_hash", "input_hash", "meta_adapter_version", "recording_path"]


def fixture_hash(tool: JudgeTool, purpose: str, payload: dict[str, Any], adapter_version: str) -> str:
    """app.core.protocols.input_hash 그대로(녹화 도구용 이름)."""
    return input_hash(tool, purpose, payload, adapter_version)


def meta_adapter_version(fixture: str = DEFAULT_FIXTURE) -> str:
    meta = json.loads(
        (REPO / "contracts" / "fixtures" / fixture / "judgments" / "_meta.json").read_text("utf-8")
    )
    value = meta["adapter_version"]
    assert isinstance(value, str)
    return value


def recording_path(tool: str, digest: str) -> str:
    """judgments 기준 상대 경로 '<tool>/<hex>.json'."""
    return f"{tool}/{digest.removeprefix('sha256:')}.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tool", required=True, choices=JUDGE_TOOLS)
    ap.add_argument("--purpose", required=True)
    ap.add_argument("--adapter-version")
    ap.add_argument("--fixture", default=DEFAULT_FIXTURE)
    ap.add_argument("payload", help="payload JSON 파일 경로('-'면 표준 입력)")
    args = ap.parse_args(argv)
    raw = sys.stdin.read() if args.payload == "-" else Path(args.payload).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        ap.error("payload는 JSON 객체여야 한다")
    version = args.adapter_version or meta_adapter_version(args.fixture)
    sys.stdout.write(fixture_hash(args.tool, args.purpose, payload, version) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
