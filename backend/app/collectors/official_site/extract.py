"""공식 홈페이지 HTML → DOM 텍스트, 접수 상태 후보 문구, 렌더 필요 여부.

접수 상태를 **판단하지 않는다**(WP2 파서·판정기 몫). 여기서는 키워드가 들어 있는 문장을 후보로 모을 뿐이다.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

__all__ = ["INTAKE_KEYWORDS", "html_to_text", "intake_candidates", "needs_render"]

INTAKE_KEYWORDS: tuple[str, ...] = (
    "선착순",
    "잔여",
    "무순위",
    "임의공급",
    "접수",
    "계약",
    "청약",
    "모집",
    "마감",
    "완판",
    "분양중",
    "분양 중",
    "동호지정",
    "동·호",
    "방문예약",
    "방문 예약",
    "사전예약",
    "견본주택",
    "모델하우스",
)
_POPUP_MARKERS = re.compile(r"(?i)(popup|pop_|layer_?pop|layerpop|modal|lightbox|swal|dialog)")
_SPA_MARKERS = re.compile(r'(?i)(id="(root|app|__next)"|__NEXT_DATA__|data-reactroot|ng-app|nuxt)')
_MIN_TEXT = 300
_MAX_CANDIDATES = 40
_MAX_LEN = 200


def html_to_text(html: str) -> str:
    """스크립트·스타일을 뺀 보이는 텍스트(줄 단위, 빈 줄 제거)."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    lines = (" ".join(line.split()) for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def intake_candidates(text: str, *, source: str) -> list[dict[str, object]]:
    """키워드가 들어 있는 줄(중복 제거, 최대 40개·줄당 200자). 순서 = 문서 순서."""
    out: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        hits = [k for k in INTAKE_KEYWORDS if k in line]
        if not hits:
            continue
        snippet = line[:_MAX_LEN]
        if snippet in seen:
            continue
        seen.add(snippet)
        out.append({"text": snippet, "keywords": hits, "source": source})
        if len(out) >= _MAX_CANDIDATES:
            break
    return out


def needs_render(html: str, text: str) -> tuple[bool, str]:
    """httpx 본문만으로 부족한가(동적 페이지·팝업) — (필요 여부, 사유)."""
    if len(text) < _MIN_TEXT:
        return True, f"텍스트 {len(text)}자"
    if _SPA_MARKERS.search(html):
        return True, "SPA"
    if _POPUP_MARKERS.search(html):
        return True, "팝업 표식"
    return False, "정적"
