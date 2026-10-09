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
from typing import Any

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


REGRESS_JUNIT = E2E / "playwright-report" / "regress-junit.xml"
E2E_RESULTS = E2E / "playwright-report" / "results.json"


def t_regress(args: list[str]) -> list[Step]:
    """회귀(RA §9): pytest -m regress(T1~T18 통합 + 모듈 골든) + e2e 흐름(Playwright) → 케이스별 요약.

    인자: ``--no-e2e``(백엔드만), ``--perf``(T16 프론트 측정 e2e/perf 추가).
    한 단계가 실패해도 나머지를 돌리고 마지막에 요약을 출력한다. 회귀 테스트가 0개면 실패로 본다."""
    steps = [
        Step(
            ["uv", "run", "pytest", "tests", "-m", "regress", "-p", "no:cacheprovider",
             f"--junitxml={REGRESS_JUNIT}"],
            BACKEND,
            "인천·김포 픽스처 회귀 (WP9)",
        )
    ]
    if "--no-e2e" not in args and (E2E / "package.json").is_file():
        if not (E2E / "node_modules").is_dir():
            steps.append(npm(E2E, "ci", note="e2e 의존성"))
        steps.append(npm(E2E, "test", note="e2e 흐름 3개 (WP9)"))
        if "--perf" in args:
            steps.append(npm(E2E, "run", "perf", note="T16 성능 측정 (WP9)"))
    return steps


_CASE_NAMES = {
    1: "통합 TOP 5", 2: "상황 B 동률", 3: "스위첸 403", 4: "이상치", 5: "세대수 상충",
    6: "복합 주장 분할", 7: "rerank 8→16", 8: "변경 없는 날", 9: "계약금 10→5%", 10: "사다리 시점",
    11: "비교군 대체", 12: "민감도", 13: "출처 누락", 14: "보안 guard", 15: "보고서", 16: "성능",
    17: "멱등성", 18: "판정기 다운",
}


def _case_of(classname: str, file: str) -> str:
    import re

    text = f"{file} {classname}".replace("\\", "/").replace(".", "/")
    m = re.search(r"test_t(\d\d)_", text)
    if m:
        n = int(m.group(1))
        return f"T{n:02d} {_CASE_NAMES.get(n, '')}".rstrip()
    m = re.search(r"tests/(\w+)/(test_\w+)", text)
    if m and m.group(1) == "regress":
        return f"흐름 {m.group(2).removeprefix('test_')}"
    return f"모듈 {m.group(1)}" if m else "기타"


def summarize_junit(path: Path) -> list[tuple[str, int, int, int, list[str]]]:
    """junit xml → [(케이스, 통과, 실패, 건너뜀, 실패 테스트 이름)]."""
    import xml.etree.ElementTree as ET

    rows: dict[str, list[Any]] = {}
    for tc in ET.parse(path).getroot().iter("testcase"):
        case = _case_of(tc.get("classname", ""), tc.get("file", ""))
        row = rows.setdefault(case, [0, 0, 0, []])
        if tc.find("failure") is not None or tc.find("error") is not None:
            row[1] += 1
            row[3].append(tc.get("name", "?"))
        elif tc.find("skipped") is not None:
            row[2] += 1
        else:
            row[0] += 1
    return [(k, *v) for k, v in sorted(rows.items())]


def summarize_playwright(path: Path) -> list[tuple[str, str]]:
    """Playwright json 리포트 → [(테스트 제목, 상태)]."""
    import json

    out: list[tuple[str, str]] = []

    def walk(suite: dict[str, Any], prefix: str) -> None:
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                results = test.get("results") or [{}]
                status = results[-1].get("status", test.get("status", "?"))
                out.append((f"{prefix}{spec.get('title', '')}", str(status)))
        for child in suite.get("suites", []):
            walk(child, f"{child.get('file') or prefix}: " if child.get("file") and not prefix else prefix)

    data = json.loads(path.read_text(encoding="utf-8"))
    for suite in data.get("suites", []):
        walk(suite, f"{suite.get('file') or suite.get('title', '')}: ")
    return out


def run_regress(steps: Sequence[Step]) -> int:
    """모든 단계를 끝까지 돌리고(실패해도 계속) 케이스별 요약을 출력한다."""
    for f in (REGRESS_JUNIT, E2E_RESULTS):
        if f.is_file():
            f.unlink()
    REGRESS_JUNIT.parent.mkdir(parents=True, exist_ok=True)
    codes: list[int] = []
    for step in steps:
        print(f"$ {step.show()}", flush=True)
        try:
            code = subprocess.call(_resolve(step.cmd), cwd=step.cwd, env={**os.environ, **step.env})
        except FileNotFoundError:
            print(f"명령을 찾을 수 없다: {step.cmd[0]}", file=sys.stderr)
            code = 127
        codes.append(code)
    print("\n==== 회귀 요약 (RA §9) ====")
    if REGRESS_JUNIT.is_file():
        rows = summarize_junit(REGRESS_JUNIT)
        if not rows:
            print("회귀 테스트가 아직 없다(WP9) — 실패로 처리", file=sys.stderr)
            codes.append(NO_TESTS_COLLECTED)
        for case, ok, bad, skip, names in rows:
            mark = "FAIL" if bad else "PASS"
            extra = f"  ← {', '.join(names[:4])}{' …' if len(names) > 4 else ''}" if names else ""
            print(f"  [{mark}] {case:<28} 통과 {ok:>3} · 실패 {bad:>2} · 건너뜀 {skip}{extra}")
    else:
        print("  (pytest junit 없음)")
    if E2E_RESULTS.is_file():
        print("  -- e2e --")
        for title, status in summarize_playwright(E2E_RESULTS):
            print(f"  [{'PASS' if status in ('passed', 'expected') else 'FAIL'}] {title} ({status})")
    bad = [c for c in codes if c not in (0,)]
    print(f"결과: {'통과' if not bad else '실패'} (단계 종료 코드 {codes})")
    return bad[0] if bad else 0


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
    if ns.task == "regress":
        return run_regress(steps)
    return run_sequential(steps)


if __name__ == "__main__":
    raise SystemExit(main())
