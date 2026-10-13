"""R7-QUEUE(계약 2026-10-09.19, DECISIONS D26-2) — G7 접수 확인 대기열 ``GET /ops/intake-queue``.

'확인 불가'·'미정' 표시 접수 행을 저장된 사유·http_status 로 묶는다(데이터 기준 — 모르는 사유는 other '기타').
저장된 행만 읽는다: 판정기 호출·DB 쓰기 없음(AGENTS 규칙 4). READONLY_TOKEN 은 200, 공유 링크 토큰은 403(D10-7).
"""

# ruff: noqa: E501  (한국어 assertion 메시지)
from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.db import get_session
from app.models import (
    ChangeEvent,
    HumanCheck,
    IntakeStatus,
    JobRun,
    JudgmentLog,
    RawDocument,
    Region,
    Snapshot,
)

from ._support import READ, WRITE, validate

URL = "/api/ops/intake-queue"
SNAP = 12  # devseed 최신 published

CATEGORY_ORDER = ["collect_failed", "identity", "no_phrase", "unresolved", "not_judged", "other", "undecided"]


def _items(body: dict[str, Any]) -> dict[int, tuple[str, str, dict[str, Any]]]:
    """complex_id → (category, 묶음 reason, 항목)."""
    out: dict[int, tuple[str, str, dict[str, Any]]] = {}
    for g in body["groups"]:
        for it in g["items"]:
            assert it["complex_id"] not in out, f"단지 {it['complex_id']} 가 두 번"
            out[it["complex_id"]] = (g["category"], g["reason"], it)
    return out


def _set_row(complex_id: int, **values: Any) -> int:
    """스냅샷 12 의 그 단지 official_popup 접수 행(표시 행)을 고친다 — 접수 행 id."""
    with get_session() as s:
        row = s.scalars(
            select(IntakeStatus).where(
                IntakeStatus.snapshot_id == SNAP,
                IntakeStatus.complex_id == complex_id,
                IntakeStatus.path == "official_popup",
            )
        ).one()
        for k, v in values.items():
            setattr(row, k, v)
        return int(row.id)


# ====================================================================== 기본 모양·devseed


def test_default_snapshot_queue_matches_contract(client: TestClient) -> None:
    r = client.get(URL, headers=WRITE)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("getIntakeQueue", 200, body)
    assert body["region_id"] == 1 and body["snapshot_id"] == SNAP and body["asof_date"] == "2026-10-08"
    assert body["snapshot_status"] == "published" and body["revision"] == 1
    items = _items(body)
    # devseed 스냅샷 12: 확인 불가 3(403 · '접속 실패' · DNS) — 수집 실패
    assert items[4][:2] == ("collect_failed", "403")
    assert items[4][2]["http_status"] == 403 and items[4][2]["evidence_url"] == "https://opus-switzen.com/"
    assert items[13][:2] == ("collect_failed", "접속 실패")
    assert items[14][:2] == ("collect_failed", "DNS")
    # 미정(표시 행 official_popup) → undecided, 사유 없으면 묶음 이름 '미정'
    for cid in (1, 5, 6, 8, 9, 10, 11, 12):
        assert items[cid][0] == "undecided", (cid, items[cid])
        assert items[cid][2]["status"] == "미정"
    assert items[1][1] == "추가 공급 미정(무순위 2차 이후 공고 없음, 공고 이력 있음)"
    assert items[5][1] == "미정"
    # 가능(2·3·7)·unofficial_ref 만 있는 단지(15·16 — 근거 아님)는 없다
    assert not {2, 3, 7, 15, 16} & set(items)
    assert body["total"] == sum(g["count"] for g in body["groups"]) == len(items) == 11
    for g in body["groups"]:
        assert g["count"] == len(g["items"])


def test_groups_follow_category_order_then_count(client: TestClient) -> None:
    body = client.get(URL, headers=WRITE).json()
    cats = [g["category"] for g in body["groups"]]
    assert cats == sorted(cats, key=CATEGORY_ORDER.index)
    for cat in set(cats):
        groups = [g for g in body["groups"] if g["category"] == cat]
        keys = [(-g["count"], g["reason"]) for g in groups]
        assert keys == sorted(keys), cat
        for g in groups:
            names = [(it["complex_name"], it["intake_id"]) for it in g["items"]]
            assert names == sorted(names)


# ====================================================================== 데이터 기준 묶음


CASES: list[tuple[int, dict[str, Any], str, str]] = [
    # (단지, 접수 행 값, category, 묶음 reason)
    (
        2,
        {"status": "확인 불가", "reason": "connect: [Errno 11001] getaddrinfo failed", "http_status": None},
        "collect_failed",
        "connect",
    ),
    (
        3,
        {"status": "확인 불가", "reason": "TLS(브라우저 재시도 실패)", "http_status": None},
        "collect_failed",
        "TLS",
    ),
    (7, {"status": "확인 불가", "reason": "404", "http_status": 404}, "collect_failed", "404"),
    (
        5,
        {"status": "확인 불가", "reason": "공식 홈페이지 동일성 미확인", "http_status": 200},
        "identity",
        "공식 홈페이지 동일성 미확인",
    ),
    (
        6,
        {"status": "확인 불가", "reason": "공식 홈페이지가 다른 단지", "http_status": 200},
        "identity",
        "공식 홈페이지가 다른 단지",
    ),
    (
        8,
        {"status": "확인 불가", "reason": "문구로 판단 불가", "http_status": 200},
        "no_phrase",
        "문구로 판단 불가",
    ),
    (
        9,
        {"status": "확인 불가", "reason": "접수 문구 없음", "http_status": 200},
        "no_phrase",
        "접수 문구 없음",
    ),
    (10, {"status": "확인 불가", "reason": "판정 미해결", "http_status": 200}, "unresolved", "판정 미해결"),
    (
        11,
        {"status": "확인 불가", "reason": "판정 대상 아님(공공분양)", "http_status": 200},
        "not_judged",
        "판정 대상 아님(공공분양)",
    ),
    (
        12,
        {"status": "확인 불가", "reason": "아직 없는 새 사유(R7-SITE)", "http_status": 200},
        "other",
        "아직 없는 새 사유(R7-SITE)",
    ),
    (1, {"status": "확인 불가", "reason": None, "http_status": 503}, "collect_failed", "503"),
]


def test_grouping_is_data_driven_from_stored_reason(client: TestClient) -> None:
    for cid, values, _cat, _reason in CASES:
        _set_row(cid, **values)
    body = client.get(URL, headers=WRITE).json()
    validate("getIntakeQueue", 200, body)
    items = _items(body)
    for cid, _values, cat, reason in CASES:
        assert items[cid][:2] == (cat, reason), (cid, items[cid][:2])
    # 사유가 빈 '확인 불가'는 Intake 와 같은 규칙(http_status 또는 '사유 미기재')
    assert items[1][2]["reason"] == "503"


@pytest.mark.parametrize(
    ("status", "reason", "http", "expected"),
    [
        ("확인 불가", "403", 403, ("collect_failed", "403")),
        ("확인 불가", "403", None, ("collect_failed", "403")),
        ("확인 불가", "robots.txt 503", None, ("collect_failed", "robots.txt")),
        ("확인 불가", "blocked_by_robots", None, ("collect_failed", "blocked_by_robots")),
        ("확인 불가", "timeout", None, ("collect_failed", "timeout")),
        ("확인 불가", "render: Timeout 30000ms", 200, ("collect_failed", "render")),
        ("확인 불가", "dns", None, ("collect_failed", "dns")),
        ("확인 불가", "수집 실패", None, ("collect_failed", "수집 실패")),
        ("확인 불가", "접수 문구 미분류", 200, ("unresolved", "접수 문구 미분류")),
        ("확인 불가", "판정 대상 아님(범위 경계)", 200, ("not_judged", "판정 대상 아님(범위 경계)")),
        ("확인 불가", "사람 확인", None, ("other", "사람 확인")),
        ("확인 불가", "Totally new", 200, ("other", "Totally new")),
        ("확인 불가", None, None, ("other", "사유 미기재")),
        ("미정", None, None, ("undecided", "미정")),
        ("미정", "추가 공급 미정", 200, ("undecided", "추가 공급 미정")),
    ],
)
def test_queue_key_rules(
    status: str, reason: str | None, http: int | None, expected: tuple[str, str]
) -> None:
    from app.api.intake_queue import queue_key

    assert queue_key(status, reason, http) == expected


# ====================================================================== 항목 필드


def test_item_screenshot_and_judgment_ref(client: TestClient) -> None:
    with get_session() as s:
        shot = RawDocument(
            source_kind="official_site", url="https://example.invalid/", fetched_at="2026-10-08T06:09:12+09:00",
            http_status=200, sha256="r7queue" + "0" * 57, path="official_site/2026-10-08/r7q.png",
            content_type="image/png", complex_id=8, region_id=1,
        )  # fmt: skip
        s.add(shot)
        s.flush()
        shot_id = int(shot.id)
    _set_row(
        8, status="확인 불가", reason="문구로 판단 불가", http_status=200, path="headless_shot",
        raw_document_id=shot_id, screenshot_path="official_site/2026-10-08/r7q.png",
        note="판정기 classify jl_441 · 판정기 classify jl_445 · 문구 해시 동일 — 이전 분류 복사(접수 행 3, 스냅샷 11)",
    )  # fmt: skip
    _set_row(9, status="확인 불가", reason="DNS", http_status=None, screenshot_path=None, note=None)
    items = _items(client.get(URL, headers=WRITE).json())
    it = items[8][2]
    assert it["path"] == "headless_shot"
    assert it["screenshot_raw_document_id"] == shot_id == it["raw_document_id"]
    assert it["screenshot_path"] == "official_site/2026-10-08/r7q.png"
    assert it["judgment_ref"] == "jl_445"  # 마지막 표식
    assert items[9][2]["screenshot_raw_document_id"] is None and items[9][2]["judgment_ref"] is None


def test_screenshot_found_by_path_when_row_points_elsewhere(client: TestClient) -> None:
    """접수 행 원문이 HTML 행이고 스크린샷이 다른 원문 행(같은 경로)이면 그 행 id."""
    with get_session() as s:
        shot = RawDocument(
            source_kind="official_site", url="https://example.invalid/p", fetched_at="2026-10-08T06:09:12+09:00",
            http_status=200, sha256="r7queue" + "1" * 57, path="official_site/2026-10-08/r7q2.png",
            content_type="image/png", complex_id=10, region_id=1,
        )  # fmt: skip
        s.add(shot)
        s.flush()
        shot_id = int(shot.id)
    _set_row(
        10, status="확인 불가", reason="문구로 판단 불가", screenshot_path="official_site/2026-10-08/r7q2.png"
    )
    it = _items(client.get(URL, headers=WRITE).json())[10][2]
    assert it["screenshot_raw_document_id"] == shot_id
    # 경로에 맞는 원문이 없으면 null(지어내지 않는다)
    _set_row(10, screenshot_path="official_site/2026-10-08/none.png")
    it = _items(client.get(URL, headers=WRITE).json())[10][2]
    assert it["screenshot_raw_document_id"] is None


def test_human_check_pending_until_revision_has_it(client: TestClient) -> None:
    from app.core.time import now_kst

    checked = (now_kst() - timedelta(minutes=1)).isoformat(timespec="seconds")
    r = client.post(
        "/api/ops/human-checks",
        json={
            "complex_id": 4, "field": "intake_status", "value_text": "가능", "kind": "phone",
            "checked_at": checked, "entered_by": "운영자", "note": "분양사무소 통화",
        },
        headers=WRITE,
    )  # fmt: skip
    assert r.status_code == 201, r.text
    hc_id = r.json()["id"]
    new_sid = r.json()["created_intake"]["snapshot_id"]
    assert new_sid != SNAP
    # 기본(발행 리비전 12)은 그대로 — 그 항목에 반영 대기 사람 확인
    body = client.get(URL, headers=WRITE).json()
    validate("getIntakeQueue", 200, body)
    assert body["snapshot_id"] == SNAP
    pending = _items(body)[4][2]["human_check_pending"]
    assert pending == {
        "id": hc_id,
        "value_text": "가능",
        "checked_at": checked,
        "created_at": pending["created_at"],
    }
    assert pending["created_at"]
    # 다른 항목은 대기 없음
    assert _items(body)[14][2]["human_check_pending"] is None
    # 새 리비전(사람 확인 접수 행이 있다)을 지정하면 그 단지는 '가능'이라 대기열에 없다
    body2 = client.get(URL, params={"snapshot": new_sid}, headers=WRITE).json()
    validate("getIntakeQueue", 200, body2)
    assert body2["snapshot_id"] == new_sid and 4 not in _items(body2)


def test_human_check_before_snapshot_is_not_pending(client: TestClient) -> None:
    """스냅샷을 만들기 전에 들어온 사람 확인(그 스냅샷에 없는 옛 입력)은 '반영 대기'가 아니다."""
    with get_session() as s:
        s.add(HumanCheck(
            complex_id=14, field="intake_status", value_text="가능", kind="phone", checked_at="2026-10-01T10:00:00+09:00",
            entered_by="운영자", note=None, created_at="2026-10-01T10:00:05+09:00",
        ))  # fmt: skip
    assert _items(client.get(URL, headers=WRITE).json())[14][2]["human_check_pending"] is None


# ====================================================================== 지역·스냅샷 선택, 404, 빈 대기열


def _other_region() -> int:
    with get_session() as s:
        reg = Region(name="R7 빈 지역", query_text="R7", selections=[], sido_codes=[], sigungu_codes=[],
                     legal_dong_codes=[], living_areas=[], age_premium_coef={}, applyhome_query={}, status="bootstrapping",
                     created_at="2026-10-13T00:00:00+09:00")  # fmt: skip
        s.add(reg)
        s.flush()
        return int(reg.id)


def test_region_without_snapshot_is_empty_200(client: TestClient) -> None:
    rid = _other_region()
    r = client.get(URL, params={"region_id": rid}, headers=WRITE)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("getIntakeQueue", 200, body)
    assert body == {
        "region_id": rid, "snapshot_id": None, "asof_date": None, "revision": None, "snapshot_status": None,
        "total": 0, "groups": [],
    }  # fmt: skip


def test_explicit_snapshot_and_404s(client: TestClient) -> None:
    r = client.get(URL, params={"snapshot": 11}, headers=WRITE)
    assert r.status_code == 200
    body = r.json()
    validate("getIntakeQueue", 200, body)
    assert body["snapshot_id"] == 11 and body["asof_date"] == "2026-10-07"
    assert 4 not in _items(body)  # 스냅샷 11 에는 403 행이 없다(리비전마다 따로)
    assert client.get(URL, params={"region_id": 1, "snapshot": 12}, headers=WRITE).status_code == 200
    rid = _other_region()
    for params in (
        {"region_id": 999},
        {"snapshot": 99999},
        {"region_id": rid, "snapshot": 12},
        {"region_id": 2**70},
    ):
        r = client.get(URL, params=params, headers=WRITE)
        assert r.status_code == 404, (params, r.text)
        validate("getIntakeQueue", 404, r.json())
    r = client.get(URL, params={"nope": 1}, headers=WRITE)
    assert r.status_code == 422
    validate("getIntakeQueue", 422, r.json())


# ====================================================================== 인증(D10-7)·읽기 전용(규칙 4)


def test_readonly_token_reads_share_token_forbidden(client: TestClient) -> None:
    r = client.get(URL, headers=READ)
    assert r.status_code == 200
    validate("getIntakeQueue", 200, r.json())
    assert client.get(URL).status_code == 401
    token = client.post("/api/share-links", json={"label": "공유"}, headers=WRITE).json()["token"]
    r = client.get(URL, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    validate("getIntakeQueue", 403, r.json())


def _counts() -> dict[str, int]:
    with get_session() as s:
        return {
            m.__tablename__: int(s.scalar(select(func.count()).select_from(m)) or 0)
            for m in (IntakeStatus, HumanCheck, JobRun, ChangeEvent, Snapshot, JudgmentLog, RawDocument)
        }


def test_get_reads_only(client: TestClient) -> None:
    """판정기 호출·DB 쓰기 없음(규칙 4): 판정 로그·잡·이벤트·리비전·접수 행 수 그대로, 판정기 모듈을 부르지 않는다."""
    import sys

    before = _counts()
    loaded = {m for m in sys.modules if m.startswith("app.judge.")}
    for params in ({}, {"snapshot": 11}, {"region_id": 1}):
        assert client.get(URL, params=params, headers=WRITE).status_code == 200
    assert _counts() == before
    new = {m for m in sys.modules if m.startswith("app.judge.")} - loaded
    assert not {m for m in new if m != "app.judge.guard"}, new
