"""스케줄러 실행 문맥: DB 세션·판정기 어댑터·수집기·알림·시계를 한곳에 모은다(테스트는 전부 바꿔 끼운다).

수집기 레지스트리 키(= ``collect.daily``/``collect.weekly`` 의 단계):

| 키 | 수집기 | 잡 |
| --- | --- | --- |
| ``applyhome`` | ``ApplyhomeCollector`` (목록 + 상세 + 경쟁률) | daily (payload source ``applyhome_list``·``applyhome_detail``) |
| ``notice_pdf`` | ``NoticePdfCollector`` | daily (청약홈 다음, 새·바뀐 공고의 공고문) |
| ``official_site`` | ``OfficialSiteCollector`` | daily |
| ``rtms`` | ``RtmsCollector`` (키 없으면 비활성) | weekly |
| ``stats`` | ``UnsoldCollector`` (+ 입주물량 추정 적재는 collect.py) | weekly |
| ``news`` | ``NewsCollector`` (키 없으면 비활성) | weekly |

판정기는 ``app.judge.get_adapter`` 로만 만든다(AGENTS 규칙 4). mock 어댑터의 녹화 디렉터리는
``JUDGE_FIXTURE_DIR`` 환경변수(없으면 저장소의 인천·김포 픽스처) — 개발·e2e 전용.
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

import contextlib
import os
import socket
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.orm import Session, sessionmaker

from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.db import get_sessionmaker
from app.core.settings import Settings, get_settings
from app.core.time import now_kst, today_kst
from app.judge.base import JudgeCaller
from app.scheduler.notify import Notifier

__all__ = [
    "CollectorFactory",
    "CollectorLike",
    "SchedulerContext",
    "default_collectors",
    "default_context",
    "default_fixture_dir",
]

REPO_ROOT = Path(__file__).resolve().parents[3]


@runtime_checkable
class CollectorLike(Protocol):
    """``app.core.protocols.Collector`` 와 같은 모양(수집기마다 부가 속성이 있어 이름만 따로 둔다)."""

    def fetch(self, region: Region, snapshot: Snapshot, since: str | None) -> list[RawDocument]: ...


CollectorFactory = Callable[["SchedulerContext"], CollectorLike]


def default_fixture_dir() -> Path:
    env = os.environ.get("JUDGE_FIXTURE_DIR")
    if env:
        return Path(env)
    return REPO_ROOT / "contracts" / "fixtures" / "incheon_gimpo_2026-10-08"


def default_collectors() -> dict[str, CollectorFactory]:
    """운영 수집기. import 는 실제로 쓸 때 한다(Playwright 등 무거운 의존성)."""

    def applyhome(ctx: SchedulerContext) -> CollectorLike:
        from app.collectors.applyhome import ApplyhomeCollector

        return ApplyhomeCollector(today=ctx.today)

    def notice_pdf(ctx: SchedulerContext) -> CollectorLike:
        from app.collectors.notice_pdf import NoticePdfCollector

        return NoticePdfCollector()

    def official_site(ctx: SchedulerContext) -> CollectorLike:
        from app.collectors.official_site import OfficialSiteCollector

        return OfficialSiteCollector()

    def rtms(ctx: SchedulerContext) -> CollectorLike:
        from app.collectors.rtms import RtmsCollector

        return RtmsCollector()

    def stats(ctx: SchedulerContext) -> CollectorLike:
        from app.collectors.stats import UnsoldCollector

        return UnsoldCollector()

    def news(ctx: SchedulerContext) -> CollectorLike:
        from app.collectors.news import NewsCollector

        return NewsCollector()

    return {
        "applyhome": applyhome,
        "notice_pdf": notice_pdf,
        "official_site": official_site,
        "rtms": rtms,
        "stats": stats,
        "news": news,
    }


def _default_reference_refresh(day: date) -> dict[str, Any]:
    from app.collectors.reference import ReferenceCollector

    report = ReferenceCollector(today=day).refresh()
    return {
        "legal_dong": report.legal_dong.total_changes if report.legal_dong else None,
        "admin_dong": report.admin_dong.total_changes if report.admin_dong else None,
        "used_fallback": list(report.used_fallback),
        "errors": list(report.errors),
        "documents": len(report.documents),
    }


@dataclass
class SchedulerContext:
    """잡 실행에 필요한 것 전부. ``adapter()`` 는 처음 쓸 때 만든다(판정기 프로세스 기동은 늦게)."""

    session_factory: sessionmaker[Session]
    adapter_factory: Callable[[], JudgeCaller]
    collectors: Mapping[str, CollectorFactory] = field(default_factory=default_collectors)
    reference_refresh: Callable[[date], dict[str, Any]] = _default_reference_refresh
    probe_judge: Callable[[], bool] | None = None
    notifier: Notifier = field(default_factory=Notifier)
    today: Callable[[], date] = today_kst
    now: Callable[[], datetime] = now_kst
    worker_id: str = field(default_factory=lambda: f"{socket.gethostname()}:{os.getpid()}")
    _adapter: JudgeCaller | None = field(default=None, repr=False)

    def adapter(self) -> JudgeCaller:
        if self._adapter is None:
            self._adapter = self.adapter_factory()
        return self._adapter

    def reset_adapter(self) -> None:
        """연결이 끊긴 어댑터를 버린다(다음 ``adapter()`` 가 새로 만든다)."""
        old, self._adapter = self._adapter, None
        close = getattr(old, "close", None)
        if callable(close):
            with contextlib.suppress(Exception):  # 닫기 실패는 무시(이미 끊긴 연결)
                close()

    def iso_now(self) -> str:
        return self.now().isoformat(timespec="seconds")

    def judge_available(self) -> bool:
        """판정기 복구 감지(degraded.py). 기본: 새 어댑터로 버전을 읽어 본다(연결 실패 = False)."""
        if self.probe_judge is not None:
            return self.probe_judge()
        from app.core.protocols import JudgeUnavailable

        try:
            fresh = self.adapter_factory()
        except JudgeUnavailable:
            return False
        try:
            if getattr(fresh, "unavailable", False):
                return False
            _ = fresh.adapter_version
            return True
        except JudgeUnavailable:
            return False
        finally:
            close = getattr(fresh, "close", None)
            if callable(close):
                with contextlib.suppress(Exception):
                    close()


def default_context(settings: Settings | None = None) -> SchedulerContext:
    s = settings or get_settings()

    def adapter_factory() -> JudgeCaller:
        from app.judge import get_adapter

        fixture = default_fixture_dir() if s.judge_adapter == "mock" else None
        return get_adapter(s, fixture_dir=fixture)

    webhook = s.webhook_url.get_secret_value() if s.webhook_url is not None else None
    return SchedulerContext(
        session_factory=get_sessionmaker(s),
        adapter_factory=adapter_factory,
        notifier=Notifier(webhook_url=webhook or None),
    )
