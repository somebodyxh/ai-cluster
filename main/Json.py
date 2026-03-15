import json
import os

# 定义配置文件名
CONFIG_PATH = "secrets.json"


def get_config():
    

    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            print("[已加载本地配置]")
            return config_data
    else:
        print("首次运行，请配置信息（以后将自动读取）：")
        
        # 1. 获取 API Keys
        #gemini_key = input("请输入 Gemini API Key: ").strip() ##(next)
        siliconcloud_key =input("请输入硅基流动 API Key").strip()
        tavily_key=input("请输入tavily api key").strip()
        openrouter_key=input("请输入OpenRouter API Key（没有直接回车跳过）").strip()
        proxy = input("请输入代理地址（如 http://127.0.0.1:7890，不用直接回车跳过）: ").strip()
        
        
        # 3. 构建字典 
        config_data = {
            "Api_Key": {
                "siliconcloud_key": siliconcloud_key,
                "tavily_key":       tavily_key,
                "openrouter_key":   openrouter_key,
            },
            "proxy": proxy
        }


        # 4. 写入文件
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        
        print(f"[配置已成功保存至 {CONFIG_PATH}]")
        return config_data

# 初始化配置
USER_CONFIG = get_config()
PROXY = USER_CONFIG.get("proxy", "")

# 读取嵌套中的变量 ---
#  Api_Key 是父节点，所以必须通过 ["Api_Key"] 进入
#GEMINI_KEY = USER_CONFIG["Api_Key"]["GEMINI_API_KEY"]
SiliconCloud_KEY = USER_CONFIG["Api_Key"]["siliconcloud_key"]
Tavily_KEY       = USER_CONFIG["Api_Key"]["tavily_key"]
OpenRouter_KEY   = USER_CONFIG["Api_Key"].get("openrouter_key", "")  # 没填时为空字符串
PROXY            = USER_CONFIG.get("proxy", "")

# 读取输入的代理
if PROXY:
    os.environ["https_proxy"] = PROXY
    os.environ["http_proxy"]  = PROXY