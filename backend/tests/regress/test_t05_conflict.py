"""T5 해링턴 세대수 1,573 vs 1,769 (RA §9) — 시스템 경계.

RA §9 기대 결과(원문): "`conflict_group` 1건, chosen = 청약홈 상세 값, 다른 값 chosen=false 보관,
compare 미호출(1차 vs 1차가 아닐 때만), 출처 패널에 둘 다 표시".

경로: 원문 행(raw_document 9066 청약홈 상세·9067 공고문, devseed 적재) → 정규화 저장 진입점
``app.normalize.store.store_raw_document``(수집 잡이 원문마다 부르는 함수) → field_provenance·complex →
POST /api/jobs ``rejudge``(complex 13) → worker(FakeJev, 실제 JevMcpAdapter 경로) → P5 compare 여부 →
GET /complexes/13 · GET /provenance/fp_… (출처 패널).

픽스처 어댑터(숨기지 않는 것): ``raw/t5_harrington/*.txt`` 는 재구성 발췌라 운영 파서(청약홈 HTML·공고문 PDF 텍스트)가
읽지 못한다(후보 0건/세대수 없음). 그래서 이 픽스처의 파서 출력 형태인 ``candidates.json`` 을 ``store_raw_document(parser=…)``
로 넣는다. 그 entity_key('applyhome_id:2025000271+2025000273+2025000274')는 저장소 키 규칙(complex = 주택관리번호)이 아니라서
해링턴 단지 행(complex 13, applyhome_id 2025000271)의 키 '2025000271' 로 바꿔 넣는다.
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from .conftest import FIXTURE, SNAP, WRITE, RegressEnv, api_get, load_json

pytestmark = pytest.mark.regress

CANDS = FIXTURE / "raw" / "t5_harrington" / "candidates.json"
HARRINGTON = 13
KEY = "2025000271"
RAW_DETAIL, RAW_NOTICE = 9066, 9067


class CandidatesParser:
    """원문 id → 픽스처 후보(``candidates.json``). 운영 ``Parser`` 프로토콜(parse(raw) → FieldCandidate 목록)."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def parse(self, raw: Any) -> list[Any]:
        from app.core.contracts_gen import FieldCandidate

        return [
            FieldCandidate.model_validate({**r, "entity_key": KEY, "entity_id": None})
            for r in self.rows
            if r["raw_document_id"] == raw.id
        ]


def _store(env: RegressEnv, order: tuple[int, ...]) -> None:
    from app.models import RawDocument
    from app.normalize.store import store_raw_document

    parser = CandidatesParser(load_json(CANDS))
    for rid in order:
        with env.session() as s:
            raw = s.get(RawDocument, rid)
            assert raw is not None, f"raw_document {rid} 없음(devseed raw/documents.json)"
            store_raw_document(s, raw, snapshot_id=SNAP, parser=parser)
            s.commit()


def _units_rows(env: RegressEnv) -> list[Any]:
    from app.models import FieldProvenance

    with env.session() as s:
        return list(
            s.scalars(
                select(FieldProvenance)
                .where(
                    FieldProvenance.entity == "complex",
                    FieldProvenance.entity_id == HARRINGTON,
                    FieldProvenance.field == "units_total",
                )
                .order_by(FieldProvenance.id)
            )
        )


def _check_db(env: RegressEnv) -> tuple[Any, Any]:
    from app.models import Complex

    rows = [r for r in _units_rows(env) if r.raw_document_id in (RAW_DETAIL, RAW_NOTICE)]
    assert len(rows) == 2, [(r.id, r.raw_document_id, r.value_text) for r in _units_rows(env)]
    groups = {r.conflict_group for r in _units_rows(env) if r.conflict_group}
    assert len(groups) == 1 and all(r.conflict_group for r in rows), [
        (r.id, r.value_text, r.conflict_group) for r in _units_rows(env)
    ]
    chosen = [r for r in _units_rows(env) if r.chosen]
    assert len(chosen) == 1, [(r.id, r.value_text, r.chosen) for r in _units_rows(env)]
    win = chosen[0]
    lose = next(r for r in rows if r.raw_document_id == RAW_NOTICE)
    assert (win.raw_document_id, win.value_text, win.source_rank) == (RAW_DETAIL, "1,573세대", 1)
    assert (lose.chosen, lose.value_text, lose.source_rank) == (False, "1,769세대", 2)
    with env.session() as s:
        cx = s.get(Complex, HARRINGTON)
        assert cx is not None and cx.units_total == 1573
    return win, lose


@pytest.mark.parametrize(
    "order", [(RAW_DETAIL, RAW_NOTICE), (RAW_NOTICE, RAW_DETAIL)], ids=["detail_first", "notice_first"]
)
def test_t05_conflict_group_chosen_applyhome_kept_other(env: RegressEnv, order: tuple[int, ...]) -> None:
    """저장 순서와 무관하게 conflict_group 1건, chosen = 청약홈 상세 1,573, 공고문 1,769 는 chosen=false 로 보관."""
    _store(env, order)
    _check_db(env)


def test_t05_no_compare_and_panel_shows_both(env: RegressEnv) -> None:
    from app.models import FieldProvenance, JudgmentLog

    _store(env, (RAW_DETAIL, RAW_NOTICE))
    win, lose = _check_db(env)

    # rejudge(해링턴) — 공개 API 로 잡 등록 → worker. 청약홈(1) vs 공고문(2)는 같은 순위 1차·1차가 아니므로 compare 미호출
    r = env.client.post(
        "/api/jobs", headers=WRITE,
        json={"job_name": "rejudge", "payload": {"snapshot_id": SNAP, "scenario_id": None, "complex_ids": [HARRINGTON], "reason": "T5 세대수 상충"}},
    )  # fmt: skip
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    env.worker(env.ctx("fake"))
    job = api_get(env, f"/jobs/{job_id}")
    assert job["status"] == "done", job
    assert env.jev.calls, "판정기 실제 경로가 돌지 않음(FakeJev 호출 0)"
    compares = [a for t, a in env.jev.calls if t == "jev_compare"]
    assert compares == [], f"compare 가 호출됨: {compares}"
    with env.session() as s:
        logs = s.scalars(
            select(JudgmentLog).where(
                JudgmentLog.tool == "compare", JudgmentLog.purpose == f"compare:{win.conflict_group}"
            )
        ).all()
        assert logs == [], [(j.seq, j.purpose) for j in logs]
        for fp_id in (win.id, lose.id):
            fp = s.get(FieldProvenance, fp_id)
            assert fp is not None and fp.compare_judgment_seq is None, (
                fp_id,
                fp.compare_judgment_seq if fp else None,
            )

    # 출처 패널: 상세 화면의 세대수 Fact → fp_<chosen> → 패널에 채택값 + 상충 그룹의 다른 값(chosen=false).
    # 계약 .10(D13-1): 발행 SNAP 은 저장본(재판정 전 값) — 재판정이 쓴 새 리비전(발행 뒤 기본 화면)을 본다
    newest = api_get(env, "/regions/1/snapshots")[0]
    assert newest["id"] != SNAP and newest["status"] == "published", newest
    body = api_get(env, f"/complexes/{HARRINGTON}", snapshot=newest["id"])
    units = body["header"]["units_total"]
    assert units["v"] == 1573 and units["prov"] == f"fp_{win.id}", units
    panel = api_get(env, f"/provenance/{units['prov']}")
    assert panel["kind"] == "field" and panel["chosen"] is True, panel
    assert (panel["value_text"], panel["source_kind"], panel["source_rank"]) == (
        "1,573세대",
        "applyhome_detail",
        1,
    ), panel
    assert panel["conflict_group"] == win.conflict_group
    others = {c["id"]: c for c in panel["conflicts"]}
    assert f"fp_{lose.id}" in others, panel["conflicts"]
    o = others[f"fp_{lose.id}"]
    assert (o["value_text"], o["chosen"], o["source_kind"], o["source_rank"]) == (
        "1,769세대",
        False,
        "notice_pdf",
        2,
    ), o
    # 다른 값 쪽 패널에서도 채택값이 보인다(둘 다 표시)
    back = api_get(env, f"/provenance/fp_{lose.id}")
    assert back["chosen"] is False and any(
        c["id"] == f"fp_{win.id}" and c["chosen"] for c in back["conflicts"]
    ), back
