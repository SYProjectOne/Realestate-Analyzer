"""T3 후반부 (RA §9): 스위첸 홈페이지 403 → '확인 불가(403)'; G7 사람 확인 '가능' 입력 →
human_check 행 + intake_status(path=human_check) 행 + change_event(critical, triggers_rejudge)
+ rejudge 잡 제안."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.db import get_session
from app.models import ChangeEvent, HumanCheck, IntakeStatus, JobRun

from ._support import FIXTURE, WRITE, validate

T3 = FIXTURE / "raw" / "human_check" / "t3_switzen_possible.json"


def _intake_count(complex_id: int) -> int:
    with get_session() as s:
        return int(
            s.scalar(
                select(func.count())
                .select_from(IntakeStatus)
                .where(IntakeStatus.complex_id == complex_id, IntakeStatus.snapshot_id == 12)
            )
            or 0
        )


def test_t3_before_is_unknown_403(client: TestClient) -> None:
    body = client.get("/api/complexes/4", headers=WRITE).json()
    cur = body["intake_current"]
    assert (cur["status"], cur["http_status"], cur["reason"]) == ("확인 불가", 403, "403")


def test_t3_human_check_creates_intake_change_and_job(client: TestClient) -> None:
    req = json.loads(T3.read_text(encoding="utf-8"))
    before = _intake_count(4)
    with get_session() as s:
        jobs_before = int(s.scalar(select(func.count()).select_from(JobRun)) or 0)
    r = client.post("/api/ops/human-checks", headers=WRITE, json=req)
    assert r.status_code == 201, r.text
    body = r.json()
    validate("createHumanCheck", 201, body)
    assert body["created_intake"]["path"] == "human_check" and body["created_intake"]["status"] == "가능"
    assert body["created_intake"]["snapshot_id"] == 12
    assert body["suggested_job"]["job_name"] == "rejudge"
    assert body["suggested_job"]["payload"]["complex_ids"] == [4]
    assert body["suggested_job"]["payload"]["change_event_ids"] == [body["change_event_id"]]

    assert _intake_count(4) == before + 1
    with get_session() as s:
        hc = s.get(HumanCheck, body["id"])
        assert hc is not None and hc.entered_by == "운영자"
        ce = s.get(ChangeEvent, body["change_event_id"])
        assert ce is not None
        assert (ce.entity, ce.severity, ce.triggers_rejudge, ce.complex_id) == (
            "intake_status",
            "critical",
            True,
            4,
        )
        assert ce.new_text == "가능"
        # 잡 등록은 화면이 POST /jobs 로 한다(openapi createHumanCheck 설명) — 여기서는 제안만
        assert int(s.scalar(select(func.count()).select_from(JobRun)) or 0) == jobs_before

    # 표시값 = human_check 우선 → '가능', 사람 확인
    detail = client.get("/api/complexes/4", headers=WRITE).json()
    assert detail["intake_current"]["path"] == "human_check"
    assert detail["intake_current"]["status"] == "가능"
    row = next(
        i
        for i in client.get("/api/snapshots/12/complexes", headers=WRITE).json()["items"]
        if i["complex_id"] == 4
    )
    assert row["intake"]["path"] == "human_check"

    # 화면이 제안 잡을 그대로 등록 → rejudge 1
    r = client.post("/api/jobs", headers=WRITE, json=body["suggested_job"])
    assert r.status_code == 202, r.text
    assert r.json()["job_name"] == "rejudge" and r.json()["kind"] == "rejudge"

    # 변경 피드에 critical 1
    feed = client.get("/api/snapshots/12/changes", params={"severity": "critical"}, headers=WRITE).json()
    assert any(c["id"] == body["change_event_id"] and c["complex_name"] == "오퍼스 한강 스위첸" for c in feed)


def test_human_check_validation(client: TestClient) -> None:
    req = json.loads(T3.read_text(encoding="utf-8"))
    r = client.post("/api/ops/human-checks", headers=WRITE, json={**req, "value_text": "아마도"})
    assert r.status_code == 422
    r = client.post("/api/ops/human-checks", headers=WRITE, json={**req, "complex_id": 99999})
    assert r.status_code == 404
    # 다른 필드(접수 상태 아님) → human_check 행만, intake·change 없음
    r = client.post(
        "/api/ops/human-checks", headers=WRITE, json={**req, "field": "move_in_ym", "value_text": "2028-08"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    validate("createHumanCheck", 201, body)
    assert body["created_intake"] is None and body["suggested_job"] is None
