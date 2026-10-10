"""R3c 성능: 점수 행이 있는 합성 1,000단지 ``/complexes?size=1000`` cold 첫 요청 0.5초 + 목록 응답 골든.

1. 골든(``test_list_responses_match_golden``): 목록(G2)·CSV 응답 바이트가 최적화(``api.views`` 목록 경로) 전과 같다.
   세 DB 상태 — ``plain``(devseed 그대로) · ``rich``(최신 공고 가격·할인·두 번째 공고·강등 3종(단지·타입·공고 가격)·
   풀린 강등·복원된 강등·OCR 값) · ``synth``(rich + 합성 1,000단지 + 점수 행 — 지역 하위 질의·읽기 전용 행 경로) — 에서
   기본 페이지·size=1000·정렬·필터·시나리오·과거 스냅샷·CSV 응답의 sha256 을 ``snapshots/list_r3c.json`` 과 비교한다.
   같은 ``views`` 함수를 쓰는 다른 화면(대시보드·시장·비교·상세·미리보기)도 같이 고정한다(목록 최적화가 그 응답을 바꾸지
   않는다). ``rich`` 의 size=1000 JSON·CSV 는 본문 전체도 ``snapshots/list_r3c/`` 에 둔다(차이가 나면 읽을 수 있게).
   의도한 응답 변경이면 ``UPDATE_GOLDEN=1`` 로 다시 쓴다(최적화 전 코드로 만든 값이다).
2. 성능: 새 엔진·새 앱의 첫 요청(cold) size=1000 을 ``COLD_RUNS`` 번 재서 중앙값.
   - 발행 리비전(``test_cold_size1000_published_under_0_2s``, D13-1 저장본 — 압축 JSON 읽기·필터·페이지만) < 0.2초.
   - 실시간 계산(``test_cold_size1000_live_revision``, 발행 전 리비전 — 묶음 적재·점수 문맥·Fact 1,000행) < ``LIVE_LIMIT_S``.
     기준 근거(R3e, 이 PC·부하 측정): 무부하 중앙값 0.44~0.50초, 전체 테스트 병행(부하) 0.69초(R3 5차 리뷰 보고
     0.498/0.692/0.438) — 경계에 붙지 않게 1.5초(최악 측정의 2배 넘는 여유). 회귀(수 초)는 여전히 잡힌다.

D13-1(계약 .10): 상태 DB 를 만든 뒤 발행 스냅샷 저장본을 다시 만든다(``devseed.rematerialize``) — 골든은 저장본을 읽는
GET 이 예전 실시간 응답과 바이트가 같음(저장본 생성 = 같은 계산, 목록 질의 = 같은 필터·정렬·페이지)을 함께 고정한다.
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
LIMIT_S = 0.2  # 발행 리비전(저장본)
LIVE_LIMIT_S = 1.5  # 실시간 계산(발행 전 리비전) — 근거는 모듈 설명
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
    # R3 4차 minor: 미확인(추정) 할인·OCR 할인(차감 안 함)·대체 벤치마크(시장 표·gap) 경로도 골든으로
    ("detail_9", "/api/complexes/9", {"snapshot": SNAP}),
    ("detail_10", "/api/complexes/10", {"snapshot": SNAP}),
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
            restored_at="2026-10-08T10:00:00+09:00" if restored else None, restored_by="human_check" if restored else None,
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
        # 단지 6: 새 출처가 다른 값 → 풀린 강등(pending) / 단지 8: 사람 확인으로 복원된 강등 — 둘 다 표시에 영향 없음
        # (새 출처로 풀린 강등은 모순 값이 다시 chosen 이면 다시 가린다 — R3 4차 M-17, 그래서 여기는 사람 확인 복원)
        fp6 = _chosen(s, "complex", 6, "units_total")
        _demote(s, 6, "complex", 6, "units_total", value_norm="999999", original=None)
        fp8 = _chosen(s, "complex", 8, "units_total")
        _demote(s, 8, "complex", 8, "units_total", value_norm=fp8.value_norm, original=fp8.id, restored=True)
        assert fp6.id != fp8.id
        # 단지 7: 판정기 추출 전 OCR 가격(라벨 추정·reason OCR) — 화면은 '추정', 점수 입력에서 가려짐
        t7 = _basis(s, 7)
        fp7 = _chosen(s, "complex_type", t7.id, "max_price_won")
        fp7.label, fp7.reason = "추정", "OCR"
        # 단지 9: 미확인(추정) 할인 / 단지 10: OCR 할인 — 둘 다 표시만, 구매가에서 빼지 않는다(D11-6·D12-3)
        for cx_id, label, reason in ((9, "추정", "공고문 할인 문구 해석"), (10, "추정", "OCR")):
            tb = _basis(s, cx_id)
            pt = _first_terms(s, cx_id)
            pt.discount_by_type = {tb.type_code: 4_000_000}
            fpd = _prov(s, "payment_terms", pt.id, f"discount_by_type.{tb.type_code}", 4_000_000, label=label)
            fpd.reason = reason
        # 대체 벤치마크(D9-2: 생활권 자체 표본 0 → 지역 전체 대체, 라벨 추정) — 시장 표·gap 사유
        from app.models import Benchmark

        bench = s.scalars(
            select(Benchmark).where(Benchmark.is_presale.is_(False)).order_by(Benchmark.id)
        ).first()
        assert bench is not None
        bench.substitute = True
        bench.note = "추정(대체: 지역 전체)"


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
        from app.api import devseed

        if kind == "synth":
            assert devseed.load_synth(settings, n=1000, snapshot_id=SNAP) == 1000
            assert _score_synth(SNAP) >= 1000
        with get_session() as s:  # 바꾼 상태로 발행 스냅샷 저장본을 다시(D13-1)
            devseed.rematerialize(s, settings=settings)
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


def _cold_size1000(settings: Settings) -> list[float]:
    from app.main import create_app

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
    return times


def test_cold_size1000_published_under_0_2s(states: dict[str, Path], use_db: Any) -> None:
    """발행 리비전 목록 = 저장본(D13-1) — 실시간 계산 없이 0.2초 안(CEO R3e 지시)."""
    times = _cold_size1000(use_db(states["synth"]))
    median = statistics.median(times)
    print("R3e published cold size=1000 (s):", [round(t, 3) for t in times], "median", round(median, 3))
    assert median < LIMIT_S, times


def test_cold_size1000_live_revision(states: dict[str, Path], use_db: Any) -> None:
    """발행 전 리비전(실시간 계산) 목록 — 기준 ``LIVE_LIMIT_S``(근거는 모듈 설명)."""
    from ._support import as_live

    settings = use_db(states["synth"])
    as_live()
    times = _cold_size1000(settings)
    median = statistics.median(times)
    print("R3e live cold size=1000 (s):", [round(t, 3) for t in times], "median", round(median, 3))
    assert median < LIVE_LIMIT_S, times
