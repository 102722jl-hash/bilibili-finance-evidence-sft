"""Acquire controlled snapshots for the external URLs already registered in V5."""

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


def registered_urls(source: Path) -> list[dict[str, Any]]:
    rows = json.loads(source.read_text(encoding="utf-8"))
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        metadata = row["metadata"]
        if metadata["dataset_version"] != "5.0.0":
            continue
        context = metadata["ui_audit_context"]
        for evidence in context.get("claim_level_evidence", []):
            if not evidence.get("source_url") or evidence.get("source_tier") == "AUTHOR":
                continue
            evidence_id = evidence["evidence_id"]
            candidate = {
                "case_id": metadata["case_id"],
                "evidence_id": evidence_id,
                "target_ref": evidence.get("target_ref"),
                "registered_source_tier": evidence.get("source_tier"),
                "source_url": evidence["source_url"],
                "registered_locator": evidence.get("locator"),
                "registered_quote": evidence.get("original_quote"),
            }
            previous = by_id.setdefault(evidence_id, candidate)
            if previous != candidate:
                raise ValueError(f"{evidence_id}: conflicting registered evidence")
    return [by_id[key] for key in sorted(by_id)]


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
        with urllib.request.urlopen(request, timeout=30) as response:
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
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    snapshots = args.out_dir / "snapshots"
    snapshots.mkdir(exist_ok=True)
    output = []
    cache: dict[str, dict[str, Any]] = {}
    for candidate in registered_urls(args.source):
        url = candidate["source_url"]
        if url not in cache:
            cache[url] = fetch(candidate, snapshots)
            time.sleep(0.5)
        acquired = cache[url]
        output.append(
            {
                **candidate,
                **{key: value for key, value in acquired.items() if key not in candidate},
            }
        )
    path = args.out_dir / "acquisition_records.jsonl"
    path.write_text("".join(json_line(row) + "\n" for row in output), encoding="utf-8")
    counts: dict[str, int] = {}
    for row in output:
        status = row["acquisition_status"]
        counts[status] = counts.get(status, 0) + 1
    print(json.dumps({"records": len(output), "statuses": counts}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
