"""
硅基流动API封装模块
"""
import threading
import time
from openai import OpenAI
from main.Json import SiliconCloud_KEY
from debug import log, log_api_call, log_api_done, log_api_error, log_stream

_client = None

def get_client():
    global _client
    if _client is None:
        log("API", "初始化 OpenAI 客户端", "base_url=https://api.siliconflow.cn/v1")
        _client = OpenAI(
            api_key=SiliconCloud_KEY,
            base_url="https://api.siliconflow.cn/v1"
        )
    return _client


def call_model_stream_to_file(model: str, file_path: str, prompt: str,
                               system_prompt: str = "", temperature: float = 0.7,
                               max_tokens: int = 2000):
    """后台线程流式调用，将 chunk 实时写入文件"""
    log_api_call(model, prompt, stream=True, max_tokens=max_tokens)
    log("STREAM", f"后台线程启动 → {file_path}")

    def _run():
        client  = get_client()
        t_start = time.time()
        total   = 0
        try:
            open(file_path, 'w', encoding='utf-8').close()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                timeout=360
            )
            with open(file_path, 'a', encoding='utf-8') as f:
                for chunk in response:
                    if not chunk.choices:
                        continue
                    content = chunk.choices[0].delta.content
                    if content:
                        f.write(content)
                        f.flush()
                        total += len(content)
                        if total % 200 < len(content):
                            log_stream(file_path.split('/')[-1], len(content), total, done=False)

            log_api_done(model, total, time.time() - t_start)
            log_stream(file_path.split('/')[-1], 0, total, done=True)

        except Exception as e:
            log_api_error(model, str(e))
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(f"\n[错误] {e}")
        finally:
            open(file_path + '.done', 'w').close()
            log("STREAM", f"写入 .done 标记")

    threading.Thread(target=_run, daemon=True,
                     name=f"stream-{model.split('/')[-1][:20]}").start()


def call_model_stream_gen(model, prompt, system_prompt="", temperature=0.7, max_tokens=2000):
    """生成器，供 st.write_stream 使用"""
    log_api_call(model, prompt, stream=True, max_tokens=max_tokens)
    client  = get_client()
    t_start = time.time()
    total   = 0
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            timeout=360
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
                      temperature: float = 0.7, max_tokens: int = 2000) -> str:
    log_api_call(model, prompt, stream=True, max_tokens=max_tokens)
    client  = get_client()
    t_start = time.time()
    full    = ""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            timeout=360
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
               temperature: float = 0.7, max_tokens: int = 2000) -> str:
    log_api_call(model, prompt, stream=False, max_tokens=max_tokens)
    client  = get_client()
    t_start = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            timeout=360
        )
        result = response.choices[0].message.content
        log_api_done(model, len(result), time.time() - t_start)
        return result
    except Exception as e:
        log_api_error(model, str(e))
        return f"[错误] 调用失败：{str(e)}"


def list_models():
    log("API", "list_models()")
    client = get_client()
    try:
        ids = [m.id for m in client.models.list().data]
        log("API", f"返回 {len(ids)} 个模型")
        return ids
    except Exception as e:
        log_api_error("list_models", str(e))
        return []
