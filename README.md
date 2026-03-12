# ⚡ AI Cluster — 多智能体 LLM 框架

> 基于 FastAPI + React 的多 Agent 协作框架。支持硅基流动 / OpenRouter 双平台混合路由，多子任务并行执行，SSE 流式输出，自动更新模型配置。

---

> ⚠️ **使用 OpenRouter 需要自备代理（设置 https_proxy）**

---

# 目录

1. [快速开始](#快速开始)
2. [项目结构](#项目结构)
3. [架构总览](#架构总览)
4. [各层详解](#各层详解)
   - [入口层](#入口层)
   - [后端路由层 backend/](#后端路由层-backend)
   - [业务层 multi_agent/](#业务层-multi_agent)
   - [API调用层 API/](#api调用层-api)
   - [配置层 config/](#配置层-config)
   - [工具层 utils/](#工具层-utils)
   - [前端 frontend/](#前端-frontend)
5. [平台路由系统](#平台路由系统)
6. [SSE 流式输出机制](#sse-流式输出机制)
7. [Agent 工作流](#agent-工作流)
8. [自动更新系统](#自动更新系统)
9. [配置文件说明](#配置文件说明)
10. [API 接口速查](#api-接口速查)
11. [更新日志](#更新日志)

---

## 快速开始

### 1. 安装依赖

```bash
pip install fastapi uvicorn openai tavily-python
```

### 2. 配置密钥

首次启动时程序会自动提示输入，生成 `secrets.json`：

```json
{
    "Api_Key": {
        "siliconcloud_key": "sk-xxx",
        "tavily_key":       "tvly-xxx（可选，没有则联网搜索不可用）",
        "openrouter_key":   "sk-or-xxx（纯国内模式可以不填）"
    },
    "proxy": "http://127.0.0.1:7890（不用代理直接留空）"
}
```

### 3. 启动

```bash
python start.py
```

浏览器打开 `http://localhost:8000`。

**其他启动选项：**

```bash
python start.py --dev          # 开发模式：后端热重载 + Vite 热更新
python start.py --port 8080    # 换端口
python start.py --skip-build   # 跳过前端构建（dist/ 已存在时）
python start.py --no-browser   # 不自动打开浏览器
```

### 4. 强制更新模型配置

```bash
python config/auto_updater.py --force
```

---

## 项目结构

```
AI集群/
│
├── main.py                        # ★ uvicorn 启动入口
├── start.py                       # ★ 一键启动脚本（全平台）
├── platform_config.py             # ★ 平台路由总配置（必读）
├── debug.py                       # 全局彩色日志工具
│
├── backend/                       # FastAPI 后端（HTTP 接口层）
│   ├── app.py                     # FastAPI 实例 + CORS + 挂载路由
│   ├── dependencies.py            # 全局单例（manager / updater）
│   └── routes/
│       ├── projects.py            # 对话 CRUD（增删改查）
│       ├── chat.py                # 普通对话 SSE 流式
│       ├── agent.py               # Agent 模式（状态机 + 并行执行）
│       └── config.py              # 平台 / 模型配置
│
├── frontend/                      # React 前端（Vite 构建）
│   └── src/
│       ├── api/index.js           # 与后端通信的封装
│       ├── store/index.js         # Zustand 全局状态
│       └── components/
│           ├── Sidebar.jsx        # 对话列表侧边栏
│           ├── ChatPanel.jsx      # 普通对话面板
│           ├── AgentPanel.jsx     # Agent 模式面板
│           └── SettingsPanel.jsx  # 设置面板
│
├── API/                           # LLM 调用层（不要直接调，通过 router）
│   ├── router.py                  # ★ 统一路由层（所有 LLM 调用入口）
│   ├── SiliconCloud_Api.py        # 硅基流动 API 封装
│   └── OpenRouter_Api.py          # OpenRouter API 封装
│
├── multi_agent/                   # 业务逻辑层
│   ├── project_manager.py         # ★ 对话管理 + 记忆压缩
│   └── message_bus.py             # 消息总线（预留，暂未接入）
│
├── config/
│   ├── auto_updater.py            # ★ 模型配置自动更新器
│   ├── model_config.json          # 自动生成：当前最佳模型配置
│   └── platform_mode.json         # 自动生成：当前平台模式
│
├── utils/
│   ├── stream_utils.py            # 流文件操作（路径/读写/取消机制）
│   └── text_utils.py              # 文本处理（parse_tasks / filter_json）
│
├── main/
│   └── Json.py                    # secrets.json 读取，导出 API Keys
│
└── projects/                      # 运行时生成
    ├── 对话名称.json               # 对话持久化
    └── .stream_xxx.txt            # 流临时文件（完成后自动删除）
```

---

## 架构总览

整个项目分为五层，从上到下：

```
┌─────────────────────────────────────────────────────────┐
│                   浏览器 React 前端                       │
│    Sidebar / ChatPanel / AgentPanel / SettingsPanel      │
└──────────────────────┬──────────────────────────────────┘
                       │ REST + SSE
┌──────────────────────▼──────────────────────────────────┐
│              后端路由层 backend/                          │
│   FastAPI 接收请求 → 调用业务层 → 返回 JSON / SSE 流     │
└──────────────────────┬──────────────────────────────────┘
                       │ 调用
┌──────────────────────▼──────────────────────────────────┐
│              业务层 multi_agent/                          │
│   ProjectManager 管理对话状态 / 历史 / 记忆压缩           │
└──────────────────────┬──────────────────────────────────┘
                       │ 调用
┌──────────────────────▼──────────────────────────────────┐
│              API调用层 API/router.py                      │
│   按角色和平台模式，路由到硅基流动或 OpenRouter           │
└───────────┬──────────────────────────┬──────────────────┘
            │                          │
┌───────────▼──────────┐  ┌────────────▼──────────────────┐
│  硅基流动            │  │  OpenRouter                   │
│  SiliconCloud_Api.py │  │  OpenRouter_Api.py            │
└──────────────────────┘  └───────────────────────────────┘
```

**一个请求的完整流程（以普通对话为例）：**

```
用户输入 → React 前端 POST /chat/send
    → backend/routes/chat.py 接收请求
    → manager.switch_project() 切换到对应对话，拿上下文
    → updater.get_best_model("writer") 选最佳模型
    → API/router.py call_model_stream_gen()
        → platform_config.get_platform_for_role("writer") 决定走哪个平台
        → SiliconCloud_Api.call_model_stream_gen() 发起真正的 API 调用
    → 每个 chunk yield 出来，包装成 SSE 格式发给前端
    → 流结束后 manager.add_message() 存入历史
```

---

## 各层详解

---

### 入口层

#### `main.py` — uvicorn 启动入口

```python
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

同时托管前端 `frontend/dist/` 静态文件，访问 `http://localhost:8000` 直接打开页面。

#### `start.py` — 一键启动脚本

自动完成：检查 Python 依赖 → 检查 secrets.json → npm install → npm run build → 检查端口 → 启动。详见快速开始。

---

### 后端路由层 `backend/`

#### `backend/dependencies.py` — 全局单例

```python
manager = ProjectManager()
updater = ModelConfigUpdater()
```

这两个对象在整个后端生命周期里只创建一次。所有路由文件都从这里 import，而不是自己 `new`，保证状态一致。

> **如果每个路由文件各自 `new ProjectManager()`，它们会各自维护一套内存状态，互相看不到对方的操作，是一个非常隐蔽的 bug。**

#### `backend/app.py` — FastAPI 主应用

挂载四个路由，配置 CORS（允许前端 `localhost:5173` 跨域访问）：

```
/projects/*   → backend/routes/projects.py
/chat/*       → backend/routes/chat.py
/agent/*      → backend/routes/agent.py
/config/*     → backend/routes/config.py
```

#### `backend/routes/projects.py` — 对话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/projects/list` | 获取所有对话名称列表 |
| POST | `/projects/create` | 新建对话 `{"name": "对话名"}` |
| POST | `/projects/switch/{name}` | 切换对话，返回该对话的完整历史消息 |
| DELETE | `/projects/delete/{name}` | 删除对话 |

#### `backend/routes/chat.py` — 普通对话

**`POST /chat/send`** 接收用户消息，返回 SSE 流：

```json
请求体: {"project_name": "xxx", "message": "你好", "web_search": false}
```

流式响应格式：
```
data: 你好\n\n
data: ，\n\n
data: 有什么可以帮你的\n\n
data: [DONE]\n\n
```

收到 `[DONE]` 表示本次回答结束。支持 `web_search: true` 联网搜索模式，会先用 Tavily 搜索后再回答。

#### `backend/routes/agent.py` — Agent 模式

Agent 采用**后台线程 + 前端轮询**方案：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/agent/decompose` | 分解任务，同时启动 Agent 工作线程 |
| GET | `/agent/status/{name}` | 轮询当前进度（前端每秒调一次） |
| POST | `/agent/cancel/{name}` | 取消任务，保留已完成内容存入历史 |
| GET | `/agent/stream/{name}` | SSE 版状态推送（备用，前端默认用轮询） |

`/agent/status` 返回结构：

```json
{
  "phase": "tasks",
  "done": false,
  "error": null,
  "tasks": [{"task_id":"task1","role":"coder","prompt":"...","depends_on":[]}],
  "completed": [{"task_id":"task1","model_short":"DeepSeek-V3","content":"..."}],
  "active": ["task2"],
  "summary_content": ""
}
```

`phase` 的取值和含义：

| phase | 说明 |
|-------|------|
| `decomposing` | 正在分解任务（调用 reasoner 模型） |
| `tasks` | 子任务执行中（并行运行） |
| `summary` | 所有子任务完成，准备汇总 |
| `summary_streaming` | 汇总内容生成中（aggregator 模型） |
| `done` | 全部完成，结果已存入历史 |
| `error` | 执行出错，`error` 字段有错误信息 |

#### `backend/routes/config.py` — 配置接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/config/platform/current` | 获取当前平台模式 |
| POST | `/config/platform/set` | 切换平台模式 `{"mode": "mixed"}` |
| GET | `/config/platform/options` | 获取所有可选平台 |
| GET | `/config/models/current` | 获取当前模型配置（来自 model_config.json） |
| POST | `/config/models/update` | 手动触发模型配置更新（异步执行） |
| GET | `/config/models/fallbacks` | 获取各角色兜底模型 |
| GET | `/config/status` | 系统状态（平台 + 上次更新时间 + 是否需要更新） |

---

### 业务层 `multi_agent/`

#### `multi_agent/project_manager.py` — 核心业务

管理所有对话的完整生命周期，每个对话持久化为 `projects/对话名.json`。

**`Project` 对象字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 对话名称 |
| `history` | list | 完整消息历史 `[{"role":"user","content":"..."}]` |
| `summary` | str\|None | 记忆压缩摘要（每6条消息触发一次） |
| `message_count` | int | 历史消息总数 |
| `agent_state` | dict\|None | Agent 执行状态（用于页面刷新后恢复） |
| `chat_stream` | dict\|None | 当前流式对话状态 |

**记忆压缩机制：**

每发送 6 条消息，自动调用 `writer` 角色模型对全部历史做摘要。
下次对话时把摘要作为上下文前缀，既保留长期记忆又节省 token。

```
第1~6条消息正常积累
第6条消息存入后 → 自动触发压缩 → 生成摘要存入 project.summary
第7条起 → get_context() 返回「摘要 + 最近10条」而不是全部历史
```

**`ProjectManager` 主要方法：**

```python
manager.create_project("对话名")          # 新建对话
manager.switch_project("对话名")          # 切换，返回 Project 对象
manager.list_projects()                   # 列出所有对话名
manager.delete_project("对话名")          # 删除
manager.add_message("user", "内容")       # 添加消息，自动保存，自动触发压缩
manager.get_context(max_history=10)       # 获取上下文字符串（摘要 + 近期历史）
```

#### `multi_agent/message_bus.py` — 消息总线（预留）

实现了发布/订阅、点对点通信、请求-响应三种模式，支持消息过期和持久化。
**当前未被任何地方调用**，为以后多 Agent 相互通信预留。

---

### API调用层 `API/`

#### `API/router.py` — 统一路由层（重要）

**所有 LLM 调用都必须通过这里，不要直接 import `SiliconCloud_Api` 或 `OpenRouter_Api`。**

对外暴露四个函数，签名与底层 API 完全一致，只多了一个 `role` 参数：

```python
from API.router import call_model, call_model_stream_gen, call_model_stream_to_file

# 普通调用（阻塞，返回完整字符串）
result = call_model(model, prompt, role="writer")

# 流式生成器（yield 每个 chunk）
for chunk in call_model_stream_gen(model, prompt, role="coder"):
    print(chunk, end="", flush=True)

# 流写入文件（后台线程，立即返回）
call_model_stream_to_file(model, fpath, prompt, role="reasoner", cancel_event=evt)
```

`role` 参数决定走哪个平台（由 `platform_config.py` 的 `MIXED_ROUTING` 控制），对调用方完全透明。

#### `main/Json.py` — 密钥管理

读取 `secrets.json`，导出全局变量供各模块使用：

```python
from main.Json import SiliconCloud_KEY, OpenRouter_KEY, Tavily_KEY, PROXY
```

首次运行时如果 `secrets.json` 不存在，会在终端交互式提示输入并自动保存。
读取 `proxy` 字段后会自动设置 `os.environ["https_proxy"]`，无需其他配置。

---

### 配置层 `config/`

#### `platform_config.py` — 平台路由总配置

**这是整个路由系统最重要的文件**，控制哪个角色走哪个平台。

```python
# 混合模式下每个角色走哪个平台，按需修改
MIXED_ROUTING = {
    "coder":      "foreign",    # → OpenRouter（可改为 "domestic" 用 Qwen-Coder）
    "reasoner":   "domestic",   # → 硅基流动（DeepSeek-R1 推理极强且便宜）
    "writer":     "domestic",   # → 硅基流动（国内中文写作 Qwen 表现好）
    "aggregator": "foreign",    # → OpenRouter（GPT/Claude 整合能力强）
}

# 当 model_config.json 里没有对应角色时的保底模型
DOMESTIC_FALLBACKS = {
    "coder":      "Qwen/Qwen2.5-Coder-32B-Instruct",
    "reasoner":   "deepseek-ai/DeepSeek-R1",
    "writer":     "Qwen/Qwen2.5-72B-Instruct",
    "aggregator": "Qwen/Qwen2.5-72B-Instruct",
}

FOREIGN_FALLBACKS = {
    "coder":      "deepseek/deepseek-chat",
    "reasoner":   "anthropic/claude-3-5-sonnet",
    "writer":     "openai/gpt-4o",
    "aggregator": "openai/gpt-4o-mini",
}
```

**修改 `MIXED_ROUTING` 之后不需要改任何其他地方**，`auto_updater.py` 的提示词是动态生成的，会自动跟着变。

三种平台模式：

```
domestic  →  所有角色全走硅基流动
foreign   →  所有角色全走 OpenRouter
mixed     →  按 MIXED_ROUTING 表分流
```

#### `config/auto_updater.py` — 模型自动更新器

每 7 天自动运行一次，流程：

```
① Tavily 搜索「最新大模型评测榜单」（4个查询）
        ↓
② 获取硅基流动 + OpenRouter 当前实际可用模型列表
        ↓
③ 把榜单 + 可用列表 + MIXED_ROUTING 配置发给 reasoner 模型
        ↓
④ 模型输出推荐的 model_config.json 内容（JSON 格式）
        ↓
⑤ validate_and_clean()：精确匹配 → 模糊匹配 → 兜底
        ↓
⑥ 写入 config/model_config.json，备份旧文件为 .bak
```

> 整个流程依赖当前 `MIXED_ROUTING` 动态生成提示词，所以改了路由配置后更新出来的模型也会对应变化。

---

### 工具层 `utils/`

#### `utils/stream_utils.py` — 流文件操作

「写文件 + 轮询」是本项目流式输出的核心机制。后台线程把模型输出的每个 chunk 写入临时文件，前端轮询这个文件读取内容。

```python
from utils.stream_utils import stream_file, read_stream, is_done, cleanup, register_cancel, cancel_stream

# 计算临时文件路径
fpath = stream_file("对话名", "task1")
# → "projects/.stream_对话名_task1.txt"

# 注册取消 Event（流开始前调用）
evt = register_cancel(fpath)
call_model_stream_to_file(model, fpath, prompt, cancel_event=evt)

# 读取当前已写入的内容（线程可能还在写）
content = read_stream(fpath)

# 检查是否完成（存在 .done 标记文件）
if is_done(fpath):
    cleanup(fpath)   # 删除 .txt 和 .done

# 停止按钮：发送取消信号，线程在下一个 chunk 边界退出
cancel_stream(fpath)
```

**取消机制原理：**

`register_cancel` 创建一个 `threading.Event` 并以文件路径为 key 存入全局注册表。
底层 API 模块的 chunk 循环里每次先 `event.is_set()` 检查，收到信号后 `break`，
不创建 `.done` 文件，并自行删除临时流文件，不留孤儿文件。

**为什么临时文件以 `.` 开头？**
`.stream_xxx.txt` 在 Linux/macOS 是隐藏文件，`ls` 不显示，保持 `projects/` 目录整洁。

#### `utils/text_utils.py` — 文本处理

```python
from utils.text_utils import filter_json, parse_tasks

# 从模型输出中清除 JSON 代码块（防止 Markdown 渲染时出现原始 JSON）
clean = filter_json("分析如下：\n```json\n{...}\n```\n以上完毕。")
# → "分析如下：\n\n以上完毕。"

# 解析 Agent 任务列表（处理模型输出各种格式问题）
tasks = parse_tasks(raw_llm_output)
# 成功 → [{"task_id":"task1","role":"coder","prompt":"...","depends_on":[]}]
# 失败 → None（调用方降级处理）
```

---

### 前端 `frontend/`

#### `src/api/index.js` — 与后端通信

封装所有 HTTP 请求和 SSE 连接。

SSE 解析方式：每个 chunk 是纯文本，直接读取 `data:` 后面的内容，遇到 `[DONE]` 结束。

```javascript
// 发起 SSE 流式对话
streamChat(projectName, message, webSearch, onChunk, onDone, onError)

// 轮询 Agent 状态
getAgentStatus(projectName)  // → { phase, done, completed, active, ... }

// 取消 Agent 任务
cancelAgent(projectName)
```

#### `src/store/index.js` — Zustand 全局状态

核心状态：

| 字段 | 说明 |
|------|------|
| `projects` | 所有对话名称列表 |
| `currentProject` | 当前对话名称 |
| `messages` | 当前对话的消息列表 |
| `isStreaming` | 是否正在流式输出（控制输入框禁用） |
| `mode` | `"chat"` \| `"agent"` |

> `setMessages` 会同时重置 `isStreaming = false`，防止切换对话后输入框因上一个对话的流式状态卡死。

#### `src/components/AgentPanel.jsx`

- 子任务卡片：运行中展开显示完整内容，已完成折叠只显示标题
- 页面刷新或切换对话后回来，自动调 `/agent/status` 检测是否有进行中的任务，有则恢复轮询
- 历史 Agent 任务从 `project.history` 加载，不依赖前端内存状态

#### `src/components/SettingsPanel.jsx`

- 平台模式切换（domestic / foreign / mixed），切换后立即生效并持久化
- 展示当前各角色使用的模型（来自 `model_config.json`）
- 一键触发模型配置更新

---

## 平台路由系统

调用链示例（混合模式，role="coder"）：

```
backend/routes/agent.py
    call_model_stream_to_file(model, fpath, prompt, role="coder")
            ↓
API/router.py → _pick("coder")
    → platform_config.get_platform_for_role("coder")
    → MIXED_ROUTING["coder"] = "foreign"
    → 返回 OpenRouter_Api 模块
            ↓
OpenRouter_Api.call_model_stream_to_file(...)
    → 后台线程向 OpenRouter 发请求，逐 chunk 写入临时文件
```

**切换模式：** 设置面板 → 平台模式 → 选择，立即写入 `config/platform_mode.json`，下一次 API 调用就生效。

---

## SSE 流式输出机制

SSE（Server-Sent Events）是一种服务器向客户端单向推送的协议，格式要求每条消息是：

```
data: 内容\n\n
```

**普通对话流程：**

```
用户发消息 → POST /chat/send
    → 后台生成器逐 chunk yield
    → FastAPI StreamingResponse 推送 SSE
    → 前端 EventSource 监听，每收到一个 chunk 追加到消息气泡
    → 收到 [DONE] 关闭连接，解除输入框禁用
```

**Agent 子任务流程（写文件 + 轮询）：**

```
/agent/decompose 启动后台工作线程
    → 工作线程并行调用 call_model_stream_to_file
        → 各子任务分别写 .stream_xxx_taskN.txt
    → 前端每秒 GET /agent/status
        → 后端读取流文件当前内容，返回 completed / active / summary_content
        → 前端更新任务卡片显示
    → 子任务完成（.done 文件出现）→ 读内容，cleanup，加入 completed
    → 全部完成 → 启动 aggregator 总结 → 写 .stream_xxx_summary.txt
    → 总结完成 → 存入历史 → done=true
```

---

## Agent 工作流

```
POST /agent/decompose
    │
    ├── reasoner 模型分解任务 → 得到 tasks[] JSON
    │
    └── start_agent_worker() 启动后台线程
                │
                ▼
        工作线程 execute_tasks()
                │
                ├── 找出所有 depends_on 已满足的任务（可能多个）
                │       └── 并行启动，各写 .stream_xxx_taskN.txt
                │
                ├── 每秒检查 active_streams：
                │       ├── .done 出现 → 读内容 → 加入 results / completed_display
                │       └── active_streams 清空 → 找下一批可执行任务
                │
                ├── 所有任务完成（results 包含全部 task_id）
                │       └── phase = "summary"
                │
                ▼
        start_summary()
                │
                ├── 按原始顺序拼接所有子任务结果
                └── aggregator 模型生成总结 → 写 .stream_xxx_summary.txt
                        │
                        └── 完成 → 存入历史 → 清理 agent_manager 状态
```

**角色说明：**

| 角色 | 适用场景 | 限制 |
|------|----------|------|
| `writer` | 写作、总结、分析、普通问答（默认） | 无 |
| `coder` | 需要写代码的任务 | 无 |
| `reasoner` | 复杂数学/逻辑推理，任务分解本身也用这个 | 每次 Agent 最多1次 |
| `searcher` | 需要联网搜索实时信息 | 每次 Agent 最多1次 |
| `aggregator` | 整合所有子任务结果，生成最终回答 | 每次 Agent 只能1个 |

**依赖关系示例：**

```
task1（coder, depends_on=[]）  ──┐
task2（writer, depends_on=[]） ──┤ 同批次并行启动
task3（aggregator, depends_on=["task1","task2"]）← 等 task1+task2 完成后启动
```

---

## 自动更新系统

**触发条件：** 距上次更新 ≥ 7 天，或点击设置面板里的「更新模型配置」。

`ModelConfigUpdater.get_best_model(role)` 的查找顺序：

```
① 查 model_config.json 的 default_mapping[role]
        ↓（没有则）
② 查 model_config.json 的 models[] 里 best_for 包含该角色的最高 ranking 模型
        ↓（还没有则）
③ 查 platform_config.py 的 DOMESTIC_FALLBACKS / FOREIGN_FALLBACKS（兜底，不会崩溃）
```

---

## 配置文件说明

### `secrets.json`（手动维护，不提交 git）

```json
{
    "Api_Key": {
        "siliconcloud_key": "硅基流动 API Key",
        "tavily_key":       "Tavily 搜索 API Key",
        "openrouter_key":   "OpenRouter API Key"
    },
    "proxy": "http://127.0.0.1:7890"
}
```

### `config/model_config.json`（自动生成）

```json
{
    "last_update": "2026-03-12",
    "models": [
        {
            "id":           "Pro/deepseek-ai/DeepSeek-V3",
            "name":         "DeepSeek-V3",
            "capabilities": {"reasoning": 0.92, "coding": 0.85, "writing": 0.94},
            "best_for":     ["writer", "reasoning"],
            "source":       "LMArena 2026-03",
            "ranking":      3
        }
    ],
    "default_mapping": {
        "coder":      "openai/gpt-4o",
        "reasoner":   "Pro/deepseek-ai/DeepSeek-R1",
        "writer":     "Pro/deepseek-ai/DeepSeek-V3",
        "aggregator": "openai/gpt-4o-mini",
        "searcher":   "Pro/deepseek-ai/DeepSeek-V3"
    }
}
```

### `config/platform_mode.json`（自动生成）

```json
{"mode": "mixed"}
```

---

## API 接口速查

```
对话管理
  GET    /projects/list
  POST   /projects/create          {"name": "对话名"}
  POST   /projects/switch/{name}
  DELETE /projects/delete/{name}

普通对话
  POST   /chat/send                {"project_name":"...","message":"...","web_search":false}
                                   → SSE 流，data: chunk ... data: [DONE]

Agent 模式
  POST   /agent/decompose          {"project_name":"...","message":"..."}
  GET    /agent/status/{name}      → {phase, done, tasks, completed, active, summary_content}
  POST   /agent/cancel/{name}
  GET    /agent/stream/{name}      → SSE 版状态推送（备用）

配置
  GET    /config/platform/current
  POST   /config/platform/set      {"mode": "domestic"|"foreign"|"mixed"}
  GET    /config/platform/options
  GET    /config/models/current
  POST   /config/models/update
  GET    /config/models/fallbacks
  GET    /config/status
```

---

## 更新日志

### v2.0 (2026-03-12)
- **架构重构**：舍弃 Streamlit，改为 FastAPI + React（Vite）前后端分离
- 新增 `backend/` 目录，`dependencies.py` 统一单例，修复三路由各自 `new manager` 导致状态不共享的 bug
- `chat.py` 消息保存移出生成器，保证不丢消息
- `agent.py` 新增后台工作线程 + `AgentStateManager`，子任务真正并行执行
- `agent.py` 新增断线恢复：页面刷新后 `/status` 接口从内存或 `project.agent_state` 恢复状态
- 前端 `store/index.js` 修复切换对话后 `isStreaming` 不重置导致输入框卡死
- `AgentPanel` 子任务可折叠，切换/刷新后自动恢复进行中任务
- `SettingsPanel` 新增平台切换、模型配置查看、一键更新
- 新增全平台启动脚本 `start.py`
- 删除已废弃的 `multi_agent/scheduler.py`

### v1.3 (2026-03-10)
- 新增联网搜索开关，普通对话与 Agent 模式均支持
- Agent 角色分配优化：reasoner 最多1次，aggregator 只能1个，新增 searcher 角色
- 统一默认模型为 DeepSeek-V3，降低推理成本
- 增加 max_token 至 20000，修复长内容截断问题
- 新增代理配置入口
- 修复 AI 思考时用户输入不显示的问题

### v1.2 (2026-03-09)
- 串行处理变量优化

### v1.1 (2026-03-09)
- 修复前端代码块渲染重叠问题，改用 st.markdown() 渲染
- 修复 XSS 缺陷
- 修复 Agent 状态机死锁 P0 问题
- 停止按钮补全真正的线程取消机制，停止后保留已完成子任务内容
- 修复侧边栏文件句柄泄漏

---

*此项目还处于开发阶段，欢迎提交 issue。*
*项目有些虽然是 AI 写的，但我会一句一句地看。因为作者快中考了，所以肯定会有疏漏，请大家轻喷。*