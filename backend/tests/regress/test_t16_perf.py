"""T16 성능 (RA §9): 합성 1,000단지 → ``/complexes`` 첫 페이지 1초 이내, G2 스크롤 60fps(가상화).

시스템 경계: devseed DB + ``devseed.load_synth``(contracts/fixtures/tools/synth.py 1,000단지) → **실제 uvicorn 프로세스**
(HTTP, 인증 헤더) → 첫 페이지 응답 시간(워밍업 1회 뒤 3회 모두 < 1 s). 프론트 가상 스크롤(rAF 프레임 간격)은
``e2e/perf/`` (Playwright, 같은 합성 DB)가 측정한다 — 여기서는 가상화가 기대하는 API 계약(페이지 크기·total)을 본다.
"""

# ruff: noqa: E501

from __future__ import annotations

import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

from .conftest import BACKEND, READ_TOKEN, SNAP, WRITE, WRITE_TOKEN, RegressEnv

pytestmark = pytest.mark.regress

LIMIT_S = 1.0
G2_SAMPLES = 5
"""G2 size 1000 첫 요청 측정 횟수(워밍업 뒤) — 판정은 중앙값."""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


PERF_LOCK = Path(tempfile.gettempdir()) / "sa-regress-t16-perf.lock"
PERF_LOCK_WAIT_S = 900.0


@contextmanager
def perf_lock() -> Iterator[None]:
    """측정 구간 상호 배제(머신 전체) — 여러 worktree 가 regress 를 동시에 돌리면 두 측정이 같은 CPU 를
    다투어 1 s 기준을 넘는다(포트·폴더 충돌이 아니라 측정 간섭). 측정만 차례로 한다. 프로세스가 죽으면 OS 가 잠금을 푼다."""
    PERF_LOCK.touch(exist_ok=True)
    with PERF_LOCK.open("r+b") as fh:
        deadline = time.monotonic() + PERF_LOCK_WAIT_S
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    pytest.fail(f"T16 측정 잠금 대기 {PERF_LOCK_WAIT_S:.0f}s 초과: {PERF_LOCK}")
                time.sleep(0.5)
        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@pytest.fixture
def server(env: RegressEnv) -> Iterator[str]:
    from app.api import devseed
    from app.core.db import reset_engine

    with perf_lock():
        yield from _server(env, devseed, reset_engine)


def _server(env: RegressEnv, devseed: Any, reset_engine: Callable[[], None]) -> Iterator[str]:
    assert devseed.load_synth(env.settings, n=1000, snapshot_id=SNAP) == 1000
    reset_engine()
    port = _free_port()
    db = Path(env.settings.database_url.removeprefix("sqlite:///"))
    child_env = {
        **{k: v for k, v in os.environ.items() if k.upper() not in {"DATABASE_URL", "ENV_FILE"}},
        "ENV": "dev",
        "DATABASE_URL": f"sqlite:///{db.as_posix()}",
        "RAW_DIR": str(env.settings.raw_dir),
        "REPORT_DIR": str(env.tmp / "reports"),
        "REFERENCE_DIR": str(env.tmp / "reference"),
        "API_TOKEN": WRITE_TOKEN,
        "READONLY_TOKEN": READ_TOKEN,
        "JUDGE_ADAPTER": "mock",
        "LOG_JSON": "false",
        "LOG_LEVEL": "WARNING",
        "ENV_FILE": str(env.tmp / "none.env"),
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND,
        env=child_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                if httpx.get(f"{base}/health", timeout=2).status_code in (200, 503):
                    break
            except httpx.HTTPError:
                pass
            if proc.poll() is not None or time.monotonic() > deadline:
                err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
                pytest.fail(f"uvicorn 기동 실패: {err[-1500:]}")
            time.sleep(0.3)
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_t16_first_page_under_1s_over_http(server: str) -> None:
    url = f"{server}/api/snapshots/{SNAP}/complexes"
    with httpx.Client(headers=WRITE, timeout=30) as c:
        warm = c.get(url)
        assert warm.status_code == 200, warm.text[:300]
        assert warm.json()["total"] >= 1000
        timings: list[tuple[str, float]] = []
        for params in ({}, {"scenario": "D"}, {"sort": "-price_mid"}, {"page": 2}):
            for _ in range(3):
                t0 = time.perf_counter()
                r = c.get(url, params=params)
                dt = time.perf_counter() - t0
                assert r.status_code == 200, r.text[:300]
                assert len(r.json()["items"]) == 50
                timings.append((str(params), dt))
        slow = [(p, round(t, 3)) for p, t in timings if t >= LIMIT_S]
        print("T16 first-page timings(s):", [(p, round(t, 3)) for p, t in timings])
        assert not slow, f"첫 페이지 {LIMIT_S}s 초과: {slow}"


def test_t16_g2_first_request_size_1000_under_1s(server: str) -> None:
    """G2(프론트 params.ts PAGE_SIZE=1000)가 실제로 부르는 첫 페이지 = size 1000 — 이것도 1 s 이내여야 한다."""
    url = f"{server}/api/snapshots/{SNAP}/complexes"
    with httpx.Client(headers=WRITE, timeout=60) as c:
        c.get(url, params={"size": 1000, "sort": "-total"})
        timings = []
        for _ in range(G2_SAMPLES):
            t0 = time.perf_counter()
            r = c.get(url, params={"size": 1000, "sort": "-total"})
            timings.append(round(time.perf_counter() - t0, 3))
            assert r.status_code == 200
    print("T16 G2 first request(size 1000) timings(s):", timings)
    # R5-PIPE 4: 가장 빠른 1회(min)가 아니라 중앙값 — 대부분의 요청이 1 s 안이어야 한다. 다른 스위트가 동시에 도는 부하에서 튀는
    # 1~2회(중앙값에 영향 없음)는 견딘다
    med = statistics.median(timings)
    assert med < LIMIT_S, f"G2 첫 요청(size 1000) 중앙값 {med}s {timings} — {LIMIT_S}s 초과"


def test_t16_virtualization_contract(server: str) -> None:
    """G2 가상 스크롤이 기대하는 응답: total = 1,016, size ≤ 1,000 한 번에(가상화로 DOM 은 일부만)."""
    with httpx.Client(headers=WRITE, timeout=60) as c:
        r = c.get(f"{server}/api/snapshots/{SNAP}/complexes", params={"size": 1000})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1000 and len(body["items"]) == 1000
