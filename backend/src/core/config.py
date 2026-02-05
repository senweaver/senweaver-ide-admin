"""
数据库和应用配置
"""
import os
from typing import Optional
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

# 数据库配置 - PostgreSQL
DATABASE_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "senweaver_web"),
}

# 构建数据库URL - PostgreSQL异步
DATABASE_URL = f"postgresql+asyncpg://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}"

# 同步数据库URL（用于初始化）
SYNC_DATABASE_URL = f"postgresql+psycopg2://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}"

# 应用配置
APP_CONFIG = {
    "title": "Senweaver Web Backend",
    "version": "2.8.3",
    "debug": os.getenv("DEBUG", "false").lower() == "true"
}

# WebSocket配置
WEBSOCKET_CONFIG = {
    "heartbeat_interval": 60,  # 心跳间隔（秒）
    "connection_timeout": 300  # 连接超时（秒）
}
