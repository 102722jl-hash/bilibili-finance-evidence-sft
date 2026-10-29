"""Manifest parsing and intake validation for the 10-video sample."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


EXPECTED_AUTHOR_MID = "472747194"
OFFICIAL_ARTICLE_HOSTS = {"mp.weixin.qq.com", "new.qq.com"}
MANIFEST_FIELDS = [
    "bvid", "title", "video_url", "author_mid", "article_url", "discovery_source",
    "text_source", "selection_status", "selection_rationale",
]


@dataclass(frozen=True)
class ManifestRecord:
    bvid: str
    title: str
    video_url: str
    author_mid: str
    article_url: str
    discovery_source: str
    text_source: str
    selection_status: str
    selection_rationale: str


def validate_manifest(path: str | Path) -> list[ManifestRecord]:
    with Path(path).open(newline="", encoding="utf8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != MANIFEST_FIELDS:
            raise ValueError(f"manifest headers must be {','.join(MANIFEST_FIELDS)}")
        records = [ManifestRecord(**row) for row in reader]

    errors: list[str] = []
    if len(records) != 10:
        errors.append(f"expected exactly 10 rows, got {len(records)}")
    if len({record.bvid for record in records}) != len(records):
        errors.append("bvid values must be unique")
    if len({record.title for record in records}) != len(records):
        errors.append("title values must be unique")
    for line_number, record in enumerate(records, start=2):
        if record.author_mid != EXPECTED_AUTHOR_MID:
            errors.append(f"line {line_number}: author_mid must be {EXPECTED_AUTHOR_MID}")
        if not record.selection_rationale.strip():
            errors.append(f"line {line_number}: selection_rationale is required")
        if record.bvid not in record.video_url:
            errors.append(f"line {line_number}: video_url does not match bvid")
        if record.article_url:
            parsed = urlparse(record.article_url)
            if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_ARTICLE_HOSTS:
                errors.append(f"line {line_number}: article_url host is not an approved official channel")
    if errors:
        raise ValueError("; ".join(errors))
    return records
