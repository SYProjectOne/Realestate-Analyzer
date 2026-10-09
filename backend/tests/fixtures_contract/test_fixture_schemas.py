"""완료 기준 1: 모든 픽스처가 contracts/schemas/ 스키마를 통과한다 (WP9, RA §4-5).

JSON 파일마다 어떤 스키마로 검증하는지는 SCHEMA_OF가 정한다. 계약에 맞는 스키마가 없는 테스트 입력은
NO_SCHEMA에 이유와 함께 둔다. 둘 다에 없는 JSON 파일이 생기면 test_every_json_file_has_a_schema가 실패한다.
"""

# ruff: noqa: E501  (한국어 assertion 메시지)
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ._fx import FIXTURE, JUDGMENTS, RAW, load_json, schema_errors

pytestmark = pytest.mark.regress

# 파일(픽스처 기준 상대 경로) → (스키마 ref, 모양). 모양: one=객체 1개, list=배열 원소마다, key:<k>=객체의 k 배열 원소마다
SCHEMA_OF: dict[str, tuple[str, str]] = {
    "region.json": ("region.json", "one"),
    "complexes.json": ("complex.json#/$defs/ComplexBundle", "list"),
    "provenance.json": ("provenance.json", "list"),
    "snapshots.json": ("snapshot.json", "list"),
    "expected_scores.json": ("expected_scores.json", "one"),
    "raw/documents.json": ("raw_document.json", "list"),
    "raw/official_site/t8_popup_pairs.json": ("raw_document.json", "values"),
    "raw/rtms/t4_metroxi2_84.json": ("score_inputs.json#/$defs/TradeInput", "key:trades"),
    "raw/rtms/t11_switzen_comparables.json": ("score_inputs.json#/$defs/TradeInput", "key:trades"),
    "raw/t5_harrington/candidates.json": ("field_candidate.json", "list"),
    "raw/t13_missing_provenance/complexes.json": ("complex.json#/$defs/ComplexBundle", "list"),
    "raw/t13_missing_provenance/provenance.json": ("provenance.json", "list"),
    "raw/human_check/t3_switzen_possible.json": ("human_check.json#/$defs/HumanCheckCreate", "one"),
    "raw/claims/t6_composite.json": ("claim.json", "key:claims"),
    "raw/scenarios/t18_judge_down.json": ("snapshot.json", "key:expected_snapshot"),
}
# 계약에 해당 스키마가 없는 테스트 입력(이유를 적는다). 새 항목은 README 매핑 표에도 적는다.
NO_SCHEMA: dict[str, str] = {
    "raw/applyhome_list/2026-10-07.json": "청약홈 목록 응답 녹화(원문 모양, 계약 DTO 아님) — T8·T17",
    "raw/applyhome_list/2026-10-08.json": "같은 목록(바이트 동일) — T8·T17",
    "raw/guard/t14_payloads.json": "guard 입력 payload(JudgePayload = 임의 JSON 객체) — T14",
    "raw/t13_missing_provenance/expected.json": "지운 출처 id 목록(테스트 기대값) — T13",
}
SKIP_DIRS = {"judgments"}  # 봉투는 test_judgments.py


def items(doc: Any, shape: str) -> list[Any]:
    if shape == "one":
        return [doc]
    if shape == "list":
        assert isinstance(doc, list) and doc, "배열이어야 하고 비어 있으면 안 된다"
        return doc
    if shape == "values":
        assert isinstance(doc, dict) and doc
        return list(doc.values())
    if shape.startswith("key:"):
        key = shape[4:]
        value = doc[key]
        return value if isinstance(value, list) else [value]
    raise AssertionError(f"알 수 없는 모양 {shape}")


@pytest.mark.parametrize("rel", sorted(NO_SCHEMA))
def test_no_schema_inputs_exist(rel: str) -> None:
    assert (FIXTURE / rel).is_file(), f"{rel} 없음"
    load_json(FIXTURE / rel)


@pytest.mark.parametrize("rel", sorted(SCHEMA_OF))
def test_fixture_file_validates(rel: str) -> None:
    path = FIXTURE / rel
    assert path.is_file(), f"{rel} 없음"
    ref, shape = SCHEMA_OF[rel]
    doc = load_json(path)
    for i, item in enumerate(items(doc, shape)):
        errs = schema_errors(ref, item)
        assert errs == [], f"{rel}[{i}] {ref}: {errs[:5]}"


def test_every_json_file_has_a_schema() -> None:
    unknown = []
    for path in sorted(FIXTURE.rglob("*.json")):
        rel = path.relative_to(FIXTURE).as_posix()
        if rel.split("/")[0] in SKIP_DIRS:
            continue
        if rel not in SCHEMA_OF and rel not in NO_SCHEMA:
            unknown.append(rel)
    assert unknown == [], f"스키마 매핑이 없는 픽스처 JSON: {unknown}"


def test_complexes_are_the_16_report_complexes() -> None:
    bundles = load_json(FIXTURE / "complexes.json")
    expected = load_json(FIXTURE / "expected_scores.json")
    want = {c["complex_id"]: (c["key"], c["name"]) for c in expected["complexes"]}
    got = {b["complex"]["id"]: (b["fixture_key"], b["complex"]["name"]) for b in bundles}
    assert len(bundles) == 16
    assert got == want, "complex_id·fixture_key·이름이 expected_scores.json과 같아야 한다(MSW 예시와 같은 번호)"
    applyhome_ids = [b["complex"]["applyhome_id"] for b in bundles if b["complex"]["applyhome_id"]]
    assert len(applyhome_ids) == len(set(applyhome_ids)), "applyhome_id 유일"


def test_complexes_living_area_matches_region() -> None:
    region = load_json(FIXTURE / "region.json")
    la_of_code = {code: la["id"] for la in region["living_areas"] for code in la["legal_dong_codes"]}
    for b in load_json(FIXTURE / "complexes.json"):
        c = b["complex"]
        assert c["region_id"] == region["id"]
        code = c.get("legal_dong_code")
        assert code in la_of_code, f"{c['name']}: 법정동 {code}가 region에 없음"
        assert c["living_area"] == la_of_code[code], f"{c['name']}: 생활권은 법정동 코드로 배정"


def test_region_living_areas_partition_legal_dongs() -> None:
    region = load_json(FIXTURE / "region.json")
    seen: list[str] = [code for la in region["living_areas"] for code in la["legal_dong_codes"]]
    assert len(seen) == len(set(seen)), "법정동은 정확히 한 생활권에만"
    assert set(seen) == set(region["legal_dong_codes"])
    for code in region["legal_dong_codes"]:
        assert code[:5] in region["sigungu_codes"] and code[:2] in region["sido_codes"]


def test_region_households_have_label() -> None:
    region = load_json(FIXTURE / "region.json")
    for la in region["living_areas"]:
        hh = la["households"]
        assert hh is not None, f"{la['name']}: 세대수 Fact 필요(값이 없으면 라벨 '확인 불가')"
        assert hh["label"] in {"추정", "확인 불가"}, "생활권 세대수는 추정(주민등록 세대) 또는 확인 불가"


def test_raw_text_files_match_documents_sha256() -> None:
    import hashlib

    docs = load_json(RAW / "documents.json")
    ids = [d["id"] for d in docs]
    assert len(ids) == len(set(ids)) and len({d["sha256"] for d in docs}) == len(docs), "id·sha256 유일"
    for d in docs:
        if d["path"] is None:
            assert d["http_status"] != 200, f"{d['id']}: 실패 행만 path=null"
            continue
        f: Path = RAW / d["path"]
        assert f.is_file(), f"{d['id']}: {d['path']} 없음"
        assert hashlib.sha256(f.read_bytes()).hexdigest() == d["sha256"], f"{d['id']}: sha256 불일치"


def test_judgments_dir_exists() -> None:
    assert (JUDGMENTS / "_meta.json").is_file()
    assert (JUDGMENTS / "_index.json").is_file()
