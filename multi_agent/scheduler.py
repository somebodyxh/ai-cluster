#此文件用于多智能体调度
# multi_agent/scheduler.py
from typing import List, Dict, Any

# ↓ 改为从 router 导入
from API.router import call_model, call_model_stream
from config.auto_updater import ModelConfigUpdater

class MultiAgentScheduler:
    
    
    def __init__(self):
        self.updater = ModelConfigUpdater()
        #

    def execute_task_sequence(self, tasks: List[Dict[str, Any]]) -> Dict[str, str]:
   
        pending = tasks[:]
        results = {}

        while pending:
            # 找出所有依赖已满足的任务
            executable = []
            for task in pending:
                deps = task.get('depends_on', [])
                if all(dep in results for dep in deps):
                    executable.append(task)

            if not executable:
                print("\n[错误] 无法满足依赖，剩余任务:", [t['task_id'] for t in pending])
                break

            # 执行第一个可执行任务
            task = executable[0]
            pending.remove(task)

            task_id = task['task_id']
            role = task['role']
            prompt_template = task['prompt']

            # 替换 prompt 中的占位符
            prompt = prompt_template
            for dep in task.get('depends_on', []):
                placeholder = f"{{{{{dep}}}}}"
                if placeholder in prompt:
                    prompt = prompt.replace(placeholder, results[dep])

            # 根据角色获取模型
            model = self.updater.get_best_model(role)
            
            # ---------- 实时日志开始 ----------
            print(f"\n[开始执行] 任务 {task_id} (角色={role})")
            print(f"[模型] 使用 {model}")
            print(f"[提示词预览] {prompt[:200]}..." if len(prompt) > 200 else f"[提示词] {prompt}")
            print("[调用模型] 正在请求...")
            # ---------------------------------

            # ↓ 加 role=role，支持平台路由
            result = call_model_stream(model, prompt, role=role)

            # ---------- 结果预览 ----------
            print(f"[完成] 任务 {task_id} 结果长度: {len(result)}")
            if result.startswith("[错误]"):
                print(f"[错误详情] {result}")
            else:
                preview = result[:200] + "..." if len(result) > 200 else result
                print(f"[结果预览] {preview}")
            # -----------------------------

            results[task_id] = result

        # 最终汇总
        print("\n" + "="*50)
        print("所有任务执行完毕，最终结果：")
        for task_id, res in results.items():
            print(f"\n--- {task_id} ---\n{res}")
        print("="*50)

        return results