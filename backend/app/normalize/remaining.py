"""잔여 공고 이력 (R3 M5) — 청약홈 무순위·임의공급·잔여세대(재공급) 공고 → ``remaining_event`` (C8 타임라인).

원천(수집기가 이미 받은 원문만 읽는다 — 네트워크 없음)
- 공식 API: ``getRemndrLttotPblancDetail``(HOUSE_SECD 04 무순위·06 불법행위 재공급) · ``getOPTLttotPblancDetail``
  (임의공급) 1건 조회 원문 → 공고번호·이름·공급위치·모집공고일·청약접수 기간. 주택형별(``…Mdl``) → 타입별 세대수.
  경쟁률(``…Cmpet``, 서비스 미신청이면 401) → 결과 문구.
- 웹(폴백): 잔여세대 상세 팝업(``selectAPTRemndrLttotPblancDetailView``) → 같은 항목, 공급 구분은 잔여세대 목록
  행의 ``data-hsecd``. 경쟁률 팝업(``selectAPTRemndrCompetitionPopup``) → 결과 문구(주택형·공급·접수·경쟁률·청약결과).
  같은 공고를 API 와 웹이 다 주면 API 를 쓴다.

kind: 04·06 → '무순위', 11(임의공급 엔드포인트 포함) → '임의'. 공급 구분을 모르면 만들지 않고 '확인 불가(공급 구분
없음)'로 기록한다(추측하지 않는다).

단지: 잔여 공고는 자기 주택관리번호를 가져 수집 정규화(store)가 따로 단지 행을 만든다. 원래 단지 = 같은 지역에서
정규화한 단지명(``benchmark.normalize_apt_name`` — 잔여 공고 회차 괄호만 제거, 차수·블록 유지)과 법정동이 같은
단지 중 잔여 공고가 아닌 것 — 하나일 때만. 없으면 이름 끝 공급 회차 괄호('(23차)')까지 뗀 키(``remainder_name_key``)로
한 번 더 찾는다(역시 하나일 때만). 없거나 여럿이면 같은 이름·법정동 잔여 공고들의 단지 행 중 가장 먼저 생긴 것에 묶고(회차가 한 타임라인에
모이게) ``unmatched`` 에 사유를 남긴다. 문자열 처리뿐이다(판단 아님).

멱등: (공고번호, kind) 하나에 행 하나 — 다시 돌리면 갱신. 새 행 = change_event(remaining_event, critical, 재판정),
단 지역 최초 적재(region.status ≠ ready = bootstrap — 전체 판정이 어차피 돈다)이거나 접수가 이미 끝난 과거 공고
(청약접수 마지막 날 < 기준일, 접수일이 없으면 모집공고일 < 기준일 − 30일)의 새 행은 info(재판정 없음 — 배포 후 첫
수집 때 과거 잔여 공고 이벤트 폭주 방지). 값 변경 = notice(결과 문구만 바뀌면 info).
원문은 URL 마다 최신 1건만 읽고, 주택형·경쟁률 원문은 URL 일괄 조회로 한 번에 찾는다(N+1 없음). 수치·날짜(notice_date·apply_dates·units)는 field_provenance(확인됨).
"""

# ruff: noqa: E501  (한국어 docstring·발췌 문구)

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, Tag
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.applyhome import api as ah_api
from app.collectors.applyhome import parse as ah_parse
from app.collectors.applyhome import site as ah_site
from app.core.contracts_gen import ProvenanceRow
from app.models import ChangeEvent, Complex, RawDocument, Region, RemainingEvent
from app.normalize._text import normalize_type_code
from app.normalize.benchmark import (
    LegalIndex,
    api_rows,
    iso_day,
    json_object_at,
    latest_by_urls,
    latest_ok_docs,
    normalize_apt_name,
    prov_row,
    read_raw_row,
)
from app.normalize.changes import fmt_value, make_event
from app.normalize.provenance import upsert_provenance

__all__ = ["KIND_BY_SECD", "RemainingSync", "sync_remaining_events"]

KIND_BY_SECD: Final = {"04": "무순위", "06": "무순위", "11": "임의"}
_API_DETAIL: Final[dict[str, ah_api.ApiKind]] = {
    "getRemndrLttotPblancDetail": "remndr",
    "getOPTLttotPblancDetail": "opt",
}
_WEB_DETAIL: Final = "selectAPTRemndrLttotPblancDetailView"
_WEB_LIST: Final = "selectAPTRemndrLttotPblancListView"
_DATE_RE: Final = re.compile(r"\d{4}-\d{2}-\d{2}")
_LONG_RE: Final = re.compile(r"^0?\d{2,3}\.\d{4}[A-Z]?\d?$")
NO_KIND: Final = "확인 불가(공급 구분 없음)"
NO_ORIGINAL: Final = "원래 단지 없음(잔여 공고 단지 행에 묶음)"
AMBIGUOUS: Final = "확인 불가(매칭 모호 — 잔여 공고 단지 행에 묶음)"


@dataclass
class _Notice:
    hm: str
    pb: str
    name: str
    address: str | None
    kind: str | None
    notice_date: str | None
    apply_dates: list[str]
    doc: RawDocument
    text: str
    api: bool
    units: dict[str, int] = field(default_factory=dict)
    units_doc: RawDocument | None = None
    units_excerpt: str | None = None
    result_text: str | None = None
    ratio_text: str | None = None


@dataclass
class RemainingSync:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    unmatched: list[dict[str, str]] = field(default_factory=list)  # [{notice_no, name, reason}]
    events: list[ChangeEvent] = field(default_factory=list)

    def stats(self) -> dict[str, Any]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "unmatched_n": len(self.unmatched),
            "unmatched": self.unmatched[:50],
        }


# ---------------------------------------------------------------- 원문 읽기


_docs = latest_ok_docs  # URL 마다 최신 원문만(같은 URL 을 다시 받은 옛 원문은 읽지 않는다)


def _dates(*values: object) -> list[str]:
    out: list[str] = []
    for v in values:
        d = iso_day(v)
        if d and d not in out:
            out.append(d)
    return out


def _api_notices(session: Session, region_id: int) -> dict[tuple[str, str], _Notice]:
    out: dict[tuple[str, str], _Notice] = {}
    kinds: dict[tuple[str, str], ah_api.ApiKind] = {}
    for path, kind in _API_DETAIL.items():
        for doc in _docs(session, region_id, "applyhome_detail", path):
            text = read_raw_row(doc)
            if text is None:
                continue
            for d in api_rows(text):
                hm, pb = str(d.get("HOUSE_MANAGE_NO") or "").strip(), str(d.get("PBLANC_NO") or "").strip()
                if not hm or not pb:
                    continue
                secd = str(d.get("HOUSE_SECD") or "").strip()
                addr = d.get("HSSPLY_ADRES")
                out[(hm, pb)] = _Notice(
                    hm=hm,
                    pb=pb,
                    name=str(d.get("HOUSE_NM") or "").strip(),
                    address=str(addr) if addr else None,
                    kind="임의" if kind == "opt" else KIND_BY_SECD.get(secd),
                    notice_date=iso_day(d.get("RCRIT_PBLANC_DE")),
                    apply_dates=_dates(d.get("SUBSCRPT_RCEPT_BGNDE"), d.get("SUBSCRPT_RCEPT_ENDDE")),
                    doc=doc,
                    text=text,
                    api=True,
                )
                kinds[(hm, pb)] = kind
    urls = latest_by_urls(
        session,
        [
            ah_api.doc_url(getattr(ah_api.ENDPOINTS[k], part), ah_api.item_params(hm, pb))
            for (hm, pb), k in kinds.items()
            for part in ("model", "competition")
        ],
    )
    for key, k in kinds.items():
        _api_units(urls, out[key], k)
        _api_result(urls, out[key], k)
    return out


def _api_units(urls: dict[str, RawDocument], n: _Notice, kind: ah_api.ApiKind) -> None:
    doc = urls.get(ah_api.doc_url(ah_api.ENDPOINTS[kind].model, ah_api.item_params(n.hm, n.pb)))
    text = read_raw_row(doc) if doc is not None else None
    if doc is None or text is None:
        return
    units: dict[str, int] = {}
    for d in api_rows(text):
        ty = str(d.get("HOUSE_TY") or "").strip()
        gen, spc = d.get("SUPLY_HSHLDCO"), d.get("SPSPLY_HSHLDCO")
        if not ty or not isinstance(gen, int) or isinstance(gen, bool):
            continue
        units[normalize_type_code(ty)] = gen + (
            spc if isinstance(spc, int) and not isinstance(spc, bool) else 0
        )
    if units:
        n.units, n.units_doc = units, doc
        n.units_excerpt = "; ".join(f"{k} {v}세대" for k, v in units.items())


def _api_result(urls: dict[str, RawDocument], n: _Notice, kind: ah_api.ApiKind) -> None:
    doc = urls.get(ah_api.doc_url(ah_api.ENDPOINTS[kind].competition, ah_api.item_params(n.hm, n.pb)))
    text = read_raw_row(doc) if doc is not None else None
    rows = api_rows(text) if text else []
    parts, ratios = [], []
    for d in rows:
        ty = str(d.get("HOUSE_TY") or "").strip()
        rate = str(d.get("CMPET_RATE") or "").strip()
        parts.append(f"{ty} 공급 {d.get('SUPLY_HSHLDCO')} · 접수 {d.get('REQ_CNT')} · 경쟁률 {rate}")
        ratios.append(f"{ty} {rate}")
    if parts:
        n.result_text, n.ratio_text = "; ".join(parts), "; ".join(ratios)


def _cell(node: Tag) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


def _query_no(url: str) -> tuple[str, str] | None:
    q = parse_qs(urlsplit(url).query)
    hm = (q.get("houseManageNo") or [""])[0]
    pb = (q.get("pblancNo") or [hm])[0]
    return (hm, pb) if hm.isdigit() else None


def _web_kinds(session: Session, region_id: int) -> dict[str, str]:
    """잔여세대 목록 원문의 행 → {주택관리번호: 공급 구분 코드}."""
    out: dict[str, str] = {}
    for doc in _docs(session, region_id, "applyhome_list", _WEB_LIST):
        html = read_raw_row(doc)
        if html is None:
            continue
        for row in ah_parse.parse_list(html, "remndr").rows:
            if row.house_secd:
                out[row.house_manage_no] = row.house_secd
    return out


def _web_notices(session: Session, region_id: int) -> dict[tuple[str, str], _Notice]:
    kinds = _web_kinds(session, region_id)
    out: dict[tuple[str, str], _Notice] = {}
    for doc in _docs(session, region_id, "applyhome_detail", _WEB_DETAIL):
        html = read_raw_row(doc)
        key = _query_no(doc.url)
        if html is None or key is None:
            continue
        soup = BeautifulSoup(html, "lxml")
        th = soup.select_one("thead th")
        name = _cell(th) if isinstance(th, Tag) else ""
        notice_date: str | None = None
        applies: list[str] = []
        units: dict[str, int] = {}
        for tr in soup.find_all("tr"):
            cells = [c for c in tr.find_all(["th", "td"], recursive=False) if isinstance(c, Tag)]
            if len(cells) < 2:
                continue
            head, value = _cell(cells[0]), _cell(cells[1])
            if head == "모집공고일":
                notice_date = iso_day(value)
            elif head == "청약접수":
                applies = list(dict.fromkeys(_DATE_RE.findall(value)))
            elif _LONG_RE.match(head) and value.replace(",", "").isdigit():
                units[normalize_type_code(head)] = int(value.replace(",", ""))
        n = _Notice(
            hm=key[0],
            pb=key[1],
            name=name,
            address=ah_parse.detail_supply_address(html),
            kind=KIND_BY_SECD.get(kinds.get(key[0], "")),
            notice_date=notice_date,
            apply_dates=applies,
            doc=doc,
            text=html,
            api=False,
        )
        if units:
            n.units, n.units_doc = units, doc
            n.units_excerpt = "; ".join(f"{k} {v}세대" for k, v in units.items())
        out[key] = n
    return out


def _web_result(urls: dict[str, RawDocument], n: _Notice) -> None:
    doc = urls.get(ah_site.competition_url("remndr", n.hm, n.pb))
    html = read_raw_row(doc) if doc is not None else None
    if html is None:
        return
    parts, ratios = [], []
    for tr in BeautifulSoup(html, "lxml").select("tbody tr"):
        cells = [_cell(td) for td in tr.find_all("td", recursive=False)]
        if len(cells) < 4 or not _LONG_RE.match(cells[0]):
            continue
        tail = f" · {cells[4]}" if len(cells) > 4 and cells[4] else ""
        parts.append(f"{cells[0]} 공급 {cells[1]} · 접수 {cells[2]} · 경쟁률 {cells[3]}{tail}")
        ratios.append(f"{cells[0]} {cells[3]}")
    if parts:
        n.result_text, n.ratio_text = "; ".join(parts), "; ".join(ratios)


# ---------------------------------------------------------------- 단지 묶기

_TRAILING_ROUND_RE: Final = re.compile(r"\(\s*\d+\s*회차\s*\)\s*$")


def remainder_name_key(name: str) -> str:
    """잔여 공고 이름 키: 이름 끝의 공급 **회차** 괄호('… (3회차)')만 뗀 정규화 이름. 잔여 공고(공식 API·웹 잔여세대
    화면으로 들어온 것)끼리 묶거나, 정확한 이름으로 원래 단지를 못 찾았을 때만 쓴다(문자열 처리).
    차수 '(N차)'는 어떤 괄호에서도 떼지 않는다(D11-4·M-8: '(2차)' 잔여 이벤트가 1차 C8 에 붙던 문제) — 원래 단지를 못
    찾으면 ``unmatched`` 에 사유를 남긴다. 단지 행 병합(store, D10-4)·벤치마크 매칭(D10-5)은 이 키를 쓰지 않는다."""
    return normalize_apt_name(_TRAILING_ROUND_RE.sub("", name))


@dataclass
class _Anchor:
    complex_id: int | None
    reason: str | None


def _anchors(session: Session, region: Region, notices: list[_Notice]) -> dict[tuple[str, str], _Anchor]:
    scope = set(region.legal_dong_codes or [])
    remaining_hms = {n.hm for n in notices}
    complexes = list(
        session.scalars(select(Complex).where(Complex.region_id == region.id).order_by(Complex.id))
    )
    self_rows = {c.applyhome_id: c for c in complexes if c.applyhome_id in remaining_hms}
    originals = [c for c in complexes if c.applyhome_id not in remaining_hms]
    index = LegalIndex(session, (n.address for n in notices))
    keyed: dict[tuple[str, str], tuple[str, str, str | None]] = {}
    groups: dict[tuple[str, str | None], list[int]] = {}
    for n in notices:
        own = self_rows.get(n.hm)
        code = own.legal_dong_code if own is not None and own.legal_dong_code else None
        code = code or index.code(n.address, scope)
        strict, loose = normalize_apt_name(n.name), remainder_name_key(n.name)
        keyed[(n.hm, n.pb)] = (strict, loose, code)
        if own is not None:
            groups.setdefault((loose, code), []).append(own.id)
    out: dict[tuple[str, str], _Anchor] = {}
    for n in notices:
        strict, name, code = keyed[(n.hm, n.pb)]
        here = [c for c in originals if c.legal_dong_code == code] if code and name else []
        hits = [c for c in here if normalize_apt_name(c.name) == strict]
        if (
            not hits
        ):  # 잔여 공고 이름 끝 회차 '(23차)' 를 뗀 키로 한 번 더(원래 단지가 정확히 1개일 때만 묶는다)
            hits = [c for c in here if remainder_name_key(c.name) == name]
        if len(hits) == 1:
            out[(n.hm, n.pb)] = _Anchor(hits[0].id, None)
            continue
        members = groups.get((name, code)) or []
        out[(n.hm, n.pb)] = _Anchor(min(members) if members else None, AMBIGUOUS if hits else NO_ORIGINAL)
    return out


# ---------------------------------------------------------------- 저장


def _prov(session: Session, ev: RemainingEvent, n: _Notice) -> None:
    key = f"{n.hm}:{n.kind}:{n.pb}"
    span = json_object_at(n.text, "HOUSE_MANAGE_NO", n.hm) if n.api else None
    ex = (
        n.text[span[0] : span[1]]
        if span
        else f"{n.name} 모집공고일 {n.notice_date} 청약접수 {' ~ '.join(n.apply_dates)}"
    )
    rows: list[ProvenanceRow] = []
    if n.notice_date:
        rows.append(
            prov_row(
                entity="remaining_event", entity_id=ev.id, key=key, field_name="notice_date", value=n.notice_date,
                value_text=n.notice_date, doc=n.doc, label="확인됨", excerpt=ex, span=span, observed_on=n.notice_date,
            )
        )  # fmt: skip
    if n.apply_dates:
        rows.append(
            prov_row(
                entity="remaining_event", entity_id=ev.id, key=key, field_name="apply_dates",
                value=json.dumps(n.apply_dates), value_text=" ~ ".join(n.apply_dates), doc=n.doc, label="확인됨",
                excerpt=ex, span=span, observed_on=n.notice_date,
            )
        )  # fmt: skip
    if n.units and n.units_doc is not None:
        total = sum(n.units.values())
        rows.append(
            prov_row(
                entity="remaining_event", entity_id=ev.id, key=key, field_name="units", value=total,
                value_text=f"{total}세대", doc=n.units_doc, label="확인됨", reason="주택형별 공급세대수 합",
                excerpt=n.units_excerpt, observed_on=n.notice_date,
            )
        )  # fmt: skip
    if rows:
        upsert_provenance(session, rows)


PAST_NOTICE_DAYS: Final = 30
"""청약접수 일자가 없는 공고는 모집공고일이 기준일보다 이만큼 이전이면 과거 공고로 본다(날짜 산술)."""


def _is_past(n: _Notice, day: str) -> bool:
    """접수가 이미 끝난 과거 공고인가(날짜 비교 — 판단 아님): 청약접수 마지막 날 < 기준일. 접수일이 없으면
    모집공고일 < 기준일 − 30일. 날짜를 모르면 과거로 보지 않는다(critical 유지 — 놓치지 않는다)."""
    if n.apply_dates:
        return max(n.apply_dates) < day
    if n.notice_date:
        return n.notice_date < (date.fromisoformat(day) - timedelta(days=PAST_NOTICE_DAYS)).isoformat()
    return False


def sync_remaining_events(
    session: Session, region_id: int, *, snapshot_id: int | None, detected_at: str
) -> RemainingSync:
    """지역의 잔여 공고 원문 → remaining_event(멱등). 이벤트는 세션에 넣고 flush 한다. commit 은 호출자."""
    region = session.get(Region, region_id)
    if region is None:
        raise LookupError(f"region {region_id} 없음")
    res = RemainingSync()
    found = _web_notices(session, region_id)
    for k, n in _api_notices(session, region_id).items():
        web = found.get(k)
        if web is not None and not n.units and web.units:
            n.units, n.units_doc, n.units_excerpt = web.units, web.units_doc, web.units_excerpt
        if n.kind is None and web is not None:
            n.kind = web.kind
        found[k] = n
    notices = [found[k] for k in sorted(found)]
    pending = [n for n in notices if n.result_text is None]
    web_urls = latest_by_urls(session, [ah_site.competition_url("remndr", n.hm, n.pb) for n in pending])
    for n in pending:
        _web_result(web_urls, n)
    quiet_all = region.status != "ready"  # 지역 최초 적재(bootstrap) — 전체 판정이 어차피 돈다
    day = detected_at[:10]
    anchors = _anchors(session, region, notices)

    existing: dict[tuple[str | None, str], RemainingEvent] = {
        (e.notice_no, e.kind): e
        for e in session.scalars(
            select(RemainingEvent)
            .join(Complex, Complex.id == RemainingEvent.complex_id)
            .where(Complex.region_id == region_id)
            .order_by(RemainingEvent.id)
        )
    }
    for n in notices:
        if n.kind is None:
            res.unmatched.append({"notice_no": n.pb, "name": n.name, "reason": NO_KIND})
            continue
        anchor = anchors[(n.hm, n.pb)]
        if anchor.reason is not None:
            res.unmatched.append({"notice_no": n.pb, "name": n.name, "reason": anchor.reason})
        if anchor.complex_id is None:
            continue
        vals: dict[str, Any] = {
            "complex_id": anchor.complex_id,
            "notice_date": n.notice_date,
            "apply_dates": list(n.apply_dates),
            "units_by_type": dict(n.units),
            "ratio_text": n.ratio_text,
            "result_text": n.result_text,
            "raw_document_id": n.doc.id,
        }
        row = existing.get((n.pb, n.kind))
        if row is None:
            row = RemainingEvent(kind=n.kind, notice_no=n.pb, **vals)
            session.add(row)
            session.flush()
            res.inserted += 1
            quiet = quiet_all or _is_past(n, day)
            res.events.append(
                make_event(
                    entity="remaining_event", entity_id=row.id, field="notice_no", old=None,
                    new=f"{n.kind} {n.pb} {n.name}", snapshot_id=snapshot_id, complex_id=anchor.complex_id,
                    detected_at=detected_at, severity="info" if quiet else "critical",
                )
            )  # fmt: skip
        else:
            changed = {a: v for a, v in vals.items() if fmt_value(getattr(row, a)) != fmt_value(v)}
            if not changed:
                res.unchanged += 1
            else:
                for attr, v in changed.items():
                    old = getattr(row, attr)
                    setattr(row, attr, v)
                    if attr == "raw_document_id":
                        continue
                    res.events.append(
                        make_event(
                            entity="remaining_event", entity_id=row.id, field=attr, old=old, new=v,
                            snapshot_id=snapshot_id, complex_id=row.complex_id, detected_at=detected_at,
                            severity="info" if attr in ("result_text", "ratio_text") else "notice",
                        )
                    )  # fmt: skip
                res.updated += 1
        _prov(session, row, n)
    session.add_all(res.events)
    session.flush()
    return res
