"""
utils/stream_utils.py - 流文件操作通用库
=====================================
本项目的流式输出采用「后台线程写文件 + 前端轮询读文件」架构：
  1. 调用 call_model_stream_to_file() 启动后台线程，实时把 chunk 写入 .txt 文件
  2. 后台线程完成后创建同名 .done 标记文件
  3. 前端（app.py）每 0.3 秒读一次 .txt，检测 .done 是否存在来判断是否完成

本模块封装以上流程中所有文件路径计算和读写操作，
任何需要操作流文件的模块都应该 from utils.stream_utils import ... 而不是重复写这些逻辑。

使用示例：
    from utils.stream_utils import stream_file, read_stream, is_done, cleanup
    fpath = stream_file("我的项目", "chat")       # → "projects/.stream_我的项目_chat.txt"
    content = read_stream(fpath)                  # 读当前已写入内容（可能还在增长）
    if is_done(fpath):                            # 检查是否完成
        cleanup(fpath)                            # 删除 .txt 和 .done
"""

import os
import re
import threading


# ── 流文件存放目录（与 app.py 保持一致）─────────────────────────────
PROJECTS_DIR = "projects"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 用文件路径作 key，存每个流对应的 threading.Event。
# 启动线程前 register_cancel() 创建 Event，停止时 cancel_stream() set() 它。
# API 层在 chunk 循环里检查 Event，收到信号立即退出并清理临时文件。
_cancel_events: dict = {}
_events_lock = threading.Lock()


def register_cancel(file_path: str) -> threading.Event:
    """
    在启动后台线程前调用，为该流注册一个取消事件并返回它。
    返回的 Event 需要传给 call_model_stream_to_file()。

    示例：
        evt   = register_cancel(fpath)
        call_model_stream_to_file(model, fpath, prompt, cancel_event=evt)
    """
    evt = threading.Event()
    with _events_lock:
        _cancel_events[file_path] = evt
    return evt


def cancel_stream(file_path: str) -> bool:
    """
    通知后台线程停止。线程在下一个 chunk 边界检测到信号后退出，
    并自行清理 .txt 和 .done，不留孤儿文件。

    返回 True 表示找到了对应的 Event 并已 set()；False 表示线程可能已结束。
    """
    with _events_lock:
        evt = _cancel_events.get(file_path)
    if evt:
        evt.set()
        return True
    return False


def clear_cancel(file_path: str):
    """线程正常结束后，从注册表中移除 Event，防止内存无限增长。"""
    with _events_lock:
        _cancel_events.pop(file_path, None)


def safe_name(name: str) -> str:
    """
    将任意字符串转为安全的文件名片段。
    去掉所有非字母数字/连字符/下划线的字符，最长保留 40 个字符。

    例：safe_name("我的项目 v1.0!")  →  "____v1_0_"  （中文被替换为下划线）
    例：safe_name("my-project")     →  "my-project"

    为什么需要这个：项目名可能包含空格、中文、特殊符号，
    直接用作文件名在某些 OS 上会报错。
    """
    return re.sub(r'[^\w\-]', '_', name)[:40]


def stream_file(project_name: str, tag: str) -> str:
    """
    计算并返回流文件的完整路径。

    参数：
        project_name : 项目名（原始名称，内部会调用 safe_name 处理）
        tag          : 任务标识，用于区分同一项目的不同流
                       常用值：
                         "chat"    → 普通对话
                         "summary" → Agent 模式总结阶段
                         task_id   → Agent 子任务（如 "task1", "task2"）

    返回：
        形如 "projects/.stream_项目名_tag.txt" 的路径字符串
        文件名以点开头（.stream_...）是为了在文件列表里与正式项目 JSON 区分，
        并且在 Linux/Mac 上默认隐藏（ls 不显示），保持目录整洁。

    示例：
        stream_file("新对话", "chat")    → "projects/.stream_新对话_chat.txt"
        stream_file("代码任务", "task1") → "projects/.stream_代码任务_task1.txt"
    """
    return os.path.join(PROJECTS_DIR, f".stream_{safe_name(project_name)}_{tag}.txt")


def read_stream(path: str) -> str:
    """
    读取流文件的当前内容。

    注意：后台线程可能仍在写入，所以每次调用读到的内容长度不同。
    如果文件不存在（还没创建）或读取失败，返回空字符串而不是抛异常。
    这样前端可以放心地在轮询中调用，不会因文件暂时不存在而崩溃。
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ""


def is_done(path: str) -> bool:
    """
    检查流文件是否已写完。

    判断依据：是否存在同名 .done 文件（如 .stream_xxx.txt.done）。
    后台线程在写完所有 chunk 之后，会在 finally 块里 touch 这个标记文件。

    为什么不直接检查「文件是否停止增长」？
    因为那需要记录上次大小并等待一段时间，逻辑复杂且不可靠。
    用 .done 标记更明确、更健壮。
    """
    return os.path.exists(path + '.done')


def cleanup(path: str):
    """
    删除流文件和对应的 .done 标记文件。

    在流完成、内容已存入对话历史之后调用，避免残留临时文件。
    删除失败（文件已被删或权限问题）时静默忽略，不影响主流程。
    """
    for p in [path, path + '.done']:
        try:
            os.remove(p)
        except Exception:
            pass