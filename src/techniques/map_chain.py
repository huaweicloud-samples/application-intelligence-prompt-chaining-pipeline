# -*- coding: utf-8 -*-
"""
技术示例 6/9 —— Map 与合并（Map Chain）
======================================
对一组同构输入逐项调用同一段子链（Map），再把各分支的对话增量合并
（merge_map_outputs），供后续节点一次性引用全部中间产物。

约定（与 merge_map_output Worker 一致）：
  * 每个分项产出的 conversation = 「公共历史 + 本分项专属两轮」；
  * 合并策略：取第一项公共历史，再把每项各自的最后两轮按顺序追加。

运行：
  python -m techniques.map_chain
"""
from __future__ import annotations

from typing import Any, Dict, List

from techniques._util import ensure_src_path, make_runtime, model_calls

ensure_src_path()

from chaining.runtime import ChainRuntime  # noqa: E402
from chaining.tools import merge_map_outputs  # noqa: E402

TOPICS = [
    "virtual private clouds",
    "event-driven architectures",
    "prompt engineering",
]

OFFLINE_RULES = [
    ("virtual private clouds", "（占位）VPC：把网络隔离封装成可复用的云上资源。"),
    ("event-driven architectures", "（占位）事件驱动：用事件解耦服务之间的直接调用。"),
    ("prompt engineering", "（占位）提示工程：把任务意图清晰传达给大模型的方法。"),
    ("Combine the previous points", "（占位）综合以上三点的一句话总结。"),
]


def _overview_item(runtime: ChainRuntime, topic: str) -> Dict[str, Any]:
    """对一个主题做一次独立概述（Map 的每一项）。"""
    out = runtime.model_turn(
        f"Write a one-sentence overview of {topic} for beginners.",
        step_id=f"mc.item.{topic.replace(' ', '_')}",
        conversation=[],
        max_tokens=80,
    )
    return {"topic": topic, "model_outputs": out}


def run_flow(payload: Dict[str, Any], runtime: ChainRuntime) -> Dict[str, Any]:
    topics: List[str] = payload.get("topics") or TOPICS

    # Map：逐项执行（concurrency>1 时并行，顺序保持与输入一致）
    item_results = runtime.map_items(
        topics, lambda topic: _overview_item(runtime, topic), concurrency=3
    )

    # 合并各分支的对话增量
    merged = merge_map_outputs(item_results)

    # 汇合节点：携带合并后的完整上下文做最终生成
    out = runtime.model_turn(
        "Combine the previous points into one two-sentence summary.",
        step_id="mc.summary",
        conversation=merged["conversation"],
        max_tokens=200,
    )
    return {
        "topics": topics,
        "merged_turns": len(merged["conversation"]),
        "final_answer": out["response"],
    }


def main() -> None:
    runtime = make_runtime(OFFLINE_RULES)
    result = run_flow({}, runtime)
    print("输入分项:", " / ".join(result["topics"]))
    print(f"合并后历史消息数: {result['merged_turns']}")
    print("汇总输出:", result["final_answer"])
    print(f"模型调用次数: {model_calls(runtime)}（3 次 Map + 1 次汇合）")


if __name__ == "__main__":
    main()
