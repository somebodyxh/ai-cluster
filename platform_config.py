"""
platform_config.py - 平台路由配置
===================================
放在项目根目录，是整个多平台路由系统的「总开关」。

职责：
    1. 存储并持久化当前平台模式（domestic / foreign / mixed）
    2. 定义混合模式下每个角色走哪个平台（MIXED_ROUTING）
    3. 提供各平台的兜底模型（DOMESTIC_FALLBACKS / FOREIGN_FALLBACKS）
    4. 供 router.py / app.py / auto_updater.py 统一查询

平台模式说明：
    "domestic"  → 所有角色全部走硅基流动（国内，便宜，速度快）
    "foreign"   → 所有角色全部走 OpenRouter（国外，模型更全，能用 GPT/Claude）
    "mixed"     → 按角色分流，见 MIXED_ROUTING

导入方式：
    from platform_config import (
        get_platform_mode, set_platform_mode,
        get_platform_for_role, get_fallback_model,
        MODE_LABELS, MIXED_ROUTING,
        DOMESTIC_FALLBACKS, FOREIGN_FALLBACKS
    )
"""

import json
import os


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 混合模式角色分配表
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 【重要】修改这里后，auto_updater.py 的提示词会自动跟随变化（动态生成），
#         不需要手动同步任何其他文件。
#
# 角色说明：
#   coder      → 编写代码的 agent
#   reasoner   → 推理/分析任务的 agent（也用于任务分解）
#   writer     → 写作/总结/普通对话的 agent
#   aggregator → 整合多个子任务结果的 agent
#
# 平台选择建议：
#   domestic（硅基流动）：DeepSeek-R1/V3 推理强，Qwen2.5-Coder 代码好，价格低
#   foreign（OpenRouter）：GPT-4o / Claude 理解复杂需求能力强，创意写作更好
#
# 你可以随时修改这个字典，比如把 writer 改回 "foreign" 让写作更有创意

MIXED_ROUTING: dict = {
    "coder":      "foreign",    # 编码 → OpenRouter（可改为 "domestic" 用 Qwen-Coder）
    "reasoner":   "domestic",   # 推理 → 硅基（DeepSeek-R1 推理极强且便宜）
    "writer":     "domestic",   # 写作 → 硅基（国内中文写作 Qwen 表现好）
    "aggregator": "foreign",    # 整合 → OpenRouter（GPT/Claude 整合能力强）
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 各平台兜底模型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 当 model_config.json 没有对应角色的配置时使用这里的值。
# 也就是说：第一次运行、或者 update 失败时，系统不会崩溃，而是用这里的默认模型。
#
# 注意：这里的 ID 必须是对应平台能识别的格式：
#   硅基流动：  "Vendor/ModelName"  如 "deepseek-ai/DeepSeek-R1"
#   OpenRouter："vendor/model"      如 "openai/gpt-4o"

DOMESTIC_FALLBACKS: dict = {
    "coder":      "Qwen/Qwen2.5-Coder-32B-Instruct",   # 硅基上最好的代码模型
    "reasoner":   "deepseek-ai/DeepSeek-R1",             # 硅基上最强推理模型
    "writer":     "Qwen/Qwen2.5-72B-Instruct",           # 硅基上综合写作模型
    "aggregator": "Qwen/Qwen2.5-72B-Instruct",           # 同上，用于整合
}

FOREIGN_FALLBACKS: dict = {
    "coder":      "deepseek/deepseek-chat",              # OpenRouter 上 DeepSeek
    "reasoner":   "anthropic/claude-3-5-sonnet",         # Claude 推理好
    "writer":     "openai/gpt-4o",                       # GPT-4o 写作均衡
    "aggregator": "openai/gpt-4o-mini",                  # 整合用 mini 够用，省钱
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 持久化配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 平台模式存储在 config/platform_mode.json，格式：{"mode": "mixed"}
# 使用文件持久化的原因：Streamlit 每次 rerun 都会重新执行脚本，
# 如果只存在内存变量里，页面刷新后选择的模式就丢了。

_CONFIG_PATH = "config/platform_mode.json"

# 内存缓存，避免每次调用都读文件（Streamlit 高频 rerun 时性能优化）
_mode: str | None = None


def get_platform_mode() -> str:
    """
    读取当前平台模式，优先返回内存缓存，没有则从文件读取。

    返回值：
        "domestic" | "foreign" | "mixed"
        读取失败时默认返回 "domestic"（最保守的选择）
    """
    global _mode
    if _mode is not None:
        return _mode
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _mode = json.load(f).get("mode", "domestic")
    except Exception:
        # 文件不存在（首次运行）或格式损坏，使用默认值
        _mode = "domestic"
    return _mode


def set_platform_mode(mode: str) -> None:
    """
    设置平台模式，同时更新内存缓存和持久化文件。

    参数：
        mode : "domestic" | "foreign" | "mixed"

    异常：
        AssertionError 如果 mode 不合法（防御性校验）
    """
    global _mode
    assert mode in ("domestic", "foreign", "mixed"), \
        f"无效模式: '{mode}'，必须是 domestic / foreign / mixed 之一"

    _mode = mode
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"mode": mode}, f, ensure_ascii=False)


def get_platform_for_role(role: str) -> str:
    """
    根据当前模式和角色，返回应使用的平台名称。

    这是 router.py 调用的核心函数。路由逻辑：
        domestic → 无论什么角色都返回 "domestic"
        foreign  → 无论什么角色都返回 "foreign"
        mixed    → 查 MIXED_ROUTING，找不到时兜底 "domestic"

    参数：
        role : "coder" | "reasoner" | "writer" | "aggregator" | 其他自定义角色

    返回：
        "domestic" | "foreign"
    """
    mode = get_platform_mode()
    if mode == "domestic":
        return "domestic"
    if mode == "foreign":
        return "foreign"
    # mixed 模式：按角色查表，未知角色默认 domestic（安全兜底）
    return MIXED_ROUTING.get(role, "domestic")


def get_fallback_model(role: str, platform: str) -> str:
    """
    获取指定角色在指定平台上的兜底模型 ID。

    当 model_config.json 里没有该角色的配置时，
    auto_updater.get_best_model() 会调用这里提供默认值。

    参数：
        role     : 角色名
        platform : "domestic" | "foreign"

    返回：
        模型 ID 字符串
    """
    if platform == "foreign":
        return FOREIGN_FALLBACKS.get(role, "openai/gpt-4o-mini")
    return DOMESTIC_FALLBACKS.get(role, "Qwen/Qwen2.5-72B-Instruct")


# ── UI 显示标签（app.py 侧边栏使用）────────────────────────────────
MODE_LABELS: dict = {
    "domestic": "🇨🇳 国内（硅基流动）",
    "foreign":  "🌐 国外（OpenRouter）",
    "mixed":    "⚡ 混合（按角色分流）",
}