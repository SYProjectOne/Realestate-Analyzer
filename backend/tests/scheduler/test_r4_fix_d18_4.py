"""R4-FIX C3·M1·M3 (D18-4) — 잔여·임의·무순위·재공급 공고 = 원 단지(사업)의 사건. R4 실데이터 녹화 재생.

녹화: ``tests/normalize/fixtures/r4_remnant`` (R4 2026-10-12 수집 원문 — 공개 분양 정보, docs.json 이 수집 순서).
- 더샵 송도그란테르 G5-1블록: 본청약 2026000164(조회 창 안) + 무순위 2026910203 → R4 에서 단지 행 10·24 로 갈라짐
- 신검단중앙역 금강펜테리움 센트럴파크: 재공급·무순위 2026930020·2026910139·2025930054 — 공고문이 '최초 주택관리번호
  2023000053' 을 인용 → R4 에서 원 단지 이름이 제목 줄 '불법행위'(확인됨)
- 힐스테이트 레이크 송도 4차: 임의공급 2025940301 → 원 2022000069 이름 '(임의공급 4차)'
- 엘리프 검단 포레듀(AA32블록): 임의공급 2026940173·2026940079 → 원 2025000302 (R4 단지 행 80·37·32)
원 공고 다시 받기(``fetch_originals``) 응답은 R4 의 과거 공고 목록 원문(같은 API·같은 행 모양)에서 그 행 1개, 주택형은
R4 과거 공고 수집이 받은 실제 응답이다.

| 테스트 | 확인 |
| --- | --- |
| ``test_remnant_notices_attach_to_original_without_own_rows`` | 잔여 공고 번호로 단지 행 없음, 원 단지 4개, 잔여 공고 이력은 원 단지에 |
| ``test_title_lines_are_not_names`` | '불법행위'·'(임의공급 4차)'·'민영 비규제지역' 등 제목 줄 이름 없음, 공고문 출처 이름 없음 |
| ``test_original_notice_refetched_by_house_manage_no`` | 원 공고를 번호로 다시 받아 이름·공고일을 채운다 |
| ``test_original_missing_scope_reason`` | 원 공고를 못 받으면 범위 사유 '원 공고 미수집'(분양가 미공개 아님) |
| ``test_same_day_recollect_is_unchanged`` | 같은 날 다시 수집해도 단지 행·change_event 0 (원문 순서 의존 없음, M5) |
"""

# ruff: noqa: E501  (한국어 docstring·픽스처 행)

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors.applyhome import api as ah_api
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.settings import Settings
from app.models import Complex, FieldProvenance, RawDocument, RemainingEvent
from app.normalize.store import raw_dto
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext

from .conftest import seed_region, seed_scenarios

FIX = Path(__file__).resolve().parents[1] / "normalize" / "fixtures" / "r4_remnant"
ASOF = "2026-10-12"
REMNANT_NOS = {
    "2026910203",
    "2026930020",
    "2026910139",
    "2025930054",
    "2025940301",
    "2026940173",
    "2026940079",
}
ORIGINALS = {"2026000164", "2023000053", "2022000069", "2025000302"}
BAD_NAMES = {
    "불법행위",
    "불법행위재공급",
    "불법행위재공급(계약취소주택)",
    "(임의공급 4차)",
    "민영 비규제지역",
}
EXPECTED_ANCHOR = {
    "2026910203": "2026000164",
    "2026930020": "2023000053",
    "2026910139": "2023000053",
    "2025930054": "2023000053",
    "2025940301": "2022000069",
    "2026940173": "2025000302",
    "2026940079": "2025000302",
}


def _manifest() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIX / "docs.json").read_text(encoding="utf-8"))
    return data


def _insert(factory: sessionmaker[Session], rows: list[dict[str, Any]]) -> list[RawDTO]:
    out: list[RawDTO] = []
    with factory() as s:
        for r in rows:
            row = s.scalars(select(RawDocument).where(RawDocument.sha256 == r["sha256"])).first()
            if row is None:
                vals = {k: v for k, v in r.items() if k not in ("id",)}
                row = RawDocument(**vals, region_id=1, complex_id=None)
                s.add(row)
                s.flush()
            out.append(raw_dto(row))
        s.commit()
    return out


@dataclass
class Replay:
    """녹화 원문을 돌려주는 수집기(네트워크 없음)."""

    factory: sessionmaker[Session]
    rows: list[dict[str, Any]]
    originals: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    original_calls: list[list[str]] = field(default_factory=list)

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        return _insert(self.factory, self.rows)

    def fetch_originals(
        self, region: RegionDTO, snapshot: SnapshotDTO, house_manage_nos: list[str]
    ) -> list[RawDTO]:
        self.original_calls.append(list(house_manage_nos))
        rows = [r for hm in house_manage_nos for r in self.originals.get(hm, [])]
        return _insert(self.factory, rows)


def _originals(m: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """원 공고 응답 → raw_document 행(URL = 수집기가 번호로 다시 받을 때의 URL)."""
    apt = ah_api.ENDPOINTS["apt"]
    mdl = {r["url"]: r for r in m["docs"]["original_mdl"]}
    out: dict[str, list[dict[str, Any]]] = {}
    for hm, o in m["originals"].items():
        params = ah_api.item_params(hm, hm)
        body = (FIX / o["detail"]).read_bytes()
        import hashlib

        rows = [
            {
                "source_kind": "applyhome_detail", "url": ah_api.doc_url(apt.detail, params),
                "fetched_at": "2026-10-12T06:40:00+09:00", "http_status": 200, "sha256": hashlib.sha256(body).hexdigest(),
                "path": f"applyhome_detail/2026-10-12/orig_{hm}.json", "content_type": "application/json; charset=UTF-8",
                "text_path": None, "table_path": None, "error_text": None, "image_hash": None, "meta": None,
            }
        ]  # fmt: skip
        mrow = mdl.get(ah_api.doc_url(apt.model, params))
        if mrow is not None:
            rows.append({k: v for k, v in mrow.items() if k != "id"})
        out[hm] = rows
    return out


def _setup(
    test_settings: Settings, factory: sessionmaker[Session], *, originals: bool = True
) -> tuple[Replay, Replay]:
    m = _manifest()
    raw_dir = test_settings.raw_dir
    shutil.copytree(FIX / "raw", raw_dir, dirs_exist_ok=True)
    for hm, o in m["originals"].items():
        dst = raw_dir / "applyhome_detail" / "2026-10-12" / f"orig_{hm}.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIX / o["detail"], dst)
    with factory() as s:
        seed_scenarios(s)
        seed_region(s)
        s.commit()
    ah = Replay(factory, m["docs"]["applyhome"], _originals(m) if originals else {})
    pdf = Replay(factory, m["docs"]["notice_pdf"])
    return ah, pdf


def _collect(make_ctx: Callable[..., SchedulerContext], ah: Replay, pdf: Replay) -> Any:
    ctx = make_ctx(collectors={"applyhome": lambda c: ah, "notice_pdf": lambda c: pdf})
    return collect(ctx, 1, ["applyhome_list", "applyhome_detail"], asof_date=ASOF)


def _complexes(factory: sessionmaker[Session]) -> dict[str, Complex]:
    with factory() as s:
        return {str(c.applyhome_id): c for c in s.scalars(select(Complex))}


def test_remnant_notices_attach_to_original_without_own_rows(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    ah, pdf = _setup(test_settings, factory)
    res = _collect(make_ctx, ah, pdf)
    assert not res.store_errors, res.store_errors
    rows = _complexes(factory)
    assert set(rows) & REMNANT_NOS == set(), f"잔여 공고 번호로 단지 행: {sorted(set(rows) & REMNANT_NOS)}"
    assert set(rows) == ORIGINALS
    with factory() as s:
        by_id = {c.id: str(c.applyhome_id) for c in s.scalars(select(Complex))}
        events = {e.notice_no: by_id[e.complex_id] for e in s.scalars(select(RemainingEvent))}
    assert events == EXPECTED_ANCHOR


def test_title_lines_are_not_names(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    ah, pdf = _setup(test_settings, factory, originals=False)
    _collect(make_ctx, ah, pdf)
    names = {c.name for c in _complexes(factory).values()}
    assert not names & BAD_NAMES, names
    with factory() as s:
        from_pdf = s.scalars(
            select(FieldProvenance)
            .join(RawDocument, RawDocument.id == FieldProvenance.raw_document_id)
            .where(
                FieldProvenance.entity == "complex",
                FieldProvenance.field == "name",
                RawDocument.source_kind == "notice_pdf",
            )
        ).all()
    assert from_pdf == [], "공고문 제목·본문 줄은 단지 이름 후보가 아니다(D18-4)"
    # 원 공고를 못 받아도 이름은 청약홈(잔여 공고 API)의 사업 이름 — 제목 줄이 아니다
    rows = _complexes(factory)
    assert rows["2023000053"].name == "신검단중앙역 금강펜테리움 센트럴파크"
    assert rows["2022000069"].name == "힐스테이트 레이크 송도 4차"


def test_original_notice_refetched_by_house_manage_no(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    ah, pdf = _setup(test_settings, factory)
    res = _collect(make_ctx, ah, pdf)
    assert ah.original_calls and set(ah.original_calls[0]) == {"2023000053", "2022000069", "2025000302"}
    assert res.loaded["originals"]["wanted"] == 3
    rows = _complexes(factory)
    assert (rows["2023000053"].name, rows["2023000053"].notice_date) == (
        "검단신도시 금강펜테리움 3차 센트럴파크",
        "2023-03-02",
    )
    assert (rows["2022000069"].name, rows["2022000069"].notice_date) == (
        "힐스테이트 레이크 송도 4차",
        "2022-02-11",
    )
    assert rows["2025000302"].notice_date == "2025-08-22"


def test_original_missing_scope_reason(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    from app.analysis.scope import ORIGINAL_MISSING, judge_scope, original_missing

    ah, pdf = _setup(test_settings, factory, originals=False)
    _collect(make_ctx, ah, pdf)
    cx = _complexes(factory)["2023000053"]
    assert original_missing(cx.applyhome_id, cx.notice_date)
    sr = judge_scope(
        inclusion_class="private_sale_apt", inclusion_decision="auto", has_price=False, intake_status=None,
        original_notice_missing=original_missing(cx.applyhome_id, cx.notice_date),
    )  # fmt: skip
    assert (sr.scope, sr.reason) == ("보류", ORIGINAL_MISSING)
    # 공고 전 단지(청약홈 번호 없음)는 그대로 '분양가 미공개(공고 전)'
    assert not original_missing(None, None)
    assert judge_scope(inclusion_class="private_sale_apt", inclusion_decision="auto", has_price=False,
                       intake_status=None).reason == "분양가 미공개(공고 전)"  # fmt: skip


def test_same_day_recollect_is_unchanged(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    ah, pdf = _setup(test_settings, factory)
    _collect(make_ctx, ah, pdf)
    before = {k: (c.id, c.name, c.official_site_url, c.notice_date) for k, c in _complexes(factory).items()}
    again = _collect(make_ctx, ah, pdf)
    after = {k: (c.id, c.name, c.official_site_url, c.notice_date) for k, c in _complexes(factory).items()}
    assert after == before
    assert again.change_event_ids == [], f"같은 날 다시 수집한 change_event {len(again.change_event_ids)}건"
