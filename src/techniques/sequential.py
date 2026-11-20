# -*- coding: utf-8 -*-
"""
技术示例 3/9 —— 顺序链（Sequential Chain）
==========================================
最简单的链式结构：多个模型节点按顺序执行，后一个节点「看到」前一个节点的
输出。实现上，运行时会自动把历史（用户提问 + 助手回答）累积进对话上下文，
因此每个节点只需关注「自己这一步要产出什么」。

典型场景：一本书的多角度拆解——摘要 → 主题 → 文风 → 汇总成一篇书评，
每一步都站在上一步的结果之上。

运行：
  python -m techniques.sequential
"""
from __future__ import annotations

from typing import Any, Dict, List

from techniques._util import ensure_src_path, make_runtime, model_calls

ensure_src_path()

from chaining.runtime import ChainRuntime  # noqa: E402

OFFLINE_RULES = [
    ("short summary of the book", "（占位）本书的摘要。"),
    ("key themes", "（占位）本书的主题分析。"),
    ("writing style", "（占位）本书的文风分析。"),
    ("final book review", "（占位）综合上述分析形成的最终书评。"),
]


def run_flow(payload: Dict[str, Any], runtime: ChainRuntime) -> Dict[str, Any]:
    book = (payload.get("book") or "The Pragmatic Programmer").strip()

    # 每一步都默认携带累积历史；返回值里包含每步产物
    steps: List[Dict[str, str]] = []

    out = runtime.model_turn(
        f"Write a short summary of the book {book}.", step_id="sq.summary", max_tokens=200
    )
    steps.append({"step": "summary", "text": out["response"]})

    out = runtime.model_turn(
        f"List the key themes of the book {book}.", step_id="sq.themes", max_tokens=200
    )
    steps.append({"step": "themes", "text": out["response"]})

    out = runtime.model_turn(
        f"Describe the writing style of the book {book}.", step_id="sq.style", max_tokens=200
    )
    steps.append({"step": "style", "text": out["response"]})

    out = runtime.model_turn(
        f"Combine your previous responses into a final book review of {book}.",
        step_id="sq.review",
        max_tokens=400,
    )
    steps.append({"step": "review", "text": out["response"]})

    return {"book": book, "steps": steps, "final_answer": steps[-1]["text"]}


def main() -> None:
    runtime = make_runtime(OFFLINE_RULES)
    result = run_flow({"book": "The Pragmatic Programmer"}, runtime)
    print("书名:", result["book"])
    for step in result["steps"]:
        print(f"[{step['step']}] {step['text'][:80]}")
    print(f"模型调用次数: {model_calls(runtime)}（四个节点顺序执行）")


if __name__ == "__main__":
    main()
