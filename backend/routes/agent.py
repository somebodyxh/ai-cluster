"""
backend/routes/agent.py — Agent 多任务调度
============================================
设计原则：
  - 所有任务状态存在内存的 AgentStateManager 里（字典 + 锁）
  - 前端每秒 GET /agent/status 拉取最新状态（轮询）
  - 状态机推进由 /status 接口触发，不依赖后台常驻线程
  - 流文件由 call_model_stream_to_file 后台线程写入，/status 里用 is_done() 检测
"""
import json
import threading
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.dependencies import manager, updater
from API.router import call_model, call_model_stream_to_file
from utils.text_utils import parse_tasks, filter_json
from utils.stream_utils import stream_file, read_stream, is_done, cleanup, register_cancel, cancel_stream
from main.Json import Tavily_KEY

router = APIRouter()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 内存状态管理（线程安全）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class AgentStateManager:
    def __init__(self):
        self._states: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def get(self, project_name: str) -> Optional[Dict]:
        with self._lock:
            return self._states.get(project_name)

    def set(self, project_name: str, state: Dict):
        with self._lock:
            self._states[project_name] = state

    def remove(self, project_name: str):
        with self._lock:
            self._states.pop(project_name, None)


_agent_states = AgentStateManager()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 数据模型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class DecomposeRequest(BaseModel):
    project_name: str
    message: str


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 状态机推进（在 /status 里调用）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _tick(project_name: str, state: Dict) -> Dict:
    """
    推进一次状态机，返回更新后的 state。
    只做状态读取和推进，不阻塞。
    """
    phase = state.get("phase")

    # ── tasks 阶段：检查完成 + 启动新任务 ──────────────────────
    if phase == "tasks":
        still_running = []

        for cs in state.get("active_streams", []):
            fpath = cs["file"]
            if is_done(fpath):
                content = read_stream(fpath)
                cleanup(fpath)
                state["results"][cs["task_id"]] = content
                state.setdefault("completed_display", []).append({
                    "task_id":     cs["task_id"],
                    "model_short": cs["model"].split("/")[-1],
                    "content":     content,
                })
            else:
                still_running.append(cs)

        state["active_streams"] = still_running

        # 如果没有正在运行的任务，检查是否还有 pending
        if not still_running:
            tasks   = state["tasks"]
            results = state["results"]
            pending = [t for t in tasks if t["task_id"] not in results]

            if not pending:
                # 所有子任务完成，进入汇总
                state["phase"] = "summary"
            else:
                # 找可执行任务并启动
                executable = [
                    t for t in pending
                    if all(d in results for d in t.get("depends_on", []))
                ]
                if not executable:
                    state["phase"] = "error"
                    state["error"] = "任务依赖死锁"
                else:
                    _launch_tasks(project_name, state, executable)

    # ── summary 阶段：启动汇总流 ────────────────────────────────
    elif phase == "summary":
        _launch_summary(project_name, state)

    # ── summary_streaming 阶段：检查汇总是否完成 ────────────────
    elif phase == "summary_streaming":
        cs = state.get("current_stream")
        if cs and is_done(cs["file"]):
            content = read_stream(cs["file"])
            cleanup(cs["file"])
            state["summary_content"] = content
            state["phase"] = "done"

            # 存入对话历史
            proj = manager.switch_project(project_name)
            if proj:
                manager.add_message("user",      state.get("user_input", ""))
                manager.add_message("assistant", filter_json(content))

        elif cs:
            # 汇总流进行中：实时更新 summary_content 供前端展示
            state["summary_content"] = read_stream(cs["file"])

    return state


def _launch_tasks(project_name: str, state: Dict, tasks: List[Dict]):
    """并行启动一批可执行任务"""
    results = state["results"]

    for task in tasks:
        task_id = task["task_id"]
        role    = task["role"]

        # searcher 直接调 Tavily，不走 LLM
        if role == "searcher":
            try:
                from tavily import TavilyClient
                client = TavilyClient(api_key=Tavily_KEY)
                resp   = client.search(task["prompt"], max_results=5)
                result = "\n".join(r["content"] for r in resp["results"])
                state["results"][task_id] = result
                state.setdefault("completed_display", []).append({
                    "task_id": task_id, "model_short": "Tavily", "content": result
                })
            except Exception as e:
                state["results"][task_id] = f"搜索失败: {e}"
            continue

        # 替换 prompt 中的占位符
        prompt = task["prompt"]
        for dep in task.get("depends_on", []):
            prompt = prompt.replace(f"{{{{{dep}}}}}", results.get(dep, ""))

        model  = updater.get_best_model(role)
        fpath  = stream_file(project_name, task_id)
        cancel = register_cancel(fpath)

        call_model_stream_to_file(model, fpath, prompt, role=role, cancel_event=cancel)

        state["active_streams"].append({
            "task_id": task_id,
            "role":    role,
            "model":   model,
            "file":    fpath,
        })


def _launch_summary(project_name: str, state: Dict):
    """启动汇总流"""
    results    = state["results"]
    all_output = [
        results[t["task_id"]]
        for t in state["tasks"]
        if t["task_id"] in results
    ]

    summary_prompt = (
        f"用户原始问题：{state.get('user_input', '')}\n\n"
        + "\n\n".join(f"子任务{i+1}结果：\n{r}" for i, r in enumerate(all_output))
        + "\n\n请整合所有子任务结果，给出简洁连贯的最终答案。不要重复子任务细节。"
    )

    model  = updater.get_best_model("aggregator")
    fpath  = stream_file(project_name, "summary")
    cancel = register_cancel(fpath)

    call_model_stream_to_file(model, fpath, summary_prompt, role="aggregator", cancel_event=cancel)

    state["current_stream"] = {
        "task_id": "总结", "role": "aggregator", "model": model, "file": fpath
    }
    state["summary_content"] = ""
    state["phase"] = "summary_streaming"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 接口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.post("/decompose")
def decompose(req: DecomposeRequest):
    """分解任务，初始化 agent_state，立刻启动第一批无依赖子任务"""
    proj = manager.switch_project(req.project_name)
    if not proj:
        raise HTTPException(status_code=404, detail="对话不存在")

    decompose_model  = updater.get_best_model("reasoner")
    decompose_prompt = f"""
请将以下用户任务分解成多个子任务，输出JSON数组。
- 子任务数量控制在 3~5 个，不要过度拆分
- 能合并的任务尽量合并，优先并行而不是串行
每个子任务包含：
- task_id: 唯一标识（如 task1, task2）
- role: writer（默认） | coder | reasoner（最多1个） | searcher（最多1个） | aggregator（必须1个且最后）
- prompt: 具体指令，可用 {{{{task_id}}}} 引用前序结果
- depends_on: 依赖的task_id列表，没有则填 []

用户任务：{req.message}

只输出JSON数组，不要其他文字。
"""

    raw   = call_model(decompose_model, decompose_prompt, temperature=0.2, max_tokens=3000, role="reasoner")
    tasks = parse_tasks(raw)

    if not tasks:
        return {"ok": False, "fallback": True, "error": "任务分解失败"}

    # 初始化状态
    state = {
        "tasks":             tasks,
        "results":           {},
        "completed_display": [],
        "active_streams":    [],
        "current_stream":    None,
        "summary_content":   "",
        "phase":             "tasks",
        "user_input":        req.message,
    }

    # 立刻启动第一批无依赖任务
    first_batch = [t for t in tasks if not t.get("depends_on")]
    _launch_tasks(req.project_name, state, first_batch)

    _agent_states.set(req.project_name, state)

    return {"ok": True, "tasks": tasks}


@router.get("/status/{project_name}")
def get_status(project_name: str):
    """
    前端每秒调一次。
    这里同时负责推进状态机（检查完成、启动下一批任务）。
    """
    state = _agent_states.get(project_name)
    if not state:
        return {"phase": "done", "done": True, "completed": [], "active": [],
                "tasks": [], "summary_content": ""}

    # 推进状态机
    state = _tick(project_name, state)
    _agent_states.set(project_name, state)

    # 构建响应
    phase = state.get("phase")
    done  = phase in ("done", "error")

    # 如果完成，从内存清理
    if done:
        _agent_states.remove(project_name)

    return {
        "phase":           phase,
        "done":            done,
        "error":           state.get("error"),
        "tasks":           state.get("tasks", []),
        "completed":       state.get("completed_display", []),
        "active":          [cs["task_id"] for cs in state.get("active_streams", [])],
        "summary_content": state.get("summary_content", ""),
    }


@router.post("/cancel/{project_name}")
def cancel(project_name: str):
    """停止所有正在运行的任务"""
    state = _agent_states.get(project_name)

    if state:
        for cs in state.get("active_streams", []):
            cancel_stream(cs["file"])
            cleanup(cs["file"])

        cs = state.get("current_stream")
        if cs:
            cancel_stream(cs["file"])
            cleanup(cs["file"])

        # 已完成部分存入历史
        completed = state.get("completed_display", [])
        if completed:
            proj = manager.switch_project(project_name)
            if proj:
                partial = "\n\n".join(
                    f"**{r['task_id']}**（{r['model_short']}）：\n{r['content']}"
                    for r in completed
                )
                manager.add_message("user", state.get("user_input", "（Agent任务）"))
                manager.add_message("assistant",
                    f"⚠️ 任务已手动停止，以下是已完成的子任务结果：\n\n{partial}")

        _agent_states.remove(project_name)

    return {"ok": True}