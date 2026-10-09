"""프론트 없이 보고서 만들기 (meta §2-8, DECISIONS D4).

    python -m app.reports.cli --snapshot 12 --format pdf [--compare 11] [--scenario 2] [--out DIR]

종료 코드: 0 성공(경로를 stdout 에), 2 스냅샷·시나리오 없음, 3 contradicted 주장으로 거부, 1 그 밖의 오류.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from app.core.db import get_session
from app.reports.errors import ReportBlocked, ReportNotFound
from app.reports.export import generate

__all__ = ["main"]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.reports.cli", description="스냅샷 보고서(HTML·PDF) 생성")
    p.add_argument("--snapshot", type=int, required=True, help="스냅샷 id")
    p.add_argument("--format", choices=("html", "pdf"), default="html")
    p.add_argument("--compare", type=int, default=None, help="비교(이전) 스냅샷 id — diff 장")
    p.add_argument("--scenario", type=int, default=None, help="본문 점수표 시나리오 id(기본 = base)")
    p.add_argument("--out", type=Path, default=None, help="출력 디렉터리(기본 REPORT_DIR)")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        with get_session() as session:
            rep = generate(
                session,
                args.snapshot,
                args.format,
                compare_snapshot_id=args.compare,
                scenario_id=args.scenario,
                out_dir=args.out,
            )
    except ReportNotFound as exc:
        print(f"없음: {exc.reason}", file=sys.stderr)
        return 2
    except ReportBlocked as exc:
        print(f"생성 거부: {exc.reason}", file=sys.stderr)
        return 3
    print(rep.path)
    if not rep.charts_inlined:
        print("경고: ECharts 번들을 찾지 못해 차트 없이 표만 넣었다(REPORT_ECHARTS_JS)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
