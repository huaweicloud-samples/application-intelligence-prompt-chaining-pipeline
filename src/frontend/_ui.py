# -*- coding: utf-8 -*-
"""
本地交互前端（Streamlit）公共组件
=================================
每个 demo 页共享同一套「运行 / 人工确认 / 结果展示」交互逻辑，页面文件只需
声明入参并传入对应的 run_flow。

运行方式：
  cd src
  streamlit run frontend/app.py
需要先注入模型访问凭据（由部署侧提供）：
  export MAAS_API_KEY=... MAAS_MODEL=...
未配置时页面会给出明确错误提示；纯编排语义演示请用 techniques/*（离线可跑）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# 允许从仓库任意目录启动 streamlit 也能 import demo / chaining / adapter
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from demo._runner import run_flow_session  # noqa: E402

# 字段：每个元素 (key, 标签, 默认值, 是否多行)
Field = Tuple[str, str, str, bool]


def chain_page(
    *,
    run_flow: Callable,
    title: str,
    intro: str,
    fields: List[Field],
    session_key: str,
) -> None:
    """
    渲染一个 demo 页面：入参表单 -> 运行 -> （如有）人工确认 -> 结果/日志。
    人工确认与续跑状态存放在 st.session_state，可跨页面重跑保持。
    """
    st.title(title)
    st.caption(intro)
    _maybe_warn_env()

    state = st.session_state.setdefault(session_key, {"phase": "idle"})

    if state["phase"] == "idle":
        payload = _render_payload_form(fields, session_key)
        if st.button("运行这条链", type="primary", key=f"{session_key}.run"):
            with st.spinner("链执行中…"):
                session = run_flow_session(run_flow, payload)
            _absorb(state, session, session_key, payload=payload)
            st.rerun()
        if not fields:
            st.caption("本流程无需入参，点击上方按钮即可运行。")

    elif state["phase"] == "awaiting_human_input":
        _render_human_input(state, session_key)
    elif state["phase"] == "ok":
        _render_ok(state, session_key)
    elif state["phase"] == "error":
        st.error(state["message"])
        if state.get("logs"):
            st.code(state["logs"], language="json")
        _reset_button(session_key)


def _render_payload_form(fields: List[Field], session_key: str) -> Dict[str, Any]:
    if fields:
        st.subheader("入参")
    payload: Dict[str, Any] = {}
    for key, label, default, multiline in fields:
        if multiline:
            payload[key] = st.text_area(label, value=default, key=f"{session_key}.f.{key}")
        else:
            payload[key] = st.text_input(label, value=default, key=f"{session_key}.f.{key}")
    return {k: v for k, v in payload.items() if str(v).strip() != ""}


def _render_human_input(state: Dict[str, Any], session_key: str) -> None:
    st.subheader("需要人工确认")
    for item in state["questions"]:
        st.markdown(f"- **{item.get('question', '')}**")
        if item.get("hint"):
            st.caption(item["hint"])
        if item.get("placeholder"):
            st.caption(f"占位提示：`{item['placeholder']}`")

    # 收集答复（当前所有确认点的答复都是 yes / no 二选一）
    replies: Dict[str, Any] = {}
    for key in state["reply_keys"]:
        replies[key] = st.radio(
            f"答复（{key}）", options=["yes", "no"], index=0,
            horizontal=True, key=f"{session_key}.reply.{key}",
        )

    if st.button("提交答复并继续", type="primary", key=f"{session_key}.resume"):
        with st.spinner("从人工答复处继续执行…"):
            session = run_flow_session(
                state["flow_run"],
                state["payload"],
                replies=replies,
                transcript=state["transcript"],
                partial_state=state["partial_state"],
            )
        _absorb(state, session, session_key)
        st.rerun()

    if st.button("放弃本次执行", key=f"{session_key}.abort"):
        st.session_state[session_key] = {"phase": "idle"}
        st.rerun()


def _render_ok(state: Dict[str, Any], session_key: str) -> None:
    st.subheader("运行结果")
    result = state["result"]
    final_answer = result.get("final_answer") or result.get("summary") or result
    if isinstance(final_answer, str):
        st.markdown(final_answer)
    else:
        st.json(final_answer)

    extra = {k: v for k, v in result.items() if k not in ("final_answer", "summary")}
    if extra:
        st.subheader("结构化产物")
        st.json(extra, expanded=False)

    with st.expander("查看链节点日志"):
        st.json(state["logs"], expanded=False)
    _reset_button(session_key)


def _reset_button(session_key: str) -> None:
    if st.button("重新运行", key=f"{session_key}.again"):
        st.session_state[session_key] = {"phase": "idle"}
        st.rerun()


def _absorb(
    state: Dict[str, Any],
    session: Dict[str, Any],
    session_key: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """把一次会话结果写回页面状态机。payload 显式传入以便续跑时原样恢复入参。"""
    st.session_state[session_key] = {
        "phase": session["status"],
        "payload": dict(payload if payload is not None else state.get("payload", {})),
        "flow_run": state.get("flow_run"),
    }
    merged = st.session_state[session_key]
    if session["status"] == "awaiting_human_input":
        merged.update(
            {
                "questions": session["questions"],
                "reply_keys": session["reply_keys"],
                "transcript": session["transcript"],
                "partial_state": session["partial_state"],
            }
        )
    elif session["status"] == "ok":
        merged.update({"result": session["result"], "logs": session["logs"]})
    else:
        merged.update({"message": session.get("message", "未知错误"), "logs": session.get("logs")})


def _maybe_warn_env() -> None:
    if not os.environ.get("MAAS_API_KEY"):
        st.warning(
            "尚未配置模型访问凭据（环境变量 MAAS_API_KEY / MAAS_MODEL）。"
            "点击运行后会提示缺少 API Key。编排语义演示请改用离线 techniques。"
        )
