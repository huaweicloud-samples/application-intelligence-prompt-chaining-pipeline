"""
行程规划（并行分支示例）
========================
三个独立的「专家」代理并行给出建议（住宿 / 餐厅 / 景点），
汇总为一份覆盖周五~周日的三日行程 Markdown。

后续可选：把行程交给本地/桌面环境的排版能力（functions/trip_planner/pdf_creator）
渲染为 PDF；在函数计算等受限运行时不内置渲染依赖，直接返回 Markdown + 打印版 HTML。
"""
from __future__ import annotations

import html as _html
from typing import Any, Dict, List

from chaining.runtime import ChainRuntime

HOTELS_PROMPT = """You are a world-class travel agent and an expert on travel to {location}.
I am going on a weekend vacation to {location}.
Please give me up to 5 suggestions for hotels for my vacation."""

RESTAURANTS_PROMPT = """You are a world-class travel agent and an expert on travel to {location}.
I am going on a weekend vacation to {location}.
Please give me suggestions for restaurants for my vacation, including up to 5 suggestions for breakfast, lunch, and dinner."""

ACTIVITIES_PROMPT = """You are a world-class travel agent and an expert on travel to {location}.
I am going on a weekend vacation to {location}.
Please give me up to 5 suggestions for activities to do or places to visit during my vacation."""

ITINERARY_PROMPT = """You are a world-class travel agent and an expert on travel to {location}.
I am going on a weekend vacation to {location} (arriving Friday, leaving Sunday).

You previously recommended these hotels, inside <hotels></hotels> XML tags.
<hotels>
{hotels}
</hotels>

You previously recommended these restaurants, inside <restaurants></restaurants> XML tags.
<restaurants>
{restaurants}
</restaurants>

You previously recommended these activities, inside <activities></activities> XML tags.
<activities>
{activities}
</activities>

Please give me a daily itinerary for my three-day vacation, based on your previous recommendations.
The itinerary should include one hotel where I will stay for the duration of the vacation.
Each of the three days in the itinerary should have one activity, one restaurant for breakfast, one restaurant for lunch, and one restaurant for dinner.
Each entry in the itinerary should include a short description of your recommended hotel, activity, or restaurant.
The itinerary should be formatted in Markdown format."""


def run_flow(
    payload: Dict[str, Any],
    runtime: ChainRuntime,
    replies: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    location = payload.get("location") or "Paris, France"

    # ---- 并行：三个独立专家建议（互不共享历史） ----
    def suggest(step_id: str, template: str) -> Dict[str, Any]:
        return runtime.model_turn(
            template.format(location=location),
            step_id=step_id,
            conversation=[],            # 独立节点：不读、不写全局历史
            max_tokens=512,
            temperature=1.0,
        )

    outputs: List[Dict[str, Any]] = runtime.parallel(
        [
            lambda: suggest("trip.hotels", HOTELS_PROMPT),
            lambda: suggest("trip.restaurants", RESTAURANTS_PROMPT),
            lambda: suggest("trip.activities", ACTIVITIES_PROMPT),
        ]
    )

    # 分支顺序即提交顺序：[0] hotels / [1] restaurants / [2] activities
    hotels, restaurants, activities = [out["response"] for out in outputs]

    # ---- 汇总：生成三日行程 ----
    itinerary_out = runtime.model_turn(
        ITINERARY_PROMPT.format(
            location=location,
            hotels=hotels,
            restaurants=restaurants,
            activities=activities,
        ),
        step_id="trip.itinerary",
        conversation=[],               # 独立节点：所有建议都内联在提示词中
        max_tokens=1024,
        temperature=1.0,
    )
    itinerary = itinerary_out["response"]

    return {
        "final_answer": itinerary,
        "location": location,
        "suggestions": {
            "hotels": hotels,
            "restaurants": restaurants,
            "activities": activities,
        },
        # 打印版 HTML：浏览器「打印为 PDF」或本地渲染器使用
        "render_html": markdown_to_html(itinerary, location),
    }


def markdown_to_html(markdown_text: str, title: str) -> str:
    """极简 Markdown → HTML（用于打印/PDF 渲染，非完整实现）。"""
    paragraphs: List[str] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("### "):
            paragraphs.append(f"<h3>{_html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            paragraphs.append(f"<h2>{_html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            paragraphs.append(f"<h1>{_html.escape(line[2:])}</h1>")
        elif line.startswith("- ") or line.startswith("* "):
            paragraphs.append(f"<li>{_html.escape(line[2:])}</li>")
        else:
            # 简单处理加粗
            safe = _html.escape(line)
            safe = safe.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
            paragraphs.append(f"<p>{safe}</p>")

    return (
        "<html><head><meta charset=\"utf-8\"><style>"
        "body{font-family:sans-serif;max-width:720px;margin:24px auto;line-height:1.6}"
        "h1,h2,h3{color:#1a1a2e}</style></head>"
        f"<body><h1>{_html.escape(title)} — 行程单</h1>{''.join(paragraphs)}</body></html>"
    )


if __name__ == "__main__":
    from demo._runner import run_flow_session

    session = run_flow_session(run_flow, {"location": "Paris, France"})
    if session["status"] == "ok":
        print(session["result"]["final_answer"])
    else:
        print("执行失败:", session.get("message"))
