"""
模型适配层（Model Adapter）
==========================

统一的模型调用入口。本仓库所有「需要调用大模型」的代码只允许通过本模块访问模型服务，
不要在业务函数里直接构造模型请求。

实现基于 ModelArts Studio（MaaS）预置模型服务提供的 OpenAI 兼容端点：

  * 对话（chat）：POST {MAAS_CHAT_BASE_URL}/chat/completions
      base_url 示例：https://api.modelarts-maas.com/v2
  * 向量化（embedding）：POST {MAAS_EMBED_BASE_URL}/embeddings
      base_url 示例：https://api.modelarts-maas.com/v1

鉴权：
  API Key 从环境变量 MAAS_API_KEY 注入（由部署侧通过 CSMS 解密后注入，见部署指导书）。
  模型名从环境变量 MAAS_MODEL 注入，可在部署时替换为账号下已开通的任一文本对话模型。

设计说明
--------
1. 消息内容兼容两种写法：
   - 纯文本：{"role": "user", "content": "你好"}
   - 内容块：{"role": "user", "content": [{"type": "text", "text": "你好"}]}
   本模块在发送前统一收敛为 OpenAI 兼容字符串形式。
2. 对话历史是角色交替的 message 列表（user / assistant），需要携带历史时由调用方
   传入 messages，本模块不做状态管理（状态管理在 chaining 运行时里做）。
3. 模型名不做任何映射，直接透传 MAAS_MODEL / 调用方显式指定的 model —— 模型选择权
   交给部署配置，避免在代码里写死某个模型名。
4. 请求内置指数退避重试，用于吸收服务端限流/瞬断。

依赖：openai（建议 1.30.x，并钉 httpx==0.27.2）
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 环境变量名（常量集中在此，便于部署配置核对）
# ---------------------------------------------------------------------------
ENV_API_KEY = "MAAS_API_KEY"
ENV_MODEL = "MAAS_MODEL"
ENV_CHAT_BASE_URL = "MAAS_CHAT_BASE_URL"
ENV_EMBED_BASE_URL = "MAAS_EMBED_BASE_URL"

DEFAULT_CHAT_BASE_URL = "https://api.modelarts-maas.com/v2"
DEFAULT_EMBED_BASE_URL = "https://api.modelarts-maas.com/v1"


# ---------------------------------------------------------------------------
# 返回数据结构
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    """模型请求调用某个工具时返回的信息。"""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ChatResult:
    """一次对话调用的结构化结果。"""
    text: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None      # stop / length / tool_calls / ...
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# 消息构造辅助
# ---------------------------------------------------------------------------

def text_message(role: str, text: str) -> Dict[str, Any]:
    """构造文本消息：{"role": ..., "content": [{"type": "text", "text": ...}]}"""
    return {"role": role, "content": [{"type": "text", "text": text}]}


def tool_result_message(tool_call_id: str, content: str) -> Dict[str, Any]:
    """构造工具执行结果消息（对应对话历史中 role=tool 的消息）。"""
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def tool_definition(name: str, description: str, input_schema: Dict[str, Any]) -> Dict[str, Any]:
    """构造 OpenAI 兼容的 function 工具声明。"""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": input_schema,
        },
    }


def _normalize_content(content: Any) -> str:
    """
    把 content 收敛为字符串。
    - 字符串直接返回；
    - 内容块数组则拼接所有 text 块（含 toolUse 等结构时返回其 JSON 表示，便于调试）。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(str(block))
                continue
            if "text" in block:
                parts.append(str(block["text"]))
            elif "image_url" in block:
                # 对话模型为纯文本模型；保留该分支仅为兼容，真实部署请勿传图片。
                parts.append("[image]")
            else:
                import json
                parts.append(json.dumps(block, ensure_ascii=False, default=str))
        return "\n".join(p for p in parts if p)
    return str(content)


# ---------------------------------------------------------------------------
# 适配器
# ---------------------------------------------------------------------------

class ModelAdapter:
    """
    MaaS OpenAI 兼容端点的适配器。
    用法：adapter.chat(messages=[...], temperature=0.7) 或 adapter.complete(prompt)。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        chat_base_url: Optional[str] = None,
        embed_base_url: Optional[str] = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key or os.environ.get(ENV_API_KEY, "")
        self.default_model = default_model or os.environ.get(ENV_MODEL, "") or None
        self.chat_base_url = chat_base_url or os.environ.get(ENV_CHAT_BASE_URL, DEFAULT_CHAT_BASE_URL)
        self.embed_base_url = embed_base_url or os.environ.get(ENV_EMBED_BASE_URL, DEFAULT_EMBED_BASE_URL)
        self.timeout = timeout
        self.max_retries = max_retries

        if not self.api_key:
            raise RuntimeError(
                f"缺少 API Key：请设置环境变量 {ENV_API_KEY}（由部署侧注入）。"
            )
        if not self.default_model:
            raise RuntimeError(
                f"缺少默认模型名：请设置环境变量 {ENV_MODEL}（如 DeepSeek-V3.2）。"
            )

        # 延迟导入，避免在无依赖环境（如仅做语法检查/离线打包）下 import 失败。
        from openai import OpenAI
        self._chat_client = OpenAI(
            api_key=self.api_key, base_url=self.chat_base_url, timeout=self.timeout
        )
        self._embed_client = OpenAI(
            api_key=self.api_key, base_url=self.embed_base_url, timeout=self.timeout
        )

    # ------------------------------------------------------------------
    # 对外 API
    # ------------------------------------------------------------------

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
        """一次性文本生成，返回纯文本。"""
        messages: List[Dict[str, Any]] = []
        if system:
            messages.append(text_message("system", system))
        messages.append(text_message("user", prompt))
        result = self.chat(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        return result.text

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
        """
        对话补全。
        messages 是 OpenAI 兼容消息列表；工具调用由 tools + tool_choice 触发。
        """
        if not messages:
            raise ValueError("messages 不能为空")

        normalized = []
        for msg in messages:
            # role=tool 的消息与携带 tool_calls 的 assistant 消息保持原样：
            # 其 content 可能为 None（协议要求），不能转成空字符串。
            if msg.get("role") == "tool" or "tool_calls" in msg:
                normalized.append(msg)
                continue
            normalized.append(
                {**msg, "content": _normalize_content(msg.get("content", ""))}
            )

        payload: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": normalized,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if top_p is not None:
            payload["top_p"] = top_p
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = self._chat_client.chat.completions.create(**payload)
                return self._to_chat_result(response)
            except Exception as exc:  # noqa: BLE001 - 网络/限流/服务错误统一重试
                last_error = exc
                logger.warning("模型调用失败（第 %s 次）：%s", attempt + 1, exc)
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避：1s, 2s, ...
        raise RuntimeError(f"模型调用多次重试后仍失败: {last_error}")

    def embed(self, texts: List[str], *, model: Optional[str] = None) -> List[List[float]]:
        """文本向量化。传入文本列表，返回向量列表。"""
        if not texts:
            return []
        response = self._embed_client.embeddings.create(
            model=model or self.default_model,
            input=texts,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _to_chat_result(self, response: Any) -> ChatResult:
        choice = response.choices[0]
        message = choice.message

        text = _normalize_content(message.content) if message.content else ""

        tool_calls: List[ToolCall] = []
        for tc in (message.tool_calls or []):
            try:
                import json
                args = json.loads(tc.function.arguments or "{}")
            except Exception:  # noqa: BLE001 - 容错：参数解析失败时保留原始字符串
                args = {"raw": tc.function.arguments}
            tool_calls.append(
                ToolCall(id=tc.id, name=tc.function.name, arguments=args)
            )

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0

        return ChatResult(
            text=text,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------

def create_adapter(**kwargs: Any) -> ModelAdapter:
    """
    创建默认适配器。参数覆盖环境变量；环境变量未配置时抛出明确错误。
    进程内应只创建一次并复用（连接复用），业务代码请使用模块级单例。
    """
    return ModelAdapter(**kwargs)


# 模块级单例（懒加载）：业务代码通过 get_adapter() 获取。
_adapter_instance: Optional[ModelAdapter] = None


def get_adapter() -> ModelAdapter:
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = ModelAdapter()
    return _adapter_instance


# ---------------------------------------------------------------------------
# 本地自测：python model_adapter.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    adapter = ModelAdapter()
    result = adapter.chat(
        messages=[text_message("user", "用一句话介绍华为云。")],
        max_tokens=100,
        temperature=0.7,
    )
    print("回复:", result.text)
    print("用量:", result.input_tokens, result.output_tokens)
