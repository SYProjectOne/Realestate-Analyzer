"""입주물량 — "추정 집계" 인터페이스 (RA §3 supply: '추정 집계'는 label 에).

공개 원천 조사(2026-10-09)
- 한국부동산원 R-ONE 의 입주예정물량 통계: robots.txt 가 ``/r-one/statistics/`` 를 막는다(전체 User-agent).
- 공공데이터포털의 부동산원·국토부 입주(예정)물량 API 는 서비스 키가 필요하다(키 없음, D1 #5).
- 국토교통 통계누리에는 시군구·월별 '입주물량' 통계표가 없다(주택건설실적·준공 실적만).
그래서 키 없는 공식 원천이 없다 → 공고문의 입주예정월 × 세대수 합산을 '추정' 라벨(reason '추정 집계')로
만든다.
입력은 WP2 가 정규화한 단지 값이고(공고문 출처), 여기서는 합산과 적재만 한다. 공식 원천이 생기면
``SupplySource``
구현을 하나 더 두면 된다.

청약홈 공식 API(R2X, 2026-10-09): ``supply_inputs_from_applyhome_api`` 가 'APT 분양정보 상세' JSON 의
입주예정월(``MVN_PREARNGE_YM``)·공급세대수(``TOT_SUPLY_HSHLDCO``)를 같은 ``SupplyInput`` 으로 바꾼다 —
합산은 그대로 ``estimate_supply``(라벨 '추정', reason '추정 집계': 공급세대 = 일반+특별, 조합원분 제외라
실제 입주 세대보다 작을 수 있다). 잔여세대(무순위·임의공급) 행은 남은 세대만 적혀 있어 단지 입주물량이
아니므로 쓰지 않고, 민간사전청약(09)은 본청약 공고에 다시 나오므로 뺀다.

출처(R3 W3): ``write_supply_provenance`` 가 추정 행의 units·year·ym 마다 field_provenance
(라벨 추정, 원문 = 단지의 채택 출처)를 쓴다 — 출처 없는 supply 행은 API 가 dev 에서
contract_violation(500)으로 막는다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.reference.load import LoadStats
from app.models import FieldProvenance, Supply

__all__ = [
    "SUPPLY_ESTIMATE_LABEL",
    "SUPPLY_ESTIMATE_REASON",
    "SUPPLY_SOURCE_FIELDS",
    "SupplyInput",
    "SupplyProvenance",
    "SupplyRecord",
    "SupplySource",
    "aggregate_supply",
    "estimate_supply",
    "load_supply",
    "supply_inputs_from_applyhome_api",
    "write_supply_provenance",
]

SUPPLY_ESTIMATE_LABEL = "추정"
SUPPLY_ESTIMATE_REASON = "추정 집계"


@dataclass(frozen=True, slots=True)
class SupplyInput:
    """단지 1개의 입주 정보(공고문 출처) — WP2 정규화 결과에서 만든다."""

    complex_id: int
    living_area: str | None
    move_in_ym: str | None  # YYYY-MM
    units: int | None
    raw_document_id: int | None = None


@dataclass(frozen=True, slots=True)
class SupplyRecord:
    living_area: str | None
    year: int
    ym: str | None
    units: int
    label: str
    reason: str | None
    complex_id: int | None = None
    raw_document_id: int | None = None


class SupplySource(Protocol):
    """입주물량 원천. 공식 통계 원천이 생기면 label='확인됨' 레코드를 내는 구현을 추가한다."""

    def supply(self, inputs: Iterable[SupplyInput]) -> list[SupplyRecord]: ...


def estimate_supply(inputs: Iterable[SupplyInput]) -> list[SupplyRecord]:
    """단지별 행: 입주예정월·세대수가 둘 다 있는 단지만(없으면 건너뛴다 — 0 으로 세지 않는다)."""
    out: list[SupplyRecord] = []
    for i in inputs:
        if not i.move_in_ym or i.units is None or i.units < 0 or len(i.move_in_ym) < 7:
            continue
        out.append(
            SupplyRecord(
                living_area=i.living_area,
                year=int(i.move_in_ym[:4]),
                ym=i.move_in_ym[:7],
                units=i.units,
                label=SUPPLY_ESTIMATE_LABEL,
                reason=SUPPLY_ESTIMATE_REASON,
                complex_id=i.complex_id,
                raw_document_id=i.raw_document_id,
            )
        )
    return out


# 청약홈 API 주택구분(HOUSE_SECD): 01 APT·10 신혼희망타운 = 단지 전체 공급(09 민간사전청약은 본청약에서 다시)
APPLYHOME_SUPPLY_HOUSE_SECD = frozenset({"01", "10"})
_YM = re.compile(r"^(\d{4})-?(\d{2})$")


def supply_inputs_from_applyhome_api(
    content: bytes | str,
    *,
    complex_id_for: Callable[[str], int | None],
    living_area_for: Callable[[int], str | None] = lambda _cid: None,
    raw_document_id: int | None = None,
) -> list[SupplyInput]:
    """청약홈 API 'APT 분양정보 상세' JSON(목록 페이지 또는 공고 1건) → ``SupplyInput``.

    ``complex_id_for(주택관리번호)`` 가 None 이면(아직 단지 행이 없거나 지역 밖) 건너뛴다.
    JSON 이 아니거나 data 가 없으면 [] (실패도 0 으로 세지 않는다).
    """
    try:
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    rows = data.get("data") if isinstance(data, dict) else None
    out: list[SupplyInput] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or str(row.get("HOUSE_SECD") or "") not in APPLYHOME_SUPPLY_HOUSE_SECD:
            continue
        cid = complex_id_for(str(row.get("HOUSE_MANAGE_NO") or ""))
        if cid is None:
            continue
        out.append(
            SupplyInput(
                complex_id=cid,
                living_area=living_area_for(cid),
                move_in_ym=_api_ym(row.get("MVN_PREARNGE_YM")),
                units=_api_int(row.get("TOT_SUPLY_HSHLDCO")),
                raw_document_id=raw_document_id,
            )
        )
    return out


def _api_ym(value: Any) -> str | None:
    m = _YM.match(str(value or "").strip())
    if m is None or not 1 <= int(m.group(2)) <= 12:
        return None
    return f"{m.group(1)}-{m.group(2)}"


def _api_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    digits = str(value or "").replace(",", "").strip()
    return int(digits) if digits.isdigit() else None


class NoticeMoveInEstimator:
    """``SupplySource`` 기본 구현: 공고문 입주예정월 합산(추정)."""

    def supply(self, inputs: Iterable[SupplyInput]) -> list[SupplyRecord]:
        return estimate_supply(inputs)


def aggregate_supply(records: Iterable[SupplyRecord]) -> dict[tuple[str | None, int], int]:
    """(생활권, 연도) → 세대수 합. 화면·점수 쪽(WP4)이 쓰는 모양."""
    out: dict[tuple[str | None, int], int] = {}
    for r in records:
        out[(r.living_area, r.year)] = out.get((r.living_area, r.year), 0) + r.units
    return out


def load_supply(session: Session, region_id: int, records: Iterable[SupplyRecord]) -> LoadStats:
    """단지별 추정 행 upsert: (region_id, complex_id, label='추정', reason='추정 집계') 하나."""
    stats = LoadStats()
    existing = {
        s.complex_id: s
        for s in session.scalars(
            select(Supply).where(Supply.region_id == region_id, Supply.reason == SUPPLY_ESTIMATE_REASON)
        )
        if s.complex_id is not None
    }
    for r in records:
        row = existing.get(r.complex_id) if r.complex_id is not None else None
        if row is None:
            session.add(
                Supply(
                    region_id=region_id,
                    living_area=r.living_area,
                    year=r.year,
                    ym=r.ym,
                    units=r.units,
                    label=r.label,
                    reason=r.reason,
                    complex_id=r.complex_id,
                    raw_document_id=r.raw_document_id,
                )
            )
            stats.inserted += 1
        elif (row.living_area, row.year, row.ym, row.units) != (r.living_area, r.year, r.ym, r.units):
            row.living_area, row.year, row.ym, row.units = r.living_area, r.year, r.ym, r.units
            row.raw_document_id = r.raw_document_id
            stats.updated += 1
        else:
            stats.unchanged += 1
    session.flush()
    return stats


# ---------------------------------------------------------------- 출처 (R3 W3)

# supply 컬럼 → 그 값을 만든 단지 필드(채택 출처를 가리킨다)
SUPPLY_SOURCE_FIELDS: dict[str, str] = {"units": "units_total", "year": "move_in_ym", "ym": "move_in_ym"}


@dataclass
class SupplyProvenance:
    written: int = 0  # 새로 채택한 출처 행
    missing: int = 0  # 단지 쪽 채택 출처가 없어 쓰지 못한 (행, 필드) — 지어내지 않는다

    def stats(self) -> dict[str, int]:
        return {"written": self.written, "missing": self.missing}


def write_supply_provenance(session: Session, region_id: int) -> SupplyProvenance:
    """추정 집계 supply 행(단지별)의 units·year·ym 출처 행
    (R3 W3, RA §3 '숫자 하나도 출처 없이 남기지 않는다').

    출처 = 그 단지의 채택 출처(complex.units_total / move_in_ym)의 원문·URL·확인일·발췌,
    라벨 '추정'(합산 집계), reason '추정 집계(단지 <필드> 출처)'. 같은 원문·같은 값의 채택 행이
    이미 있으면 그대로(멱등), 값·원문이 바뀌면 새 행을 채택하고 옛 행은 chosen=false 로 남긴다
    (삭제 없음). 단지 출처가 없으면 ``missing`` 으로 센다.
    """
    out = SupplyProvenance()
    rows = [
        s
        for s in session.scalars(
            select(Supply)
            .where(Supply.region_id == region_id, Supply.reason == SUPPLY_ESTIMATE_REASON)
            .order_by(Supply.id)
        )
        if s.complex_id is not None
    ]
    if not rows:
        return out
    cids = sorted({s.complex_id for s in rows if s.complex_id is not None})
    srcs: dict[tuple[int, str], FieldProvenance] = {}
    for fp in session.scalars(
        select(FieldProvenance)
        .where(
            FieldProvenance.entity == "complex",
            FieldProvenance.entity_id.in_(cids),
            FieldProvenance.field.in_(sorted(set(SUPPLY_SOURCE_FIELDS.values()))),
            FieldProvenance.chosen.is_(True),
        )
        .order_by(FieldProvenance.id)
    ):
        if fp.entity_id is not None and fp.label != "확인 불가" and (fp.url or "").strip():
            srcs[(fp.entity_id, fp.field)] = fp
    current: dict[tuple[int, str], list[FieldProvenance]] = {}
    for fp in session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == "supply",
            FieldProvenance.entity_id.in_([s.id for s in rows]),
            FieldProvenance.chosen.is_(True),
        )
    ):
        if fp.entity_id is not None:
            current.setdefault((fp.entity_id, fp.field), []).append(fp)
    for row in rows:
        assert row.complex_id is not None
        for name, src_field in SUPPLY_SOURCE_FIELDS.items():
            value = getattr(row, name)
            src = srcs.get((row.complex_id, src_field))
            if value is None:
                continue
            if src is None:
                out.missing += 1
                continue
            text = str(value)
            chosen = current.get((row.id, name), [])
            if any(
                fp.value_text == text and fp.raw_document_id == src.raw_document_id and fp.url == src.url
                for fp in chosen
            ):
                continue
            for fp in chosen:
                fp.chosen = False
            session.add(
                FieldProvenance(
                    entity="supply",
                    entity_id=row.id,
                    entity_key=f"complex:{row.complex_id}",
                    field=name,
                    value_text=text,
                    value_norm=text,
                    raw_document_id=src.raw_document_id,
                    url=src.url,
                    checked_at=src.checked_at,
                    label=SUPPLY_ESTIMATE_LABEL,
                    reason=f"{SUPPLY_ESTIMATE_REASON}(단지 {src_field} 출처)",
                    source_rank=src.source_rank,
                    chosen=True,
                    excerpt=src.excerpt,
                    excerpt_start=src.excerpt_start,
                    excerpt_end=src.excerpt_end,
                    observed_on=src.observed_on,
                )
            )
            out.written += 1
    session.flush()
    return out
