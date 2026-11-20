# -*- coding: utf-8 -*-
"""
技术示例 1/9 —— 模型调用（Model Invocation）
============================================
最基础的编排单元：向模型发起一次对话补全，拿到文本产物并继续。
链式编排里的每个「节点」本质上都是这样一次调用，区别只在于：

  * step_id：节点唯一标识（断点续跑/回放缓存的键，链内必须唯一）
  * prompt：发给模型的指令（英文，避免中文指令影响开源模型输出）
  * max_tokens / temperature / top_p：控制输出的长度与随机性

运行：
  python -m techniques.model_invocation
  # 或（已设置 MAAS_API_KEY 时走真实模型）
  python techniques/model_invocation.py
"""
from __future__ import annotations

from typing import Any, Dict

from techniques._util import ensure_src_path, make_runtime, model_calls

ensure_src_path()

from chaining.runtime import ChainRuntime  # noqa: E402

# 离线占位回复：按「匹配子串」命中，子串越长优先级越高
OFFLINE_RULES = [
    ("one-sentence introduction", "「模型调用」示例：这是一句关于所选主题的占位简介。"),
]


def run_flow(payload: Dict[str, Any], runtime: ChainRuntime) -> Dict[str, Any]:
    topic = (payload.get("topic") or "serverless prompt chaining").strip()

    out = runtime.model_turn(
        f"Write a one-sentence introduction about {topic} for a developer blog.",
        step_id="mi.intro",
        max_tokens=120,
        temperature=0.7,
    )
    return {
        "topic": topic,
        "response": out["response"],
        "step_id": out["step_id"],
        "temperature": out["temperature"],
        "finish_reason": out["finish_reason"],
    }


def main() -> None:
    runtime = make_runtime(OFFLINE_RULES)
    result = run_flow({"topic": "prompt chaining orchestration"}, runtime)
    print("主题   :", result["topic"])
    print("节点   :", result["step_id"], "| 采样温度:", result["temperature"])
    print("模型输出:", result["response"])
    print(f"模型调用次数: {model_calls(runtime)}（一次链 = 一次调用）")


if __name__ == "__main__":
    main()
