"""
热门仓库推荐（ReAct 工具型 Agent 示例）
========================================
两个 Agent 接力完成「查 GitHub → 读 README → 写简介」，语义相当于把两条
工具链合并在一个工具型 Agent 案例中：

  1. lookup agent：模型自主调用 get_trending_github_repositories 工具拿到
     GitHub Trending 仓库列表，回答「今天最热门的仓库 URL」（温度 0，
     只输出 URL；提取失败最多重试 3 次）；
  2. summarize agent：模型自主调用 get_github_repository_readme 工具读取该
     仓库 README，输出 100–200 词的简介。

说明：
  * GitHub 工具实现见同目录 github_tools.py（纯标准库，无需第三方依赖）；
  * GITHUB_TOKEN 环境变量可选（不设置也能读公开仓库）。
  * 工具型 Agent 的「选工具、看结果、再回答」循环由模型驱动，
    外部副作用（真实 HTTP 请求）在断点续跑时按缓存原样回放，不重复请求。

payload:
  { }  （可空；无需业务入参）
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from adapter.model_adapter import tool_definition
from chaining.runtime import ChainRuntime
from chaining.tools import run_tool_agent
from demo.most_popular_repo.github_tools import (
    EXAMPLE_OWNER_REPO,
    REPO_URL_RE,
    tool_dispatcher,
)

LOOKUP_QUESTION = (
    "What is the top trending repository on GitHub today? "
    "Provide only the URL of the top GitHub repository as your answer."
)
LOOKUP_QUESTION_RETRY = (
    "What is the URL of the top trending repository? "
    "Provide only the URL of the top GitHub repository as your answer."
)
SUMMARIZE_QUESTION = (
    "Briefly describe the popular open source project {repo} in 100 - 200 words."
)

TRENDING_TOOL = tool_definition(
    "get_trending_github_repositories",
    "Retrieves the GitHub Trending Repositories webpage. Use this when you need to "
    "get information about which repositories are currently trending on GitHub. "
    "Provide an empty string as the input. The output will be the text response of "
    "a GET request to the Trending Repositories page.",
    {
        "type": "object",
        "properties": {"input": {"type": "string", "description": "Empty string (not used)"}},
        "required": ["input"],
    },
)

README_TOOL = tool_definition(
    "get_github_repository_readme",
    "Retrieves the content of a GitHub repository's README file. Use this when you "
    "need to get information about a specific GitHub repository. Provide the URL of "
    "the GitHub repository as the input. The output will be the contents of the "
    "readme.",
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


def run_flow(
    payload: Dict[str, Any],
    runtime: ChainRuntime,
    replies: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    repo_url = _lookup_trending_repo(runtime)
    summary = _summarize_repo(runtime, repo_url)

    owner_repo = repo_url.replace("https://github.com/", "").rstrip("/")
    return {
        "final_answer": summary,
        "repo": repo_url,
        "repo_owner_repo": owner_repo,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# 内部步骤
# ---------------------------------------------------------------------------


def _lookup_trending_repo(runtime: ChainRuntime) -> str:
    """Agent #1：找到当天最热门的 GitHub 仓库 URL（最多重试 3 次）。"""
    last_response = ""
    for attempt in range(1, 4):
        question = LOOKUP_QUESTION if attempt == 1 else LOOKUP_QUESTION_RETRY
        agent_out = run_tool_agent(
            runtime,
            user_input=question,
            tools=[TRENDING_TOOL],
            dispatcher=tool_dispatcher,
            step_id_prefix=f"repo.lookup.attempt{attempt}",
            system_prompt=(
                "You are a GitHub power user. You help with interacting with GitHub "
                "and with git repositories. When asked for the top trending "
                "repository, call the provided tool, then answer with only the URL of "
                "the top repository."
            ),
            max_tokens=256,
            temperature=0.0,
            max_iterations=6,
        )
        last_response = agent_out["response"]

        match = REPO_URL_RE.search(last_response)
        if match and EXAMPLE_OWNER_REPO not in match.group(1):
            return match.group(0)
        # 模型没有给出可用 URL：下一轮强调只输出 URL
        continue

    raise RuntimeError(
        "Could not find a GitHub repository URL from the agent responses. "
        f"Last response: {last_response!r}"
    )


def _summarize_repo(runtime: ChainRuntime, repo_url: str) -> str:
    """Agent #2：读取仓库 README 并给出 100–200 词简介。"""
    agent_out = run_tool_agent(
        runtime,
        user_input=SUMMARIZE_QUESTION.format(repo=repo_url),
        tools=[README_TOOL],
        dispatcher=tool_dispatcher,
        step_id_prefix="repo.summarize",
        system_prompt=(
            "You are a GitHub power user. You help with interacting with GitHub and "
            "with git repositories."
        ),
        max_tokens=500,
        temperature=0.0,
        max_iterations=6,
    )
    return agent_out["response"].strip()


if __name__ == "__main__":
    from demo._runner import run_flow_session

    session = run_flow_session(run_flow, {})
    if session["status"] == "ok":
        result = session["result"]
        print("仓库:", result["repo"])
        print("摘要:\n", result["final_answer"])
    else:
        print("执行失败:", session.get("message"))
