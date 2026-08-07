# Bilibili Evidence Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public-source research pipeline that collects 10 capital-market/company-case videos from the specified Bilibili UP, aligns official article text with video evidence, and produces fact-propagation and author-reasoning graphs with auditable verification metadata.

**Architecture:** A Python CLI stores immutable raw source snapshots and normalized records in a local project directory. Source adapters handle Bilibili public pages and user-supplied/confirmed public WeChat article URLs; deterministic text processing creates atomic-claim candidates, while explicit edge records separate facts, mechanisms, inferences, and conclusions. Markdown, Mermaid, and CSV reports are rendered from the same SQLite-backed graph.

**Tech Stack:** Python 3.11+, `requests`, `beautifulsoup4`, `pytest`, SQLite (`sqlite3`), JSONL/CSV, Mermaid in Markdown. ASR is an optional adapter and is not required for the article-first pilot.

---

### Task 1: Scaffold the research package and test fixtures

**Files:**
- Create: `pyproject.toml`
- Create: `src/evidence_chain/__init__.py`
- Create: `src/evidence_chain/cli.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/bilibili_video.html`
- Create: `tests/fixtures/article.html`

- [ ] **Step 1: Write the failing CLI smoke test**

```python
def test_cli_help_runs(capsys):
    from evidence_chain.cli import main
    assert main(["--help"]) == 0
    assert "collect" in capsys.readouterr().out
```

- [ ] **Step 2: Run the test and confirm the scaffold is missing**

Run: `python -m pytest tests/test_cli.py -q`
Expected: FAIL because `tests/test_cli.py` and the package entry point do not exist yet.

- [ ] **Step 3: Add the package metadata and minimal CLI**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "evidence-chain"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["requests>=2.31", "beautifulsoup4>=4.12"]

[project.scripts]
evidence-chain = "evidence_chain.cli:main"
```

```python
# src/evidence_chain/cli.py
import argparse

def main(argv=None):
    parser = argparse.ArgumentParser(prog="evidence-chain")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("collect")
    sub.add_parser("extract")
    sub.add_parser("report")
    parser.parse_args(argv)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the smoke test and install editable package**

Run: `python -m pytest tests/test_cli.py -q` and `python -m pip install -e .`
Expected: PASS and an `evidence-chain` console command is available.

- [ ] **Step 5: Commit the scaffold**

```bash
git add pyproject.toml src tests
git commit -m "chore: scaffold evidence chain package"
```

### Task 2: Define graph records and durable local storage

**Files:**
- Create: `src/evidence_chain/models.py`
- Create: `src/evidence_chain/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write model and round-trip tests**

```python
def test_claim_and_edge_round_trip(tmp_path):
    from evidence_chain.models import Claim, Edge
    from evidence_chain.storage import Store
    store = Store(tmp_path / "research.db")
    claim = Claim("C1", "V1", "F", "监管", "清理", "场外配资", "2015-06-01", None, "原文", 0, 4, "SRC1", "S5", "confirmed", "")
    edge = Edge("E1", "C1", "C2", "triggers", "explicit_author", "", ["SRC1"], "medium", "", "open")
    store.put_claim(claim)
    store.put_edge(edge)
    assert store.get_claim("C1").claim_id == "C1"
    assert store.get_edge("E1").from_claim_id == "C1"
```

- [ ] **Step 2: Implement typed dataclasses and SQLite schema**

`Claim` fields must match the specification: `claim_id`, `video_id`, `node_type`, `subject`, `predicate`, `object`, event bounds, quote/timestamps, source reference, source grade, verification status, and notes. `Edge` must contain both claim IDs, relation type, origin, mechanism text, evidence references, confidence, alternative explanation, and review status. `Store` must create tables with primary keys and JSON-encode evidence-reference lists.

- [ ] **Step 3: Run the storage test**

Run: `python -m pytest tests/test_storage.py -q`
Expected: PASS with a temporary SQLite database and no network access.

- [ ] **Step 4: Commit the graph core**

```bash
git add src/evidence_chain/models.py src/evidence_chain/storage.py tests/test_storage.py
git commit -m "feat: add claim graph models and sqlite storage"
```

### Task 3: Collect public Bilibili metadata without bypassing controls

**Files:**
- Create: `src/evidence_chain/sources/bilibili.py`
- Create: `tests/test_bilibili_source.py`
- Modify: `src/evidence_chain/cli.py`

- [ ] **Step 1: Write parser tests against a saved HTML fixture**

```python
def test_parse_video_page_extracts_canonical_metadata():
    from evidence_chain.sources.bilibili import parse_video_page
    record = parse_video_page(open("tests/fixtures/bilibili_video.html", encoding="utf8").read(), "https://www.bilibili.com/video/BVTEST/")
    assert record.bvid == "BVTEST"
    assert record.title.startswith("【巫师】")
    assert record.author_mid == "472747194"
```

- [ ] **Step 2: Implement `fetch_public_video(url)` with a fixed user agent, timeout, and one request per URL**

The adapter must use `requests.get`, accept only `bilibili.com` URLs, save the response body and SHA-256 under `data/raw/bilibili/<bvid>/`, and return a metadata record. It must raise a typed `SourceBlocked` error on CAPTCHA/login/HTTP 403/412 instead of retrying aggressively.

- [ ] **Step 3: Add a `collect` CLI command**

```text
evidence-chain collect --video-url https://www.bilibili.com/video/BV1Htgh6DErU/ --out data
```

The command writes `videos.csv` and a raw HTML snapshot, but does not download the video stream.

- [ ] **Step 4: Run fixture tests**

Run: `python -m pytest tests/test_bilibili_source.py -q`
Expected: PASS; add a separate `@pytest.mark.network` smoke test that is skipped unless `RUN_NETWORK_TESTS=1`.

- [ ] **Step 5: Commit the public metadata collector**

```bash
git add src/evidence_chain/sources/bilibili.py src/evidence_chain/cli.py tests/test_bilibili_source.py
git commit -m "feat: collect public bilibili metadata"
```

### Task 4: Discover and fetch official synchronized article text

**Files:**
- Create: `src/evidence_chain/sources/wechat.py`
- Create: `src/evidence_chain/text.py`
- Create: `tests/test_wechat_source.py`
- Create: `tests/test_text.py`

- [ ] **Step 1: Write tests for official-article extraction and blocked access**

```python
def test_parse_article_preserves_title_author_and_paragraphs():
    from evidence_chain.sources.wechat import parse_article
    article = parse_article(open("tests/fixtures/article.html", encoding="utf8").read(), "https://mp.weixin.qq.com/s/TEST")
    assert article.title.startswith("【巫师】")
    assert article.author == "巫师财经"
    assert "国家队" in article.text

def test_captcha_is_recorded_as_blocked():
    from evidence_chain.sources.wechat import parse_article, SourceBlocked
    html = "<html><body>验证码 VerifyCode</body></html>"
    try:
        parse_article(html, "https://weixin.sogou.com/link/blocked")
    except SourceBlocked as exc:
        assert "captcha" in str(exc).lower()
    else:
        raise AssertionError("captcha page must not be treated as article text")
```

- [ ] **Step 2: Implement article URL ingestion**

`discover_article_candidates(query)` may use a public search index, but it must return candidate URLs and snippets only. `fetch_article(url)` accepts a manually confirmed `mp.weixin.qq.com` URL, saves raw HTML and hash, and stops on CAPTCHA, login, or robots denial. It must never attempt to solve the challenge or enumerate hidden article URLs.

- [ ] **Step 3: Normalize article and subtitle text**

`normalize_text` removes navigation/footer boilerplate, keeps paragraph boundaries, normalizes full-width punctuation without changing wording, and records a mapping from normalized paragraph IDs to raw offsets.

- [ ] **Step 4: Run text and source tests**

Run: `python -m pytest tests/test_wechat_source.py tests/test_text.py -q`
Expected: PASS with local fixtures only.

- [ ] **Step 5: Commit article ingestion**

```bash
git add src/evidence_chain/sources/wechat.py src/evidence_chain/text.py tests/test_wechat_source.py tests/test_text.py tests/fixtures/article.html
git commit -m "feat: ingest official article text with blocked-source handling"
```

### Task 5: Generate atomic-claim candidates and author reasoning edges

**Files:**
- Create: `src/evidence_chain/claims.py`
- Create: `src/evidence_chain/edges.py`
- Create: `tests/test_claims.py`
- Create: `tests/test_edges.py`

- [ ] **Step 1: Write deterministic claim-splitting tests**

```python
def test_split_claims_separates_fact_mechanism_and_conclusion():
    from evidence_chain.claims import split_claims
    claims = split_claims("证金买入救市标的，因此价格不敏感，作者认为这是可预测的买方。")
    assert [claim.node_type for claim in claims] == ["F", "M", "C"]
```

- [ ] **Step 2: Implement sentence splitting and typed candidates**

Split on sentence punctuation and causal cue phrases (`因此`, `所以`, `意味着`, `说明`, `背后是`, `这就是`). Extract explicit dates, percentages, currency amounts, stock codes, and named entities into structured fields. Never infer a causal edge solely from adjacency; create a `precedes` edge first when only temporal order is available.

- [ ] **Step 3: Implement edge generation**

`build_author_edges(claims)` creates `explicit_author` edges when cue phrases or explicit verbs are present, and `implicit_author` edges only when the same paragraph has a resolvable subject and a causal verb. Every implicit edge gets `confidence="low"` until reviewed.

- [ ] **Step 4: Run extraction tests**

Run: `python -m pytest tests/test_claims.py tests/test_edges.py -q`
Expected: PASS, including a regression test proving that “随后” creates `precedes`, not `causes`.

- [ ] **Step 5: Commit claim extraction**

```bash
git add src/evidence_chain/claims.py src/evidence_chain/edges.py tests/test_claims.py tests/test_edges.py
git commit -m "feat: extract atomic claims and author reasoning edges"
```

### Task 6: Add evidence records and external-verification workflow

**Files:**
- Create: `src/evidence_chain/verification.py`
- Create: `tests/test_verification.py`
- Modify: `src/evidence_chain/storage.py`

- [ ] **Step 1: Write verification-state tests**

```python
def test_unverified_claim_is_not_labeled_false():
    from evidence_chain.verification import classify_claim
    result = classify_claim([], [])
    assert result.status == "unverifiable"
    assert result.status != "contradicted"
```

- [ ] **Step 2: Implement source and evidence records**

Store source URL, publisher, publication time, retrieved time, source grade (`S1`–`S5`), title, quoted support, hash, HTTP status, and access failure. `classify_claim` must distinguish no evidence, supporting evidence, contradictory evidence, and conflicting sources.

- [ ] **Step 3: Add structured review import**

Accept a reviewer CSV with `claim_id`, `status`, `source_grade`, `evidence_refs`, `reason`, and `reviewer`. Reject unknown claim IDs and invalid status/grade values with line-numbered errors.

- [ ] **Step 4: Run verification tests**

Run: `python -m pytest tests/test_verification.py -q`
Expected: PASS, including conflicting-source and missing-source cases.

- [ ] **Step 5: Commit verification workflow**

```bash
git add src/evidence_chain/verification.py src/evidence_chain/storage.py tests/test_verification.py
git commit -m "feat: add evidence grades and verification states"
```

### Task 7: Render per-video reports and graph exports

**Files:**
- Create: `src/evidence_chain/report.py`
- Create: `tests/test_report.py`
- Modify: `src/evidence_chain/cli.py`

- [ ] **Step 1: Write report fixture tests**

```python
def test_report_contains_both_chains_and_source_table(tmp_path):
    from evidence_chain.report import render_report
    report = render_report(sample_graph())
    assert "事实传导链" in report
    assert "作者推理链" in report
    assert "外部核验" in report
    assert "```mermaid" in report
```

- [ ] **Step 2: Implement deterministic renderers**

Render Markdown sections in the order specified by the design. Render Mermaid node labels with escaped punctuation and show edge origin/status. Export `videos.csv`, `claims.csv`, `edges.csv`, and `sources.csv` with stable column order.

- [ ] **Step 3: Add the `report` CLI command**

```text
evidence-chain report --video-id BV1Htgh6DErU --db data/research.db --out reports/BV1Htgh6DErU.md
```

- [ ] **Step 4: Run report tests**

Run: `python -m pytest tests/test_report.py -q`
Expected: PASS with stable output snapshots.

- [ ] **Step 5: Commit report generation**

```bash
git add src/evidence_chain/report.py src/evidence_chain/cli.py tests/test_report.py
git commit -m "feat: render evidence and reasoning chain reports"
```

### Task 8: Run a one-video pilot and validate the 10-video intake

**Files:**
- Create: `data/sample_manifest.csv`
- Create: `reports/BV1Htgh6DErU.md`
- Create: `reports/README.md`
- Modify: `src/evidence_chain/cli.py`

- [ ] **Step 1: Add the confirmed pilot manifest**

Use the public BVID `BV1Htgh6DErU` for the Xu Xiang video and leave the article URL blank until a public article URL is manually confirmed. Store the Sogou search result URL as `discovery_source`, not as the article itself.

- [ ] **Step 2: Execute the article-first pilot**

Run:

```text
evidence-chain collect --manifest data/sample_manifest.csv --out data
evidence-chain extract --video-id BV1Htgh6DErU --db data/research.db
evidence-chain report --video-id BV1Htgh6DErU --db data/research.db --out reports/BV1Htgh6DErU.md
```

Expected: a report with both chains, at least one explicitly marked unsupported or unverifiable author inference, and no claim that a search snippet is a primary source.

- [ ] **Step 3: Validate the 10-video manifest**

Run: `evidence-chain validate-manifest --manifest data/sample_manifest.csv`
Expected: exactly 10 unique BVIDs, all author mids equal `472747194`, no duplicate title, and every row has a selection rationale.

- [ ] **Step 4: Run the complete test suite**

Run: `python -m pytest -q`
Expected: all local tests pass; live-network tests remain skipped unless explicitly enabled.

- [ ] **Step 5: Commit the pilot outputs**

```bash
git add data reports src/evidence_chain/cli.py tests
git commit -m "feat: run first evidence-chain pilot"
```

## Self-review checklist

- Public-only collection and no-bypass constraints are represented in Tasks 3, 4, and 8.
- Article-first text, subtitle fallback, and ASR boundary are represented in Task 4.
- Fact chain, reasoning chain, verification chain, source grades, and alternative explanations are represented in Tasks 5–7.
- Stable raw snapshots, hashes, and audit records are represented in Tasks 2–4.
- The plan contains no unresolved `TBD`, `TODO`, or “implement later” instructions.
- The plan assumes no existing repository conventions because the workspace is currently empty.
