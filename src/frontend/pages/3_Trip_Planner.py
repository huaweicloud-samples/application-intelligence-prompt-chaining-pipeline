# -*- coding: utf-8 -*-
"""
行程规划（Trip planner chain）· 并行扇出示例
=============================================
本地交互入口：对同一目的地并行征求三个独立维度的专家建议
（住宿 / 餐饮 / 景点），再把三份建议作为内联上下文合成一份三日行程。
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from demo.trip_planner.flow import run_flow  # noqa: E402
from frontend._ui import chain_page  # noqa: E402

st.set_page_config(page_title="行程规划 · 并行扇出", layout="wide")

chain_page(
    run_flow=run_flow,
    title="行程规划（Trip planner chain）",
    intro=(
        "并行扇出（Parallel fan-out）：三个互不依赖的专家建议分支同时运行 —— "
        "住宿、餐饮、景点 —— 分支各自独立（不共享对话历史）。"
        "全部完成后由汇合节点把三份建议内联进提示词，生成一份三日行程，"
        "并附带可直接「打印为 PDF」的 HTML 版本。"
    ),
    fields=[
        ("location", "目的地（location）", "Paris, France", False),
    ],
    session_key="frontend.trip_planner",
)
