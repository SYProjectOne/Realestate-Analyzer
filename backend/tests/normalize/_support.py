"""WP2 테스트 공용 경로·도구(픽스처 fixture는 conftest.py)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.models import Region
from app.normalize.living_area import default_living_areas
from app.normalize.region_resolve import ReferenceData

FIX = Path(__file__).parent / "fixtures"
NOTICE = FIX / "notice"
APPLYHOME = FIX / "applyhome"
REFERENCE = FIX / "reference"
NOTICE_BASE = "https://static.applyhome.co.kr/ai/aia/getAtchmnfl.do?"
DETAIL_URL = "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancDetail.do?houseManageNo={n}&pblancNo={n}"
COMP_URL = "https://www.applyhome.co.kr/ai/aia/selectAPTCompetitionPopup.do?houseManageNo={n}&pblancNo={n}"


def notice_manifest() -> dict[str, dict[str, Any]]:
    return {m["file"]: m for m in json.loads((NOTICE / "manifest.json").read_text(encoding="utf-8"))}


def notice_file(stem_part: str) -> Path:
    return next(NOTICE.glob(f"*{stem_part}*.txt"))


def dto(
    *,
    source_kind: str,
    url: str,
    fetched_at: str = "2026-10-09T06:00:00+09:00",
    http_status: int | None = 200,
    raw_id: int | None = 1,
    complex_id: int | None = None,
    region_id: int | None = None,
    path: str | None = None,
    text_path: str | None = None,
    sha: str | None = None,
    error_text: str | None = None,
) -> RawDocumentDTO:
    return RawDocumentDTO(
        id=raw_id,
        source_kind=source_kind,  # type: ignore[arg-type]
        url=url,
        fetched_at=fetched_at,
        http_status=http_status,
        sha256=sha or hashlib.sha256(url.encode()).hexdigest(),
        path=path,
        content_type=None,
        text_path=text_path,
        complex_id=complex_id,
        region_id=region_id,
        error_text=error_text,
    )


AddRaw = Callable[..., RawDocumentDTO]


def make_region(
    session: Session, ref: ReferenceData, sigungu_codes: list[str], *, name: str = "테스트 지역"
) -> Region:
    legal = sorted(
        r.code for r in ref.legal if r.active and r.eupmyeondong_name and r.sigungu_code in sigungu_codes
    )
    region = Region(
        name=name,
        query_text=name,
        selections=[{"kind": "sigungu", "code": c, "full_name": c} for c in sigungu_codes],
        sido_codes=sorted({c[:2] for c in legal}),
        sigungu_codes=sorted(set(sigungu_codes)),
        legal_dong_codes=legal,
        living_areas=default_living_areas(legal, ref.legal),
        age_premium_coef={"c_per_year": 0.015, "cap_years": 8, "label": "추정"},
        applyhome_query={},
        status="ready",
        created_at="2026-10-09T06:00:00+09:00",
    )
    session.add(region)
    session.flush()
    return region
