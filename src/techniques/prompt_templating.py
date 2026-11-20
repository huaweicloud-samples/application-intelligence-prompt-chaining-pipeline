# -*- coding: utf-8 -*-
"""
技术示例 2/9 —— 提示词模板（Prompt Templating）
==============================================
把「指令骨架」和「每次变化的变量」分离：同一套模板对多条输入复用，
避免在代码里拼接字符串、也便于统一调整措辞。

本示例用一条课程简介模板，分别渲染两门课程（面向不同受众），
两条分支互不相关，因此各自使用空历史（conversation=[]）。

运行：
  python -m techniques.prompt_templating
"""
from __future__ import annotations

from typing import Any, Dict, List

from techniques._util import ensure_src_path, make_runtime, model_calls

ensure_src_path()

from chaining.runtime import ChainRuntime  # noqa: E402

COURSE_TEMPLATE = (
    "Write a two-sentence course description for the online course \"{title}\". "
    "The target audience is {audience}. Emphasize the practical outcome."
)

OFFLINE_RULES = [
    ("serverless architecture on the cloud",
     "（占位）云上无服务器架构实战课：面向开发者的简介。"),
    ("building applications with large models",
     "（占位）大模型应用开发课：面向决策者的简介。"),
]


def run_flow(payload: Dict[str, Any], runtime: ChainRuntime) -> Dict[str, Any]:
    courses: List[Dict[str, str]] = payload.get("courses") or [
        {"title": "serverless architecture on the cloud", "audience": "developers"},
        {"title": "building applications with large models", "audience": "decision makers"},
    ]
    descriptions = []
    for idx, course in enumerate(courses, start=1):
        prompt = COURSE_TEMPLATE.format(**course)
        out = runtime.model_turn(
            prompt,
            step_id=f"pt.course.{idx}",
            conversation=[],  # 模板渲染互不相关：每条使用独立历史
            max_tokens=160,
            temperature=0.4,
        )
        descriptions.append(
            {"title": course["title"], "audience": course["audience"], "description": out["response"]}
        )
    return {"descriptions": descriptions}


def main() -> None:
    runtime = make_runtime(OFFLINE_RULES)
    result = run_flow({}, runtime)
    for item in result["descriptions"]:
        print(f"- 《{item['title']}》（面向 {item['audience']}）")
        print(f"    {item['description']}")
    print(f"模型调用次数: {model_calls(runtime)}（模板复用两次）")


if __name__ == "__main__":
    main()
