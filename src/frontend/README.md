# 本地交互前端（frontend）

基于 Streamlit 的本地交互台：把六个 demo 流程（`src/demo/*/flow.py`）变成
浏览器里可操作的表单 → 运行 → 结果/日志页面，用于在没有函数计算环境时体验
与联调提示词链。

## 启动

```bash
cd src
pip install -r frontend/requirements.txt   # 安装 streamlit
export MAAS_API_KEY=... MAAS_MODEL=...     # 模型访问凭据（部署侧下发）
streamlit run frontend/app.py              # 浏览器打开 http://localhost:8501
```

未配置 `MAAS_API_KEY` 时页面会给出明显提示；点击运行会进入错误态并显示原因。
纯编排语义演示（不联网、不依赖账号）请使用 `../techniques`。

## 页面与流程

| 页面文件 | demo 流程 | 编排形态 |
| --- | --- | --- |
| `pages/1_Blog_Post.py` | `demo.blog_post` | 顺序链 |
| `pages/2_Story_Writer.py` | `demo.story_writer` | JSON 校验 + Map |
| `pages/3_Trip_Planner.py` | `demo.trip_planner` | 并行扇出 + 汇合 |
| `pages/4_Movie_Pitch.py` | `demo.movie_pitch` | 并行采样 + 仲裁 + **人工确认** |
| `pages/5_Meal_Planner.py` | `demo.meal_planner` | 辩论循环 + 评分仲裁 |
| `pages/6_Most_Popular_Repo.py` | `demo.most_popular_repo` | 工具型 Agent（ReAct） |

页面文件只声明「入参与流程函数」，共享 `_ui.py` 的页面状态机：

- `idle`：渲染入参表单 → 点击「运行这条链」；
- `awaiting_human_input`：流程命中人工确认点（目前只有 movie_pitch）时，
  把问题清单 + 二选一答复渲染出来；提交答复后带着回放缓存续跑；
- `ok`：最终回答 + 结构化产物 + 整条链的节点日志（step_id / 温度 / token 用量）；
- `error`：错误信息 + 已执行节点日志。

## 续跑语义

带人工确认点的流程在首次运行命中确认点时，页面会保存该次运行的
`payload / flow_run / transcript / partial_state`。用户答复后，`run_flow_session`
恢复回放缓存、合并中间态，从「答复之后」的节点继续执行：
已完成的模型节点按缓存原样回放（不重复调用模型、不产生随机差异），
因此点击「提交答复并继续」只会对新增节点发起调用。
