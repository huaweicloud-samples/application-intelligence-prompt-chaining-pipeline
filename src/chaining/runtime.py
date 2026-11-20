"""
代码编排运行时（Chaining Runtime）
==================================

把「提示词链」（prompt chaining）的常用编排原语以 Python 代码形式提供。
每个 demo（src/demo/*）用普通 Python 控制流 + 本运行时的方法串联模型调用、
并行分支、循环、条件与人工确认点，形成一条可执行、可回放、可续跑的链。

为什么用代码编排
----------------
无状态、函数式的「链」结构在代码里最直观：顺序链 = 顺序调用，并行 = 线程池，
分支 = if/else，循环 = for，Map = 对列表逐项调用，人工确认点 = 挂起信号。
demo 目录下的每个流程都是可读的 Python 函数，不再需要单独的图形化状态机
定义文件 —— 状态与分支在代码中一目了然，且天然支持单元测试与本地运行。

运行形态
--------
1) 本地运行（默认）：runtime 直接使用 src/adapter 的 MaaS 适配器调用模型，
   适合教学与联调，不需要任何云上资源。
2) 服务化运行：把每个 demo 的入口包成函数（src/demo/<name>/handler.py），
   部署到函数计算服务（FunctionGraph），由事件触发整条链在服务端执行。

人工确认点（Human-in-the-loop）
------------------------------
MoviePitch / MealPlanner 等流程中存在「等待用户拍板」的节点。本运行时用
HumanInputRequired 信号表达挂起：
  * 链执行到确认点时，若无用户答复则抛出 HumanInputRequired，携带待确认
    清单与该时刻的运行回放缓存；
  * 调用方（页面）把问题展示给用户，收集答复后带着回放缓存 + 答复重新发起
    执行；
  * 重放缓存保证：已完成的模型调用结果原样重放（不再二次调用模型、不产生
    随机差异），只有新的人工答复之后的步骤才真正调用模型。

等同语义：可以把「回放缓存 + 答复」理解为一次显式的「继续执行」指令。
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Sequence

from adapter.model_adapter import (
    ChatResult,
    ModelAdapter,
    get_adapter,
    text_message,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 消息 / 历史工具
# ---------------------------------------------------------------------------


def as_content_blocks(text: str) -> List[Dict[str, Any]]:
    """把文本包装为内容块数组（消息正文统一走 OpenAI 兼容 wire 格式）。"""
    return [{"type": "text", "text": text}]


def append_user_turn(history: List[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
    history.append(text_message("user", text))
    return history


def append_assistant_turn(history: List[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
    history.append(text_message("assistant", text))
    return history


# ---------------------------------------------------------------------------
# 单步模型调用的产物
# ---------------------------------------------------------------------------

class TurnOutput:
    """一次模型调用（一个链上节点）的结构化产物。"""

    def __init__(
        self,
        step_id: str,
        prompt: str,
        response: str,
        temperature: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        self.step_id = step_id
        self.prompt = prompt
        self.response = response
        self.temperature = temperature
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "prompt": self.prompt,
            "response": self.response,
            "temperature": self.temperature,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


# ---------------------------------------------------------------------------
# 人工确认信号
# ---------------------------------------------------------------------------

class HumanInputItem:
    """一个等待用户确认的问题。"""

    def __init__(
        self,
        question: str,
        *,
        placeholder: str = "",
        hint: str = "",
    ) -> None:
        self.question = question
        self.placeholder = placeholder
        self.hint = hint

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "placeholder": self.placeholder,
            "hint": self.hint,
        }


class HumanInputRequired(Exception):
    """
    链需要人工输入才能继续。
    reply_keys：该信号等待的答复键（调用方在 replies 中给出）。
    """

    def __init__(
        self,
        items: Sequence[HumanInputItem],
        reply_keys: Sequence[str],
        *,
        transcript: Optional[List[Dict[str, Any]]] = None,
        partial_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__("需要人工输入以继续执行")
        self.items = list(items)
        self.reply_keys = list(reply_keys)
        self.transcript = list(transcript or [])
        self.partial_state = partial_state or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "awaiting_human_input",
            "questions": [it.to_dict() for it in self.items],
            "reply_keys": self.reply_keys,
            "transcript": self.transcript,
            "partial_state": self.partial_state,
        }


# ---------------------------------------------------------------------------
# 链运行时
# ---------------------------------------------------------------------------

class ChainRuntime:
    """
    链执行环境。
      * adapter: 模型适配器（默认进程级单例）
      * history: 跨节点的完整对话历史（用户/助手交替）
      * logs:    每个模型节点的产物日志（供页面展示「链」的中间结果）
      * replay:  回放缓存 {step_id: {"response": ..., "input_tokens":...,
                 "output_tokens":..., "temperature":...}}
    """

    def __init__(
        self,
        adapter: Optional[ModelAdapter] = None,
        *,
        max_workers: int = 4,
    ) -> None:
        self.adapter = adapter or get_adapter()
        self.max_workers = max_workers
        self.reset()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self.history: List[Dict[str, Any]] = []
        self.logs: List[Dict[str, Any]] = []
        self.replay: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def record_tool_results(
        self, step_id: str, results: Sequence[Dict[str, str]]
    ) -> None:
        """
        把工具执行结果关联到某个模型节点（用于回放续跑时原样恢复，
        避免断点续跑重复执行外部工具造成结果漂移）。
        results: [{"tool_call_id": ..., "result": ...}, ...]
        """
        with self._lock:
            for log in self.logs:
                if log.get("step_id") == step_id:
                    log["tool_results"] = list(results)
            cached = self.replay.get(step_id)
            if cached is not None:
                cached["tool_results"] = list(results)

    def restore_transcript(self, transcript: Sequence[Dict[str, Any]]) -> None:
        """
        载入先前执行的回放缓存（断点续跑）。
        transcript 形如 ChainRuntime.logs（to_dict 输出）。
        已存在的节点会在后续 model_turn 中原样重放，不重复调用模型。
        """
        self.replay = {}
        self.logs = []
        self.history = []
        for log in transcript:
            self.replay[log["step_id"]] = dict(log)
            self.logs.append(dict(log))
        self.history = _rebuild_history_from_logs(self.logs)

    # ------------------------------------------------------------------
    # 模型节点
    # ------------------------------------------------------------------

    def model_turn(
        self,
        prompt: str,
        *,
        step_id: str,
        conversation: Optional[List[Dict[str, Any]]] = None,
        include_conversation: bool = True,
        system: Optional[str] = None,
        max_tokens: int = 250,
        temperature: float = 1.0,
        top_p: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行一次模型调用并记录产物。

        参数：
          prompt              本轮用户提示词
          step_id             节点唯一 ID（断点续跑/回放缓存键，须在整条链内唯一）
          conversation        显式对话历史；缺省时使用运行时累积历史 self.history
          include_conversation 为 False 时不携带历史，只发送 prompt

        返回统一结构：
          {
            "step_id": ..., "prompt": ..., "response": ...,
            "conversation": [...],  # 本轮调用后累积得到的完整对话
            "temperature": ...,
            "tool_calls": [...],    # 命中工具时非空
            "finish_reason": ...,
          }

        累积语义：
          1) base = 显式 conversation；否则 = self.history（include_conversation=True 时）；
          2) prompt 非空时，追加一条 [user: prompt]；
          3) 模型回复 assistant: response；
          4) 新对话 = 发送的 messages + [assistant: response]，作为返回值 conversation。
          5) 使用缺省历史（conversation=None）时，self.history 同步更新为新对话，
             供后续节点继续累积。
        """
        uses_global_history = conversation is None
        if conversation is not None:
            base = list(conversation)
        elif include_conversation:
            base = list(self.history)
        else:
            base = []

        messages = list(base)
        if prompt:
            messages = append_user_turn(messages, prompt)

        replay_key = step_id
        cached = self.replay.get(replay_key)

        with self._lock:
            if cached is not None:
                logger.info("回放节点 %s（不重复调用模型）", step_id)
                response_text = cached["response"]
                temperature_used = float(cached.get("temperature", temperature))
                input_tokens = int(cached.get("input_tokens", 0))
                output_tokens = int(cached.get("output_tokens", 0))
                tool_calls = cached.get("tool_calls", [])
                finish_reason = cached.get("finish_reason", "stop")
            else:
                result = self.adapter.chat(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    tools=tools,
                    tool_choice=tool_choice,
                )
                response_text = result.text
                temperature_used = temperature
                input_tokens = result.input_tokens
                output_tokens = result.output_tokens
                tool_calls = [tc.__dict__ for tc in result.tool_calls]
                finish_reason = result.finish_reason or "stop"

            # 累积新对话：已发送消息 + 助手回复（工具调用轮不追加文本回复）
            if tool_calls:
                full_conversation = list(messages)
            else:
                full_conversation = list(messages)
                full_conversation = append_assistant_turn(full_conversation, response_text)

            if uses_global_history:
                self.history = list(full_conversation)

            output = {
                "step_id": step_id,
                "prompt": prompt,
                "response": response_text,
                "conversation": full_conversation,
                "temperature": temperature_used,
                "tool_calls": tool_calls,
                "finish_reason": finish_reason,
            }
            # 记录日志 / 缓存
            log = {
                "step_id": step_id,
                "prompt": prompt,
                "response": response_text,
                "temperature": temperature_used,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tool_calls": tool_calls,
                "finish_reason": finish_reason,
            }
            self.replay[replay_key] = log
            self.logs.append(log)
            return output

    # ------------------------------------------------------------------
    # 组合原语
    # ------------------------------------------------------------------

    def parallel(self, workers: Sequence[Callable[[], Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        并行执行一组零参函数（通常各自内部完成一次或多次 model_turn），
        返回按传入顺序排列的结果列表。每个 worker 内部自行写入 self.logs。
        注意：并行分支不得依赖彼此的中间产物（与并行分支语义一致）。
        """
        if len(workers) <= 1:
            return [w() for w in workers]
        results: List[Any] = [None] * len(workers)
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(workers))) as pool:
            futures = [pool.submit(w) for w in workers]
            for idx, fut in enumerate(futures):
                results[idx] = fut.result()
        return results

    def map_items(
        self,
        items: Sequence[Any],
        fn: Callable[[Any], Dict[str, Any]],
        *,
        concurrency: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        对列表逐项执行 fn(item)，返回结果列表。concurrency>1 时并行处理，
        顺序保持与输入一致（Map 语义）。
        """
        if concurrency <= 1:
            return [fn(item) for item in items]

        results: List[Any] = [None] * len(items)
        index_map = {id(item): idx for idx, item in enumerate(items)}  # noqa: 保持顺序

        def run(item: Any, idx: int) -> None:
            results[idx] = fn(item)

        with ThreadPoolExecutor(max_workers=min(concurrency, len(items))) as pool:
            futures = [
                pool.submit(run, item, idx) for idx, item in enumerate(items)
            ]
            for fut in futures:
                fut.result()
        return results


def _rebuild_history_from_logs(logs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    从日志重建对话历史（近似）：每个有文本产物的节点追加一条助手消息。
    供断点续跑场景下保持历史上下文一致。
    """
    history: List[Dict[str, Any]] = []
    for log in logs:
        response = log.get("response", "")
        if response and not log.get("tool_calls"):
            history = append_assistant_turn(history, response)
    return history
