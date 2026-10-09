"""DECISIONS D9-1 판정 범위 — 파이프라인·API 경로(WP9-후속, 보고서와의 차이는 픽스처 README 'D9-1로 인한 차이').

- mock(합성 판정 녹화 = 보고서 classify) 재판정 뒤 API 의 judge_scope 가 README 표와 같다.
- '참고 후보(순위만)'·'미해결'·'보류'는 종합 점수·순위가 없다(사다리 미실행 → p10 null → 종합 미판정, analysis/scope.py 표).
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from app.models import Ladder

from .conftest import SNAP, WRITE, RegressEnv, api_get

pytestmark = pytest.mark.regress

# 합성 녹화(보고서 classify #62·#110) + 픽스처 접수 행 → D9-1. 계약 .4 전에는 '미해결'이 score_total 에 '제외'로 실린다.
EXPECTED_SCOPE: dict[int, tuple[str, ...]] = {
    1: ("판정 대상",), 2: ("판정 대상",), 3: ("판정 대상",), 4: ("미해결", "제외"), 5: ("판정 대상",), 6: ("판정 대상",),
    7: ("판정 대상",), 8: ("판정 대상",), 9: ("판정 대상",), 10: ("판정 대상",), 11: ("판정 대상",), 12: ("판정 대상",),
    13: ("참고",), 14: ("미해결", "제외"), 15: ("보류",), 16: ("미해결", "제외"),
}  # fmt: skip
# 기대값 갱신(R3 마무리): 12 더샵 송도마리나베이 '참고' → '판정 대상' — CEO 결정으로 접수 '미정'(마감·4회차 미정 = 공고 이력 +
# 추가 공급 미정, meta §1-3-4).


def _full_rejudge(env: RegressEnv, judge: str) -> None:
    r = env.client.post(
        "/api/jobs",
        headers=WRITE,
        json={"job_name": "rejudge", "payload": {"snapshot_id": SNAP, "scenario_id": None, "complex_ids": None, "reason": "D9-1 회귀"}},
    )
    assert r.status_code == 202, r.text
    assert env.worker(env.ctx(judge)) == 0
    job = api_get(env, f"/jobs/{r.json()['id']}")
    assert job["status"] == "done", job


def _rows(env: RegressEnv) -> dict[int, dict[str, Any]]:
    body = api_get(env, f"/snapshots/{SNAP}/complexes", scenario="base", size=100)
    return {r["complex_id"]: r for r in body["items"]}


def test_d91_scope_after_mock_rejudge_matches_readme(env: RegressEnv) -> None:
    _full_rejudge(env, "mock")
    assert env.mock_misses == [], env.mock_misses[:5]
    rows = _rows(env)
    bad = {cid: rows[cid].get("judge_scope") for cid, ok in EXPECTED_SCOPE.items() if rows[cid].get("judge_scope") not in ok}
    assert not bad, bad
    top5 = [t["complex_id"] for t in api_get(env, f"/snapshots/{SNAP}/dashboard", scenario="base")["top5"]]
    assert top5 and not set(top5) & {4, 14, 16}


def _leave_ladder_rows(env: RegressEnv, *, src: int, dst: int) -> int:
    """같은 스냅샷에 ``dst`` 단지의 사다리 행을 남겨 둔다(``src`` 행 복사) — 이전 범위의 판정·이월·devseed 행 재현."""
    with env.session() as s:
        rows = list(s.scalars(select(Ladder).where(Ladder.snapshot_id == SNAP, Ladder.complex_id == src)))
        for lad in rows:
            s.add(Ladder(snapshot_id=SNAP, complex_id=dst, horizon=lad.horizon, target_ym=lad.target_ym,
                         months_from_asof=lad.months_from_asof, p5=lad.p5, p10=lad.p10, p20=lad.p20, p_flat=lad.p_flat,
                         verdicts=lad.verdicts, annualized=lad.annualized, status=lad.status,
                         judgment_seq=lad.judgment_seq, proposition_text=lad.proposition_text))  # fmt: skip
        s.commit()
        return len(rows)


def test_d91_reference_scope_has_no_total_or_rank(env: RegressEnv) -> None:
    """D9-1 '참고 후보(순위만)': 사다리 미실행 → 종합 미판정·순위 없음, 같은 스냅샷에 남은 사다리 행이 있어도.

    (R3 마무리) 원래 재현 = 마리나베이(12, 접수 '불가') 의 devseed(보고서 #67) 사다리 행이 점수에 쓰여 4.18·8위가 나오던 것.
    CEO 결정으로 마리나베이 접수가 '미정'(판정 대상)이 되어, 같은 결함을 해링턴(13, 접수 '확인 불가' = 참고)에 엘리프(2)의
    사다리 행을 남겨 두는 방식으로 재현한다 — 점수 입력(``analysis.complex_input``)·API 표시(``api.views.load_bundles``)가
    참여 규칙(``analysis.scope.runs_ladder``)으로 걸러야 한다."""
    assert _leave_ladder_rows(env, src=2, dst=13) > 0
    _full_rejudge(env, "mock")
    rows = _rows(env)
    assert rows[13]["judge_scope"] == "참고", rows[13]["judge_scope"]
    bad = {cid: (r["total"]["v"], r.get("rank")) for cid, r in rows.items()
           if r.get("judge_scope") in ("참고", "보류", "미해결", "제외") and (r["total"]["v"] is not None or r.get("rank") is not None)}  # fmt: skip
    assert not bad, bad
    assert rows[13]["p10"]["v"] is None, rows[13]["p10"]  # API 표시도 남은 사다리 행을 쓰지 않는다
    detail = api_get(env, "/complexes/13", snapshot=SNAP)
    assert detail["ladder"] == [], detail["ladder"]
