# 证据推理 SFT 数据集 V3

本目录是可直接用于监督微调的三消息 `messages` JSONL，而不是原始研究材料。

## 文件与规模

- `train_messages.jsonl`：2 条训练样本。
- `validation_messages.jsonl`：0 条独立案例验证样本，不得混入训练。
- 每条助手输出监督直接答案、可回答性、事实传导链、作者推理链、外部核验链、引用和不确定性边界。
- 每个链步骤显式保存 `premises`、`inference`、`conclusion`、`evidence` 和 `reasoning_text`；其中命题和证据均包含实际文本，不需要再通过 `NODE-*` ID 回查。

## 使用边界

- `author_trace` 只学习忠实复原作者观点，不代表现实因果成立。
- `world_evidence` 只学习外部材料实际支持的范围。
- `unsupported` 和 `not_reviewed` 步骤不得在训练或推理时改写为已确认事实。
- 数据不包含模型隐藏或自由式思维过程，只包含来源可追溯、关系明确的公开命题推理链。
- 当前 90 条样本适合验证 SFT 管线和小规模领域适配，不足以单独训练具备广泛泛化能力的基础模型。
