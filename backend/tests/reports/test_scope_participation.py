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
from app.models import (
    Benchmark,
    Claim,
    Complex,
    ComplexType,
    FieldProvenance,
    IntakeStatus,
    JudgmentLog,
    Ladder,
    PaymentTerms,
    Region,
    ScoreRun,
    ScoreTotal,
)
from app.normalize.benchmark import SUBSTITUTE_NOTE
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
        if any(td.get_text(strip=True).removesuffix("재판정 필요") == name for td in tds[:2]):
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
            assert policy.current_price(types, pays, discount_label=None) == price_view.current_price(
                types, pays, discount_label=None
            )


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


def _set_stored_scope(s: Session, snapshot_id: int, complex_id: int, value: str) -> None:
    """그 스냅샷 점수 실행 전부의 저장 범위(score_total.judge_scope)를 바꾼다(D10-1 표시 기준)."""
    runs = select(ScoreRun.id).where(ScoreRun.snapshot_id == snapshot_id)
    rows = list(
        s.scalars(
            select(ScoreTotal).where(ScoreTotal.score_run_id.in_(runs), ScoreTotal.complex_id == complex_id)
        )
    )
    assert rows
    for r in rows:
        r.judge_scope = value
    s.flush()


@pytest.fixture
def leftover(scratch: Session) -> tuple[ReportData, str]:
    # 13 = 저장 '참고', 15 = 저장 '보류' — 남은 사다리 행을 만든다.
    # 4 = TOP 5(4위)·남은 사다리 행 있음 — 저장 범위를 '참고'로 바꿔 TOP 5 안의 비대상 단지를 만든다.
    for cid in (13, 15):
        _add_leftover_ladder(scratch, cid)
    have4 = scratch.scalar(
        select(func.count()).select_from(Ladder).where(Ladder.snapshot_id == 12, Ladder.complex_id == 4)
    )
    assert have4, "픽스처 전제: 단지 4에 사다리 행"
    _set_stored_scope(scratch, 12, 4, "참고")
    data = load_report(scratch, 12)
    return data, render_html(data).html


def test_scopes_of_leftover_complexes(leftover: tuple[ReportData, str]) -> None:
    data, _ = leftover
    by = data.complex_by_id
    assert (by[13].judge_scope, by[15].judge_scope, by[4].judge_scope) == ("참고", "보류", "참고")
    assert {by[c].scope_source for c in (4, 13, 15)} == {"스냅샷 저장값"}
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
    assert 4 in {s.complex_id for s in data.top5}, "픽스처 전제: 단지 4가 TOP 5(점수 행)"
    spec = c01_ladder(data)
    assert spec is not None
    name4 = data.complex_by_id[4].name
    series = [x for x in spec.option["series"] if x["name"].startswith(name4)]
    assert len(series) == 1
    assert all(item["value"] is None for item in series[0]["data"])
    assert all(item["label"]["formatter"].startswith("판정 범위: ") for item in series[0]["data"])
    row = next(r for r in spec.rows if r[0] == name4)
    assert any(isinstance(x, str) and x.startswith("판정 범위: 참고 후보(순위만)") for x in row), row
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
    assert "판정 범위: 참고 후보(순위만)" in text, text
    assert "0.33" not in text, text
    s7 = _section(html, "s7")
    assert "판정 범위: 참고 후보(순위만)" in s7.get_text(" ", strip=True)
    assert "남은 사다리 명제" not in html  # 남은 행의 명제 문장(§7)도 쓰지 않는다


def test_target_complexes_still_show_ladder(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        data = load_report(s, 12)
    target = [c.id for c in data.complexes if c.judge_scope == "판정 대상"]
    assert target and {lad.complex_id for lad in data.ladders} == set(target)


# ---------------------------------------------------------------------------- D10-1 저장값 기준


def test_d10_1_report_uses_stored_scope_with_rejudge_badge(factory: sessionmaker[Session]) -> None:
    """단지 4: 저장값 '판정 대상'(rank 4) · 현재 사실 '미해결' — 저장값을 보이고 '재판정 필요' 배지만."""
    with factory() as s:
        data = load_report(s, 12)
    cx = data.complex_by_id[4]
    assert (cx.judge_scope, cx.scope_source, cx.current_scope) == ("판정 대상", "스냅샷 저장값", "미해결")
    assert cx.rejudge_needed and "미해결(분류 판정 미해결)" in cx.rejudge_text
    assert 4 in {lad.complex_id for lad in data.ladders}  # 저장 범위 = 판정 대상 → 저장된 사다리
    assert next(v for v in data.scores if v.complex_id == 4).rank == 4
    same = data.complex_by_id[1]
    assert not same.rejudge_needed and same.scope_reason == same.current_reason
    html = render_html(data).html
    s3 = _section(html, "s3")
    assert "재판정 필요 — 현재 사실로는 미해결(분류 판정 미해결)" in _row_text(s3, 0, cx.name)
    for sid in ("s6", "s7", "s8"):
        assert "재판정 필요" in _section(html, sid).get_text(" ", strip=True), sid


def test_d10_1_changed_facts_do_not_change_snapshot_scope(scratch: Session) -> None:
    """현재 사실이 바뀌어도(classify review) 스냅샷 범위·순위·사다리는 저장값 그대로 + 배지."""
    before = load_report(scratch, 12)
    cx = scratch.get(Complex, 2)
    assert cx is not None
    cx.inclusion_decision = "review"
    scratch.flush()
    after = load_report(scratch, 12)
    c2 = after.complex_by_id[2]
    assert c2.judge_scope == "판정 대상" and c2.current_scope == "미해결" and c2.rejudge_needed
    rank = {v.complex_id: v.rank for v in before.scores}
    assert {v.complex_id: v.rank for v in after.scores} == rank
    assert 2 in {lad.complex_id for lad in after.ladders}


def test_d10_1_no_stored_row_uses_current_facts(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        data = load_report(s, 11)
    stored = {v.complex_id for v in data.scores}
    for cx in data.complexes:
        if cx.id not in stored:
            assert cx.scope_source == "현재 사실" and not cx.rejudge_needed


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


def test_diff_ladder_uses_scope_for_non_target(scratch: Session) -> None:
    """§12 diff 표도 같은 참여 규칙(저장 범위 기준) — 비대상 단지의 남은 사다리 행은 확률 대신 판정 범위."""
    base = [r for r in diff_snapshots(scratch, 11, 12).rows if r.table == "ladder" and r.complex_id == 4]
    assert base and base[0].new == "0.33"  # 저장 범위 '판정 대상' → 저장된 사다리
    _set_stored_scope(scratch, 12, 4, "참고")
    rows = [r for r in diff_snapshots(scratch, 11, 12).rows if r.table == "ladder" and r.complex_id == 4]
    assert rows and all("0.33" not in r.new for r in rows), rows
    assert rows[0].new == "판정 범위: 참고 후보(순위만)"


def test_wait_new_evidence_not_recorded(factory: sessionmaker[Session]) -> None:
    """녹화 decide 입력에 [wait_new] 블록이 없으면 '근거 블록 기록 없음'(지어내지 않는다)."""
    with factory() as s:
        data = load_report(s, 12)
    block = next(b for b in data.scenarios if b.code == "A")
    assert block.has_wait_new and block.wait_new_evidence is None
    sec = _section(render_html(data).html, "s8")
    assert "근거 블록 기록 없음" in sec.get_text(" ", strip=True)


def test_wait_new_evidence_shown_from_decide_input(scratch: Session) -> None:
    block = next(b for b in load_report(scratch, 12).scenarios if b.code == "A")
    assert block.judgment_seq is not None
    log = scratch.get(JudgmentLog, block.judgment_seq)
    assert log is not None
    evidence = (
        "[complex_1] 단지 카드\n요건 사전 계산: …\n\n"
        "[wait_new] 모집공고 대기 — 12개월 내 공고 예정 단지를 기다림\n"
        "지역 (A) 트랙 공고 예정 1곳(기준일 2026-10-08, 12개월 내 공고 예정 단지):\n"
        "- 시험 예정 단지(모집공고일 미정(공고 전); 분양가 미공개; 판정 범위 보류 — 공고 후 재판정)"
    )
    log.input_json = {**(log.input_json or {}), "evidence": evidence}
    scratch.flush()
    data = load_report(scratch, 12)
    block = next(b for b in data.scenarios if b.code == "A")
    assert block.wait_new_evidence is not None and "시험 예정 단지" in block.wait_new_evidence
    assert "단지 카드" not in block.wait_new_evidence
    sec = _section(render_html(data).html, "s8")
    pre = sec.select_one(".wait-new-evidence pre")
    assert pre is not None and "시험 예정 단지" in pre.get_text()


# ---------------------------------------------------------------------------- N-M3·N-M4 벤치마크


def test_benchmark_areas_cover_every_living_area(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        data = load_report(s, 12)
        region = s.get(Region, 1)
        assert region is not None
        names = {str(la.get("name")) for la in region.living_areas or []}
    assert names <= {a.living_area_name for a in data.benchmark_areas}
    html = render_html(data).html
    assert "확인 불가(수집 전)" not in html
    for a in data.benchmark_areas:
        assert (a.empty_reason is None) == bool(a.rows)
        if a.empty_reason:
            assert a.empty_reason.startswith("벤치마크 없음(")


def _bench_with_rows(s: Session) -> tuple[str, list[Benchmark]]:
    by: dict[str, list[Benchmark]] = {}
    for b in s.scalars(select(Benchmark).where(Benchmark.region_id == 1).order_by(Benchmark.id)):
        by.setdefault(b.living_area or "", []).append(b)
    la = next(k for k, v in by.items() if k and any(not b.is_presale for b in v))
    return la, by[la]


def test_benchmark_empty_area_shows_reason(scratch: Session) -> None:
    la, rows = _bench_with_rows(scratch)
    for b in rows:
        scratch.delete(b)
    scratch.flush()
    data = load_report(scratch, 12)
    region = scratch.get(Region, 1)
    assert region is not None
    name = next((str(x["name"]) for x in region.living_areas or [] if str(x.get("id")) == la), la)
    area = next(a for a in data.benchmark_areas if a.living_area_name == name)
    assert not area.rows and area.empty_reason and area.empty_reason.startswith("벤치마크 없음(")
    sec = _section(render_html(data).html, "s5")
    assert area.empty_reason in sec.get_text(" ", strip=True)


def test_benchmark_substitute_rows_marked_and_not_double_counted(scratch: Session) -> None:
    """지역 전체 대체 행(다른 생활권 표본 복사)은 '대체' 표기 + 지역 집계에 다시 세지 않는다(N-M4)."""
    la_src, rows = _bench_with_rows(scratch)
    target_la = next(
        str(la.get("id"))
        for la in (scratch.get(Region, 1).living_areas or [])  # type: ignore[union-attr]
        if str(la.get("id")) != la_src
    )
    for b in scratch.scalars(select(Benchmark).where(Benchmark.living_area == target_la)):
        scratch.delete(b)
    scratch.flush()
    before = load_report(scratch, 12)
    n_before = len([b for b in before.benchmarks if not b.substitute])
    src = next(b for b in rows if not b.is_presale)
    copy = Benchmark(
        region_id=1,
        living_area=target_la,
        name=src.name,
        completed_year=src.completed_year,
        sale_year=src.sale_year,
        sale_price_84_won=src.sale_price_84_won,
        trade_median_won=src.trade_median_won,
        is_presale=False,
        substitute=True,  # 계약 2026-10-09.7 — 판별은 컬럼
        note=f"[bm:test:{target_la}] {SUBSTITUTE_NOTE} — 생활권 {target_la} 자체 표본 0, 원 생활권 {la_src}",
    )
    scratch.add(copy)
    scratch.flush()
    for fld, v in (("sale_price_84_won", src.sale_price_84_won), ("trade_median_won", src.trade_median_won)):
        if v is not None:
            scratch.add(
                FieldProvenance(
                    entity="benchmark", entity_id=copy.id, field=fld, value_text=str(v),
                    url="https://www.applyhome.co.kr/test", checked_at="2026-10-08", label="추정",
                    reason="대체: 지역 전체", source_rank=1, chosen=True,
                )
            )  # fmt: skip
    scratch.flush()
    data = load_report(scratch, 12)
    assert len([b for b in data.benchmarks if not b.substitute]) == n_before
    tname = next(a.living_area_name for a in data.benchmark_areas if any(r.substitute for r in a.rows))
    area = next(a for a in data.benchmark_areas if a.living_area_name == tname)
    assert (area.own_n, area.substitute_n) == (0, 1) and area.empty_reason is None
    assert tname not in data.recent_sale_cases  # 대체 행은 이 생활권 사례로 세지 않는다
    sec = _section(render_html(data).html, "s5")
    text = sec.get_text(" ", strip=True)
    assert f"생활권별 벤치마크 {n_before}건(+ 지역 전체 대체 1행, 중복 집계 안 함)" in text
    assert "자체 표본 0 — 지역 전체 대체(추정) 1행" in text and "대체(지역 전체, 추정)" in text


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
