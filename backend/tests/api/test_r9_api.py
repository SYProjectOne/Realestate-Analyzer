"""R9-API(계약 2026-10-09.20, DECISIONS D28-5) — 초보자 UI 데이터 요청(ui-benchmark 20-gap §2-2) Q1·Q4·Q5·Q6·Q7·Q8·Q9.

- Q1 계약금·중도금·잔금 원 금액(대표 타입 P_mid × 현재 납부 조건 비율 — RA §6-7 산술, 비교 TermsRow 와 같은 함수·같은 값).
- Q4 경쟁률 요약(1순위 해당지역 최고 경쟁률·미달 행 수)·당첨 가점 칸('확인 불가(가점 미수집)' — 수집 전).
- Q5 사유 코드(reason_code)·짧은 지역 합계 사유 + 내역·변경 피드 한 줄 요약·생활권 이름(la_n 대신).
- Q6 가격 갭 퍼센트(gap_pct, 출처 '.raw')와 점수 s_gap(gap_score, 출처 성분)을 나눈다.
- Q7 점수 행(대시보드 TOP·비교)에 목록 행과 같은 사실 Fact.
- Q8 접수 행 공급 종류(저장 문구 후보 키워드만 — 새 판단 없음).
- Q9 목록 정렬 키 intake(가능 → 미정 → 확인 불가 → 불가, 같은 상태 안 마감 임박 → id).
판정기 호출 없음, 읽기 전용 토큰 의미 그대로(GET 200).
"""

# ruff: noqa: E501  (한국어 assertion 메시지)
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import (
    ChangeEvent,
    Competition,
    FieldProvenance,
    IntakeStatus,
    PaymentTerms,
    ScoreComponent,
    ScoreRun,
)

from ._support import READ, WRITE, as_live, assert_facts_labelled, iter_facts, publish_revision, validate

SNAP = 12  # devseed 최신 published(인천)


def share_won(mid: Decimal, pct: Decimal) -> int:
    """서버 산술(``analysis.price.share_won``) — 함수 안에서 불러 수정 전 코드에서도 테스트마다 실패가 보이게."""
    from app.analysis.price import share_won as f

    return f(mid, pct)


def reason_code(reason: str | None, http: int | None = None) -> str | None:
    from app.api.reason_codes import reason_code as f

    return f(reason, http)


EL = 2  # 엘리프 검단 포레듀 — 가능(공식 팝업 '선착순 동·호지정'), 납부 조건 2개(현재 = 5%)


def _get(client: TestClient, url: str, op: str, headers: dict[str, str] = WRITE, **params: Any) -> Any:
    r = client.get(url, headers=headers, params=params)
    assert r.status_code == 200, (url, r.text[:500])
    body = r.json()
    validate(op, 200, body)
    return body


def _rows(client: TestClient, snap: int = SNAP, **params: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = _get(
        client, f"/api/snapshots/{snap}/complexes", "listComplexes", size=200, **params
    )["items"]
    return items


def _detail(client: TestClient, cid: int, snap: int = SNAP) -> dict[str, Any]:
    body: dict[str, Any] = _get(client, f"/api/complexes/{cid}", "getComplex", snapshot=snap)
    return body


def _prov(entity: str, entity_id: int, field: str, value: Any, *, label: str = "확인됨") -> str:
    with get_session() as s:
        fp = FieldProvenance(
            entity=entity, entity_id=entity_id, entity_key=f"r9:{entity}:{entity_id}", field=field,
            value_text=str(value), value_norm=str(value), label=label, reason=None,
            url="https://www.applyhome.co.kr/r9", checked_at="2026-10-08", source_rank=1, chosen=True,
        )  # fmt: skip
        s.add(fp)
        s.flush()
        return f"fp_{fp.id}"


def _competition(cid: int, rnd: str, type_code: str, supply: int, applied: int, kind: str = "본청약") -> int:
    with get_session() as s:
        c = Competition(
            complex_id=cid, round=rnd, kind=kind, type_code=type_code, supply=supply, applied=applied,
            ratio_or_shortfall_text=None, raw_document_id=None,
        )  # fmt: skip
        s.add(c)
        s.flush()
        cid_ = int(c.id)
    _prov("competition", cid_, "supply", supply)
    _prov("competition", cid_, "applied", applied)
    return cid_


# ====================================================================== Q1 계약금·중도금·잔금 원 금액


def test_q1_detail_payment_amounts_are_pmid_times_ratio(client: TestClient) -> None:
    d = _detail(client, EL)
    pa = d["price"]["payment_amounts"]
    cur = next(p for p in d["payment"] if p["is_current"])
    assert pa["payment_terms_id"] == cur["id"] and pa["basis_type_code"] == d["price"]["basis_type_code"]
    mid = Decimal(d["price"]["price_low"]["v"] + d["price"]["price_high"]["v"]) / 2
    for key, ratio, what in (
        ("down_payment_won", "down_payment_pct", "계약금"),
        ("interim_won", "interim_pct", "중도금"),
        ("balance_won", "balance_pct", "잔금"),
    ):
        f, r = pa[key], cur[ratio]
        assert r["label"] != "확인 불가", (key, r)
        assert f["v"] == share_won(mid, Decimal(str(r["v"]))), (key, f, r)
        assert f["label"] == "추정" and f["unit"] == "won", f
        assert f["reason"].startswith(f"산술(중간 가격 × {what} "), f  # D30-6(계약 .22): 'P_mid' → '중간 가격'
        assert f["prov"] == d["price"]["price_mid"]["prov"], f
    assert pa["down_payment_first_won"] == cur["down_payment_first_won"]
    assert pa["formula"].startswith("금액 = 중간 가격(") and "P_mid" not in pa["formula"]  # D30-6


def test_q1_same_value_in_list_row_and_compare_terms(client: TestClient) -> None:
    d = _detail(client, EL)
    row = next(r for r in _rows(client) if r["complex_id"] == EL)
    cmp_ = _get(client, f"/api/snapshots/{SNAP}/compare", "getCompare", ids=f"{EL},7")
    term = next(t for t in cmp_["terms"] if t["complex_id"] == EL)
    want = d["price"]["payment_amounts"]["down_payment_won"]
    assert row["down_payment_won"] == want == term["down_payment_won"], (row["down_payment_won"], want, term)


def test_q1_missing_ratio_is_unknown_with_reason(client: TestClient) -> None:
    as_live()
    with get_session() as s:
        cur = max(
            s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == EL)),
            key=lambda p: (p.effective_from, p.id),
        )
        cur.balance_pct = None
    d = _detail(client, EL)
    bal = d["price"]["payment_amounts"]["balance_won"]
    assert bal["label"] == "확인 불가" and bal["v"] is None and bal["reason"], bal
    assert bal["reason_code"] == reason_code(bal["reason"])
    assert d["price"]["payment_amounts"]["down_payment_won"]["label"] == "추정"


# ====================================================================== Q4 경쟁률 요약·당첨 가점


def test_q4_summary_from_first_rank_local_rows(client: TestClient) -> None:
    as_live()
    a = _competition(EL, "1순위 해당지역", "84.9939", 100, 750)  # 7.50
    _competition(EL, "1순위 해당지역", "84.9582", 50, 20)  # 0.40 · 미달
    _competition(EL, "1순위 기타지역", "84.9939", 10, 900)  # 기준 행 아님
    _competition(EL, "무순위", "84.9939", 2, 999, kind="무순위")  # 기준 행 아님
    d = _detail(client, EL)
    cs = d["competition_summary"]
    assert cs["basis"] == "본청약 1순위 해당지역" and cs["rows"] == 2
    assert cs["max_ratio"]["v"] == 7.5 and cs["max_ratio"]["label"] == "확인됨", cs
    assert cs["max_ratio"]["reason"] == "산술(접수 750 ÷ 공급 100)"
    with get_session() as s:
        applied_fp = s.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "competition",
                FieldProvenance.entity_id == a,
                FieldProvenance.field == "applied",
            )
        ).one()
    assert cs["max_ratio"]["prov"] == f"fp_{applied_fp.id}"
    assert cs["shortfall_types"]["v"] == 1 and cs["shortfall_types"]["unit"] == "count"
    shown = {c["id"]: c["type_code"] for c in d["competition"]}
    assert cs["max_ratio_type_code"] == shown[a]
    # 같은 함수 — 목록 행·점수 행(대시보드 TOP·비교)
    row = next(r for r in _rows(client) if r["complex_id"] == EL)
    assert row["competition_summary"] == cs
    dash = _get(client, f"/api/snapshots/{SNAP}/dashboard", "getDashboard")
    top = next((t for t in dash["top5"] if t["complex_id"] == EL), None)
    if top is not None:
        assert top["competition_summary"] == cs


def test_q4_no_rows_and_winning_score_not_collected(client: TestClient) -> None:
    d = _detail(client, EL)
    cs = d["competition_summary"]
    assert cs["rows"] == 0 and cs["max_ratio"]["label"] == "확인 불가" and cs["max_ratio_type_code"] is None
    assert cs["max_ratio"]["reason"] == "1순위 해당지역 경쟁률 없음"
    assert cs["winning_score_min"]["reason"] == cs["winning_score_max"]["reason"]
    assert d["competition"], "devseed 엘리프 경쟁률 행"
    for c in d["competition"]:
        for k in ("winning_score_min", "winning_score_max", "winning_score_avg"):
            assert c[k]["label"] == "확인 불가" and c[k]["reason"] == "가점 미수집", (k, c[k])
            assert c[k]["reason_code"] == "not_collected"


def _scores(comp_id: int, lo: str, hi: str, avg: str) -> dict[str, str]:
    """R9-PARSE 저장 모양: Competition.winning_score_* + 같은 이름 출처 행(웹 경쟁률 팝업)."""
    vals = {"winning_score_min": lo, "winning_score_max": hi, "winning_score_avg": avg}
    with get_session() as s:
        c = s.get(Competition, comp_id)
        assert c is not None
        for k, v in vals.items():
            setattr(c, k, Decimal(v))
    return {k: _prov("competition", comp_id, k, v) for k, v in vals.items()}


def test_q4_collected_winning_scores_light_up(client: TestClient) -> None:
    """R9-PARSE 가 저장한 당첨 가점(경쟁률 팝업)은 Fact 로 나온다 — 원문 숫자 그대로(0/0/0 도 숫자, '가점제 당첨자 없음'은 화면 문구
    D29-4). 요약은 1순위 해당지역 행 모두에 값이 있을 때 최저의 최솟값·최고의 최댓값. 가점이 없는 행은 여전히 '가점 미수집'."""
    as_live()
    a = _competition(EL, "1순위 해당지역", "59.9801", 73, 454)
    b = _competition(EL, "1순위 해당지역", "75.9096", 87, 185)
    zero = _competition(EL, "1순위 기타지역", "59.9801", 73, 80)
    pa = _scores(a, "42", "63", "48.5")
    _scores(b, "30", "55", "37.54")
    _scores(zero, "0", "0", "0")
    d = _detail(client, EL)
    rows = {c["id"]: c for c in d["competition"]}
    assert (
        rows[a]["winning_score_min"]["v"],
        rows[a]["winning_score_max"]["v"],
        rows[a]["winning_score_avg"]["v"],
    ) == (
        42,
        63,
        48.5,
    )
    assert (
        rows[a]["winning_score_avg"]["label"] == "확인됨"
        and rows[a]["winning_score_avg"]["prov"] == pa["winning_score_avg"]
    )
    assert [rows[zero][k]["v"] for k in ("winning_score_min", "winning_score_max", "winning_score_avg")] == [
        0,
        0,
        0,
    ]
    assert all(rows[zero][k]["label"] == "확인됨" for k in ("winning_score_min", "winning_score_max"))
    cs = d["competition_summary"]
    assert (cs["winning_score_min"]["v"], cs["winning_score_max"]["v"]) == (30, 63)
    assert cs["winning_score_min"]["label"] == "확인됨"
    others = [c for c in d["competition"] if c["id"] not in (a, b, zero)]
    assert others and all(c["winning_score_min"]["reason"] == "가점 미수집" for c in others)


def test_q4_incomplete_basis_row_makes_shortfall_unknown(client: TestClient) -> None:
    as_live()
    _competition(EL, "1순위 해당지역", "84.9939", 100, 750)
    with get_session() as s:
        c = Competition(
            complex_id=EL, round="1순위 해당지역", kind="본청약", type_code="59", supply=None, applied=None
        )
        s.add(c)
    cs = _detail(client, EL)["competition_summary"]
    assert cs["rows"] == 2 and cs["max_ratio"]["v"] == 7.5
    assert (
        cs["shortfall_types"]["label"] == "확인 불가" and cs["shortfall_types"]["reason"] == "일부 누락 1건"
    )


# ====================================================================== Q5 사유 코드


REASON_CASES: list[tuple[str | None, int | None, str | None]] = [
    ("403", None, "fetch_failed"),
    (None, 403, "fetch_failed"),
    ("문구로 판단 불가", 500, "fetch_failed"),
    ("DNS", None, "fetch_failed"),
    ("connect: [Errno 11001] getaddrinfo failed", None, "fetch_failed"),
    ("TLS(브라우저 재시도 실패)", None, "fetch_failed"),
    ("empty_dataset: totalCount 0", 200, "fetch_failed"),
    ("접속 실패", None, "fetch_failed"),
    ("원문 없음", None, "not_collected"),
    ("원 공고 미수집", None, "not_collected"),
    ("미분양 자료 없음", None, "not_collected"),
    ("가점 미수집", None, "not_collected"),
    ("공고 전", None, "not_published"),
    ("분양가 미공개", None, "not_published"),
    ("발코니 표 해석 실패", None, "parse_failed"),
    ("공급금액 표 없음", None, "parse_failed"),
    ("스캔", None, "parse_failed"),
    ("출처 누락", None, "source_missing"),
    ("검증 모순", None, "demoted"),
    ("출처 상충 — compare 대기", None, "conflict_hold"),
    ("확인 불가(타입 모호)", None, "conflict_hold"),
    ("일부 누락 2건", None, "partial_missing"),
    ("공식 홈페이지 동일성 미확인", 200, "identity_unconfirmed"),
    ("공식 홈페이지가 다른 단지", 200, "other_complex_site"),
    ("접수 문구 없음", 200, "no_phrase"),
    ("문구로 판단 불가", 200, "phrase_inconclusive"),
    ("판정 대상 아님(공공분양)", None, "not_target"),
    ("입력 차단(guard)", None, "input_blocked"),
    ("판정 미해결", None, "unresolved"),
    ("접수 문구 미분류", None, "unresolved"),
    ("미해결(review)", None, "unresolved"),
    ("미판정", None, "unjudged"),
    ("판정 기록 없음", None, "unjudged"),
    ("회귀 (a)단계 고정 입력", None, "unjudged"),
    ("미입력", None, "not_entered"),
    ("비교군 없음(같은 생활권 비교 거래 없음)", None, "no_sample"),
    ("사람 확인", None, "human_check"),
    ("값 없음", None, "no_value"),
    ("예정 시기 미기재", None, "no_value"),
    ("납부 조건 없음", None, "no_value"),
    ("결측", None, "no_value"),
    ("거리 미측정", None, "other"),
    ("추가 공급 미정(무순위 2차 이후 공고 없음, 공고 이력 있음)", None, "other"),
    (None, None, None),
    ("", 200, None),
]


@pytest.mark.parametrize(("reason", "http", "code"), REASON_CASES)
def test_q5_reason_code_rules(reason: str | None, http: int | None, code: str | None) -> None:
    from app.api.reason_codes import REASON_CODES

    assert reason_code(reason, http) == code
    assert code is None or code in REASON_CODES


def test_q5_every_unknown_fact_carries_its_reason_code(client: TestClient) -> None:
    bodies = [
        _get(client, f"/api/snapshots/{SNAP}/dashboard", "getDashboard"),
        _get(client, f"/api/snapshots/{SNAP}/complexes", "listComplexes", size=200),
        _detail(client, EL),
        _detail(client, 15),
        _get(client, f"/api/snapshots/{SNAP}/market", "getMarket"),
    ]
    seen = 0
    for body in bodies:
        assert_facts_labelled(body)
        for path, f in iter_facts(body):
            if f["label"] == "확인 불가":
                seen += 1
                assert f.get("reason_code") == reason_code(f["reason"]), (path, f)
            else:
                assert "reason_code" not in f, (path, f)
    assert seen > 50


def test_q5_intake_reason_code_and_queue(client: TestClient) -> None:
    d = _detail(client, 4)  # 오퍼스 — 403
    cur = d["intake_current"]
    assert cur["status"] == "확인 불가" and cur["reason_code"] == "fetch_failed"
    assert _detail(client, EL)["intake_current"]["reason_code"] is None  # 가능 — 사유 없음
    q = _get(client, "/api/ops/intake-queue", "getIntakeQueue", headers=READ)
    for g in q["groups"]:
        for it in g["items"]:
            assert it["reason_code"] == (
                reason_code(it["reason"], it["http_status"]) if it["reason"] else None
            )
            if g["category"] == "collect_failed":
                assert it["reason_code"] == "fetch_failed"


def test_q5_region_sum_reason_is_short_with_breakdown(client: TestClient) -> None:
    dash = _get(client, f"/api/snapshots/{SNAP}/dashboard", "getDashboard")
    un = dash["kpis"]["unsold"]
    assert un["total"]["reason"].startswith("지역 합계(시군구 ") and len(un["total"]["reason"]) <= 20, un[
        "total"
    ]
    parts = un["breakdown"]
    assert len(parts) >= 2 and all(p["ym"] == un["ym"] for p in parts)
    assert sum(p["total"]["v"] for p in parts) == un["total"]["v"]
    assert sum(p["post_completion"]["v"] for p in parts) == un["post_completion"]["v"]
    assert all(p["scope_name"] for p in parts)
    for p in dash["unsold_series"]:
        r = p["total"].get("reason") or ""
        assert "·" not in r and not r.endswith(" 합"), p["total"]  # 예전 '<이름> <값>·… 합' 나열이 아니다


def test_q5_change_feed_summary_hides_hash(client: TestClient) -> None:
    h1, h2 = "4017" + "a" * 60, "59fd" + "b" * 60
    with get_session() as s:
        s.add(
            ChangeEvent(
                snapshot_id=SNAP, entity="complex", entity_id=EL, field="official_popup_hash", old_text=h1, new_text=h2,
                detected_at="2026-10-08T23:59:00+09:00", severity="critical", triggers_rejudge=True, complex_id=EL,
            )
        )  # fmt: skip
    as_live()
    feed = _get(client, f"/api/snapshots/{SNAP}/changes", "listChanges")
    ev = next(e for e in feed if e["field"] == "official_popup_hash")
    assert ev["field_label"] == "공식 홈페이지 팝업" and ev["value_kind"] == "hash"
    assert ev["summary"] == "공식 홈페이지 팝업이 바뀌었습니다"
    assert h1 not in ev["summary"] and (ev["old_text"], ev["new_text"]) == (h1, h2)  # 원값은 그대로(D25-2)
    down = next(e for e in feed if e["field"] == "down_payment_pct")
    assert (
        down["value_kind"] == "plain"
        and down["summary"] == f"계약금 비율(%): {down['old_text']} → {down['new_text']}"
    )
    for e in feed:
        assert e["summary"] and e["field_label"] and e["value_kind"] in ("plain", "hash", "json")
        if e["value_kind"] != "plain":
            assert (e["old_text"] or "#")[:6] not in e["summary"], e


@pytest.mark.parametrize(
    ("entity", "field", "old", "new", "label", "summary"),
    [
        (
            "complex",
            "popup_image_hash",
            "9be1…c04",
            "47d0…a1e",
            "공식 홈페이지 팝업 그림",
            "공식 홈페이지 팝업 그림이 바뀌었습니다",
        ),
        (
            "complex",
            "apply_dates",
            "[]",
            '[{"kind":"1순위"}]',
            "청약 접수 일정",
            "청약 접수 일정이 바뀌었습니다",
        ),
        (
            "payment_terms",
            "interim_schedule[1].due_date",
            "2026-10-18",
            "2026-10-30",
            "중도금 1회차 납부일",
            "중도금 1회차 납부일: 2026-10-18 → 2026-10-30",
        ),
        (
            "payment_terms",
            "price_by_type.84A.max_price_won",
            "578000000",
            "559000000",
            "84A 최고 공급가",
            "84A 최고 공급가: 578000000 → 559000000",
        ),
        ("complex", "move_in_ym", None, "2028-03", "입주 예정월", "입주 예정월: 없음 → 2028-03"),
        ("notice", "new_notice", None, "무순위 2차", "새 공고", "새 공고: 무순위 2차"),
        ("complex", "unknown_field_x", "a", "b", "unknown_field_x", "unknown_field_x: a → b"),
    ],
)
def test_q5_change_text_table(
    entity: str, field: str, old: str | None, new: str | None, label: str, summary: str
) -> None:
    from app.api.change_text import change_summary, field_label

    assert field_label(entity, field) == label
    assert change_summary(entity, field, old, new) == summary


def test_q5_market_living_area_names(client: TestClient) -> None:
    m = _get(client, f"/api/snapshots/{SNAP}/market", "getMarket")
    names = {a["id"]: a["name"] for a in m["living_areas"]}
    assert m["supply"] and m["benchmark_flags"]
    for p in [*m["supply"], *m["benchmark_flags"], *m["benchmarks"], *m["move_in_markers"]]:
        assert p["living_area_name"] == names.get(p["living_area"] or ""), p


# ====================================================================== Q6 가격 갭 퍼센트 vs 점수


def test_q6_gap_percent_and_score_have_distinct_names_and_drawers(client: TestClient) -> None:
    as_live()
    run_id0 = _detail(client, EL)["score"]["score_run_id"]  # 기본 시나리오(base) 점수 실행
    with get_session() as s:
        run = s.get(ScoreRun, run_id0)
        assert run is not None
        comp = s.scalars(
            select(ScoreComponent).where(
                ScoreComponent.score_run_id == run.id,
                ScoreComponent.complex_id == EL,
                ScoreComponent.component == "gap",
            )
        ).one()
        comp.raw_value = Decimal("8.1")
        run_id, score = run.id, float(comp.score_0_10)
    d = _detail(client, EL)
    gap = d["gap"]
    assert gap["gap_pct"]["v"] == 8.1 and gap["gap_pct"]["unit"] == "pct"
    assert gap["gap_pct"]["prov"] == f"sc_{run_id}_{EL}_gap.raw"
    assert gap["gap_score"]["v"] == score and gap["gap_score"]["unit"] == "score"
    assert gap["gap_score"]["prov"] == f"sc_{run_id}_{EL}_gap"
    assert gap["score"] == gap["gap_score"]  # 옛 이름 = 같은 Fact
    row = next(r for r in _rows(client) if r["complex_id"] == EL)
    assert row["gap_pct"] == gap["gap_pct"] or row["gap_pct"]["prov"] == gap["gap_pct"]["prov"]
    raw = _get(client, f"/api/provenance/{gap['gap_pct']['prov']}", "getProvenance")
    assert raw["kind"] == "score_component" and raw["field"] == "gap.raw" and raw["value_text"] == "8.1"
    pts = _get(client, f"/api/provenance/{gap['gap_score']['prov']}", "getProvenance")
    assert pts["field"] == "gap" and pts["value_text"] == f"{score:g}"
    assert client.get(f"/api/provenance/sc_{run_id}_{EL}_p10.raw", headers=WRITE).status_code in (200, 404)


def test_q6_published_drawer_for_raw_gap(client: TestClient) -> None:
    run_id0 = _detail(client, EL)["score"]["score_run_id"]
    with get_session() as s:
        run = s.get(ScoreRun, run_id0)
        assert run is not None
        for comp in s.scalars(
            select(ScoreComponent).where(
                ScoreComponent.score_run_id == run.id, ScoreComponent.component == "gap"
            )
        ):
            comp.raw_value = Decimal("-3.25")
    rev = publish_revision(1, "R9 gap.raw 서랍")
    d = _detail(client, EL, rev)
    pid = d["gap"]["gap_pct"]["prov"]
    if pid is None:  # 새 리비전 점수 실행이 원값을 다시 만들지 않으면(이월 실행) 건너뛴다
        pytest.skip("새 리비전에 gap 원값 없음")
    assert pid.endswith("_gap.raw")
    r = client.get(f"/api/provenance/{pid}", headers=READ, params={"snapshot_id": rev})
    assert r.status_code == 200, r.text
    assert r.json()["field"] == "gap.raw"


# ====================================================================== Q7 점수 행 사실


FACT_KEYS = ("price_low", "price_high", "resale_end", "move_in_ym", "gap_pct", "competition_summary")


def test_q7_dashboard_top_rows_carry_list_facts(client: TestClient) -> None:
    dash = _get(client, f"/api/snapshots/{SNAP}/dashboard", "getDashboard")
    rows = {r["complex_id"]: r for r in _rows(client)}
    assert dash["top5"]
    for t in dash["top5"]:
        row = rows[t["complex_id"]]
        for k in FACT_KEYS:
            assert t[k] == row[k], (t["complex_id"], k, t[k], row[k])


def test_q7_compare_and_detail_score_rows_carry_same_facts(client: TestClient) -> None:
    rows = {r["complex_id"]: r for r in _rows(client)}
    cmp_ = _get(client, f"/api/snapshots/{SNAP}/compare", "getCompare", ids=f"{EL},7")
    for r in cmp_["rows"]:
        for k in FACT_KEYS:
            assert r[k] == rows[r["complex_id"]][k], (r["complex_id"], k)
    d = _detail(client, EL)
    assert d["score"] is not None
    for k in FACT_KEYS:
        assert d["score"][k] == rows[EL][k], k


def test_q7_live_revision_same_as_list(client: TestClient) -> None:
    as_live()
    test_q7_dashboard_top_rows_carry_list_facts(client)


# ====================================================================== Q8 접수 공급 종류


def _set_intake(cid: int, **values: Any) -> None:
    with get_session() as s:
        row = s.scalars(
            select(IntakeStatus).where(
                IntakeStatus.snapshot_id == SNAP,
                IntakeStatus.complex_id == cid,
                IntakeStatus.path == "official_popup",
            )
        ).one()
        for k, v in values.items():
            setattr(row, k, v)


@pytest.mark.parametrize(
    ("status", "note", "kind", "basis"),
    [
        (
            "가능",
            "문구 후보: 무순위 계약자 모집 / 견본주택 안내 · 판정기 classify jl_5",
            "무순위",
            "무순위 계약자 모집",
        ),
        (
            "가능",
            "문구 후보: 잔여세대 선착순 동·호지정 계약 중 · 판정기 classify jl_5",
            "선착순",
            "잔여세대 선착순 동·호지정 계약 중",
        ),
        (
            "미정",
            "문구 후보: 임의공급 2차 모집 예정 · 판정기 classify jl_7",
            "임의",
            "임의공급 2차 모집 예정",
        ),
        (
            "가능",
            "문구 후보: 무순위 접수 / 선착순 계약 · 판정기 classify jl_5",
            None,
            "공급 종류 문구가 여럿(무순위·선착순)",
        ),
        ("가능", "문구 후보: 분양 중 · 판정기 classify jl_5", None, None),
        ("확인 불가", "문구 후보: 무순위 계약자 모집 · 판정기 classify jl_5", None, None),
        ("가능", "판정기 classify jl_5(무순위 문구 근거)", None, None),
    ],
)
def test_q8_supply_kind_from_stored_phrase_only(
    client: TestClient, status: str, note: str, kind: str | None, basis: str | None
) -> None:
    as_live()
    _set_intake(EL, status=status, note=note, reason=None if status != "확인 불가" else "문구로 판단 불가")
    cur = _detail(client, EL)["intake_current"]
    assert (cur["supply_kind"], cur["supply_kind_basis"]) == (kind, basis), cur


def test_q8_human_check_and_unofficial_rows_have_no_supply_kind(client: TestClient) -> None:
    d = _detail(client, EL)
    assert d["intake_current"]["supply_kind"] == "선착순"  # devseed 팝업 '선착순 동·호지정'
    for it in d["intake"]:
        if it["path"] in ("human_check", "unofficial_ref"):
            assert it["supply_kind"] is None and it["supply_kind_basis"] is None, it


# ====================================================================== Q9 정렬 키 intake


ORDER = {"가능": 0, "미정": 1, "확인 불가": 2, None: 2, "불가": 3}


def test_q9_sort_by_intake_status_then_id(client: TestClient) -> None:
    rows = _rows(client, sort="intake")
    keys = [(ORDER[(r["intake"] or {}).get("status")], r["complex_id"]) for r in rows]
    assert [k[0] for k in keys] == sorted(k[0] for k in keys)
    statuses = [(r["intake"] or {}).get("status") for r in rows]
    assert statuses[0] == "가능" and "미정" in statuses
    desc = _rows(client, sort="-intake")
    assert [ORDER[(r["intake"] or {}).get("status")] for r in desc] == sorted(
        (ORDER[(r["intake"] or {}).get("status")] for r in desc), reverse=True
    )
    # 같은 상태 안 순서는 방향과 무관(마감 → id)
    open_asc = [r["complex_id"] for r in rows if (r["intake"] or {}).get("status") == "가능"]
    open_desc = [r["complex_id"] for r in desc if (r["intake"] or {}).get("status") == "가능"]
    assert open_asc == open_desc
    # 읽기 전용 토큰도 GET 200
    assert (
        client.get(f"/api/snapshots/{SNAP}/complexes", params={"sort": "intake"}, headers=READ).status_code
        == 200
    )


def test_q9_nearest_deadline_first_within_status(client: TestClient) -> None:
    from app.models import Complex

    as_live()
    opened = [r["complex_id"] for r in _rows(client) if (r["intake"] or {}).get("status") == "가능"]
    assert len(opened) >= 2, opened
    first, second = sorted(opened)[:2]
    with get_session() as s:
        a, b = s.get(Complex, first), s.get(Complex, second)
        assert a is not None and b is not None
        a.apply_dates = [{"kind": "1순위", "start": "2026-11-20", "end": "2026-11-21"}]
        b.apply_dates = [
            {"kind": "특별공급", "start": "2026-10-01", "end": "2026-10-02"},  # 기준일(10-08) 전 — 지남
            {"kind": "1순위", "start": "2026-10-20", "end": "2026-10-21"},
        ]
    rows = _rows(client, sort="intake")
    got = [r["complex_id"] for r in rows if (r["intake"] or {}).get("status") == "가능"]
    assert got[:2] == [second, first], got


def test_q9_unknown_sort_key_still_422(client: TestClient) -> None:
    r = client.get(f"/api/snapshots/{SNAP}/complexes", params={"sort": "intake_status"}, headers=WRITE)
    assert r.status_code == 422, r.text
