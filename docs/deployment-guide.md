# 部署指南

## 前置要求

1. **华为云账号**: 已开通 ModelArts Studio 服务
2. **Python**: 3.9+ (推荐 3.11+)
3. **Terraform**: 1.5+ (仅基础设施部署需要)

## 快速开始

### 方式一：本地 Streamlit 前端

```bash
# 1. 克隆仓库
git clone https://github.com/huaweicloud-samples/huawei-prompt-chaining
cd huawei-prompt-chaining/src

# 2. 安装依赖
pip install -r frontend/requirements.txt

# 3. 配置模型访问凭证
export MAAS_API_KEY="your-api-key"
export MAAS_MODEL="your-model-name"  # 例如 deepseek-v4

# 4. 启动前端
streamlit run frontend/app.py
# 浏览器打开 http://localhost:8501
```

### 方式二：离线演示 (无需 API Key)

```bash
cd src
python -m techniques.sequential          # 顺序链示例
python -m techniques.parallel           # 并行示例
python -m techniques.human_input        # 人工确认示例
# 所有 techniques 均可离线运行
```

### 方式三：函数计算部署

```bash
# 1. 进入 infra 目录
cd infra

# 2. 复制配置
cp tfvars.example tfvars.dev

# 3. 编辑 tfvars.dev，填入:
# - region: "cn-north-4"
# - project_name: "prompt-chaining"
# - maas_api_key: "your-key"
# - maas_model: "your-model"

# 4. 初始化并验证
terraform init
terraform validate

# 5. 计划与部署
terraform plan -var-file=tfvars.dev
terraform apply -var-file=tfvars.dev
```

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `MAAS_API_KEY` | 是 | ModelArts Studio API Key |
| `MAAS_MODEL` | 是 | 模型名称，如 `deepseek-v4` |
| `MAAS_CHAT_BASE_URL` | 否 | 对话端点，默认 `https://api.modelarts-maas.com/v2` |
| `MAAS_EMBED_BASE_URL` | 否 | 向量端点，默认 `https://api.modelarts-maas.com/v1` |
| `GITHUB_TOKEN` | 否 | GitHub API Token（可选，用于提高速率限制） |

## 验证

### 本地前端验证

启动后，在页面输入测试参数：

| Demo | 测试参数 |
|------|----------|
| Blog Post | `novel: Pride and Prejudice by Jane Austen` |
| Story Writer | `story_description: The wild west` |
| Trip Planner | `location: Paris, France` |
| Movie Pitch | `movie_description: Cowboys in space` |
| Meal Planner | `ingredients: Chicken, Rice` |
| Most Popular Repo | (无需参数) |

### 人工确认流程验证

1. 进入 **Movie Pitch** 页面
2. 输入 `movie_description: a chef who can taste memories`
3. 点击运行 → 页面显示「需要人工确认」
4. 选择 **yes** → 扩写为一页纸 pitch
5. 选择 **no** → 进入新一轮重新生成

## 费用说明

| 资源 | 说明 | 参考价格 |
|------|------|----------|
| ModelArts 推理 | 按 token 结算 | DeepSeek V4 |
| FunctionGraph (可选) | 按调用量结算 | 基础额度内 |
| VPC/EIP (可选) | 公网访问 | 按带宽时长结算 |

> **注意**: 部署前请阅读仓库内部过程文档了解完整限制。

## 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 运行时提示缺少 API Key | 未设置 MAAS_API_KEY | 检查环境变量是否正确导出 |
| 模型调用超时 | 网络问题或端点错误 | 检查 MAAS_CHAT_BASE_URL |
| 人工确认后流程卡住 | 续跑时 payload 丢失 | 确保使用最新版本 frontend/_ui.py |
| 并行分支结果异常 | 闭包捕获问题 | 检查 lambda 默认参数写法 |

## 下一步

- 阅读 `docs/architecture.md` 了解架构细节
- 阅读仓库内部过程记录了解背景
- 阅读仓库内部过程文档了解限制条件
