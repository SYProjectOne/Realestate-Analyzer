"""R3 M12: 판정기 버전 변경 감지는 error·blocked 행을 근거로 쓰지 않는다 + 모델을 처음 알게 된 것은 변경 아님."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.judge.base import make_adapter_version
from app.models import JudgmentLog
from app.scheduler.judge_version import is_version_change, last_logged

BARE = make_adapter_version("0.14.1")
WITH_MODEL = make_adapter_version("0.14.1", "jev-1.13.0")


def _row(session: Session, seq_hex: str, status: str, version: str) -> None:
    session.add(JudgmentLog(tool="screen", purpose="p", input_hash="sha256:" + seq_hex * 64, input_len=1,
                            input_json={}, output_json={}, status=status, adapter_version=version,
                            created_at="2026-10-09T00:00:00+09:00"))  # fmt: skip
    session.flush()


def test_m12_last_logged_skips_error_and_blocked_rows(db_session: Session) -> None:
    assert last_logged(db_session) == (0, None)
    _row(db_session, "a", "ok", WITH_MODEL)
    _row(db_session, "b", "error", BARE)  # 판정기 첫 호출 실패 — 모델 모름
    _row(db_session, "c", "blocked", BARE)
    seq, version = last_logged(db_session)
    assert version == WITH_MODEL and seq == 1


def test_m12_first_model_is_not_a_version_change() -> None:
    assert not is_version_change(BARE, WITH_MODEL)  # 모델을 처음 알게 됨
    assert is_version_change(WITH_MODEL, make_adapter_version("0.14.1", "jev-1.14.0"))
    assert is_version_change(WITH_MODEL, make_adapter_version("0.15.0", "jev-1.13.0"))
    assert is_version_change(BARE, make_adapter_version("0.15.0", "jev-1.13.0"))
    assert not is_version_change(None, WITH_MODEL) and not is_version_change(WITH_MODEL, WITH_MODEL)
