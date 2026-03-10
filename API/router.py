"""
API/router.py - 统一路由层

现有代码把所有 import 改成从这里导入即可：
    from API.router import call_model, call_model_stream_gen, call_model_stream_to_file

路由逻辑完全由 platform_config.py 控制，对调用方透明。
"""

import API.SiliconCloud_Api as _domestic
import API.OpenRouter_Api   as _foreign
from platform_config import get_platform_for_role
from debug import log


def _pick(role: str):
    """根据角色和当前平台模式，返回对应的 API 模块"""
    platform = get_platform_for_role(role)
    if platform == "foreign":
        log("API", f"路由 role={role} → OpenRouter")
        return _foreign
    else:
        log("API", f"路由 role={role} → 硅基流动")
        return _domestic


# ── 对外接口（与原 SiliconCloud_Api.py 完全一致）─────────────────

def call_model(model: str, prompt: str, system_prompt: str = "",
               temperature: float = 0.7, max_tokens: int = 20000,
               role: str = "writer") -> str:
    return _pick(role).call_model(
        model, prompt, system_prompt, temperature, max_tokens
    )


def call_model_stream_gen(model, prompt, system_prompt="",
                          temperature=0.7, max_tokens=20000,
                          role: str = "writer"):
    yield from _pick(role).call_model_stream_gen(
        model, prompt, system_prompt, temperature, max_tokens
    )


def call_model_stream(model: str, prompt: str, system_prompt: str = "",
                      temperature: float = 0.7, max_tokens: int = 20000,
                      role: str = "writer") -> str:
    return _pick(role).call_model_stream(
        model, prompt, system_prompt, temperature, max_tokens
    )


def call_model_stream_to_file(model: str, file_path: str, prompt: str,
                               system_prompt: str = "", temperature: float = 0.7,
                               max_tokens: int = 20000, role: str = "writer",
                               cancel_event=None):
    """
    cancel_event : stream_utils.register_cancel() 返回的 threading.Event，
                   透传给底层 API 模块，实现真正的线程取消。
    """
    _pick(role).call_model_stream_to_file(
        model, file_path, prompt, system_prompt, temperature, max_tokens,
        cancel_event=cancel_event
    )


def list_models(platform: str = "domestic") -> list:
    if platform == "foreign":
        return _foreign.list_models()
    return _domestic.list_models()