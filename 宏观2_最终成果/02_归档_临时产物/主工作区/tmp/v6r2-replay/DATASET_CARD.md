# V6 第二轮可审计 SFT 数据集

本轮把 V5 已取得的一手材料登记为 `source -> context -> evidence-link -> hash` 完整链，并逐题重投影第一轮待补证样本。

- `answer_sft`: 103 条，可用于回答训练，其中部分样本保留有边界的 `partially_answerable`。
- `abstention_sft`: 20 条，因果识别门禁未通过，必须输出 `ABSTAIN`。
- `evidence_pending`: 57 条，仍缺少可复核原文或命题级闭环。
- 原 89 条待补证样本中闭合 32 条，剩余 57 条。

重要边界：乐华招股书未披露匿名艺人身份；CFTC材料不替代法院交易序列；小米年报不含首日收盘价；保时捷单品牌数据不代表整个汽车市场；无直接反证不标记 contradicted。所有记录仍为 `NEEDS_HUMAN_REVIEW`，不得自动视为正式发布。
