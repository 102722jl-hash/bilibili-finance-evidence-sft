"""Build the first-round V6 SFT candidate from the merged V4.1/V5 audit export."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "auditable-sft/6.0-first-round"
ANSWERABILITY_PREFIX = re.compile(r"^可回答性目标：.*(?:\r?\n)?", re.MULTILINE)
REQUIRED_CITATION_FIELDS = (
    "evidence_id",
    "source_id",
    "source_url",
    "locator",
    "source_tier",
    "content_sha256",
    "snapshot_sha256",
)


def json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("input must be a JSON array")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json_line(row) + "\n" for row in rows), encoding="utf-8")


def message(record: dict[str, Any], role: str) -> dict[str, Any]:
    return next(item for item in record["messages"] if item["role"] == role)


def evidence_index(audit_context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["evidence_id"]: row
        for row in audit_context.get("claim_level_evidence", [])
        if row.get("evidence_id")
    }


def enrich_citations(record: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = record["metadata"]
    index = evidence_index(metadata["ui_audit_context"])
    citations = []
    for source_record in metadata.get("source_records", []):
        evidence = index.get(source_record.get("evidence_id"), {})
        citations.append(
            {
                "evidence_id": source_record.get("evidence_id"),
                "source_id": source_record.get("source_id") or evidence.get("source_id"),
                "source_url": source_record.get("source_url") or evidence.get("source_url"),
                "locator": source_record.get("locator") or evidence.get("locator"),
                "source_tier": evidence.get("source_tier"),
                "temporal_role": evidence.get("temporal_role"),
                "content_sha256": evidence.get("content_sha256"),
                "snapshot_sha256": evidence.get("snapshot_sha256"),
                "acceptance_status": evidence.get("acceptance_status"),
                "coverage": evidence.get("coverage"),
                "stance": evidence.get("stance"),
                "target_ref": evidence.get("target_ref"),
            }
        )
    return citations


def citation_passes_gate(citation: dict[str, Any]) -> bool:
    return (
        citation.get("acceptance_status") == "ACCEPTED"
        and citation.get("source_tier") in {"T1", "T2"}
        and all(citation.get(field) for field in REQUIRED_CITATION_FIELDS)
    )


def release_partition(record: dict[str, Any], citations: list[dict[str, Any]]) -> tuple[str, list[str]]:
    if record["metadata"]["truth_scope"] == "author_trace":
        return "candidate", []
    if not citations:
        return "audit_only", ["WORLD_EVIDENCE_NO_TRACEABLE_CITATION"]
    if not all(citation_passes_gate(citation) for citation in citations):
        return "audit_only", ["WORLD_EVIDENCE_CITATION_GATE_INCOMPLETE"]
    return "candidate", []


def cleaned_user(record: dict[str, Any]) -> str:
    content = message(record, "user")["content"]
    cleaned = ANSWERABILITY_PREFIX.sub("", content)
    cleaned = cleaned.replace("推理任务：因果归因拒答", "推理任务：因果归因评估")
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def assistant_payload(record: dict[str, Any], citations: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = record["metadata"]
    answerability = metadata["rule_state"]
    original = metadata["final_result"]["direct_answer"]
    return {
        "answerability": answerability,
        "direct_answer": "ABSTAIN" if answerability == "unanswerable" else original,
        "local_reasoning_path": metadata["premise_chain_v41"],
        "verification": metadata["verification"],
        "uncertainty_note": metadata["uncertainty_note"],
        "missing_evidence": metadata.get("missing_evidence", []),
        "citations": citations,
    }


def project_record(record: dict[str, Any], audit_context_id: str) -> dict[str, Any]:
    metadata = record["metadata"]
    citations = enrich_citations(record)
    partition, reasons = release_partition(record, citations)
    payload = assistant_payload(record, citations)
    return {
        "id": record["id"],
        "messages": [
            message(record, "system"),
            {"role": "user", "content": cleaned_user(record)},
            {"role": "assistant", "content": json_line(payload)},
        ],
        "metadata": {
            "schema_version": SCHEMA_VERSION,
            "case_id": metadata["case_id"],
            "event_cluster_id": metadata["event_cluster_id"],
            "analysis_as_of": metadata["analysis_as_of"],
            "question_role": metadata["logic_key"],
            "truth_scope": metadata["truth_scope"],
            "user_intent": metadata["user_intent"],
            "answerability": metadata["rule_state"],
            "source_dataset_version": metadata["dataset_version"],
            "derived_from_qa_id": metadata["derived_from_qa_id"],
            "source_split": metadata["split"],
            "release_partition": partition,
            "audit_only_reasons": reasons,
            "audit_context_id": audit_context_id,
            "citation_count": len(citations),
        },
    }


def build_audit_contexts(source_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    by_case: dict[str, dict[str, Any]] = {}
    context_ids: dict[str, str] = {}
    for record in source_rows:
        metadata = record["metadata"]
        case_id = metadata["case_id"]
        context_id = f"AUDIT-V6R1-{case_id}"
        context_ids[case_id] = context_id
        candidate = {
            "audit_context_id": context_id,
            "schema_version": "case-audit-context/6.0-first-round",
            "case_id": case_id,
            "event_cluster_id": metadata["event_cluster_id"],
            "source_dataset_version": metadata["dataset_version"],
            "training_visibility": "excluded_from_messages",
            "audit_context": metadata["ui_audit_context"],
        }
        previous = by_case.setdefault(case_id, candidate)
        if json_line(previous) != json_line(candidate):
            raise ValueError(f"{case_id}: inconsistent repeated audit context")
    return [by_case[key] for key in sorted(by_case)], context_ids


def validate_records(records: list[dict[str, Any]], audit_contexts: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    context_ids = {row["audit_context_id"] for row in audit_contexts}
    if len(records) != 180 or len({row["id"] for row in records}) != 180:
        errors.append("expected 180 unique QA records")
    if len(audit_contexts) != 20 or len(context_ids) != 20:
        errors.append("expected 20 unique case audit contexts")

    for record in records:
        record_id = record["id"]
        roles = [item.get("role") for item in record.get("messages", [])]
        if roles != ["system", "user", "assistant"]:
            errors.append(f"{record_id}: invalid message roles")
            continue
        user = message(record, "user")["content"]
        if "可回答性目标：" in user:
            errors.append(f"{record_id}: answerability leaked into user input")
        try:
            assistant = json.loads(message(record, "assistant")["content"])
        except json.JSONDecodeError:
            errors.append(f"{record_id}: assistant is not valid JSON")
            continue
        required = {
            "answerability",
            "direct_answer",
            "local_reasoning_path",
            "verification",
            "uncertainty_note",
            "missing_evidence",
            "citations",
        }
        if set(assistant) != required:
            errors.append(f"{record_id}: invalid assistant contract")
        if assistant.get("answerability") == "unanswerable" and assistant.get("direct_answer") != "ABSTAIN":
            errors.append(f"{record_id}: refusal protocol is inconsistent")
        path = assistant.get("local_reasoning_path", [])
        if not 1 <= len(path) <= 4:
            errors.append(f"{record_id}: local path length is outside 1-4")
        metadata = record["metadata"]
        if metadata.get("audit_context_id") not in context_ids:
            errors.append(f"{record_id}: unresolved audit context")
        if "ui_audit_context" in metadata or "premise_chain_v41" in metadata:
            errors.append(f"{record_id}: legacy audit payload remains in QA metadata")
        if metadata.get("release_partition") == "candidate" and metadata.get("truth_scope") == "world_evidence":
            if not assistant.get("citations") or not all(citation_passes_gate(row) for row in assistant["citations"]):
                errors.append(f"{record_id}: candidate world-evidence record failed citation gate")
        if metadata.get("release_partition") == "audit_only" and not metadata.get("audit_only_reasons"):
            errors.append(f"{record_id}: audit-only reason missing")

    counts = {
        "records": len(records),
        "case_audit_contexts": len(audit_contexts),
        "release_partition": dict(Counter(row["metadata"]["release_partition"] for row in records)),
        "source_split": dict(Counter(row["metadata"]["source_split"] for row in records)),
        "candidate_split": dict(
            Counter(
                row["metadata"]["source_split"]
                for row in records
                if row["metadata"]["release_partition"] == "candidate"
            )
        ),
        "truth_scope": dict(Counter(row["metadata"]["truth_scope"] for row in records)),
        "answerability": dict(Counter(row["metadata"]["answerability"] for row in records)),
    }
    return {"schema_version": SCHEMA_VERSION, "errors": errors, "warnings": [], "counts": counts}


def build_release(source: Path, out_dir: Path) -> dict[str, Any]:
    source_rows = read_json(source)
    audit_contexts, context_ids = build_audit_contexts(source_rows)
    records = [
        project_record(record, context_ids[record["metadata"]["case_id"]])
        for record in source_rows
    ]
    records.sort(key=lambda row: row["id"])
    report = validate_records(records, audit_contexts)
    if report["errors"]:
        raise ValueError("; ".join(report["errors"][:10]))

    out_dir.mkdir(parents=True, exist_ok=True)
    all_path = out_dir / "qa_records.jsonl"
    context_path = out_dir / "case_audit_contexts.jsonl"
    train_path = out_dir / "train.jsonl"
    validation_path = out_dir / "validation.jsonl"
    audit_only_path = out_dir / "audit_only.jsonl"
    report_path = out_dir / "validation_report.json"
    card_path = out_dir / "DATASET_CARD.md"

    candidate = [row for row in records if row["metadata"]["release_partition"] == "candidate"]
    audit_only = [row for row in records if row["metadata"]["release_partition"] == "audit_only"]
    write_jsonl(all_path, records)
    write_jsonl(context_path, audit_contexts)
    write_jsonl(train_path, [row for row in candidate if row["metadata"]["source_split"] == "train"])
    write_jsonl(validation_path, [row for row in candidate if row["metadata"]["source_split"] == "validation"])
    write_jsonl(audit_only_path, audit_only)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    card_path.write_text(
        "# V6 第一轮可审计 SFT 候选集\n\n"
        "本目录由 V4.1/V5 合并审计导出确定性派生，不覆盖原始数据。当前状态为 "
        "`NEEDS_HUMAN_REVIEW`，不是正式发布版。\n\n"
        "## 训练入口\n\n"
        "- `train.jsonl`：唯一训练入口，只读取每行的 `messages`。\n"
        "- `validation.jsonl`：验证入口，不得加入训练。\n"
        "- `audit_only.jsonl`：证据门禁未闭合，只用于补证和人工审核。\n"
        "- `qa_records.jsonl`：180 条完整索引，不得默认整体训练。\n"
        "- `case_audit_contexts.jsonl`：案例级完整母图，不进入模型消息。\n\n"
        "## 第一轮调整\n\n"
        "1. 训练输入不再包含可回答性目标。\n"
        "2. Assistant 统一输出结构化 JSON；不可回答时 `direct_answer=ABSTAIN`。\n"
        "3. 案例母图按案例去重，通过 `audit_context_id` 关联。\n"
        "4. 现实证据题只有在 T1/T2、定位、正文哈希和快照哈希齐全时进入候选。\n\n"
        f"候选共 {len(candidate)} 条：训练 {sum(row['metadata']['source_split'] == 'train' for row in candidate)} 条，"
        f"验证 {sum(row['metadata']['source_split'] == 'validation' for row in candidate)} 条；"
        f"`audit_only` {len(audit_only)} 条。\n",
        encoding="utf-8",
    )

    files = [all_path, context_path, train_path, validation_path, audit_only_path, report_path, card_path]
    manifest = {
        "dataset_version": "6.0-first-round",
        "schema_version": SCHEMA_VERSION,
        "derived_from": {
            "path": source.name,
            "sha256": sha256(source),
        },
        "formal_ready": False,
        "review_status": "NEEDS_HUMAN_REVIEW",
        "training_contract": "trainers may read messages only; case audit contexts are excluded",
        "counts": report["counts"],
        "files": {path.name: {"sha256": sha256(path), "bytes": path.stat().st_size} for path in files},
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def check_release(out_dir: Path) -> dict[str, Any]:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        path = out_dir / name
        if not path.is_file() or sha256(path) != expected["sha256"]:
            raise ValueError(f"{name}: hash mismatch")
    records = read_jsonl(out_dir / "qa_records.jsonl")
    contexts = read_jsonl(out_dir / "case_audit_contexts.jsonl")
    report = validate_records(records, contexts)
    if report["errors"] or report["warnings"]:
        raise ValueError(json.dumps(report, ensure_ascii=False))
    if len(read_jsonl(out_dir / "train.jsonl")) != report["counts"]["candidate_split"].get("train", 0):
        raise ValueError("train split count mismatch")
    if len(read_jsonl(out_dir / "validation.jsonl")) != report["counts"]["candidate_split"].get("validation", 0):
        raise ValueError("validation split count mismatch")
    if len(read_jsonl(out_dir / "audit_only.jsonl")) != report["counts"]["release_partition"].get("audit_only", 0):
        raise ValueError("audit-only count mismatch")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        report = check_release(args.out_dir)
        print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))
        return 0
    if args.source is None:
        parser.error("--source is required unless --check is used")
    manifest = build_release(args.source, args.out_dir)
    print(json.dumps(manifest["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
