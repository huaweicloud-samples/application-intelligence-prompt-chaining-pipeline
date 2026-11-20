"""
电影提案（并行采样 + 仲裁 + 人工确认示例）
==========================================
一条带「轮次」语义的人工确认链：

  1. 三个「编剧」（Red=0 / Blue=0.5 / Green=1 三个温度档）并行各自生成一段电影提案；
  2. 一个「制片人」模型从中挑一个最佳提案（输出 1/2/3 → red/blue/green）；
  3. 「真人制片人」确认是否开绿灯（HumanInputRequired 挂起信号）：
       - yes → 把选定提案扩写成单页 pitch（one-pager）；
       - no  → 带着上一轮提案回到第 1 步重新生成（每条分支的提示词会引用
               被否决的旧提案，要求给出全新 idea —— 新一轮走新的节点 ID）。
  4. 每一轮生成/仲裁使用「轮次」限定节点 ID：人工否决后的新一轮会真正重新
     调用模型（新 step_id），而断点续跑时旧轮次按回放缓存原样恢复。

payload:
  { "movie_description": "一句话故事前提（必填）" }

replies（续跑）:
  { "producer_choice": "yes" | "no" }
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from chaining.runtime import ChainRuntime, HumanInputItem, HumanInputRequired

# 温度档位：档位名 -> 采样温度（低温度更保守，高温度更有想象力）
TEMPERATURE_SETTINGS: List[Tuple[str, float]] = [
    ("Red", 0.0),
    ("Blue", 0.5),
    ("Green", 1.0),
]

PITCH_TEMPLATE = (
    "You are an Oscar-winning screenwriter and you are pitching an idea for a new "
    "movie about {movie_description} to a major movie producer.\n"
    "Give me your movie pitch in one paragraph.\n"
    "Start with a tagline sentence that describes the movie as a whole, then follow "
    "with a synopsis of the story and the major characters."
)

NEW_PITCH_TEMPLATE = (
    "You are an Oscar-winning screenwriter and you are pitching an idea for a new "
    "movie about {movie_description} to a major movie producer.\n"
    "You previously pitched this idea for the movie, inside <previous_pitch></previous_pitch> "
    "XML tags. The movie producer rejected this idea and asked for a new idea.\n"
    "<previous_pitch>\n{previous_pitch}\n</previous_pitch>\n"
    "Give me your new movie pitch in one paragraph.\n"
    "Start with a tagline sentence that describes the movie as a whole, then follow "
    "with a synopsis of the story and the major characters."
)

ONE_PAGER_TEMPLATE = (
    "You are an Oscar-winning screenwriter and you are pitching an idea for a new "
    "movie about {movie_description} to a major movie producer.\n"
    "You previously pitched this short description for the movie, inside <pitch></pitch> "
    "XML tags.\n"
    "<pitch>\n{winning_movie_pitch}\n</pitch>\n"
    "Now create a one-page movie pitch, based on your previous short description for "
    "the movie."
)


def run_flow(
    payload: Dict[str, Any],
    runtime: ChainRuntime,
    replies: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    replies = replies or {}
    movie_description = (payload.get("movie_description") or "").strip()
    if not movie_description:
        raise ValueError(
            "缺少 movie_description：请提供一句话电影故事前提（如 "
            "「a chef who can taste memories」）。"
        )

    producer_choice = replies.get("producer_choice")
    if producer_choice == "yes":
        return _finish_one_pager(payload, runtime, movie_description)

    if producer_choice == "no":
        # 制片人否决：进入下一轮重新生成（新一轮会用「上一轮提案被否决」的提示词）
        round_no = int(payload.get("movie_round") or 1) + 1
        previous_pitches: Dict[str, Any] = payload.get("pitches") or {}
    else:
        # 首次执行（或新会话）
        round_no = int(payload.get("movie_round") or 1)
        previous_pitches = {}

    pitches = _generate_pitches(
        runtime, movie_description=movie_description,
        round_no=round_no, previous_pitches=previous_pitches,
    )
    chosen_color, winning_pitch = _choose_pitch(
        runtime, movie_description=movie_description,
        round_no=round_no, pitches=pitches,
    )

    # ---- 人工确认：真人制片人是否开绿灯（抛挂起信号，等待答复续跑） ----
    preview = winning_pitch.strip()
    if len(preview) > 200:
        preview = preview[:200] + "…"
    raise HumanInputRequired(
        [
            HumanInputItem(
                "制片人先生/女士，这是本轮的胜出电影提案，是否开绿灯推进？",
                placeholder="yes / no",
                hint="回复 yes：把该提案扩写为一页纸 pitch；回复 no：要求三位编剧重新提案。",
            ),
            HumanInputItem(
                f"胜出提案（{chosen_color}）：\n{preview}",
                placeholder="",
                hint="当前轮次 movie_round={round_no}，其余候选见 partial_state.pitches。".format(
                    round_no=round_no
                ),
            ),
        ],
        reply_keys=["producer_choice"],
        transcript=runtime.logs,
        partial_state={
            "movie_round": round_no,
            "pitches": pitches,
            "chosen_color": chosen_color,
            "winning_movie_pitch": winning_pitch,
        },
    )


# ---------------------------------------------------------------------------
# 内部步骤
# ---------------------------------------------------------------------------


def _generate_pitches(
    runtime: ChainRuntime,
    *,
    movie_description: str,
    round_no: int,
    previous_pitches: Dict[str, Any],
) -> Dict[str, str]:
    """
    三个温度档并行生成提案。上一轮提案存在时（制片人否决后的新一轮），
    各分支提示词引用本档被否决的旧提案，要求给出全新 idea。
    """

    def pitch_worker(temperature_name: str, temperature: float) -> Dict[str, Any]:
        previous_pitch = (previous_pitches or {}).get(temperature_name.lower())
        if previous_pitch:
            prompt = NEW_PITCH_TEMPLATE.format(
                movie_description=movie_description,
                previous_pitch=previous_pitch,
            )
        else:
            prompt = PITCH_TEMPLATE.format(movie_description=movie_description)

        out = runtime.model_turn(
            prompt,
            step_id=f"movie.r{round_no}.pitch.{temperature_name.lower()}",
            conversation=[],            # 独立节点：不携带任何历史
            max_tokens=1024,
            temperature=temperature,
        )
        return {temperature_name.lower(): out["response"]}

    branch_results: List[Dict[str, Any]] = runtime.parallel(
        [
            lambda name=name, temp=temp: pitch_worker(name, temp)
            for name, temp in TEMPERATURE_SETTINGS
        ]
    )
    pitches: Dict[str, str] = {}
    for branch in branch_results:
        pitches.update(branch)
    return pitches


def _choose_pitch(
    runtime: ChainRuntime,
    *,
    movie_description: str,
    round_no: int,
    pitches: Dict[str, str],
) -> Tuple[str, str]:
    """
    制片人仲裁：从三份提案中选一份。
    返回 (color_name_lower, pitch_text)。
    """
    lines = [
        "You are a producer of Oscar-winning movies, and you are deciding on the "
        "next movie you will make.",
        f"Screenwriters previously pitched you on {len(TEMPERATURE_SETTINGS)} movie "
        "ideas, and you need to pick one of the ideas.",
    ]
    for i, (temperature_name, _temperature) in enumerate(TEMPERATURE_SETTINGS):
        pitch_key = temperature_name.lower()
        lines.append(
            f"\n{i + 1}. Movie pitch #{i + 1} ({temperature_name}) is below, inside "
            f"<{pitch_key}></{pitch_key}> XML tags.\n"
            f"<{pitch_key}>\n{pitches[pitch_key]}\n</{pitch_key}>"
        )
    lines.append("\nNow choose one of the movie pitches. The possible selections are:")
    for i, (temperature_name, _temperature) in enumerate(TEMPERATURE_SETTINGS):
        lines.append(f"({i + 1}) Movie pitch {temperature_name}")
    lines.append(
        "\nReply with ONLY the number of the movie pitch you select (1, 2, or 3), "
        "then the color name. For example: 2) Movie pitch Blue"
    )
    prompt = "\n".join(lines)

    out = runtime.model_turn(
        prompt,
        step_id=f"movie.r{round_no}.chooser",
        conversation=[],                # 独立节点：三份提案都内联在提示词里
        max_tokens=300,
        temperature=0.3,
    )
    response = (out.get("response") or "").strip()

    match = re.search(r"([1-3])", response)
    if not match:
        raise RuntimeError(f"Unknown model pitch choice: {response!r}")
    index = int(match.group(1))
    chosen_color = TEMPERATURE_SETTINGS[index - 1][0].lower()
    return chosen_color, pitches[chosen_color]


def _finish_one_pager(
    payload: Dict[str, Any],
    runtime: ChainRuntime,
    movie_description: str,
) -> Dict[str, Any]:
    """制片人开绿灯：把胜出提案扩写为一页纸 pitch。"""
    winning_pitch = (payload.get("winning_movie_pitch") or "").strip()
    if not winning_pitch:
        raise ValueError(
            "缺少 winning_movie_pitch：开绿灯续跑必须携带首次执行返回的 partial_state。"
        )
    round_no = int(payload.get("movie_round") or 1)

    out = runtime.model_turn(
        ONE_PAGER_TEMPLATE.format(
            movie_description=movie_description,
            winning_movie_pitch=winning_pitch,
        ),
        step_id=f"movie.r{round_no}.onepager",
        conversation=[],                # 独立节点：内容全部内联
        max_tokens=2048,
        temperature=1.0,
    )
    return {
        "final_answer": out["response"],
        "movie_description": movie_description,
        "movie_round": round_no,
        "chosen_color": payload.get("chosen_color"),
        "winning_movie_pitch": winning_pitch,
        "pitches": payload.get("pitches", {}),
    }


if __name__ == "__main__":
    from demo._runner import run_flow_session

    import sys

    session = run_flow_session(
        run_flow,
        {"movie_description": "a chef who can taste memories"},
    )
    print("状态:", session["status"])
    if session["status"] == "awaiting_human_input":
        print("等待制片人答复；请携带 transcript 与 partial_state 续跑：")
        print(json := session)  # noqa: F841  (便于复制续跑参数)
        sys.exit(0)
    if session["status"] == "ok":
        print(session["result"]["final_answer"])
    else:
        print("执行失败:", session.get("message"))
