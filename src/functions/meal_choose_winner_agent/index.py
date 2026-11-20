"""
评分仲裁 Worker（meal_choose_winner_agent）
==========================================
在 MealPlanner 流程中，裁判为两位厨师最终建议打分后，本函数选取得分最高者。
纯逻辑、不调用模型：取 scores 中 score 最大的 chef，返回该厨师的建议文本。

事件体：
  {
    "scores": { "red_chef": {"score": 90, ...}, "blue_chef": {"score": 85, ...} },
    "meals":  { "red_chef": "建议文本", "blue_chef": "建议文本" }
  }

链内同语义实现见 src/demo/meal_planner/flow.py 的 _pick_winner。
"""
from __future__ import annotations

from typing import Any, Dict


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    body = event.get("body", event)
    if isinstance(body, str):
        import json
        body = json.loads(body)

    scores = body.get("scores") or {}
    meals = body.get("meals") or {}

    highest_score = -1.0
    winning_chef: str | None = None
    for key, value in scores.items():
        score = float(value.get("score", -1))
        if score > highest_score:
            highest_score = score
            winning_chef = key

    if not winning_chef:
        raise RuntimeError("No winning meal found")
    if winning_chef not in meals:
        raise RuntimeError(f"Missing meal text for winning chef {winning_chef}")

    return {
        "statusCode": 200,
        "winning_chef": winning_chef,
        "winning_meal": meals[winning_chef],
        "winning_score": highest_score,
    }


if __name__ == "__main__":
    sample = {
        "scores": {
            "red_chef": {"score": 90, "score_reasoning": "..."},
            "blue_chef": {"score": 85, "score_reasoning": "..."},
        },
        "meals": {"red_chef": "番茄鸡肉焗饭", "blue_chef": "蒜香米饭碗"},
    }
    print(handler(sample, None))
