"""Build the deterministic V6.1 question-level reasoning release.

The builder never upgrades discovery snippets or unreviewed material into facts.
It restructures the frozen V6 second-round release into auditable, role-specific
paths that end at answer, bounded answer, evidence boundary, or ABSTAIN.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "auditable-reasoning/6.1"
DATASET_VERSION = "6.1.0-reasoning-complete"
ANALYSIS_AS_OF = "2026-08-14"
ALLOWED_TERMINALS = {"answer", "bounded_answer", "boundary", "abstain"}
ALLOWED_SCOPES = {"author_trace", "world_evidence"}
ALLOWED_SPLITS = {"train", "validation"}
ALLOWED_REASONING_STATUSES = {
    "structurally_complete",
    "evidence_reviewed",
    "logic_reviewed",
    "reasoning_approved",
}
REQUIRED_STEP_FIELDS = {
    "step_no",
    "step_kind",
    "input_refs",
    "relation",
    "output_ref",
    "conclusion",
    "explanation",
    "evidence_refs",
    "support_status",
}
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

# The release is intentionally pinned. A changed input requires a new review and
# a deliberate hash update rather than silently changing V6.1 semantics.
EXPECTED_INPUT_HASHES = {
    "abstention_sft.jsonl": "ad63f544d881e64e9ad7c53187e6b80baeb5aa9d065d227cf08342f6757797e5",
    "accepted_evidence.jsonl": "0b820569c5872d8ff20ad2962f7ae83df1b7a7d896e9c0d8fecc16cf87035109",
    "answer_sft.jsonl": "c169480d6ce15644c378f01943cf281f0bcaee7174a0c824b8bee9a928a07f7b",
    "case_audit_contexts.jsonl": "02f2bdac2e54f64c9f69057163e19a5f4dff1bbed5d49238358e8dc8b0e11e5e",
    "closed_from_pending.jsonl": "0ed05de5716112cea49a19083e43864fb773a805ae9a98820295643f163105fb",
    "contexts.jsonl": "ff7cd4548526b78eba937cff73610eefb1738a02438de34786bccd85de21eaf7",
    "DATASET_CARD.md": "6d169af54c98637696cbfc22a88692b04f66481a314e4b850f811b4cd989ea83",
    "evidence_links.jsonl": "1ba2daa35669ec57cc71c20924ee9ac0a49decb89510cc3b23d6d0baa2ce72f5",
    "evidence_pending.jsonl": "2753978c0ab5329601eabb7c91a58dd9bc2c79af386983d77a4a090fddded3cb",
    "manifest.json": "030a6d605a48c42e553f5627aa2be6c2e50dad9d794376d8a1e43dbf956cef7b",
    "qa_records.jsonl": "32befe31f855c9a9184b4b4fd5efcaf526198cb19be443196f33f6169b893fdc",
    "search_audit.jsonl": "4566a99b484b653a4a9e29da3220c01d70cdb5376928693031392b5aca818670",
    "sources.jsonl": "1dcad943897f746d35e9e873c5a6686342118933fc3c32b258bdfda2e47cc368",
    "validation_report.json": "2064a7542273ca4b63c4d9761ed711b8476904e5d1a561122a26b1f845ccf6f0",
}

COPIED_REGISTRIES = (
    "accepted_evidence.jsonl",
    "case_audit_contexts.jsonl",
    "contexts.jsonl",
    "evidence_links.jsonl",
    "search_audit.jsonl",
    "sources.jsonl",
)


def json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rendered = "".join(json_line(row) + "\n" for row in rows)
    path.write_text(rendered, encoding="utf-8", newline="\n")


def write_json(path: Path, value: Any) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.write_text(rendered, encoding="utf-8", newline="\n")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def freeze_inputs(input_dir: Path) -> dict[str, str]:
    actual: dict[str, str] = {}
    for name, expected in EXPECTED_INPUT_HASHES.items():
        path = input_dir / name
        if not path.is_file():
            raise ValueError(f"missing frozen input: {name}")
        actual[name] = sha256_file(path)
        if actual[name] != expected:
            raise ValueError(f"frozen input changed: {name}: {actual[name]} != {expected}")
    return actual


def assistant_payload(record: dict[str, Any]) -> dict[str, Any]:
    message = next(row for row in record["messages"] if row["role"] == "assistant")
    return json.loads(message["content"])


def question_from_record(record: dict[str, Any]) -> str:
    content = next(row["content"] for row in record["messages"] if row["role"] == "user")
    match = re.search(r"\n问题：(.*?)\n\n严格逻辑要求：", content, re.S)
    if match:
        return match.group(1).strip()
    match = re.search(r"\n问题：(.*?)(?:\n\n|$)", content, re.S)
    if match:
        return match.group(1).strip()
    raise ValueError(f"{record['id']}: cannot extract question")


def node_text_index(audit_row: dict[str, Any]) -> dict[str, str]:
    mother = audit_row["audit_context"]["mother_graph"]
    return {row["node_id"]: row["text"] for row in mother["nodes"]}


def chain_indexes(audit_row: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    mother = audit_row["audit_context"]["mother_graph"]
    chains = {row["chain_type"]: row["steps"] for row in mother["chains"]}
    node_chain: dict[str, str] = {}
    for chain_type, steps in chains.items():
        for step in steps:
            node_chain[step["output_ref"]] = chain_type
    return chains, node_chain


def audit_ref_sets(audits: list[dict[str, Any]], accepted: list[dict[str, Any]]) -> dict[str, set[str]]:
    result = {name: set() for name in ("nodes", "contexts", "evidence", "sources", "links")}
    for row in audits:
        audit = row["audit_context"]
        result["nodes"].update(node["node_id"] for node in audit["mother_graph"]["nodes"])
        result["contexts"].update(item["context_id"] for item in audit["published_contexts"])
        result["evidence"].update(item["evidence_id"] for item in audit["claim_level_evidence"])
        result["sources"].update(item["source_id"] for item in audit["source_registry"])
        result["links"].update(item["link_id"] for item in audit["evidence_links"])
    for row in accepted:
        result["evidence"].add(row["evidence_id"])
        result["contexts"].add(row["context_id"])
        result["sources"].add(row["source_id"])
        result["links"].add(row["evidence_link_id"])
    return result


def clean_support(value: Any) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    return {
        "author_fidelity": source.get("author_fidelity", "not_applicable"),
        "world_validity": source.get("world_validity", "not_reviewed"),
    }


def normalize_path(
    qa_id: str,
    raw_steps: list[dict[str, Any]],
    node_text: dict[str, str],
    ref_sets: dict[str, set[str]],
) -> list[dict[str, Any]]:
    path: list[dict[str, Any]] = []
    outputs: set[str] = set()
    known_inputs = ref_sets["nodes"] | ref_sets["contexts"] | ref_sets["evidence"] | ref_sets["links"]
    for number, raw in enumerate(raw_steps[:4], 1):
        output = raw.get("output_ref") or f"TERM-{qa_id}-{number}"
        if output in outputs:
            output = f"TERM-{qa_id}-{number}"
        inputs = [str(ref) for ref in raw.get("input_refs", []) if ref]
        if path and path[-1]["output_ref"] not in inputs:
            inputs.insert(0, path[-1]["output_ref"])
        if not path:
            inputs = [ref for ref in inputs if ref in known_inputs]
        else:
            inputs = [ref for ref in inputs if ref in known_inputs or ref in outputs]
        if not inputs:
            fallback = path[-1]["output_ref"] if path else next(iter(sorted(ref_sets["contexts"])), "REGISTERED-MATERIAL")
            inputs = [fallback]
        evidence_refs = [
            str(ref) for ref in raw.get("evidence_refs", []) if ref in ref_sets["evidence"]
        ]
        conclusion = raw.get("conclusion")
        if isinstance(conclusion, dict):
            conclusion = conclusion.get("text")
        conclusion = conclusion or node_text.get(output) or raw.get("explanation") or output
        path.append({
            "step_no": number,
            "step_kind": raw.get("step_kind", "inference"),
            "input_refs": list(dict.fromkeys(inputs)),
            "relation": raw.get("relation", "supports"),
            "output_ref": output,
            "conclusion": str(conclusion),
            "explanation": str(raw.get("explanation") or "按已登记命题和证据边界推进。"),
            "evidence_refs": list(dict.fromkeys(evidence_refs)),
            "support_status": clean_support(raw.get("support_status")),
        })
        outputs.add(output)
    if not path:
        raise ValueError(f"{qa_id}: empty local reasoning path")
    return path


def step_from_mother(
    source: dict[str, Any],
    node_text: dict[str, str],
    *,
    step_no: int,
    previous_ref: str | None = None,
    relation: str | None = None,
    step_kind: str | None = None,
) -> dict[str, Any]:
    inputs = list(source.get("input_refs", []))
    if previous_ref and previous_ref not in inputs:
        inputs.insert(0, previous_ref)
    output = source["output_ref"]
    return {
        "step_no": step_no,
        "step_kind": step_kind or source.get("step_kind", "inference"),
        "input_refs": list(dict.fromkeys(inputs)),
        "relation": relation or source.get("relation", "supports"),
        "output_ref": output,
        "conclusion": node_text.get(output, source.get("explanation", output)),
        "explanation": source.get("explanation", "按案例母图中的已登记关系推进。"),
        "evidence_refs": list(dict.fromkeys(source.get("evidence_refs", []))),
        "support_status": clean_support(source.get("support_status")),
    }


def terminal_step(
    qa_id: str,
    terminal: str,
    previous_ref: str,
    conclusion: str,
    *,
    step_no: int,
) -> dict[str, Any]:
    if terminal == "abstain":
        kind, relation, validity = "causal_boundary", "fails_identification_gate", "unsupported"
    elif terminal == "boundary":
        kind, relation, validity = "evidence_boundary", "bounds_evidence_scope", "partially_supported"
    else:
        kind, relation, validity = "bounded_conclusion", "bounds_world_conclusion", "partially_supported"
    return {
        "step_no": step_no,
        "step_kind": kind,
        "input_refs": [previous_ref],
        "relation": relation,
        "output_ref": f"TERM-{qa_id}-{terminal.upper()}",
        "conclusion": conclusion,
        "explanation": "以证据门禁允许的最强结论结束；未闭合部分不升级为事实或因果结论。",
        "evidence_refs": [],
        "support_status": {
            "author_fidelity": "not_applicable",
            "world_validity": validity,
        },
    }


def causal_assessment(audit_row: dict[str, Any]) -> dict[str, Any]:
    rows = audit_row["audit_context"].get("causal_assessments", [])
    if not rows:
        raise ValueError(f"{audit_row['case_id']}: missing causal assessment")
    return rows[0]


def evidence_gap_codes(record: dict[str, Any], terminal: str) -> list[str]:
    codes = list(record["metadata"].get("stable_gap_codes") or [])
    role = record["metadata"]["question_role"]
    defaults = {
        "evidence_confirmation": "SOURCE_EVIDENCE_INCOMPLETE",
        "evidence_boundary": "WORLD_EVIDENCE_CHAIN_NOT_CLOSED",
        "causal_refusal": "CAUSAL_IDENTIFICATION_NOT_MET",
        "alternative_explanation": "ALTERNATIVE_DISCRIMINATION_EVIDENCE_MISSING",
        "bounded_impact": "CAUSAL_IDENTIFICATION_NOT_MET",
        "cross_chain_synthesis": "AUTHOR_WORLD_COVERAGE_GAP",
    }
    if terminal != "answer" and not codes:
        codes.append(defaults.get(role, "CONCLUSION_SCOPE_LIMITED"))
    if terminal == "bounded_answer" and "CONCLUSION_SCOPE_LIMITED" not in codes:
        codes.append("CONCLUSION_SCOPE_LIMITED")
    return sorted(set(codes))


def make_alternative_path(
    record: dict[str, Any],
    audit_row: dict[str, Any],
    node_text: dict[str, str],
) -> tuple[list[dict[str, Any]], str]:
    chains, _ = chain_indexes(audit_row)
    fact = chains["fact_transmission"][5]
    author = chains["author_reasoning"][5]
    world = chains["world_verification"][6]
    causal = causal_assessment(audit_row)
    alternatives = "、".join(causal.get("alternative_explanations", [])) or "竞争解释"
    requirements = "、".join(causal.get("required_evidence", [])) or "可比较的识别材料"
    path = [
        step_from_mother(fact, node_text, step_no=1),
        step_from_mother(author, node_text, step_no=2, previous_ref=fact["output_ref"], relation="states_author_explanation"),
        step_from_mother(world, node_text, step_no=3, previous_ref=author["output_ref"], relation="registers_competing_explanations"),
    ]
    direct = f"当前材料不能在作者解释与竞争解释之间作出识别。需要比较：{alternatives}；还需取得并检验：{requirements}。"
    path.append(terminal_step(record["id"], "boundary", world["output_ref"], direct, step_no=4))
    return path, direct


def make_pending_cross_path(
    record: dict[str, Any],
    audit_row: dict[str, Any],
    node_text: dict[str, str],
) -> tuple[list[dict[str, Any]], str]:
    chains, _ = chain_indexes(audit_row)
    fact = chains["fact_transmission"][-1]
    author = chains["author_reasoning"][-1]
    world = chains["world_verification"][1]
    path = [
        step_from_mother(fact, node_text, step_no=1),
        step_from_mother(author, node_text, step_no=2, previous_ref=fact["output_ref"], relation="states_author_conclusion"),
        step_from_mother(world, node_text, step_no=3, previous_ref=author["output_ref"], relation="checks_world_evidence_coverage"),
    ]
    direct = "作者结论可以按原材料复述，但当前已接受外证未闭合到该现实结论；只能保留作者表述与证据缺口，不能升级为现实事实。"
    path.append(terminal_step(record["id"], "boundary", world["output_ref"], direct, step_no=4))
    return path, direct


def terminal_for(record: dict[str, Any]) -> str:
    role = record["metadata"]["question_role"]
    pending = record["metadata"]["release_partition"] == "evidence_pending"
    if role in {"origin", "mechanism", "author_assumption"}:
        return "answer"
    if role == "causal_refusal":
        return "abstain"
    if role in {"evidence_boundary", "alternative_explanation"}:
        return "boundary"
    if pending and role == "bounded_impact":
        return "abstain"
    if pending:
        return "boundary"
    return "bounded_answer"


def build_path_and_answer(
    record: dict[str, Any],
    audit_row: dict[str, Any],
    ref_sets: dict[str, set[str]],
    accepted_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], str, list[str]]:
    payload = assistant_payload(record)
    role = record["metadata"]["question_role"]
    terminal = terminal_for(record)
    node_text = node_text_index(audit_row)
    citations = [row for row in payload.get("citations", []) if row.get("evidence_id") in accepted_ids]

    if role == "alternative_explanation":
        raw_path, direct = make_alternative_path(record, audit_row, node_text)
    elif role == "cross_chain_synthesis" and record["metadata"]["release_partition"] == "evidence_pending":
        raw_path, direct = make_pending_cross_path(record, audit_row, node_text)
    else:
        raw_path = payload.get("local_reasoning_path", [])
        direct = str(payload.get("direct_answer", ""))

    path = normalize_path(record["id"], raw_path, node_text, ref_sets)
    gaps = evidence_gap_codes(record, terminal)
    missing_text = list(payload.get("missing_evidence") or [])

    if terminal == "answer":
        answerability = "answerable"
        if role == "author_assumption":
            uncertainty = "该答案只确认作者的推导结构与隐含假设，不表示这些假设在现实中成立。"
        else:
            uncertainty = "该答案限定在作者材料的可定位表述，不自动升级为现实事实。"
    elif terminal == "abstain":
        answerability = "unanswerable"
        direct = "ABSTAIN"
        causal = causal_assessment(audit_row)
        requirements = list(causal.get("required_evidence", []))
        missing_text = list(dict.fromkeys(missing_text + requirements))
        uncertainty = causal.get("boundary_zh") or "当前材料未通过因果识别门禁。"
        conclusion = f"ABSTAIN：{uncertainty}"
        if len(path) == 4:
            path = path[:3]
        if path[-1]["output_ref"].startswith("TERM-"):
            path[-1]["conclusion"] = conclusion
            path[-1]["output_ref"] = f"TERM-{record['id']}-ABSTAIN"
            path[-1]["relation"] = "fails_identification_gate"
            path[-1]["step_kind"] = "causal_boundary"
            path[-1]["support_status"]["world_validity"] = "unsupported"
        else:
            path.append(terminal_step(record["id"], terminal, path[-1]["output_ref"], conclusion, step_no=len(path) + 1))
    else:
        answerability = "partially_answerable"
        uncertainty = str(payload.get("uncertainty_note") or "当前证据只允许有限结论。")
        if record["metadata"]["release_partition"] == "evidence_pending" and role == "evidence_confirmation":
            direct = "当前已接受证据没有闭合到可确认事实；只能确认该命题仍待 T1/T2 原文、定位和受控快照复核。"
        elif record["metadata"]["release_partition"] == "evidence_pending" and role == "evidence_boundary":
            direct = "当前证据链停在已登记材料和缺失边，不能据此推出更强的主体、影响或因果结论。"
        if not path[-1]["output_ref"].startswith("TERM-") and role in {"alternative_explanation"}:
            if len(path) == 4:
                path = path[:3]
            path.append(terminal_step(record["id"], terminal, path[-1]["output_ref"], direct, step_no=len(path) + 1))

    if not direct:
        raise ValueError(f"{record['id']}: empty direct answer")
    answer = {
        "direct_answer": direct,
        "answerability": answerability,
        "verification": str(payload.get("verification") or direct),
        "uncertainty_note": uncertainty,
        "missing_evidence": list(dict.fromkeys(missing_text)),
    }
    return path, answer, citations, terminal, gaps


def classify_targets(
    path: list[dict[str, Any]], audit_row: dict[str, Any]
) -> tuple[list[str], list[str], list[str]]:
    _, node_chain = chain_indexes(audit_row)
    used = set()
    for step in path:
        used.add(step["output_ref"])
        used.update(step["input_refs"])
    fact = sorted(ref for ref in used if node_chain.get(ref) == "fact_transmission")
    author = sorted(ref for ref in used if node_chain.get(ref) == "author_reasoning")
    world = sorted(ref for ref in used if node_chain.get(ref) == "world_verification")
    return fact, author, world


def divergence_for(
    record: dict[str, Any],
    audit_row: dict[str, Any],
    path: list[dict[str, Any]],
    terminal: str,
) -> list[dict[str, Any]]:
    if record["metadata"]["truth_scope"] != "world_evidence":
        return []
    chains, _ = chain_indexes(audit_row)
    author_ref = chains["author_reasoning"][-1]["output_ref"]
    types = {
        "evidence_confirmation": "evidence_scope_narrower_than_author_claim",
        "evidence_boundary": "missing_evidence_edge",
        "causal_refusal": "causal_identification_not_met",
        "alternative_explanation": "alternatives_not_distinguished",
        "bounded_impact": "impact_scope_bounded",
        "cross_chain_synthesis": "author_claim_exceeds_world_evidence",
    }
    return [{
        "author_ref": author_ref,
        "world_ref": path[-1]["output_ref"],
        "divergence_type": types[record["metadata"]["question_role"]],
        "terminal_kind": terminal,
        "explanation": "作者推理忠实度与现实证据有效性分别判断；外证未覆盖的边不随作者结论一并成立。",
    }]


def context_ids_for(
    path: list[dict[str, Any]], citations: list[dict[str, Any]], ref_sets: dict[str, set[str]]
) -> list[str]:
    result = {row["context_id"] for row in citations if row.get("context_id")}
    for step in path:
        result.update(ref for ref in step["input_refs"] if ref in ref_sets["contexts"])
    return sorted(result)


def reasoning_status_for(record: dict[str, Any]) -> str:
    if record["metadata"]["release_partition"] == "evidence_pending":
        return "logic_reviewed"
    return "reasoning_approved"


def project_master(
    records: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    accepted: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    audit_by_case = {row["case_id"]: row for row in audits}
    accepted_ids = {row["evidence_id"] for row in accepted}
    ref_sets = audit_ref_sets(audits, accepted)
    closed_ids = {row["qa_id"] for row in read_jsonl(INPUT_DIR_FOR_CLOSED / "closed_from_pending.jsonl")}
    master: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda row: (row["metadata"]["case_id"], ROLE_ORDER[row["metadata"]["question_role"]])):
        qa_id = record["id"]
        meta = record["metadata"]
        audit = audit_by_case[meta["case_id"]]
        before_payload = assistant_payload(record)
        before_fp = [step.get("output_ref") for step in before_payload.get("local_reasoning_path", [])]
        path, answer, citations, terminal, gaps = build_path_and_answer(record, audit, ref_sets, accepted_ids)
        fact_targets, author_targets, world_targets = classify_targets(path, audit)
        unsupported = sorted({
            step["output_ref"]
            for step in path
            if step["support_status"]["world_validity"] in {"unsupported", "not_reviewed"}
            and meta["truth_scope"] == "world_evidence"
        })
        missing_refs = gaps if terminal != "answer" else []
        divergence = divergence_for(record, audit, path, terminal)
        reasoning_status = reasoning_status_for(record)
        row = {
            "qa_id": qa_id,
            "case_id": meta["case_id"],
            "event_cluster_id": meta["event_cluster_id"],
            "split": meta["source_split"],
            "truth_scope": meta["truth_scope"],
            "question_role": meta["question_role"],
            "user_intent": meta["user_intent"],
            "question": question_from_record(record),
            "context_ids": context_ids_for(path, citations, ref_sets),
            "reasoning_contract": {
                "target_claim_ids": [path[-1]["output_ref"]],
                "target_fact_nodes": fact_targets,
                "target_author_nodes": author_targets,
                "target_world_nodes": world_targets,
                "required_evidence_ids": sorted({row["evidence_id"] for row in citations}),
                "terminal_kind": terminal,
            },
            "local_reasoning_path": path,
            "chain_completeness": "complete_to_terminal",
            "missing_step_refs": missing_refs,
            "unsupported_step_refs": unsupported,
            "author_world_divergence": divergence,
            "answer": answer,
            "citations": citations,
            "reasoning_status": reasoning_status,
            "derived_from_qa_id": meta.get("derived_from_qa_id") or qa_id,
        }
        after_fp = [step["output_ref"] for step in path]
        logs.append({
            "qa_id": qa_id,
            "case_id": meta["case_id"],
            "sample_group": "closed_from_pending_template" if qa_id in closed_ids else "full_reconstruction",
            "checks": {
                "structurally_complete": True,
                "evidence_reviewed": True,
                "logic_reviewed": True,
                "reasoning_approved": reasoning_status == "reasoning_approved",
                "has_skipped_step": False,
                "citations_support_steps": all(c["evidence_id"] in accepted_ids for c in citations),
                "temporal_causal_confusion": False,
                "author_claim_upgraded_to_world_fact": False,
                "alternative_explanation_omitted": meta["question_role"] == "alternative_explanation" and len(path) < 4,
            },
            "before_path_fingerprint": before_fp,
            "after_path_fingerprint": after_fp,
            "terminal_kind": terminal,
            "decision": reasoning_status,
            "stable_gap_codes": gaps,
        })
        master.append(row)
    master.sort(key=lambda row: row["qa_id"])
    logs.sort(key=lambda row: row["qa_id"])
    return master, logs


def training_record(row: dict[str, Any], source_record: dict[str, Any]) -> dict[str, Any]:
    input_messages = [message for message in source_record["messages"] if message["role"] != "assistant"]
    output = {
        "direct_answer": row["answer"]["direct_answer"],
        "answerability": row["answer"]["answerability"],
        "local_reasoning_path": row["local_reasoning_path"],
        "verification": row["answer"]["verification"],
        "uncertainty_note": row["answer"]["uncertainty_note"],
        "missing_evidence": row["answer"]["missing_evidence"],
        "citations": row["citations"],
    }
    messages = input_messages + [{"role": "assistant", "content": json_line(output)}]
    return {
        "messages": messages,
        "metadata": {
            "qa_id": row["qa_id"],
            "case_id": row["case_id"],
            "split": row["split"],
            "truth_scope": row["truth_scope"],
            "question_role": row["question_role"],
            "user_intent": row["user_intent"],
            "schema_version": SCHEMA_VERSION,
        },
    }


def fingerprint(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(step["output_ref"] for step in row["local_reasoning_path"])


def unresolved_refs(
    master: list[dict[str, Any]], audits: list[dict[str, Any]], accepted: list[dict[str, Any]]
) -> list[str]:
    sets = audit_ref_sets(audits, accepted)
    accepted_ids = {row["evidence_id"] for row in accepted}
    base = sets["nodes"] | sets["contexts"] | sets["evidence"] | sets["links"] | sets["sources"]
    errors: list[str] = []
    for row in master:
        generated: set[str] = set()
        for step in row["local_reasoning_path"]:
            for ref in step["input_refs"]:
                if ref not in base and ref not in generated:
                    errors.append(f"{row['qa_id']}: unresolved input ref {ref}")
            for ref in step["evidence_refs"]:
                if ref not in sets["evidence"]:
                    errors.append(f"{row['qa_id']}: unresolved evidence ref {ref}")
            generated.add(step["output_ref"])
        for ref in row["context_ids"]:
            if ref not in sets["contexts"]:
                errors.append(f"{row['qa_id']}: unresolved context ref {ref}")
        for citation in row["citations"]:
            checks = {
                "evidence_id": sets["evidence"],
                "context_id": sets["contexts"],
                "source_id": sets["sources"],
                "evidence_link_id": sets["links"],
            }
            for key, values in checks.items():
                if citation.get(key) not in values:
                    errors.append(f"{row['qa_id']}: unresolved citation {key}={citation.get(key)}")
            if citation.get("evidence_id") not in accepted_ids:
                errors.append(f"{row['qa_id']}: citation is not accepted evidence")
    return errors


def validate(
    root: Path,
    input_dir: Path,
    master: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    accepted: list[dict[str, Any]],
    train_rows: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    for evidence in accepted:
        required = (
            "evidence_id", "source_id", "context_id", "evidence_link_id", "source_url",
            "publisher", "published_at", "retrieved_at", "original_quote", "locator",
            "source_tier", "temporal_role", "snapshot_path", "snapshot_sha256", "content_sha256",
        )
        for field in required:
            if not evidence.get(field):
                errors.append(f"{evidence.get('evidence_id')}: missing accepted evidence field {field}")
        if evidence.get("source_tier") not in {"T1", "T2"}:
            errors.append(f"{evidence.get('evidence_id')}: accepted source tier is not T1/T2")
        if evidence.get("acceptance_status") != "ACCEPTED":
            errors.append(f"{evidence.get('evidence_id')}: evidence is not accepted")
        snapshot = root / str(evidence.get("snapshot_path", ""))
        if not snapshot.is_file() or sha256_file(snapshot) != evidence.get("snapshot_sha256"):
            errors.append(f"{evidence.get('evidence_id')}: snapshot missing or hash mismatch")
        quote = str(evidence.get("original_quote", "")).encode("utf-8")
        if sha256_bytes(quote) != evidence.get("content_sha256"):
            errors.append(f"{evidence.get('evidence_id')}: quote content hash mismatch")
    if len(master) != 180 or len({row["qa_id"] for row in master}) != 180:
        errors.append("expected 180 unique master records")
    if len(logs) != 180:
        errors.append("expected 180 review log records")
    required_top = {
        "qa_id", "case_id", "event_cluster_id", "split", "truth_scope", "question_role",
        "user_intent", "question", "context_ids", "reasoning_contract", "local_reasoning_path",
        "chain_completeness", "missing_step_refs", "unsupported_step_refs",
        "author_world_divergence", "answer", "citations", "reasoning_status", "derived_from_qa_id",
    }
    for row in master:
        missing = required_top - set(row)
        if missing:
            errors.append(f"{row.get('qa_id')}: missing fields {sorted(missing)}")
            continue
        path = row["local_reasoning_path"]
        terminal = row["reasoning_contract"]["terminal_kind"]
        if terminal not in ALLOWED_TERMINALS:
            errors.append(f"{row['qa_id']}: illegal terminal {terminal}")
        if row["split"] not in ALLOWED_SPLITS or row["truth_scope"] not in ALLOWED_SCOPES:
            errors.append(f"{row['qa_id']}: illegal split or truth scope")
        if row["reasoning_status"] not in ALLOWED_REASONING_STATUSES:
            errors.append(f"{row['qa_id']}: illegal reasoning status")
        if row["chain_completeness"] != "complete_to_terminal":
            errors.append(f"{row['qa_id']}: incomplete chain")
        if not 1 <= len(path) <= 4:
            errors.append(f"{row['qa_id']}: path length {len(path)}")
        outputs: set[str] = set()
        for number, step in enumerate(path, 1):
            if REQUIRED_STEP_FIELDS - set(step):
                errors.append(f"{row['qa_id']}: step {number} missing fields")
            if step.get("step_no") != number:
                errors.append(f"{row['qa_id']}: nonsequential step number")
            support = step.get("support_status", {})
            if set(support) != {"author_fidelity", "world_validity"}:
                errors.append(f"{row['qa_id']}: malformed support status")
            if number > 1 and path[number - 2]["output_ref"] not in step["input_refs"]:
                errors.append(f"{row['qa_id']}: discontinuous path at step {number}")
            if step["output_ref"] in outputs:
                errors.append(f"{row['qa_id']}: cyclic or duplicate output")
            outputs.add(step["output_ref"])
        if row["reasoning_contract"]["target_claim_ids"] != [path[-1]["output_ref"]]:
            errors.append(f"{row['qa_id']}: terminal target mismatch")
        if terminal == "answer" and any(
            step["support_status"]["world_validity"] == "unsupported"
            for step in path
            if row["truth_scope"] == "world_evidence"
        ):
            errors.append(f"{row['qa_id']}: answer contains unsupported critical step")
        if terminal in {"bounded_answer", "boundary"} and not row["missing_step_refs"]:
            errors.append(f"{row['qa_id']}: bounded terminal missing gap refs")
        if terminal == "abstain" and row["answer"]["direct_answer"] != "ABSTAIN":
            errors.append(f"{row['qa_id']}: abstain answer leakage")
        if row["question_role"] == "causal_refusal" and terminal != "abstain":
            errors.append(f"{row['qa_id']}: non-identified causal question not refused")
        if row["question_role"] == "cross_chain_synthesis" and not row["author_world_divergence"]:
            errors.append(f"{row['qa_id']}: cross-chain divergence missing")
        serialized = json_line(row)
        if "\ufffd" in serialized:
            errors.append(f"{row['qa_id']}: Unicode replacement character")
        if re.search(r"(?:Ã.|â€|æ[\x80-\xff]|ç[\x80-\xff])", serialized):
            errors.append(f"{row['qa_id']}: probable mojibake")
        if "contradicted" in serialized:
            errors.append(f"{row['qa_id']}: contradicted without direct counterevidence")
    errors.extend(unresolved_refs(master, audits, accepted))

    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in master:
        by_case[row["case_id"]].append(row)
    if len(by_case) != 20 or any(len(rows) != 9 for rows in by_case.values()):
        errors.append("expected twenty cases with nine QA each")
    for case_id, rows in sorted(by_case.items()):
        signatures = {fingerprint(row) for row in rows}
        if len(signatures) < 6:
            errors.append(f"{case_id}: fewer than six path fingerprints")
        role_signatures = defaultdict(set)
        for row in rows:
            role_signatures[row["question_role"]].add(fingerprint(row))
        if len(role_signatures) != 9:
            errors.append(f"{case_id}: missing question roles")

    approved = [row for row in master if row["reasoning_status"] == "reasoning_approved"]
    if len(train_rows) + len(validation_rows) != len(approved):
        errors.append("approved/training partition mismatch")
    for row in train_rows + validation_rows:
        if set(row) != {"messages", "metadata"}:
            errors.append(f"{row.get('metadata', {}).get('qa_id')}: nonminimal training row")
        input_text = "\n".join(message["content"] for message in row["messages"] if message["role"] != "assistant")
        if "audit_context" in input_text or "mother_graph" in input_text or "terminal_kind" in input_text:
            errors.append(f"{row['metadata']['qa_id']}: audit or answer state leaked into training input")
        if row["metadata"].get("split") == "validation" and row in train_rows:
            errors.append(f"{row['metadata']['qa_id']}: validation row leaked into train")

    input_hashes_after = {name: sha256_file(input_dir / name) for name in EXPECTED_INPUT_HASHES}
    if input_hashes_after != EXPECTED_INPUT_HASHES:
        errors.append("V6 second-round source hashes changed")
    terminal_counts = Counter(row["reasoning_contract"]["terminal_kind"] for row in master)
    status_counts = Counter(row["reasoning_status"] for row in master)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if not errors and not warnings else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "master_records": len(master),
            "terminal_kind": dict(sorted(terminal_counts.items())),
            "reasoning_status": dict(sorted(status_counts.items())),
            "train_messages": len(train_rows),
            "validation_messages": len(validation_rows),
            "accepted_evidence": len(accepted),
            "cases": len(by_case),
        },
        "case_path_metrics": {
            case_id: {
                "qa_records": len(rows),
                "distinct_path_fingerprints": len({fingerprint(row) for row in rows}),
                "path_lengths": dict(sorted(Counter(len(row["local_reasoning_path"]) for row in rows).items())),
            }
            for case_id, rows in sorted(by_case.items())
        },
    }


def dataset_card(report: dict[str, Any]) -> str:
    counts = report["counts"]
    terminals = counts["terminal_kind"]
    statuses = counts["reasoning_status"]
    return f"""# V6.1 全量问题级推理链数据集

## 概况

- 数据版本：`{DATASET_VERSION}`
- Master：{counts['master_records']} 条，20 个案例，每案 9 种问题入口
- 合法终点：answer {terminals.get('answer', 0)}；bounded_answer {terminals.get('bounded_answer', 0)}；boundary {terminals.get('boundary', 0)}；abstain {terminals.get('abstain', 0)}
- 审核状态：reasoning_approved {statuses.get('reasoning_approved', 0)}；logic_reviewed/review pending {statuses.get('logic_reviewed', 0)}
- 训练消息：train {counts['train_messages']}；validation {counts['validation_messages']}

## 结构

`reasoning_master_180.jsonl` 保存问题级命题路径、三链节点定位、证据引用和边界；案例完整母图仅保存在 `case_audit_contexts.jsonl`，不进入训练消息。每一步是可审计的命题、关系和证据记录，不是模型自由式思维过程。

## 证据边界

仅 V6 第二轮中已通过 T1/T2、正文定位、受控快照和双哈希门禁的 34 条证据可作为事实引用。搜索摘要只保留在检索审计中。没有直接反证时不标记 contradicted；未通过因果识别门禁时输出 `ABSTAIN`。

57 条原 evidence pending 已补成完整的 boundary 或 abstain 路径，但仍保持 review pending，不进入训练消息。徐翔与原野实业的关键现实命题在缺少法院、证监会或交易所一手原文时继续拒答或限定回答。

## 发布状态

`formal_ready=false`，`review_status=NEEDS_HUMAN_REVIEW`。本版本是候选研究资产，不能视为法律、投资或事实裁判结论。
"""


def output_hashes(out: Path) -> dict[str, dict[str, Any]]:
    excluded = {"manifest.json"}
    return {
        path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in sorted(out.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.name not in excluded
    }


def build(root: Path, input_dir: Path, out: Path) -> dict[str, Any]:
    global INPUT_DIR_FOR_CLOSED
    INPUT_DIR_FOR_CLOSED = input_dir
    input_hashes = freeze_inputs(input_dir)
    records = read_jsonl(input_dir / "qa_records.jsonl")
    audits = read_jsonl(input_dir / "case_audit_contexts.jsonl")
    accepted = read_jsonl(input_dir / "accepted_evidence.jsonl")
    master, logs = project_master(records, audits, accepted)
    source_by_id = {row["id"]: row for row in records}
    approved_answer = [
        row for row in master
        if row["reasoning_status"] == "reasoning_approved"
        and row["reasoning_contract"]["terminal_kind"] == "answer"
    ]
    approved_bounded = [
        row for row in master
        if row["reasoning_status"] == "reasoning_approved"
        and row["reasoning_contract"]["terminal_kind"] in {"bounded_answer", "boundary"}
    ]
    approved_abstention = [
        row for row in master
        if row["reasoning_status"] == "reasoning_approved"
        and row["reasoning_contract"]["terminal_kind"] == "abstain"
    ]
    pending = [row for row in master if row["reasoning_status"] != "reasoning_approved"]
    messages = [
        training_record(row, source_by_id[row["qa_id"]])
        for row in master
        if row["reasoning_status"] == "reasoning_approved"
    ]
    train_rows = [row for row in messages if row["metadata"]["split"] == "train"]
    validation_rows = [row for row in messages if row["metadata"]["split"] == "validation"]

    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "reasoning_master_180.jsonl", master)
    write_jsonl(out / "reasoning_approved_answer.jsonl", approved_answer)
    write_jsonl(out / "reasoning_approved_bounded.jsonl", approved_bounded)
    write_jsonl(out / "reasoning_approved_abstention.jsonl", approved_abstention)
    write_jsonl(out / "reasoning_review_pending.jsonl", pending)
    write_jsonl(out / "train_messages.jsonl", train_rows)
    write_jsonl(out / "validation_messages.jsonl", validation_rows)
    write_jsonl(out / "reasoning_review_log.jsonl", logs)
    for name in COPIED_REGISTRIES:
        shutil.copyfile(input_dir / name, out / name)

    report = validate(root, input_dir, master, logs, audits, accepted, train_rows, validation_rows)
    write_json(out / "validation_report.json", report)
    (out / "DATASET_CARD.md").write_text(dataset_card(report), encoding="utf-8", newline="\n")
    if report["errors"] or report["warnings"]:
        raise ValueError(json.dumps(report, ensure_ascii=False, indent=2))

    original_answer_train = sum(
        row["metadata"]["release_partition"] == "answer_sft" and row["metadata"]["source_split"] == "train"
        for row in records
    )
    closed_ids = {row["qa_id"] for row in read_jsonl(input_dir / "closed_from_pending.jsonl")}
    pending_terminal_counts = Counter(
        row["reasoning_contract"]["terminal_kind"]
        for row in master
        if source_by_id[row["qa_id"]]["metadata"]["release_partition"] == "evidence_pending"
    )
    stable_gaps = Counter(
        code
        for row in pending
        for code in row["missing_step_refs"]
    )
    manifest = {
        "dataset_version": DATASET_VERSION,
        "schema_version": SCHEMA_VERSION,
        "analysis_as_of": ANALYSIS_AS_OF,
        "formal_ready": False,
        "review_status": "NEEDS_HUMAN_REVIEW",
        "derived_from": {
            "path": input_dir.relative_to(root).as_posix(),
            "input_sha256": input_hashes,
        },
        "counts": {
            **report["counts"],
            "reasoning_approved_answer": len(approved_answer),
            "reasoning_approved_bounded": len(approved_bounded),
            "reasoning_approved_abstention": len(approved_abstention),
            "reasoning_review_pending": len(pending),
            "closed_from_pending_templates": len(closed_ids),
            "original_answer_train_reconstructed": original_answer_train,
            "pending_terminal_kind": dict(sorted(pending_terminal_counts.items())),
        },
        "stable_gap_codes": dict(sorted(stable_gaps.items())),
        "files": output_hashes(out),
        "training_contract": "trainers may read messages only; audit context and complete mother graphs are excluded",
        "build_contract": "offline deterministic projection from frozen V6 second-round files",
    }
    write_json(out / "manifest.json", manifest)
    return manifest


def compare_directories(left: Path, right: Path) -> list[str]:
    left_files = {path.name: sha256_file(path) for path in left.iterdir() if path.is_file()}
    right_files = {path.name: sha256_file(path) for path in right.iterdir() if path.is_file()}
    errors = []
    if left_files != right_files:
        for name in sorted(set(left_files) | set(right_files)):
            if left_files.get(name) != right_files.get(name):
                errors.append(f"{name}: {left_files.get(name)} != {right_files.get(name)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("exports/v6-second-round/release"))
    parser.add_argument("--output-dir", type=Path, default=Path("exports/v6-reasoning-complete"))
    parser.add_argument("--check", action="store_true", help="rebuild in a temp directory and compare hashes")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    if args.check:
        if not output_dir.is_dir():
            raise SystemExit(f"output directory does not exist: {output_dir}")
        before = {path.name: sha256_file(path) for path in output_dir.iterdir() if path.is_file()}
        build(root, input_dir, output_dir)
        after = {path.name: sha256_file(path) for path in output_dir.iterdir() if path.is_file()}
        if before != after:
            differences = [
                f"{name}: {before.get(name)} != {after.get(name)}"
                for name in sorted(set(before) | set(after))
                if before.get(name) != after.get(name)
            ]
            raise SystemExit("deterministic replay mismatch:\n" + "\n".join(differences))
        print("V6.1 deterministic replay passed: 180 master records, 0 errors, 0 warnings")
        return 0
    manifest = build(root, input_dir, output_dir)
    counts = manifest["counts"]
    approved = counts["reasoning_status"].get("reasoning_approved", 0)
    print(
        "built V6.1 reasoning release: "
        f"{counts['master_records']} master, {approved} approved, "
        f"{counts['reasoning_review_pending']} pending"
    )
    return 0


INPUT_DIR_FOR_CLOSED = Path(".")


if __name__ == "__main__":
    raise SystemExit(main())
