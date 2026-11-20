# 链式编排技术示例（techniques）

本目录把提示词链（Prompt Chaining）的九种常用编排技术拆成最小可运行的示例。
每个文件只演示一种技术，可直接阅读源码理解「用代码编排一条链」的写法，
也可直接运行观察输出与模型调用次数。

## 运行方式

```bash
cd src
python -m techniques.<示例模块名>        # 例如 python -m techniques.sequential
```

**离线/在线双模式**（由 `techniques/_util.py` 统一处理）：

- 未配置 `MAAS_API_KEY`：自动注入 `chaining/testing.ScriptedAdapter`（离线规则式
  假模型），不访问网络即可确定性跑通，模型调用次数固定 —— 适合教学与 CI；
- 已配置 `MAAS_API_KEY` / `MAAS_MODEL`：走真实 MaaS 端点做真实验证。

每次示例结束都会打印本次运行的模型调用次数与各节点产物摘要，便于对照。

## 示例清单

| 模块 | 技术 | 链条形态 | 模型调用次数（离线） |
|---|---|---|---|
| `model_invocation` | 模型调用 | 单节点：一次 `model_turn` | 1 |
| `prompt_templating` | 提示词模板 | 同一模板渲染两次，各走一个独立节点 | 2 |
| `sequential` | 顺序链 | 四步顺序执行，历史逐级累积 | 4 |
| `parallel` | 并行扇出 | 两个受众标题草稿并行，汇合后选一 | 3 |
| `conditional` | 条件分支 | 先让模型判断意图，再走 travel / explain 分支 | 4 |
| `map_chain` | Map / 逐项 | 三个主题逐项生成（并发 3），合并后汇总 | 4 |
| `validation` | 结构校验修复 | 草稿 JSON 校验失败 → 模型修复（循环） | 2 |
| `service_invocation` | 服务调用（工具型 Agent） | 模型声明工具 → 执行器回填 → 再作答 | 2 |
| `human_input` | 人工确认点 | 草稿 → 询问人工 → 携带答复续跑 | 首次 1 + 续跑 1 |

说明：

- 「模型调用次数」以离线模式的 `ScriptedAdapter.calls` 为准，真实模型下节点数量一致，
  但工具/校验失败的修复轮次数取决于模型输出质量。
- `human_input` 展示 `HumanInputRequired` 门控与回放续跑语义：续跑只对「人工答复之后」
  的新增节点调用模型，之前节点从回放缓存恢复，不重复调用。
- 目录内 `_util.py` 与 `__init__.py` 为公共设施（路径注入、离线/在线运行时工厂、
  调用计数），不是示例本身。

## 约定

- 每个示例文件的模块 docstring 描述该技术、链条结构与离线规则匹配要点。
- 代码只依赖 Python 标准库与 `src/` 内模块，无第三方依赖（校验示例使用 jsonschema
  仅在离线校验演示路径中按需 import）。
- 离线规则的匹配基准是「最后一条消息文本」（而非全量历史拼接），按最长匹配子串
  优先，因此同一示例可重复运行且输出稳定。
