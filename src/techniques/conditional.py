# -*- coding: utf-8 -*-
"""
技术示例 5/9 —— 条件分支（Conditional Chain）
=============================================
先让模型对输入做一次「分类/判断」（输出受控为 yes/no），再用普通 Python
if/else 决定走哪条子链。判断与分支都只是代码，行为一目了然、便于测试。

运行：
  python -m techniques.conditional
"""
from __future__ import annotations

from typing import Any, Dict

from techniques._util import ensure_src_path, make_runtime, model_calls

ensure_src_path()

from chaining.runtime import ChainRuntime  # noqa: E402

OFFLINE_RULES = [
    # 判断轮：只有判断提示词带这个标记；用 callable 按问题内容返回 yes / no
    ("Is this request a travel-related request",
     lambda text: "yes" if "travel to Paris" in text else "no"),
    # 分支子链
    ("one-day itinerary", "（占位）巴黎一日行程建议。"),
    ("in two sentences", "（占位）关于 Python 装饰器的两句话解释。"),
]


def run_flow(payload: Dict[str, Any], runtime: ChainRuntime) -> Dict[str, Any]:
    question = (payload.get("question") or "").strip()
    if not question:
        raise ValueError("缺少 question")

    # 1) 判断轮：输出被约束为 yes / no
    decision = runtime.model_turn(
        f"{question}\n\n"
        "Is this request a travel-related request? Reply with exactly 'yes' or 'no'.",
        step_id="cd.decide",
        max_tokens=5,
        temperature=0.0,
    )
    is_travel = decision["response"].strip().lower().startswith("yes")

    # 2) if/else 分支：代码可见、可单测
    if is_travel:
        out = runtime.model_turn(
            f"Build a one-day itinerary for the travel request: {question}",
            step_id="cd.travel",
            max_tokens=200,
        )
        branch = "travel"
    else:
        out = runtime.model_turn(
            f"Answer the following question in two sentences: {question}",
            step_id="cd.explain",
            max_tokens=150,
        )
        branch = "explain"

    return {"question": question, "branch": branch, "final_answer": out["response"]}


def main() -> None:
    runtime = make_runtime(OFFLINE_RULES)
    for question in ("Plan a 3-day trip to travel to Paris.", "How do I write a python decorator?"):
        runtime.reset()  # 每条链从干净历史开始（adapter 调用计数保留）
        result = run_flow({"question": question}, runtime)
        print(f"问题: {question}")
        print(f"  分支: {result['branch']} | 输出: {result['final_answer'][:70]}")
    print(f"两问共用同一运行时，模型调用次数: {model_calls(runtime)}（每次 = 判断 1 次 + 分支 1 次）")


if __name__ == "__main__":
    main()
