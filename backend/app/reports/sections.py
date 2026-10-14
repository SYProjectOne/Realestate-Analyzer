"""보고서 고정 목차 (meta §2-3, DECISIONS D4·D28-4). 제목 문자열은 HTML·PDF 텍스트 검사(T15)의 기준이다.

R9-REPORT(D28-4, 30-proposal §11-2 (6)): 장 번호(§1~§11)와 개수·순서는 그대로 두고, 초보 독자용 쉬운 말 제목을
앞에 쓰고 원래 용어를 괄호에 남긴다(원 장 이름은 ``ORIGINAL_TITLES`` — RA·meta 와 대조용). '§8 종합 추천'은
'추천'이 금지어라 '§8 종합 정리(판정기 결과)'로 바꾼다(30-proposal 결정 13 권고안).

본문 = §1~§9 + §12(비교 장). 부록 = §10 부록 A · §11 부록 B · 부록 C 용어 · 부록 D 전체 표.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "APPENDIX_C_TITLE",
    "APPENDIX_D_TITLE",
    "APPENDIX_TITLES",
    "BODY_TITLES",
    "DISCLAIMER",
    "EXTRA_TITLE",
    "ORIGINAL_TITLES",
    "SECTION_TITLES",
]

SECTION_TITLES: Final[tuple[str, ...]] = (
    "§1 기준일과 제도(규제·전매·거주의무)",
    "§2 판정기 연결 확인",
    "§3 어떤 단지를 넣고 뺐나(포함·제외 분류)",
    "§4 단지 목록 — 청약 진행·예정(A)과 남은 집(B)",
    "§5 주변 시세·호재·입주 물량(벤치마크·공급)",
    "§6 가격 전망과 종합 점수(사다리·rerank·TOP 5)",
    "§7 상위 5곳 자세히 보기(TOP 5)",
    "§8 종합 정리(판정기 결과)",
    "§9 확인하지 못한 것과 한계",
    "§10 부록 A 판정기 호출 기록",
    "§11 부록 B 참고자료(출처 URL·확인일)",
)

ORIGINAL_TITLES: Final[tuple[str, ...]] = (
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

EXTRA_TITLE: Final = "§12 이전 기준일과 달라진 점(지역 추가·변경)"

APPENDIX_C_TITLE: Final = "부록 C 용어 풀이"
APPENDIX_D_TITLE: Final = "부록 D 전체 표(본문 요약 표의 원본)"

BODY_TITLES: Final[tuple[str, ...]] = (*SECTION_TITLES[:9], EXTRA_TITLE)
APPENDIX_TITLES: Final[tuple[str, ...]] = (*SECTION_TITLES[9:], APPENDIX_C_TITLE, APPENDIX_D_TITLE)

DISCLAIMER: Final = "투자 권유 아님 · 상대 비교"
