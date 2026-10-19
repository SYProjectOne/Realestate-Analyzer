"""D31-3 P2 extract — 언론 기사 분양가: 필드·purpose, auto 값만 돌려준다(review·빈 값·ok 아닌 봉투는 버림)."""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

from app.judge import payloads as P
from app.judge import pipeline


class _Stub:
    def __init__(self, status: str, fields: list[dict[str, Any]]) -> None:
        self.status, self.fields = status, fields
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    def call(self, tool: str, payload: dict[str, Any], purpose: str, **_kw: Any) -> Any:
        self.calls.append((tool, payload, purpose))
        return SimpleNamespace(status=self.status, result={"fields": self.fields})


def test_fields_name_the_complex_and_patterns_find_amounts() -> None:
    fields = P.benchmark_price_extract_fields("송도더베뉴")
    assert [f.id for f in fields] == list(P.BENCHMARK_PRICE_FIELDS)
    assert all("'송도더베뉴' 단지" in f.description for f in fields)
    price = re.compile(fields[0].pattern)
    for text in ("4억1320만원", "3억 9천만 원", "4억 원", "4억800만원"):
        assert price.search(text), text
    assert re.compile(fields[1].pattern).search("3.3㎡당 1,238만원")


def test_returns_auto_values_only() -> None:
    stub = _Stub(
        "ok",
        [
            {"name": "price_84", "value_text": " 4억1320만원 ", "decision": "auto"},
            {"name": "price_per_3_3", "value_text": "1238만원", "decision": "review"},
            {"name": "public_sale", "value_text": None, "decision": "auto"},
        ],
    )
    got = pipeline.p2_extract_benchmark_price(
        stub,  # type: ignore[arg-type]
        target_key="ntabc",
        name="송도더베뉴",
        document="문서",
        snapshot_id=3,
    )
    assert got == {"price_84": "4억1320만원"}
    tool, payload, purpose = stub.calls[0]
    assert tool == "extract" and purpose == "extract:bm_price:ntabc"
    assert payload["purpose"] == P.BENCHMARK_PRICE_PURPOSE and payload["document"] == "문서"


def test_not_ok_envelope_gives_nothing() -> None:
    stub = _Stub("review", [{"name": "price_84", "value_text": "4억원", "decision": "auto"}])
    got = pipeline.p2_extract_benchmark_price(
        stub,  # type: ignore[arg-type]
        target_key="k",
        name="n",
        document="d",
        snapshot_id=None,
    )
    assert got == {}


def test_descriptions_carry_the_place_to_tell_same_name_complexes_apart() -> None:
    fields = P.benchmark_price_extract_fields("유승한내들 에듀파크", "인천광역시 서구 당하동")
    assert all("인천광역시 서구 당하동에 있는 '유승한내들 에듀파크' 단지" in f.description for f in fields)
    assert "다른 지역의 같은 이름 단지" in fields[0].description


def test_link_payload_puts_none_first_and_rejects_reserved_ids() -> None:
    import pytest

    p = P.classify_benchmark_link_payload(
        "청약 공고 단지: 송도 미래 1차", [("g1", "실거래 단지 '신송도역센트럴뷰'")]
    )
    assert [c["id"] for c in p["classes"]] == [P.BENCHMARK_LINK_NONE, "g1"]
    assert p["items"][0]["id"] == "n"
    with pytest.raises(ValueError):
        P.classify_benchmark_link_payload("x", [("none", "y")])


def test_p4_classify_benchmark_link_returns_the_single_item() -> None:
    class _One:
        def call(self, tool: str, payload: dict[str, Any], purpose: str, **_kw: Any) -> Any:
            assert tool == "classify" and purpose == "classify:bm_link:2021000101:2021000101"
            return SimpleNamespace(status="ok", result={"label": "g1", "prob": 0.97, "decision": "auto"})

    o = pipeline.p4_classify_benchmark_link(
        _One(),  # type: ignore[arg-type]
        notice_key="2021000101:2021000101",
        text="t",
        candidates=[("g1", "d")],
        snapshot_id=None,
    )
    assert (o.label, o.resolved) == ("g1", True)
