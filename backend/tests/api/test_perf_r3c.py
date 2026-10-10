"""R3c 성능: 점수 행이 있는 합성 1,000단지 ``/complexes?size=1000`` cold 첫 요청 0.5초 + 목록 응답 골든.

1. 골든(``test_list_responses_match_golden``): 목록(G2)·CSV 응답 바이트가 최적화(``api.views`` 목록 경로) 전과 같다.
   세 DB 상태 — ``plain``(devseed 그대로) · ``rich``(최신 공고 가격·할인·두 번째 공고·강등 3종(단지·타입·공고 가격)·
   풀린 강등·복원된 강등·OCR 값) · ``synth``(rich + 합성 1,000단지 + 점수 행 — 지역 하위 질의·읽기 전용 행 경로) — 에서
   기본 페이지·size=1000·정렬·필터·시나리오·과거 스냅샷·CSV 응답의 sha256 을 ``snapshots/list_r3c.json`` 과 비교한다.
   같은 ``views`` 함수를 쓰는 다른 화면(대시보드·시장·비교·상세·미리보기)도 같이 고정한다(목록 최적화가 그 응답을 바꾸지
   않는다). ``rich`` 의 size=1000 JSON·CSV 는 본문 전체도 ``snapshots/list_r3c/`` 에 둔다(차이가 나면 읽을 수 있게).
   의도한 응답 변경이면 ``UPDATE_GOLDEN=1`` 로 다시 쓴다(최적화 전 코드로 만든 값이다).
2. 성능(``test_cold_size1000_with_scores_under_half_second``): 새 엔진·새 앱의 첫 요청(cold) size=1000 을
   ``COLD_RUNS`` 번 재서 중앙값 < 0.5초(기존 ``test_perf_t16``·``test_perf_r3`` 의 1초 기준은 그대로).
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import os
import shutil
import statistics
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session, reset_engine
from app.core.settings import Settings, set_settings
from app.models import Claim, ComplexType, FactDemotion, FieldProvenance, PaymentTerms

from ._support import WRITE
from .conftest import Seeded, make_settings
from .test_perf_r3 import _score_synth

SNAP = 12
COLD_RUNS = 5
LIMIT_S = 0.5
GOLDEN = Path(__file__).parent / "snapshots" / "list_r3c.json"
BODIES = Path(__file__).parent / "snapshots" / "list_r3c"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"

LIST = f"/api/snapshots/{SNAP}/complexes"
CSV = f"/api/snapshots/{SNAP}/complexes.csv"
ALL = ("plain", "rich", "synth")
SMALL = (
    "plain",
    "rich",
)  # 미리보기: 합성 1,000단지는 rerank 후보 250개 초과로 원래 500(판정기 payload 한도 — 이 변경 무관)
CASES: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("default", LIST, {}),
    ("size1000", LIST, {"size": 1000}),
    ("sort_price_mid", LIST, {"sort": "-price_mid", "size": 1000}),
    ("sort_name_page2", LIST, {"sort": "name", "page": 2, "size": 5}),
    ("sort_gap_resale", LIST, {"sort": "resale_end", "size": 200}),
    (
        "filter_scope_area",
        LIST,
        {"filter[judge_scope]": "판정 대상,참고", "filter[living_area]": "la_2,la_4", "sort": "-gap_pct"},
    ),
    (
        "filter_price",
        LIST,
        {"filter[price_min]": 300_000_000, "filter[price_max]": 900_000_000, "sort": "price_low"},
    ),
    (
        "filter_misc",
        LIST,
        {"filter[intake_status]": "가능,확인 불가", "filter[move_in_year]": 2028, "sort": "-p10"},
    ),
    ("scenario_a", LIST, {"scenario": "A", "size": 1000}),
    ("scenario_c_rank", LIST, {"scenario": "C", "sort": "rank", "size": 300}),
    ("last_change", LIST, {"sort": "-last_change", "size": 100}),
    ("past_snapshot", f"/api/snapshots/{SNAP - 1}/complexes", {"size": 1000}),
    ("csv", CSV, {}),
    ("csv_scenario_b", CSV, {"scenario": "B", "sort": "name"}),
    # 같은 views 함수(load_bundles·score_ctx·price_range·ladder_view·provenance_for)를 쓰는 다른 화면
    ("dashboard", f"/api/snapshots/{SNAP}/dashboard", {}),
    ("dashboard_c", f"/api/snapshots/{SNAP}/dashboard", {"scenario": "C"}),
    ("market", f"/api/snapshots/{SNAP}/market", {}),
    ("compare", f"/api/snapshots/{SNAP}/compare", {"ids": "2,3,4,5,7"}),
    ("detail_2", "/api/complexes/2", {"snapshot": SNAP}),
    ("detail_3", "/api/complexes/3", {"snapshot": SNAP}),
    ("detail_5", "/api/complexes/5", {"snapshot": SNAP, "scenario": "A"}),
    ("detail_7", "/api/complexes/7", {"snapshot": SNAP}),
    ("preview", "/api/scenarios/1/preview", {"snapshot": SNAP}),
)
ONLY: dict[str, tuple[str, ...]] = {"preview": SMALL}
FULL_BODIES = {("rich", "size1000"): "rich_size1000.json", ("rich", "csv"): "rich.csv"}


# ====================================================================== DB 상태


def _chosen(s: Any, entity: str, entity_id: int, field: str) -> FieldProvenance:
    fp = s.scalars(
        select(FieldProvenance)
        .where(
            FieldProvenance.entity == entity,
            FieldProvenance.entity_id == entity_id,
            FieldProvenance.field == field,
            FieldProvenance.chosen.is_(True),
        )
        .order_by(FieldProvenance.id)
    ).first()
    assert fp is not None, (entity, entity_id, field)
    return fp  # type: ignore[no-any-return]


def _prov(
    s: Any, entity: str, entity_id: int, field: str, value: Any, label: str = "확인됨"
) -> FieldProvenance:
    fp = FieldProvenance(
        entity=entity, entity_id=entity_id, field=field, value_text=str(value), value_norm=str(value),
        url="https://www.applyhome.co.kr/notice", checked_at="2026-10-07", label=label, source_rank=1,
        chosen=True, excerpt=f"{field} {value}",
    )  # fmt: skip
    s.add(fp)
    s.flush()
    return fp


def _demote(s: Any, cx: int, entity: str, entity_id: int, field: str, *, value_norm: str | None, original: int | None,
            restored: bool = False) -> None:  # fmt: skip
    claim = Claim(snapshot_id=SNAP, section=f"complex:{cx}", complex_id=cx, text=f"{field} 모순",
                  verify_status="contradicted", ordinal=0)  # fmt: skip
    s.add(claim)
    s.flush()
    s.add(
        FactDemotion(
            claim_id=claim.id, snapshot_id=SNAP, complex_id=cx, entity=entity, entity_id=entity_id, field=field,
            original_fp_id=original, demotion_fp_id=None, original_value_text=value_norm, value_norm=value_norm,
            created_at="2026-10-08T09:00:00+09:00",
            restored_at="2026-10-08T10:00:00+09:00" if restored else None, restored_by="new_source" if restored else None,
        )
    )  # fmt: skip


def _basis(s: Any, cx: int) -> ComplexType:
    from app.analysis.price_view import basis_type

    t = basis_type(list(s.scalars(select(ComplexType).where(ComplexType.complex_id == cx))))
    assert t is not None and t.max_price_won is not None, cx
    return t


def _first_terms(s: Any, cx: int) -> PaymentTerms:
    pt = s.scalars(
        select(PaymentTerms).where(PaymentTerms.complex_id == cx).order_by(PaymentTerms.id)
    ).first()
    assert pt is not None, cx
    return pt  # type: ignore[no-any-return]


def _enrich() -> None:
    """강등 오버레이·최신 공고 가격·할인·OCR 경로를 모두 지나는 상태(고정 값 — 시각 의존 없음)."""
    with get_session() as s:
        # 단지 3: 최초 공고 가격 + 새 공고(임의공급) 가격·할인(확인됨) → 현재 구매가·변동률·할인 구성
        t3 = _basis(s, 3)
        first = _first_terms(s, 3)
        won = int(t3.max_price_won or 0)
        first.price_by_type = {
            t3.type_code: {"max_price_won": won, "floor_sample_price_won": won - 9_000_000}
        }
        for item, v in (("max_price_won", won), ("floor_sample_price_won", won - 9_000_000)):
            _prov(s, "payment_terms", first.id, f"price_by_type.{t3.type_code}.{item}", v)
        new = PaymentTerms(
            complex_id=3, notice_no="R3C-2", notice_kind="임의", effective_from="2026-10-01",
            down_payment_pct=10, interim_schedule=[],
            price_by_type={t3.type_code: {"max_price_won": won + 5_000_000, "floor_sample_price_won": won - 4_000_000}},
            discount_by_type={t3.type_code: 3_000_000},
        )  # fmt: skip
        s.add(new)
        s.flush()
        _prov(s, "payment_terms", new.id, "down_payment_pct", 10)
        _prov(s, "payment_terms", new.id, "effective_from", "2026-10-01")
        _prov(s, "payment_terms", new.id, f"price_by_type.{t3.type_code}.max_price_won", won + 5_000_000)
        _prov(
            s,
            "payment_terms",
            new.id,
            f"price_by_type.{t3.type_code}.floor_sample_price_won",
            won - 4_000_000,
        )
        _prov(s, "payment_terms", new.id, f"discount_by_type.{t3.type_code}", 3_000_000)
        # 단지 2: 전매제한 강등(단지 필드) — 목록 전매 종료일이 '확인 불가(검증 모순)'
        cx2 = 2
        fp = _prov(s, "complex", cx2, "resale_months", 12)
        from app.models import Complex

        c2 = s.get(Complex, cx2)
        assert c2 is not None
        if c2.winner_date is None:
            c2.winner_date = "2026-09-01"
            _prov(s, "complex", cx2, "winner_date", "2026-09-01")
        c2.resale_months = 12
        for old in s.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "complex", FieldProvenance.entity_id == cx2,
                FieldProvenance.field == "resale_months", FieldProvenance.id != fp.id,
            )
        ):  # fmt: skip
            old.chosen = False
        _demote(s, cx2, "complex", cx2, "resale_months", value_norm="12", original=fp.id)
        # 단지 4: 기준 타입 공고문 가격 강등(옛 출처 행 — value_norm 없음, original 이 chosen)
        t4 = _basis(s, 4)
        fp4 = _chosen(s, "complex_type", t4.id, "max_price_won")
        _demote(s, 4, "complex_type", t4.id, "max_price_won", value_norm=None, original=fp4.id)
        # 단지 5: 현재 공고 가격 강등(M-4)
        t5 = _basis(s, 5)
        p5 = _first_terms(s, 5)
        won5 = int(t5.max_price_won or 0) + 1_000_000
        p5.price_by_type = {t5.type_code: {"max_price_won": won5}}
        fp5 = _prov(s, "payment_terms", p5.id, f"price_by_type.{t5.type_code}.max_price_won", won5)
        _demote(
            s,
            5,
            "payment_terms",
            p5.id,
            f"price_by_type.{t5.type_code}.max_price_won",
            value_norm=str(won5),
            original=fp5.id,
        )
        # 단지 6: 새 출처가 다른 값 → 풀린 강등(pending) / 단지 8: 복원된 강등 — 둘 다 표시에 영향 없음
        fp6 = _chosen(s, "complex", 6, "units_total")
        _demote(s, 6, "complex", 6, "units_total", value_norm="999999", original=None)
        fp8 = _chosen(s, "complex", 8, "units_total")
        _demote(s, 8, "complex", 8, "units_total", value_norm=fp8.value_norm, original=fp8.id, restored=True)
        assert fp6.id != fp8.id
        # 단지 7: 판정기 추출 전 OCR 가격(라벨 추정·reason OCR) — 화면은 '추정', 점수 입력에서 가려짐
        t7 = _basis(s, 7)
        fp7 = _chosen(s, "complex_type", t7.id, "max_price_won")
        fp7.label, fp7.reason = "추정", "OCR"


def _build(src: Path, dst: Path, raw_dir: Path, reports: Path, kind: str) -> Path:
    shutil.copyfile(src, dst)
    settings = make_settings(dst, raw_dir, reports)
    set_settings(settings)
    try:
        if kind in (
            "rich",
            "synth",
        ):  # synth = rich + 합성 1,000단지(지역 하위 질의 경로에서도 강등·가격 경로)
            _enrich()
        if kind == "synth":
            from app.api import devseed

            assert devseed.load_synth(settings, n=1000, snapshot_id=SNAP) == 1000
            assert _score_synth(SNAP) >= 1000
    finally:
        set_settings(None)
        reset_engine()
    return dst


@pytest.fixture(scope="module")
def states(seeded_db: Seeded, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    base = tmp_path_factory.mktemp("r3c_states")
    return {
        kind: _build(seeded_db.db, base / f"{kind}.db", seeded_db.raw_dir, base / "reports", kind)
        for kind in ("plain", "rich", "synth")
    }


@pytest.fixture
def use_db(seeded_db: Seeded, tmp_path: Path) -> Iterator[Any]:
    """``use_db(path)`` → 그 DB 복사본의 Settings(테스트 끝에 설정·엔진 정리)."""

    def make(path: Path) -> Settings:
        db = tmp_path / path.name
        shutil.copyfile(path, db)
        settings = make_settings(db, seeded_db.raw_dir, tmp_path / "reports")
        set_settings(settings)
        return settings

    try:
        yield make
    finally:
        set_settings(None)
        reset_engine()


# ====================================================================== 1. 골든


def _digest(name: str, body: bytes) -> dict[str, Any]:
    """응답 sha256·길이. 대시보드는 수집 신선도(``kpis.data_freshness.stale_sources`` — 지금 시각 기준 경과)만 빼고 본다."""
    if name.startswith("dashboard"):
        doc = json.loads(body)
        doc["kpis"]["data_freshness"]["stale_sources"] = None
        body = json.dumps(doc, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}


def test_list_responses_match_golden(states: dict[str, Path], use_db: Any) -> None:
    from app.main import create_app

    got: dict[str, dict[str, Any]] = {}
    bodies: dict[str, bytes] = {}
    for kind, path in states.items():
        settings = use_db(path)
        reset_engine()
        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            for name, url, params in CASES:
                if kind not in ONLY.get(name, ALL):
                    continue
                r = client.get(url, params=params, headers=WRITE)
                assert r.status_code == 200, (kind, name, r.text[:300])
                key = f"{kind}:{name}"
                got[key] = _digest(name, r.content)
                if (kind, name) in FULL_BODIES:
                    bodies[FULL_BODIES[(kind, name)]] = r.content
    # 골든이 실제로 강등·합성 경로를 지난다(상태가 의미 있다)
    rich = json.loads(bodies["rich_size1000.json"])
    assert any(
        it["resale_end"]["label"] == "확인 불가" and it["resale_end"].get("reason") == "검증 모순"
        for it in rich["items"]
    )
    assert any(it["price_high"].get("reason") == "검증 모순" for it in rich["items"])
    if UPDATE:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        BODIES.mkdir(parents=True, exist_ok=True)
        text = json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        GOLDEN.write_bytes(text.encode("utf-8"))
        for fname, body in bodies.items():
            (BODIES / fname).write_bytes(body)
        pytest.skip("golden updated (UPDATE_GOLDEN=1)")
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for fname, body in bodies.items():
        stored = (BODIES / fname).read_bytes()
        assert body == stored, f"{fname}: 본문이 골든과 다르다(snapshots/list_r3c/{fname})"
    diff = {k: (want.get(k), v) for k, v in got.items() if want.get(k) != v}
    assert not diff, f"골든과 다른 응답: {sorted(diff)}"
    assert set(want) == set(got)


# ====================================================================== 2. 성능


def test_cold_size1000_with_scores_under_half_second(states: dict[str, Path], use_db: Any) -> None:
    from app.main import create_app

    settings = use_db(states["synth"])
    times: list[float] = []
    for run in range(COLD_RUNS):
        reset_engine()  # cold: 커넥션 풀·문장 캐시 없이 새 앱
        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            t0 = time.perf_counter()
            r = client.get(LIST, params={"size": 1000}, headers=WRITE)
            times.append(time.perf_counter() - t0)
            assert r.status_code == 200, r.text[:300]
            if run == 0:
                body = r.json()
                assert len(body["items"]) == 1000 and body["total"] >= 1000
                assert sum(it["total"]["label"] != "확인 불가" for it in body["items"]) >= 1000, (
                    "점수 행이 있다"
                )
    median = statistics.median(times)
    print("R3c cold size=1000 (s):", [round(t, 3) for t in times], "median", round(median, 3))
    assert median < LIMIT_S, times
