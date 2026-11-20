"""
博客长文生成（顺序链示例）
=========================
把一本书拆成五个递进的写作任务，前一节点的输出作为后一节点的对话上下文，
最终合成一篇结构完整的书评博客：

  摘要(1-2句) → 情节 → 主题 → 文风 → 成文(五段)
"""
from __future__ import annotations

from typing import Any, Dict

from chaining.runtime import ChainRuntime

# 五个节点：step_id 唯一；温度沿用默认；前 4 个 250 tokens，成文 1000 tokens。
# 除首个节点外都携带此前全部对话（顺序链累积语义由运行时保证）。
STEP_DEFS = [
    (
        "blog.summary",
        "Write a 1-2 sentence summary for the book {novel}.",
        250,
    ),
    (
        "blog.plot",
        "Write a paragraph describing the plot of the book {novel}.",
        250,
    ),
    (
        "blog.themes",
        "Write a paragraph analyzing the key themes of the book {novel}.",
        250,
    ),
    (
        "blog.style",
        "Write a paragraph discussing the writing style and tone of the book {novel}.",
        250,
    ),
    (
        "blog.post",
        'Combine your previous responses into a blog post titled "{novel} - A Literature '
        "Review\" for my literature blog. Start the blog post with an introductory "
        "paragraph at the beginning and a conclusion paragraph at the end. "
        "The blog post should be five paragraphs in total.",
        1000,
    ),
]


def run_flow(
    payload: Dict[str, Any],
    runtime: ChainRuntime,
    replies: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    novel = payload.get("novel") or payload.get("book") or "Pride and Prejudice by Jane Austen"

    outputs = []
    for step_id, template, max_tokens in STEP_DEFS:
        prompt = template.format(novel=novel)
        outputs.append(
            runtime.model_turn(
                prompt,
                step_id=step_id,
                max_tokens=max_tokens,
                temperature=1.0,
            )
        )

    return {
        "final_answer": outputs[-1]["response"],
        "title": f"{novel} - A Literature Review",
    }


if __name__ == "__main__":
    # 本地自测：python -m demo.blog_post.flow
    from demo._runner import run_flow_session

    session = run_flow_session(run_flow, {"novel": "Pride and Prejudice by Jane Austen"})
    if session["status"] == "ok":
        print("标题:", session["result"]["title"])
        print("正文:\n", session["result"]["final_answer"])
        print(f"链上节点数: {len(session['logs'])}")
    else:
        print("执行失败:", session.get("message"))
