"""계약 2026-10-09.4 (R3 수정 F3) — 판정 범위 '미해결', 주장 목록·수정, 호재 URL 입력, 공유 링크, 역할 enum, 비수치 메타.

리뷰 항목: C2(D9-1 '미해결'), M8(contradicted 목록·문장 수정), M6(호재 URL 입력), M9(공유 링크 30일),
minor 15(entered_by 역할), minor 16(URL scheme), minor 29(맨 숫자 → Fact 또는 x-nonfact 근거).
"""

# ruff: noqa: E501  (한국어 assertion 메시지·표)
from __future__ import annotations

import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry

from ._support import SCHEMAS, load_json


def _errors(rel: str, registry: Registry[Any], value: Any, pointer: str = "") -> list[str]:
    schema: dict[str, Any] = {"$ref": rel + (f"#{pointer}" if pointer else "")}
    v = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    return [e.message for e in v.iter_errors(value)]


def _op(doc: dict[str, Any], method: str, path: str) -> dict[str, Any]:
    op: dict[str, Any] = doc["paths"][path][method]
    return op


# ---------------------------------------------------------------- C2 / D9-1


def test_judge_scope_has_unresolved_value() -> None:
    enum = load_json(SCHEMAS / "score_row.json")["$defs"]["JudgeScope"]["enum"]
    assert enum == ["판정 대상", "보류", "참고", "미해결", "제외"]
    desc = load_json(SCHEMAS / "score_row.json")["$defs"]["JudgeScope"]["description"]
    for word in ("미해결", "참고 후보(순위만)", "보류 — 공고 후 재판정", "확인 불가", "D9-1"):
        assert word in desc, word


# ---------------------------------------------------------------- M8 주장


def test_claims_list_and_patch_operations(bundled: dict[str, Any]) -> None:
    lst = _op(bundled, "get", "/snapshots/{sid}/claims")
    assert lst["operationId"] == "listClaims"
    status = next(p for p in lst["parameters"] if p.get("name") == "status")
    assert "contradicted" in status["schema"]["enum"]
    assert lst["responses"]["200"]["content"]["application/json"]["schema"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/ClaimView"},
    }
    patch = _op(bundled, "patch", "/claims/{id}")
    assert patch["operationId"] == "reviseClaim"
    assert patch["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ClaimPatch"
    }
    assert patch["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/JobRun"
    }
    assert "409" in patch["responses"]


def test_claim_reverify_job_payload(schema_registry: Registry[Any]) -> None:
    # 계약 2026-10-09.6: claim.reverify 는 POST /jobs(JobCreate)로 넣을 수 없다 — payload 스키마 자체만 검사한다
    ok = {"snapshot_id": 12, "claim_id": 7001, "text": "a"}
    assert _errors("job_payloads/claim_reverify.json", schema_registry, ok) == []
    bad = {"snapshot_id": 12, "claim_id": 7001, "text": ""}
    assert _errors("job_payloads/claim_reverify.json", schema_registry, bad)
    assert _errors("claim.json", schema_registry, {"text": ""}, "/$defs/ClaimPatch")
    assert _errors("claim.json", schema_registry, {"text": "x" * 2001}, "/$defs/ClaimPatch")
    assert _errors("claim.json", schema_registry, {"text": "고친 문장"}, "/$defs/ClaimPatch") == []


# ---------------------------------------------------------------- M6 호재 URL


def test_catalyst_create_operation(bundled: dict[str, Any]) -> None:
    op = _op(bundled, "post", "/catalysts")
    assert op["operationId"] == "createCatalyst"
    assert op["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CatalystCreated"
    }


def test_catalyst_create_rejects_non_http_url(schema_registry: Registry[Any]) -> None:
    base = {"region_id": 1, "url": "https://news.example.org/a/1", "title": "역 신설 확정", "excerpt": None}
    assert _errors("catalyst.json", schema_registry, base, "/$defs/CatalystCreate") == []
    for url in ("javascript:alert(1)", "data:text/html,x", "ftp://x/y", "//x/y", "file:///etc/passwd"):
        assert _errors("catalyst.json", schema_registry, {**base, "url": url}, "/$defs/CatalystCreate"), url


# ---------------------------------------------------------------- M9 공유 링크


def test_share_link_operations(bundled: dict[str, Any]) -> None:
    create = _op(bundled, "post", "/share-links")
    assert create["operationId"] == "createShareLink"
    assert create["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ShareLinkCreated"
    }
    assert "30" in create["description"] and "읽기 전용" in create["description"]
    lst = _op(bundled, "get", "/share-links")
    assert "403" in lst["responses"], "공유(읽기 전용) 토큰으로 목록을 볼 수 없다"
    revoke = _op(bundled, "delete", "/share-links/{id}")
    assert revoke["operationId"] == "revokeShareLink"
    scheme = bundled["components"]["securitySchemes"]["bearerAuth"]["description"]
    assert "공유 링크" in scheme and "만료" in scheme


def test_share_link_schema(schema_registry: Registry[Any]) -> None:
    link = load_json(SCHEMAS / "share_link.json")
    assert link["properties"]["status"]["enum"] == ["active", "expired", "revoked"]
    assert "token" not in link["properties"], "목록·조회 응답에는 토큰이 없다(발급 응답에서 한 번만)"
    created = link["$defs"]["ShareLinkCreated"]
    assert "token" in created["required"]
    assert _errors("share_link.json", schema_registry, {"label": "x" * 65}, "/$defs/ShareLinkCreate")


# ---------------------------------------------------------------- minor 15 entered_by


def test_human_check_entered_by_is_role_enum(schema_registry: Registry[Any]) -> None:
    base = {
        "complex_id": 4, "field": "intake_status", "value_text": "가능", "kind": "phone",
        "checked_at": "2026-10-09T10:20:00+09:00", "entered_by": "운영자", "note": None,
    }  # fmt: skip
    assert _errors("human_check.json", schema_registry, base, "/$defs/HumanCheckCreate") == []
    for name in ("홍길동", "김 운영", "operator", "운영자 홍길동"):
        assert _errors(
            "human_check.json", schema_registry, {**base, "entered_by": name}, "/$defs/HumanCheckCreate"
        ), name


# ---------------------------------------------------------------- minor 29 맨 숫자


_META_NAME = re.compile(r"^(id|page|size)$|_id$|_ids$|_seq$")


def _reachable_response_components(doc: dict[str, Any]) -> set[str]:
    schemas = doc["components"]["schemas"]
    seen: set[str] = set()
    stack: list[Any] = [doc["components"]["responses"]]
    for item in doc["paths"].values():
        for method, op in item.items():
            if method in ("get", "post", "put", "patch", "delete"):
                stack.append(op["responses"])
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[1]
                if name not in seen:
                    seen.add(name)
                    stack.append(schemas[name])
            stack.extend(v for k, v in node.items() if k not in ("examples", "example"))
        elif isinstance(node, list):
            stack.extend(node)
    return seen


def _is_number(prop: dict[str, Any]) -> bool:
    t = prop.get("type")
    types = t if isinstance(t, list) else [t]
    if any(x in ("number", "integer") for x in types):
        return True
    if any(_is_number(alt) for alt in prop.get("anyOf", []) + prop.get("oneOf", [])):
        return True
    items = prop.get("items")
    return bool(prop.get("type") == "array" and isinstance(items, dict) and _is_number(items))


def test_bare_numbers_in_responses_are_declared_nonfact(bundled: dict[str, Any]) -> None:
    """minor 29: 응답에 나가는 맨 숫자는 Fact 이거나 `x-nonfact: <근거>` 로 '비수치 메타'임을 계약에 적는다.

    식별자·페이지(id, *_id, *_ids, *_seq, page, size)는 이름 규칙으로 메타다. Fact.v 는 Fact 자신.
    """
    schemas = bundled["components"]["schemas"]
    missing = []
    for name in sorted(_reachable_response_components(bundled)):
        if name == "Fact":
            continue
        for prop_name, prop in (schemas[name].get("properties") or {}).items():
            if not _is_number(prop) or _META_NAME.search(prop_name):
                continue
            reason = prop.get("x-nonfact")
            if not (isinstance(reason, str) and len(reason.strip()) >= 4):
                missing.append(f"{name}.{prop_name}")
    assert missing == []
