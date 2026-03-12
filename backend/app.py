"""
backend/app.py — FastAPI 主应用
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routes import projects, chat, agent, config

app = FastAPI(title="AI Cluster API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type"],  # SSE 需要前端能读到这个响应头
)

app.include_router(projects.router, prefix="/projects")
app.include_router(chat.router,     prefix="/chat")
app.include_router(agent.router,    prefix="/agent")
app.include_router(config.router,   prefix="/config")