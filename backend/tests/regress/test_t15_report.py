"""T15 보고서 (RA §9, DECISIONS D4 기준 — HTML + PDF).

기대(D4 완료 기준): 픽스처 스냅샷 2개로 html·pdf 생성; HTML이 외부 네트워크 없이 열림(외부 URL 리소스 0);
PDF 페이지 수 > 0 이고 텍스트 추출로 섹션 제목 11개 확인; 참고자료 URL 전수 형식 유효; §8 숫자 20개 = ``score_total``;
diff 표 생성; contradicted claim이 있으면 생성 거부.

시스템 경계: devseed DB → POST /api/reports(202) → worker(--once, report 잡) → GET /api/reports(목록) →
GET /api/reports/{id}(다운로드) → 파일 검사. 거부는 API(409 publish_blocked)와 잡(직접 등록 → failed blocked) 둘 다.
"""

# ruff: noqa: E501

from __future__ import annotations

import io
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from urllib.parse import urlparse

import pytest
from bs4 import BeautifulSoup, Tag
from sqlalchemy import select

from .conftest import SNAP, SNAP_OLD, WRITE, RegressEnv

pytestmark = pytest.mark.regress

EXT = re.compile(r"^\s*(https?:)?//", re.I)


def _make(env: RegressEnv, body: dict[str, Any]) -> tuple[int, bytes, str]:
    r = env.client.post("/api/reports", headers=WRITE, json=body)
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    assert env.worker(env.ctx("mock")) == 0
    listed = env.client.get("/api/reports", headers=WRITE, params={"snapshot_id": body["snapshot_id"]}).json()
    row = next(x for x in listed if x["id"] == job_id)
    assert row["status"] == "done", row
    d = env.client.get(f"/api/reports/{job_id}", headers=WRITE)
    assert d.status_code == 200, d.text
    return job_id, d.content, d.headers.get("content-type", "")


def _titles() -> list[str]:
    from app.reports.sections import SECTION_TITLES

    return list(SECTION_TITLES)


@pytest.mark.parametrize(("sid", "compare"), [(SNAP, SNAP_OLD), (SNAP_OLD, None)])
def test_t15_html_via_api_self_contained(env: RegressEnv, sid: int, compare: int | None) -> None:
    from app.models import RawDocument, ScoreTotal

    body: dict[str, Any] = {"snapshot_id": sid, "format": "html"}
    if compare is not None:
        body["compare_snapshot_id"] = compare
    _, content, ctype = _make(env, body)
    assert ctype.startswith("text/html")
    soup = BeautifulSoup(content.decode("utf-8"), "lxml")
    # 섹션 11개 + 앵커
    for n, title in enumerate(_titles(), start=1):
        sec = soup.find("section", id=f"s{n}")
        assert isinstance(sec, Tag), f"§{n} 없음"
        h2 = sec.find("h2")
        assert isinstance(h2, Tag) and title in h2.get_text(" ", strip=True), (n, title)
    # 외부 URL 리소스 0
    for tag in soup.find_all(
        ["script", "img", "iframe", "source", "video", "audio", "embed", "track", "input"]
    ):
        assert not EXT.match(str(tag.get("src") or "")), tag
    for tag in soup.find_all("link"):
        assert not EXT.match(str(tag.get("href") or "")), tag
    css = " ".join(t.get_text() for t in soup.find_all("style"))
    assert not re.search(r"url\(\s*['\"]?(https?:)?//", css, re.I) and "@import" not in css
    # 참고자료 URL 전수 형식 유효(+ DB 원문 URL 전부 포함)
    s11 = soup.find("section", id="s11")
    assert isinstance(s11, Tag)
    links = [str(a["href"]) for a in s11.select("a.ref-url")]
    assert links
    for href in links:
        u = urlparse(href)
        assert u.scheme in ("http", "https") and u.netloc and " " not in href, href
    with env.session() as s:
        urls = {
            u
            for u in s.scalars(select(RawDocument.url).where(RawDocument.region_id == 1))
            if u and u.startswith("http")
        }
    assert urls <= set(links), sorted(urls - set(links))[:5]
    if sid == SNAP:
        # §8 숫자 20개 이상 = score_total
        s8 = soup.find("section", id="s8")
        assert isinstance(s8, Tag)
        cells = s8.select('[data-prov^="st_"]')
        assert len(cells) >= 20, len(cells)
        with env.session() as s:
            for cell in cells:
                st = s.get(ScoreTotal, int(str(cell["data-prov"])[3:]))
                assert st is not None and st.total is not None
                want = Decimal(st.total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                v = cell.select_one(".v")
                assert v is not None and v.get_text(strip=True) == f"{want}", cell
    if compare is not None:
        table = soup.find("table", id="diff-table")
        assert isinstance(table, Tag), "diff 표 없음"
        tbody = table.find("tbody")
        assert isinstance(tbody, Tag) and len(tbody.find_all("tr")) > 0


@pytest.mark.parametrize(("sid", "compare"), [(SNAP, SNAP_OLD), (SNAP_OLD, None)])
def test_t15_pdf_via_api_pages_and_titles(env: RegressEnv, sid: int, compare: int | None) -> None:
    from pypdf import PdfReader

    body: dict[str, Any] = {"snapshot_id": sid, "format": "pdf"}
    if compare is not None:
        body["compare_snapshot_id"] = compare
    _, content, ctype = _make(env, body)
    assert ctype.startswith("application/pdf") and content[:5] == b"%PDF-"
    reader = PdfReader(io.BytesIO(content))
    assert len(reader.pages) > 0
    text = re.sub(r"\s+", "", "".join(p.extract_text() or "" for p in reader.pages))
    missing = [t for t in _titles() if text.count(re.sub(r"\s+", "", t)) < 2]  # 목차 + 본문
    assert not missing, missing


def test_t15_contradicted_claim_refuses(env: RegressEnv) -> None:
    from app.models import Claim, JobRun
    from app.scheduler.jobs import enqueue

    with env.session() as s:
        s.add(
            Claim(
                snapshot_id=SNAP,
                section="regress T15",
                complex_id=None,
                text="회귀 테스트 contradicted 주장",
                verify_status="contradicted",
                ordinal=0,
            )
        )
        s.commit()
    r = env.client.post("/api/reports", headers=WRITE, json={"snapshot_id": SNAP, "format": "html"})
    assert r.status_code == 409 and r.json()["code"] == "publish_blocked", r.text
    # API 를 거치지 않고 잡을 직접 넣어도 잡이 거부한다
    with env.session() as s:
        jid = enqueue(s, "report", {"snapshot_id": SNAP, "format": "html"}).id
        s.commit()
    env.worker(env.ctx("mock"))
    with env.session() as s:
        job = s.get(JobRun, jid)
        assert job is not None and job.status == "failed" and "blocked" in (job.error_text or ""), (
            job.status if job else None
        )
    assert not any(env.settings.report_dir.rglob("*.html")) if env.settings.report_dir.exists() else True
