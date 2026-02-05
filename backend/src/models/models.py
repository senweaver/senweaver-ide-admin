"""
数据库模型定义
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index, Enum as SQLEnum, DECIMAL, BigInteger
from sqlalchemy.orm import relationship
from src.core.database import Base
import enum


class ArticleStatus(enum.Enum):
    """文章状态"""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class UserStatus(enum.Enum):
    """用户状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"
    DELETED = "deleted"


class OrderStatus(enum.Enum):
    """订单状态"""
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class TransactionType(enum.Enum):
    """交易类型"""
    RECHARGE = "recharge"       # 充值
    CONSUME = "consume"         # 消费
    REFUND = "refund"           # 退款
    GIFT = "gift"               # 赠送
    ADJUSTMENT = "adjustment"   # 调整


class PaymentMethod(enum.Enum):
    """支付方式"""
    ALIPAY = "alipay"
    WECHAT = "wechat"
    BALANCE = "balance"
    ADMIN = "admin"  # 管理员操作


# ============ 用户相关模型 ============
class User(Base):
    """用户模型 - WebSocket连接的用户"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), unique=True, nullable=False, index=True)  # WebSocket传入的user_id
    nickname = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(20), nullable=True, index=True)
    avatar = Column(String(500), nullable=True)
    
    # 余额相关
    balance = Column(DECIMAL(10, 2), default=0.00)  # 账户余额
    total_recharge = Column(DECIMAL(10, 2), default=0.00)  # 总充值金额
    total_consume = Column(DECIMAL(10, 2), default=0.00)  # 总消费金额
    
    # 使用统计
    total_connections = Column(Integer, default=0)  # 总连接次数
    total_online_duration = Column(BigInteger, default=0)  # 总在线时长（秒）
    total_messages = Column(Integer, default=0)  # 总消息数
    total_api_calls = Column(Integer, default=0)  # 总API调用次数
    
    # 状态
    status = Column(SQLEnum(UserStatus), default=UserStatus.ACTIVE)
    is_vip = Column(Boolean, default=False)
    vip_expire_at = Column(DateTime, nullable=True)
    
    # 时间
    first_seen_at = Column(DateTime, default=datetime.now)  # 首次连接时间
    last_seen_at = Column(DateTime, default=datetime.now)   # 最后连接时间
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    usage_logs = relationship("UsageLog", back_populates="user", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_user_status', 'status'),
        Index('idx_user_last_seen', 'last_seen_at'),
    )


class Order(Base):
    """订单模型"""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(64), unique=True, nullable=False, index=True)  # 订单号
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # 订单信息
    order_type = Column(String(50), default="recharge")  # 订单类型：recharge充值, subscribe订阅, service服务
    product_name = Column(String(200), nullable=True)  # 商品名称
    product_desc = Column(String(500), nullable=True)  # 商品描述
    
    # 金额
    amount = Column(DECIMAL(10, 2), nullable=False)  # 订单金额
    paid_amount = Column(DECIMAL(10, 2), default=0.00)  # 实付金额
    discount_amount = Column(DECIMAL(10, 2), default=0.00)  # 优惠金额
    
    # 支付信息
    payment_method = Column(SQLEnum(PaymentMethod), nullable=True)
    payment_no = Column(String(100), nullable=True)  # 第三方支付单号
    paid_at = Column(DateTime, nullable=True)
    
    # 状态
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    remark = Column(String(500), nullable=True)
    
    # 时间
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    expired_at = Column(DateTime, nullable=True)  # 订单过期时间
    
    # 关联
    user = relationship("User", back_populates="orders")
    
    __table_args__ = (
        Index('idx_order_user_status', 'user_id', 'status'),
        Index('idx_order_created', 'created_at'),
    )


class Transaction(Base):
    """交易流水"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_no = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    
    # 交易信息
    type = Column(SQLEnum(TransactionType), nullable=False)
    amount = Column(DECIMAL(10, 2), nullable=False)  # 交易金额（正数增加，负数减少）
    balance_before = Column(DECIMAL(10, 2), nullable=False)  # 交易前余额
    balance_after = Column(DECIMAL(10, 2), nullable=False)   # 交易后余额
    
    # 描述
    description = Column(String(500), nullable=True)
    remark = Column(String(500), nullable=True)
    
    # 操作人
    operator = Column(String(100), nullable=True)  # 操作人（管理员操作时记录）
    
    created_at = Column(DateTime, default=datetime.now)
    
    # 关联
    user = relationship("User", back_populates="transactions")
    
    __table_args__ = (
        Index('idx_trans_user_type', 'user_id', 'type'),
        Index('idx_trans_created', 'created_at'),
    )


class UsageLog(Base):
    """使用记录日志"""
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    client_id = Column(String(100), nullable=False)
    
    # 使用类型
    usage_type = Column(String(50), nullable=False)  # api_call, message, connection, model_use等
    usage_detail = Column(String(200), nullable=True)  # 详细信息，如模型名称
    
    # 计费相关
    tokens_used = Column(Integer, default=0)  # 使用的token数
    cost = Column(DECIMAL(10, 4), default=0.0000)  # 费用
    
    # 请求信息
    request_ip = Column(String(50), nullable=True)
    request_duration = Column(Integer, default=0)  # 请求耗时（毫秒）
    
    created_at = Column(DateTime, default=datetime.now, index=True)
    
    # 关联
    user = relationship("User", back_populates="usage_logs")
    
    __table_args__ = (
        Index('idx_usage_user_type', 'user_id', 'usage_type'),
    )


class UserModelAccess(Base):
    __tablename__ = "user_model_access"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    enabled = Column(Boolean, default=True)
    usage_limit = Column(Integer, default=1000)
    used_count = Column(Integer, default=0)
    used_total = Column(Integer, default=0)  # 总使用量

    reset_period_days = Column(Integer, default=30)  # 重置周期（天）
    last_reset_time = Column(DateTime, default=datetime.now)  # 上次重置时间

    disabled_reason = Column(String(200), nullable=True)
    disabled_at = Column(DateTime, nullable=True)
    enabled_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User")

    __table_args__ = (
        Index("idx_model_access_enabled", "enabled"),
    )


class RechargePackage(Base):
    """充值套餐"""
    __tablename__ = "recharge_packages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    
    # 金额
    price = Column(DECIMAL(10, 2), nullable=False)  # 售价
    original_price = Column(DECIMAL(10, 2), nullable=True)  # 原价
    bonus_amount = Column(DECIMAL(10, 2), default=0.00)  # 赠送金额
    
    # 状态
    is_active = Column(Boolean, default=True)
    is_hot = Column(Boolean, default=False)  # 热门标记
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Article(Base):
    """文章模型"""
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False, index=True)
    excerpt = Column(String(500), nullable=True)
    content = Column(Text, nullable=True)
    category = Column(String(50), nullable=False, index=True)
    icon = Column(String(100), default="fas fa-file-alt")
    author = Column(String(100), nullable=False)
    author_initial = Column(String(10), nullable=True)
    status = Column(SQLEnum(ArticleStatus), default=ArticleStatus.PUBLISHED)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    read_time = Column(String(50), default="5分钟阅读")
    tags = Column(String(500), nullable=True)  # JSON格式存储标签
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    published_at = Column(DateTime, nullable=True)

    # 关联评论
    comments = relationship("Comment", back_populates="article", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_category_status', 'category', 'status'),
        Index('idx_created_at', 'created_at'),
    )


class Comment(Base):
    """评论模型"""
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False, index=True)
    author = Column(String(100), nullable=False)
    author_initial = Column(String(10), nullable=True)
    content = Column(Text, nullable=False)
    likes = Column(Integer, default=0)
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)  # 支持回复
    is_approved = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    # 关联
    article = relationship("Article", back_populates="comments")
    replies = relationship("Comment", backref="parent", remote_side=[id])


class ConnectionLog(Base):
    """WebSocket连接日志"""
    __tablename__ = "connection_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(100), nullable=True, index=True)
    action = Column(String(20), nullable=False)  # connect, disconnect, heartbeat
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('idx_client_action', 'client_id', 'action'),
    )


class DailyStats(Base):
    """每日统计数据"""
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, unique=True, index=True)
    total_connections = Column(Integer, default=0)
    unique_users = Column(Integer, default=0)
    peak_concurrent = Column(Integer, default=0)
    total_duration_seconds = Column(Integer, default=0)  # 总在线时长
    new_users = Column(Integer, default=0)
    returning_users = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class UserActivity(Base):
    """用户活动记录"""
    __tablename__ = "user_activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=True, index=True)
    client_id = Column(String(100), nullable=False)
    connect_time = Column(DateTime, nullable=False)
    disconnect_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, default=0)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_user_connect', 'user_id', 'connect_time'),
    )


class Subscriber(Base):
    """订阅者"""
    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    subscribed_at = Column(DateTime, default=datetime.now)
    unsubscribed_at = Column(DateTime, nullable=True)


class IDEVersion(Base):
    """IDE版本管理"""
    __tablename__ = "ide_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(50), nullable=False, unique=True, index=True)
    
    # 文件信息
    filename = Column(String(255), nullable=True)
    file_size = Column(Integer, default=0)
    file_path = Column(String(500), nullable=True)
    external_url = Column(String(500), nullable=True)  # 第三方下载链接
    
    # 更新日志
    changelog = Column(Text, nullable=True)
    
    # 版本信息
    description = Column(String(500), nullable=True)
    is_latest = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    download_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    published_at = Column(DateTime, nullable=True)


class AdminUser(Base):
    """管理员账号"""
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True, index=True)
    password_hash = Column(String(128), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(20), default="admin")
    email = Column(String(255), nullable=True)

    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class KeyPoolProvider(Base):
    """密钥池提供商"""
    __tablename__ = "key_pool_providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True, index=True)  # 提供商名称，如 "deepseek", "ownProvider"
    display_name = Column(String(100), nullable=False)  # 显示名称，如 "DeepSeek", "Own Provider"
    base_url = Column(String(500), nullable=True)  # 基础URL
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)  # 是否启用
    priority = Column(Integer, default=0)  # 优先级，越高越优先

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联
    key_pools = relationship("KeyPool", back_populates="provider", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_provider_active', 'is_active', 'priority'),
    )


class KeyPool(Base):
    """密钥池"""
    __tablename__ = "key_pools"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(Integer, ForeignKey("key_pool_providers.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # 密钥池名称
    description = Column(String(500), nullable=True)
    api_key = Column(String(500), nullable=False)  # API密钥
    is_active = Column(Boolean, default=True)  # 是否启用
    max_clients = Column(Integer, default=-1)  # 最大客户端数量，-1表示无限制
    current_clients = Column(Integer, default=0)  # 当前客户端数量

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联
    provider = relationship("KeyPoolProvider", back_populates="key_pools")
    allocations = relationship("KeyAllocation", back_populates="key_pool", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_pool_provider_active', 'provider_id', 'is_active'),
        Index('idx_pool_name', 'name'),
    )


class KeyAllocation(Base):
    """密钥分配记录"""
    __tablename__ = "key_allocations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_pool_id = Column(Integer, ForeignKey("key_pools.id"), nullable=False, index=True)
    client_id = Column(String(100), nullable=False, index=True)  # WebSocket客户端ID
    user_id = Column(String(100), nullable=True, index=True)  # 用户ID

    allocated_at = Column(DateTime, default=datetime.now)  # 分配时间
    released_at = Column(DateTime, nullable=True)  # 释放时间
    is_active = Column(Boolean, default=True)  # 是否活跃

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联
    key_pool = relationship("KeyPool", back_populates="allocations")

    __table_args__ = (
        Index('idx_alloc_client_active', 'client_id', 'is_active'),
        Index('idx_alloc_pool_active', 'key_pool_id', 'is_active'),
        Index('idx_alloc_user', 'user_id'),
    )
