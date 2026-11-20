# -*- coding: utf-8 -*-
"""
热门仓库速览（Most popular repo）· 工具型 Agent 示例
====================================================
本地交互入口：无入参。模型先声明需要调用外部工具（获取今日热门 GitHub 仓库、
读取仓库 README），由执行器逐项执行并把结果回填为 tool 消息，
如此往复直到模型给出最终文字回答 —— 即 ReAct 风格的工具循环（Agent loop）。
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from demo.most_popular_repo.flow import run_flow  # noqa: E402
from frontend._ui import chain_page  # noqa: E402

st.set_page_config(page_title="热门仓库速览 · 工具型 Agent", layout="wide")

chain_page(
    run_flow=run_flow,
    title="热门仓库速览（Most popular repo）",
    intro=(
        "工具型 Agent（ReAct loop）：演示模型如何通过「工具声明 → 工具调用 → "
        "结果回填 → 再作答」的循环完成单靠文本无法完成的任务。"
        "本流程无需入参，将自动完成：查找当日热门 GitHub 仓库 → 读取其 README → "
        "生成一段 100–200 词的仓库简介。注意：该流程需要可访问公网。"
    ),
    fields=[],
    session_key="frontend.most_popular_repo",
)
