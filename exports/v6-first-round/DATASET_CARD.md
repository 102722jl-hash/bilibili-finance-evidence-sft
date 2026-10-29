# V6 第一轮可审计 SFT 候选集

本目录由 V4.1/V5 合并审计导出确定性派生，不覆盖原始数据。当前状态为 `NEEDS_HUMAN_REVIEW`，不是正式发布版。

## 训练入口

- `train.jsonl`：唯一训练入口，只读取每行的 `messages`。
- `validation.jsonl`：验证入口，不得加入训练。
- `audit_only.jsonl`：证据门禁未闭合，只用于补证和人工审核。
- `qa_records.jsonl`：180 条完整索引，不得默认整体训练。
- `case_audit_contexts.jsonl`：案例级完整母图，不进入模型消息。

## 第一轮调整

1. 训练输入不再包含可回答性目标。
2. Assistant 统一输出结构化 JSON；不可回答时 `direct_answer=ABSTAIN`。
3. 案例母图按案例去重，通过 `audit_context_id` 关联。
4. 现实证据题只有在 T1/T2、定位、正文哈希和快照哈希齐全时进入候选。

候选共 71 条：训练 55 条，验证 16 条；`audit_only` 109 条。
