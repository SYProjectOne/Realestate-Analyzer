"""R3b 마무리 — 청약홈 상세의 단지 홈페이지 주소 → ``complex.official_site_url`` (+ 출처 행) → official_site 수집 대상.

- API 상세 ``HMPG_ADRES``(실응답 녹화)와 웹 상세 '당첨자 발표일' 칸의 홈페이지 링크를 후보로 낸다(같은 값).
- 정규화(``normalize_site_url``): 스킴 없는 주소에 http://, http/https 만, 빈 경로 '/', 청약홈 자신·'없음' 제외.
- 저장하면 complex.official_site_url 이 채워지고 출처 행(field_provenance)이 생긴다 → 수집기가 그 주소를 대상으로 쓴다.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.official_site.collector import OfficialSiteCollector, SiteTarget
from app.models import Complex, FieldProvenance, Region
from app.normalize._text import normalize_site_url
from app.normalize.applyhome_api_parser import parse_applyhome_api_json
from app.normalize.applyhome_parser import parse_applyhome_html
from app.normalize.store import store_raw_document

from ._support import FIX, AddRaw, dto

API = FIX / "applyhome_api"
WEB = FIX / "applyhome"
URLS = {m["file"]: m["url"] for m in json.loads((API / "manifest.json").read_text(encoding="utf-8"))}


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("https://prugio-riverfront.com/", "https://prugio-riverfront.com/"),
        ("https://cantaviltheedition.com", "https://cantaviltheedition.com/"),
        ("  HTTP://WWW.Example-Apt.CO.KR/main.html#top ", "http://www.example-apt.co.kr/main.html"),
        ("www.해링턴플레이스풍무.com", "http://www.해링턴플레이스풍무.com/"),
        ("https://www.엘리프검단포레듀.com", "https://www.엘리프검단포레듀.com/"),
        ("http://site.kr:8080/?a=1", "http://site.kr:8080/?a=1"),
        (None, None),
        ("", None),
        ("없음", None),
        ("-", None),
        ("1668-0552", None),
        ("ftp://site.kr/", None),
        ("javascript:alert(1)", None),
        ("https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancDetail.do", None),
        ("http://localhost/", None),
    ],
)
def test_normalize_site_url(raw: str | None, want: str | None) -> None:
    assert normalize_site_url(raw) == want
    if want is not None:
        assert normalize_site_url(want) == want  # 멱등


def test_api_detail_hmpg_adres_candidate_with_excerpt() -> None:
    name = "getAPTLttotPblancDetail_2026000367.json"
    text = (API / name).read_text(encoding="utf-8")
    cands = parse_applyhome_api_json(text, dto(source_kind="applyhome_detail", url=URLS[name]))
    site = [c for c in cands if c.field == "official_site_url"]
    assert len(site) == 1
    c = site[0]
    assert (c.entity, c.entity_key, c.value) == ("complex", "2026000367", "https://prugio-riverfront.com/")
    assert c.excerpt == '"HMPG_ADRES":"https://prugio-riverfront.com/"'
    assert text[c.excerpt_start or 0 : c.excerpt_end] == c.excerpt  # 발췌 = 원문 조각
    assert c.label == "확인됨" and c.source_rank == 1 and c.observed_on == "2026-07-30"
    # 홈페이지가 null 인 공고(무순위)는 후보 없음
    rname = "getRemndrLttotPblancDetail_2026910242.json"
    rtext = (API / rname).read_text(encoding="utf-8")
    rc = parse_applyhome_api_json(rtext, dto(source_kind="applyhome_detail", url=URLS[rname]))
    assert not [x for x in rc if x.field == "official_site_url"]


@pytest.mark.parametrize(
    ("file", "key", "want"),
    [
        (API / "web_detail_2026000367.html", "2026000367", "https://prugio-riverfront.com/"),
        (WEB / "detail_2025000271.html", "2025000271", "http://www.해링턴플레이스풍무.com/"),
        (WEB / "detail_2025000573.html", "2025000573", "https://cantaviltheedition.com/"),
    ],
)
def test_web_detail_homepage_link_candidate(file: object, key: str, want: str) -> None:
    from pathlib import Path

    path = Path(str(file))
    html = path.read_text(encoding="utf-8")
    url = URLS.get(path.name) or (
        f"https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancDetail.do?houseManageNo={key}&pblancNo={key}"
    )
    cands = parse_applyhome_html(html, dto(source_kind="applyhome_detail", url=url))
    site = [c for c in cands if c.field == "official_site_url"]
    assert [(c.entity_key, c.value) for c in site] == [(key, want)]
    assert site[0].excerpt and "홈페이지" in site[0].excerpt


def test_store_fills_official_site_url_with_provenance_and_collector_targets_it(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    name = "getAPTLttotPblancDetail_2026000367.json"
    raw = add_raw(
        (API / name).read_text(encoding="utf-8"),
        source_kind="applyhome_detail",
        url=URLS[name],
        region_id=region.id,
        ext="json",
    )
    store_raw_document(db_session, raw)
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026000367")).one()
    assert cx.official_site_url == "https://prugio-riverfront.com/"
    fp = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == "complex",
            FieldProvenance.entity_id == cx.id,
            FieldProvenance.field == "official_site_url",
            FieldProvenance.chosen.is_(True),
        )
    ).one()
    assert fp.url == URLS[name] and fp.label == "확인됨" and "HMPG_ADRES" in (fp.excerpt or "")
    # official_site 수집기: targets 를 주지 않으면 region 의 complex.official_site_url 이 대상
    collector = OfficialSiteCollector(session_factory=lambda: db_session)  # type: ignore[arg-type,return-value]
    targets = collector._region_targets(db_session, SimpleNamespace(id=region.id))  # type: ignore[arg-type]
    assert SiteTarget("https://prugio-riverfront.com/", cx.id) in targets
