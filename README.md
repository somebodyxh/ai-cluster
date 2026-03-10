# ⚡ AI Cluster — 多智能体 LLM 框架

> 一个基于 Streamlit 的多 Agent 协作框架，支持国内（硅基流动）/ 国外（OpenRouter）双平台混合路由，自动更新模型配置，流式输出实时显示，Agent 子任务并行执行。

---
![alt text](1773020553109.png)
# 目录

1. [项目结构](#项目结构)
2. [快速开始](#快速开始)
3. [核心架构图](#核心架构图)
4. [文件详解](#文件详解)
5. [通用库说明](#通用库说明)
6. [平台路由系统](#平台路由系统)
7. [流式输出机制](#流式输出机制)
8. [Agent 工作流](#agent-工作流)
9. [自动更新系统](#自动更新系统)
10. [配置文件说明](#配置文件说明)


---



# 重要！！

用 OpenRouter 需要自备代理

## 项目结构

```
AI集群/
├── app.py                         # ★ Streamlit 前端主入口
├── platform_config.py             # ★ 平台路由总配置（domestic/foreign/mixed）
├── debug.py                       # ★ 全局调试日志模块
│
├── main/
│   └── Json.py                    # secrets.json 读取，导出 API Keys
│
├── API/
│   ├── SiliconCloud_Api.py        # 硅基流动 API 封装
│   ├── OpenRouter_Api.py          # OpenRouter API 封装
│   └── router.py                  # ★ 统一路由层（所有调用入口）
│
├── config/
│   ├── auto_updater.py            # ★ 模型配置自动更新器
│   ├── model_config.json          # 自动生成：当前最佳模型配置
│   ├── model_config.json.bak      # 每次更新前自动备份
│   └── platform_mode.json         # 持久化：当前平台模式
│
├── multi_agent/
│   ├── project_manager.py         # ★ 项目/对话管理，持久化到 projects/
│   ├── scheduler.py               # Agent 任务调度（CLI 模式）
│   └── message_bus.py             # 消息总线（多智能体通信，待接入）
│
├── utils/                         # ★ 通用工具库（见下方"通用库说明"）
│   ├── __init__.py
│   ├── stream_utils.py            # 流文件操作：路径计算、读写、完成检测、取消机制
│   └── text_utils.py              # 文本处理：filter_json、parse_tasks
│
├── projects/                      # 运行时生成：对话持久化 JSON + 流临时文件
│   ├── 对话名称.json
│   └── .stream_xxx_yyy.txt        # 临时流文件（完成后删除）
│
└── secrets.json                   # 本地密钥文件（不提交到 git！）
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install streamlit openai tavily-python
```

### 2. 配置密钥

首次运行时程序会提示输入（请在 cmd 或终端内输入），自动生成 `secrets.json`：

```json
{
    "Api_Key": {
        "siliconcloud_key": "sk-xxx",
        "tavily_key":       "tvly-xxx",
        "openrouter_key":   "sk-or-xxx"
    }
}
```

> `openrouter_key` 留空也可以，但混合/国外模式下会报错。

### 3. 启动

```bash
streamlit run app.py
```

### 4. 强制更新模型配置

```bash
python config/auto_updater.py --force
```

---

## 核心架构图

```
用户输入
    │
    ▼
[app.py - Streamlit 前端]
    │ call_model_stream_to_file(model, fpath, prompt, role=xxx, cancel_event=evt)
    ▼
[API/router.py - 路由层]
    │ 查 platform_config.get_platform_for_role(role)
    ├──────────────────────────┐
    ▼                          ▼
[SiliconCloud_Api.py]    [OpenRouter_Api.py]
 硅基流动 API              OpenRouter API
    │                          │
    └──────────┬───────────────┘
               ▼
        后台线程写文件（支持 cancel_event 取消）
        projects/.stream_xxx.txt
               │
               ▼ (每 0.3 秒)
        [app.py 轮询读文件]
               │
               ▼
        实时显示流式内容
        （完成后用 st.markdown 渲染，支持代码高亮）
```

---

## 文件详解

### `platform_config.py` — 平台路由总配置

**最重要的配置文件**，控制整个路由系统。

| 变量 | 类型 | 说明 |
|------|------|------|
| `MIXED_ROUTING` | `dict` | 混合模式下各角色走哪个平台，可自由修改 |
| `DOMESTIC_FALLBACKS` | `dict` | 硅基流动各角色兜底模型 ID |
| `FOREIGN_FALLBACKS` | `dict` | OpenRouter 各角色兜底模型 ID |
| `MODE_LABELS` | `dict` | 侧边栏显示标签 |

**关键函数：**

```python
get_platform_mode()                      # 返回 "domestic" | "foreign" | "mixed"
set_platform_mode("mixed")               # 写入内存 + 持久化到文件
get_platform_for_role("coder")           # 返回该角色应走的平台
get_fallback_model("writer", "foreign")  # 返回兜底模型 ID
```

**修改混合模式路由：**

```python
MIXED_ROUTING = {
    "coder":      "foreign",   # 改成 "domestic" 则用硅基的 Qwen-Coder
    "reasoner":   "domestic",  # 保持国内，DeepSeek-R1 推理极强
    "writer":     "domestic",  # 改成 "foreign" 则用 GPT-4o
    "aggregator": "foreign",   # 改成 "domestic" 则省钱
}
```

> **重要**：修改 `MIXED_ROUTING` 后 `auto_updater.py` 的提示词会**自动同步**，无需手动修改任何其他地方。

---

### `API/router.py` — 统一路由层

所有对 LLM 的调用都应该通过这里，**不要直接调** `SiliconCloud_Api` 或 `OpenRouter_Api`。

```python
from API.router import call_model, call_model_stream_to_file
from utils.stream_utils import register_cancel

# role 参数决定走哪个平台（混合模式下）
result = call_model(model, prompt, role="reasoner")

# cancel_event 用于停止按钮真正终止后台线程
evt = register_cancel(fpath)
call_model_stream_to_file(model, fpath, prompt, role="writer", cancel_event=evt)
```

**为什么要有 router 层？**
直接调具体 API 模块的话，切换平台就需要改所有调用处。有了 router 层，只需改 `platform_config.py` 里的一行配置。

---

### `config/auto_updater.py` — 模型配置自动更新器

每7天自动运行一次，流程：
1. 用 Tavily 搜索最新大模型榜单
2. 把榜单 + 两个平台实际可用模型 ID 发给主 LLM
3. LLM 输出 `model_config.json` 的内容
4. 验证所有模型 ID 确实存在于对应平台
5. 保存配置

**关键变量：**

| 变量 | 说明 |
|------|------|
| `MAIN_MODEL` | 执行分析任务的模型（`role="reasoner"`，混合模式走硅基） |
| `CONFIG_FILE` | 输出路径 `config/model_config.json` |

---

### `multi_agent/project_manager.py` — 项目管理器

管理所有对话（项目）的生命周期。每个对话存一个 JSON 文件。

**`Project` 类的字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 对话名称 |
| `history` | `List[Dict]` | 完整对话历史 `[{"role": "user", "content": "..."}]` |
| `summary` | `str\|None` | 记忆压缩后的摘要（每6条消息触发一次） |
| `message_count` | `int` | 历史消息总数（用于触发压缩） |
| `agent_state` | `Dict\|None` | Agent 模式的执行状态机（见 Agent 工作流） |
| `chat_stream` | `Dict\|None` | 当前普通对话流的状态 `{file, model, user_input}` |

**记忆压缩机制：**
每发送 6 条消息，自动调用 `writer` 角色模型对全部历史做摘要，
下次对话时把摘要作为上下文前缀，既保留长期记忆又节省 token。

---

### `app.py` — Streamlit 前端

**Session State 变量：**

| 变量 | 说明 |
|------|------|
| `st.session_state.manager` | `ProjectManager` 单例 |
| `st.session_state.updater` | `ModelConfigUpdater` 单例 |
| `st.session_state.scheduler` | `MultiAgentScheduler` 单例 |
| `st.session_state.mode` | `"chat"` \| `"agent"` |
| `st.session_state.show_new_form` | 是否显示新建对话表单 |

---

### `debug.py` — 全局调试日志

所有模块通用的带颜色终端日志。

```python
from debug import log, log_api_call, log_api_done, log_stream, log_project

log("API",      "调用模型", "model=xxx prompt=yyy")
log("STREAM",   "写入 chunk", "+120字 共350字")
log("FRONTEND", "用户输入",  "内容前50字")
log("PROJECT",  "保存项目",  "历史10条")
log("ERROR",    "调用失败",  "timeout")
```

颜色对照：API=青色，STREAM=蓝色，AGENT=洋红，FRONTEND=绿色，PROJECT=黄色，ERROR=红色

---

## 通用库说明

`utils/` 目录是本项目的**通用工具库**，把多个文件都用到的逻辑集中在这里。

### `utils/stream_utils.py`

流文件操作，供 `app.py` 和任何需要检查流状态的模块使用。

```python
from utils.stream_utils import (
    stream_file, read_stream, is_done, cleanup, safe_name,
    register_cancel, cancel_stream, clear_cancel
)

# 计算流文件路径
fpath = stream_file("我的项目", "chat")
# → "projects/.stream_我的项目_chat.txt"

# 读取当前内容（后台线程可能仍在写）
content = read_stream(fpath)

# 检查是否完成（存在 .done 文件）
if is_done(fpath):
    cleanup(fpath)   # 删除 .txt 和 .done

# ── 取消机制（停止按钮用）──────────────────────────────
# 1. 启动线程前注册，拿到 Event
evt = register_cancel(fpath)
call_model_stream_to_file(model, fpath, prompt, cancel_event=evt)

# 2. 用户点停止时发信号，线程在下一个 chunk 边界退出并自行清理临时文件
cancel_stream(fpath)

# 3. 线程正常结束后自动调用（无需手动调）
clear_cancel(fpath)
```

**取消机制原理：**
`register_cancel` 创建一个 `threading.Event` 并以文件路径为 key 存入全局注册表。
API 层的 chunk 循环里每次先检查这个 Event，收到信号后 `break`，不创建 `.done` 文件，
并自行删除临时流文件，不留孤儿文件。

**为什么流文件以 `.` 开头？**
`.stream_xxx.txt` 在 Linux/Mac 上是隐藏文件，`ls` 不会显示，保持 `projects/` 目录整洁。

### `utils/text_utils.py`

文本处理工具。

```python
from utils.text_utils import filter_json, parse_tasks

# 清理模型输出中夹带的 JSON 块
clean = filter_json("分析结果如下：\n```json\n{...}\n```\n以上是完整分析。")
# → "分析结果如下：\n\n以上是完整分析。"

# 提取子任务列表
tasks = parse_tasks(raw_llm_output)
# → [{"task_id": "task1", "role": "coder", "prompt": "...", "depends_on": []}]
# 失败时返回 None
```

---

## 平台路由系统

```
模式              所有请求走向
─────────────────────────────────────────
domestic          全部 → 硅基流动
foreign           全部 → OpenRouter
mixed             按 MIXED_ROUTING 表分流
```

**混合模式下的调用链：**

```
call_model(..., role="coder")
    → router._pick("coder")
    → platform_config.get_platform_for_role("coder")
    → MIXED_ROUTING["coder"] = "foreign"
    → 返回 OpenRouter_Api 模块
    → 用 OpenRouter 的 API 调用
```

**切换模式：** 侧边栏 → API 平台 → 选择模式，立即生效并持久化。

---

## 流式输出机制

**为什么用文件而不是 `st.write_stream`？**

Streamlit 的 `st.write_stream` 要求生成器在同一次 rerun 里完成，
无法在切换对话后回来继续显示。

本框架用「文件 + 轮询」方案解决这个问题：

```
用户发送消息
    │
    ▼
evt = register_cancel(fpath)          ← 注册取消 Event
call_model_stream_to_file(model, fpath, prompt, cancel_event=evt)
    │  启动后台守护线程，立即返回
    ▼
proj.chat_stream = {"file": fpath, ...}
manager._save_project(proj)           ← 状态持久化
st.rerun()
    │
    ▼ (每次 rerun 检测)
content = read_stream(fpath)          ← 读取当前已写入的内容
show_live(label, content, is_done(fpath))
    │
    ├── 未完成 → 显示 live-box + 光标动画; time.sleep(0.3); st.rerun()
    │
    └── 完成   → cleanup(fpath)
                 manager.add_message(...)  ← 存入历史
                 proj.chat_stream = None
                 st.rerun()
                 （历史消息用 st.markdown 渲染，支持代码高亮和表格）
```

**停止按钮：**
点击停止后调用 `cancel_stream(fpath)`，后台线程在下一个 chunk 边界检测到信号后退出，
自行删除临时流文件，不创建 `.done`。已完成的子任务内容会先存入历史记录再清状态。

**切换对话时发生什么？**
后台线程继续写文件（线程不受 Streamlit rerun 影响）。
切回这个对话时，第一次 rerun 就会检测到文件继续轮询，无缝衔接。

---

## Agent 工作流

Agent 模式下 `proj.agent_state` 是一个状态机，**子任务并行执行**：

```
phase: "tasks"
    │
    ├── 找出所有依赖已满足的任务（可能多个）
    │       └── 并行启动多个后台线程
    │               └── active_streams = [{task_id, role, model, file}, ...]
    │
    ├── 轮询 active_streams（每 0.3 秒）：
    │       ├── 收集已完成的 → 存入 results / completed_display
    │       ├── 完成的从列表移除，未完成的继续追踪
    │       └── active_streams 清空 → rerun 找下一批可执行任务
    │
    ├── 所有任务完成（pending 为空）
    │       └── phase = "summary"
    │
    ▼
phase: "summary"
    │   按原始任务顺序重建结果列表，启动总结流
    │   current_stream = {task_id: "总结", role: "aggregator", ...}
    └── phase = "summary_streaming"
            │
            └── 轮询 → done → 存入历史 → agent_state = None
```

**并行执行说明：**
没有依赖关系（`depends_on: []`）的任务会在同一批次并发启动，各自独占一个后台线程。
有依赖的任务会等 `depends_on` 里所有任务都进入 `results` 后，才在下一批次启动。
这样在保证依赖顺序正确的前提下，最大化并发度。

**`agent_state` 字段说明：**

| 字段 | 说明 |
|------|------|
| `tasks` | 完整任务列表（来自 LLM 分解） |
| `results` | `{task_id: 结果文本}`，依赖检查和总结阶段使用 |
| `completed_display` | `[{task_id, model_short, content}]`，用于渲染已完成任务卡片 |
| `active_streams` | 当前正在并行运行的流列表 `[{task_id, role, model, file}]` |
| `current_stream` | 仅 `summary_streaming` 阶段使用，存总结流信息 |
| `phase` | 当前阶段：`"tasks"` \| `"summary"` \| `"summary_streaming"` |
| `user_input` | 用户原始输入（总结阶段引用） |

---

## 自动更新系统

**触发条件：** 距上次更新 ≥ 7 天，或点击侧边栏「更新模型配置」按钮（`force=True`）。

**数据流：**
```
Tavily 搜索（4个查询）
    ↓
search_results（评测榜单文本）
    ↓
analyze_with_llm()
    ├── 获取两个平台实际可用模型列表
    ├── 动态生成提示词（基于 MIXED_ROUTING，非硬编码）
    └── 调用 MAIN_MODEL（role="reasoner"）
            ↓
        LLM 输出 JSON
            ↓
validate_and_clean()
    ├── 精确匹配模型 ID
    ├── 失败时模糊匹配
    └── fallback 时从正确平台取模型
            ↓
        model_config.json（保存）
```

---

## 配置文件说明

### `secrets.json`（手动维护，不提交 git）

```json
{
    "Api_Key": {
        "siliconcloud_key": "硅基流动 API Key",
        "tavily_key":       "Tavily 搜索 API Key（可选，无则用模拟数据）",
        "openrouter_key":   "OpenRouter API Key（纯国内模式可不填）"
    }
}
```

### `config/model_config.json`（自动生成）

```json
{
    "last_update": "2026-03-08",
    "models": [
        {
            "id":           "Pro/deepseek-ai/DeepSeek-V3",
            "name":         "DeepSeek-V3",
            "capabilities": {"reasoning": 0.92, "coding": 0.85, "writing": 0.94},
            "best_for":     ["reasoning", "chinese"],
            "source":       "LMArena 2026-02",
            "ranking":      5
        }
    ],
    "default_mapping": {
        "coder":      "openai/gpt-4o",
        "reasoner":   "Pro/deepseek-ai/DeepSeek-R1",
        "writer":     "Pro/deepseek-ai/DeepSeek-V3",
        "vision":     "Qwen/Qwen2-VL-72B-Instruct",
        "aggregator": "openai/gpt-4o-mini"
    }
}
```

### `config/platform_mode.json`（自动生成）

```json
{"mode": "mixed"}
```

---

# 此项目还处于开发阶段，欢迎提交问题。