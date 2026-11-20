# pdf_creator —— 行程单 PDF/打印版生成 Worker

受限运行时不内置 PDF 渲染依赖，本示例的取舍：
- 链内（`demo/trip_planner`）直接返回 Markdown + 打印版 HTML；
- 本 Worker 提供独立部署参考：`markdown → printable HTML`，浏览器
  「打印为 PDF」或本地渲染器即可产出 PDF。

若你的运行环境允许安装 weasyprint，也可在本函数基础上把 `html` 再渲染为
PDF 字节流返回（README 不再赘述）。
