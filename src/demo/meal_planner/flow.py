"""
晚餐规划（红蓝大厨辩论 + 评分仲裁示例）
========================================
两条厨师智能体链对同一食材清单并行出菜，随后进入「打分 → 辩论 → 一致性
裁判」的迭代循环：

  1. 两位厨师（Red / Blue）各自独立给出晚餐建议（相同食材前提）；
  2. 裁判模型给两份建议打分（JSON 输出，带结构校验修复循环）；
  3. 两位厨师看到对方建议与双方得分后各自「辩论」，改进自己的建议
     （每位厨师都沿用自己的对话历史持续累积，是彼此独立的子链）；
  4. 主持人模型判断两位厨师是否已达成一致（agree=yes/no JSON 输出）；
  5. 达成一致或辩论轮次达到上限(3) → 裁判再次为最终建议打分 →
     选最高分厨师为胜者（winning_chef）→ 为胜者建议生成完整菜谱。

编排原语映射：
  * 评分修复循环 → validated_json_response（JSON Schema 校验）
  * 并行分支（两位厨师的建议与辩论）→ runtime.parallel
  * 一致性判断回边 → while 循环 + 轮次计数
  * 选胜者（纯逻辑取最高分）→ 本地 argmax

payload:
  { "ingredients": "手头食材清单（必填）" }
"""
from __future__ import annotations

from typing import Any, Dict, List

from chaining.runtime import ChainRuntime
from chaining.tools import validated_json_response

CHEFS = ["red", "blue"]                     # 两位厨师，按此顺序编号
MAX_DEBATE_ROUNDS = 3                       # 辩论轮次上限

MEAL_GENERATOR_PROMPT = (
    "You are a world-class chef and you help people to plan out tasty home-cooked "
    "meals that they can cook themselves.\n"
    "I need help determining a tasty dinner I can make with the following ingredients "
    "I have on hand in my kitchen:\n{ingredients}\n"
    "Suggest the tastiest dinner I can make at home with these ingredients and minimal "
    "additional ingredients.\n"
    "Do not provide a full recipe, only provide a one or two sentence description of "
    "the meal, including a name for the meal."
)

RECIPE_PROMPT = (
    "You are a world-class chef and you help people to plan out tasty home-cooked "
    "meals that they can cook themselves.\n"
    "I need help determining a tasty dinner I can make with the following ingredients "
    "I have on hand in my kitchen:\n{ingredients}\n\n"
    "You previously suggested this meal, inside <dinner></dinner> XML tags.\n"
    "<dinner>\n{winning_meal}\n</dinner>\n\n"
    "Create a recipe for this meal, based on your previous meal suggestion and the "
    "ingredients I have on hand."
)

# 打分 / 主持人一致性的 JSON Schema
SCORE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}
for chef in CHEFS:
    SCORE_SCHEMA["properties"][f"{chef}_chef"] = {
        "type": "object",
        "properties": {
            "score": {"type": "number"},
            "score_reasoning": {"type": "string"},
        },
        "required": ["score", "score_reasoning"],
        "additionalProperties": False,
    }
    SCORE_SCHEMA["required"].append(f"{chef}_chef")

REFEREE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "do_chefs_agree": {"type": "string", "enum": ["yes", "no"]},
    },
    "required": ["reasoning", "do_chefs_agree"],
    "additionalProperties": False,
}


def run_flow(
    payload: Dict[str, Any],
    runtime: ChainRuntime,
    replies: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    ingredients = (payload.get("ingredients") or "").strip()
    if not ingredients:
        raise ValueError(
            "缺少 ingredients：请提供手头食材清单（如 「chicken, tomatoes, rice, garlic」）。"
        )

    # ---- 1) 两位厨师并行给出初始建议 ----
    meals: Dict[str, str] = {}
    convs: Dict[str, List[Dict[str, Any]]] = {}

    def initial_suggestion(chef: str) -> Dict[str, Any]:
        out = runtime.model_turn(
            MEAL_GENERATOR_PROMPT.format(ingredients=ingredients),
            step_id=f"meal.init.{chef}",
            conversation=[],             # 独立分支：每位厨师一条自己的链
            max_tokens=500,
            temperature=1.0,
        )
        return {"chef": chef, "response": out["response"], "conversation": out["conversation"]}

    initial_results: List[Dict[str, Any]] = runtime.parallel(
        [lambda chef=c: initial_suggestion(chef) for c in CHEFS]
    )
    for result in initial_results:
        chef = result["chef"]
        meals[f"{chef}_chef"] = result["response"]
        convs[chef] = result["conversation"]

    # ---- 2~5) 打分 → 辩论 → 一致性判断（未达成则回边继续） ----
    loop_index = 0
    while True:
        scores = _score_meals(runtime, loop_index=loop_index, meals=meals, final=False)
        loop_index += 1

        meals, convs = _debate(
            runtime,
            loop_index=loop_index,
            convs=convs,
            meals=meals,
            scores=scores,
            ingredients=ingredients,
        )

        agreed = _referee(runtime, loop_index=loop_index, meals=meals)
        if agreed or loop_index >= MAX_DEBATE_ROUNDS:
            break

    # ---- 6) 最终评分 + 选胜者 + 生成菜谱 ----
    final_scores = _score_meals(runtime, loop_index=loop_index, meals=meals, final=True)

    winning_chef, winning_meal = _pick_winner(final_scores, meals)
    recipe_out = runtime.model_turn(
        RECIPE_PROMPT.format(ingredients=ingredients, winning_meal=winning_meal),
        step_id=f"meal.recipe.{loop_index}",
        conversation=[],                 # 独立节点：内容全部内联
        max_tokens=2000,
        temperature=1.0,
    )

    return {
        "final_answer": recipe_out["response"],
        "recipe": recipe_out["response"],
        "winning_chef": winning_chef,
        "meal": winning_meal,
        "winning_meal": winning_meal,
        "ingredients": ingredients,
        "debate_rounds": loop_index,
        "meals": meals,
        "final_scores": final_scores,
    }


# ---------------------------------------------------------------------------
# 内部步骤
# ---------------------------------------------------------------------------


def _build_score_prompt(meals: Dict[str, str]) -> str:
    """组装打分提示词：要求模型按结构化格式输出双方得分。"""
    lines = [
        "You are a world-class chef acting as a judge on a cooking competition TV "
        "show. On this show, you evaluate how tasty each contestant's meal is.",
        "Multiple contestants are competing to prepare the tastiest dish using a set "
        "of ingredients.",
    ]
    for i, chef in enumerate(CHEFS):
        meal_key = f"{chef}_chef"
        lines.append(
            f"\n{i + 1}. Contestant #{i + 1} (Chef {chef.capitalize()}) prepared the "
            f"following dish, inside <{meal_key}></{meal_key}> XML tags.\n"
            f"<{meal_key}>\n{meals[meal_key]}\n</{meal_key}>"
        )
    lines.extend(
        [
            "\nIMPORTANT: Your response must be ONLY a JSON object. Do not use "
            "markdown code blocks, backticks, or any formatting. Start your response "
            "directly with the opening brace.",
            "\nScore the tastiness of each contestant's dish using a number between 0 "
            "and 100.",
            "Try to have a distinct tastiness score for each contestant. Output 1 or 2 "
            "sentences explaining your reasoning for how you scored the contestant, "
            "and then output the score.",
            "\nYour response should be formatted as a JSON object, with a key for each "
            "contestant and an object containing that contestant's score and your "
            "reasoning.",
        ]
    )
    example = []
    for i, chef in enumerate(CHEFS):
        meal_key = f"{chef}_chef"
        example.append(
            f'    "{meal_key}": {{\n'
            f'        "score_reasoning": "Brief reasons for the score I assigned to '
            f'Chef {chef.capitalize()}...",\n'
            f'        "score": {80 + i}\n'
            "    }"
        )
    lines.append(
        "\nAn example of a valid response is below, inside <example></example> XML "
        "tags.\n<example>\n{\n"
        + ",\n".join(example)
        + "\n}\n</example>"
    )
    lines.append(
        "\nDo not include any other content other than the JSON object in your "
        "response. Do not include any XML tags in your response. Do not wrap the JSON "
        "in markdown code blocks or backticks."
    )
    return "\n".join(lines)


def _score_meals(
    runtime: ChainRuntime,
    *,
    loop_index: int,
    meals: Dict[str, str],
    final: bool,
) -> Dict[str, Any]:
    """裁判给当前两份建议打分，并用 JSON Schema 校验/修复。"""
    tag = "finalscore" if final else "score"
    step_id = f"meal.{tag}.{loop_index}"
    out = runtime.model_turn(
        _build_score_prompt(meals),
        step_id=step_id,
        conversation=[],                 # 独立节点：建议都内联在提示词里
        max_tokens=500,
        temperature=1.0,
    )
    return validated_json_response(
        runtime,
        step_id_prefix=step_id,
        response_text=out["response"],
        schema=SCORE_SCHEMA,
    )


def _build_debate_prompt(
    chef: str,
    meals: Dict[str, str],
    scores: Dict[str, Any],
    ingredients: str,
) -> str:
    """组装某位厨师的辩论提示词：参考对手建议/双方得分，改进自己的建议。"""
    other = [c for c in CHEFS if c != chef][0]
    other_name = other.capitalize()
    chef_name = chef.capitalize()

    other_meal = meals[f"{other}_chef"]
    other_score = scores[f"{other}_chef"]["score"]
    other_reasoning = scores[f"{other}_chef"]["score_reasoning"]
    own_score = scores[f"{chef}_chef"]["score"]
    own_reasoning = scores[f"{chef}_chef"]["score_reasoning"]

    return (
        f"Another chef (Chef {other_name}) suggested the following meal to me, inside "
        f"<{other_name}Dinner></{other_name}Dinner> XML tags.\n"
        f"<{other_name}Dinner>\n{other_meal}\n</{other_name}Dinner>\n"
        f"Chef {other_name}'s suggested meal was scored for tastiness on a scale of 0 "
        f"to 100 and received the following score and score explanation, inside "
        f"<{other_name}Score></{other_name}Score> XML tags.\n"
        f"<{other_name}Score>\n{other_score}\n{other_reasoning}\n</{other_name}Score>\n"
        f"You got the following tastiness score and score explanation for your own "
        f"meal suggestion, inside <{chef_name}Score></{chef_name}Score> XML tags.\n"
        f"<{chef_name}Score>\n{own_score}\n{own_reasoning}\n</{chef_name}Score>\n"
        "Compare the other chefs' answers with yours and try to improve your own "
        "answer to be more tasty than theirs.\n"
        + MEAL_GENERATOR_PROMPT.format(ingredients=ingredients)
    )


def _debate(
    runtime: ChainRuntime,
    *,
    loop_index: int,
    convs: Dict[str, List[Dict[str, Any]]],
    meals: Dict[str, str],
    scores: Dict[str, Any],
    ingredients: str,
) -> tuple[Dict[str, str], Dict[str, List[Dict[str, Any]]]]:
    """两位厨师并行辩论一轮：各自沿用自己的对话历史改进建议。"""

    def chef_debater(chef: str) -> Dict[str, Any]:
        prompt = _build_debate_prompt(chef, meals, scores, ingredients)
        out = runtime.model_turn(
            prompt,
            step_id=f"meal.debate.{loop_index}.{chef}",
            conversation=convs[chef],    # 每位厨师自己的链（含此前全部轮次）
            max_tokens=500,
            temperature=1.0,
        )
        return {
            "chef": chef,
            "response": out["response"],
            "conversation": out["conversation"],
        }

    results: List[Dict[str, Any]] = runtime.parallel(
        [lambda chef=c: chef_debater(chef) for c in CHEFS]
    )
    new_meals: Dict[str, str] = {}
    new_convs: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        chef = result["chef"]
        new_meals[f"{chef}_chef"] = result["response"]
        new_convs[chef] = result["conversation"]
    return new_meals, new_convs


def _build_referee_prompt(meals: Dict[str, str]) -> str:
    """组装主持人一致性判断提示词：输出 agree=yes/no 的结构化判定。"""
    lines = [
        "You are a world-class chef and you help people to plan out tasty home-cooked "
        "meals that they can cook themselves.",
        "Multiple other chefs are working together to agree on the tastiest dinner I "
        "could make at home.",
    ]
    for i, chef in enumerate(CHEFS):
        lines.append(
            f"\n{i + 1}. Meal suggestion from Chef {chef.capitalize()} is below, "
            f"inside <{chef.capitalize()}></{chef.capitalize()}> XML tags.\n"
            f"<{chef.capitalize()}>\n{meals[f'{chef}_chef']}\n</{chef.capitalize()}>"
        )
    lines.extend(
        [
            "\nIMPORTANT: Your response must be ONLY a JSON object. Do not use "
            "markdown code blocks, backticks, or any formatting. Start your response "
            "directly with the opening brace.",
            "\nDo these chefs agree with each other on the tastiest meal I could make?",
            "Answer no only if the chefs suggested very different meals.",
            "Answer yes if the chefs suggested the same meal, similar meals, or meals "
            "that are a small variation of each other.",
            "Start your response with an explanation of your reasoning, then provide a "
            "single 'yes' or 'no' indicating whether agreement has been reached.",
            "\nYour response should be formatted as a JSON object.",
            "\nAn example of a valid response is below when the chefs do agree, inside "
            "<example></example> XML tags.\n"
            "<example>\n{\n    \"reasoning\": \"Brief reasons for why I believe the "
            "chefs have reached agreement...\",\n    \"do_chefs_agree\": \"yes\"\n"
            "}\n</example>",
            "\nAnother example of a valid response is below when the chefs do not "
            "agree, inside <example></example> XML tags.\n"
            "<example>\n{\n    \"reasoning\": \"Brief reasons for why I believe the "
            "chefs have not reached agreement...\",\n    \"do_chefs_agree\": \"no\"\n"
            "}\n</example>",
            "\nDo not include any other content other than the JSON object in your "
            "response. Do not include any XML tags in your response. Do not wrap the "
            "JSON in markdown code blocks or backticks.",
        ]
    )
    return "\n".join(lines)


def _referee(
    runtime: ChainRuntime,
    *,
    loop_index: int,
    meals: Dict[str, str],
) -> bool:
    """主持人判断两位厨师是否已达成一致。"""
    step_id = f"meal.referee.{loop_index}"
    out = runtime.model_turn(
        _build_referee_prompt(meals),
        step_id=step_id,
        conversation=[],                 # 独立节点
        max_tokens=500,
        temperature=1.0,
    )
    parsed = validated_json_response(
        runtime,
        step_id_prefix=step_id,
        response_text=out["response"],
        schema=REFEREE_SCHEMA,
    )
    return parsed["do_chefs_agree"] == "yes"


def _pick_winner(
    final_scores: Dict[str, Any],
    meals: Dict[str, str],
) -> tuple[str, str]:
    """取最高分厨师为胜者（纯逻辑 argmax，不调用模型）。"""
    highest_score = -1.0
    winning_chef: str | None = None
    for chef in CHEFS:
        score = float(final_scores[f"{chef}_chef"]["score"])
        if score > highest_score:
            highest_score = score
            winning_chef = f"{chef}_chef"
    if not winning_chef:
        raise RuntimeError("No winning meal found")
    return winning_chef, meals[winning_chef]


if __name__ == "__main__":
    from demo._runner import run_flow_session

    session = run_flow_session(
        run_flow,
        {"ingredients": "chicken, tomatoes, rice, garlic"},
    )
    if session["status"] == "ok":
        print(session["result"]["final_answer"])
    else:
        print("执行失败:", session.get("message"))
