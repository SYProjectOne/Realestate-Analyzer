"""행안부 행정기관(행정동) 및 관할구역(법정동) 변경내역 = jscode (키 불필요) → 행정동·매핑 레코드.

원천: 행안부 게시판 ``BBSMSTR_000000000052`` 의 "행정기관(행정동) 및 관할구역(법정동) 변경내역(YYYY.M.D.
시행)" 글.
첨부 ``jscodeYYYYMMDD.zip`` 안에 cp949 고정폭 txt 3종(+ 같은 내용의 xlsx):
- ``KIKcd_H.YYYYMMDD``: 행정동코드 시도명 시군구명 읍면동명 생성일자 말소일자
- ``KIKmix.YYYYMMDD``: 행정동코드 시도명 시군구명 읍면동명 법정동코드 동리명 생성일자 말소일자
- ``KIKcd_B.YYYYMMDD``: 법정동(여기서는 쓰지 않음 — 법정동은 code.go.kr 전체자료)

고정폭은 머리글의 열 이름 시작 위치(바이트, cp949)로 자른다. 시행일이 기준일 이후인 글은 고르지 않는다.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.collectors.reference.legal_dong import ReferenceParseError

__all__ = [
    "MOIS_BASE",
    "MOIS_BOARD_PARAMS",
    "MOIS_BOARD_URL",
    "AdminDongRecord",
    "Article",
    "Attachment",
    "JscodeData",
    "parse_attachments",
    "parse_board",
    "parse_jscode_zip",
    "pick_article",
    "pick_jscode",
    "read_fixed_width",
]

MOIS_BASE = "https://www.mois.go.kr"
MOIS_BOARD_URL = f"{MOIS_BASE}/frt/bbs/type001/commonSelectBoardList.do"
MOIS_BOARD_PARAMS = {"bbsId": "BBSMSTR_000000000052"}
MOIS_ARTICLE_URL = f"{MOIS_BASE}/frt/bbs/type001/commonSelectBoardArticle.do"

_TITLE_RE = re.compile(r"행정기관\(행정동\)\s*및\s*관할구역\(법정동\)\s*변경내역")
_EFFECTIVE_RE = re.compile(r"(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*시행")
_NTT_RE = re.compile(r"nttId=(\d+)")
_JSCODE_RE = re.compile(r"^jscode(\d{8})\.zip(?:\s|$)")


@dataclass(frozen=True, slots=True)
class Article:
    ntt_id: str
    title: str
    effective: date | None

    @property
    def url(self) -> str:
        return f"{MOIS_ARTICLE_URL}?bbsId={MOIS_BOARD_PARAMS['bbsId']}&nttId={self.ntt_id}"


@dataclass(frozen=True, slots=True)
class Attachment:
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class AdminDongRecord:
    code: str
    full_name: str
    name: str
    sigungu_code: str
    active: bool


@dataclass(frozen=True, slots=True)
class JscodeData:
    source_date: str | None  # 파일 이름의 시행일(YYYY-MM-DD)
    admin_dongs: list[AdminDongRecord]
    mappings: list[tuple[str, str]]  # (admin_code, legal_code), 유일


def parse_board(html: str) -> list[Article]:
    soup = BeautifulSoup(html, "lxml")
    seen: dict[str, Article] = {}
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if "commonSelectBoardArticle" not in href or "BBSMSTR_000000000052" not in href:
            continue
        title = " ".join(a.get_text(" ").split())
        m = _NTT_RE.search(href)
        if not m or not _TITLE_RE.search(title):
            continue
        eff = _EFFECTIVE_RE.search(title)
        effective = date(int(eff.group(1)), int(eff.group(2)), int(eff.group(3))) if eff else None
        seen.setdefault(m.group(1), Article(m.group(1), title, effective))
    return list(seen.values())


def pick_article(articles: list[Article], today: date) -> Article | None:
    """시행일이 기준일 이하인 글 중 가장 최근. 시행일을 못 읽은 글은 마지막 수단."""
    dated = [a for a in articles if a.effective is not None and a.effective <= today]
    if dated:
        return max(dated, key=lambda a: (a.effective or date.min, int(a.ntt_id)))
    undated = [a for a in articles if a.effective is None]
    return max(undated, key=lambda a: int(a.ntt_id)) if undated else None


def parse_attachments(html: str, base: str = MOIS_BASE) -> list[Attachment]:
    soup = BeautifulSoup(html, "lxml")
    out: list[Attachment] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if "FileDown.do" not in href:
            continue
        name = " ".join(a.get_text(" ").split())
        if name:
            out.append(Attachment(name, urljoin(base, href)))
    return out


def pick_jscode(attachments: list[Attachment]) -> Attachment | None:
    """``jscodeYYYYMMDD.zip``(말소코드포함 판이 아닌 것)."""
    for att in attachments:
        if _JSCODE_RE.match(att.name.strip()):
            return att
    return None


def read_fixed_width(data: bytes, encoding: str = "cp949") -> list[dict[str, str]]:
    """머리글 열 이름의 바이트 위치로 고정폭 행을 자른다."""
    lines = data.split(b"\n")
    if not lines:
        return []
    header = lines[0].rstrip(b"\r")
    starts: list[tuple[int, str]] = []
    pos = 0
    for token in header.split(b" "):
        if token:
            starts.append((pos, token.decode(encoding)))
        pos += len(token) + 1
    if len(starts) < 2:
        raise ReferenceParseError("고정폭 머리글을 읽지 못했다")
    out: list[dict[str, str]] = []
    for raw in lines[1:]:
        line = raw.rstrip(b"\r")
        if not line.strip():
            continue
        row: dict[str, str] = {}
        for idx, (start, name) in enumerate(starts):
            end = starts[idx + 1][0] if idx + 1 < len(starts) else len(line)
            row[name] = line[start:end].decode(encoding, errors="replace").strip()
        out.append(row)
    return out


def _member(zf: zipfile.ZipFile, prefix: str) -> bytes | None:
    for info in zf.infolist():
        base = info.filename.rsplit("/", 1)[-1]
        if base.startswith(prefix) and not base.lower().endswith((".xlsx", ".xls")) and not info.is_dir():
            return zf.read(info)
    return None


def parse_jscode_zip(content: bytes) -> JscodeData:
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise ReferenceParseError("jscode zip 이 아니다")
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        h = _member(zf, "KIKcd_H.")
        mix = _member(zf, "KIKmix.")
        names = [i.filename for i in zf.infolist()]
    if h is None or mix is None:
        raise ReferenceParseError("KIKcd_H·KIKmix 파일이 없다")
    source_date = None
    for n in names:
        m = re.search(r"(\d{4})(\d{2})(\d{2})", n)
        if m:
            source_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            break
    admins: list[AdminDongRecord] = []
    for row in read_fixed_width(h):
        code = row.get("행정동코드", "")
        if len(code) != 10 or not code.isdigit():
            continue
        parts = [row.get("시도명", ""), row.get("시군구명", ""), row.get("읍면동명", "")]
        parts = [p for p in parts if p]
        if not parts:
            continue
        admins.append(
            AdminDongRecord(
                code=code,
                full_name=" ".join(parts),
                name=parts[-1],
                sigungu_code=code[:5],
                active=not row.get("말소일자"),
            )
        )
    pairs: dict[tuple[str, str], None] = {}
    for row in read_fixed_width(mix):
        a, b = row.get("행정동코드", ""), row.get("법정동코드", "")
        if len(a) == 10 and len(b) == 10 and a.isdigit() and b.isdigit() and not row.get("말소일자"):
            pairs[(a, b)] = None
    if not admins or not pairs:
        raise ReferenceParseError("행정동·매핑 행이 없다")
    return JscodeData(source_date, admins, list(pairs))
