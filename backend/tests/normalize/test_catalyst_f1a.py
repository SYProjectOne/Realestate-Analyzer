"""R3 M6: 호재 후보 행 — 뉴스 수집 결과·사람 URL 입력 → catalyst(stage 미확정, 위치 미확정, 연결 없음).

분류(kind·stage)는 판정기 P4 classify 몫이다(AGENTS 규칙 3) — 여기서는 키워드로 거르거나 단계를 정하지 않는다.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Catalyst, CatalystLink, Region
from app.normalize.catalyst import CatalystInputError, catalyst_candidate, catalysts_from_news

from ._support import AddRaw

NEWS_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news?query=x&display=20&start=1&sort=date"


def test_human_url_becomes_unclassified_candidate(db_session: Session, region: Region) -> None:
    out = catalyst_candidate(
        db_session,
        region.id,
        url="https://www.example.go.kr/notice/123",
        title="  ○○선 연장 기본계획 고시  ",
        excerpt="국토부는 ○○선 연장 기본계획을 고시했다",
    )
    assert out.created
    cat = out.catalyst
    assert (cat.name, cat.kind, cat.stage, cat.decision) == ("○○선 연장 기본계획 고시", "기타", "미확정", None)
    assert cat.location_confirmed is False and cat.lat is None and cat.lon is None
    assert cat.source_url == "https://www.example.go.kr/notice/123"
    assert cat.note is not None and "기본계획을 고시했다" in cat.note
    assert cat.stage_prob is None and cat.judgment_seq is None and cat.expected_ym is None
    assert db_session.scalar(select(func.count()).select_from(CatalystLink)) == 0

    again = catalyst_candidate(db_session, region.id, url="https://www.example.go.kr/notice/123", title="다른 제목")
    assert not again.created and again.catalyst.id == cat.id


@pytest.mark.parametrize(
    ("url", "title"),
    [("javascript:alert(1)", "제목"), ("ftp://x.y/z", "제목"), ("https://x.y/z", "   "), ("not a url", "제목")],
)
def test_invalid_input_is_rejected(db_session: Session, region: Region, url: str, title: str) -> None:
    with pytest.raises(CatalystInputError):
        catalyst_candidate(db_session, region.id, url=url, title=title)


def test_news_items_become_candidates_without_filtering(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    body = {
        "items": [
            {
                "title": "<b>송도</b> 6·8공구 개발 속도",
                "originallink": "https://news.example.com/a1",
                "link": "https://n.news.example.com/a1",
                "description": "인천경제청은 &quot;개발&quot; 계획을 밝혔다",
                "pubDate": "Wed, 07 Oct 2026 09:00:00 +0900",
            },
            {
                "title": "검단 신규 분양 일정",
                "originallink": "",
                "link": "https://n.news.example.com/a2",
                "description": "분양 일정",
                "pubDate": "Wed, 07 Oct 2026 10:00:00 +0900",
            },
            {"title": "", "originallink": "https://news.example.com/empty", "description": "제목 없음"},
        ]
    }
    doc = add_raw(json.dumps(body, ensure_ascii=False), source_kind="news", url=NEWS_URL, region_id=region.id, ext="json")
    res = catalysts_from_news(db_session, region.id, [doc])
    rows = list(db_session.scalars(select(Catalyst).order_by(Catalyst.id)))
    assert [(c.name, c.source_url) for c in rows] == [
        ("송도 6·8공구 개발 속도", "https://news.example.com/a1"),
        ("검단 신규 분양 일정", "https://n.news.example.com/a2"),
    ]
    assert all(c.stage == "미확정" and c.kind == "기타" and not c.location_confirmed for c in rows)
    assert rows[0].raw_document_id == doc.id
    assert rows[0].note is not None and '"개발"' in rows[0].note
    assert (res.inserted, res.existing) == (2, 0)

    again = catalysts_from_news(db_session, region.id, [doc])
    assert (again.inserted, again.existing) == (0, 2)
    assert db_session.scalar(select(func.count()).select_from(Catalyst)) == 2


def test_failed_news_document_is_ignored(db_session: Session, region: Region) -> None:
    from app.core.contracts_gen import RawDocument as RawDTO

    failed = RawDTO(
        id=None,
        source_kind="news",
        url=NEWS_URL,
        fetched_at="2026-10-08T06:00:00+09:00",
        http_status=401,
        sha256="f" * 64,
        path=None,
        content_type=None,
        text_path=None,
        complex_id=None,
        region_id=region.id,
        error_text="401",
        image_hash=None,
    )
    res = catalysts_from_news(db_session, region.id, [failed])
    assert res.inserted == 0
