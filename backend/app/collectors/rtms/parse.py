"""국토부 아파트 매매 실거래가 Open API XML → ``TradeRecord`` (RA §3 rtms_trade).

엔드포인트: ``https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade``
(serviceKey, LAWD_CD 5자리, DEAL_YMD YYYYMM, pageNo, numOfRows).

응답(2024 개편 사양): ``<response><header><resultCode>000</resultCode>…<body><items><item>`` — 항목
aptNm·aptDong·buildYear·dealYear·dealMonth·dealDay·dealAmount("82,500"
만원)·excluUseAr·floor·sggCd·umdCd·umdNm·
jibun·dealingGbn·cdealType("O" = 해제)·cdealDay("26.10.02")·rgstDate.
오류(키 없음·미등록 등)는 ``<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>…`` (HTTP 401/403 또는 200).

해제(cancelled) 플래그를 보존한다 — 점수에서 빼는 것은 WP4 몫이다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

__all__ = ["TradePage", "TradeRecord", "api_error_message", "parse_trade_xml"]

TradeSource = Literal["openapi", "reprocessed"]
TradeLabel = Literal["확인됨", "재가공"]
_OK_CODES = {"00", "000"}


@dataclass(frozen=True, slots=True)
class TradeRecord:
    apt_name: str
    dong: str | None  # 법정동 이름(umdNm)
    legal_dong_code: str | None  # sggCd + umdCd (10자리)
    completed_year: int | None
    area_m2: Decimal
    floor: int | None
    price_won: int
    deal_date: str  # YYYY-MM-DD
    cancelled: bool
    cancel_date: str | None = None
    is_presale: bool = False
    source: TradeSource = "openapi"
    label: TradeLabel = "확인됨"
    apt_dong: str | None = None  # 아파트 동(101동 등)
    jibun: str | None = None
    dealing_type: str | None = None


@dataclass(slots=True)
class TradePage:
    result_code: str | None
    result_msg: str | None
    total_count: int = 0
    page_no: int = 1
    num_rows: int = 0
    items: list[TradeRecord] = field(default_factory=list)
    skipped: int = 0

    @property
    def ok(self) -> bool:
        return self.result_code in _OK_CODES


def _text(el: ET.Element, tag: str) -> str | None:
    child = el.find(tag)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    digits = value.replace(",", "").strip()
    if digits.lstrip("-").isdigit():
        return int(digits)
    return None


def _cancel_date(value: str | None) -> str | None:
    """'26.10.02' → '2026-10-02'. 형식이 다르면 원문."""
    if not value:
        return None
    parts = value.strip().split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        y, m, d = (int(p) for p in parts)
        y = y + 2000 if y < 100 else y
        return f"{y:04d}-{m:02d}-{d:02d}"
    return value.strip()


def api_error_message(content: bytes) -> str | None:
    """공공데이터포털 공통 오류 XML의 errMsg(없으면 None)."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    msg = root.findtext(".//cmmMsgHeader/errMsg")
    return msg.strip() if msg else None


def parse_trade_xml(content: bytes) -> TradePage:
    if b"<!DOCTYPE" in content[:512] or b"<!ENTITY" in content:
        return TradePage(result_code=None, result_msg="XML 오류: DTD·엔티티는 받지 않는다")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        return TradePage(result_code=None, result_msg=f"XML 오류: {exc}")
    err = root.findtext(".//cmmMsgHeader/errMsg")
    if err:
        code = root.findtext(".//cmmMsgHeader/returnReasonCode")
        return TradePage(result_code=(code or "").strip() or "ERR", result_msg=err.strip())
    page = TradePage(
        result_code=(root.findtext(".//header/resultCode") or "").strip() or None,
        result_msg=(root.findtext(".//header/resultMsg") or "").strip() or None,
        total_count=_int(root.findtext(".//body/totalCount")) or 0,
        page_no=_int(root.findtext(".//body/pageNo")) or 1,
        num_rows=_int(root.findtext(".//body/numOfRows")) or 0,
    )
    for item in root.iterfind(".//body/items/item"):
        name = _text(item, "aptNm")
        price_man = _int(_text(item, "dealAmount"))
        y, m, d = (_int(_text(item, t)) for t in ("dealYear", "dealMonth", "dealDay"))
        try:
            area = Decimal(_text(item, "excluUseAr") or "").quantize(Decimal("0.01"))
        except InvalidOperation:
            area = None
        if not name or price_man is None or y is None or m is None or d is None or area is None:
            page.skipped += 1
            continue
        sgg, umd = _text(item, "sggCd"), _text(item, "umdCd")
        legal = f"{sgg}{umd}" if sgg and umd and len(sgg) == 5 and len(umd) == 5 else None
        cdeal = (_text(item, "cdealType") or "").upper()
        page.items.append(
            TradeRecord(
                apt_name=name,
                dong=_text(item, "umdNm"),
                legal_dong_code=legal,
                completed_year=_int(_text(item, "buildYear")),
                area_m2=area,
                floor=_int(_text(item, "floor")),
                price_won=price_man * 10_000,
                deal_date=f"{y:04d}-{m:02d}-{d:02d}",
                cancelled=cdeal == "O",
                cancel_date=_cancel_date(_text(item, "cdealDay")),
                apt_dong=_text(item, "aptDong"),
                jibun=_text(item, "jibun"),
                dealing_type=_text(item, "dealingGbn"),
            )
        )
    return page
