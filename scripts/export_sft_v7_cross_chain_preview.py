"""Build one deterministic V7 cross-chain reasoning preview.

The preview projects an existing frozen case mother graph into explicit
premise -> relation -> conclusion steps. It does not acquire evidence or
upgrade any evidence status from the V6 release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "auditable-video-reasoning/7.1-layered-preview"
DATASET_VERSION = "7.1.0-layered-cross-chain-preview"
ANALYSIS_AS_OF = "2026-08-17"
DEFAULT_CASE_ID = "CASE-VANKE"
DEFAULT_QA_ID = "QA-V41-0309"
CHAIN_KEYS = {
    "fact_transmission": "fact_transmission",
    "author_reasoning": "author_reasoning",
    "world_verification": "world_verification",
}


def json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json_line(row) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    matches = [row for row in rows if row.get(key) == value]
    if len(matches) != 1:
        raise ValueError(f"expected one row with {key}={value}, found {len(matches)}")
    return matches[0]


def projected_evidence(
    audit: dict[str, Any], accepted_rows: list[dict[str, Any]], case_id: str
) -> list[dict[str, Any]]:
    accepted = {
        row["evidence_id"]: row for row in accepted_rows if row.get("case_id") == case_id
    }
    result: list[dict[str, Any]] = []
    for claim in audit["claim_level_evidence"]:
        evidence_id = claim["evidence_id"]
        source = accepted.get(evidence_id, claim)
        result.append(
            {
                "evidence_id": evidence_id,
                "acceptance_status": source.get("acceptance_status"),
                "acceptance_reason": source.get("acceptance_reason"),
                "source_id": source.get("source_id"),
                "source_tier": source.get("source_tier"),
                "publisher": source.get("publisher"),
                "published_at": source.get("published_at"),
                "retrieved_at": source.get("retrieved_at"),
                "source_url": source.get("source_url"),
                "original_quote": source.get("original_quote", ""),
                "locator": source.get("locator", ""),
                "snapshot_path": source.get("snapshot_path"),
                "snapshot_sha256": source.get("snapshot_sha256", ""),
                "content_sha256": source.get("content_sha256", ""),
                "temporal_role": source.get("temporal_role"),
                "supports_node_ids": source.get("supports_node_ids")
                or [claim["target_ref"]],
                "gap_description": claim.get("gap_description", ""),
                "required_evidence": claim.get("required_evidence", ""),
            }
        )
    return result


def ref_kind(ref: str) -> str:
    if ref.startswith("NODE-"):
        return "node"
    if ref.startswith("CTX-"):
        return "source_context"
    if ref.startswith("EV-"):
        return "evidence"
    if ref.startswith("TERM-"):
        return "terminal"
    return "unknown"


def closure_basis(step: dict[str, Any], evidence_index: dict[str, dict[str, Any]]) -> str:
    evidence = [evidence_index[ref] for ref in step.get("evidence_refs", [])]
    if any(row.get("acceptance_status") == "GAP" for row in evidence):
        return "EVIDENCE_GAP"
    if any(row.get("acceptance_status") == "ACCEPTED" for row in evidence):
        validity = step.get("support_status", {}).get("world_validity")
        return "DIRECT_FACT" if validity == "confirmed" else "PREMISE_SUPPORT"
    fidelity = step.get("support_status", {}).get("author_fidelity")
    if fidelity in {"explicit", "implicit"}:
        return "AUTHOR_TRACE"
    return "BOUNDARY_SYNTHESIS"


def project_chains(
    audit: dict[str, Any], ref_text: dict[str, str], evidence_index: dict[str, dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    chains: dict[str, list[dict[str, Any]]] = {}
    for source_chain in audit["mother_graph"]["chains"]:
        chain_type = source_chain["chain_type"]
        if chain_type not in CHAIN_KEYS:
            continue
        projected: list[dict[str, Any]] = []
        for step in source_chain["steps"]:
            premise_refs = list(
                dict.fromkeys(step["input_refs"] + step.get("evidence_refs", []))
            )
            premises = [
                {
                    "ref": ref,
                    "ref_kind": ref_kind(ref),
                    "statement": ref_text[ref],
                }
                for ref in premise_refs
            ]
            projected.append(
                {
                    "step_no": step["step_no"],
                    "node_id": step["output_ref"],
                    "node_kind": step["step_kind"],
                    "premises": premises,
                    "premise_refs": premise_refs,
                    "relation": step["relation"],
                    "conclusion": ref_text[step["output_ref"]],
                    "explanation": step["explanation"],
                    "source_refs": [
                        ref for ref in step["input_refs"] if ref.startswith("CTX-")
                    ],
                    "evidence_refs": step.get("evidence_refs", []),
                    "closure_basis": closure_basis(step, evidence_index),
                    "support_status": step["support_status"],
                }
            )
        chains[CHAIN_KEYS[chain_type]] = projected
    return chains


def build_preview(
    audit_row: dict[str, Any],
    master_row: dict[str, Any],
    accepted_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    audit = audit_row["audit_context"]
    case_id = audit_row["case_id"]
    evidence = projected_evidence(audit, accepted_rows, case_id)
    evidence_index = {row["evidence_id"]: row for row in evidence}
    node_text = {row["node_id"]: row["text"] for row in audit["mother_graph"]["nodes"]}
    context_text = {row["context_id"]: row["text"] for row in audit["published_contexts"]}
    evidence_text = {
        row["evidence_id"]: row["original_quote"]
        or row["gap_description"]
        or row["required_evidence"]
        or row["evidence_id"]
        for row in evidence
    }
    ref_text = node_text | context_text | evidence_text
    chains = project_chains(audit, ref_text, evidence_index)

    author_contexts = [
        row
        for row in audit["published_contexts"]
        if row.get("source_id") in audit["case_overview"]["source_provenance"]["author_source_ids"]
    ]
    source_segments = []
    for index, context in enumerate(author_contexts, 1):
        source_segments.append(
            {
                "segment_id": context["context_id"],
                "time_range": {"start": None, "end": None},
                "locator": context["locator"],
                "transcript_or_paraphrase": context["text"],
                "visual_evidence": [],
                "logic_role": "background" if index == 1 else "claim",
                "source_id": context["source_id"],
                "release_status": context["release_status"],
                "limitations": context["limitations"],
            }
        )

    causal = audit["causal_assessments"][0]
    final_refs = [
        audit["mother_graph"]["chains"][0]["end_ref"],
        audit["mother_graph"]["chains"][1]["end_ref"],
        audit["mother_graph"]["chains"][2]["end_ref"],
    ]
    final_premises = [
        {"ref": ref, "ref_kind": "node", "statement": ref_text[ref]} for ref in final_refs
    ]

    completeness = audit["completeness"]["dimensions"]
    citation_refs = [row["evidence_id"] for row in master_row["citations"]]
    answer = {
        "answerability": master_row["answer"]["answerability"],
        "direct_answer": master_row["answer"]["direct_answer"],
        "citation_refs": citation_refs,
        "citations": master_row["citations"],
        "verification": master_row["answer"]["verification"],
        "uncertainty_note": master_row["answer"]["uncertainty_note"],
        "missing_evidence": master_row["answer"]["missing_evidence"],
        "causal_conclusion": causal["causal_conclusion"],
    }
    training_answer = {
        "answerability": answer["answerability"],
        "direct_answer": answer["direct_answer"],
        "citation_refs": citation_refs,
        "uncertainty_note": answer["uncertainty_note"],
        "causal_conclusion": answer["causal_conclusion"],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": DATASET_VERSION,
        "metadata": {
            "analysis_as_of": ANALYSIS_AS_OF,
            "sample_id": "DEMO-VANKE-CROSS-CHAIN-001",
            "case_id": case_id,
            "event_cluster_id": audit_row["event_cluster_id"],
            "projection_scope": "full_case_cross_chain_preview",
        },
        "qa": {
            "qa_id": master_row["qa_id"],
            "question": master_row["question"],
            "question_role": master_row["question_role"],
            "user_intent": master_row["user_intent"],
            "truth_scope": master_row["truth_scope"],
            "split": master_row["split"],
            "reasoning_status": master_row["reasoning_status"],
        },
        "answer": answer,
        "reasoning": {
            "chain_participation": {
                "fact_transmission": "used",
                "author_reasoning": "used",
                "world_verification": "used",
            },
            "chains": chains,
            "cross_chain_alignments": audit["chain_alignments"],
            "final_reasoning": {
                "premises": final_premises,
                "premise_refs": final_refs,
                "relation": "cross_chain_bounded_synthesis",
                "conclusion": answer["direct_answer"],
                "verification": answer["verification"],
            },
        },
        "audit": {
            "source_trace": {
                "video_id": audit["case_overview"]["video_id"],
                "primary_author_source_type": audit["case_overview"]["source_provenance"]
                ["primary_author_source_type"],
                "extraction_status": "PARTIAL",
                "segments": source_segments,
                "gaps": ["VIDEO_TIMESTAMP_NOT_AVAILABLE", "VISUAL_EVIDENCE_NOT_EXTRACTED"],
            },
            "evidence_registry": evidence,
            "causal_assessment": {
                "status": causal["identification_status"],
                "causal_attribution_allowed": causal["causal_attribution_allowed"],
                "causal_conclusion": causal["causal_conclusion"],
                "method": causal["method"],
                "gate_results": {},
                "unmet_conditions": causal["required_evidence"],
                "confounders": causal["alternative_explanations"],
                "counterevidence": [],
                "boundary_zh": causal["boundary_zh"],
            },
            "closure_status": {
                "local_path_closed": True,
                "source_traceable": completeness["provenance_completeness"]["status"],
                "event_chain_coverage": completeness["event_coverage"]["status"],
                "argument_chain_connected": True,
                "argument_world_support": completeness["mechanism_coverage"]["status"],
                "world_evidence_closed": completeness["evidence_coverage"]["status"],
                "causal_identification": completeness["causal_identification"]["status"],
                "cross_chain_alignment": completeness["cross_chain_alignment"]["status"],
                "review_status": "NEEDS_HUMAN_REVIEW",
                "formal_ready": False,
            },
        },
        "training_projection": {
            "status": "PREVIEW_ONLY_EXCLUDED",
            "eligibility_reasons": [
                "NEEDS_HUMAN_REVIEW",
                "VIDEO_TIMESTAMP_NOT_AVAILABLE",
                "VISUAL_EVIDENCE_NOT_EXTRACTED",
            ],
            "messages": [
                {
                    "role": "system",
                    "content": "区分作者表述与现实证据，只输出可审计的有限结论；因果未识别时必须拒绝归因。",
                },
                {"role": "user", "content": master_row["question"]},
                {"role": "assistant", "content": json_line(training_answer)},
            ],
        },
    }


def validate_preview(sample: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    required_layers = {"metadata", "qa", "answer", "reasoning", "audit", "training_projection"}
    missing_layers = required_layers - set(sample)
    if missing_layers:
        errors.append(f"LAYER_SET_INCOMPLETE:{sorted(missing_layers)}")
    warnings = list(sample["audit"]["source_trace"]["gaps"])
    chains = sample["reasoning"].get("chains", {})
    if set(chains) != set(CHAIN_KEYS.values()):
        errors.append("THREE_CHAIN_SET_INCOMPLETE")

    evidence_index = {row["evidence_id"]: row for row in sample["audit"]["evidence_registry"]}
    known_refs = set(evidence_index)
    known_refs.update(
        row["segment_id"] for row in sample["audit"]["source_trace"]["segments"]
    )
    all_nodes: set[str] = set()
    for chain_name, steps in chains.items():
        prior: set[str] = set()
        for number, step in enumerate(steps, 1):
            if step["step_no"] != number:
                errors.append(f"{chain_name}:{step['node_id']}:NONSEQUENTIAL_STEP")
            if number > 1 and steps[number - 2]["node_id"] not in step["premise_refs"]:
                errors.append(f"{chain_name}:{step['node_id']}:DISCONTINUOUS_PATH")
            for premise in step["premises"]:
                if premise["ref"] not in known_refs | all_nodes | prior:
                    errors.append(f"{chain_name}:{step['node_id']}:UNRESOLVED_PREMISE:{premise['ref']}")
                if not premise["statement"]:
                    errors.append(f"{chain_name}:{step['node_id']}:EMPTY_PREMISE")
            for evidence_id in step["evidence_refs"]:
                if evidence_id not in evidence_index:
                    errors.append(f"{chain_name}:{step['node_id']}:UNRESOLVED_EVIDENCE:{evidence_id}")
            validity = step["support_status"]["world_validity"]
            if chain_name == "world_verification" and validity == "confirmed":
                accepted = [
                    evidence_index[ref]
                    for ref in step["evidence_refs"]
                    if ref in evidence_index
                    and evidence_index[ref]["acceptance_status"] == "ACCEPTED"
                    and evidence_index[ref]["source_tier"] in {"T1", "T2"}
                ]
                if not accepted:
                    errors.append(f"{chain_name}:{step['node_id']}:CONFIRMED_WITHOUT_T1_T2")
            prior.add(step["node_id"])
            all_nodes.add(step["node_id"])

    for alignment in sample["reasoning"]["cross_chain_alignments"]:
        for key in ("from_ref", "to_ref"):
            if alignment[key] not in all_nodes | known_refs:
                errors.append(f"{alignment['alignment_id']}:UNRESOLVED_{key.upper()}")
    for ref in sample["reasoning"]["final_reasoning"]["premise_refs"]:
        if ref not in all_nodes:
            errors.append(f"FINAL_REASONING:UNRESOLVED_PREMISE:{ref}")

    causal = sample["audit"]["causal_assessment"]
    if causal["status"] != "IDENTIFIED" and (
        causal["causal_attribution_allowed"] or causal["causal_conclusion"] != "ABSTAIN"
    ):
        errors.append("CAUSAL_GATE_CONTRADICTION")
    if sample["audit"]["closure_status"]["formal_ready"]:
        errors.append("PREVIEW_MUST_NOT_BE_FORMAL_READY")
    if sample["answer"]["direct_answer"] != sample["reasoning"]["final_reasoning"]["conclusion"]:
        errors.append("ANSWER_REASONING_TERMINAL_MISMATCH")
    for evidence_id in sample["answer"]["citation_refs"]:
        evidence_row = evidence_index.get(evidence_id)
        if not evidence_row or evidence_row["acceptance_status"] != "ACCEPTED":
            errors.append(f"ANSWER_CITATION_NOT_ACCEPTED:{evidence_id}")

    projection = sample["training_projection"]
    if projection["status"] != "PREVIEW_ONLY_EXCLUDED":
        errors.append("PREVIEW_TRAINING_STATUS_INVALID")
    if [row["role"] for row in projection["messages"]] != ["system", "user", "assistant"]:
        errors.append("TRAINING_MESSAGE_ROLE_ORDER_INVALID")
    else:
        training_answer = json.loads(projection["messages"][2]["content"])
        if training_answer["direct_answer"] != sample["answer"]["direct_answer"]:
            errors.append("TRAINING_ANSWER_MISMATCH")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS_PREVIEW" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "samples": 1,
            "chains": len(chains),
            "reasoning_steps": sum(len(steps) for steps in chains.values()),
            "accepted_evidence": sum(
                row["acceptance_status"] == "ACCEPTED"
                for row in sample["audit"]["evidence_registry"]
            ),
            "evidence_gaps": sum(
                row["acceptance_status"] == "GAP"
                for row in sample["audit"]["evidence_registry"]
            ),
            "messages": len(sample["training_projection"]["messages"]),
        },
    }


def build_card(sample: dict[str, Any], report: dict[str, Any]) -> str:
    counts = report["counts"]
    return f"""# V7 分层三链推理单样本预览

- 样本：`{sample['metadata']['sample_id']}` / `{sample['metadata']['case_id']}` / `{sample['qa']['qa_id']}`
- 分层：QA、答案、推理、审计、训练投影
- 三链：事实传导、作者论证、现实验证
- 推理节点：{counts['reasoning_steps']}
- 已接受证据：{counts['accepted_evidence']}
- 证据缺口：{counts['evidence_gaps']}
- 训练消息：{counts['messages']}（`PREVIEW_ONLY_EXCLUDED`）
- 校验状态：`{report['status']}`

本目录只用于确认 V7 字段和内容密度。它读取冻结的 V6 数据，不覆盖 V6，
不升级证据状态，也不解除 `NEEDS_HUMAN_REVIEW` 或 `formal_ready=false`。

`reasoning_preview.pretty.json` 适合人工查看；`reasoning_preview.jsonl` 展示未来
Master 文件的一行存储形式。当前作者材料没有视频时间戳和画面提取，因此来源
追踪保持 `PARTIAL`，相关缺口保存在校验报告中。
"""


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=root / "exports" / "v6-reasoning-complete",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "exports" / "v7-cross-chain-reasoning-preview",
    )
    parser.add_argument("--case-id", default=DEFAULT_CASE_ID)
    parser.add_argument("--qa-id", default=DEFAULT_QA_ID)
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    input_paths = {
        "case_audit_contexts.jsonl": input_dir / "case_audit_contexts.jsonl",
        "reasoning_master_180.jsonl": input_dir / "reasoning_master_180.jsonl",
        "accepted_evidence.jsonl": input_dir / "accepted_evidence.jsonl",
    }
    for name, path in input_paths.items():
        if not path.is_file():
            raise ValueError(f"missing input {name}: {path}")

    audit = select(read_jsonl(input_paths["case_audit_contexts.jsonl"]), "case_id", args.case_id)
    master = select(read_jsonl(input_paths["reasoning_master_180.jsonl"]), "qa_id", args.qa_id)
    if master["case_id"] != args.case_id:
        raise ValueError(f"QA {args.qa_id} belongs to {master['case_id']}, not {args.case_id}")
    accepted = read_jsonl(input_paths["accepted_evidence.jsonl"])
    sample = build_preview(audit, master, accepted)
    report = validate_preview(sample)

    compact_path = output_dir / "reasoning_preview.jsonl"
    pretty_path = output_dir / "reasoning_preview.pretty.json"
    report_path = output_dir / "validation_report.json"
    card_path = output_dir / "DATASET_CARD.md"
    write_jsonl(compact_path, [sample])
    write_json(pretty_path, sample)
    report["sample_sha256"] = sha256_file(compact_path)
    write_json(report_path, report)
    card_path.write_text(build_card(sample, report), encoding="utf-8", newline="\n")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": DATASET_VERSION,
        "analysis_as_of": ANALYSIS_AS_OF,
        "parent_version": "6.1.0-reasoning-complete",
        "preview_only": True,
        "formal_ready": False,
        "input_sha256": {name: sha256_file(path) for name, path in sorted(input_paths.items())},
        "output_sha256": {
            path.name: sha256_file(path)
            for path in (compact_path, pretty_path, report_path, card_path)
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
