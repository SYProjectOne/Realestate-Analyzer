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
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
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


def t_backfill(_args: list[str]) -> list[Step]:
    """발행 리비전 저장본 backfill(D14-9, 멱등): migrate 뒤 빠진 저장본 종류·행 단위 사람 확인 이전."""
    return [uv("python", "-m", "app.snapshot_view", "backfill")]


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
    한 단계가 실패해도 나머지를 돌리고 마지막에 요약을 출력한다. 회귀 테스트가 0개면 실패로 본다.

    순서(R3 4차 리뷰 — T13 프론트 lint 검사의 간헐 실패 원인): frontend ``npm ci`` 는 pytest **전에** 끝낸다. 같은 frontend
    에서 ``npm ci`` 가 node_modules 를 다시 쓰는 동안 eslint 를 부르면 모듈을 못 찾아 stdout 이 비었다. node_modules 가
    없으면 여기서 먼저 설치한다(있으면 그대로 — 바꾸려면 미리 ``npm ci``)."""
    steps: list[Step] = []
    if has_frontend() and not (FRONTEND / "node_modules").is_dir():
        steps.append(npm(FRONTEND, "ci", note="T13 프론트 lint 검사 전에(회귀 pytest 보다 먼저)"))
    steps += [
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


# e2e 실행 격리 — 여러 worktree(또는 같은 worktree 의 두 프로세스)가 regress 를 동시에 돌려도
# 포트·데이터 폴더·리포트 파일이 겹치지 않게 실행마다 OS 가 준 빈 포트와 고유 임시 폴더를 환경변수로 넘긴다.
# e2e/env.ts·e2e/playwright.config.ts·e2e/perf/playwright.config.ts 가 읽고,
# 없으면 기존 고정값(수동 실행 호환).
# frontend/e2e/api·pages 설정 변수도 같이 넘긴다(그 설정도 같은 이름을 읽는다 — 하위 명령에서 부를 때 격리).
E2E_PORT_VARS = (
    "E2E_FLOW_API_PORT", "E2E_FLOW_WEB_PORT", "E2E_PERF_API_PORT", "E2E_PERF_WEB_PORT",  # e2e/
    "E2E_API_PORT", "E2E_API_WEB_PORT", "E2E_PAGES_PORT", "E2E_PERF_PORT",  # frontend/e2e/api·pages
)
E2E_DATA_VARS = (("E2E_FLOW_DATA", "flows"), ("E2E_PERF_DATA", "perf"), ("E2E_API_DATA", "api"))


def free_ports(n: int) -> list[int]:
    """OS 가 준 빈 TCP 포트 n 개(서로 다름). 모두 잡은 뒤 한꺼번에 놓아 같은 포트가 두 번 나오지 않게 한다."""
    socks: list[socket.socket] = []
    try:
        for _ in range(n):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", 0))
            socks.append(s)
        return [int(s.getsockname()[1]) for s in socks]
    finally:
        for s in socks:
            s.close()


def _rmtree(path: Path, attempts: int = 20) -> bool:
    """Windows 에서 방금 끝난 서버가 SQLite 파일을 잠깐 쥐고 있을 수 있다 — 잠시 재시도."""
    for _ in range(attempts):
        if not path.exists():
            return True
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return True
        time.sleep(0.5)
    return not path.exists()


@dataclass(frozen=True)
class E2EIsolation:
    """regress 1회분의 격리 자원: 임시 폴더(root) 아래 데이터·리포트, worktree 안 Playwright 산출물 폴더."""

    root: Path
    env: dict[str, str]
    junit: Path
    results: Path
    output: Path

    @classmethod
    def create(cls, base_env: Mapping[str, str]) -> E2EIsolation:
        root = Path(tempfile.mkdtemp(prefix="sa-e2e-run-"))
        env: dict[str, str] = {}
        for var, port in zip(E2E_PORT_VARS, free_ports(len(E2E_PORT_VARS)), strict=True):
            if var not in base_env:
                env[var] = str(port)
        for var, sub in E2E_DATA_VARS:
            if var not in base_env:
                (root / sub).mkdir()
                env[var] = (root / sub).as_posix()
        results = root / "results.json"
        output = E2E / "test-results" / root.name
        env["E2E_RESULTS_JSON"] = results.as_posix()
        env["E2E_OUTPUT_DIR"] = output.as_posix()
        return cls(root=root, env=env, junit=root / "regress-junit.xml", results=results, output=output)

    def apply(self, step: Step) -> tuple[list[str], dict[str, str]]:
        """단계의 명령(junit 경로 → 이 실행 것)과 환경변수(격리 값 우선)."""
        cmd = [f"--junitxml={self.junit}" if a.startswith("--junitxml=") else a for a in step.cmd]
        return cmd, {**os.environ, **step.env, **self.env}

    def publish(self) -> None:
        """요약에 쓴 리포트를 기본 위치(e2e/playwright-report/)에 복사 — 동시 실행이면 마지막 것이 남는다."""
        REGRESS_JUNIT.parent.mkdir(parents=True, exist_ok=True)
        for src, dst in ((self.junit, REGRESS_JUNIT), (self.results, E2E_RESULTS)):
            if src.is_file():
                tmp = dst.with_name(f"{dst.name}.{self.root.name}")
                shutil.copyfile(src, tmp)
                os.replace(tmp, dst)
            else:
                dst.unlink(missing_ok=True)

    def cleanup(self, keep_output: bool) -> None:
        """임시 폴더는 항상 지운다. 실패한 실행의 Playwright 산출물(trace)은 keep_output 이면 남긴다."""
        if not _rmtree(self.root):
            print(f"임시 폴더를 지우지 못했다: {self.root}", file=sys.stderr)
        artifacts = [p for p in self.output.iterdir() if p.name != ".last-run.json"] if self.output.is_dir() else []
        if not keep_output or not artifacts:
            _rmtree(self.output)


def run_regress(steps: Sequence[Step]) -> int:
    """모든 단계를 끝까지 돌리고(실패해도 계속) 케이스별 요약을 출력한다. 실행마다 포트·폴더를 격리한다."""
    iso = E2EIsolation.create(os.environ)
    shown = " ".join(f"{k}={iso.env[k]}" for k in (*E2E_PORT_VARS, "E2E_FLOW_DATA") if k in iso.env)
    print(f"# e2e 격리: {shown}", flush=True)
    code = 1
    try:
        code = _run_regress(steps, iso)
    finally:
        iso.cleanup(keep_output=code != 0)
    return code


def _run_regress(steps: Sequence[Step], iso: E2EIsolation) -> int:
    codes: list[int] = []
    for step in steps:
        print(f"$ {step.show()}", flush=True)
        cmd, env = iso.apply(step)
        try:
            code = subprocess.call(_resolve(cmd), cwd=step.cwd, env=env)
        except FileNotFoundError:
            print(f"명령을 찾을 수 없다: {step.cmd[0]}", file=sys.stderr)
            code = 127
        codes.append(code)
    iso.publish()
    print("\n==== 회귀 요약 (RA §9) ====")
    if iso.junit.is_file():
        rows = summarize_junit(iso.junit)
        if not rows:
            print("회귀 테스트가 아직 없다(WP9) — 실패로 처리", file=sys.stderr)
            codes.append(NO_TESTS_COLLECTED)
        for case, ok, bad, skip, names in rows:
            mark = "FAIL" if bad else "PASS"
            extra = f"  ← {', '.join(names[:4])}{' …' if len(names) > 4 else ''}" if names else ""
            print(f"  [{mark}] {case:<28} 통과 {ok:>3} · 실패 {bad:>2} · 건너뜀 {skip}{extra}")
    else:
        print("  (pytest junit 없음)")
    if iso.results.is_file():
        print("  -- e2e --")
        for title, status in summarize_playwright(iso.results):
            print(f"  [{'PASS' if status in ('passed', 'expected') else 'FAIL'}] {title} ({status})")
    failed = [c for c in codes if c not in (0,)]
    print(f"결과: {'통과' if not failed else '실패'} (단계 종료 코드 {codes})")
    return failed[0] if failed else 0


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
    "backfill": t_backfill,
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
