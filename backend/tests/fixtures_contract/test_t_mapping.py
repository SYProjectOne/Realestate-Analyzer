"""완료 기준 2: T1~T18 각각 필요한 픽스처가 있다 (RA §9 표 ↔ 픽스처 README 매핑 표).

README.md의 '| T<n> |' 행에서 백틱으로 적은 경로를 모아 존재를 검사하고, 사례별 핵심 내용을 확인한다.
"""

# ruff: noqa: E501  (한국어 assertion 메시지)
from __future__ import annotations

import re
from typing import Any

import pytest

from ._fx import FIXTURE, JUDGMENTS, RAW, iter_facts, load_json

pytestmark = pytest.mark.regress

README = FIXTURE / "README.md"
ROW = re.compile(r"^\|\s*(T\d{1,2})\s*\|(.*)$")
PATH = re.compile(r"`([^`]+)`")


def mapping() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in README.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m:
            out[m.group(1)] = [p for p in PATH.findall(m.group(2)) if "/" in p or p.endswith((".json", ".txt", ".md", ".py", ".png"))]
    return out


def bundle(cid: int) -> dict[str, Any]:
    b: dict[str, Any] = next(x for x in load_json(FIXTURE / "complexes.json") if x["complex"]["id"] == cid)
    return b


def judgment(seq: int) -> dict[str, Any]:
    row = next(r for r in load_json(JUDGMENTS / "_index.json") if r["judgment_seq"] == seq)
    doc: dict[str, Any] = load_json(JUDGMENTS / row["file"])
    return doc


def test_mapping_table_has_t1_to_t18() -> None:
    m = mapping()
    assert sorted(m, key=lambda t: int(t[1:])) == [f"T{i}" for i in range(1, 19)]


@pytest.mark.parametrize("case", [f"T{i}" for i in range(1, 19)])
def test_mapped_fixtures_exist(case: str) -> None:
    paths = mapping()[case]
    assert paths, f"{case}: 매핑 표에 픽스처 경로가 없다"
    repo_root = FIXTURE.parents[2]
    for rel in paths:
        target = (repo_root / rel) if rel.startswith("contracts/") else (FIXTURE / rel)
        assert target.exists(), f"{case}: {rel} 없음"


def test_t3_switzen_403() -> None:
    docs = load_json(RAW / "documents.json")
    d403 = [d for d in docs if d["complex_id"] == 4 and d["source_kind"] == "official_site"]
    assert d403 and d403[0]["http_status"] == 403 and d403[0]["path"] is None
    intake = bundle(4)["intake"]
    official = [i for i in intake if i["path"] == "official_popup"]
    assert official[0]["status"] == "확인 불가" and official[0]["http_status"] == 403 and official[0]["reason"] == "403"
    hc = load_json(RAW / "human_check/t3_switzen_possible.json")
    assert hc["complex_id"] == 4 and hc["field"] == "intake_status" and hc["value_text"] == "가능"


def test_t4_single_outlier() -> None:
    doc = load_json(RAW / "rtms/t4_metroxi2_84.json")
    prices = sorted(t["price_won"] for t in doc["trades"])
    assert len(prices) >= 8
    assert prices[-1] == 1_100_000_000 and prices[-2] <= 680_000_000, "84㎡ 중 1건만 크게 벗어남(11억)"
    assert doc["label"] == "재가공" and doc["source_url"].startswith("https://")


def test_t5_conflict_candidates() -> None:
    cands = load_json(RAW / "t5_harrington/candidates.json")
    values = {(c["source_kind"], c["value"]) for c in cands}
    assert values == {("applyhome_detail", 1573), ("notice_pdf", 1769)}
    ranks = {c["source_kind"]: c["source_rank"] for c in cands}
    assert ranks == {"applyhome_detail": 1, "notice_pdf": 2}
    assert len({c["entity_key"] for c in cands}) == 1 and len({c["field"] for c in cands}) == 1


def test_t6_composite_claim() -> None:
    doc = load_json(RAW / "claims/t6_composite.json")
    assert "unlikely" in doc["claims"][0]["text"] and "uncertain" in doc["claims"][0]["text"]
    assert doc["claims"][0]["judgment_seq"] == 131 and doc["expected_min_atomic_claims"] >= 2


def test_t8_popup_pairs() -> None:
    pairs = load_json(RAW / "official_site/t8_popup_pairs.json")
    assert pairs["yesterday"]["image_hash"] == pairs["today_same"]["image_hash"]
    assert pairs["yesterday"]["image_hash"] != pairs["today_changed"]["image_hash"]
    a = (RAW / "applyhome_list/2026-10-07.json").read_bytes()
    b = (RAW / "applyhome_list/2026-10-08.json").read_bytes()
    assert a == b, "변경 없는 날: 목록 바이트 동일"


def test_t9_payment_terms_two_notices() -> None:
    terms = bundle(7)["payment_terms"]
    assert len(terms) == 2
    first = next(t for t in terms if not t["is_current"])
    cur = next(t for t in terms if t["is_current"])
    assert first["down_payment_pct"]["v"] == 10 and cur["down_payment_pct"]["v"] == 5
    assert cur["change_vs_first"]["down_payment_pct_delta"]["v"] == -5
    assert cur["notice_kind"] == "임의"
    docs = {d["url"] for d in load_json(RAW / "documents.json") if d["complex_id"] == 7 and d["source_kind"] == "notice_pdf"}
    assert len(docs) == 2, "같은 단지 공고 2건(원문 발췌)"


def test_t10_move_in_far_apart() -> None:
    gochon, river = bundle(11)["complex"], bundle(9)["complex"]
    assert gochon["move_in_ym"]["v"] < "2027-01" and river["move_in_ym"]["v"] == "2031-01"
    assert judgment(119)["complex_id"] == 9 and judgment(120)["complex_id"] == 11


def test_t11_substitute_comparables() -> None:
    doc = load_json(RAW / "rtms/t11_switzen_comparables.json")
    names = {t["apt_name"] for t in doc["trades"]}
    assert any("리버시티" in n for n in names) and any("센트럴자이" in n for n in names)
    assert all((t["completed_year"] or 0) < 2026 for t in doc["trades"]), "신축(같은 산단 입주 단지) 0건"


def test_t13_removed_provenance() -> None:
    exp = load_json(RAW / "t13_missing_provenance/expected.json")
    removed = set(exp["removed_prov_ids"])
    prov = {r["id"] for r in load_json(RAW / "t13_missing_provenance/provenance.json")}
    used = {f["prov"] for _, f in iter_facts(load_json(RAW / "t13_missing_provenance/complexes.json")) if f["prov"]}
    assert removed and removed <= used and not (removed & prov)


def test_t14_guard_payloads() -> None:
    doc = load_json(RAW / "guard/t14_payloads.json")
    kinds = {c["kind"] for c in doc["cases"]}
    assert {"phone", "email", "resident_no", "env_value"} <= kinds
    assert all(c["expect_status"] == "blocked" for c in doc["cases"])


def test_t16_synth_tool_exists() -> None:
    assert (FIXTURE.parent / "tools" / "synth.py").is_file()


def test_t18_judge_down() -> None:
    doc = load_json(RAW / "scenarios/t18_judge_down.json")
    assert doc["raise"] == "JudgeUnavailable"
    assert doc["expected_snapshot"]["degraded"] is True
