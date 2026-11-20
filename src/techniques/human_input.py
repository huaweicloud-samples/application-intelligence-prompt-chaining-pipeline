# -*- coding: utf-8 -*-
"""
技术示例 9/9 —— 人工确认（Human in the Loop）
============================================
流程运行到需要人拍板的节点时抛 HumanInputRequired（挂起信号），把「已执行
节点回放缓存 + 业务中间态」带给调用方；调用方收集答复后携带 transcript /
partial_state 重新执行，运行时会**原样重放**已完成的节点（不重复调用模型），
只从答复之后继续 —— 等同于一次显式的「继续执行」。

运行：
  python -m techniques.human_input
"""
from __future__ import annotations

from typing import Any, Dict

from techniques._util import ensure_src_path, make_runtime, model_calls

ensure_src_path()

from chaining.runtime import ChainRuntime, HumanInputItem, HumanInputRequired  # noqa: E402
from demo._runner import run_flow_session  # noqa: E402

OFFLINE_RULES = [
    ("headline for the post", "（占位）「从零上手云原生」——这是草拟的标题。"),
    ("Write the full blog post", "（占位）这是用户确认后生成的完整博文正文。"),
]


def run_flow(
    payload: Dict[str, Any],
    runtime: ChainRuntime,
    replies: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    replies = replies or {}
    topic = (payload.get("topic") or "cloud-native").strip()

    # 用户已确认 -> 直接进入终稿（只有这一步会新调用模型）
    if replies.get("approved") == "yes":
        draft = (payload.get("draft") or "").strip()
        out = runtime.model_turn(
            "Write the full blog post based on the approved headline below.\n"
            f"<headline>\n{draft}\n</headline>",
            step_id="hi.final",
            conversation=[],
            max_tokens=400,
        )
        return {"topic": topic, "draft": draft, "final_answer": out["response"]}

    # 第一次执行：先草拟标题，再向用户确认
    out = runtime.model_turn(
        f"Write a headline for the post about {topic}.",
        step_id="hi.draft",
        max_tokens=60,
    )
    draft = out["response"]
    raise HumanInputRequired(
        [
            HumanInputItem(
                "是否用这条标题继续撰写全文？",
                placeholder="yes / no",
                hint="回复 yes：基于该标题生成全文；回复 no：重新草拟（此处仅演示 yes 续跑）。",
            ),
            HumanInputItem(f"草拟标题：\n{draft}", placeholder="", hint=""),
        ],
        reply_keys=["approved"],
        transcript=runtime.logs,
        partial_state={"draft": draft},
    )


def main() -> None:
    runtime = make_runtime(OFFLINE_RULES)
    payload = {"topic": "cloud-native"}

    # 1) 首次执行：命中人工确认点，模型只被调用 1 次
    first = run_flow_session(run_flow, payload, adapter=runtime.adapter)
    print("首次执行状态:", first["status"])
    print(f"  模型调用次数: {len(runtime.adapter.calls)}")
    assert first["status"] == "awaiting_human_input"

    # 2) 用户答复 yes 后续跑：草稿节点被重放，只新增终稿 1 次调用
    second = run_flow_session(
        run_flow,
        payload,
        replies={"approved": "yes"},
        transcript=first["transcript"],
        partial_state=first["partial_state"],
        adapter=runtime.adapter,
    )
    print("续跑状态:", second["status"])
    print(f"  续跑后总模型调用次数: {len(runtime.adapter.calls)}（仅新增 1 次，草稿按缓存重放）")
    print("终稿:", second["result"]["final_answer"])


if __name__ == "__main__":
    main()
