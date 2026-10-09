"""법정동코드 전체자료 (행정표준코드관리시스템 code.go.kr, 키 불필요) → ``LegalDongRecord``.

원천: ``GET https://www.code.go.kr/etc/codeFullDown.do?codeseId=법정동코드`` → ``법정동코드 전체자료.zip``
안의
cp949 탭 구분 txt 1개(``법정동코드\\t법정동명\\t폐지여부``; 폐지여부 = 존재|폐지). 폐지 코드도 행으로 남긴다
(legal_dong.active=false, DECISIONS D2-1).

이름 분해: 시도·시군구·읍면동·리 이름은 상위 코드 행의 전체 이름을 접두어로 떼어 얻는다
("경기도 수원시 장안구 파장동" → 시군구 "수원시 장안구"). 상위 행이 없거나 접두어가 아니면 공백 단위로 나눈다.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

__all__ = [
    "LEGAL_DONG_PARAMS",
    "LEGAL_DONG_URL",
    "LegalDongRecord",
    "ReferenceParseError",
    "decode_korean",
    "parse_legal_dong_text",
    "parse_legal_dong_zip",
]

LEGAL_DONG_URL = "https://www.code.go.kr/etc/codeFullDown.do"
LEGAL_DONG_PARAMS = {"codeseId": "법정동코드"}


class ReferenceParseError(ValueError):
    """참조 파일 형식이 기대와 다르다(다운로드가 HTML 오류 페이지인 경우 등)."""


@dataclass(frozen=True, slots=True)
class LegalDongRecord:
    code: str
    sido_name: str
    sigungu_name: str | None
    eupmyeondong_name: str | None
    ri_name: str | None
    full_name: str
    sigungu_code: str
    active: bool


def decode_korean(data: bytes) -> str:
    """UTF-8(BOM 포함) 우선, 아니면 cp949."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("cp949", errors="replace")


def _rest(full: str, prefix: str | None) -> str | None:
    if prefix and full.startswith(prefix):
        rest = full[len(prefix) :].strip()
        return rest or None
    return None


def parse_legal_dong_text(text: str) -> list[LegalDongRecord]:
    rows: list[tuple[str, str, bool]] = []
    for i, line in enumerate(text.splitlines()):
        cols = [c.strip() for c in line.split("\t")]
        if i == 0 and cols and not cols[0].isdigit():
            continue  # 머리글
        if len(cols) < 2 or len(cols[0]) != 10 or not cols[0].isdigit():
            continue
        active = (cols[2] if len(cols) > 2 else "존재") != "폐지"
        rows.append((cols[0], " ".join(cols[1].split()), active))
    if not rows:
        raise ReferenceParseError("법정동코드 행이 없다")
    names = {code: name for code, name, _ in rows}
    out: list[LegalDongRecord] = []
    for code, full, active in rows:
        tokens = full.split(" ")
        sido_full = names.get(code[:2] + "00000000")
        sido = sido_full if sido_full and full.startswith(sido_full) else tokens[0]
        sgg_level, emd_level, ri_level = code[2:5] != "000", code[5:8] != "000", code[8:] != "00"
        sgg_full = names.get(code[:5] + "00000") if sgg_level else None
        emd_full = names.get(code[:8] + "00") if emd_level else None
        sgg_ok = sgg_full is not None and full.startswith(sgg_full)
        emd_ok = emd_full is not None and full.startswith(emd_full)
        sigungu = _rest(sgg_full, sido) if sgg_ok and sgg_full else None
        eupmyeondong = ri = None
        if emd_level and emd_ok and emd_full:
            eupmyeondong = _rest(emd_full, sgg_full if sgg_ok else sido)
            emd_ok = eupmyeondong is not None
        if ri_level and emd_ok:
            ri = _rest(full, emd_full)
        # 상위 행으로 못 나누면 공백 단위로(뒤에서부터 리 → 읍면동, 나머지가 시군구)
        if (ri_level and ri is None) or (emd_level and not emd_ok) or (sgg_level and not sgg_ok):
            rest = tokens[1:]
            if ri_level and rest:
                popped = rest.pop()
                ri = ri or popped
            if emd_level and rest:
                popped = rest.pop()
                eupmyeondong = eupmyeondong or popped
            if sgg_level and not sgg_ok:
                sigungu = " ".join(rest) or None
        out.append(
            LegalDongRecord(
                code=code,
                sido_name=sido,
                sigungu_name=sigungu,
                eupmyeondong_name=eupmyeondong,
                ri_name=ri,
                full_name=full,
                sigungu_code=code[:5],
                active=active,
            )
        )
    return out


def parse_legal_dong_zip(content: bytes) -> list[LegalDongRecord]:
    """``법정동코드 전체자료.zip`` 바이트 → 레코드. zip 이 아니거나 txt 가 없으면 ReferenceParseError."""
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise ReferenceParseError("zip 이 아니다(오류 페이지일 수 있음)")
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        txts = [i for i in zf.infolist() if not i.is_dir() and i.file_size > 0]
        if not txts:
            raise ReferenceParseError("zip 안에 파일이 없다")
        biggest = max(txts, key=lambda i: i.file_size)
        return parse_legal_dong_text(decode_korean(zf.read(biggest)))
