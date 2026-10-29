# V7 分层三链推理全量候选

- Master：180 条，20 个案例，每案 9 个 QA 入口
- 推理节点：515
- 已接受证据引用：154
- 证据缺口引用：645
- QA 角色：{'alternative_explanation': 20, 'author_assumption': 20, 'bounded_impact': 20, 'causal_refusal': 20, 'cross_chain_synthesis': 20, 'evidence_boundary': 20, 'evidence_confirmation': 20, 'mechanism': 20, 'origin': 20}
- 校验状态：`PASS_CANDIDATE_PREVIEW`

每条记录均拆为 `qa`、`answer`、`reasoning`、`audit` 和 `training_projection` 五层。
训练投影全部标记为 `PREVIEW_ONLY_EXCLUDED`，本目录不是正式训练发布。
视频时间戳和画面缺口不会被补写，仍保留为 gap code。
