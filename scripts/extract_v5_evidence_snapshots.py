"""Extract reviewable text and candidate locators from V5 controlled snapshots."""

from __future__ import annotations

import argparse
import difflib
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from pypdf import PdfReader


class BlockParser(HTMLParser):
    BLOCKS = {"article", "div", "h1", "h2", "h3", "h4", "li", "p", "section", "td", "th"}

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self.current: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag in self.BLOCKS and self.current:
            self.flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1
        if tag in self.BLOCKS:
            self.flush()

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            value = re.sub(r"\s+", " ", html.unescape(data)).strip()
            if value:
                self.current.append(value)

    def flush(self) -> None:
        value = re.sub(r"\s+", " ", " ".join(self.current)).strip()
        if len(value) >= 8:
            self.blocks.append(value)
        self.current = []


def json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def decode_html(data: bytes) -> str:
    head = data[:4096].decode("ascii", errors="ignore")
    match = re.search(r"charset\s*=\s*[\"']?([\w-]+)", head, re.IGNORECASE)
    candidates = [match.group(1)] if match else []
    candidates.extend(["utf-8", "gb18030"])
    best = ""
    best_errors = 10**9
    for encoding in candidates:
        try:
            text = data.decode(encoding, errors="replace")
        except LookupError:
            continue
        errors = text.count("\ufffd")
        if errors < best_errors:
            best, best_errors = text, errors
    return best


def html_blocks(path: Path) -> list[dict[str, Any]]:
    parser = BlockParser()
    parser.feed(decode_html(path.read_bytes()))
    parser.flush()
    seen: set[str] = set()
    rows = []
    for block in parser.blocks:
        if block in seen:
            continue
        seen.add(block)
        rows.append({"locator": f"html_block:{len(rows) + 1}", "text": block})
    return rows


def pdf_blocks(path: Path) -> list[dict[str, Any]]:
    reader = PdfReader(str(path))
    rows = []
    for page_no, page in enumerate(reader.pages, 1):
        text = re.sub(r"[ \t]+", " ", page.extract_text() or "")
        paragraphs = [re.sub(r"\s+", " ", row).strip() for row in re.split(r"\n{2,}|(?<=。)\s*", text)]
        paragraphs = [row for row in paragraphs if len(row) >= 8]
        if not paragraphs and text.strip():
            paragraphs = [re.sub(r"\s+", " ", text).strip()]
        for paragraph_no, paragraph in enumerate(paragraphs, 1):
            rows.append({"locator": f"pdf_page:{page_no}:paragraph:{paragraph_no}", "text": paragraph})
    return rows


def normalized(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff%]+", "", value).lower()


def best_matches(registered_quote: str, blocks: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    target = normalized(registered_quote)
    matches = []
    for block in blocks:
        candidate = normalized(block["text"])
        if not candidate:
            continue
        score = difflib.SequenceMatcher(None, target, candidate).ratio()
        if target and target in candidate:
            score = 1.0
        matches.append({**block, "similarity": round(score, 4)})
    return sorted(matches, key=lambda row: (-row["similarity"], row["locator"]))[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquisition", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.acquisition.read_text(encoding="utf-8").splitlines() if line.strip()]
    cache: dict[str, list[dict[str, Any]]] = {}
    output = []
    for record in records:
        if record.get("acquisition_status") != "ACQUIRED":
            output.append({**record, "extraction_status": "NOT_ACQUIRED", "candidate_matches": []})
            continue
        path = Path(record["snapshot_path"])
        cache_key = record["snapshot_sha256"]
        if cache_key not in cache:
            try:
                cache[cache_key] = pdf_blocks(path) if path.suffix.lower() == ".pdf" else html_blocks(path)
            except Exception as exc:
                output.append(
                    {
                        **record,
                        "extraction_status": "EXTRACT_ERROR",
                        "extraction_error": f"{type(exc).__name__}: {exc}",
                        "candidate_matches": [],
                    }
                )
                continue
            extracted_path = path.with_suffix(path.suffix + ".txt")
            extracted_path.write_text(
                "\n\n".join(f"[{row['locator']}]\n{row['text']}" for row in cache[cache_key]),
                encoding="utf-8",
            )
        matches = best_matches(record.get("registered_quote", ""), cache[cache_key])
        output.append(
            {
                **record,
                "extraction_status": "EXTRACTED" if cache[cache_key] else "NO_TEXT",
                "extracted_block_count": len(cache[cache_key]),
                "candidate_matches": matches,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json_line(row) + "\n" for row in output), encoding="utf-8")
    statuses: dict[str, int] = {}
    for row in output:
        status = row["extraction_status"]
        statuses[status] = statuses.get(status, 0) + 1
    print(json.dumps({"records": len(output), "statuses": statuses}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
