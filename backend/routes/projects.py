"""
backend/routes/projects.py — 对话管理
"""
import os, glob
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.dependencies import manager
from utils.stream_utils import PROJECTS_DIR

router = APIRouter()


class CreateRequest(BaseModel):
    name: str


@router.get("/list")
def list_projects():
    return {"projects": manager.list_projects()}


@router.post("/create")
def create_project(req: CreateRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    try:
        manager.create_project(name)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/switch/{name}")
def switch_project(name: str):
    proj = manager.switch_project(name)
    if not proj:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"ok": True, "history": proj.history}


@router.delete("/delete/{name}")
def delete_project(name: str):
    # 清理该对话遗留的所有流临时文件
    pattern = os.path.join(PROJECTS_DIR, f".stream_{name}*")
    for f in glob.glob(pattern):
        try:
            os.remove(f)
        except Exception:
            pass

    manager.delete_project(name)
    return {"ok": True}