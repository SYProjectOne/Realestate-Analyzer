"""청약홈 HTML(실제 녹화) → 후보: 상세·경쟁률·목록."""

from __future__ import annotations

import json

from app.core.protocols import Parser
from app.normalize.applyhome_parser import ApplyhomeParser, parse_applyhome_html

from ._support import APPLYHOME, COMP_URL, DETAIL_URL, dto

RANK_AREA_KINDS = [
    "특별공급",
    "1순위 해당지역",
    "1순위 기타지역",
    "2순위 해당지역",
    "2순위 기타지역",
]  # R9-PARSE Q3


def _by(cands: list, entity: str, key: str, field: str):  # type: ignore[no-untyped-def,type-arg]
    return next(c for c in cands if c.entity == entity and c.entity_key == key and c.field == field)


def test_parser_protocol() -> None:
    assert isinstance(ApplyhomeParser(), Parser)


def test_detail_harrington_1bl() -> None:
    html = (APPLYHOME / "detail_2025000271.html").read_text(encoding="utf-8")
    raw = dto(source_kind="applyhome_detail", url=DETAIL_URL.format(n="2025000271"))
    c = parse_applyhome_html(html, raw)
    key = "2025000271"
    assert _by(c, "complex", key, "name").value == "해링턴플레이스 풍무(1BL)"
    assert _by(c, "complex", key, "units_total").value == 670
    assert _by(c, "complex", key, "units_general").value == 303
    assert _by(c, "complex", key, "units_special").value == 367
    assert _by(c, "complex", key, "notice_date").value == "2025-07-04"
    assert _by(c, "complex", key, "winner_date").value == "2025-07-23"
    assert _by(c, "complex", key, "move_in_ym").value == "2028-08"
    assert json.loads(str(_by(c, "complex", key, "contract_dates").value)) == [
        {"from": "2025-08-04", "to": "2025-08-06"}
    ]
    applies = json.loads(str(_by(c, "complex", key, "apply_dates").value))
    assert [a["kind"] for a in applies] == RANK_AREA_KINDS  # R9-PARSE Q3
    assert _by(c, "complex", key, "developer").value == "우리자산신탁 주식회사"
    assert _by(c, "complex", key, "builder").value == "효성중공업 주식회사"
    p = _by(c, "complex_type", f"{key}:84A", "max_price_won")
    assert p.value == 770_000_000 and p.value_text == "77,000만원" and p.source_rank == 2
    a = _by(c, "complex_type", f"{key}:84A", "area_m2")
    assert a.value == 84.75 and a.source_rank == 1
    assert _by(c, "complex_type", f"{key}:84A", "units").value == 266
    u = _by(c, "complex", key, "units_total")
    assert u.source_rank == 1 and u.label == "확인됨" and u.excerpt == "공급규모 670세대"
    assert u.excerpt_start is not None and html[u.excerpt_start : u.excerpt_end].startswith("<tr>")


def test_detail_letterless_type_codes_keep_long_form() -> None:
    html = (APPLYHOME / "detail_2025000573.html").read_text(encoding="utf-8")
    c = parse_applyhome_html(html, dto(source_kind="applyhome_detail", url=DETAIL_URL.format(n="2025000573")))
    keys = {x.entity_key for x in c if x.entity == "complex_type"}
    assert "2025000573:84.9582" in keys and "2025000573:66.95" not in keys


def test_competition_rows() -> None:
    html = (APPLYHOME / "competition_2025000271.html").read_text(encoding="utf-8")
    c = parse_applyhome_html(html, dto(source_kind="applyhome_detail", url=COMP_URL.format(n="2025000271")))
    key = "2025000271:본청약:1순위 해당지역:74A"
    assert _by(c, "competition", key, "supply").value == 77
    assert _by(c, "competition", key, "applied").value == 6
    assert _by(c, "competition", key, "ratio_or_shortfall_text").value == "(△71)"
    assert all(x.source_rank == 1 for x in c)  # 경쟁률 = 청약홈 1


def test_list_rows() -> None:
    html = (APPLYHOME / "list_gyeonggi_202507_q.html").read_text(encoding="utf-8")
    c = parse_applyhome_html(
        html, dto(source_kind="applyhome_list", url="https://www.applyhome.co.kr/ai/aia/list")
    )
    names = {x.entity_key: x.value for x in c if x.field == "name"}
    assert names == {
        "2025000271": "해링턴플레이스 풍무(1BL)",
        "2025000273": "해링턴플레이스 풍무(2BL)",
        "2025000274": "해링턴플레이스 풍무(3BL)",
    }
    assert _by(c, "complex", "2025000271", "winner_date").value == "2025-07-23"


def test_failed_raw_gives_no_candidates() -> None:
    raw = dto(source_kind="applyhome_detail", url=DETAIL_URL.format(n="1"), http_status=403)
    assert ApplyhomeParser().parse(raw) == []
