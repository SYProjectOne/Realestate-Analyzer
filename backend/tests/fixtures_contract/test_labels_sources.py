"""완료 기준 3: 수치 필드 전부 라벨·출처가 있다 (AGENTS 5, RA §3 field_provenance).

픽스처의 모든 Fact를 전수 검사한다.
- label은 5종 중 하나(빈 라벨 금지).
- label='확인 불가'면 reason(사유)이 있다.
- 그 밖의 라벨이면 prov가 있고, prov가 가리키는 출처가 실제로 있다:
  fp_/cs_/rd_ → provenance.json 행(출처 URL·확인일·라벨), jl_ → judgments/_index.json 의 judgment_seq.
- 출처 행의 url은 http(s) URL, checked_at은 날짜, 라벨은 Fact 라벨과 같다.
"""

# ruff: noqa: E501  (한국어 assertion 메시지)
from __future__ import annotations

import re
from typing import Any

import pytest

from ._fx import FIXTURE, JUDGMENTS, LABELS, RAW, iter_facts, load_json

pytestmark = pytest.mark.regress

URL = re.compile(r"^https?://[^\s]+$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Fact가 들어 있는 픽스처(출처 맵 = provenance.json 공유)
FACT_FILES = ["complexes.json", "region.json"]


def provenance() -> dict[str, dict[str, Any]]:
    rows = load_json(FIXTURE / "provenance.json")
    out = {r["id"]: r for r in rows}
    assert len(out) == len(rows), "provenance id 유일"
    return out


def judgment_seqs() -> set[int]:
    return {r["judgment_seq"] for r in load_json(JUDGMENTS / "_index.json")}


def all_facts() -> list[tuple[str, dict[str, Any]]]:
    facts: list[tuple[str, dict[str, Any]]] = []
    for rel in FACT_FILES:
        facts += [(f"{rel}{p}", f) for p, f in iter_facts(load_json(FIXTURE / rel))]
    return facts


def test_fact_count_is_substantial() -> None:
    facts = all_facts()
    assert len(facts) > 500, f"Fact {len(facts)}개 — 16단지 수치 필드가 다 들어 있어야 한다"


def test_every_fact_has_label_and_reason_or_source() -> None:
    prov = provenance()
    seqs = judgment_seqs()
    problems: list[str] = []
    for path, f in all_facts():
        label = f["label"]
        if label not in LABELS:
            problems.append(f"{path}: 라벨 {label!r}")
            continue
        if label == "확인 불가":
            if not (f.get("reason") or "").strip():
                problems.append(f"{path}: 확인 불가 사유 없음")
            continue
        p = f["prov"]
        if not p:
            problems.append(f"{path}: prov 없음")
        elif p.startswith("jl_"):
            if int(p[3:]) not in seqs:
                problems.append(f"{path}: 판정 {p} 녹화 없음")
        elif p not in prov:
            problems.append(f"{path}: 출처 {p} 행 없음")
        if f["checked_at"] is None or not DATE.match(f["checked_at"]):
            problems.append(f"{path}: 확인일 없음")
    assert problems == [], "\n".join(problems[:40])


def test_provenance_rows_have_url_date_label() -> None:
    problems: list[str] = []
    for pid, row in provenance().items():
        if row["kind"] == "judgment":
            if row["judgment_seq"] is None:
                problems.append(f"{pid}: judgment_seq 없음")
            continue
        if not (row["url"] and URL.match(row["url"])):
            problems.append(f"{pid}: url {row['url']!r}")
        if not (row["checked_at"] and DATE.match(row["checked_at"])):
            problems.append(f"{pid}: checked_at")
        if not row["excerpt"]:
            problems.append(f"{pid}: 발췌 없음")
    assert problems == [], "\n".join(problems[:40])


def test_fact_label_equals_provenance_label() -> None:
    prov = provenance()
    bad = [
        f"{path}: Fact {f['label']} ≠ 출처 {prov[f['prov']]['label']}"
        for path, f in all_facts()
        if f["prov"] in prov and f["label"] != "확인 불가" and prov[f["prov"]]["label"] != f["label"]
    ]
    assert bad == [], "\n".join(bad[:20])


def test_provenance_excerpt_offsets_point_into_raw_text() -> None:
    """출처 행이 raw 문서를 가리키면 excerpt_start/end가 그 텍스트의 발췌 위치다(G3 하이라이트)."""
    docs = {d["id"]: d for d in load_json(RAW / "documents.json")}
    checked = 0
    for pid, row in provenance().items():
        rid = row["raw_document_id"]
        if rid is None:
            continue
        assert rid in docs, f"{pid}: raw_document {rid} 없음"
        doc = docs[rid]
        assert doc["url"] == row["url"], f"{pid}: 출처 URL과 raw url 다름"
        if row["excerpt_start"] is None:
            continue
        text = (RAW / doc["text_path"]).read_text(encoding="utf-8")
        assert text[row["excerpt_start"] : row["excerpt_end"]] == row["excerpt"], pid
        checked += 1
    assert checked > 200, f"오프셋 검사 {checked}건 — 공고문 발췌 수치는 오프셋을 가져야 한다"


def test_unverifiable_values_explain_why() -> None:
    """보고서에 없는 값은 '확인 불가(사유)' — 사유 문자열이 비어 있지 않고 120자 이하."""
    reasons = [f["reason"] for _, f in all_facts() if f["label"] == "확인 불가"]
    assert reasons, "보고서에 없는 값이 하나도 없을 수는 없다(공고 전 단지 등)"
    assert all(0 < len(r) <= 120 for r in reasons)
