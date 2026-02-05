"""
Pydantic数据模型（请求/响应）
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr
from enum import Enum


class ArticleStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


# ============ 文章相关 ============
class ArticleBase(BaseModel):
    title: str
    excerpt: Optional[str] = None
    content: Optional[str] = None
    category: str
    icon: Optional[str] = "fas fa-file-alt"
    author: str
    author_initial: Optional[str] = None
    read_time: Optional[str] = "5分钟阅读"
    tags: Optional[str] = None


class ArticleCreate(ArticleBase):
    status: Optional[ArticleStatus] = ArticleStatus.PUBLISHED


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    author: Optional[str] = None
    author_initial: Optional[str] = None
    status: Optional[ArticleStatus] = None
    read_time: Optional[str] = None
    tags: Optional[str] = None


class ArticleResponse(ArticleBase):
    id: int
    status: ArticleStatus
    views: int
    likes: int
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ArticleListResponse(BaseModel):
    id: int
    title: str
    excerpt: Optional[str] = None
    category: str
    icon: str
    author: str
    authorInitial: Optional[str] = None
    date: str
    views: int
    likes: int

    class Config:
        from_attributes = True


# ============ 评论相关 ============
class CommentBase(BaseModel):
    content: str
    author: str
    author_initial: Optional[str] = None


class CommentCreate(CommentBase):
    article_id: int
    parent_id: Optional[int] = None


class CommentResponse(CommentBase):
    id: int
    article_id: int
    likes: int
    parent_id: Optional[int] = None
    created_at: datetime
    time: str  # 格式化的时间字符串

    class Config:
        from_attributes = True


# ============ 用户统计相关 ============
class ConnectionStats(BaseModel):
    total_clients: int
    online_clients: int
    offline_clients: int
    active_connections: int


class DailyStatsResponse(BaseModel):
    date: str
    total_connections: int
    unique_users: int
    peak_concurrent: int
    total_duration_seconds: int
    new_users: int
    returning_users: int


class UserStatsOverview(BaseModel):
    today_connections: int
    today_unique_users: int
    today_peak_concurrent: int
    total_connections: int
    total_unique_users: int
    average_duration_minutes: float


class ClientResponse(BaseModel):
    client_id: str
    user_id: Optional[str] = None
    connect_time: str
    last_heartbeat: str
    is_online: bool


# ============ 订阅相关 ============
class SubscribeRequest(BaseModel):
    email: EmailStr


class SubscribeResponse(BaseModel):
    success: bool
    message: str


# ============ 通用响应 ============
class SuccessResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: Optional[str] = None


class PaginatedResponse(BaseModel):
    items: List
    total: int
    page: int
    page_size: int
    total_pages: int
