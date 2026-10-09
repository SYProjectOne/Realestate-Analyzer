"""WP8 테스트 전용 픽스처 로더 — contracts/fixtures/incheon_gimpo_2026-10-08 → DB (스냅샷 11·12).

WP5 ``api/devseed.py`` 가 아직 없어서 WP8 테스트가 직접 적재한다(R2 지시서 WP8). 이 로더는 WP7 파이프라인이
만들 파생 테이블(score_run·score_component·score_total·ladder·decision·claim·catalyst)을 녹화된 판정 봉투와
``app.analysis`` 로 다시 만든다. 판정기는 부르지 않는다.

- 점수: 회귀 (a)단계 — 보고서 구성 점수(expected_scores.json)를 fixed_components 로, 내장 시나리오 5개 전부.
  스냅샷 12 = 통합 16(rerank #124), 스냅샷 11 = 인천 8(rerank #71, t7 relevance_prev × 10).
- 사다리: noul 봉투(move_in_plus_1y), 판정 안 된 asof_plus_3y·5y는 status=review 행.
- decide: 봉투 → decision 행(동률은 ``analysis.score.decide_outcome``),
  사전 계산은 ``RequirementPrecalculator``.
- verify: 봉투 claims → claim 행. #131 contradicted 복합 주장은 분할 자식 2개(verified)를 둔다
  (T6 — 분할 재검증).
- 호재: classify:catalyst 봉투 items → catalyst 행(review 면 stage 미확정).
- 벤치마크·공급·미분양: expected_scores_v2.json inputs(재가공·비공식 라벨 그대로) + field_provenance 행.
지역명은 픽스처에만 있다(코드에는 없음).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.analysis.scenarios import BUILTIN_SCENARIOS, RequirementPrecalculator, requirement_mismatch
from app.analysis.score import decide_outcome, run_detailed
from app.core.contracts_gen import (
    ComplexScoreInput,
    FixedComponents,
    RerankAnchor,
    RerankItem,
    ScoreInputs,
)
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.models import (
    Benchmark,
    Catalyst,
    Claim,
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
    Scenario,
    ScoreComponent,
    ScoreRun,
    ScoreTotal,
    Snapshot,
    Supply,
    Unsold,
)

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "contracts" / "fixtures" / "incheon_gimpo_2026-10-08"
COMPONENTS6 = ("p10", "rerank", "gap", "benchmark", "supply", "liquidity")
SNAP_PREV, SNAP_CUR = 11, 12


def _load(name: str) -> Any:
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


def _is_fact(v: Any) -> bool:
    return isinstance(v, dict) and "label" in v and "v" in v


def _val(v: Any) -> Any:
    return v["v"] if _is_fact(v) else v


def _dec(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _facts(obj: Any) -> Iterator[dict[str, Any]]:
    if _is_fact(obj):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _facts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _facts(v)


@dataclass
class SeedInfo:
    region_id: int = 1
    snapshots: tuple[int, int] = (SNAP_PREV, SNAP_CUR)
    score_runs: dict[tuple[int, str], int] = field(default_factory=dict)  # (snapshot, code) -> run id
    complex_ids: dict[int, list[int]] = field(default_factory=dict)  # snapshot -> complex ids


class _Prov:
    """fixture prov id(fp_1_001) → (entity, db entity id). 확인 불가 Fact 는 출처 행을 새로 만든다."""

    def __init__(self) -> None:
        self.owner: dict[str, tuple[str, int]] = {}
        self.unknown: list[FieldProvenance] = []

    def walk(self, entity: str, entity_id: int, record: dict[str, Any]) -> None:
        for key, value in record.items():
            if _is_fact(value) and value.get("prov") is None and value["label"] == "확인 불가":
                self.unknown.append(
                    FieldProvenance(
                        entity=entity,
                        entity_id=entity_id,
                        field=key,
                        value_text=None,
                        label="확인 불가",
                        reason=(value.get("reason") or "사유 미기재")[:120],
                        source_rank=9,
                        chosen=True,
                        checked_at=value.get("checked_at"),
                    )
                )
        for fact in _facts(record):
            prov = fact.get("prov")
            if isinstance(prov, str) and prov.startswith("fp_"):
                self.owner.setdefault(prov, (entity, entity_id))


def _region(session: Session) -> None:
    r = _load("region.json")
    session.add(
        Region(
            id=r["id"],
            name=r["name"],
            query_text=r["query_text"],
            selections=r["selections"],
            sido_codes=r["sido_codes"],
            sigungu_codes=r["sigungu_codes"],
            legal_dong_codes=r["legal_dong_codes"],
            living_areas=r["living_areas"],
            age_premium_coef=r["age_premium_coef"],
            supply_ref_pct=_dec(r["supply_ref_pct"]),
            applyhome_query=r["applyhome_query"],
            status=r["status"],
            created_at=r["created_at"],
        )
    )
    for s in _load("snapshots.json"):
        session.add(
            Snapshot(
                id=s["id"],
                region_id=s["region_id"],
                asof_date=s["asof_date"],
                status=s["status"],
                degraded=s["degraded"],
                created_at=s["created_at"],
                published_at=s["published_at"],
            )
        )
    session.flush()


_COMPLEX_COLS = [
    "id",
    "region_id",
    "applyhome_id",
    "name",
    "former_names",
    "address",
    "legal_dong_code",
    "living_area",
    "official_site_url",
    "developer",
    "trustee",
    "builder",
    "housing_type",
    "land_type",
    "price_cap",
    "regulated",
    "units_total",
    "units_general",
    "units_special",
    "officetel_units",
    "notice_date",
    "apply_dates",
    "winner_date",
    "contract_dates",
    "move_in_ym",
    "resale_months",
    "residency_months",
    "rewin_restriction_years",
    "inclusion_class",
    "inclusion_decision",
    "track",
]


def _complexes(session: Session, prov: _Prov) -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = _load("complexes.json")
    for b in bundles:
        c = b["complex"]
        row = Complex(**{k: _val(c.get(k)) for k in _COMPLEX_COLS})
        rel = _val(c.get("resale_release_on_registration"))
        row.resale_release_on_registration = None if rel is None else True
        prob = c.get("inclusion_prob")
        if _is_fact(prob):
            row.inclusion_prob = _dec(prob["v"])
            p = prob.get("prov") or ""
            if p.startswith("jl_"):
                row.inclusion_judgment_seq = int(p[3:])
        row.former_names = c.get("former_names") or []
        row.apply_dates = c.get("apply_dates") or []
        row.contract_dates = c.get("contract_dates") or []
        session.add(row)
        prov.walk("complex", row.id, c)
    session.flush()
    for d in _load("raw/documents.json"):
        session.add(
            RawDocument(
                **{
                    k: d.get(k)
                    for k in [
                        "id",
                        "source_kind",
                        "url",
                        "fetched_at",
                        "http_status",
                        "sha256",
                        "path",
                        "content_type",
                        "text_path",
                        "complex_id",
                        "region_id",
                        "error_text",
                        "image_hash",
                    ]
                }
            )
        )
    session.flush()
    for b in bundles:
        cid = b["complex"]["id"]
        for t in b["types"]:
            row_t = ComplexType(
                complex_id=cid,
                type_code=t["type_code"],
                area_m2=_dec(_val(t["area_m2"])),
                units=_val(t["units"]),
                max_price_won=_val(t["max_price_won"]),
                floor_sample_price_won=_val(t["floor_sample_price_won"]),
                floor_sample_text=t.get("floor_sample_text"),
                balcony_won=_val(t["balcony_won"]),
                options_required_won=_val(t["options_required_won"]),
                options_text=t.get("options_text"),
                notice_type_code=t.get("notice_type_code"),
            )
            session.add(row_t)
            session.flush()
            prov.walk("complex_type", row_t.id, t)
        for p in b["payment_terms"]:
            row_p = PaymentTerms(
                complex_id=cid,
                notice_no=p["notice_no"],
                notice_kind=p.get("notice_kind"),
                effective_from=_val(p["effective_from"]),
                down_payment_pct=_dec(_val(p["down_payment_pct"])),
                down_payment_first_won=_val(p["down_payment_first_won"]),
                interim_pct=_dec(_val(p["interim_pct"])),
                interim_terms_text=p.get("interim_terms_text"),
                balance_pct=_dec(_val(p["balance_pct"])),
                interim_schedule=p.get("interim_schedule") or [],
            )
            session.add(row_p)
            session.flush()
            prov.walk("payment_terms", row_p.id, p)
        for k in b["competition"]:
            row_k = Competition(
                complex_id=cid,
                round=k["round"],
                kind=k["kind"],
                type_code=k["type_code"],
                supply=_val(k["supply"]),
                applied=_val(k["applied"]),
                ratio_or_shortfall_text=k.get("ratio_or_shortfall_text"),
                raw_document_id=k.get("raw_document_id"),
            )
            session.add(row_k)
            session.flush()
            prov.walk("competition", row_k.id, k)
        for e in b["remaining_events"]:
            row_e = RemainingEvent(
                complex_id=cid,
                kind=e["kind"],
                notice_no=e.get("notice_no"),
                notice_date=_val(e.get("notice_date")),
                apply_dates=[_val(x) for x in e.get("apply_dates") or []],
                units_by_type=e.get("units_by_type") or {},
                ratio_text=e.get("ratio_text"),
                result_text=e.get("result_text"),
                raw_document_id=e.get("raw_document_id"),
            )
            session.add(row_e)
            session.flush()
            prov.walk("remaining_event", row_e.id, e)
    session.flush()
    return bundles


def _intake(session: Session, bundles: list[dict[str, Any]], prev_ids: set[int]) -> None:
    for b in bundles:
        for i in b["intake"]:
            for sid in (SNAP_CUR, SNAP_PREV):
                if sid == SNAP_PREV and b["complex"]["id"] not in prev_ids:
                    continue
                session.add(
                    IntakeStatus(
                        complex_id=i["complex_id"],
                        snapshot_id=sid,
                        status=i["status"],
                        path=i["path"],
                        evidence_url=i.get("evidence_url"),
                        screenshot_path=i.get("screenshot_path"),
                        raw_document_id=i.get("raw_document_id"),
                        http_status=i.get("http_status"),
                        checked_at=i["checked_at"],
                        reason=i.get("reason"),
                        note=i.get("note"),
                        entered_by=i.get("entered_by"),
                    )
                )
    session.flush()


def _provenance(session: Session, prov: _Prov) -> None:
    for p in _load("provenance.json"):
        entity, entity_id = prov.owner.get(p["id"], (p["entity"], p["entity_id"]))
        session.add(
            FieldProvenance(
                entity=entity,
                entity_id=entity_id,
                field=p["field"],
                value_text=p.get("value_text"),
                raw_document_id=p.get("raw_document_id"),
                url=p.get("url"),
                checked_at=p.get("checked_at"),
                label=p["label"],
                reason=p.get("reason"),
                source_rank=p.get("source_rank") or 1,
                chosen=bool(p.get("chosen")),
                conflict_group=p.get("conflict_group"),
                excerpt=p.get("excerpt"),
                excerpt_start=p.get("excerpt_start"),
                excerpt_end=p.get("excerpt_end"),
                compare_judgment_seq=p.get("compare_judgment_seq"),
            )
        )
    session.add_all(prov.unknown)
    session.flush()


def _envelopes() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out = []
    for r in _load("judgments/_index.json"):
        env = _load(f"judgments/{r['file']}")
        out.append((r, env))
    return out


def _judgments(session: Session, envs: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
    for r, e in envs:
        session.add(
            JudgmentLog(
                seq=e["judgment_seq"],
                snapshot_id=e["snapshot_id"],
                tool=e["tool"],
                purpose=e["purpose"],
                complex_id=e.get("complex_id"),
                input_hash=e["input_hash"],
                input_len=e.get("input_len"),
                input_json=r["payload"],
                output_json=e.get("raw") or {},
                status=e["status"],
                confidence=_dec(e.get("confidence")),
                duration_ms=e.get("duration_ms"),
                created_at=e["created_at"],
                adapter_version=e["adapter_version"],
                error_text=e.get("error_text"),
            )
        )
    session.flush()


def _scenarios(session: Session) -> None:
    for sc in BUILTIN_SCENARIOS:
        session.add(
            Scenario(
                id=sc.id,
                code=sc.code,
                name=sc.name,
                is_builtin=True,
                params=sc.params.model_dump(mode="json", exclude_none=True),
                weights=sc.weights.model_dump(mode="json", exclude_none=True),
                requirements=sc.requirements.model_dump(mode="json", exclude_none=True),
                policy=sc.policy.model_dump(mode="json"),
                created_at=sc.created_at or "2026-10-09T00:00:00+09:00",
            )
        )
    session.flush()


def _score_inputs(snapshot_id: int) -> tuple[ScoreInputs, list[int]]:
    expected = _load("expected_scores.json")
    v2 = _load("expected_scores_v2.json")["inputs"]
    by_id = {c["complex_id"]: c for c in expected["complexes"]}
    if snapshot_id == SNAP_CUR:
        ids = sorted(by_id)
        anchor = RerankAnchor.model_validate(v2["rerank"])
        rerank_fixed = {cid: by_id[cid]["components"]["rerank"] for cid in ids}
        asof = "2026-10-08"
    else:
        t7 = expected["t7_incheon_only"]
        key_to_id = {c["key"]: c["complex_id"] for c in expected["complexes"]}
        rows = {key_to_id[r["key"]]: r for r in t7["rows"]}
        ids = sorted(rows)
        items = sorted(
            (
                RerankItem(
                    candidate_id=f"complex:{cid}", complex_id=cid, relevance=r["relevance_prev"], rank=1
                )
                for cid, r in rows.items()
            ),
            key=lambda i: -i.relevance,
        )
        anchor = RerankAnchor(
            judgment_seq=t7["rerank_judgment_seq_prev"],
            status="ok",
            items=[it.model_copy(update={"rank": n + 1}) for n, it in enumerate(items)],
        )
        rerank_fixed = {cid: round(rows[cid]["relevance_prev"] * 10, 4) for cid in ids}
        asof = "2026-10-07"
    complexes: list[ComplexScoreInput] = []
    for raw in v2["complexes"]:
        cid = raw["complex_id"]
        if cid not in ids:
            continue
        comps = dict(by_id[cid]["components"])
        fixed = None
        if comps and all(comps.get(k) is not None for k in COMPONENTS6):
            comps["rerank"] = rerank_fixed[cid]
            fixed = FixedComponents(source="보고서 §12-4-3", **{k: comps[k] for k in COMPONENTS6})
        item = dict(raw)
        item["judge_scope"] = by_id[cid]["judge_scope"]
        item["fixed_components"] = fixed
        complexes.append(ComplexScoreInput.model_validate(item))
    data = dict(v2)
    data.update(snapshot_id=snapshot_id, asof_date=asof, rerank=anchor, complexes=complexes)
    return ScoreInputs.model_validate(data), ids


def _scores(session: Session, info: SeedInfo) -> dict[int, ScoreInputs]:
    inputs_by_snap: dict[int, ScoreInputs] = {}
    for sid in (SNAP_PREV, SNAP_CUR):
        inputs, ids = _score_inputs(sid)
        inputs_by_snap[sid] = inputs
        info.complex_ids[sid] = ids
        snap = session.get(Snapshot, sid)
        assert snap is not None
        dto = SnapshotDTO(
            id=sid,
            region_id=1,
            asof_date=snap.asof_date,
            status="ready",
            degraded=False,
            created_at=snap.created_at,
        )
        for sc in BUILTIN_SCENARIOS:
            detail = run_detailed(dto, sc, inputs)
            res = detail.result
            run = ScoreRun(
                snapshot_id=sid,
                scenario_id=sc.id,
                weights=sc.weights.model_dump(mode="json", exclude_none=True),
                rerank_judgment_seq=res.rerank_judgment_seq,
                prev_score_run_id=info.score_runs.get((SNAP_PREV, sc.code or ""))
                if sid == SNAP_CUR
                else None,
                created_at=f"{snap.asof_date}T07:00:00+09:00",
            )
            session.add(run)
            session.flush()
            info.score_runs[(sid, sc.code or "")] = run.id
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
                        flags=comp.flags or [],
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
                    )
                )
    session.flush()
    return inputs_by_snap


def _ladders(session: Session, envs: list[tuple[dict[str, Any], dict[str, Any]]], info: SeedInfo) -> None:
    done: set[tuple[int, int, str]] = set()
    for _, e in envs:
        if e["tool"] != "noul" or e.get("complex_id") is None:
            continue
        res = e["result"]
        probs = {p["key"]: p for p in res.get("propositions", [])}
        targets = [SNAP_CUR] if e["snapshot_id"] == SNAP_CUR else [SNAP_PREV, SNAP_CUR]
        for sid in targets:
            key = (sid, e["complex_id"], res["horizon"])
            if key in done or e["complex_id"] not in info.complex_ids[sid]:
                continue
            done.add(key)
            session.add(
                Ladder(
                    snapshot_id=sid,
                    complex_id=e["complex_id"],
                    horizon=res["horizon"],
                    target_ym=res["target_ym"],
                    months_from_asof=None,
                    p5=_dec(probs.get("p5", {}).get("prob")),
                    p10=_dec(probs.get("p10", {}).get("prob")),
                    p20=_dec(probs.get("p20", {}).get("prob")),
                    p_flat=_dec(probs.get("p_flat", {}).get("prob")),
                    verdicts={k: v.get("verdict") for k, v in probs.items()},
                    annualized={},
                    status=e["status"],
                    judgment_seq=e["judgment_seq"],
                    proposition_text=probs.get("p10", {}).get("text"),
                )
            )
    for sid in (SNAP_PREV, SNAP_CUR):
        asof_year = 2026
        for cid in info.complex_ids[sid]:
            for horizon, years in (("asof_plus_3y", 3), ("asof_plus_5y", 5)):
                session.add(
                    Ladder(
                        snapshot_id=sid,
                        complex_id=cid,
                        horizon=horizon,
                        target_ym=f"{asof_year + years}-10",
                        months_from_asof=years * 12,
                        verdicts={},
                        annualized={},
                        status="review",
                    )
                )
    session.flush()


def _decisions(
    session: Session,
    envs: list[tuple[dict[str, Any], dict[str, Any]]],
    info: SeedInfo,
    inputs_by_snap: dict[int, ScoreInputs],
) -> None:
    scen = {sc.code: sc for sc in BUILTIN_SCENARIOS}
    calc = RequirementPrecalculator()
    for _, e in envs:
        if e["tool"] != "decide":
            continue
        code = e["purpose"].split(":")[1].removeprefix("scenario_")
        sid = e["snapshot_id"]
        sc = scen[code]
        run_id = info.score_runs[(sid, code)]
        res = e["result"]
        options = list(dict.fromkeys([*res.get("checks", {}).keys(), *res.get("probs", {}).keys()]))
        outcome = {
            o.key: o
            for o in decide_outcome(
                status=e["status"],
                confidence=e.get("confidence"),
                probs=res.get("probs", {}),
                selected=res.get("selected"),
            )
        }
        cx_inputs = {c.complex_id: c for c in inputs_by_snap[sid].complexes}
        for opt in options:
            o = outcome.get(opt)
            cid = int(opt.split(":")[1]) if opt.startswith("complex:") else None
            checks = res.get("checks", {}).get(opt, {})
            pre: dict[str, dict[str, str] | None] = {"access": None, "regulation": None, "funds": None}
            mismatch = False
            if cid is not None and cid in cx_inputs:
                ps = calc.evaluate(cx_inputs[cid], sc, asof_date=inputs_by_snap[sid].asof_date)
                for req in ("access", "regulation", "funds"):
                    rp = getattr(ps, req)
                    pre[req] = rp.model_dump()
                    mismatch = mismatch or requirement_mismatch(rp.status, checks.get(req))
            session.add(
                Decision(
                    score_run_id=run_id,
                    scenario_id=sc.id,
                    complex_id=cid,
                    option_key="complex" if cid is not None else opt,
                    prob=_dec(o.prob) if o else None,
                    chosen=bool(o and o.chosen),
                    tie=bool(o and o.tie),
                    req_access_pre=pre["access"],
                    req_regulation_pre=pre["regulation"],
                    req_funds_pre=pre["funds"],
                    req_access_judge=checks.get("access"),
                    req_regulation_judge=checks.get("regulation"),
                    req_funds_judge=checks.get("funds"),
                    mismatch=mismatch,
                    confidence=_dec(e.get("confidence")),
                    warnings=res.get("warnings") or [],
                    judgment_seq=e["judgment_seq"],
                )
            )
    session.flush()


def _claims(session: Session, envs: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
    for r, e in envs:
        if e["tool"] != "verify":
            continue
        known = r["payload"].get("known_claims") or {}
        section = str(r["payload"].get("section", ""))[:32]
        for n, c in enumerate(e["result"].get("claims", [])):
            text = known.get(c["claim_id"]) or f"주장 {c['claim_id']} (보고서 미기재 — 집계로 만든 id)"
            row = Claim(
                snapshot_id=e["snapshot_id"],
                section=section,
                text=text,
                evidence_text=None,
                verify_status=c["verdict"],
                judgment_seq=e["judgment_seq"],
                ordinal=n,
            )
            session.add(row)
            session.flush()
            if c["verdict"] == "contradicted":
                for k, child in enumerate(
                    (
                        "고촌센트럴자이 +10%·+20%와 롯데캐슬 +20% 명제는 unlikely이다",
                        "나머지 명제는 uncertain이다",
                    )
                ):
                    session.add(
                        Claim(
                            snapshot_id=e["snapshot_id"],
                            section=section,
                            text=child,
                            verify_status="verified",
                            parent_claim_id=row.id,
                            ordinal=k,
                        )
                    )
    session.flush()


def _market(session: Session, envs: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
    region = _load("region.json")
    la_by_sigungu = {la["legal_dong_codes"][0][:5]: la["id"] for la in region["living_areas"]}
    v2 = _load("expected_scores_v2.json")["inputs"]
    la_names = {la["id"]: la["name"] for la in v2["living_areas"]}
    checked = "2026-10-07"

    def prov(entity: str, eid: int, field_: str, label: str, reason: str | None = None) -> None:
        session.add(
            FieldProvenance(
                entity=entity,
                entity_id=eid,
                field=field_,
                label=label,
                reason=reason,
                source_rank=2,
                chosen=True,
                checked_at=checked,
                value_text=None,
            )
        )

    for b in v2["benchmarks"]:
        row_b = Benchmark(
            region_id=1,
            living_area=la_by_sigungu.get(b["living_area"], b["living_area"]),
            name=b["name"],
            completed_year=b.get("completed_year"),
            sale_year=b.get("sale_year"),
            sale_price_84_won=b.get("sale_price_84_won"),
            sale_price_label=b["label"],
            trade_median_won=b.get("trade_median_won"),
            is_presale=bool(b.get("is_presale")),
        )
        session.add(row_b)
        session.flush()
        for f in ("sale_price_84_won", "trade_median_won", "completed_year", "sale_year"):
            prov("benchmark", row_b.id, f, b["label"])
    for s in v2["supply"]:
        row_s = Supply(
            region_id=1,
            living_area=la_by_sigungu.get(s["living_area"], s["living_area"]),
            year=s["year"],
            ym=s.get("ym"),
            units=s["units"],
            label=s["label"],
            reason="추정 집계" if s["label"] == "추정" else None,
            complex_id=s.get("complex_id"),
        )
        session.add(row_s)
        session.flush()
        prov("supply", row_s.id, "units", s["label"], row_s.reason)
    for u in v2["unsold"]:
        row_u = Unsold(
            region_id=1,
            scope_code=u.get("scope_code"),
            scope_name=la_names.get(u.get("scope_code") or ""),
            ym=u["ym"],
            total=u.get("total"),
            post_completion=u.get("post_completion"),
            source_label=u["label"],
        )
        session.add(row_u)
        session.flush()
        prov("unsold", row_u.id, "total", u["label"])
        prov("unsold", row_u.id, "post_completion", u["label"])
    for _, e in envs:
        if e["tool"] != "classify" or not e["purpose"].startswith("classify:catalyst"):
            continue
        for item in e["result"].get("items", []):
            stage = item["label"] if item.get("decision") == "auto" else "미확정"
            session.add(
                Catalyst(
                    region_id=1,
                    name=item["candidate"][:200],
                    kind="기타",
                    stage=stage if stage in ("확정", "계획", "추진", "언론", "미확정") else "미확정",
                    stage_prob=_dec(item.get("prob")),
                    decision=item.get("decision"),
                    judgment_seq=e["judgment_seq"],
                    note=None
                    if stage == item["label"]
                    else f"판정기 label {item['label']} · {item.get('decision')}",
                )
            )
    session.flush()


def seed(session: Session) -> SeedInfo:
    """픽스처 전부를 적재한다(commit 은 호출자)."""
    info = SeedInfo()
    prov = _Prov()
    _region(session)
    bundles = _complexes(session, prov)
    expected = _load("expected_scores.json")
    key_to_id = {c["key"]: c["complex_id"] for c in expected["complexes"]}
    prev_ids = {key_to_id[r["key"]] for r in expected["t7_incheon_only"]["rows"]}
    _intake(session, bundles, prev_ids)
    _provenance(session, prov)
    envs = _envelopes()
    _judgments(session, envs)
    _scenarios(session)
    inputs = _scores(session, info)
    _ladders(session, envs, info)
    _decisions(session, envs, info, inputs)
    _claims(session, envs)
    _market(session, envs)
    return info


def add_contradicted_claim(session: Session, snapshot_id: int) -> int:
    """T15: 분할되지 않은 contradicted 주장 1건(생성 거부 시험용)."""
    row = Claim(
        snapshot_id=snapshot_id,
        section="8-F1",
        text="시험용 contradicted 주장",
        verify_status="contradicted",
        ordinal=99,
    )
    session.add(row)
    session.flush()
    return row.id
