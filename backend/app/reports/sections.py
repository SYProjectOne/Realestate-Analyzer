"""보고서 고정 목차 (meta §2-3, DECISIONS D4). 제목 문자열은 HTML·PDF 텍스트 검사의 기준이다."""

from __future__ import annotations

from typing import Final

__all__ = ["DISCLAIMER", "EXTRA_TITLE", "SECTION_TITLES"]

SECTION_TITLES: Final[tuple[str, ...]] = (
    "§1 기준일·제도",
    "§2 판정기 연결 확인",
    "§3 포함/제외 기준과 분류 결과",
    "§4 (A) 청약 진행·예정 / (B) 잔여물건 전수",
    "§5 벤치마크·비교 시세·호재·공급",
    "§6 판정 — 사다리·rerank·종합 점수·TOP 5",
    "§7 TOP 5 딥리서치",
    "§8 종합 추천",
    "§9 검증 한계",
    "§10 부록 A 판정기 호출 로그",
    "§11 부록 B 참고자료",
)

EXTRA_TITLE: Final = "§12 지역 추가·변경 장 — 이전 스냅샷 대비"

DISCLAIMER: Final = "투자 권유 아님 · 상대 비교"
