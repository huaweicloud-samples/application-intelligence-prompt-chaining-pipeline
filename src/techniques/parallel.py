# -*- coding: utf-8 -*-
"""
技术示例 4/9 —— 并行分支（Parallel Chain）
==========================================
多个互不依赖的模型节点同时执行（扇出），全部完成后汇合（扇入）继续。

注意事项：
  * 并行分支彼此不得依赖对方的中间产物；需要共享的上下文应内联进各自的
    提示词，或提前放到公共历史里。
  * 列表推导里的 lambda 必须用「默认参数捕获」当前值
    （lambda a=a: fn(a)），否则所有分支会共享循环变量的最后值。

运行：
  python -m techniques.parallel
"""
from __future__ import annotations

from typing import Any, Dict, List

from techniques._util import ensure_src_path, make_runtime, model_calls

ensure_src_path()

from chaining.runtime import ChainRuntime  # noqa: E402

OFFLINE_RULES = [
    ("for developers", "（占位）写给开发者的标题：把云上复杂性藏起来。"),
    ("for decision makers", "（占位）写给决策者的标题：把收益与效率讲清楚。"),
    ("pick one headline", "（占位）合并后选定的最终标题。"),
]

# 扇出的两个受众
AUDIENCES = ("developers", "decision makers")


def _draft_headline(runtime: ChainRuntime, topic: str, audience: str) -> Dict[str, str]:
    prompt = f"Write a blog headline about {topic} for {audience}."
    out = runtime.model_turn(
        prompt,
        step_id=f"pl.draft.{audience}",
        conversation=[],  # 分支独立：互不携带对方历史
        max_tokens=80,
        temperature=0.9,
    )
    return {"audience": audience, "headline": out["response"]}


def run_flow(payload: Dict[str, Any], runtime: ChainRuntime) -> Dict[str, Any]:
    topic = (payload.get("topic") or "serverless").strip()

    # 扇出：默认参数捕获 audience，避免闭包共享循环变量
    branch_results = runtime.parallel(
        [lambda audience=a: _draft_headline(runtime, topic, audience) for a in AUDIENCES]
    )

    # 扇入：把各分支结果放进一个提示词，再做一次最终决策
    lines = "\n".join(f"- {item['headline']}" for item in branch_results)
    prompt = (
        "Here are two candidate headlines for the same blog post.\n"
        f"{lines}\n"
        "Pick one headline, or write a better one that combines the best of both. "
        "Reply with the single headline only."
    )
    out = runtime.model_turn(prompt, step_id="pl.choose", max_tokens=120)
    return {
        "topic": topic,
        "candidates": [item["headline"] for item in branch_results],
        "final_headline": out["response"],
    }


def main() -> None:
    runtime = make_runtime(OFFLINE_RULES)
    result = run_flow({"topic": "cloud-native applications"}, runtime)
    print("主题:", result["topic"])
    for idx, candidate in enumerate(result["candidates"], start=1):
        print(f"  候选 {idx}: {candidate}")
    print("最终标题:", result["final_headline"])
    print(f"模型调用次数: {model_calls(runtime)}（2 次并行 + 1 次汇合）")


if __name__ == "__main__":
    main()
