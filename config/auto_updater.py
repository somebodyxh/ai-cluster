# config/auto_updater.py
"""
模型配置自动更新器
==================
职责：
    每隔7天自动搜索最新大模型评测榜单（LMArena / 天罡 / xbench），
    让主 LLM 分析榜单数据并生成 model_config.json，
    从而让框架始终使用当前最强的模型。

工作流程：
    1. needs_update()            → 判断是否需要更新（距上次 >= 7 天）
    2. search_latest_rankings()  → 用 Tavily 搜索最新评测，无 Tavily 则用内置模拟数据
    3. analyze_with_llm()        → 把搜索结果 + 当前可用模型列表送给主 LLM，生成配置 JSON
    4. validate_and_clean()      → 校验模型 ID 是否真实存在，做模糊匹配修正
    5. _save_config()            → 写入 config/model_config.json

注意：
    MAIN_MODEL 是分析评测数据用的模型，role="reasoner"，
    在混合模式下会路由到硅基流动（DeepSeek），节省 OpenRouter 费用。
"""

import json
import os
import shutil
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

# router 统一路由层，不直接调硅基或 OpenRouter
from API.router import call_model, list_models
# 读取当前平台模式和混合路由配置
from platform_config import get_platform_mode, MIXED_ROUTING

try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False
    print("警告: tavily-python 未安装，搜索功能将使用模拟模式。")


# ── 配置文件路径 ──────────────────────────────────────────────────
CONFIG_DIR  = "config"
CONFIG_FILE = os.path.join(CONFIG_DIR, "model_config.json")
BACKUP_FILE = os.path.join(CONFIG_DIR, "model_config.json.bak")

# ── 分析评测数据用的主模型 ─────────────────────────────────────────
# role="reasoner" → 混合模式下走硅基流动（DeepSeek 分析能力强且便宜）
MAIN_MODEL = "Pro/deepseek-ai/DeepSeek-V3.2"

os.makedirs(CONFIG_DIR, exist_ok=True)


class ModelConfigUpdater:
    """
    模型配置管理器，负责读取、更新、查询 model_config.json。

    主要接口：
        updater.get_best_model("coder")  → 返回 coder 角色的最佳模型 ID
        updater.update(force=True)       → 强制触发一次更新流程
        updater.needs_update()           → 是否需要更新（7天没更新则 True）
    """

    def __init__(self, tavily_api_key: Optional[str] = None):
        self.config = self._load_config()
        self.tavily_client = None

        if TAVILY_AVAILABLE and tavily_api_key:
            self.tavily_client = TavilyClient(api_key=tavily_api_key)
        elif TAVILY_AVAILABLE:
            api_key = os.getenv("TAVILY_API_KEY")
            if api_key:
                self.tavily_client = TavilyClient(api_key=api_key)

    # ━━━━ 配置文件读写 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _load_config(self) -> Dict[str, Any]:
        """从文件加载配置，失败时返回空配置（系统继续用 fallback 模型运行）。"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"last_update": "2000-01-01", "models": [], "default_mapping": {}}

    def _save_config(self, config: Dict[str, Any]) -> None:
        """先备份旧文件再写新文件，避免写入中断导致配置损坏。"""
        if os.path.exists(CONFIG_FILE):
            shutil.copy2(CONFIG_FILE, BACKUP_FILE)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        self.config = config
        print(f"[配置] 已保存到 {CONFIG_FILE}")

    def needs_update(self) -> bool:
        """距上次更新是否已超过 7 天。首次运行（last_update=2000-01-01）必定触发。"""
        last_str = self.config.get("last_update", "2000-01-01")
        try:
            last = datetime.strptime(last_str, "%Y-%m-%d")
        except ValueError:
            return True
        return (datetime.now() - last).days >= 7

    # ━━━━ 搜索评测数据 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def search_latest_rankings(self) -> str:
        """搜索最新大模型评测榜单，无 Tavily 则用内置模拟数据。"""
        if self.tavily_client:
            queries = [
                "最新大模型评测 LMArena 2026",
                "xbench 模型榜单 2026",
                "天罡评测 大模型 2026",
                "Hugging Face 开源模型排行榜 2026",
            ]
            all_results = []
            for q in queries:
                try:
                    response = self.tavily_client.search(
                        query=q, search_depth="advanced", max_results=3
                    )
                    for r in response.get('results', []):
                        all_results.append(
                            f"标题: {r.get('title')}\n"
                            f"内容: {r.get('content')}\n"
                            f"来源: {r.get('url')}\n"
                        )
                except Exception as e:
                    print(f"搜索 '{q}' 失败: {e}")
            if all_results:
                return "\n---\n".join(all_results)
            print("[搜索] 真实搜索失败，使用模拟数据。")
        else:
            print("[搜索] 未配置 Tavily，使用模拟数据。")

        return self._mock_search_results()

    def _mock_search_results(self) -> str:
        return """
LMArena 2026年2月榜单：
综合能力前十：1. claude-opus-4-6, 2. gemini-3.1-pro, 3. gpt-5.4, 5. deepseek-v3.2-Speciale,
6. qwen2.5-72b, 7. minimax-m2.1, 8. glm-5, 9. kimi-k2.5, 10. llama-4-70b

代码能力特别突出：GLM-5（全球第8）、MiniMax-M2.1
数学推理：Kimi K2.5-thinking（全球第8）、deepseek-r1-0528
多模态视觉：Seed 2.0（全球第4）、qwen2.5-vl-72b

天罡评测 2026年1月：
任务分解：deepseek-v3.2-Speciale 93.5分
信息抽取：deepseek-v3.2-Speciale 93.49分
中文能力：qwen2.5-72b 94.2分
"""

    # ━━━━ LLM 分析 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def analyze_with_llm(self, search_results: str) -> Optional[Dict[str, Any]]:
        """
        让主 LLM 分析评测数据，生成 model_config.json 的内容。

        【Bug 修复】原版提示词硬编码了 "coder/reasoner 用硅基，writer/aggregator 用 OpenRouter"，
        与 MIXED_ROUTING 的实际配置不同步，导致 LLM 选错模型 ID。
        现在动态读取 MIXED_ROUTING，提示词和配置完全一致。
        """
        mode = get_platform_mode()

        # 分平台获取可用模型列表
        try:
            domestic_models = list_models("domestic")
            domestic_str    = "\n".join(f"- {m}" for m in domestic_models[:60]) or "暂无"
        except Exception as e:
            print(f"[警告] 获取硅基流动模型列表失败: {e}")
            domestic_str = "暂无"

        try:
            foreign_models = list_models("foreign") if mode in ("foreign", "mixed") else []
            foreign_str    = "\n".join(f"- {m}" for m in foreign_models[:60]) or "暂无"
        except Exception as e:
            print(f"[警告] 获取 OpenRouter 模型列表失败: {e}")
            foreign_str = "暂无"

        # 动态生成提示词中的平台分配说明（完全来自 MIXED_ROUTING，不硬编码角色名）
        if mode == "mixed":
            domestic_roles = [r for r, p in MIXED_ROUTING.items() if p == "domestic"]
            foreign_roles  = [r for r, p in MIXED_ROUTING.items() if p == "foreign"]
            routing_lines  = "\n".join(
                f"  - {r}: {'硅基流动（国内）' if p == 'domestic' else 'OpenRouter（国外）'}"
                for r, p in MIXED_ROUTING.items()
            )
            available_section = (
                f"当前为混合模式，各角色平台分配如下（来自 MIXED_ROUTING 配置）：\n"
                f"{routing_lines}\n\n"
                f"【硅基流动可用模型ID】（{' / '.join(domestic_roles) or '无'} 必须从这里选）：\n"
                f"{domestic_str}\n\n"
                f"【OpenRouter可用模型ID】（{' / '.join(foreign_roles) or '无'} 必须从这里选）：\n"
                f"{foreign_str}\n\n"
                f"**重要**：每个角色的模型 ID 必须严格来自该角色对应平台的列表，绝对不能混用。"
            )
        elif mode == "foreign":
            available_section = (
                f"当前为国外模式，所有角色请从 OpenRouter 模型列表中选择。\n\n"
                f"【OpenRouter可用模型ID】：\n{foreign_str}"
            )
        else:
            available_section = (
                f"当前为国内模式，所有角色请从硅基流动模型列表中选择。\n\n"
                f"【硅基流动可用模型ID】：\n{domestic_str}"
            )

        system_prompt = (
            "你是一个专业的AI分析师。"
            "请根据提供的搜索数据，生成模型配置JSON。只输出JSON，不要其他文字。"
        )
        user_prompt = f"""
请根据以下搜索到的模型评测信息，生成一个模型配置文件。

搜索信息：
{search_results}

要求：
1. 提取评测中提到的模型，整理成列表，每个模型包含：
   id、name、capabilities（各能力评分0-1）、best_for（列表）、source（来源）、ranking（排名）。
2. 为以下任务类型推荐最佳模型：coder、reasoner、writer、vision、aggregator，写入 default_mapping 字段。
3. **非常重要**：所有模型 ID 必须严格匹配下方对应平台的可用列表（区分大小写），优先 Pro 版本。
4. 输出 JSON 格式，包含字段：last_update（当前日期）、models（列表）、default_mapping（字典）。
5. 优先选择最新版本，避免已被替代的旧型号。
6. 暂不使用 Qwen 类型的模型。
7. aggregator 尽量使用 deepseek 系列。

{available_section}

示例格式：
{{
  "last_update": "2026-03-08",
  "models": [
    {{
      "id": "Pro/deepseek-ai/DeepSeek-V3",
      "name": "DeepSeek-V3",
      "capabilities": {{"reasoning": 0.92, "coding": 0.85, "writing": 0.94, "chinese": 0.96}},
      "best_for": ["writing", "reasoning"],
      "source": "LMArena 2026-02",
      "ranking": 5
    }}
  ],
  "default_mapping": {{
    "coder":      "对应平台模型ID",
    "reasoner":   "对应平台模型ID",
    "writer":     "对应平台模型ID",
    "vision":     "对应平台模型ID",
    "aggregator": "对应平台模型ID"
  }}
}}
"""
        response = call_model(
            model=MAIN_MODEL,
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=3000,
            role="reasoner"   # 走硅基，省 OpenRouter 费用
        )

        print("\n" + "=" * 50)
        print("主LLM原始响应:")
        print(response)
        print(f"响应长度: {len(response)}")
        print("=" * 50 + "\n")

        try:
            start = response.find('{')
            end   = response.rfind('}') + 1
            if start == -1 or end <= 0:
                print("[错误] 未找到 JSON 格式输出")
                return None
            return json.loads(response[start:end])
        except Exception as e:
            print(f"[错误] 解析 JSON 失败: {e}")
            return None

    # ━━━━ 配置校验 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def validate_and_clean(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        校验 LLM 生成的配置，确保所有模型 ID 真实存在。

        【Bug 修复】原版 fallback 直接用 valid_models[0]["id"]，
        在混合模式下可能用了错误平台的模型 ID（如把硅基 ID 给了应走 OpenRouter 的角色）。
        现在 fallback 时按角色查 MIXED_ROUTING，从正确平台的模型池里取第一个。
        """
        mode = get_platform_mode()

        try:
            domestic_set = set(list_models("domestic"))
        except Exception:
            domestic_set = set()

        try:
            foreign_set = set(list_models("foreign")) if mode in ("foreign", "mixed") else set()
        except Exception:
            foreign_set = set()

        available_set = domestic_set | foreign_set

        if not available_set:
            print("[警告] 无法获取任何模型列表，跳过验证")
            return config

        def prefer_pro(candidates: List[str]) -> str:
            pro = [m for m in candidates if m.startswith("Pro/")]
            return pro[0] if pro else candidates[0]

        def fuzzy_match(target: str, pool: set) -> Optional[str]:
            t = target.lower()
            matches = [m for m in pool if t in m.lower() or m.lower() in t]
            return prefer_pro(matches) if matches else None

        def get_role_pool(role: str) -> set:
            """返回该角色在当前模式下应使用的平台模型集合。"""
            if mode == "mixed":
                plat = MIXED_ROUTING.get(role, "domestic")
                return foreign_set if plat == "foreign" else domestic_set
            return foreign_set if mode == "foreign" else domestic_set

        # 校验 models 列表
        valid_models = []
        for m in config.get("models", []):
            orig_id = m.get("id", "")
            if orig_id in available_set:
                valid_models.append(m)
                continue
            matched = fuzzy_match(orig_id, available_set)
            if matched:
                print(f"[信息] 模糊匹配: {orig_id} → {matched}")
                m["id"] = matched
                valid_models.append(m)
            else:
                print(f"[警告] 移除不可用模型: {orig_id}")

        if not valid_models:
            fb = "Qwen/Qwen2.5-7B-Instruct" if mode != "foreign" else "openai/gpt-4o-mini"
            if fb in available_set:
                valid_models.append({
                    "id": fb, "name": "Fallback",
                    "capabilities": {"reasoning": 0.7, "coding": 0.7, "writing": 0.7},
                    "best_for": ["general"], "source": "fallback", "ranking": 999
                })
                print(f"[信息] 使用保底模型: {fb}")

        config["models"] = valid_models

        # 校验 default_mapping
        mapping = config.get("default_mapping", {})
        for role, model_id in list(mapping.items()):
            if model_id in available_set:
                continue

            role_pool = get_role_pool(role)
            matched   = fuzzy_match(model_id, role_pool) or fuzzy_match(model_id, available_set)

            if matched:
                print(f"[信息] 映射模糊匹配: {model_id} → {matched}")
                mapping[role] = matched
            elif role_pool:
                # 从正确平台的模型池取第一个（Bug 修复核心）
                fb = prefer_pro(list(role_pool))
                mapping[role] = fb
                print(f"[信息] 角色 {role} 使用平台兜底: {fb}")
            else:
                del mapping[role]
                print(f"[警告] 角色 {role} 无可用模型，已移除")

        config["default_mapping"] = mapping
        return config

    # ━━━━ 公开入口 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def update(self, force: bool = False) -> Dict[str, Any]:
        """
        执行完整更新流程。
        force=True 时忽略7天限制，立即重新搜索并更新。
        """
        if not force and not self.needs_update():
            print(f"[跳过] 上次更新为 {self.config.get('last_update')}，未到一周")
            return self.config

        print("[更新] 开始搜索最新模型评测...")
        search_text = self.search_latest_rankings()

        print("[更新] 调用主LLM分析...")
        new_config = self.analyze_with_llm(search_text)

        if new_config is None:
            print("[更新] 分析失败，保留旧配置")
            return self.config

        new_config["last_update"] = datetime.now().strftime("%Y-%m-%d")
        new_config = self.validate_and_clean(new_config)
        self._save_config(new_config)
        print(f"[完成] 下次更新建议在 {datetime.now() + timedelta(days=7):%Y-%m-%d}")
        return new_config

    def get_best_model(self, task_type: str,
                       default: str = "Qwen/Qwen2.5-72B-Instruct") -> str:
        """
        获取指定任务类型的最佳模型 ID。
        config/model_config.json 里没有该角色时返回 default。
        """
        return self.config.get("default_mapping", {}).get(task_type, default)


# ── 命令行直接运行 ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="更新模型配置")
    parser.add_argument("--force",      action="store_true", help="强制更新（忽略7天限制）")
    parser.add_argument("--tavily-key", default=None,        help="Tavily API 密钥")
    args = parser.parse_args()

    updater = ModelConfigUpdater(tavily_api_key=args.tavily_key)
    updater.update(force=args.force)