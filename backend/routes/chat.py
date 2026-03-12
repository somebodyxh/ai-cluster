"""
backend/routes/chat.py — 普通对话（SSE 流式）
"""
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.dependencies import manager, updater
from API.router import call_model_stream_gen
from main.Json import Tavily_KEY

router = APIRouter()


class ChatRequest(BaseModel):
    project_name: str
    message: str
    web_search: bool = False


@router.post("/send")
def send_chat(req: ChatRequest):
    proj = manager.switch_project(req.project_name)
    if not proj:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="对话不存在")

    context = manager.get_context()
    model = updater.get_best_model("writer")

    # 构建 prompt，联网搜索时前置搜索结果
    prompt = f"{context}\n用户: {req.message}\n助手:"
    if req.web_search:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=Tavily_KEY)
            results = client.search(req.message, max_results=5)
            search_context = "\n".join(r["content"] for r in results["results"])
            prompt = (
                f"以下是联网搜索结果，请基于此回答：\n{search_context}\n\n"
                f"{context}\n用户: {req.message}\n助手:"
            )
        except Exception as e:
            # 搜索失败静默降级，不影响对话
            pass

    def stream_generator():
        full_response = ""
        failed = False

        try:
            for chunk in call_model_stream_gen(model, prompt, role="writer"):
                full_response += chunk
                # 用 JSON 编码 chunk，避免 chunk 内含换行符破坏 SSE 格式
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception:
            failed = True

        # 无论成功还是失败，只要有内容就存入历史
        # 放在 finally 外层保证一定执行
        if full_response:
            manager.add_message("user", req.message)
            manager.add_message("assistant", full_response)
            compressed = manager.add_message("assistant", full_response)

            if compressed:
                yield f"data: {json.dumps('[COMPRESSING]', ensure_ascii=False)}\n\n"
            


        yield f"data: {json.dumps('[DONE]')}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )