# 宏观2 · B 站财经视频 → 原子命题级证据链 → 可审计推理 SFT 数据集

> 把 B 站财经视频（UP 主"巫师财经"）的口播内容，抽成**以「原子命题」为单位的证据链**，再逐链组织成**可审计、可追溯、可拒答**的推理 SFT 数据集。
> 核心卖点是「**证据链 + 审计治理 + 拒答**」，而不是普通问答对生成。

一句口播要被拆成原子命题，并标注它是**事实 / 机制 / 作者推断 / 作者结论**；作者观点永远不能被当成世界事实；证据不足就**主动拒答**；原始数据不可改，任何修正都以「血缘纠正」叠加。所以它的价值不是"转写了多少视频"，而是"每条结论能不能被审计与复现"。

---

## 在线查看

| 入口 | 链接 |
|---|---|
| 仓库 | https://github.com/102722jl-hash/bilibili-finance-evidence-sft |
| 在线站点（GitHub Pages） | https://102722jl-hash.github.io/bilibili-finance-evidence-sft/ |
| 交互式 UI · 案例工作台 | https://102722jl-hash.github.io/bilibili-finance-evidence-sft/sft-case-ui-demo.html |
| 交互式 UI · 证据链查看器 | https://102722jl-hash.github.io/bilibili-finance-evidence-sft/sft-chain-visualizer.html |
| 项目完全剖析（HTML） | [宏观2_项目完全剖析.html](https://102722jl-hash.github.io/bilibili-finance-evidence-sft/%E5%AE%8F%E8%A7%822_%E9%A1%B9%E7%9B%AE%E5%AE%8C%E5%85%A8%E5%89%96%E6%9E%90.html) |

---

## 项目亮点

- **原子命题级证据图**：以 `Claim`（`frozen=True` 不可变 dataclass）+ `Edge` 构建图结构，节点分 **F/M/I/C/U** 五类（可核验事实 / 传导机制 / 作者推断 / 作者结论 / 传闻缺证），把"事实—机制—推断—结论"严格分层。
- **三链分层建模**：`fact_transmission`（事实传导，8 步）/ `author_reasoning`（作者推理，7 步）/ `world_verification`（现实验证，8 步），三泳道固定骨架并用 `chain_alignments` 做跨链对齐——**"作者叙事"与"现实证据"物理分离**。
- **可审计推理 + 主动拒答**：`terminal_kind` **四态**（answer / bounded_answer / boundary / abstain）；V6.1 实测 **answer 60 / boundary 58 / bounded_answer 33 / abstain 29**（合计 180）；拒答不是异常分支，而是被显式建模、可评测的一类期望行为。
- **9 项审核布尔门禁**：含 `author_claim_upgraded_to_world_fact`（防"把作者观点升格为世界事实"）与 `temporal_causal_confusion`（防"把先后发生误当因果"）——把**财经 AI 最常见的两类错误**代码化。
- **防泄漏与可复现门禁**：**14 文件输入冻结哈希（SHA-256 白名单）+ 导出后复校验** 双向锁；训练输入字段黑名单（`audit_context` / `mother_graph` / `terminal_kind`）；来源快照 **双哈希**（`snapshot_sha256` + `content_sha256`）。
- **数据血缘纠错**：发现 bug 不篡改原始数据，而是新增血缘纠正记录（`lineage_corrections=10`），原始数据保持 immutable。
- **规模量化**：**20 案例 / 180 master 记录 / 515 推理步 / 154 证据引用 / 645 gap 引用 / 17 来源**；**97 导出文件 / 52 源码模块 / 64 测试 / 766MB 归档**（含自建 faster-whisper 模型 463.7MB）。
- **诚实的数据姿态**：`gap_refs=645` 远多于 `accepted_evidence_refs=154`（约 4:1）——系统承认的缺口比它掌握的确定证据多得多，不掩盖缺证。

---

## 技术栈与运行环境

| 层 | 技术 |
|---|---|
| 后端 / 脚本 | Python 3.11/3.12+（stdlib + `dataclasses` + `json` + `hashlib`(SHA-256) + `argparse`），`scripts/` 16 个 `.py` |
| 抓取 / 解析 | `requests`、`beautifulsoup4`、`pypdf`、`python-docx` |
| 测试 | pytest（`tests/conftest.py` 注入 `SRC_DIR`，定义 `FIXTURES_DIR`） |
| 存储 | SQLite（`research.db` / `research_v2.db` / `db.sqlite`）+ JSONL + CSV |
| 前端 | 纯 HTML + 原生 JS（无框架），全局 `window.SFT_CASES_DATA` / `window.SFT_CHAIN_DATA` |
| UI 验收 | Playwright（`.mjs`）双视口（桌面 + 移动端） |
| 本地服务 | HTTP 端口 8765 |
| 图表 / 导出 | Mermaid；JSONL 为主，另导出合并 JSON |

---

## 架构总览：三链模型与三泳道

```
┌──────────────────────────── 一个案例（case）────────────────────────────┐
│  ① fact_transmission   事实传导链 （8 步；CASE-VANKE 例外 9 步）          │
│     —— "外部世界发生了什么、怎么传导"                                     │
├──────────────────────────────────────────────────────────────────────┤
│  ② author_reasoning    作者推理链 （7 步）                               │
│     —— "UP 主是怎么推断的（含其隐含假设）"                                │
├──────────────────────────────────────────────────────────────────────┤
│  ③ world_verification  现实验证链 （8 步）                               │
│     —— "用公开证据去验证作者的说法"                                       │
└──────────────────────────────────────────────────────────────────────┘
                    ↓ chain_alignments（跨链对齐）
   fact_to_author_premise / evidence_to_claim / gap_blocks_inference /
   author_to_bounded_world
```

前端以三条泳道并排展示，`laneStepCounts = [8, 7, 8]`（万科 `[9, 7, 8]`），与 `data/cases/v4.1/manifest.json` 完全一致，并由 Playwright 双视口断言各案例 `nodeCount`。

前端不是"演示壳"，而是**审计结果的可视化验证工具**——`verification.json` 用断言把"页面渲染出的节点数"与"数据集里的节点数"绑死，形成 UI 与数据的一致性门禁。

---

## 目录结构

```
宏观2/
├── exports/                          # 97 个导出文件（v6 三阶段 + v7 跨链）
│   ├── v6-first-round/               # schema auditable-sft/6.0-first-round
│   ├── v6-reasoning-complete/        # schema auditable-reasoning/6.1
│   ├── v6-second-round/{acquisition,release}/
│   ├── v7-cross-chain-reasoning/     # schema auditable-video-reasoning/7.1-layered
│   └── v7-cross-chain-reasoning-preview/
├── scripts/                          # 16 个 .py（采集 / 导出 / 校验 / 报告）
├── reports/v4.1-ui/                  # Playwright 双视口验收（desktop.png / mobile.png / verification.json）
├── docs/superpowers/{specs,plans}/   # 设计文档与计划
├── sft-case-ui-demo.html             # 案例 UI 演示
├── sft-chain-visualizer.html/js      # 三链泳道可视化
├── sft-cases-data.js (~7.6MB) / sft-case-grain-data.js / sft-cases-workbench.js
├── 宏观2_最终成果/00_总览/            # 项目展示 HTML + 文件清单 CSV
├── 宏观2_最终成果/02_归档_临时产物/    # worktree 临时产物归档
└── .worktrees/evidence-chain/        # 工作树工程：src 52 模块 / tests 64 / docs 12 / scripts 19
```

**规模统计**：exports 导出文件 **97**、scripts **16**、worktree 工程文件 **489**（src **52** / tests **64** / docs 12 / scripts 19）、归档素材 **766MB**（faster-whisper 模型 463.7MB + audio 299.1MB + bilibili 2.4MB）。

源码 52 个模块分布：`src/evidence_chain/` 根 10 + `cases/` 7 + `qa/` 24 + `sources/` 3 + `training/` 8。

---

## 领域模型与案例规模

### 节点类型（`node_type`）

| 类型 | 语义 |
|---|---|
| **F** | 可核验事实（Fact） |
| **M** | 传导机制（Mechanism） |
| **I** | 作者推断（Inference） |
| **C** | 作者结论（Conclusion） |
| **U** | 传闻 / 缺证 / 无法判定（Unverifiable） |

### 关系类型与边 origin

- **设计目标 8 种关系**：`precedes / causes / triggers / amplifies / enables / supports / contradicts / author_implies`；
  当前代码自动生成覆盖 **3 种**：`causes`（因此/所以/从而/进而）、`precedes`（随后/之后/此后）、`supports`（作者认为/作者指出/这说明/这意味着/这就是），其余 5 种依赖案例数据标注。
- **边 origin 4 值**：`explicit_author / implicit_author / externally_supported / narrative_only`。
- **来源强度**：实现层 `source_tier ∈ {AUTHOR, T1, T2, T4}`（AUTHOR = 作者口播，单列一档，不与 T1~T5 混用）；**核验状态 6 值**：`confirmed / partially_confirmed / unsupported / contradicted / disputed / unverifiable`。
- **跨链对齐类型**：`fact_to_author_premise / evidence_to_claim / gap_blocks_inference / author_to_bounded_world`。

### 关键规模数字

| 项目 | 数字 |
|---|---|
| 案例数 | 20（V4.1 十案例基线 + V5 扩展） |
| 每案例节点数 | 23（CASE-VANKE 24）；`evidence_records=8`、`alignments=6` |
| 每案例 QA 数 / 对话路径数 | 9 / 5 |
| 三泳道步数 | 8 / 7 / 8（VANKE 9 / 7 / 8） |
| V4.1 基线 seed | `20260813`（含 `v4_baseline_hashes`） |
| V6 首轮记录 | 180（train 144 / val 36）；answerability `{answerable:48, partially:112, unanswerable:20}` |
| V6.1 master | 180（train 99 / val 24）；`distinct_path_fingerprints=9`、`qa_records=9` 每案 |
| V6 二轮发布 | `{answer_sft:103, evidence_pending:57, abstention_sft:20}` |
| V7 样本 / 推理步 | 180 / 515（accepted_evidence_refs 154 / gap_refs 645） |

V4.1 首轮十案例主题：徐翔、万科争夺战、世纪白银操纵案、上市公司财务造假、雷军与小米、香港金融保卫战、保时捷与大众并购、赵薇资本博弈、娃哈哈治理、王一博。

---

## 可审计推理与拒答（abstention）机制

- **终态四值**（`terminal_kind`）：`answer`（直接回答）/ `bounded_answer`（有界回答）/ `boundary`（边界说明）/ `abstain`（拒答）。四态比"答/不答"细腻得多——`bounded_answer` 是"能答一部分并明确划出边界"，`boundary` 是"说明证据边界但不给结论"，把不确定性编码进输出契约。
- **拒答字段契约**：`causal_conclusion="ABSTAIN"`、`causal_attribution_allowed=false`、`identification_status="NOT_IDENTIFIED"`（见 `case_audit_contexts.jsonl` 的 `causal_assessments`）。
- **9 项审核布尔门禁**（`reasoning_review_log.jsonl` 的 `checks`）：

| 门禁 | 防的是什么 |
|---|---|
| `alternative_explanation_omitted` | 漏掉替代解释 |
| **`author_claim_upgraded_to_world_fact`** | **把作者观点升格为世界事实**（核心） |
| `citations_support_steps` | 引证是否真的支撑推理步 |
| `evidence_reviewed` | 证据是否已审 |
| `has_skipped_step` | 是否跳步 |
| `logic_reviewed` | 逻辑是否已审 |
| `reasoning_approved` | 推理是否已批准 |
| `structurally_complete` | 结构是否完整 |
| **`temporal_causal_confusion`** | **把"先后发生"误当"因果"** |

- **审计元数据与训练输入物理隔离**：`case_audit_contexts` 标 `training_visibility="metadata_only_excluded_from_messages"`，绝不进训练输入。
- **问答分类**：`question_role` 9 值（含独立的 `causal_refusal` 因果拒答）、`user_intent` 6 类（understand / explain / verify / impact / evaluate / compare）。
- **bounded_answer 样例**：记录 `author_world_divergence`（`divergence_type="evidence_scope_narrower_than_author_claim"`），显式记录"作者主张"与"现实证据"的偏离；`missing_step_refs=["CONCLUSION_SCOPE_LIMITED","SOURCE_EVIDENCE_INCOMPLETE"]`。

---

## V7 跨链推理：五层结构

`exports/v7-cross-chain-reasoning`（schema `auditable-video-reasoning/7.1-layered`，status `PASS_CANDIDATE_PREVIEW`）：

- samples **180** / cases **20** / reasoning_steps **515** / accepted_evidence_refs **154** / gap_refs **645** / lineage_corrections **10**；9 种 role 各 20。
- **每条记录拆为 5 层**：`qa / answer / reasoning / audit / training_projection`；训练投影标 `PREVIEW_ONLY_EXCLUDED`（全量为"候选预览"，非正式训练发布）。
- **warnings**：`SOURCE_CONTEXT_NOT_EMBEDDED / VIDEO_TIMESTAMP_NOT_AVAILABLE / VISUAL_EVIDENCE_NOT_EXTRACTED`。
- 预览目录 `v7-cross-chain-reasoning-preview`（`.../7.1-layered-preview`，status `PASS_PREVIEW`）：samples 1 / chains 3 / reasoning_steps 24。

---

## 防泄漏与可复现门禁（核心竞争力）

- **输入冻结哈希（双向锁）**：导出脚本维护 14 个文件的 SHA-256 白名单（`abstention_sft / accepted_evidence / answer_sft / case_audit_contexts / closed_from_pending / contexts / DATASET_CARD.md / evidence_links / evidence_pending / manifest.json / qa_records / search_audit / sources / validation_report`）；逐文件比对（缺失报 `missing frozen input`、不符报 `frozen input changed`），**导出后再复校验一次**（变更报 `V6 second-round source hashes changed`）——防止"读入 A 版本、写出 B 版本"的静默漂移。
- **防泄漏字段黑名单**：禁止 `"audit_context" / "mother_graph" / "terminal_kind"` 进入训练输入 messages。连 `terminal_kind`（终态）都要禁，因为它等价于"答案标签"——泄漏进输入模型就"看着答案做推理"。
- **快照双哈希门禁**：来源快照同时携带 `snapshot_sha256` 与 `content_sha256`，内容与快照双向锁定。
- **因果与引证门禁**：非 `IDENTIFIED` 却允许因果归因 → 报 `CAUSAL_GATE_CONTRADICTION`；answer 引证 `source_tier` 必须 ∈ `{T1, T2}`，否则报 `ANSWER_CITATION_TIER_INELIGIBLE`。
- **血缘纠正**：常量 `KNOWN_V5_CONTEXT_LEAK = "CTX-BIRTH-SUBSIDY-A1"` 记录 V5 跨案例上下文泄漏点；V7 将其归一化为 `mother_graph.fact_transmission.start_ref` 并产出纠正记录 `{correction_code:"V6_CROSS_CASE_CONTEXT_REPLACED", ...}`，原始数据不篡改。
- **基线冻结与确定性**：`frozen_baseline_hashes` / `v4_baseline_hashes` 锁基线；`split_strategy="event_cluster"`（同一事件簇样本不跨 train/val 边界）；固定 seed + master `sample_sha256` 指纹。

---

## 数据采集与来源治理

- **采集流水线**：`acquire_v5_evidence.py`、`acquire_v5_evidence_expansion.py`、`extract_v5_evidence_snapshots.py`；产物快照以 **SHA-256 作为文件名**（内容寻址存储，天然去重、防篡改），`snapshots/` 下成对的 `<sha256>.html / .pdf` 与 `.txt`。
- **来源治理状态机**：`source_audit` statuses ∈ `{CONTEXT_ONLY, REJECTED, ACCEPTED}`；准入须"可引用定位器 URL 完整 + 门禁通过"（`T1_SOURCE_QUOTE_LOCATOR_URL_COMPLETE` / `GATES_PASSED`）；不可复现（403/404）或非来源事实则降级或拒绝，**不伪造**。
- **披露与合规**：`sponsorship_disclosure{status, sponsor, source_ref, notes}` 明示是否含商业赞助；视频时间戳与画面（视觉证据）缺口一律保留为 gap，不补写。
- **合规立场**：不复现违法行为、不使用非公开信息、不绕过登录 / 验证码 / 付费墙 / 反爬。

---

## 已知局限与后续规划

**已知局限**

1. **视觉 / 时间戳缺失**：V7 三处 warning（`VIDEO_TIMESTAMP_NOT_AVAILABLE` / `VISUAL_EVIDENCE_NOT_EXTRACTED` / `SOURCE_CONTEXT_NOT_EMBEDDED`）。
2. **训练集是隔离而非清洗**：审计元数据通过"排除字段"避免进入训练输入，属工程隔离，非内容脱敏。
3. **关系类型实现不完整**：设计 8 关系，自动生成仅 `causes / precedes / supports`，其余依赖案例数据标注（U 类节点与部分关系类型的代码枚举未完全确证）。
4. **V7 仍为候选预览**：`PASS_CANDIDATE_PREVIEW`、`training_projection` 标 `PREVIEW_ONLY_EXCLUDED`，非正式训练发布。
5. **部分 QA 未闭环**：二轮发布 `evidence_pending=57`（约占 180 的 32%），且 `logic_reviewed=57` 尚未晋升 `reasoning_approved`。
6. 前端 `sft-cases-data.js`（≈7.6MB）为静态演示数据，未确认真实服务端。

**后续规划**：补齐视觉证据与视频时间戳；把 `evidence_pending` 的 57 条 QA 继续闭环；将 `logic_reviewed` 晋升为 `reasoning_approved`；扩展关系自动生成覆盖（从 3 种向 8 种逼近）；将 V7 从 `PASS_CANDIDATE_PREVIEW` 推进到正式训练发布。

---

## 许可与数据来源

本项目数据来源与合规披露见 `docs/` 及项目内说明文件（`DATASET_CARD.md`、`source_audit`、`sponsorship_disclosure` 等）。

> 本 README 由 [`宏观2_项目完全剖析.md`](./宏观2_项目完全剖析.md) 整理提炼；所有案例数、样本数、字段枚举、常量、哈希均以项目内文件实测为准。
