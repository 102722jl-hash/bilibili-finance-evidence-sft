(function () {
  "use strict";

  const rootAsset = window.SFT_CASES_DATA;
  if (!rootAsset || !rootAsset.datasets?.merged || !rootAsset.datasets?.v41 || !rootAsset.datasets?.v5) {
    throw new Error("未找到 V4.1/V5 双版本数据资产。");
  }
  let datasetKey = rootAsset.default_dataset || "merged";
  let dataset = rootAsset.datasets[datasetKey];

  const labels = {
    chain: {
      fact_transmission: ["事实传导链", "事件起点 → 作用机制 → 后续事件 → 最终结果", "fact"],
      author_reasoning: ["作者推理链", "作者前提 → 中间判断 → 隐含假设 → 作者结论", "author"],
      world_verification: ["外部核验链", "外部证据 → 支持范围 → 证据缺口 → 现实结论", "world"],
    },
    kind: {
      fact: "事实", mechanism: "作用机制", judgment: "中间判断",
      assumption: "隐含假设", conclusion: "结论", evidence: "外部证据",
      evidence_boundary: "证据边界",
      observed_event: "观察事件", policy_condition: "制度条件", market_mechanism: "市场机制",
      industry_effect: "产业影响", turning_point: "关键转折", policy_response: "政策响应",
      premise: "作者前提", verified_fact: "核验事实", verified_mechanism: "核验机制",
      verified_boundary: "核验边界", evidence_gap: "证据缺口", world_conclusion: "现实结论",
      condition: "必要条件", effect: "结果", event: "事件", feedback: "反馈",
      boundary: "边界", gap: "缺口", alternative: "替代解释", causal_boundary: "因果边界",
      source_inventory: "来源清单", source_gate: "来源门禁", coverage_boundary: "覆盖边界",
      assumption_gap: "假设缺口", causal_gap: "因果缺口",
    },
    status: {
      confirmed: "已确认", partially_supported: "部分支持", unsupported: "证据不足",
      not_reviewed: "未核验", explicit: "作者明示", implicit: "隐含前提",
      not_applicable: "不适用", answerable: "可回答",
      partially_answerable: "部分可回答", unanswerable: "不可回答",
    },
    intent: {
      understand: "理解事件", explain: "解释机制", verify: "核验事实",
      impact: "分析影响", evaluate: "评价充分性", compare: "比较解释",
    },
    scope: { author_trace: "作者论证", world_evidence: "现实证据" },
    split: { train: "训练集", validation: "验证集" },
    entry: {
      first_contact: "首次了解", reason_followup: "原因追问",
      verification_doubt: "真实性质疑", comparison: "比较与替代解释",
      impact_followup: "影响追问", evaluation: "评价追问",
    },
    coverage: {
      origin: "事件起点", mechanism: "作用机制", turning_point: "关键转折",
      outcome: "最终结果", impact: "现实影响", verification: "外部核验",
    },
    relation: {
      observes: "观察到", leads_to: "传导至", produces: "产生后续",
      concludes: "得出结论", states: "陈述前提", interprets: "解释为",
      assumes: "依赖假设", supports: "证据支持", bounds: "限定范围",
      limits: "指出缺口", followed_by: "随后发生",
      compares_author_conclusion: "比较作者结论", tests_against_evidence_boundary: "检验证据边界",
      bounds_world_conclusion: "限定现实结论",
      supports_descriptive_co_movement: "支持描述性共变", supports_policy_mechanism: "支持政策机制",
      blocks_timeline_claim: "阻断时序命题", blocks_coordination_claim: "阻断协同归因",
      blocks_causal_claim: "阻断因果归因", requires_alternatives: "要求检验替代解释",
      blocks_exposure_estimate: "阻断暴露估计", blocks_default_link: "阻断违约传导",
      blocks_loss_estimate: "阻断损失估计", blocks_systemic_feedback: "阻断系统反馈",
      supports_governance_mechanism: "支持治理机制", supports_event_sequence: "支持事件序列",
      bounds_specific_rumor: "限定到具体传闻", blocks_motive_inference: "阻断动机推断",
      blocks_causal_attribution: "阻断因果归因",
    },
    source: {
      full_article: "完整图文稿", full_asr: "完整语音转写", sampled_asr: "抽样语音转写",
      author_video: "作者视频", author_article: "作者文章", external_primary: "外部一手来源",
      official_author_article: "作者官方图文稿",
      official_document: "官方文件", official_statistics: "官方统计", news_report: "新闻报道",
    },
  };
  const displayTitles = {
    "CASE-KOREA": "韩国工薪经济与结构压力",
    "CASE-VANKE": "万科控制权争夺",
    "CASE-WAHAHA": "娃哈哈继承纠纷",
  };
  const displayTitle = pack => displayTitles[pack.case_id] || pack.title;
  const sourceDatasetKey = row => row.source_dataset || (datasetKey === "v5" ? "v5" : "v41");
  const sourceVersionLabel = row => sourceDatasetKey(row) === "v5" ? "V5" : "V4.1";

  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
  const text = (group, value) => labels[group]?.[value] || value || "未标注";
  const index = (rows, key) => Object.fromEntries((rows || []).map(row => [row[key], row]));
  const payload = record => {
    try {
      return JSON.parse(record.messages.find(message => message.role === "assistant")?.content || "{}");
    } catch (_) {
      return {};
    }
  };
  const selectedAnswer = () => payload(current.sft_records[selectedRecord] || current.sft_records[0]);
  const selectedLocalRefs = () => new Set((selectedAnswer().local_reasoning_path || []).map(step => step.output_ref));
  const statusClass = value => value === "confirmed" ? "confirmed"
    : value === "partially_supported" ? "partial"
      : value === "unsupported" ? "unsupported" : "";
  const timeRange = pack => {
    const start = pack.time_scope?.start || "未标注";
    const end = pack.time_scope?.end;
    return end && end !== start ? `${start} 至 ${end}` : start;
  };
  const enumText = value => {
    for (const group of ["status", "intent", "scope", "split", "entry", "coverage", "relation", "kind", "source"]) {
      if (labels[group]?.[value]) return labels[group][value];
    }
    return value;
  };
  const localizedObject = value => Array.isArray(value)
    ? value.map(localizedObject)
    : value && typeof value === "object"
      ? Object.fromEntries(Object.entries(value).map(([key, item]) => [key, localizedObject(item)]))
      : typeof value === "string" ? enumText(value) : value;
  const localizedPrompt = value => String(value || "")
    .replaceAll("author_trace", "作者论证")
    .replaceAll("world_evidence", "现实证据")
    .replaceAll("not_reviewed", "未核验")
    .replaceAll("partially_supported", "部分支持")
    .replaceAll("unsupported", "证据不足")
    .replaceAll("contradicted", "存在直接反证");

  let current = dataset.cases.find(row => row.case_pack.case_id === "CASE-GRAIN") || dataset.cases[0];
  let selectedNodeId = "";
  let selectedPath = 0;
  let selectedRecord = 0;

  function currentMaps() {
    return {
      nodes: index(current.case_pack.nodes, "node_id"),
      contexts: index(current.contexts, "context_id"),
      sources: index(current.sources, "source_id"),
      links: index(current.evidence_links, "link_id"),
      evidence: index(current.deep_audit?.evidence_records, "evidence_id"),
      qa: index(current.qa_items, "qa_id"),
      gold: index(current.qa_gold, "qa_id"),
      records: index(current.sft_records.map(row => ({ ...row, qa_id: row.metadata.qa_id })), "qa_id"),
    };
  }

  function renderCaseList(query = "") {
    const rows = dataset.cases;
    const listTitle = datasetKey === "merged"
      ? "合并版 · 20 个案例"
      : datasetKey === "v5" ? "V5 · 10 个内容案例" : "V4.1 · 10 个事件案例";
    document.querySelector("aside.cases").innerHTML = `
      <div class="side-title">${listTitle}</div>
      <input class="case-search" id="caseSearch" placeholder="搜索案例" value="${esc(query)}">
      <div id="caseList">${rows.map(row => {
        const pack = row.case_pack;
        const split = row.sft_records[0]?.metadata?.source_split;
        const haystack = `${pack.case_id} ${pack.title} ${displayTitle(pack)} ${pack.event_cluster_id} ${(pack.entities || []).join(" ")}`.toLowerCase();
        return `<button class="case-item ${pack.case_id === current.case_pack.case_id ? "active" : ""}" data-case-id="${esc(pack.case_id)}" data-search="${esc(haystack)}">
          <div class="case-id">${esc(pack.case_id)}</div>
          <div class="case-name">${esc(displayTitle(pack))}</div>
          <div class="case-meta">${datasetKey === "merged" ? `${sourceVersionLabel(row)} · ` : ""}${row.qa_items.length} 个问题 · ${row.dialogue_paths.length} 条路径 · ${text("split", split)}</div>
        </button>`;
      }).join("")}</div>`;
    document.getElementById("caseSearch").addEventListener("input", event => {
      const needle = event.target.value.trim().toLowerCase();
      document.querySelectorAll("[data-case-id]").forEach(button => {
        button.hidden = Boolean(needle) && !button.dataset.search.includes(needle);
      });
    });
    document.querySelectorAll("[data-case-id]").forEach(button => button.addEventListener("click", () => selectCase(button.dataset.caseId)));
  }

  function renderHeader() {
    const pack = current.case_pack;
    const sourceKey = sourceDatasetKey(current);
    const sourceMap = index(current.sources, "source_id");
    const authorContexts = current.contexts.filter(row => sourceMap[row.source_id]?.source_tier === "AUTHOR" || row.source_id.startsWith("SRC-AUTHOR"));
    const externalContexts = current.contexts.length - authorContexts.length;
    document.querySelector(".crumb").textContent = `案例中心 / ${displayTitle(pack)}`;
    document.querySelector(".case-head").innerHTML = `<div>
      <div class="eyebrow">${esc(pack.case_id)} · ${esc(pack.event_cluster_id.toUpperCase())}${pack.parent_event_cluster_id ? ` · 上级簇 ${esc(pack.parent_event_cluster_id.toUpperCase())}` : ""}</div>
      <h1>${esc(displayTitle(pack))}</h1>
      <p class="desc">${sourceKey === "v5" ? `原始视频：${esc((pack.video_ids || []).join("、"))} · ` : `时间范围：${esc(timeRange(pack))} · `}作者材料 ${authorContexts.length} 段 · 外部/审计材料 ${externalContexts} 段 · ${pack.nodes.length} 个命题节点</p>
    </div><div class="badges">
      <span class="badge ${pack.formal_ready === false ? "warn" : "ok"}">${pack.review_status === "approved" ? "已审核" : pack.review_status === "sample_reviewed" ? "深化样本已审" : pack.review_status === "NEEDS_HUMAN_REVIEW" ? "待人工审核" : esc(pack.review_status)}</span>
      <span class="badge">${sourceKey === "v5" ? "V5 内容迁移" : "V4.1 深化图"}</span>
      <span class="badge">${current.qa_items.length} 个问题</span>
      <span class="badge">${current.dialogue_paths.length} 条对话路径</span>
      <span class="badge warn">存在证据边界</span>
    </div>`;
  }

  function chainNodes(chain) {
    const maps = currentMaps();
    return chain.steps.map(step => ({ step, node: maps.nodes[step.output_ref] }));
  }

  function renderChains() {
    const narrative = current.macro_narrative;
    const localRefs = selectedLocalRefs();
    document.querySelector("#chains .claim").innerHTML = `<small>作者中心主张</small>${esc(narrative.central_claim)}`;
    document.getElementById("lanes").innerHTML = current.case_pack.chains.map(chain => {
      const [name, summary, css] = labels.chain[chain.chain_type];
      return `<section class="lane ${css}"><div class="lane-head">
        <div class="lane-name"><span class="lane-dot"></span>${name}</div>
        <div class="lane-summary">${summary}</div>
      </div><div class="flow">${chainNodes(chain).map(({ step, node }) => `<button class="node ${node.node_id === selectedNodeId ? "selected" : ""} ${localRefs.size && !localRefs.has(node.node_id) ? "omitted" : ""} ${localRefs.has(node.node_id) ? "local" : ""}" data-node-id="${esc(node.node_id)}">
        <div class="node-step">STEP ${step.step_no}<span>${text("kind", step.step_kind)}</span></div>
        <div class="node-text">${esc(node.text)}</div>
        <span class="node-status ${statusClass(step.support_status.world_validity)}">${text("status", step.support_status.world_validity)}</span>
      </button>`).join("")}</div></section>`;
    }).join("");
    document.querySelectorAll("[data-node-id]").forEach(button => button.addEventListener("click", () => {
      selectedNodeId = button.dataset.nodeId;
      renderChains();
      renderInspector();
    }));
  }

  function findStep(nodeId) {
    for (const chain of current.case_pack.chains) {
      const step = chain.steps.find(row => row.output_ref === nodeId);
      if (step) return { chain, step };
    }
    return null;
  }

  function refText(refId) {
    const maps = currentMaps();
    return maps.nodes[refId]?.text || maps.contexts[refId]?.text || maps.links[refId]?.notes
      || maps.evidence[refId]?.original_quote || maps.evidence[refId]?.gap_description || refId;
  }

  function renderInspector() {
    const maps = currentMaps();
    const node = maps.nodes[selectedNodeId] || current.case_pack.nodes[0];
    selectedNodeId = node.node_id;
    const found = findStep(node.node_id);
    const step = found.step;
    const evidence = [...new Set([
      ...(node.context_ids || []),
      ...(step.evidence_refs || []),
      ...step.input_refs.filter(ref => ref.startsWith("CTX-") || ref.startsWith("EL-") || ref.startsWith("EV-")),
    ])];
    document.getElementById("inspector").innerHTML = `<div class="ref">${esc(node.node_id)}</div>
      <div class="inspect-title">${esc(node.text)}</div>
      <div class="status-grid">
        <div class="status-box"><span>作者忠实度</span><strong>${text("status", step.support_status.author_fidelity)}</strong></div>
        <div class="status-box"><span>现实有效性</span><strong>${text("status", step.support_status.world_validity)}</strong></div>
      </div>
      <div class="section"><div class="section-label">输入前提</div><div class="section-text">${step.input_refs.map(ref => `<div><span class="ref">${esc(ref)}</span>${esc(refText(ref))}</div>`).join("")}</div></div>
      <div class="section"><div class="section-label">推断关系</div><div class="section-text"><strong>${text("relation", step.relation)}</strong> <span style="color:var(--muted)">（${esc(step.relation)}）</span><br>${esc(step.explanation)}</div></div>
      <div class="section"><div class="section-label">输出命题</div><div class="section-text">${esc(node.text)}</div></div>
      <div class="section"><div class="section-label">关联证据</div><div class="section-text">${evidence.length ? evidence.map(ref => `<div><span class="ref">${esc(ref)}</span>${esc(refText(ref))}</div>`).join("") : "该步骤没有绑定直接证据；请结合前序步骤及支持状态阅读。"}</div></div>`;
  }

  function renderDialogue() {
    const maps = currentMaps();
    const paths = current.dialogue_paths;
    const path = paths[selectedPath] || paths[0];
    document.getElementById("pathSelect").innerHTML = paths.map((row, indexValue) => `<option value="${indexValue}" ${indexValue === selectedPath ? "selected" : ""}>${esc(row.dialogue_id)} · ${row.turn_count} 轮 · ${text("entry", row.entry_kind)}</option>`).join("");
    document.getElementById("pathCount").textContent = `共 ${paths.length} 条正式路径`;
    const coverageOrder = ["origin", "mechanism", "turning_point", "outcome", "impact", "verification"];
    document.getElementById("dialogueContent").innerHTML = `<div class="coverage">${coverageOrder.map(tag => `<div class="cover ${path.cumulative_coverage_tags.includes(tag) ? "done" : ""}">${text("coverage", tag)}</div>`).join("")}</div>
      <div class="path-summary"><span class="badge ok">链条${path.chain_completeness === "complete" ? "完整" : "不完整"}</span><span class="badge">${path.turn_count} 轮</span><span class="badge">入口：${text("entry", path.entry_kind)}</span></div>
      <div class="dialogue">${path.qa_ids.map((qaId, turn) => {
        const item = maps.qa[qaId];
        const gold = maps.gold[qaId];
        const answer = payload(maps.records[qaId]);
        return `<div class="turn-card"><div class="turn-no ${turn < path.qa_ids.length - 1 ? "done" : "current"}">${turn + 1}</div>
          <div class="turn-main"><div class="turn-q">${esc(item.conversational_question)}</div>
          <div class="turn-tags">${esc(qaId)} · 独立问题：${esc(item.standalone_question)}</div>
          <div class="turn-answer">${esc(answer.direct_answer || gold.answer.direct_answer)}</div>
          <div class="turn-audit"><span class="audit-chip">意图：${text("intent", item.user_intent)}</span><span class="audit-chip">范围：${text("scope", item.truth_scope)}</span><span class="audit-chip">目标：${esc(gold.target_ref_ids.join("、"))}</span></div></div>
          <div class="intent">${text("intent", item.user_intent)}</div></div>`;
      }).join("")}</div>`;
    document.getElementById("pathSelect").onchange = event => {
      selectedPath = Number(event.target.value);
      renderDialogue();
    };
  }

  function renderSources() {
    const sourceKey = sourceDatasetKey(current);
    const contextsBySource = {};
    current.contexts.forEach(row => (contextsBySource[row.source_id] ||= []).push(row));
    const deepEvidence = current.deep_audit?.evidence_records || [];
    const accepted = deepEvidence.filter(row => row.acceptance_status === "ACCEPTED");
    const gaps = deepEvidence.filter(row => row.acceptance_status === "GAP");
    const deepCards = current.deep_audit ? `<div class="claim"><small>${sourceKey === "v5" ? "V5" : "V4.1"} 命题级证据图</small>${accepted.length} 条已接受 T1/T2 证据 · ${gaps.length} 条明确缺口 · ${current.deep_audit.chain_alignments.length} 条跨链对齐。搜索摘要不作为证据。</div>
      ${deepEvidence.map(row => `<article class="source-card"><div class="source-card-head"><div class="source-card-title">${esc(row.evidence_id)} · ${row.acceptance_status === "ACCEPTED" ? "已接受证据" : row.acceptance_status === "GAP" ? "证据缺口" : "背景材料"}</div><div class="source-card-meta">目标：${esc(row.target_ref)} · ${esc(row.source_tier)} · ${esc(row.stance)} · ${esc(row.coverage)}</div>${row.source_url ? `<a class="source-url" href="${esc(row.source_url)}" target="_blank" rel="noreferrer">${esc(row.source_url)}</a>` : ""}</div><div class="context-card"><div class="context-id">SHA-256 ${esc(row.content_sha256 || row.snapshot_sha256 || "无可接受快照")}</div><div class="context-text">${esc(row.original_quote || row.gap_description)}</div><div class="source-card-meta">定位：${esc(row.locator || "未定位")}${row.required_evidence ? `<br>仍需：${esc(row.required_evidence)}` : ""}</div></div></article>`).join("")}` : "";
    document.getElementById("sourcesContent").innerHTML = `${deepCards}<div class="claim"><small>正式来源与证据覆盖</small>${current.sources.length} 个来源 · ${current.contexts.length} 个公开片段 · ${current.evidence_links.length} 条${sourceKey === "v5" ? " V5" : " V4.1"}证据链接。保留来源、定位、哈希与内部审计 ID。</div>
      ${current.sources.map(source => `<article class="source-card"><div class="source-card-head">
        <div class="source-card-title">${esc(source.publisher)} · ${text("source", source.source_kind)}</div>
        <div class="source-card-meta">${esc(source.source_id)} · ${esc(source.source_tier || "未分级")} · ${source.temporal_role === "author_material" ? "作者材料" : "事后核验"} · ${source.is_full_text ? "全文来源" : "短摘录来源"} · ${source.authorship_confirmed ? "归属已确认" : "归属未确认"}</div>
        <a class="source-url" href="${esc(source.url)}" target="_blank" rel="noreferrer">${esc(source.url)}</a>
      </div>${(contextsBySource[source.source_id] || []).map(context => `<div class="context-card"><div class="context-id">${esc(context.context_id)} · SHA-256 ${esc(context.content_sha256)}</div><div class="context-text">${esc(context.text)}</div><div class="source-card-meta">定位：${esc(JSON.stringify(context.locator))}<br>限制：${esc((context.limitations || []).join("；") || "无")}</div></div>`).join("") || `<div class="context-card"><div class="context-text">该来源没有发布上下文片段。</div></div>`}
      ${current.evidence_links.filter(link => link.source_id === source.source_id).map(link => `<div class="link-row"><strong>${esc(link.link_id)}</strong><span>${esc(link.notes)}<br>目标：${esc(link.target_ref)}</span><span class="node-status ${link.coverage === "full" ? "confirmed" : link.coverage === "partial" ? "partial" : "unsupported"}">${link.coverage === "full" ? "完整覆盖" : link.coverage === "partial" ? "部分覆盖" : "无直接覆盖"}</span></div>`).join("")}</article>`).join("")}`;
  }

  function renderTraining() {
    const sourceKey = sourceDatasetKey(current);
    const maps = currentMaps();
    const records = current.sft_records;
    const record = records[selectedRecord] || records[0];
    const qaId = record.metadata.qa_id;
    const item = maps.qa[qaId];
    const answer = payload(record);
    const metrics = dataset.metrics || {};
    const reduction = metrics.v3_average_assistant_characters
      ? Math.round((1 - metrics.average_assistant_characters / metrics.v3_average_assistant_characters) * 100)
      : 0;
    document.getElementById("qaList").innerHTML = `<div class="dataset-stats"><div class="stat"><strong>${records.length}</strong><span>案例 SFT 样本</span></div><div class="stat"><strong>${new Set(records.map(row => row.metadata.user_intent)).size}</strong><span>用户意图</span></div><div class="stat"><strong>${metrics.local_path_signatures || 0}</strong><span>全局局部路径</span></div><div class="stat"><strong>${reduction}%</strong><span>较 V3 输出缩减</span></div></div>${records.map((row, i) => `<button class="qa-button ${i === selectedRecord ? "active" : ""}" data-record-index="${i}"><div class="qa-button-id">${esc(row.metadata.qa_id)} · ${text("intent", row.metadata.user_intent)} · ${text("status", row.metadata.answerability)}</div><div class="qa-button-q">${esc(maps.qa[row.metadata.qa_id].standalone_question)}</div></button>`).join("")}`;
    const localSteps = answer.local_reasoning_path || [];
    const motherSteps = current.case_pack.chains.reduce((sum, chain) => sum + chain.steps.length, 0);
    const conclusionText = step => typeof step.conclusion === "string" ? step.conclusion : step.conclusion?.text || step.explanation;
    const causal = current.deep_audit?.causal_assessments?.[0];
    const auditDetail = current.deep_audit
      ? `${Object.entries(current.deep_audit.completeness.dimensions).map(([key, value]) => `${key}：${value.status}`).join("；")}<br>因果识别：${causal.identification_status} / ${causal.causal_conclusion}`
      : "完整三链保存在 V4 audit_context，只用于人工审计。";
    const chainCards = `<div class="supervision-card world"><h4>本题局部监督路径 · ${localSteps.length} 步</h4>${localSteps.map(step => `<div class="supervision-step"><strong>${step.step_no}. ${text("relation", step.relation)}</strong> <span class="ref">${esc(step.parent_chain_id)} / STEP ${step.parent_step_no}</span><br>${esc(conclusionText(step))}<br><span class="node-status ${statusClass(step.support_status?.world_validity)}">${text("status", step.support_status?.world_validity)}</span></div>`).join("")}</div><div class="supervision-card"><h4>案例完整母图 · ${motherSteps} 步</h4><div class="supervision-step">${auditDetail}</div><div class="supervision-step">母图不进入训练消息；当前题只监督 ${localSteps.length} 个必要步骤。</div></div><div class="supervision-card author"><h4>证据边界</h4><div class="supervision-step">${esc(answer.verification || "")}</div><div class="supervision-step">${esc(answer.missing_evidence?.join("；") || "当前题无需额外缺失证据说明")}</div></div>`;
    document.getElementById("qaDetail").innerHTML = `<div class="qa-head"><div class="qa-head-id">${esc(qaId)} · ${text("split", record.metadata.source_split)} · ${text("scope", record.metadata.truth_scope)} · ${text("intent", record.metadata.user_intent)}</div><div class="qa-head-q">${esc(item.standalone_question)}</div></div>
      <div class="qa-body"><div class="answer-block"><strong>标准直接答案</strong><br>${esc(answer.direct_answer)}</div>
      <div class="kv"><div class="kv-key">回答状态</div><div><span class="badge ok">${text("status", answer.answerability)}</span> <span class="badge">局部链：${localSteps.length} 步</span> <span class="badge">角色：${esc(record.metadata.question_role)}</span></div></div>
      <div class="kv"><div class="kv-key">证据边界</div><div>${esc(answer.uncertainty_note)}</div></div>
      <h3 style="font-size:12px;margin:15px 0 7px">${sourceKey === "v5" ? "V5" : "V4.1"} 监督目标：问题级局部链</h3><div class="supervision-grid">${chainCards}</div>
      <div class="section"><div class="section-label">模型实际输入（枚举已中文化展示）</div><div class="codebox">${esc(localizedPrompt(record.messages.filter(message => message.role !== "assistant").map(message => `[${message.role === "system" ? "系统规则" : "用户材料"}]\n${message.content}`).join("\n\n")))}</div></div>
      <details class="fold"><summary>展开完整标准输出 JSON（枚举已中文化展示）</summary><div class="fold-body"><div class="codebox">${esc(JSON.stringify(localizedObject(answer), null, 2))}</div></div></details></div>`;
    document.querySelectorAll("[data-record-index]").forEach(button => button.addEventListener("click", () => {
      selectedRecord = Number(button.dataset.recordIndex);
      renderTraining();
      renderChains();
    }));
  }

  function selectCase(caseId) {
    current = dataset.cases.find(row => row.case_pack.case_id === caseId) || current;
    selectedNodeId = current.case_pack.chains[0].steps[0].output_ref;
    selectedPath = 0;
    selectedRecord = 0;
    renderAll();
  }

  function renderAll() {
    document.querySelectorAll("[data-dataset-key]").forEach(button => button.classList.toggle("active", button.dataset.datasetKey === datasetKey));
    renderCaseList();
    renderHeader();
    renderChains();
    renderInspector();
    renderDialogue();
    renderSources();
    renderTraining();
  }

  document.querySelectorAll(".tab").forEach(button => button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(item => item.classList.remove("active"));
    document.querySelectorAll(".view").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    document.getElementById(button.dataset.view).classList.add("active");
  }));

  document.querySelectorAll("[data-dataset-key]").forEach(button => button.addEventListener("click", () => {
    const nextKey = button.dataset.datasetKey;
    if (!rootAsset.datasets[nextKey] || nextKey === datasetKey) return;
    datasetKey = nextKey;
    dataset = rootAsset.datasets[datasetKey];
    current = dataset.cases[0];
    selectedNodeId = current.case_pack.chains[0].steps[0].output_ref;
    selectedPath = 0;
    selectedRecord = 0;
    renderAll();
  }));

  selectedNodeId = current.case_pack.chains[0].steps[0].output_ref;
  renderAll();
})();
