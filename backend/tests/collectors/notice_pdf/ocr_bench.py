"""OCR 후보 벤치마크 도구 (DECISIONS D5, docs/adr/ADR-12-ocr.md). 테스트가 아니라 사람이 돌리는 도구다.

1) 시료 만들기 (프로젝트 venv — pdfplumber·pypdfium2):
   uv run python tests/collectors/notice_pdf/ocr_bench.py make-samples <pdf 파일:0부터 센 쪽> ...
   → contracts/fixtures/ocr_samples/sample_NN.png (200dpi 회색조) + .txt(텍스트 레이어 = 정답) + manifest.json
     (채점 대상 = 가격표 숫자 토큰: 금액 1,234,567 · 주택형 084.9766C · 층 32층/16~20층 · 소수 59.92)

2) 측정 (후보마다 **별도 임시 venv** — 프로젝트 .venv 오염 금지):
   <venv>/python ocr_bench.py run <engine> [--samples DIR] [--out result.json]
   engine: rapidocr | paddleocr | easyocr | surya | tesseract
   이 단계는 표준 라이브러리 + Pillow + 후보 엔진만 쓴다.

채점: 정답 숫자 토큰 각각이 OCR 출력 숫자 토큰(같은 정규식)에 그대로 있으면 일치(중복은 개수만큼).
문자 정확도 = 1 − Σ(정답 토큰과 가장 가까운 미사용 OCR 토큰의 편집 거리) / Σ(정답 토큰 길이).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
SAMPLES = ROOT / "contracts" / "fixtures" / "ocr_samples"
DPI = 200
NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+|\d{3}\.\d{2,4}[A-Z]?|\d+(?:~\d+)?층|\d+\.\d+")


def numbers(text: str) -> list[str]:
    return NUM_RE.findall(text.replace(" ,", ",").replace(", ", ","))


def _edit(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def score(truth: list[str], got: list[str]) -> dict[str, Any]:
    pool = Counter(got)
    exact = 0
    missing: list[str] = []
    for t in truth:
        if pool[t] > 0:
            pool[t] -= 1
            exact += 1
        else:
            missing.append(t)
    rest = list(pool.elements())
    errors = 0
    for t in missing:
        if not rest:
            errors += len(t)
            continue
        best = min(range(len(rest)), key=lambda k: _edit(t, rest[k]))
        errors += min(len(t), _edit(t, rest[best]))
        rest.pop(best)
    total_chars = sum(len(t) for t in truth) or 1
    return {
        "tokens": len(truth),
        "exact": exact,
        "token_recall": exact / len(truth) if truth else 1.0,
        "char_accuracy": 1 - errors / total_chars,
        "missing": missing[:20],
    }


# --- 시료 만들기 -------------------------------------------------------------------------------
def make_samples(specs: list[str], out: Path) -> None:
    import pdfplumber
    import pypdfium2 as pdfium

    out.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    for n, spec in enumerate(specs, 1):
        path_s, _, page_s = spec.rpartition(":")
        source, page = Path(path_s), int(page_s)
        with pdfplumber.open(source) as pdf:
            text = pdf.pages[page].extract_text() or ""
        image = pdfium.PdfDocument(str(source))[page].render(scale=DPI / 72).to_pil().convert("L")
        stem = f"sample_{n:02d}"
        image.save(out / f"{stem}.png", optimize=True)
        (out / f"{stem}.txt").write_text(text + "\n", encoding="utf-8")
        manifest.append(
            {
                "image": f"{stem}.png",
                "truth_text": f"{stem}.txt",
                "source_pdf": source.name,
                "page": page + 1,
                "dpi": DPI,
                "numbers": numbers(text),
            }
        )
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


# --- 엔진 -------------------------------------------------------------------------------------
def _ocr_rapidocr(path: Path) -> str:
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

    # rapidocr 3.10 기본 인식기(PP-OCRv6 small)는 한국어가 없다 → 인식기만 PP-OCRv5 korean mobile
    params = {
        "Rec.lang_type": LangRec.KOREAN,
        "Rec.ocr_version": OCRVersion.PPOCRV5,
        "Rec.model_type": ModelType.MOBILE,
    }
    engine = _cache("rapidocr", lambda: RapidOCR(params=params))
    result = engine(str(path))
    return "\n".join(result.txts or [])


def _ocr_paddleocr(path: Path) -> str:
    from paddleocr import PaddleOCR

    engine = _cache(
        "paddleocr",
        lambda: PaddleOCR(
            # 검출은 CPU 용 mobile(기본 server 검출은 이 PC 에서 페이지당 수 분), 인식은 PP-OCRv5 korean
            text_detection_model_name=os.environ.get("PADDLE_DET", "PP-OCRv5_mobile_det"),
            text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            # paddlepaddle 3.x Windows CPU: oneDNN 경로가 PP-OCRv5 에서 NotImplementedError → 끈다
            enable_mkldnn=False,
        ),
    )
    lines: list[str] = []
    for res in engine.predict(str(path)):
        lines.extend(res["rec_texts"])
    return "\n".join(lines)


def _ocr_easyocr(path: Path) -> str:
    import easyocr

    reader = _cache("easyocr", lambda: easyocr.Reader(["ko", "en"], gpu=False))
    return "\n".join(str(t) for t in reader.readtext(str(path), detail=0, paragraph=False))


def _ocr_surya(path: Path) -> str:
    from PIL import Image
    from surya.detection import DetectionPredictor
    from surya.foundation import FoundationPredictor
    from surya.recognition import RecognitionPredictor

    def build() -> tuple[Any, Any]:
        return RecognitionPredictor(FoundationPredictor()), DetectionPredictor()

    rec, det = _cache("surya", build)
    preds = rec([Image.open(path).convert("RGB")], det_predictor=det)
    return "\n".join(line.text for line in preds[0].text_lines)


def _ocr_tesseract(path: Path) -> str:
    import pytesseract
    from PIL import Image

    # Tesseract 는 pip 로 설치되지 않는 별도 실행 파일이다(TESSERACT_CMD, TESSDATA_PREFIX 로 위치 지정)
    pytesseract.pytesseract.tesseract_cmd = os.environ.get("TESSERACT_CMD", "tesseract")
    return str(pytesseract.image_to_string(Image.open(path), lang="kor+eng", config="--psm 6"))


ENGINES = {
    "rapidocr": _ocr_rapidocr,
    "paddleocr": _ocr_paddleocr,
    "easyocr": _ocr_easyocr,
    "surya": _ocr_surya,
    "tesseract": _ocr_tesseract,
}
_CACHE: dict[str, Any] = {}


def _cache(key: str, factory: Any) -> Any:
    if key not in _CACHE:
        _CACHE[key] = factory()
    return _CACHE[key]


def run(engine: str, samples: Path, out: Path | None) -> dict[str, Any]:
    fn = ENGINES[engine]
    manifest = json.loads((samples / "manifest.json").read_text(encoding="utf-8"))
    t0 = time.perf_counter()
    fn(samples / manifest[0]["image"])  # 모델 적재·워밍업은 페이지 시간에서 뺀다
    warmup = time.perf_counter() - t0
    rows = []
    for item in manifest:
        t = time.perf_counter()
        text = fn(samples / item["image"])
        seconds = time.perf_counter() - t
        s = score(item["numbers"], numbers(text))
        rows.append({"image": item["image"], "seconds": round(seconds, 2), **s, "ocr_text": text})
        print(
            f"{engine} {item['image']}: {s['exact']}/{s['tokens']}"
            f" char={s['char_accuracy']:.4f} {seconds:.1f}s"
        )
    tokens = sum(r["tokens"] for r in rows)
    summary = {
        "engine": engine,
        "warmup_s": round(warmup, 1),
        "max_page_s": max(r["seconds"] for r in rows),
        "mean_page_s": round(sum(r["seconds"] for r in rows) / len(rows), 2),
        "token_recall": sum(r["exact"] for r in rows) / tokens,
        "char_accuracy": sum(r["char_accuracy"] * r["tokens"] for r in rows) / tokens,
        "all_numbers_exact": all(r["exact"] == r["tokens"] for r in rows),
        "pages": rows,
    }
    if out is not None:
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make-samples")
    mk.add_argument("specs", nargs="+")
    mk.add_argument("--out", type=Path, default=SAMPLES)
    rn = sub.add_parser("run")
    rn.add_argument("engine", choices=sorted(ENGINES))
    rn.add_argument("--samples", type=Path, default=SAMPLES)
    rn.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "make-samples":
        make_samples(args.specs, args.out)
    else:
        run(args.engine, args.samples, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
