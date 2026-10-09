"""F1a(R3 C1·M5·M6·M7) 테스트 공용: 청약홈 API JSON·실거래 행을 합성한다.

값은 가상이다(형식은 2026-10-09 실제 응답 녹화와 같다 — ``tests/collectors/applyhome/fixtures``).
지역명은 테스트 데이터에만 나온다(AGENTS 규칙 15).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.collectors.applyhome import api as ah_api
from app.models import Complex, RtmsTrade

from ._support import AddRaw

ASOF = "2026-10-08"
FETCHED = "2026-10-08T06:00:00+09:00"


def api_page(rows: list[dict[str, Any]]) -> str:
    return json.dumps(
        {
            "currentCount": len(rows),
            "data": rows,
            "matchCount": len(rows),
            "page": 1,
            "perPage": 100,
            "totalCount": 9999,
        },
        ensure_ascii=False,
    )


def notice_row(
    hm: str,
    name: str,
    address: str,
    notice: str,
    move_in: str | None,
    *,
    housing: str = "민영",
    area: str = "인천",
) -> dict[str, Any]:
    return {
        "HOUSE_MANAGE_NO": hm,
        "PBLANC_NO": hm,
        "HOUSE_NM": name,
        "HSSPLY_ADRES": address,
        "RCRIT_PBLANC_DE": notice,
        "MVN_PREARNGE_YM": move_in,
        "HOUSE_DTL_SECD_NM": housing,
        "HOUSE_SECD": "01",
        "SUBSCRPT_AREA_CODE_NM": area,
        "TOT_SUPLY_HSHLDCO": 500,
    }


def list_url(area: str, begin: date = date(2016, 10, 1), end: date = date(2026, 10, 8)) -> str:
    return ah_api.doc_url(ah_api.ENDPOINTS["apt"].detail, ah_api.list_params("apt", area, begin, end, 1))


def model_url(hm: str, kind: ah_api.ApiKind = "apt") -> str:
    return ah_api.doc_url(ah_api.ENDPOINTS[kind].model, ah_api.item_params(hm, hm))


def detail_url(hm: str, kind: ah_api.ApiKind) -> str:
    return ah_api.doc_url(ah_api.ENDPOINTS[kind].detail, ah_api.item_params(hm, hm))


def model_rows(
    hm: str, types: list[tuple[str, int | None, int]], *, special: int = 0
) -> list[dict[str, Any]]:
    """types = [(주택형 원문, 최고가(만원) | None, 일반 세대수)]."""
    return [
        {
            "HOUSE_MANAGE_NO": hm,
            "PBLANC_NO": hm,
            "HOUSE_TY": ty,
            "LTTOT_TOP_AMOUNT": str(price) if price is not None else None,
            "MODEL_NO": f"{i + 1:02d}",
            "SPSPLY_HSHLDCO": special,
            "SUPLY_AR": None,
            "SUPLY_HSHLDCO": units,
        }
        for i, (ty, price, units) in enumerate(types)
    ]


def add_list(add_raw: AddRaw, region_id: int, area: str, rows: list[dict[str, Any]], **kw: Any) -> int:
    doc = add_raw(
        api_page(rows),
        source_kind="applyhome_list",
        url=kw.pop("url", None) or list_url(area),
        region_id=region_id,
        fetched_at=kw.pop("fetched_at", FETCHED),
        ext="json",
    )
    assert doc.id is not None
    return doc.id


def add_model(add_raw: AddRaw, region_id: int, hm: str, types: list[tuple[str, int | None, int]]) -> int:
    doc = add_raw(
        api_page(model_rows(hm, types)),
        source_kind="applyhome_detail",
        url=model_url(hm),
        region_id=region_id,
        fetched_at=FETCHED,
        ext="json",
    )
    assert doc.id is not None
    return doc.id


def rtms_url(lawd: str, ym: str) -> str:
    return (
        "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
        f"?LAWD_CD={lawd}&DEAL_YMD={ym}&numOfRows=1000&pageNo=1"
    )


def add_trade(
    session: Session,
    region_id: int,
    name: str,
    price_man: int,
    day: str,
    *,
    legal: str | None = None,
    dong: str | None = None,
    area: str = "84.95",
    built: int | None = None,
    cancelled: bool = False,
    presale: bool = False,
    raw_document_id: int | None = None,
    source: str = "openapi",
) -> RtmsTrade:
    t = RtmsTrade(
        region_id=region_id,
        apt_name=name,
        dong=dong,
        legal_dong_code=legal,
        completed_year=built,
        area_m2=Decimal(area),
        floor=10,
        price_won=price_man * 10_000,
        deal_date=day,
        cancelled=cancelled,
        is_presale=presale,
        source=source,
        raw_document_id=raw_document_id,
    )
    session.add(t)
    session.flush()
    return t


def add_complex(session: Session, region_id: int, hm: str | None, name: str, **kw: Any) -> Complex:
    cx = Complex(
        region_id=region_id,
        applyhome_id=hm,
        name=name,
        former_names=[],
        apply_dates=kw.pop("apply_dates", []),
        contract_dates=kw.pop("contract_dates", []),
        inclusion_class=kw.pop("inclusion_class", "미분류"),
        **kw,
    )
    session.add(cx)
    session.flush()
    return cx
