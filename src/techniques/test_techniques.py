# -*- coding: utf-8 -*-
"""
techniques 回归校验
===================
以子进程方式逐个运行九个技术示例（强制离线：去掉 MAAS_API_KEY），断言退出码为 0，
并按输出中的「模型调用次数」断言离线模式的确定性调用次数。

用法：
  python -m techniques.test_techniques     # 直接运行（无需 pytest）
  pytest src/techniques/test_techniques.py # 或由 pytest 收集

每个示例的离线次数即 README 表中的期望值：1/2/4/3/4/4/2/2/2。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent

# 模块名 -> 期望在输出中出现的“模型调用次数”片段（human_input 自断言退出码即可）
EXPECTED_COUNTS = {
    "model_invocation": "模型调用次数: 1",
    "prompt_templating": "模型调用次数: 2",
    "sequential": "模型调用次数: 4",
    "parallel": "模型调用次数: 3",
    "conditional": "模型调用次数: 4",
    "map_chain": "模型调用次数: 4",
    "validation": "模型调用次数: 2",
    "service_invocation": "模型调用次数: 2",
    "human_input": "续跑后总模型调用次数: 2",
}


def _clean_env() -> dict:
    env = dict(os.environ)
    # 强制离线：真实凭据会走 MaaS，导致次数与确定性断言不适用
    for key in ("MAAS_API_KEY", "MAAS_MODEL", "MAAS_CHAT_BASE_URL", "MAAS_EMBED_BASE_URL"):
        env.pop(key, None)
    return env


def _run_one(module_name: str, expected_fragment: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", f"techniques.{module_name}"],
        cwd=str(_SRC),
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"techniques.{module_name} 运行失败 rc={proc.returncode}\n{output}"
    )
    assert expected_fragment in output, (
        f"techniques.{module_name} 模型调用次数不符，期望包含 {expected_fragment!r}\n{output}"
    )


def _run_all() -> None:
    for module_name, fragment in EXPECTED_COUNTS.items():
        _run_one(module_name, fragment)
        print(f"PASS techniques.{module_name}")


def test_techniques_run_offline() -> None:
    _run_all()


if __name__ == "__main__":
    _run_all()
    print("ALL_TECHNIQUES_OK")
