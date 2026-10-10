"""T3 후반부 (RA §9): 스위첸 홈페이지 403 → '확인 불가(403)'; G7 사람 확인 '가능' 입력 →
human_check 행 + intake_status(path=human_check) 행 + change_event(critical, triggers_rejudge)
+ rejudge 잡 제안.

D11-1(계약 .8): 발행 스냅샷(12)은 불변 — 사람 확인 접수 행·변경 이벤트는 같은 기준일의 새 리비전(building)에 들어가고,
재판정·publish 뒤 그 리비전이 기본 화면이 된다. 발행 12 의 접수 행은 그대로다."""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.db import get_session
from app.models import ChangeEvent, HumanCheck, IntakeStatus, JobRun

from ._support import FIXTURE, WRITE, validate

T3 = FIXTURE / "raw" / "human_check" / "t3_switzen_possible.json"


def _t3_req() -> dict[str, Any]:
    """T3 픽스처 본문. 픽스처(WP9)의 checked_at 은 날짜만 — 계약 .11(D14-6)부터 시간대 붙은 RFC3339 만 받으므로 그 날 KST 시각으로."""
    req: dict[str, Any] = json.loads(T3.read_text(encoding="utf-8"))
    if len(str(req["checked_at"])) == 10:
        req["checked_at"] = f"{req['checked_at']}T10:00:00+09:00"
    return req


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
    from app.models import Snapshot

    req = _t3_req()
    before = _intake_count(4)
    with get_session() as s:
        jobs_before = int(s.scalar(select(func.count()).select_from(JobRun)) or 0)
    r = client.post("/api/ops/human-checks", headers=WRITE, json=req)
    assert r.status_code == 201, r.text
    body = r.json()
    validate("createHumanCheck", 201, body)
    assert body["created_intake"]["path"] == "human_check" and body["created_intake"]["status"] == "가능"
    rev = body["created_intake"]["snapshot_id"]
    with get_session() as s:
        snap = s.get(Snapshot, rev)
        assert snap is not None and rev != 12, "발행 12 는 불변 — 새 리비전"
        assert (snap.revision, snap.revision_of, snap.status) == (2, 12, "building")
        assert snap.asof_date == s.get(Snapshot, 12).asof_date  # type: ignore[union-attr]
    # 계약 .9(D12-5): 재판정은 자동 등록 — rejudge_job_id. suggested_job 은 그 잡과 같은 payload(호환)
    assert body["suggested_job"]["job_name"] == "rejudge"
    with get_session() as s:
        rj = s.get(JobRun, body["rejudge_job_id"])
        assert rj is not None and (rj.job_name, rj.status) == ("rejudge", "queued")
        assert rj.payload["snapshot_id"] == rev and rj.payload["complex_ids"] == [4]
        assert rj.payload["change_event_ids"] == [body["change_event_id"]]

    assert _intake_count(4) == before, "발행 스냅샷의 접수 행은 바뀌지 않는다"
    with get_session() as s:
        hc = s.get(HumanCheck, body["id"])
        assert hc is not None and hc.entered_by == "운영자"
        ce = s.get(ChangeEvent, body["change_event_id"])
        assert ce is not None
        assert (ce.entity, ce.severity, ce.triggers_rejudge, ce.complex_id, ce.snapshot_id) == (
            "intake_status",
            "critical",
            True,
            4,
            rev,
        )
        assert ce.new_text == "가능"
        # D12-5: 자동 등록 rejudge 1건(화면이 POST /jobs 하지 않는다)
        assert int(s.scalar(select(func.count()).select_from(JobRun)) or 0) == jobs_before + 1

    # 기본 화면(발행 12)은 그대로, 새 리비전에서는 human_check 우선 → '가능'
    assert client.get("/api/complexes/4", headers=WRITE).json()["intake_current"]["status"] == "확인 불가"
    detail = client.get("/api/complexes/4", params={"snapshot": rev}, headers=WRITE).json()
    assert detail["intake_current"]["path"] == "human_check"
    assert detail["intake_current"]["status"] == "가능"
    row = next(
        i
        for i in client.get(f"/api/snapshots/{rev}/complexes", headers=WRITE).json()["items"]
        if i["complex_id"] == 4
    )
    assert row["intake"]["path"] == "human_check"
    snaps = client.get("/api/regions/1/snapshots", headers=WRITE).json()
    validate("listSnapshots", 200, snaps)
    assert any(x["id"] == rev and x["revision"] == 2 and x["revision_of"] == 12 for x in snaps)

    # 화면이 (옛 토스트 버튼으로) 제안을 다시 보내도 대기 중인 같은 잡 — 중복 rejudge 없음
    r = client.post("/api/jobs", headers=WRITE, json=body["suggested_job"])
    assert r.status_code == 202, r.text
    assert r.json()["id"] == body["rejudge_job_id"] and r.json()["kind"] == "rejudge"
    with get_session() as s:
        assert int(s.scalar(select(func.count()).select_from(JobRun)) or 0) == jobs_before + 1

    # 변경 피드(새 리비전)에 critical 1
    feed = client.get(f"/api/snapshots/{rev}/changes", params={"severity": "critical"}, headers=WRITE).json()
    assert any(c["id"] == body["change_event_id"] and c["complex_name"] == "오퍼스 한강 스위첸" for c in feed)


def test_human_check_validation(client: TestClient) -> None:
    req = _t3_req()
    r = client.post("/api/ops/human-checks", headers=WRITE, json={**req, "value_text": "아마도"})
    assert r.status_code == 422
    r = client.post("/api/ops/human-checks", headers=WRITE, json={**req, "complex_id": 99999})
    assert r.status_code == 404
    # 기타(other) → human_check 행만, intake·change·잡 제안 없음
    r = client.post(
        "/api/ops/human-checks", headers=WRITE, json={**req, "field": "other", "value_text": "견본주택 휴무"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    validate("createHumanCheck", 201, body)
    assert body["created_intake"] is None and body["suggested_job"] is None and body["entity"] is None
    assert body["rejudge_job_id"] is None, "기타는 기록만 — 재판정 없음"
    # 계약 밖 field 값 → 422(계약 .8 HumanCheckField)
    r = client.post("/api/ops/human-checks", headers=WRITE, json={**req, "field": "price", "value_text": "1"})
    assert r.status_code == 422
    # 사실 필드(입주 예정) → 0순위 후보로 사실이 바뀌고(D11-3) 잡 제안 — 접수 행 없음
    r = client.post(
        "/api/ops/human-checks", headers=WRITE, json={**req, "field": "move_in_ym", "value_text": "2028-08"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    validate("createHumanCheck", 201, body)
    assert body["created_intake"] is None and (body["entity"], body["entity_id"]) == ("complex", 4)
    assert body["rejudge_job_id"] is not None and body["suggested_job"]["job_name"] == "rejudge"
    detail = client.get("/api/complexes/4", headers=WRITE).json()
    assert (
        detail["header"]["move_in_ym"]["v"] == "2028-08"
        and detail["header"]["move_in_ym"]["label"] == "확인됨"
    )
    # minor 11: 형·범위 — 정수 필드 소수·범위 밖·연월 아님은 422(잘라 쓰지 않는다)
    for field, value in (("resale_months", "6.02"), ("resale_months", "-3"), ("residency_months", "999"),
                         ("move_in_ym", "2999-01"), ("move_in_ym", "2028-13"), ("down_payment_pct", "150")):  # fmt: skip
        r = client.post(
            "/api/ops/human-checks", headers=WRITE, json={**req, "field": field, "value_text": value}
        )
        assert r.status_code == 422, (field, value, r.text)
    # 길이·guard: note 500자 초과·전화번호는 422
    r = client.post("/api/ops/human-checks", headers=WRITE, json={**req, "note": "가" * 501})
    assert r.status_code == 422
    r = client.post("/api/ops/human-checks", headers=WRITE, json={**req, "note": "담당 010-1234-5678 통화"})
    assert r.status_code == 422
