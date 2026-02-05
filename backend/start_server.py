#!/usr/bin/env python3
"""
启动服务器并检查路由
"""
import uvicorn
from main import app

if __name__ == "__main__":
    print("启动服务器...")
    print(f"已注册路由数量: {len(app.routes)}")

    # 打印所有路由
    for i, route in enumerate(app.routes[:10]):  # 只显示前10个
        if hasattr(route, 'path'):
            methods = getattr(route, 'methods', 'UNKNOWN')
            print(f"{i+1}. {methods} {route.path}")

    print("\n启动服务器在 http://0.0.0.0:18016")
    uvicorn.run(app, host="0.0.0.0", port=18016)
