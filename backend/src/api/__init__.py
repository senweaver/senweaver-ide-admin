"""
路由模块
"""
from .articles import router as articles_router
from .stats import router as stats_router
from .admin import router as admin_router
from .users import router as users_router
from .orders import router as orders_router

__all__ = ["articles_router", "stats_router", "admin_router", "users_router", "orders_router"]
