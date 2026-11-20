"""
离线脚本化模型适配器（仅本地演示 / 自测用）
==========================================
生产路径永远使用 adapter/model_adapter.py 的 ModelAdapter（MaaS 端点）；
本模块只在「没有 API Key 也想跑通一条链」的场景使用 —— techniques/* 的
`__main__` 自测、以及单元测试都会注入本适配器。

行为：
  * chat() 返回由「规则表」决定的确定性回复，不发起任何网络请求；
  * 规则表 = [(匹配子串, 回复), ...]；回复可以是字符串或 callable(全文)->str；
    命中多条时取「匹配子串最长」的一条，保证确定性；
  * 工具轮：当调用方传入 tools 且消息里还没有 role=tool 的结果时，返回对
    第一个工具的工具调用；一旦消息里已存在工具结果，返回最终文本；
  * 每次调用都会写入 self.calls，供断言「模型被调了几次」。

典型用法：
    from chaining.testing import ScriptedAdapter
    rules = [("summary", "这是摘要"), ("plot", "这是情节")]
    rt = ChainRuntime(adapter=ScriptedAdapter(rules))
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from adapter.model_adapter import ChatResult, ToolCall

Rule = Tuple[str, Any]  # (匹配子串, 字符串或 callable(全文) -> str)


def _flatten(messages: Sequence[Dict[str, Any]]) -> str:
    """把消息列表拍平成一段文本（用于规则匹配与回显）。"""
    parts: List[str] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            text = " ".join(
                str(block.get("text", ""))
                for block in content
                if isinstance(block, dict) and block.get("text")
            )
        elif isinstance(content, str):
            text = content
        elif content is None:
            text = ""
        else:
            text = str(content)
        role = msg.get("role", "?")
        if role == "tool":
            text = f"[tool result] {text}"
        parts.append(text)
    return "\n".join(parts)


def _last_message_text(messages: Sequence[Dict[str, Any]]) -> str:
    """取最后一条消息的文本（规则匹配基准，避免历史累积干扰）。"""
    if not messages:
        return ""
    msg = messages[-1]
    content = msg.get("content")
    if isinstance(content, list):
        return " ".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("text")
        )
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    return str(content)


class ScriptedAdapter:
    """确定性假模型：按规则表返回文本；带工具时模拟「先调工具、后作答」。"""

    def __init__(
        self,
        rules: Optional[Sequence[Rule]] = None,
        *,
        fallback: Optional[str] = None,
    ) -> None:
        self.rules: List[Rule] = list(rules or [])
        self.fallback = fallback or "（离线模型占位回复）"
        self.calls: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # ModelAdapter 兼容接口
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        max_tokens: int = 250,
        temperature: float = 1.0,
        top_p: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> ChatResult:
        full_text = _flatten(messages)
        last_text = _last_message_text(messages)
        self.calls.append(
            {
                "text": full_text,
                "temperature": temperature,
                "tools": bool(tools),
                "max_tokens": max_tokens,
            }
        )

        # 工具轮：还没有工具结果 -> 请求调用第一个工具；已有结果 -> 直接作答
        if tools:
            has_tool_result = any(msg.get("role") == "tool" for msg in messages)
            if not has_tool_result:
                return self._propose_tool(tools, full_text)

        reply = self._resolve(last_text, full_text)
        return ChatResult(text=reply, finish_reason="stop")

    def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 250,
        temperature: float = 1.0,
        top_p: Optional[float] = None,
    ) -> str:
        messages: List[Dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(
            messages=messages, max_tokens=max_tokens, temperature=temperature
        ).text

    def embed(self, texts: List[str], *, model: Optional[str] = None) -> List[List[float]]:
        return [[0.0] * 8 for _ in texts]

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _resolve(self, last_text: str, full_text: str) -> str:
        search = (last_text or full_text).lower()
        best_value: Any = None
        best_len = -1
        for pattern, value in self.rules:
            # dict 值只用于工具参数声明，不作为文本回复
            if isinstance(value, dict) or not pattern:
                continue
            if pattern.lower() in search and len(pattern) > best_len:
                best_value = value
                best_len = len(pattern)
        if best_value is None:
            return self.fallback
        if callable(best_value):
            return str(best_value(full_text))
        return str(best_value)

    def _propose_tool(self, tools: Sequence[Dict[str, Any]], text: str) -> ChatResult:
        first = tools[0]
        function = first.get("function", first)
        name = function.get("name", "unknown_tool")
        arguments: Dict[str, Any] = {"input": ""}
        # 允许规则显式指定参数（匹配子串 -> {"input": "..."}）
        lowered = text.lower()
        for pattern, value in self.rules:
            if callable(value) or not isinstance(value, dict):
                continue
            if pattern and pattern.lower() in lowered and "input" in value:
                arguments = dict(value)
                break
        return ChatResult(
            text="",
            tool_calls=[
                ToolCall(
                    id=f"call_{len(self.calls)}",
                    name=name,
                    arguments=arguments,
                )
            ],
            finish_reason="tool_calls",
        )


# ---------------------------------------------------------------------------
# 便捷入口：直接跑「默认离线演示运行时」
# ---------------------------------------------------------------------------

def offline_runtime(rules: Optional[Sequence[Rule]] = None) -> Any:
    """构造注入脚本化适配器的 ChainRuntime（惰性导入避免循环依赖）。"""
    from chaining.runtime import ChainRuntime

    return ChainRuntime(adapter=ScriptedAdapter(rules))


if __name__ == "__main__":
    rt = offline_runtime([("你好", "你好！我是离线演示模型。")])
    out = rt.model_turn("你好", step_id="demo.greet")
    print(out["response"])
