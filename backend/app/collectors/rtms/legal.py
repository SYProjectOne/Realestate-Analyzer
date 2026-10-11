"""실거래 거래 → 법정동 코드 (R4 C2, DECISIONS D18-3).

실제 국토부 매매·분양권 실거래 API 응답에는 ``umdCd`` 가 없다(``sggCd``·``umdNm`` 만 — R4 2026-10-12 녹화 144건 전부).
``umdCd`` 가 있으면 ``sggCd + umdCd`` 를 그대로 쓰고, 없으면 참조 표(legal_dong)에서 **같은 시군구 코드**의 활성 행을
읍면동 이름(+ 리 이름)으로 찾는다. ``umdNm`` 이 두 낱말이면(읍면 지역 ``고촌읍 신곡리``) 읍면 + 리로 찾는다.

- 정확히 1행 → 그 코드. 0행 → NULL + 사유 '참조 표에 없음', 2행 이상 → NULL + '모호'. 시군구 코드가 없으면 '시군구 코드 없음'.
- 동 이름만으로는 안 된다: 같은 이름이 다른 구에 있다(예: 오류동 — 계양구·검단구). 시군구 코드는 API 가 분구 뒤의 새
  코드로 돌려준다(검단구 28290 — 분구 전 달도 새 코드).
- 이것은 파싱(이름 → 코드 표 찾기)이지 판단이 아니다(AGENTS 규칙 3).

보정(``repair_legal_dong_codes``): 이미 법정동 코드 없이 적재된 행은 원문 URL 의 ``LAWD_CD``(= 요청한 시군구 = 응답 sggCd)
와 저장된 동 이름(umdNm)으로 같은 표 찾기를 한다. 수집 적재가 끝날 때마다 돌고(멱등 — NULL 행만), 수동 실행도 된다::

    uv run python -m app.collectors.rtms.legal --region 1
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LegalDong, RawDocument, RtmsTrade

__all__ = [
    "REASON_AMBIGUOUS",
    "REASON_NOT_FOUND",
    "REASON_NO_SGG",
    "LegalDongIndex",
    "lawd_of_url",
    "repair_legal_dong_codes",
]

REASON_NOT_FOUND: Final = "참조 표에 없음"
REASON_AMBIGUOUS: Final = "모호"
REASON_NO_SGG: Final = "시군구 코드 없음"
_LAWD_RE: Final = re.compile(r"[?&]LAWD_CD=(\d{5})(?:&|$)")


def lawd_of_url(url: str | None) -> str | None:
    """실거래 API 원문 주소(키 없음)의 ``LAWD_CD`` 5자리."""
    m = _LAWD_RE.search(url or "")
    return m.group(1) if m else None


def _split(umd_name: str) -> tuple[str, str | None]:
    parts = umd_name.split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return umd_name.strip(), None


@dataclass
class LegalDongIndex:
    """(시군구 코드, 읍면동, 리) → 활성 법정동 코드들."""

    by_key: dict[tuple[str, str, str | None], list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, session: Session, sigungu_codes: Iterable[str]) -> LegalDongIndex:
        codes = sorted({c for c in sigungu_codes if c})
        idx = cls()
        if not codes:
            return idx
        rows = session.execute(
            select(
                LegalDong.code, LegalDong.sigungu_code, LegalDong.eupmyeondong_name, LegalDong.ri_name
            ).where(LegalDong.active.is_(True), LegalDong.sigungu_code.in_(codes))
        )
        acc: dict[tuple[str, str, str | None], list[str]] = defaultdict(list)
        for code, sgg, emd, ri in rows:
            if not emd:
                continue
            acc[(str(sgg), str(emd).strip(), (str(ri).strip() or None) if ri else None)].append(str(code))
        idx.by_key = dict(acc)
        return idx

    def resolve(self, sgg: str | None, umd_name: str | None) -> tuple[str | None, str | None]:
        """(코드, 사유). 코드가 있으면 사유 None."""
        if not sgg:
            return None, REASON_NO_SGG
        if not umd_name or not umd_name.strip():
            return None, REASON_NOT_FOUND
        emd, ri = _split(umd_name)
        found = self.by_key.get((sgg, emd, ri), [])
        if len(found) == 1:
            return found[0], None
        return None, (REASON_AMBIGUOUS if found else REASON_NOT_FOUND)


def repair_legal_dong_codes(session: Session, region_id: int) -> dict[str, int]:
    """법정동 코드가 NULL 인 이 지역 실거래 행을 원문 LAWD_CD + 동 이름으로 보정한다(멱등). commit 은 호출자."""
    out = {"repaired": 0, "unmatched": 0, "ambiguous": 0, "no_sgg": 0}
    rows = list(
        session.execute(
            select(RtmsTrade, RawDocument.url)
            .outerjoin(RawDocument, RawDocument.id == RtmsTrade.raw_document_id)
            .where(RtmsTrade.region_id == region_id, RtmsTrade.legal_dong_code.is_(None))
        )
    )
    if not rows:
        return out
    idx = LegalDongIndex.load(session, {lawd_of_url(url) or "" for _, url in rows})
    for trade, url in rows:
        code, why = idx.resolve(lawd_of_url(url), trade.dong)
        if code is not None:
            trade.legal_dong_code = code
            out["repaired"] += 1
        elif why == REASON_AMBIGUOUS:
            out["ambiguous"] += 1
        elif why == REASON_NO_SGG:
            out["no_sgg"] += 1
        else:
            out["unmatched"] += 1
    session.flush()
    return out


def main(argv: Sequence[str] | None = None) -> int:
    from app.core.db import get_sessionmaker

    p = argparse.ArgumentParser(description="실거래 법정동 코드 보정(D18-3) — NULL 행만")
    p.add_argument("--region", type=int, required=True)
    args = p.parse_args(argv)
    with get_sessionmaker()() as session:
        out = repair_legal_dong_codes(session, args.region)
        session.commit()
    print(out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
