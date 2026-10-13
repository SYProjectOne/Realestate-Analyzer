"""계약 2026-10-09.19 — 자유 문장 입력(주장 수정·호재 제목·지역 이름·생활권 이름)에 보이는 글자가 없으면 스키마 단계에서 422.

schemathesis RejectedPositiveData 재현: ``PATCH /claims/6990`` ``{"text": "\\u001e"}`` 가 스키마를 통과했는데 서버가 '비었다' 422.
이제 스키마가 같은 값을 거절하므로 schemathesis 의 양성 사례에 들지 않는다(서버 응답은 그대로 422).
"""

# ruff: noqa: E501  (한국어 docstring)
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ._support import WRITE, validate

BLANKS = ["\u001e", " ", " \u3000\t", "\ufeff", "\x01\x02", "\x85\xa0"]


def _claim_id() -> int:
    from sqlalchemy import select

    from app.core.db import get_session
    from app.models import Claim

    with get_session() as s:
        cid = s.scalars(select(Claim.id).order_by(Claim.id).limit(1)).first()
    assert cid is not None
    return int(cid)


def _loc_ends(body: dict[str, object], name: str) -> bool:
    errs = body.get("field_errors") or []
    assert isinstance(errs, list)
    return any(isinstance(e, dict) and list(e.get("loc") or [])[-1:] == [name] for e in errs)


@pytest.mark.parametrize("text", BLANKS, ids=[repr(b) for b in BLANKS])
def test_claim_revise_blank_text_is_schema_422(client: TestClient, text: str) -> None:
    r = client.patch(f"/api/claims/{_claim_id()}", json={"text": text}, headers=WRITE)
    assert r.status_code == 422, r.text
    body = r.json()
    validate("reviseClaim", 422, body)
    assert body["code"] == "validation_error" and _loc_ends(body, "text"), body


@pytest.mark.parametrize(
    ("op", "body", "name"),
    [
        ("reviseClaim", {"text": "\u001e"}, "text"),
        (
            "createCatalyst",
            {"region_id": 1, "url": "https://www.example-news.kr/a/1", "title": " \u3000"},
            "title",
        ),
        (
            "updateRegion",
            {"selections": [{"kind": "sigungu", "code": "28185", "full_name": "x"}], "name": "\x01"},
            "name",
        ),
    ],
)
def test_contract_rejects_what_server_calls_empty(op: str, body: dict[str, object], name: str) -> None:
    """schemathesis RejectedPositiveData 재현: 서버가 '비었다'로 거절하는 값은 계약(요청 스키마)도 거절한다."""
    from app.api.contract import check_body
    from app.api.errors import ApiError

    with pytest.raises(ApiError) as exc:
        check_body(op, body)
    assert any(list(e.get("loc") or [])[-1:] == [name] for e in exc.value.field_errors or []), (
        exc.value.field_errors
    )


def test_claim_revise_visible_text_with_control_char_is_not_called_empty(client: TestClient) -> None:
    """보이는 글자가 있으면 '비었다'가 아니다(앞뒤 공백·제어 문자는 서버가 다룬다) — 422 라도 다른 이유(같은 대상 규칙)."""
    r = client.patch(f"/api/claims/{_claim_id()}", json={"text": "\u001e고친 문장이다."}, headers=WRITE)
    assert "비었다" not in r.text


def test_catalyst_blank_title_is_schema_422(client: TestClient) -> None:
    r = client.post(
        "/api/catalysts",
        json={"region_id": 1, "url": "https://www.example-news.kr/article/77", "title": "\u3000\u001e"},
        headers=WRITE,
    )
    assert r.status_code == 422, r.text
    validate("createCatalyst", 422, r.json())
    assert _loc_ends(r.json(), "title")


def test_region_patch_blank_name_is_schema_422(client: TestClient) -> None:
    sel = client.get("/api/regions/1", headers=WRITE).json()["selections"]
    r = client.patch("/api/regions/1", json={"selections": sel, "name": " \u001f "}, headers=WRITE)
    assert r.status_code == 422, r.text
    validate("updateRegion", 422, r.json())
    assert _loc_ends(r.json(), "name")


def test_living_area_blank_name_is_schema_422(client: TestClient) -> None:
    region = client.get("/api/regions/1", headers=WRITE).json()
    areas = [
        {"id": a["id"], "name": a["name"], "legal_dong_codes": a["legal_dong_codes"]}
        for a in region["living_areas"]
    ]
    areas[0]["name"] = "\x01"
    r = client.put("/api/regions/1/living-areas", json={"living_areas": areas}, headers=WRITE)
    assert r.status_code == 422, r.text
    validate("updateLivingAreas", 422, r.json())
    assert _loc_ends(r.json(), "name")
