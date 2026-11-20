# Prompt Chaining on Huawei Cloud

[中文版](./README.cn.md)

[中文](./README.md) | English

This project provides prompt chaining examples on Huawei Cloud's ModelArts Studio (MaaS), demonstrating how to implement chain orchestration, human-in-the-loop, and resumable execution using Python code.

## 1. Overview

Prompt chaining splits complex tasks into multiple model call nodes, where each node depends on the previous one's output. This project demonstrates 6 typical chaining patterns:

- **Sequential Chain**: Multi-step sequential execution with context accumulation
- **Parallel Fan-out**: Multiple branches executing in parallel then merging
- **Map**: Process list items in parallel then merge results
- **Conditional**: Different paths based on model judgment
- **Human Input**: Pause for user confirmation before continuing
- **Tool-using Agent**: Model calls external tools then answers

## 2. Architecture

This project uses a "code-as-orchestration" approach:

```
User → Streamlit Frontend → Chaining Runtime → ModelAdapter → MaaS (LLM)
```

- **Chaining Runtime**: Core orchestration engine with `model_turn`, `parallel`, `map_items`
- **ModelAdapter**: The only module that directly connects to MaaS (OpenAI-compatible API)
- **Frontend**: Local Streamlit UI for interactive demo execution

See [Architecture](./docs/architecture.md) for details.

## 3. Quick Start

### Prerequisites

- Python 3.9+
- Huawei Cloud account (ModelArts Studio enabled)

### Local Run

```bash
# 1. Clone repository
git clone https://github.com/huaweicloud-samples/huawei-prompt-chaining
cd huawei-prompt-chaining/src

# 2. Install dependencies
pip install -r frontend/requirements.txt

# 3. Configure credentials
export MAAS_API_KEY="your-api-key"
export MAAS_MODEL="deepseek-v4"

# 4. Start frontend
streamlit run frontend/app.py
```

### Offline Demo (No API Key Required)

```bash
cd src
python -m techniques.sequential     # Sequential example
python -m techniques.parallel     # Parallel example
python -m techniques.human_input  # Human input example
```

## 4. Demo Flows

| Demo | Pattern | Input |
|------|---------|-------|
| Blog Post | Sequential | novel |
| Story Writer | JSON Validation + Map | story_description |
| Trip Planner | Parallel Fan-out | location |
| Movie Pitch | Parallel + Human Input | movie_description |
| Meal Planner | Debate Loop | ingredients |
| Most Popular Repo | Tool-using Agent | (none) |

Each demo includes:

- `flow.py`: Business logic
- `handler.py`: Function entry (optional deployment)
- Standalone test entry `if __name__ == "__main__":`

## 5. Techniques

`src/techniques/` contains 9 minimal runnable examples:

1. **model_invocation** - Basic model call
2. **prompt_templating** - Prompt template reuse
3. **sequential** - Sequential chain
4. **parallel** - Parallel fan-out
5. **conditional** - Conditional branching
6. **map_chain** - Map items
7. **validation** - JSON validation & repair
8. **service_invocation** - Tool invocation
9. **human_input** - Human confirmation

Run any example:

```bash
python -m techniques.<example_name>
```

## 6. Core API

### ChainRuntime

```python
from chaining.runtime import ChainRuntime
rt = ChainRuntime()

# Single model call
out = rt.model_turn("prompt", step_id="unique.step")

# Parallel execution
results = rt.parallel([lambda: fn1(), lambda: fn2()])

# Map items
items = ["a", "b", "c"]
results = rt.map_items(items, lambda x: process(x), concurrency=3)
```

### Human Input

```python
from chaining.runtime import HumanInputRequired, HumanInputItem
raise HumanInputRequired(
    [HumanInputItem("Continue?", placeholder="yes/no")],
    reply_keys=["confirm"],
    transcript=rt.logs,
    partial_state={"data": "..."},
)
```

## 7. Deployment

### Local Run

See "Quick Start" section.

### FunctionGraph (Optional)

Each demo's `handler.py` can be packaged as a FunctionGraph function:

```bash
cd infra
terraform init
terraform validate
terraform apply
```

See [Deployment Guide](./docs/deployment-guide.md) for details.

## 8. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MAAS_API_KEY` | Yes | ModelArts Studio API Key |
| `MAAS_MODEL` | Yes | Model name |
| `MAAS_CHAT_BASE_URL` | No | Chat endpoint |
| `GITHUB_TOKEN` | No | GitHub API Token |

## 9. Charges

| Resource | Settlement |
|----------|------------|
| ModelArts Chat (DeepSeek V4) | Settled per token |
| FunctionGraph | Monthly base quota included |
| APIG | Monthly base quota included |

See the internal process docs for limits.

## 10. Directory Structure

```
.
├── docs/
│   ├── architecture.md       # Architecture
│   └── deployment-guide.md  # Deployment Guide
│   ├── architecture-adaptation.md  # Architecture Adaptation
│   ├── migration-report.md       # Migration Report
│   └── response-constraints.md   # Constraints
├── src/
│   ├── adapter/              # Model Adapter
│   ├── chaining/            # Chaining Runtime
│   ├── demo/                # 6 Demo Flows
│   ├── functions/           # Optional Worker Functions
│   ├── techniques/          # 9 Teaching Examples
│   └── frontend/            # Streamlit Frontend
├── README.md
├── README-en.md
└── LICENSE
```

## 11. Constraints

This project follows design constraints (C1-C15):

- Code only in `huaweicloud/` directory
- Documentation uses Huawei Cloud perspective
- Charge details kept in internal process docs
- Access credentials not committed; use placeholders

See internal process records for details.

## 12. FAQ

**Q: "MAAS_API_KEY not found"?**
A: Check environment variable is set correctly: `echo $MAAS_API_KEY`.

**Q: Parallel results incorrect?**
A: Check lambda uses default parameter capture, see `parallel.py`.

**Q: Flow stuck after human confirmation?**
A: Ensure `_ui.py` is latest version; resume requires `transcript` and `partial_state`.

## 13. Verification

Run tests:

```bash
cd src
python -m techniques.test_techniques   # Offline regression tests
```

## 14. Contributing

Issues and Pull Requests are welcome.

## 15. License

MIT No Attribution.
