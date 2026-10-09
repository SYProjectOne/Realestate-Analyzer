"""픽스처 생성 공용 부품 (WP9): Fact·출처(provenance)·원문 발췌(raw txt) 를 한 번에 만든다.

규칙
- Fact는 출처 키(src)로 만든다. 출처가 원문 발췌 문서(notice_pdf·applyhome_detail·official_site·news)면
  발췌 문장을 그 문서의 재구성 txt에 한 줄로 쓰고, provenance 행에 excerpt_start/end 오프셋을 남긴다.
- 산술 값(라벨 '추정', reason '산술 …')은 원문 발췌 대신 식을 excerpt·formula_text로 남긴다.
- 보고서에 없는 값은 Fact(label='확인 불가', reason=사유).
- 판정기 값은 prov='jl_<seq>'(provenance 행 없이 judgments/_index.json 이 출처).
"""

# ruff: noqa: E501  (데이터 표 한 줄 유지)
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

CHECKED = "2026-10-07"  # 보고서 확인일(모든 수치)
FETCHED_AT = "2026-10-07T00:00:00+09:00"  # 녹화 시각(시각 미기재 → 자정 고정, 픽스처 관례)

KIND_DIR = {
    "notice_pdf": "notice",
    "applyhome_detail": "applyhome_detail",
    "applyhome_list": "applyhome_list",
    "official_site": "official_site",
    "news": "news",
    "rtms": "rtms",
    "reference": "reference",
    "stats": "stats",
}
DEFAULT_LABEL = {
    "notice_pdf": "확인됨",
    "applyhome_detail": "확인됨",
    "applyhome_list": "확인됨",
    "official_site": "확인됨",
    "news": "비공식",
    "rtms": "재가공",
    "reference": "확인됨",
    "stats": "확인됨",
}
SOURCE_RANK = {"notice_pdf": 1, "applyhome_detail": 1, "applyhome_list": 1, "official_site": 2, "news": 3}


def dumps(doc: Any) -> str:
    """픽스처 JSON 직렬화 규칙(재생성 비교용): UTF-8, 들여쓰기 2, 키 순서 유지, LF, 끝 줄바꿈."""
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- 값 지정자


@dataclass(frozen=True)
class S:
    """출처 src의 원문 값. text = 원문 표기(발췌 한 줄)."""

    src: str
    v: Any
    unit: str
    text: str
    reason: str | None = None
    label: str | None = None
    compare: int | None = None  # 상충을 compare로 판정한 judgment_seq


@dataclass(frozen=True)
class D:
    """산술 값(라벨 추정). formula = 식(값을 채운 문자열), src = 근거 출처."""

    v: Any
    unit: str
    formula: str
    src: str
    reason: str = "산술"


@dataclass(frozen=True)
class U:
    """확인 불가(사유)."""

    reason: str


@dataclass(frozen=True)
class J:
    """판정기 값(라벨 추정, prov jl_<seq>)."""

    v: Any
    unit: str
    seq: int
    reason: str = "판정기"


Spec = S | D | U | J


@dataclass
class Source:
    key: str
    kind: str
    url: str
    title: str
    complex_id: int | None
    lines: list[str] = field(default_factory=list)
    offsets: dict[str, tuple[int, int]] = field(default_factory=dict)
    doc_id: int | None = None
    http_status: int | None = 200
    error_text: str | None = None

    @property
    def file_name(self) -> str:
        cid = f"{self.complex_id:02d}" if self.complex_id is not None else "region"
        return f"{KIND_DIR[self.kind]}/{cid}_{self.key}.txt"

    def header(self) -> str:
        return (
            f"# 재구성 발췌 — {self.title}\n"
            f"# 원문: {self.url}\n"
            "# 값은 docs/source/incheon_gimpo_report.md(확인일 2026-10-07)에 기재된 것만 옮겼다. 원문 PDF·페이지 그대로가 아니다.\n"
        )

    def add_line(self, text: str) -> tuple[int, int]:
        if text in self.offsets:
            return self.offsets[text]
        self.lines.append(text)
        body_before = self.header() + "".join(line + "\n" for line in self.lines[:-1])
        start = len(body_before)
        end = start + len(text)
        self.offsets[text] = (start, end)
        return start, end

    def text(self) -> str:
        return self.header() + "".join(line + "\n" for line in self.lines)


class Registry:
    """출처·원문 문서·provenance 행을 모은다. doc id는 9001부터, 생성 순서대로."""

    def __init__(self) -> None:
        self.sources: dict[tuple[int | None, str], Source] = {}
        self.provenance: list[dict[str, Any]] = []
        self.counters: dict[int | None, int] = {}
        self.extra_docs: list[dict[str, Any]] = []  # 실패 행·이미지·목록 등(텍스트 발췌 아님)
        self.files: dict[str, bytes] = {}  # raw/ 기준 경로 → 내용

    def source(self, cid: int | None, key: str, kind: str, url: str, title: str) -> Source:
        k = (cid, key)
        if k not in self.sources:
            self.sources[k] = Source(key=key, kind=kind, url=url, title=title, complex_id=cid)
        return self.sources[k]

    def get(self, cid: int | None, key: str) -> Source:
        return self.sources[(cid, key)]

    def next_prov(self, cid: int | None) -> str:
        n = self.counters.get(cid, 0) + 1
        self.counters[cid] = n
        scope = f"{cid}" if cid is not None else "r"
        return f"fp_{scope}_{n:03d}"

    def fact(self, cid: int | None, spec: Spec, entity: str, field_name: str) -> dict[str, Any]:
        if isinstance(spec, U):
            return {
                "v": None,
                "label": "확인 불가",
                "reason": spec.reason,
                "prov": None,
                "checked_at": CHECKED,
            }
        if isinstance(spec, J):
            return {"v": spec.v, "label": "추정", "reason": spec.reason, "prov": f"jl_{spec.seq}",
                    "checked_at": CHECKED, "unit": spec.unit}  # fmt: skip
        pid = self.next_prov(cid)
        if isinstance(spec, D):
            src = self.get(cid, spec.src)
            self.provenance.append(self._prov_row(pid, cid, entity, field_name, src, "추정", spec.reason,
                                                  spec.formula, None, formula=spec.formula))  # fmt: skip
            return {"v": spec.v, "label": "추정", "reason": spec.reason, "prov": pid, "checked_at": CHECKED,
                    "unit": spec.unit}  # fmt: skip
        src = self.get(cid, spec.src)
        label = spec.label or DEFAULT_LABEL[src.kind]
        span = src.add_line(spec.text)
        row = self._prov_row(pid, cid, entity, field_name, src, label, spec.reason, spec.text, span)
        if spec.compare is not None:
            row["compare_judgment_seq"] = spec.compare
            row["conflict_group"] = f"{entity}:{cid}:{field_name}"
        self.provenance.append(row)
        fact: dict[str, Any] = {"v": spec.v, "label": label}
        if spec.reason:
            fact["reason"] = spec.reason
        fact.update({"prov": pid, "checked_at": CHECKED, "unit": spec.unit})
        return fact

    def _prov_row(
        self,
        pid: str,
        cid: int | None,
        entity: str,
        field_name: str,
        src: Source,
        label: str,
        reason: str | None,
        excerpt: str,
        span: tuple[int, int] | None,
        formula: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": pid,
            "kind": "field",
            "entity": entity,
            "entity_id": cid if entity == "complex" else None,
            "field": field_name,
            "value_text": excerpt,
            "label": label,
            "reason": reason,
            "url": src.url,
            "checked_at": CHECKED,
            "excerpt": excerpt,
            "excerpt_start": span[0] if span else None,
            "excerpt_end": span[1] if span else None,
            "raw_document_id": None if span is None else -1,  # 문서 id는 finalize에서 채운다
            "source_kind": src.kind,
            "http_status": src.http_status,
            "source_rank": SOURCE_RANK.get(src.kind) if span else None,
            "chosen": True,
            "conflict_group": None,
            "conflicts": [],
            "formula_text": formula,
            "judgment_seq": None,
            "compare_judgment_seq": None,
            "_src": (src.complex_id, src.key),
        }

    def finalize_documents(self, start_id: int = 9001) -> list[dict[str, Any]]:
        """발췌가 있는 출처마다 txt 파일·RawDocument 행을 만들고 provenance에 문서 id를 채운다."""
        docs: list[dict[str, Any]] = []
        by_sha: dict[str, dict[str, Any]] = {}
        next_id = start_id
        for src in self.sources.values():
            if not src.lines:
                continue
            data = src.text().encode("utf-8")
            sha = sha256_hex(data)
            if sha in by_sha:  # 같은 원문(여러 단지가 공유) = 한 행(sha256 유일), 단지 귀속 없음
                shared = by_sha[sha]
                shared["complex_id"] = None
                src.doc_id = shared["id"]
                continue
            self.files[src.file_name] = data
            src.doc_id = next_id
            next_id += 1
            doc = raw_doc(src.doc_id, src.kind, src.url, src.file_name, data, src.complex_id)
            by_sha[sha] = doc
            docs.append(doc)
        for extra in self.extra_docs:
            extra["id"] = next_id
            next_id += 1
            docs.append(extra)
        for row in self.provenance:
            key = row.pop("_src")
            if row["raw_document_id"] == -1:
                row["raw_document_id"] = self.sources[key].doc_id
        return docs


def raw_doc(
    doc_id: int | None,
    kind: str,
    url: str,
    path: str | None,
    data: bytes | None,
    complex_id: int | None,
    *,
    http_status: int | None = 200,
    error_text: str | None = None,
    fetched_at: str = FETCHED_AT,
    content_type: str | None = "text/plain; charset=utf-8",
    image_hash: str | None = None,
    text_path: str | None = "same",
) -> dict[str, Any]:
    """RawDocument 행. 실패 행(data=None)의 sha256 = sha256('fail:'+url+':'+상태+':'+날짜) (raw_document.json)."""
    if data is None:
        status = str(http_status) if http_status is not None else (error_text or "error")
        sha = sha256_hex(f"fail:{url}:{status}:{fetched_at[:10]}".encode())
        path = None
        content_type = None
        text_path = None
    else:
        sha = sha256_hex(data)
    return {
        "id": doc_id,
        "source_kind": kind,
        "url": url,
        "fetched_at": fetched_at,
        "http_status": http_status,
        "sha256": sha,
        "path": path,
        "content_type": content_type,
        "text_path": path if text_path == "same" else text_path,
        "complex_id": complex_id,
        "region_id": 1,
        "error_text": error_text,
        "image_hash": image_hash,
    }


def png_bytes(width: int, height: int, rgb: tuple[int, int, int], stripe: tuple[int, int, int]) -> bytes:
    """의존성 없는 작은 PNG(팝업 스크린샷 대용, T8). 같은 인자 = 같은 바이트."""
    import struct
    import zlib

    rows = b""
    for y in range(height):
        row = b"\x00"
        for x in range(width):
            row += bytes(stripe if (x + y) % 7 == 0 else rgb)
        rows += row

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )
