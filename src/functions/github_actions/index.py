"""
GitHub 只读工具 Worker（独立部署形态）
====================================
与链内工具（demo/most_popular_repo/github_tools.py）行为一致的独立函数，
供「把工具拆成独立函数服务」的部署形态演示：

  事件体（APIG JSON body 或直接事件）：
    {
      "tool": "get_trending_github_repositories" | "get_github_repository_readme",
      "arguments": { "input": "..." }
    }
    # 兼容写法：顶层直接给 {"name": ..., "arguments": {...}}

  响应：
    成功 -> {"statusCode": 200, "contents": "<工具返回文本>"}
    失败 -> {"statusCode": 400/500, "error": "错误描述"}

说明：
  * 仅使用标准库（urllib + html.parser），无需第三方依赖；
  * GITHUB_TOKEN 环境变量可选（提高 api.github.com 配额，不设置也能读公开仓库）；
  * 真实 HTTP 副作用仅在本函数内发生，链内断点续跑不会重复调用本函数（由运行时
    缓存工具结果，见 chaining/runtime.record_tool_results）。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:  # 目录作为代码根目录直接部署时使用绝对导入
    from . import github_tools
except ImportError:  # pragma: no cover - 兼容包内导入形态
    import github_tools  # type: ignore

KNOWN_TOOLS = ("get_trending_github_repositories", "get_github_repository_readme")


def _decode(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body", event)
    if isinstance(body, str):
        return json.loads(body)
    if not isinstance(body, dict):
        raise TypeError("请求体必须为 JSON 对象")
    return body


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        body = _decode(event)
    except Exception as exc:  # noqa: BLE001 - 统一包装为错误响应
        return {"statusCode": 400, "error": f"请求体解析失败: {exc}"}

    tool_name = body.get("tool") or body.get("name")
    arguments = body.get("arguments") or {}

    if tool_name not in KNOWN_TOOLS:
        return {
            "statusCode": 400,
            "error": (
                f"未知工具 {tool_name!r}。可用工具："
                + ", ".join(KNOWN_TOOLS)
            ),
        }

    try:
        contents = github_tools.tool_dispatcher(tool_name, arguments)
    except Exception as exc:  # noqa: BLE001 - 工具执行异常统一返回
        logger.exception("工具 %s 执行失败", tool_name)
        return {"statusCode": 500, "error": f"{tool_name} 执行失败: {exc}"}

    return {"statusCode": 200, "contents": contents}


if __name__ == "__main__":
    # 本地自测（不触发真实网络请求时可直接看错误处理路径）
    sample = {"tool": "get_trending_github_repositories", "arguments": {"input": ""}}
    print(json.dumps(handler(sample, None), ensure_ascii=False)[:500])
