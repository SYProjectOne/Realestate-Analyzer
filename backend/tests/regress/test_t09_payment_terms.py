"""T9 임의공급 계약금 10% → 5% (RA §9) — 시스템 경계.

RA §9 기대 결과(원문): "`payment_terms` 행 2개, 현재 조건 = 최신, `change_event` critical, 유동성 점수 D/5 항 2 → 1로 +1".
(픽스처: 같은 단지 공고 2건 = 칸타빌(complex 7) ``raw/notice/07_n.txt``(최초 공고, 계약금 10%) ·
``raw/notice/07_r2.txt``(임의공급 2차, 계약금 5%), ``complexes.json`` id 7 payment_terms 2행)

경로(이틀): 칸타빌의 payment_terms 행(devseed)을 비운 뒤
- 1일차(2026-10-09): POST /api/jobs ``collect.daily``(sources=[notice_pdf]) → worker 의 수집 단계가 원문 9022(07_n)를
  ``normalize.store.store_raw_document`` 로 저장 → 첫 납부 조건 행. 같은 스냅샷 rejudge(칸타빌)를 API 로 넣어 점수 기준선.
- 2일차(2026-10-10): 같은 잡으로 원문 9025(07_r2) → 둘째 행 + change_event(critical) → 변경 감지가 rejudge 자동 등록 →
  FakeJev 파이프라인 점수. 확인은 GET /complexes/7 · GET /snapshots/{sid}/changes · DB 행.

픽스처 어댑터(숨기지 않는 것): 07_n·07_r2 는 재구성 발췌라 운영 공고문 파서(``NoticeParser``)가 계약금·공고번호를 읽지 못한다
(머리 주석 줄을 단지명으로 읽고, 07_r2 는 최초 주택관리번호 문장이 없어 새 단지 키 2026940116 을 만든다). 그래서 파서만
픽스처 줄을 그대로 읽는 어댑터(운영 파서와 같은 후보 모양: payment_terms ``<단지 키>:<공고번호>``)로 바꾸고, 나머지(수집 잡·저장·
변경 감지·rejudge·점수·API)는 운영 경로 그대로 쓴다.
"""

# ruff: noqa: E501

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pytest
from sqlalchemy import delete, select

from .conftest import WRITE, RegressEnv, api_get, cur

pytestmark = pytest.mark.regress

CANTAVIL = 7
COMPLEX_KEY = "2025000573"  # 칸타빌 최초 주택관리번호(complex.applyhome_id)
RAW_FIRST, RAW_R2 = 9022, 9025  # raw/documents.json: notice/07_n.txt · notice/07_r2.txt

# 원문 id → (공고번호, 공고 종류, [(field, 줄 정규식, 값, 라벨, reason)])
NOTICES: dict[int, tuple[str, str, list[tuple[str, str, Any, str, str | None]]]] = {
    RAW_FIRST: (
        "2025000573",
        "본청약",
        [
            ("effective_from", r"^공고 2025-11-21$", "2025-11-21", "확인됨", None),
            ("down_payment_pct", r"^계약금 10%\(최초 공고\)$", 10.0, "확인됨", None),
        ],
    ),
    RAW_R2: (
        "2026940116",
        "임의",
        [
            ("effective_from", r"^임의 2차 접수 06-12~15$", "2026-06-12", "추정", "접수 시작일로 대체"),
            ("down_payment_pct", r"^계약금 5%\(계약 시\)$", 5.0, "확인됨", None),
            ("interim_pct", r"^중도금 60%\(6회, 26-07-24~29-05-25\)$", 60.0, "확인됨", None),
            ("balance_pct", r"^잔금 35%$", 35.0, "확인됨", None),
        ],
    ),
}


class FixtureNoticeParser:
    """재구성 발췌 txt 의 줄을 그대로 읽어 payment_terms 후보를 낸다(발췌·오프셋 = 그 줄)."""

    source_kind = "notice_pdf"

    def __init__(self, raw_dir: Any) -> None:
        self.raw_dir = raw_dir

    def parse(self, raw: Any) -> list[Any]:
        from app.core.contracts_gen import FieldCandidate

        notice_no, kind, fields = NOTICES[raw.id]
        text = (self.raw_dir / raw.text_path).read_text(encoding="utf-8")
        key = f"{COMPLEX_KEY}:{notice_no}"
        eff = next(v for f, _, v, _, _ in fields if f == "effective_from")
        out = []

        def cand(field: str, value: Any, m: re.Match[str], label: str, reason: str | None) -> Any:
            return FieldCandidate.model_validate(
                {
                    "entity": "payment_terms", "entity_id": None, "entity_key": key, "field": field,
                    "value_text": m.group(0), "value": value, "source_rank": 1, "source_kind": "notice_pdf",
                    "primary": True, "label": label, "reason": reason, "excerpt": m.group(0),
                    "excerpt_start": m.start(), "excerpt_end": m.end(), "raw_document_id": raw.id,
                    "url": raw.url, "checked_at": raw.fetched_at[:10], "observed_on": eff, "needs_extract": False,
                }
            )  # fmt: skip

        first_line = re.search(r"^.+$", text, re.M)
        assert first_line is not None
        out.append(cand("notice_kind", kind, first_line, "확인됨", None))
        for field, pattern, value, label, reason in fields:
            m = re.search(pattern, text, re.M)
            assert m is not None, (raw.text_path, pattern)
            out.append(cand(field, value, m, label, reason))
        return out


class NoticeCollector:
    """collect 단계 'notice_pdf' 수집기: 이미 받은 원문 행(raw_document)을 돌려준다(네트워크 없음)."""

    def __init__(self, env: RegressEnv, raw_ids: list[int]) -> None:
        self.env, self.raw_ids = env, raw_ids

    def fetch(self, region: Any, snapshot: Any, since: Any) -> list[Any]:
        from app.models import RawDocument
        from app.normalize.store import raw_dto

        with self.env.session() as s:
            rows = [s.get(RawDocument, i) for i in self.raw_ids]
            assert all(r is not None and r.complex_id == CANTAVIL for r in rows), rows
            return [raw_dto(r) for r in rows if r is not None]


def _clear_terms(env: RegressEnv) -> None:
    """전제: 칸타빌 납부 조건이 아직 없다(devseed 행과 그 출처 행을 비운다 — 정규화 경로가 다시 만든다)."""
    from app.models import FieldProvenance, PaymentTerms

    with env.session() as s:
        ids = list(s.scalars(select(PaymentTerms.id).where(PaymentTerms.complex_id == CANTAVIL)))
        assert len(ids) == 2, f"devseed 칸타빌 payment_terms 2행 예상, 실제 {ids}"
        s.execute(
            delete(FieldProvenance).where(
                FieldProvenance.entity == "payment_terms", FieldProvenance.entity_id.in_(ids)
            )
        )
        s.execute(delete(PaymentTerms).where(PaymentTerms.id.in_(ids)))
        s.commit()


def _daily(env: RegressEnv, raw_ids: list[int]) -> dict[str, Any]:
    r = env.client.post(
        "/api/jobs",
        headers=WRITE,
        json={"job_name": "collect.daily", "payload": {"region_id": 1, "sources": ["notice_pdf"]}},
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    env.worker(env.ctx("fake", collectors={"notice_pdf": lambda ctx: NoticeCollector(env, raw_ids)}))
    job = api_get(env, f"/jobs/{job_id}")
    assert job["status"] == "done", job
    assert job["stats"]["stored"] == len(raw_ids) and not job["stats"]["store_errors"], job["stats"]
    return dict(job["stats"])


def _rejudge(env: RegressEnv, sid: int) -> None:
    r = env.client.post(
        "/api/jobs", headers=WRITE,
        json={"job_name": "rejudge", "payload": {"snapshot_id": sid, "scenario_id": None, "complex_ids": [CANTAVIL], "reason": "T9 기준선"}},
    )  # fmt: skip
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    env.worker(env.ctx("fake"))
    job = api_get(env, f"/jobs/{job_id}")
    assert job["status"] == "done", job


def _liquidity(env: RegressEnv, sid: int) -> tuple[float, str]:
    sid = cur(env, sid)  # 발행 뒤 재판정 = 같은 기준일 새 리비전(D11-1)
    body = api_get(env, f"/complexes/{CANTAVIL}", snapshot=sid, scenario="base")
    assert body["score"] is not None, f"snapshot {sid}: 칸타빌 점수 없음"
    comp = body["score"]["components"]["liquidity"]
    score = comp.get("score", comp)
    assert score["v"] is not None, comp
    formula = api_get(env, f"/provenance/{score['prov']}")["formula_text"] or ""
    return float(score["v"]), formula


def test_t09_two_notices_current_latest_critical_and_liquidity_plus_one(
    env: RegressEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models import ChangeEvent, PaymentTerms
    from app.normalize import store

    real = store.parser_for

    def parser_for(source_kind: str, **kw: Any) -> Any:
        return (
            FixtureNoticeParser(env.settings.raw_dir)
            if source_kind == "notice_pdf"
            else real(source_kind, **kw)
        )

    monkeypatch.setattr(store, "parser_for", parser_for)
    _clear_terms(env)

    # 1일차: 최초 공고(계약금 10%) → 첫 행. 점수 기준선은 같은 스냅샷 rejudge(공개 API)
    day1 = _daily(env, [RAW_FIRST])
    sid1 = int(day1["snapshot_id"])
    with env.session() as s:
        rows = list(s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == CANTAVIL)))
        assert [(r.notice_no, float(r.down_payment_pct or 0)) for r in rows] == [("2025000573", 10.0)]
    _rejudge(env, sid1)
    liq1, f1 = _liquidity(env, sid1)
    assert "D/5(10/5=2)" in f1, f1

    # 2일차: 임의공급 2차(계약금 5%) → 둘째 행 + critical → 변경 감지가 rejudge 자동 등록
    env.clock.day = date(2026, 10, 10)
    day2 = _daily(env, [RAW_R2])
    sid2 = int(day2["snapshot_id"])
    assert sid2 != sid1
    assert day2["rejudge_complex_ids"] == [CANTAVIL], day2
    rj = api_get(env, f"/jobs/{day2['rejudge_job_id']}")
    assert rj["status"] == "done", rj

    with env.session() as s:
        rows = sorted(
            s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == CANTAVIL)),
            key=lambda r: r.effective_from,
        )
        assert [(r.notice_no, r.effective_from, float(r.down_payment_pct or 0)) for r in rows] == [
            ("2025000573", "2025-11-21", 10.0),
            ("2026940116", "2026-06-12", 5.0),
        ]
        new_id = rows[1].id
        evs = list(
            s.scalars(
                select(ChangeEvent).where(ChangeEvent.snapshot_id == sid2, ChangeEvent.complex_id == CANTAVIL)
            )
        )
        dp = [e for e in evs if e.entity == "payment_terms" and e.field == "down_payment_pct"]
        assert len(dp) == 1, [(e.entity, e.field, e.old_text, e.new_text, e.severity) for e in evs]
        assert (dp[0].old_text, dp[0].new_text, dp[0].severity, dp[0].triggers_rejudge, dp[0].entity_id) == (
            "10",
            "5",
            "critical",
            True,
            new_id,
        )

    # API: 변경 목록(critical)
    changes = api_get(env, f"/snapshots/{sid2}/changes", severity="critical")
    items = changes["items"] if isinstance(changes, dict) else changes
    flat = [str(i) for i in items]
    assert any("down_payment_pct" in t and "critical" in t for t in flat), items

    # API: 상세 — 납부 조건 2행, 현재 = 최신(임의 2차 5%), 최초 대비 −5%p
    body = api_get(env, f"/complexes/{CANTAVIL}", snapshot=sid2)
    pays = body["payment"]
    assert len(pays) == 2, pays
    cur = [p for p in pays if p["is_current"]]
    assert len(cur) == 1 and cur[0]["notice_no"] == "2026940116" and cur[0]["down_payment_pct"]["v"] == 5, cur
    assert cur[0]["change_vs_first"]["down_payment_pct_delta"]["v"] == -5, cur[0]["change_vs_first"]

    # 유동성: D/5 항 2 → 1 → 점수 +1 (Y_resale·거주의무는 두 날 같다: 전매 종료 2026-06 이미 지남)
    liq2, f2 = _liquidity(env, sid2)
    assert "D/5(5/5=1)" in f2, f2
    assert liq2 - liq1 == pytest.approx(1.0, abs=1e-6), (liq1, f1, liq2, f2)
