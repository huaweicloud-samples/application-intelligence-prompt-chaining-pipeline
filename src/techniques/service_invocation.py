# -*- coding: utf-8 -*-
"""
技术示例 8/9 —— 服务 / 工具调用（Service Invocation）
====================================================
当模型需要外部信息（查数据、调接口）时，用「工具型 Agent 循环」：
模型自主决定调用哪个工具 -> 代码执行该工具（dispatcher）-> 把结果作为
role=tool 消息回填 -> 模型继续推理，直到给出最终答复。

本示例用「本地缓存仓库概览」充当外部服务，避免离线演示依赖公网；换成
真实服务时只需替换 dispatcher —— 例如调用 src/functions/github_actions
Worker（通过 APIG 暴露），或直接内嵌同一套函数。

运行：
  python -m techniques.service_invocation
"""
from __future__ import annotations

from typing import Any, Dict

from techniques._util import ensure_src_path, make_runtime, model_calls

ensure_src_path()

from adapter.model_adapter import tool_definition  # noqa: E402
from chaining.runtime import ChainRuntime  # noqa: E402
from chaining.tools import run_tool_agent  # noqa: E402

# 本地「外部服务」数据源（演示用；真实部署时替换为 HTTP 调用）
REPO_OVERVIEWS = {
    "https://github.com/huaweicloud/huaweicloud-sdk-python":
        "The official Python SDK for Huawei Cloud services, generated from the "
        "service definitions, providing typed clients for REST APIs.",
    "https://github.com/huaweicloud/ModelArts-examples":
        "Example notebooks and scripts for ModelArts, covering training, "
        "inference and MaaS scenarios.",
}

OVERVIEW_TOOL = tool_definition(
    "get_repository_overview",
    "Retrieves the README overview of a GitHub repository. Use this when you need "
    "to know what a repository is about. Provide the full repository URL as input.",
    {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "The full GitHub repository URL, e.g. https://github.com/owner/repo",
            }
        },
        "required": ["input"],
    },
)

# 离线规则：第一轮触发工具（value 为 dict 时按 input 传给工具）
OFFLINE_RULES = [
    ("https://github.com/huaweicloud/huaweicloud-sdk-python",
     {"input": "https://github.com/huaweicloud/huaweicloud-sdk-python"}),
    # 工具结果已出现后，返回最终答复
    ("official Python SDK", "（占位）根据工具结果得到的最终回答：它是一套官方 Python SDK。"),
]


def dispatcher(name: str, arguments: Dict[str, str]) -> str:
    """把模型请求的工具调用分发到实现（真实场景：转发到 Worker / HTTP 服务）。"""
    if name != "get_repository_overview":
        raise ValueError(f"未知工具: {name}")
    url = (arguments.get("input") or "").strip()
    overview = REPO_OVERVIEWS.get(url)
    if overview is None:
        return f"找不到仓库 {url} 的概览信息。"
    return f"README overview of {url}:\n{overview}"


def run_flow(payload: Dict[str, Any], runtime: ChainRuntime) -> Dict[str, Any]:
    repo_url = (payload.get("repo_url")
                or "https://github.com/huaweicloud/huaweicloud-sdk-python").strip()

    agent_out = run_tool_agent(
        runtime,
        user_input=(
            f"Look up the repository {repo_url} and summarize what it is about "
            "in one or two sentences."
        ),
        tools=[OVERVIEW_TOOL],
        dispatcher=dispatcher,
        step_id_prefix="sv.repo",
        system_prompt=(
            "You are a developer advocate. When asked about a repository, call the "
            "provided tool first, then answer based on its result."
        ),
        max_tokens=200,
        temperature=0.0,
    )
    return {"repo_url": repo_url, "final_answer": agent_out["response"], "steps": agent_out["steps"]}


def main() -> None:
    runtime = make_runtime(OFFLINE_RULES)
    result = run_flow({}, runtime)
    print("查询仓库:", result["repo_url"])
    for step in result["steps"]:
        print(f"  工具调用: {step['tool']}({step['arguments']})")
    print("最终回答:", result["final_answer"])
    print(f"模型调用次数: {model_calls(runtime)}（1 次决策调工具 + 1 次读取结果作答）")


if __name__ == "__main__":
    main()
