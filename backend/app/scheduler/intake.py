"""접수 상태 행의 분류 문구·이전 분류 복사 (DECISIONS D10-2, R3 재리뷰 N-C2).

- ``intake_text``: 접수 상태 행의 원문(공식 홈페이지 HTML·렌더 DOM 텍스트) → classify 항목 텍스트. 접수 문구 후보 줄
  (normalize official_site 파서 — 분류하지 않음)이 있으면 그 줄들, 없으면 DOM 텍스트 앞부분. 파이프라인 접수 classify
  입력과 여기 해시 비교가 같은 함수를 쓴다.
- ``carry_classification``: '접수 문구 미분류' 행의 문구 해시(sha256)가 같은 (단지, 경로)의 **직전 분류 행**(판정기
  classify 로 정한 행)과 같으면 그 분류(status·reason·note)를 복사한다 — 판정 호출 없음. 수집(collect)과 파이프라인
  접수 classify 앞에서 부른다. 그래서 변경 없는 날(T8) publish 스냅샷의 접수 상태·판정 범위·순위가 전날과 같고,
  다음 변경일에 단지마다 D9-3 critical 이벤트가 쏟아지지 않는다.
- 판단하지 않는다: 문자열 해시 비교(산술)만. 문구가 바뀌었으면 미분류로 두어 판정기가 다시 분류한다.
- 판정기 버전(R3 3차 minor 3): ``adapter_version`` 을 주면 그 버전으로 분류한 행만 복사한다. 버전이 바뀐 전체 재판정(D6)에서는
  ``reset_stale_classification`` 이 다른 버전으로 분류(·복사)된 행을 미분류로 되돌려 판정기가 다시 분류한다.
- R7-SITE(D26-1): 접수 항목에 스크린샷 행의 **팝업 그림 OCR 글자**(라벨 '추정(OCR)', ``OCR_HEADER`` 아래)를 붙인다 — 수집기가
  그림 해시로 캐시하므로 변경 없는 날 입력이 그대로다(분류 복사). (D26-3) 범위 경계·민간분양 아닌 단지(포함/제외 classify auto
  제외 클래스)의 미분류 행은 판정기에 보내지 않고 사유 '판정 대상 아님(<구분>)'으로 둔다(``mark_not_target`` — 분류 복사
  앞에서). 그 단지가 다시 대상이 되면 미분류로 되돌린다. 구분은 complex 행 값(판정기 classify·주소 매칭 결과)을 옮길 뿐이다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.scope import BOUNDARY_CLASS, EXCLUDED_CLASSES, pick_intake
from app.collectors.official_site.collector import OCR_LABEL, popup_ocr_texts
from app.collectors.official_site.extract import html_head
from app.judge import payloads as P
from app.judge import pipeline as jp
from app.models import ChangeEvent, Complex, IntakeStatus, JudgmentLog, RawDocument, Snapshot
from app.normalize._text import read_raw_text
from app.normalize.official_site_parser import intake_context, unique_lines
from app.normalize.store import raw_dto

__all__ = [
    "CLASSIFIED_MARK",
    "COPIED_MARK",
    "INTAKE_PATHS",
    "NOT_TARGET",
    "NO_TEXT",
    "OCR_HEADER",
    "UNCLASSIFIED",
    "SiteEvidence",
    "carry_classification",
    "classified_version",
    "current_item_text",
    "display_url",
    "intake_body",
    "intake_change_events",
    "intake_text",
    "mark_not_target",
    "not_target_reason",
    "ocr_text",
    "page_text",
    "pending_complexes",
    "reset_stale_classification",
    "site_evidence",
    "site_item",
    "text_sha256",
]

UNCLASSIFIED: Final = "접수 문구 미분류"  # collect.intake_rows 가 남기는 사유(분류 대기)
INTAKE_PATHS: Final = ("official_popup", "headless_shot")
CLASSIFIED_MARK: Final = "판정기 classify"
"""파이프라인 접수 classify 가 note 에 남기는 표식(``판정기 classify jl_<seq>``) — 판정기로 정한 행."""
COPIED_MARK: Final = "문구 해시 동일 — 이전 분류 복사"
NO_TEXT: Final = "접수 문구 없음"
"""원문에 접수 문구가 없어 판정기 호출 없이 남긴 사유(파이프라인 접수 classify) — 문구가 그대로 없으면 그대로 복사."""


OCR_HEADER: Final = f"[팝업 그림 글자 — {OCR_LABEL}]"
"""접수 항목에서 팝업 그림 OCR 글자 앞에 두는 줄(판정기가 추정 글자임을 본다)."""
OCR_PART_MAX: Final = 800
"""접수 항목의 OCR 부분 상한(나머지는 페이지 문구 몫)."""
NOT_TARGET: Final = "판정 대상 아님"
"""D26-3: 접수 판정에서 뺀 단지(범위 경계·민간분양 아님)의 사유 머리 — '판정 대상 아님(공공분양)'."""
_CLASS_TEXT: Final = {
    "public_sale": "공공분양",
    "public_rental": "공공임대",
    "private_rental": "민간임대",
    "non_apartment": "비아파트",
    "out_of_scope": "범위 밖",
}


def not_target_reason(cx: Complex) -> str | None:
    """D26-3: 접수 판정(공식 홈페이지 동일성·접수 classify)에서 빼는 단지면 사유, 아니면 None. 범위 경계(주소 매칭, D2-6)이거나
    포함/제외 classify 가 auto 로 제외 클래스(공공분양·임대·비아파트·범위 밖)라고 한 단지 — ``analysis.scope.judge_scope`` 의
    '제외' 규칙과 같은 조건(미해결은 빼지 않는다)."""
    cls = cx.inclusion_class
    if cls == BOUNDARY_CLASS:
        return f"{NOT_TARGET}({BOUNDARY_CLASS})"
    if cls in EXCLUDED_CLASSES and cx.inclusion_decision == "auto":
        return f"{NOT_TARGET}({_CLASS_TEXT.get(cls, cls)})"
    return None


def mark_not_target(session: Session, snapshot_id: int) -> list[int]:
    """이 스냅샷의 '접수 문구 미분류' 행 중 판정 대상이 아닌 단지(``not_target_reason``) → 상태 '확인 불가' + 그 사유(판정 호출
    없음). 반대로 '판정 대상 아님' 행인데 단지가 다시 대상이면(법정동 보정·재분류) 미분류로 되돌린다. 바꾼 행 id."""
    out: list[int] = []
    for row in session.scalars(
        select(IntakeStatus)
        .where(IntakeStatus.snapshot_id == snapshot_id, IntakeStatus.path.in_(INTAKE_PATHS))
        .order_by(IntakeStatus.id)
    ):
        if row.reason != UNCLASSIFIED and not (row.reason or "").startswith(NOT_TARGET):
            continue
        cx = session.get(Complex, row.complex_id)
        why = not_target_reason(cx) if cx is not None else None
        if row.reason == UNCLASSIFIED and why is not None:
            row.status, row.reason = "확인 불가", why
        elif row.reason != UNCLASSIFIED and why is None:
            row.status, row.reason = "확인 불가", UNCLASSIFIED
        elif row.reason != UNCLASSIFIED and why != row.reason:
            row.reason = why
        else:
            continue
        out.append(row.id)
    if out:
        session.flush()
    return out


def ocr_text(session: Session, row: IntakeStatus) -> str:
    """접수 행 원문(스크린샷 행)의 팝업 그림 OCR 글자(수집기 meta — 라벨 '추정(OCR)'). 없으면 ''."""
    if row.path != "headless_shot" or row.raw_document_id is None:
        return ""
    doc = session.get(RawDocument, row.raw_document_id)
    if doc is None or not (doc.content_type or "").startswith("image/"):
        return ""
    try:
        return "\n".join(popup_ocr_texts(raw_dto(doc))).strip()
    except Exception:  # 원문 파일 없음 등 — OCR 글자 없음
        return ""


def _row_text(session: Session, row: IntakeStatus) -> str:
    """접수 행 원문의 페이지 문구 전체(렌더 행이면 렌더 후 DOM 텍스트, HTML 행이면 HTML 의 보이는 텍스트)."""
    doc = session.get(RawDocument, row.raw_document_id) if row.raw_document_id is not None else None
    if doc is None:
        return ""
    dto = raw_dto(doc)
    src = dto.model_copy(update={"path": None}) if row.path == "headless_shot" else dto
    try:
        return (read_raw_text(src) or "").strip()
    except Exception:  # 원문 파일 없음 등 — 문구 없음
        return ""


INTAKE_BODY_BUDGET: Final = jp.SITE_ITEM_BUDGET - 100
"""접수 항목 페이지 부분 목표 길이('단지: 이름' 줄 몫과 공개 텍스트 가림 여유를 뺀 값 — 2000자 자르기에 끝이 잘리지 않게)."""


def intake_body(session: Session, row: IntakeStatus) -> str:
    """접수 classify 의 페이지 부분: 접수 문구 후보 줄과 그 앞뒤 줄(``official_site_parser.intake_context``), 후보가 없으면
    줄 중복을 뺀 페이지 문구(앞·뒤). 원문에 문구가 없으면 ''(→ '접수 문구 없음', 판정 호출 없음).

    R7-SITE(D26-1): 스크린샷 행에 팝업 그림 OCR 글자가 있으면 ``OCR_HEADER`` 아래에 붙인다(같은 규칙 — 페이지·OCR 어느 쪽이든
    후보가 있으면 후보 문맥만, 둘 다 없으면 둘 다 문구). OCR 부분은 ``OCR_PART_MAX`` 자 안, 페이지 부분이 나머지.

    후보가 있을 때 페이지 문구 전체를 덧붙이지 않는다 — 실제 판정기 재생(인천 첫 실행 48행, R6_TESTS_INTAKE §4)에서 메뉴·광고
    문구가 섞이면 '선착순 동·호지정' 같은 분명한 문구도 open·auto → review 로 흐려졌다(4행)."""
    text = _row_text(session, row)
    ocr = ocr_text(session, row)
    if not text and not ocr:
        return ""
    page_ctx = intake_context(text) if text else []
    ocr_ctx = intake_context(ocr) if ocr else []
    if page_ctx or ocr_ctx:  # 후보가 있으면 후보 문맥만(페이지·OCR 각각)
        page, pop = "\n".join(page_ctx), "\n".join(ocr_ctx)
    else:
        page, pop = "\n".join(unique_lines(text)), "\n".join(unique_lines(ocr))
    if not pop:  # OCR 글자가 없으면 R6-INTAKE 와 같은 입력(input_hash 그대로)
        return P.head_tail(page, INTAKE_BODY_BUDGET)
    block = OCR_HEADER + "\n" + P.head_tail(pop, OCR_PART_MAX)
    if not page:
        return block
    return P.head_tail(page, INTAKE_BODY_BUDGET - len(block) - 1) + "\n" + block


def intake_text(session: Session, row: IntakeStatus) -> str:
    """접수 상태 행 → classify 항목 텍스트: '단지: <이름>' + ``intake_body``. 문구가 없으면 ''.

    R6-INTAKE(인천 첫 실행 — 접수 classify 43건 중 확인 불가 36): 예전에는 후보 줄만 따로 보냈다 — 후보가 '마감재리스트'
    (마감재 = 마감 자재, 파서 거짓 후보)뿐이면 페이지 문구 대신 그 한 줄이 입력이 되었고, '분양중공사중'·'무순위 모집공고'
    같은 조각은 어느 단지의 무엇인지 몰라 review 로 남았다. 이제 단지 이름·후보 앞뒤 줄·페이지 문구를 함께 보낸다(분류는
    판정기만).
    파이프라인 접수 classify 입력과 분류 복사의 문구 해시가 같은 함수를 쓴다."""
    body = intake_body(session, row)
    if not body:
        return ""
    cx = session.get(Complex, row.complex_id)
    head = f"단지: {cx.name}\n" if cx is not None and cx.name else ""
    return head + body


@dataclass(frozen=True, slots=True)
class SiteEvidence:
    """공식 홈페이지 동일성 classify 의 페이지 쪽 근거(R6-INTAKE): 보이는 주소(IDN 한글 표기, 쿼리 제외)·이동 후 주소·HTML
    제목·설명·페이지 문구(줄 중복 제거). 모두 공개 페이지에서 읽은 값이다."""

    url: str | None
    final_url: str | None
    title: str | None
    description: str | None
    text: str


def _unicode_host(host: str) -> str:
    """퓨니코드 라벨(xn--)을 유니코드로(실패하면 그대로)."""
    try:
        return ".".join(
            lbl.encode("ascii").decode("idna") if lbl.startswith("xn--") else lbl for lbl in host.split(".")
        )
    except UnicodeError:
        return host


def display_url(url: str | None) -> str | None:
    """사람이 읽는 주소: 퓨니코드(xn--) 호스트를 한글로 풀고 쿼리·조각을 뗀다(공개 주소만 — 규칙 6). 실패하면 원문에서
    쿼리만 뗀다."""
    if not url:
        return None
    try:
        parts = urlsplit(url)
        host = _unicode_host(parts.hostname or "")
        netloc = host + (f":{parts.port}" if parts.port else "")
        return urlunsplit((parts.scheme, netloc, parts.path, "", "")) or None
    except ValueError:
        return url.split("?", 1)[0].split("#", 1)[0] or None


def _html_row(session: Session, doc: RawDocument) -> RawDocument | None:
    """접수 행 원문에 맞는 HTML 원문 행: HTML 행이면 그 행, 렌더 PNG 행이면 같은 URL 의 HTML 행 중 메타의
    ``render.screenshot_sha256`` 이 그 PNG 인 가장 최근 행(없으면 같은 URL 의 가장 최근 성공 HTML 행). 원문 행은 sha256 로
    하나라 같은 페이지면 같은 행이다(결정적)."""
    if not (doc.content_type or "").startswith("image/"):
        return doc
    rows = [
        r
        for r in session.scalars(
            select(RawDocument)
            .where(
                RawDocument.source_kind == "official_site",
                RawDocument.url == doc.url,
                RawDocument.http_status == 200,
                RawDocument.path.is_not(None),
            )
            .order_by(RawDocument.id.desc())
            .limit(50)
        )
        if not (r.content_type or "").startswith(("image/", "application/json"))
    ]
    for r in rows:
        render = (r.meta or {}).get("render") if isinstance(r.meta, dict) else None
        if isinstance(render, dict) and render.get("screenshot_sha256") == doc.sha256:
            return r
    return rows[0] if rows else None


def site_evidence(session: Session, row: IntakeStatus) -> SiteEvidence:
    """D21-5 동일성 classify 의 페이지 근거(R6-INTAKE). 원문이 없으면 빈 근거."""
    doc = session.get(RawDocument, row.raw_document_id) if row.raw_document_id is not None else None
    if doc is None:
        return SiteEvidence(None, None, None, None, "")
    html_row = _html_row(session, doc)
    title = desc = final = None
    if html_row is not None:
        meta = html_row.meta if isinstance(html_row.meta, dict) else {}
        final = display_url(str(meta.get("final_url") or "") or None)
        try:
            html = read_raw_text(raw_dto(html_row).model_copy(update={"text_path": None}))
        except Exception:  # 원문 파일 없음 — 제목·설명 없이
            html = None
        if html:
            title, desc = html_head(html)
    return SiteEvidence(
        url=display_url(row.evidence_url or doc.url),
        final_url=final,
        title=title,
        description=desc,
        text="\n".join(unique_lines(_row_text(session, row))),
    )


def site_item(session: Session, row: IntakeStatus, cx: Complex) -> jp.SiteItem:
    """접수 행 → 동일성 classify 항목(단지 사실 + 페이지 근거). 파이프라인 동일성 classify 와 분류 복사의 입력 비교가 같은
    함수를 쓴다."""
    ev = site_evidence(session, row)
    return jp.SiteItem(
        row.complex_id,
        row.path,
        cx.name,
        cx.address,
        ev.text,
        builder=cx.builder,
        developer=cx.developer,
        units_total=cx.units_total,
        url=ev.url,
        final_url=ev.final_url,
        title=ev.title,
        description=ev.description,
    )


def page_text(session: Session, row: IntakeStatus) -> str:
    """접수 행 원문의 페이지 문구(줄 중복 제거, 전체) — 동일성 항목이 길이에 맞춰 앞·뒤를 남긴다(``SiteItem``).

    예전(R4 재시험 N6)에는 앞 1500자만 넘겨 꼬리말(시행·현장 주소·세대수)이 빠졌다(R6-INTAKE)."""
    return "\n".join(unique_lines(_row_text(session, row)))


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _classified(row: IntakeStatus) -> bool:
    """파이프라인이 처리한 행: 판정기 classify 결과이거나 '접수 문구 없음'(호출 없이 사유만)."""
    return row.reason != UNCLASSIFIED and (CLASSIFIED_MARK in (row.note or "") or row.reason == NO_TEXT)


def _previous_classified(session: Session, snap: Snapshot, row: IntakeStatus) -> IntakeStatus | None:
    """같은 지역·(단지, 경로)의 기준일 전(또는 같은 기준일의 앞선) 스냅샷에서 가장 최근의 판정기 분류 행."""
    stmt = (
        select(IntakeStatus)
        .join(Snapshot, Snapshot.id == IntakeStatus.snapshot_id)
        .where(
            Snapshot.region_id == snap.region_id,
            Snapshot.id != snap.id,
            Snapshot.asof_date <= snap.asof_date,
            IntakeStatus.complex_id == row.complex_id,
            IntakeStatus.path == row.path,
            IntakeStatus.reason.is_distinct_from(UNCLASSIFIED),
        )
        .order_by(Snapshot.asof_date.desc(), IntakeStatus.id.desc())
    )
    for cand in session.scalars(stmt.limit(20)):
        if _classified(cand):
            return cand
    return None


_SEQ_RE = re.compile(re.escape(CLASSIFIED_MARK) + r" jl_(\d+)")


def classified_version(session: Session, row: IntakeStatus) -> str | None:
    """그 행의 분류를 낸 판정 봉투의 adapter_version(note 의 ``판정기 classify jl_<seq>`` — 복사 행도 원 표식을 지닌다).
    표식·로그가 없으면 None(버전 미상)."""
    found = _SEQ_RE.findall(row.note or "")
    if not found:
        return None
    log = session.get(JudgmentLog, int(found[-1]))
    return log.adapter_version if log is not None else None


def _logged_item(session: Session, prev: IntakeStatus) -> tuple[str, str] | None:
    """분류 행 note 의 ``판정기 classify jl_<seq>`` 판정 입력(judgment_log.input_json)에서 그 행의 항목 (종류, 텍스트).
    종류 = 'site'(동일성 classify 에서 멈춘 행) | 'intake'(접수 classify 행). 표식·로그·항목이 없으면 None."""
    found = _SEQ_RE.findall(prev.note or "")
    if not found:
        return None
    log = session.get(JudgmentLog, int(found[-1]))
    items = (log.input_json or {}).get("items") if log is not None else None
    if not isinstance(items, list):
        return None
    for kind in ("site", "intake"):
        key = f"{kind}:c{prev.complex_id}:{prev.path}"
        hit = next((it for it in items if isinstance(it, dict) and it.get("id") == key), None)
        if hit is not None and hit.get("text") is not None:
            return kind, str(hit["text"])
    return None


def current_item_text(session: Session, row: IntakeStatus, kind: str) -> str | None:
    """지금 원문·단지 사실로 만들 판정기 항목 텍스트(payload 빌더의 공개 텍스트 정리·길이 제한까지 — 로그와 같은 모양).
    kind = 'site'(동일성) | 'intake'(접수). 단지가 없으면 None."""
    if kind == "site":
        cx = session.get(Complex, row.complex_id)
        if cx is None:
            return None
        it = site_item(session, row, cx)
        payload = P.classify_site_identity_payload([(it.key, it.item_text)])
    else:
        item = jp.IntakeItem(row.complex_id, row.path, intake_text(session, row))
        payload = P.classify_intake_payload([(item.key, item.text)])
    return str(payload["items"][0]["text"])


def _same_input(session: Session, prev: IntakeStatus, row: IntakeStatus) -> bool | None:
    """D22-2·D10-2(R6-INTAKE): 직전 분류를 낸 판정기 입력(그 행의 항목 텍스트)이 지금 이 행으로 만들 입력과 같은가.
    모르면(표식·로그 없음 — 사람·옛 행) None. 원문이 같아도 **입력 조립이 바뀌면**(단지 사실 — 이름·주소·시공 등 — 이나
    동일성 근거가 달라지면) False → 복사하지 않고 판정기가 다시 분류한다. 같으면 복사(호출 없음). 텍스트 비교(산술)."""
    logged = _logged_item(session, prev)
    if logged is None:
        return None
    kind, text = logged
    now = current_item_text(session, row, kind)
    return None if now is None else now == text


def _strip_marks(note: str | None) -> str | None:
    parts = [p for p in (note or "").split(" · ") if p and not p.startswith((CLASSIFIED_MARK, COPIED_MARK))]
    return " · ".join(parts) or None


def reset_stale_classification(session: Session, snapshot_id: int, adapter_version: str) -> list[int]:
    """판정기 버전이 바뀐 뒤(D6 전체 재판정): 이 스냅샷에서 **다른 버전**으로 분류(또는 그 분류를 복사)한 접수 행을
    '접수 문구 미분류'로 되돌린다 — 파이프라인 접수 classify 가 새 버전으로 다시 분류한다(R3 3차 minor 3). 되돌린 행 id."""
    out: list[int] = []
    for row in session.scalars(
        select(IntakeStatus)
        .where(
            IntakeStatus.snapshot_id == snapshot_id,
            IntakeStatus.path.in_(INTAKE_PATHS),
            IntakeStatus.reason.is_distinct_from(UNCLASSIFIED),
        )
        .order_by(IntakeStatus.id)
    ):
        if CLASSIFIED_MARK not in (row.note or ""):
            continue  # 판정기 분류가 아닌 행(접수 문구 없음·사람 확인 등)
        ver = classified_version(session, row)
        if ver is not None and ver != adapter_version:
            row.reason = UNCLASSIFIED
            row.note = _strip_marks(row.note)
            out.append(row.id)
    if out:
        session.flush()
    return out


def _image_changed(session: Session, prev: IntakeStatus, row: IntakeStatus) -> bool:
    """두 접수 행의 원문 중 하나라도 그림 해시(``raw_document.image_hash``)가 있고 서로 다르면 True."""
    a = session.get(RawDocument, prev.raw_document_id) if prev.raw_document_id is not None else None
    b = session.get(RawDocument, row.raw_document_id) if row.raw_document_id is not None else None
    ha, hb = (a.image_hash if a else None), (b.image_hash if b else None)
    return (ha is not None or hb is not None) and ha != hb


def carry_classification(
    session: Session, snapshot_id: int, *, adapter_version: str | None = None
) -> list[int]:
    """이 스냅샷의 '접수 문구 미분류' 행 중 문구 해시가 직전 분류 행과 같은 것 → 분류 복사. 복사한 행 id.

    ``adapter_version`` 을 주면 직전 분류가 다른 판정기 버전이면 복사하지 않는다(R3 3차 minor 3 — 미분류로 남아 판정기가
    새 버전으로 분류한다)."""
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        return []
    mark_not_target(session, snapshot_id)  # D26-3: 판정 대상 아닌 단지는 복사·판정 전에 사유를 정한다
    rows = list(
        session.scalars(
            select(IntakeStatus)
            .where(
                IntakeStatus.snapshot_id == snapshot_id,
                IntakeStatus.path.in_(INTAKE_PATHS),
                IntakeStatus.reason == UNCLASSIFIED,
            )
            .order_by(IntakeStatus.id)
        )
    )
    out: list[int] = []
    for row in rows:
        prev = _previous_classified(session, snap, row)
        if prev is None:
            if not intake_text(session, row).strip():
                # 원문에 접수 문구가 없다(팝업 그림만 등) — 분류할 것이 없으니 판정 호출 없이 사유만(파이프라인과 같은 규칙)
                row.reason = NO_TEXT
                out.append(row.id)
            continue
        if adapter_version is not None and CLASSIFIED_MARK in (prev.note or ""):
            ver = classified_version(session, prev)
            if ver is not None and ver != adapter_version:
                continue
        if prev.raw_document_id != row.raw_document_id and _image_changed(session, prev, row):
            continue  # 팝업 그림이 바뀌었다 — DOM 문구가 같아도 그림 속 접수 안내는 다를 수 있다(R3 3차 minor 4)
        if prev.raw_document_id != row.raw_document_id:  # 같은 원문 행(같은 sha256)이면 문구도 같다
            now_text = intake_text(session, row).strip()
            if text_sha256(now_text) != text_sha256(intake_text(session, prev).strip()):
                continue
        if _same_input(session, prev, row) is False:
            continue  # R6-INTAKE: 판정기 입력 조립(동일성 근거·접수 문구 문맥·단지 사실)이 바뀌었다 — 다시 분류
        row.status = prev.status
        row.reason = prev.reason
        # 복사 표식은 매일 쌓이지 않게 마지막 것만 둔다
        base = " · ".join(p for p in (prev.note or "").split(" · ") if p and not p.startswith(COPIED_MARK))
        mark = f"{COPIED_MARK}(접수 행 {prev.id}, 스냅샷 {prev.snapshot_id})"
        row.note = f"{base} · {mark}" if base else mark
        out.append(row.id)
    if out:
        session.flush()
    return out


def pending_complexes(session: Session, snapshot_id: int) -> list[int]:
    """분류 복사 뒤에도 '접수 문구 미분류'로 남은 행의 단지(문구가 바뀌었거나 처음 본 문구) — 판정기 classify 가 필요하다.

    수집(collect)은 이 단지들을 재판정 대상에 넣는다: 미분류인 채 이전 판정을 복사해 publish 하면 접수 상태와 저장 범위가
    갈린다(N-C2 '변경 없는 날 P4 없이 publish')."""
    return sorted(
        set(
            session.scalars(
                select(IntakeStatus.complex_id).where(
                    IntakeStatus.snapshot_id == snapshot_id,
                    IntakeStatus.path.in_(INTAKE_PATHS),
                    IntakeStatus.reason == UNCLASSIFIED,
                )
            )
        )
    )


def intake_change_events(
    session: Session,
    snap: Snapshot,
    prev: Snapshot | None,
    complex_ids: Sequence[int],
    *,
    detected_at: str,
) -> list[ChangeEvent]:
    """표시 접수 상태(``analysis.scope.pick_intake``)가 이전 스냅샷과 다르면 change_event(intake_status, critical).

    판단하지 않는다 — 두 스냅샷의 접수 행 status 문자열 비교(산술)만. 이전 스냅샷에 표시 행이 없으면 기준선(이벤트 없음).
    같은 스냅샷·단지·새 상태의 intake_status 이벤트가 이미 있으면(사람 확인 입력 API·이전 실행) 만들지 않는다.
    수집(공식 홈페이지 403 처럼 분류 없이 표시 접수가 바뀌는 날 — R3 3차 minor 4)과 파이프라인(분류 뒤)이 같이 쓴다.
    """
    if prev is None or not complex_ids:
        return []
    ids = list(complex_ids)
    rows: dict[tuple[int, int], list[IntakeStatus]] = {}
    for r in session.scalars(
        select(IntakeStatus).where(
            IntakeStatus.snapshot_id.in_([snap.id, prev.id]), IntakeStatus.complex_id.in_(ids)
        )
    ):
        rows.setdefault((r.snapshot_id, r.complex_id), []).append(r)
    existing = {
        (e.complex_id, e.new_text)
        for e in session.scalars(
            select(ChangeEvent).where(
                ChangeEvent.snapshot_id == snap.id,
                ChangeEvent.entity == "intake_status",
                ChangeEvent.field == "status",
            )
        )
    }
    events: list[ChangeEvent] = []
    for cid in sorted(ids):
        now = pick_intake(rows.get((snap.id, cid), []))
        before = pick_intake(rows.get((prev.id, cid), []))
        if now is None or before is None or now.status == before.status:
            continue
        if (cid, now.status) in existing:
            continue
        ev = ChangeEvent(
            snapshot_id=snap.id,
            entity="intake_status",
            entity_id=now.id,
            field="status",
            old_text=before.status,
            new_text=now.status,
            detected_at=detected_at,
            severity="critical",
            triggers_rejudge=True,
            complex_id=cid,
        )
        session.add(ev)
        events.append(ev)
    session.flush()
    return events
