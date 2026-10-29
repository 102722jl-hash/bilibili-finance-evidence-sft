"""Acquire immutable snapshots for curated V5 evidence-expansion candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def extension(content_type: str, url: str) -> str:
    if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        return ".pdf"
    guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
    return guessed if guessed in {".html", ".htm", ".txt", ".json", ".xml"} else ".bin"


def fetch(candidate: dict[str, Any], snapshots: Path) -> dict[str, Any]:
    requested_url = candidate["source_url"]
    request = urllib.request.Request(
        requested_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; EvidenceChainResearch/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,text/plain;q=0.9,*/*;q=0.5",
        },
    )
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read()
            status = getattr(response, "status", 200)
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "application/octet-stream")
    except urllib.error.HTTPError as exc:
        return {
            **candidate,
            "acquisition_status": "HTTP_ERROR",
            "http_status": exc.code,
            "retrieved_at": retrieved_at,
            "error": str(exc),
        }
    except Exception as exc:
        return {
            **candidate,
            "acquisition_status": "FETCH_ERROR",
            "retrieved_at": retrieved_at,
            "error": f"{type(exc).__name__}: {exc}",
        }

    digest = hashlib.sha256(body).hexdigest()
    suffix = extension(content_type, final_url)
    snapshot_path = snapshots / f"{digest}{suffix}"
    if not snapshot_path.exists():
        snapshot_path.write_bytes(body)
    return {
        **candidate,
        "acquisition_status": "ACQUIRED" if status == 200 and body else "INVALID_RESPONSE",
        "http_status": status,
        "final_url": final_url,
        "content_type": content_type,
        "retrieved_at": retrieved_at,
        "response_bytes": len(body),
        "snapshot_sha256": digest,
        "snapshot_path": snapshot_path.as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    candidates = config.get("sources", [])
    if len({row["candidate_id"] for row in candidates}) != len(candidates):
        raise ValueError("duplicate candidate_id")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    snapshots = args.out_dir / "snapshots"
    snapshots.mkdir(exist_ok=True)
    records = []
    for candidate in sorted(candidates, key=lambda row: row["candidate_id"]):
        records.append(fetch(candidate, snapshots))
        time.sleep(0.5)
    output = args.out_dir / "expansion_acquisition_records.jsonl"
    history = []
    if output.exists():
        history = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line.strip()]
    merged = history + records
    seen: set[tuple[str, str, str]] = set()
    attempts = []
    for row in merged:
        key = (row["candidate_id"], row["source_url"], row["retrieved_at"])
        if key not in seen:
            seen.add(key)
            attempts.append(row)
    output.write_text("".join(json_line(row) + "\n" for row in attempts), encoding="utf-8")
    counts: dict[str, int] = {}
    for row in records:
        counts[row["acquisition_status"]] = counts.get(row["acquisition_status"], 0) + 1
    print(json.dumps({"records": len(records), "statuses": counts}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
