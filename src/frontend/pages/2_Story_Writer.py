# -*- coding: utf-8 -*-
"""
故事创作（Story writer chain）· Map 示例
=========================================
本地交互入口：先让模型做角色设计（约束为 JSON 输出并通过 Schema 校验/修复），
再对每个角色并发推演个人故事线（Map），最后把所有支线合并成完整上下文，
生成一个完整故事。
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from demo.story_writer.flow import run_flow  # noqa: E402
from frontend._ui import chain_page  # noqa: E402

st.set_page_config(page_title="故事创作 · Map", layout="wide")

chain_page(
    run_flow=run_flow,
    title="故事创作（Story writer chain）",
    intro=(
        "Map / 并发子任务：按「角色设计 → 逐角色故事线（并发 Map）→ 合并上下文 → "
        "生成完整故事」组织。角色设计节点要求严格 JSON 输出，"
        "命中 JSON Schema 校验失败时自动进入修复循环（validation 技巧）。"
    ),
    fields=[
        ("story_description", "故事描述或题材（story_description）", "The wild west", False),
    ],
    session_key="frontend.story_writer",
)
