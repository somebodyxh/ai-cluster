"""
API/OpenRouter_Api.py - OpenRouter API 封装模块
================================================
接口与 SiliconCloud_Api.py 完全一致，可直接替换。

OpenRouter 是一个 API 聚合平台，用同一个接口访问：
    - OpenAI：gpt-4o、gpt-4o-mini、o1
    - Anthropic：claude-3-5-sonnet、claude-3-opus
    - Google：gemini-pro、gemini-flash
    - Meta：llama-3.1-70b 等开源模型
    - 更多...

模型 ID 格式：  "vendor/model-name"
    如：   "openai/gpt-4o"
           "anthropic/claude-3-5-sonnet"
           "google/gemini-pro-1.5"

文档：https://openrouter.ai/docs

【Bug 修复】原版没有检查 OpenRouter_KEY 是否为空，
空字符串会被 OpenAI SDK 当作无效密钥，导致 401 错误且报错信息不直观。
现在在 get_client() 里加入检查，KEY 为空时立即给出清晰提示。
"""

import os
import threading
import time
from openai import OpenAI
from main.Json import OpenRouter_KEY
from debug import log, log_api_call, log_api_done, log_api_error, log_stream


# 延迟初始化的客户端单例（第一次调用时创建，避免启动时校验 KEY）
_client: OpenAI | None = None


def get_client() -> OpenAI:
    """
    获取 OpenRouter 客户端单例。

    【Bug 修复】加入 KEY 非空检查：
    如果 secrets.json 里没有填 OpenRouter_KEY，
    原版会用空字符串初始化客户端，调用时报 401 且不说明原因。
    现在提前检测并给出明确提示。

    单例模式：多次调用只创建一个客户端实例（节省连接开销）。
    """
    global _client

    # 【Bug 修复】KEY 为空时给出明确提示，而不是等到调用时才 401
    if not OpenRouter_KEY:
        raise RuntimeError(
            "[OpenRouter] API Key 未配置！\n"
            "请在 secrets.json 的 Api_Key 中添加 'openrouter_key' 字段，\n"
            "或者在平台选择器中切换到「国内」模式。"
        )

    if _client is None:
        log("API", "初始化 OpenRouter 客户端", "base_url=https://openrouter.ai/api/v1")
        _client = OpenAI(
            api_key=OpenRouter_KEY,
            base_url="https://openrouter.ai/api/v1"
        )
    return _client


def call_model_stream_to_file(model: str, file_path: str, prompt: str,
                               system_prompt: str = "", temperature: float = 0.7,
                               max_tokens: int = 2000,
                               cancel_event: threading.Event = None,
                               **kwargs) -> None:
    """
    后台线程流式调用，将 chunk 实时写入文件。
    cancel_event : 由 stream_utils.register_cancel() 创建并传入，收到信号后停止写入并清理临时文件。
    """
    log_api_call(model, prompt, stream=True, max_tokens=max_tokens)
    log("STREAM", f"后台线程启动 [OpenRouter] → {file_path}")

    def _run():
        from utils.stream_utils import clear_cancel
        client    = get_client()
        t_start   = time.time()
        total     = 0
        cancelled = False
        try:
            open(file_path, 'w', encoding='utf-8').close()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                timeout=360,
            )
            with open(file_path, 'a', encoding='utf-8') as f:
                for chunk in response:
                    if cancel_event and cancel_event.is_set():
                        cancelled = True
                        log("STREAM", f"收到取消信号，停止写入 [OpenRouter] → {file_path}")
                        break
                    if not chunk.choices:
                        continue
                    content = chunk.choices[0].delta.content
                    if content:
                        f.write(content)
                        f.flush()
                        total += len(content)
                        if total % 200 < len(content):
                            log_stream(file_path.split('/')[-1], len(content), total, done=False)

            if not cancelled:
                log_api_done(model, total, time.time() - t_start)
                log_stream(file_path.split('/')[-1], 0, total, done=True)

        except Exception as e:
            log_api_error(model, str(e))
            if not cancelled:
                try:
                    with open(file_path, 'a', encoding='utf-8') as f:
                        f.write(f"\n[错误] {e}")
                except Exception:
                    pass
        finally:
            clear_cancel(file_path)
            if cancelled:
                for p in [file_path, file_path + '.done']:
                    try:
                        os.remove(p)
                    except Exception:
                        pass
                log("STREAM", "已取消，临时文件已清理 [OpenRouter]")
            else:
                open(file_path + '.done', 'w').close()
                log("STREAM", "写入 .done 标记 [OpenRouter]")

    threading.Thread(
        target=_run, daemon=True,
        name=f"stream-or-{model.split('/')[-1][:15]}"
    ).start()


def call_model_stream_gen(model: str, prompt: str, system_prompt: str = "",
                          temperature: float = 0.7, max_tokens: int = 2000,
                          **kwargs):
    """
    流式生成器，供 st.write_stream() 使用。
    每个 chunk 是一个字符串片段，Streamlit 会把它们实时拼接显示。
    """
    log_api_call(model, prompt, stream=True, max_tokens=max_tokens)
    client  = get_client()
    t_start = time.time()
    total   = 0
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            timeout=360,
        )
        for chunk in response:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                total += len(content)
                yield content
        log_api_done(model, total, time.time() - t_start)
    except Exception as e:
        log_api_error(model, str(e))
        yield f"[错误] 调用模型失败: {str(e)}"


def call_model_stream(model: str, prompt: str, system_prompt: str = "",
                      temperature: float = 0.7, max_tokens: int = 2000,
                      **kwargs) -> str:
    """
    流式调用，结果打印到终端（CLI / scheduler 命令行模式使用）。
    返回完整的输出字符串。
    """
    log_api_call(model, prompt, stream=True, max_tokens=max_tokens)
    client  = get_client()
    t_start = time.time()
    full    = ""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            timeout=360,
        )
        for chunk in response:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                print(content, end="", flush=True)
                full += content
        print()
        log_api_done(model, len(full), time.time() - t_start)
        return full
    except Exception as e:
        log_api_error(model, str(e))
        return f"[错误] 调用失败：{str(e)}"


def call_model(model: str, prompt: str, system_prompt: str = "",
               temperature: float = 0.7, max_tokens: int = 2000,
               **kwargs) -> str:
    """
    非流式调用，等待完整响应后返回。
    适合需要解析 JSON 的场景（如任务分解、模型配置更新），
    因为流式返回的 JSON 可能被截断导致解析失败。
    """
    log_api_call(model, prompt, stream=False, max_tokens=max_tokens)
    client  = get_client()
    t_start = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            timeout=360,
        )
        result = response.choices[0].message.content
        log_api_done(model, len(result), time.time() - t_start)
        return result
    except Exception as e:
        log_api_error(model, str(e))
        return f"[错误] 调用失败：{str(e)}"


def list_models() -> list:
    """
    列出 OpenRouter 当前可用的所有模型 ID。
    auto_updater.py 的 validate_and_clean() 用这个来验证模型 ID 是否存在。
    失败时返回空列表（不抛异常，让调用方决定如何处理）。
    """
    log("API", "list_models() [OpenRouter]")
    client = get_client()
    try:
        ids = [m.id for m in client.models.list().data]
        log("API", f"OpenRouter 返回 {len(ids)} 个模型")
        return ids
    except Exception as e:
        log_api_error("list_models [OpenRouter]", str(e))
        return []