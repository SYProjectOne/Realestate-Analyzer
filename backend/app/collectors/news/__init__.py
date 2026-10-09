"""뉴스 수집기(네이버 검색 API — NAVER Cloud API HUB 기본, 개발자센터 레거시).

NEWS_API_KEY 가 없으면 비활성.
"""

from app.collectors.news.collector import (
    DISABLED_NO_KEY,
    NAVER_NEWS_URL,
    NCP_NEWS_URL,
    PROVIDERS,
    NewsCollector,
    NewsItem,
    Provider,
    parse_credentials,
    parse_news_json,
)

__all__ = [
    "DISABLED_NO_KEY",
    "NAVER_NEWS_URL",
    "NCP_NEWS_URL",
    "PROVIDERS",
    "NewsCollector",
    "NewsItem",
    "Provider",
    "parse_credentials",
    "parse_news_json",
]
