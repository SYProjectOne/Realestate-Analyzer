"""R3 C1 실데이터: 인천·김포 픽스처 지역으로 실제 청약홈 API(과거 10년)·rtms(36개월)를 받아 벤치마크를 만든다.

실행(키는 출력·커밋하지 않는다):
    ENV_FILE=<메인 체크아웃>/.env uv run pytest -m live tests/scheduler/test_assemble_live_f1a.py -s

생활권별 표본 수·대체 생활권·매칭 실패 사유를 출력한다(보고서용). 표본 수는 실제 데이터에 따라 바뀌므로 단언하지
않는다 — 단언은 '수집이 실패 행 없이 돌고, 조립이 예외 없이 끝나며, 만든 행마다 출처가 있다'까지.
"""

# ruff: noqa: E501  (한국어 docstring·출력)

from __future__ import annotations

import json
import os
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.applyhome import ApplyhomeCollector
from app.collectors.reference.legal_dong import parse_legal_dong_zip
from app.collectors.reference.load import upsert_legal_dongs
from app.collectors.rtms import RtmsCollector
from app.models import Benchmark, FieldProvenance, Region, Snapshot
from app.normalize.benchmark import BENCHMARK_FIELDS, build_benchmarks
from app.scheduler import snapshots
from app.scheduler.assemble import BENCHMARK_HISTORY_YEARS, RTMS_BACKFILL_MONTHS

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "contracts" / "fixtures" / "incheon_gimpo_2026-10-08"
REFERENCE = REPO / "contracts" / "fixtures" / "reference"
ASOF = "2026-10-08"


def _live_key() -> str | None:
    from app.core.settings import load_settings

    secret = load_settings().data_go_kr_key
    value = secret.get_secret_value() if secret is not None else None
    return value or os.environ.get("DATA_GO_KR_KEY")


@pytest.mark.live
def test_live_benchmark_samples_incheon_gimpo(db_session: Session, raw_dir: Path) -> None:
    key = _live_key()
    if not key:
        pytest.skip("DATA_GO_KR_KEY 없음 (ENV_FILE 로 .env 경로를 준다)")
    upsert_legal_dongs(
        db_session,
        parse_legal_dong_zip((REFERENCE / "legal_dong_full.zip").read_bytes()),
        source_date="2026-09-01",
    )
    r = json.loads((FIXTURE / "region.json").read_text(encoding="utf-8"))
    region = Region(
        id=r["id"], name=r["name"], query_text=r["query_text"], selections=r["selections"], sido_codes=r["sido_codes"],
        sigungu_codes=r["sigungu_codes"], legal_dong_codes=r["legal_dong_codes"], living_areas=r["living_areas"],
        age_premium_coef=r["age_premium_coef"], supply_ref_pct=Decimal(str(r["supply_ref_pct"])), applyhome_query={},
        status="ready", created_at=r["created_at"],
    )  # fmt: skip
    db_session.add(region)
    snap = Snapshot(
        region_id=region.id,
        asof_date=ASOF,
        status="building",
        degraded=False,
        created_at=f"{ASOF}T06:00:00+09:00",
    )
    db_session.add(snap)
    db_session.commit()
    region_dto, snap_dto = snapshots.region_dto(region), snapshots.snapshot_dto(snap)

    ah = ApplyhomeCollector(session=db_session, service_key=key)
    hist = ah.fetch_history(region_dto, snap_dto, years=BENCHMARK_HISTORY_YEARS)
    db_session.commit()
    assert hist and all(d.http_status == 200 for d in hist), Counter(d.http_status for d in hist)
    assert all(key not in d.url for d in hist)

    rt = RtmsCollector(service_key=key, months=1)
    back = rt.backfill(region_dto, snap_dto, months=RTMS_BACKFILL_MONTHS)
    bad = [(d.url, d.http_status, d.error_text) for d in back if d.http_status != 200]
    assert not bad, bad[:5]

    res = build_benchmarks(db_session, region.id, asof_date=ASOF)
    db_session.commit()
    rows = list(db_session.scalars(select(Benchmark).order_by(Benchmark.living_area, Benchmark.id)))
    names = {a["id"]: a["name"] for a in region.living_areas}
    print("\n== 청약홈 과거 공고:", ah.history_stats)
    print("== rtms 과거 월: 원문", len(back), "적재", rt.load_stats)
    print("== 생활권별 자체 표본(분양권 제외):", {f"{k} {names.get(k)}": v for k, v in res.samples.items()})
    print("== 지역 전체 대체:", [f"{k} {names.get(k)}" for k in res.substituted])
    print("== 매칭 실패 사유:", Counter(u["reason"] for u in res.unmatched))
    for b in rows:
        if b.note and "대체" in b.note:
            continue
        print(
            f"  {b.living_area} {b.name} 분양 {b.sale_year}({b.sale_period}) {b.sale_price_84_won:,} → 중앙 {b.trade_median_won:,} ({b.n_trades}건 {b.trade_window}) presale={b.is_presale}"
        )
    for u in res.unmatched[:40]:
        print("  미매칭:", u)
    for b in rows:
        for f in BENCHMARK_FIELDS:
            if getattr(b, f) is None:
                continue
            fp = db_session.scalars(
                select(FieldProvenance).where(
                    FieldProvenance.entity == "benchmark", FieldProvenance.entity_id == b.id,
                    FieldProvenance.field == f, FieldProvenance.chosen.is_(True),
                )
            ).first()  # fmt: skip
            assert fp is not None and fp.url and fp.label, (b.name, f)
