# -*- coding: utf-8 -*-
"""
技术示例 7/9 —— 结构校验与修复（Structured Output Validation）
=============================================================
当后续代码要消费模型的 JSON 输出时，先做「解析 + JSON Schema 校验」，
校验失败就让模型自己修复后重试（最多 MAX_FIX_ATTEMPTS 次），保证下游拿到
的一定是符合契约的结构。

运行：
  python -m techniques.validation
"""
from __future__ import annotations

from typing import Any, Dict

from techniques._util import ensure_src_path, make_runtime, model_calls

ensure_src_path()

from chaining.runtime import ChainRuntime  # noqa: E402
from chaining.tools import validated_json_response  # noqa: E402

ITINERARY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "city": {"type": "string"},
        "days": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "nights": {"type": "integer", "minimum": 0},
    },
    "required": ["city", "days", "nights"],
    "additionalProperties": False,
}

OFFLINE_RULES = [
    # 第一次输出：故意是不完整/非法的 JSON（结尾缺右花括号）
    ("itinerary JSON", '{"city": "Beijing", "days": ["D1", "D2"]'),
    # 修复提示词触发后：返回符合 schema 的完整 JSON
    ("fix errors", '{"city": "Beijing", "days": ["D1", "D2"], "nights": 1}'),
]


def run_flow(payload: Dict[str, Any], runtime: ChainRuntime) -> Dict[str, Any]:
    destination = (payload.get("destination") or "Beijing").strip()

    # 1) 模型草拟 JSON 行程
    out = runtime.model_turn(
        "You are a travel planner. Draft an itinerary JSON for a 2-day trip. "
        f"The destination is {destination}.\n"
        'The JSON must contain keys: "city" (string), "days" (array of strings), '
        '"nights" (integer). Do NOT include any explanation, only return the JSON object.',
        step_id="vl.draft",
        max_tokens=300,
        temperature=0.0,
    )

    # 2) 解析 + 校验 + 失败自动修复循环
    parsed = validated_json_response(
        runtime,
        step_id_prefix="vl.check",
        response_text=out["response"],
        schema=ITINERARY_SCHEMA,
    )
    return {"parsed": parsed, "raw_response": out["response"]}


def main() -> None:
    runtime = make_runtime(OFFLINE_RULES)
    result = run_flow({}, runtime)
    print("首次草稿（不合法 JSON）:", result["raw_response"])
    print("校验/修复后对象:", result["parsed"])
    print(f"模型调用次数: {model_calls(runtime)}（1 次草稿 + 1 次修复；修复循环在链内自动完成）")


if __name__ == "__main__":
    main()
