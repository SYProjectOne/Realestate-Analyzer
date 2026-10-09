"""픽스처 매니페스트 (R3 minor 6): contracts/fixtures/** 의 sha256 목록 + 바꾼 사유.

픽스처를 바꾸면 이 스크립트로 매니페스트를 다시 만들고, 같은 사유 문장을 contracts/CHANGELOG.md 맨 위 항목에 적는다.
``tests/contracts/test_fixture_manifest.py`` 가 (1) 파일 해시 = 매니페스트, (2) 사유가 CHANGELOG 에 그대로 있음을 강제한다.

사용법 (backend/ 에서)::

    uv run python scripts/fixture_manifest.py --reason "R3: canonical JSON 정규화로 judgments input_hash 재생성"
    uv run python scripts/fixture_manifest.py --check     # 다르면 exit 1
"""

# ruff: noqa: E501  (한국어 docstring·메시지)
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = BACKEND_DIR.parent / "contracts"
FIXTURES_DIR = CONTRACTS_DIR / "fixtures"
MANIFEST = CONTRACTS_DIR / "fixtures.sha256.json"
_SKIP_PARTS = {"__pycache__", ".pytest_cache", "node_modules"}


def file_hashes(root: Path = FIXTURES_DIR) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or _SKIP_PARTS & set(p.parts) or p.suffix == ".pyc":
            continue
        data = p.read_bytes()
        if p.suffix.lower() not in (".zip", ".png", ".pdf", ".jpg", ".xlsx"):
            data = data.replace(b"\r\n", b"\n")  # 체크아웃 줄바꿈과 무관하게(.gitattributes eol=lf)
        out[p.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
    return out


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def write_manifest(reason: str, path: Path = MANIFEST) -> dict[str, Any]:
    data = {
        "description": "contracts/fixtures/** sha256. 픽스처를 바꾸면 backend/scripts/fixture_manifest.py --reason 으로 "
        "다시 만들고 같은 reason 문장을 contracts/CHANGELOG.md 에 적는다(R3 minor 6).",
        "reason": reason,
        "files": file_hashes(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return data


def diff(manifest: dict[str, Any]) -> list[str]:
    want: dict[str, str] = manifest.get("files") or {}
    have = file_hashes()
    out = [f"+ {k}" for k in sorted(set(have) - set(want))]
    out += [f"- {k}" for k in sorted(set(want) - set(have))]
    out += [f"~ {k}" for k in sorted(set(have) & set(want)) if have[k] != want[k]]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--reason", help="바꾼 사유(CHANGELOG 맨 위 항목에 같은 문장을 적는다)")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.check:
        changes = diff(load_manifest())
        for line in changes:
            sys.stdout.write(line + "\n")
        return 1 if changes else 0
    if not args.reason or len(args.reason.strip()) < 8:
        ap.error("--reason 은 8자 이상(무엇을 왜 바꿨는지)")
    data = write_manifest(args.reason.strip())
    sys.stdout.write(f"{MANIFEST}: {len(data['files'])} files\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
