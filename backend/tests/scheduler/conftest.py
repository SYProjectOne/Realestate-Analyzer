"""WP7 스케줄러 테스트 공용 fixture.

- ``SynthJev``: JEV 응답 모양을 결정적으로 만들어 주는 가짜 전송(Transport). 실제 호출 수를 센다(T8·T17).
  ``JevMcpAdapter(transport=SynthJev())`` 로 쓰면 guard·캐시·judgment_log 가 실제 경로 그대로 돈다.
- ``seed_fixture``: contracts/fixtures/incheon_gimpo_2026-10-08 (region·complexes·provenance)을 DB 에 적재
  (테스트 전용 로더 — WP5 devseed 와 독립). 지역명은 픽스처 파일에만 있다(AGENTS 규칙 15).
- ``RowsCollector``: 원문 행을 넣고 돌려주는 가짜 수집기(같은 sha256 이면 기존 행 — 실제 수집기와 같은 멱등).
- ``Clock``: ctx.today/now 를 테스트가 정한다.
"""

# ruff: noqa: E501  (한국어 docstring·픽스처 행)

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.scenarios import BUILTIN_SCENARIOS
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.protocols import JudgeUnavailable
from app.core.time import KST
from app.judge.base import ToolResponse
from app.judge.jev_mcp import JevMcpAdapter
from app.models import (
    Benchmark,
    ComplexType,
    FieldProvenance,
    IntakeStatus,
    PaymentTerms,
    RawDocument,
    Region,
    RtmsTrade,
    Scenario,
    Snapshot,
    Supply,
    Unsold,
)
from app.models import Complex as ComplexRow
from app.scheduler.context import SchedulerContext
from app.scheduler.notify import Notifier

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "contracts" / "fixtures" / "incheon_gimpo_2026-10-08"
REFERENCE_COPY = REPO / "contracts" / "fixtures" / "reference"
APPLYHOME_RECORDING = (
    REPO / "backend" / "tests" / "collectors" / "applyhome" / "fixtures" / "applyhome_2026-10-09.zip"
)


def _h(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


# ---------------------------------------------------------------- 가짜 JEV


@dataclass
class SynthJev:
    """JEV 0.14.x 응답 모양을 payload 에서 결정적으로 만든다. ``calls`` = 판정기로 실제 간 호출."""

    version: str = "0.14.1"
    model: str = "jev-1.13.0"
    down: bool = False
    verdict: str = "verified"
    calls: list[str] = field(default_factory=list)

    def server_version(self) -> str:
        if self.down:
            raise JudgeUnavailable("synth: down")
        return self.version

    def close(self) -> None:
        return None

    def call(self, tool_name: str, arguments: dict[str, Any]) -> ToolResponse:
        if self.down:
            raise JudgeUnavailable("synth: down")
        self.calls.append(tool_name)
        fn = getattr(self, "_" + tool_name.removeprefix("jev_"))
        raw = {"tool": tool_name, "model": self.model, **fn(arguments)}
        return ToolResponse(raw=raw, is_error=False, duration_ms=3)

    # --- 도구별
    def _screen(self, a: dict[str, Any]) -> dict[str, Any]:
        return {
            "probabilities": {"injection": 0.01, "substance": 0.97, "relevance": 0.97},
            "recommendation": {"action": "pass"},
        }

    def _extract(self, a: dict[str, Any]) -> dict[str, Any]:
        return {
            "results": [
                {"id": f["id"], "value": None, "status": "not_found", "confidence": 0.9} for f in a["fields"]
            ]
        }

    def _audit(self, a: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": "pass",
            "records": [{"id": r["id"], "action": "ok", "p_wrong": 0.05} for r in a["records"]],
        }

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        first = a["classes"][0]["id"]
        return {
            "results": [
                {
                    "id": it["id"],
                    "classification": first,
                    "probabilities": {first: 0.96},
                    "top_probability": 0.96,
                    "confidence": 0.95,
                    "decision": "auto",
                }
                for it in a["items"]
            ]
        }

    def _compare(self, a: dict[str, Any]) -> dict[str, Any]:
        return {
            "overall": {
                "relation": "same_fact",
                "probabilities": {"same_fact": 0.9},
                "confidence": 0.9,
                "decision": "auto",
            },
            "aspects": [],
        }

    def _noul(self, a: dict[str, Any]) -> dict[str, Any]:
        out = []
        for i, p in enumerate(a["propositions"]):
            base = 0.25 + (_h(p[:60]) % 40) / 100
            prob = round(base - 0.1 * i if i < 3 else 1 - base, 2)
            prob = min(0.95, max(0.05, prob))
            label = "likely" if prob >= 0.6 else "unlikely" if prob <= 0.3 else "uncertain"
            out.append(
                {"id": f"proposition{i}", "proposition": p, "probability": prob, "label": label, "auto": True}
            )
        return {"status": "ok", "results": out}

    def _rerank(self, a: dict[str, Any]) -> dict[str, Any]:
        cands = sorted(a["candidates"], key=lambda c: _h(c["text"]))
        n = len(cands)
        return {
            "query": a["query"],
            "ranked": [
                {"rank": i + 1, "id": c["id"], "relevance": round(0.95 - 0.8 * i / max(1, n - 1), 3)}
                for i, c in enumerate(cands)
            ],
        }

    def _decide(self, a: dict[str, Any]) -> dict[str, Any]:
        ids = [c["id"] for c in a["candidates"]]
        probs = {cid: round(0.6 / (i + 1), 3) for i, cid in enumerate(ids)}
        probs.update({"ask_user": 0.02, "investigate": 0.01})
        checks = [
            {"candidate": cid, "requirement": j, "answer": "supported"}
            for cid in ids
            for j in range(len(a["requirements"]))
        ]
        return {
            "recommendation": {
                "selected": ids[0],
                "escaped": False,
                "confidence": 0.8,
                "probabilities": probs,
            },
            "checks": checks,
            "warnings": [],
        }

    def _verify(self, a: dict[str, Any]) -> dict[str, Any]:
        return {
            "results": [
                {"id": f"claim{i}", "claim": c, "verdict": self.verdict, "confidence": 0.95, "action": "auto"}
                for i, c in enumerate(a["claims"])
            ]
        }


# ---------------------------------------------------------------- 시계·수집기


@dataclass
class Clock:
    day: date = date(2026, 10, 8)

    def today(self) -> date:
        return self.day

    def now(self) -> datetime:
        return datetime(self.day.year, self.day.month, self.day.day, 6, 0, tzinfo=KST)


@dataclass
class RowsCollector:
    """원문 행(dict, raw_document 컬럼)을 넣고 DTO 로 돌려준다. sha256 이 같으면 기존 행."""

    factory: sessionmaker[Session]
    rows: list[dict[str, Any]]
    fetched: int = 0

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        from app.normalize.store import raw_dto

        self.fetched += 1
        out: list[RawDTO] = []
        with self.factory() as s:
            for r in self.rows:
                row = s.scalars(select(RawDocument).where(RawDocument.sha256 == r["sha256"])).first()
                if row is None:
                    row = RawDocument(**{k: v for k, v in r.items() if k != "id"})
                    s.add(row)
                    s.flush()
                out.append(raw_dto(row))
            s.commit()
        return out


def popup_row(key: str) -> dict[str, Any]:
    """t8_popup_pairs.json 의 yesterday·today_same·today_changed → raw_document 컬럼."""
    pairs = json.loads(
        (FIXTURE / "raw" / "official_site" / "t8_popup_pairs.json").read_text(encoding="utf-8")
    )
    d = dict(pairs[key])
    d.pop("id", None)
    return d


# ---------------------------------------------------------------- 픽스처 적재


def _v(fact: Any) -> Any:
    return fact.get("v") if isinstance(fact, dict) else fact


def seed_scenarios(s: Session) -> None:
    for sc in BUILTIN_SCENARIOS:
        s.add(
            Scenario(
                id=sc.id,
                code=sc.code,
                name=sc.name,
                is_builtin=True,
                params=sc.params.model_dump(mode="json"),
                weights={k: v for k, v in sc.weights.model_dump().items() if v is not None},
                requirements=sc.requirements.model_dump(mode="json"),
                policy=sc.policy.model_dump(mode="json"),
                created_at=sc.created_at or "2026-10-09T00:00:00+09:00",
            )
        )


def seed_region(s: Session, **overrides: Any) -> Region:
    r = json.loads((FIXTURE / "region.json").read_text(encoding="utf-8"))
    r.update(overrides)
    row = Region(
        id=r["id"],
        name=r["name"],
        query_text=r["query_text"],
        selections=r["selections"],
        sido_codes=r["sido_codes"],
        sigungu_codes=r["sigungu_codes"],
        legal_dong_codes=r["legal_dong_codes"],
        living_areas=r["living_areas"],
        age_premium_coef=r["age_premium_coef"],
        supply_ref_pct=Decimal(str(r["supply_ref_pct"])),
        applyhome_query={},
        status=r.get("status", "ready"),
        created_at=r["created_at"],
    )
    s.add(row)
    s.flush()
    return row


def seed_fixture(
    factory: sessionmaker[Session], *, asof: str = "2026-10-07", status: str = "building"
) -> int:
    """지역·시나리오·단지 16개·타입·납부 조건·출처·접수 상태(스냅샷 1개)를 넣는다. 스냅샷 id 를 돌려준다."""
    prov = {p["id"]: p for p in json.loads((FIXTURE / "provenance.json").read_text(encoding="utf-8"))}
    bundles = json.loads((FIXTURE / "complexes.json").read_text(encoding="utf-8"))
    with factory() as s:
        seed_scenarios(s)
        region = seed_region(s)
        snap = Snapshot(
            region_id=region.id,
            asof_date=asof,
            status=status,
            degraded=False,
            created_at=f"{asof}T06:00:00+09:00",
        )
        s.add(snap)
        s.flush()

        def add_prov(entity: str, entity_id: int, field_name: str, fact: Any) -> None:
            if not isinstance(fact, dict) or not fact.get("prov") or not str(fact["prov"]).startswith("fp_"):
                return
            p = prov.get(fact["prov"])
            if p is None:
                return
            s.add(
                FieldProvenance(
                    entity=entity,
                    entity_id=entity_id,
                    field=field_name,
                    value_text=p.get("value_text"),
                    url=p.get("url"),
                    checked_at=p.get("checked_at"),
                    label=p["label"],
                    reason=p.get("reason"),
                    source_rank=p.get("source_rank") or 1,
                    chosen=bool(p.get("chosen", True)),
                    conflict_group=p.get("conflict_group"),
                    excerpt=p.get("excerpt"),
                )
            )

        for b in bundles:
            c = b["complex"]
            reg = _v(c["resale_release_on_registration"])
            cx = ComplexRow(
                id=c["id"],
                region_id=region.id,
                applyhome_id=c["applyhome_id"],
                name=c["name"],
                former_names=c["former_names"],
                address=c["address"],
                legal_dong_code=c["legal_dong_code"],
                living_area=c["living_area"],
                official_site_url=c["official_site_url"],
                housing_type=_v(c["housing_type"]),
                land_type=_v(c["land_type"]),
                price_cap=_v(c["price_cap"]),
                regulated=_v(c["regulated"]),
                units_total=_v(c["units_total"]),
                notice_date=_v(c["notice_date"]),
                apply_dates=[],
                winner_date=_v(c["winner_date"]),
                contract_dates=[],
                move_in_ym=_v(c["move_in_ym"]),
                resale_months=_v(c["resale_months"]),
                resale_release_on_registration=None if reg is None else reg == "등기 시 해제",
                residency_months=_v(c["residency_months"]),
                rewin_restriction_years=_v(c["rewin_restriction_years"]),
                inclusion_class="미분류",
                track=c.get("track"),
            )
            s.add(cx)
            s.flush()
            for f in ("resale_months", "residency_months", "move_in_ym", "units_total", "winner_date"):
                add_prov("complex", cx.id, f, c.get(f))
            for t in b["types"]:
                area = _v(t["area_m2"])
                ct = ComplexType(
                    complex_id=cx.id,
                    type_code=t["type_code"],
                    area_m2=Decimal(str(area)) if area is not None else None,
                    units=_v(t["units"]),
                    max_price_won=_v(t["max_price_won"]),
                    floor_sample_price_won=_v(t["floor_sample_price_won"]),
                    floor_sample_text=t.get("floor_sample_text"),
                    balcony_won=_v(t["balcony_won"]),
                    options_required_won=_v(t["options_required_won"]),
                    options_text=t.get("options_text"),
                )
                s.add(ct)
                s.flush()
                for f in ("max_price_won", "floor_sample_price_won", "balcony_won"):
                    add_prov("complex_type", ct.id, f, t.get(f))
            for p in b["payment_terms"]:
                dp = _v(p["down_payment_pct"])
                pt = PaymentTerms(
                    complex_id=cx.id,
                    notice_no=p["notice_no"],
                    notice_kind=p.get("notice_kind"),
                    effective_from=_v(p["effective_from"]) or asof,
                    down_payment_pct=Decimal(str(dp)) if dp is not None else None,
                    interim_terms_text=p.get("interim_terms_text"),
                    interim_schedule=p.get("interim_schedule") or [],
                )
                s.add(pt)
                s.flush()
                add_prov("payment_terms", pt.id, "down_payment_pct", p.get("down_payment_pct"))
            for i in b["intake"]:
                s.add(
                    IntakeStatus(
                        complex_id=cx.id,
                        snapshot_id=snap.id,
                        status=i["status"],
                        path=i["path"],
                        evidence_url=i.get("evidence_url"),
                        http_status=i.get("http_status"),
                        checked_at=i["checked_at"],
                        reason=i.get("reason"),
                        note=i.get("note"),
                    )
                )
        s.commit()
        return snap.id


def seed_market(factory: sessionmaker[Session], region_id: int = 1) -> None:
    """expected_scores_v2.json 의 시장 입력(거래·벤치마크·입주물량·미분양·세대수 가정)을 DB 행으로.

    v2 입력의 생활권 id(시군구 코드) → 픽스처 지역 생활권(la_*)으로 바꾼다. 세대수는 v2 가정값(라벨 추정).
    """
    v2 = json.loads((FIXTURE / "expected_scores_v2.json").read_text(encoding="utf-8"))["inputs"]
    with factory() as s:
        region = s.get(Region, region_id)
        assert region is not None
        areas = [dict(a) for a in region.living_areas]
        by_code = {a["legal_dong_codes"][0][:5]: a for a in areas}
        la = {code: a["id"] for code, a in by_code.items()}
        first_dong = {code: a["legal_dong_codes"][0] for code, a in by_code.items()}
        for item in v2["living_areas"]:
            a = by_code.get(item["id"])
            if a is not None and item["households"] is not None:
                a["households"] = {
                    "v": item["households"], "label": "추정", "reason": "v2 가정값", "prov": "rd_0",
                    "checked_at": "2026-10-07",
                }  # fmt: skip
        region.living_areas = areas
        for t in v2["trades"]:
            s.add(
                RtmsTrade(
                    region_id=region_id, apt_name=t["apt_name"], legal_dong_code=first_dong.get(t["living_area"]),
                    completed_year=t["completed_year"], area_m2=Decimal(str(t["area_m2"])), floor=t["floor"],
                    price_won=t["price_won"], deal_date=t["deal_date"], cancelled=t["cancelled"],
                    is_presale=t["is_presale"], source=t["source"],
                )
            )  # fmt: skip
        for b in v2["benchmarks"]:
            s.add(
                Benchmark(
                    region_id=region_id, living_area=la.get(b["living_area"]), name=b["name"],
                    completed_year=b["completed_year"], sale_year=b["sale_year"],
                    sale_price_84_won=b["sale_price_84_won"], sale_price_label=b["label"],
                    trade_median_won=b["trade_median_won"], is_presale=b["is_presale"],
                )
            )  # fmt: skip
        for u in v2["supply"]:
            s.add(
                Supply(
                    region_id=region_id, living_area=la.get(u["living_area"]), year=u["year"], ym=u["ym"],
                    units=u["units"], label=u["label"], complex_id=u["complex_id"],
                )
            )  # fmt: skip
        for u in v2["unsold"]:
            s.add(
                Unsold(
                    region_id=region_id, scope_code=u["scope_code"], ym=u["ym"], total=u["total"],
                    post_completion=u["post_completion"], source_label=u["label"],
                )
            )  # fmt: skip
        s.commit()


# ---------------------------------------------------------------- 문맥


@pytest.fixture
def factory(db_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture
def jev() -> SynthJev:
    return SynthJev()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def make_ctx(
    factory: sessionmaker[Session], jev: SynthJev, clock: Clock
) -> Iterator[Callable[..., SchedulerContext]]:
    made: list[SchedulerContext] = []

    def _make(**kw: Any) -> SchedulerContext:
        def adapter() -> JevMcpAdapter:
            return JevMcpAdapter(transport=jev, session_factory=factory, secrets=[])

        ctx = SchedulerContext(
            session_factory=factory,
            adapter_factory=kw.pop("adapter_factory", adapter),
            collectors=kw.pop("collectors", {}),
            reference_refresh=kw.pop("reference_refresh", lambda d: {"skipped": "test"}),
            probe_judge=kw.pop("probe_judge", None),
            notifier=kw.pop("notifier", Notifier()),
            today=clock.today,
            now=clock.now,
            worker_id=kw.pop("worker_id", "test-worker"),
        )
        made.append(ctx)
        return ctx

    yield _make
    for c in made:
        c.reset_adapter()


@pytest.fixture
def seeded(factory: sessionmaker[Session], test_settings: Any) -> int:
    """픽스처 지역·단지·시장 자료(스냅샷 2026-10-07, building). 스냅샷 id."""
    sid = seed_fixture(factory)
    seed_market(factory)
    return sid
