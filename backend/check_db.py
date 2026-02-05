#!/usr/bin/env python3
"""
检查数据库表
"""
from src.core.database import sync_engine, Base
from src.models.models import KeyPoolProvider, KeyPool, KeyAllocation

# 创建表（如果不存在）
Base.metadata.create_all(bind=sync_engine)
print("数据库表创建完成")

# 检查表是否存在
from sqlalchemy import inspect
inspector = inspect(sync_engine)

tables = inspector.get_table_names()
print(f"数据库中的表: {tables}")

key_pool_tables = [t for t in tables if 'key_pool' in t.lower()]
print(f"密钥池相关表: {key_pool_tables}")

if 'key_pool_providers' in tables:
    print("✅ key_pool_providers 表存在")
else:
    print("❌ key_pool_providers 表不存在")

if 'key_pools' in tables:
    print("✅ key_pools 表存在")
else:
    print("❌ key_pools 表不存在")

if 'key_allocations' in tables:
    print("✅ key_allocations 表存在")
else:
    print("❌ key_allocations 表不存在")
