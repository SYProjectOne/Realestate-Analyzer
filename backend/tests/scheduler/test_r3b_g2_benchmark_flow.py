"""R3b G2 통합: 벤치마크 생성(collect.weekly → assemble → normalize.benchmark) → 종합 점수(pipeline) — 실데이터 녹화 기반.

- 실거래: WP1b 녹화 ``tests/collectors/rtms/fixtures/openapi_trade_28185_202609.xml``(국토부 OpenAPI 실제 응답, 2026-09)
  → ``collectors.rtms.parse_trade_xml`` → ``load_trades``(실제 적재 경로).
- 과거 공고(청약홈 API 모양): 녹화 실거래에 있는 단지 이름·법정동 그대로 1건(분양가 84㎡ 최고가). 청약홈 API 는 2020년
  이후 자료만 주므로(assemble 주석) 과거 공고 녹화가 없다 — 이 한 건만 합성이고 나머지는 녹화·픽스처다.
- 기대: 자기 생활권(la_1) 행은 생성 행 이름 그대로, 표본 0 생활권은 지역 전체 대체 → 점수 식에 '대체(지역 전체)'(N-M4),
  생활권 표본이 생긴 단지는 종합 점수가 계산된다.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.score import SUBSTITUTE_TEXT
from app.collectors.applyhome import api as ah_api
from app.collectors.rtms.collector import load_trades
from app.collectors.rtms.parse import parse_trade_xml
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.snapshot import store_raw
from app.judge.jev_mcp import JevMcpAdapter
from app.models import Benchmark, Complex, LegalDong, RawDocument, ScoreComponent, ScoreRun, ScoreTotal
from app.normalize.benchmark import SUBSTITUTE_NOTE
from app.normalize.store import raw_dto
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext
from app.scheduler.pipeline import run_pipeline

from .conftest import REPO, SynthJev

RTMS_XML = REPO / "backend" / "tests" / "collectors" / "rtms" / "fixtures" / "openapi_trade_28185_202609.xml"
SONGDO = "2818510600"
NAME = "e편한세상송도"  # 녹화 실거래(2026-09)에 있는 단지(준공 2018, 송도동)
ASOF = "2026-10-07"


def _save(s: Session, body: dict[str, object], *, source_kind: str, url: str) -> RawDTO:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    row = s.scalars(select(RawDocument).where(RawDocument.sha256 == sha)).first()
    if row is None:
        stored = store_raw(data, source=source_kind, day=date(2026, 10, 7), ext="json")
        row = RawDocument(
            source_kind=source_kind, url=url, fetched_at=f"{ASOF}T06:00:00+09:00", http_status=200,
            sha256=stored.sha256, path=stored.relpath, content_type="application/json", region_id=1,
        )  # fmt: skip
        s.add(row)
        s.flush()
    return raw_dto(row)


@dataclass
class HistoryApplyhome:
    factory: sessionmaker[Session]

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        return []

    def fetch_history(self, region: RegionDTO, snapshot: SnapshotDTO, *, years: int) -> list[RawDTO]:
        row = {
            "HOUSE_MANAGE_NO": "2016000301", "PBLANC_NO": "2016000301", "HOUSE_NM": NAME,
            "HSSPLY_ADRES": "인천광역시 연수구 송도동 319-1", "RCRIT_PBLANC_DE": "2016-03-10", "MVN_PREARNGE_YM": "201812",
            "HOUSE_DTL_SECD_NM": "민영", "SUBSCRPT_AREA_CODE_NM": "인천",
        }  # fmt: skip
        model = {
            "HOUSE_MANAGE_NO": "2016000301",
            "PBLANC_NO": "2016000301",
            "HOUSE_TY": "084.9800A",
            "LTTOT_TOP_AMOUNT": "41000",
        }
        page = {"matchCount": 1, "page": 1, "perPage": 100}
        with self.factory() as s:
            lst = _save(
                s, {"data": [row], **page}, source_kind="applyhome_list",
                url=ah_api.doc_url(ah_api.ENDPOINTS["apt"].detail, ah_api.list_params("apt", "인천", date(2016, 10, 1), date(2026, 10, 7), 1)),
            )  # fmt: skip
            mdl = _save(
                s, {"data": [model], **page}, source_kind="applyhome_detail",
                url=ah_api.doc_url(ah_api.ENDPOINTS["apt"].model, ah_api.item_params("2016000301", "2016000301")),
            )  # fmt: skip
            s.commit()
        return [lst, mdl]


@dataclass
class RecordedRtms:
    """backfill = 녹화 OpenAPI 응답을 실제 파서·적재 함수로 rtms_trade 에."""

    factory: sessionmaker[Session]

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        return []

    def backfill(self, region: RegionDTO, snapshot: SnapshotDTO, *, months: int) -> list[RawDTO]:
        page = parse_trade_xml(RTMS_XML.read_bytes())
        assert page.items, "녹화 실거래 없음"
        with self.factory() as s:
            load_trades(s, region.id, [(None, t) for t in page.items])
            s.commit()
        return []


def test_benchmark_generation_to_total_score_from_recordings(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    with factory() as s:
        s.execute(delete(Benchmark))  # 픽스처 v2 벤치마크 대신 생성 행만
        s.add(
            LegalDong(
                code=SONGDO, sido_name="인천광역시", sigungu_name="연수구", eupmyeondong_name="송도동", ri_name=None,
                full_name="인천광역시 연수구 송도동", sigungu_code="28185", active=True, source_date="2026-09-01",
            )
        )  # fmt: skip
        s.commit()
    ctx = make_ctx(
        collectors={
            "applyhome": lambda c: HistoryApplyhome(factory),
            "rtms": lambda c: RecordedRtms(factory),
        },
        adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]),
    )
    res = collect(ctx, 1, ["rtms"], asof_date=ASOF)
    assert "assemble.benchmark" not in res.errors, res.errors
    with factory() as s:
        own = list(s.scalars(select(Benchmark).where(Benchmark.living_area == "la_1")))
        assert [b.name for b in own] == [NAME], [(b.name, b.note) for b in own]
        b = own[0]
        assert (
            b.sale_price_84_won == 410_000_000
            and b.trade_median_won
            and b.trade_median_won > b.sale_price_84_won
        )
        assert not (b.note and SUBSTITUTE_NOTE in b.note) and b.substitute is False
        subs = list(s.scalars(select(Benchmark).where(Benchmark.living_area != "la_1")))
        assert subs and all(
            x.substitute and x.note and SUBSTITUTE_NOTE in x.note for x in subs
        )  # 표본 0 생활권 = 지역 전체 대체(계약 .7 컬럼 + 설명 note)

    out = run_pipeline(ctx, seeded)
    assert not out.degraded, out.error
    with factory() as s:
        run = s.scalars(
            select(ScoreRun).where(ScoreRun.snapshot_id == seeded, ScoreRun.scenario_id == 1)
        ).one()
        comps = {
            (c.complex_id, c.component): c
            for c in s.scalars(select(ScoreComponent).where(ScoreComponent.score_run_id == run.id))
        }
        totals = {
            t.complex_id: t for t in s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == run.id))
        }
        la = {c.id: c.living_area for c in s.scalars(select(Complex).where(Complex.region_id == 1))}
        own_cx = [cid for cid, a in la.items() if a == "la_1" and (cid, "benchmark") in comps]
        other_cx = [cid for cid, a in la.items() if a != "la_1" and (cid, "benchmark") in comps]
        assert own_cx and other_cx
        for cid in own_cx:
            c = comps[(cid, "benchmark")]
            assert (
                c.score_0_10 is not None
                and NAME in (c.formula_text or "")
                and SUBSTITUTE_TEXT not in (c.formula_text or "")
            )
        for cid in other_cx:
            c = comps[(cid, "benchmark")]
            assert (
                c.score_0_10 is not None and SUBSTITUTE_TEXT in (c.formula_text or "") and c.label == "추정"
            )
        # 생성 벤치마크로 종합 점수: 판정 대상(사다리 ok)인 자기 생활권 단지의 총점이 계산되고 순위가 있다
        judged = [cid for cid in own_cx if totals[cid].judge_scope == "판정 대상"]
        assert judged and all(
            totals[cid].total is not None and totals[cid].rank is not None for cid in judged
        )
