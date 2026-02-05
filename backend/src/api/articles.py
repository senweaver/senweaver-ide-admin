"""
文章管理API路由
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, desc
from sqlalchemy.orm import selectinload

from src.core.database import get_db
from src.models.models import Transaction, TransactionType, User, Article, Comment, ArticleStatus as DBArticleStatus, Subscriber
from src.schemas.schemas import (
    ArticleCreate, ArticleUpdate, ArticleResponse, ArticleListResponse,
    CommentCreate, CommentResponse, SubscribeRequest, SubscribeResponse
)

router = APIRouter(prefix="/api/blog", tags=["Blog"])


def format_date(dt: datetime) -> str:
    """格式化日期"""
    return dt.strftime("%Y-%m-%d")


def format_relative_time(dt: datetime) -> str:
    """格式化相对时间"""
    now = datetime.now()
    diff = now - dt
    
    if diff.days > 30:
        return dt.strftime("%Y年%m月%d日")
    elif diff.days > 0:
        return f"{diff.days}天前"
    elif diff.seconds >= 3600:
        return f"{diff.seconds // 3600}小时前"
    elif diff.seconds >= 60:
        return f"{diff.seconds // 60}分钟前"
    else:
        return "刚刚"


# ============ 文章API ============
@router.get("/posts", response_model=List[ArticleListResponse])
async def get_posts(
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取文章列表"""
    query = select(Article).where(Article.status == DBArticleStatus.PUBLISHED)
    
    if category:
        query = query.where(Article.category == category)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (Article.title.like(search_pattern)) |
            (Article.excerpt.like(search_pattern))
        )
    
    query = query.order_by(desc(Article.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    articles = result.scalars().all()
    
    return [
        ArticleListResponse(
            id=article.id,
            title=article.title,
            excerpt=article.excerpt,
            category=article.category,
            icon=article.icon or "fas fa-file-alt",
            author=article.author,
            authorInitial=article.author_initial or article.author[0] if article.author else "A",
            date=format_date(article.created_at),
            views=article.views,
            likes=article.likes
        )
        for article in articles
    ]


@router.get("/posts/{post_id}", response_model=ArticleResponse)
async def get_post(post_id: int, db: AsyncSession = Depends(get_db)):
    """获取单篇文章"""
    result = await db.execute(
        select(Article).where(Article.id == post_id)
    )
    article = result.scalar_one_or_none()
    
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    # 增加浏览量
    await db.execute(
        update(Article).where(Article.id == post_id).values(views=Article.views + 1)
    )
    await db.commit()
    
    return article


@router.post("/posts", response_model=ArticleResponse)
async def create_post(article: ArticleCreate, db: AsyncSession = Depends(get_db)):
    """创建文章"""
    db_article = Article(
        title=article.title,
        excerpt=article.excerpt,
        content=article.content,
        category=article.category,
        icon=article.icon,
        author=article.author,
        author_initial=article.author_initial or (article.author[0] if article.author else "A"),
        status=DBArticleStatus(article.status.value),
        read_time=article.read_time,
        tags=article.tags,
        published_at=datetime.now() if article.status == "published" else None
    )
    
    db.add(db_article)
    await db.commit()
    await db.refresh(db_article)
    
    return db_article


@router.put("/posts/{post_id}", response_model=ArticleResponse)
async def update_post(post_id: int, article: ArticleUpdate, db: AsyncSession = Depends(get_db)):
    """更新文章"""
    result = await db.execute(
        select(Article).where(Article.id == post_id)
    )
    db_article = result.scalar_one_or_none()
    
    if not db_article:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    update_data = article.model_dump(exclude_unset=True)
    
    if "status" in update_data:
        update_data["status"] = DBArticleStatus(update_data["status"].value)
        if update_data["status"] == DBArticleStatus.PUBLISHED and not db_article.published_at:
            update_data["published_at"] = datetime.now()
    
    for key, value in update_data.items():
        setattr(db_article, key, value)
    
    await db.commit()
    await db.refresh(db_article)
    
    return db_article


@router.delete("/posts/{post_id}")
async def delete_post(post_id: int, db: AsyncSession = Depends(get_db)):
    """删除文章"""
    result = await db.execute(
        select(Article).where(Article.id == post_id)
    )
    db_article = result.scalar_one_or_none()
    
    if not db_article:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    await db.delete(db_article)
    await db.commit()
    
    return {"success": True, "message": "文章已删除"}


@router.post("/posts/{post_id}/like")
async def like_post(post_id: int, db: AsyncSession = Depends(get_db)):
    """点赞文章"""
    result = await db.execute(
        select(Article).where(Article.id == post_id)
    )
    article = result.scalar_one_or_none()
    
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    await db.execute(
        update(Article).where(Article.id == post_id).values(likes=Article.likes + 1)
    )
    await db.commit()
    
    return {"success": True, "likes": article.likes + 1}


# ============ 分类API ============
@router.get("/categories")
async def get_categories(db: AsyncSession = Depends(get_db)):
    """获取所有分类"""
    result = await db.execute(
        select(Article.category, func.count(Article.id).label("count"))
        .where(Article.status == DBArticleStatus.PUBLISHED)
        .group_by(Article.category)
    )
    categories = result.all()
    
    return [
        {"name": cat.category, "count": cat.count}
        for cat in categories
    ]


# ============ 评论API ============
@router.get("/posts/{post_id}/comments", response_model=List[CommentResponse])
async def get_comments(post_id: int, db: AsyncSession = Depends(get_db)):
    """获取文章评论"""
    result = await db.execute(
        select(Comment)
        .where(Comment.article_id == post_id, Comment.is_approved == True)
        .order_by(desc(Comment.created_at))
    )
    comments = result.scalars().all()
    
    return [
        CommentResponse(
            id=comment.id,
            article_id=comment.article_id,
            content=comment.content,
            author=comment.author,
            author_initial=comment.author_initial or comment.author[0],
            likes=comment.likes,
            parent_id=comment.parent_id,
            created_at=comment.created_at,
            time=format_relative_time(comment.created_at)
        )
        for comment in comments
    ]


@router.post("/posts/{post_id}/comments", response_model=CommentResponse)
async def create_comment(post_id: int, comment: CommentCreate, db: AsyncSession = Depends(get_db)):
    """创建评论"""
    # 验证文章存在
    result = await db.execute(
        select(Article).where(Article.id == post_id)
    )
    article = result.scalar_one_or_none()
    
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    db_comment = Comment(
        article_id=post_id,
        content=comment.content,
        author=comment.author,
        author_initial=comment.author_initial or comment.author[0],
        parent_id=comment.parent_id
    )
    
    db.add(db_comment)
    await db.commit()
    await db.refresh(db_comment)
    
    return CommentResponse(
        id=db_comment.id,
        article_id=db_comment.article_id,
        content=db_comment.content,
        author=db_comment.author,
        author_initial=db_comment.author_initial,
        likes=db_comment.likes,
        parent_id=db_comment.parent_id,
        created_at=db_comment.created_at,
        time=format_relative_time(db_comment.created_at)
    )


@router.post("/comments/{comment_id}/like")
async def like_comment(comment_id: int, db: AsyncSession = Depends(get_db)):
    """点赞评论"""
    result = await db.execute(
        select(Comment).where(Comment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")
    
    await db.execute(
        update(Comment).where(Comment.id == comment_id).values(likes=Comment.likes + 1)
    )
    await db.commit()
    
    return {"success": True, "likes": comment.likes + 1}


# ============ 订阅API ============
@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(request: SubscribeRequest, db: AsyncSession = Depends(get_db)):
    """订阅邮件"""
    # 检查是否已订阅
    result = await db.execute(
        select(Subscriber).where(Subscriber.email == request.email)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        if existing.is_active:
            return SubscribeResponse(success=True, message="您已经订阅了我们的邮件")
        else:
            # 重新激活订阅
            existing.is_active = True
            existing.unsubscribed_at = None
            await db.commit()
            return SubscribeResponse(success=True, message="订阅已重新激活")
    
    # 创建新订阅
    subscriber = Subscriber(email=request.email)
    db.add(subscriber)
    await db.commit()
    
    return SubscribeResponse(success=True, message="订阅成功！感谢您的关注")
