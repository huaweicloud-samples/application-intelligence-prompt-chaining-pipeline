"""
行程单 PDF 生成 Worker（pdf_creator）
=====================================
受限运行时不内置 PDF 渲染依赖，本示例对「服务端 PDF」采用两层设计：
  1) 链直接返回 Markdown + 打印版 HTML（demo/trip_planner 的 render_html）；
  2) 本 Worker 提供独立部署形态：输入 Markdown 行程，输出适合浏览器
     「打印为 PDF」/ 桌面渲染器使用的 HTML（纯标准库，无重型依赖）。

事件体：
  { "markdown": "Markdown 行程文本", "title": "标题（可选）" }
响应：{ "statusCode": 200, "html": "...", "format": "printable-html" }
"""
from __future__ import annotations

import html as _html
from typing import Any, Dict, List


def markdown_to_html(markdown_text: str, title: str = "行程单") -> str:
    """极简 Markdown → 打印版 HTML（仅覆盖行程常用语法，非完整实现）。"""
    paragraphs: List[str] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("### "):
            paragraphs.append(f"<h3>{_html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            paragraphs.append(f"<h2>{_html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            paragraphs.append(f"<h1>{_html.escape(line[2:])}</h1>")
        elif line.startswith("- ") or line.startswith("* "):
            paragraphs.append(f"<li>{_html.escape(line[2:])}</li>")
        else:
            safe = _html.escape(line)
            safe = safe.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
            paragraphs.append(f"<p>{safe}</p>")

    return (
        "<html><head><meta charset=\"utf-8\"><style>"
        "body{font-family:sans-serif;max-width:720px;margin:24px auto;line-height:1.6}"
        "h1,h2,h3{color:#1a1a2e}</style></head>"
        f"<body><h1>{_html.escape(title)}</h1>{''.join(paragraphs)}</body></html>"
    )


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    body = event.get("body", event)
    if isinstance(body, str):
        import json
        body = json.loads(body)

    markdown_text = body.get("markdown") or body.get("itinerary") or ""
    if not markdown_text:
        return {"statusCode": 400, "error": "缺少 markdown（行程文本）"}

    title = body.get("title") or "行程单"
    return {
        "statusCode": 200,
        "html": markdown_to_html(markdown_text, title),
        "format": "printable-html",
    }


if __name__ == "__main__":
    sample = {
        "title": "巴黎三日游",
        "markdown": "# Day 1\n\n- 上午：卢浮宫\n- 下午：**埃菲尔铁塔**",
    }
    out = handler(sample, None)
    assert "<h1>巴黎三日游</h1>" in out["html"]
    print("OK, html length =", len(out["html"]))
