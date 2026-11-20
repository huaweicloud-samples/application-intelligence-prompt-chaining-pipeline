"""
Map 分支产物合并 Worker
=======================
合并 Map/并行分支里每个分项产生的对话增量，得到一条完整对话历史。

约定：每个分项形如
  { "model_outputs": { "conversation": [...公共历史..., ...本分项专属两轮...] } }
合并策略：
  1) 以第一项的「公共历史」= conversation[:-2] 为底；
  2) 按输入顺序把每项各自的最后两轮（user 提示 + assistant 产出）依次追加。
返回 {"statusCode": 200, "conversation": 合并后的历史}

链内等同实现见 chaining.tools.merge_map_outputs。
"""
from __future__ import annotations

from typing import Any, Dict, List


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    body = event.get("body", event)
    if isinstance(body, str):
        import json
        body = json.loads(body)

    map_results: List[Dict[str, Any]] = body.get("map_results") or []
    if not map_results:
        return {"statusCode": 200, "conversation": []}

    first = list(map_results[0]["model_outputs"]["conversation"])
    merged: List[Dict[str, Any]] = list(first[:-2])
    for item_result in map_results:
        conv = list(item_result["model_outputs"]["conversation"])
        merged.extend(conv[-2:])
    return {"statusCode": 200, "conversation": merged}


if __name__ == "__main__":
    sample = {
        "map_results": [
            {"model_outputs": {"conversation": [
                {"role": "user", "content": "公共提示"},
                {"role": "assistant", "content": "公共回答"},
                {"role": "user", "content": "分项1提示"},
                {"role": "assistant", "content": "分项1回答"},
            ]}},
            {"model_outputs": {"conversation": [
                {"role": "user", "content": "公共提示"},
                {"role": "assistant", "content": "公共回答"},
                {"role": "user", "content": "分项2提示"},
                {"role": "assistant", "content": "分项2回答"},
            ]}},
        ]
    }
    result = handler(sample, None)
    assert len(result["conversation"]) == 6, result
    print("OK", [m["role"] for m in result["conversation"]])
