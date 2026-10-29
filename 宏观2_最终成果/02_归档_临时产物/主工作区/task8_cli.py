"""Command-line entry point for the evidence-chain pipeline."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from .manifest import EXPECTED_AUTHOR_MID, validate_manifest
from .report import export_csv, load_graph, render_report
from .sources.bilibili import fetch_public_video


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-chain")
    subparsers = parser.add_subparsers(dest="command")
    collect_parser = subparsers.add_parser("collect", help="collect public source snapshots")
    collect_group = collect_parser.add_mutually_exclusive_group(required=True)
    collect_group.add_argument("--video-url")
    collect_group.add_argument("--manifest")
    collect_parser.add_argument("--out", default="data")
    subparsers.add_parser("extract", help="extract claims from collected sources")
    report_parser = subparsers.add_parser("report", help="render an evidence-chain report")
    report_parser.add_argument("--video-id", required=True)
    report_parser.add_argument("--db", required=True)
    report_parser.add_argument("--out", required=True)
    manifest_parser = subparsers.add_parser("validate-manifest", help="validate the 10-video intake manifest")
    manifest_parser.add_argument("--manifest", required=True)
    return parser


def _write_videos(records, out_dir: str | Path) -> Path:
    path = Path(out_dir) / "videos.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["bvid", "title", "author_mid", "author_name", "url", "published_at", "retrieved_at", "raw_sha256"]
    with path.open("w", newline="", encoding="utf8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: getattr(record, field) for field in fields} for record in records)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        raise
    if args.command == "collect":
        records = []
        if args.video_url:
            records.append(fetch_public_video(args.video_url, args.out))
        else:
            for manifest_record in validate_manifest(args.manifest):
                record = fetch_public_video(manifest_record.video_url, args.out)
                if record.author_mid != EXPECTED_AUTHOR_MID or record.bvid != manifest_record.bvid:
                    raise ValueError(f"collected metadata mismatch for {manifest_record.bvid}")
                records.append(record)
        _write_videos(records, args.out)
        for record in records:
            print(json.dumps(asdict(record), ensure_ascii=False))
    elif args.command == "validate-manifest":
        records = validate_manifest(args.manifest)
        print(f"valid manifest: {len(records)} videos; author_mid={EXPECTED_AUTHOR_MID}")
    elif args.command == "report":
        graph = load_graph(args.db, args.video_id)
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_report(graph), encoding="utf8")
        export_csv(graph, out_path.parent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
