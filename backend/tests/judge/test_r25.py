"""계약 2026-10-09.3 WP3: 접수 상태·포함/제외 배치 classify, judgment_log.result_json, 남은 contradicted."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.judge import payloads as P
from app.judge import pipeline
from app.judge.claims import remaining_contradicted
from app.models import Claim, JudgmentLog, Region, Snapshot

from .conftest import FakeTransport


def classify_response(rows: list[tuple[str, str, str]]) -> dict[str, Any]:
    """[(item id, 클래스, decision)] → JEV 0.14 classify 응답."""
    return {
        "tool": "jev_classify",
        "results": [
            {
                "id": i,
                "classification": cls,
                "probabilities": {cls: 0.95 if d == "auto" else 0.55},
                "top_probability": 0.95 if d == "auto" else 0.55,
                "confidence": 0.9,
                "decision": d,
            }
            for i, cls, d in rows
        ],
        "thresholds": {"auto_accept": 0.85, "minimum_margin": 0.5},
    }


# ---------------------------------------------------------------- payload


def test_intake_payload_has_four_classes_and_no_thresholds() -> None:
    p = P.classify_intake_payload(
        [("intake:c2:official_popup", "잔여 세대 선착순 동호지정 계약 중 ☎ 032-123-4567")]
    )
    assert [c["id"] for c in p["classes"]] == ["open", "pending", "closed", "unknown"]
    assert set(P.INTAKE_STATUS_BY_CLASS.values()) == {"가능", "미정", "불가", "확인 불가"}
    assert "032-123-4567" not in p["items"][0]["text"]  # 공개 텍스트만
    assert not {"auto_accept", "minimum_margin"} & set(p)


def test_classify_batch_limits() -> None:
    with pytest.raises(ValueError, match="1~64"):
        P.classify_inclusion_batch_payload([(f"complex:{i}", "t") for i in range(65)])
    with pytest.raises(ValueError, match="중복"):
        P.classify_intake_payload([("a", "x"), ("a", "y")])
    single = P.classify_inclusion_payload(item_id="complex:1", text="사업주체: 민간")
    assert single == P.classify_inclusion_batch_payload([("complex:1", "사업주체: 민간")])  # 녹화 hash 유지


# ---------------------------------------------------------------- 접수 상태


def test_intake_classify_auto_and_review(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    items = [
        pipeline.IntakeItem(2, "headless_shot", "잔여 세대 선착순 동호지정 계약 중"),
        pipeline.IntakeItem(3, "official_popup", "분양 완료 감사합니다"),
        pipeline.IntakeItem(4, "official_popup", "분양안내 계약안내문"),
        pipeline.IntakeItem(5, "official_popup", "견본주택 오픈 예정"),
    ]
    t = FakeTransport(
        responses={
            "jev_classify": classify_response(
                [
                    ("intake:c2:headless_shot", "open", "auto"),
                    ("intake:c3:official_popup", "closed", "auto"),
                    ("intake:c4:official_popup", "open", "review"),  # 미해결 → 확인 불가(판정 미해결)
                    ("intake:c5:official_popup", "pending", "auto"),
                ]
            )
        }
    )
    adapter = make_adapter(t)
    out = pipeline.p4_classify_intake(adapter, items, snapshot_id=None)
    assert len(t.calls) == 1  # 배치 1회
    got = {k: (o.status, o.reason) for k, o in out.items()}
    assert got == {
        "intake:c2:headless_shot": ("가능", None),
        "intake:c3:official_popup": ("불가", None),
        "intake:c4:official_popup": ("확인 불가", "판정 미해결"),
        "intake:c5:official_popup": ("미정", None),
    }
    assert all(o.judgment_seq is not None for o in out.values())
    # 같은 입력 → 캐시(호출 0)
    pipeline.p4_classify_intake(adapter, list(reversed(items)), snapshot_id=None)
    assert len(t.calls) == 1
    # result_json 에 정규화 결과(배치 items)
    with session_factory() as s:
        row = s.scalars(select(JudgmentLog).where(JudgmentLog.purpose == "classify:intake:batch0")).one()
        assert row.result_json is not None and row.result_json["label"] == "batch"
        assert {it["id"] for it in row.result_json["items"]} == set(got)


def test_intake_unknown_class_and_single_review(make_adapter: Callable[..., Any]) -> None:
    item = pipeline.IntakeItem(6, "official_popup", "메뉴 분양안내")
    t = FakeTransport(responses={"jev_classify": classify_response([(item.key, "unknown", "auto")])})
    out = pipeline.p4_classify_intake(make_adapter(t), [item])
    assert (out[item.key].status, out[item.key].reason) == ("확인 불가", "문구로 판단 불가")
    item2 = pipeline.IntakeItem(7, "official_popup", "선착순 계약")
    t2 = FakeTransport(responses={"jev_classify": classify_response([(item2.key, "open", "review")])})
    out2 = pipeline.p4_classify_intake(make_adapter(t2), [item2])
    assert (out2[item2.key].status, out2[item2.key].reason) == ("확인 불가", "판정 미해결")  # 미정 아님


# ---------------------------------------------------------------- 포함/제외 배치


def test_inclusion_batch_one_call(make_adapter: Callable[..., Any]) -> None:
    rows = [(f"complex:{i}", "private_sale_apt" if i != 3 else "public_sale", "auto" if i != 4 else "review")
            for i in (1, 2, 3, 4)]  # fmt: skip
    t = FakeTransport(responses={"jev_classify": classify_response(rows)})
    out = pipeline.p4_classify_inclusion_batch(
        make_adapter(t), [(4, "d"), (2, "b"), (1, "a"), (3, "c")], snapshot_id=None
    )
    assert len(t.calls) == 1
    sent = t.calls[0][1]
    assert [it["id"] for it in sent["items"]] == ["complex:1", "complex:2", "complex:3", "complex:4"]
    assert out[1].resolved and out[1].label == "private_sale_apt"
    assert out[3].resolved and out[3].label == "public_sale"
    assert not out[4].resolved and out[4].decision == "review"


# ---------------------------------------------------------------- 남은 contradicted


def test_remaining_contradicted_ignores_split_parents(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as s:
        region = s.get(Region, 1)
        assert region is not None
        snap = Snapshot(region_id=1, asof_date="2026-10-08", status="ready", degraded=False,
                        created_at="2026-10-08T06:00:00+09:00")  # fmt: skip
        s.add(snap)
        s.flush()
        parent = Claim(snapshot_id=snap.id, section="s", text="A이고 B다", verify_status="contradicted")
        alone = Claim(snapshot_id=snap.id, section="s", text="C다", verify_status="contradicted")
        s.add_all([parent, alone])
        s.flush()
        s.add(Claim(snapshot_id=snap.id, section="s", text="A다", verify_status="verified",
                    parent_claim_id=parent.id))  # fmt: skip
        s.flush()
        left = remaining_contradicted(s, snap.id)
        assert [c.id for c in left] == [alone.id]
        from app.reports.data import count_remaining_contradicted
        from app.scheduler.snapshots import contradicted_count

        assert [c.id for c in count_remaining_contradicted(s, snap.id)] == [alone.id]
        assert contradicted_count(s, snap.id) == 1
