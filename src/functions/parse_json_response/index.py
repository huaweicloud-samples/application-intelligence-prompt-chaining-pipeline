"""
JSON 解析 + Schema 校验 Worker
==============================
独立部署形态的「解析并校验」函数，等同链内工具 chaining.tools.parse_and_validate
+ validated_json_response 的校验部分；修复循环由编排层（链代码）负责。

事件体：
  {
    "response_text": "模型返回的 JSON 文本",
    "json_schema": { ... }          # JSON Schema（可选，缺省只做语法解析）
  }

响应：
  成功 -> {"statusCode": 200, "parsed_output": <对象>}
  失败 -> {"statusCode": 400, "error": "错误描述"}
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


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

    response_text = body.get("response_text", "")
    schema = body.get("json_schema") or {}

    try:
        obj = json.loads(response_text)
    except json.JSONDecodeError as exc:
        logger.warning("response_text 不是合法 JSON: %s", exc)
        return {"statusCode": 400, "error": f"response_text 不是合法 JSON: {exc}"}

    if schema:
        try:
            from jsonschema import validate as json_schema_validate
            json_schema_validate(instance=obj, schema=schema)
        except Exception as exc:  # noqa: BLE001 - Schema 校验异常统一返回
            logger.warning("JSON Schema 校验失败: %s", exc)
            return {"statusCode": 400, "error": f"JSON Schema 校验失败: {exc}"}

    return {"statusCode": 200, "parsed_output": obj}


if __name__ == "__main__":
    import sys

    sample = {"response_text": '[{"name": "A"}]', "json_schema": {}}
    print(handler(sample, None))
