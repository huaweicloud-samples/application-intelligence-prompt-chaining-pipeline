# merge_map_output —— Map 分支产物合并 Worker

独立部署形态的「Map 合并」函数，与链内工具 `chaining/tools.py` 的
`merge_map_outputs` 逻辑一致。

- 输入：`{map_results: [{model_outputs: {conversation: [...]}}]}`
- 输出：`{conversation: 合并后的完整历史}`
- 使用场景：StoryWriter 里每个角色的故事弧由 Map 并行生成后，汇总为一条
  供「全文生成」节点使用的对话历史。
