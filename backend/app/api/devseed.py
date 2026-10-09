"""개발·e2e용 픽스처 적재기 — DB 가 비어 있어도 API·화면이 돌게 (WP5, R2).

``python -m app.api.devseed [--fixture DIR] [--reference region|full|none] [--synth N] [--no-reset]``
(``DATABASE_URL``·``RAW_DIR`` 은 환경변수/.env). 기본은 SQLite 개발 DB 를 비우고 다시 만든다.

적재 내용(모두 contracts/ 의 읽기 전용 파일에서 온다 — 판정기 호출 없음):

- 참조: ``fixtures/reference/legal_dong_full.zip``·``jscode*.zip`` → legal_dong·admin_dong·admin_legal_map
  (``region`` = 픽스처 지역의 시도만, ``full`` = 전국, ``none`` = 생략).
  수집기(WP1b)의 파서·적재 함수를 그대로 쓴다.
- 내장 시나리오 5개(마이그레이션 0001 시드와 같은 ``analysis.scenarios.BUILTIN_SCENARIOS``)가 없으면 넣는다.
- ``<fixture>/region.json``·``snapshots.json``·``raw/documents.json``(원문 파일은 RAW_DIR 로 복사)·
  ``complexes.json``(+ ``provenance.json`` → field_provenance: Fact 마다 (entity, 행 id, field) 출처 행 1개)·
  ``judgments/``(녹화 봉투 → judgment_log; 원응답 = output_json, 정규화 결과 = result_json,
  계약 2026-10-09.3).
- 사다리(noul 녹화) → ladder, 호재 분류(classify 녹화) → catalyst, decide 녹화 → decision.
- 점수: ``expected_scores_v2.json`` 의 입력(ScoreInputs, 생활권 id 는 region 의 la_* 로 맞춤)에
  ``expected_scores.json``(a)단계 구성 점수를 ``fixed_components`` 로 넣어 내장 시나리오 5개를
  ``analysis.score.run_detailed`` 로 계산 → score_run·score_component·score_total·comparable_set.
  시장 원자료(벤치마크·실거래·입주 물량·미분양)도 같은 입력에서 적재한다
  (출처 행 라벨 = 입력 라벨, reason '보고서 재구성').
- ``contracts/examples/changes.json``·``checklist.json`` → change_event·checklist_item(보고서 기반 예시).

``replace_bundles``(T13: 출처 행을 지운 단지 묶음으로 바꿔 넣기)와
``load_synth``(T16: 합성 단지 n개)도 여기 있다.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.analysis.ladder import annualized, ladder_targets
from app.analysis.scenarios import BUILTIN_SCENARIOS, RequirementPrecalculator, requirement_mismatch
from app.analysis.score import decide_outcome, run_detailed
from app.api.contract import CONTRACTS_DIR
from app.core.contracts_gen import (
    ComplexScoreInput,
    FixedComponents,
    RerankAnchor,
    RerankItem,
    ScoreInputs,
)
from app.core.contracts_gen import Scenario as ScenarioDTO
from app.core.db import get_engine, get_session, reset_engine
from app.core.logging import get_logger
from app.core.settings import Settings, get_settings, set_settings
from app.models import (
    Base,
    Benchmark,
    Catalyst,
    ChangeEvent,
    ChecklistItem,
    Claim,
    ComparableSet,
    Competition,
    Complex,
    ComplexType,
    Decision,
    FieldProvenance,
    IntakeStatus,
    JudgmentLog,
    Ladder,
    PaymentTerms,
    RawDocument,
    Region,
    RemainingEvent,
    RtmsTrade,
    Scenario,
    ScoreComponent,
    ScoreRun,
    ScoreTotal,
    Snapshot,
    Supply,
    Unsold,
)

__all__ = ["DEFAULT_FIXTURE", "SeedReport", "load_synth", "main", "replace_bundles", "seed"]

log = get_logger("app.api.devseed")

DEFAULT_FIXTURE = CONTRACTS_DIR / "fixtures" / "incheon_gimpo_2026-10-08"
REFERENCE_FIXTURE = CONTRACTS_DIR / "fixtures" / "reference"
EXAMPLES = CONTRACTS_DIR / "examples"
SYNTH_TOOL = CONTRACTS_DIR / "fixtures" / "tools" / "synth.py"

UNKNOWN = "확인 불가"
SEED_REASON = "보고서 재구성"
COMPONENT_KEYS = ("p10", "rerank", "gap", "benchmark", "supply", "liquidity", "move_in")
MissingMode = Literal["skip", "create"]
ReferenceMode = Literal["region", "full", "none"]


@dataclass
class SeedReport:
    legal_dongs: int = 0
    admin_dongs: int = 0
    complexes: int = 0
    provenance: int = 0
    judgments: int = 0
    score_runs: int = 0
    raw_documents: int = 0
    households: int = 0
    claims: int = 0
    notes: list[str] = field(default_factory=list)


# ====================================================================== 공용


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _v(f: dict[str, Any] | None) -> Any:
    """Fact → 값(확인 불가면 None)."""
    if not isinstance(f, dict) or f.get("label") == UNKNOWN:
        return None
    return f.get("v")


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _jl(f: dict[str, Any] | None) -> int | None:
    prov = (f or {}).get("prov") or ""
    return int(prov[3:]) if prov.startswith("jl_") and prov[3:].isdigit() else None


def _sgg_to_la(region: Region) -> dict[str, str]:
    out: dict[str, str] = {}
    for la in region.living_areas or []:
        for code in la.get("legal_dong_codes") or []:
            out.setdefault(code[:5], str(la["id"]))
    return out


# ====================================================================== 출처 행


class _ProvWriter:
    """Fact → field_provenance 행(dict). 같은 (entity, id, field)는 첫 Fact 만."""

    def __init__(self, prov_rows: dict[str, dict[str, Any]], raw_ids: set[int], missing: MissingMode) -> None:
        self.rows = prov_rows
        self.raw_ids = raw_ids
        self.missing = missing
        self.out: list[dict[str, Any]] = []
        self._seen: set[tuple[str, int, str]] = set()

    def add(self, entity: str, entity_id: int, fld: str, f: dict[str, Any] | None) -> None:
        if not isinstance(f, dict):
            return
        key = (entity, entity_id, fld)
        if key in self._seen:
            return
        prov = f.get("prov") or ""
        label = f.get("label") or UNKNOWN
        base: dict[str, Any] = {
            "entity": entity,
            "entity_id": entity_id,
            "entity_key": None,
            "field": fld,
            "source_rank": 1,
            "chosen": True,
            "checked_at": f.get("checked_at"),
            "label": label,
            "reason": f.get("reason"),
            "value_text": None if f.get("v") is None else str(f.get("v")),
            "raw_document_id": None,
            "url": None,
            "conflict_group": None,
            "excerpt": None,
            "excerpt_start": None,
            "excerpt_end": None,
            "compare_judgment_seq": None,
            "value_norm": None,
            "observed_on": None,
        }
        if prov.startswith("fp_"):
            src = self.rows.get(prov)
            if src is None:
                if self.missing == "skip":
                    return  # T13: 출처 행 없음 그대로 둔다
                base["reason"] = base["reason"] or "출처 행 합성(성능 픽스처)"
            else:
                rid = src.get("raw_document_id")
                base.update(
                    value_text=src.get("value_text"),
                    raw_document_id=rid if rid in self.raw_ids else None,
                    url=src.get("url"),
                    checked_at=src.get("checked_at") or base["checked_at"],
                    label=src.get("label") or label,
                    reason=src.get("reason") if src.get("reason") is not None else base["reason"],
                    source_rank=src.get("source_rank") or 1,
                    conflict_group=src.get("conflict_group"),
                    excerpt=src.get("excerpt"),
                    excerpt_start=src.get("excerpt_start"),
                    excerpt_end=src.get("excerpt_end"),
                )
        elif label != UNKNOWN:
            return  # jl_·sc_ 등 파생 출처는 API 가 그 원천으로 붙인다
        self._seen.add(key)
        self.out.append(base)

    def add_plain(
        self, entity: str, entity_id: int, fld: str, value: Any, label: str, checked_at: str | None
    ) -> None:
        """시장 원자료(보고서 재구성 입력)의 출처 행."""
        key = (entity, entity_id, fld)
        if key in self._seen or value is None:
            return
        self._seen.add(key)
        self.out.append(
            {
                "entity": entity,
                "entity_id": entity_id,
                "entity_key": None,
                "field": fld,
                "source_rank": 1,
                "chosen": True,
                "checked_at": checked_at,
                "label": label,
                "reason": SEED_REASON,
                "value_text": str(value),
                "raw_document_id": None,
                "url": "docs/source/incheon_gimpo_report.md",
                "conflict_group": None,
                "excerpt": None,
                "excerpt_start": None,
                "excerpt_end": None,
                "compare_judgment_seq": None,
                "value_norm": None,
                "observed_on": None,
            }
        )

    def flush(self, session: Session) -> int:
        n = len(self.out)
        for i in range(0, n, 2000):
            session.execute(insert(FieldProvenance), self.out[i : i + 2000])
        self.out.clear()
        return n


# ====================================================================== 단지 묶음


_COMPLEX_FACTS: dict[str, str | None] = {
    "housing_type": "text",
    "land_type": "text",
    "price_cap": "text",
    "regulated": "text",
    "units_total": "int",
    "units_general": "int",
    "units_special": "int",
    "officetel_units": "int",
    "notice_date": "text",
    "winner_date": "text",
    "move_in_ym": "text",
    "resale_months": "int",
    "residency_months": "int",
    "rewin_restriction_years": "int",
}
_TYPE_FACTS = (
    "area_m2",
    "units",
    "max_price_won",
    "floor_sample_price_won",
    "balcony_won",
    "options_required_won",
)
_PAY_FACTS = ("effective_from", "down_payment_pct", "down_payment_first_won", "interim_pct", "balance_pct")


def _schedule(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"kind": it.get("kind") or "", "start": _v(it.get("start")), "end": _v(it.get("end"))}
        for it in items
        if _v(it.get("start")) is not None
    ]


def _first_fact(facts: Iterable[dict[str, Any] | None]) -> dict[str, Any] | None:
    for f in facts:
        if isinstance(f, dict) and f.get("label") != UNKNOWN:
            return f
    return None


def _load_bundle(
    session: Session,
    b: dict[str, Any],
    writer: _ProvWriter,
    *,
    snapshot_id: int,
    raw_ids: set[int],
    existing: Complex | None = None,
) -> Complex:
    c = b["complex"]
    cx = existing or Complex(id=c["id"])
    cx.region_id = c["region_id"]
    cx.applyhome_id = c.get("applyhome_id")
    cx.name = c["name"]
    cx.former_names = list(c.get("former_names") or [])
    cx.address = c.get("address")
    cx.legal_dong_code = c.get("legal_dong_code")
    cx.living_area = c.get("living_area")
    cx.official_site_url = c.get("official_site_url")
    cx.developer, cx.trustee, cx.builder = c.get("developer"), c.get("trustee"), c.get("builder")
    for name, kind in _COMPLEX_FACTS.items():
        value = _v(c.get(name))
        setattr(cx, name, int(value) if (kind == "int" and value is not None) else value)
    rr = _v(c.get("resale_release_on_registration"))
    cx.resale_release_on_registration = None if rr is None else rr == "등기 시 해제"
    cx.apply_dates = _schedule(c.get("apply_dates") or [])
    cx.contract_dates = _schedule(c.get("contract_dates") or [])
    cx.inclusion_class = c.get("inclusion_class") or "미분류"
    cx.inclusion_decision = c.get("inclusion_decision")
    cx.inclusion_prob = _dec(_v(c.get("inclusion_prob")))
    cx.inclusion_judgment_seq = _jl(c.get("inclusion_prob"))
    cx.track = c.get("track")
    if existing is None:
        session.add(cx)
    session.flush()

    for name in (*_COMPLEX_FACTS, "resale_release_on_registration", "resale_end"):
        writer.add("complex", cx.id, name, c.get(name))
    writer.add(
        "complex", cx.id, "apply_dates", _first_fact(i.get("start") for i in c.get("apply_dates") or [])
    )
    writer.add(
        "complex", cx.id, "contract_dates", _first_fact(i.get("start") for i in c.get("contract_dates") or [])
    )

    for t in b.get("types") or []:
        ct = ComplexType(
            complex_id=cx.id,
            type_code=t["type_code"],
            notice_type_code=t.get("notice_type_code"),
            area_m2=_dec(_v(t.get("area_m2"))),
            units=_v(t.get("units")),
            max_price_won=_v(t.get("max_price_won")),
            floor_sample_price_won=_v(t.get("floor_sample_price_won")),
            floor_sample_text=t.get("floor_sample_text"),
            balcony_won=_v(t.get("balcony_won")),
            options_required_won=_v(t.get("options_required_won")),
            options_text=t.get("options_text"),
        )
        session.add(ct)
        session.flush()
        for name in _TYPE_FACTS:
            writer.add("complex_type", ct.id, name, t.get(name))

    for p in b.get("payment_terms") or []:
        eff = _v(p.get("effective_from"))
        if eff is None:
            continue
        sched = [
            {"seq": s["seq"], "due_date": _v(s.get("due_date")), "pct": _v(s.get("pct"))}
            for s in p.get("interim_schedule") or []
        ]
        pbt: dict[str, Any] = {}
        for code, item in (p.get("price_by_type") or {}).items():
            pbt[code] = {
                "notice_type_code": item.get("notice_type_code"),
                "units": _v(item.get("units")),
                "max_price_won": _v(item.get("max_price_won")),
                "floor_sample_price_won": _v(item.get("floor_sample_price_won")),
                "floor_sample_text": item.get("floor_sample_text"),
            }
        pt = PaymentTerms(
            complex_id=cx.id,
            notice_no=p["notice_no"],
            notice_kind=p.get("notice_kind"),
            effective_from=str(eff),
            down_payment_pct=_dec(_v(p.get("down_payment_pct"))),
            down_payment_first_won=_v(p.get("down_payment_first_won")),
            interim_pct=_dec(_v(p.get("interim_pct"))),
            interim_terms_text=p.get("interim_terms_text"),
            balance_pct=_dec(_v(p.get("balance_pct"))),
            interim_schedule=sched,
            price_by_type=pbt or None,
        )
        session.add(pt)
        session.flush()
        for name in _PAY_FACTS:
            writer.add("payment_terms", pt.id, name, p.get(name))
        writer.add(
            "payment_terms",
            pt.id,
            "interim_schedule",
            _first_fact(s.get("due_date") for s in p.get("interim_schedule") or []),
        )
        for code, item in (p.get("price_by_type") or {}).items():
            for k in ("units", "max_price_won", "floor_sample_price_won"):
                writer.add("payment_terms", pt.id, f"price_by_type.{code}.{k}", item.get(k))

    for comp in b.get("competition") or []:
        rid = comp.get("raw_document_id")
        row = Competition(
            complex_id=cx.id,
            round=comp["round"],
            kind=comp["kind"],
            type_code=comp["type_code"],
            supply=_v(comp.get("supply")),
            applied=_v(comp.get("applied")),
            ratio_or_shortfall_text=comp.get("ratio_or_shortfall_text"),
            raw_document_id=rid if rid in raw_ids else None,
        )
        session.add(row)
        session.flush()
        writer.add("competition", row.id, "supply", comp.get("supply"))
        writer.add("competition", row.id, "applied", comp.get("applied"))

    for ev in b.get("remaining_events") or []:
        rid = ev.get("raw_document_id")
        by_type = {str(k): int(v) for k, v in (ev.get("units_by_type") or {}).items()}
        units = _v(ev.get("units"))
        if not by_type and units is not None:
            by_type = {"전체": int(units)}
        row_ev = RemainingEvent(
            complex_id=cx.id,
            kind=ev["kind"],
            notice_no=ev.get("notice_no"),
            notice_date=_v(ev.get("notice_date")),
            apply_dates=[d for d in (_v(x) for x in ev.get("apply_dates") or []) if d is not None],
            units_by_type=by_type,
            ratio_text=ev.get("ratio_text"),
            result_text=ev.get("result_text"),
            raw_document_id=rid if rid in raw_ids else None,
        )
        session.add(row_ev)
        session.flush()
        writer.add("remaining_event", row_ev.id, "notice_date", ev.get("notice_date"))
        writer.add("remaining_event", row_ev.id, "apply_dates", _first_fact(ev.get("apply_dates") or []))
        writer.add("remaining_event", row_ev.id, "units", ev.get("units"))

    for it in b.get("intake") or []:
        rid = it.get("raw_document_id")
        session.add(
            IntakeStatus(
                complex_id=cx.id,
                snapshot_id=it.get("snapshot_id") or snapshot_id,
                status=it["status"],
                path=it["path"],
                evidence_url=it.get("evidence_url"),
                screenshot_path=it.get("screenshot_path"),
                raw_document_id=rid if rid in raw_ids else None,
                http_status=it.get("http_status"),
                checked_at=it["checked_at"],
                reason=it.get("reason"),
                note=it.get("note"),
                entered_by=it.get("entered_by"),
            )
        )
    return cx


def _raw_ids(session: Session) -> set[int]:
    return set(session.scalars(select(RawDocument.id)))


def _prov_rows(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    return {row["id"]: row for row in _load(path)}


def load_bundles(
    session: Session,
    bundles: Sequence[dict[str, Any]],
    prov_rows: dict[str, dict[str, Any]],
    *,
    snapshot_id: int,
    missing: MissingMode = "skip",
) -> tuple[int, int]:
    raw_ids = _raw_ids(session)
    writer = _ProvWriter(prov_rows, raw_ids, missing)
    for b in bundles:
        _load_bundle(session, b, writer, snapshot_id=snapshot_id, raw_ids=raw_ids)
    n_prov = writer.flush(session)
    session.flush()
    return len(bundles), n_prov


# ====================================================================== 참조·지역·원문·스냅샷


def _load_reference(
    session: Session,
    mode: ReferenceMode,
    sidos: set[str],
    report: SeedReport,
    raw_dir: Path | None = None,
) -> None:
    if mode == "none":
        return
    from app.collectors.reference.jscode import parse_jscode_zip
    from app.collectors.reference.legal_dong import parse_legal_dong_zip
    from app.collectors.reference.load import (
        replace_admin_legal_map,
        upsert_admin_dongs,
        upsert_legal_dongs,
    )

    manifest = _load(REFERENCE_FIXTURE / "manifest.json")

    def keep(code: str) -> bool:
        return mode == "full" or code[:2] in sidos

    legal_zip = REFERENCE_FIXTURE / "legal_dong_full.zip"
    if legal_zip.exists():
        records = [r for r in parse_legal_dong_zip(legal_zip.read_bytes()) if keep(r.code)]
        src = str(manifest.get("legal_dong_full.zip", {}).get("downloaded_at", ""))[:10] or "2026-10-09"
        upsert_legal_dongs(session, records, source_date=src)
        report.legal_dongs = len(records)
    households = sorted(REFERENCE_FIXTURE.glob("jumin_households_*.csv"))
    if households and raw_dir is not None:  # 주민등록 세대 현황(D2-1) — 생활권 세대수(R3 W11)
        from app.collectors.reference.rawstore import RawStore
        from app.collectors.stats.households import load_household_stats, parse_household_csv

        content = households[-1].read_bytes()
        # 원문 행(source_kind=stats) = 세대수 Fact 의 출처(rd_<id>).
        # reference.refresh 사본 경로와 같은 모양(sha 같으면 재사용)
        doc = RawStore(session, raw_dir=raw_dir).save_content(
            source_kind="stats",
            url=f"fixture://reference/{households[-1].name}",
            content=content,
            http_status=None,
            ext="csv",
            content_type="text/csv",
        )
        _, recs = parse_household_csv(content)
        kept = [r for r in recs if keep(r.scope_code)]
        load_household_stats(session, kept, raw_document_id=doc.id)
        report.households = len(kept)
    js = sorted(REFERENCE_FIXTURE.glob("jscode*.zip"))
    if js:
        data = parse_jscode_zip(js[-1].read_bytes())
        admins = [a for a in data.admin_dongs if keep(a.code)]
        upsert_admin_dongs(session, admins, source_date=data.source_date or "2026-10-09")
        replace_admin_legal_map(session, [(a, b) for a, b in data.mappings if keep(a)])
        report.admin_dongs = len(admins)


def _ensure_scenarios(session: Session) -> None:
    have = {code for code in session.scalars(select(Scenario.code)) if code}
    for sc in BUILTIN_SCENARIOS:
        if sc.code in have:
            continue
        session.add(
            Scenario(
                id=sc.id,
                code=sc.code,
                name=sc.name,
                is_builtin=True,
                params=sc.params.model_dump(mode="json"),
                weights=sc.weights.model_dump(mode="json", exclude_none=True),
                requirements=sc.requirements.model_dump(mode="json", exclude_none=True),
                policy=sc.policy.model_dump(mode="json"),
                created_at=sc.created_at or "2026-10-09T00:00:00+09:00",
            )
        )
    session.flush()


def _load_region(session: Session, data: dict[str, Any]) -> Region:
    region = Region(
        id=data["id"],
        name=data["name"],
        query_text=data["query_text"],
        selections=data["selections"],
        sido_codes=data["sido_codes"],
        sigungu_codes=data["sigungu_codes"],
        legal_dong_codes=data["legal_dong_codes"],
        living_areas=[
            {
                k: v
                for k, v in la.items()
                if k in ("id", "name", "legal_dong_codes", "households", "supply_ref_units")
            }
            for la in data["living_areas"]
        ],
        age_premium_coef=data["age_premium_coef"],
        supply_ref_pct=_dec(data.get("supply_ref_pct", 0.08)),
        applyhome_query=data.get("applyhome_query") or {},
        status=data.get("status") or "ready",
        created_at=data.get("created_at") or "2026-10-07T00:00:00+09:00",
    )
    session.add(region)
    session.flush()
    return region


def _load_raw(session: Session, fixture: Path, raw_dir: Path) -> int:
    docs = _load(fixture / "raw" / "documents.json")
    src_root = fixture / "raw"
    for d in docs:
        for rel in {d.get("path"), d.get("text_path")} - {None}:
            src = src_root / str(rel)
            dst = raw_dir / str(rel)
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
        session.add(
            RawDocument(
                id=d["id"],
                source_kind=d["source_kind"],
                url=d["url"],
                fetched_at=d["fetched_at"],
                http_status=d.get("http_status"),
                sha256=d["sha256"],
                path=d.get("path"),
                content_type=d.get("content_type"),
                text_path=d.get("text_path"),
                complex_id=None,
                region_id=d.get("region_id"),
                error_text=d.get("error_text"),
                image_hash=d.get("image_hash"),
                table_path=d.get("table_path"),
                meta=d.get("meta"),
            )
        )
    session.flush()
    return len(docs)


def _link_raw_complexes(session: Session, fixture: Path) -> None:
    for d in _load(fixture / "raw" / "documents.json"):
        if d.get("complex_id") is not None:
            row = session.get(RawDocument, d["id"])
            if row is not None and session.get(Complex, d["complex_id"]) is not None:
                row.complex_id = d["complex_id"]


def _load_snapshots(session: Session, fixture: Path) -> list[Snapshot]:
    out: list[Snapshot] = []
    for s in _load(fixture / "snapshots.json"):
        snap = Snapshot(
            id=s["id"],
            region_id=s["region_id"],
            asof_date=s["asof_date"],
            status=s["status"],
            degraded=bool(s.get("degraded")),
            created_at=s["created_at"],
            published_at=s.get("published_at"),
        )
        session.add(snap)
        out.append(snap)
    session.flush()
    return out


# ====================================================================== 판정 녹화


def _load_judgments(session: Session, fixture: Path) -> dict[int, dict[str, Any]]:
    """녹화 봉투 → judgment_log(seq = judgment_seq). 반환 = seq → 봉투."""
    jdir = fixture / "judgments"
    index = _load(jdir / "_index.json")
    out: dict[int, dict[str, Any]] = {}
    for row in index:
        env = _load(jdir / row["file"])
        seq = int(row["judgment_seq"])
        out[seq] = env
        payload = row.get("payload") or {}
        session.add(
            JudgmentLog(
                seq=seq,
                snapshot_id=env.get("snapshot_id"),
                tool=env["tool"],
                purpose=env["purpose"],
                complex_id=env.get("complex_id"),
                input_hash=env["input_hash"],
                input_len=env.get("input_len"),
                input_json=payload,
                output_json=dict(env.get("raw") or {}),
                result_json=dict(env.get("result") or {}),
                status=env["status"],
                confidence=_dec(env.get("confidence")),
                duration_ms=env.get("duration_ms"),
                created_at=env.get("created_at") or "2026-10-07",
                adapter_version=env.get("adapter_version") or "mock-fixture-2026-10-08",
                error_text=env.get("error_text"),
            )
        )
    session.flush()
    return out


def _load_ladders(session: Session, envs: dict[int, dict[str, Any]], snapshots: dict[int, Snapshot]) -> None:
    for seq, env in sorted(envs.items()):
        if env["tool"] != "noul" or env.get("complex_id") is None:
            continue
        snap = snapshots.get(env.get("snapshot_id") or 0)
        if snap is None or session.get(Complex, env["complex_id"]) is None:
            continue
        r = env.get("result") or {}
        horizon = r.get("horizon") or "move_in_plus_1y"
        target = str(r.get("target_ym") or "")
        cx = session.get(Complex, env["complex_id"])
        assert cx is not None
        targets = ladder_targets(snap.asof_date, move_in_ym=cx.move_in_ym, immediate=False)
        months = targets[horizon].months_from_asof if horizon in targets else None
        if target and len(target) == 7:
            y, m = int(target[:4]), int(target[5:])
            ay, am = int(snap.asof_date[:4]), int(snap.asof_date[5:7])
            months = max(1, (y - ay) * 12 + (m - am))
        props = {p.get("key"): p for p in r.get("propositions") or []}
        ann = annualized(months) if months else None
        session.add(
            Ladder(
                snapshot_id=snap.id,
                complex_id=env["complex_id"],
                horizon=horizon,
                target_ym=target
                or (targets[horizon].target_ym if horizon in targets else snap.asof_date[:7]),
                months_from_asof=months,
                p5=_dec(props.get("p5", {}).get("prob")),
                p10=_dec(props.get("p10", {}).get("prob")),
                p20=_dec(props.get("p20", {}).get("prob")),
                p_flat=_dec(props.get("p_flat", {}).get("prob")),
                verdicts={k: props.get(k, {}).get("verdict") for k in ("p5", "p10", "p20", "p_flat")},
                annualized=ann.model_dump(mode="json")
                if ann is not None
                else {"p5": None, "p10": None, "p20": None},
                status=env["status"],
                judgment_seq=seq,
                proposition_text=(props.get("p10") or {}).get("text"),
            )
        )
    session.flush()
    _carry_ladders(session, snapshots)


def _carry_ladders(session: Session, snapshots: dict[int, Snapshot]) -> None:
    """같은 입력의 noul 은 다시 부르지 않는다(캐시).

    나중 스냅샷에 없는 사다리는 앞 스냅샷 판정(같은 seq)을 잇는다."""
    ordered = sorted(snapshots.values(), key=lambda s: s.asof_date)
    for i, snap in enumerate(ordered[1:], start=1):
        have = {
            (lad.complex_id, lad.horizon)
            for lad in session.scalars(select(Ladder).where(Ladder.snapshot_id == snap.id))
        }
        for prev in reversed(ordered[:i]):
            for lad in session.scalars(select(Ladder).where(Ladder.snapshot_id == prev.id)):
                key = (lad.complex_id, lad.horizon)
                if key in have:
                    continue
                have.add(key)
                session.add(
                    Ladder(
                        snapshot_id=snap.id,
                        complex_id=lad.complex_id,
                        horizon=lad.horizon,
                        target_ym=lad.target_ym,
                        months_from_asof=lad.months_from_asof,
                        p5=lad.p5,
                        p10=lad.p10,
                        p20=lad.p20,
                        p_flat=lad.p_flat,
                        verdicts=dict(lad.verdicts or {}),
                        annualized=dict(lad.annualized or {}),
                        status=lad.status,
                        judgment_seq=lad.judgment_seq,
                        proposition_text=lad.proposition_text,
                    )
                )
    session.flush()


def _load_catalysts(session: Session, envs: dict[int, dict[str, Any]], region_id: int) -> None:
    for seq, env in sorted(envs.items()):
        if env["tool"] != "classify" or not str(env.get("purpose", "")).startswith("classify:catalyst"):
            continue
        for item in (env.get("result") or {}).get("items") or []:
            name = str(item.get("candidate") or "").strip()
            if not name:
                continue
            auto = item.get("decision") == "auto"
            label = str(item.get("label") or "")
            session.add(
                Catalyst(
                    region_id=region_id,
                    name=name[:200],
                    kind="기타",
                    stage=label if auto and label in ("확정", "계획", "추진", "언론", "미확정") else "미확정",
                    stage_prob=_dec(item.get("prob")),
                    decision=item.get("decision"),
                    expected_ym=None,
                    location_confirmed=False,
                    judgment_seq=seq,
                    note="종류(kind)는 보고서에 분류가 없어 '기타'(devseed)",
                )
            )
    session.flush()


# ====================================================================== 점수·시장


def _expected_fixed(fixture: Path) -> dict[int, FixedComponents]:
    path = fixture / "expected_scores.json"
    if not path.exists():
        return {}
    out: dict[int, FixedComponents] = {}
    for c in _load(path).get("complexes") or []:
        comps = {k: c["components"].get(k) for k in COMPONENT_KEYS if k in (c.get("components") or {})}
        out[int(c["complex_id"])] = FixedComponents(source="보고서 §12-4-3 (회귀 (a)단계)", **comps)
    return out


def _score_inputs(fixture: Path, region: Region) -> ScoreInputs | None:
    path = fixture / "expected_scores_v2.json"
    if not path.exists():
        return None
    raw = _load(path).get("inputs")
    if not isinstance(raw, dict):
        return None
    to_la = _sgg_to_la(region)

    def la(v: Any) -> Any:
        if isinstance(v, str) and not v.startswith("la_"):
            return to_la.get(v[:5], v)
        return v

    for la_in in raw.get("living_areas") or []:
        sgg = str(la_in.get("id") or "")
        if not la_in.get("unsold_scope_codes") and sgg.isdigit():
            la_in["unsold_scope_codes"] = [sgg[:5]]
        la_in["id"] = la(la_in.get("id"))
    for key in ("trades", "benchmarks", "supply", "complexes"):
        for item in raw.get(key) or []:
            item["living_area"] = la(item.get("living_area"))
    fixed = _expected_fixed(fixture)
    for cx in raw.get("complexes") or []:
        if cx.get("fixed_components") is None and int(cx["complex_id"]) in fixed:
            cx["fixed_components"] = fixed[int(cx["complex_id"])].model_dump(mode="json", exclude_none=True)
    return ScoreInputs.model_validate(raw)


def _prev_snapshot_inputs(fixture: Path, cur: ScoreInputs) -> tuple[ScoreInputs, list[int]] | None:
    """이전 스냅샷(T7 — 보고서 §12-4-3 인천 8단지) 점수 입력.

    현재 입력을 그 단지·rerank 이전 앵커(relevance_prev × 10)로 좁힌다. expected_scores.json 에 t7 블록이
    없으면 None. (R3 F4 요청: 보고서 diff 시험)"""
    path = fixture / "expected_scores.json"
    if not path.exists():
        return None
    expected = _load(path)
    t7 = expected.get("t7_incheon_only")
    if not isinstance(t7, dict) or not t7.get("rows"):
        return None
    by_key = {c["key"]: c for c in expected["complexes"]}
    rows = {int(by_key[r["key"]]["complex_id"]): r for r in t7["rows"] if r["key"] in by_key}
    ids = sorted(rows)
    ranked = sorted(rows.items(), key=lambda kv: -float(kv[1]["relevance_prev"]))
    anchor = RerankAnchor(
        judgment_seq=t7.get("rerank_judgment_seq_prev"),
        status="ok",
        items=[
            RerankItem(
                candidate_id=f"complex:{cid}",
                complex_id=cid,
                relevance=float(r["relevance_prev"]),
                rank=n + 1,
            )
            for n, (cid, r) in enumerate(ranked)
        ],
    )
    by_id = {int(c["complex_id"]): c for c in expected["complexes"]}
    complexes = []
    for cx in cur.complexes:
        if cx.complex_id not in rows:
            continue
        comps = {k: by_id[cx.complex_id]["components"].get(k) for k in COMPONENT_KEYS}
        comps["rerank"] = round(float(rows[cx.complex_id]["relevance_prev"]) * 10, 4)
        fixed = FixedComponents(
            source="보고서 §12-4-3 (T7)", **{k: v for k, v in comps.items() if v is not None}
        )
        complexes.append(cx.model_copy(update={"fixed_components": fixed}))
    prev_sid = int(t7.get("snapshot_id_prev") or cur.snapshot_id - 1)
    prev_day = str(t7.get("asof_date_prev") or "2026-10-07")
    prev = cur.model_copy(
        update={"snapshot_id": prev_sid, "asof_date": prev_day, "rerank": anchor, "complexes": complexes}
    )
    return prev, ids


def _copy_intake(session: Session, src_sid: int, dst_sid: int, ids: Sequence[int]) -> None:
    """이전 스냅샷 접수 상태 = 현재 스냅샷 행 복사(파이프라인은 스냅샷마다 접수 행을 남긴다)."""
    for row in list(
        session.scalars(
            select(IntakeStatus).where(IntakeStatus.snapshot_id == src_sid, IntakeStatus.complex_id.in_(ids))
        )
    ):
        session.add(
            IntakeStatus(
                complex_id=row.complex_id, snapshot_id=dst_sid, status=row.status, path=row.path,
                evidence_url=row.evidence_url, screenshot_path=row.screenshot_path,
                raw_document_id=row.raw_document_id, http_status=row.http_status, checked_at=row.checked_at,
                reason=row.reason, note=row.note, entered_by=row.entered_by,
            )
        )  # fmt: skip
    session.flush()


# 녹화 verify 봉투의 contradicted 복합 주장(T6)을 원자 분할 재검증한 자식 문장 — 보고서 §12-4 원문
_SPLIT_CHILDREN = (
    "고촌센트럴자이 +10%·+20%와 롯데캐슬 +20% 명제는 unlikely이다",
    "나머지 명제는 uncertain이다",
)


def _load_claims(session: Session, envs: dict[int, dict[str, Any]]) -> int:
    """verify 봉투 → claim 행(판정기 호출 없음).

    contradicted 복합 주장에는 분할 자식(verified) 2개를 둔다(T6) — 남은 contradicted 0 이라 publish·보고서는
    막히지 않는다."""
    jdir_index = {int(r["judgment_seq"]): r for r in _load(DEFAULT_FIXTURE / "judgments" / "_index.json")}
    n = 0
    for seq, e in sorted(envs.items()):
        if e.get("tool") != "verify" or e.get("snapshot_id") is None:
            continue
        payload = jdir_index.get(seq, {}).get("payload") or {}
        known = payload.get("known_claims") or {}
        section = str(payload.get("section", ""))[:32]
        for k, c in enumerate((e.get("result") or {}).get("claims", [])):
            text = (
                known.get(c.get("claim_id")) or f"주장 {c.get('claim_id')} (보고서 미기재 — 집계로 만든 id)"
            )
            row = Claim(
                snapshot_id=e["snapshot_id"], section=section, text=text, evidence_text=None,
                verify_status=c.get("verdict"), judgment_seq=seq, ordinal=k,
            )  # fmt: skip
            session.add(row)
            session.flush()
            n += 1
            if c.get("verdict") == "contradicted":
                for j, child in enumerate(_SPLIT_CHILDREN):
                    session.add(
                        Claim(
                            snapshot_id=e["snapshot_id"], section=section, text=child,
                            verify_status="verified", parent_claim_id=row.id, ordinal=j,
                        )
                    )  # fmt: skip
                    n += 1
    session.flush()
    return n


def _load_market(session: Session, inputs: ScoreInputs, region: Region, writer: _ProvWriter) -> None:
    checked = inputs.asof_date
    for b in inputs.benchmarks:
        row = Benchmark(
            region_id=region.id,
            living_area=b.living_area,
            name=b.name,
            completed_year=b.completed_year,
            sale_year=b.sale_year,
            sale_period=getattr(b, "sale_period", None),
            sale_price_84_won=b.sale_price_84_won,
            sale_price_label=b.label,
            trade_median_won=b.trade_median_won,
            is_presale=bool(b.is_presale),
            note=SEED_REASON,
        )
        session.add(row)
        session.flush()
        for f in ("sale_price_84_won", "trade_median_won"):
            writer.add_plain("benchmark", row.id, f, getattr(row, f), b.label or "추정", checked)
    # 입력 거래는 생활권만 안다 → 그 생활권의 첫 법정동 코드를 대표로 둔다(재구성 자료, 동 단위 위치 아님)
    rep_code = {str(a["id"]): (a.get("legal_dong_codes") or [None])[0] for a in region.living_areas or []}
    for t in inputs.trades:
        trade = RtmsTrade(
            region_id=region.id,
            apt_name=t.apt_name,
            legal_dong_code=rep_code.get(str(t.living_area)),
            dong=None,
            completed_year=t.completed_year,
            area_m2=_dec(t.area_m2) or Decimal(0),
            floor=t.floor,
            price_won=t.price_won,
            deal_date=t.deal_date,
            cancelled=bool(t.cancelled),
            is_presale=bool(t.is_presale),
            source=t.source,
        )
        session.add(trade)
        session.flush()
        label = "재가공" if t.source == "reprocessed" else "확인됨"
        writer.add_plain("rtms_trade", trade.id, "price_won", t.price_won, label, t.deal_date)
    for s in inputs.supply:
        row_s = Supply(
            region_id=region.id,
            living_area=s.living_area,
            year=s.year,
            ym=s.ym,
            units=s.units,
            label=s.label or "추정",
            reason="추정 집계" if (s.label or "추정") == "추정" else None,
            complex_id=s.complex_id if s.complex_id and session.get(Complex, s.complex_id) else None,
        )
        session.add(row_s)
        session.flush()
        writer.add_plain("supply", row_s.id, "units", s.units, row_s.label, checked)
    for u in inputs.unsold:
        row_u = Unsold(
            region_id=region.id,
            scope_code=u.scope_code,
            scope_name=next(
                (
                    str(a["name"])
                    for a in region.living_areas
                    if _sgg_to_la(region).get(str(u.scope_code)) == a["id"]
                ),
                None,
            ),
            ym=u.ym,
            total=u.total,
            post_completion=u.post_completion,
            source_label=u.label or "재가공",
        )
        session.add(row_u)
        session.flush()
        writer.add_plain("unsold", row_u.id, "total", u.total, row_u.source_label, checked)
        writer.add_plain(
            "unsold", row_u.id, "post_completion", u.post_completion, row_u.source_label, checked
        )
    session.flush()


def _scenario_dto(sc: Scenario) -> ScenarioDTO:
    return ScenarioDTO.model_validate(
        {
            "id": sc.id,
            "code": sc.code,
            "name": sc.name,
            "is_builtin": sc.is_builtin,
            "params": sc.params,
            "weights": sc.weights,
            "requirements": sc.requirements,
            "policy": sc.policy,
            "created_at": sc.created_at,
        }
    )


def _p10_backed(inputs: ScoreInputs, horizon: str) -> ScoreInputs:
    """고정 p10(보고서 (a)단계 = 입주+1년 사다리 값)은 그 시나리오 시점의 사다리 입력이 있는 단지에만 남긴다.

    상황 C(기준일+5년)는 픽스처에 5년 사다리가 없다 — 1년 값을 고정 성분으로 쓰면 성분 3.9 인데
    화면 p10 사실값(그 시점 사다리)은 null 이 된다(R3 3차 minor 7). 빼면 p10 이 '사다리 없음'(미판정)으로
    계산되고 종합도 미판정이다(D9-1)."""
    out = []
    for c in inputs.complexes:
        fc = c.fixed_components
        if fc is not None and fc.p10 is not None and not any(lad.horizon == horizon for lad in c.ladders):
            c = c.model_copy(update={"fixed_components": fc.model_copy(update={"p10": None})})
        out.append(c)
    return inputs.model_copy(update={"complexes": out})


def _load_scores(
    session: Session,
    inputs: ScoreInputs,
    snap: Snapshot,
    envs: dict[int, dict[str, Any]],
) -> int:
    """스냅샷 점수(내장 시나리오마다 score_run).

    그 스냅샷에 점수 실행이 이미 있으면 건너뛴다(멱등 — 0 반환)."""
    have = select(ScoreRun.id).where(ScoreRun.snapshot_id == snap.id).limit(1)
    if session.scalars(have).first() is not None:
        return 0
    from app.scheduler.snapshots import snapshot_dto

    snap_dto = snapshot_dto(snap)
    created = snap.published_at or snap.created_at
    decide_by_code: dict[str, tuple[int, dict[str, Any]]] = {}
    for seq, env in envs.items():
        purpose = str(env.get("purpose") or "")
        if (
            env["tool"] == "decide"
            and env.get("snapshot_id") == snap.id
            and purpose.startswith("decide:scenario_")
        ):
            decide_by_code[purpose.removeprefix("decide:scenario_").split(":")[0]] = (seq, env)
    cx_inputs = {c.complex_id: c for c in inputs.complexes}
    precalc = RequirementPrecalculator()
    runs = 0
    scenarios = list(
        session.scalars(select(Scenario).where(Scenario.is_builtin.is_(True)).order_by(Scenario.id))
    )
    for sc in scenarios:
        dto = _scenario_dto(sc)
        sc_inputs = _p10_backed(inputs, dto.policy.p10_horizon)
        detail = run_detailed(snap_dto, dto, sc_inputs, with_sensitivity=True)
        res = detail.result
        run = ScoreRun(
            snapshot_id=snap.id,
            scenario_id=sc.id,
            weights=dto.weights.model_dump(mode="json", exclude_none=True),
            rerank_judgment_seq=res.rerank_judgment_seq if res.rerank_judgment_seq in envs else None,
            created_at=created,
        )
        session.add(run)
        session.flush()
        runs += 1
        for comp in res.components:
            session.add(
                ScoreComponent(
                    score_run_id=run.id,
                    complex_id=comp.complex_id,
                    component=comp.component,
                    raw_value=_dec(comp.raw_value),
                    score_0_10=_dec(comp.score_0_10),
                    formula_text=comp.formula_text,
                    label=comp.label,
                    reason=comp.reason,
                    delta=_dec(comp.delta),
                    flags=list(comp.flags or []),
                )
            )
        for tot in res.totals:
            session.add(
                ScoreTotal(
                    score_run_id=run.id,
                    complex_id=tot.complex_id,
                    total=_dec(tot.total),
                    rank=tot.rank,
                    tie_group=tot.tie_group,
                    unstable=tot.unstable,
                    judge_scope=cx_inputs[tot.complex_id].judge_scope
                    if tot.complex_id in cx_inputs
                    else None,
                )
            )
        if sc.code == "base":
            for cid, gap in detail.gaps.items():
                for m in gap.members:
                    session.add(
                        ComparableSet(
                            complex_id=cid,
                            snapshot_id=snap.id,
                            member_apt_name=m.member_apt_name,
                            completed_year=m.completed_year,
                            substitute=m.substitute,
                            adjusted=m.adjusted,
                            coef_used=m.coef_used,
                            n_trades=m.n_trades,
                            low_won=m.low_won,
                            median_won=m.median_won,
                            adjusted_median_won=m.adjusted_median_won,
                            high_won=m.high_won,
                            outliers_excluded=m.outliers_excluded,
                            excluded_reason=m.excluded_reason,
                            note=m.note,
                        )
                    )
        hit = decide_by_code.get(sc.code or "")
        if hit is not None:
            _load_decisions(session, run, sc, dto, hit, cx_inputs, precalc, snap.asof_date)
    session.flush()
    return runs


def _load_decisions(
    session: Session,
    run: ScoreRun,
    sc: Scenario,
    dto: ScenarioDTO,
    hit: tuple[int, dict[str, Any]],
    cx_inputs: dict[int, ComplexScoreInput],
    precalc: RequirementPrecalculator,
    asof: str,
) -> None:
    seq, env = hit
    r = env.get("result") or {}
    probs: dict[str, float] = {str(k): float(v) for k, v in (r.get("probs") or {}).items()}
    checks: dict[str, dict[str, str]] = r.get("checks") or {}
    options = decide_outcome(
        status=env["status"], confidence=env.get("confidence"), probs=probs, selected=r.get("selected")
    )
    for opt in options:
        key = opt.key
        cid: int | None = None
        option_key = key
        if key.startswith("complex:") and key[8:].isdigit():
            cid = int(key[8:])
            option_key = "complex"
            if session.get(Complex, cid) is None:
                continue
        elif key not in ("wait_new", "ask_user", "investigate", "none"):
            continue
        pre: dict[str, Any] = {}
        judged = checks.get(key, {})
        mism = False
        if cid is not None and cid in cx_inputs:
            pres = precalc.evaluate(cx_inputs[cid], dto, asof_date=asof)
            for req in ("access", "regulation", "funds"):
                p = getattr(pres, req)
                pre[req] = p.model_dump(mode="json")
                mism = mism or requirement_mismatch(p.status, judged.get(req))  # type: ignore[arg-type]
        session.add(
            Decision(
                score_run_id=run.id,
                scenario_id=sc.id,
                complex_id=cid,
                option_key=option_key,
                prob=_dec(opt.prob),
                chosen=opt.chosen,
                tie=opt.tie,
                req_access_pre=pre.get("access"),
                req_regulation_pre=pre.get("regulation"),
                req_funds_pre=pre.get("funds"),
                req_access_judge=judged.get("access"),
                req_regulation_judge=judged.get("regulation"),
                req_funds_judge=judged.get("funds"),
                mismatch=mism,
                confidence=_dec(env.get("confidence")),
                warnings=list(r.get("warnings") or []),
                judgment_seq=seq,
            )
        )


# ====================================================================== 예시(변경·체크리스트)


def _load_examples(session: Session) -> None:
    complex_ids = set(session.scalars(select(Complex.id)))
    snap_ids = set(session.scalars(select(Snapshot.id)))
    path = EXAMPLES / "changes.json"
    if path.exists():
        for ev in _load(path).get("value") or []:
            session.add(
                ChangeEvent(
                    snapshot_id=ev.get("snapshot_id") if ev.get("snapshot_id") in snap_ids else None,
                    entity=ev["entity"],
                    entity_id=ev.get("entity_id"),
                    field=ev["field"],
                    old_text=ev.get("old_text"),
                    new_text=ev.get("new_text"),
                    detected_at=ev["detected_at"],
                    severity=ev["severity"],
                    triggers_rejudge=bool(ev.get("triggers_rejudge")),
                    complex_id=ev.get("complex_id") if ev.get("complex_id") in complex_ids else None,
                )
            )
    path = EXAMPLES / "checklist.json"
    if path.exists():
        for it in _load(path).get("value") or []:
            session.add(
                ChecklistItem(
                    complex_id=it.get("complex_id") if it.get("complex_id") in complex_ids else None,
                    kind=it["kind"],
                    title=it["title"],
                    due_date=it.get("due_date"),
                    status=it.get("status") or "open",
                    note=it.get("note"),
                )
            )
    session.flush()


# ====================================================================== 진입점


def _guard(settings: Settings) -> None:
    """devseed 는 지어낸 출처 행(합성 단지·녹화 판정)을 넣는다.

    ENV=prod 이거나 SQLite 가 아닌 DB 면 거부한다(R3 minor 30)."""
    if settings.env == "prod":
        raise RuntimeError("devseed 는 ENV=prod 에서 쓰지 않는다(운영 DB 에 지어낸 출처 행 금지)")
    if not settings.is_sqlite:
        raise RuntimeError("devseed 는 SQLite 개발 DB 에서만 쓴다(운영 DB 보호)")


def _reset_schema(settings: Settings) -> None:
    engine = get_engine(settings)
    if not settings.is_sqlite:
        raise RuntimeError("devseed --reset 은 SQLite 개발 DB 에서만 쓴다(운영 DB 보호)")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def seed(
    settings: Settings | None = None,
    *,
    fixture_dir: Path = DEFAULT_FIXTURE,
    reference: ReferenceMode = "region",
    reset: bool = True,
) -> SeedReport:
    """픽스처 전체 적재(한 트랜잭션). reset=True 면 SQLite 스키마를 지우고 다시 만든다."""
    s = settings or get_settings()
    _guard(s)
    if reset:
        _reset_schema(s)
    else:
        Base.metadata.create_all(get_engine(s))
    report = SeedReport()
    region_data = _load(fixture_dir / "region.json")
    with get_session(s) as session:
        if session.get(Region, region_data["id"]) is not None:
            raise RuntimeError(f"region {region_data['id']} 이 이미 있다 — --reset 으로 다시 만든다")
        _load_reference(session, reference, set(region_data.get("sido_codes") or []), report, s.raw_dir)
        _ensure_scenarios(session)
        region = _load_region(session, region_data)
        report.raw_documents = _load_raw(session, fixture_dir, s.raw_dir)
        snaps = {sn.id: sn for sn in _load_snapshots(session, fixture_dir)}
        latest = max(snaps.values(), key=lambda sn: sn.asof_date)
        bundles = _load(fixture_dir / "complexes.json")
        # judgment_log 의 complex_id FK 때문에 단지를 먼저
        report.complexes, report.provenance = load_bundles(
            session, bundles, _prov_rows(fixture_dir / "provenance.json"), snapshot_id=latest.id
        )
        _link_raw_complexes(session, fixture_dir)
        envs = _load_judgments(session, fixture_dir)
        report.judgments = len(envs)
        _load_ladders(session, envs, snaps)
        _load_catalysts(session, envs, region.id)
        inputs = _score_inputs(fixture_dir, region)
        if inputs is not None and inputs.snapshot_id in snaps:
            writer = _ProvWriter({}, set(), "create")
            _load_market(session, inputs, region, writer)
            report.provenance += writer.flush(session)
            report.score_runs = _load_scores(session, inputs, snaps[inputs.snapshot_id], envs)
            prev = _prev_snapshot_inputs(fixture_dir, inputs)
            if prev is not None and prev[0].snapshot_id in snaps:
                report.score_runs += _load_scores(session, prev[0], snaps[prev[0].snapshot_id], envs)
                _copy_intake(session, inputs.snapshot_id, prev[0].snapshot_id, prev[1])
        else:
            report.notes.append("expected_scores_v2.json 입력 없음 — 점수·시장 미적재")
        report.claims = _load_claims(session, envs)
        _load_examples(session)
    log.info("devseed.done", extra={"complexes": report.complexes, "provenance": report.provenance})
    return report


def replace_bundles(
    settings: Settings | None = None,
    *,
    bundles_path: Path,
    provenance_path: Path | None,
    missing: MissingMode = "skip",
) -> int:
    """단지 묶음(ComplexBundle[])을 바꿔 넣는다(T13 용).

    사실 테이블·출처 행만 교체하고 점수·판정 행은 그대로 둔다."""
    s = settings or get_settings()
    _guard(s)
    bundles = _load(bundles_path)
    prov = _prov_rows(provenance_path)
    with get_session(s) as session:
        raw_ids = _raw_ids(session)
        writer = _ProvWriter(prov, raw_ids, missing)
        for b in bundles:
            cid = int(b["complex"]["id"])
            existing = session.get(Complex, cid)
            snapshot_ids = {
                i.snapshot_id
                for i in session.scalars(select(IntakeStatus).where(IntakeStatus.complex_id == cid))
            }
            sub = {
                "complex_type": select(ComplexType.id).where(ComplexType.complex_id == cid),
                "payment_terms": select(PaymentTerms.id).where(PaymentTerms.complex_id == cid),
                "competition": select(Competition.id).where(Competition.complex_id == cid),
                "remaining_event": select(RemainingEvent.id).where(RemainingEvent.complex_id == cid),
            }
            for entity, ids_stmt in sub.items():
                ids = list(session.scalars(ids_stmt))
                if ids:
                    session.execute(
                        delete(FieldProvenance).where(
                            FieldProvenance.entity == entity, FieldProvenance.entity_id.in_(ids)
                        )
                    )
            session.execute(
                delete(FieldProvenance).where(
                    FieldProvenance.entity == "complex", FieldProvenance.entity_id == cid
                )
            )
            for model in (ComplexType, PaymentTerms, Competition, RemainingEvent, IntakeStatus):
                session.execute(delete(model).where(model.complex_id == cid))
            session.flush()
            snap_id = next(iter(snapshot_ids), None) or 0
            _load_bundle(session, b, writer, snapshot_id=snap_id, raw_ids=raw_ids, existing=existing)
        writer.flush(session)
    return len(bundles)


def _synth_generate(n: int) -> list[dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("_synth_tool", SYNTH_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"합성 도구를 읽을 수 없다: {SYNTH_TOOL}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out: list[dict[str, Any]] = mod.generate(n)
    return out


def load_synth(settings: Settings | None = None, *, n: int = 1000, snapshot_id: int = 12) -> int:
    """T16: 합성 단지 n개(contracts/fixtures/tools/synth.py)를 지역 1·스냅샷에 넣는다.

    출처 행은 Fact 에서 합성한다(성능 전용)."""
    s = settings or get_settings()
    _guard(s)
    bundles = _synth_generate(n)
    with get_session(s) as session:
        count, _ = load_bundles(session, bundles, {}, snapshot_id=snapshot_id, missing="create")
    return count


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.api.devseed", description=__doc__.split("\n\n")[0])
    ap.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE, help="픽스처 디렉터리")
    ap.add_argument("--reference", choices=["region", "full", "none"], default="region")
    ap.add_argument("--synth", type=int, default=0, help="합성 단지 n개 추가(T16)")
    ap.add_argument("--no-reset", action="store_true", help="스키마를 지우지 않는다(빈 DB 에만)")
    args = ap.parse_args(argv)
    settings = get_settings()
    set_settings(settings)
    try:
        report = seed(settings, fixture_dir=args.fixture, reference=args.reference, reset=not args.no_reset)
        if args.synth:
            report.complexes += load_synth(settings, n=args.synth)
    finally:
        reset_engine()
    sys.stdout.write(
        f"devseed: db={settings.database_url} raw={settings.raw_dir} complexes={report.complexes} "
        f"provenance={report.provenance} judgments={report.judgments} score_runs={report.score_runs} "
        f"legal_dongs={report.legal_dongs} admin_dongs={report.admin_dongs} "
        f"households={report.households} claims={report.claims}\n"
    )
    for note in report.notes:
        sys.stdout.write(f"  note: {note}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
