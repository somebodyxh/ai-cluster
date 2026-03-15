"""
backend/app.py — FastAPI 主应用
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.routes import projects, chat, agent, config

# ── 路径 ──────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")

# ── 应用 ──────────────────────────────────────────────────────
app = FastAPI(title="AI Cluster API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type"],
)

# ── API 路由 ──────────────────────────────────────────────────
app.include_router(projects.router, prefix="/projects")
app.include_router(chat.router,     prefix="/chat")
app.include_router(agent.router,    prefix="/agent")
app.include_router(config.router,   prefix="/config")

# ── 前端静态文件 ──────────────────────────────────────────────
# 挂载 /assets 让 JS/CSS 走 StaticFiles（性能更好，自动处理 MIME 类型）
# 必须在通配路由之前挂载，否则会被通配路由拦截
_assets_dir = os.path.join(FRONTEND_DIST, "assets")
if os.path.isdir(_assets_dir):
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    # 防止路径遍历攻击
    if ".." in full_path:
        raise HTTPException(status_code=400, detail="Invalid path")

    # 请求的具体文件存在就直接返回（favicon.ico / robots.txt 等）
    file_path = os.path.join(FRONTEND_DIST, full_path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)

    # 其他一切（根路径 + 前端 History 路由）都返回 index.html
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)

    raise HTTPException(status_code=404, detail="Frontend not built. Run: npm run build")