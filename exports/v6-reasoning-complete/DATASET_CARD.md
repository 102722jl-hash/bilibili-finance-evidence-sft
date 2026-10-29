# V6.1 全量问题级推理链数据集

## 概况

- 数据版本：`6.1.0-reasoning-complete`
- Master：180 条，20 个案例，每案 9 种问题入口
- 合法终点：answer 60；bounded_answer 33；boundary 58；abstain 29
- 审核状态：reasoning_approved 123；logic_reviewed/review pending 57
- 训练消息：train 99；validation 24

## 结构

`reasoning_master_180.jsonl` 保存问题级命题路径、三链节点定位、证据引用和边界；案例完整母图仅保存在 `case_audit_contexts.jsonl`，不进入训练消息。每一步是可审计的命题、关系和证据记录，不是模型自由式思维过程。

## 证据边界

仅 V6 第二轮中已通过 T1/T2、正文定位、受控快照和双哈希门禁的 34 条证据可作为事实引用。搜索摘要只保留在检索审计中。没有直接反证时不标记 contradicted；未通过因果识别门禁时输出 `ABSTAIN`。

57 条原 evidence pending 已补成完整的 boundary 或 abstain 路径，但仍保持 review pending，不进入训练消息。徐翔与原野实业的关键现实命题在缺少法院、证监会或交易所一手原文时继续拒答或限定回答。

## 发布状态

`formal_ready=false`，`review_status=NEEDS_HUMAN_REVIEW`。本版本是候选研究资产，不能视为法律、投资或事实裁判结论。
