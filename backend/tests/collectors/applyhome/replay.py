"""녹화 HTTP 재생 (respx). 녹화 = zip 하나(``manifest.json`` + 응답 본문 파일). 웹 + API 녹화는 ``merged``.

키 = (METHOD, scheme://host/path, 정렬된 쿼리, 정렬된 POST 폼 중 ``KEY_FORM_FIELDS``).
녹화에 없는 요청은 ``AssertionError`` — 테스트가 조용히 통과하지 않게 한다.
"""

from __future__ import annotations

import json
import zipfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import httpx
import respx

KEY_FORM_FIELDS = ("beginPd", "endPd", "suplyAreaCode", "pageIndex")
SECRET_PARAMS = frozenset({"serviceKey"})
ROBOTS_404 = "The requested URL was not found on this server."

Key = tuple[str, str, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]


def request_key(method: str, url: str, form: dict[str, str] | None = None) -> Key:
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}{parts.path}"
    # serviceKey(공공데이터포털 키)는 녹화에 없다 — 빼고 맞춘다
    query = tuple(
        sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in SECRET_PARAMS)
    )
    body = tuple(sorted((k, v) for k, v in (form or {}).items() if k in KEY_FORM_FIELDS))
    return (method.upper(), base, query, body)


@dataclass(slots=True)
class Entry:
    method: str
    url: str
    form: dict[str, str] | None
    status: int
    content_type: str
    file: str | None


@dataclass(slots=True)
class Recording:
    archive: zipfile.ZipFile
    entries: dict[Key, Entry]
    overrides: dict[Key, httpx.Response | Callable[[httpx.Request], httpx.Response]] = field(
        default_factory=dict
    )
    calls: Counter[str] = field(default_factory=Counter)

    @classmethod
    def load(cls, path: Path) -> Recording:
        archive = zipfile.ZipFile(path)
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        entries: dict[Key, Entry] = {}
        for item in manifest["entries"]:
            e = Entry(
                method=item["method"],
                url=item["url"],
                form=item.get("form"),
                status=item["status"],
                content_type=item.get("content_type", "text/html;charset=UTF-8"),
                file=item.get("file"),
            )
            entries[request_key(e.method, e.url, e.form)] = e
        return cls(archive=archive, entries=entries)

    def body(self, entry: Entry) -> bytes:
        if entry.file is None:
            return b""
        return self.archive.read(entry.file)

    def override(
        self,
        method: str,
        url: str,
        response: httpx.Response | Callable[[httpx.Request], httpx.Response],
        form: dict[str, str] | None = None,
    ) -> None:
        """녹화 대신 돌려줄 응답(또는 요청을 받아 응답을 만들거나 httpx 예외를 던지는 함수)."""
        self.overrides[request_key(method, url, form)] = response

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.url.path == "/robots.txt":
            self.calls["robots"] += 1
            return httpx.Response(404, text=ROBOTS_404)
        form: dict[str, str] | None = None
        if request.method == "POST":
            form = dict(parse_qsl(request.content.decode("utf-8"), keep_blank_values=True))
        key = request_key(request.method, url, form)
        self.calls[request.url.host] += 1
        if key in self.overrides:
            found = self.overrides[key]
            return found(request) if callable(found) else found
        entry = self.entries.get(key)
        if entry is None:
            raise AssertionError(f"녹화에 없는 요청: {request.method} {url} {form}")
        return httpx.Response(
            entry.status, content=self.body(entry), headers={"content-type": entry.content_type}
        )

    def mock(self, first: Callable[[respx.MockRouter], None] | None = None) -> respx.MockRouter:
        """녹화 재생 라우터. ``first`` = 녹화보다 먼저 맞출 라우트(respx 는 등록 순서로 맞춘다)."""
        router = respx.mock(assert_all_called=False)
        if first is not None:
            first(router)
        router.route(host="www.applyhome.co.kr").mock(side_effect=self.handler)
        router.route(host="static.applyhome.co.kr").mock(side_effect=self.handler)
        router.route(host="api.odcloud.kr").mock(side_effect=self.handler)
        return router

    def merged(self, other: Recording) -> Recording:
        """두 녹화를 하나로(같은 키는 other 우선) — 웹 녹화 + API 녹화 재생."""
        merged = MergedRecording(archive=self.archive, entries={**self.entries, **other.entries})
        merged.sources = {k: self for k in self.entries} | {k: other for k in other.entries}
        return merged


@dataclass(slots=True)
class MergedRecording(Recording):
    sources: dict[Key, Recording] = field(default_factory=dict)

    def body(self, entry: Entry) -> bytes:
        if entry.file is None:
            return b""
        src = self.sources.get(request_key(entry.method, entry.url, entry.form), self)
        return src.archive.read(entry.file)
