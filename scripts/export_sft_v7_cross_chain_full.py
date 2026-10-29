"""Build the full layered V7 candidate release from frozen V6 inputs.

Each row is a QA projection with explicit QA, answer, reasoning, audit, and
training layers. The source registries remain lineage references; no evidence
is upgraded and no external acquisition occurs here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from export_sft_v7_cross_chain_preview import (
    projected_evidence,
    read_jsonl,
    ref_kind,
    write_json,
    write_jsonl,
)


SCHEMA_VERSION = "auditable-video-reasoning/7.1-layered"
DATASET_VERSION = "7.1.0-layered-cross-chain"
ANALYSIS_AS_OF = "2026-08-17"
EXPECTED_CASES = 20
EXPECTED_ROWS = 180
CHAIN_TYPES = {"fact_transmission", "author_reasoning", "world_verification"}
KNOWN_V5_CONTEXT_LEAK = "CTX-BIRTH-SUBSIDY-A1"
ROLE_ORDER = {
    "origin": 1,
    "mechanism": 2,
    "author_assumption": 3,
    "evidence_confirmation": 4,
    "evidence_boundary": 5,
    "causal_refusal": 6,
    "alternative_explanation": 7,
    "bounded_impact": 8,
    "cross_chain_synthesis": 9,
}
ROLE_PARTICIPATION = {
    "origin": {"fact_transmission": "used", "author_reasoning": "context", "world_verification": "not_required"},
    "mechanism": {"fact_transmission": "used", "author_reasoning": "context", "world_verification": "context"},
    "author_assumption": {"fact_transmission": "context", "author_reasoning": "used", "world_verification": "context"},
    "evidence_confirmation": {"fact_transmission": "context", "author_reasoning": "context", "world_verification": "used"},
    "evidence_boundary": {"fact_transmission": "context", "author_reasoning": "context", "world_verification": "used"},
    "causal_refusal": {"fact_transmission": "used", "author_reasoning": "used", "world_verification": "used"},
    "alternative_explanation": {"fact_transmission": "context", "author_reasoning": "used", "world_verification": "used"},
    "bounded_impact": {"fact_transmission": "used", "author_reasoning": "context", "world_verification": "used"},
    "cross_chain_synthesis": {"fact_transmission": "used", "author_reasoning": "used", "world_verification": "used"},
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    matches = [row for row in rows if row.get(key) == value]
    if len(matches) != 1:
        raise ValueError(f"expected one row with {key}={value}, found {len(matches)}")
    return matches[0]


def evidence_union(
    audit: dict[str, Any], accepted_rows: list[dict[str, Any]], case_id: str
) -> list[dict[str, Any]]:
    rows = projected_evidence(audit, accepted_rows, case_id)
    seen = {row["evidence_id"] for row in rows}
    for accepted in accepted_rows:
        if accepted.get("case_id") != case_id or accepted["evidence_id"] in seen:
            continue
        rows.append(
            {
                "evidence_id": accepted["evidence_id"],
                "acceptance_status": accepted.get("acceptance_status"),
                "acceptance_reason": accepted.get("acceptance_reason"),
                "source_id": accepted.get("source_id"),
                "source_tier": accepted.get("source_tier"),
                "publisher": accepted.get("publisher"),
                "published_at": accepted.get("published_at"),
                "retrieved_at": accepted.get("retrieved_at"),
                "source_url": accepted.get("source_url"),
                "original_quote": accepted.get("original_quote", ""),
                "locator": accepted.get("locator", ""),
                "snapshot_path": accepted.get("snapshot_path"),
                "snapshot_sha256": accepted.get("snapshot_sha256", ""),
                "content_sha256": accepted.get("content_sha256", ""),
                "temporal_role": accepted.get("temporal_role"),
                "supports_node_ids": accepted.get("supports_node_ids", []),
                "gap_description": "",
                "required_evidence": "",
            }
        )
        seen.add(accepted["evidence_id"])
    return sorted(rows, key=lambda row: row["evidence_id"])


def context_index(
    audit: dict[str, Any], global_contexts: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in audit["published_contexts"]:
        result[row["context_id"]] = row
    for row in global_contexts:
        result.setdefault(row["context_id"], row)
    for row in evidence:
        context_id = row.get("context_id")
        if context_id and context_id not in result:
            result[context_id] = {
                "context_id": context_id,
                "source_id": row.get("source_id"),
                "locator": row.get("locator"),
                "text": row.get("original_quote", ""),
                "limitations": [],
                "release_status": "evidence_registry",
            }
    return result


def source_segments(
    audit: dict[str, Any], context_ids: list[str], contexts: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    segments: list[dict[str, Any]] = []
    gaps: list[str] = []
    for context_id in context_ids:
        context = contexts.get(context_id)
        if not context:
            gaps.append(f"SOURCE_CONTEXT_UNRESOLVED:{context_id}")
            continue
        locator = context.get("locator")
        text = context.get("text", "")
        segments.append(
            {
                "segment_id": context_id,
                "time_range": {"start": None, "end": None},
                "locator": locator,
                "transcript_or_paraphrase": text,
                "visual_evidence": [],
                "logic_role": "source_context",
                "source_id": context.get("source_id"),
                "release_status": context.get("release_status"),
                "limitations": context.get("limitations", []),
            }
        )
        if not isinstance(locator, dict) or "start" not in locator or "timestamp" not in locator:
            gaps.append("VIDEO_TIMESTAMP_NOT_AVAILABLE")
        if not context.get("visual_evidence"):
            gaps.append("VISUAL_EVIDENCE_NOT_EXTRACTED")
    if not segments:
        gaps.append("SOURCE_CONTEXT_NOT_EMBEDDED")
    return segments, sorted(set(gaps))


def ref_text_index(
    audit: dict[str, Any], contexts: dict[str, dict[str, Any]], evidence: list[dict[str, Any]]
) -> dict[str, str]:
    index = {row["node_id"]: row["text"] for row in audit["mother_graph"]["nodes"]}
    index.update({key: value.get("text", "") for key, value in contexts.items()})
    for row in evidence:
        index[row["evidence_id"]] = (
            row.get("original_quote")
            or row.get("gap_description")
            or row.get("required_evidence")
            or row["evidence_id"]
        )
    for chain in audit["mother_graph"]["chains"]:
        if chain["start_ref"] in index or not chain["steps"]:
            continue
        first_output = chain["steps"][0]["output_ref"]
        first_statement = index.get(first_output, "")
        if first_statement:
            index[chain["start_ref"]] = first_statement
    return index


def chain_for_ref(audit: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for chain in audit["mother_graph"]["chains"]:
        for step in chain["steps"]:
            result[step["output_ref"]] = chain["chain_type"]
    return result


def normalize_projection_refs(
    row: dict[str, Any], audit: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, str]]]:
    steps = row["local_reasoning_path"]
    context_ids = list(row.get("context_ids", []))
    corrections: list[dict[str, str]] = []
    if not row["case_id"].startswith("CASE-V5-"):
        return steps, context_ids, corrections

    fact_chain = next(
        chain
        for chain in audit["mother_graph"]["chains"]
        if chain["chain_type"] == "fact_transmission"
    )
    actual_start_ref = fact_chain["start_ref"]
    if not any(KNOWN_V5_CONTEXT_LEAK in step["input_refs"] for step in steps):
        return steps, context_ids, corrections

    normalized_steps = []
    for step in steps:
        normalized_steps.append(
            {
                **step,
                "input_refs": [
                    actual_start_ref if ref == KNOWN_V5_CONTEXT_LEAK else ref
                    for ref in step["input_refs"]
                ],
            }
        )
    context_ids = [ref for ref in context_ids if ref != KNOWN_V5_CONTEXT_LEAK]
    corrections.append(
        {
            "correction_code": "V6_CROSS_CASE_CONTEXT_REPLACED",
            "from_ref": KNOWN_V5_CONTEXT_LEAK,
            "to_ref": actual_start_ref,
            "authority": "mother_graph.fact_transmission.start_ref",
        }
    )
    return normalized_steps, context_ids, corrections


def detailed_local_path(
    steps: list[dict[str, Any]],
    ref_text: dict[str, str],
    evidence_index: dict[str, dict[str, Any]],
    chain_index: dict[str, str],
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    path: list[dict[str, Any]] = []
    refs: set[str] = set()
    chain_refs: set[str] = set()
    local_output_text: dict[str, str] = {}
    for step in steps:
        premise_refs = list(dict.fromkeys(step["input_refs"] + step.get("evidence_refs", [])))
        premises = []
        for ref in premise_refs:
            refs.add(ref)
            statement = ref_text.get(ref, "") or local_output_text.get(ref, "")
            if not statement:
                statement = f"UNRESOLVED_REF:{ref}"
            premises.append({"ref": ref, "ref_kind": ref_kind(ref), "statement": statement})
            if ref in chain_index:
                chain_refs.add(chain_index[ref])
        refs.add(step["output_ref"])
        if step["output_ref"] in chain_index:
            chain_refs.add(chain_index[step["output_ref"]])
        path.append(
            {
                "step_no": step["step_no"],
                "node_id": step["output_ref"],
                "node_kind": step["step_kind"],
                "premises": premises,
                "premise_refs": premise_refs,
                "relation": step["relation"],
                "conclusion": step["conclusion"],
                "explanation": step["explanation"],
                "source_refs": [ref for ref in premise_refs if ref.startswith("CTX-")],
                "evidence_refs": step.get("evidence_refs", []),
                "support_status": step["support_status"],
                "chain_membership": chain_index.get(step["output_ref"], "terminal_boundary"),
                "evidence_status": {
                    ref: evidence_index.get(ref, {}).get("acceptance_status", "UNRESOLVED")
                    for ref in step.get("evidence_refs", [])
                },
            }
        )
        local_output_text[step["output_ref"]] = step["conclusion"]
    return path, refs, chain_refs


def local_anchor_registry(
    audit: dict[str, Any], local_path: list[dict[str, Any]], ref_text: dict[str, str]
) -> list[dict[str, str]]:
    mother_nodes = {row["node_id"] for row in audit["mother_graph"]["nodes"]}
    chain_starts = {chain["start_ref"] for chain in audit["mother_graph"]["chains"]}
    valid_anchors = mother_nodes | chain_starts
    prior_outputs: set[str] = set()
    anchors: dict[str, dict[str, str]] = {}
    for step in local_path:
        for premise in step["premises"]:
            ref = premise["ref"]
            if ref in valid_anchors and ref not in prior_outputs:
                anchors[ref] = {
                    "ref": ref,
                    "ref_kind": premise["ref_kind"],
                    "statement": ref_text.get(ref, premise["statement"]),
                    "origin": "mother_graph_start" if ref in chain_starts else "mother_graph_node",
                }
        prior_outputs.add(step["node_id"])
    return [anchors[ref] for ref in sorted(anchors)]


def chain_anchors(audit: dict[str, Any], ref_text: dict[str, str]) -> dict[str, dict[str, Any]]:
    anchors = {}
    for chain in audit["mother_graph"]["chains"]:
        steps = chain["steps"]
        anchors[chain["chain_type"]] = {
            "start_ref": chain["start_ref"],
            "start_statement": ref_text.get(chain["start_ref"], chain["start_ref"]),
            "end_ref": chain["end_ref"],
            "end_statement": ref_text.get(chain["end_ref"], chain["end_ref"]),
            "step_count": len(steps),
        }
    return anchors


def relevant_alignments(
    audit: dict[str, Any], refs: set[str], role: str
) -> list[dict[str, Any]]:
    if role in {"causal_refusal", "alternative_explanation", "cross_chain_synthesis"}:
        return audit["chain_alignments"]
    return [
        row
        for row in audit["chain_alignments"]
        if row.get("from_ref") in refs or row.get("to_ref") in refs
    ]


def build_sample(
    row: dict[str, Any],
    audit_row: dict[str, Any],
    accepted_rows: list[dict[str, Any]],
    global_contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    audit = audit_row["audit_context"]
    evidence = evidence_union(audit, accepted_rows, row["case_id"])
    evidence_index = {item["evidence_id"]: item for item in evidence}
    contexts = context_index(audit, global_contexts, evidence)
    ref_text = ref_text_index(audit, contexts, evidence)
    chain_index = chain_for_ref(audit)
    normalized_steps, normalized_context_ids, lineage_corrections = normalize_projection_refs(row, audit)
    local_path, local_refs, local_chains = detailed_local_path(
        normalized_steps, ref_text, evidence_index, chain_index
    )
    local_anchors = local_anchor_registry(audit, local_path, ref_text)
    context_ids = sorted(
        set(normalized_context_ids) | {ref for ref in local_refs if ref.startswith("CTX-")}
    )
    segments, source_gaps = source_segments(audit, context_ids, contexts)
    overview = audit["case_overview"]
    provenance = overview.get("source_provenance", {})
    author_sources = [item for item in audit.get("source_registry", []) if item.get("source_tier") == "AUTHOR"]
    author_source = author_sources[0] if author_sources else {}
    video_id = overview.get("video_id")
    if not video_id:
        match = re.search(r"/video/(BV[0-9A-Za-z]+)", str(author_source.get("url", "")))
        video_id = match.group(1) if match else None
    author_source_type = provenance.get("primary_author_source_type") or author_source.get("source_kind")
    if not video_id:
        source_gaps = sorted(set(source_gaps) | {"VIDEO_ID_NOT_AVAILABLE"})
    if not author_source_type:
        source_gaps = sorted(set(source_gaps) | {"AUTHOR_SOURCE_TYPE_NOT_AVAILABLE"})
    citation_refs = [item["evidence_id"] for item in row["citations"]]
    causal = audit["causal_assessments"][0]
    completeness = audit["completeness"]["dimensions"]
    chain_states = ROLE_PARTICIPATION[row["question_role"]]
    answer = {
        "answerability": row["answer"]["answerability"],
        "direct_answer": row["answer"]["direct_answer"],
        "citation_refs": citation_refs,
        "citations": row["citations"],
        "verification": row["answer"]["verification"],
        "uncertainty_note": row["answer"]["uncertainty_note"],
        "missing_evidence": row["answer"]["missing_evidence"],
        "causal_conclusion": causal["causal_conclusion"] if row["truth_scope"] == "world_evidence" else None,
    }
    final_step = local_path[-1]
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
            "sample_id": f"V7-{row['qa_id']}",
            "case_id": row["case_id"],
            "event_cluster_id": row["event_cluster_id"],
            "projection_scope": "role_aware_cross_chain_projection",
            "parent_version": "6.1.0-reasoning-complete",
        },
        "qa": {
            "qa_id": row["qa_id"],
            "question": row["question"],
            "question_role": row["question_role"],
            "user_intent": row["user_intent"],
            "truth_scope": row["truth_scope"],
            "split": row["split"],
            "reasoning_status": row["reasoning_status"],
            "derived_from_qa_id": row["derived_from_qa_id"],
        },
        "answer": answer,
        "reasoning": {
            "chain_participation": chain_states,
            "local_path": local_path,
            "local_chain_refs": sorted(local_chains),
            "local_anchor_registry": local_anchors,
            "case_chain_anchors": chain_anchors(audit, ref_text),
            "cross_chain_alignments": relevant_alignments(audit, local_refs, row["question_role"]),
            "final_reasoning": {
                "premises": final_step["premises"],
                "premise_refs": final_step["premise_refs"],
                "relation": "qa_terminal_projection",
                "conclusion": answer["direct_answer"],
                "verification": answer["verification"],
            },
        },
        "audit": {
            "lineage_corrections": lineage_corrections,
            "source_trace": {
                "video_id": video_id,
                "primary_author_source_type": author_source_type,
                "extraction_status": "PARTIAL" if source_gaps else "TRACEABLE",
                "segments": segments,
                "gaps": source_gaps,
            },
            "evidence_registry": [
                item for item in evidence if item["evidence_id"] in set(citation_refs) | set(local_refs)
            ],
            "causal_assessment": {
                "status": causal["identification_status"],
                "causal_attribution_allowed": causal["causal_attribution_allowed"],
                "causal_conclusion": causal["causal_conclusion"],
                "method": causal["method"],
                "gate_results": {},
                "unmet_conditions": causal.get("required_evidence", causal.get("unmet_conditions", [])),
                "confounders": causal["alternative_explanations"],
                "counterevidence": [],
                "boundary_zh": causal["boundary_zh"],
            },
            "case_completeness": completeness,
            "closure_status": {
                "local_path_closed": True,
                "source_traceable": "complete" if not source_gaps else "partial",
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
            "eligibility_reasons": ["NEEDS_HUMAN_REVIEW", *source_gaps],
            "messages": [
                {
                    "role": "system",
                    "content": "区分作者表述与现实证据，只输出可审计的有限结论；因果未识别时必须拒绝归因。",
                },
                {"role": "user", "content": row["question"]},
                {"role": "assistant", "content": json.dumps(training_answer, ensure_ascii=False, sort_keys=True)},
            ],
        },
    }


def validate_sample(sample: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {"metadata", "qa", "answer", "reasoning", "audit", "training_projection"}
    missing = required - set(sample)
    if missing:
        errors.append(f"LAYER_SET_INCOMPLETE:{sorted(missing)}")
    local_path = sample["reasoning"]["local_path"]
    if not local_path:
        errors.append(f"{sample['qa']['qa_id']}:EMPTY_LOCAL_PATH")
        return errors
    participation = sample["reasoning"]["chain_participation"]
    if set(participation) != CHAIN_TYPES:
        errors.append(f"{sample['qa']['qa_id']}:THREE_CHAIN_SET_INCOMPLETE")
    if participation != ROLE_PARTICIPATION[sample["qa"]["question_role"]]:
        errors.append(f"{sample['qa']['qa_id']}:ROLE_CHAIN_PARTICIPATION_MISMATCH")
    evidence = {row["evidence_id"]: row for row in sample["audit"]["evidence_registry"]}
    anchors = {
        row["ref"]: row for row in sample["reasoning"]["local_anchor_registry"]
    }
    known = (
        set(evidence)
        | set(anchors)
        | {row["segment_id"] for row in sample["audit"]["source_trace"]["segments"]}
    )
    for anchor_ref, anchor in anchors.items():
        if not anchor["statement"] or anchor["statement"].startswith("UNRESOLVED_REF:"):
            errors.append(f"{sample['qa']['qa_id']}:INVALID_LOCAL_ANCHOR:{anchor_ref}")
    outputs: set[str] = set()
    for index, step in enumerate(local_path, 1):
        if step["step_no"] != index:
            errors.append(f"{sample['qa']['qa_id']}:NONSEQUENTIAL_STEP")
        if index > 1 and local_path[index - 2]["node_id"] not in step["premise_refs"]:
            errors.append(f"{sample['qa']['qa_id']}:DISCONTINUOUS_PATH")
        if not step["premises"] or not step["relation"] or not step["conclusion"]:
            errors.append(f"{sample['qa']['qa_id']}:INCOMPLETE_REASONING_STEP:{index}")
        for premise in step["premises"]:
            if premise["ref"] not in known | outputs:
                errors.append(f"{sample['qa']['qa_id']}:UNRESOLVED_PREMISE:{premise['ref']}")
            if not premise["statement"]:
                errors.append(f"{sample['qa']['qa_id']}:EMPTY_PREMISE:{premise['ref']}")
            elif premise["statement"].startswith("UNRESOLVED_REF:"):
                errors.append(
                    f"{sample['qa']['qa_id']}:UNRESOLVED_PREMISE_TEXT:{premise['ref']}"
                )
        for evidence_id in step["evidence_refs"]:
            if evidence_id not in evidence:
                errors.append(f"{sample['qa']['qa_id']}:UNRESOLVED_EVIDENCE:{evidence_id}")
        if step["node_id"] in outputs:
            errors.append(f"{sample['qa']['qa_id']}:DUPLICATE_OUTPUT:{step['node_id']}")
        outputs.add(step["node_id"])
    for evidence_id in sample["answer"]["citation_refs"]:
        if evidence_id not in evidence or evidence[evidence_id]["acceptance_status"] != "ACCEPTED":
            errors.append(f"{sample['qa']['qa_id']}:ANSWER_CITATION_NOT_ACCEPTED:{evidence_id}")
        elif evidence[evidence_id]["source_tier"] not in {"T1", "T2"}:
            errors.append(f"{sample['qa']['qa_id']}:ANSWER_CITATION_TIER_INELIGIBLE:{evidence_id}")
    if sample["metadata"]["case_id"].startswith("CASE-V5-") and any(
        KNOWN_V5_CONTEXT_LEAK in step["premise_refs"] for step in local_path
    ):
        errors.append(f"{sample['qa']['qa_id']}:V5_CROSS_CASE_CONTEXT_LEAK")
    causal = sample["audit"]["causal_assessment"]
    if causal["status"] != "IDENTIFIED" and (
        causal["causal_attribution_allowed"] or causal["causal_conclusion"] != "ABSTAIN"
    ):
        errors.append(f"{sample['qa']['qa_id']}:CAUSAL_GATE_CONTRADICTION")
    if sample["answer"]["direct_answer"] != sample["reasoning"]["final_reasoning"]["conclusion"]:
        errors.append(f"{sample['qa']['qa_id']}:ANSWER_REASONING_MISMATCH")
    messages = sample["training_projection"]["messages"]
    if sample["training_projection"]["status"] != "PREVIEW_ONLY_EXCLUDED":
        errors.append(f"{sample['qa']['qa_id']}:TRAINING_NOT_EXCLUDED")
    closure = sample["audit"]["closure_status"]
    if closure["review_status"] != "NEEDS_HUMAN_REVIEW" or closure["formal_ready"]:
        errors.append(f"{sample['qa']['qa_id']}:REVIEW_BOUNDARY_VIOLATION")
    if [message["role"] for message in messages] != ["system", "user", "assistant"]:
        errors.append(f"{sample['qa']['qa_id']}:MESSAGE_ROLE_ORDER")
    else:
        assistant = json.loads(messages[2]["content"])
        if assistant["direct_answer"] != sample["answer"]["direct_answer"]:
            errors.append(f"{sample['qa']['qa_id']}:TRAINING_ANSWER_MISMATCH")
    return errors


def build_gap_manifest(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for sample in samples:
        gaps = list(sample["audit"]["source_trace"]["gaps"])
        gaps.extend(sample["answer"]["missing_evidence"])
        gaps.extend(sample["audit"]["closure_status"]["world_evidence_closed"] != "complete" and ["WORLD_EVIDENCE_PARTIAL"] or [])
        result.append(
            {
                "qa_id": sample["qa"]["qa_id"],
                "case_id": sample["metadata"]["case_id"],
                "gap_codes": sorted(set(gaps)),
                "review_status": sample["audit"]["closure_status"]["review_status"],
            }
        )
    return result


def dataset_card(samples: list[dict[str, Any]], report: dict[str, Any]) -> str:
    counts = report["counts"]
    role_counts = Counter(sample["qa"]["question_role"] for sample in samples)
    return f"""# V7 分层三链推理全量候选

- Master：{counts['samples']} 条，{counts['cases']} 个案例，每案 9 个 QA 入口
- 推理节点：{counts['reasoning_steps']}
- 已接受证据引用：{counts['accepted_evidence_refs']}
- 证据缺口引用：{counts['gap_refs']}
- QA 角色：{dict(sorted(role_counts.items()))}
- 校验状态：`{report['status']}`

每条记录均拆为 `qa`、`answer`、`reasoning`、`audit` 和 `training_projection` 五层。
训练投影全部标记为 `PREVIEW_ONLY_EXCLUDED`，本目录不是正式训练发布。
视频时间戳和画面缺口不会被补写，仍保留为 gap code。
"""


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=root / "exports" / "v6-reasoning-complete")
    parser.add_argument("--output-dir", type=Path, default=root / "exports" / "v7-cross-chain-reasoning")
    args = parser.parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    audit_rows = read_jsonl(input_dir / "case_audit_contexts.jsonl")
    master_rows = read_jsonl(input_dir / "reasoning_master_180.jsonl")
    accepted_rows = read_jsonl(input_dir / "accepted_evidence.jsonl")
    global_contexts = read_jsonl(input_dir / "contexts.jsonl")
    audit_by_case = {row["case_id"]: row for row in audit_rows}
    samples: list[dict[str, Any]] = []
    for row in sorted(master_rows, key=lambda item: item["qa_id"]):
        if row["case_id"] not in audit_by_case:
            raise ValueError(f"missing audit case for {row['case_id']}")
        samples.append(build_sample(row, audit_by_case[row["case_id"]], accepted_rows, global_contexts))

    errors = [error for sample in samples for error in validate_sample(sample)]
    case_counts = Counter(sample["metadata"]["case_id"] for sample in samples)
    role_counts = Counter(sample["qa"]["question_role"] for sample in samples)
    if len(samples) != EXPECTED_ROWS:
        errors.append(f"EXPECTED_{EXPECTED_ROWS}_SAMPLES_GOT_{len(samples)}")
    if len(case_counts) != EXPECTED_CASES or any(count != 9 for count in case_counts.values()):
        errors.append("EXPECTED_20_CASES_WITH_9_QA_EACH")
    if any(count != 20 for count in role_counts.values()) or len(role_counts) != 9:
        errors.append("EXPECTED_9_ROLES_WITH_20_EACH")

    compact_path = output_dir / "reasoning_master_180.jsonl"
    pretty_path = output_dir / "reasoning_preview_vanke.pretty.json"
    qa_path = output_dir / "qa_records.jsonl"
    answer_path = output_dir / "answer_records.jsonl"
    training_path = output_dir / "training_messages_preview.jsonl"
    gap_path = output_dir / "gap_manifest.jsonl"
    report_path = output_dir / "validation_report.json"
    card_path = output_dir / "DATASET_CARD.md"
    write_jsonl(compact_path, samples)
    vanke = next(sample for sample in samples if sample["metadata"]["case_id"] == "CASE-VANKE" and sample["qa"]["question_role"] == "cross_chain_synthesis")
    write_json(pretty_path, vanke)
    write_jsonl(qa_path, [{"qa": sample["qa"], "sample_id": sample["metadata"]["sample_id"]} for sample in samples])
    write_jsonl(answer_path, [{"answer": sample["answer"], "qa_id": sample["qa"]["qa_id"]} for sample in samples])
    write_jsonl(training_path, [{"qa_id": sample["qa"]["qa_id"], **sample["training_projection"]} for sample in samples])
    write_jsonl(gap_path, build_gap_manifest(samples))

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS_CANDIDATE_PREVIEW" if not errors else "FAIL",
        "errors": errors,
        "warnings": sorted({gap for sample in samples for gap in sample["audit"]["source_trace"]["gaps"]}),
        "counts": {
            "samples": len(samples),
            "cases": len(case_counts),
            "reasoning_steps": sum(len(sample["reasoning"]["local_path"]) for sample in samples),
            "accepted_evidence_refs": sum(
                len(sample["answer"]["citation_refs"]) for sample in samples
            ),
            "gap_refs": sum(
                len(item["gap_codes"]) for item in build_gap_manifest(samples)
            ),
            "lineage_corrections": sum(
                len(sample["audit"]["lineage_corrections"]) for sample in samples
            ),
            "roles": dict(sorted(role_counts.items())),
        },
    }
    report["sample_sha256"] = hashlib.sha256(compact_path.read_bytes()).hexdigest()
    write_json(report_path, report)
    card_path.write_text(dataset_card(samples, report), encoding="utf-8", newline="\n")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": DATASET_VERSION,
        "analysis_as_of": ANALYSIS_AS_OF,
        "parent_version": "6.1.0-reasoning-complete",
        "preview_only": True,
        "formal_ready": False,
        "input_sha256": {
            name: sha256_file(input_dir / name)
            for name in ("case_audit_contexts.jsonl", "reasoning_master_180.jsonl", "accepted_evidence.jsonl", "contexts.jsonl")
        },
        "output_sha256": {
            path.name: sha256_file(path)
            for path in (compact_path, pretty_path, qa_path, answer_path, training_path, gap_path, report_path, card_path)
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
