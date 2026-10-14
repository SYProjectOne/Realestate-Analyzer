"""R10-FOLLOW(계약 2026-10-09.21, DECISIONS D29-2·D29-3) — API 쪽.

- D29-3: 체크리스트 kind '청약 접수'·'당첨자 발표'가 저장되고 `GET /ops/checklist` 가 계약대로 돌려준다(0018 CHECK).
- D29-2: 원 단지에 병합된 중복 단지 행(`complex.merged_into_id`)은 새 리비전의 목록·대시보드에서 빠지고, 이미 발행된 리비전은
  저장본 그대로(D11-1). 병합 change_event 는 사람이 읽는 한 줄 요약.
- 당첨 가점 사유 셋(R10 과제 3): 발표 전 · 가점 당첨자 없음(팝업 '-', 미달이면 '(미달)') · 가점 미수집. 요약은 가점 당첨자 없는 행을
  빼고 센다.
판정기 호출 없음, 읽기 전용 토큰 의미 그대로.
"""

# ruff: noqa: E501  (한국어 assertion 메시지)
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import ChecklistItem, Competition, Complex, FieldProvenance, Snapshot

from ._support import READ, WRITE, as_live, publish_revision, validate

SNAP = 12  # devseed 최신 published(인천)
EL = 2  # 엘리프 검단 포레듀
DASH = "가점 당첨자 없음(청약홈 '-')"


def reason_code(reason: str | None) -> str | None:
    from app.api.reason_codes import reason_code as f

    return f(reason)


def _get(client: TestClient, url: str, op: str, headers: dict[str, str] = WRITE, **params: Any) -> Any:
    r = client.get(url, headers=headers, params=params)
    assert r.status_code == 200, (url, r.text[:500])
    body = r.json()
    validate(op, 200, body)
    return body


def _detail(client: TestClient, cid: int, snap: int = SNAP) -> dict[str, Any]:
    body: dict[str, Any] = _get(client, f"/api/complexes/{cid}", "getComplex", snapshot=snap)
    return body


def _rows(client: TestClient, snap: int = SNAP) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = _get(client, f"/api/snapshots/{snap}/complexes", "listComplexes", size=200)[
        "items"
    ]
    return items


def _prov(
    entity_id: int, field: str, value: Any, *, label: str = "확인됨", reason: str | None = None,
    checked_at: str = "2026-10-08",
) -> str:  # fmt: skip
    with get_session() as s:
        fp = FieldProvenance(
            entity="competition", entity_id=entity_id, entity_key=f"r10:competition:{entity_id}", field=field,
            value_text=None if value is None else str(value), value_norm=None if value is None else str(value),
            label=label, reason=reason, url="https://www.applyhome.co.kr/ai/aia/selectAPTCompetitionPopup.do?r10",
            checked_at=checked_at, source_rank=1, chosen=True,
        )  # fmt: skip
        s.add(fp)
        s.flush()
        return f"fp_{fp.id}"


def _competition(rnd: str, type_code: str, supply: int, applied: int, ratio: str | None) -> int:
    with get_session() as s:
        c = Competition(
            complex_id=EL, round=rnd, kind="본청약", type_code=type_code, supply=supply, applied=applied,
            ratio_or_shortfall_text=ratio, raw_document_id=None,
        )  # fmt: skip
        s.add(c)
        s.flush()
        cid = int(c.id)
    _prov(cid, "supply", supply)
    _prov(cid, "applied", applied)
    return cid


def _dash(cid: int, checked_at: str) -> str:
    """경쟁률 팝업 당첨가점 칸 '-' 의 저장 모양(``normalize.applyhome_parser`` — 값 없는 '확인 불가' 출처 행)."""
    out = ""
    for f in ("winning_score_min", "winning_score_max", "winning_score_avg"):
        out = _prov(cid, f, None, label="확인 불가", reason=DASH, checked_at=checked_at)
    return out


def _scores(cid: int, lo: int, hi: int, avg: float) -> None:
    with get_session() as s:
        c = s.get(Competition, cid)
        assert c is not None
        c.winning_score_min, c.winning_score_max, c.winning_score_avg = lo, hi, avg  # type: ignore[assignment]
    for f, v in (("winning_score_min", lo), ("winning_score_max", hi), ("winning_score_avg", avg)):
        _prov(cid, f, v)


def _set_winner(day: str) -> str:
    with get_session() as s:
        cx = s.get(Complex, EL)
        snap = s.get(Snapshot, SNAP)
        assert cx is not None and snap is not None
        cx.winner_date = day
        return str(snap.asof_date)


# ====================================================================== 당첨 가점 사유 셋


def test_reason_codes_for_new_winning_score_reasons() -> None:
    assert reason_code("가점 당첨자 없음(미달)") == "no_winner"
    assert reason_code(DASH) == "no_winner"
    assert reason_code("발표 전(당첨자 발표 2026-11-05)") == "not_published"
    assert reason_code("가점 미수집") == "not_collected"


def test_dash_cells_give_no_winner_reasons_distinct_from_not_collected(client: TestClient) -> None:
    as_live()
    _set_winner("2026-01-10")
    short = _competition("1순위 해당지역", "84A", 100, 40, "(△60)")
    full = _competition("1순위 기타지역", "84A", 100, 150, "1.50")
    stale = _competition("1순위 기타지역", "59A", 80, 20, "(△60)")
    none = _competition("1순위 기타지역", "74A", 80, 90, "1.13")
    p_short = _dash(short, "2026-02-01")
    _dash(full, "2026-02-01")
    _dash(stale, "2026-01-05")  # 발표(01-10) 전에 받은 팝업의 '-' — 결과가 아니다
    rows = {c["id"]: c for c in _detail(client, EL)["competition"]}
    for name in ("winning_score_min", "winning_score_max", "winning_score_avg"):
        f = rows[short][name]
        assert (f["v"], f["label"], f["reason"], f["reason_code"]) == (
            None,
            "확인 불가",
            "가점 당첨자 없음(미달)",
            "no_winner",
        ), f
        assert f["prov"] is not None and f["prov"].startswith("fp_") and f["checked_at"] == "2026-02-01"
        g = rows[full][name]
        assert (g["reason"], g["reason_code"]) == (DASH, "no_winner"), g
        for cid in (stale, none):
            h = rows[cid][name]
            assert (h["reason"], h["reason_code"], h["prov"]) == ("가점 미수집", "not_collected", None), (
                cid,
                h,
            )
    assert rows[short]["winning_score_avg"]["prov"] == p_short


def test_before_announcement_is_not_published(client: TestClient) -> None:
    as_live()
    with get_session() as s:
        asof = str(s.get(Snapshot, SNAP).asof_date)  # type: ignore[union-attr]
    later = f"{int(asof[:4]) + 1}{asof[4:]}"
    _set_winner(later)
    short = _competition("1순위 해당지역", "84A", 100, 40, "(△60)")
    _dash(short, f"{asof[:4]}-01-01")
    d = _detail(client, EL)
    f = next(c for c in d["competition"] if c["id"] == short)["winning_score_min"]
    assert (f["reason"], f["reason_code"]) == (f"발표 전(당첨자 발표 {later})", "not_published"), f
    cs = d["competition_summary"]["winning_score_min"]
    assert cs["reason_code"] == "not_published", cs


def test_summary_skips_no_winner_rows(client: TestClient) -> None:
    as_live()
    _set_winner("2026-01-10")
    a = _competition("1순위 해당지역", "59A", 73, 454, "6.22")
    b = _competition("1순위 해당지역", "84A", 100, 40, "(△60)")
    _scores(a, 42, 63, 48.5)
    _dash(b, "2026-02-01")
    cs = _detail(client, EL)["competition_summary"]
    lo, hi = cs["winning_score_min"], cs["winning_score_max"]
    assert (lo["v"], hi["v"]) == (42, 63), (lo, hi)
    assert lo["label"] == "확인됨" and "가점 당첨자 없는 1행 제외" in lo["reason"], lo
    # 모두 '-' 면 그 사유
    with get_session() as s:
        for c in s.scalars(select(Competition).where(Competition.id == a)):
            s.delete(c)
    cs2 = _detail(client, EL)["competition_summary"]
    assert (cs2["winning_score_min"]["reason"], cs2["winning_score_min"]["reason_code"]) == (
        "가점 당첨자 없음(미달)",
        "no_winner",
    )


# ====================================================================== D29-3 체크리스트 새 종류


def test_checklist_new_kinds_are_stored_and_listed(client: TestClient) -> None:
    with get_session() as s:
        s.add_all(
            [
                ChecklistItem(
                    complex_id=EL, kind="청약 접수", title="1순위 청약 접수(해당지역·기타지역)",
                    due_date="2026-10-20", status="open", note="자동: 청약홈 청약 일정 2026-10-20",
                ),
                ChecklistItem(
                    complex_id=EL, kind="당첨자 발표", title="당첨자 발표", due_date="2026-10-27",
                    status="open", note="자동: 청약홈 당첨자 발표일",
                ),
            ]
        )  # fmt: skip
    for headers in (WRITE, READ):
        items = _get(client, "/api/ops/checklist", "listChecklist", headers=headers, complex_id=EL)
        kinds = {(i["kind"], i["title"], i["due_date"]) for i in items}
        assert ("청약 접수", "1순위 청약 접수(해당지역·기타지역)", "2026-10-20") in kinds
        assert ("당첨자 발표", "당첨자 발표", "2026-10-27") in kinds


# ====================================================================== D29-2 병합된 중복 단지 행


def _top(client: TestClient, snap: int) -> list[int]:
    dash = _get(client, f"/api/snapshots/{snap}/dashboard", "getDashboard")
    return [int(t["complex_id"]) for t in dash["top5"]]


def test_merged_row_leaves_new_revision_but_published_view_is_unchanged(client: TestClient) -> None:
    before = {r["complex_id"] for r in _rows(client)}
    top = _top(client, SNAP)
    dup = next(c for c in top if c != EL)
    assert dup in before
    with get_session() as s:
        cx = s.get(Complex, dup)
        assert cx is not None
        cx.merged_into_id = EL
    # D11-1: 이미 발행된 리비전은 저장본 그대로
    assert {r["complex_id"] for r in _rows(client)} == before
    assert _top(client, SNAP) == top
    assert _detail(client, dup)["header"]["id"] == dup  # 옛 리비전 링크는 그대로 열린다
    # 새 리비전(실제 발행 경로)에서는 빠진다
    new = publish_revision(reason="R10 병합 뒤 리비전")
    rows = {r["complex_id"] for r in _rows(client, new)}
    assert dup not in rows and rows == before - {dup}
    assert dup not in _top(client, new)


def test_merged_row_leaves_live_list_and_market(client: TestClient) -> None:
    as_live()
    every = {r["complex_id"] for r in _rows(client)}
    dup = sorted(every - {EL})[0]
    with get_session() as s:
        cx = s.get(Complex, dup)
        assert cx is not None
        cx.merged_into_id = EL
    assert {r["complex_id"] for r in _rows(client)} == every - {dup}
    assert dup not in _top(client, SNAP)


def test_merge_event_summary() -> None:
    from app.api.change_text import change_summary, field_label

    new = "2025000397 두산위브 더센트럴 도화에 병합 — 같은 사업(공고 2025940268 공고문이 원 공고 2025000397 인용)"

    assert field_label("complex", "merged_into") == "같은 사업 단지 병합"
    assert change_summary("complex", "merged_into", None, new) == f"중복 단지 행 병합: {new}"
