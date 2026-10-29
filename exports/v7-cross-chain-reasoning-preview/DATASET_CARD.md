# V7 分层三链推理单样本预览

- 样本：`DEMO-VANKE-CROSS-CHAIN-001` / `CASE-VANKE` / `QA-V41-0309`
- 分层：QA、答案、推理、审计、训练投影
- 三链：事实传导、作者论证、现实验证
- 推理节点：24
- 已接受证据：6
- 证据缺口：2
- 训练消息：3（`PREVIEW_ONLY_EXCLUDED`）
- 校验状态：`PASS_PREVIEW`

本目录只用于确认 V7 字段和内容密度。它读取冻结的 V6 数据，不覆盖 V6，
不升级证据状态，也不解除 `NEEDS_HUMAN_REVIEW` 或 `formal_ready=false`。

`reasoning_preview.pretty.json` 适合人工查看；`reasoning_preview.jsonl` 展示未来
Master 文件的一行存储形式。当前作者材料没有视频时间戳和画面提取，因此来源
追踪保持 `PARTIAL`，相关缺口保存在校验报告中。
