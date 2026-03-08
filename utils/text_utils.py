"""
utils/text_utils.py - 文本处理通用库
====================================
封装项目中反复出现的文本解析逻辑，统一放在这里方便复用和测试。

目前包含：
  - filter_json()  : 清理模型输出中夹带的原始 JSON，保留可读文本
  - parse_tasks()  : 从模型输出中提取任务列表 JSON 数组
"""

import json
import re


def filter_json(text: str) -> str:
    """
    清理模型输出中夹带的 JSON 块，只保留人类可读的文字部分。

    为什么需要这个：
        Agent 模式下某些模型（尤其是推理型）会在回答里附带原始 JSON，
        比如把任务列表或结构化数据直接输出到对话里。
        存入历史记录前需要把这些内联 JSON 去掉，否则对话展示很难看。

    处理规则：
        1. 删除 ```json [...] ``` 格式的 JSON 数组代码块
        2. 删除 ```json {...} ``` 格式的 JSON 对象代码块
        3. 删除单行的简单 JSON 对象（{...} 不含换行）

    参数：
        text : 原始文本（可能混有 JSON）

    返回：
        清理后的文本，首尾去掉空白。空输入原样返回空字符串。

    示例：
        输入：
            "好的，以下是任务计划：\\n```json\\n[{"task_id": "t1"}]\\n```\\n请确认。"
        输出：
            "好的，以下是任务计划：\\n\\n请确认。"
    """
    if not text:
        return ""
    # 删除 ```json [...] ``` 形式（任务数组）
    text = re.sub(r'```json\s*\[.*?\]\s*```', '', text, flags=re.DOTALL)
    # 删除 ```json {...} ``` 形式（单个对象）
    text = re.sub(r'```json\s*\{.*?\}\s*```', '', text, flags=re.DOTALL)
    # 删除单行的裸 JSON 对象（整行都是 {...}，不含花括号嵌套）
    text = re.sub(r'^\s*\{[^{}\n]+\}\s*$', '', text, flags=re.MULTILINE)
    return text.strip()


def parse_tasks(raw: str):
    """
    从模型输出中提取子任务 JSON 数组。

    模型输出格式约定（在 decompose_prompt 里指定）：
        [
          {
            "task_id":    "task1",          # 唯一标识，字符串
            "role":       "coder",          # 执行角色
            "prompt":     "请实现...",       # 具体指令
            "depends_on": ["task0"]         # 依赖列表，没有依赖填 []
          },
          ...
        ]

    健壮性处理：
        - 允许模型在 JSON 前后输出多余文字（取第一个 [ 到最后一个 ] 之间的内容）
        - task_id 和 depends_on 里的字符串自动去首尾空格，防止后续依赖匹配失败
        - depends_on 如果模型输出了字符串而非列表（偶发），自动转为列表
        - 解析失败一律返回 None，由调用方决定降级策略

    参数：
        raw : 模型的原始输出文本

    返回：
        成功 → List[Dict]，任务列表
        失败 → None

    示例 depends_on 修复：
        模型输出 "depends_on": "task1"  →  转为 ["task1"]
        模型输出 "depends_on": " task1 " →  转为 ["task1"]
    """
    try:
        # 找到第一个 [ 和最后一个 ]，提取中间内容
        s = raw.find('[')
        e = raw.rfind(']') + 1
        if s == -1 or e <= s:
            return None

        tasks = json.loads(raw[s:e])

        for t in tasks:
            # task_id 去空格，防止占位符替换时匹配失败（如 "{{ task1 }}"）
            t["task_id"] = t["task_id"].strip()

            deps = t.get("depends_on", [])
            if isinstance(deps, str):
                # 模型偶尔会输出字符串而非列表
                t["depends_on"] = [deps.strip()] if deps.strip() else []
            elif isinstance(deps, list):
                # 列表里每个元素都去空格
                t["depends_on"] = [d.strip() for d in deps if isinstance(d, str)]
            else:
                t["depends_on"] = []

        return tasks

    except Exception:
        # JSON 解析失败：模型没有按格式输出
        return None