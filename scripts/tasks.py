#!/usr/bin/env python3
"""작업 러너 — Windows 에 make 가 없어도 같은 명령을 쓴다. ``Makefile`` 은 이 파일의 래퍼다.

    python scripts/tasks.py <작업> [인자…]      # 저장소 어디서든
    python scripts/tasks.py --dry-run regress   # 실행할 명령만 출력
    python scripts/tasks.py --list

표준 라이브러리만 쓴다(가상환경 밖에서도 실행). 백엔드 명령은 ``uv run`` 으로 backend/.venv 에서 돈다.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
E2E = ROOT / "e2e"
INFRA = ROOT / "infra"

BACKEND_MODULES = ("core", "models", "collectors", "normalize", "judge", "analysis", "api", "scheduler", "reports")
NO_TESTS_COLLECTED = 5


@dataclass(frozen=True)
class Step:
    cmd: list[str]
    cwd: Path
    note: str = ""
    allow_codes: tuple[int, ...] = (0,)
    env: dict[str, str] = field(default_factory=dict)

    def show(self) -> str:
        rel = self.cwd.relative_to(ROOT).as_posix() if self.cwd != ROOT else "."
        env = " ".join(f"{k}={v}" for k, v in self.env.items())
        prefix = f"[{rel}] " + (env + " " if env else "")
        return prefix + " ".join(self.cmd) + (f"    # {self.note}" if self.note else "")


def uv(*args: str, note: str = "", allow: tuple[int, ...] = (0,)) -> Step:
    return Step(["uv", "run", *args], BACKEND, note, allow)


def npm(where: Path, *args: str, note: str = "") -> Step:
    return Step(["npm", *args], where, note)


def has_frontend() -> bool:
    return (FRONTEND / "package.json").is_file()


# ---------------------------------------------------------------- 작업 정의


def t_test(args: list[str]) -> list[Step]:
    """백엔드 테스트. 인자 = 모듈 이름(core, judge …) 또는 pytest 인자. 없으면 전체."""
    targets: list[str] = []
    extra: list[str] = []
    for a in args:
        if a in BACKEND_MODULES:
            targets.append(f"tests/{a}")
        else:
            extra.append(a)
    return [uv("pytest", *(targets or ["tests"]), *extra, allow=(0, NO_TESTS_COLLECTED))]


def t_lint(_args: list[str]) -> list[Step]:
    """ruff + mypy --strict (+ 프론트 eslint)."""
    steps = [uv("ruff", "check", "app", "tests"), uv("mypy", "app")]
    if has_frontend():
        steps.append(npm(FRONTEND, "run", "lint"))
    return steps


def t_typecheck(_args: list[str]) -> list[Step]:
    """mypy --strict (+ 프론트 tsc --noEmit)."""
    steps = [uv("mypy", "app")]
    if has_frontend():
        steps.append(npm(FRONTEND, "run", "typecheck"))
    return steps


def t_fmt(_args: list[str]) -> list[Step]:
    """ruff --fix (자동 수정 가능한 것만)."""
    return [uv("ruff", "check", "--fix", "app", "tests")]


def t_gen(_args: list[str]) -> list[Step]:
    """계약 → 코드 생성: 백엔드(app.core.contracts_gen, WP0-A) + 프론트(npm run gen:api)."""
    steps: list[Step] = []
    if (BACKEND / "app" / "core" / "contracts_gen.py").is_file():
        steps.append(uv("python", "-m", "app.core.contracts_gen", note="contracts → pydantic"))
    else:
        steps.append(Step([sys.executable, "-c", "print('app/core/contracts_gen.py 없음 — 건너뜀')"], ROOT))
    if has_frontend():
        steps.append(npm(FRONTEND, "run", "gen:api", note="openapi.yaml → src/api/schema.d.ts"))
    return steps


def t_migrate(_args: list[str]) -> list[Step]:
    """alembic upgrade head (DATABASE_URL 기본 sqlite:///./dev.db)."""
    return [uv("alembic", "upgrade", "head")]


def t_api(args: list[str]) -> list[Step]:
    """api 개발 서버(uvicorn --reload, :8000)."""
    return [uv("uvicorn", "app.main:app", "--reload", "--port", "8000", *args)]


def t_worker(args: list[str]) -> list[Step]:
    """worker (python -m app.worker [--once])."""
    return [uv("python", "-m", "app.worker", *args)]


def t_web(_args: list[str]) -> list[Step]:
    """프론트 개발 서버(vite)."""
    return [npm(FRONTEND, "run", "dev")] if has_frontend() else []


def t_dev(_args: list[str]) -> list[Step]:
    """api + worker (+ web) 를 함께 띄운다. Ctrl+C 로 모두 종료."""
    return [*t_api([]), *t_worker([]), *t_web([])]


def t_regress(_args: list[str]) -> list[Step]:
    """회귀(RA §9): pytest -m regress (+ e2e 가 있으면 Playwright). 회귀 테스트가 0개면 실패로 본다."""
    steps = [uv("pytest", "tests", "-m", "regress", note="인천·김포 픽스처 회귀 (WP9)")]
    if (E2E / "package.json").is_file():
        steps.append(npm(E2E, "test", note="e2e (WP9)"))
    return steps


def t_check(args: list[str]) -> list[Step]:
    """lint + 전체 테스트 (커밋 전, AGENTS 규칙 17)."""
    return [*t_lint(args), *t_test([])]


def t_compose(_args: list[str]) -> list[Step]:
    """docker compose config 검증. Docker 가 없으면 파이썬 구조 테스트로 대신한다."""
    if shutil.which("docker"):
        return [Step(["docker", "compose", "-f", "infra/docker-compose.yml", "config", "-q"], ROOT)]
    return [uv("pytest", "tests/core/test_repo_layout.py", "-k", "compose", note="Docker 미설치 — 구조만 검증")]


TASKS: dict[str, Callable[[list[str]], list[Step]]] = {
    "test": t_test,
    "lint": t_lint,
    "typecheck": t_typecheck,
    "fmt": t_fmt,
    "gen": t_gen,
    "migrate": t_migrate,
    "api": t_api,
    "worker": t_worker,
    "web": t_web,
    "dev": t_dev,
    "regress": t_regress,
    "check": t_check,
    "compose-config": t_compose,
}
PARALLEL = {"dev"}


# ---------------------------------------------------------------- 실행


def _resolve(cmd: list[str]) -> list[str]:
    exe = shutil.which(cmd[0])
    return [exe, *cmd[1:]] if exe else cmd


def run_sequential(steps: Sequence[Step]) -> int:
    for step in steps:
        print(f"$ {step.show()}", flush=True)
        try:
            code = subprocess.call(_resolve(step.cmd), cwd=step.cwd, env={**os.environ, **step.env})
        except FileNotFoundError:
            print(f"명령을 찾을 수 없다: {step.cmd[0]}", file=sys.stderr)
            return 127
        if code == NO_TESTS_COLLECTED and code in step.allow_codes:
            print("(수집된 테스트 0개)", flush=True)
            continue
        if code not in step.allow_codes:
            if code == NO_TESTS_COLLECTED and "regress" in step.cmd:
                print("회귀 테스트가 아직 없다(WP9) — 실패로 처리", file=sys.stderr)
            return code
    return 0


def run_parallel(steps: Sequence[Step]) -> int:
    procs: list[subprocess.Popen[bytes]] = []
    for step in steps:
        print(f"$ {step.show()} &", flush=True)
        procs.append(subprocess.Popen(_resolve(step.cmd), cwd=step.cwd, env={**os.environ, **step.env}))
    try:
        while all(p.poll() is None for p in procs):
            try:
                procs[0].wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()  # posix: SIGTERM, Windows: TerminateProcess
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return max((p.returncode or 0) for p in procs)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/tasks.py",
        description="subscription-analyzer 작업 러너",
        epilog="\n".join(f"  {name:<15} {(fn.__doc__ or '').strip().splitlines()[0]}" for name, fn in TASKS.items()),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="실행하지 않고 명령만 출력")
    parser.add_argument("--list", action="store_true", help="작업 목록")
    parser.add_argument("task", nargs="?", choices=sorted(TASKS))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    ns = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    if ns.list or ns.task is None:
        parser.print_help()
        return 0
    steps = TASKS[ns.task](list(ns.args))
    if ns.dry_run:
        for step in steps:
            print(step.show())
        if not steps:
            print("(할 일 없음)")
        return 0
    if ns.task in PARALLEL and len(steps) > 1:
        return run_parallel(steps)
    return run_sequential(steps)


if __name__ == "__main__":
    raise SystemExit(main())
