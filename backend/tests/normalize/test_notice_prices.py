"""완료 기준 1: 인천·김포 공고문 발췌(실제 청약홈 공고문) → complex_type 가격이 기대값과 원 단위 일치."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.normalize.notice_parser import parse_notice_text

from ._support import NOTICE, dto, notice_manifest

EXPECTED: dict[str, Any] = json.loads((NOTICE / "expected_complex_types.json").read_text(encoding="utf-8"))

# 보고서(docs/source/incheon_gimpo_report.md §4·§12-2-2·§7)의 '공급금액 최고가(만원)'
# — 기대값 파일과 독립인 대조값
REPORT_MAX_MANWON: dict[str, dict[str, int]] = {
    "2025000271_harrington1.txt": {"84A": 77_000, "84B": 75_800, "84C": 75_400},
    "2025000273_harrington2.txt": {"84A": 77_200, "84B": 75_900, "84C": 75_500},
    "2025000274_harrington3.txt": {"74A": 69_700, "74B": 68_500},
    "2025000573_kantavil.txt": {"84A": 67_800, "84B": 68_500},
    "2025000076_lotte.txt": {"84A": 78_400, "84B": 76_500},
    "2025000222_switzen.txt": {"84A": 69_300, "84B": 68_900, "84C": 68_300},
    "2026000367_riverfront.txt": {
        "84A": 77_300,
        "84B": 76_800,
        "84C": 74_200,
        "84D": 73_700,
        "84E": 75_200,
        "84F": 74_200,
    },
    "2025000656_gienheim.txt": {"84A": 69_890, "84B": 68_260, "84C": 69_740},
    "2026000329_hoban3.txt": {"84A": 76_250, "84B": 75_220, "84C": 74_350, "84D": 73_590},
    "2026000073_grascent2.txt": {"84": 71_150, "105": 82_530},
    "2025000302_elif.txt": {"84A": 60_900, "84B": 58_100, "84F": 60_200, "64A": 50_700},
    "2025000435_centreville.txt": {
        "74A": 54_850,
        "84A": 61_620,
        "84B": 59_960,
        "101A": 69_940,
        "101B": 69_940,
        "101C": 68_310,
    },
    "2026000194_lakepark22.txt": {"84A": 65_330, "84B": 64_660, "84C": 63_680},
}
# 보고서에 적힌 대표층 공급금액·발코니(원) — 최저층 규칙과 맞는 것만
REPORT_FLOOR_WON: dict[str, dict[str, int]] = {
    "2025000076_lotte.txt": {"84B": 664_000_000},
    "2025000222_switzen.txt": {"84C": 620_000_000},
    "2026000367_riverfront.txt": {"84A": 644_000_000},
    "2026000073_grascent2.txt": {"84": 654_100_000},
}
REPORT_BALCONY_WON: dict[str, dict[str, int]] = {
    "2025000271_harrington1.txt": {"84A": 26_000_000},
    "2025000573_kantavil.txt": {"84A": 19_000_000},
    "2025000076_lotte.txt": {"84B": 38_000_000},
    "2025000222_switzen.txt": {"84A": 5_981_000},
    "2025000656_gienheim.txt": {"84A": 18_100_000},
    "2026000329_hoban3.txt": {"84A": 5_860_000},
    "2026000073_grascent2.txt": {"84": 6_640_000},
    "2025000302_elif.txt": {"84A": 3_140_000, "84B": 3_700_000},
    "2025000435_centreville.txt": {"84A": 5_966_000, "84B": 7_240_000, "101A": 5_086_000},
}


def _parsed(fname: str) -> dict[str, dict[str, Any]]:
    m = notice_manifest()[fname]
    raw = dto(source_kind="notice_pdf", url=m["url"])
    out: dict[str, dict[str, Any]] = {}
    for c in parse_notice_text((NOTICE / fname).read_text(encoding="utf-8"), raw):
        if c.entity == "complex_type" and not c.needs_extract and c.entity_key:
            t = c.entity_key.split(":", 1)[1]
            out.setdefault(t, {})[c.field] = c.value
    return out


def test_at_least_eight_complexes_with_prices() -> None:
    with_prices = [f for f, v in EXPECTED.items() if any("max_price_won" in t for t in v["types"].values())]
    assert len(with_prices) >= 8, with_prices


@pytest.mark.parametrize("fname", sorted(EXPECTED))
def test_complex_type_prices_match_expected_to_the_won(fname: str) -> None:
    got = _parsed(fname)
    exp = EXPECTED[fname]["types"]
    assert set(got) >= set(exp)
    for t, fields in exp.items():
        for f, v in fields.items():
            g = got[t][f]
            if f == "area_m2":
                assert g == pytest.approx(v), (fname, t, f)
            else:
                assert isinstance(g, (int, float)) and int(g) == g == v, (fname, t, f, g, v)


@pytest.mark.parametrize("fname", sorted(REPORT_MAX_MANWON))
def test_max_price_matches_report_manwon(fname: str) -> None:
    got = _parsed(fname)
    for t, manwon in REPORT_MAX_MANWON[fname].items():
        assert got[t]["max_price_won"] == manwon * 10_000, (fname, t)


@pytest.mark.parametrize("fname", sorted(REPORT_FLOOR_WON))
def test_floor_sample_matches_report(fname: str) -> None:
    got = _parsed(fname)
    for t, won in REPORT_FLOOR_WON[fname].items():
        assert got[t]["floor_sample_price_won"] == won


@pytest.mark.parametrize("fname", sorted(REPORT_BALCONY_WON))
def test_balcony_matches_report(fname: str) -> None:
    got = _parsed(fname)
    for t, won in REPORT_BALCONY_WON[fname].items():
        assert got[t]["balcony_won"] == won


def test_every_candidate_has_excerpt_offsets_inside_text() -> None:
    for fname in EXPECTED:
        text = (NOTICE / fname).read_text(encoding="utf-8")
        raw = dto(source_kind="notice_pdf", url=notice_manifest()[fname]["url"])
        for c in parse_notice_text(text, raw):
            assert c.excerpt.strip(), (fname, c.field)
            assert c.excerpt_start is not None and c.excerpt_end is not None
            assert text[c.excerpt_start : c.excerpt_end].strip() == c.excerpt
            assert c.label in ("확인됨", "확인 불가")
            assert c.url and c.checked_at == "2026-10-09"
            if c.label == "확인 불가":
                assert c.reason


def test_unassignable_rows_become_extract_requests_not_guesses() -> None:
    """센트레빌 120P 행은 공급금액이 두 줄로 쪼개져 있어 배정하지 않는다 → needs_extract(추측 금지)."""
    fname = "2025000435_centreville.txt"
    raw = dto(source_kind="notice_pdf", url=notice_manifest()[fname]["url"])
    cands = parse_notice_text((NOTICE / fname).read_text(encoding="utf-8"), raw)
    p120 = [c for c in cands if c.entity_key == "2025000435:120P" and c.field == "max_price_won"]
    assert len(p120) == 1 and p120[0].needs_extract and p120[0].value is None and p120[0].label == "확인 불가"
