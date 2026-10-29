"""Export V4.1 auditable QA records in a v23-compatible SFT envelope."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROLE_NAMES = {
    "origin": "事件起点识别",
    "mechanism": "作用机制解释",
    "author_assumption": "作者隐含假设识别",
    "evidence_confirmation": "外部证据确认",
    "evidence_boundary": "证据边界判断",
    "causal_refusal": "因果归因拒答",
    "alternative_explanation": "替代解释比较",
    "bounded_impact": "有边界现实影响判断",
    "cross_chain_synthesis": "跨链综合判断",
}

ANSWERABILITY_TEXT = {
    "answerable": "材料足以支持有边界回答",
    "partially_answerable": "材料仅支持部分回答",
    "unanswerable": "材料不足，必须拒绝确定回答",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_ui_asset(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    prefix = "window.SFT_CASES_DATA="
    if not text.startswith(prefix):
        raise ValueError("unsupported UI asset envelope")
    payload = text[len(prefix):]
    if payload.endswith(";"):
        payload = payload[:-1]
    value = json.loads(payload)
    if not isinstance(value, dict) or not isinstance(value.get("cases"), list):
        raise ValueError("invalid UI asset")
    return value


def build_ui_audit_context(ui_case: dict[str, Any]) -> dict[str, Any]:
    pack = ui_case["case_pack"]
    deep = ui_case.get("deep_audit") or {}
    evidence = deep.get("evidence_records", [])
    return {
        "schema_version": "ui-audit-context/1.0",
        "training_visibility": "metadata_only_excluded_from_messages",
        "usage_note": "用于复现案例工作台和人工审计；训练器只读取 messages，不得把本字段作为输入或标签。",
        "case_overview": {
            key: pack.get(key)
            for key in (
                "case_id", "event_cluster_id", "title", "video_id", "entities", "time_scope",
                "source_provenance", "sponsorship_disclosure", "review_status", "reviewer_id",
                "generator_id", "dataset_version", "split",
            )
            if key in pack
        },
        "ui_summary": {
            "node_count": len(pack.get("nodes", [])),
            "chain_step_counts": {
                chain["chain_type"]: len(chain.get("steps", [])) for chain in pack.get("chains", [])
            },
            "question_count": len(ui_case.get("qa_items", [])),
            "dialogue_path_count": len(ui_case.get("dialogue_paths", [])),
            "source_count": len(ui_case.get("sources", [])),
            "context_count": len(ui_case.get("contexts", [])),
            "evidence_link_count": len(ui_case.get("evidence_links", [])),
            "claim_evidence_status_counts": {
                status: sum(row.get("acceptance_status") == status for row in evidence)
                for status in ("ACCEPTED", "CONTEXT_ONLY", "GAP")
            },
        },
        "author_central_claim": (ui_case.get("macro_narrative") or {}).get("central_claim", ""),
        "macro_narrative": ui_case.get("macro_narrative"),
        "mother_graph": {
            "graph_id": deep.get("graph_id"),
            "nodes": pack.get("nodes", []),
            "chains": pack.get("chains", []),
            "critical_distinctions": deep.get("critical_distinctions", []),
        },
        "chain_alignments": deep.get("chain_alignments", []),
        "claim_level_evidence": evidence,
        "causal_assessments": deep.get("causal_assessments", []),
        "completeness": deep.get("completeness", {}),
        "source_registry": ui_case.get("sources", []),
        "published_contexts": ui_case.get("contexts", []),
        "evidence_links": ui_case.get("evidence_links", []),
        "question_catalog": ui_case.get("qa_items", []),
        "dialogue_paths": ui_case.get("dialogue_paths", []),
        "followup_graph": ui_case.get("followup_graph"),
    }


def render_user(row: dict[str, Any]) -> str:
    materials = "\n".join(
        f"[{step['output_ref']}] {step['conclusion']}"
        for step in row["gold"]["local_reasoning_path"]
    )
    return (
        f"分析对象：{row['case_id']}\n"
        f"推理任务：{ROLE_NAMES[row['question_role']]}\n"
        f"真值范围：{row['truth_scope']}\n"
        f"可回答性目标：{ANSWERABILITY_TEXT[row['answerability']]}\n\n"
        f"材料：\n{materials}\n\n"
        f"问题：{row['question']}\n\n"
        "严格逻辑要求：请区分作者表述与现实证据，按材料列出前提、关系、"
        "中间结论和最终结论；时间先后不自动构成因果。证据不足时必须明确缺口，"
        "不得把背景材料或搜索线索写成已确认事实。"
    )


def render_assistant(row: dict[str, Any]) -> str:
    gold = row["gold"]
    path = gold["local_reasoning_path"]
    lines = [f"最终判断：{ANSWERABILITY_TEXT[row['answerability']]}。"]
    for index, step in enumerate(path, 1):
        status = step["support_status"]
        lines.append(
            f"前提/步骤{index}：{step['conclusion']}"
            f"（关系：{step['relation']}；作者忠实度：{status['author_fidelity']}；"
            f"现实有效性：{status['world_validity']}）。"
        )
    lines.append("规则一（真值范围）：作者推理忠实只说明准确复原作者论证，不等于现实因果成立。")
    lines.append("规则二（时间与因果）：时间先后或机制一致性不能替代比较组、混杂控制和稳健性检验。")
    lines.append("规则三（证据门槛）：只有可定位并通过审核的来源材料才能支持对应现实命题；缺口不得当作反证。")
    if len(path) > 1:
        lines.append(f"中间结论：局部路径依次连接为 {' -> '.join(step['output_ref'] for step in path)}。")
    else:
        lines.append(f"中间结论：当前问题只需要命题 {path[0]['output_ref']}，无需展开案例完整母图。")
    lines.append(f"最终结论：{gold['direct_answer']}")
    lines.append(f"核验结论：{gold['verification']}")
    lines.append(f"边界：{gold['uncertainty_note']}")
    if gold["missing_evidence"]:
        lines.append("缺失证据：" + "；".join(gold["missing_evidence"]) + "。")
    if gold["citations"]:
        refs = [
            f"{item['evidence_id']}（{item['source_id']}，{item['locator']}）"
            for item in gold["citations"]
        ]
        lines.append("引用：" + "；".join(refs) + "。")
    else:
        lines.append("引用：当前局部回答没有可发布的正式外证引用；不得自行补造。")
    return "\n".join(lines)


def project(row: dict[str, Any], case_title: str, ui_case: dict[str, Any]) -> dict[str, Any]:
    gold = row["gold"]
    source_family = "V5" if row["dataset_version"].startswith("5.") else "V4.1"
    return {
        "id": row["qa_id"],
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是严格有向逻辑链分析助手。每个结论必须由给定材料中的明确前提经过可审计关系推出；"
                    "区分作者推理与现实证据，核对时间、来源和支持状态。证据不足时限定回答或拒答；"
                    "不输出自由式思维过程，只输出可审计的命题路径和证据边界。"
                ),
            },
            {"role": "user", "content": render_user(row)},
            {"role": "assistant", "content": render_assistant(row)},
        ],
        "metadata": {
            "entity": case_title,
            "case_id": row["case_id"],
            "event_cluster_id": row["event_cluster_id"],
            "analysis_as_of": "2026-08-13",
            "logic_key": row["question_role"],
            "logic_name": ROLE_NAMES[row["question_role"]],
            "logic_provenance": row["audit_context_ref"],
            "rule_state": row["answerability"],
            "rule_state_text": ANSWERABILITY_TEXT[row["answerability"]],
            "truth_scope": row["truth_scope"],
            "user_intent": row["user_intent"],
            "chain_class": row["question_role"],
            "dataset_version": row["dataset_version"],
            "sft_version": f"{source_family.lower()}-v23-compatible-merged",
            "source_version": f"{source_family} auditable QA",
            "split": row["split"],
            "derived_from_qa_id": row["derived_from_qa_id"],
            "premise_chain_v41": gold["local_reasoning_path"],
            "source_records": gold["citations"],
            "missing_evidence": gold["missing_evidence"],
            "verification": gold["verification"],
            "uncertainty_note": gold["uncertainty_note"],
            "final_result": {
                "answerability": row["answerability"],
                "direct_answer": gold["direct_answer"],
                "path_length": len(gold["local_reasoning_path"]),
                "citation_count": len(gold["citations"]),
                "causal_attribution_allowed": False,
                "boundary": gold["uncertainty_note"],
            },
            "ui_audit_context": build_ui_audit_context(ui_case),
            "format_compatibility": {
                "reference_envelope": "financial_reasoning_sft_v23_100.json",
                "top_level_fields": ["id", "messages", "metadata"],
                "domain_specific_financial_fields_fabricated": False,
            },
        },
    }


def validate(rows: list[dict[str, Any]], expected_count: int) -> None:
    if len(rows) != expected_count or len({row["id"] for row in rows}) != expected_count:
        raise ValueError(f"expected {expected_count} unique records")
    case_counts = Counter(row["metadata"]["case_id"] for row in rows)
    if set(case_counts.values()) != {9}:
        raise ValueError(f"expected nine records per case: {dict(case_counts)}")
    cluster_splits: dict[str, set[str]] = {}
    for row in rows:
        cluster_splits.setdefault(row["metadata"]["event_cluster_id"], set()).add(row["metadata"]["split"])
    leaking = {cluster: sorted(splits) for cluster, splits in cluster_splits.items() if len(splits) > 1}
    if leaking:
        raise ValueError(f"event clusters cross splits: {leaking}")
    for row in rows:
        if set(row) != {"id", "messages", "metadata"}:
            raise ValueError(f"{row.get('id')}: incompatible top-level envelope")
        if [message["role"] for message in row["messages"]] != ["system", "user", "assistant"]:
            raise ValueError(f"{row['id']}: invalid message sequence")
        if not all(isinstance(message["content"], str) and message["content"] for message in row["messages"]):
            raise ValueError(f"{row['id']}: empty message")
        if "audit_context" in "\n".join(message["content"] for message in row["messages"]):
            raise ValueError(f"{row['id']}: mother graph leaked into messages")
        path = row["metadata"]["premise_chain_v41"]
        if not 1 <= len(path) <= 4:
            raise ValueError(f"{row['id']}: invalid local path length")
        ui_context = row["metadata"].get("ui_audit_context", {})
        if ui_context.get("training_visibility") != "metadata_only_excluded_from_messages":
            raise ValueError(f"{row['id']}: UI audit context training boundary missing")
        mother_graph = ui_context.get("mother_graph", {})
        if len(mother_graph.get("chains", [])) != 3 or len(mother_graph.get("nodes", [])) < 23:
            raise ValueError(f"{row['id']}: UI mother graph incomplete")
        if len(ui_context.get("question_catalog", [])) != 9:
            raise ValueError(f"{row['id']}: UI question catalog incomplete")
        if len(ui_context.get("dialogue_paths", [])) != 5:
            raise ValueError(f"{row['id']}: UI dialogue paths incomplete")
        if not ui_context.get("causal_assessments") or not ui_context.get("completeness"):
            raise ValueError(f"{row['id']}: UI audit diagnostics incomplete")


def records_from_ui_dataset(dataset: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    cases: dict[str, dict[str, Any]] = {}
    for ui_case in dataset["cases"]:
        pack = ui_case["case_pack"]
        case_id = pack["case_id"]
        cases[case_id] = ui_case
        questions = {row["qa_id"]: row for row in ui_case["qa_items"]}
        golds = {row["qa_id"]: row for row in ui_case["qa_gold"]}
        for sft in ui_case["sft_records"]:
            metadata = sft["metadata"]
            qa_id = metadata["qa_id"]
            item = questions[qa_id]
            gold = dict(golds[qa_id])
            gold.pop("qa_id", None)
            gold.pop("target_ref_ids", None)
            records.append({
                "qa_id": qa_id,
                "case_id": case_id,
                "event_cluster_id": pack["event_cluster_id"],
                "dataset_version": pack["dataset_version"],
                "derived_from_qa_id": qa_id,
                "audit_context_ref": pack.get("graph_id") or (ui_case.get("deep_audit") or {}).get("graph_id"),
                "split": metadata["source_split"],
                "truth_scope": metadata["truth_scope"],
                "user_intent": metadata["user_intent"],
                "question_role": metadata["question_role"],
                "answerability": metadata["answerability"],
                "question": item["standalone_question"],
                "gold": gold,
            })
    return sorted(records, key=lambda row: row["qa_id"]), cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--graphs", type=Path)
    parser.add_argument("--ui-asset", type=Path, required=True)
    parser.add_argument("--ui-dataset", choices=("merged", "v41", "v5"), default="merged")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    ui_asset = read_ui_asset(args.ui_asset)
    if ui_asset.get("datasets"):
        dataset = ui_asset["datasets"][args.ui_dataset]
    else:
        dataset = ui_asset
    records, ui_cases = records_from_ui_dataset(dataset)
    output = [project(row, ui_cases[row["case_id"]]["case_pack"]["title"], ui_cases[row["case_id"]]) for row in records]
    validate(output, len(records))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"exported {len(output)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
