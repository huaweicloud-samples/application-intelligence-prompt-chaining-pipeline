# -*- coding: utf-8 -*-
"""
美食规划（Meal planner chain）· 多智能体辩论示例
=================================================
本地交互入口：两位「厨师」智能体基于同一份手头食材并行出菜 →
自动打分 → 辩论改进 → 一致性裁判判断是否达成一致；
未达成一致则进入下一轮辩论（带轮次上限），最终由裁判选出胜者并生成完整菜谱。
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from demo.meal_planner.flow import run_flow  # noqa: E402
from frontend._ui import chain_page  # noqa: E402

st.set_page_config(page_title="美食规划 · 多智能体辩论", layout="wide")

chain_page(
    run_flow=run_flow,
    title="美食规划（Meal planner chain）",
    intro=(
        "多智能体辩论 / 循环（Debate loop）：两位厨师对同一食材清单分别给出方案，"
        "随后在「打分 → 参照对手与得分改进自己 → 一致性裁判」之间循环，"
        "直到双方达成一致或达到轮次上限；最终输出胜者的完整菜谱。"
        "请在下方输入手头食材（英文逗号分隔）。"
    ),
    fields=[
        ("ingredients", "手头食材（ingredients）", "Chicken, Rice", False),
    ],
    session_key="frontend.meal_planner",
)
