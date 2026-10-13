"""단지 주소 → 법정동 코드 (R6-DONG, DECISIONS D2-6·D18-7·D21-6).

문자열 파싱 규칙이다(판단 아님 — 규칙 3). 지역·지명은 코드에 없고 전부 참조 표(legal_dong·admin_dong·admin_legal_map)에서 온다
(규칙 15). 참조 표의 역사 표현은 ``legal_dong.active`` 하나뿐이다(법정동코드 전체자료의 '폐지여부'; 생성·폐지 일자·이전 이름 열은
없다). 그래서 옛 구 → 새 구는 이름 겹침으로 찾는다(아래 ``DongRef.successors``).

주소를 토큰으로 나누고 왼쪽부터 읽는다. 시도 토큰('인천광역시', '경기도')이 나오면 새 구간이 시작된다(여러 시도에 걸친 주소 —
'인천광역시 계양구 귤현동, …, 경기도 부천시 대장동, 서울특별시 강서구 오곡동'). 읍면동 토큰마다 그 구간의 시도·시군구 토큰으로
후보를 좁힌다:

1. 법정동 이름: 활성 행 중 같은 이름(리가 있으면 리까지) → 구간 시도 → 구간 시군구 이름(이름 조각이 가장 많이 맞는 것) → 시군구가
   폐지된 옛 구면 그 후계 구(``successors``) → 여럿이면 지역 법정동(scope)으로 → 하나일 때만.
2. 행정동 이름('간석1동'): 행정동 → 매핑된 활성 법정동이 하나면 그것. 여럿이면 번지 주소('311-1번지')이고 행정동 이름에서 숫자를 뗀
   이름('간석동')의 법정동이 매핑 안에 하나일 때만(지번은 법정동 기준). 아니면 모호.
3. 여러 동을 나열한 주소: 지역 안 첫 동. 지역 안 동이 없으면 처음 정해진 동(지역 밖 → 범위 경계).
4. 읍면동·행정동 토큰이 하나도 없으면: 구간에 시군구(또는 옛 구의 후계 구)가 있고 지구 이름 토큰('인천검암역세권', '…지구',
   '…신도시')에 그 구 법정동 이름(접미사 뗀 2자 이상)이 정확히 하나 들어 있을 때만 그 법정동(rule 'district'). 아니면 None.

못 정하면 None — 호출자가 '범위 경계'로 둔다(D2-6).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AdminDong, AdminLegalMap, LegalDong
from app.normalize.region_resolve import AdminRow, LegalRow, normalize_name

__all__ = ["DongMatch", "DongRef", "match_address", "split_address"]

_SPLIT = re.compile(r"[\s(),\[\]/·ㆍ・]+")
_SIDO_TAILS = ("특별자치시", "특별자치도", "특별시", "광역시", "직할시", "도")
_LOT = re.compile(r"^산?\d+(?:-\d+)?(?:번지)?")
_ADMIN_NUM = re.compile(r"^(.+?)제?[\d.,·]+(동|가)$")
_DISTRICT_MARKS = ("지구", "역세권", "신도시", "국제도시", "택지", "구역", "단지")


def split_address(address: str) -> list[str]:
    return [t for t in _SPLIT.split(address) if t]


def _legal_row(r: LegalDong) -> LegalRow:
    return LegalRow(
        code=r.code,
        sido_name=r.sido_name,
        sigungu_name=r.sigungu_name,
        eupmyeondong_name=r.eupmyeondong_name,
        ri_name=r.ri_name,
        full_name=r.full_name,
        sigungu_code=r.sigungu_code,
        active=bool(r.active),
    )


@dataclass(frozen=True)
class DongMatch:
    code: str | None
    candidates: bool  # 주소에 참조 표의 활성 읍면동·행정동 이름이 있었다(못 정했으면 '모호')
    rule: str  # dong | successor | admin | district | none


class DongRef:
    """참조 표 조회(세션 범위 캐시). 지역 단지 전체를 다시 맞출 때 한 개를 같이 쓴다."""

    def __init__(self, session: Session) -> None:
        self._s = session
        self._named: dict[str, list[LegalRow]] = {}
        self._admin_named: dict[str, list[AdminRow]] = {}
        self._areas: list[LegalRow] | None = None
        self._sido_dongs: dict[str, list[LegalRow]] = {}
        self._succ: dict[str, frozenset[str]] = {}

    def legal_named(self, names: Iterable[str]) -> list[LegalRow]:
        asked = set(names)
        want = sorted(asked - set(self._named))
        if want:
            for n in want:
                self._named[n] = []
            for r in self._s.scalars(select(LegalDong).where(LegalDong.eupmyeondong_name.in_(want))):
                self._named[str(r.eupmyeondong_name)].append(_legal_row(r))
        return [r for n in sorted(asked) for r in self._named.get(n, [])]

    def admin_named(self, names: Iterable[str]) -> list[AdminRow]:
        """읍면동 단위 행정동만(시도·시군구 단위 행 — 코드 끝 5자리 00000 — 은 이름이 시도·시군구라 뺀다)."""
        asked = set(names)
        want = sorted(asked - set(self._admin_named))
        if want:
            for n in want:
                self._admin_named[n] = []
            for a in self._s.scalars(
                select(AdminDong).where(AdminDong.name.in_(want), AdminDong.active.is_(True))
            ):
                if a.code[5:] == "00000":
                    continue
                self._admin_named[a.name].append(
                    AdminRow(code=a.code, full_name=a.full_name, name=a.name, sigungu_code=a.sigungu_code)
                )
        return [a for n in sorted(asked) for a in self._admin_named.get(n, [])]

    def admin_legal(self, admin_code: str) -> list[LegalRow]:
        codes = list(
            self._s.scalars(select(AdminLegalMap.legal_code).where(AdminLegalMap.admin_code == admin_code))
        )
        if not codes:
            return []
        rows = self._s.scalars(
            select(LegalDong).where(LegalDong.code.in_(sorted(set(codes))), LegalDong.active.is_(True))
        )
        return [_legal_row(r) for r in rows if r.eupmyeondong_name]

    def areas(self) -> list[LegalRow]:
        """시도·시군구 단위 행(읍면동 이름 없음) — 활성·폐지 모두."""
        if self._areas is None:
            self._areas = [
                _legal_row(r)
                for r in self._s.scalars(
                    select(LegalDong).where(LegalDong.eupmyeondong_name.is_(None)).order_by(LegalDong.code)
                )
            ]
        return self._areas

    def sido_dongs(self, sido_code: str) -> list[LegalRow]:
        """그 시도의 읍면동 단위 행(리 제외) — 활성·폐지 모두."""
        if sido_code not in self._sido_dongs:
            self._sido_dongs[sido_code] = [
                _legal_row(r)
                for r in self._s.scalars(
                    select(LegalDong).where(
                        LegalDong.code.like(f"{sido_code}%"),
                        LegalDong.eupmyeondong_name.is_not(None),
                        LegalDong.ri_name.is_(None),
                    )
                )
            ]
        return self._sido_dongs[sido_code]

    def has_active(self, sigungu_code: str) -> bool:
        """그 시군구에 활성 읍면동이 있다(= 폐지된 시군구가 아니다)."""
        return any(r.active and r.sigungu_code == sigungu_code for r in self.sido_dongs(sigungu_code[:2]))

    def successors(self, old_sigungu_code: str) -> frozenset[str]:
        """폐지된 시군구 G 의 후계 시군구(같은 시도의 활성 시군구 S). 참조 표에 이전 관계 열이 없어 이름 겹침으로 정한다:
        k = |S 활성 읍면동 이름 ∩ G 폐지 읍면동 이름| 이 S 의 과반(S 가 대부분 G 에서 왔다 — 분구·개칭) 이거나 G 의 과반(G 가
        대부분 S 로 갔다 — 통합)이면 후계. 같은 이름 동 하나가 우연히 겹친 구(옛 서구 오류동 ↔ 계양구 오류동)는 후계가 아니다."""
        if old_sigungu_code in self._succ:
            return self._succ[old_sigungu_code]
        rows = self.sido_dongs(old_sigungu_code[:2])
        active: dict[str, set[str]] = defaultdict(set)
        old: set[str] = set()
        for r in rows:
            name = str(r.eupmyeondong_name)
            if r.sigungu_code == old_sigungu_code:
                if not r.active:
                    old.add(name)
            elif r.active:
                active[r.sigungu_code].add(name)
        out = frozenset(
            sgg
            for sgg, names in active.items()
            if (k := len(names & old)) and (2 * k > len(names) or 2 * k > len(old))
        )
        self._succ[old_sigungu_code] = out
        return out


@dataclass
class _Segment:
    sido: str | None  # 정규화한 시도 이름('인천')
    tokens: list[str]


def _norm_sido(name: str) -> str:
    return normalize_name(name, sido=True)


def _context_filter(
    rows: Sequence[LegalRow],
    sgg_of: dict[str, LegalRow],
    seg: _Segment,
    ref: DongRef,
    *,
    olds: Sequence[LegalRow],
) -> tuple[list[LegalRow], str]:
    """구간 시군구 토큰으로 좁힌다. 활성 시군구 이름 조각이 가장 많이 맞는 행 → 아니면 옛 구의 후계 구 → 아니면 그대로."""
    named = set(seg.tokens)

    def score(r: LegalRow) -> int:
        area = sgg_of.get(r.sigungu_code)
        name = (area.sigungu_name if area else None) or r.sigungu_name or ""
        return sum(p in named for p in name.split())

    scored = [(score(r), r) for r in rows]
    best = max((sc for sc, _ in scored), default=0)
    if best > 0:
        return [r for sc, r in scored if sc == best], "dong"
    succ: set[str] = set()
    for o in olds:
        succ |= ref.successors(o.sigungu_code)
    sub = [r for r in rows if r.sigungu_code in succ]
    if sub:
        return sub, "successor"
    return list(rows), "dong"


def _pick(rows: Sequence[LegalRow], scope: Collection[str] | None) -> str | None:
    codes = sorted({r.code for r in rows})
    if len(codes) > 1 and scope:
        codes = [c for c in codes if c in scope] or codes
    return codes[0] if len(codes) == 1 else None


def match_address(address: str, ref: DongRef, *, scope: Collection[str] | None = None) -> DongMatch:
    """주소 → 법정동(모듈 docstring 규칙). scope = 지역 법정동 코드."""
    toks = split_address(address)
    if not toks:
        return DongMatch(None, False, "none")
    areas = ref.areas()
    sido_rows = [a for a in areas if a.sigungu_name is None]
    sido_full = {a.sido_name for a in sido_rows}
    sido_norm = {_norm_sido(a.sido_name) for a in sido_rows}
    sgg_rows = [a for a in areas if a.sigungu_name]
    sgg_of = {a.sigungu_code: a for a in sgg_rows if a.active}
    sido_of_code = {a.code[:2]: _norm_sido(a.sido_name) for a in sido_rows}

    def is_sido(t: str) -> bool:
        return t in sido_full or (
            t.endswith(_SIDO_TAILS) and _norm_sido(t) in sido_norm and _norm_sido(t) != t
        )

    inactive = [r for r in ref.legal_named(toks) if not r.active]

    def olds_named(seg: _Segment) -> list[LegalRow]:
        """구간에 이름이 나온 폐지 시군구. 시군구 단위 행이 없으면(작은 참조 표) 같은 이름 폐지 읍면동 행의 시군구로."""
        named = set(seg.tokens)

        def hit(r: LegalRow) -> bool:
            return (
                bool(r.sigungu_name)
                and (seg.sido is None or _norm_sido(r.sido_name) == seg.sido)
                and all(p in named for p in (r.sigungu_name or "").split())
            )

        out = {a.sigungu_code: a for a in sgg_rows if not a.active and hit(a)}
        for r in inactive:
            if (
                r.sigungu_code not in out
                and r.sigungu_code not in sgg_of
                and hit(r)
                and not ref.has_active(r.sigungu_code)
            ):
                out[r.sigungu_code] = r
        return list(out.values())

    legal = [r for r in ref.legal_named(toks) if r.active]
    legal_names = {str(r.eupmyeondong_name) for r in legal}
    admin = ref.admin_named(t for t in toks if t not in legal_names)
    admin_names = {a.name for a in admin}
    candidates = bool(legal_names & set(toks)) or bool(admin_names)

    seg = _Segment(None, [])
    segments: list[_Segment] = [seg]
    found: list[tuple[str, str]] = []  # (code, rule) 주소 순서
    for i, t in enumerate(toks):
        if is_sido(t):
            seg = _Segment(_norm_sido(t), [t])
            segments.append(seg)
            continue
        rest = set(toks[i + 1 :])
        if t in legal_names:
            rows = [r for r in legal if r.eupmyeondong_name == t]
            ri = [r for r in rows if r.ri_name and r.ri_name in rest]
            rows = ri or [r for r in rows if not r.ri_name]
            if seg.sido is not None:
                rows = [r for r in rows if _norm_sido(r.sido_name) == seg.sido]
            if rows:
                rows, rule = _context_filter(rows, sgg_of, seg, ref, olds=olds_named(seg))
                code = _pick(rows, scope)
                if code is not None:
                    found.append((code, rule))
        elif t in admin_names:
            code = _admin_code(
                t, toks[i + 1 : i + 2], admin, sgg_of, sido_of_code, seg, ref, olds_named(seg), scope
            )
            if code is not None:
                found.append((code, "admin"))
        seg.tokens.append(t)
    if found:
        inside = [f for f in found if scope and f[0] in scope]
        code, rule = (inside or found)[0]
        return DongMatch(code, True, rule)
    if candidates:
        return DongMatch(None, True, "none")
    for s in segments:
        code = _district_code(s, sgg_of, ref, olds_named(s))
        if code is not None:
            return DongMatch(code, False, "district")
    return DongMatch(None, False, "none")


def _admin_code(
    name: str,
    after: Sequence[str],
    admin: Sequence[AdminRow],
    sgg_of: dict[str, LegalRow],
    sido_of_code: dict[str, str],
    seg: _Segment,
    ref: DongRef,
    olds: Sequence[LegalRow],
    scope: Collection[str] | None,
) -> str | None:
    rows = [a for a in admin if a.name == name]
    if seg.sido is not None:
        rows = [a for a in rows if sido_of_code.get(a.code[:2]) == seg.sido]
    if not rows:
        return None
    named = set(seg.tokens)

    def score(a: AdminRow) -> int:
        area = sgg_of.get(a.sigungu_code)
        return sum(p in named for p in ((area.sigungu_name if area else None) or "").split())

    best = max(score(a) for a in rows)
    if best > 0:
        rows = [a for a in rows if score(a) == best]
    else:
        succ: set[str] = set()
        for o in olds:
            succ |= ref.successors(o.sigungu_code)
        rows = [a for a in rows if a.sigungu_code in succ] or rows
    if len({a.code for a in rows}) != 1:
        return None
    legal = ref.admin_legal(rows[0].code)
    code = _pick(legal, None)
    if code is not None:
        return code
    m = _ADMIN_NUM.match(name)
    if m is None or not after or not _LOT.match(after[0]):
        return None
    base = m.group(1) + m.group(2)
    same = [r for r in legal if r.eupmyeondong_name == base and not r.ri_name]
    return _pick(same, scope) if len(same) == 1 else None


def _district_code(
    seg: _Segment, sgg_of: dict[str, LegalRow], ref: DongRef, olds: Sequence[LegalRow]
) -> str | None:
    named = set(seg.tokens)
    sggs = {
        code
        for code, a in sgg_of.items()
        if a.sigungu_name
        and (seg.sido is None or _norm_sido(a.sido_name) == seg.sido)
        and all(p in named for p in a.sigungu_name.split())
    }
    for o in olds:
        sggs |= ref.successors(o.sigungu_code)
    if not sggs:
        return None
    area_names = {p for code in sggs for p in (sgg_of[code].sigungu_name or "").split() if code in sgg_of}
    area_names |= {p for o in olds for p in (o.sigungu_name or "").split()}
    words = [t for t in seg.tokens if t not in area_names and any(m in t for m in _DISTRICT_MARKS)]
    if not words:
        return None
    hits: set[str] = set()
    for sgg in sorted(sggs):
        for r in ref.sido_dongs(sgg[:2]):
            if r.sigungu_code != sgg or not r.active:
                continue
            stem = normalize_name(str(r.eupmyeondong_name))
            if len(stem) >= 2 and any(stem in w for w in words):
                hits.add(r.code)
    return hits.pop() if len(hits) == 1 else None
