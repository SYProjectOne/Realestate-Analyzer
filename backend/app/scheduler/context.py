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

네트워크 모드(R3 W10 — worker CLI 녹화 재생·오프라인): 환경변수로 수집기의 HTTP 전송을 바꾼다.

| 환경변수 | 값 | 뜻 |
| --- | --- | --- |
| ``WORKER_NET_MODE`` | ``live``(기본) / ``offline`` / ``replay`` | offline = 모든 요청 ConnectError(실패 행으로 남음), replay = 녹화 재생 |
| ``WORKER_REPLAY_ARCHIVE`` | zip 경로 | replay 녹화(``manifest.json`` + 본문, 청약홈 WP1a 녹화 형식). 녹화에 없는 요청은 ConnectError |
| ``WORKER_TODAY`` | YYYY-MM-DD | 시계 고정(녹화 조회 창과 맞추기). 없으면 실제 오늘 |

offline·replay 에서는 공식 홈페이지 렌더(Playwright)를 끈다(``render='never'``) — 렌더 폴백이 실제 접속을 하므로.
참조 표 갱신도 같은 전송을 써서 실패하면 저장소 사본(``contracts/fixtures/reference``)으로 폴백한다.
``python -m app.worker`` 가 ``default_context`` 를 쓰므로 CLI 에 그대로 적용된다.

판정기는 ``app.judge.get_adapter`` 로만 만든다(AGENTS 규칙 4). mock 어댑터의 녹화 디렉터리는
``JUDGE_FIXTURE_DIR`` 환경변수(없으면 저장소의 인천·김포 픽스처) — 개발·e2e 전용.
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

import contextlib
import json
import os
import socket
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable
from urllib.parse import parse_qsl, urlsplit

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.db import get_sessionmaker
from app.core.settings import Settings, get_settings
from app.core.time import KST, now_kst, today_kst
from app.judge.base import JudgeCaller
from app.scheduler.notify import Notifier

if TYPE_CHECKING:
    from app.core.http import HttpClient

__all__ = [
    "NET_MODES",
    "CollectorFactory",
    "CollectorLike",
    "NetConfig",
    "SchedulerContext",
    "default_collectors",
    "default_context",
    "default_fixture_dir",
    "net_config_from_env",
    "offline_transport",
    "replay_transport",
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


NET_MODES: Final = ("live", "offline", "replay")
_REPLAY_FORM_KEYS: Final = ("beginPd", "endPd", "suplyAreaCode", "pageIndex")
_SECRET_PARAMS: Final = frozenset({"serviceKey"})


@dataclass(frozen=True)
class NetConfig:
    """수집기 네트워크 모드(W10)."""

    mode: str = "live"
    replay_archive: Path | None = None
    today: date | None = None

    def __post_init__(self) -> None:
        if self.mode not in NET_MODES:
            raise ValueError(f"WORKER_NET_MODE 는 {NET_MODES} 중 하나: {self.mode!r}")
        if self.mode == "replay" and (self.replay_archive is None or not self.replay_archive.is_file()):
            raise ValueError(
                f"WORKER_NET_MODE=replay 에는 WORKER_REPLAY_ARCHIVE(zip)가 필요: {self.replay_archive}"
            )


def net_config_from_env(environ: Mapping[str, str] | None = None) -> NetConfig:
    env = os.environ if environ is None else environ
    archive = env.get("WORKER_REPLAY_ARCHIVE")
    today = env.get("WORKER_TODAY")
    return NetConfig(
        mode=(env.get("WORKER_NET_MODE") or "live").strip().lower(),
        replay_archive=Path(archive) if archive else None,
        today=date.fromisoformat(today) if today else None,
    )


def _fail(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("[offline] WORKER_NET_MODE — 네트워크 꺼짐", request=request)


def offline_transport() -> httpx.MockTransport:
    """모든 요청 ConnectError(DNS 실패와 같은 실패 행)."""
    return httpx.MockTransport(_fail)


def _replay_key(
    method: str, url: str, form: Mapping[str, str] | None
) -> tuple[str, str, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    parts = urlsplit(url)
    query = tuple(
        sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in _SECRET_PARAMS)
    )
    body = tuple(sorted((k, v) for k, v in (form or {}).items() if k in _REPLAY_FORM_KEYS))
    return (method.upper(), f"{parts.scheme}://{parts.netloc}{parts.path}", query, body)


def replay_transport(archive_path: Path) -> httpx.MockTransport:
    """녹화 zip(manifest.json entries: method·url·form·status·file·content_type) 재생. robots.txt 는 404(허용).

    녹화에 없는 요청은 ConnectError(실패 행) — 실제 사이트로 나가지 않는다. 미스 목록은 ``transport.misses``.
    """
    archive = zipfile.ZipFile(archive_path)
    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    entries = {_replay_key(e["method"], e["url"], e.get("form")): e for e in manifest["entries"]}
    misses: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404, text="not found")
        form = None
        if request.method == "POST":
            form = dict(parse_qsl(request.content.decode("utf-8"), keep_blank_values=True))
        entry = entries.get(_replay_key(request.method, str(request.url), form))
        if entry is None:
            misses.append(f"{request.method} {request.url.host}{request.url.path}")
            raise httpx.ConnectError("[replay] 녹화에 없는 요청", request=request)
        body = archive.read(entry["file"]) if entry.get("file") else b""
        headers = {"content-type": entry.get("content_type", "text/html")}
        return httpx.Response(entry["status"], content=body, headers=headers)

    transport = httpx.MockTransport(handle)
    transport.misses = misses  # type: ignore[attr-defined]
    return transport


def _net_client(net: NetConfig, *, replay: bool) -> HttpClient:
    from app.core.http import HttpClient

    transport = (
        replay_transport(net.replay_archive)
        if replay and net.mode == "replay" and net.replay_archive is not None
        else offline_transport()
    )
    return HttpClient(
        max_retries=0, jitter=0.0, rate_per_host=1000.0, sleep=lambda _s: None, transport=transport
    )


def default_collectors(net: NetConfig | None = None) -> dict[str, CollectorFactory]:
    """운영 수집기. import 는 실제로 쓸 때 한다(Playwright 등 무거운 의존성).

    ``net`` 이 offline·replay 면 수집기마다 그 전송의 HttpClient 를 넣는다(W10). replay 녹화는 청약홈·공고문만 —
    나머지 수집기는 오프라인(실패 행).
    """
    if net is not None and net.mode != "live":
        return _offline_collectors(net)

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


def _offline_collectors(net: NetConfig) -> dict[str, CollectorFactory]:
    def applyhome(ctx: SchedulerContext) -> CollectorLike:
        from app.collectors.applyhome import ApplyhomeCollector

        return ApplyhomeCollector(http=_net_client(net, replay=True), today=ctx.today, service_key=None)

    def notice_pdf(ctx: SchedulerContext) -> CollectorLike:
        from app.collectors.notice_pdf import NoticePdfCollector

        return NoticePdfCollector(http=_net_client(net, replay=True), ocr=None)

    def official_site(ctx: SchedulerContext) -> CollectorLike:
        from app.collectors.official_site import OfficialSiteCollector

        return OfficialSiteCollector(http=_net_client(net, replay=False), render="never")

    def rtms(ctx: SchedulerContext) -> CollectorLike:
        from app.collectors.rtms import RtmsCollector

        return RtmsCollector(http=_net_client(net, replay=False))

    def stats(ctx: SchedulerContext) -> CollectorLike:
        from app.collectors.stats import UnsoldCollector

        return UnsoldCollector(http=_net_client(net, replay=False))

    def news(ctx: SchedulerContext) -> CollectorLike:
        from app.collectors.news import NewsCollector

        return NewsCollector(http=_net_client(net, replay=False))

    return {
        "applyhome": applyhome,
        "notice_pdf": notice_pdf,
        "official_site": official_site,
        "rtms": rtms,
        "stats": stats,
        "news": news,
    }


def _offline_reference_refresh(net: NetConfig) -> Callable[[date], dict[str, Any]]:
    def refresh(day: date) -> dict[str, Any]:
        from app.collectors.reference import ReferenceCollector

        report = ReferenceCollector(http=_net_client(net, replay=False), today=day).refresh()
        return {
            "legal_dong": report.legal_dong.total_changes if report.legal_dong else None,
            "admin_dong": report.admin_dong.total_changes if report.admin_dong else None,
            "used_fallback": list(report.used_fallback),
            "errors": list(report.errors),
            "documents": len(report.documents),
            "net_mode": net.mode,
        }

    return refresh


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

    def __post_init__(self) -> None:
        # 보낸 알림 영속 기록(job_run stats 의 notified_event_ids) — 재시작해도 같은 이벤트를 다시 보내지 않는다(R3 m13)
        if self.notifier.load_sent is None:
            factory = self.session_factory

            def _load() -> set[int]:
                from app.scheduler.notify import sent_ids_from_jobs

                with factory() as session:
                    return sent_ids_from_jobs(session)

            self.notifier.load_sent = _load

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


def default_context(settings: Settings | None = None, net: NetConfig | None = None) -> SchedulerContext:
    s = settings or get_settings()

    def adapter_factory() -> JudgeCaller:
        from app.judge import get_adapter

        fixture = default_fixture_dir() if s.judge_adapter == "mock" else None
        return get_adapter(s, fixture_dir=fixture)

    webhook = s.webhook_url.get_secret_value() if s.webhook_url is not None else None
    net = net_config_from_env() if net is None else net
    ctx = SchedulerContext(
        session_factory=get_sessionmaker(s),
        adapter_factory=adapter_factory,
        collectors=default_collectors(net),
        notifier=Notifier(webhook_url=webhook or None),
    )
    if net.mode != "live":
        ctx.reference_refresh = _offline_reference_refresh(net)
    if net.today is not None:
        pinned = net.today
        ctx.today = lambda: pinned
        ctx.now = lambda: datetime(pinned.year, pinned.month, pinned.day, 6, 0, tzinfo=KST)
    return ctx
