# -*- coding: utf-8 -*-
"""
电影提案（Movie pitch chain）· 人工确认示例
============================================
本地交互入口：三位编剧（三个温度档）并行写提案 → 制片人仲裁选出一份胜出提案 →
进入人工确认点（Human-in-the-loop）：你扮演真人制片人，
「开绿灯」则把胜出提案扩写为一页纸 pitch，「否决」则触发新一轮重新提案
（新一轮会看到上一轮被否决的旧提案，要求给出全新 idea）。
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from demo.movie_pitch.flow import run_flow  # noqa: E402
from frontend._ui import chain_page  # noqa: E402

st.set_page_config(page_title="电影提案 · 人工确认", layout="wide")

chain_page(
    run_flow=run_flow,
    title="电影提案（Movie pitch chain）",
    intro=(
        "人工确认点（Human-in-the-loop）：三位编剧（Blue / Green / Red 三个温度档）"
        "并行给出提案 → 制片人仲裁挑出胜出者 → 等待真人制片人拍板。"
        "回放缓存保证：你答复后只有新增节点真正调用模型，既在结果不变的前提下"
        "不会重复调用或产生随机差异。"
    ),
    fields=[
        ("movie_description", "一句话电影故事前提（movie_description）", "Cowboys in space", False),
    ],
    session_key="frontend.movie_pitch",
)
