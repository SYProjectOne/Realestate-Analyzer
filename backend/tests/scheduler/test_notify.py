"""notify.py: WEBHOOK_URL 없으면 no-op, critical 만, guard 통과분만, 실패해도 예외 없음 (DECISIONS D1 #7)."""

from __future__ import annotations

from typing import Any

import httpx
import respx

from app.models import ChangeEvent
from app.scheduler.notify import Notifier


def _recorder(sent: list[Any]) -> Any:
    def post(url: str, body: dict[str, Any]) -> int:
        sent.append(body)
        return 200

    return post


def _ev(severity: str = "critical", new_text: str = "a1b2", complex_id: int | None = 2) -> ChangeEvent:
    return ChangeEvent(
        snapshot_id=1, entity="complex", entity_id=complex_id, field="official_popup_hash", old_text="0f0f",
        new_text=new_text, detected_at="2026-10-08T06:00:00+09:00", severity=severity, triggers_rejudge=True,
        complex_id=complex_id,
    )  # fmt: skip


def test_no_webhook_is_noop() -> None:
    sent: list[Any] = []
    n = Notifier(webhook_url=None, post=_recorder(sent), secrets=[])
    assert n.notify([_ev()]).skipped == "no_webhook" and sent == []


def test_only_critical_sent_with_public_fields() -> None:
    sent: list[tuple[str, dict[str, Any]]] = []

    def post(url: str, body: dict[str, Any]) -> int:
        sent.append((url, body))
        return 204

    n = Notifier(webhook_url="https://hooks.example.test/x", post=post, secrets=[])
    assert n.notify([_ev("notice")]).skipped == "no_critical"
    r = n.notify([_ev(), _ev("info")], {2: "테스트 단지"})
    assert r.sent == 1 and r.status == 204
    url, body = sent[0]
    assert url == "https://hooks.example.test/x"
    assert body["events"][0]["complex"] == "테스트 단지" and "중요 변경 1건" in body["text"]


def test_guard_blocks_personal_info_and_secrets() -> None:
    sent: list[Any] = []
    n = Notifier(
        webhook_url="https://hooks.example.test/x",
        post=_recorder(sent),
        secrets=["s3cr3t-key"],
    )
    assert n.notify([_ev(new_text="분양 문의 010-1234-5678")]).skipped == "guard"
    assert n.notify([_ev(new_text="key=s3cr3t-key")]).skipped == "guard"
    assert sent == []


def test_http_failure_does_not_raise() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post("https://hooks.example.test/x").mock(return_value=httpx.Response(500))
        r = Notifier(webhook_url="https://hooks.example.test/x", secrets=[]).notify([_ev()])
    assert r.sent == 0 and r.skipped == "error" and r.status == 500
    with respx.mock(assert_all_called=True) as router:
        router.post("https://hooks.example.test/x").mock(side_effect=httpx.ConnectError("down"))
        r = Notifier(webhook_url="https://hooks.example.test/x", secrets=[]).notify([_ev()])
    assert r.skipped == "error"
