# -*- coding: utf-8 -*-
"""
techniques 示例的公共小工具
==========================
* ensure_src_path：以脚本方式运行（python techniques/xx.py）时把 src 根目录加入
  sys.path，保证 import chaining / adapter 可解析；以模块方式运行时为空操作。
* make_runtime：设置了 MAAS_API_KEY 时走真实模型；否则注入脚本化适配器，
  让示例在离线环境也能确定性跑通（输出为占位回复，仅演示编排语义）。
* model_calls：返回脚本化适配器已发生的模型调用次数（真实模型时无意义）。
"""
from __future__ import annotations

import os
import sys
from typing import Optional, Sequence

_RULES = Sequence  # 避免未使用告警


def ensure_src_path() -> None:
    if __package__ in (None, ""):
        _src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _src not in sys.path:
            sys.path.insert(0, _src)


def make_runtime(rules: Optional[list] = None):
    from chaining.runtime import ChainRuntime

    if os.environ.get("MAAS_API_KEY"):
        # 真实模型：需要 MAAS_API_KEY / MAAS_MODEL 环境变量
        return ChainRuntime()
    from chaining.testing import ScriptedAdapter

    return ChainRuntime(adapter=ScriptedAdapter(rules or []))


def model_calls(runtime) -> int:
    adapter = getattr(runtime, "adapter", None)
    if adapter is not None and hasattr(adapter, "calls"):
        return len(adapter.calls)
    return 0
