"""
人工确认节点占位 Worker（seek_user_input）
==========================================
代码编排形态下，需要真人拍板时由链内运行时直接抛 HumanInputRequired 信号
（携带问题、回放缓存与业务中间态），调用方（页面/入口函数）收集答复后带
缓存续跑 —— 不再依赖外部任务令牌与轮询。可参考：src/demo/movie_pitch。

本 Worker 保留「部署占位」形态作参考：调用方可以把问题与上下文持久化到
任意后端（数据库/消息队列），handler 原样回显事件便于联调与对接。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)

    # 生产对接时：把 body["question"] 与上下文写进会话存储，并把本次输入回显。
    logger.info("收到人工确认请求: %s", json.dumps(body, ensure_ascii=False))
    return {
        "statusCode": 200,
        "echo": body,
        "note": "把该请求持久化到会话后端后，等待用户作答并继续业务流程。",
    }


if __name__ == "__main__":
    print(handler({"question": "是否开绿灯？", "context": {"winning_movie_pitch": "..."}}, None))
