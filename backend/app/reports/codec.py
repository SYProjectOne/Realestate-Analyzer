"""보고서 입력 데이터(``reports.data.ReportData``) ↔ JSON — 발행 리비전 저장본(DECISIONS D13-1).

발행 트랜잭션이 보고서 입력 데이터를 저장(``snapshot_view`` kind=report)하고, 보고서 잡은 그 저장본을 되살려 렌더한다
(현재 사실로 다시 적재하지 않는다). 형식은 태그 JSON:

- 데이터클래스 → ``{"$dc": "<이름>", "f": {필드: 값}}`` (``reports.data``·``reports.diff`` 의 데이터클래스만 — 허용 목록)
- 계약 모델(``Fact`` 등 pydantic) → ``{"$m": "<이름>", "f": {필드: 값}}`` (되살릴 때 ``model_construct`` — 강제 변환 없음)
- Decimal ``{"$d": "1.23"}`` · date ``{"$date": "2026-10-08"}`` · tuple ``{"$t": [...]}``
- 문자열이 아닌 키의 dict ``{"$kv": [[키, 값], ...]}`` (키 순서 유지)
- ``$`` 로 시작하는 키를 가진 보통 dict 는 ``{"$raw": {...}}`` 로 감싼다(태그와 섞이지 않게)

판단 없음 — 값 그대로 옮긴다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

from pydantic import BaseModel

__all__ = ["decode_data", "encode_data"]


def _registry() -> tuple[dict[str, type], dict[str, type[BaseModel]]]:
    from app.core import contracts_gen
    from app.reports import data as rdata
    from app.reports import diff as rdiff

    dcs: dict[str, type] = {}
    for mod in (rdata, rdiff):
        for name, obj in vars(mod).items():
            if isinstance(obj, type) and dataclasses.is_dataclass(obj) and obj.__module__ == mod.__name__:
                dcs[name] = obj
    models = {
        name: obj
        for name, obj in vars(contracts_gen).items()
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel
    }
    return dcs, models


_FIELDS: dict[type, tuple[str, ...]] = {}


def _field_names(cls: type) -> tuple[str, ...]:
    names = _FIELDS.get(cls)
    if names is None:
        if issubclass(cls, BaseModel):
            names = tuple(cls.model_fields)
        else:
            names = tuple(f.name for f in dataclasses.fields(cast(Any, cls)))
        _FIELDS[cls] = names
    return names


def encode_data(obj: Any, memo: dict[int, tuple[Any, Any]] | None = None) -> Any:
    """``memo``(같은 적재의 여러 시나리오 — 공유하는 단지 뷰·Fact)는 이미 바꾼 객체를 다시 바꾸지 않는다(객체를 함께
    붙잡아 id 재사용을 막는다)."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if memo is not None:
        hit = memo.get(id(obj))
        if hit is not None and hit[0] is obj:
            return hit[1]
    out: Any
    if isinstance(obj, Decimal):
        return {"$d": str(obj)}
    if isinstance(obj, datetime):
        return {"$dt": obj.isoformat()}
    if isinstance(obj, date):
        return {"$date": obj.isoformat()}
    if isinstance(obj, BaseModel):
        out = {
            "$m": type(obj).__name__,
            "f": {k: encode_data(getattr(obj, k), memo) for k in _field_names(type(obj))},
        }
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {
            "$dc": type(obj).__name__,
            "f": {k: encode_data(getattr(obj, k), memo) for k in _field_names(type(obj))},
        }
    elif isinstance(obj, tuple):
        return {"$t": [encode_data(v, memo) for v in obj]}
    elif isinstance(obj, (list, set, frozenset)):
        return [encode_data(v, memo) for v in obj]
    elif isinstance(obj, dict):
        if all(isinstance(k, str) for k in obj):
            body = {k: encode_data(v, memo) for k, v in obj.items()}
            return {"$raw": body} if any(k.startswith("$") for k in obj) else body
        return {"$kv": [[encode_data(k, memo), encode_data(v, memo)] for k, v in obj.items()]}
    else:
        raise TypeError(f"보고서 데이터 직렬화 불가: {type(obj).__name__}")
    if memo is not None:
        memo[id(obj)] = (obj, out)
    return out


def decode_data(obj: Any, _reg: tuple[dict[str, type], dict[str, type[BaseModel]]] | None = None) -> Any:
    reg = _reg or _registry()
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, list):
        return [decode_data(v, reg) for v in obj]
    if not isinstance(obj, dict):  # pragma: no cover - JSON 밖
        raise TypeError(type(obj).__name__)
    if "$d" in obj:
        return Decimal(obj["$d"])
    if "$dt" in obj:
        return datetime.fromisoformat(obj["$dt"])
    if "$date" in obj:
        return date.fromisoformat(obj["$date"])
    if "$t" in obj:
        return tuple(decode_data(v, reg) for v in obj["$t"])
    if "$kv" in obj:
        return {decode_data(k, reg): decode_data(v, reg) for k, v in obj["$kv"]}
    if "$raw" in obj:
        return {k: decode_data(v, reg) for k, v in obj["$raw"].items()}
    if "$dc" in obj:
        cls = reg[0][obj["$dc"]]
        return cls(**{k: decode_data(v, reg) for k, v in obj["f"].items()})
    if "$m" in obj:
        model = reg[1][obj["$m"]]
        return model.model_construct(**{k: decode_data(v, reg) for k, v in obj["f"].items()})
    return {k: decode_data(v, reg) for k, v in obj.items()}
