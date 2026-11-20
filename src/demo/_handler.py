"""
函数入口工厂
============
所有 demo 的函数入口（部署到函数计算服务后由 APIG/定时/消息事件触发）共用同一
事件契约与响应格式，差异只有「执行业务流程」。

事件体（APIG JSON body）：
  {
    "payload": {...},       # 业务入参（与本地执行一致）
    "replies": {...},       # 可选：续跑时用户答复
    "transcript": [...]     # 可选：续跑时回放缓存
  }
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from demo._runner import decode_event_body, ok_response, run_flow_session


def make_handler(
    flow_run: Callable[[Dict[str, Any], Any, Dict[str, Any]], Dict[str, Any]]
) -> Callable[[Dict[str, Any], Any], Dict[str, Any]]:
    """根据 demo 的 run_flow 函数生成标准事件处理器。"""

    def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        body = decode_event_body(event)
        payload = body.get("payload", body)
        replies = body.get("replies")
        transcript = body.get("transcript")
        partial_state = body.get("partial_state")
        session = run_flow_session(
            flow_run,
            payload,
            replies=replies,
            transcript=transcript,
            partial_state=partial_state,
        )
        return ok_response(session)

    handler.__name__ = f"{flow_run.__module__}_handler"
    return handler
