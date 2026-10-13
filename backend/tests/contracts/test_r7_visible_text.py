"""계약 2026-10-09.19 (R7-QUEUE, 조정자 요청) — 자유 문장 입력의 '보이는 글자 1자 이상' 규칙이 스키마와 서버에서 같다.

schemathesis 가 찾은 어긋남: ``PATCH /claims/{id}`` ``{"text": "\\u001e"}`` 는 스키마(minLength 1)를 통과했지만 서버가
``strip()`` 으로 비워 422 '비었다'(RejectedPositiveData). 같은 꼴(서버가 앞뒤 공백을 지운 뒤 비면 422)인 요청 필드 4개
(ClaimPatch.text · CatalystCreate.title · RegionPatch.name · LivingAreaInput.name)에 같은 ``pattern`` 을 둔다.
"""

# ruff: noqa: E501  (한국어 docstring)
from __future__ import annotations

import sys
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from app.api.contract import VISIBLE_TEXT_PATTERN, has_visible

from ._support import SCHEMAS, load_json

FIELDS = [
    ("claim.json", ("$defs", "ClaimPatch", "properties", "text")),
    ("catalyst.json", ("$defs", "CatalystCreate", "properties", "title")),
    ("region.json", ("$defs", "RegionPatch", "properties", "name")),
    ("living_area.json", ("$defs", "LivingAreaInput", "properties", "name")),
]


def _prop(file: str, path: tuple[str, ...]) -> dict[str, Any]:
    node: Any = load_json(SCHEMAS / file)
    for key in path:
        node = node[key]
    assert isinstance(node, dict)
    return node


@pytest.mark.parametrize(("file", "path"), FIELDS, ids=[f[1][1] for f in FIELDS])
def test_free_text_fields_share_the_server_pattern(file: str, path: tuple[str, ...]) -> None:
    prop = _prop(file, path)
    assert prop["pattern"] == VISIBLE_TEXT_PATTERN
    assert "보이는 글자" in prop["description"]


def _samples() -> list[str]:
    singles = [chr(c) for c in (*range(0x0000, 0x0300), 0x1680, *range(0x2000, 0x2070))]
    singles += ["\u3000", "\ufeff", "\u200b", "가"]
    return [
        *singles,
        " \u3000\t",
        "\u001e",
        " a ",
        "\x01가",
        "\n\r\x0b\x0c\x1c\x1d\x1e\x1f\x85\xa0",
        "고친 문장",
    ]


def test_schema_pattern_equals_server_rule_and_strip_never_empties() -> None:
    """스키마 통과 ⇔ 서버 ``has_visible`` — 그리고 통과한 값은 ``strip()`` 해도 비지 않는다(서버 '비었다' 422 에 닿지 않는다)."""
    schema = {"type": "string", "minLength": 1, "pattern": VISIBLE_TEXT_PATTERN}
    v = Draft202012Validator(schema)
    for s in _samples():
        assert v.is_valid(s) == has_visible(s), repr(s)
        if has_visible(s):
            assert s.strip(), repr(s)
    # 파이썬 공백(str.isspace) 전부는 보이는 글자가 아니다
    spaces = [chr(c) for c in range(sys.maxunicode + 1) if chr(c).isspace()]
    assert spaces and not any(has_visible(ch) for ch in spaces)
    assert not has_visible("\u001e") and has_visible("\u001ea")
