"""Build a compact browser asset from the canonical V4 QA/SFT release."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_v5_asset(source_root: Path) -> dict[str, Any]:
    cases_dir = source_root / "data" / "cases" / "v5"
    train_dir = source_root / "data" / "train" / "v5"
    graphs = read_jsonl(cases_dir / "case_graphs.jsonl")
    evidence = read_jsonl(cases_dir / "evidence_records.jsonl")
    records = read_jsonl(train_dir / "qa_records.jsonl")
    evidence_by_case = {graph["case_id"]: [] for graph in graphs}
    records_by_case = {graph["case_id"]: [] for graph in graphs}
    for row in evidence:
        evidence_by_case[row["case_id"]].append(row)
    for row in records:
        records_by_case[row["case_id"]].append(row)
    path_specs = [
        ("first_contact", [0, 1, 7]),
        ("reason_followup", [0, 1, 2, 8]),
        ("verification_doubt", [3, 4, 5]),
        ("comparison", [2, 6, 7]),
        ("impact_followup", [1, 4, 7, 8]),
    ]
    coverage = {
        "first_contact": ["origin", "mechanism", "outcome"],
        "reason_followup": ["origin", "mechanism", "outcome", "verification"],
        "verification_doubt": ["verification"],
        "comparison": ["mechanism", "impact", "verification"],
        "impact_followup": ["mechanism", "outcome", "impact", "verification"],
    }
    cases = []
    for graph in sorted(graphs, key=lambda row: row["case_no"]):
        case_id = graph["case_id"]
        case_records = sorted(records_by_case[case_id], key=lambda row: row["qa_id"])
        case_evidence = sorted(evidence_by_case[case_id], key=lambda row: row["evidence_id"])
        source_rows = {}
        context_rows = []
        link_rows = []
        for item in case_evidence:
            source_id = item["source_id"]
            source_rows.setdefault(source_id, {
                "source_id": source_id, "publisher": source_id, "source_kind": "external_primary" if item["source_tier"] in {"T1", "T2"} else "audit_note",
                "source_tier": item["source_tier"], "temporal_role": item["temporal_role"], "url": item["source_url"],
                "is_full_text": bool(item["snapshot_sha256"]), "authorship_confirmed": item["source_tier"] == "AUTHOR",
            })
            context_id = f"CTX-{item['evidence_id']}"
            context_rows.append({
                "context_id": context_id, "source_id": source_id,
                "content_sha256": item["content_sha256"] or item["snapshot_sha256"],
                "text": item["original_quote"] or item["gap_description"], "locator": item["locator"] or {"kind": "evidence_gap"},
                "limitations": [item["required_evidence"]] if item["required_evidence"] else [],
            })
            link_rows.append({
                "link_id": item["evidence_id"], "source_id": source_id, "target_ref": item["target_ref"],
                "notes": item["gap_description"] or item["original_quote"], "coverage": item["coverage"],
            })
        qa_items = [{
            "qa_id": row["qa_id"], "conversational_question": row["question"], "standalone_question": row["question"],
            "user_intent": row["user_intent"], "truth_scope": row["truth_scope"], "answerability": row["answerability"],
            "question_role": row["question_role"],
        } for row in case_records]
        qa_gold = [{"qa_id": row["qa_id"], **row["gold"], "target_ref_ids": [step["output_ref"] for step in row["gold"]["local_reasoning_path"]]} for row in case_records]
        sft_records = [{"messages": row["messages"], "metadata": {
            "qa_id": row["qa_id"], "case_id": case_id, "source_split": row["split"], "truth_scope": row["truth_scope"],
            "user_intent": row["user_intent"], "answerability": row["answerability"], "question_role": row["question_role"],
        }} for row in case_records]
        dialogues = []
        for number, (entry, indexes) in enumerate(path_specs, 1):
            qa_ids = [case_records[index]["qa_id"] for index in indexes]
            dialogues.append({
                "dialogue_id": f"DIALOGUE-{case_id}-{number:02d}", "case_id": case_id, "dataset_version": "5.0.0",
                "entry_kind": entry, "turn_count": len(qa_ids), "qa_ids": qa_ids,
                "cumulative_coverage_tags": coverage[entry], "chain_completeness": "complete" if len(coverage[entry]) >= 4 else "partial",
            })
        cases.append({
            "case_pack": graph,
            "contexts": context_rows,
            "sources": list(source_rows.values()),
            "evidence_links": link_rows,
            "qa_items": qa_items,
            "qa_gold": qa_gold,
            "dialogue_paths": dialogues,
            "followup_graph": {"dataset_version": "5.0.0", "case_id": case_id, "nodes": qa_items, "edges": []},
            "macro_narrative": {"case_id": case_id, "central_claim": next(chain for chain in graph["chains"] if chain["chain_type"] == "author_reasoning")["steps"][-1]["output_ref"]},
            "sft_records": sft_records,
            "deep_audit": {**graph, "evidence_records": case_evidence, "causal_assessments": [graph["causal_assessment"]], "completeness": {"dimensions": {"event_coverage": {"status": "partial"}, "mechanism_coverage": {"status": "partial"}, "evidence_coverage": {"status": "blocked"}, "causal_identification": {"status": "blocked"}, "alternative_explanation_coverage": {"status": "partial"}, "cross_chain_alignment": {"status": "complete"}, "provenance_completeness": {"status": "partial"}, "temporal_consistency": {"status": "partial"}}}},
        })
        nodes = {node["node_id"]: node for node in graph["nodes"]}
        cases[-1]["macro_narrative"]["central_claim"] = nodes[cases[-1]["macro_narrative"]["central_claim"]]["text"]
    manifest = json.loads((train_dir / "manifest.json").read_text(encoding="utf8"))
    return {
        "dataset_version": "5.0.0", "generated_from": {"case_manifest_sha256": sha256(cases_dir / "manifest.json"), "training_manifest_sha256": sha256(train_dir / "manifest.json")},
        "metrics": {"local_path_signatures": manifest["metrics"]["path_signatures"], "average_assistant_characters": 0},
        "counts": {"cases": 10, "qa_items": 90, "dialogue_paths": 50, "train_records": 72, "validation_records": 18},
        "cases": cases,
    }


def build_asset(source_root: Path) -> dict[str, Any]:
    cases_dir = source_root / "data" / "cases" / "v4"
    train_dir = source_root / "data" / "train" / "v4"
    v3_qa_dir = source_root / "data" / "qa" / "v3"
    case_packs = read_jsonl(cases_dir / "case_packs.jsonl")
    records = read_jsonl(train_dir / "qa_records.jsonl")
    old_dialogues = read_jsonl(v3_qa_dir / "dialogue_paths.jsonl")
    old_graphs = read_jsonl(v3_qa_dir / "followup_graphs.jsonl")
    narratives = read_jsonl(v3_qa_dir / "macro_narratives.jsonl")
    v41_cases_dir = source_root / "data" / "cases" / "v4.1"
    v41_train_dir = source_root / "data" / "train" / "v4.1"
    v41_graphs = read_jsonl(v41_cases_dir / "case_graphs.jsonl") if v41_cases_dir.is_dir() else []
    v41_evidence = read_jsonl(v41_cases_dir / "evidence_records.jsonl") if v41_cases_dir.is_dir() else []
    v41_records = read_jsonl(v41_train_dir / "qa_records.jsonl") if v41_train_dir.is_dir() else []
    v41_graph_by_case = {row["case_id"]: row for row in v41_graphs}
    v41_records_by_case = {
        case_id: sorted((row for row in v41_records if row["case_id"] == case_id), key=lambda row: row["qa_id"])
        for case_id in v41_graph_by_case
    }
    old_to_new = {row["derived_from_qa_id"]: row["qa_id"] for row in records}
    cases = []
    for pack in sorted(case_packs, key=lambda row: row["case_id"]):
        case_id = pack["case_id"]
        case_records = sorted((row for row in records if row["case_id"] == case_id), key=lambda row: row["qa_id"])
        audit = case_records[0]["audit_context"]
        qa_items = [
            {
                "qa_id": row["qa_id"],
                "conversational_question": row["question"]["conversational"],
                "standalone_question": row["question"]["standalone"],
                "user_intent": row["user_intent"],
                "truth_scope": row["truth_scope"],
                "answerability": row["answerability"],
                "question_role": row["question_role"],
            }
            for row in case_records
        ]
        qa_gold = [{"qa_id": row["qa_id"], **row["gold"]} for row in case_records]
        sft_records = [
            {
                "messages": row["messages"],
                "metadata": {
                    "qa_id": row["qa_id"],
                    "case_id": case_id,
                    "source_split": row["split"],
                    "truth_scope": row["truth_scope"],
                    "user_intent": row["user_intent"],
                    "answerability": row["answerability"],
                    "question_role": row["question_role"],
                },
            }
            for row in case_records
        ]
        dialogues = []
        for row in old_dialogues:
            if row["case_id"] != case_id:
                continue
            dialogues.append({**row, "dataset_version": "4.0.0", "qa_ids": [old_to_new[qa_id] for qa_id in row["qa_ids"]]})
        old_graph = next(row for row in old_graphs if row["case_id"] == case_id)
        graph = {
            **old_graph,
            "dataset_version": "4.0.0",
            "entry_qa_ids": [old_to_new[qa_id] for qa_id in old_graph["entry_qa_ids"]],
            "nodes": [{**node, "qa_id": old_to_new[node["qa_id"]]} for node in old_graph["nodes"]],
            "edges": [
                {**edge, "from_qa_id": old_to_new[edge["from_qa_id"]], "to_qa_id": old_to_new[edge["to_qa_id"]]}
                for edge in old_graph["edges"]
            ],
        }
        deep_graph = v41_graph_by_case.get(case_id)
        deep_records = v41_records_by_case.get(case_id, [])
        if deep_graph:
            v4_to_v41 = {row["derived_from_qa_id"]: row["qa_id"] for row in deep_records}
            pack = {
                **pack,
                "dataset_version": "4.1.0",
                "nodes": deep_graph["nodes"],
                "chains": deep_graph["chains"],
                "review_status": deep_graph["review_status"],
                "generator_id": deep_graph["generator_id"],
            }
            qa_items = [
                {
                    "qa_id": row["qa_id"],
                    "conversational_question": row["question"],
                    "standalone_question": row["question"],
                    "user_intent": row["user_intent"],
                    "truth_scope": row["truth_scope"],
                    "answerability": row["answerability"],
                    "question_role": row["question_role"],
                }
                for row in deep_records
            ]
            qa_gold = [{"qa_id": row["qa_id"], **row["gold"], "target_ref_ids": [step["output_ref"] for step in row["gold"]["local_reasoning_path"]]} for row in deep_records]
            sft_records = [
                {
                    "messages": row["messages"],
                    "metadata": {
                        "qa_id": row["qa_id"], "case_id": case_id, "source_split": row["split"],
                        "truth_scope": row["truth_scope"], "user_intent": row["user_intent"],
                        "answerability": row["answerability"], "question_role": row["question_role"],
                    },
                }
                for row in deep_records
            ]
            dialogues = [{**row, "dataset_version": "4.1.0", "qa_ids": [v4_to_v41[qa_id] for qa_id in row["qa_ids"]]} for row in dialogues]
            graph = {
                **graph,
                "dataset_version": "4.1.0",
                "entry_qa_ids": [v4_to_v41[qa_id] for qa_id in graph["entry_qa_ids"]],
                "nodes": [{**node, "qa_id": v4_to_v41[node["qa_id"]]} for node in graph["nodes"]],
                "edges": [{**edge, "from_qa_id": v4_to_v41[edge["from_qa_id"]], "to_qa_id": v4_to_v41[edge["to_qa_id"]]} for edge in graph["edges"]],
            }
        cases.append(
            {
                "case_pack": pack,
                "contexts": audit["contexts"],
                "sources": audit["source_registry"],
                "evidence_links": audit["evidence_links"],
                "qa_items": qa_items,
                "qa_gold": qa_gold,
                "dialogue_paths": sorted(dialogues, key=lambda row: row["dialogue_id"]),
                "followup_graph": graph,
                "macro_narrative": next(row for row in narratives if row["case_id"] == case_id),
                "sft_records": sft_records,
                "deep_audit": {
                    **deep_graph,
                    "evidence_records": [row for row in v41_evidence if row["case_id"] == case_id],
                } if deep_graph else None,
                "v4_records": [
                    {
                        key: row[key]
                        for key in (
                            "qa_id", "answerability", "question_role", "difficulty",
                            "task_context", "gold", "derived_from_qa_id",
                        )
                    }
                    for row in case_records
                ],
            }
        )
    v4_manifest = json.loads((train_dir / "manifest.json").read_text(encoding="utf-8"))
    v41_asset = {
        "dataset_version": "4.1.0-ten-case-on-v4",
        "generated_from": {
            "case_manifest_sha256": sha256(cases_dir / "manifest.json"),
            "training_manifest_sha256": sha256(train_dir / "manifest.json"),
            "v41_case_manifest_sha256": sha256(v41_cases_dir / "manifest.json") if v41_cases_dir.is_dir() else "",
            "v41_training_manifest_sha256": sha256(v41_train_dir / "manifest.json") if v41_train_dir.is_dir() else "",
        },
        "metrics": {
            **v4_manifest["metrics"],
        },
        "counts": {
            "cases": 10,
            "qa_items": 90,
            "dialogue_paths": sum(len(row["dialogue_paths"]) for row in cases),
            "train_records": sum(row["split"] == "train" for row in records),
            "validation_records": sum(row["split"] == "validation" for row in records),
        },
        "cases": cases,
    }
    validate_asset(v41_asset)
    v5_asset = build_v5_asset(source_root)
    validate_asset(v5_asset)
    merged_cases = []
    for source_key, source_asset in (("v41", v41_asset), ("v5", v5_asset)):
        for case in source_asset["cases"]:
            merged_cases.append({**case, "source_dataset": source_key})
    merged_cases.sort(key=lambda row: (row["source_dataset"], row["case_pack"]["case_id"]))
    merged_asset = {
        "dataset_version": "4.1+5.0-merged-ui",
        "generated_from": {
            "v41": v41_asset["generated_from"],
            "v5": v5_asset["generated_from"],
        },
        "metrics": {
            "local_path_signatures": (
                v41_asset["metrics"].get("local_path_signatures", 0)
                + v5_asset["metrics"].get("local_path_signatures", 0)
            ),
            "average_assistant_characters": 0,
        },
        "counts": {
            "cases": 20,
            "qa_items": 180,
            "dialogue_paths": 100,
            "train_records": 144,
            "validation_records": 36,
        },
        "cases": merged_cases,
    }
    validate_merged_asset(merged_asset)
    return {
        **merged_asset,
        "default_dataset": "merged",
        "datasets": {"merged": merged_asset, "v41": v41_asset, "v5": v5_asset},
    }


def validate_asset(asset: dict[str, Any]) -> None:
    if len(asset.get("cases", [])) != 10:
        raise ValueError("expected ten cases")
    splits: Counter[str] = Counter()
    for row in asset["cases"]:
        case_id = row["case_pack"]["case_id"]
        if len(row["qa_items"]) != 9 or len(row["qa_gold"]) != 9 or len(row["sft_records"]) != 9:
            raise ValueError(f"{case_id}: expected nine V4 QA/SFT records")
        if len(row["dialogue_paths"]) != 5 or len(row["case_pack"]["chains"]) != 3:
            raise ValueError(f"{case_id}: dialogue or mother graph incomplete")
        if len({tuple(step["output_ref"] for step in gold["local_reasoning_path"]) for gold in row["qa_gold"]}) < 6:
            raise ValueError(f"{case_id}: local path diversity missing")
        for record in row["sft_records"]:
            splits[record["metadata"]["source_split"]] += 1
            payload = json.loads(record["messages"][2]["content"])
            if "chain_bundle" in payload or not payload.get("local_reasoning_path"):
                raise ValueError(f"{record['metadata']['qa_id']}: V4 local supervision missing")
        if row.get("deep_audit"):
            lengths = {chain["chain_type"]: len(chain["steps"]) for chain in row["case_pack"]["chains"]}
            if lengths["fact_transmission"] < 6 or lengths["author_reasoning"] < 5 or lengths["world_verification"] < 6:
                raise ValueError(f"{case_id}: V4.1 mother graph is not deepened")
            if not row["deep_audit"].get("chain_alignments") or not row["deep_audit"].get("causal_assessments"):
                raise ValueError(f"{case_id}: V4.1 deep audit is incomplete")
    if splits != Counter({"train": 72, "validation": 18}):
        raise ValueError(f"unexpected splits: {dict(splits)}")


def validate_merged_asset(asset: dict[str, Any]) -> None:
    if len(asset.get("cases", [])) != 20:
        raise ValueError("merged asset must contain twenty cases")
    source_counts = Counter(row.get("source_dataset") for row in asset["cases"])
    if source_counts != Counter({"v41": 10, "v5": 10}):
        raise ValueError(f"unexpected merged sources: {dict(source_counts)}")
    case_ids = [row["case_pack"]["case_id"] for row in asset["cases"]]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("merged asset contains duplicate case IDs")
    qa_ids = [item["qa_id"] for row in asset["cases"] for item in row["qa_items"]]
    if len(qa_ids) != 180 or len(qa_ids) != len(set(qa_ids)):
        raise ValueError("merged asset must contain 180 unique QA IDs")
    splits = Counter(
        record["metadata"]["source_split"]
        for row in asset["cases"]
        for record in row["sft_records"]
    )
    if splits != Counter({"train": 144, "validation": 36}):
        raise ValueError(f"unexpected merged splits: {dict(splits)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    asset = build_asset(args.source_root.resolve())
    rendered = "window.SFT_CASES_DATA=" + json.dumps(asset, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + ";\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("sft-cases-data.js is stale; rebuild it")
        print("valid merged UI asset: 20 cases, 180 QA; V4.1 and V5 lineage retained")
        return 0
    args.output.write_text(rendered, encoding="utf-8")
    print(f"built {args.output}: merged 20 cases, 180 QA; V4.1 and V5 lineage retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
