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
