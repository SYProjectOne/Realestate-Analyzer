"""R6-INTAKE — 공식 홈페이지 동일성 classify 항목(D21-5)의 근거.

인천 첫 실행(운영 DB 스냅샷 1, jl_443·444): 동일성 70건 중 same_complex·review 11건. 항목에는 단지 이름·주소와 페이지 문구 앞
1500자만 있었다 — 홈페이지 주소(도메인이 단지 이름인 경우가 많다)·HTML 제목·설명·시공·시행·세대수가 없고, 시행·현장 주소·총
세대수가 있는 꼬리말이 잘렸다(예 '포레나더샵 인천시청역' 렌더 문구 1825자 — 회전 배너가 같은 문구를 3번 되풀이, 현장 주소는
1500자 뒤). 근거를 더할 뿐 같은 단지인지는 판정기가 정한다(규칙 3).
"""

# ruff: noqa: E501  (한국어 docstring·문구)

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.collectors.official_site.extract import html_head
from app.judge import payloads as P
from app.judge import pipeline as jp

from .conftest import FakeTransport
from .test_r25 import classify_response

FIX = Path(__file__).resolve().parents[1] / "scheduler" / "fixtures" / "r6_intake_incheon_pages.json"


def _page(name: str) -> dict[str, object]:
    data = json.loads(FIX.read_text(encoding="utf-8"))
    return next(c for c in data["complexes"] if c["name"] == name)


def test_head_tail_keeps_footer_within_limit() -> None:
    text = "\n".join(f"메뉴 {i}" for i in range(400)) + "\n현장 인천광역시 남동구 간석1동 311-1일원"
    out = P.head_tail(text, 1000)
    assert len(out) <= 1000 and out.startswith("메뉴 0") and out.endswith("311-1일원")
    assert P.HEAD_TAIL_GAP in out
    assert P.head_tail("짧은 문구", 1000) == "짧은 문구"
    assert P.head_tail(text, 1000) == out, "결정적"


def test_site_item_carries_url_title_builder_and_footer() -> None:
    pg = _page("포레나더샵 인천시청역")
    title, desc = html_head(str(pg["head_html"]))
    assert title == "포레나더샵 인천시청역"
    lines = list(dict.fromkeys(str(pg["rendered_text"]).splitlines()))
    item = jp.SiteItem(
        24, "headless_shot", str(pg["name"]), str(pg["address"]), "\n".join(lines),
        builder=str(pg["builder"]), developer=str(pg["developer"]), units_total=735,
        url="https://incheon.forena.co.kr/", final_url="https://incheon.forena.co.kr/", title=title, description=desc,
    )  # fmt: skip
    text = P.classify_site_identity_payload([(item.key, item.item_text)])["items"][0]["text"]
    assert len(text) <= P.ITEM_TEXT_MAX and not text.endswith("…"), "2000자 자르기에 꼬리말이 잘리지 않는다"
    for want in (
        "홈페이지 주소: https://incheon.forena.co.kr/",
        "페이지 제목: 포레나더샵 인천시청역",
        "시공: (주)한화 건설부문, (주)포스코이앤씨",
        "시행: 상인천초교주변주택재개발정비사업조합",
        "청약홈 공급 세대수: 735세대",
        "인천광역시 남동구 간석1동 311-1일원",  # 꼬리말 현장 주소(예전 1500자 자르기 밖)
    ):
        assert want in text, want
    assert "최종 주소" not in text, "이동이 없으면 같은 주소를 두 번 쓰지 않는다"


def test_html_head_reads_title_and_description() -> None:
    pg = _page("중앙하이츠 갈산역 센트럴")
    title, desc = html_head(str(pg["head_html"]))
    assert title == "중앙하이츠 갈산역 센트럴 | 갈산역 0분의 가치"
    assert desc is not None and desc.startswith("중앙하이츠 갈산역 센트럴 - 갈산역")
    assert html_head("<html><body>본문</body></html>") == (None, None)


def test_site_payload_is_order_independent_with_new_fields(make_adapter: Callable[..., Any]) -> None:
    """D22-2: 배치 입력은 항목 순서와 무관하다(새 근거 필드 포함) — 순서를 바꿔 다시 부르면 캐시(호출 0)."""
    a = jp.SiteItem(3, "headless_shot", "가", None, "문구", url="https://a.example/", title="가")
    b = jp.SiteItem(1, "official_popup", "나", "주소", "문구2", builder="시공사")
    t = FakeTransport(
        responses={
            "jev_classify": classify_response(
                [
                    ("site:c1:official_popup", "same_complex", "auto"),
                    ("site:c3:headless_shot", "unclear", "review"),
                ]
            )
        }
    )
    adapter = make_adapter(t)
    out = jp.p4_classify_site_identity(adapter, [a, b])
    assert jp.is_same_site(out["site:c1:official_popup"]) and not jp.is_same_site(
        out["site:c3:headless_shot"]
    )
    jp.p4_classify_site_identity(adapter, [b, a])
    assert len(t.calls) == 1
