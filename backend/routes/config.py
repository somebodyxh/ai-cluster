"""
backend/routes/config.py — 平台 & 模型配置
"""
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from backend.dependencies import updater
from platform_config import (
    get_platform_mode, set_platform_mode,
    MODE_LABELS, MIXED_ROUTING,
    DOMESTIC_FALLBACKS, FOREIGN_FALLBACKS,
)

router = APIRouter()


class PlatformRequest(BaseModel):
    mode: str  # "domestic" | "foreign" | "mixed"


@router.get("/platform/current")
def get_platform():
    mode = get_platform_mode()
    return {
        "mode":          mode,
        "label":         MODE_LABELS.get(mode, mode),
        "mixed_routing": MIXED_ROUTING if mode == "mixed" else {},
    }


@router.post("/platform/set")
def set_platform(req: PlatformRequest):
    if req.mode not in ("domestic", "foreign", "mixed"):
        return {"ok": False, "error": "无效的平台模式"}
    set_platform_mode(req.mode)
    return {"ok": True, "label": MODE_LABELS[req.mode]}


@router.get("/platform/options")
def get_options():
    return {
        "options": [
            {"value": k, "label": v} for k, v in MODE_LABELS.items()
        ],
        "current": get_platform_mode(),
    }


@router.get("/models/current")
def get_models():
    cfg = updater.config
    return {
        "last_update":     cfg.get("last_update", "未知"),
        "default_mapping": cfg.get("default_mapping", {}),
        "models":          cfg.get("models", []),
    }


@router.post("/models/update")
def update_models(background_tasks: BackgroundTasks):
    """
    模型更新是耗时操作（需调 Tavily + LLM），放到后台线程执行，
    接口立刻返回，不阻塞其他请求。
    """
    background_tasks.add_task(updater.update, force=True)
    return {"ok": True, "message": "模型配置更新已在后台启动，稍后刷新查看结果"}


@router.get("/models/fallbacks")
def get_fallbacks():
    return {"domestic": DOMESTIC_FALLBACKS, "foreign": FOREIGN_FALLBACKS}


@router.get("/status")
def get_status():
    return {
        "platform":       get_platform_mode(),
        "models_updated": updater.config.get("last_update", "未知"),
        "needs_update":   updater.needs_update(),
    }