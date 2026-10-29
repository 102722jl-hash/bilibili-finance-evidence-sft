"""Command-line entry point for the evidence-chain pipeline."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .report import export_csv, load_graph, render_report
from .sources.bilibili import fetch_public_video


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-chain")
    subparsers = parser.add_subparsers(dest="command")
    collect_parser = subparsers.add_parser("collect", help="collect public source snapshots")
    collect_parser.add_argument("--video-url", required=True)
    collect_parser.add_argument("--out", default="data")
    subparsers.add_parser("extract", help="extract claims from collected sources")
    report_parser = subparsers.add_parser("report", help="render an evidence-chain report")
    report_parser.add_argument("--video-id", required=True)
    report_parser.add_argument("--db", required=True)
    report_parser.add_argument("--out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        raise
    if args.command == "collect":
        record = fetch_public_video(args.video_url, args.out)
        print(json.dumps(asdict(record), ensure_ascii=False))
    elif args.command == "report":
        graph = load_graph(args.db, args.video_id)
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_report(graph), encoding="utf8")
        export_csv(graph, out_path.parent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
