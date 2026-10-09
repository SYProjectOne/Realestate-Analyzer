"""worker 프로세스 진입점: ``python -m app.worker [--once] [--interval 초]``.

``app.scheduler.runner.main(argv)`` (WP7) 가 있으면 그대로 위임한다(인자 목록을 그대로 넘김).
없으면 heartbeat 로그만 남긴다 — ``--once`` 는 한 번 남기고 0 으로 끝난다.
"""

from __future__ import annotations

import argparse
import importlib
import signal
import sys
import threading
from collections.abc import Callable, Sequence
from types import FrameType
from typing import Any, cast

from app.core.db import get_engine, ping, reset_engine
from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings

log = get_logger("app.worker")

RunnerMain = Callable[[list[str] | None], int]


def _load_runner() -> RunnerMain | None:
    try:
        module = importlib.import_module("app.scheduler.runner")
    except ModuleNotFoundError as exc:
        if exc.name in {"app.scheduler.runner", "app.scheduler"} or exc.name is None:
            return None
        raise
    fn = getattr(module, "main", None)
    return cast(RunnerMain, fn) if callable(fn) else None


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m app.worker", description="subscription-analyzer worker")
    p.add_argument("--once", action="store_true", help="한 번 실행하고 끝낸다")
    p.add_argument("--interval", type=float, default=None, help="heartbeat 간격(초)")
    args, _unknown = p.parse_known_args(list(argv))
    return args


def heartbeat() -> None:
    s = get_settings()
    log.info("worker.heartbeat", extra={"env": s.env, "db": "ok" if ping(get_engine(s)) else "error"})


def main(argv: Sequence[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    settings = get_settings()
    configure_logging(settings)

    runner = _load_runner()
    if runner is not None:
        log.info("worker.delegate", extra={"to": "app.scheduler.runner.main"})
        return runner(argv_list)

    args = _parse(argv_list)
    log.info("worker.start", extra={"mode": "heartbeat", "reason": "app.scheduler.runner 없음"})
    stop = threading.Event()

    def _stop(signum: int, _frame: FrameType | None) -> None:
        log.info("worker.stop", extra={"signal": signum})
        stop.set()

    previous: dict[signal.Signals, Any] = {}
    if not args.once and threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.getsignal(sig)
            signal.signal(sig, _stop)

    interval = args.interval if args.interval is not None else settings.worker_heartbeat_s
    try:
        while True:
            heartbeat()
            if args.once or stop.wait(interval):
                break
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        reset_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
