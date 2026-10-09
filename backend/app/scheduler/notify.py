"""critical change_event 웹훅 알림 (RA §10, DECISIONS D1 #7).

- ``WEBHOOK_URL`` 이 비어 있으면 아무것도 보내지 않는다(no-op, 기본값 — 사람 답: 웹훅 없음).
- critical 만 보낸다. 본문은 공개 분양 정보(단지명·필드·이전/새 값·감지 시각)뿐이고, 보내기 전에
  ``app.judge.guard.check_payload`` 를 **이벤트마다** 통과해야 한다(전화·주민번호·이메일·환경변수 값 → 그 이벤트만
  빼고 나머지는 보낸다, AGENTS 규칙 6 · R3 minor 13). 모두 걸리면 skipped='guard'.
- 같은 change_event(id)는 한 번만 보낸다. 보낸 id 는 잡 stats 의 ``notified_event_ids`` 로 **영속**한다(R3 m13) — worker
  를 다시 띄워도 ``Notifier.load_sent``(job_run stats 에서 읽기)로 이미 보낸 이벤트를 다시 보내지 않는다.
  알림 경로: collect.daily(handlers), rejudge 잡(payload change_event_ids — 사람 확인·생활권 편집 등 API 경로),
  파이프라인 접수 상태 변경(D9-3), 판정기 버전 변경(judge_version).
- 서버 쪽 알림(R3 m13): API 가 만든 critical 이벤트(사람 확인 접수 상태·생활권 편집)는 화면 토스트의 '재판정' 클릭을
  기다리지 않는다 — worker 가 큐를 돌 때마다 ``pending_api_events`` 를 찾아 그 이벤트로 rejudge 를 등록한다(재판정 잡이
  알림을 보내고 stats 에 남긴다). 토스트로 이미 등록됐거나(같은 이벤트 id 를 가진 잡) 이미 보낸 이벤트는 건너뛴다.
- 전송 실패는 예외로 잡을 멈추지 않는다 — 로그(상태 코드만)와 반환값으로 남긴다. URL 은 로그에 쓰지 않는다.
- 웹훅은 크롤링이 아니라서 ``core.http``(robots·속도 제한) 대신 httpx 를 직접 쓴다.
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.judge.guard import check_payload, default_secrets
from app.models import ChangeEvent, IntakeStatus, JobRun

__all__ = [
    "SENT_KEY",
    "Notifier",
    "NotifyResult",
    "build_payload",
    "pending_api_events",
    "sent_ids_from_jobs",
]

SENT_KEY: Final = "notified_event_ids"
"""잡 stats(어느 깊이든)에 보낸 change_event id 목록을 남기는 키 — 영속 기록."""
_JOB_SCAN: Final = 2000
_PENDING_DAYS: Final = 7

log = get_logger("app.scheduler.notify")
PostFn = Callable[[str, dict[str, Any]], int]
_TEXT_MAX = 300


def _post(url: str, body: dict[str, Any]) -> int:
    with httpx.Client(timeout=10.0) as client:
        return client.post(url, json=body).status_code


def build_payload(events: Sequence[ChangeEvent], names: Mapping[int, str]) -> dict[str, Any]:
    items = [
        {
            "entity": e.entity,
            "field": e.field,
            "complex": names.get(e.complex_id) if e.complex_id is not None else None,
            "old": (e.old_text or "")[:_TEXT_MAX] or None,
            "new": (e.new_text or "")[:_TEXT_MAX] or None,
            "detected_at": e.detected_at,
            "triggers_rejudge": bool(e.triggers_rejudge),
        }
        for e in events
    ]
    lines = [
        f"- {i['complex'] or i['entity']}: {i['field']} {i['old'] or '∅'} → {i['new'] or '∅'}" for i in items
    ]
    return {"text": f"[청약 분석] 중요 변경 {len(items)}건\n" + "\n".join(lines), "events": items}


@dataclass(slots=True)
class NotifyResult:
    sent: int = 0
    skipped: str | None = None  # 'no_webhook' | 'no_critical' | 'guard' | 'error' | 'already_sent'
    status: int | None = None
    blocked: int = 0  # guard 에 걸려 뺀 이벤트 수
    event_ids: list[int] = field(default_factory=list)  # 이번에 보낸 이벤트 id(잡 stats 에 영속)

    def stats(self) -> dict[str, Any]:
        """잡 stats 용(``notified_event_ids`` = 영속 기록)."""
        return {"sent": self.sent, "skipped": self.skipped, "status": self.status, "blocked": self.blocked,
                SENT_KEY: list(self.event_ids)}  # fmt: skip


def _walk_ids(obj: Any, out: set[int]) -> None:
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            if k == SENT_KEY and isinstance(v, list):
                out.update(int(i) for i in v if isinstance(i, int))
            else:
                _walk_ids(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_ids(v, out)


def sent_ids_from_jobs(session: Session, limit: int = _JOB_SCAN) -> set[int]:
    """최근 잡(id 내림차순 ``limit`` 개) stats 의 ``notified_event_ids`` 합집합 — 재시작해도 다시 보내지 않는다."""
    out: set[int] = set()
    for stats in session.scalars(select(JobRun.stats).order_by(JobRun.id.desc()).limit(limit)):
        _walk_ids(stats, out)
    return out


def _job_event_ids(session: Session, limit: int = _JOB_SCAN) -> set[int]:
    """잡 payload 의 change_event_ids(토스트·수집이 이미 재판정에 실은 이벤트)."""
    out: set[int] = set()
    for payload in session.scalars(select(JobRun.payload).order_by(JobRun.id.desc()).limit(limit)):
        ids = (payload or {}).get("change_event_ids") if isinstance(payload, Mapping) else None
        if isinstance(ids, list):
            out.update(int(i) for i in ids if isinstance(i, int))
    return out


def pending_api_events(session: Session, *, now: datetime, sent: Iterable[int] = ()) -> list[ChangeEvent]:
    """API 가 만든 critical·재판정 이벤트 중 아직 재판정 잡에 실리지 않고 보내지도 않은 것(최근 7일).

    API 경로 = 사람 확인 접수 상태(intake_status 이벤트의 행이 path 'human_check')·생활권 편집(entity 'region').
    수집·파이프라인 이벤트는 그 잡이 바로 알리므로 여기서 다루지 않는다."""
    since = (now - timedelta(days=_PENDING_DAYS)).isoformat()
    done = set(sent) | _job_event_ids(session) | sent_ids_from_jobs(session)
    out: list[ChangeEvent] = []
    rows = session.scalars(
        select(ChangeEvent)
        .where(
            ChangeEvent.severity == "critical",
            ChangeEvent.triggers_rejudge.is_(True),
            ChangeEvent.entity.in_(("intake_status", "region")),
            ChangeEvent.detected_at >= since[:10],
        )
        .order_by(ChangeEvent.id)
    )
    for ev in rows:
        if ev.id in done:
            continue
        if ev.entity == "intake_status":
            row = session.get(IntakeStatus, ev.entity_id) if ev.entity_id is not None else None
            if row is None or row.path != "human_check":
                continue
        out.append(ev)
    return out


@dataclass
class Notifier:
    webhook_url: str | None = None
    post: PostFn = _post
    secrets: Sequence[str] | None = None
    sent_bodies: list[dict[str, Any]] = field(default_factory=list, repr=False)
    sent_ids: set[int] = field(default_factory=set, repr=False)
    load_sent: Callable[[], Iterable[int]] | None = field(default=None, repr=False)
    """영속 기록 읽기(SchedulerContext 가 job_run stats 를 읽는 함수를 단다). 처음 보낼 때 1회 합친다."""
    _loaded: bool = field(default=False, repr=False)

    def _ensure_loaded(self) -> None:
        if self._loaded or self.load_sent is None:
            return
        try:
            self.sent_ids.update(self.load_sent())
            self._loaded = True
        except Exception:  # DB 미준비 등 — 다음에 다시
            log.warning("notify.load_sent.error")

    def notify(self, events: Iterable[ChangeEvent], names: Mapping[int, str] | None = None) -> NotifyResult:
        critical = [e for e in events if e.severity == "critical"]
        if not self.webhook_url:
            return NotifyResult(skipped="no_webhook")
        if not critical:
            return NotifyResult(skipped="no_critical")
        self._ensure_loaded()
        fresh = [e for e in critical if e.id is None or e.id not in self.sent_ids]
        if not fresh:
            return NotifyResult(skipped="already_sent")
        secrets = self.secrets if self.secrets is not None else default_secrets()
        allowed: list[ChangeEvent] = []
        blocked = 0
        for e in fresh:  # 건별 guard — 한 건 때문에 배치 전체를 버리지 않는다
            checked = check_payload(build_payload([e], names or {}), secrets=secrets)
            if checked.ok:
                allowed.append(e)
            else:
                blocked += 1
                log.warning("notify.blocked", extra={"kinds": ",".join(checked.kinds()), "event_id": e.id})
        if not allowed:
            return NotifyResult(skipped="guard", blocked=blocked)
        critical = allowed
        body = build_payload(critical, names or {})
        try:
            status = self.post(self.webhook_url, body)
        except httpx.HTTPError as exc:
            log.warning("notify.error", extra={"error": type(exc).__name__, "events": len(critical)})
            return NotifyResult(skipped="error", blocked=blocked)
        self.sent_bodies.append(body)
        if status >= 400:
            log.warning("notify.http_error", extra={"status": status, "events": len(critical)})
            return NotifyResult(skipped="error", status=status, blocked=blocked)
        ids = [e.id for e in critical if e.id is not None]
        self.sent_ids.update(ids)
        log.info("notify.sent", extra={"status": status, "events": len(critical), "blocked": blocked})
        return NotifyResult(sent=len(critical), status=status, blocked=blocked, event_ids=ids)
