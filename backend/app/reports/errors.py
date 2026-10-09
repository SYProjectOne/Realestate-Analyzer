"""보고서 생성 예외. WP7 runner·WP5 API 가 잡아 job_run.status=failed / 409 로 바꾼다."""

from __future__ import annotations

__all__ = ["ReportBlocked", "ReportError", "ReportNotFound"]


class ReportError(Exception):
    """보고서를 만들 수 없음(공통 부모)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ReportBlocked(ReportError):
    """스냅샷에 contradicted claim 이 남아 있어 생성 거부(DECISIONS D4, 계약 Report.blocked_reason)."""


class ReportNotFound(ReportError):
    """스냅샷·비교 스냅샷·시나리오가 없음."""
