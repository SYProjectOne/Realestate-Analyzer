"""R3b G1 — 판정기 입력(judge/): N-M2(D10-6) · C3 · F1b(ADAPTER_CODE_VERSION · Mock '합성' 표식).

N-M2: 뉴스 → P1 screen(호재 관련성) 입력, P4 호재 분류 클래스에 '호재 아님', 종류(kind)도 classify 입력.
      파이프라인 연결(통과분만 후보, '호재 아님'이면 후보 폐기·기록)은 G2(scheduler)가 이 함수들을 부른다.
C3: OCR 필드가 32개를 넘어도 잘리지 않게 extract 요청을 32개 단위로 나눈다.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.contracts_gen import FieldCandidate
from app.core.protocols import canonical_hash_json
from app.judge import payloads as P
from app.judge import pipeline
from app.judge.base import ADAPTER_CODE_VERSION, CANONICAL_FINGERPRINT, CANONICAL_SAMPLE
from app.judge.mock import SYNTHETIC_KEY, MockAdapter, is_synthetic, write_recording
from app.models import JudgmentLog
from app.models.enums import CATALYST_KIND
from app.normalize.extract_request import EXTRACT_FIELDS_MAX, build_extract_requests

from .conftest import FakeTransport
from .test_payloads import assert_jev_valid

# ---------------------------------------------------------------- N-M2 (D10-6)


def test_nm2_catalyst_classes_include_not_catalyst() -> None:
    ids = [c["id"] for c in P.CATALYST_CLASSES]
    assert P.NOT_CATALYST == "호재 아님" and P.NOT_CATALYST in ids
    payload = P.classify_catalyst_payload(item_id="catalyst:1", text="송도 신규 분양 청약 일정 안내")
    assert_jev_valid("classify", payload)
    assert P.NOT_CATALYST in [c["id"] for c in payload["classes"]]


def test_nm2_catalyst_screen_payload_is_relevance_check() -> None:
    payload = P.catalyst_screen_payload(
        title="GTX-B 송도역 착공", excerpt="국토부는 GTX-B 노선 착공을 발표했다. 문의 010-1234-5678",
        url="https://news.example.com/a/1",
    )
    assert_jev_valid("screen", payload)
    assert "GTX-B 송도역 착공" in payload["text"] and "010-1234-5678" not in payload["text"]
    assert "호재" in payload["purpose"] and "분양" in payload["purpose"]  # 분양 광고·일정 기사는 호재 아님을 목적에 적는다
    assert not {"block_at", "review_at"} & set(payload)


def test_nm2_catalyst_kind_payload_uses_contract_kinds() -> None:
    payload = P.classify_catalyst_kind_payload(item_id="catalyst:1", text="지하철 7호선 연장 착공")
    assert_jev_valid("classify", payload)
    assert [c["id"] for c in payload["classes"]] == list(CATALYST_KIND)


def _classify_raw(label: str, decision: str = "auto") -> dict[str, Any]:
    return {
        "tool": "jev_classify", "model": "jev-1.13.0",
        "thresholds": {"auto_accept": 0.85, "minimum_margin": 0.5},
        "results": [{"id": "x", "classification": label, "probabilities": {label: 0.97}, "confidence": 0.97,
                     "margin": 0.9, "top_probability": 0.97, "decision": decision}],
    }  # fmt: skip


def test_nm2_pipeline_screen_and_not_catalyst(make_adapter: Callable[..., Any]) -> None:
    adapter = make_adapter(FakeTransport(responses={"jev_classify": _classify_raw("호재 아님")}))
    s = pipeline.p1_screen_catalyst(adapter, catalyst_key="7", title="송도 분양 일정", excerpt="청약 접수 안내", url="https://n.example.com/1")
    assert s.usable is True  # 녹화 screen = pass
    out = pipeline.p4_classify_catalyst(adapter, catalyst_key="7", text="송도 분양 일정")
    assert out.label == P.NOT_CATALYST and pipeline.is_not_catalyst(out)
    assert pipeline.catalyst_stage(out) is None  # 단계 아님 → 후보 폐기(G2)


def test_nm2_pipeline_kind_classify(make_adapter: Callable[..., Any]) -> None:
    adapter = make_adapter(FakeTransport(responses={"jev_classify": _classify_raw("교통")}))
    out = pipeline.p4_classify_catalyst_kind(adapter, catalyst_key="7", text="GTX-B 착공")
    assert out.label == "교통" and out.resolved
    assert pipeline.catalyst_kind(out) == "교통"
    review = make_adapter(FakeTransport(responses={"jev_classify": _classify_raw("교통", "review")}))
    out2 = pipeline.p4_classify_catalyst_kind(review, catalyst_key="8", text="GTX-B 착공 검토")
    assert pipeline.catalyst_kind(out2) == "기타"  # 미해결은 '기타'(판단 대체 없음)


def test_nm2_stage_resolved_only() -> None:
    assert set(P.CATALYST_STAGE_CLASSES) == {"확정", "계획", "추진", "언론", "미확정"}


# ---------------------------------------------------------------- C3


def _cand(i: int) -> FieldCandidate:
    return FieldCandidate(
        entity="complex_type", entity_id=None, entity_key="2026000001:84A", field=f"price_by_type.T{i:02d}.max_price_won",
        value_text=None, value=None, source_rank=1, source_kind="notice_pdf", primary=True, label="확인 불가",
        reason="OCR", excerpt=f"T{i:02d} 공급금액 …", excerpt_start=i, excerpt_end=i + 1, raw_document_id=5,
        url="https://static.applyhome.co.kr/x.pdf", checked_at="2026-10-09", observed_on="2026-09-01", needs_extract=True,
    )  # fmt: skip


def test_c3_more_than_32_fields_split_without_truncation() -> None:
    reqs = build_extract_requests([_cand(i) for i in range(70)])
    assert EXTRACT_FIELDS_MAX == 32
    assert [len(r.fields) for r in reqs] == [32, 32, 6]
    assert [f for r in reqs for f in r.fields] == [f"price_by_type.T{i:02d}.max_price_won" for i in range(70)]
    assert "T00 " in reqs[0].text and "T40 " not in reqs[0].text and "T40 " in reqs[1].text


# ---------------------------------------------------------------- F1b 버전·합성 표식


def test_f1b_adapter_code_version_bumped_and_canonical_fingerprint_pinned() -> None:
    """정준화(canonical_value·canonical_hash_json) 정의가 바뀌면 이 지문이 깨진다 → ADAPTER_CODE_VERSION 을 올리고
    지문을 갱신한다(전체 재판정 1회). R3 정준화 변경으로 0.1.0 → 0.2.0."""
    assert ADAPTER_CODE_VERSION != "0.1.0"
    got = hashlib.sha256(canonical_hash_json(CANONICAL_SAMPLE).encode("utf-8")).hexdigest()
    assert got == CANONICAL_FINGERPRINT, "정준화 규칙 변경 — ADAPTER_CODE_VERSION 을 올리고 CANONICAL_FINGERPRINT 갱신"


def test_f1b_mock_replay_rows_are_marked_synthetic(tmp_path: Path, session_factory: sessionmaker[Session], samples: dict[str, Any]) -> None:
    (tmp_path / "judgments").mkdir()
    (tmp_path / "judgments" / "_meta.json").write_text(json.dumps({"adapter_version": "0.2.0+jev-mcp@0.14.1"}), encoding="utf-8")
    mock = MockAdapter(tmp_path, secrets=[], session_factory=session_factory)
    payload = P.screen_payload("공고 발췌", task="t")
    from app.core.contracts_gen import JudgmentEnvelope
    from app.judge import cache

    key = cache.compute_hash("screen", "screen:x", payload, mock.adapter_version)
    write_recording(tmp_path, JudgmentEnvelope(
        tool="screen", purpose="screen:x", input_hash=key, input_len=10, status="ok", confidence=0.9, cached=False,
        result={"verdict": "pass"}, raw=samples["jev_screen"]["response"], duration_ms=5, judgment_seq=None,
        created_at="2026-10-09T06:00:00+09:00", adapter_version=mock.adapter_version,
    ))  # fmt: skip
    env = mock.call("screen", payload, "screen:x")
    assert is_synthetic(env.raw)
    with session_factory() as s:
        row = s.scalars(select(JudgmentLog).where(JudgmentLog.input_hash == key)).one()
        assert row.output_json.get(SYNTHETIC_KEY) and is_synthetic(row.output_json)
    plain = MockAdapter(tmp_path, secrets=[]).call("screen", payload, "screen:x")  # DB 없이: 녹화와 동일(픽스처 규칙)
    assert not is_synthetic(plain.raw)
