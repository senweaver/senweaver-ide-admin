"""
管理员认证和管理API
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete, desc, and_
from pydantic import BaseModel

from src.core.database import get_db
from src.models.models import Article, Comment, Subscriber, ConnectionLog, DailyStats, ArticleStatus as DBArticleStatus, AdminUser

router = APIRouter(prefix="/api/admin", tags=["Admin"])
security = HTTPBearer()

# 会话存储
active_sessions = {}

# 默认管理员配置
DEFAULT_ADMIN = {
    "username": os.getenv("DEFAULT_ADMIN_USERNAME", "").strip(),
    "password": os.getenv("DEFAULT_ADMIN_PASSWORD", ""),
    "name": os.getenv("DEFAULT_ADMIN_NAME", "超级管理员"),
    "role": "super_admin",
}

async def init_default_admin(db: AsyncSession):
    """初始化默认管理员账号"""
    await db.execute(delete(AdminUser).where(func.length(func.trim(AdminUser.username)) == 0))
    await db.commit()

    if not DEFAULT_ADMIN["username"] or not DEFAULT_ADMIN["password"]:
        return

    result = await db.execute(select(AdminUser).where(AdminUser.username == DEFAULT_ADMIN["username"]))
    if result.scalar_one_or_none():
        return

    admin = AdminUser(
        username=DEFAULT_ADMIN["username"],
        password_hash=hashlib.sha256(DEFAULT_ADMIN["password"].encode()).hexdigest(),
        name=DEFAULT_ADMIN["name"],
        role=DEFAULT_ADMIN["role"],
    )
    db.add(admin)
    await db.commit()
    print(f"默认管理员已创建: {DEFAULT_ADMIN['username']}")


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    user: Optional[dict] = None
    message: str


class AdminStatsResponse(BaseModel):
    total_articles: int
    published_articles: int
    draft_articles: int
    total_comments: int
    pending_comments: int
    total_subscribers: int
    active_subscribers: int
    today_connections: int
    online_users: int


def verify_admin_token(token: str) -> Optional[dict]:
    """验证管理员令牌 (用于WebSocket等非HTTP Bearer场景)"""
    if token not in active_sessions:
        return None
    
    session = active_sessions[token]
    if datetime.now() > session["expires_at"]:
        del active_sessions[token]
        return None
    
    return session


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证管理员令牌"""
    token = credentials.credentials
    if token not in active_sessions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的令牌"
        )
    
    session = active_sessions[token]
    if datetime.now() > session["expires_at"]:
        del active_sessions[token]
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌已过期"
        )
    
    return session


@router.post("/login", response_model=LoginResponse)
async def admin_login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """管理员登录"""
    # 初始化默认管理员
    await init_default_admin(db)
    
    username = request.username
    password_hash = hashlib.sha256(request.password.encode()).hexdigest()
    
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    user = result.scalar_one_or_none()
    
    if not user or user.password_hash != password_hash:
        return LoginResponse(success=False, message="用户名或密码错误")
    
    if not user.is_active:
        return LoginResponse(success=False, message="账号已被禁用")
    
    # 更新登录时间
    user.last_login_at = datetime.now()
    await db.commit()
    
    # 生成令牌
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(hours=24)
    
    active_sessions[token] = {
        "user_id": user.id,
        "username": user.username,
        "name": user.name,
        "role": user.role,
        "expires_at": expires_at
    }
    
    return LoginResponse(
        success=True,
        token=token,
        user={"username": user.username, "name": user.name, "role": user.role},
        message="登录成功"
    )


@router.post("/logout")
async def admin_logout(session: dict = Depends(verify_token)):
    """管理员登出"""
    # 从活跃会话中移除
    for token, sess in list(active_sessions.items()):
        if sess["username"] == session["username"]:
            del active_sessions[token]
            break
    
    return {"success": True, "message": "已登出"}


@router.get("/me")
async def get_current_admin(session: dict = Depends(verify_token)):
    """获取当前管理员信息"""
    return {
        "username": session["username"],
        "name": session["name"],
        "role": session["role"]
    }


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_stats(
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取管理后台统计数据"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 文章统计
    result = await db.execute(select(func.count(Article.id)))
    total_articles = result.scalar() or 0
    
    result = await db.execute(
        select(func.count(Article.id)).where(Article.status == DBArticleStatus.PUBLISHED)
    )
    published_articles = result.scalar() or 0
    
    result = await db.execute(
        select(func.count(Article.id)).where(Article.status == DBArticleStatus.DRAFT)
    )
    draft_articles = result.scalar() or 0
    
    # 评论统计
    result = await db.execute(select(func.count(Comment.id)))
    total_comments = result.scalar() or 0
    
    result = await db.execute(
        select(func.count(Comment.id)).where(Comment.is_approved == False)
    )
    pending_comments = result.scalar() or 0
    
    # 订阅者统计
    result = await db.execute(select(func.count(Subscriber.id)))
    total_subscribers = result.scalar() or 0
    
    result = await db.execute(
        select(func.count(Subscriber.id)).where(Subscriber.is_active == True)
    )
    active_subscribers = result.scalar() or 0
    
    # 连接统计
    result = await db.execute(
        select(func.count(ConnectionLog.id)).where(
            and_(
                ConnectionLog.action == "connect",
                ConnectionLog.created_at >= today
            )
        )
    )
    today_connections = result.scalar() or 0
    
    # 当前在线用户（从内存获取）
    from src.core.connection_manager import manager
    online_users = len(manager.active_connections)
    
    return AdminStatsResponse(
        total_articles=total_articles,
        published_articles=published_articles,
        draft_articles=draft_articles,
        total_comments=total_comments,
        pending_comments=pending_comments,
        total_subscribers=total_subscribers,
        active_subscribers=active_subscribers,
        today_connections=today_connections,
        online_users=online_users
    )


# ============ 文章管理 ============
@router.get("/articles")
async def get_admin_articles(
    page: int = 1,
    page_size: int = 20,
    size: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取文章列表（管理员）"""
    if size is not None:
        page_size = size
    if keyword and not search:
        search = keyword
    query = select(Article)
    
    if status:
        query = query.where(Article.status == DBArticleStatus(status))
    
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (Article.title.like(search_pattern)) |
            (Article.author.like(search_pattern))
        )

    if category:
        query = query.where(Article.category == category)
    
    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0
    
    # 分页
    query = query.order_by(desc(Article.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    articles = result.scalars().all()
    
    return {
        "items": [
            {
                "id": a.id,
                "title": a.title,
                "category": a.category,
                "author": a.author,
                "status": a.status.value,
                "view_count": a.views,
                "likes": a.likes,
                "created_at": a.created_at.isoformat(),
                "updated_at": a.updated_at.isoformat()
            }
            for a in articles
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/articles/categories")
async def get_article_categories(session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Article.category).distinct().order_by(Article.category))
    cats = [r[0] for r in result.all() if r and r[0]]
    return cats


class ArticleCreate(BaseModel):
    title: str
    category: str
    excerpt: Optional[str] = None
    content: Optional[str] = None
    author: str


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    author: Optional[str] = None
    status: Optional[str] = None


@router.get("/articles/{article_id}")
async def get_admin_article(article_id: int, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Article).where(Article.id == article_id))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="文章不存在")
    return {
        "id": a.id,
        "title": a.title,
        "category": a.category,
        "excerpt": a.excerpt,
        "content": a.content,
        "author": a.author,
        "status": a.status.value,
        "view_count": a.views,
        "likes": a.likes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


@router.post("/articles")
async def create_admin_article(data: ArticleCreate, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    from src.models.models import ArticleStatus
    a = Article(
        title=data.title,
        category=data.category,
        excerpt=data.excerpt,
        content=data.content,
        author=data.author,
        author_initial=(data.author[:1] if data.author else None),
        status=ArticleStatus.DRAFT,
        published_at=None,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return {"id": a.id}


@router.put("/articles/{article_id}")
async def update_admin_article(article_id: int, data: ArticleUpdate, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Article).where(Article.id == article_id))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="文章不存在")

    if data.title is not None:
        a.title = data.title
    if data.category is not None:
        a.category = data.category
    if data.excerpt is not None:
        a.excerpt = data.excerpt
    if data.content is not None:
        a.content = data.content
    if data.author is not None:
        a.author = data.author
        a.author_initial = data.author[:1] if data.author else None
    if data.status is not None:
        a.status = DBArticleStatus(data.status)

    await db.commit()
    return {"success": True}


@router.post("/articles/{article_id}/publish")
async def publish_admin_article(article_id: int, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    from src.models.models import ArticleStatus
    result = await db.execute(select(Article).where(Article.id == article_id))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="文章不存在")
    a.status = ArticleStatus.PUBLISHED
    a.published_at = datetime.now()
    await db.commit()
    return {"success": True}


@router.delete("/articles/{article_id}")
async def delete_admin_article(
    article_id: int,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """删除文章"""
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    await db.delete(article)
    await db.commit()
    
    return {"success": True, "message": "文章已删除"}


# ============ 评论管理 ============
@router.get("/comments")
async def get_admin_comments(
    page: int = 1,
    page_size: int = 20,
    size: Optional[int] = None,
    approved: Optional[bool] = None,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取评论列表"""
    if size is not None:
        page_size = size

    # 关联文章标题，满足前端展示
    query = select(Comment, Article.title).join(Article, Article.id == Comment.article_id)
    
    if approved is not None:
        query = query.where(Comment.is_approved == approved)
    
    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0
    
    # 分页
    query = query.order_by(desc(Comment.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    rows = result.all()
    
    return {
        "items": [
            {
                "id": c.id,
                "article_title": title,
                "author": c.author,
                "content": c.content,
                "status": "approved" if c.is_approved else "pending",
                "created_at": c.created_at.isoformat()
            }
            for c, title in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.put("/comments/{comment_id}/approve")
async def approve_comment(
    comment_id: int,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """审核通过评论"""
    await db.execute(
        update(Comment).where(Comment.id == comment_id).values(is_approved=True)
    )
    await db.commit()
    return {"success": True, "message": "评论已通过审核"}


@router.post("/comments/{comment_id}/approve")
async def approve_comment_post(comment_id: int, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """审核通过评论"""
    return await approve_comment(comment_id=comment_id, session=session, db=db)


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """删除评论"""
    await db.execute(delete(Comment).where(Comment.id == comment_id))
    await db.commit()
    return {"success": True, "message": "评论已删除"}


# ============ 订阅者管理 ============
@router.get("/subscribers")
async def get_subscribers(
    page: int = 1,
    page_size: int = 20,
    active: Optional[bool] = None,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取订阅者列表"""
    query = select(Subscriber)
    
    if active is not None:
        query = query.where(Subscriber.is_active == active)
    
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0
    
    query = query.order_by(desc(Subscriber.subscribed_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    subscribers = result.scalars().all()
    
    return {
        "items": [
            {
                "id": s.id,
                "email": s.email,
                "is_active": s.is_active,
                "subscribed_at": s.subscribed_at.isoformat()
            }
            for s in subscribers
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


# ============ 连接日志 ============
@router.get("/connections")
async def get_connection_logs(
    page: int = 1,
    page_size: int = 50,
    action: Optional[str] = None,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取连接日志"""
    query = select(ConnectionLog)
    
    if action:
        query = query.where(ConnectionLog.action == action)
    
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0
    
    query = query.order_by(desc(ConnectionLog.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return {
        "items": [
            {
                "id": log.id,
                "client_id": log.client_id[:8] + "...",
                "user_id": log.user_id,
                "action": log.action,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


# ============ 交易记录 ============
@router.get("/transactions")
async def get_admin_transactions(
    page: int = 1,
    page_size: int = 20,
    size: Optional[int] = None,
    type: Optional[str] = None,
    user_id: Optional[int] = None,
    search: Optional[str] = None,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取交易记录列表"""
    from src.models.models import Transaction, TransactionType, User
    
    if size is not None:
        page_size = size
        
    query = select(Transaction, User).join(User, Transaction.user_id == User.id)
    
    if type:
        query = query.where(Transaction.type == TransactionType(type))
        
    if user_id:
        query = query.where(Transaction.user_id == user_id)
        
    if search:
        # Search by transaction no or user nickname/id
        query = query.where(
            (Transaction.transaction_no.like(f"%{search}%")) |
            (User.nickname.like(f"%{search}%")) |
            (User.user_id.like(f"%{search}%"))
        )
    
    # Count
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0
    
    # List
    query = query.order_by(desc(Transaction.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    rows = result.all()
    
    return {
        "items": [
            {
                "id": t.id,
                "transaction_no": t.transaction_no,
                "user_id": t.user_id,
                "user_name": u.nickname or u.user_id,
                "type": t.type.value,
                "amount": float(t.amount),
                "balance_before": float(t.balance_before),
                "balance_after": float(t.balance_after),
                "description": t.description,
                "remark": t.remark,
                "operator": t.operator,
                "created_at": t.created_at.isoformat()
            }
            for t, u in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


# ============ 仪表盘统计 ============
@router.get("/stats/dashboard")
async def get_dashboard_stats(
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取仪表盘统计数据"""
    from src.models.models import User, Order
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    result = await db.execute(select(func.count(User.id)))
    total_users = result.scalar() or 0
    
    result = await db.execute(select(func.sum(User.total_recharge)))
    total_recharge = result.scalar() or 0
    
    result = await db.execute(select(func.count(Article.id)))
    total_articles = result.scalar() or 0
    
    from src.core.connection_manager import manager
    online_count = len(manager.active_connections)
    
    result = await db.execute(select(Order).order_by(desc(Order.created_at)).limit(5))
    recent_orders = result.scalars().all()
    
    user_trend = []
    for i in range(7):
        day = today - timedelta(days=6-i)
        next_day = day + timedelta(days=1)
        result = await db.execute(
            select(func.count(User.id)).where(and_(User.first_seen_at >= day, User.first_seen_at < next_day))
        )
        user_trend.append({"date": day.strftime("%m-%d"), "count": result.scalar() or 0})
    
    return {
        "stats": {"total_users": total_users, "online_count": online_count, "total_recharge": float(total_recharge or 0), "total_articles": total_articles},
        "recent_orders": [{"id": o.id, "order_no": o.order_no, "amount": float(o.amount), "status": o.status.value if hasattr(o.status, 'value') else str(o.status)} for o in recent_orders],
        "user_trend": user_trend
    }


@router.get("/stats/users")
async def get_users_stats(session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    from src.models.models import User, UserStatus

    total = (await db.execute(select(func.count(User.id)))).scalar() or 0
    active = (await db.execute(select(func.count(User.id)).where(User.status == UserStatus.ACTIVE))).scalar() or 0
    vip = (await db.execute(select(func.count(User.id)).where(User.is_vip == True))).scalar() or 0

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    trend = []
    for i in range(7):
        day = today - timedelta(days=6 - i)
        next_day = day + timedelta(days=1)
        c = (await db.execute(select(func.count(User.id)).where(and_(User.first_seen_at >= day, User.first_seen_at < next_day)))).scalar() or 0
        trend.append({"date": day.strftime("%m-%d"), "count": c})

    return {"total": total, "active": active, "vip": vip, "trend": trend}


@router.get("/stats/orders")
async def get_orders_stats(session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    from src.models.models import Order, OrderStatus

    total = (await db.execute(select(func.count(Order.id)))).scalar() or 0
    pending = (await db.execute(select(func.count(Order.id)).where(Order.status == OrderStatus.PENDING))).scalar() or 0
    paid = (await db.execute(select(func.count(Order.id)).where(Order.status == OrderStatus.PAID))).scalar() or 0
    refunded = (await db.execute(select(func.count(Order.id)).where(Order.status == OrderStatus.REFUNDED))).scalar() or 0
    total_amount = (await db.execute(select(func.sum(Order.amount)))).scalar() or 0

    return {
        "total": total,
        "pending": pending,
        "paid": paid,
        "refunded": refunded,
        "total_amount": float(total_amount or 0)
    }


@router.get("/logs")
async def get_logs(page: int = 1, size: int = 20, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """获取连接日志"""
    query = select(ConnectionLog)
    result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = result.scalar() or 0
    result = await db.execute(query.order_by(desc(ConnectionLog.created_at)).offset((page - 1) * size).limit(size))
    logs = result.scalars().all()
    return {"items": [{"id": l.id, "user_id": l.user_id or l.client_id[:12], "action": l.action, "ip": l.ip_address, "user_agent": l.user_agent or "", "created_at": l.created_at.isoformat()} for l in logs], "total": total}


@router.get("/transactions")
async def get_transactions(page: int = 1, size: int = 20, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """获取交易记录"""
    from models import Transaction
    query = select(Transaction)
    result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = result.scalar() or 0
    result = await db.execute(query.order_by(desc(Transaction.created_at)).offset((page - 1) * size).limit(size))
    txs = result.scalars().all()
    return {"items": [{"id": t.id, "user_id": t.user_id, "type": t.type.value if hasattr(t.type, 'value') else str(t.type), "amount": float(t.amount), "balance_after": float(t.balance_after), "remark": t.remark or "", "created_at": t.created_at.isoformat()} for t in txs], "total": total}


# ============ 充值套餐管理 ============
from src.models.models import RechargePackage

class PackageCreate(BaseModel):
    name: str
    price: float
    amount: float = None
    bonus: float = 0
    is_hot: bool = False

@router.get("/packages")
async def get_packages(session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """获取充值套餐列表"""
    result = await db.execute(select(RechargePackage).order_by(RechargePackage.sort_order))
    packages = result.scalars().all()
    return [{"id": p.id, "name": p.name, "price": float(p.price), "amount": float(p.price), "bonus": float(p.bonus_amount or 0), "is_hot": p.is_hot, "is_active": p.is_active} for p in packages]

@router.post("/packages")
async def create_package(data: PackageCreate, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """创建充值套餐"""
    pkg = RechargePackage(name=data.name, price=data.price, bonus_amount=data.bonus, is_hot=data.is_hot)
    db.add(pkg)
    await db.commit()
    await db.refresh(pkg)
    return {"id": pkg.id, "name": pkg.name, "price": float(pkg.price)}

@router.put("/packages/{pkg_id}")
async def update_package(pkg_id: int, data: PackageCreate, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """更新充值套餐"""
    result = await db.execute(select(RechargePackage).where(RechargePackage.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(status_code=404, detail="套餐不存在")
    pkg.name = data.name
    pkg.price = data.price
    pkg.bonus_amount = data.bonus
    pkg.is_hot = data.is_hot
    await db.commit()
    return {"success": True}

@router.delete("/packages/{pkg_id}")
async def delete_package(pkg_id: int, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """删除充值套餐"""
    result = await db.execute(select(RechargePackage).where(RechargePackage.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(status_code=404, detail="套餐不存在")
    await db.delete(pkg)
    await db.commit()
    return {"success": True}


# ============ 管理员管理 ============
class AdminCreate(BaseModel):
    username: str
    password: str
    name: str
    email: Optional[str] = None

class AdminUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

@router.get("/admins")
async def get_admins(session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """获取管理员列表"""
    await db.execute(delete(AdminUser).where(func.length(func.trim(AdminUser.username)) == 0))
    await db.commit()
    result = await db.execute(select(AdminUser).order_by(desc(AdminUser.created_at)))
    admins = result.scalars().all()
    return {"items": [{"id": a.id, "username": a.username, "name": a.name, "role": a.role, "email": a.email, "is_active": a.is_active, "last_login_at": a.last_login_at.isoformat() if a.last_login_at else None, "created_at": a.created_at.isoformat() if a.created_at else None} for a in admins], "total": len(admins)}

@router.post("/admins")
async def create_admin(data: AdminCreate, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """创建管理员"""
    username = (data.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if not data.password:
        raise HTTPException(status_code=400, detail="密码不能为空")
    if not (data.name or "").strip():
        raise HTTPException(status_code=400, detail="姓名不能为空")

    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")
    admin = AdminUser(
        username=username,
        password_hash=hashlib.sha256(data.password.encode()).hexdigest(),
        name=data.name.strip(),
        email=data.email,
        role="admin",
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return {"success": True, "id": admin.id, "username": admin.username}

@router.get("/admins/{admin_id}")
async def get_admin(admin_id: int, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """获取管理员详情"""
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=404, detail="管理员不存在")
    return {"id": admin.id, "username": admin.username, "name": admin.name, "role": admin.role, "email": admin.email, "is_active": admin.is_active}

@router.put("/admins/{admin_id}")
async def update_admin(admin_id: int, data: AdminUpdate, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """更新管理员信息"""
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=404, detail="管理员不存在")
    if data.name is not None:
        admin.name = data.name
    if data.email is not None:
        admin.email = data.email
    if data.password is not None:
        admin.password_hash = hashlib.sha256(data.password.encode()).hexdigest()
    if data.is_active is not None:
        admin.is_active = data.is_active
    await db.commit()
    return {"success": True}

@router.delete("/admins/{admin_id}")
async def delete_admin(admin_id: int, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """删除管理员"""
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=404, detail="管理员不存在")
    if admin.role == "super_admin":
        raise HTTPException(status_code=400, detail="不能删除超级管理员")
    await db.delete(admin)
    await db.commit()
    return {"success": True}

@router.post("/change-password")
async def change_password(data: PasswordChange, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """修改密码"""
    admin = None
    user_id = session.get("user_id")
    if user_id:
        result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
        admin = result.scalar_one_or_none()

    # 兼容旧token：早期会话里没有user_id
    if not admin:
        username = session.get("username")
        if username:
            result = await db.execute(select(AdminUser).where(AdminUser.username == username))
            admin = result.scalar_one_or_none()

    if not admin:
        raise HTTPException(status_code=404, detail="用户不存在")
    old_hash = hashlib.sha256(data.old_password.encode()).hexdigest()
    if admin.password_hash != old_hash:
        raise HTTPException(status_code=400, detail="原密码错误")
    admin.password_hash = hashlib.sha256(data.new_password.encode()).hexdigest()
    await db.commit()
    return {"success": True, "message": "密码修改成功"}


# ============ IDE版本管理 ============
from src.models.models import IDEVersion
from pathlib import Path
import shutil
import aiofiles
from fastapi import UploadFile, File, Form

DOWNLOAD_DIR = Path(__file__).parent.parent / "download"

def ensure_update_log(version_dir: Path, content: Optional[str] = None) -> Path:
    """确保版本目录下存在UpdateLog.md"""
    version_dir.mkdir(parents=True, exist_ok=True)
    changelog_path = version_dir / "UpdateLog.md"
    if not changelog_path.exists():
        changelog_path.write_text(content or "", encoding="utf-8")
    return changelog_path

class VersionCreate(BaseModel):
    version: str
    description: Optional[str] = None
    changelog: Optional[str] = None
    is_latest: bool = False
    external_url: Optional[str] = None

class VersionUpdate(BaseModel):
    description: Optional[str] = None
    changelog: Optional[str] = None
    is_latest: Optional[bool] = None
    is_active: Optional[bool] = None
    external_url: Optional[str] = None

@router.get("/versions")
async def get_versions(session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """获取IDE版本列表"""
    result = await db.execute(select(IDEVersion).order_by(desc(IDEVersion.created_at)))
    versions = result.scalars().all()
    return {"items": [{"id": v.id, "version": v.version, "filename": v.filename, "file_size": v.file_size, "changelog": v.changelog, "description": v.description, "is_latest": v.is_latest, "is_active": v.is_active, "download_count": v.download_count, "external_url": v.external_url, "created_at": v.created_at.isoformat() if v.created_at else None, "published_at": v.published_at.isoformat() if v.published_at else None} for v in versions], "total": len(versions)}

@router.post("/versions")
async def create_version(data: VersionCreate, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """创建新版本"""
    existing = await db.execute(select(IDEVersion).where(IDEVersion.version == data.version))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="版本号已存在")
    
    if data.is_latest:
        await db.execute(update(IDEVersion).values(is_latest=False))
    
    version = IDEVersion(version=data.version, description=data.description, changelog=data.changelog, is_latest=data.is_latest, external_url=data.external_url)
    db.add(version)
    await db.commit()
    await db.refresh(version)

    if data.is_latest:
        from src.core.connection_manager import manager
        await manager.trigger_version_update(version.version)
    
    version_dir = DOWNLOAD_DIR / data.version
    version_dir.mkdir(parents=True, exist_ok=True)

    # 确保更新日志文件存在（客户端/其他接口依赖）
    ensure_update_log(version_dir, data.changelog)
    
    return {"id": version.id, "version": version.version}

@router.get("/versions/{version_id}")
async def get_version(version_id: int, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """获取版本详情"""
    result = await db.execute(select(IDEVersion).where(IDEVersion.id == version_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {"id": v.id, "version": v.version, "filename": v.filename, "file_size": v.file_size, "file_path": v.file_path, "changelog": v.changelog, "description": v.description, "is_latest": v.is_latest, "is_active": v.is_active, "download_count": v.download_count, "external_url": v.external_url, "created_at": v.created_at.isoformat() if v.created_at else None}

@router.put("/versions/{version_id}")
async def update_version(version_id: int, data: VersionUpdate, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """更新版本信息"""
    result = await db.execute(select(IDEVersion).where(IDEVersion.id == version_id))
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    if data.is_latest:
        await db.execute(update(IDEVersion).values(is_latest=False))
    
    if data.description is not None:
        version.description = data.description
    if data.changelog is not None:
        version.changelog = data.changelog
        changelog_path = DOWNLOAD_DIR / version.version / "UpdateLog.md"
        changelog_path.parent.mkdir(parents=True, exist_ok=True)
        changelog_path.write_text(data.changelog, encoding="utf-8")
    if data.is_latest is not None:
        version.is_latest = data.is_latest
    if data.is_active is not None:
        version.is_active = data.is_active
    if data.external_url is not None:
        version.external_url = data.external_url
    
    await db.commit()

    if data.is_latest:
        from src.core.connection_manager import manager
        await manager.trigger_version_update(version.version)

    return {"success": True}

@router.delete("/versions/{version_id}")
async def delete_version(version_id: int, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """删除版本"""
    result = await db.execute(select(IDEVersion).where(IDEVersion.id == version_id))
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    version_dir = DOWNLOAD_DIR / version.version
    if version_dir.exists():
        shutil.rmtree(version_dir)
    
    await db.delete(version)
    await db.commit()
    return {"success": True}

@router.post("/versions/{version_id}/upload")
async def upload_version_file(version_id: int, file: UploadFile = File(...), session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """上传版本安装包"""
    result = await db.execute(select(IDEVersion).where(IDEVersion.id == version_id))
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    version_dir = DOWNLOAD_DIR / version.version
    version_dir.mkdir(parents=True, exist_ok=True)

    # 确保更新日志文件存在（若尚未编辑日志，也要生成空文件）
    ensure_update_log(version_dir, version.changelog)
    
    file_path = version_dir / file.filename
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    version.filename = file.filename
    version.file_size = len(content)
    version.file_path = str(file_path)
    version.published_at = datetime.now()
    await db.commit()
    
    return {"success": True, "filename": file.filename, "size": len(content)}

@router.post("/versions/{version_id}/set-latest")
async def set_latest_version(version_id: int, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """设置为最新版本"""
    result = await db.execute(select(IDEVersion).where(IDEVersion.id == version_id))
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    await db.execute(update(IDEVersion).values(is_latest=False))
    version.is_latest = True
    await db.commit()

    # 立即广播新版本
    from src.core.connection_manager import manager
    await manager.trigger_version_update(version.version)

    return {"success": True}
