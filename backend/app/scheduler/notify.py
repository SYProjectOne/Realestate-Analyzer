"""critical change_event 웹훅 알림 (RA §10, DECISIONS D1 #7).

- ``WEBHOOK_URL`` 이 비어 있으면 아무것도 보내지 않는다(no-op, 기본값 — 사람 답: 웹훅 없음).
- critical 만 보낸다. 본문은 공개 분양 정보(단지명·필드·이전/새 값·감지 시각)뿐이고, 보내기 전에
  ``app.judge.guard.check_payload`` 를 통과해야 한다(전화·주민번호·이메일·환경변수 값 → 보내지 않음, AGENTS 규칙 6).
- 전송 실패는 예외로 잡을 멈추지 않는다 — 로그(상태 코드만)와 반환값으로 남긴다. URL 은 로그에 쓰지 않는다.
- 웹훅은 크롤링이 아니라서 ``core.http``(robots·속도 제한) 대신 httpx 를 직접 쓴다.
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.logging import get_logger
from app.judge.guard import check_payload, default_secrets
from app.models import ChangeEvent

__all__ = ["Notifier", "NotifyResult", "build_payload"]

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
    skipped: str | None = None  # 'no_webhook' | 'no_critical' | 'guard' | 'error'
    status: int | None = None


@dataclass
class Notifier:
    webhook_url: str | None = None
    post: PostFn = _post
    secrets: Sequence[str] | None = None
    sent_bodies: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def notify(self, events: Iterable[ChangeEvent], names: Mapping[int, str] | None = None) -> NotifyResult:
        critical = [e for e in events if e.severity == "critical"]
        if not self.webhook_url:
            return NotifyResult(skipped="no_webhook")
        if not critical:
            return NotifyResult(skipped="no_critical")
        body = build_payload(critical, names or {})
        checked = check_payload(body, secrets=self.secrets if self.secrets is not None else default_secrets())
        if not checked.ok:
            log.warning("notify.blocked", extra={"kinds": ",".join(checked.kinds()), "events": len(critical)})
            return NotifyResult(skipped="guard")
        try:
            status = self.post(self.webhook_url, body)
        except httpx.HTTPError as exc:
            log.warning("notify.error", extra={"error": type(exc).__name__, "events": len(critical)})
            return NotifyResult(skipped="error")
        self.sent_bodies.append(body)
        if status >= 400:
            log.warning("notify.http_error", extra={"status": status, "events": len(critical)})
            return NotifyResult(skipped="error", status=status)
        log.info("notify.sent", extra={"status": status, "events": len(critical)})
        return NotifyResult(sent=len(critical), status=status)
