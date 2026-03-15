"""
项目管理器
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional

# ↓ 改为从 router 导入
from API.router import call_model
from config.auto_updater import ModelConfigUpdater
from debug import log, log_project

PROJECTS_DIR = "projects"
os.makedirs(PROJECTS_DIR, exist_ok=True)


class Project:
    def __init__(self, name: str, created_at: str = None):
        self.name        = name
        self.created_at  = created_at or datetime.now().isoformat()
        self.history: List[Dict[str, str]] = []
        self.summary: Optional[str]        = None
        self.message_count                 = 0
        self.agent_state: Optional[Dict]   = None
        self.chat_stream: Optional[Dict]   = None
        self.updater                       = ModelConfigUpdater()

    def to_dict(self) -> dict:
        return {
            "name":          self.name,
            "created_at":    self.created_at,
            "history":       self.history,
            "summary":       self.summary,
            "message_count": self.message_count,
            "agent_state":   self.agent_state,
            "chat_stream":   self.chat_stream,
        }

    @classmethod
    def from_dict(cls, data: dict):
        proj               = cls(data["name"], data["created_at"])
        proj.history       = data["history"]
        proj.summary       = data["summary"]
        proj.message_count = data["message_count"]
        proj.agent_state   = data.get("agent_state")
        proj.chat_stream   = data.get("chat_stream")
        return proj


class ProjectManager:
    def __init__(self, projects_dir: str = PROJECTS_DIR):
        self.projects_dir   = projects_dir
        self.current_project: Optional[Project] = None
        self._load_all_projects()
        log_project("ProjectManager 初始化",
                    f"已加载 {len(self.projects_list)} 个项目: {self.projects_list}")

    def _project_path(self, name: str) -> str:
        return os.path.join(self.projects_dir, f"{name}.json")

    def _load_all_projects(self):
        self.projects_list = []
        if os.path.exists(self.projects_dir):
            for fname in os.listdir(self.projects_dir):
                if fname.endswith(".json"):
                    self.projects_list.append(fname[:-5])

    def create_project(self, name: str) -> "Project":
        if name in self.projects_list:
            raise ValueError(f"项目 '{name}' 已存在")
        proj = Project(name)
        self._save_project(proj)
        self.projects_list.append(name)
        self.current_project = proj
        log_project(f"创建项目 '{name}'")
        return proj

    def switch_project(self, name: str) -> Optional["Project"]:
        if name not in self.projects_list:
            log("ERROR", f"switch_project: '{name}' 不存在")
            return None
        with open(self._project_path(name), 'r', encoding='utf-8') as f:
            proj = Project.from_dict(json.load(f))
        self.current_project = proj
        log_project(f"切换到 '{name}'",
                    f"历史 {len(proj.history)} 条  "
                    f"agent_state={'有' if proj.agent_state else '无'}  "
                    f"chat_stream={'有' if proj.chat_stream else '无'}")
        return proj

    def list_projects(self) -> List[str]:
        return self.projects_list

    def delete_project(self, name: str):
        if name not in self.projects_list:
            return
        os.remove(self._project_path(name))
        self.projects_list.remove(name)
        if self.current_project and self.current_project.name == name:
            self.current_project = None
        log_project(f"删除项目 '{name}'")

    def _save_project(self, proj: "Project"):
        with open(self._project_path(proj.name), 'w', encoding='utf-8') as f:
            json.dump(proj.to_dict(), f, ensure_ascii=False, indent=2)
        log_project(f"保存 '{proj.name}'",
                    f"历史 {len(proj.history)} 条  "
                    f"agent_state={'有' if proj.agent_state else '无'}  "
                    f"chat_stream={'有' if proj.chat_stream else '无'}")

    def add_message(self, role: str, content: str):
        if not self.current_project:
            raise RuntimeError("没有激活的项目")
        self.current_project.history.append({"role": role, "content": content})
        self.current_project.message_count += 1
        self._save_project(self.current_project)
        log_project(f"add_message role={role}",
                    f"内容前50字: {repr(content[:50])}")
        compressed = False
        if self.current_project.message_count % 20 == 0:
            log_project("触发记忆压缩", f"message_count={self.current_project.message_count}")
            self.compress_memory()
            compressed = True
        return compressed

    def get_context(self, max_history: int = 10) -> str:
        if not self.current_project:
            return ""
        ctx = ""
        if self.current_project.summary:
            ctx += f"[项目摘要] {self.current_project.summary}\n\n"
        recent = self.current_project.history[-max_history:]
        for msg in recent:
            prefix = "用户" if msg["role"] == "user" else "助手"
            ctx += f"{prefix}: {msg['content']}\n"
        log_project("get_context",
                    f"摘要={'有' if self.current_project.summary else '无'}  "
                    f"历史取最近 {len(recent)} 条")
        return ctx

    def compress_memory(self):
        if not self.current_project:
            return
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in self.current_project.history
        )
        prompt  = f"请对以下对话历史进行摘要，提炼关键信息和用户意图。\n\n{history_text}\n\n摘要："
        model   = self.current_project.updater.get_best_model("writer")
        # ↓ 加 role="writer"
        summary = call_model(model, prompt,
                             system_prompt="你是一个擅长总结的助手。",
                             temperature=0.3, max_tokens=500,
                             role="writer")
        self.current_project.summary = summary
        self._save_project(self.current_project)
        log_project(f"记忆压缩完成 '{self.current_project.name}'",
                    f"摘要长度 {len(summary)} 字符")