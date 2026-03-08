"""
debug.py - 全局调试日志模块
在任何文件里 from debug import log 即可使用
"""
import time
import sys
import threading
from datetime import datetime

# ── ANSI 颜色 ──────────────────────────────────────────────────────
_C = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "dim":    "\033[2m",
    "red":    "\033[91m",
    "green":  "\033[92m",
    "yellow": "\033[93m",
    "blue":   "\033[94m",
    "magenta":"\033[95m",
    "cyan":   "\033[96m",
    "white":  "\033[97m",
    "gray":   "\033[90m",
}

# ── 模块标签颜色 ────────────────────────────────────────────────────
_TAG_COLOR = {
    "API":      "cyan",
    "STREAM":   "blue",
    "AGENT":    "magenta",
    "FRONTEND": "green",
    "PROJECT":  "yellow",
    "UPDATER":  "gray",
    "ERROR":    "red",
    "INFO":     "white",
}

_lock = threading.Lock()


def _color(text: str, name: str) -> str:
    return f"{_C.get(name,'')}{text}{_C['reset']}"


def log(tag: str, msg: str, detail: str = ""):
    """
    tag   : API / STREAM / AGENT / FRONTEND / PROJECT / UPDATER / ERROR / INFO
    msg   : 主要信息
    detail: 可选补充（灰色小字）
    """
    now    = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    tid    = threading.current_thread().name
    color  = _TAG_COLOR.get(tag.upper(), "white")
    tag_s  = _color(f"[{tag.upper():8s}]", color)
    time_s = _color(now, "dim")
    tid_s  = _color(f"({tid})", "dim")
    detail_s = f"  {_color(detail, 'gray')}" if detail else ""

    line = f"{time_s} {tag_s} {msg}{detail_s} {tid_s}"
    with _lock:
        print(line, flush=True)


def log_api_call(model: str, prompt_preview: str, stream: bool, max_tokens: int):
    log("API", f"▶ {_color(model.split('/')[-1], 'cyan')}",
        f"stream={stream} max_tokens={max_tokens} prompt={repr(prompt_preview[:80])}")


def log_api_done(model: str, length: int, elapsed: float):
    log("API", f"✓ {_color(model.split('/')[-1], 'cyan')}",
        f"输出 {length} 字符  耗时 {elapsed:.2f}s")


def log_api_error(model: str, error: str):
    log("ERROR", f"✗ {_color(model.split('/')[-1], 'cyan')}  {error}")


def log_stream(tag_id: str, chunk_len: int, total: int, done: bool):
    status = _color("DONE", "green") if done else _color("...", "blue")
    log("STREAM", f"{tag_id}  +{chunk_len}字  共{total}字  {status}")


def log_frontend(event: str, detail: str = ""):
    log("FRONTEND", event, detail)


def log_agent(event: str, detail: str = ""):
    log("AGENT", event, detail)


def log_project(event: str, detail: str = ""):
    log("PROJECT", event, detail)