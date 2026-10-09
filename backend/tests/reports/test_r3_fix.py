"""R3 수정 F4 — 리뷰 항목별 테스트(M14 · minor 7 · minor 26 · minor 39 · C2 · M3).

DB 를 바꾸는 테스트는 같은 세션에서 flush 후 ``load_report`` 를 부르고 rollback 한다(세션 공용 DB 보존).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup, Tag
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings, set_settings
from app.models import Complex, FieldProvenance, JudgmentLog, PaymentTerms, Snapshot
from app.reports.charts import c01_ladder, c06_score_breakdown, c07_decision
from app.reports.data import _thresholds, load_report
from app.reports.errors import ReportProvenanceMissing
from app.reports.export import generate
from app.reports.policy import JUDGE_SCOPE_TEXT, judge_scope

from ._seed import SeedInfo

# ---------------------------------------------------------------------------- 공용


def _prov(session: Session, entity: str, entity_id: int, fld: str, value: str, label: str = "확인됨") -> int:
    row = FieldProvenance(
        entity=entity,
        entity_id=entity_id,
        field=fld,
        value_text=value,
        url="https://www.applyhome.co.kr/test",
        checked_at="2026-10-07",
        label=label,
        source_rank=1,
        chosen=True,
    )
    session.add(row)
    session.flush()
    return row.id


@pytest.fixture
def scratch(factory: sessionmaker[Session]) -> Iterator[Session]:
    """바꿔 보고 되돌리는 세션."""
    with factory() as s:
        try:
            yield s
        finally:
            s.rollback()


# ---------------------------------------------------------------------------- M14 캘린더 날짜


def test_m14_calendar_reads_plain_interim_schedule_from_devseed(factory: sessionmaker[Session]) -> None:
    """devseed 는 interim_schedule.due_date 를 문자열로 저장한다 — 3개월 안 중도금이 캘린더에 나와야 한다."""
    with factory() as s:
        data = load_report(s, 12)
    got = {(r.complex_name, r.day) for r in data.calendar if r.what.startswith("중도금")}
    names = {c.id: c.name for c in data.complexes}
    want = {
        (names[3], "2026-10-30"),
        (names[3], "2026-12-18"),
        (names[8], "2026-11-13"),
        (names[8], "2026-12-13"),
        (names[10], "2026-10-15"),
    }
    assert want <= got, want - got
    assert (names[10], "2027-04-15") not in got  # 3개월 밖
    for r in data.calendar:
        if r.fact is not None:
            assert r.fact.label != "확인 불가" and str(r.fact.prov).startswith("fp_"), r


def test_m14_calendar_reads_normalizer_shapes(scratch: Session) -> None:
    """정규화기 저장 형태: apply_dates [{kind,date}], contract_dates [{from,to}], interim [{seq,due_date}]."""
    cx = scratch.get(Complex, 2)
    assert cx is not None
    cx.apply_dates = [{"kind": "특별공급", "date": "2026-10-20"}, {"kind": "1순위", "date": "2026-10-21"}]
    cx.contract_dates = [{"from": "2026-11-02", "to": "2026-11-04"}]
    fp_apply = _prov(scratch, "complex", 2, "apply_dates", "특별공급 2026-10-20; 1순위 2026-10-21")
    fp_contract = _prov(scratch, "complex", 2, "contract_dates", "2026-11-02 ~ 2026-11-04")
    pay = scratch.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == 2)).first()
    assert pay is not None
    pay.interim_schedule = [
        {"seq": 1, "due_date": "2026-12-01", "pct": 10.0},
        {"seq": 2, "due_date": "2027-03-01", "pct": 10.0},  # 3개월 밖
    ]
    scratch.execute(
        delete(FieldProvenance).where(
            FieldProvenance.entity == "payment_terms",
            FieldProvenance.entity_id == pay.id,
            FieldProvenance.field == "interim_schedule",
        )
    )
    fp_interim = _prov(scratch, "payment_terms", pay.id, "interim_schedule", "1차 2026-12-01")
    scratch.flush()
    data = load_report(scratch, 12)
    rows = {(r.day, r.what): r for r in data.calendar if r.complex_name == cx.name}
    assert set(rows) == {
        ("2026-10-20", "청약 특별공급"),
        ("2026-10-21", "청약 1순위"),
        ("2026-11-02", "계약 시작"),
        ("2026-11-04", "계약 종료"),
        ("2026-12-01", "중도금 1회차"),
    }, set(rows)
    provs = {r.what: r.fact.prov for r in rows.values() if r.fact is not None}
    assert provs["청약 1순위"] == f"fp_{fp_apply}"
    assert provs["계약 종료"] == f"fp_{fp_contract}"
    assert provs["중도금 1회차"] == f"fp_{fp_interim}"


def test_m14_calendar_still_reads_embedded_fact_shape(scratch: Session) -> None:
    cx = scratch.get(Complex, 2)
    assert cx is not None
    fact = {"v": "2026-10-25", "label": "확인됨", "prov": "fp_9", "checked_at": "2026-10-07", "unit": "date"}
    cx.apply_dates = [{"kind": "본청약", "start": fact, "end": None}]
    scratch.flush()
    data = load_report(scratch, 12)
    assert any(r.day == "2026-10-25" and r.what == "본청약" for r in data.calendar)


def test_m14_calendar_rendered_in_section8(factory: sessionmaker[Session], out_dir: Path) -> None:
    with factory() as s:
        rep = generate(s, 12, "html", out_dir=out_dir)
    soup = BeautifulSoup(rep.path.read_text(encoding="utf-8"), "lxml")
    sec = soup.find("section", id="s8")
    assert isinstance(sec, Tag)
    text = sec.get_text(" ", strip=True)
    assert "2026-10-30" in text and "중도금 1회차" in text
    assert "3개월 안 일정 없음" not in text


# ---------------------------------------------------------------------------- minor 7 부록 A 임계값


def _expected_thresholds(s: Session, region_id: int, asof: str) -> dict[str, dict[str, list[Any]]]:
    snaps = select(Snapshot.id).where(Snapshot.region_id == region_id, Snapshot.asof_date <= asof)
    out: dict[str, dict[str, list[Any]]] = defaultdict(dict)
    for j in s.scalars(
        select(JudgmentLog).where(JudgmentLog.snapshot_id.in_(snaps)).order_by(JudgmentLog.seq)
    ):
        for k, v in _thresholds(j.output_json).items():
            vals = out[j.tool].setdefault(k, [])
            if v not in vals:
                vals.append(v)
    return out


def _s10_tool_cells(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "lxml")
    sec = soup.find("section", id="s10")
    assert isinstance(sec, Tag)
    table = sec.find("table")
    assert isinstance(table, Tag)
    out: dict[str, str] = {}
    for tr in table.select("tbody tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(tds) == 4:
            out[tds[0].removeprefix("jev_")] = tds[3]
    return out


def test_minor7_appendix_a_thresholds_per_tool(factory: sessionmaker[Session], out_dir: Path) -> None:
    with factory() as s:
        snap = s.get(Snapshot, 12)
        assert snap is not None
        want = _expected_thresholds(s, snap.region_id, snap.asof_date)
        rep = generate(s, 12, "html", out_dir=out_dir)
    cells = _s10_tool_cells(rep.path.read_text(encoding="utf-8"))
    # 녹화 응답에 임계값이 있는 도구 5개(audit·classify·extract·screen·verify)
    assert {"audit", "classify", "extract", "screen", "verify"} <= set(want)
    for tool, cell in cells.items():
        if tool in want:
            for k, vals in want[tool].items():
                assert f"{k} {' / '.join(str(v) for v in vals)}" in cell, (tool, cell)
        else:
            assert cell == "응답에 임계값 없음", (tool, cell)
    assert cells["screen"] == "block 0.75, review 0.25"
    assert cells["audit"] == "wrong_at 0.7"


def test_minor7_threshold_change_shows_both_values(scratch: Session) -> None:
    """JEV 업데이트로 임계값이 바뀌면(D6) 누계 부록에 두 값을 모두 적는다."""
    top = max(scratch.scalars(select(JudgmentLog.seq)))
    scratch.add(
        JudgmentLog(
            seq=top + 1,
            snapshot_id=12,
            tool="classify",
            purpose="classify:test",
            complex_id=None,
            input_hash="t" * 64,
            input_len=1,
            input_json={},
            output_json={"result": {"thresholds": {"auto_accept": 0.9}}},
            result_json={},
            status="ok",
            created_at="2026-10-08",
            adapter_version="jev-test",
        )
    )
    scratch.flush()
    data = load_report(scratch, 12)
    row = next(t for t in data.judge_tools if t.tool == "classify")
    assert "auto_accept 0.85 / 0.9" in row.thresholds, row.thresholds


# ---------------------------------------------------------------------------- minor 26 C1·C7 라벨


_PROB_LABEL = re.compile(r"^(0|1)\.\d{2} 추정( · \S+)?$")


def test_minor26_c01_labels_are_rounded_and_labelled(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        data = load_report(s, 12)
    spec = c01_ladder(data)
    assert spec is not None
    n = 0
    for series in spec.option["series"]:
        for item in series["data"]:
            assert isinstance(item, dict), item
            fmt = item["label"]["formatter"]
            if item["value"] is None:
                continue
            n += 1
            assert _PROB_LABEL.match(fmt), fmt
            assert round(item["value"], 2) == item["value"]
    assert n > 0


def test_minor26_c01_unresolved_label(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        data = load_report(s, 12)
    top = {v.complex_id for v in data.top5}
    lad = next(lad for lad in data.ladders if lad.complex_id in top)
    lad.status = "review"
    spec = c01_ladder(data)
    assert spec is not None
    series = next(x for x in spec.option["series"] if x["name"].startswith(lad.name))
    assert all(item["label"]["formatter"] == "미해결" for item in series["data"])


def test_minor26_c07_labels_are_rounded_and_labelled(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        data = load_report(s, 12)
    spec = c07_decision(data)
    assert spec is not None
    items = spec.option["series"][0]["data"]
    assert items
    for item in items:
        assert _PROB_LABEL.match(item["label"]["formatter"]), item
        assert round(item["value"], 2) == item["value"]


def test_minor26_c06_unjudged_bar_has_zero_length(factory: sessionmaker[Session]) -> None:
    """미판정 성분은 막대 길이 0(+ '미판정' 라벨) — w×10 으로 스택을 부풀리지 않는다."""
    with factory() as s:
        data = load_report(s, 12)
    row = next(v for v in data.scores if v.rank is not None)
    comp = next(iter(row.components.values()))
    comp.contribution = None
    spec = c06_score_breakdown(data)
    assert spec is not None
    series = next(x for x in spec.option["series"] if x["id"] == comp.key)
    idx = [v.complex_id for v in data.scores if v.rank is not None].index(row.complex_id)
    item = series["data"][idx]
    assert item["value"] == 0 and item["label"]["formatter"] == "미판정"


# ---------------------------------------------------------------------------- minor 39 출처 누락


def _drop_units_total_prov(s: Session) -> None:
    s.execute(
        delete(FieldProvenance).where(
            FieldProvenance.entity == "complex",
            FieldProvenance.entity_id == 1,
            FieldProvenance.field == "units_total",
        )
    )
    s.flush()


def test_minor39_missing_provenance_raises_in_dev(scratch: Session, report_settings: Settings) -> None:
    assert report_settings.env == "dev"
    _drop_units_total_prov(scratch)
    with pytest.raises(ReportProvenanceMissing) as exc:
        load_report(scratch, 12)
    assert "complex 1" in str(exc.value) and "units_total" in str(exc.value)


def test_minor39_missing_provenance_warns_in_prod(
    scratch: Session,
    report_env: tuple[Settings, Engine, SeedInfo],
    caplog: pytest.LogCaptureFixture,
) -> None:
    prod = report_env[0].model_copy(update={"env": "prod"})
    set_settings(prod)
    try:
        _drop_units_total_prov(scratch)
        with caplog.at_level(logging.WARNING, logger="app.reports.data"):
            data = load_report(scratch, 12)
    finally:
        set_settings(report_env[0])
    f = data.complex_by_id[1].facts["units_total"]
    assert f.label == "확인 불가" and f.reason == "출처 누락" and f.v is None
    assert any("출처 누락" in r.getMessage() and "units_total" in r.getMessage() for r in caplog.records)


def test_minor39_fixture_report_has_no_missing_provenance(factory: sessionmaker[Session]) -> None:
    """dev 규칙이 켜져도 픽스처 두 스냅샷은 생성된다(값이 있는데 출처 행 없는 수치 0)."""
    with factory() as s:
        for sid in (11, 12):
            load_report(s, sid)


# ---------------------------------------------------------------------------- C2 판정 범위(D9-1)


@pytest.mark.parametrize(
    ("cls", "decision", "has_price", "intake", "want"),
    [
        ("public_rental", "auto", True, "가능", "제외"),
        ("non_apartment", "auto", True, "가능", "제외"),
        ("범위 경계", None, True, "가능", "제외"),
        ("미분류", None, True, "가능", "미해결"),
        ("manual_review", "manual_review", True, "가능", "미해결"),
        ("private_sale_apt", "review", True, "가능", "미해결"),
        ("public_sale", "review", True, "가능", "미해결"),
        ("private_sale_apt", "auto", False, "가능", "보류"),
        ("private_sale_apt", "auto", True, "확인 불가", "참고"),
        ("private_sale_apt", "auto", True, "불가", "참고"),
        ("private_sale_apt", "auto", True, None, "참고"),
        ("private_sale_apt", "auto", True, "가능", "판정 대상"),
        ("private_sale_apt", "auto", True, "미정", "판정 대상"),
    ],
)
def test_c2_judge_scope_rule(
    cls: str, decision: str | None, has_price: bool, intake: str | None, want: str
) -> None:
    assert (
        judge_scope(
            inclusion_class=cls, inclusion_decision=decision, has_price=has_price, intake_status=intake
        )
        == want
    )


def test_c2_scope_texts_follow_d9_1() -> None:
    assert JUDGE_SCOPE_TEXT["보류"] == "보류 — 공고 후 재판정"
    assert JUDGE_SCOPE_TEXT["미해결"] == "미해결(분류 판정 미해결)"
    assert JUDGE_SCOPE_TEXT["참고"] == "참고 후보(순위만)"


def test_c2_report_scope_per_complex(factory: sessionmaker[Session], out_dir: Path) -> None:
    with factory() as s:
        data = load_report(s, 12)
        rep = generate(s, 12, "html", out_dir=out_dir)
    by = data.complex_by_id
    assert by[2].judge_scope == "판정 대상"  # auto · 가능
    assert by[6].judge_scope == "판정 대상"  # auto · 미정
    assert by[4].judge_scope == "미해결"  # classify review
    assert by[14].judge_scope == "미해결"
    assert by[12].judge_scope == "참고"  # 공식 팝업 '불가'
    assert by[13].judge_scope == "참고"  # 공식 팝업 '확인 불가'(비공식 미정은 표시에 안 씀)
    assert by[15].judge_scope == "참고"  # 비공식만 — 표시 접수 상태 없음
    unresolved = {r.complex_id for r in data.classify_rows if r.unresolved}
    assert {4, 14, 16} <= unresolved
    soup = BeautifulSoup(rep.path.read_text(encoding="utf-8"), "lxml")
    sec = soup.find("section", id="s3")
    assert isinstance(sec, Tag)
    rows = {
        tr.find("td").get_text(strip=True): tr.get_text(" ", strip=True)
        for tr in sec.select("table")[0].select("tbody tr")
    }
    assert "미해결(분류 판정 미해결)" in rows[by[4].name]
    assert "참고 후보(순위만)" in rows[by[12].name]
    assert "판정 대상" in rows[by[2].name]


# ---------------------------------------------------------------------------- M3 현재 구매가(§6-1)


def test_m3_current_price_prefers_latest_price_by_type(scratch: Session) -> None:
    base = load_report(scratch, 12).complex_by_id[7]
    assert base.basis is not None
    code = base.basis.type_code
    pays = list(scratch.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == 7)))
    latest = max(pays, key=lambda p: (p.effective_from or "", p.id))
    latest.price_by_type = {code: {"max_price_won": 777_000_000, "floor_sample_price_won": 700_000_000}}
    fp_max = _prov(scratch, "payment_terms", latest.id, f"price_by_type.{code}.max_price_won", "777000000")
    fp_floor = _prov(
        scratch, "payment_terms", latest.id, f"price_by_type.{code}.floor_sample_price_won", "700000000"
    )
    scratch.flush()
    cx = load_report(scratch, 12).complex_by_id[7]
    extra = sum(
        int(f.v) for f in (cx.basis.balcony, cx.basis.options) if cx.basis and isinstance(f.v, (int, float))
    )
    assert cx.price_high.v == 777_000_000 + extra
    assert cx.price_low.v == 700_000_000 + extra
    assert cx.price_high.prov == f"fp_{fp_max}"
    assert cx.price_low.prov == f"fp_{fp_floor}"


def test_m3_current_price_falls_back_to_complex_type(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        cx = load_report(s, 12).complex_by_id[7]
    assert cx.basis is not None and isinstance(cx.basis.max_price.v, int)
    assert cx.price_high.prov == cx.basis.max_price.prov
