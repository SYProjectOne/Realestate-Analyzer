"""WP8 판정 범위 정합(계약 2026-10-09.5).

공용 함수 위임 · 사다리 참여 규칙 · 상황 A '모집공고 대기' · 시드 중복.

DB 를 바꾸는 테스트는 같은 세션에서 flush 후 ``load_report`` 를 부르고 rollback 한다(세션 공용 DB 보존).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup, Tag
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis import price_view, scope
from app.models import Claim, ComplexType, IntakeStatus, Ladder, PaymentTerms
from app.reports import policy
from app.reports.charts import build_charts, c01_ladder
from app.reports.data import ReportData, load_report
from app.reports.diff import diff_snapshots
from app.reports.render import render_html

NOT_TARGET_P10 = Decimal("0.7700")  # 픽스처 어디에도 없는 값 — 표시되면 바로 보인다


@pytest.fixture
def scratch(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as s:
        try:
            yield s
        finally:
            s.rollback()


def _section(html: str, sid: str) -> Tag:
    sec = BeautifulSoup(html, "lxml").find("section", id=sid)
    assert isinstance(sec, Tag)
    return sec


def _row_text(sec: Tag, table_idx: int, name: str) -> str:
    for tr in sec.select("table")[table_idx].select("tbody tr"):
        tds = tr.find_all("td")
        if any(td.get_text(strip=True) == name for td in tds[:2]):
            return str(tr.get_text(" ", strip=True))
    raise AssertionError(f"{name} 행 없음")


# ---------------------------------------------------------------------------- 1. 공용 함수 위임


@pytest.mark.parametrize(
    ("cls", "decision", "has_price", "intake"),
    [
        ("범위 경계", "auto", True, "가능"),
        ("public_sale", "auto", True, "가능"),
        ("private_sale_apt", "review", True, "가능"),
        ("미분류", None, True, None),
        ("private_sale_apt", "auto", False, "가능"),
        ("private_sale_apt", "auto", True, "불가"),
        ("private_sale_apt", "auto", True, None),
        ("private_sale_apt", "auto", True, "미정"),
    ],
)
def test_policy_judge_scope_is_shared_function(
    cls: str, decision: str | None, has_price: bool, intake: str | None
) -> None:
    kw = {
        "inclusion_class": cls,
        "inclusion_decision": decision,
        "has_price": has_price,
        "intake_status": intake,
    }
    assert policy.judge_scope(**kw) == scope.judge_scope(**kw)  # type: ignore[arg-type]


def test_policy_current_price_is_shared_function(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        for cid in (1, 7, 15):
            types = list(s.scalars(select(ComplexType).where(ComplexType.complex_id == cid)))
            pays = list(s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == cid)))
            assert policy.current_price(types, pays) == price_view.current_price(types, pays)


def test_current_terms_order_matches_shared_function(scratch: Session) -> None:
    """같은 effective_from 이면 notice_no → id(공용 ``current_terms``).

    옛 보고서 순서(effective_from → id)와 다른 경우."""
    pays = list(
        scratch.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == 7).order_by(PaymentTerms.id))
    )
    if len(pays) < 2:
        first = pays[0]
        scratch.add(
            PaymentTerms(
                complex_id=7,
                notice_no="0000000000",
                notice_kind=first.notice_kind,
                effective_from=first.effective_from,
            )
        )
        scratch.flush()
        pays = list(
            scratch.scalars(
                select(PaymentTerms).where(PaymentTerms.complex_id == 7).order_by(PaymentTerms.id)
            )
        )
    day = "2026-09-01"
    for n, p in enumerate(pays):
        p.effective_from = day
        p.notice_no = f"9{len(pays) - n:09d}"  # id 가 작을수록 notice_no 가 크다
    scratch.flush()
    want = price_view.current_terms(pays)
    assert want is not None and want.id == pays[0].id
    data = load_report(scratch, 12)
    cur = data.complex_by_id[7].current_payment
    assert cur is not None and cur.notice_no == want.notice_no


def test_intake_shown_uses_shared_pick_intake(scratch: Session) -> None:
    """같은 날 '날짜만'(사람 입력)과 '시각 포함' 값 — 날짜만 비교하고 id 큰 행(공용 ``pick_intake``)."""
    rows = list(
        scratch.scalars(
            select(IntakeStatus).where(IntakeStatus.snapshot_id == 12, IntakeStatus.complex_id == 2)
        )
    )
    base = rows[0]
    a = IntakeStatus(
        complex_id=2,
        snapshot_id=12,
        status="불가",
        path="human_check",
        checked_at="2026-10-08T23:59:00+09:00",
    )
    b = IntakeStatus(complex_id=2, snapshot_id=12, status="미정", path="human_check", checked_at="2026-10-08")
    for r in (a, b):
        r.evidence_url = base.evidence_url
        scratch.add(r)
        scratch.flush()
    want = scope.pick_intake(
        scratch.scalars(
            select(IntakeStatus).where(IntakeStatus.snapshot_id == 12, IntakeStatus.complex_id == 2)
        )
    )
    assert want is not None and want.id == b.id
    cx = load_report(scratch, 12).complex_by_id[2]
    assert cx.intake_shown is not None and cx.intake_shown.status == "미정"
    assert sum(1 for i in cx.intake if i.used) == 1


# ---------------------------------------------------------------------------- 2. 사다리 참여 규칙


def _add_leftover_ladder(s: Session, complex_id: int) -> None:
    """'판정 대상'이 아닌 단지에 남은 사다리 행(이전 범위의 판정·이월)을 만든다."""
    seq = s.scalars(select(Ladder.judgment_seq).where(Ladder.judgment_seq.is_not(None))).first()
    for horizon in ("move_in_plus_1y", "asof_plus_3y"):
        s.add(
            Ladder(
                snapshot_id=12,
                complex_id=complex_id,
                horizon=horizon,
                target_ym="2030-01",
                months_from_asof=40,
                p5=NOT_TARGET_P10,
                p10=NOT_TARGET_P10,
                p20=NOT_TARGET_P10,
                p_flat=NOT_TARGET_P10,
                verdicts={"p10": "likely"},
                annualized={},
                status="ok",
                judgment_seq=seq,
                proposition_text="남은 사다리 명제",
            )
        )
    s.flush()


@pytest.fixture
def leftover(scratch: Session) -> tuple[ReportData, str]:
    # 13 = 참고(접수 확인 불가), 15 = 보류(분양가 미공개). 4 = 미해결(devseed 에 남은 사다리 행이 이미 있다)
    for cid in (13, 15):
        _add_leftover_ladder(scratch, cid)
    have4 = scratch.scalar(
        select(func.count()).select_from(Ladder).where(Ladder.snapshot_id == 12, Ladder.complex_id == 4)
    )
    assert have4, "픽스처 전제: 미해결 단지 4에 남은 사다리 행"
    data = load_report(scratch, 12)
    return data, render_html(data).html


def test_scopes_of_leftover_complexes(leftover: tuple[ReportData, str]) -> None:
    data, _ = leftover
    by = data.complex_by_id
    assert (by[13].judge_scope, by[15].judge_scope, by[4].judge_scope) == ("참고", "보류", "미해결")
    for cid in (4, 13, 15):
        assert by[cid].scope_note.startswith(f"판정 범위: {by[cid].judge_scope_text}"), by[cid].scope_note
        assert by[cid].scope_reason


def test_leftover_ladders_not_in_report_data(leftover: tuple[ReportData, str]) -> None:
    data, _ = leftover
    shown = {lad.complex_id for lad in data.ladders} | set(data.ladder_other)
    assert not shown & {4, 13, 15}
    for lad in data.ladders:
        assert data.complex_by_id[lad.complex_id].judge_scope == "판정 대상"
    assert all(lad.p10.v != float(NOT_TARGET_P10) for lad in data.ladders)


def test_leftover_ladders_not_counted_in_appendix(leftover: tuple[ReportData, str]) -> None:
    data, _ = leftover
    names = {data.complex_by_id[c].name for c in (4, 13, 15)}
    for call in data.calls:
        for n in names:
            assert f"§6 사다리({n})" not in call.used_in, call


def test_c01_shows_scope_instead_of_probability(leftover: tuple[ReportData, str]) -> None:
    data, _ = leftover
    assert 4 in {s.complex_id for s in data.top5}, "픽스처 전제: 미해결 단지 4가 TOP 5(점수 행)"
    spec = c01_ladder(data)
    assert spec is not None
    name4 = data.complex_by_id[4].name
    series = [x for x in spec.option["series"] if x["name"].startswith(name4)]
    assert len(series) == 1
    assert all(item["value"] is None for item in series[0]["data"])
    assert all(item["label"]["formatter"].startswith("판정 범위: ") for item in series[0]["data"])
    row = next(r for r in spec.rows if r[0] == name4)
    assert any(isinstance(x, str) and x.startswith("판정 범위: 미해결") for x in row), row
    for x in spec.option["series"]:
        for item in x["data"]:
            assert item["value"] != float(NOT_TARGET_P10)


def test_section6_ladder_table_shows_scope(leftover: tuple[ReportData, str]) -> None:
    data, html = leftover
    sec = _section(html, "s6")
    for cid in (4, 13, 15):
        cx = data.complex_by_id[cid]
        text = _row_text(sec, 0, cx.name)
        assert "판정 범위:" in text and cx.judge_scope_text in text, text
        assert "0.77" not in text and "0.33" not in text, text
    assert "0.77" not in sec.select("table")[0].get_text(" ", strip=True)


def test_section7_and_8_show_scope_not_probability(leftover: tuple[ReportData, str]) -> None:
    data, html = leftover
    cx = data.complex_by_id[4]
    s8 = _section(html, "s8")
    text = _row_text(s8, 0, cx.name)  # 8-1 TOP 5 비교표
    assert "판정 범위: 미해결(분류 판정 미해결)" in text, text
    assert "0.33" not in text, text
    s7 = _section(html, "s7")
    assert "판정 범위: 미해결(분류 판정 미해결)" in s7.get_text(" ", strip=True)
    assert "남은 사다리 명제" not in html  # 남은 행의 명제 문장(§7)도 쓰지 않는다


def test_target_complexes_still_show_ladder(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        data = load_report(s, 12)
    target = [c.id for c in data.complexes if c.judge_scope == "판정 대상"]
    assert target and {lad.complex_id for lad in data.ladders} == set(target)


# ---------------------------------------------------------------------------- 3. 상황 A '모집공고 대기'


@pytest.mark.parametrize("sid", [11, 12])
def test_wait_new_in_scenario_a_decisions(factory: sessionmaker[Session], sid: int) -> None:
    with factory() as s:
        data = load_report(s, sid)
    block = next(b for b in data.scenarios if b.code == "A")
    wait = [d for d in block.decisions if d.virtual]
    assert len(wait) == 1 and wait[0].option == "모집공고 대기" and wait[0].complex_id is None
    assert wait[0].chosen and isinstance(wait[0].prob.v, float)
    assert block.picked == ["모집공고 대기"]


def test_wait_new_in_c07_for_scenario_a(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        data = load_report(s, 12)
    charts = {c.id: c for c in build_charts(data)}
    assert "c07" in charts  # 기본 시나리오(보고서 시나리오) 그대로
    spec = charts["c07_A"]
    labels = spec.option["yAxis"]["data"]
    assert "모집공고 대기" in labels
    item = spec.option["series"][0]["data"][labels.index("모집공고 대기")]
    assert "가상 후보" in item["label"]["formatter"] and item["value"] == 0.94
    row = next(r for r in spec.rows if r[0] == "모집공고 대기")
    assert "가상 후보" in row and "선택" in row


def test_wait_new_in_section8_summary_and_table(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        data = load_report(s, 12)
    sec = _section(render_html(data).html, "s8")
    summary = sec.select_one("table.scenario-summary")
    assert summary is not None
    rows = {
        tr.td.get_text(strip=True): tr.get_text(" ", strip=True)
        for tr in summary.select("tbody tr")
        if tr.td is not None
    }
    a = next(v for k, v in rows.items() if k.startswith("A"))
    assert "모집공고 대기" in a and "가상 후보" in a and "0.94" in a, a
    assert len(rows) == len(data.scenarios)
    assert sec.select_one("#chart-c07_A") is not None or "c07_A" in str(sec)
    # 상황 A 결정 표: 가상 후보 배지
    tables = sec.select("table")
    assert any("모집공고 대기" in t.get_text() and "가상 후보" in t.get_text() for t in tables[2:])


def test_diff_ladder_uses_scope_for_non_target(factory: sessionmaker[Session]) -> None:
    """§12 diff 표도 같은 참여 규칙 — 미해결 단지 4의 남은 사다리 행은 확률 대신 판정 범위."""
    with factory() as s:
        d = diff_snapshots(s, 11, 12)
    rows = [r for r in d.rows if r.table == "ladder" and r.complex_id == 4]
    assert rows and all("0.33" not in r.new for r in rows), rows
    assert rows[0].new == "판정 범위: 미해결(분류 판정 미해결)"


# ---------------------------------------------------------------------------- 4. 시드 중복 정리


def test_seed_has_no_duplicate_rows(factory: sessionmaker[Session]) -> None:
    """devseed 가 스냅샷 11 점수·접수·claim 을 이미 넣는다 — 보고서 시드가 같은 행을 또 넣지 않는다."""
    with factory() as s:
        intake = Counter(
            (r.snapshot_id, r.complex_id, r.path, r.checked_at, r.status)
            for r in s.scalars(select(IntakeStatus))
        )
        assert max(intake.values()) == 1, [k for k, n in intake.items() if n > 1][:3]
        claims = Counter(
            (c.snapshot_id, c.judgment_seq, c.ordinal, c.text, c.parent_claim_id)
            for c in s.scalars(select(Claim))
        )
        assert max(claims.values()) == 1, [k for k, n in claims.items() if n > 1][:3]
