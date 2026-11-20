"""
编排辅助工具（chaining.tools）
=============================

提供链式流程中反复出现的非模型能力：
  * JSON 结构校验与修复循环（parse → 校验 → 失败让模型修复 → 重试）
  * Map 分支产物合并（合并每个分项的对话增量）
  * 工具型 Agent 循环（模型自主决定调用工具 → 执行 → 回填结果 → 继续）

这些工具对应 Worker 函数族（src/functions/*），二者行为一致：
  * 独立 Worker 函数（src/functions/parse_json_response 等）用于演示「函数即服务」的
    独立部署形态；
  * 链运行时内直接调用本模块（内嵌形态），避免同进程内多次函数跳转的开销。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

from adapter.model_adapter import tool_result_message
from chaining.runtime import ChainRuntime

logger = logging.getLogger(__name__)

MAX_FIX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# JSON 解析与校验
# ---------------------------------------------------------------------------

def parse_and_validate(response_text: str, schema: Dict[str, Any]) -> Any:
    """
    解析 JSON 字符串并按其 JSON Schema 校验，返回对象。
    失败抛出 json.JSONDecodeError / jsonschema.ValidationError。
    """
    obj = json.loads(response_text)          # 失败抛 JSONDecodeError
    if schema:
        from jsonschema import validate as json_schema_validate
        json_schema_validate(instance=obj, schema=schema)
    return obj


def _build_fix_prompt(error: Exception, schema: Dict[str, Any]) -> str:
    schema_text = json.dumps(schema, indent=2, ensure_ascii=False)
    return (
        "I attempted to validate your response against my JSON schema, but received "
        "the following error inside <error></error> XML tags.\n"
        "<error>\n"
        f"{type(error).__name__}\n\n"
        f"{error}\n"
        "</error>\n\n"
        "Here is my JSON schema, inside <schema></schema> XML tags:\n"
        "<schema>\n"
        f"{schema_text}\n"
        "</schema>\n\n"
        "Please try to fix errors in the JSON response you gave previously and return "
        "a new JSON response that complies with the JSON schema.\n"
        "Do NOT include any explanation, comments, apology, or markdown style "
        "code-back-ticks.\n"
        "Remember - only return a valid JSON object."
    )


def validated_json_response(
    runtime: ChainRuntime,
    *,
    step_id_prefix: str,
    response_text: str,
    schema: Optional[Dict[str, Any]] = None,
    max_fix_tokens: int = 500,
) -> Any:
    """
    解析 + 校验 + （失败时）让模型修复后重试。

    相当于 parse_json_response Worker + 修复循环：最多修复 MAX_FIX_ATTEMPTS 次，
    全部失败时抛出最后一次校验异常。
    """
    schema = schema or {}
    current = response_text
    for attempt in range(MAX_FIX_ATTEMPTS + 1):
        try:
            return parse_and_validate(current, schema)
        except Exception as exc:  # noqa: BLE001 - JSON/Schema 错误统一进入修复
            if attempt >= MAX_FIX_ATTEMPTS:
                logger.error("JSON 校验失败且修复次数用尽: %s", exc)
                raise
            logger.warning("JSON 校验失败（第 %s 次），让模型修复：%s", attempt + 1, exc)
            fix_prompt = _build_fix_prompt(exc, schema)
            out = runtime.model_turn(
                fix_prompt,
                step_id=f"{step_id_prefix}.fix.{attempt + 1}",
                include_conversation=False,
                max_tokens=max_fix_tokens,
                temperature=0.0,
            )
            current = out["response"]
    raise RuntimeError("unreachable")  # pragma: no cover


# ---------------------------------------------------------------------------
# Map 分支产物合并
# ---------------------------------------------------------------------------

def merge_map_outputs(map_results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """
    合并 Map 分支结果（与独立 merge_map_output Worker 逻辑一致）。

    约定：每个分项形如 {"...": {...}, "model_outputs": {..., "conversation": [...]}}，
    且 conversation = 「公共历史 + 本分项专属两轮（user 提示 + assistant 产出）」。
    合并策略：
      1) 取第一项的公共历史 = conversation[:-2]；
      2) 按输入顺序，把每项各自的最后两轮 append 到公共历史之后。
    返回 {"conversation": 合并后的历史}。
    """
    if not map_results:
        return {"conversation": []}

    first = list(map_results[0]["model_outputs"]["conversation"])
    merged = list(first[:-2])
    for item_result in map_results:
        conv = list(item_result["model_outputs"]["conversation"])
        merged.extend(conv[-2:])
    return {"conversation": merged}


# ---------------------------------------------------------------------------
# 工具型 Agent 循环（ReAct 风格）
# ---------------------------------------------------------------------------

def run_tool_agent(
    runtime: ChainRuntime,
    *,
    user_input: str,
    tools: List[Dict[str, Any]],
    dispatcher: Callable[[str, Dict[str, Any]], str],
    step_id_prefix: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    max_iterations: int = 8,
) -> Dict[str, Any]:
    """
    工具型 Agent 主循环：

      1) 携带 system + 用户问题 + 历史调用模型，模型返回文本或 tool_calls；
      2) 若返回 tool_calls：逐个执行（dispatcher(name, arguments) → 文本结果），
         把结果作为 tool 消息回填，继续调用模型；
      3) 若返回纯文本（无 tool_calls）→ 作为最终答复结束。

    dispatcher 返回值为字符串（工具执行结果，写入 tool 消息）。
    返回 {"response": 最终文本, "steps": 每轮工具调用日志}。
    """
    from adapter.model_adapter import text_message

    messages: List[Dict[str, Any]] = []
    if system_prompt:
        messages.append(text_message("system", system_prompt))
    messages.append(text_message("user", user_input))

    steps: List[Dict[str, Any]] = []
    final_text = ""

    def _assistant_tool_message(tool_calls: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """把模型返回的 tool_calls 序列化为 OpenAI 协议里的 assistant 消息。"""
        wire_calls = []
        for tc in tool_calls:
            wire_calls.append(
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False),
                    },
                }
            )
        return {"role": "assistant", "content": None, "tool_calls": wire_calls}

    for iteration in range(max_iterations):
        step_id = f"{step_id_prefix}.agent.{iteration + 1}"
        out = runtime.model_turn(
            "",  # prompt 无实际含义（本轮消息完全由 messages 决定）
            step_id=step_id,
            conversation=messages,
            include_conversation=False,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
        )
        tool_calls = out.get("tool_calls") or []
        cached_log = runtime.replay.get(step_id) if runtime.replay else None

        if tool_calls:
            # 1) 回填本轮 assistant 消息（含 tool_calls），保持协议完整
            messages.append(_assistant_tool_message(tool_calls))
            # 2) 回放命中时复用已缓存的工具结果，避免重放期间再次调用外部工具
            cached_results = (cached_log or {}).get("tool_results")
            results: List[Dict[str, str]] = []
            for idx, tc in enumerate(tool_calls):
                name = tc["name"]
                arguments = tc.get("arguments", {})
                if cached_results is not None and idx < len(cached_results):
                    result_text = cached_results[idx]["result"]
                else:
                    logger.info("Agent 调用工具 %s(%s)", name, arguments)
                    try:
                        result_text = dispatcher(name, arguments)
                    except Exception as exc:  # noqa: BLE001 - 工具错误回传给模型
                        result_text = f"工具执行失败：{exc}"
                results.append({"tool_call_id": tc["id"], "result": result_text})
                messages.append(tool_result_message(tc["id"], result_text))
                steps.append({"tool": name, "arguments": arguments, "result": result_text})
            if cached_results is None:
                runtime.record_tool_results(step_id, results)
            continue

        # 纯文本轮 → 结束
        final_text = out.get("response", "")
        break
    else:
        raise RuntimeError("Agent 达到最大迭代次数仍未结束")

    return {"response": final_text, "steps": steps}
