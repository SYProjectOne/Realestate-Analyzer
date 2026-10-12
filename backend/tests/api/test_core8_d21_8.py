"""R4 재시험 FE9 보고(DECISIONS D21-8) — 공고 예정 후보의 가격·공고일 '확인 불가(공고 전)', 단지 이름 출처·라벨(계약 .16).

- 트랙 (A) 공고 예정 후보(주택관리번호·공고일 없음)의 공고일 Fact 사유 = '공고 전'(이전: '값 없음'), 가격 Fact 사유 = '공고 전'
  (이전: '분양가 미공개'). 목록 행·단지 상세 머리 모두.
- 계약 2026-10-09.16: ``ComplexRow``·``Complex``(상세 머리)에 선택 필드 ``name_prov``(fp_<id>|null)·``name_label``(라벨|null) —
  공고 예정 후보 이름은 언론 '비공식', 청약홈 공고 단지는 '확인됨'.
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from ._support import READ, validate
from .test_r3b_g3 import SNAP


def _rows(client: TestClient) -> list[dict[str, Any]]:
    r = client.get(f"/api/snapshots/{SNAP}/complexes", params={"size": 200}, headers=READ)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("listComplexes", 200, body)
    items: list[dict[str, Any]] = body["items"]
    return items


def test_contract_version_is_16() -> None:
    from app.core.protocols import CONTRACT_VERSION

    assert CONTRACT_VERSION == "2026-10-09.16"


def test_pre_notice_candidate_price_and_notice_date_reason(client: TestClient) -> None:
    rows = _rows(client)
    upcoming = [r for r in rows if r["track"] == "A"]
    assert upcoming, "픽스처에 트랙 (A) 공고 예정 후보가 있다"
    for row in upcoming:
        for key in ("price_low", "price_high", "price_mid"):
            assert (row[key]["label"], row[key].get("reason")) == ("확인 불가", "공고 전"), (
                row["name"],
                key,
                row[key],
            )
        r = client.get(f"/api/complexes/{row['complex_id']}", headers=READ)
        assert r.status_code == 200, r.text
        head = r.json()["header"]
        if head["applyhome_id"] is None:
            assert (head["notice_date"]["label"], head["notice_date"].get("reason")) == (
                "확인 불가",
                "공고 전",
            )
            assert r.json()["price"]["price_low"].get("reason") == "공고 전"


def test_name_provenance_fields(client: TestClient) -> None:
    """목록 행·상세 머리에 ``name_prov``·``name_label`` 키(계약 .16). 픽스처 시드는 이름 출처 행이 없어 null."""
    rows = _rows(client)
    assert all("name_prov" in r and "name_label" in r for r in rows), "목록 행에 name_prov·name_label 키"
    d = client.get(f"/api/complexes/{rows[0]['complex_id']}", headers=READ)
    assert d.status_code == 200, d.text
    head = d.json()["header"]
    assert "name_prov" in head and "name_label" in head
    assert (head["name_prov"], head["name_label"]) == (rows[0]["name_prov"], rows[0]["name_label"])


def test_name_provenance_from_chosen_row() -> None:
    """이름 출처 = chosen 출처 행(공고 예정 후보 = 언론 '비공식'). 출처 행이 없으면 null(이름은 Fact 가 아니라 출처 누락 오류 없음)."""
    from types import SimpleNamespace

    from app.api.facts import FactMaker, ProvIndex, ProvRef
    from app.api.views import name_provenance
    from app.core.settings import Settings

    idx = ProvIndex()
    idx._rows[("complex", 7, "name")] = ProvRef(
        31, "비공식", "2026-10-12", "언론(공고 예정, 청약홈 미등록)", "https://news.example/a", 9
    )
    fm = FactMaker(Settings(_env_file=None), idx)  # type: ignore[call-arg]
    assert name_provenance(fm, SimpleNamespace(id=7)) == {"name_prov": "fp_31", "name_label": "비공식"}
    assert name_provenance(fm, SimpleNamespace(id=8)) == {"name_prov": None, "name_label": None}
