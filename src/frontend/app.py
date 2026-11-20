# -*- coding: utf-8 -*-
"""
提示词链本地交互台（Streamlit 首页）
====================================
在左侧页面导航中选择一个 demo，即可在本地浏览器里以「表单 → 运行 → 结果/日志」
的方式体验提示词链（Prompt Chaining）的常见编排形态。

模型后端使用 MaaS（ModelArts Studio）预置模型服务提供的 OpenAI 兼容端点，
运行前需通过环境变量传递访问凭据（由部署侧负责下发）：
    MAAS_API_KEY       API Key
    MAAS_MODEL         模型名
未配置凭据时点击运行会给出明确错误；若只想离线演示编排语义，
请改用 src/techniques（不需要任何云上资源）。
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="提示词链本地交互台", layout="wide")

st.title("提示词链（Prompt Chaining）本地交互台")

st.markdown(
    """
    这套示例把常用提示词链编排原语用普通 Python 表达：顺序链、并行扇出、Map、
    条件分支、循环辩论、人工确认点与工具型 Agent。每个 demo 的流程都写在
    `src/demo/<name>/flow.py`，是可读、可单测、可回放的代码 ——
    不依赖任何图形化状态机文件。

    **运行前置**：需要可访问 MaaS 端点，并注入模型访问凭据
    （`MAAS_API_KEY` / `MAAS_MODEL`）。本机无凭据时，流程会以明确报错提示；
    纯编排语义演示请使用 `src/techniques`（离线可跑，无需网络与账号）。
    """
)

st.subheader("Demo 一览")

st.markdown(
    """
| 页面 | 编排形态 | 入参 | 说明 |
|---|---|---|---|
| 1 博客长文 | 顺序链 | 一部作品 | 摘要→情节→主题→文风→成文，五步合成一篇书评博客 |
| 2 故事创作 | Map 并发 + JSON 校验 | 故事描述 | 角色设计（严格 JSON）→逐角色故事线→合并→完整故事 |
| 3 行程规划 | 并行扇出 + 汇合 | 目的地 | 住宿/餐饮/景点三路专家并行，合成三日行程（附打印版 HTML） |
| 4 电影提案 | 人工确认点 | 一句话故事前提 | 三档温度并行提案→仲裁→真人制片人开绿灯/否决 |
| 5 美食规划 | 多智能体辩论循环 | 手头食材 | 两位厨师出菜→打分→辩论→裁判，直至一致并输出菜谱 |
| 6 热门仓库速览 | 工具型 Agent（ReAct） | 无 | 模型声明工具→执行器回填→再作答，输出仓库简介 |
"""
)

st.markdown(
    """
    ---
    **启动方式**

    ```bash
    cd src
    pip install -r frontend/requirements.txt
    export MAAS_API_KEY=... MAAS_MODEL=...   # 也可在页面内临时设置
    streamlit run frontend/app.py
    ```

    左侧导航进入各 demo 页面。运行结果页会同时展示：最终回答、结构化产物
    （若流程产生）与整条链的节点日志（每次模型调用的 step_id、温度、Token 用量）。
    """
)
