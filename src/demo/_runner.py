"""
会话执行包装器
==============
统一处理「执行 → 人工确认 → 续跑」的会话协议，供前端与函数入口复用。

协议：
  * execute() 首次执行：flow 无人工确认时返回最终结果；
    命中人工确认点时，flow 抛 HumanInputRequired，包装器序列化为
    {"status": "awaiting_human_input", "questions", "reply_keys",
     "transcript", "partial_state"}。
  * execute() 续跑：调用方把首次返回的 transcript / partial_state 原样带回，
    并附带 replies（用户答复 dict），包装器恢复回放缓存后重放已执行节点，
    从人工答复处继续，直到下一个确认点或结束。
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from chaining.runtime import ChainRuntime, HumanInputRequired


class ExecutionError(Exception):
    """流程执行失败（业务异常已包装）。"""


def run_flow_session(
    flow_run: Callable[[Dict[str, Any], ChainRuntime, Dict[str, Any]], Dict[str, Any]],
    payload: Dict[str, Any],
    *,
    replies: Optional[Dict[str, Any]] = None,
    transcript: Optional[List[Dict[str, Any]]] = None,
    partial_state: Optional[Dict[str, Any]] = None,
    adapter: Any = None,
) -> Dict[str, Any]:
    """
    执行（或续跑）一个 demo 流程。

    参数：
      flow_run      demo 的 run_flow(payload, runtime, replies) 函数
      payload       业务入参
      replies       用户答复 dict（续跑必需，键与 reply_keys 对齐）
      transcript    首次执行时返回的回放缓存（续跑必需）
      partial_state 首次执行时返回的业务中间态（续跑必需，会并入 payload）
      adapter       模型适配器（默认进程级单例；测试可注入替身）

    返回：最终结果 dict（含 status="ok"）或等待人工输入 dict。
    """
    runtime = ChainRuntime(adapter=adapter) if adapter is not None else ChainRuntime()
    if transcript:
        runtime.restore_transcript(transcript)

    merged_payload: Dict[str, Any] = {}
    if partial_state:
        merged_payload.update(partial_state)
    merged_payload.update(payload)

    try:
        result = flow_run(merged_payload, runtime, replies or {})
        return {
            "status": "ok",
            "result": result,
            "logs": runtime.logs,
        }
    except HumanInputRequired as gate:
        return {
            "status": "awaiting_human_input",
            "questions": [it.to_dict() for it in gate.items],
            "reply_keys": gate.reply_keys,
            "transcript": gate.transcript or runtime.logs,
            "partial_state": gate.partial_state or {},
        }
    except Exception as exc:  # noqa: BLE001 - 统一包装业务异常
        return {
            "status": "error",
            "message": str(exc),
            "logs": runtime.logs,
        }


def decode_event_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    函数入口的事件解码：兼容函数计算 APIG 触发器的 JSON body 字符串，
    以及测试时直接传入的 dict。
    """
    body = event.get("body", event)
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ExecutionError(f"请求体不是合法 JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise ExecutionError("请求体必须为 JSON 对象")
    return body


def ok_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """构造函数入口的标准响应体（APIG 兼容）。"""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, ensure_ascii=False, default=str),
    }
