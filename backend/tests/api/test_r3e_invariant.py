"""R3e CORE3 — D13-1 발행 리비전 = 저장된 읽기 모델(materialized) 불변 테스트 (계약 2026-10-09.10, R3 5차 리뷰 K2·M6).

리비전을 실제 발행 경로(``scheduler.snapshots.republish`` → ``publish`` → ``snapshot_view.materialize``)로 발행한 뒤
아래 변경을 하나씩 가하고, 매 단계마다 **그 리비전의 모든 GET·CSV·보고서(HTML) 바이트**가 발행 직후와 같은지 본다.

| 단계 | 변경 | 리뷰 |
| --- | --- | --- |
| A | 사실(새 공고 가격·입주월 재수집) | K2 사실 |
| B | 강등(PATCH /claims) | K2 강등 오버레이 |
| C | 사람 확인(POST /ops/human-checks) | K2 |
| D | 새 단지 행(수집·지역 확장) | K2 단지 목록 16→17 |
| E | 호재 PATCH(연결 그대로 예정월만·연결 변경·예정월 null) | K2 catalysts.py |
| F | 생활권 편집(PUT living-areas) | K2 생활권 |
| G | 지역 이름 변경(PATCH /regions) | K2 지역 이름 |
| H | 입주 물량 재수집(collect._supply) | K2 la_2 12,203→11,534 |
| I | classify 재판정(분류·확률·호재 단계·stage_prob·judgment_seq 제자리 갱신) | K2 inclusion_prob·stage_prob |
| J | 같은 기준일 새 리비전 발행(republish) | D11-1 |

그리고 발행 리비전 GET 이 실시간 계산(묶음 적재·점수 문맥·보고서 적재)을 **타지 않음**을 그 함수들을 막아 놓고 보인다.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import Catalyst, Complex, Snapshot

from ._support import READ, WRITE
from .test_r3b_g3 import CX, SNAP, _ensure_resale
from .test_r3d_core2 import _demote_price, human_check, store_cx_field, store_notice

SCENARIOS = ("base", "A", "B", "C", "D")


def _publish_revision() -> int:
    """SNAP 위 새 리비전을 실제 발행 경로로 발행(파생 행 복사 → publish → materialize)."""
    from app.scheduler.snapshots import republish

    with get_session() as s:
        rev = republish(s, 1, reason="불변 테스트 리비전", created_at="2026-10-09T08:00:00+09:00")
        assert rev is not None and rev.status == "published"
        return int(rev.id)


def _urls(rev: int, complex_ids: list[int]) -> list[str]:
    urls: list[str] = []
    for cid in complex_ids:
        urls.append(f"/api/complexes/{cid}?snapshot={rev}")
    for sc in ("A", "D"):
        urls.append(f"/api/complexes/{CX}?snapshot={rev}&scenario={sc}")
    for sc in SCENARIOS:
        urls += [
            f"/api/snapshots/{rev}/dashboard?scenario={sc}",
            f"/api/snapshots/{rev}/complexes?size=200&scenario={sc}",
            f"/api/snapshots/{rev}/sensitivity?scenario={sc}",
            f"/api/snapshots/{rev}/compare?ids=1,{CX}&scenario={sc}",
        ]
    urls += [
        f"/api/snapshots/{rev}/complexes?sort=name&size=7&page=2",
        f"/api/snapshots/{rev}/complexes?sort=-price_mid",
        f"/api/snapshots/{rev}/complexes?filter[living_area]=la_2&sort=move_in_ym",
        f"/api/snapshots/{rev}/complexes?filter[judge_scope]=판정 대상&sort=last_change",
        f"/api/snapshots/{rev}/complexes?filter[q]=검단",
        f"/api/snapshots/{rev}/complexes.csv",
        f"/api/snapshots/{rev}/complexes.csv?scenario=D&sort=name",
        f"/api/snapshots/{rev}/market",
        f"/api/snapshots/{rev}/market?living_area=la_1",
        f"/api/snapshots/{rev}/market?living_area=la_2",
        f"/api/snapshots/{rev}/changes",
        f"/api/snapshots/{rev}/changes?since=2026-01-01",
        f"/api/snapshots/{rev}/changes?compare_snapshot=11",
        f"/api/snapshots/{rev}/changes?severity=critical",
    ]
    return urls


def _report_bytes(rev: int, out: Path) -> dict[str, str]:
    from app.models import Scenario
    from app.reports.export import generate

    got: dict[str, str] = {}
    with get_session() as s:
        d_id = s.scalars(select(Scenario.id).where(Scenario.code == "D")).one()
        for tag, kw in (
            ("base", {}),
            ("D", {"scenario_id": d_id}),
            ("vs11", {"compare_snapshot_id": 11}),
        ):
            rep = generate(s, rev, "html", out_dir=out / tag, **kw)  # type: ignore[arg-type]
            got[tag] = hashlib.sha256(rep.path.read_bytes()).hexdigest()
    return got


class _Grab:
    def __init__(self, client: TestClient, rev: int, tmp: Path) -> None:
        self.client, self.rev, self.tmp, self.n = client, rev, tmp, 0
        with get_session() as s:
            ids = sorted(s.scalars(select(Complex.id).where(Complex.region_id == 1)))
        self.urls = _urls(rev, ids)
        self.base = self.grab()

    def grab(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for u in self.urls:
            r = self.client.get(u, headers=READ)
            assert r.status_code == 200, (u, r.status_code, r.text[:300])
            out[u] = r.content
        self.n += 1
        out["report"] = _report_bytes(self.rev, self.tmp / f"g{self.n}")
        return out

    def same(self, step: str) -> None:
        now = self.grab()
        changed = [k for k in self.base if now[k] != self.base[k]]
        assert not changed, f"{step}: 발행 리비전 {self.rev} 응답이 바뀌었다(D13-1): {changed[:8]}"


def _mutations(client: TestClient) -> list[tuple[str, Callable[[], None]]]:
    def a_facts() -> None:
        from app.api.views import basis_type
        from app.models import ComplexType

        with get_session() as s:
            t = basis_type(list(s.scalars(select(ComplexType).where(ComplexType.complex_id == CX))))
            assert t is not None
            code = t.type_code
        store_notice(CX, "2026990301", {"effective_from": "2026-10-09", "notice_kind": "무순위",
                                        f"price_by_type.{code}.max_price_won": 777_000_000}, observed_on="2026-10-12")  # fmt: skip
        store_cx_field(1, "move_in_ym", "2031-01", "notice_pdf", "2026-10-12", "inv-a")

    def b_demote() -> None:
        _demote_price(client, 658_140_000)
        from app.models import Claim

        with (
            get_session() as s
        ):  # 시험용 contradicted 주장(발행 리비전에 붙인 픽스처)은 고친 문장 재검증 통과로 닫는다
            for c in s.scalars(select(Claim).where(Claim.verify_status == "contradicted")):
                c.verify_status = "verified"

    def c_human() -> None:
        _ensure_resale(12)
        human_check(client, "resale_months", "24")
        human_check(client, "move_in_ym", "2029-09", cx=3)

    def d_new_complex() -> None:
        with get_session() as s:
            s.add(Complex(region_id=1, applyhome_id="2026999301", name="나중에 수집된 단지", former_names=[],
                          apply_dates=[], contract_dates=[], inclusion_class="private_sale_apt", living_area="la_2",
                          legal_dong_code="2829010300"))  # fmt: skip

    def e_catalyst() -> None:
        with get_session() as s:
            cat = Catalyst(
                region_id=1, name="불변 테스트 역", kind="교통", stage="계획", location_confirmed=False
            )
            s.add(cat)
            s.flush()
            cid = cat.id
        body = {"location_confirmed": True, "complex_ids": [CX], "expected_ym": "2029-01"}
        assert client.patch(f"/api/catalysts/{cid}", json=body, headers=WRITE).status_code == 200
        assert (
            client.patch(
                f"/api/catalysts/{cid}", json={**body, "expected_ym": "2030-06"}, headers=WRITE
            ).status_code
            == 200
        )
        assert (
            client.patch(
                f"/api/catalysts/{cid}", json={**body, "expected_ym": None}, headers=WRITE
            ).status_code
            == 200
        )
        assert (
            client.patch(
                f"/api/catalysts/{cid}", json={**body, "complex_ids": [CX, 1]}, headers=WRITE
            ).status_code
            == 200
        )

    def f_living_areas() -> None:
        region = client.get("/api/regions/1", headers=READ).json()
        areas = [{"id": a["id"], "name": a["name"] + "(개명)", "legal_dong_codes": a["legal_dong_codes"]}
                 for a in region["living_areas"]]  # fmt: skip
        la2 = next(a for a in areas if a["id"] == "la_2")
        moved, la2["legal_dong_codes"] = la2["legal_dong_codes"][:3], la2["legal_dong_codes"][3:]
        areas.append({"id": None, "name": "새 생활권", "legal_dong_codes": moved})
        r = client.put("/api/regions/1/living-areas", json={"living_areas": areas}, headers=WRITE)
        assert r.status_code == 200, r.text

    def g_region_name() -> None:
        sels = client.get("/api/regions/1", headers=READ).json()["selections"]
        r = client.patch("/api/regions/1", json={"selections": sels, "name": "개명한 지역"}, headers=WRITE)
        assert r.status_code == 200, r.text

    def h_supply() -> None:
        from app.collectors.stats.supply import write_supply_provenance
        from app.scheduler.collect import _supply

        with get_session() as s:
            _supply(s, 1)
            write_supply_provenance(s, 1)

    def i_classify() -> None:
        with get_session() as s:
            for cx in s.scalars(select(Complex).where(Complex.region_id == 1)):
                cx.inclusion_prob = 0.123  # type: ignore[assignment]
                if cx.id == 1:
                    cx.inclusion_class = "범위 경계"
            for c in s.scalars(select(Catalyst).where(Catalyst.region_id == 1)):
                c.stage, c.stage_prob, c.judgment_seq = "호재 아님", 0.91, 1  # type: ignore[assignment]

    def j_new_revision() -> None:
        """판정 중인(사람 확인·강등이 만든) 가장 새 리비전을 이월·발행 → 그 위에 또 리비전 발행."""
        from app.scheduler.persist import carry_forward
        from app.scheduler.snapshots import latest_for_region, previous, publish

        with get_session() as s:
            newest = latest_for_region(s, 1)
            assert newest is not None
            if newest.status != "published":
                base = previous(s, newest, published_only=True)
                assert base is not None
                carry_forward(s, base.id, newest.id, created_at="2026-10-09T13:00:00+09:00")
                from app.models import Claim

                for c in s.scalars(select(Claim).where(Claim.snapshot_id == newest.id)):
                    if c.verify_status == "contradicted":  # B 의 고친 문장 재검증 통과(claim.reverify) 가정
                        c.verify_status = "verified"
                newest.status = "ready"
                ok, n = publish(s, newest.id, now="2026-10-09T13:05:00+09:00")
                assert ok, n
        _publish_revision()

    return [
        ("A 사실", a_facts),
        ("B 강등", b_demote),
        ("C 사람 확인", c_human),
        ("D 새 단지", d_new_complex),
        ("E 호재 PATCH", e_catalyst),
        ("F 생활권 편집", f_living_areas),
        ("G 지역 이름", g_region_name),
        ("H 입주 물량 재수집", h_supply),
        ("I classify 재판정", i_classify),
        ("J 새 리비전 발행", j_new_revision),
    ]


@pytest.mark.parametrize("which", ["devseed", "republished"])
def test_d13_1_published_revision_bytes_never_change(client: TestClient, tmp_path: Path, which: str) -> None:
    rev = SNAP if which == "devseed" else _publish_revision()
    grab = _Grab(client, rev, tmp_path)
    for step, change in _mutations(client):
        change()
        grab.same(step)


def test_d13_1_published_get_does_not_run_live_computation(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """발행 리비전 GET·보고서는 저장본만 읽는다 — 실시간 계산 함수(묶음 적재·점수 문맥·보고서 적재·시장 계산)를 막아도 200."""
    import app.api.views as views
    import app.reports.data as rdata
    import app.snapshot_view as sv

    rev = _publish_revision()
    with get_session() as s:
        ids = sorted(s.scalars(select(Complex.id).where(Complex.region_id == 1)))

    def boom(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("발행 리비전 GET 이 실시간 계산을 탔다")

    for mod, name in ((views, "load_bundles"), (views, "score_ctx"), (rdata, "load_report_live")):
        monkeypatch.setattr(mod, name, boom)
    for name in sv.LIVE_BUILDERS:
        monkeypatch.setattr(sv, name, boom)
    for u in _urls(rev, ids):
        r = client.get(u, headers=READ)
        assert r.status_code == 200, (u, r.text[:300])
    _report_bytes(rev, tmp_path)


def test_d13_1_building_revision_is_live(client: TestClient) -> None:
    """발행 전(building·ready) 리비전만 실시간 계산 — 사실 변경이 바로 보인다."""
    from .test_r3d_core2 import _revision_of

    live = _revision_of(SNAP, publish=False)
    before = client.get(f"/api/complexes/1?snapshot={live}", headers=READ).json()["header"]["move_in_ym"]["v"]
    store_cx_field(1, "move_in_ym", "2031-03", "notice_pdf", "2026-10-12", "inv-live")
    after = client.get(f"/api/complexes/1?snapshot={live}", headers=READ).json()["header"]["move_in_ym"]["v"]
    assert before != after == "2031-03"
    with get_session() as s:
        assert s.get(Snapshot, live).status == "building"  # type: ignore[union-attr]
