# parse_json_response —— JSON 解析 + Schema 校验 Worker

独立部署形态的「解析并校验」函数，与链内工具 `chaining/tools.py` 的
`parse_and_validate` / `validated_json_response` 校验逻辑一致。

| 部署形态 | 入口 | 说明 |
| --- | --- | --- |
| 独立 Worker | `index.handler` | 事件：`{response_text, json_schema?}`；返回 `{statusCode, parsed_output \| error}` |
| 链内嵌 | `chaining.tools.parse_and_validate` | 同进程直接调用，避免函数跳转开销 |

- 依赖：`jsonschema`（见 requirements.txt）
- 修复循环（解析/校验失败让模型修 JSON）属于编排层职责，Worker 只做校验。
