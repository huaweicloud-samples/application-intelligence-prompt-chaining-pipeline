# 华为云提示词链编排示例

[English](./README.md)

简体中文 | [中文版](./README.cn.md)

本项目提供基于华为云 ModelArts Studio (MaaS) 的提示词链（Prompt Chaining）编排示例，演示如何使用代码实现链式编排、人工确认与断点续跑。

## 1. 项目概述

提示词链（Prompt Chaining）是一种将复杂任务拆分为多个模型调用节点的技术，每个节点依赖前一个节点的输出，形成「链式」处理流程。本项目展示了 6 种典型的链式编排模式：

- **顺序链**: 多步骤顺序执行，每步累积上下文
- **并行扇出**: 多分支并行执行后汇合
- **Map 逐项**: 对列表逐项执行后合并
- **条件分支**: 根据模型判断选择不同路径
- **人工确认**: 等待用户拍板后继续执行
- **工具型 Agent**: 模型调用外部工具后作答

## 2. 架构

本项目采用「代码即编排」的架构，用 Python 控制流表达链式逻辑：

```
用户 → Streamlit 前端 → Chaining Runtime → ModelAdapter → MaaS (LLM)
```

- **Chaining Runtime**: 核心编排引擎，提供 `model_turn`、`parallel`、`map_items` 等方法
- **ModelAdapter**: 唯一直连 MaaS 的模块，封装 OpenAI 兼容 API
- **前端**: 本地 Streamlit 界面，可交互运行 6 个 demo

详见 [架构文档](./docs/architecture.md)

## 3. 快速开始

### 前置条件

- Python 3.9+
- 华为云账号（已开通 ModelArts Studio）

### 本地运行

```bash
# 1. 克隆仓库
git clone https://github.com/huaweicloud-samples/huawei-prompt-chaining
cd huawei-prompt-chaining/src

# 2. 安装依赖
pip install -r frontend/requirements.txt

# 3. 配置模型凭证
export MAAS_API_KEY="your-api-key"
export MAAS_MODEL="deepseek-v4"

# 4. 启动前端
streamlit run frontend/app.py
```

### 离线演示（无需 API Key）

```bash
cd src
python -m techniques.sequential     # 顺序链示例
python -m techniques.parallel       # 并行示例
python -m techniques.human_input    # 人工确认示例
```

## 4. Demo 流程

| Demo | 编排模式 | 输入参数 |
|------|----------|----------|
| Blog Post | 顺序链 | novel |
| Story Writer | JSON 校验 + Map | story_description |
| Trip Planner | 并行扇出 | location |
| Movie Pitch | 并行 + 人工确认 | movie_description |
| Meal Planner | 辩论循环 | ingredients |
| Most Popular Repo | 工具型 Agent | (无) |

每个 Demo 包含：

- `flow.py`: 业务流程代码
- `handler.py`: 函数入口（可选部署用）
- 独立测试入口 `if __name__ == "__main__":`

## 5. 技术示例

`src/techniques/` 目录下有 9 个最小可运行的示例：

1. **model_invocation** - 基础模型调用
2. **prompt_templating** - 提示词模板复用
3. **sequential** - 顺序链
4. **parallel** - 并行扇出
5. **conditional** - 条件分支
6. **map_chain** - Map 逐项
7. **validation** - 结构校验修复
8. **service_invocation** - 工具调用
9. **human_input** - 人工确认

每个示例均可离线运行：

```bash
python -m techniques.<示例名>
```

## 6. 核心 API

### ChainRuntime

```python
from chaining.runtime import ChainRuntime
rt = ChainRuntime()

# 单次模型调用
out = rt.model_turn("prompt", step_id="unique.step")

# 并行执行
results = rt.parallel([lambda: fn1(), lambda: fn2()])

# Map 逐项
items = ["a", "b", "c"]
results = rt.map_items(items, lambda x: process(x), concurrency=3)
```

### 人工确认

```python
from chaining.runtime import HumanInputRequired, HumanInputItem
raise HumanInputRequired(
    [HumanInputItem("是否继续？", placeholder="yes/no")],
    reply_keys=["confirm"],
    transcript=rt.logs,
    partial_state={"data": "..."},
)
```

## 7. 部署

### 本地运行

见「快速开始」章节。

### 函数计算（可选）

每个 Demo 的 `handler.py` 可打包为 FunctionGraph 函数：

```bash
cd infra
terraform init
terraform validate
terraform apply
```

详见 [部署指南](./docs/deployment-guide.md)

## 8. 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `MAAS_API_KEY` | 是 | ModelArts Studio API Key |
| `MAAS_MODEL` | 是 | 模型名称 |
| `MAAS_CHAT_BASE_URL` | 否 | 对话端点 |
| `GITHUB_TOKEN` | 否 | GitHub API Token |

## 9. 费用

| 资源 | 结算方式 |
|------|----------|
| ModelArts 对话 (DeepSeek V4) | 按 token 结算 |
| FunctionGraph | 提供每月基础调用额度 |
| APIG | 提供每月基础调用额度 |

响应约束详情见仓库内部过程文档。

## 10. 文档结构

```
.
├── docs/
│   ├── architecture.md       # 架构说明
│   └── deployment-guide.md  # 部署指南
│   ├── architecture-adaptation.md  # 架构适配说明
│   ├── migration-report.md       # 过程记录
│   └── response-constraints.md   # 响应约束
├── src/
│   ├── adapter/              # 模型适配层
│   ├── chaining/            # 链运行时
│   ├── demo/                # 6 个 demo 流程
│   ├── functions/           # 可选 Worker 函数
│   ├── techniques/          # 9 个教学示例
│   └── frontend/            # Streamlit 前端
├── README.md
├── README-en.md
└── LICENSE
```

## 11. 约束

本项目遵循以下设计约束（C1-C15）：

- 代码仅在华为云目录 (`huaweicloud/`)
- 文档采用华为云视角
- 部署费用信息仅保存在内部过程目录
- 访问凭据不落盘，使用占位符

详见仓库内部过程记录

## 12. 常见问题

**Q: 提示缺少 MAAS_API_KEY？**
A: 检查环境变量是否正确设置，`echo $MAAS_API_KEY` 确认。

**Q: 并行结果异常？**
A: 检查 lambda 是否使用默认参数捕获变量，参考 `parallel.py` 中的写法。

**Q: 人工确认后流程卡住？**
A: 确保 `_ui.py` 版本为最新，续跑需要携带 `transcript` 和 `partial_state`。

## 13. 验证

运行测试：

```bash
cd src
python -m techniques.test_techniques   # 离线回归测试
```

## 14. 贡献

欢迎提交 Issue 和 Pull Request。

## 15. 许可证

本项目基于 MIT No Attribution 许可证。
