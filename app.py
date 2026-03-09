import streamlit as st
import sys, os, json, time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multi_agent.project_manager import ProjectManager
from multi_agent.scheduler import MultiAgentScheduler
from API.router import call_model, call_model_stream_to_file
from config.auto_updater import ModelConfigUpdater
from main.Json import Tavily_KEY
from platform_config import get_platform_mode, set_platform_mode, MODE_LABELS, MIXED_ROUTING
# 通用工具库（
from utils.stream_utils import (safe_name, stream_file, read_stream,
                                is_done, cleanup,
                                register_cancel, cancel_stream)   # P1: 取消支持
from utils.text_utils import filter_json, parse_tasks

os.environ["TAVILY_API_KEY"] = Tavily_KEY

# ================================================================
# 页面配置
# ================================================================
st.set_page_config(
    page_title="AI Cluster",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================================================================
# 样式
# ================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Noto+Sans+SC:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans SC', sans-serif; font-size: 15px; }
.stApp { background: #212121; color: #ececec; }

[data-testid="stSidebar"] { background: #171717; border-right: 1px solid #2d2d2d; }
[data-testid="stSidebar"] * { color: #d4d4d4 !important; }
[data-testid="stSidebar"] button {
    text-align: left !important; justify-content: flex-start !important;
    border: none !important; background: transparent !important;
    color: #aaa !important; padding: 9px 14px !important;
    border-radius: 8px !important; font-size: 0.875rem !important;
    font-weight: 400 !important; transition: background 0.15s, color 0.15s;
}
[data-testid="stSidebar"] button:hover { background: #252525 !important; color: #fff !important; }
[data-testid="stSidebar"] button[kind="primary"] {
    background: #2f2f2f !important; color: #fff !important; font-weight: 500 !important;
}
[data-testid="stSidebar"] input {
    background: #2a2a2a !important; border: 1px solid #3d3d3d !important;
    border-radius: 8px !important; color: #ececec !important; font-size: 0.875rem !important;
}
[data-testid="stChatMessage"] { background: transparent !important; border: none !important; padding: 4px 0 !important; }
[data-testid="stChatInput"] { background: #212121 !important; border-top: 1px solid #2d2d2d !important; padding: 12px 0 8px !important; }
[data-testid="stChatInput"] textarea {
    background: #2a2a2a !important; border: 1px solid #3d3d3d !important;
    border-radius: 14px !important; color: #ececec !important;
    font-family: 'Noto Sans SC', sans-serif !important; font-size: 0.95rem !important;
    padding: 12px 18px !important; resize: none !important;
}
[data-testid="stChatInput"] textarea:focus { border-color: #555 !important; box-shadow: none !important; }
h1, h2, h3 { color: #fff !important; font-weight: 400 !important; }

[data-testid="stExpander"] {
    background: #1c1c1c !important; border: 1px solid #2d2d2d !important;
    border-radius: 10px !important; margin: 6px 0 !important;
}
[data-testid="stExpander"] summary { font-size: 0.875rem !important; color: #aaa !important; padding: 10px 14px !important; }

code {
    font-family: 'JetBrains Mono', monospace !important; background: #2a2a2a !important;
    border-radius: 5px !important; padding: 2px 7px !important;
    font-size: 0.83em !important; color: #e5c07b !important;
}
pre {
    margin: 16px 0 !important;
    clear: both;
    overflow-x: auto;
    border-radius: 8px !important;
    background: #1a1a1a !important;
    border: 1px solid #333 !important;
    padding: 14px !important;
}
pre code {
    /* pre 已经处理了边框和内边距，code 只负责字体和颜色 */
    background: transparent !important;
    color: #abb2bf !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 0 !important;
    font-size: inherit !important;
    display: block;
}
.live-box {
    margin-bottom: 20px !important;    /* 增加底部间距 */
}
hr { border-color: #2d2d2d !important; margin: 20px 0 !important; }

.badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 20px; font-size: 0.78rem;
    font-family: 'JetBrains Mono', monospace; margin: 4px 2px;
}
.badge-ok   { background:#1a2e1a; color:#4ade80; border:1px solid #2a4a2a; }
.badge-run  { background:#1a2040; color:#60a5fa; border:1px solid #2a3a60; }
.badge-err  { background:#2e1a1a; color:#f87171; border:1px solid #4a2a2a; }
.badge-done { background:#1e1a2e; color:#a78bfa; border:1px solid #3a2a4e; }

.live-box {
    background: #1a1f2e; border: 1px solid #2a3a60; border-radius: 10px;
    padding: 14px 18px; margin: 8px 0; min-height: 40px;
    font-size: 0.95rem; line-height: 1.7; color: #ececec;
    white-space: pre-wrap; word-break: break-word;
}
.cursor { display: inline-block; width: 2px; height: 1em; background: #60a5fa;
    vertical-align: middle; animation: blink 0.8s step-end infinite; margin-left: 1px; }
@keyframes blink { 50% { opacity: 0; } }

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #1a1a1a; }
::-webkit-scrollbar-thumb { background: #3a3a3a; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #4a4a4a; }
</style>
""", unsafe_allow_html=True)


# ================================================================
# 工具函数
# ================================================================
ROLE_ICON = {"coder": "💻", "reasoner": "🧠", "writer": "✍️", "aggregator": "🔗"}
PROJECTS_DIR = "projects"


# filter_json / parse_tasks / safe_name / stream_file / read_stream / is_done / cleanup
# 已移至 utils/ 通用库，顶部 import 处统一导入，此处不再重复定义。


# ================================================================
# Session state 初始化
# ================================================================
if "manager"       not in st.session_state:
    st.session_state.manager       = ProjectManager()
if "updater"       not in st.session_state:
    st.session_state.updater       = ModelConfigUpdater()
if "scheduler"     not in st.session_state:
    st.session_state.scheduler     = MultiAgentScheduler()
if "mode"          not in st.session_state:
    st.session_state.mode          = "chat"
if "show_new_form" not in st.session_state:
    st.session_state.show_new_form = False

manager: ProjectManager     = st.session_state.manager
updater: ModelConfigUpdater = st.session_state.updater

projects = manager.list_projects()
if not projects:
    manager.create_project("新对话")
    projects = manager.list_projects()
if manager.current_project is None:
    manager.switch_project(projects[0])


# ================================================================
# 侧边栏
# ================================================================
with st.sidebar:
    st.markdown("# AI Cluster")
    st.divider()

    new_mode = st.radio(
        "模式",
        options=["chat", "agent"],
        format_func=lambda x: "💬 普通对话" if x == "chat" else "⚡ Agent 集群",
        index=0 if st.session_state.mode == "chat" else 1,
        label_visibility="collapsed",
        key="mode_radio" 
    )
    if new_mode != st.session_state.mode:
        st.session_state.mode = new_mode
        st.rerun()

    st.divider()

    # ── 平台选择 ──────────────────────────────────────────────────
    st.markdown("<div style='font-size:0.78rem;color:#666;padding:2px 4px 6px;'>API 平台</div>",
                unsafe_allow_html=True)
    current_platform  = get_platform_mode()
    platform_options  = ["domestic", "foreign", "mixed"]
    new_platform = st.radio(
        "平台",
        options=platform_options,
        format_func=lambda x: MODE_LABELS[x],
        index=platform_options.index(current_platform),
        label_visibility="collapsed",
        key="platform_radio"
    )
    if new_platform != current_platform:
        set_platform_mode(new_platform)
        st.rerun()
    if new_platform == "mixed":
        with st.expander("⚙️ 角色路由", expanded=False):
            st.caption("在 platform_config.py 的 MIXED_ROUTING 里修改")
            for _r, _p in MIXED_ROUTING.items():
                _icon = ROLE_ICON.get(_r, "⚙️")
                _badge = "🇨🇳" if _p == "domestic" else "🌐"
                st.markdown(f"{_icon} `{_r}` → {_badge} {_p}")

    st.divider()

    # 新建对话
    if not st.session_state.show_new_form:
        if st.button("➕ 新对话", use_container_width=True):
            st.session_state.show_new_form = True
            st.rerun()
    else:
        new_name = st.text_input("名称", placeholder="输入名称…",
                                 label_visibility="collapsed",
                                 key="new_chat_name_input")
        col_ok, col_cancel = st.columns(2)
        with col_ok:
            if st.button("✓ 创建", use_container_width=True, type="primary"):
                name = new_name.strip() or f"对话 {len(manager.list_projects()) + 1}"
                base, suf = name, 1
                while name in manager.list_projects():
                    name = f"{base} ({suf})"; suf += 1
                manager.create_project(name)
                manager.switch_project(name)
                st.session_state.show_new_form = False
                st.rerun()
        with col_cancel:
            if st.button("✕ 取消", use_container_width=True):
                st.session_state.show_new_form = False
                st.rerun()

    st.markdown("<div style='font-size:0.78rem;color:#666;padding:6px 4px 4px;'>历史对话</div>",
                unsafe_allow_html=True)

    current_name = manager.current_project.name if manager.current_project else ""
    for p_name in reversed(manager.list_projects()):
        label = (p_name[:22] + "…") if len(p_name) > 22 else p_name
        # 检查是否有正在进行的任务
        is_streaming = False
        try:
            with open(os.path.join(PROJECTS_DIR, f"{p_name}.json"), encoding="utf-8") as _f:
                pd = json.load(_f)
            is_streaming = bool(pd.get("agent_state")) or bool(pd.get("chat_stream"))
        except Exception:
            pass
        btn_label = f"{'⚡' if is_streaming else '💬'} {label}"
        btype = "primary" if p_name == current_name else "secondary"
        if st.button(btn_label, key=f"p_{p_name}", use_container_width=True, type=btype):
            manager.switch_project(p_name)
            st.rerun()

    st.divider()

    if st.button("🗑️ 删除当前对话", use_container_width=True):
        if manager.current_project:
            name = manager.current_project.name
            manager.delete_project(name)
            remaining = manager.list_projects()
            if remaining:
                manager.switch_project(remaining[-1])
            else:
                manager.create_project("新对话")
                manager.switch_project("新对话")
            st.rerun()

    st.divider()

    if st.button("🔄 更新模型配置", use_container_width=True):
        with st.spinner("搜索最新评测中…"):
            updater.update(force=True)
        st.success("配置已更新！")

    with st.expander("📊 当前模型配置"):
        mapping = updater.config.get("default_mapping", {})
        if mapping:
            for role, mid in mapping.items():
                st.markdown(f"{ROLE_ICON.get(role,'⚙️')} `{role}` → `{mid.split('/')[-1]}`")
        else:
            st.markdown("_暂无配置_")
        st.caption(f"更新于 {updater.config.get('last_update','未知')}")


# ================================================================
# 主区域头部
# ================================================================
proj = manager.current_project

col_title, col_mode = st.columns([5, 1])
with col_title:
    st.markdown(f"<h3 style='margin:0;padding:8px 0 4px;'>{proj.name}</h3>",
                unsafe_allow_html=True)
with col_mode:
    badge_cls  = "badge-run" if st.session_state.mode == "agent" else "badge-ok"
    badge_text = "⚡ Agent"  if st.session_state.mode == "agent" else "💬 Chat"
    st.markdown(
        f"<div style='text-align:right;padding-top:14px;'>"
        f"<span class='badge {badge_cls}'>{badge_text}</span></div>",
        unsafe_allow_html=True
    )
st.divider()

# 渲染已保存的历史消息
for msg in proj.history:
    clean = filter_json(msg["content"])
    if not clean:
        continue
    with st.chat_message(msg["role"]):
        st.markdown(clean)


# ================================================================
# 实时流显示区（核心：切换对话后回来继续轮询）
# ================================================================

def show_live(label: str, content: str, done: bool):
    """渲染实时输出块，完成后用 markdown 正常渲染"""
    with st.expander(label, expanded=not done):
        if done:
            # 完成后交给 Streamlit markdown 渲染，代码块/表格等正常显示
            st.markdown(content)
        else:
            # 流进行中：纯文本 + 光标动画
            cursor = "<span class='cursor'></span>"
            st.markdown(
                f"<div class='live-box'>{content}{cursor}</div>",
                unsafe_allow_html=True
            )


is_streaming_now = False   # 当前是否正在轮询，用于控制 chat_input 显示

# ─── 普通对话 流轮询 ──────────────────────────────────────────────
if proj.chat_stream:
    cs        = proj.chat_stream
    file_path = cs["file"]
    content   = read_stream(file_path)
    done      = is_done(file_path)
    short     = cs["model"].split("/")[-1]

    with st.chat_message("assistant"):
        label = f"✓ 回复 · {short}" if done else f"⟳ 思考中 · {short}"
        show_live(label, content, done)

    if done:
        cleanup(file_path)
        manager.add_message("user",      cs["user_input"])
        manager.add_message("assistant", filter_json(content))
        proj.chat_stream = None
        manager._save_project(proj)
        st.rerun()
    else:
        is_streaming_now = True
        time.sleep(0.5)
        st.rerun()


# ─── Agent 流轮询 ─────────────────────────────────────────────────
elif proj.agent_state:
    state = proj.agent_state

    # 显示已完成的子任务结果
    for r in state.get("completed_display", []):
        with st.chat_message("assistant"):
            with st.expander(f"✓ {r['task_id']} 完成 · {r['model_short']}", expanded=False):
                st.markdown(r["content"])

    # ── 状态机路由 ──────────────────────────────────────────────────
    # 【P0 修复】summary_streaming 必须最先判断。
    # 原版把它放在最后一个 elif，但通用 current_stream handler 会先「抢走」
    # 总结流来处理，处理完后 current_stream=None，轮到 summary_streaming 时
    # 什么都不做 → add_message 永远不调用 → Agent 死锁。

    if state.get("phase") == "summary_streaming":
        # 总结阶段有专属的完成处理逻辑，不能让通用 handler 代劳
        cs = state.get("current_stream")
        if cs:
            file_path = cs["file"]
            content   = read_stream(file_path)
            done      = is_done(file_path)
            short     = cs["model"].split("/")[-1]

            with st.chat_message("assistant"):
                st.divider()
                label = f"✓ 整合完成 · {short}" if done else f"🔗 整合结果 · {short} ⟳"
                show_live(label, content, done)

            if done:
                cleanup(file_path)
                manager.add_message("user",      state.get("user_input", ""))
                manager.add_message("assistant", filter_json(content))
                proj.agent_state = None
                manager._save_project(proj)
                st.rerun()
            else:
                is_streaming_now = True
                time.sleep(0.3)
                st.rerun()

    elif state.get("current_stream"):
        # 通用子任务流轮询（只在 phase=="tasks" 期间会走到这里）
        cs        = state["current_stream"]
        file_path = cs["file"]
        content   = read_stream(file_path)
        done      = is_done(file_path)
        icon      = ROLE_ICON.get(cs["role"], "⚙️")
        short     = cs["model"].split("/")[-1]

        with st.chat_message("assistant"):
            label = f"✓ {cs['task_id']} 完成 · {short}" if done \
                    else f"{icon} {cs['task_id']} · {cs['role']} · {short} ⟳"
            show_live(label, content, done)

        if done:
            cleanup(file_path)
            state.setdefault("completed_display", []).append({
                "task_id":     cs["task_id"],
                "model_short": short,
                "content":     content
            })
            state["results"][cs["task_id"]] = content
            state["all_output"].append(content)
            state["current_stream"] = None
            manager._save_project(proj)
            st.rerun()
        else:
            is_streaming_now = True
            time.sleep(0.3)
            st.rerun()

    elif state.get("phase") == "tasks":
        # 没有当前流 → 找下一个可执行任务
        tasks   = state["tasks"]
        results = state["results"]
        pending = [t for t in tasks if t["task_id"] not in results]

        if pending:
            executable = [t for t in pending
                          if all(d in results for d in t.get("depends_on", []))]
            if not executable:
                st.markdown(
                    "<span class='badge badge-err'>✗ 依赖死锁，请放弃任务</span>",
                    unsafe_allow_html=True
                )
            else:
                task    = executable[0]
                task_id = task["task_id"]
                role    = task["role"]
                model   = updater.get_best_model(role)
                prompt  = task["prompt"]
                for dep in task.get("depends_on", []):
                    prompt = prompt.replace(f"{{{{{dep}}}}}", results.get(dep, ""))

                fpath = stream_file(proj.name, task_id)
                cancel_evt = register_cancel(fpath)
                call_model_stream_to_file(model, fpath, prompt, role=role,
                                         cancel_event=cancel_evt)
                state["current_stream"] = {
                    "task_id": task_id, "role": role,
                    "model": model, "file": fpath
                }
                manager._save_project(proj)
                is_streaming_now = True
                time.sleep(0.2)
                st.rerun()
        else:
            state["phase"] = "summary"
            manager._save_project(proj)
            st.rerun()

    elif state.get("phase") == "summary":
        # 启动总结（current_stream 此时一定为 None）
        summary_model  = updater.get_best_model("aggregator")
        user_input     = state.get("user_input", "")
        summary_prompt = (
            f"用户原始问题：{user_input}\n\n"
            + "\n\n".join(
                f"子任务{i+1}结果：\n{r}"
                for i, r in enumerate(state.get("all_output", []))
            )
            + "\n\n请整合所有子任务结果，给出简洁连贯的最终答案。不要重复子任务细节。"
        )
        fpath = stream_file(proj.name, "summary")
        cancel_evt = register_cancel(fpath)
        call_model_stream_to_file(summary_model, fpath, summary_prompt,
                                 role="aggregator", cancel_event=cancel_evt)
        state["current_stream"] = {
            "task_id": "总结", "role": "aggregator",
            "model": summary_model, "file": fpath
        }
        state["phase"] = "summary_streaming"
        manager._save_project(proj)
        is_streaming_now = True
        time.sleep(0.5)
        st.rerun()



# ================================================================
# 输入区（流式进行中时禁用）
# ================================================================
if is_streaming_now:
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("⏹️ 停止", use_container_width=True):
            proj = manager.current_project

            if proj.chat_stream:
                # 通知线程停止（线程会自行清理临时文件）
                cancel_stream(proj.chat_stream["file"])
                cleanup(proj.chat_stream["file"])   # 兜底：确保即使线程还没反应文件也清掉
                proj.chat_stream = None

            if proj.agent_state:
                cs = proj.agent_state.get("current_stream")
                if cs:
                    cancel_stream(cs["file"])
                    cleanup(cs["file"])

                #把已完成的子任务内容存入历史，停止后用户仍能看到
                completed = proj.agent_state.get("completed_display", [])
                if completed:
                    user_q   = proj.agent_state.get("user_input", "（Agent任务）")
                    partial  = "\n\n".join(
                        f"**{r['task_id']}**（{r['model_short']}）：\n{r['content']}"
                        for r in completed
                    )
                    manager.add_message("user", user_q)
                    manager.add_message(
                        "assistant",
                        f"⚠️ 任务已手动停止，以下是已完成的子任务结果：\n\n{partial}"
                    )

                proj.agent_state = None

            manager._save_project(proj)
            st.rerun()
    with col2:
        st.caption("任务进行中，点击停止可终止")
else:
    placeholder_text = {
        "chat":  "有什么可以帮你…",
        "agent": "描述一个复杂任务，Agent 集群自动拆解执行…",
    }.get(st.session_state.mode, "输入指令…")
    if user_input := st.chat_input(placeholder_text):


        # ─── 普通对话 ───────────────────────────────────────────
        if st.session_state.mode == "chat":
            model   = updater.get_best_model("writer")
            context = manager.get_context()
            prompt  = f"{context}\n用户: {user_input}\n助手:"
            fpath   = stream_file(proj.name, "chat")

            cancel_evt = register_cancel(fpath)          # P1: 注册取消事件
            call_model_stream_to_file(
                model, fpath, prompt,
                system_prompt="你是一个有帮助的AI助手，请基于对话历史回答用户问题。",
                role="writer",
                cancel_event=cancel_evt                  # P1: 传入线程
            )
            proj.chat_stream = {
                "file":       fpath,
                "model":      model,
                "user_input": user_input
            }
            manager._save_project(proj)
            st.rerun()

        # ─── Agent 集群 ─────────────────────────────────────────
        elif st.session_state.mode == "agent":
            # 分解任务
            with st.chat_message("assistant"):
                st.markdown(
                    "<span class='badge badge-run'>⟳ 正在分解任务…</span>",
                    unsafe_allow_html=True
                )
            decompose_model  = updater.get_best_model("reasoner")
            decompose_prompt = f"""
请将以下用户任务分解成多个子任务，输出JSON数组。
每个子任务包含：
- task_id: 唯一标识（如 task1, task2）
- role: coder / reasoner / writer / aggregator
- prompt: 具体指令，可用 {{{{task_id}}}} 引用前序结果
- depends_on: 依赖的task_id列表，没有则填 []

用户任务：{user_input}

只输出JSON数组，不要其他文字。
"""
            raw   = call_model(decompose_model, decompose_prompt,
                               temperature=0.2, max_tokens=2500, role="reasoner")
            tasks = parse_tasks(raw)

            if not tasks:
                with st.chat_message("assistant"):
                    st.markdown(
                        "<span class='badge badge-err'>✗ 分解失败，降级为普通对话</span>",
                        unsafe_allow_html=True
                    )
                    model = updater.get_best_model("writer")
                    fpath = stream_file(proj.name, "chat")
                    cancel_evt = register_cancel(fpath)
                    call_model_stream_to_file(model, fpath, user_input, role="writer",
                                             cancel_event=cancel_evt)
                    proj.chat_stream = {"file": fpath, "model": model, "user_input": user_input}
                    manager._save_project(proj)
                    st.rerun()

            else:
                with st.chat_message("assistant"):
                    st.markdown(
                        f"<span class='badge badge-ok'>✓ 已分解为 {len(tasks)} 个子任务</span>",
                        unsafe_allow_html=True
                    )
                    with st.expander(f"📋 任务计划（共 {len(tasks)} 个）", expanded=True):
                        for t in tasks:
                            icon  = ROLE_ICON.get(t.get("role", ""), "⚙️")
                            deps  = t.get("depends_on", [])
                            dep_s = f"  ← {', '.join(deps)}" if deps else ""
                            st.markdown(f"{icon} **{t['task_id']}** `{t.get('role','')}`{dep_s}")
                            preview = t.get("prompt", "")
                            st.caption(preview[:120] + ("…" if len(preview) > 120 else ""))

                # 初始化 agent_state，然后 rerun 进入轮询循环
                proj.agent_state = {
                    "tasks":             tasks,
                    "results":           {},
                    "all_output":        [],
                    "completed_display": [],
                    "current_stream":    None,
                    "phase":             "tasks",
                    "user_input":        user_input
                }
                manager._save_project(proj)
                st.rerun()