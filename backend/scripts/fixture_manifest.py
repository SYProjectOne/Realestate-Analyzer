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


def files_digest(files: dict[str, str]) -> str:
    """파일 해시 목록 전체의 sha256(경로 순) — 픽스처 집합 1개의 지문."""
    body = "\n".join(f"{k} {v}" for k, v in sorted(files.items()))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class ReasonReused(ValueError):
    """픽스처가 바뀌었는데 이전 사유를 그대로 쓰려 했다(R3 3차 RA 부분 — 변경마다 새 사유)."""


def write_manifest(reason: str, path: Path = MANIFEST) -> dict[str, Any]:
    """매니페스트를 다시 쓴다. 픽스처 지문이 바뀌었는데 사유가 이전(이력 어느 것이든)과 같으면 ``ReasonReused``.
    이전 (사유, 지문)은 ``history`` 에 남는다(사유 재사용 검사·감사 기록)."""
    files = file_hashes()
    digest = files_digest(files)
    old: dict[str, Any] = load_manifest(path) if path.is_file() else {}
    history: list[dict[str, str]] = list(old.get("history") or [])
    if old.get("reason"):
        prev_digest = str(old.get("files_digest") or files_digest(old.get("files") or {}))
        prev = {"reason": str(old["reason"]), "files_digest": prev_digest}
        if not history or history[-1] != prev:
            history.append(prev)
    changed = bool(old) and files_digest(old.get("files") or {}) != digest
    if changed and any(h["reason"] == reason for h in history):
        raise ReasonReused(
            f"픽스처가 바뀌었는데 이전 사유를 다시 썼다: {reason!r} — 이번 변경의 사유를 새로 적는다"
        )
    data = {
        "description": "contracts/fixtures/** sha256. 픽스처를 바꾸면 backend/scripts/fixture_manifest.py --reason 으로 "
        "다시 만들고 같은 reason 문장을 contracts/CHANGELOG.md 에 적는다(R3 minor 6). 변경마다 새 사유(history).",
        "reason": reason,
        "files_digest": digest,
        "history": history,
        "files": files,
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
    try:
        data = write_manifest(args.reason.strip())
    except ReasonReused as exc:
        ap.error(str(exc))
    sys.stdout.write(f"{MANIFEST}: {len(data['files'])} files\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
