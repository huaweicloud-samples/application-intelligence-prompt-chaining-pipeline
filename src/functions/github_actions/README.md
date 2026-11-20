# github_actions —— GitHub 只读工具 Worker

独立部署形态的 GitHub 只读工具函数（仓库搜索 / README 摘要），与链内
（`demo/most_popular_repo`）共用同一套语义。

- 事件体：`{"tool": "get_trending_github_repositories" | "get_github_repository_readme", "arguments": {"input": "..."}}`
- 响应：`{"statusCode": 200, "contents": "<工具返回文本>"}`
- 仅用 Python 标准库（urllib + html.parser），`requirements.txt` 为空；
- 可选环境变量 `GITHUB_TOKEN`（用于提高 api.github.com 速率配额，不设置也能读公开仓库）。
