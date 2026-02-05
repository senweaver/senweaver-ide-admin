
# 密钥池配置
# 从 main.py 迁移过来的静态配置

ALIBAILIAN_KEYS = []

ZAI_KEYS = []

OPENROUTER_KEYS = []

DEEPSEEK_KEYS = []

MOONSHOTAI_KEYS = []

OWNPROVIDER_KEYS = []

PROVIDERS_CONFIG = [
    {
        "name": "alibailian",
        "display_name": "阿里百炼",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "keys": ALIBAILIAN_KEYS,
        "priority": 90
    },
    {
        "name": "zai",
        "display_name": "zAi",
        "base_url": "https://api.zai.com/v1",  # 假设的URL，需要确认
        "keys": ZAI_KEYS,
        "priority": 80
    },
    {
        "name": "openrouter",
        "display_name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "keys": OPENROUTER_KEYS,
        "priority": 100
    },
    {
        "name": "deepseek",
        "display_name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "keys": DEEPSEEK_KEYS,
        "priority": 95
    },
    {
        "name": "moonshotai",
        "display_name": "Moonshot AI",
        "base_url": "https://api.moonshot.cn/v1",
        "keys": MOONSHOTAI_KEYS,
        "priority": 85
    },
    {
        "name": "ownProvider",
        "display_name": "Own Provider",
        "base_url": "",
        "keys": OWNPROVIDER_KEYS,
        "priority": 50
    }
]
