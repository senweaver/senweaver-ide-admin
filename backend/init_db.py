"""
数据库初始化脚本
运行此脚本来创建数据库表和初始数据
"""
import asyncio
from datetime import datetime
from sqlalchemy import create_engine, text
from src.core.config import DATABASE_CONFIG, SYNC_DATABASE_URL


def create_database():
    """创建数据库（如果不存在）- PostgreSQL"""
    # 连接到PostgreSQL服务器（连接到默认postgres数据库）
    server_url = f"postgresql+psycopg2://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/postgres"
    
    engine = create_engine(server_url, isolation_level="AUTOCOMMIT")
    
    with engine.connect() as conn:
        # 检查数据库是否存在
        result = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname = '{DATABASE_CONFIG['database']}'"))
        exists = result.fetchone()
        
        if not exists:
            conn.execute(text(f"CREATE DATABASE {DATABASE_CONFIG['database']} ENCODING 'UTF8'"))
            print(f"数据库 {DATABASE_CONFIG['database']} 已创建")
        else:
            print(f"数据库 {DATABASE_CONFIG['database']} 已存在")
    
    engine.dispose()


def create_tables():
    """创建数据库表"""
    from src.core.database import sync_engine, Base
    from src.models.models import (Article, Comment, ConnectionLog, DailyStats, UserActivity,
                        Subscriber, User, Order, Transaction, UsageLog, RechargePackage,
                        KeyPoolProvider, KeyPool, KeyAllocation)
    
    Base.metadata.create_all(bind=sync_engine)
    print("所有数据库表已创建")


def insert_sample_data():
    """插入示例数据"""
    from sqlalchemy.orm import Session
    from database import sync_engine
    from src.models.models import Article, ArticleStatus
    
    sample_articles = [
        {
            "title": "Senweaver Designer 模式：重新定义AI编程工作流",
            "excerpt": "Designer 模式是 Senweaver 的核心创新之一，它将复杂的编程任务转化为可执行的任务委托...",
            "content": "完整的文章内容...",
            "category": "产品更新",
            "icon": "fas fa-rocket",
            "author": "John Doe",
            "author_initial": "J",
            "read_time": "8分钟阅读",
            "tags": '["Designer模式", "AI编程", "产品更新"]'
        },
        {
            "title": "深入理解 MCP 协议及其在Senweaver中的应用",
            "excerpt": "Model Context Protocol（MCP）是现代AI编程工具的核心技术之一，本文深入探讨其原理...",
            "content": "完整的文章内容...",
            "category": "技术文章",
            "icon": "fas fa-code",
            "author": "Sarah Chen",
            "author_initial": "S",
            "read_time": "12分钟阅读",
            "tags": '["MCP", "协议", "技术深度"]'
        },
        {
            "title": "提升开发效率的10个Senweaver使用技巧",
            "excerpt": "Senweaver不仅仅是一个代码编辑器，它是一个完整的AI编程平台。本文分享10个实用技巧...",
            "content": "完整的文章内容...",
            "category": "教程",
            "icon": "fas fa-lightbulb",
            "author": "Mike Wang",
            "author_initial": "M",
            "read_time": "6分钟阅读",
            "tags": '["技巧", "教程", "效率"]'
        },
        {
            "title": "AI代码生成 vs 传统编码：效率与质量的平衡",
            "excerpt": "随着AI编程工具的崛起，开发者社区对AI生成代码的质量和效率展开了广泛讨论...",
            "content": "完整的文章内容...",
            "category": "技术文章",
            "icon": "fas fa-microchip",
            "author": "Alex Johnson",
            "author_initial": "A",
            "read_time": "10分钟阅读",
            "tags": '["AI", "代码质量", "对比分析"]'
        },
        {
            "title": "Senweaver 2.8 版本更新日志",
            "excerpt": "2.8版本带来了多项重大改进，包括性能优化、新功能和Bug修复...",
            "content": "完整的更新日志内容...",
            "category": "产品更新",
            "icon": "fas fa-bell",
            "author": "Senweaver Team",
            "author_initial": "S",
            "read_time": "3分钟阅读",
            "tags": '["更新", "版本", "功能"]'
        },
        {
            "title": "使用Senweaver构建全栈应用教程",
            "excerpt": "从零开始，手把手教你使用Senweaver快速构建一个完整的全栈Web应用...",
            "content": "完整的教程内容...",
            "category": "教程",
            "icon": "fas fa-graduation-cap",
            "author": "Emily Zhang",
            "author_initial": "E",
            "read_time": "15分钟阅读",
            "tags": '["全栈", "教程", "实战"]'
        }
    ]
    
    with Session(sync_engine) as session:
        # 检查是否已有数据
        existing = session.query(Article).first()
        if existing:
            print("数据库中已有文章数据，跳过示例数据插入")
            return
        
        for article_data in sample_articles:
            article = Article(
                title=article_data["title"],
                excerpt=article_data["excerpt"],
                content=article_data["content"],
                category=article_data["category"],
                icon=article_data["icon"],
                author=article_data["author"],
                author_initial=article_data["author_initial"],
                read_time=article_data["read_time"],
                tags=article_data["tags"],
                status=ArticleStatus.PUBLISHED,
                published_at=datetime.now()
            )
            session.add(article)
        
        session.commit()
        print(f"已插入 {len(sample_articles)} 篇示例文章")


def insert_key_pool_data():
    """插入密钥池初始数据"""
    from sqlalchemy.orm import Session
    from src.core.database import sync_engine
    from src.models.models import KeyPoolProvider, KeyPool

    with Session(sync_engine) as session:
        # 检查是否已有数据
        existing_provider = session.query(KeyPoolProvider).first()
        if existing_provider:
            print("数据库中已有密钥池数据，跳过初始数据插入")
            return

        # 创建提供商
        providers_data = [
            {
                "name": "deepseek",
                "display_name": "DeepSeek",
                "base_url": "https://api.deepseek.com",
                "description": "DeepSeek AI 提供商",
                "priority": 10,
                "is_active": True
            },
            {
                "name": "ownProvider",
                "display_name": "Own Provider",
                "base_url": "",
                "description": "自有模型提供商",
                "priority": 5,
                "is_active": True
            }
        ]

        providers = []
        for provider_data in providers_data:
            provider = KeyPoolProvider(**provider_data)
            session.add(provider)
            providers.append(provider)

        session.flush()  # 获取ID

        # 创建密钥池
        key_pools_data = [
            {
                "provider_id": providers[0].id,  # DeepSeek
                "name": "DeepSeek 主池",
                "description": "DeepSeek 主密钥池",
                "api_key": "sk-your-deepseek-api-key-here",  # 这需要在实际部署时替换
                "max_clients": -1,
                "is_active": True
            },
            {
                "provider_id": providers[1].id,  # Own Provider
                "name": "Own Provider 池1",
                "description": "自有模型提供商密钥池1",
                "api_key": "sk-new-shared-api-key1",
                "max_clients": -1,
                "is_active": True
            },
            {
                "provider_id": providers[1].id,  # Own Provider
                "name": "Own Provider 池2",
                "description": "自有模型提供商密钥池2",
                "api_key": "sk-new-shared-api-key2",
                "max_clients": -1,
                "is_active": True
            },
            {
                "provider_id": providers[1].id,  # Own Provider
                "name": "Own Provider 池3",
                "description": "自有模型提供商密钥池3",
                "api_key": "sk-new-shared-api-key3",
                "max_clients": -1,
                "is_active": True
            }
        ]

        for pool_data in key_pools_data:
            key_pool = KeyPool(**pool_data)
            session.add(key_pool)

        session.commit()
        print(f"已创建 {len(providers_data)} 个提供商和 {len(key_pools_data)} 个密钥池")


def main():
    """主函数"""
    print("=" * 50)
    print("Senweaver Web 数据库初始化")
    print("=" * 50)
    
    try:
        # 1. 创建数据库
        print("\n1. 创建数据库...")
        create_database()
        
        # 2. 创建表
        print("\n2. 创建数据库表...")
        create_tables()
        
        # 3. 插入示例数据
        print("\n3. 插入示例数据...")
        insert_sample_data()

        # 4. 插入密钥池数据
        print("\n4. 插入密钥池初始数据...")
        insert_key_pool_data()
        
        print("\n" + "=" * 50)
        print("数据库初始化完成！")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n错误: {e}")
        print("\n请确保：")
        print("1. MySQL服务已启动")
        print("2. config.py 中的数据库配置正确")
        print("3. 数据库用户有创建数据库的权限")
        raise


if __name__ == "__main__":
    main()
