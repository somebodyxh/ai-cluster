#!/usr/bin/env python3
#后端调用接口 比较简陋 但可以手动da命令操作
import sys
from config.auto_updater import ModelConfigUpdater
from multi_agent.scheduler import MultiAgentScheduler
from API.SiliconCloud_Api import call_model
from main.Json import Tavily_KEY   
from config.auto_updater import ModelConfigUpdater
from multi_agent.project_manager import ProjectManager
from API.SiliconCloud_Api import call_model, call_model_stream
import os
os.environ["TAVILY_API_KEY"] = Tavily_KEY   # 将 Tavily_KEY 设为环境变量



def main():
    # 初始化更新器和调度器
    scheduler = MultiAgentScheduler()
    updater = ModelConfigUpdater(tavily_api_key=Tavily_KEY)
    project_manager = ProjectManager() 
    

    print("=" * 50)
    print("down")
    print("命令：")
    print("  /update  - 强制更新模型配置（每周自动检查，可手动触发）")
    print("  /run     - 运行示例多智能体任务（写代码+解释）")
    print("  /exit    - 退出程序")
    print("  直接输入问题 - 使用默认模型回答")
    print("/help 显示帮助")
    print("项目模式命令：")
    print("  /project new <name>   - 创建新项目")
    print("  /project list          - 列出所有项目")
    print("  /project switch <name> - 切换到指定项目")
    print("  /project delete <name> - 删除项目")
    print("  /chat <问题>           - 在当前项目下对话（自动记忆）")
    print("  /project current        - 显示当前项目")
    print("=" * 50)

    while True:
        try:
            cmd = input("\n请输入命令或问题: ").strip()
            if not cmd:
                continue

            if cmd == "/exit":
                print("再见！")
                break

            elif cmd == "/update":
                print("[手动更新] 正在更新模型配置...")
                updater.update(force=True)
                print("[完成] 配置已更新，可使用 /run 测试。")
            
            elif cmd == "/help":               
                print("=" * 50)
                print("down")
                print("命令：")
                print("  /update  - 强制更新模型配置（每周自动检查，可手动触发）")
                print("  /exit    - 退出程序")
                print("  直接输入问题 - 使用默认模型回答")
                print("项目模式命令：")
                print("  /project new <name>   - 创建新项目")
                print("  /project list          - 列出所有项目")
                print("  /project switch <name> - 切换到指定项目")
                print("  /project delete <name> - 删除项目")
                print("  /chat <问题>           - 在当前项目下对话（自动记忆）")
                print("  /project current        - 显示当前项目")
                print("=" * 50)

            elif cmd == "/run":
                print("[运行示例] 启动多智能体任务...")
                # 定义示例任务：先写代码，后解释
                tasks = [
                    {
                        "task_id": "code_task",
                        "role": "coder",      # 代码角色
                        "prompt": "用Python写一个快速排序算法。",
                        "depends_on": []
                    },
                    {
                        "task_id": "explain_task",
                        "role": "writer",     # 写作角色
                        "prompt": "用中文解释上面的快速排序代码：\n{{code_task}}",
                        "depends_on": ["code_task"]
                    }
                ]
            elif cmd.startswith("/project "):
                parts = cmd.split(maxsplit=2)
                if len(parts) < 2:
                    print("用法：/project <new|list|switch|delete|current> [参数]")
                    continue
                subcmd = parts[1]
                if subcmd == "new" and len(parts) == 3:
                    name = parts[2]
                    try:
                        proj = project_manager.create_project(name)
                        print(f"项目 '{name}' 创建成功，并已切换到该项目。")
                    except ValueError as e:
                        print(e)
                elif subcmd == "list":
                    projs = project_manager.list_projects()
                    if projs:
                        print("已有项目：")
                        for p in projs:
                            mark = "*" if project_manager.current_project and project_manager.current_project.name == p else " "
                            print(f"  {mark} {p}")
                    else:
                        print("暂无项目。")
                elif subcmd == "switch" and len(parts) == 3:
                    name = parts[2]
                    proj = project_manager.switch_project(name)
                    if proj:
                        print(f"已切换到项目 '{name}'")
                    else:
                        print(f"项目 '{name}' 不存在")
                elif subcmd == "delete" and len(parts) == 3:
                    name = parts[2]
                    project_manager.delete_project(name)
                    print(f"项目 '{name}' 已删除")
                elif subcmd == "current":
                    if project_manager.current_project:
                        print(f"当前项目：{project_manager.current_project.name}")
                        print(f"消息数：{project_manager.current_project.message_count}")
                        if project_manager.current_project.summary:
                            print(f"项目摘要：{project_manager.current_project.summary[:100]}...")
                    else:
                        print("当前没有激活的项目，请先用 /project new 或 /project switch 选择项目。")
                else:
                    print("无效的 project 子命令")

            elif cmd.startswith("/chat "):
                if not project_manager.current_project:
                    print("请先创建或切换到一个项目（使用 /project new 或 /project switch）")
                    continue
                user_question = cmd[6:].strip()
                # 获取上下文
                context = project_manager.get_context()
                # 构造带上下文的提示
                full_prompt = f"{context}\n用户: {user_question}\n助手:"
                # 调用模型回答（可以用默认模型）
                model = updater.get_best_model("writer")
                answer = call_model_stream(model, full_prompt, system_prompt="你是一个有帮助的助手，请基于对话历史回答。")
                project_manager.add_message("user", user_question)
                project_manager.add_message("assistant", answer)
                print(f"\n[回答]: {answer}")
            

            else:
                # 简单对话模式：使用默认的写作模型回答
                model = updater.get_best_model("writer")
                print(f"[简单模式] 使用模型: {model}")
                answer = call_model(model, cmd)
                print(f"\n[回答]: {answer}")

        except KeyboardInterrupt:
            print("\n\n用户中断，退出。")
            break
        except Exception as e:
            print(f"\n[错误] {e}")


if __name__ == "__main__":
    main()