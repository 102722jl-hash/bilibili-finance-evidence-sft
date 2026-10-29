# QA 推理链评测集 V1

本数据集是从公开材料的原子命题、作者关系边和外部核验证据派生的中文开放材料评测集。

## 真值边界

- `author_trace` 只评估模型是否忠实还原作者的表述和推导，不表示现实因果成立。
- `world_evidence` 只采用经过记录的外部证据覆盖范围；缺少证据时必须拒答。
- 无外部证据不等于主张错误，数据集不会据此生成 `contradicted` 标签。

## 规模

- QA：8
- 上下文片段：9
- `author_fact`：1
- `author_relation`：1
- `author_multihop`：1
- `author_conclusion_support`：1
- `world_confirmed`：1
- `world_partial`：1
- `world_unanswerable`：1
- `world_source_scope`：1

## 发布与许可边界

只发布研究所需的短引文、定位信息、公开 URL 和内容哈希；不重新分发完整稿件、音视频、受限页面或搜索摘要。
原始材料的权利归各发布者所有。若来源失效、权利人提出合理请求或发现不当收录，应在后续版本移除并更新 manifest。

## 复核与局限

V1 使用确定性规则生成，并由 Codex 进行结构化复核；正式论文发布前建议增加独立人工复核与争议仲裁。
本构建未包含 sampled-ASR 片段。
不提供隐藏测试服务器；公开 test 结果可能随模型训练数据污染而失效。
