"""
backend/app.py — FastAPI 主应用
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routes import projects, chat, agent, config
from fastapi.responses import FileResponse
from fastapi import FastAPI, HTTPException  # 添加 HTTPException


app = FastAPI(title="AI Cluster API")


# 获取项目根目录和前端构建目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type"],
)


app.include_router(projects.router, prefix="/projects")
app.include_router(chat.router,     prefix="/chat")
app.include_router(agent.router,    prefix="/agent")
app.include_router(config.router,   prefix="/config")

# 通配路由：处理所有前端静态文件和前端路由
@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    # 防止路径遍历攻击
    if ".." in full_path or full_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")
    
    # 构建完整的文件路径
    file_path = os.path.join(FRONTEND_DIST, full_path)
    
    # 如果是文件且存在，直接返回（自动设置正确的 MIME 类型）
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # 否则返回 index.html（支持前端 History 路由）
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    
    # 如果 index.html 也不存在，返回 404
    raise HTTPException(status_code=404, detail="Frontend not found")

# 添加根路径的快捷方式
@app.get("/")
async def root():
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {"message": "API is running, but frontend not built"}