# ruff: noqa: E501
"""e2e 오프라인 도구(WP9) — 네트워크 없이 백엔드를 돌리기 위한 HTTP 전송 2개.

- ``replay_transport(zip)``: 청약홈 웹 녹화(WP1a ``backend/tests/collectors/applyhome/fixtures/applyhome_2026-10-09.zip``,
  ``manifest.json`` + 본문 파일)를 재생하는 ``httpx.MockTransport``. 키 = (METHOD, scheme://host/path, 정렬된 쿼리,
  정렬된 POST 폼 중 목록 조회 키). robots.txt 는 404(허용). 녹화에 없는 요청은 ConnectError(실패 행으로 남는다).
- ``offline_transport()``: 모든 요청 ConnectError(DNS 실패와 같은 실패 행).

모듈 테스트 helper 를 import 하지 않는다(녹화 파일 형식만 공유).
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import httpx

KEY_FORM_FIELDS = ("beginPd", "endPd", "suplyAreaCode", "pageIndex")
SECRET_PARAMS = frozenset({"serviceKey"})

Key = tuple[str, str, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]


def _key(method: str, url: str, form: dict[str, str] | None) -> Key:
    parts = urlsplit(url)
    query = tuple(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in SECRET_PARAMS))
    body = tuple(sorted((k, v) for k, v in (form or {}).items() if k in KEY_FORM_FIELDS))
    return (method.upper(), f"{parts.scheme}://{parts.netloc}{parts.path}", query, body)


def _fail(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("[e2e offline] network disabled", request=request)


def offline_transport() -> httpx.MockTransport:
    return httpx.MockTransport(_fail)


def replay_transport(archive_path: Path) -> httpx.MockTransport:
    archive = zipfile.ZipFile(archive_path)
    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    entries = {_key(e["method"], e["url"], e.get("form")): e for e in manifest["entries"]}
    misses: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404, text="not found")
        form = None
        if request.method == "POST":
            form = dict(parse_qsl(request.content.decode("utf-8"), keep_blank_values=True))
        entry = entries.get(_key(request.method, str(request.url), form))
        if entry is None:
            misses.append(f"{request.method} {request.url}")
            raise httpx.ConnectError("[e2e replay] 녹화에 없는 요청", request=request)
        body = archive.read(entry["file"]) if entry.get("file") else b""
        return httpx.Response(entry["status"], content=body, headers={"content-type": entry.get("content_type", "text/html")})

    transport = httpx.MockTransport(handle)
    transport.misses = misses  # type: ignore[attr-defined]
    return transport
