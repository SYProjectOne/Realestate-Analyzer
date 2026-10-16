"""R11-BE(계약 2026-10-09.22, DECISIONS D30-5·D30-6) — API 쪽.

- D30-5 목업 "API 필요" 값: 없던 것 둘을 더했다 — G6 시장 ``unsold_latest``(대시보드 ``kpis.unsold`` 와 같은 함수·같은 값),
  G3·G4 ``gap.comps_median``·``comps_median_unadjusted``(점수 실행 저장값 — gap% 의 기준). 이미 있던 셋(G1 목록 ``total``,
  G7 주장 목록 ``verify_status``, G3 ``competition_summary.winning_score_*``)은 세기만으로 화면이 쓴다(D25-3).
- D30-6 서버 문구: 요건 이유·원 금액 사유의 'P_mid' → '중간 가격', 판정 범위 사유의 영어 분류명 → 한국어.
판정기 호출 없음, 읽기 전용 토큰 의미 그대로(GET 200).
"""

# ruff: noqa: E501  (한국어 assertion 메시지)
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import Complex, ScoreComponent

from ._support import READ, WRITE, as_live, validate

SNAP = 12  # devseed 최신 published(인천)
EL = 2  # 엘리프 검단 포레듀
ENGLISH_CLASSES = (
    "public_sale",
    "public_rental",
    "private_rental",
    "non_apartment",
    "out_of_scope",
    "private_sale_apt",
)


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
    items: list[dict[str, Any]] = _get(
        client, f"/api/snapshots/{snap}/complexes", "listComplexes", size=1000
    )["items"]
    return items


def _gap_row(run_id: int, cid: int) -> ScoreComponent:
    with get_session() as s:
        row = s.scalars(
            select(ScoreComponent).where(
                ScoreComponent.score_run_id == run_id,
                ScoreComponent.complex_id == cid,
                ScoreComponent.component == "gap",
            )
        ).one()
        s.expunge(row)
        return row


def _stored_median(row: ScoreComponent) -> int | None:
    from app.analysis.gap import median_from_flags

    return row.median_won if row.median_won is not None else median_from_flags(row.flags)


# ====================================================================== D30-5 A1 시장 미분양 지역 합계


def test_a1_market_unsold_latest_is_dashboard_kpi(client: TestClient) -> None:
    """G6 요약 카드 합계 = G1 KPI 와 같은 함수·같은 값(시장 응답만으로 그린다 — 화면이 unsold[] 를 더하지 않는다)."""
    dash = _get(client, f"/api/snapshots/{SNAP}/dashboard", "getDashboard", headers=READ)
    market = _get(client, f"/api/snapshots/{SNAP}/market", "getMarket", headers=READ)
    latest = market["unsold_latest"]
    assert latest == dash["kpis"]["unsold"], (latest, dash["kpis"]["unsold"])
    assert latest["ym"] is not None and latest["total"]["label"] != "확인 불가", latest
    assert latest["total"]["reason"].startswith("지역 합계(시군구 "), latest["total"]
    assert sum(p["total"]["v"] for p in latest["breakdown"]) == latest["total"]["v"]
    assert sum(p["post_completion"]["v"] for p in latest["breakdown"]) == latest["post_completion"]["v"]
    # 내역은 시장 unsold[] 의 그 달 단위별 점과 같은 행
    same_month = [p for p in market["unsold"] if p["ym"] == latest["ym"]]
    assert sorted(latest["breakdown"], key=lambda p: p["scope_code"]) == sorted(
        same_month, key=lambda p: p["scope_code"]
    )


def test_a1_market_unsold_latest_follows_living_area_units(client: TestClient) -> None:
    market = _get(client, f"/api/snapshots/{SNAP}/market", "getMarket")
    checked = 0
    for la in market["living_areas"]:
        one = _get(client, f"/api/snapshots/{SNAP}/market", "getMarket", living_area=la["id"])
        latest = one["unsold_latest"]
        shown = {p["scope_code"] for p in one["unsold"]}
        if not shown:
            assert (
                latest["ym"] is None and latest["total"]["label"] == "확인 불가" and latest["breakdown"] == []
            ), latest
            continue
        assert {p["scope_code"] for p in latest["breakdown"]} <= shown, (la, latest)
        if latest["total"]["label"] != "확인 불가":
            assert sum(p["total"]["v"] for p in latest["breakdown"]) == latest["total"]["v"]
        checked += 1
    assert checked >= 1


# ====================================================================== D30-5 A2 비교군 전체 중앙값


def _assert_gap_basis(gap: dict[str, Any], stored: int) -> None:
    med = gap["comps_median"]
    assert med["v"] == stored, (med, stored)
    assert med["prov"] == gap["gap_pct"]["prov"] and med["prov"].endswith("_gap.raw"), med
    assert med["unit"] == "won" and med["reason"].startswith("비교군 실거래 "), med
    # gap% 의 기준이 바로 이 값이다(현재 구매가 중앙 − 중앙값)/중앙값 × 100 — 표시 반올림 오차만
    mid = Decimal(str(gap["price_mid"]["v"]))
    pct = (mid - Decimal(stored)) / Decimal(stored) * 100
    assert abs(pct - Decimal(str(gap["gap_pct"]["v"]))) < Decimal("0.01"), (pct, gap["gap_pct"])


def test_a2_detail_and_compare_gap_carry_stored_comps_median(client: TestClient) -> None:
    rows = [r for r in _rows(client) if r["gap_pct"]["label"] != "확인 불가"]
    assert rows
    seen = 0
    for r in rows[:6]:
        d = _detail(client, r["complex_id"])
        gap = d["gap"]
        row = _gap_row(d["score"]["score_run_id"], r["complex_id"])
        stored = _stored_median(row)
        assert stored is not None, r["complex_id"]
        _assert_gap_basis(gap, stored)
        want_label = "추정" if "substitute" in (row.flags or []) else "재가공"
        assert gap["comps_median"]["label"] == want_label, gap["comps_median"]
        if gap["gap_pct_unadjusted"] is not None:
            un = gap["comps_median_unadjusted"]
            assert un is not None and un["label"] == "재가공" and un["reason"].endswith("중앙값(미보정)"), un
        seen += 1
    ids = ",".join(str(r["complex_id"]) for r in rows[:2])
    cmp_ = _get(client, f"/api/snapshots/{SNAP}/compare", "getCompare", ids=ids)
    for cid in ids.split(","):
        assert cmp_["gaps"][cid]["comps_median"] == _detail(client, int(cid))["gap"]["comps_median"]
    assert seen >= 1


def test_a2_unknown_gap_gives_unknown_median(client: TestClient) -> None:
    rows = [r for r in _rows(client) if r["gap_pct"]["label"] == "확인 불가"]
    assert rows, "devseed 에 가격 갭 확인 불가 단지가 있어야 한다(공고 전 단지)"
    gap = _detail(client, rows[0]["complex_id"])["gap"]
    med = gap["comps_median"]
    assert med["label"] == "확인 불가" and med["v"] is None and med["reason"], med
    assert med["reason_code"], med
    assert gap["comps_median_unadjusted"] is None


def test_a2_old_score_run_fallback(client: TestClient) -> None:
    """0019 전 실행(median_won 없음·태그 없음): 대체 단지가 없으면 같은 값인 미보정 중앙값, 있으면 '확인 불가'(역산하지 않는다)."""
    as_live()
    d = _detail(client, EL)
    run_id = d["score"]["score_run_id"]
    with get_session() as s:
        row = s.scalars(
            select(ScoreComponent).where(
                ScoreComponent.score_run_id == run_id,
                ScoreComponent.complex_id == EL,
                ScoreComponent.component == "gap",
            )
        ).one()
        row.raw_value = Decimal("-5.2")  # gap% 가 있는 실행(test_r9_api Q6 와 같은 방식)
        unadj = 612_000_000  # 옛 실행(0004 열)의 미보정 중앙값
        row.median_won = None
        row.unadjusted_median_won = unadj
        row.flags = [f for f in row.flags or [] if not f.startswith("median_won=") and f != "substitute"]
    med = _detail(client, EL)["gap"]["comps_median"]
    assert med["v"] == unadj and med["label"] == "재가공", med
    with get_session() as s:
        row = s.scalars(
            select(ScoreComponent).where(
                ScoreComponent.score_run_id == run_id,
                ScoreComponent.complex_id == EL,
                ScoreComponent.component == "gap",
            )
        ).one()
        row.flags = [*(row.flags or []), "substitute"]
    med = _detail(client, EL)["gap"]["comps_median"]
    assert (
        med["label"] == "확인 불가" and med["v"] is None and med["reason"] == "옛 점수 실행(재판정 뒤 표시)"
    ), med


# ====================================================================== D30-5 A3·A4·A5 이미 있는 값(세기만)


def test_a3_a4_a5_values_already_in_responses(client: TestClient) -> None:
    """새 필드 없이 쓰는 값: G1 전체 단지 수 = 목록 total, G7 상태별 수 = 주장 목록 verify_status 세기,
    G3 가점 범위 = competition_summary.winning_score_min/max(서버 Fact)."""
    page = _get(client, f"/api/snapshots/{SNAP}/complexes", "listComplexes", headers=READ, size=1)
    full = _rows(client)
    assert page["total"] == len(full) >= 1
    claims = _get(client, f"/api/snapshots/{SNAP}/claims", "listClaims", headers=READ)
    assert all("verify_status" in c and "remaining" in c for c in claims)
    for status in ("verified", "contradicted", "unsupported", "review"):
        only = _get(client, f"/api/snapshots/{SNAP}/claims", "listClaims", headers=READ, status=status)
        assert len(only) == sum(1 for c in claims if c["verify_status"] == status), status
    cs = _detail(client, EL)["competition_summary"]
    assert cs is not None and {"winning_score_min", "winning_score_max"} <= set(cs)
    assert cs["winning_score_min"]["label"] and cs["winning_score_max"]["label"]


# ====================================================================== D30-6 서버 문구


def _strings(obj: Any, path: str = "$") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        out.append((path, obj))
    return out


def _p_mid_outside_score_formula(body: Any) -> list[tuple[str, str]]:
    """'P_mid' 가 남은 문자열 — 점수 성분 식(formula_text — RA §6 식 표기)은 뺀다."""
    return [(p, s) for p, s in _strings(body) if "P_mid" in s and not p.endswith(".formula_text")]


def test_d30_6_no_p_mid_in_reasons(client: TestClient) -> None:
    rows = _rows(client)
    assert not _p_mid_outside_score_formula(rows)
    assert any(
        (r.get("down_payment_won") or {}).get("reason", "").startswith("산술(중간 가격 × 계약금 ")
        for r in rows
    )
    d = _detail(client, EL)
    assert not _p_mid_outside_score_formula(d), _p_mid_outside_score_formula(d)[:3]
    assert d["price"]["payment_amounts"]["formula"].startswith("금액 = 중간 가격(")
    cmp_ = _get(client, f"/api/snapshots/{SNAP}/compare", "getCompare", ids=f"{EL},7", scenario="B")
    assert not _p_mid_outside_score_formula(cmp_), _p_mid_outside_score_formula(cmp_)[:3]


def test_d30_6_funds_requirement_evidence_in_preview(client: TestClient) -> None:
    """요건 사전 계산(시나리오 미리보기): 계약금 비율이 없으면 근거가 '계약금 비율 확인 불가(중간 가격 …)'."""
    as_live()
    with get_session() as s:
        from app.models import PaymentTerms

        for p in s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == EL)):
            p.down_payment_pct = None
    scenarios = _get(client, "/api/scenarios", "listScenarios")
    sid = next(sc["id"] for sc in scenarios if sc.get("code") == "B")
    r = client.get(f"/api/scenarios/{sid}/preview", headers=WRITE, params={"snapshot": SNAP})
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    validate("previewScenario", 200, body)
    pre = next(x for x in body["requirements_pre"] if x["complex_id"] == EL)
    assert pre["funds"]["evidence"].startswith("계약금 비율 확인 불가(중간 가격 "), pre["funds"]
    assert not _p_mid_outside_score_formula(body)


def test_d30_6_judge_scope_reason_uses_korean_class_names(client: TestClient) -> None:
    as_live()
    with get_session() as s:
        cx = s.get(Complex, EL)
        assert cx is not None
        cx.inclusion_class, cx.inclusion_decision = "public_sale", "auto"
    row = next(r for r in _rows(client) if r["complex_id"] == EL)
    assert row["judge_scope_reason"] == "포함/제외 classify 제외 클래스(공공분양)", row["judge_scope_reason"]
    head = _detail(client, EL)["header"]
    assert head["judge_scope_reason"] == row["judge_scope_reason"]
    with get_session() as s:
        cx = s.get(Complex, EL)
        assert cx is not None
        cx.inclusion_class, cx.inclusion_decision = "미분류", "review"
    row = next(r for r in _rows(client) if r["complex_id"] == EL)
    assert row["judge_scope_reason"] == "포함/제외 classify 미해결(검토, 미분류)", row["judge_scope_reason"]
    for r in _rows(client):
        reason = r.get("judge_scope_reason") or ""
        assert not any(e in reason for e in ENGLISH_CLASSES), (r["complex_id"], reason)
