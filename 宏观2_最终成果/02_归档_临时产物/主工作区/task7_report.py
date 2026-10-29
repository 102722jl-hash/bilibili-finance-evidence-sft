"""Deterministic Markdown and CSV renderers for evidence-chain graphs."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import Claim, Edge
from .storage import Store
from .verification import SourceRecord


@dataclass(frozen=True)
class GraphData:
    video_id: str
    title: str
    claims: list[Claim]
    edges: list[Edge]
    sources: list[SourceRecord]


VIDEO_FIELDS = ["bvid", "title"]
CLAIM_FIELDS = [
    "claim_id", "video_id", "node_type", "subject", "predicate", "object", "event_time_start",
    "event_time_end", "quote", "timestamp_start", "timestamp_end", "source_ref", "source_grade",
    "verification_status", "notes",
]
EDGE_FIELDS = [
    "edge_id", "from_claim_id", "to_claim_id", "relation_type", "origin", "mechanism_text",
    "evidence_refs", "confidence", "alternative_explanation", "review_status",
]
SOURCE_FIELDS = [
    "source_id", "url", "publisher", "published_at", "retrieved_at", "source_grade", "title",
    "quoted_support", "raw_sha256", "http_status", "access_failure",
]


def _claim_map(graph: GraphData) -> dict[str, Claim]:
    return {claim.claim_id: claim for claim in graph.claims}


def _edge_lines(graph: GraphData, relation_types: set[str] | None = None) -> list[str]:
    claims = _claim_map(graph)
    lines: list[str] = []
    for edge in sorted(graph.edges, key=lambda item: item.edge_id):
        if relation_types and edge.relation_type not in relation_types:
            continue
        source = claims.get(edge.from_claim_id)
        target = claims.get(edge.to_claim_id)
        if source is None or target is None:
            continue
        lines.append(
            f"- `{source.claim_id}` {source.quote} --[{edge.relation_type}; {edge.origin}; "
            f"{edge.review_status}]--> `{target.claim_id}` {target.quote}"
        )
    return lines or ["- （暂无可渲染关系）"]


def _verification_lines(graph: GraphData) -> list[str]:
    return [
        f"- `{claim.claim_id}`：{claim.verification_status}（来源等级 {claim.source_grade}）"
        for claim in sorted(graph.claims, key=lambda item: item.claim_id)
    ] or ["- （暂无命题）"]


def _mermaid(graph: GraphData) -> str:
    claims = _claim_map(graph)
    lines = ["```mermaid", "graph LR"]
    for claim in sorted(graph.claims, key=lambda item: item.claim_id):
        label = claim.quote.replace("\\", "\\\\").replace('"', "\\\"").replace("[", "(").replace("]", ")")
        lines.append(f'    {claim.claim_id.replace(":", "_")}["{label}"]')
    for edge in sorted(graph.edges, key=lambda item: item.edge_id):
        if edge.from_claim_id not in claims or edge.to_claim_id not in claims:
            continue
        label = f"{edge.relation_type}/{edge.origin}/{edge.review_status}".replace('"', "'")
        lines.append(
            f'    {edge.from_claim_id.replace(":", "_")} -->|"{label}"| {edge.to_claim_id.replace(":", "_")}'
        )
    lines.append("```")
    return "\n".join(lines)


def render_report(graph: GraphData) -> str:
    fact_edges = {"causes", "triggers", "amplifies", "precedes"}
    reasoning_edges = {"supports", "causes"}
    broken = [edge for edge in graph.edges if edge.review_status != "reviewed" or not edge.evidence_refs]
    disputed = [edge for edge in graph.edges if edge.review_status == "disputed" or edge.alternative_explanation]
    lines = [
        f"# {graph.title or graph.video_id}", "", f"- 视频 ID：`{graph.video_id}`",
        f"- 命题数：{len(graph.claims)}；关系数：{len(graph.edges)}", "", "## 事实传导链", "",
        *_edge_lines(graph, fact_edges), "", "## 作者推理链", "", *_edge_lines(graph, reasoning_edges),
        "", "## 外部核验", "", *_verification_lines(graph), "", "## 断裂边、争议边和替代解释", "",
    ]
    lines.extend(
        (f"- `{edge.edge_id}`：断裂或待复核（{edge.review_status}）" for edge in broken)
        if broken else ["- （暂无断裂边）"]
    )
    lines.extend(
        f"- `{edge.edge_id}`：替代解释：{edge.alternative_explanation or '存在争议来源'}"
        for edge in disputed
    )
    lines.extend(["", "## 来源表", "", "| source_id | publisher | grade | title | URL | access_failure |", "| --- | --- | --- | --- | --- | --- |"])
    for source in sorted(graph.sources, key=lambda item: item.source_id):
        lines.append(f"| {source.source_id} | {source.publisher} | {source.source_grade} | {source.title} | {source.url} | {source.access_failure} |")
    lines.extend(["", "## Mermaid 关系图", "", _mermaid(graph), ""])
    return "\n".join(lines)


def load_graph(db_path: str | Path, video_id: str) -> GraphData:
    store = Store(db_path)
    with store._connect() as connection:
        claim_rows = connection.execute("SELECT * FROM claims WHERE video_id = ? ORDER BY claim_id", (video_id,)).fetchall()
        edge_rows = connection.execute(
            "SELECT e.* FROM edges e JOIN claims c ON c.claim_id = e.from_claim_id WHERE c.video_id = ? ORDER BY e.edge_id",
            (video_id,),
        ).fetchall()
        has_sources = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sources'").fetchone()
        source_rows = connection.execute("SELECT * FROM sources ORDER BY source_id").fetchall() if has_sources else []
    claims = [Claim(**dict(row)) for row in claim_rows]
    edges: list[Edge] = []
    for row in edge_rows:
        data = dict(row)
        data["evidence_refs"] = json.loads(data["evidence_refs"])
        edges.append(Edge(**data))
    return GraphData(video_id, video_id, claims, edges, [SourceRecord(**dict(row)) for row in source_rows])


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def export_csv(graph: GraphData, out_dir: str | Path) -> dict[str, Path]:
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    claim_rows = [{field: getattr(claim, field) for field in CLAIM_FIELDS} for claim in sorted(graph.claims, key=lambda item: item.claim_id)]
    edge_rows = []
    for edge in sorted(graph.edges, key=lambda item: item.edge_id):
        row = {field: getattr(edge, field) for field in EDGE_FIELDS}
        row["evidence_refs"] = ";".join(edge.evidence_refs)
        edge_rows.append(row)
    source_rows = [{field: getattr(source, field) for field in SOURCE_FIELDS} for source in sorted(graph.sources, key=lambda item: item.source_id)]
    paths = {
        "videos": directory / "videos.csv", "claims": directory / "claims.csv",
        "edges": directory / "edges.csv", "sources": directory / "sources.csv",
    }
    _write_csv(paths["videos"], VIDEO_FIELDS, [{"bvid": graph.video_id, "title": graph.title}])
    _write_csv(paths["claims"], CLAIM_FIELDS, claim_rows)
    _write_csv(paths["edges"], EDGE_FIELDS, edge_rows)
    _write_csv(paths["sources"], SOURCE_FIELDS, source_rows)
    return paths
