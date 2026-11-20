# -*- coding: utf-8 -*-
"""
博客长文生成（Blog post chain）· 顺序链示例
============================================
本地交互入口：把一本书拆成五个递进的写作任务，
前一节点的输出累积为后一节点的对话上下文，最终合成一篇结构完整的书评博客。
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from demo.blog_post.flow import run_flow  # noqa: E402
from frontend._ui import chain_page  # noqa: E402

st.set_page_config(page_title="博客长文生成 · 顺序链", layout="wide")

chain_page(
    run_flow=run_flow,
    title="博客长文生成（Blog post chain）",
    intro=(
        "顺序链（Sequential Chaining）：对一部作品生成一篇结构完整的书评博客。"
        "五个子任务依次执行 —— 摘要 → 情节 → 主题 → 文风 → 成文，"
        "前一步的输出自动作为后一步的对话上下文（由运行时累积历史保证），"
        "最终把各段内容合并为五段式博客文章。"
    ),
    fields=[
        ("novel", "要评论的作品（novel）", "Pride and Prejudice by Jane Austen", False),
    ],
    session_key="frontend.blog_post",
)
