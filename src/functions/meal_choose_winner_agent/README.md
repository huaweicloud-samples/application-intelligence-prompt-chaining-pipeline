# meal_choose_winner_agent —— 评分仲裁 Worker

MealPlanner「选胜者」环节：给定裁判打分 `scores` 与各位厨师最新建议
`meals`，取最高分厨师（纯逻辑 argmax，不调用模型）。

| 部署形态 | 入口 | 说明 |
| --- | --- | --- |
| 独立 Worker | `index.handler` | 事件：`{scores, meals}`；返回 `{winning_chef, winning_meal, winning_score}` |
| 链内嵌 | `demo/meal_planner/flow.py::_pick_winner` | 同进程直接计算 |

说明：入口显式接收 `meals` 参数，直接完成「评委打分 JSON → 厨师建议文本」的
映射与最高分选择，逻辑直白、可单测。

