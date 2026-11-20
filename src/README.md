# 源码布局与开发约定

本目录是可交付的提示词链（prompt chaining）样例源码，全部代码只依赖华为云服务能力
（模型推理走 ModelArts Studio 的 OpenAI 兼容端点，经由 `adapter` 适配层）。

## 目录结构

```
src/
├── adapter/
│   └── model_adapter.py        # 模型适配层：统一 chat / embed 入口（唯一允许直连模型的地方）
├── chaining/
│   ├── runtime.py              # 链运行时：历史累积、模型节点、并行/Map、回放与人工确认信号
│   ├── tools.py                # JSON 校验修复循环 / Map 合并 / 工具型 Agent 循环
│   └── testing.py              # ScriptedAdapter：离线规则式假模型（techniques/单测用，免网络）
├── functions/                  # 可独立部署的 Worker 函数（每个目录为一个函数）
│   ├── parse_json_response/    #   解析 + JSON Schema 校验
│   ├── merge_map_output/       #   Map 分支产物合并
│   ├── seek_user_input/        #   人工确认节点占位（记录问题与上下文）
│   ├── meal_choose_winner_agent/  # 评分仲裁（选最高分厨师）
│   ├── pdf_creator/            #   行程单 PDF 生成（本地渲染参考实现）
│   └── github_actions/         #   GitHub 只读工具（仓库搜索 / README 摘要）
├── demo/                       # 六个端到端演示应用（每个都是独立可运行的一条链）
│   ├── blog_post/
│   ├── story_writer/
│   ├── trip_planner/
│   ├── movie_pitch/
│   ├── meal_planner/
│   └── most_popular_repo/
├── techniques/                 # 九种链式编排技术示例（可独立运行，教学用）
└── frontend/                   # 本地交互前端（streamlit）
    ├── README.md               #   使用说明（启动 / 页面 / 续跑语义）
    ├── app.py                  #   首页：demo 一览
    ├── _ui.py                  #   页面状态机公共组件
    └── pages/                  #   六个 demo 页面（顺序执行入口）
```

## 模型适配层（adapter）

业务代码一律通过 `ChainRuntime`（内部持有 adapter）访问模型，禁止绕过运行时直连模型。

```python
from chaining.runtime import ChainRuntime
rt = ChainRuntime()                       # 读取环境变量 MAAS_API_KEY / MAAS_MODEL
out = rt.model_turn("你的提示词", step_id="unique.node")
print(out["response"])
```

环境变量由部署侧注入：`MAAS_API_KEY`（API Key）、`MAAS_MODEL`（模型名）、
`MAAS_CHAT_BASE_URL`（默认 `https://api.modelarts-maas.com/v2`）、`MAAS_EMBED_BASE_URL`
（默认 `https://api.modelarts-maas.com/v1`）。

## 链运行时语义（chaining/runtime）

`model_turn(prompt, *, step_id, conversation=None, include_conversation=True, ...)`

- 消息模型：`{"role": "user"|"assistant", "content": [{"type": "text", "text": ...}]}`。
- 历史累积：缺省时运行时内部维护 `history`（全链对话上下文），每轮后自动追加
  user 提问 + assistant 回答；下一个节点自动携带全部历史（可观测的「链条」效果）。
- `conversation=xxx` 显式传入时使用该历史且**不修改**运行时的全局历史（用于 Map 分支
  等互相独立的子链）。
- `include_conversation=False` 且不传 `conversation`：只发送本条 prompt（不携带历史）。
- 返回值含 `step_id / prompt / response / conversation / temperature / tool_calls /
  finish_reason`。
- `step_id` 在整条链内必须唯一：它同时是断点续跑的回放缓存键。

**断点续跑（人工确认）**：节点需要用户拍板时抛 `HumanInputRequired`：

```python
from chaining.runtime import HumanInputRequired, HumanInputItem
raise HumanInputRequired(
    [HumanInputItem("请选择一个方向", placeholder="A / B")],
    reply_keys=["choice"],
    transcript=rt.logs,                 # 已执行节点日志（原样回放）
    partial_state={"foo": "bar"},       # 业务中间态（随异常返回给调用方）
)
```

调用方把 `questions` 展示给用户，收集答复后带着 `transcript` + `replies` 重新执行：
运行时会原样回放 `transcript` 中的节点（不重复调用模型、不产生随机差异），
只从「人工答复之后」的节点开始真正调用模型。等同语义：一次显式的「继续执行」。

demo 流程函数统一签名：

```python
def run_flow(payload: dict, runtime: ChainRuntime) -> dict:
    """返回 {"final_answer": ..., "extra": ...}; 需人工输入时抛 HumanInputRequired"""
```

## demo 参考实现：blog_post（顺序链）

5 个代理顺序执行：摘要 → 情节 → 主题 → 文风 → 成文。前 4 个默认携带累积历史，
最后一个 `max_tokens=1000`。`payload = {"novel": "..."}`。

```python
from chaining.runtime import ChainRuntime

def run_flow(payload, rt):
    novel = payload["novel"]
    prompts = [
        ("blog.summary",   f"Write a 1-2 sentence summary for the book {novel}.", 250),
        ("blog.plot",      f"Write a paragraph describing the plot of the book {novel}.", 250),
        ("blog.themes",    f"Write a paragraph analyzing the key themes of the book {novel}.", 250),
        ("blog.style",     f"Write a paragraph discussing the writing style and tone of the book {novel}.", 250),
        ("blog.post",
         f'Combine your previous responses into a blog post titled "{novel} - A Literature Review" '
         "for my literature blog. Start the blog post with an introductory paragraph at the "
         "beginning and a conclusion paragraph at the end. The blog post should be five "
         "paragraphs in total.", 1000),
    ]
    outputs = []
    for step_id, prompt, max_tokens in prompts:
        outputs.append(rt.model_turn(prompt, step_id=step_id, max_tokens=max_tokens))
    return {"final_answer": outputs[-1]["response"], "title": f"{novel} - A Literature Review"}
```

其余 demo 覆盖：并行分支、条件、Map+合并、结构校验修复、人工确认、工具型 Agent。
每个 demo 的 `handler.py` 是部署到函数计算时的入口（还原 transcript → run_flow → 序列化）。

## 技术示例（techniques）

`src/techniques/*.py` 每个文件是一个可独立运行的示例，把某一种编排技术讲透，
内部实现使用同一套运行时 API。覆盖：模型调用、提示词模板、顺序链、并行、条件、
Map、结构校验、服务调用、人工确认。运行方式与每个示例的说明见
`src/techniques/README.md`。

关键设计：示例不强制联网。未配置 `MAAS_API_KEY` 时，`techniques/_util.py` 会注入
`chaining/testing.py` 提供的 `ScriptedAdapter`（离线规则式假模型），让链条以确定的
模型调用次数跑通（用于教学与 CI）；配置了真实凭据时则走真实验证。两种模式都通过
`adapter.calls` 统计每次模型调用。

## 本地交互前端（frontend）

`streamlit run frontend/app.py` 启动后，左侧导航进入六个 demo 页面。页面共用
`frontend/_ui.py` 的状态机（入参表单 → 运行 → 人工确认 → 结果/日志），页面文件
只声明入参与流程函数。带人工确认点的 movie_pitch 页面在「提交答复并继续」时会把
首次执行返回的 transcript/partial_state 原样带回续跑，仅对新增节点调用模型。

## 编码约束（务必遵守）

- 语言：注释/日志用中文或英文均可；对外输出的提示词（发给模型的 prompt）用英文。
- 兼容性：目标运行时为 Python 3.9+（函数计算运行时）。避免使用 3.10+ 独有语法
  （`match`、`X | Y` 类型标注）；导入 `from __future__ import annotations` 可选。
- 职责边界：只有 `adapter/model_adapter.py` 允许 import openai / 构造模型请求；
  其余文件只允许通过运行时或 adapter 访问模型。
- 每个函数目录需包含 `requirements.txt`（如适用）与 README 说明；demo 与 techniques
  目录不含额外第三方依赖（`frontend/requirements.txt` 单独声明 streamlit）。
- 新增任何目录/模块前先保持 import 可解析（相对 src 根，包目录需 `__init__.py`）。

## 本地运行

```bash
cd src
export MAAS_API_KEY=... MAAS_MODEL=...            # 由部署侧提供；缺省时 techniques 走离线模式
python -m demo.blog_post.flow                      # 模块内含自测入口（需要真实凭据）
python -m techniques.sequential                    # 跑技术示例（无凭据时自动离线）
streamlit run frontend/app.py                      # 交互前端（pip install -r frontend/requirements.txt）
```
