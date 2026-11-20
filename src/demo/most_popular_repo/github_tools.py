"""
GitHub 只读工具（demo 内嵌实现）
================================
与独立 Worker 函数（src/functions/github_actions）共用同一套语义：
  * get_trending_github_repositories —— 抓取 GitHub Trending 页，返回按热度排序的仓库列表
  * get_github_repository_readme —— 返回某仓库 README（前 5000 字符）

仅使用 Python 标准库（urllib + html.parser），demo / 函数目录无需第三方依赖；
可选的 GITHUB_TOKEN 环境变量用于提高 api.github.com 的速率限制（不设置也能
读取公开仓库，只是配额较低）。
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import urllib.request
from html.parser import HTMLParser
from typing import Dict, List

logger = logging.getLogger(__name__)

GITHUB_TRENDING_URL = "https://github.com/trending"
README_TRUNCATE_LIMIT = 5000
# 识别示例 URL（模型可能把提示词里的示例抄回来，要拒绝）
EXAMPLE_OWNER_REPO = "orgname/reponame"
REPO_URL_RE = re.compile(r"https?://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")

TRENDING_INTRO = (
    "Here are the contents of the GitHub Trending Repositories page. The repositories "
    "on the page are ordered by popularity (the highest trending repository is first)."
)


def _http_get(url: str, *, accept: str = "text/html") -> str:
    """标准库 GET 请求，返回响应文本。"""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": accept}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - 仅访问固定 GitHub 域名
        return response.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# GitHub Trending 页解析
# ---------------------------------------------------------------------------

class _ArticleTextExtractor(HTMLParser):
    """只抽取 <article class="Box-row ..."> 内部的文本。"""

    def __init__(self) -> None:
        super().__init__()
        self._depth = 0
        self._buffer: List[str] = []
        self.articles: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        if tag == "article":
            classes = dict(attrs).get("class", "").split()
            if "Box-row" in classes and self._depth == 0:
                self._depth = 1
                self._buffer = []
                return
        if self._depth:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._depth:
            self._depth -= 1
            if self._depth == 0 and tag == "article":
                text = _clean_whitespace("".join(self._buffer))
                if text:
                    self.articles.append(text)

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._buffer.append(data)


def _clean_whitespace(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\n\s*\n", "\n", text)       # 去重复空行
    text = re.sub(r"[ \t]+", " ", text)         # 行内空白收敛
    return text.strip()


def get_trending_github_repositories(input_text: str) -> str:
    """
    获取 GitHub Trending 仓库列表（按热度从高到低）。
    input_text 参数不使用（工具声明要求一个字符串参数，模型会传空串）。
    """
    page = _http_get(GITHUB_TRENDING_URL)
    parser = _ArticleTextExtractor()
    parser.feed(page)

    entries = parser.articles[:20]
    if not entries:
        # 页面结构变化时给出提示，而不是静默失败
        return (
            "I could not parse the GitHub Trending page. "
            "The page structure may have changed; please try again."
        )
    lines = [TRENDING_INTRO] + entries
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# README 获取
# ---------------------------------------------------------------------------

def get_github_repository_readme(repo_url: str) -> str:
    """
    获取仓库 README（最多 README_TRUNCATE_LIMIT 字符）。
    repo_url 形如 https://github.com/owner/repo。
    """
    match = REPO_URL_RE.search(repo_url or "")
    if not match:
        return (
            f"The repository URL {repo_url!r} is invalid. Provide a full URL like "
            "https://github.com/owner/repo."
        )
    owner_repo = match.group(1)
    if EXAMPLE_OWNER_REPO in owner_repo:
        return (
            f"{repo_url} is the example repository URL from the instructions, not a "
            "real repository. Please pick a repository from the trending list."
        )

    # 1) 优先 raw.githubusercontent.com（无需配额，无需鉴权）
    raw_url = f"https://raw.githubusercontent.com/{owner_repo}/HEAD/README.md"
    try:
        readme = _http_get(raw_url)
        return _wrap_readme(repo_url, readme)
    except Exception as exc:  # noqa: BLE001 - raw 失败走 API 兜底
        logger.info("raw README 获取失败（%s），尝试 GitHub API 兜底", exc)

    # 2) GitHub REST API 兜底：GET /repos/{owner}/{repo}/readme（raw 格式）
    api_url = f"https://api.github.com/repos/{owner_repo}/readme"
    try:
        readme = _http_get(api_url, accept="application/vnd.github.raw+json")
        return _wrap_readme(repo_url, readme)
    except Exception as exc:  # noqa: BLE001 - 404 / 无 README / 限流等统一兜底
        if getattr(exc, "code", None) == 404:
            return (
                f"Could not find a README for the repository {repo_url}. "
                "It may not exist in the repository."
            )
        logger.warning("GitHub API README 获取失败：%s", exc)
        return f"I could not fetch the README for {repo_url}: {exc}"


def _wrap_readme(repo_url: str, readme: str) -> str:
    if len(readme) > README_TRUNCATE_LIMIT:
        return (
            f"Here are the first {README_TRUNCATE_LIMIT:,} characters of the README "
            f"for {repo_url}.\n{readme[:README_TRUNCATE_LIMIT]}"
        )
    return f"Here are the full contents of the README for {repo_url}.\n{readme}"


# ---------------------------------------------------------------------------
# 工具注册表（供 ReAct Agent dispatcher 使用）
# ---------------------------------------------------------------------------

def tool_dispatcher(name: str, arguments: Dict[str, str]) -> str:
    """把模型发出的工具调用分发到上面的实现。"""
    if name == "get_trending_github_repositories":
        return get_trending_github_repositories(arguments.get("input", ""))
    if name == "get_github_repository_readme":
        return get_github_repository_readme(arguments.get("input", ""))
    raise ValueError(f"Unknown GitHub tool: {name}")


def tool_parameters() -> List[Dict[str, str]]:
    """供 JSON 摘要展示用的参数名清单。"""
    return ["input"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys

    demo = sys.argv[1] if len(sys.argv) > 1 else "trending"
    if demo == "readme":
        url = sys.argv[2] if len(sys.argv) > 2 else "https://github.com/huaweicloud/huaweicloud-sdk-python"
        result = get_github_repository_readme(url)
    else:
        result = get_trending_github_repositories("")
    print(result[:3000])
    print(json.dumps({"len": len(result)}))
