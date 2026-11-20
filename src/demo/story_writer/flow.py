"""
故事创作（Map + 结构校验示例）
==============================
一条完整的故事创作流水线：

  角色设计(JSON 数组，严格结构校验，失败自动修复)
    → 并发为每个角色生成故事线（Map，最大并发 3）
    → 合并所有故事线上下文
    → 生成完整短篇故事
"""
from __future__ import annotations

from typing import Any, Dict, List

from chaining.runtime import ChainRuntime
from chaining.tools import merge_map_outputs, validated_json_response

# 角色 JSON 数组的严格 Schema（顺序无关、不允许额外字段、必须恰好 5 个）
CHARACTERS_SCHEMA: Dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["name", "description"],
        "additionalProperties": False,
    },
    "minItems": 5,
    "maxItems": 5,
    "uniqueItems": True,
}

# 角色设计提示词：只允许返回合法 JSON 数组（占位符 {story} 由入参填充）
CHARACTERS_PROMPT = """IMPORTANT: Your response must be ONLY a JSON array. Do not use markdown code blocks, backticks, or any formatting. Start your response directly with the opening bracket.

You are an award-winning fiction writer and you are writing a new story about {story}.
Before writing the story, describe five characters that will be in the story.

Your response should be formatted as a JSON array, with each element in the array containing a "name" key for the character's name and a "description" key with the character's description.
An example of a valid response is below, inside <example></example> XML tags.
<example>
[
    {{
        "name": "Character 1",
        "description": "Description for character 1"
    }},
    {{
        "name": "Character 2",
        "description": "Description for character 2"
    }}
]
</example>
Do not include any other content other than the JSON object in your response. Do not include any XML tags in your response. Do not wrap the JSON in markdown code blocks or backticks."""

STORY_DESCRIPTION = "Now write the short story about {story}. Respond only with the story content."


def run_flow(
    payload: Dict[str, Any],
    runtime: ChainRuntime,
    replies: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    story = payload.get("story_description") or payload.get("story") or "The wild west"

    # ---- 节点 1：角色设计（严格 JSON 输出） ----
    characters_out = runtime.model_turn(
        CHARACTERS_PROMPT.format(story=story),
        step_id="story.characters",
        max_tokens=1024,
        temperature=1.0,
        include_conversation=False,
    )
    characters = validated_json_response(
        runtime,
        step_id_prefix="story.characters.parse",
        response_text=characters_out["response"],
        schema=CHARACTERS_SCHEMA,
        max_fix_tokens=500,
    )

    # ---- 节点 2：Map —— 为每个角色生成独立故事线 ----
    # 所有分项共享「角色设计」快照历史；最大并发 3。
    snapshot_conversation = characters_out["conversation"]

    def character_arc(char: Dict[str, Any]) -> Dict[str, Any]:
        prompt = (
            "Now describe what will happen in the story to {name}, who you previously "
            "described as: {description}."
        ).format(name=char["name"], description=char["description"])
        return runtime.model_turn(
            prompt,
            step_id=f"story.arc.{char['name']}",
            conversation=snapshot_conversation,
            max_tokens=1024,
            temperature=1.0,
        )

    arc_outputs = runtime.map_items(characters, character_arc, concurrency=3)

    # ---- 节点 3：合并各角色故事线上下文 ----
    merged = merge_map_outputs([{"model_outputs": out} for out in arc_outputs])
    merged_conversation: List[Dict[str, Any]] = merged["conversation"]

    # ---- 节点 4：生成完整故事（携带全部合并后的上下文） ----
    story_out = runtime.model_turn(
        STORY_DESCRIPTION.format(story=story),
        step_id="story.full",
        conversation=merged_conversation,
        max_tokens=2048,
        temperature=1.0,
    )

    return {
        "final_answer": story_out["response"],
        "characters": characters,
        "arcs": [out["response"] for out in arc_outputs],
    }


if __name__ == "__main__":
    # 本地自测：python -m demo.story_writer.flow
    from demo._runner import run_flow_session

    session = run_flow_session(run_flow, {"story_description": "The wild west"})
    if session["status"] == "ok":
        print("角色:", [c["name"] for c in session["result"]["characters"]])
        print("故事:\n", session["result"]["final_answer"][:2000])
    else:
        print("执行失败:", session.get("message"))
