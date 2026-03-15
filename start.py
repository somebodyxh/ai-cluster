#!/usr/bin/env python3
"""
AI Cluster 启动脚本 — 全平台通用
用法：python start.py [--dev] [--port 8000] [--skip-build] [--help]
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ── 颜色输出（Windows 10+ / Unix 通用）────────────────────────────────────────
if sys.platform == "win32":
    os.system("")   # 开启 Windows 终端 ANSI 支持

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"

def info(msg):   print(f"{CYAN}[INFO]{RESET}  {msg}")
def ok(msg):     print(f"{GREEN}[OK]{RESET}    {msg}")
def warn(msg):   print(f"{YELLOW}[WARN]{RESET}  {msg}")
def error(msg):  print(f"{RED}[ERROR]{RESET} {msg}")
def title(msg):  print(f"\n{BOLD}{CYAN}{msg}{RESET}")

# ── 路径 ──────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).parent.resolve()
FRONTEND = ROOT / "frontend"
DIST     = FRONTEND / "dist"
SECRETS  = ROOT / "secrets.json"

# ── 参数解析 ──────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="AI Cluster 启动脚本")
    p.add_argument("--dev",         action="store_true", help="开发模式：前后端分别热重载")
    p.add_argument("--port",        type=int, default=8000, help="后端端口（默认 8000）")
    p.add_argument("--skip-build",  action="store_true", help="跳过前端构建（已有 dist/ 时使用）")
    p.add_argument("--no-browser",  action="store_true", help="启动后不自动打开浏览器")
    return p.parse_args()

# ── 工具函数 ──────────────────────────────────────────────────────────────────
def run(cmd, cwd=None, env=None):
    """执行命令，支持字符串或列表，实时输出，失败时退出。"""
    if isinstance(cmd, str):
        # 对于字符串，使用 shell=True（但注意路径中的特殊字符需要转义）
        proc = subprocess.run(
            cmd, shell=True, cwd=cwd or ROOT,
            env={**os.environ, **(env or {})}
        )
    else:
        # 对于列表，使用 shell=False，安全处理特殊字符
        proc = subprocess.run(
            cmd, shell=False, cwd=cwd or ROOT,
            env={**os.environ, **(env or {})}
        )
    if proc.returncode != 0:
        error(f"命令失败（exit {proc.returncode}）：{cmd}")
        sys.exit(1)

def check_command(cmd, install_hint):
    """检查命令是否存在，不存在则提示安装并退出。"""
    if not shutil.which(cmd.split()[0]):
        error(f"未找到 {cmd.split()[0]}，请先安装：{install_hint}")
        sys.exit(1)
    return True

def port_in_use(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

def open_browser(url, delay=1.5):
    """延迟打开浏览器，等服务器就绪。"""
    import threading, webbrowser
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()

# ── 检查步骤 ──────────────────────────────────────────────────────────────────
def check_python_deps():
    title("1/4  检查 Python 依赖")
    missing = []
    for pkg, import_name in [
        ("fastapi",         "fastapi"),
        ("uvicorn",         "uvicorn"),
        ("openai",          "openai"),
        ("tavily-python",   "tavily"),
    ]:
        try:
            __import__(import_name)
            ok(f"  {pkg}")
        except ImportError:
            warn(f"  {pkg}  ← 未安装")
            missing.append(pkg)

    if missing:
        info(f"正在安装缺失依赖：{' '.join(missing)}")
        # 用列表传参，不走 shell，路径里有括号/空格也不会出错
        result = subprocess.run([sys.executable, "-m", "pip", "install"] + missing)
        if result.returncode != 0:
            error("依赖安装失败，请手动运行：pip install " + " ".join(missing))
            sys.exit(1)
        ok("依赖安装完成")

def check_secrets():
    title("2/4  检查密钥配置")
    if SECRETS.exists():
        ok(f"secrets.json 已存在：{SECRETS}")
    else:
        warn("未找到 secrets.json，首次运行将在启动后提示输入。")

def build_frontend(skip_build):
    title("3/4  检查前端")

    if not FRONTEND.exists():
        error(f"未找到 frontend/ 目录：{FRONTEND}")
        sys.exit(1)

    check_command("node", "https://nodejs.org")
    check_command("npm",  "https://nodejs.org")

    node_modules = FRONTEND / "node_modules"
    if not node_modules.exists():
        info("安装前端依赖（npm install）...")
        run("npm install", cwd=FRONTEND)
        ok("npm install 完成")
    else:
        ok("node_modules 已存在，跳过 install")

    if skip_build and DIST.exists():
        ok(f"跳过构建，使用已有 dist/（--skip-build）")
        return

    if DIST.exists() and not skip_build:
        # dist 存在但源码可能更新，给用户选择
        info("dist/ 已存在。")

    info("构建前端（npm run build）...")
    run("npm run build", cwd=FRONTEND)
    ok("前端构建完成")

def check_port(port):
    title("4/4  检查端口")
    if port_in_use(port):
        error(f"端口 {port} 已被占用！")
        info("请用 --port 指定其他端口，例如：python start.py --port 8080")
        sys.exit(1)
    ok(f"端口 {port} 可用")

# ── 启动模式 ──────────────────────────────────────────────────────────────────
def start_production(port, no_browser):
    """生产模式：uvicorn 托管前端静态文件。"""
    url = f"http://localhost:{port}"
    print(f"\n{BOLD}{GREEN}{'─'*50}{RESET}")
    print(f"{BOLD}  🚀  AI Cluster 启动中{RESET}")
    print(f"  地址：{BOLD}{url}{RESET}")
    print(f"  停止：Ctrl + C")
    print(f"{BOLD}{GREEN}{'─'*50}{RESET}\n")

    if not no_browser:
        open_browser(url, delay=2.0)

    run(
        [sys.executable, "-m", "uvicorn", "backend.app:app",
         "--host", "0.0.0.0", "--port", str(port)],
        cwd=ROOT
    )

def start_dev(port, no_browser):
    """开发模式：后端 --reload + 前端 vite dev server 并行运行。"""
    import threading

    vite_port = port + 1

    print(f"\n{BOLD}{YELLOW}{'─'*50}{RESET}")
    print(f"{BOLD}  🛠   AI Cluster 开发模式{RESET}")
    print(f"  后端 API：{BOLD}http://localhost:{port}{RESET}")
    print(f"  前端 Dev：{BOLD}http://localhost:{vite_port}{RESET}  ← 打开这个")
    print(f"  停止：Ctrl + C")
    print(f"{BOLD}{YELLOW}{'─'*50}{RESET}\n")

    if not no_browser:
        open_browser(f"http://localhost:{vite_port}", delay=3.0)

    backend_cmd = (
        f"{sys.executable} -m uvicorn backend.app:app "
        f"--host 0.0.0.0 --port {port} --reload"
    )
    frontend_cmd = f"npm run dev -- --port {vite_port}"

    backend_proc  = None
    frontend_proc = None

    try:
        backend_proc  = subprocess.Popen(backend_cmd,  shell=True, cwd=ROOT)
        frontend_proc = subprocess.Popen(frontend_cmd, shell=True, cwd=FRONTEND)

        # 等待任意一个进程退出
        while True:
            if backend_proc.poll()  is not None: break
            if frontend_proc.poll() is not None: break
            time.sleep(0.5)

    except KeyboardInterrupt:
        info("收到 Ctrl+C，正在停止...")
    finally:
        for proc in [backend_proc, frontend_proc]:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        ok("已停止")

# ── 主入口 ────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    print(f"\n{BOLD}{CYAN}⚡ AI Cluster 启动脚本{RESET}")
    print(f"   平台：{sys.platform}  Python：{sys.version.split()[0]}\n")

    check_python_deps()
    check_secrets()

    if args.dev:
        # 开发模式不需要构建 dist
        title("3/4  跳过前端构建（开发模式）")
        check_command("node", "https://nodejs.org")
        node_modules = FRONTEND / "node_modules"
        if not node_modules.exists():
            info("安装前端依赖（npm install）...")
            run("npm install", cwd=FRONTEND)
    else:
        build_frontend(args.skip_build)

    check_port(args.port)

    if args.dev:
        start_dev(args.port, args.no_browser)
    else:
        start_production(args.port, args.no_browser)


if __name__ == "__main__":
    main()